"""Per-field signal breakdown for the saved logistic predictions: season end and every saved as-of date.

    python baseline/export_contributions.py

For each saved fold, refits the saved model on the other folds, then splits each held-out field's
log-odds into one contribution per feature: coefficient x standardized value. The intercept plus the
contributions equals the model's log-odds. The export stops unless the resulting probability matches
the saved one for every field-year: heldout_predictions.csv for the season-end model (as_of empty),
and asof.json for each mid-season date (as_of = that date, using only the features available then,
exactly as harvest/asof.py refits them). Positive contributions push toward Silage.

Season end uses the model version in baseline/model_version.py, which must match the saved
metrics.json: v1 = run_baseline.build_model() (median imputation, scaling, logistic regression C=1);
v2 = candidate H (13 features, L1 with C by field-grouped inner CV; fitted with field ids as groups,
on the training rows in saved order, exactly as run_baseline.evaluate fits it; L1 zeros appear as
zero contributions). Mid-season dates always use the v1 month-cut refit, as harvest/asof.py does.

Writes baseline/outputs/feature_contributions.csv:
    OBJECTID, year, as_of, feature, value, contribution, intercept, fold
"""
import csv
import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import build_model  # noqa: E402
import model_version  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / 'outputs'
TOLERANCE = 1e-5  # asof.json stores probabilities to 6 decimals
MONTH_END = {'ndvi_07': (7, 31), 'ndvi_08': (8, 31), 'ndvi_09': (9, 30), 'ndvi_10': (10, 31), 'ndvi_11': (11, 30)}


def _load():
    features = json.loads((OUT_DIR / 'metrics.json').read_text(encoding='utf-8'))['features']
    with (OUT_DIR / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    return features, rows


def _fold_pipeline(version, X, y, groups, features):
    """The fitted (imputer, scaler, logistic regression) pipeline for one training fold."""
    if version == 'v1':
        return build_model().fit(X, y)
    import pandas as pd
    model = model_version.build_model(version).fit(pd.DataFrame(X, columns=features), y, groups)
    return model_version.fitted_pipeline(model)


def _breakdown(rows, features, saved: dict, as_of: str, version: str = 'v1') -> list[dict]:
    """Contributions for every row from fold models on `features`; saved = {(oid, year): probability}."""
    num = lambda v: float(v) if v not in ('', None) else np.nan
    X = np.array([[num(r[c]) for c in features] for r in rows])
    y = np.array([r['label'] == 'Silage' for r in rows], dtype=int)
    folds = np.array([int(r['fold']) for r in rows])
    groups = np.array([int(r['OBJECTID']) for r in rows])
    out = []
    for k in sorted(set(folds)):
        train = folds != k
        model = _fold_pipeline(version, X[train], y[train], groups[train], features)
        imputer, scaler, logit = model.steps[0][1], model.steps[1][1], model.steps[2][1]
        parts = scaler.transform(imputer.transform(X[folds == k])) * logit.coef_[0]
        intercept = float(logit.intercept_[0])
        for i, row_index in enumerate(np.flatnonzero(folds == k)):
            r = rows[row_index]
            key = (int(r['OBJECTID']), int(r['year']))
            if key not in saved:
                continue
            prob = 1 / (1 + math.exp(-(intercept + parts[i].sum())))
            if abs(prob - saved[key]) > TOLERANCE:
                raise SystemExit(f'{key} as of {as_of or "season end"}: breakdown gives {prob:.6f}, saved {saved[key]:.6f}')
            for j, name in enumerate(features):
                out.append({'OBJECTID': key[0], 'year': key[1], 'as_of': as_of, 'feature': name,
                            'value': X[row_index, j], 'contribution': round(float(parts[i, j]), 6),
                            'intercept': round(intercept, 6), 'fold': int(k)})
    return out


def compute() -> list[dict]:
    features, rows = _load()
    version = model_version.current()
    model_version.check_saved_matches(version, OUT_DIR / 'metrics.json')
    season_end = {(int(r['OBJECTID']), int(r['year'])): float(r['silage_probability']) for r in rows}
    out = _breakdown(rows, features, season_end, '', version)
    asof = json.loads((OUT_DIR / 'asof.json').read_text(encoding='utf-8'))
    for d in asof['dates']:
        day = date.fromisoformat(d['as_of'])
        if day >= date(d['year'], 11, 30) or not d['predictions']:
            continue  # season end uses the saved full model above; nothing decided yet before Jul 31
        usable = [f for f, (m, dd) in MONTH_END.items() if day >= date(d['year'], m, dd)]
        saved = {(p['field_id'], d['year']): p['silage_probability'] for p in d['predictions']}
        out += _breakdown(rows, usable, saved, d['as_of'])
    return out


def main() -> dict:
    rows = compute()
    path = OUT_DIR / 'feature_contributions.csv'
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        for r in rows:
            w.writerow({**r, 'value': '' if math.isnan(r['value']) else round(float(r['value']), 6)})
    return {'out': str(path.relative_to(OUT_DIR.parents[1])), 'rows': len(rows),
            'field_years': len({(r['OBJECTID'], r['year']) for r in rows}),
            'as_of_dates': sorted({r['as_of'] for r in rows if r['as_of']})}


if __name__ == '__main__':
    print(json.dumps(main(), indent=2))
