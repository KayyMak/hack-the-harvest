#!/usr/bin/env python3
"""
Builds web/public/snapshot/ from the REAL repo data, replacing the fake stub:

  BARC_Corn.2021-2023.gpkg                 -> fields_<year>.json   (83 field outlines + BARC label per year)
  baseline/outputs/heldout_predictions.csv -> predict_<year>_<year>-11-30.json  (held-out calls, season end)
  baseline/outputs/metrics.json            -> evaluate_strict.json (confusion, precision/recall + Wilson 95% CI,
                                              balanced accuracy, always-grain baseline, by-year)
  baseline/outputs/observations.csv        -> series_<id>_<year>.json (per-date NDVI for scored field-years)

Optional inputs (see web/DATA_HANDOFF.md); each one is used automatically when it exists:
  baseline/outputs/asof_predictions.csv      -> mid-season predict files + convergence chart
  baseline/outputs/feature_contributions.csv -> per-field "why the model decided" bars
  baseline/outputs/rollup.json (or rollup_<year>.json) -> Maryland acres vs Census
  baseline/outputs/chips/<id>_<year>_{pre,post}.png    -> before/after images
  baseline/outputs/estimate_2025/summary.json (+ benchmark.json) -> estimate_2025.json (2025 Maryland estimate)
  forecast/outputs/summary.json (+ data/reference NASS 2025 acres) -> forecast_2025.json (graded 2025 forecast)
  baseline/outputs/unlabeled/                -> unlabeled.json (model calls on blank-label corn fields)
Agent execution is unavailable in static mode.

Run from the repo root:  python3 web/scripts/build-real-snapshot.py   (needs: pip install pyproj)
"""
import csv
import sys
import os
import shutil
import json
import math
import sqlite3
import struct
from collections import defaultdict
from pathlib import Path

from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get('CUTLINE_OUT', ROOT / 'web' / 'public' / 'snapshot'))
GPKG = ROOT / 'BARC_Corn.2021-2023.gpkg'
BASE = Path(os.environ.get('CUTLINE_BASE', ROOT / 'baseline' / 'outputs'))
YEARS = [2021, 2022, 2023]
SEASON_END = '11-30'
KEEP = {'README.md'}

# NAD83 / Maryland (ftUS) -> WGS84 lon/lat
TO_WGS84 = Transformer.from_crs('EPSG:2248', 'EPSG:4326', always_xy=True)


def wilson(k: int, n: int, z: float = 1.959964):
    if n == 0:
        return {'value': 0.0, 'lo': 0.0, 'hi': 0.0}
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {'value': round(p, 4), 'lo': round(max(0.0, c - h), 4), 'hi': round(min(1.0, c + h), 4)}


def read_wkb(buf: bytes, off: int = 0):
    """Minimal WKB reader for Polygon / MultiPolygon. Returns (geojson geometry, next offset)."""
    order = '<' if buf[off] == 1 else '>'
    gtype = struct.unpack_from(order + 'I', buf, off + 1)[0] % 1000
    off += 5

    def ring(o):
        n = struct.unpack_from(order + 'I', buf, o)[0]
        o += 4
        pts = []
        for _ in range(n):
            x, y = struct.unpack_from(order + 'dd', buf, o)
            o += 16
            lon, lat = TO_WGS84.transform(x, y)
            pts.append([round(lon, 7), round(lat, 7)])
        return pts, o

    def polygon(o):
        n = struct.unpack_from(order + 'I', buf, o)[0]
        o += 4
        rings = []
        for _ in range(n):
            r, o = ring(o)
            rings.append(r)
        return rings, o

    if gtype == 3:
        rings, off = polygon(off)
        return {'type': 'Polygon', 'coordinates': rings}, off
    if gtype == 6:
        n = struct.unpack_from(order + 'I', buf, off)[0]
        off += 4
        polys = []
        for _ in range(n):
            sub, off = read_wkb(buf, off)
            polys.append(sub['coordinates'])
        return {'type': 'MultiPolygon', 'coordinates': polys}, off
    raise ValueError(f'unsupported geometry type {gtype}')


def gpkg_geometry(blob: bytes):
    flags = blob[3]
    env = (flags >> 1) & 0b111
    env_len = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[env]
    geom, _ = read_wkb(blob, 8 + env_len)
    return geom


