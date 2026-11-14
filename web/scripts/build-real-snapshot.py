#!/usr/bin/env python3
"""
Builds web/public/snapshot/ from the REAL repo data, replacing the fake stub:

  BARC_Corn.2021-2023.gpkg                 -> fields_<year>.json   (83 field outlines + BARC label per year)
  baseline/outputs/heldout_predictions.csv -> predict_<year>_<year>-11-30.json  (held-out calls, season end)
  baseline/outputs/metrics.json            -> evaluate_strict.json (confusion, precision/recall + Wilson 95% CI,
                                              balanced accuracy, always-grain baseline, by-year)
  baseline/outputs/observations.csv        -> series_<id>_<year>.json (per-date NDVI for scored field-years)

Not produced (no real source yet): Maryland roll-up, image chips, as-of snapshots before season end.
The agent trace stays the existing demo files.

Run from the repo root:  python3 web/scripts/build-real-snapshot.py   (needs: pip install pyproj)
"""
import csv
import json
import math
import sqlite3
import struct
from collections import defaultdict
from pathlib import Path

from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'web' / 'public' / 'snapshot'
GPKG = ROOT / 'BARC_Corn.2021-2023.gpkg'
BASE = ROOT / 'baseline' / 'outputs'
YEARS = [2021, 2022, 2023]
SEASON_END = '11-30'
KEEP = {'agent_run.json', 'README.md'}  # demo agent files and docs survive a rebuild

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
        if p.name in KEEP or p.name.startswith('agent_trace_'):
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
                'top_features': '[]',
            })
    for year in YEARS:
        write(f'predict_{year}_{year}-{SEASON_END}', preds[year])

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
        'convergence': [],
        'abstained': 0,
        'n_evaluated': m['evaluated_field_years'],
        'n_fields': m['evaluated_fields'],
        'model_name': 'Logistic regression on NDVI',
        'balanced_accuracy': round(m['logistic']['balanced_accuracy'], 4),
        'baseline': {'name': 'Always grain', **summary(m['always_grain'])},
        'by_year': {y: {'model': summary(v['logistic']), 'baseline': summary(v['always_grain'])} for y, v in m['by_year'].items()},
    })

    # ---- per-date NDVI series for scored field-years ----
    series = defaultdict(list)
    with (BASE / 'observations.csv').open(encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            if r['status'] != 'ok' or not r['ndvi']:
                continue
            series[(int(r['OBJECTID']), int(r['year']))].append({'date': r['date'], 'ndvi': round(float(r['ndvi']), 4), 'ndti': None})
    for (oid, year), pts in series.items():
        pts.sort(key=lambda p: p['date'])
        write(f'series_{oid}_{year}', {'OBJECTID': oid, 'year': year, 'points': pts, 'decline_date': None})

    write('_meta', {
        'stub': False,
        'note': 'Real BARC data: field outlines and labels from BARC_Corn.2021-2023.gpkg; held-out predictions and metrics from baseline/outputs (logistic regression, field-held-out folds).',
        'years': YEARS,
        'as_of_dates': [f'{y}-{SEASON_END}' for y in YEARS],
        'season_end_only': True,
    })
    print(f'wrote real snapshot: {len(rows)} fields x {len(YEARS)} years, {sum(len(v) for v in preds.values())} predictions, {len(series)} series -> {OUT}')


if __name__ == '__main__':
    main()
