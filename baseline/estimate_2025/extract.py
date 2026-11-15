"""Step 3: 2025 Sentinel-2 features for the sampled fields, same recipe as the baseline.

    python baseline/estimate_2025/extract.py pilot              # one BARC field-year, then one 2025 field
    python baseline/estimate_2025/extract.py catalog            # scene list for July-November 2025
    python baseline/estimate_2025/extract.py run --batches 0 1  # resumable; one cache file per scene
    python baseline/estimate_2025/extract.py features           # offline: features.csv, skipped fields

Everything that decides a value is imported from baseline/run_baseline.py: the scene
filter (CONFIG), the SCL cloud mask, the reflectance scale and offset, NDVI, the
clear-pixel rule and the feature summary. The only difference is how pixels are read:
the baseline reads one window around all BARC fields, which statewide would be whole
tiles, so this reads one small window per field on the same native 10 m grid. `pilot`
checks that this reproduces the baseline's saved observations for one BARC field-year.
Tiles west of 78 W are UTM zone 17, so the raster's own UTM grid is accepted instead of
only EPSG:32618.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import time
from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pandas as pd
import planetary_computer as pc
import pystac
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds, Window
from pystac_client import Client
from shapely.geometry import box, mapping, shape

from common import MIN_VALID_DATES, OUT, SCENE_CACHE, YEAR, write_json
import run_baseline as rb

CONFIG = rb.CONFIG
GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_TIMEOUT='60',
    GDAL_HTTP_MAX_RETRY='4', GDAL_HTTP_RETRY_DELAY='2',
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif', VSI_CACHE=True)


def read_sample():
    fields = gpd.read_file(OUT / 'sample_fields.geojson')
    fields['id'] = fields['id'].astype(str)
    return fields


def extract_item(item, fields, key='id'):
    """Observations of every field the scene footprint touches. Raises on read failure."""
    interested = fields[fields.geometry.intersects(shape(item.geometry))]
    if interested.empty:
        return []
    date = item.datetime.date().isoformat()
    signed = pc.sign(item)
    baseline = float(item.properties['s2:processing_baseline'])
    records = []
    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(signed.assets['B04'].href) as red_src, \
                rasterio.open(signed.assets['B08'].href) as nir_src, \
                rasterio.open(signed.assets['SCL'].href) as scl_src:
            epsg = red_src.crs.to_epsg()
            if epsg is None or not 32601 <= epsg <= 32660 or red_src.res != (10.0, 10.0):
                raise ValueError(f'Unexpected raster grid: {red_src.crs}, {red_src.res}')
            grid = dict(crs=red_src.crs, transform=red_src.transform, width=red_src.width,
                height=red_src.height, resampling=Resampling.nearest)
            full = Window(0, 0, red_src.width, red_src.height)
            # SCL is native 20 m: align to red's 10 m grid using nearest, as the baseline does.
            with WarpedVRT(nir_src, **grid) as nir_vrt, WarpedVRT(scl_src, **grid) as scl_vrt:
                for row in interested.to_crs(red_src.crs).itertuples():
                    w = from_bounds(*row.geometry.bounds, red_src.transform)
                    c0, r0 = int(np.floor(w.col_off)), int(np.floor(w.row_off))
                    c1, r1 = int(np.ceil(w.col_off + w.width)), int(np.ceil(w.row_off + w.height))
                    try:
                        window = Window(c0, r0, c1 - c0, r1 - r0).intersection(full)
                    except rasterio.errors.WindowError:
                        continue  # the footprint touches the field but the raster grid does not
                    if window.width <= 0 or window.height <= 0:
                        continue
                    transform = red_src.window_transform(window)
                    red = red_src.read(1, window=window, masked=True)
                    nir = nir_vrt.read(1, window=window, masked=True)
                    scl = scl_vrt.read(1, window=window, masked=True)
                    masks = [~np.ma.getmaskarray(a) for a in (red, nir, scl)]
                    red_ref, red_cal = rb.reflectance(red.filled(0), item.assets['B04'], baseline)
                    nir_ref, nir_cal = rb.reflectance(nir.filled(0), item.assets['B08'], baseline)
                    good = np.logical_and.reduce(masks) & np.isin(scl.filled(0), CONFIG['valid_scl'])
                    values = rb.ndvi_values(red_ref, nir_ref, good)
                    inside = geometry_mask([mapping(row.geometry)], out_shape=values.shape,
                        transform=transform, invert=True, all_touched=False)
                    total = int(inside.sum())
                    vals = values[inside]
                    vals = vals[np.isfinite(vals)]
                    clear = len(vals)
                    fraction = clear / total if total else 0
                    accepted = clear >= CONFIG['min_pixels'] and fraction >= CONFIG['min_clear_fraction']
                    records.append({key: getattr(row, key), 'item_id': item.id, 'date': date,
                        'scene_cloud_percent': item.properties.get('eo:cloud_cover'),
                        'field_pixels': total, 'clear_pixels': clear, 'clear_fraction': fraction,
                        'ndvi': float(np.median(vals)) if accepted else None,
                        'status': 'ok' if accepted else 'insufficient_clear_pixels',
                        'processing_baseline': baseline,
                        'offset': [red_cal['offset'], nir_cal['offset']]})
    return records


def search_items(geometry, year):
    client = Client.open(CONFIG['catalog'])
    for attempt in range(6):
        try:
            return sorted(client.search(collections=[CONFIG['collection']], intersects=mapping(geometry),
                datetime=f'{year}-07-01/{year}-11-30',
                query={'eo:cloud_cover': {'lt': CONFIG['scene_cloud_lt']}}).items(), key=lambda i: i.id)
        except Exception as exc:  # flaky network: retry the whole search
            print(f'catalog attempt {attempt + 1} failed: {type(exc).__name__}', flush=True)
            time.sleep(5)
    raise RuntimeError('Catalog search failed after retries')


def catalog():
    fields = read_sample()
    items = search_items(box(*fields.total_bounds), YEAR)
    SCENE_CACHE.mkdir(parents=True, exist_ok=True)
    (SCENE_CACHE / 'catalog.json').write_text(json.dumps([i.to_dict() for i in items]), encoding='utf-8')
    write_json(OUT / 'catalog.json', dict(
        retrieved_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        query=dict(collection=CONFIG['collection'], catalog=CONFIG['catalog'],
            intersects_bbox=[round(v, 5) for v in fields.total_bounds],
            datetime=f'{YEAR}-07-01/{YEAR}-11-30', cloud_lt=CONFIG['scene_cloud_lt']),
        scenes=len(items), item_ids=[i.id for i in items]))
    print(f'{len(items)} scenes', flush=True)


def load_items():
    return [pystac.Item.from_dict(d) for d in json.loads((SCENE_CACHE / 'catalog.json').read_text())]


def scene_path(batch, item_id):
    return SCENE_CACHE / f'batch_{batch}' / f'{item_id}.json'


def run_scene(item, fields, batch, attempts=3):
    path = scene_path(batch, item.id)
    error = None
    for attempt in range(attempts):
        try:
            records = extract_item(item, fields)
            write_json(path, dict(item_id=item.id, status='ok', records=records))
            return len(records), None
        except Exception as exc:
            # No signed URLs/tokens in stored errors.
            error = f'{type(exc).__name__}: {str(exc).split("?")[0][:300]}'
            time.sleep(3 * (attempt + 1))
    interested = fields[fields.geometry.intersects(shape(item.geometry))]
    write_json(path, dict(item_id=item.id, status='read_error', error=error,
        records=[dict(id=i, item_id=item.id, date=item.datetime.date().isoformat(), ndvi=None,
            status='read_error') for i in interested.id]))
    return 0, error


def run(batches, workers, retry_errors):
    fields, items = read_sample(), load_items()
    for batch in batches:
        selected = fields[fields.batch == batch]
        todo = []
        for item in items:
            path = scene_path(batch, item.id)
            if path.exists() and not (retry_errors and json.loads(path.read_text())['status'] != 'ok'):
                continue
            if selected.geometry.intersects(shape(item.geometry)).any():
                todo.append(item)
        print(f'batch {batch}: {len(selected)} fields, {len(todo)} scenes to read', flush=True)
        started, errors = time.time(), 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run_scene, item, selected, batch) for item in todo]
            for n, future in enumerate(as_completed(futures), 1):
                _, error = future.result()
                errors += error is not None
                if n % 25 == 0 or n == len(todo):
                    print(f'  batch {batch}: {n}/{len(todo)} scenes, {errors} read errors, '
                          f'{time.time() - started:.0f} s', flush=True)
        write_json(SCENE_CACHE / f'batch_{batch}' / '_done.json', dict(
            finished_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'), read_errors=errors))


def completed_batches():
    done = []
    for path in sorted(SCENE_CACHE.glob('batch_*/_done.json')):
        done.append(int(path.parent.name.split('_')[1]))
    return sorted(done)


def features():
    """Offline. Uses whole finished batches only, so the scored fields stay a random sample."""
    fields = read_sample()
    batches = completed_batches()
    if not batches:
        raise RuntimeError('No finished batch; run extraction first')
    fields = fields[fields.batch.isin(batches)]
    by_field = {i: [] for i in fields.id}
    scene_errors = 0
    for batch in batches:
        for path in sorted((SCENE_CACHE / f'batch_{batch}').glob('S2*.json')):
            scene = json.loads(path.read_text())
            scene_errors += scene['status'] != 'ok'
            for record in scene['records']:
                by_field[record['id']].append(record)
    rows, observations = [], []
    for field in fields.itertuples():
        obs = sorted(by_field[field.id], key=lambda r: (r['date'], r['item_id']))
        row = SimpleNamespace(OBJECTID=int(field.id), year=YEAR, label=None)
        summary = rb.summarize(row, dict(observations=obs))
        del summary['OBJECTID'], summary['label']
        rows.append(dict(id=field.id, county=field.county, acres=field.acres, batch=field.batch, **summary))
        observations.extend(obs)
    table = pd.DataFrame(rows)
    table['status'] = np.where(table.valid_dates >= MIN_VALID_DATES, 'ok', 'too_few_clear_dates')
    table.loc[(table.status != 'ok') & (table.read_errors > 0) &
              (table.valid_dates + table.read_errors >= MIN_VALID_DATES), 'status'] = 'read_error'
    table.loc[table.scene_observations == 0, 'status'] = 'no_intersecting_scenes'
    table.to_csv(OUT / 'features.csv', index=False)
    table[table.status != 'ok'].to_csv(OUT / 'skipped_fields.csv', index=False)
    keep = ['id', 'item_id', 'date', 'scene_cloud_percent', 'field_pixels', 'clear_pixels',
            'clear_fraction', 'ndvi', 'status', 'processing_baseline']
    pd.DataFrame(observations).reindex(columns=keep).to_csv(OUT / 'observations.csv.gz', index=False)
    report = dict(batches=batches, fields=int(len(table)), scored_fields=int((table.status == 'ok').sum()),
        skipped=table[table.status != 'ok'].status.value_counts().to_dict(),
        scene_read_errors=int(scene_errors), field_scene_records=len(observations),
        accepted_records=int(sum(r['status'] == 'ok' for r in observations)),
        valid_dates_min_median_max=[int(table.valid_dates.min()), float(table.valid_dates.median()),
                                    int(table.valid_dates.max())],
        missing_feature_counts={k: int(v) for k, v in table.loc[table.status == 'ok', rb.FEATURES].isna().sum().items()},
        min_valid_dates=MIN_VALID_DATES)
    write_json(OUT / 'extraction.json', report)
    print(json.dumps(report, indent=2), flush=True)


def pilot():
    """Gate 1: reproduce the baseline's saved observations for BARC field 1 / 2021.
    Gate 2: one sampled 2025 field has enough clear dates and no read failures."""
    labels = rb.read_labels()
    row = labels.iloc[0]
    saved = json.loads(rb.cache_path(row).read_text())['observations']
    catalog_file = next(iter(sorted((rb.CACHE / 'catalog').glob(f'{int(row.year)}_*.json'))))
    items = {d['id']: pystac.Item.from_dict(d) for d in json.loads(catalog_file.read_text())['items']}
    one = gpd.GeoDataFrame([dict(id=str(int(row.OBJECTID)), geometry=row.geometry)], crs=4326)
    worst, compared, mismatched = 0.0, 0, []
    for old in saved:
        new = extract_item(items[old['item_id']], one)
        assert len(new) == 1, old['item_id']
        new = new[0]
        same = (new['status'] == old['status'] and new['field_pixels'] == old['field_pixels']
                and new['clear_pixels'] == old['clear_pixels'])
        if old['ndvi'] is not None and new['ndvi'] is not None:
            worst = max(worst, abs(new['ndvi'] - old['ndvi']))
        if not same or (old['ndvi'] is None) != (new['ndvi'] is None):
            mismatched.append(old['item_id'])
        compared += 1
    barc = dict(field=int(row.OBJECTID), year=int(row.year), scenes_compared=compared,
        mismatched_scenes=mismatched, max_abs_ndvi_difference=worst,
        passed=not mismatched and worst < 1e-6)
    print('BARC reproduction:', json.dumps(barc), flush=True)

    fields = read_sample()
    field = fields[fields.order == 0]
    scenes = search_items(field.geometry.iloc[0], YEAR)
    obs, errors = [], 0
    for item in scenes:
        try:
            obs.extend(extract_item(item, field))
        except Exception as exc:
            errors += 1
            print('read error', item.id, type(exc).__name__, flush=True)
    summary = rb.summarize(SimpleNamespace(OBJECTID=int(field.id.iloc[0]), year=YEAR, label=None),
        dict(observations=obs))
    summary = {k: None if isinstance(v, float) and not np.isfinite(v) else v for k, v in summary.items()}
    offsets = sorted({(o['processing_baseline'], *o['offset']) for o in obs})
    new = dict(field=field.id.iloc[0], county=field.county.iloc[0], acres=round(float(field.acres.iloc[0]), 2),
        candidate_scenes=len(scenes), scene_read_errors=errors,
        processing_baseline_and_offsets=[list(o) for o in offsets], summary=summary,
        passed=summary['valid_dates'] >= MIN_VALID_DATES and errors == 0)
    print('2025 field:', json.dumps(new), flush=True)
    write_json(OUT / 'pilot.json', dict(passed=barc['passed'] and new['passed'],
        checked_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        barc_reproduction=barc, field_2025=new))
    if not (barc['passed'] and new['passed']):
        raise RuntimeError('Pilot gate failed; do not expand')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['pilot', 'catalog', 'run', 'features'])
    parser.add_argument('--batches', type=int, nargs='*', default=[0])
    parser.add_argument('--workers', type=int, default=12)
    parser.add_argument('--retry-errors', action='store_true')
    args = parser.parse_args()
    if args.stage == 'run':
        run(args.batches, args.workers, args.retry_errors)
    else:
        {'pilot': pilot, 'catalog': catalog, 'features': features}[args.stage]()
