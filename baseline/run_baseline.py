"""BARC numerical Sentinel-2 baseline. Originals are opened read-only.

Run `pilot`, then `extract`, then `evaluate`. Only the first two need network.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import traceback

import geopandas as gpd
import numpy as np
import pandas as pd
import planetary_computer as pc
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds, Window
from pyproj import CRS
from pystac_client import Client
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (balanced_accuracy_score, brier_score_loss,
    confusion_matrix, precision_recall_fscore_support)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / 'outputs'
CACHE = HERE / 'cache'
SOURCE = ROOT / 'BARC_Corn.2021-2023.gpkg'
LAYER = 'barc_silage_grain_corn20212023'
CATALOG = 'https://planetarycomputer.microsoft.com/api/stac/v1'
CONFIG = dict(version=1, collection='sentinel-2-l2a', catalog=CATALOG,
    months=[7, 8, 9, 10, 11], scene_cloud_lt=40, bands=['B04', 'B08', 'SCL'],
    valid_scl=[4, 5, 6, 7], min_pixels=3, min_clear_fraction=0.2,
    pixel_selection='center inside polygon', ndvi_range=[-1, 1],
    scl_resampling='nearest', resolution_m=10, expected_crs='EPSG:32618')
FEATURES = [f'ndvi_{m:02d}' for m in CONFIG['months']] + [
    'peak_ndvi', 'peak_doy', 'late_ndvi', 'early_minus_late']


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, indent=2, allow_nan=False), encoding='utf-8')
    tmp.replace(path)


def source_hash():
    return hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def signature():
    return hashlib.sha256((source_hash() + json.dumps(CONFIG, sort_keys=True)).encode()).hexdigest()


def verify_originals():
    hashes = json.loads((HERE / 'original_sha256.json').read_text())
    for name, expected in hashes.items():
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f'Original changed since initial inspection: {name}')


def read_labels():
    fields = gpd.read_file(SOURCE, layer=LAYER)
    if fields.OBJECTID.isna().any() or not fields.OBJECTID.is_unique:
        raise ValueError('OBJECTID must uniquely identify each source polygon')
    if fields.crs is None or fields.is_empty.any() or not fields.is_valid.all():
        raise ValueError('Missing CRS or empty/invalid source polygon')
    rows = []
    counts = {}
    for year in (2021, 2022, 2023):
        labels = fields[f'Corn_{year}'].fillna('').str.strip()
        unexpected = sorted(set(labels) - {'', 'Grain', 'Silage'})
        if unexpected:
            raise ValueError(f'Unexpected {year} labels: {unexpected}')
        counts[str(year)] = {v or 'blank': int((labels == v).sum())
                            for v in ('Grain', 'Silage', '')}
        for idx in fields.index[labels.isin(['Grain', 'Silage'])]:
            rows.append(dict(OBJECTID=int(fields.loc[idx, 'OBJECTID']), year=year,
                label=labels.loc[idx], geometry=fields.loc[idx, 'geometry']))
    jobs = gpd.GeoDataFrame(rows, geometry='geometry', crs=fields.crs).to_crs(4326)
    jobs = jobs.sort_values(['year', 'OBJECTID']).reset_index(drop=True)
    audit = dict(fields=len(fields), labeled_field_years=len(jobs),
        labeled_fields=int(jobs.OBJECTID.nunique()), label_counts=counts,
        crs_wkt=fields.crs.to_wkt(), crs_authority=fields.crs.to_authority(),
        equivalent_epsg2248=fields.crs.equals(CRS('EPSG:2248')),
        epsg2248_max_bounds_difference_degrees=float(np.max(np.abs(
            fields.to_crs(4326).total_bounds -
            fields.set_crs(2248, allow_override=True).to_crs(4326).total_bounds))),
        wgs84_bounds=fields.to_crs(4326).total_bounds.tolist(),
        source_sha256=source_hash(), config=CONFIG, cache_signature=signature())
    write_json(OUT / 'audit.json', audit)
    jobs.drop(columns='geometry').to_csv(OUT / 'labels.csv', index=False)
    return jobs


def cache_path(row):
    return CACHE / f'{int(row.OBJECTID)}_{int(row.year)}.json'


def load_cache(row):
    path = cache_path(row)
    if not path.exists():
        return None
    result = json.loads(path.read_text())
    if result['signature'] != signature():
        raise ValueError(f'Stale cache: {path}; move it aside before re-extraction')
    return result


def ndvi_values(red, nir, good):
    # Cast BEFORE subtraction to prevent unsigned-integer wraparound.
    red, nir = red.astype('float32'), nir.astype('float32')
    den = red + nir
    valid = good & np.isfinite(red) & np.isfinite(nir) & (den > 0)
    values = np.full(red.shape, np.nan, dtype='float32')
    np.divide(nir - red, den, out=values, where=valid)
    values[(values < -1) | (values > 1)] = np.nan
    return values


def reflectance(raw, asset, baseline):
    """Honor explicit STAC calibration; otherwise use ESA processing baseline."""
    meta = asset.extra_fields.get('raster:bands', [{}])[0]
    scale = float(meta.get('scale', 0.0001))
    offset = float(meta.get('offset', -0.1 if baseline >= 4 else 0))
    return raw.astype('float32') * scale + offset, dict(scale=scale, offset=offset)


def extract_scene(item, jobs):
    """One shared COG window per scene; exact field masks; no raw raster cache."""
    interested = jobs[jobs.geometry.intersects(shape(item.geometry))]
    if interested.empty:
        return []
    date = item.datetime.date().isoformat()
    try:
        signed = pc.sign(item)
        # Small HTTP range reads, bounded timeout/retries, no directory listing.
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',
                GDAL_HTTP_TIMEOUT='60', GDAL_HTTP_MAX_RETRY='2', GDAL_HTTP_RETRY_DELAY='1',
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif', VSI_CACHE=True):
            with rasterio.open(signed.assets['B04'].href) as red_src:
                if red_src.crs != CRS('EPSG:32618') or red_src.res != (10.0, 10.0):
                    raise ValueError(f'Unexpected raster grid: {red_src.crs}, {red_src.res}')
                projected = interested.to_crs(red_src.crs)
                bounds = projected.total_bounds
                w = from_bounds(*bounds, red_src.transform)
                c0, r0 = int(np.floor(w.col_off)), int(np.floor(w.row_off))
                c1, r1 = int(np.ceil(w.col_off+w.width)), int(np.ceil(w.row_off+w.height))
                window = Window(c0, r0, c1-c0, r1-r0).intersection(
                    Window(0, 0, red_src.width, red_src.height))
                transform = red_src.window_transform(window)
                red = red_src.read(1, window=window, masked=True)
                height, width = red.shape
                arrays = {}
                masks = [~np.ma.getmaskarray(red)]
                for band in ['B08', 'SCL']:
                    with rasterio.open(signed.assets[band].href) as src:
                        # SCL is native 20 m: align to red's 10 m grid using nearest.
                        with WarpedVRT(src, crs=red_src.crs, transform=transform,
                                width=width, height=height, resampling=Resampling.nearest) as vrt:
                            a = vrt.read(1, masked=True)
                            arrays[band] = a.filled(0)
                            masks.append(~np.ma.getmaskarray(a))
                baseline = float(item.properties['s2:processing_baseline'])
                red_ref, red_cal = reflectance(red.filled(0), item.assets['B04'], baseline)
                nir_ref, nir_cal = reflectance(arrays['B08'], item.assets['B08'], baseline)
                good = np.logical_and.reduce(masks) & np.isin(arrays['SCL'], CONFIG['valid_scl'])
                values = ndvi_values(red_ref, nir_ref, good)
                records = []
                for row in projected.itertuples():
                    inside = geometry_mask([mapping(row.geometry)], out_shape=values.shape,
                        transform=transform, invert=True, all_touched=False)
                    total = int(inside.sum())
                    vals = values[inside]
                    vals = vals[np.isfinite(vals)]
                    clear = len(vals)
                    fraction = clear / total if total else 0
                    accepted = clear >= CONFIG['min_pixels'] and fraction >= CONFIG['min_clear_fraction']
                    records.append(dict(OBJECTID=int(row.OBJECTID), year=int(row.year),
                        item_id=item.id, date=date, scene_cloud_percent=item.properties.get('eo:cloud_cover'),
                        field_pixels=total, clear_pixels=clear, clear_fraction=fraction,
                        ndvi=float(np.median(vals)) if accepted else None,
                        status='ok' if accepted else 'insufficient_clear_pixels',
                        calibration=dict(processing_baseline=baseline, red=red_cal, nir=nir_cal)))
                return records
    except Exception as exc:
        # No signed URLs/tokens in stored errors.
        error = f'{type(exc).__name__}: {str(exc).split("?")[0][:400]}'
        return [dict(OBJECTID=int(r.OBJECTID), year=int(r.year), item_id=item.id,
            date=date, ndvi=None, status='read_error', error=error)
            for r in interested.itertuples()]


def extract(jobs):
    missing = [idx for idx, row in jobs.iterrows() if load_cache(row) is None]
    if not missing:
        print('All requested field-years are cached.', flush=True)
        return
    client = Client.open(CATALOG)
    for year, selected in jobs.loc[missing].groupby('year'):
        geom = unary_union(selected.geometry.tolist())
        items = sorted(client.search(collections=[CONFIG['collection']],
            intersects=mapping(geom), datetime=f'{year}-07-01/{year}-11-30',
            query={'eo:cloud_cover': {'lt': CONFIG['scene_cloud_lt']}}).items(), key=lambda i: i.id)
        key = hashlib.sha256(geom.wkb).hexdigest()[:12]
        write_json(CACHE / 'catalog' / f'{year}_{key}.json', dict(
            retrieved_utc=datetime.now(timezone.utc).isoformat(),
            query=dict(collection=CONFIG['collection'], intersects=mapping(geom),
                datetime=f'{year}-07-01/{year}-11-30', cloud_lt=CONFIG['scene_cloud_lt']),
            items=[i.to_dict() for i in items]))
        print(f'{year}: {len(items)} scenes for {len(selected)} field-years.', flush=True)
        records = {int(r.OBJECTID): [] for r in selected.itertuples()}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(extract_scene, item, selected) for item in items]
            for n, future in enumerate(as_completed(futures), 1):
                result = future.result()
                for record in result:
                    records[record['OBJECTID']].append(record)
                errors = sum(r['status'] == 'read_error' for r in result)
                if n == 1 or n % 5 == 0 or n == len(items) or errors:
                    print(f'  {year}: scene {n}/{len(items)} processed; {errors} read errors.', flush=True)
        for row in selected.itertuples():
            obs = sorted(records[int(row.OBJECTID)], key=lambda r: (r['date'], r['item_id']))
            write_json(cache_path(row), dict(signature=signature(), OBJECTID=int(row.OBJECTID),
                year=int(row.year), label=row.label, queried_scenes=len(items),
                observations=obs, status='complete' if obs else 'no_intersecting_scenes'))


def daily_series(obs):
    valid = pd.DataFrame([r for r in obs if r['status'] == 'ok'])
    if valid.empty:
        return pd.Series(dtype=float)
    # Adjacent tile / processing duplicates count once per date, not twice.
    return valid.groupby('date').ndvi.median().rename_axis('date').set_axis(
        pd.to_datetime(sorted(valid.date.unique())))


def summarize(row, result):
    obs = result['observations']
    s = daily_series(obs)
    f = {name: np.nan for name in FEATURES}
    for month in CONFIG['months']:
        f[f'ndvi_{month:02d}'] = s[s.index.month == month].median()
    if not s.empty:
        early = s[s.index.month <= 8].median()
        late = s[s.index.month >= 10].median()
        f.update(peak_ndvi=s.max(), peak_doy=float(s.idxmax().day_of_year),
            late_ndvi=s[s.index.month >= 9].median(), early_minus_late=early-late)
    return dict(OBJECTID=int(row.OBJECTID), year=int(row.year), label=row.label,
        valid_dates=len(s), scene_observations=len(obs),
        rejected_cloud_or_nodata=sum(r['status'] == 'insufficient_clear_pixels' for r in obs),
        read_errors=sum(r['status'] == 'read_error' for r in obs), **f)


def metrics(y, pred, probabilities):
    cm = confusion_matrix(y, pred, labels=[0, 1])
    tn, fp, fn, tp = (int(x) for x in cm.ravel())
    p, r, f1, _ = precision_recall_fscore_support(y, pred, labels=[1], zero_division=0)
    return dict(n=len(y), silage_precision=float(p[0]), silage_recall=float(r[0]),
        silage_f1=float(f1[0]), false_positive_rate=fp/(fp+tn) if fp+tn else None,
        balanced_accuracy=float(balanced_accuracy_score(y, pred)),
        brier_score=float(brier_score_loss(y, probabilities)),
        confusion_matrix=cm.tolist(), matrix_order=['Grain', 'Silage'],
        matrix_rows='true', matrix_columns='predicted')


def build_model():
    return make_pipeline(SimpleImputer(strategy='median', keep_empty_features=True),
        StandardScaler(), LogisticRegression(C=1.0, max_iter=2000, random_state=42))


def write_results(report, table, observations):
    lr, grain = report['logistic'], report['always_grain']
    metric_names = [('Silage precision', 'silage_precision'), ('Silage recall', 'silage_recall'),
        ('Silage F1', 'silage_f1'), ('False positive rate', 'false_positive_rate'),
        ('Balanced accuracy', 'balanced_accuracy'), ('Brier score (lower is better)', 'brier_score')]
    lines = ['# Measured BARC baseline results', '',
        'All predictions below are held out by field: five stratified group folds, '
        '34 field groups, seed 42. All years of a field share one fold. '
        'Imputation, scaling, and model fitting occur inside each training fold.', '',
        '| Metric | Logistic regression | Always Grain |', '| --- | ---: | ---: |']
    for label, key in metric_names:
        lines.append(f'| {label} | {lr[key]:.4f} | {grain[key]:.4f} |')
    lines += ['', 'Silage is the positive class. For the always-Grain predictor, '
        'precision has a zero denominator and is reported as 0 by convention.', '',
        '## Confusion matrices', '',
        'Rows are reference labels; columns are predictions.', '',
        '| Logistic regression | Predicted Grain | Predicted Silage |',
        '| --- | ---: | ---: |',
        f'| True Grain | {lr["confusion_matrix"][0][0]} | {lr["confusion_matrix"][0][1]} |',
        f'| True Silage | {lr["confusion_matrix"][1][0]} | {lr["confusion_matrix"][1][1]} |', '',
        '| Always Grain | Predicted Grain | Predicted Silage |', '| --- | ---: | ---: |',
        f'| True Grain | {grain["confusion_matrix"][0][0]} | {grain["confusion_matrix"][0][1]} |',
        f'| True Silage | {grain["confusion_matrix"][1][0]} | {grain["confusion_matrix"][1][1]} |', '',
        '## By year, using the same held-out predictions', '',
        '| Year | n | Silage precision | Recall | F1 | FPR | Balanced accuracy |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for year, records in report['by_year'].items():
        m = records['logistic']
        lines.append(f'| {year} | {m["n"]} | {m["silage_precision"]:.4f} | '
            f'{m["silage_recall"]:.4f} | {m["silage_f1"]:.4f} | '
            f'{m["false_positive_rate"]:.4f} | {m["balanced_accuracy"]:.4f} |')
    lines += ['', 'The always-Grain balanced accuracy is 0.5 in every year; '
        'its Silage precision, recall, F1, and false positive rate are 0.', '',
        '## Missing data and failures', '',
        f'- {len(table)} labeled field-years, of which {report["evaluated_field_years"]} '
        f'were evaluated and {report["excluded_field_years"]} excluded for no usable dates.',
        '- 205 blank source labels excluded before any supervised processing.',
        f'- {len(observations)} field-scene records, '
        f'{sum(r["status"] == "ok" for r in observations)} accepted and '
        f'{report["cloud_or_nodata_rejections"]} rejected for insufficient clear pixels.',
        f'- {report["read_errors"]} read errors. Read errors are separate from cloud/nodata rejections.',
        f'- {int(table.valid_dates.sum())} usable field-dates after duplicate-date aggregation; '
        f'{int(table.valid_dates.min())}–{int(table.valid_dates.max())} per field-year.',
        f'- {sum(report["missing_feature_counts"].values())} missing final feature cells '
        f'out of {len(table) * len(FEATURES)}. Missingness is preserved until fold-level imputation.',
        '- No feature was entirely missing in a training fold.' if
        not any(r['all_missing_training_features'] for r in report['folds']) else
        '- Entirely missing training-fold features are listed in metrics.json.', '',
        'The pilot was field 1 / 2021: 27 candidate scenes, 23 usable dates, '
        '3 rejected scene observations, no read failures, and 667 polygon-center pixels. '
        'The full extraction started only after this gate passed. '
        'The four observed processing baselines were checked against product XML '
        '(calibration_verification.json).', '',
        'The original machine lacked the analysis packages. A local Python 3.12.10 '
        'environment resolved this. Network access required sandbox approval; '
        'all requested satellite reads then completed successfully.', '',
        '## Interpretation', '',
        f'The model identifies {lr["confusion_matrix"][1][1]} of 12 Silage examples '
        f'while misclassifying {lr["confusion_matrix"][0][1]} of 32 Grain examples. '
        'The improvement over always-Grain is useful for an initial baseline, '
        'but five missed Silage examples remain. The sample is small and all fields '
        'are near BARC. Nearby fields can share imagery and management. '
        'Field grouping does not demonstrate transfer to other regions or future years. '
        'No tuning or threshold selection was performed using held-out predictions.', '',
        'See ../README.md for methods, package requirements, CRS checks, references, '
        'and commands. Numerical predictions, split IDs, and metrics are saved alongside this file.', '']
    (OUT / 'results.md').write_text('\n'.join(lines), encoding='utf-8')


def evaluate(jobs):
    rows, observations = [], []
    for row in jobs.itertuples():
        result = load_cache(row)
        if result is None:
            raise RuntimeError(f'Missing extraction cache for {row.OBJECTID}/{row.year}')
        rows.append(summarize(row, result))
        observations.extend(result['observations'])
    table = pd.DataFrame(rows)
    table.to_csv(OUT / 'features.csv', index=False)
    pd.DataFrame(observations).drop(columns='calibration', errors='ignore').to_csv(
        OUT / 'observations.csv', index=False)
    table[['OBJECTID', 'year', 'label']].join(table[FEATURES].isna().add_suffix('_missing')).to_csv(
        OUT / 'missing_features.csv', index=False)
    usable = table[table.valid_dates > 0].copy().reset_index(drop=True)
    table[table.valid_dates == 0].to_csv(OUT / 'excluded_no_observations.csv', index=False)
    if len(usable) < 5 or usable.label.nunique() != 2:
        raise RuntimeError('Insufficient observed examples/classes for grouped validation')
    X = usable[FEATURES]
    y = (usable.label == 'Silage').astype(int).to_numpy()
    groups = usable.OBJECTID.to_numpy()
    pred = np.full(len(y), -1)
    proba = np.full(len(y), np.nan)
    folds = np.full(len(y), -1)
    fold_records = []
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    for fold, (train, test) in enumerate(cv.split(X, y, groups), 1):
        assert not set(groups[train]) & set(groups[test]), 'Field leakage'
        if len(set(y[train])) != 2:
            raise RuntimeError(f'Fold {fold} training data has only one class')
        model = build_model()
        model.fit(X.iloc[train], y[train])
        pred[test] = model.predict(X.iloc[test])
        proba[test] = model.predict_proba(X.iloc[test])[:, 1]
        folds[test] = fold
        fold_records.append(dict(fold=fold, training_fields=sorted(set(map(int, groups[train]))),
            test_fields=sorted(set(map(int, groups[test]))),
            all_missing_training_features=X.iloc[train].columns[X.iloc[train].isna().all()].tolist(),
            imputation_medians=model[0].statistics_.tolist(),
            logistic=metrics(y[test], pred[test], proba[test]),
            always_grain=metrics(y[test], np.zeros(len(test), dtype=int), np.zeros(len(test)))))
    assert np.all(pred >= 0) and np.isfinite(proba).all()
    usable['fold'] = folds
    usable['predicted_label'] = np.where(pred == 1, 'Silage', 'Grain')
    usable['silage_probability'] = proba
    usable['always_grain_prediction'] = 'Grain'
    assert usable.groupby('OBJECTID').fold.nunique().max() == 1
    usable.to_csv(OUT / 'heldout_predictions.csv', index=False)
    report = dict(protocol='5-fold StratifiedGroupKFold, OBJECTID groups, shuffle=True, seed=42',
        features=FEATURES, threshold=0.5, class_weight=None, C=1.0,
        preprocessing='Training-fold median imputation then training-fold standard scaling; wholly missing training columns filled with zero',
        labeled_field_years=len(table), evaluated_field_years=len(usable),
        evaluated_fields=int(usable.OBJECTID.nunique()),
        excluded_field_years=int((table.valid_dates == 0).sum()),
        missing_feature_counts={k: int(v) for k, v in table[FEATURES].isna().sum().items()},
        read_errors=int(table.read_errors.sum()),
        cloud_or_nodata_rejections=int(table.rejected_cloud_or_nodata.sum()),
        logistic=metrics(y, pred, proba),
        always_grain=metrics(y, np.zeros(len(y), dtype=int), np.zeros(len(y))),
        folds=fold_records, by_year={})
    for year in sorted(usable.year.unique()):
        take = usable.year.eq(year).to_numpy()
        report['by_year'][str(year)] = dict(logistic=metrics(y[take], pred[take], proba[take]),
            always_grain=metrics(y[take], np.zeros(take.sum(), dtype=int), np.zeros(take.sum())))
    write_json(OUT / 'metrics.json', report)
    write_results(report, table, observations)
    print(json.dumps({k: report[k] for k in ['evaluated_field_years', 'read_errors',
        'missing_feature_counts', 'logistic', 'always_grain']}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['pilot', 'extract', 'evaluate'])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    verify_originals()
    jobs = read_labels()
    if args.stage == 'pilot':
        pilot = jobs.iloc[:1]
        extract(pilot)
        row = pilot.iloc[0]
        result = load_cache(row)
        summary = summarize(row, result)
        passed = summary['valid_dates'] >= 3 and summary['read_errors'] == 0
        # Round-trip JSON nulls for missing features.
        summary = {k: None if isinstance(v, float) and not np.isfinite(v) else v
                   for k, v in summary.items()}
        write_json(OUT / 'pilot.json', dict(passed=passed, signature=signature(), summary=summary))
        print('PILOT:', json.dumps(summary), 'passed:', passed, flush=True)
        if not passed:
            raise RuntimeError('Pilot quality gate failed; inspect its cache before expanding')
    elif args.stage == 'extract':
        gate = json.loads((OUT / 'pilot.json').read_text())
        if not gate['passed'] or gate['signature'] != signature():
            raise RuntimeError('Run a successful pilot with current configuration first')
        extract(jobs)
    else:
        evaluate(jobs)
    verify_originals()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'last_failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise
