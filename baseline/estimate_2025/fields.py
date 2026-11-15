"""Steps 1-2: Maryland 2025 corn fields and a seeded sample of them.

    python baseline/estimate_2025/fields.py download   # needs network; writes data/raw/
    python baseline/estimate_2025/fields.py select     # offline

Field polygons are USDA Crop Sequence Boundaries (CSB) from the fiboa copy named in
data/download_csb.sh. That file covers 2016-2023 and carries only a 2023 crop code,
so "corn in 2025" is confirmed against the 2025 Cropland Data Layer (CDL): a field
counts when at least half of its 30 m CDL pixels are class 1 (Corn).
"""
import argparse
from datetime import datetime, timezone
import hashlib

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
import shapely

from common import (ACRE_M2, BATCH_SIZE, CDL_MD, CDL_URL, CORN_CODE, CSB_MD, CSB_URL,
    MIN_CORN_SHARE, OUT, RAW, SAMPLE_SIZE, SEED, YEAR, write_json)

# Maryland in the CSB grid (NAD83 / Conus Albers, metres); ids start with state FIPS 24.
MD_BOX = dict(xmin=1380000, xmax=1830000, ymin=1820000, ymax=2080000)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def download():
    """Read only the Maryland slice of the national parquet (row groups chosen by bbox)."""
    import duckdb
    import urllib.request
    RAW.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute('INSTALL httpfs; LOAD httpfs; SET http_retries=10; SET http_timeout=180000;')
    con.execute(f"""COPY (
        SELECT id, "crop:code" AS crop_code_2023, "crop:name" AS crop_name_2023,
               administrative_area_level_2 AS county, ST_AsWKB(geometry) AS geometry_wkb,
               bbox.xmin AS xmin, bbox.ymin AS ymin, bbox.xmax AS xmax, bbox.ymax AS ymax
        FROM read_parquet('{CSB_URL}')
        WHERE bbox.xmax >= {MD_BOX['xmin']} AND bbox.xmin <= {MD_BOX['xmax']}
          AND bbox.ymax >= {MD_BOX['ymin']} AND bbox.ymin <= {MD_BOX['ymax']}
          AND id LIKE '24%')
        TO '{CSB_MD.as_posix()}' (FORMAT parquet)""")
    urllib.request.urlretrieve(CDL_URL, CDL_MD)
    print('Downloaded', CSB_MD, CDL_MD, flush=True)


def read_csb():
    table = pd.read_parquet(CSB_MD)
    geometry = shapely.from_wkb(table.pop('geometry_wkb').to_numpy())
    # The CSB grid has the parameters of EPSG:5070, which is also the CDL grid.
    fields = gpd.GeoDataFrame(table, geometry=geometry, crs='EPSG:5070')
    if fields.id.isna().any() or not fields.id.is_unique:
        raise ValueError('CSB ids must be unique')
    if fields.is_empty.any():
        raise ValueError('Empty CSB polygon')
    return fields.sort_values('id').reset_index(drop=True)


def corn_share_2025(fields):
    """Share of each field's CDL 2025 pixel centres that are corn; exact, no resampling."""
    with rasterio.open(CDL_MD) as src:
        if src.crs.to_epsg() != 5070 or src.res != (30.0, 30.0):
            raise ValueError(f'Unexpected CDL grid: {src.crs}, {src.res}')
        cdl = src.read(1)
        transform = src.transform
    index = rasterize(((g, i + 1) for i, g in enumerate(fields.geometry)), out_shape=cdl.shape,
        transform=transform, fill=0, dtype='uint32', all_touched=False)
    n = len(fields) + 1
    pixels = np.bincount(index.ravel(), minlength=n)[1:]
    corn = np.bincount(index[cdl == CORN_CODE].ravel(), minlength=n)[1:]
    state_corn_pixels = int((cdl == CORN_CODE).sum())
    in_fields = int(corn.sum())
    return pixels, corn, state_corn_pixels, in_fields


