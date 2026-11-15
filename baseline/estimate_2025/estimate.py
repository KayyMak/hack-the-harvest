"""Steps 4-7: fit on BARC, predict the 2025 sample, scale up, score, summarize. Offline.

    python baseline/estimate_2025/estimate.py

Model: the baseline pipeline (run_baseline.build_model) fitted once on every labeled
BARC field-year with usable dates. Nothing here reads the 2025 NASS values until the
estimate is final; they are only used to report the error afterwards.

Raw estimate
    silage share = sum(P(silage) * acres) / sum(acres) over scored sample fields
    silage acres = share * Maryland 2025 corn acres;  grain = corn acres - silage

Calibrated estimate (the misclassification adjustment in backend compute_rollup)
    q = acre share of scored sample fields called Silage at the 0.5 threshold
    share = (q - FPR) / (TPR - FPR), clipped to [0, 1]
    TPR and FPR are acre-weighted and come from the saved held-out BARC predictions.

Intervals are percentile bootstraps (2,000 draws, seeded). Raw: sample fields are
redrawn within county. Calibrated: sample fields are redrawn within county and BARC
fields are redrawn (all years of a field together) to redraw TPR and FPR.
"""
import csv
from datetime import datetime, timezone
import json
import subprocess
import sys

import numpy as np
import pandas as pd

from common import BASELINE, CDL_URL, CSB_URL, MIN_VALID_DATES, OUT, ROOT, SEED, STATE, YEAR, write_json
import run_baseline as rb

DRAWS = 2000
THRESHOLD = 0.5
ACCESSED = '2026-11-14'
ITEMS = {'silage': 'CORN, SILAGE - ACRES HARVESTED', 'grain': 'CORN, GRAIN - ACRES HARVESTED'}


def barc_training():
    table = pd.read_csv(BASELINE / 'outputs' / 'features.csv')
    usable = table[table.valid_dates > 0].reset_index(drop=True)
    if not set(usable.label) <= {'Grain', 'Silage'}:
        raise ValueError('Only Grain/Silage reference labels may enter training')
    return usable


def barc_heldout():
    """Saved held-out BARC calls with field acres, for the error rates."""
    preds = pd.read_csv(BASELINE / 'outputs' / 'heldout_predictions.csv')
    geo = json.loads((BASELINE / 'outputs' / 'fields.geojson').read_text(encoding='utf-8'))
    acres = {f['properties']['field_id']: f['properties']['acres'] for f in geo['features']}
    preds['acres'] = preds.OBJECTID.map(acres)
    return preds[preds.acres.notna()].reset_index(drop=True)


def rates(heldout):
    """Acre-weighted TPR and FPR; the same arithmetic as backend/app/artifacts._rates."""
    silage, grain = heldout[heldout.label == 'Silage'], heldout[heldout.label == 'Grain']
    if not silage.acres.sum() or not grain.acres.sum():
        return None, None
    tpr = silage.acres[silage.predicted_label == 'Silage'].sum() / silage.acres.sum()
    fpr = grain.acres[grain.predicted_label == 'Silage'].sum() / grain.acres.sum()
    return float(tpr), float(fpr)


def adjusted_share(q, tpr, fpr):
    if tpr is None or fpr is None or tpr - fpr <= 0:
        return None
    return min(1.0, max(0.0, (q - fpr) / (tpr - fpr)))


def county_draw(rng, strata):
    return np.concatenate([rng.choice(index, size=len(index), replace=True) for index in strata])


def interval(values):
    lo, hi = np.percentile(values, [2.5, 97.5])
    return [float(lo), float(hi)]