def write(name: str, data) -> None:
    (OUT / f'{name}.json').write_text(json.dumps(data, separators=(',', ':')), encoding='utf-8')


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in OUT.iterdir():
        if p.name in KEEP:
            continue
        if p.is_dir():
            for q in p.iterdir():
                q.unlink()
            p.rmdir()
        else:
            p.unlink()

    # ---- fields ----
    con = sqlite3.connect(GPKG)
    table = con.execute("select table_name from gpkg_contents where data_type='features'").fetchone()[0]
    rows = con.execute(f'select geom, OBJECTID, FIELD, ACRES, Corn_2021, Corn_2022, Corn_2023 from "{table}"').fetchall()
    for y_i, year in enumerate(YEARS):
        feats = []
        for geom, oid, field, acres, *labels in rows:
            feats.append({
                'type': 'Feature',
                'geometry': gpkg_geometry(geom),
                'properties': {'OBJECTID': oid, 'FIELD': field, 'ACRES': round(acres, 1) if acres else None, 'label': labels[y_i]},
            })
        write(f'fields_{year}', {'type': 'FeatureCollection', 'features': feats})

    # ---- optional: per-field feature contributions ----
    contrib = defaultdict(list)  # (OBJECTID, year, as_of or '') -> [{name, value, contrib}]
    cpath = BASE / 'feature_contributions.csv'
    if cpath.exists():
        with cpath.open(encoding='utf-8', newline='') as f:
            for r in csv.DictReader(f):
                key = (int(r['OBJECTID']), int(r['year']), (r.get('as_of') or '').strip())
                contrib[key].append({'name': r['feature'], 'value': round(float(r['value']), 4), 'contrib': round(float(r['contribution']), 4)})

    def top_features(oid: int, year: int, as_of: str = '') -> str:
        rows_ = contrib.get((oid, year, as_of)) or []
        if not rows_ and (not as_of or as_of.endswith(f'-{SEASON_END}')):  # never show later months mid-season
            rows_ = contrib.get((oid, year, '')) or []
        return json.dumps(sorted(rows_, key=lambda c: -abs(c['contrib']))[:6])

    # ---- held-out predictions (season end) ----
    preds = defaultdict(list)
    with (BASE / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            year = int(r['year'])
            preds[year].append({
                'OBJECTID': int(r['OBJECTID']),
                'year': year,
                'as_of': f'{year}-{SEASON_END}',
                'p_silage': round(float(r['silage_probability']), 4),
                'class': r['predicted_label'],
                'abstain': False,
                'top_features': top_features(int(r['OBJECTID']), year),
            })
    for year in YEARS:
        write(f'predict_{year}_{year}-{SEASON_END}', preds[year])

    # ---- optional: mid-season (as-of) predictions ----
    asof_dates = []
    convergence = []
    apath = BASE / 'asof_predictions.csv'
    if apath.exists():
        by_date = defaultdict(list)
        with apath.open(encoding='utf-8', newline='') as f:
            for r in csv.DictReader(f):
                status = (r.get('status') or 'decided').strip().lower()
                cls = r['predicted_label'] if status == 'decided' else ('Insufficient' if status == 'insufficient' else 'Pending')
                p = r.get('silage_probability') or ''
                by_date[r['as_of']].append({
                    'OBJECTID': int(r['OBJECTID']), 'year': int(r['year']), 'as_of': r['as_of'],
                    'p_silage': round(float(p), 4) if p and status == 'decided' else None,
                    'class': cls, 'abstain': status == 'insufficient',
                    'top_features': top_features(int(r['OBJECTID']), int(r['year']), r['as_of']),
                })
        truth = {}
        with (BASE / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as f:
            for r in csv.DictReader(f):
                truth[(int(r['OBJECTID']), int(r['year']))] = r['label']
        for as_of, rows_ in sorted(by_date.items()):
            write(f'predict_{as_of[:4]}_{as_of}', rows_)
            asof_dates.append(as_of)
        # convergence pooled over years by month-day
        by_md = defaultdict(list)
        for as_of, rows_ in by_date.items():
            by_md[as_of[5:]].extend(rows_)
        for md in sorted(by_md):
            rows_ = [x for x in by_md[md] if (x['OBJECTID'], x['year']) in truth]
            dec = [x for x in rows_ if x['class'] in ('Grain', 'Silage')]
            ok = sum(1 for x in dec if x['class'] == truth[(x['OBJECTID'], x['year'])])
            convergence.append({'as_of': f'{YEARS[1]}-{md}', 'share_decided': round(len(dec) / max(1, len(rows_)), 4),
                                'acc_decided': round(ok / len(dec), 4) if dec else 0.0})

    # ---- saved as-of calls from `python -m harvest.export_asof` (what the live API serves) ----
    jpath = BASE / 'asof.json'
    if not asof_dates and jpath.exists():
        saved = json.loads(jpath.read_text(encoding='utf-8'))
        for d in saved['dates']:
            rows_ = [{'OBJECTID': p['field_id'], 'year': d['year'], 'as_of': d['as_of'],
                      'p_silage': round(p['silage_probability'], 4), 'class': p['predicted_label'],
                      'abstain': False, 'top_features': top_features(p['field_id'], d['year'], d['as_of'])}
                     for p in d['predictions']]
            rows_ += [{'OBJECTID': i, 'year': d['year'], 'as_of': d['as_of'], 'p_silage': None, 'class': 'Pending',
                       'abstain': False, 'top_features': '[]'} for i in d['pending_field_ids']]
            if not d['as_of'].endswith(f'-{SEASON_END}'):  # season end already written from held-out predictions
                write(f"predict_{d['year']}_{d['as_of']}", rows_)
            asof_dates.append(d['as_of'])
        convergence = [{'as_of': f"{YEARS[1]}-{p['month_day']}", 'share_decided': p['share_decided'],
                        'acc_decided': p['accuracy_decided'], 'bal_acc': p['balanced_accuracy']}
                       for p in saved['pooled'] if p['share_decided'] is not None]

    # ---- evaluation ----
    m = json.loads((BASE / 'metrics.json').read_text(encoding='utf-8'))
    order = m['logistic']['matrix_order']
    cm = m['logistic']['confusion_matrix']  # rows = true, cols = predicted

    def per_class(i: int):
        tp = cm[i][i]
        support = sum(cm[i])
        called = sum(cm[r][i] for r in range(len(order)))
        return {'precision': wilson(tp, called), 'recall': wilson(tp, support), 'support': support}

    def summary(block):
        return {k: block[k] for k in ('n', 'silage_precision', 'silage_recall', 'balanced_accuracy', 'brier_score', 'confusion_matrix')}

    write('evaluate_strict', {
        'split': 'field',
        'split_label': 'held out by field',
        'protocol': m['protocol'],
        'labels': order,
        'confusion': cm,
        'per_class': {lab: per_class(i) for i, lab in enumerate(order)},
        'convergence': convergence,
        'abstained': 0,
        'n_evaluated': m['evaluated_field_years'],
        'n_fields': m['evaluated_fields'],
        'model_name': m.get('model', 'Logistic regression on NDVI'),
        'balanced_accuracy': round(m['logistic']['balanced_accuracy'], 4),
        'baseline': {'name': 'Always grain', **summary(m['always_grain'])},
        'by_year': {y: {'model': summary(v['logistic']), 'baseline': summary(v['always_grain'])} for y, v in m['by_year'].items()},
        'model_version': m.get('model_version', 'v1'),
        **({'selection': {k: m['selection'][k] for k in ('note', 'nested_selection_mean_balanced_accuracy',
                                                         'v1_mean_balanced_accuracy_same_seeds',
                                                         'gain_vs_v1_field_bootstrap_95ci', 'details')}}
           if 'selection' in m else {}),
        **({'v1_same_split': {'name': 'v1 (nine NDVI features)', **summary(m['v1_logistic_same_split'])}}
           if 'v1_logistic_same_split' in m else {}),
    })

    # ---- per-date NDVI series for scored field-years ----
    series = defaultdict(list)
    sources = [BASE / 'observations.csv']
    if (BASE / 'unlabeled' / 'observations.csv').exists():  # unlabeled field-years with model calls
        sources.append(BASE / 'unlabeled' / 'observations.csv')
    for source in sources:
        with source.open(encoding='utf-8', newline='') as f:
            for r in csv.DictReader(f):
                if r['status'] != 'ok' or not r['ndvi']:
                    continue
                series[(int(r['OBJECTID']), int(r['year']))].append({'date': r['date'], 'ndvi': round(float(r['ndvi']), 4), 'ndti': None})
    for (oid, year), pts in series.items():
        pts.sort(key=lambda p: p['date'])
        write(f'series_{oid}_{year}', {'OBJECTID': oid, 'year': year, 'points': pts, 'decline_date': None})

    # ---- optional: Maryland roll-up ----
    has_rollup = False
    for year in YEARS:
        rpath = BASE / f'rollup_{year}.json'
        if not rpath.exists() and (BASE / 'rollup.json').exists():
            rpath = BASE / 'rollup.json'
        if not rpath.exists():
            continue
        r = json.loads(rpath.read_text(encoding='utf-8'))
        if int(r['year']) != year:
            continue
        has_rollup = True
        (OUT / f'rollup_{year}.csv').write_text(
            'year,aggregation_level,state_name,commodity,crop_use,statistic,unit,value,cv_percent,source\n'
            f"{year},STATE,{r['region'].upper()},CORN,silage,AREA HARVESTED,ACRES,{round(r['acres'])},{r.get('cv_pct', '')},Cutline model estimate\n",
            encoding='utf-8')
        write(f'rollup_{year}', {'year': year, 'region': r['region'], 'acres': r['acres'], 'ci': [r['ci_lo'], r['ci_hi']],
                                 'cv_pct': r.get('cv_pct', 0), 'census_acres': r['census_acres'], 'csv_url': f'rollup_{year}.csv'})

    # ---- silage acres by as-of date (same code the API route uses) ----
    has_acres_convergence = False
    try:
        sys.path.insert(0, str(ROOT / 'backend'))
        from app import artifacts  # needs the backend's pydantic dependency installed
        previous_output = artifacts.OUTPUT_DIR
        try:
            artifacts.OUTPUT_DIR = BASE
            write('convergence_acres', json.loads(artifacts.compute_convergence().model_dump_json()))
        finally:
            artifacts.OUTPUT_DIR = previous_output
        has_acres_convergence = True
    except Exception as exc:  # explicit, never a silent substitute
        print(f'convergence_acres.json NOT written: {exc}')

    # ---- model calls on blank-label fields CDL marks as corn (same reader as GET /api/unlabeled) ----
    try:
        sys.path.insert(0, str(ROOT / 'backend'))
        from app import artifacts
        previous_output = artifacts.OUTPUT_DIR
        try:
            artifacts.OUTPUT_DIR = BASE
            write('unlabeled', json.loads(artifacts.read_unlabeled().model_dump_json()))
        finally:
            artifacts.OUTPUT_DIR = previous_output
    except Exception as exc:  # explicit, never a silent substitute; the dashboard shows Pending
        print(f'unlabeled.json NOT written: {exc}')

    # ---- optional: before/after chips ----
    has_chips = False
    cdir = BASE / 'chips'
    if cdir.is_dir():
        (OUT / 'chips').mkdir(exist_ok=True)
        for png in cdir.glob('*.png'):
            shutil.copy2(png, OUT / 'chips' / png.name)
            has_chips = True

    # ---- optional: 2025 Maryland estimate, in the same {summary, benchmark} shape as GET /api/estimate_2025 ----
    edir = BASE / 'estimate_2025'
    if (edir / 'summary.json').exists():
        bpath = edir / 'benchmark.json'
        write('estimate_2025', {
            'summary': json.loads((edir / 'summary.json').read_text(encoding='utf-8')),
            'benchmark': json.loads(bpath.read_text(encoding='utf-8')) if bpath.exists() else None,
        })
    else:  # not generated yet: the dashboard shows a pending slot instead
        print(f"skipped estimate_2025.json ({edir / 'summary.json'} not found)")

    # ---- graded 2025 forecast: the backend's own reader, so the snapshot matches GET /api/forecast_2025 ----
    try:
        sys.path.insert(0, str(ROOT / 'backend'))
        from app.artifacts import read_forecast_2025
        write('forecast_2025', read_forecast_2025().model_dump(mode='json', exclude_unset=True))
    except Exception as exc:  # missing forecast or backend deps: the dashboard shows a pending slot instead
        print(f'skipped forecast_2025.json ({exc})')

    # ---- BARC-only acre roll-up: reuse the backend's own computation so offline matches live ----
    try:
        sys.path.insert(0, str(ROOT / 'backend'))
        from app.artifacts import compute_rollup  # same code as GET /api/baseline/rollup
        write('barc_rollup', compute_rollup().model_dump())
    except Exception as exc:  # backend deps missing: the dashboard shows a pending slot instead
        print(f'skipped barc_rollup.json ({exc})')

    write('_meta', {
        'stub': False,
        'note': 'Real BARC data: field outlines and labels from BARC_Corn.2021-2023.gpkg; held-out predictions and metrics from baseline/outputs '
                f"({m.get('model', 'logistic regression')}, field-held-out folds).",
        'years': YEARS,
        'as_of_dates': sorted(set(asof_dates)) or [f'{y}-{SEASON_END}' for y in YEARS],
        'season_end_only': not asof_dates,
        'has_chips': has_chips,
        'has_rollup': has_rollup,
        'has_acres_convergence': has_acres_convergence,
        'has_contributions': bool(contrib),
    })
    print(f'wrote real snapshot: {len(rows)} fields x {len(YEARS)} years, {sum(len(v) for v in preds.values())} predictions, {len(series)} series -> {OUT}')


if __name__ == '__main__':
    main()
