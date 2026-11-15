"""Greenness series and before/after chips for every unlabeled (blank-label) field-year.

    python baseline/export_unlabeled_imagery.py observations   # offline, from baseline/cache_unlabeled/
    python baseline/export_unlabeled_imagery.py chips          # network: Planetary Computer, no key

`observations` writes baseline/outputs/unlabeled/observations.csv in the same columns as
baseline/outputs/observations.csv, for every blank field-year in baseline/outputs/unlabeled/corn_check.csv
that has an extraction cache: the likely-corn ones with model calls and, as evidence only, the not-corn
and mixed ones (`unlabeled_calls.py extract-all`), which get no call. Labeled field-years are refused.
The rows come from the extraction cache written by baseline/unlabeled_calls.py with the baseline
recipe; nothing is re-measured or filled in. observations_coverage.json lists field-years without a
cache, without a usable look, or with scenes that still failed to read.

`chips` picks scenes and renders images exactly as baseline/export_chips.py does (largest drop between
consecutive usable looks), writing <OBJECTID>_<year>_{pre,post}.png into baseline/outputs/chips/ and a
separate chips/index_unlabeled.json so the labeled index is untouched. A scene that cannot be read is
skipped and listed, never substituted; a field-year with fewer than two usable looks has no drop to
show and is listed under too_few_usable_looks. A chip already on disk for the same scene is kept.
"""
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'outputs'
CACHE = HERE / 'cache_unlabeled'
UNLABELED = OUT / 'unlabeled'
COLUMNS = ['OBJECTID', 'year', 'item_id', 'date', 'scene_cloud_percent', 'field_pixels', 'clear_pixels',
           'clear_fraction', 'ndvi', 'status']


def labeled_field_years() -> set[tuple[int, int]]:
    with (OUT / 'labels.csv').open(encoding='utf-8', newline='') as f:
        return {(int(r['OBJECTID']), int(r['year'])) for r in csv.DictReader(f)}


def refuse_labeled(keys) -> list[tuple[int, int]]:
    clash = sorted(set(keys) & labeled_field_years())
    if clash:
        raise ValueError(f'Labeled field-years in the unlabeled outputs: {clash}')
    return sorted(keys)


def called_field_years() -> list[tuple[int, int]]:
    """Blank field-years with a model call (likely corn by CDL)."""
    with (UNLABELED / 'predictions.csv').open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    return refuse_labeled({(int(r['field_id']), int(r['year'])) for r in rows})


def blank_field_years() -> list[tuple[int, int]]:
    """Every blank field-year, whatever its CDL category."""
    with (UNLABELED / 'corn_check.csv').open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    return refuse_labeled({(int(r['field_id']), int(r['year'])) for r in rows if r['label'] == 'blank'})