def select():
    fields = read_csb()
    pixels, corn, state_corn_pixels, corn_pixels_in_fields = corn_share_2025(fields)
    fields['acres'] = fields.geometry.area / ACRE_M2
    fields['cdl_pixels'] = pixels
    fields['corn_share_2025'] = np.where(pixels > 0, corn / np.maximum(pixels, 1), np.nan)
    is_corn = (pixels > 0) & (fields.corn_share_2025 >= MIN_CORN_SHARE)
    population = fields[is_corn].copy()

    # Proportional allocation by county, largest remainders, then one seeded draw per county.
    rng = np.random.default_rng(SEED)
    size = min(SAMPLE_SIZE, len(population))
    counts = population.county.value_counts().sort_index()
    exact = counts / counts.sum() * size
    take = np.floor(exact).astype(int)
    for county in (exact - take).sort_values(ascending=False, kind='stable').index[:size - int(take.sum())]:
        take[county] += 1
    chosen = []
    for county, k in take.items():
        ids = population.id[population.county == county].to_numpy()
        chosen.extend(rng.choice(ids, size=int(k), replace=False).tolist())
    sample = population[population.id.isin(chosen)].copy()
    # A seeded random order: any prefix (whole batches) is itself a random sample.
    sample['order'] = rng.permutation(len(sample))
    sample = sample.sort_values('order').reset_index(drop=True)
    sample['batch'] = sample.order // BATCH_SIZE
    lonlat = sample.geometry.centroid.to_crs(4326)
    sample['lon'], sample['lat'] = lonlat.x.round(5), lonlat.y.round(5)

    OUT.mkdir(parents=True, exist_ok=True)
    columns = ['id', 'county', 'acres', 'cdl_pixels', 'corn_share_2025', 'crop_code_2023',
               'lon', 'lat', 'order', 'batch']
    sample[columns].round({'acres': 3, 'corn_share_2025': 4}).to_csv(OUT / 'sample_fields.csv', index=False)
    sample[['id', 'county', 'acres', 'order', 'batch', 'geometry']].to_crs(4326).to_file(
        OUT / 'sample_fields.geojson', driver='GeoJSON', COORDINATE_PRECISION=6)
    by_county = population.groupby('county').agg(corn_fields=('id', 'size'), corn_acres=('acres', 'sum'))
    by_county['sampled_fields'] = sample.county.value_counts()
    by_county.fillna(0).astype({'sampled_fields': int}).round({'corn_acres': 1}).to_csv(OUT / 'population_by_county.csv')
    report = dict(
        year=YEAR, generated_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        csb_fields_maryland=int(len(fields)), csb_fields_without_cdl_pixels=int((pixels == 0).sum()),
        corn_rule=(f'CSB field with at least {MIN_CORN_SHARE:.0%} of its 30 m CDL {YEAR} pixel centres '
                   f'in class {CORN_CODE} (Corn)'),
        corn_fields_2025=int(len(population)), corn_acres_2025=round(float(population.acres.sum()), 1),
        corn_fields_also_corn_in_2023=int((population.crop_code_2023 == '1').sum()),
        cdl_corn_acres_2025=round(state_corn_pixels * 900 / ACRE_M2, 1),
        cdl_corn_acres_inside_csb_fields=round(corn_pixels_in_fields * 900 / ACRE_M2, 1),
        counties=int(population.county.nunique()),
        sample=dict(seed=SEED, requested_fields=SAMPLE_SIZE, sampled_fields=int(len(sample)),
            sampled_acres=round(float(sample.acres.sum()), 1), stratified_by='county',
            allocation='proportional to corn-field count, largest remainders',
            batch_size=BATCH_SIZE, batches=int(sample.batch.max()) + 1),
        inputs=dict(
            csb=dict(url=CSB_URL, slice='Maryland rows only (id prefix 24)', sha256=sha256(CSB_MD),
                     vintage='CSB 2016-2023; crop code is for 2023'),
            cdl=dict(url=CDL_URL, sha256=sha256(CDL_MD), vintage=f'Cropland Data Layer {YEAR}, Maryland')))
    write_json(OUT / 'population.json', report)
    print({k: v for k, v in report.items() if k not in ('inputs',)}, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['download', 'select'])
    {'download': download, 'select': select}[parser.parse_args().stage]()
