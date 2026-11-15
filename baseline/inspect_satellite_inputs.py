"""Pilot-first imagery checks against cached field-scene measurements.

Small Sentinel-2 windows only; original inputs and all model outputs stay read-only.
Run `pilot`, inspect its reproduced measurements, then run `run`.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
import matplotlib.pyplot as plt
import numpy as np
import planetary_computer as pc
import pystac
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds, Window
from shapely.geometry import mapping

from run_baseline import CONFIG, LAYER, SOURCE, ndvi_values, reflectance, verify_originals, write_json

OUT = HERE / 'outputs' / 'diagnostics' / 'imagery_323_327'
CASES = {323: (2023, ['2023-09-02', '2023-09-07', '2023-09-12', '2023-10-02', '2023-11-16']),
         327: (2021, ['2021-08-23', '2021-09-02', '2021-09-12', '2021-09-27', '2021-10-07', '2021-11-16'])}
BANDS = ['B04', 'B03', 'B02', 'B08', 'SCL']
SCL_NAMES = ['No data', 'Saturated', 'Dark', 'Shadow', 'Vegetation', 'Bare soil',
             'Water', 'Unclassified', 'Cloud medium', 'Cloud high', 'Cirrus', 'Snow']
SCL_COLORS = ['#000000', '#ff0000', '#555555', '#7d482d', '#287a35', '#dbc47a',
              '#2869bd', '#999999', '#bbbbbb', '#ffffff', '#81d4e8', '#edb9ed']


def inputs():
    fields = gpd.read_file(SOURCE, layer=LAYER)
    items = {}
    for path in (HERE / 'cache/catalog').glob('*.json'):
        for item in json.loads(path.read_text())['items']:
            items[item['id']] = item
    recovered_dir = HERE / 'outputs/diagnostics/scene_filter_gaps'
    recovered = json.loads((recovered_dir / 'observations.json').read_text()) if (recovered_dir / 'observations.json').exists() else []
    for path in recovered_dir.glob('catalog_*.json'):
        for item in json.loads(path.read_text())['items']:
            items[item['id']] = item
    tasks = []
    for field_id, (year, dates) in CASES.items():
        cache = HERE / 'cache' / f'{field_id}_{year}.json'
        saved = json.loads(cache.read_text())
        geom = fields.loc[fields.OBJECTID.eq(field_id)]
        assert len(geom) == 1
        for date in dates:
            candidates = [r for r in list(saved['observations']) + recovered
                          if r['OBJECTID'] == field_id and r['year'] == year
                          and r['date'] == date and r['status'] == 'ok']
            if not candidates:
                raise ValueError(f'No accepted reference observation for {field_id}/{date}')
            # Prefer highest clear fraction; deterministic tie-break by item ID.
            reference = max(candidates, key=lambda r: (r['clear_fraction'], r['item_id']))
            item = items[reference['item_id']]
            fingerprint = hashlib.sha256(json.dumps(dict(version=1, item=item, reference=reference,
                source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                config=CONFIG, buffer_m=100, bands=BANDS), sort_keys=True).encode()).hexdigest()
            tasks.append((field_id, year, date, geom, item, reference, fingerprint))
    return tasks


def read_chip(task):
    field_id, year, date, geom, unsigned, reference, fingerprint = task
    stem = f'{field_id}_{date}'
    arrays_path = OUT / 'chips' / f'{stem}.npz'
    metadata_path = OUT / 'chips' / f'{stem}.json'
    if arrays_path.exists() and metadata_path.exists():
        meta = json.loads(metadata_path.read_text())
        if meta['fingerprint'] != fingerprint:
            raise ValueError(f'Stale diagnostic chip: {stem}')
        with np.load(arrays_path, allow_pickle=False) as cache:
            arrays = {key: cache[key] for key in cache.files}
        print(f'Cached {stem}', flush=True)
        return arrays, meta
    item = pystac.Item.from_dict(unsigned)
    signed = pc.sign(item)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_TIMEOUT='60',
            GDAL_HTTP_MAX_RETRY='2', GDAL_HTTP_RETRY_DELAY='1',
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif', VSI_CACHE=True):
        with rasterio.open(signed.assets['B04'].href) as red_src:
            if str(red_src.crs) != 'EPSG:32618' or red_src.res != (10.0, 10.0):
                raise ValueError('Unexpected image CRS or resolution')
            projected = geom.to_crs(red_src.crs)
            left, bottom, right, top = projected.total_bounds
            w = from_bounds(left-100, bottom-100, right+100, top+100, red_src.transform)
            c0, r0 = int(np.floor(w.col_off)), int(np.floor(w.row_off))
            c1, r1 = int(np.ceil(w.col_off+w.width)), int(np.ceil(w.row_off+w.height))
            window = Window(c0, r0, c1-c0, r1-r0).intersection(Window(0, 0, red_src.width, red_src.height))
            transform = red_src.window_transform(window)
            red = red_src.read(1, window=window, masked=True)
            height, width = red.shape
            raw, masks = {'B04': red.filled(0)}, {'B04': ~np.ma.getmaskarray(red)}
            for band in BANDS[1:]:
                with rasterio.open(signed.assets[band].href) as src:
                    with WarpedVRT(src, crs=red_src.crs, transform=transform,
                            width=width, height=height, resampling=Resampling.nearest) as vrt:
                        value = vrt.read(1, masked=True)
                        raw[band], masks[band] = value.filled(0), ~np.ma.getmaskarray(value)
            baseline = float(item.properties['s2:processing_baseline'])
            reflectances, calibration = {}, {}
            for band in BANDS[:-1]:
                reflectances[band], calibration[band] = reflectance(raw[band], item.assets[band], baseline)
            good = masks['B04'] & masks['B08'] & masks['SCL'] & np.isin(raw['SCL'], CONFIG['valid_scl'])
            ndvi = ndvi_values(reflectances['B04'], reflectances['B08'], good)
            inside = geometry_mask([mapping(projected.geometry.iloc[0])], out_shape=ndvi.shape,
                                   transform=transform, invert=True, all_touched=False)
            vals = ndvi[inside & np.isfinite(ndvi)]
            total, clear = int(inside.sum()), len(vals)
            measured = dict(field_pixels=total, clear_pixels=clear, clear_fraction=clear/total,
                            ndvi=float(np.median(vals)))
            assert total == reference['field_pixels'], 'Polygon pixel count mismatch'
            assert clear == reference['clear_pixels'], 'Clear-pixel count mismatch'
            np.testing.assert_allclose(measured['ndvi'], reference['ndvi'], atol=1e-6, rtol=0)
            scl_counts = Counter(map(int, raw['SCL'][inside]))
            rgb = np.stack([reflectances[b] for b in ['B04', 'B03', 'B02']], axis=-1)
            rgb = np.clip(rgb / 0.3, 0, 1) ** (1/2.2)
            rgb[~(masks['B04'] & masks['B03'] & masks['B02'])] = 0
            arrays = dict(rgb=rgb, ndvi=ndvi, inside=inside, scl=raw['SCL'])
            meta = dict(field_id=field_id, year=year, date=date, item_id=item.id,
                scene_cloud_percent=item.properties.get('eo:cloud_cover'),
                processing_baseline=baseline, calibration=calibration, fingerprint=fingerprint,
                crs=str(red_src.crs), transform=list(transform)[:6],
                reference=reference, measured=measured, matches_cached_measurements=True,
                scl_counts={SCL_NAMES[k]: v for k, v in sorted(scl_counts.items())},
                ndvi_quantiles={str(q): float(np.quantile(vals, q)) for q in [.1, .25, .5, .75, .9]},
                fraction_usable_ndvi_over_06=float((vals > .6).mean()),
                rgb_display='Fixed reflectance range 0..0.3, gamma 1/2.2, no per-scene stretch',
                unsigned_assets={b: item.assets[b].href for b in BANDS})
    arrays_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(arrays_path, **arrays)
    write_json(metadata_path, meta)
    print(f'Verified {stem}: {total} field pixels; {clear} clear; NDVI {measured["ndvi"]:.4f}', flush=True)
    return arrays, meta


def plot(field_id, chips, suffix=''):
    fig, axes = plt.subplots(len(chips), 3, figsize=(11, 3.3*len(chips)),
                            squeeze=False, layout='constrained')
    cmap = ListedColormap(SCL_COLORS)
    norm = BoundaryNorm(np.arange(-.5, 12.5), 12)
    for row, (arrays, meta) in enumerate(chips):
        inside = arrays['inside']
        axes[row, 0].imshow(arrays['rgb'])
        image = axes[row, 1].imshow(np.ma.masked_where(~inside, arrays['ndvi']),
                                    vmin=0, vmax=1, cmap='YlGn')
        axes[row, 2].imshow(arrays['scl'], cmap=cmap, norm=norm, interpolation='nearest')
        axes[row, 0].set_ylabel(f'{meta["date"]}\nClear: {meta["measured"]["clear_fraction"]:.0%}\n'
                                f'NDVI: {meta["measured"]["ndvi"]:.3f}', fontsize=10)
        for ax in axes[row]:
            ax.contour(inside.astype(float), levels=[.5], colors=['#ed1677'], linewidths=1.2)
            ax.set_xticks([])
            ax.set_yticks([])
    for ax, title in zip(axes[0], ['True color (fixed display stretch)', 'Cloud-masked NDVI inside field', 'SCL: coarse scene classification']):
        ax.set_title(title, fontsize=10)
    fig.colorbar(image, ax=axes[:, 1].tolist(), label='NDVI', shrink=.5)
    fig.suptitle(f'Field {field_id} / {chips[0][1]["year"]}: input checks, not harvest proof', fontsize=14)
    used = sorted(set(int(k) for arrays, _ in chips for k in np.unique(arrays['scl'])))
    fig.legend(handles=[Patch(facecolor=SCL_COLORS[k], edgecolor='#777777', label=f'{k}: {SCL_NAMES[k]}')
                        for k in used], loc='outside lower center', ncols=4, fontsize=8)
    path = OUT / f'field_{field_id}{suffix}.png'
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return str(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['pilot', 'run'])
    args = parser.parse_args()
    verify_originals()
    tasks = inputs()
    gate = OUT / 'pilot.json'
    if args.stage == 'pilot':
        arrays, meta = read_chip(tasks[0])
        path = plot(tasks[0][0], [(arrays, meta)], '_pilot')
        write_json(gate, dict(passed=True, fingerprint=tasks[0][-1], plot=path,
                             measured=meta['measured'], item_id=meta['item_id']))
        print('Pilot passed: pixel counts and NDVI reproduce the saved extraction.', flush=True)
    else:
        pilot = json.loads(gate.read_text())
        if not pilot['passed'] or pilot['fingerprint'] != tasks[0][-1]:
            raise ValueError('Run the current one-scene pilot first')
        results, failures = {}, []
        for task in tasks:
            try:
                results.setdefault(task[0], []).append(read_chip(task))
            except Exception as exc:
                failures.append(dict(field_id=task[0], date=task[2], error_type=type(exc).__name__,
                                     error=str(exc).split('?')[0][:300]))
                print(f'Failed {task[0]} / {task[2]}: {type(exc).__name__}', flush=True)
        plots = [plot(fid, chips) for fid, chips in results.items() if chips]
        write_json(OUT / 'summary.json', dict(plots=plots, failures=failures,
            scenes=[m for chips in results.values() for _, m in chips]))
        if failures:
            raise RuntimeError(f'{len(failures)} scenes failed; see summary.json')
        print('All image measurements reproduce the cached extraction.', flush=True)
    verify_originals()


if __name__ == '__main__':
    main()
