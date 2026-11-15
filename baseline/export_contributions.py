"""Per-field signal breakdown for the saved held-out logistic predictions.

    python baseline/export_contributions.py

For each saved fold, refits the same pipeline as run_baseline.py (training-fold median imputation,
standard scaling, logistic regression C=1) on the other folds, then splits each held-out field's
log-odds into one contribution per feature: coefficient x standardized value. The intercept plus the
contributions equals the model's log-odds, and the export stops unless the resulting probability
matches the saved silage_probability for every field-year, so the breakdown is the model's actual
decision. Positive contributions push toward Silage, negative toward Grain.

Writes baseline/outputs/feature_contributions.csv:
    OBJECTID, year, as_of, feature, value, contribution, intercept, fold
(as_of empty = the saved season-end predictions; value is the raw feature, before imputation).
"""
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import build_model  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / 'outputs'
TOLERANCE = 1e-6


def compute() -> list[dict]:
    features = json.loads((OUT_DIR / 'metrics.json').read_text(encoding='utf-8'))['features']
    with (OUT_DIR / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    num = lambda v: float(v) if v not in ('', None) else np.nan
    X = np.array([[num(r[c]) for c in features] for r in rows])
    y = np.array([r['label'] == 'Silage' for r in rows], dtype=int)
    folds = np.array([int(r['fold']) for r in rows])
    out = []
    for k in sorted(set(folds)):
        model = build_model().fit(X[folds != k], y[folds != k])
        imputer, scaler, logit = model.steps[0][1], model.steps[1][1], model.steps[2][1]
        z = scaler.transform(imputer.transform(X[folds == k]))
        parts = z * logit.coef_[0]
        intercept = float(logit.intercept_[0])
        for i, row_index in enumerate(np.flatnonzero(folds == k)):
            r = rows[row_index]
            prob = 1 / (1 + math.exp(-(intercept + parts[i].sum())))
            saved = float(r['silage_probability'])
            if abs(prob - saved) > TOLERANCE:
                raise SystemExit(f"field {r['OBJECTID']}/{r['year']}: breakdown gives {prob:.6f}, saved {saved:.6f}")
            for j, name in enumerate(features):
                out.append({'OBJECTID': int(r['OBJECTID']), 'year': int(r['year']), 'as_of': '', 'feature': name,
                            'value': X[row_index, j], 'contribution': round(float(parts[i, j]), 6),
                            'intercept': round(intercept, 6), 'fold': int(k)})
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
            'field_years': len({(r['OBJECTID'], r['year']) for r in rows})}


if __name__ == '__main__':
    print(json.dumps(main(), indent=2))
