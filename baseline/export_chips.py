"""Before/after true-color chips for each labeled field-year: baseline/outputs/chips/.

    python baseline/export_chips.py            # needs network: planetarycomputer.microsoft.com and
                                               # sentinel2l2a01.blob.core.windows.net (no key needed)

For each labeled field-year, picks the two consecutive usable scenes (status ok in observations.csv)
with the largest NDVI drop: the last look before the drop ("pre") and the first look after ("post").
Reads the Sentinel-2 L2A true-color asset ("visual", 10 m) for exactly those scene IDs from Microsoft
Planetary Computer, crops a window around the field, outlines the field, and writes
<OBJECTID>_<year>_{pre,post}.png plus chips/index.json (scene IDs, dates, NDVI) for provenance.
Never substitutes another scene: if a scene cannot be read, that chip is skipped and logged.
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import planetary_computer  # noqa: E402
import rasterio  # noqa: E402
from pystac_client import Client  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'baseline' / 'outputs'
CHIPS = OUT / 'chips'
GPKG = ROOT / 'BARC_Corn.2021-2023.gpkg'
LAYER = 'barc_silage_grain_corn20212023'
STAC = 'https://planetarycomputer.microsoft.com/api/stac/v1'
PAD_M = 120  # metres of context around the field


def pick_scenes() -> dict:
    """{(oid, year): (pre_row, post_row)} for labeled field-years, from usable observations only."""
    with (OUT / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as f:
        labeled = {(int(r['OBJECTID']), int(r['year'])) for r in csv.DictReader(f)}
    obs = defaultdict(list)
    with (OUT / 'observations.csv').open(encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            key = (int(r['OBJECTID']), int(r['year']))
            if key in labeled and r['status'] == 'ok' and r['ndvi'] not in ('', None):
                obs[key].append(r)
    picks = {}
    for key, rows in obs.items():
        rows.sort(key=lambda r: (r['date'], r['item_id']))
        if len(rows) < 2:
            continue
        drops = [float(a['ndvi']) - float(b['ndvi']) for a, b in zip(rows, rows[1:])]
        i = int(np.argmax(drops))
        picks[key] = (rows[i], rows[i + 1])
    return picks


def render(item, geom, path: Path, title: str) -> None:
    href = planetary_computer.sign(item.assets['visual'].href)
    with rasterio.open(href) as src:
        shape = gpd.GeoSeries([geom], crs=4326).to_crs(src.crs).iloc[0]
        minx, miny, maxx, maxy = shape.bounds
        window = from_bounds(minx - PAD_M, miny - PAD_M, maxx + PAD_M, maxy + PAD_M, src.transform)
        rgb = src.read([1, 2, 3], window=window, boundless=True, fill_value=0)
        transform = src.window_transform(window)
    left, top = transform * (0, 0)
    right, bottom = transform * (rgb.shape[2], rgb.shape[1])
    fig, ax = plt.subplots(figsize=(3.2, 3.2), dpi=100)
    ax.imshow(np.moveaxis(rgb, 0, -1), extent=(left, right, bottom, top))
    for poly in getattr(shape, 'geoms', [shape]):
        x, y = poly.exterior.xy
        ax.plot(x, y, color='#ffd400', linewidth=1.6)
    ax.set_title(title, fontsize=9)
    ax.set_axis_off()
    fig.tight_layout(pad=0.2)
    fig.savefig(path)
    plt.close(fig)


def main() -> dict:
    CHIPS.mkdir(parents=True, exist_ok=True)
    fields = gpd.read_file(GPKG, layer=LAYER).to_crs(4326).set_index('OBJECTID')
    picks = pick_scenes()
    ids = sorted({r['item_id'] for pre, post in picks.values() for r in (pre, post)})
    catalog = Client.open(STAC)
    items = {}
    for start in range(0, len(ids), 50):
        for item in catalog.search(collections=['sentinel-2-l2a'], ids=ids[start:start + 50]).items():
            items[item.id] = item
    index, missing = {}, []
    for (oid, year), (pre, post) in sorted(picks.items()):
        entry = {}
        for which, row in (('pre', pre), ('post', post)):
            item = items.get(row['item_id'])
            if item is None:
                missing.append(f"{oid}_{year}_{which}: scene {row['item_id']} not found")
                continue
            try:
                render(item, fields.loc[oid].geometry, CHIPS / f'{oid}_{year}_{which}.png',
                       f"{'Before' if which == 'pre' else 'After'} the drop · {row['date']} · NDVI {float(row['ndvi']):.2f}")
            except Exception as exc:  # explicit skip, never a substitute image
                missing.append(f'{oid}_{year}_{which}: {exc}')
                continue
            entry[which] = {'item_id': row['item_id'], 'date': row['date'], 'ndvi': round(float(row['ndvi']), 4)}
        index[f'{oid}_{year}'] = entry
    (CHIPS / 'index.json').write_text(json.dumps({'source': 'Sentinel-2 L2A visual (10 m), Microsoft Planetary Computer',
        'selection': 'consecutive usable scenes with the largest NDVI drop', 'chips': index, 'skipped': missing},
        indent=1), encoding='utf-8')
    written = len(list(CHIPS.glob('*.png')))
    return {'field_years': len(picks), 'png_written': written, 'skipped': missing}


if __name__ == '__main__':
    result = main()
    print(json.dumps(result, indent=2))
    sys.exit(1 if result['skipped'] else 0)
