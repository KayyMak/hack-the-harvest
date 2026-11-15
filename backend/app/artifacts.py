"""Read saved analysis outputs without importing or running the analysis stack."""
import csv
import json
import math
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from pydantic import ValidationError

from .schemas import (AsOfResults, Convergence, ConvergencePoint, ConvergenceYear, BaselineSummary, BarcField, DeclineRuleBaseline, Estimate2025, Observation, Prediction, QuickStatsRow,
    Rollup, YearRollup)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / 'baseline' / 'outputs'
FIELDS_GPKG = ROOT / 'BARC_Corn.2021-2023.gpkg'
FIELDS_TABLE = 'barc_silage_grain_corn20212023'


class ArtifactUnavailable(Exception):
    pass


def read_summary() -> BaselineSummary:
    try:
        return BaselineSummary.model_validate_json(
            (OUTPUT_DIR / 'metrics.json').read_text(encoding='utf-8'))
    except (OSError, ValueError, ValidationError) as exc:
        raise ArtifactUnavailable('Saved baseline metrics are missing or invalid.') from exc


def read_decline_rule() -> DeclineRuleBaseline:
    try:
        return DeclineRuleBaseline.model_validate_json(
            (OUTPUT_DIR / 'decline_rule' / 'metrics.json').read_text(encoding='utf-8'))
    except (OSError, ValueError, ValidationError) as exc:
        raise ArtifactUnavailable('Saved decline-rule baseline (baseline/outputs/decline_rule/metrics.json) '
            'is missing or invalid.') from exc


