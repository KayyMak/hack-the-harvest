"""Model calls for BARC field-years with a blank label. Originals are opened read-only.

A blank label is unknown: the field may not have been corn that year. Stages:

  corn     USDA Cropland Data Layer (CDL) corn share for every field-year, labeled
           ones included as a check of the corn rule. Reads a small clip of the
           Maryland CDL GeoTIFF (CDL_URL) by HTTP range requests into data/raw/cdl/
           (gitignored).
  pilot    Sentinel-2 extraction for one blank field-year (--field, --year).
  extract  Same extraction for every blank field-year the corn stage marks likely corn.
  predict  Fit run_baseline.build_model() on the labeled field-years and call the
           likely-corn blank field-years. Offline.

Extraction and features reuse run_baseline.py unchanged (same CONFIG, signature,
masking, calibration and monthly features). Caches go to cache_unlabeled/ and
outputs to outputs/unlabeled/; the baseline's own cache and outputs are not written.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds
from shapely.geometry import mapping
from sklearn.model_selection import StratifiedGroupKFold

import run_baseline as rb

HERE = rb.HERE
ROOT = rb.ROOT
OUT = rb.OUT / 'unlabeled'
CACHE = HERE / 'cache_unlabeled'
CDL_DIR = ROOT / 'data' / 'raw' / 'cdl'
CDL_URL = 'https://nassgeodata.gmu.edu/webservice/nass_data_cache/byfips/CDL_{year}_24.tif'
YEARS = (2021, 2022, 2023)
CORN = 1
# CDL double-crop classes that include corn.
DOUBLE_CROP_CORN = {225: 'Dbl Crop WinWht/Corn', 226: 'Dbl Crop Oats/Corn',
    228: 'Dbl Crop Triticale/Corn', 237: 'Dbl Crop Barley/Corn', 241: 'Dbl Crop Corn/Soybeans'}
CLASS_NAMES = {1: 'Corn', 4: 'Sorghum', 5: 'Soybeans', 12: 'Sweet Corn', 13: 'Pop or Orn Corn',
    21: 'Barley', 23: 'Spring Wheat', 24: 'Winter Wheat', 26: 'Dbl Crop WinWht/Soybeans',
    27: 'Rye', 28: 'Oats', 36: 'Alfalfa', 37: 'Other Hay/Non Alfalfa', 58: 'Clover/Wildflowers',
    59: 'Sod/Grass Seed', 61: 'Fallow/Idle Cropland', 111: 'Open Water',
    121: 'Developed/Open Space', 122: 'Developed/Low Intensity', 123: 'Developed/Med Intensity',
    124: 'Developed/High Intensity', 131: 'Barren', 141: 'Deciduous Forest',
    142: 'Evergreen Forest', 143: 'Mixed Forest', 152: 'Shrubland', 176: 'Grassland/Pasture',
    190: 'Woody Wetlands', 195: 'Herbaceous Wetlands', 205: 'Triticale',
    236: 'Dbl Crop WinWht/Sorghum', 254: 'Dbl Crop Barley/Soybeans', **DOUBLE_CROP_CORN}
LIKELY_CORN_SHARE = 0.5
MIXED_SHARE = 0.2
MIN_CDL_PIXELS = 10
CAVEAT = ('These are model calls on BARC field-years that have no silage/grain label. '
    'There is no reference label to check them against. A field-year is called only when '
    'the USDA Cropland Data Layer shows it was mostly corn that year; CDL itself has errors. '
    'The 95% interval uses the model\'s own probabilities as independent Bernoulli outcomes; '
    'it does not include model error or uncertainty about whether the field was corn.')


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def read_fields():
    fields = gpd.read_file(rb.SOURCE, layer=rb.LAYER)
    if fields.OBJECTID.isna().any() or not fields.OBJECTID.is_unique or fields.crs is None:
        raise ValueError('OBJECTID must be unique and the source CRS declared')
    return fields


def field_years(fields):
    """Every (OBJECTID, year) with its label; blank stays blank (unknown, never Grain)."""
    rows = []
    for year in YEARS:
        labels = fields[f'Corn_{year}'].fillna('').str.strip()
        unexpected = sorted(set(labels) - {'', 'Grain', 'Silage'})
        if unexpected:
            raise ValueError(f'Unexpected {year} labels: {unexpected}')
        for idx in fields.index:
            rows.append(dict(field_id=int(fields.loc[idx, 'OBJECTID']), year=year,
                label=labels.loc[idx] or 'blank', acres=float(fields.loc[idx, 'ACRES'])))
    return pd.DataFrame(rows)


def cdl_shares(fields, year, path):
    """Share of CDL pixels whose centers fall inside each polygon, by class."""
    out = {}
    with rasterio.open(path) as src:
        projected = fields.to_crs(src.crs)
        for row in projected.itertuples():
            window = from_bounds(*row.geometry.buffer(60).bounds, src.transform).round_offsets().round_lengths()
            data = src.read(1, window=window)
            inside = geometry_mask([mapping(row.geometry)], out_shape=data.shape,
                transform=src.window_transform(window), invert=True, all_touched=False)
            values = data[inside]
            values = values[values != (src.nodata if src.nodata is not None else 0)]
            classes, counts = np.unique(values, return_counts=True)
            out[int(row.OBJECTID)] = {int(c): int(n) for c, n in zip(classes, counts)}
        meta = dict(crs=str(src.crs), resolution_m=list(src.res))
    return out, meta


def cdl_clip(fields, year):
    """Clip of the statewide CDL around the BARC fields, read by HTTP range requests.

    The statewide file (~90 MB) is not needed: the clip keeps the source grid, CRS and values.
    """
    path = CDL_DIR / f'CDL_{year}_24_barc_clip.tif'
    if path.exists():
        return path
    url = CDL_URL.format(year=year)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_TIMEOUT='60',
            GDAL_HTTP_MAX_RETRY='5', GDAL_HTTP_RETRY_DELAY='3'):
        with rasterio.open(f'/vsicurl/{url}') as src:
            bounds = fields.to_crs(src.crs).total_bounds + np.array([-300, -300, 300, 300])
            window = from_bounds(*bounds, src.transform).round_offsets().round_lengths()
            data = src.read(1, window=window)
            profile = dict(driver='GTiff', width=data.shape[1], height=data.shape[0], count=1,
                dtype=data.dtype, crs=src.crs, transform=src.window_transform(window),
                nodata=src.nodata, compress='deflate')
    CDL_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp.tif')
    with rasterio.open(tmp, 'w', **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(source_url=url, accessed_utc=utc_now())
    tmp.replace(path)
    return path


CATEGORIES = ('likely_corn', 'mixed', 'not_corn', 'uncertain')


def classify_corn(n_pixels, corn_share):
    """likely_corn: >= 50% corn pixels; mixed: 20-50% (part corn, not called);
    not_corn: < 20%; uncertain: too few CDL pixels to judge."""
    if n_pixels < MIN_CDL_PIXELS:
        return 'uncertain'
    if corn_share >= LIKELY_CORN_SHARE:
        return 'likely_corn'
    return 'mixed' if corn_share >= MIXED_SHARE else 'not_corn'


def corn_stage():
    fields = read_fields()
    table = field_years(fields)
    sources, records = [], []
    for year in YEARS:
        path = cdl_clip(fields, year)
        hist, meta = cdl_shares(fields, year, path)
        with rasterio.open(path) as src:
            tags = src.tags()
        sources.append(dict(year=year, url=tags.get('source_url', CDL_URL.format(year=year)),
            local_clip=f'data/raw/cdl/{path.name} (gitignored)',
            accessed_utc=tags.get('accessed_utc'), **meta))
        for fid, counts in hist.items():
            n = sum(counts.values())
            corn = counts.get(CORN, 0)
            double = sum(counts.get(c, 0) for c in DOUBLE_CROP_CORN)
            top = max(counts, key=counts.get) if counts else None
            records.append(dict(field_id=fid, year=year, cdl_pixels=n, corn_pixels=corn,
                double_crop_corn_pixels=double,
                corn_share=round(corn / n, 4) if n else None,
                corn_incl_double_share=round((corn + double) / n, 4) if n else None,
                top_class=top, top_class_name=CLASS_NAMES.get(top, f'class {top}') if top else None,
                top_class_share=round(counts[top] / n, 4) if n else None,
                classes=json.dumps({str(k): v for k, v in sorted(counts.items(), key=lambda kv: -kv[1])})))
    cdl = pd.DataFrame(records)
    table = table.merge(cdl, on=['field_id', 'year'], how='left', validate='one_to_one')
    labeled = table[table.label != 'blank']
    # Pick the rule that the labeled corn field-years support.
    rules = {}
    for name, col in (('corn_class_only', 'corn_share'), ('corn_incl_double_crop', 'corn_incl_double_share')):
        cats = [classify_corn(n, s or 0) for n, s in zip(labeled.cdl_pixels, labeled[col])]
        rules[name] = dict(share_column=col,
            labeled_passing=sum(c == 'likely_corn' for c in cats), labeled_total=len(labeled),
            labeled_passing_by_label={lab: int(sum(c == 'likely_corn' for c, l in zip(cats, labeled.label) if l == lab))
                                      for lab in ('Grain', 'Silage')},
            blank_likely_corn=int(sum(classify_corn(n, s or 0) == 'likely_corn' for n, s in zip(
                table[table.label == 'blank'].cdl_pixels, table[table.label == 'blank'][col]))))
    rule = 'corn_incl_double_crop' if rules['corn_incl_double_crop']['labeled_passing'] > rules['corn_class_only']['labeled_passing'] else 'corn_class_only'
    share_col = rules[rule]['share_column']
    table['corn_check_share'] = table[share_col]
    table['category'] = [classify_corn(n, s or 0) for n, s in zip(table.cdl_pixels, table[share_col])]
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / 'corn_check.csv', index=False)
    blank = table[table.label == 'blank']
    labeled = table[table.label != 'blank']
    summary = dict(
        generated_utc=utc_now(),
        question='Which blank field-years were corn? A blank label can mean the field was not corn that year.',
        rule=dict(name=rule, share_column=share_col, likely_corn_share_at_least=LIKELY_CORN_SHARE,
            mixed_share_at_least=MIXED_SHARE, min_cdl_pixels=MIN_CDL_PIXELS,
            categories=classify_corn.__doc__.split('\n')[0] + ' ' + classify_corn.__doc__.split('\n')[1].strip(), corn_classes={str(CORN): 'Corn', **{str(k): v for k, v in (
                DOUBLE_CROP_CORN.items() if rule == 'corn_incl_double_crop' else [])}},
            pixel_selection='CDL 30 m pixel centers inside the polygon'),
        rules_compared=rules,
        blank_field_years=len(blank),
        blank_by_category={c: int((blank.category == c).sum()) for c in CATEGORIES},
        blank_by_year={str(y): {c: int(((blank.year == y) & (blank.category == c)).sum())
                                for c in CATEGORIES} for y in YEARS},
        blank_likely_corn_acres={str(y): round(float(blank[(blank.year == y) & (blank.category == 'likely_corn')].acres.sum()), 2)
                                 for y in YEARS},
        blank_not_corn_top_classes=blank[blank.category == 'not_corn'].top_class_name.value_counts().to_dict(),
        labeled_sanity_check=dict(
            field_years=len(labeled),
            likely_corn=int((labeled.category == 'likely_corn').sum()),
            sensitivity=round(float((labeled.category == 'likely_corn').mean()), 4),
            not_passing=labeled[labeled.category != 'likely_corn'][
                ['field_id', 'year', 'label', 'cdl_pixels', 'corn_share', 'corn_incl_double_share',
                 'top_class_name', 'category']].to_dict('records'),
            median_corn_share=float(labeled.corn_share.median())),
        sources=sources)
    rb.write_json(OUT / 'corn_check.json', summary)
    print(json.dumps({k: summary[k] for k in ('rule', 'rules_compared', 'blank_by_category', 'blank_by_year',
        'labeled_sanity_check')}, indent=2, default=str), flush=True)


def blank_jobs(selection):
    """GeoDataFrame in EPSG:4326 with the columns run_baseline.extract/summarize read."""
    fields = read_fields().set_index('OBJECTID')
    rows = [dict(OBJECTID=int(f), year=int(y), label=None, geometry=fields.loc[int(f), 'geometry'])
            for f, y in selection]
    for r in rows:
        label = fields.loc[r['OBJECTID'], f'Corn_{r["year"]}']
        if not pd.isna(label) and str(label).strip():
            raise ValueError(f'{r["OBJECTID"]}/{r["year"]} is labeled; this script only extracts blank field-years')
    jobs = gpd.GeoDataFrame(rows, geometry='geometry', crs=fields.crs).to_crs(4326)
    return jobs.sort_values(['year', 'OBJECTID']).reset_index(drop=True)


def use_unlabeled_cache():
    rb.CACHE = CACHE  # run_baseline.cache_path reads this global at call time


def likely_corn_blanks():
    table = pd.read_csv(OUT / 'corn_check.csv')
    take = table[(table.label == 'blank') & (table.category == 'likely_corn')]
    return list(zip(take.field_id, take.year))


def extract_stage(selection):
    use_unlabeled_cache()
    jobs = blank_jobs(selection)
    rb.extract(jobs)
    for row in jobs.itertuples():
        s = rb.summarize(row, rb.load_cache(row))
        print(json.dumps({k: (None if isinstance(v, float) and not np.isfinite(v) else v)
                          for k, v in s.items()}), flush=True)


def labeled_features():
    table = pd.read_csv(rb.OUT / 'features.csv')
    return table[table.valid_dates > 0].reset_index(drop=True)


def reproduce_heldout(usable):
    """Re-run the saved CV from features.csv; probabilities must match heldout_predictions.csv."""
    X, y = usable[rb.FEATURES], (usable.label == 'Silage').astype(int).to_numpy()
    proba = np.full(len(y), np.nan)
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    for train, test in cv.split(X, y, usable.OBJECTID.to_numpy()):
        model = rb.build_model().fit(X.iloc[train], y[train])
        proba[test] = model.predict_proba(X.iloc[test])[:, 1]
    saved = pd.read_csv(rb.OUT / 'heldout_predictions.csv')
    merged = usable[['OBJECTID', 'year']].assign(p=proba).merge(saved[['OBJECTID', 'year', 'silage_probability']],
        on=['OBJECTID', 'year'], validate='one_to_one')
    return float(np.max(np.abs(merged.p - merged.silage_probability)))


def bernoulli(p, acres):
    expected = float(np.sum(p * acres))
    sd = math.sqrt(float(np.sum(acres * acres * p * (1 - p))))
    return dict(expected_silage_acres=round(expected, 2),
        expected_silage_acres_95ci=[round(max(0.0, expected - 1.96 * sd), 2), round(expected + 1.96 * sd, 2)],
        cv_percent=round(100 * sd / expected, 1) if expected else None)


def kraatz_check(pred, corn):
    """Farm harvest/planting records (Kraatz 2023) on blank field-years: evidence only, never training.

    Every blank field-year with a record is listed, including ones the CDL gate left uncalled."""
    path = ROOT / 'kraatz_labels.csv'
    if not path.exists():
        return []
    k = pd.read_csv(path).dropna(subset=['OBJECTID'])
    k = k[(~k.conflict.astype(bool)) & k.year.isin(YEARS)]
    k = k.assign(field_id=k.OBJECTID.astype(int))
    blank = corn[corn.label == 'blank'][['field_id', 'year', 'corn_check_share', 'category']]
    m = k.merge(blank, on=['field_id', 'year'], how='inner').merge(
        pred[['field_id', 'year', 'predicted_label', 'silage_probability']], on=['field_id', 'year'], how='left')
    return [dict(field_id=int(r.field_id), year=int(r.year), farm_record=r.harvest_type,
        record_source=r.label_source, record_share_inside_polygon=round(float(r.share), 3),
        cdl_corn_share=round(float(r.corn_check_share), 4), corn_category=r.category,
        predicted_label=r.predicted_label if isinstance(r.predicted_label, str) and r.predicted_label else None,
        silage_probability=None if pd.isna(r.silage_probability) else round(float(r.silage_probability), 4))
        for r in m.sort_values(['year', 'field_id']).itertuples()]


def predict_stage():
    use_unlabeled_cache()
    corn = pd.read_csv(OUT / 'corn_check.csv')
    usable = labeled_features()
    max_diff = reproduce_heldout(usable)
    if max_diff > 1e-9:
        raise RuntimeError(f'Cannot reproduce saved held-out probabilities (max diff {max_diff})')
    model = rb.build_model().fit(usable[rb.FEATURES], (usable.label == 'Silage').astype(int))
    jobs = blank_jobs(likely_corn_blanks())
    rows = []
    for row in jobs.itertuples():
        result = rb.load_cache(row)
        if result is None:
            raise RuntimeError(f'Missing extraction cache for {row.OBJECTID}/{row.year}; run extract')
        rows.append(rb.summarize(row, result))
    feats = pd.DataFrame(rows).drop(columns='label').rename(columns={'OBJECTID': 'field_id'})
    feats = feats.merge(corn[['field_id', 'year', 'acres', 'corn_check_share', 'cdl_pixels']],
        on=['field_id', 'year'], validate='one_to_one').rename(columns={'corn_check_share': 'corn_share'})
    feats['missing_features'] = [';'.join(f for f in rb.FEATURES if pd.isna(r[f])) for _, r in feats.iterrows()]
    callable_ = feats.valid_dates > 0
    feats['silage_probability'] = np.nan
    feats['predicted_label'] = ''
    if callable_.any():
        X = feats.loc[callable_, rb.FEATURES]
        feats.loc[callable_, 'silage_probability'] = model.predict_proba(X)[:, 1]
        feats.loc[callable_, 'predicted_label'] = np.where(model.predict(X) == 1, 'Silage', 'Grain')
    feats['status'] = np.where(callable_, 'called', 'no_usable_dates')
    cols = ['field_id', 'year', 'acres', 'corn_share', 'cdl_pixels', 'valid_dates', 'scene_observations',
        'rejected_cloud_or_nodata', 'read_errors', *rb.FEATURES, 'missing_features',
        'silage_probability', 'predicted_label', 'status']
    feats = feats[cols].sort_values(['year', 'field_id'])
    feats.to_csv(OUT / 'predictions.csv', index=False)

    called = feats[feats.status == 'called']
    corn_summary = json.loads((OUT / 'corn_check.json').read_text(encoding='utf-8'))
    metrics = json.loads((rb.OUT / 'metrics.json').read_text(encoding='utf-8'))
    by_year = []
    for year in YEARS:
        c = called[called.year == year]
        p, a = c.silage_probability.to_numpy(float), c.acres.to_numpy(float)
        by_year.append(dict(year=year, field_years_called=len(c),
            total_acres=round(float(a.sum()), 2),
            called_silage=int((c.predicted_label == 'Silage').sum()),
            called_grain=int((c.predicted_label == 'Grain').sum()),
            called_silage_acres=round(float(c[c.predicted_label == 'Silage'].acres.sum()), 2),
            called_grain_acres=round(float(c[c.predicted_label == 'Grain'].acres.sum()), 2),
            no_usable_dates=int(((feats.year == year) & (feats.status == 'no_usable_dates')).sum()),
            **bernoulli(p, a)))
    summary = dict(
        generated_utc=utc_now(),
        scope='BARC field-years with a blank silage/grain label that CDL marks as likely corn',
        caveat=CAVEAT,
        counts=dict(blank_field_years=corn_summary['blank_field_years'],
            **{f'blank_{k}': v for k, v in corn_summary['blank_by_category'].items()},
            called=len(called), no_usable_dates=int((feats.status == 'no_usable_dates').sum())),
        corn_rule=corn_summary['rule'],
        cdl_sanity_check_on_labeled=dict((k, corn_summary['labeled_sanity_check'][k])
            for k in ('field_years', 'likely_corn', 'sensitivity')),
        no_usable_dates=feats[feats.status == 'no_usable_dates'][['field_id', 'year']].to_dict('records'),
        by_year=by_year,
        model=dict(name='run_baseline.build_model() (median imputation, standard scaling, logistic regression C=1.0)',
            features=rb.FEATURES, threshold=0.5, trained_on='all labeled field-years with usable dates',
            training_field_years=len(usable), training_silage=int((usable.label == 'Silage').sum()),
            training_grain=int((usable.label == 'Grain').sum()),
            heldout_reproduced_max_abs_diff=max_diff,
            extraction_config=rb.CONFIG, cache_signature=rb.signature()),
        heldout_accuracy_for_context=dict(
            note='Field-held-out 5-fold results of the same model on labeled field-years (baseline/outputs/metrics.json)',
            **{k: metrics['logistic'][k] for k in ('n', 'balanced_accuracy', 'silage_precision',
                'silage_recall', 'silage_f1', 'false_positive_rate', 'brier_score')}),
        farm_record_spot_check=dict(
            note=('Kraatz (2023) farm planting/harvest records for blank field-years, including ones the CDL '
                  'gate did not call (predicted_label null). Evidence only, not an official label and never '
                  'used in training.'),
            rows=kraatz_check(feats, corn)),
        method='expected = sum(p_silage * acres); 95% interval and CV% from independent Bernoulli variance, as in /api/baseline/rollup',
        sources=[
            dict(name='USDA NASS Cropland Data Layer, Maryland, 2021-2023', url=CDL_URL.format(year='<YEAR>'),
                 accessed_utc=[s['accessed_utc'] for s in corn_summary['sources']]),
            dict(name='Sentinel-2 L2A, Microsoft Planetary Computer', url=rb.CATALOG,
                 accessed_utc=sorted({json.loads(p.read_text(encoding='utf-8'))['retrieved_utc'][:10]
                                      for p in (CACHE / 'catalog').glob('*.json')})),
            dict(name='BARC field boundaries and labels', file=rb.SOURCE.name),
            dict(name='Kraatz (2023) BARC farm records', doi='10.5281/zenodo.8087301', file='kraatz_labels.csv')])
    rb.write_json(OUT / 'summary.json', summary)
    print(json.dumps({k: summary[k] for k in ('counts', 'by_year', 'farm_record_spot_check')}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('stage', choices=['corn', 'pilot', 'extract', 'predict'])
    parser.add_argument('--field', type=int)
    parser.add_argument('--year', type=int)
    args = parser.parse_args()
    rb.verify_originals()
    if args.stage == 'corn':
        corn_stage()
    elif args.stage == 'pilot':
        if args.field is None or args.year is None:
            parser.error('pilot needs --field and --year')
        extract_stage([(args.field, args.year)])
    elif args.stage == 'extract':
        extract_stage(likely_corn_blanks())
    else:
        predict_stage()
    rb.verify_originals()


if __name__ == '__main__':
    main()
