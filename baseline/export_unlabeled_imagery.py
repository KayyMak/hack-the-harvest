"""Greenness series and before/after chips for the unlabeled field-years that have model calls.

    python baseline/export_unlabeled_imagery.py observations   # offline, from baseline/cache_unlabeled/
    python baseline/export_unlabeled_imagery.py chips          # network: Planetary Computer, no key

`observations` writes baseline/outputs/unlabeled/observations.csv in the same columns as
baseline/outputs/observations.csv, for every field-year in baseline/outputs/unlabeled/predictions.csv
(labeled field-years are refused). The rows come from the extraction cache written by
baseline/unlabeled_calls.py with the baseline recipe; nothing is re-measured or filled in.

`chips` picks scenes and renders images exactly as baseline/export_chips.py does (largest drop between
consecutive usable looks), writing <OBJECTID>_<year>_{pre,post}.png into baseline/outputs/chips/ and a
separate chips/index_unlabeled.json so the labeled index is untouched. A scene that cannot be read is
skipped and listed, never substituted.
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'outputs'
CACHE = HERE / 'cache_unlabeled'
UNLABELED = OUT / 'unlabeled'
COLUMNS = ['OBJECTID', 'year', 'item_id', 'date', 'scene_cloud_percent', 'field_pixels', 'clear_pixels',
           'clear_fraction', 'ndvi', 'status']


def called_field_years() -> list[tuple[int, int]]:
    with (UNLABELED / 'predictions.csv').open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    with (OUT / 'labels.csv').open(encoding='utf-8', newline='') as f:
        labeled = {(int(r['OBJECTID']), int(r['year'])) for r in csv.DictReader(f)}
    keys = sorted({(int(r['field_id']), int(r['year'])) for r in rows})
    clash = [k for k in keys if k in labeled]
    if clash:
        raise ValueError(f'Labeled field-years in the unlabeled calls: {clash}')
    return keys


def observations() -> dict:
    rows, missing = [], []
    for oid, year in called_field_years():
        path = CACHE / f'{oid}_{year}.json'
        if not path.exists():
            missing.append(f'{oid}_{year}')
            continue
        cached = json.loads(path.read_text(encoding='utf-8'))
        if cached['OBJECTID'] != oid or cached['year'] != year:
            raise ValueError(f'Cache {path.name} is for another field-year')
        for o in cached['observations']:
            rows.append({c: ('' if o.get(c) is None else o.get(c)) for c in COLUMNS})
    rows.sort(key=lambda r: (r['OBJECTID'], r['year'], r['date'], r['item_id']))
    with (UNLABELED / 'observations.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return {'field_years': len(called_field_years()) - len(missing), 'rows': len(rows),
            'usable_rows': sum(r['status'] == 'ok' for r in rows), 'missing_cache': missing}


def pick_scenes() -> dict:
    """Same rule as export_chips.pick_scenes, applied to the unlabeled observations."""
    obs = defaultdict(list)
    with (UNLABELED / 'observations.csv').open(encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            if r['status'] == 'ok' and r['ndvi'] not in ('', None):
                obs[(int(r['OBJECTID']), int(r['year']))].append(r)
    picks = {}
    for key, rows in obs.items():
        rows.sort(key=lambda r: (r['date'], r['item_id']))
        if len(rows) < 2:
            continue
        drops = [float(a['ndvi']) - float(b['ndvi']) for a, b in zip(rows, rows[1:])]
        i = drops.index(max(drops))
        picks[key] = (rows[i], rows[i + 1])
    return picks


def chips() -> dict:
    import geopandas as gpd
    from pystac_client import Client
    sys.path.insert(0, str(HERE))
    from export_chips import CHIPS, GPKG, LAYER, STAC, render

    CHIPS.mkdir(parents=True, exist_ok=True)
    fields = gpd.read_file(GPKG, layer=LAYER).to_crs(4326).set_index('OBJECTID')
    picks = pick_scenes()
    ids = sorted({r['item_id'] for pre, post in picks.values() for r in (pre, post)})
    catalog = Client.open(STAC)
    items = {}
    for start in range(0, len(ids), 50):
        for attempt in range(5):
            try:
                for item in catalog.search(collections=['sentinel-2-l2a'], ids=ids[start:start + 50]).items():
                    items[item.id] = item
                break
            except Exception:
                if attempt == 4:
                    raise
    index, skipped = {}, []
    for (oid, year), (pre, post) in sorted(picks.items()):
        entry = {}
        for which, row in (('pre', pre), ('post', post)):
            item = items.get(row['item_id'])
            if item is None:
                skipped.append(f"{oid}_{year}_{which}: scene {row['item_id']} not found")
                continue
            error = None
            for attempt in range(4):  # flaky network: retry the same scene, never another one
                try:
                    render(item, fields.loc[oid].geometry, CHIPS / f'{oid}_{year}_{which}.png',
                           f"{'Before' if which == 'pre' else 'After'} the drop · {row['date']} · NDVI {float(row['ndvi']):.2f}")
                    error = None
                    break
                except Exception as exc:
                    error = exc
            if error is not None:
                skipped.append(f'{oid}_{year}_{which}: {type(error).__name__}')
                continue
            entry[which] = {'item_id': row['item_id'], 'date': row['date'], 'ndvi': round(float(row['ndvi']), 4)}
        index[f'{oid}_{year}'] = entry
    (CHIPS / 'index_unlabeled.json').write_text(json.dumps({
        'source': 'Sentinel-2 L2A visual (10 m), Microsoft Planetary Computer',
        'selection': 'consecutive usable scenes with the largest NDVI drop',
        'scope': 'unlabeled field-years with season-end model calls (baseline/outputs/unlabeled/)',
        'chips': index, 'skipped': skipped}, indent=1), encoding='utf-8')
    return {'field_years': len(picks), 'chips_written': sum(len(e) for e in index.values()), 'skipped': skipped}


if __name__ == '__main__':
    stage = sys.argv[1] if len(sys.argv) > 1 else ''
    if stage not in ('observations', 'chips'):
        sys.exit(__doc__)
    result = observations() if stage == 'observations' else chips()
    print(json.dumps(result, indent=2))
    sys.exit(1 if result.get('skipped') or result.get('missing_cache') else 0)