def nass_reference():
    """Maryland 2025 rows of the judges' file. Read only to report errors."""
    out = {}
    with open(ROOT / 'data' / 'reference' / 'quickstats_2025_judges.csv', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            if row['Year'] == str(YEAR) and row['Geo Level'] == 'STATE' and row['State'] == STATE:
                for use, item in ITEMS.items():
                    if row['Data Item'] == item and row['Domain'] == 'TOTAL':
                        out[use] = int(row['Value'].replace(',', ''))
    if set(out) != set(ITEMS):
        raise ValueError('Maryland 2025 reference rows not found')
    return out


def write_predictions(path, silage, grain):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Year', 'Geo Level', 'State', 'Data Item', 'Domain', 'Value'])
        writer.writerow([YEAR, 'STATE', STATE, ITEMS['grain'], 'TOTAL', f'{round(grain):,}'])
        writer.writerow([YEAR, 'STATE', STATE, ITEMS['silage'], 'TOTAL', f'{round(silage):,}'])


def benchmark(predictions, out):
    subprocess.run([sys.executable, '-m', 'harvest.benchmark', '--predictions', str(predictions),
        '--out', str(out)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    report = json.loads(out.read_text(encoding='utf-8'))
    rows = {c['crop_use'].lower(): c for c in report['comparisons']
            if c['geo_kind'] == 'STATE' and c['geography'] == STATE and c['status'] == 'scored'}
    return {use: dict(error=rows[use]['signed_error'], relative_error=rows[use]['relative_error'])
            for use in ITEMS}


def block(silage, corn_acres, share, draws_share):
    lo, hi = interval(draws_share)
    return dict(silage_acres=round(silage, 1),
        silage_acres_95ci=[round(lo * corn_acres, 1), round(hi * corn_acres, 1)],
        grain_acres=round(corn_acres - silage, 1),
        grain_acres_95ci=[round(corn_acres - hi * corn_acres, 1), round(corn_acres - lo * corn_acres, 1)],
        silage_share=round(share, 4))


def main():
    population = json.loads((OUT / 'population.json').read_text(encoding='utf-8'))
    extraction = json.loads((OUT / 'extraction.json').read_text(encoding='utf-8'))
    corn_acres = population['corn_acres_2025']

    train = barc_training()
    model = rb.build_model()
    model.fit(train[rb.FEATURES], (train.label == 'Silage').astype(int).to_numpy())

    features = pd.read_csv(OUT / 'features.csv', dtype={'id': str})
    scored = features[features.status == 'ok'].reset_index(drop=True)
    skipped = features[features.status != 'ok']
    p = model.predict_proba(scored[rb.FEATURES])[:, 1]
    acres = scored.acres.to_numpy()
    called = p >= THRESHOLD
    scored.assign(silage_probability=p, predicted_label=np.where(called, 'Silage', 'Grain'))[
        ['id', 'county', 'acres', 'valid_dates', *rb.FEATURES, 'silage_probability', 'predicted_label']
    ].to_csv(OUT / 'predictions.csv', index=False)

    raw_share = float((p * acres).sum() / acres.sum())
    q = float(acres[called].sum() / acres.sum())
    heldout = barc_heldout()
    tpr, fpr = rates(heldout)
    cal_share = adjusted_share(q, tpr, fpr)

    rng = np.random.default_rng(SEED)
    strata = [np.flatnonzero(scored.county.to_numpy() == c) for c in sorted(scored.county.unique())]
    barc_fields = heldout.OBJECTID.unique()
    by_field = {f: heldout[heldout.OBJECTID == f] for f in barc_fields}
    raw_draws, cal_draws, undefined = [], [], 0
    for _ in range(DRAWS):
        take = county_draw(rng, strata)
        a, pp = acres[take], p[take]
        raw_draws.append((pp * a).sum() / a.sum())
        redraw = pd.concat([by_field[f] for f in rng.choice(barc_fields, size=len(barc_fields), replace=True)])
        share = adjusted_share(a[pp >= THRESHOLD].sum() / a.sum(), *rates(redraw))
        if share is None:
            undefined += 1
        else:
            cal_draws.append(share)

    raw = block(raw_share * corn_acres, corn_acres, raw_share, raw_draws)
    calibrated = None
    if cal_share is not None and cal_draws:
        calibrated = block(cal_share * corn_acres, corn_acres, cal_share, cal_draws)
        calibrated.update(tpr=round(tpr, 4), fpr=round(fpr, 4),
            predicted_silage_acre_share=round(q, 4), undefined_bootstrap_draws=undefined,
            method=('share = (q - FPR) / (TPR - FPR), clipped to [0, 1]; q is the acre share of scored '
                    'sample fields called Silage at 0.5; TPR and FPR are acre-weighted rates from the '
                    f'{len(heldout)} saved held-out BARC field-years'))
    headline = 'calibrated' if calibrated else 'raw'

    # The estimate is final above this line. The reference is read only to report errors.
    nass = nass_reference()
    write_predictions(OUT / 'state_estimates.csv', (calibrated or raw)['silage_acres'], (calibrated or raw)['grain_acres'])
    errors = {headline: benchmark(OUT / 'state_estimates.csv', OUT / 'benchmark.json')}
    if calibrated:
        write_predictions(OUT / 'state_estimates_raw.csv', raw['silage_acres'], raw['grain_acres'])
        errors['raw'] = benchmark(OUT / 'state_estimates_raw.csv', OUT / 'benchmark_raw.json')
    else:
        errors['calibrated'] = None

    reasons = {k: int(v) for k, v in skipped.status.value_counts().items()}
    summary = dict(
        year=YEAR, state=STATE, generated_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        headline=headline,
        population=dict(
            source='USDA Crop Sequence Boundaries (2016-2023 polygons), Maryland, checked against the 2025 Cropland Data Layer',
            corn_rule=population['corn_rule'], csb_fields_maryland=population['csb_fields_maryland'],
            corn_fields_2025=population['corn_fields_2025'], corn_acres_2025=corn_acres,
            cdl_corn_acres_2025=population['cdl_corn_acres_2025']),
        sample=dict(seed=SEED, stratified_by='county', requested_fields=population['sample']['requested_fields'],
            sampled_fields=int(len(features)), sampled_acres=round(float(features.acres.sum()), 1),
            scored_fields=int(len(scored)), scored_acres=round(float(acres.sum()), 1),
            skipped_fields=int(len(skipped)), skipped_reasons=reasons, min_valid_dates=MIN_VALID_DATES,
            batches_used=extraction['batches'], batches_drawn=population['sample']['batches']),
        model=dict(name='Logistic regression on NDVI (the BARC baseline pipeline)',
            training_field_years=int(len(train)), training_silage_field_years=int((train.label == 'Silage').sum()),
            features=rb.FEATURES, threshold=THRESHOLD,
            sample_fields_called_silage=int(called.sum())),
        raw=raw, calibrated=calibrated,
        nass_2025=dict(silage_acres=nass['silage'], grain_acres=nass['grain'],
            source='USDA NASS Quick Stats, 2025 survey, acres harvested (data/reference/quickstats_2025_judges.csv)'),
        benchmark=errors,
        method=(
            f"Maryland {YEAR} corn fields are Crop Sequence Boundaries polygons with at least half of their "
            f"{YEAR} Cropland Data Layer pixels in corn: {population['corn_fields_2025']:,} fields, {corn_acres:,.0f} acres. "
            f"A seeded random sample of {len(features):,} fields, allocated by county, was read from Sentinel-2 L2A "
            f"(July-November {YEAR}) with the baseline's cloud mask, reflectance offset and nine NDVI features. "
            f"The baseline logistic regression, fitted on all {len(train)} labeled BARC field-years, gives each field a "
            "silage probability. Raw: probability-weighted silage acres in the sample, scaled to all Maryland corn acres. "
            "Calibrated: the acre share called silage, corrected with the miss and false-alarm rates measured on "
            "held-out BARC fields. Grain is corn acres minus silage. The 2025 NASS values were not used to fit, "
            "choose or adjust anything."),
        limitations=[
            'The model was trained on 44 field-years from one research farm (BARC, 2021-2023); how well it transfers to other Maryland farms and to 2025 is untested.',
            'The calibration rates come from 12 silage and 32 grain BARC field-years, so the calibrated range is wide.',
            'The raw range reflects only which fields were sampled, not model error, so it is too narrow.',
            'Field polygons date from 2023; corn in 2025 is taken from the Cropland Data Layer, which has its own classification error.',
            'Corn acres here are mapped field acres, not NASS acres harvested; abandoned or failed corn is not removed.',
            f'Fields with fewer than {MIN_VALID_DATES} clear Sentinel-2 dates are skipped and listed, not filled in.',
        ],
        sources=[
            dict(name='USDA NASS Crop Sequence Boundaries (fiboa copy on Source Cooperative)', url=CSB_URL, accessed=ACCESSED),
            dict(name=f'USDA NASS Cropland Data Layer {YEAR}, Maryland (CropScape)', url=CDL_URL, accessed=ACCESSED),
            dict(name='Sentinel-2 L2A, Microsoft Planetary Computer STAC', url=rb.CATALOG, accessed=ACCESSED),
            dict(name='BARC silage and grain corn labels 2021-2023 (repository GeoPackage)', url='BARC_Corn.2021-2023.gpkg', accessed=ACCESSED),
            dict(name='USDA NASS Quick Stats 2025, corn acres harvested (judges\' reference)', url='https://quickstats.nass.usda.gov/', accessed=ACCESSED),
        ])
    write_json(OUT / 'summary.json', summary)
    print(json.dumps({k: summary[k] for k in ('headline', 'sample', 'raw', 'calibrated', 'nass_2025', 'benchmark')}, indent=2))


if __name__ == '__main__':
    main()
