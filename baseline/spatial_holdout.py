"""Spatial hold-out: train on some BARC fields, test on a geographically separate block. Offline.

    python baseline/spatial_holdout.py

The main results hold out fields (all years of a field together) and the submission also holds out
whole years. The challenge asks for a spatially separated hold-out too, because nearby fields can
share management and imagery conditions.

Holding out one farm at a time is not possible: 11 of the 12 labeled silage field-years are on
Central Farm, so leaving it out leaves one silage example to train on. Instead, field centroids
(EPSG:32618) are grouped into k spatial blocks with k-means, and each block is held out in turn
(GroupKFold over blocks). All imputation, scaling and fitting use the baseline pipeline
(run_baseline.build_model) on the training blocks only. Every k in K is reported; none is chosen
after seeing scores. Reported gaps are the distance from each test block's fields to the nearest
training field.
"""
import json
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.model_selection import GroupKFold

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_baseline import FEATURES, build_model, metrics, write_json  # noqa: E402

OUT = HERE / 'outputs'
K = (4, 5, 6)
SEED = 0


def load():
    fields = gpd.read_file(OUT / 'fields.geojson').to_crs(32618).set_index('field_id')
    table = pd.read_csv(OUT / 'features.csv')
    table = table[table.valid_dates > 0].reset_index(drop=True)
    if not set(table.label) <= {'Grain', 'Silage'}:
        raise ValueError('Only Grain/Silage labels may be evaluated')
    return fields, table


def blocks_for(fields, table, k):
    centroids = fields.geometry.centroid
    model = KMeans(k, n_init=20, random_state=SEED).fit(np.c_[centroids.x, centroids.y])
    xy = np.c_[centroids.loc[table.OBJECTID].x, centroids.loc[table.OBJECTID].y]
    return model.predict(xy), xy


def run(fields, table, k):
    y = (table.label == 'Silage').astype(int).to_numpy()
    X = table[FEATURES]
    block, xy = blocks_for(fields, table, k)
    pred = np.full(len(y), -1)
    proba = np.full(len(y), np.nan)
    folds = []
    for train, test in GroupKFold(k).split(X, y, block):
        if len(set(y[train])) < 2:
            return {'k': k, 'status': 'a training fold has only one class'}
        if set(table.OBJECTID.iloc[train]) & set(table.OBJECTID.iloc[test]):
            raise AssertionError('Field leakage across spatial blocks')
        model = build_model().fit(X.iloc[train], y[train])
        pred[test] = model.predict(X.iloc[test])
        proba[test] = model.predict_proba(X.iloc[test])[:, 1]
        gap = min(float(np.hypot(*(xy[i] - xy[j]))) for i in test for j in train)
        folds.append({'block': int(block[test][0]), 'test_field_years': int(len(test)),
                      'test_silage': int(y[test].sum()), 'test_fields': sorted(set(map(int, table.OBJECTID.iloc[test]))),
                      'min_gap_to_training_m': round(gap)})
    result = metrics(y, pred, proba)
    return {'k': k, 'status': 'ok', 'folds': folds,
            'logistic': result,
            'always_grain': metrics(y, np.zeros(len(y), dtype=int), np.zeros(len(y)))}


def main():
    fields, table = load()
    farm = {int(i): f for i, f in fields['farm'].items()}
    by_farm = table.assign(farm=table.OBJECTID.map(farm)).groupby(['farm', 'label']).size().unstack(fill_value=0)
    report = {
        'protocol': 'GroupKFold over k-means spatial blocks of field centroids (EPSG:32618); baseline pipeline; '
                    f'k in {list(K)}, all reported; seed {SEED}',
        'why_not_leave_one_farm_out': 'Central Farm holds 11 of the 12 labeled silage field-years.',
        'labeled_field_years_by_farm': {f: {c: int(v) for c, v in row.items()} for f, row in by_farm.iterrows()},
        'field_held_out_reference': json.loads((OUT / 'metrics.json').read_text())['logistic'],
        'results': [run(fields, table, k) for k in K],
    }
    write_json(OUT / 'spatial_holdout.json', report)
    for r in report['results']:
        if r['status'] != 'ok':
            print(r['k'], r['status'])
            continue
        m = r['logistic']
        print(f"k={r['k']}: balanced accuracy {m['balanced_accuracy']:.3f}, silage recall {m['silage_recall']:.2f}, "
              f"precision {m['silage_precision']:.2f}, Brier {m['brier_score']:.3f}, "
              f"gaps {[f['min_gap_to_training_m'] for f in r['folds']]} m")
    return report


if __name__ == '__main__':
    main()
