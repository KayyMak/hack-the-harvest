"""Read saved analysis outputs without importing or running the analysis stack."""
import csv
import math
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from pydantic import ValidationError

from .schemas import (BaselineSummary, BarcField, Observation, Prediction, QuickStatsRow,
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


def _num(value: str | None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


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


def compute_rollup() -> Rollup:
    """Acre roll-up of saved held-out predictions, per year, next to reference acres.

    Expected silage acres = sum(p * acres). The 95% interval treats field-years as
    independent Bernoulli outcomes: var = sum(acres^2 * p * (1 - p)).
    """
    acres = {f.field_id: f.acres for f in read_fields()}
    by_year: dict[int, list[Prediction]] = {}
    for p in read_predictions():
        by_year.setdefault(p.year, []).append(p)
    years = []
    for year, preds in sorted(by_year.items()):
        known = [(p, acres[p.field_id]) for p in preds if acres.get(p.field_id) is not None]
        expected = sum(p.silage_probability * a for p, a in known)
        sd = math.sqrt(sum(a * a * p.silage_probability * (1 - p.silage_probability) for p, a in known))
        years.append(YearRollup(year=year, field_years=len(preds),
            total_acres=round(sum(a for _, a in known), 2),
            reference_silage_acres=round(sum(a for p, a in known if p.reference_label == 'Silage'), 2),
            predicted_silage_acres=round(sum(a for p, a in known if p.predicted_label == 'Silage'), 2),
            expected_silage_acres=round(expected, 2),
            expected_silage_acres_95ci=(round(max(0.0, expected - 1.96 * sd), 2),
                                        round(expected + 1.96 * sd, 2)),
            missing_acres_field_years=len(preds) - len(known)))
    return Rollup(scope='Labeled BARC field-years with saved held-out predictions only',
        method='expected = sum(p_silage * acres); 95% CI from independent Bernoulli variance',
        years=years)


def read_quickstats(state: str) -> list[QuickStatsRow]:
    """NASS QuickStats export at $QUICKSTATS_CSV. (D)/(S)/(H)-style values are flagged
    as suppressed with value null, never zero."""
    path = os.environ.get('QUICKSTATS_CSV')
    if not path:
        raise ArtifactUnavailable('QUICKSTATS_CSV is not set.')
    try:
        with open(path, encoding='utf-8-sig', newline='') as file:
            rows = list(csv.DictReader(file))
        if not rows:
            raise ValueError('Empty QuickStats file')
        cols = {c.lower().strip(): c for c in rows[0]}
        pick = lambda *names: next((cols[n] for n in names if n in cols), None)
        state_col, year_col = pick('state_name', 'state'), pick('year')
        item_col, value_col = pick('short_desc', 'data item'), pick('value')
        if value_col is None:
            raise ValueError('No Value column')
        out = []
        for r in rows:
            if state_col and r[state_col].strip().upper() != state.upper():
                continue
            raw = r[value_col].strip()
            suppressed = raw.startswith('(') and raw.endswith(')')
            out.append(QuickStatsRow(
                year=int(r[year_col]) if year_col and r[year_col].strip().isdigit() else None,
                state=r[state_col].strip() if state_col else None,
                item=r[item_col].strip() if item_col else None,
                value=None if suppressed else _num(raw.replace(',', '')), suppressed=suppressed))
        return out
    except (OSError, ValueError, KeyError, ValidationError) as exc:
        raise ArtifactUnavailable('QuickStats file is missing or invalid.') from exc