def read_predictions() -> list[Prediction]:
    try:
        with (OUTPUT_DIR / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as file:
            rows = list(csv.DictReader(file))
        if not rows:
            raise ValueError('Empty predictions file')
        return [Prediction(field_id=row['OBJECTID'], year=row['year'],
            reference_label=row['label'], predicted_label=row['predicted_label'],
            silage_probability=row['silage_probability'], fold=row['fold'],
            valid_dates=row['valid_dates']) for row in rows]
    except (OSError, ValueError, KeyError, ValidationError) as exc:
        raise ArtifactUnavailable('Saved baseline predictions are missing or invalid.') from exc


def read_asof() -> AsOfResults:
    """Saved mid-season calls, written once by `python -m harvest.export_asof` (never fitted here)."""
    try:
        return AsOfResults.model_validate_json((OUTPUT_DIR / 'asof.json').read_text(encoding='utf-8'))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ArtifactUnavailable('Saved as-of results are missing or invalid; run python -m harvest.export_asof.') from exc


def compute_convergence() -> Convergence:
    """Silage-acre estimate at each saved as-of date, per year, next to BARC reference acres.

    Same arithmetic as compute_rollup, applied to the saved as-of calls: expected = sum(p * acres),
    95% interval from independent Bernoulli variance. The interval reflects the model's own
    probabilities only; it does not include error in the probabilities themselves.
    """
    acres = {f.field_id: f.acres for f in read_fields()}
    results = read_asof()
    by_year: dict[int, list[ConvergencePoint]] = {}
    for d in sorted(results.dates, key=lambda x: (x.year, x.as_of)):
        known = [(p, acres[p.field_id]) for p in d.predictions if acres.get(p.field_id) is not None]
        if not known:
            raise ArtifactUnavailable(f'No scored fields with known acreage for {d.as_of}; '
                                      'the silage-acre estimate is unavailable.')
        expected = sum(p.silage_probability * a for p, a in known)
        sd = math.sqrt(sum(a * a * p.silage_probability * (1 - p.silage_probability) for p, a in known))
        by_year.setdefault(d.year, []).append(ConvergencePoint(as_of=d.as_of, mode=d.mode,
            field_years=len(d.predictions), expected_silage_acres=round(expected, 2),
            expected_silage_acres_95ci=(round(max(0.0, expected - 1.96 * sd), 2), round(expected + 1.96 * sd, 2)),
            cv_percent=round(100 * sd / expected, 1) if expected else None,
            predicted_silage_acres=round(sum(a for p, a in known if p.predicted_label == 'Silage'), 2),
            reference_silage_acres=round(sum(a for p, a in known if p.reference_label == 'Silage'), 2),
            total_acres=round(sum(a for _, a in known), 2),
            missing_acres_field_years=len(d.predictions) - len(known)))
    return Convergence(scope='Labeled BARC field-years only; not a Maryland statewide estimate',
        method=('expected = sum(p_silage * acres) from the saved as-of calls; 95% interval and CV% from '
                'independent Bernoulli variance, as in /api/baseline/rollup'),
        years=[ConvergenceYear(year=y, points=pts) for y, pts in sorted(by_year.items())])


def read_estimate_2025() -> Estimate2025:
    """Saved 2025 Maryland estimate, written offline by baseline/estimate_2025 (never computed here).
    benchmark.json is the unmodified `python -m harvest.benchmark` report; null when it was not saved."""
    directory = OUTPUT_DIR / 'estimate_2025'
    try:
        summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
        benchmark = None
        if (directory / 'benchmark.json').exists():
            benchmark = json.loads((directory / 'benchmark.json').read_text(encoding='utf-8'))
            if not isinstance(benchmark, dict):
                raise ValueError('Benchmark report is not a JSON object')
        return Estimate2025.model_validate({'summary': summary, 'benchmark': benchmark})
    except (OSError, ValueError, ValidationError) as exc:
        raise ArtifactUnavailable('Saved 2025 Maryland estimate is missing or invalid; '
            'expected baseline/outputs/estimate_2025/summary.json.') from exc


def _num(value: str | None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def read_fields_geojson() -> dict:
    """Field polygons for maps (EPSG:4326), exported by baseline/export_fields_geojson.py."""
    try:
        data = json.loads((OUTPUT_DIR / 'fields.geojson').read_text(encoding='utf-8'))
        features = data['features']
        if data.get('type') != 'FeatureCollection' or not features:
            raise ValueError('Not a non-empty FeatureCollection')
        for f in features:
            if f['geometry']['type'] not in ('Polygon', 'MultiPolygon'):
                raise ValueError('Unexpected geometry type')
            int(f['properties']['field_id'])
        return data
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ArtifactUnavailable('Field polygons are missing or invalid; run baseline/export_fields_geojson.py.') from exc


def read_fields() -> list[BarcField]:
    """Field attributes (no geometry) from the source GeoPackage, opened read-only."""
    try:
        with closing(sqlite3.connect(f'file:{FIELDS_GPKG}?mode=ro', uri=True)) as db:
            rows = db.execute(
                f'SELECT OBJECTID, FARM, FIELD, ACRES FROM "{FIELDS_TABLE}" ORDER BY OBJECTID').fetchall()
        if not rows:
            raise ValueError('No fields')
        return [BarcField(field_id=r[0], farm=r[1], field=r[2], acres=r[3]) for r in rows]
    except (sqlite3.Error, ValueError, ValidationError) as exc:
        raise ArtifactUnavailable('Field table is missing or invalid.') from exc


def read_observations(field_id: int, year: int) -> list[Observation]:
    """Per-scene NDVI and clear fraction for one field-year, including rejected scenes."""
    try:
        with (OUTPUT_DIR / 'observations.csv').open(encoding='utf-8', newline='') as file:
            rows = [r for r in csv.DictReader(file)
                    if r['OBJECTID'] == str(field_id) and r['year'] == str(year)]
        return sorted((Observation(date=r['date'], ndvi=_num(r['ndvi']),
            clear_fraction=_num(r['clear_fraction']),
            scene_cloud_percent=_num(r['scene_cloud_percent']), status=r['status'])
            for r in rows), key=lambda o: o.date)
    except (OSError, KeyError, ValidationError) as exc:
        raise ArtifactUnavailable('Saved observations are missing or invalid.') from exc


def _rates(preds: list[Prediction], acres: dict[int, float | None]) -> tuple[float | None, float | None]:
    """Acre-weighted error rates for correcting an acre-weighted predicted share."""
    known = [(p, acres[p.field_id]) for p in preds if acres.get(p.field_id) is not None]
    pos = [(p, area) for p, area in known if p.reference_label == 'Silage']
    neg = [(p, area) for p, area in known if p.reference_label == 'Grain']
    pos_acres, neg_acres = sum(a for _, a in pos), sum(a for _, a in neg)
    tpr = sum(a for p, a in pos if p.predicted_label == 'Silage') / pos_acres if pos_acres else None
    fpr = sum(a for p, a in neg if p.predicted_label == 'Silage') / neg_acres if neg_acres else None
    return tpr, fpr


def compute_rollup(predictions: list[Prediction] | None = None) -> Rollup:
    """Acre roll-up of saved held-out predictions, per year, next to reference acres.

    Expected silage acres = sum(p * acres). The 95% interval treats field-years as
    independent Bernoulli outcomes: var = sum(acres^2 * p * (1 - p)); CV% = 100 * sd / expected.
    Adjusted share = (q - FPR) / (TPR - FPR), with q the acre share predicted Silage and
    TPR/FPR acre-weighted and estimated from the OTHER years only.
    """
    acres = {f.field_id: f.acres for f in read_fields()}
    by_year: dict[int, list[Prediction]] = {}
    all_preds = predictions if predictions is not None else read_predictions()
    for p in all_preds:
        by_year.setdefault(p.year, []).append(p)
    years = []
    for year, preds in sorted(by_year.items()):
        known = [(p, acres[p.field_id]) for p in preds if acres.get(p.field_id) is not None]
        if not known:
            continue
        expected = sum(p.silage_probability * a for p, a in known)
        sd = math.sqrt(sum(a * a * p.silage_probability * (1 - p.silage_probability) for p, a in known))
        total = sum(a for _, a in known)
        predicted = sum(a for p, a in known if p.predicted_label == 'Silage')
        q = predicted / total if total else 0.0
        tpr, fpr = _rates([p for p in all_preds if p.year != year], acres)
        adjusted = None
        if tpr is not None and fpr is not None and tpr - fpr > 0:
            adjusted = min(1.0, max(0.0, (q - fpr) / (tpr - fpr)))
        years.append(YearRollup(year=year, field_years=len(preds),
            total_acres=round(total, 2),
            reference_silage_acres=round(sum(a for p, a in known if p.reference_label == 'Silage'), 2),
            predicted_silage_acres=round(predicted, 2),
            expected_silage_acres=round(expected, 2),
            expected_silage_acres_95ci=(round(max(0.0, expected - 1.96 * sd), 2),
                                        round(expected + 1.96 * sd, 2)),
            cv_percent=round(100 * sd / expected, 1) if expected else None,
            predicted_silage_share=round(q, 4),
            adjusted_silage_share=round(adjusted, 4) if adjusted is not None else None,
            adjusted_silage_acres=round(adjusted * total, 2) if adjusted is not None else None,
            adjustment_rates={'tpr': tpr, 'fpr': fpr},
            missing_acres_field_years=len(preds) - len(known)))
    return Rollup(scope='Labeled BARC field-years with saved held-out predictions only',
        method=('expected = sum(p_silage * acres); 95% CI and CV% from independent Bernoulli '
                'variance; adjusted share = (q - FPR) / (TPR - FPR) with acre-weighted rates '
                'from the other years'),
        years=years)


# Same columns, in the same order, as the lab's QuickStats file
QUICKSTATS_COLUMNS = ['year', 'aggregation_level', 'state_name', 'state_ansi', 'county_name',
    'county_ansi', 'commodity', 'crop_use', 'measurement', 'statistic', 'unit', 'value',
    'cv_percent', 'source', 'domain', 'domain_category', 'reference_period', 'frequency',
    'short_description']


def quickstats_rows(rollup: Rollup) -> list[dict]:
    """Roll-up years as rows shaped like the lab's QuickStats file."""
    return [{'year': y.year, 'aggregation_level': 'BARC LABELED FIELDS', 'state_name': 'MARYLAND',
        'state_ansi': '24', 'county_name': '', 'county_ansi': '', 'commodity': 'CORN',
        'crop_use': 'silage', 'measurement': 'harvested', 'statistic': 'AREA HARVESTED',
        'unit': 'ACRES', 'value': f'{y.expected_silage_acres:,.1f}',
        'cv_percent': '' if y.cv_percent is None else y.cv_percent, 'source': 'MODEL',
        'domain': 'TOTAL', 'domain_category': 'NOT SPECIFIED', 'reference_period': 'YEAR',
        'frequency': 'ANNUAL', 'short_description': 'CORN, SILAGE - ACRES HARVESTED'}
        for y in rollup.years]


def rollup_quickstats_csv(rollup: Rollup | None = None) -> str:
    """The roll-up in the lab QuickStats file's column shape, as CSV text."""
    import io
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=QUICKSTATS_COLUMNS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(quickstats_rows(rollup or compute_rollup()))
    return buffer.getvalue()


def _suppressed(raw: str) -> bool:
    raw = raw.strip()
    return raw.startswith('(') and raw.endswith(')')


def read_quickstats(state: str, year: int | None = None, crop_use: str | None = None,
                    level: str | None = None, total_only: bool = True) -> list[QuickStatsRow]:
    """NASS QuickStats export at $QUICKSTATS_CSV (the lab's corn grain/silage file).
    Suppressed values such as (D), (S), (H) are flagged with value null, never zero.
    total_only keeps domain TOTAL rows (drops irrigated and other breakdowns)."""
    path = os.environ.get('QUICKSTATS_CSV')
    if not path:
        raise ArtifactUnavailable('QUICKSTATS_CSV is not set. Point it at a NASS QuickStats CSV, for example '
            'data/reference/quickstats_2025_judges.csv (2025 judge totals).')
    try:
        with open(path, encoding='utf-8-sig', newline='') as file:
            reader = csv.DictReader(file)
            cols = {c.lower().strip(): c for c in reader.fieldnames or []}
            pick = lambda *names: next((cols[n] for n in names if n in cols), None)
            c_state, c_year = pick('state_name', 'state'), pick('year')
            c_item = pick('short_description', 'short_desc', 'data item')
            c_value, c_cv = pick('value'), pick('cv_percent', 'cv (%)')
            c_county, c_level = pick('county_name', 'county'), pick('aggregation_level', 'agg_level_desc', 'geo level')
            c_use, c_source = pick('crop_use', 'util_practice_desc'), pick('source', 'source_desc', 'program')
            c_domain = pick('domain', 'domain_desc')
            if c_value is None:
                raise ValueError('No value column')
            if c_state is None or (year is not None and c_year is None):
                raise ValueError('Missing state or requested year column')
            if level and c_level is None:
                raise ValueError('No aggregation level column for the requested filter')
            if crop_use and c_use is None and c_item is None:
                raise ValueError('No crop use or description column for the requested filter')
            get = lambda r, c: (r.get(c) or '').strip() if c else ''
            out = []
            for r in reader:
                if c_state and get(r, c_state).upper() != state.upper():
                    continue
                y = get(r, c_year)
                if year is not None and y != str(year):
                    continue
                if level and c_level and get(r, c_level).upper() != level.upper():
                    continue
                if total_only and c_domain and get(r, c_domain).upper() not in ('', 'TOTAL'):
                    continue
                use = get(r, c_use).lower()
                if use not in ('grain', 'silage'):
                    uses = set(re.findall(r'\b(grain|silage)\b', get(r, c_item), flags=re.IGNORECASE))
                    uses = {u.lower() for u in uses}
                    use = uses.pop() if len(uses) == 1 else ''
                if crop_use:
                    if not use:
                        raise ValueError('Cannot identify crop use for the requested filter')
                    if use != crop_use.lower():
                        continue
                raw, cv = get(r, c_value), get(r, c_cv)
                out.append(QuickStatsRow(year=int(y) if y.isdigit() else None,
                    state=get(r, c_state) or None, county=get(r, c_county) or None,
                    aggregation_level=get(r, c_level) or None, crop_use=use or None,
                    source=get(r, c_source) or None, item=get(r, c_item) or None,
                    value=None if _suppressed(raw) else _num(raw.replace(',', '')),
                    cv_percent=None if not cv or _suppressed(cv) else _num(cv.replace(',', '')),
                    suppressed=_suppressed(raw)))
        return out
    except (OSError, ValueError, KeyError, ValidationError) as exc:
        raise ArtifactUnavailable('QuickStats file is missing or invalid.') from exc