def observations() -> dict:
    blanks = blank_field_years()
    stray = sorted(p.name for p in CACHE.glob('*.json')
                   if tuple(int(x) for x in p.stem.split('_')) not in set(blanks))
    if stray:
        raise ValueError(f'Caches for field-years that are not blank: {stray}')
    rows, missing, no_usable, read_errors = [], [], [], {}
    for oid, year in blanks:
        path = CACHE / f'{oid}_{year}.json'
        if not path.exists():
            missing.append(f'{oid}_{year}')
            continue
        cached = json.loads(path.read_text(encoding='utf-8'))
        if cached['OBJECTID'] != oid or cached['year'] != year:
            raise ValueError(f'Cache {path.name} is for another field-year')
        for o in cached['observations']:
            rows.append({c: ('' if o.get(c) is None else o.get(c)) for c in COLUMNS})
        if not any(o['status'] == 'ok' for o in cached['observations']):
            no_usable.append(f'{oid}_{year}')
        failed = sorted(o['item_id'] for o in cached['observations'] if o['status'] == 'read_error')
        if failed:
            read_errors[f'{oid}_{year}'] = failed
    rows.sort(key=lambda r: (r['OBJECTID'], r['year'], r['date'], r['item_id']))
    with (UNLABELED / 'observations.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    called = set(called_field_years())
    coverage = {
        'scope': 'every blank-label field-year in corn_check.csv; model calls only for the likely-corn ones',
        'blank_field_years': len(blanks),
        'with_series': len(blanks) - len(missing),
        'with_model_call': sum(k in called for k in blanks),
        'evidence_only': sum(k not in called for k in blanks),
        'missing_cache': missing,
        'no_usable_looks': no_usable,
        'scenes_still_failing_to_read': read_errors}
    (UNLABELED / 'observations_coverage.json').write_text(json.dumps(coverage, indent=1), encoding='utf-8')
    return {'field_years': len(blanks) - len(missing), 'rows': len(rows),
            'usable_rows': sum(r['status'] == 'ok' for r in rows), 'missing_cache': missing,
            'no_usable_looks': no_usable, 'scenes_still_failing_to_read': read_errors}


def usable_looks() -> dict:
    """{(oid, year): usable rows} for every field-year in the unlabeled observations (may be empty)."""
    obs = defaultdict(list)
    with (UNLABELED / 'observations.csv').open(encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            rows = obs[(int(r['OBJECTID']), int(r['year']))]
            if r['status'] == 'ok' and r['ndvi'] not in ('', None):
                rows.append(r)
    return obs


def pick_scenes() -> dict:
    """Same rule as export_chips.pick_scenes, applied to the unlabeled observations."""
    picks = {}
    for key, rows in usable_looks().items():
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
    refuse_labeled(picks)
    too_few = [f'{oid}_{year}: {len(rows)} usable look(s)'
               for (oid, year), rows in sorted(usable_looks().items()) if len(rows) < 2]
    path = CHIPS / 'index_unlabeled.json'
    previous = json.loads(path.read_text(encoding='utf-8'))['chips'] if path.exists() else {}

    def kept(key, which, row):
        """A chip already rendered for this exact scene is reused, not re-read."""
        old = previous.get(key, {}).get(which)
        return old is not None and old['item_id'] == row['item_id'] and (CHIPS / f'{key}_{which}.png').exists()

    todo = {r['item_id'] for (oid, year), pair in picks.items()
            for which, r in zip(('pre', 'post'), pair) if not kept(f'{oid}_{year}', which, r)}
    ids = sorted(todo)
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
                time.sleep(5 * (attempt + 1))
    index, skipped = {}, []

    def save():
        path.write_text(json.dumps({
            'source': 'Sentinel-2 L2A visual (10 m), Microsoft Planetary Computer',
            'selection': 'consecutive usable scenes with the largest NDVI drop',
            'scope': ('every blank-label field-year (baseline/outputs/unlabeled/observations.csv): '
                      'likely-corn ones with model calls, and not-corn or mixed ones as evidence only'),
            'chips': {**previous, **index} if len(index) < len(picks) else index,
            'skipped': skipped, 'too_few_usable_looks': too_few}, indent=1), encoding='utf-8')

    for n, ((oid, year), (pre, post)) in enumerate(sorted(picks.items()), 1):
        key = f'{oid}_{year}'
        entry = {}
        for which, row in (('pre', pre), ('post', post)):
            if not kept(key, which, row):
                item = items.get(row['item_id'])
                if item is None:
                    skipped.append(f"{key}_{which}: scene {row['item_id']} not found")
                    continue
                error = None
                for attempt in range(4):  # flaky network: retry the same scene, never another one
                    try:
                        render(item, fields.loc[oid].geometry, CHIPS / f'{key}_{which}.png',
                               f"{'Before' if which == 'pre' else 'After'} the drop · {row['date']} · NDVI {float(row['ndvi']):.2f}")
                        error = None
                        break
                    except Exception as exc:
                        error = exc
                        time.sleep(3 * (attempt + 1))
                if error is not None:
                    skipped.append(f'{key}_{which}: {type(error).__name__}')
                    continue
            entry[which] = {'item_id': row['item_id'], 'date': row['date'], 'ndvi': round(float(row['ndvi']), 4)}
        index[key] = entry
        if n % 10 == 0:
            print(f'{n}/{len(picks)} field-years', flush=True)
            save()
    save()
    return {'field_years': len(picks), 'chips_written': sum(len(e) for e in index.values()),
            'rendered_now': sum(1 for (oid, year), pair in picks.items() for which, r in zip(('pre', 'post'), pair)
                                if not kept(f'{oid}_{year}', which, r)),
            'skipped': skipped, 'too_few_usable_looks': too_few}


if __name__ == '__main__':
    stage = sys.argv[1] if len(sys.argv) > 1 else ''
    if stage not in ('observations', 'chips'):
        sys.exit(__doc__)
    result = observations() if stage == 'observations' else chips()
    print(json.dumps(result, indent=2))
    sys.exit(1 if result.get('skipped') or result.get('missing_cache') else 0)
