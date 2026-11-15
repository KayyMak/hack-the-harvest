"""Controlled input experiment: remove only the tile-wide cloud prefilter.

Reuse original observations plus additional >=40%-cloud scenes, keeping pixel
masking, features, model, and saved field folds fixed. Run pilot then run.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import geopandas as gpd
import numpy as np
import pandas as pd
import pystac
from pystac_client import Client
from pystac_client.stac_api_io import StacApiIO
from shapely.ops import unary_union

import run_baseline as baseline

OUT = HERE / 'outputs' / 'experiments' / 'no_scene_cloud_filter'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def setup():
    baseline.verify_originals()
    reference = pd.read_csv(HERE / 'outputs' / 'heldout_predictions.csv')
    fields = gpd.read_file(baseline.SOURCE, layer=baseline.LAYER)[['OBJECTID', 'geometry']]
    jobs = gpd.GeoDataFrame(reference[['OBJECTID', 'year', 'label']].merge(fields,
        on='OBJECTID', validate='many_to_one'), geometry='geometry', crs=fields.crs).to_crs(4326)
    jobs = jobs.sort_values(['year', 'OBJECTID']).reset_index(drop=True)
    metadata = json.loads((HERE / 'outputs' / 'metrics.json').read_text())
    assert len(jobs) == metadata['evaluated_field_years']
    assert jobs.label.isin(['Grain', 'Silage']).all()
    original = {(int(r.OBJECTID), int(r.year)): baseline.load_cache(r) for r in jobs.itertuples()}
    if any(c is None for c in original.values()):
        raise ValueError('Original extraction cache is incomplete')
    config = dict(version=1, baseline_config=baseline.CONFIG,
        changed_policy='No scene-wide cloud threshold; original pixel mask/acceptance unchanged',
        inputs={name: hashlib.sha256((HERE / 'outputs' / name).read_bytes()).hexdigest()
                for name in ['heldout_predictions.csv', 'metrics.json']},
        original_cache_hashes={f'{fid}_{year}': fingerprint(cache) for (fid, year), cache in original.items()})
    path = OUT / 'protocol.json'
    if path.exists() and json.loads(path.read_text()) != config:
        raise ValueError('Experiment inputs changed; move old experiment results aside')
    baseline.write_json(path, config)
    return jobs, reference, metadata, original, fingerprint(config)


def scene_records(item, jobs, signature):
    path = OUT / 'additional_scenes' / f'{item.id}.json'
    cached = json.loads(path.read_text()) if path.exists() else dict(signature=signature,
        requested_fields=[], records=[])
    if cached['signature'] != signature:
        raise ValueError(f'Stale scene cache: {item.id}')
    missing = jobs[~jobs.OBJECTID.isin(cached['requested_fields'])]
    if not missing.empty:
        cached['records'].extend(baseline.extract_scene(item, missing))
        cached['requested_fields'] = sorted(set(cached['requested_fields']) | set(map(int, missing.OBJECTID)))
        baseline.write_json(path, cached)
    selected = set(map(int, jobs.OBJECTID))
    return [r for r in cached['records'] if r['OBJECTID'] in selected]


def extract(jobs, signature):
    additional = {(int(r.OBJECTID), int(r.year)): [] for r in jobs.itertuples()}
    client = None
    for year, selected in jobs.groupby('year'):
        geom = unary_union(selected.geometry.tolist()).__geo_interface__
        query = dict(collections=[baseline.CONFIG['collection']], intersects=geom,
            datetime=f'{year}-07-01/{year}-11-30',
            query={'eo:cloud_cover': {'gte': baseline.CONFIG['scene_cloud_lt']}})
        path = OUT / 'catalog' / f'{year}_{fingerprint(query)[:12]}.json'
        if path.exists():
            items = [pystac.Item.from_dict(i) for i in json.loads(path.read_text())['items']]
        else:
            if client is None:
                client = Client.open(baseline.CATALOG, stac_io=StacApiIO(timeout=30))
            items = list(client.search(**query).items())
            baseline.write_json(path, dict(query=query, items=[i.to_dict() for i in items]))
        print(f'{year}: {len(items)} additional scenes for {len(selected)} field-years.', flush=True)
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(scene_records, item, selected, signature) for item in items]
            for count, future in enumerate(as_completed(futures), 1):
                for record in future.result():
                    additional[(record['OBJECTID'], record['year'])].append(record)
                if count == 1 or count % 5 == 0 or count == len(items):
                    print(f'  {year}: {count}/{len(items)} processed.', flush=True)
    return additional


def combined(original, additional):
    records = list(original['observations']) + additional
    if len({r['item_id'] for r in records}) != len(records):
        raise ValueError('Repeated item ID while merging original/additional observations')
    return {'observations': sorted(records, key=lambda r: (r['date'], r['item_id']))}


def fit_on_saved_folds(table, metadata):
    result = table.copy()
    result['silage_probability'] = np.nan
    result['predicted_label'] = ''
    result['fold'] = 0
    for split in metadata['folds']:
        train = result.OBJECTID.isin(split['training_fields'])
        test = result.OBJECTID.isin(split['test_fields'])
        if (train & test).any() or not (train | test).all():
            raise ValueError('Saved folds do not partition experiment fields')
        model = baseline.build_model()
        model.fit(result.loc[train, baseline.FEATURES], result.loc[train, 'label'].eq('Silage').astype(int))
        result.loc[test, 'silage_probability'] = model.predict_proba(result.loc[test, baseline.FEATURES])[:, 1]
        result.loc[test, 'predicted_label'] = np.where(model.predict(result.loc[test, baseline.FEATURES]), 'Silage', 'Grain')
        result.loc[test, 'fold'] = split['fold']
    assert result.silage_probability.notna().all()
    assert result.groupby('OBJECTID').fold.nunique().max() == 1
    return result


def score(table):
    return baseline.metrics(table.label.eq('Silage').astype(int).to_numpy(),
        table.predicted_label.eq('Silage').astype(int).to_numpy(), table.silage_probability.to_numpy())


def acreage(table):
    fields = gpd.read_file(baseline.SOURCE, layer=baseline.LAYER)[['OBJECTID', 'ACRES']]
    joined = table.merge(fields, on='OBJECTID', validate='many_to_one')
    if joined.ACRES.isna().any():
        raise ValueError('Missing field acreage')
    rows = []
    for year, subset in joined.groupby('year'):
        truth = float(subset.loc[subset.label.eq('Silage'), 'ACRES'].sum())
        hard = float(subset.loc[subset.predicted_label.eq('Silage'), 'ACRES'].sum())
        expected = float((subset.ACRES * subset.silage_probability).sum())
        rows.append(dict(year=int(year), reference_silage_acres=truth, predicted_silage_acres=hard,
            expected_silage_acres=expected, hard_signed_error_acres=hard-truth,
            expected_signed_error_acres=expected-truth))
    return rows


def evaluate(jobs, original, additional, reference, metadata):
    old_rows, new_rows, observations = [], [], []
    for row in jobs.itertuples():
        key = (int(row.OBJECTID), int(row.year))
        result = combined(original[key], additional[key])
        old_rows.append(baseline.summarize(row, original[key]))
        new_rows.append(baseline.summarize(row, result))
        observations.extend(result['observations'])
    old, new = pd.DataFrame(old_rows), pd.DataFrame(new_rows)
    if new.valid_dates.eq(0).any() or new.read_errors.sum():
        raise ValueError('Incomplete experiment observations; no model comparison is reported')
    rebuilt = fit_on_saved_folds(old, metadata)
    expected = reference.set_index(['OBJECTID', 'year']).loc[
        list(zip(rebuilt.OBJECTID, rebuilt.year)), 'silage_probability'].to_numpy()
    np.testing.assert_allclose(rebuilt.silage_probability, expected, atol=1e-10, rtol=0)
    predictions = fit_on_saved_folds(new, metadata)
    predictions.to_csv(OUT / 'heldout_predictions.csv', index=False)
    new.to_csv(OUT / 'features.csv', index=False)
    pd.DataFrame(observations).drop(columns='calibration', errors='ignore').to_csv(OUT / 'observations.csv', index=False)
    coverage = old[['OBJECTID', 'year', 'valid_dates']].merge(new[['OBJECTID', 'year', 'valid_dates']],
        on=['OBJECTID', 'year'], suffixes=('_original', '_experiment'), validate='one_to_one')
    coverage['added_dates'] = coverage.valid_dates_experiment - coverage.valid_dates_original
    assert coverage.added_dates.ge(0).all()
    coverage.to_csv(OUT / 'coverage.csv', index=False)
    compare = predictions.merge(reference[['OBJECTID', 'year', 'predicted_label', 'silage_probability']],
        on=['OBJECTID', 'year'], suffixes=('_experiment', '_original'), validate='one_to_one')
    changes = compare[compare.predicted_label_experiment.ne(compare.predicted_label_original)]
    changes.to_csv(OUT / 'changed_predictions.csv', index=False)
    report = dict(policy='Remove only whole-scene cloud prefilter; unchanged per-pixel mask, feature definitions, model, and saved folds',
        evaluated_field_years=len(new), original=score(rebuilt), experiment=score(predictions),
        always_grain=metadata['always_grain'], added_usable_field_dates=int(coverage.added_dates.sum()),
        additional_scene_records=sum(map(len, additional.values())), read_errors=int(new.read_errors.sum()),
        original_acreage=acreage(rebuilt), experiment_acreage=acreage(predictions),
        changed_predictions=changes[['OBJECTID', 'year', 'label', 'predicted_label_original',
            'predicted_label_experiment', 'silage_probability_original', 'silage_probability_experiment']].to_dict('records'),
        by_year={str(year): dict(original=score(rebuilt[rebuilt.year.eq(year)]),
            experiment=score(predictions[predictions.year.eq(year)])) for year in sorted(new.year.unique())},
        limitations=['Exploratory comparison on already-inspected BARC data; not an independent test.',
                     'Acreage applies only to these labeled BARC fields, not statewide 2025 targets.'])
    baseline.write_json(OUT / 'metrics.json', report)
    print(json.dumps(report, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['pilot', 'run'])
    args = parser.parse_args()
    jobs, reference, metadata, original, signature = setup()
    gate = OUT / 'pilot.json'
    if args.stage == 'pilot':
        selected = jobs[jobs.OBJECTID.eq(323) & jobs.year.eq(2023)]
        additional = extract(selected, signature)
        row = next(selected.itertuples())
        result = combined(original[(323, 2023)], additional[(323, 2023)])
        summary = baseline.summarize(row, result)
        before = baseline.summarize(row, original[(323, 2023)])
        passed = summary['valid_dates'] > before['valid_dates'] and summary['read_errors'] == 0
        baseline.write_json(gate, dict(passed=passed, signature=signature, field_id=323, year=2023,
            original_dates=before['valid_dates'], experiment_dates=summary['valid_dates'],
            note='Gate checks extraction and coverage, never classification correctness'))
        print(f'Pilot passed: {passed}; usable dates {before["valid_dates"]} -> {summary["valid_dates"]}', flush=True)
        if not passed:
            raise RuntimeError('Pilot extraction/coverage gate failed')
    else:
        pilot = json.loads(gate.read_text())
        if not pilot['passed'] or pilot['signature'] != signature:
            raise ValueError('Successful current pilot required')
        evaluate(jobs, original, extract(jobs, signature), reference, metadata)
    baseline.verify_originals()


if __name__ == '__main__':
    main()
