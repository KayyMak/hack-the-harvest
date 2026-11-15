"""Model-v2 candidate (experiment candidate H): baseline 9 features + 4 NDVI timing features,
training-fold median imputation, standard scaling, L1 logistic regression (liblinear) with C
chosen by field-grouped inner CV (pooled log loss), threshold 0.5.

    python baseline/model_v2/candidate.py

writes, under baseline/model_v2/outputs/ only:
  heldout_predictions_candidate.csv  same columns as baseline/outputs/heldout_predictions.csv
                                     (seed-42 field folds), plus the four timing features
  candidate_metrics.json             seed-42 held-out metrics, and the C and coefficients of the
                                     model fitted on all 44 labeled field-years

This is a candidate only. It does not touch the shared baseline outputs; adopting it is the ML
owner's decision (see results.md, "Adoption").

API for adopters:
  FEATURES                       column order the model expects
  timing_from_observations(obs)  4 timing features from one field-year's per-scene records
                                 (dicts with 'date', 'ndvi', 'status', as in observations.csv)
  add_timing_features(df, obs)   adds the 4 columns to a frame with OBJECTID/field_id and year
  build_model()                  unfitted model; fit(X, y, groups) NEEDS field ids as groups
                                 (C is chosen by field-grouped inner CV); predict_proba(X) is
                                 sklearn-shaped (n, 2)
"""
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import run_baseline as rb  # noqa: E402
from features import (BASE_FEATURES, TIMING_FEATURES, BASELINE_OUT, base_features, build_table,  # noqa: E402
                      daily_series, timing_features)
from experiment import BY_NAME, REFERENCE_SEED, fit, heldout  # noqa: E402

SPEC = BY_NAME['H']
FEATURES = list(SPEC.features)
assert FEATURES == BASE_FEATURES + TIMING_FEATURES
OUT = HERE / 'outputs'


def timing_from_observations(observations):
    return timing_features(daily_series(observations))


def add_timing_features(frame, observations):
    """observations: {(field id, year): [per-scene records]}. Missing field-years get NaN
    timing features (imputed by the model), never zeros."""
    key = 'OBJECTID' if 'OBJECTID' in frame else 'field_id'
    rows = [timing_from_observations(observations.get((int(f), int(y)), []))
            for f, y in zip(frame[key], frame['year'])]
    return frame.assign(**{c: [r[c] for r in rows] for c in TIMING_FEATURES})


class CandidateModel:
    seed = REFERENCE_SEED

    def fit(self, X, y, groups=None):
        if groups is None:
            raise ValueError('CandidateModel.fit needs field ids as groups for its grouped inner CV')
        X = pd.DataFrame(X)[FEATURES].to_numpy(float)
        self.fitted_ = fit(SPEC, X, np.asarray(y).astype(int), np.asarray(groups), self.seed)
        self.C_ = self.fitted_.C
        return self

    def predict_proba(self, X):
        p = self.fitted_.predict_proba(pd.DataFrame(X)[FEATURES].to_numpy(float))
        return np.column_stack([1 - p, p])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= self.fitted_.threshold).astype(int)

    def coefficients(self):
        lr = self.fitted_.model[-1]
        return dict(intercept=float(lr.intercept_[0]),
                    standardized=dict(zip(FEATURES, map(float, lr.coef_[0]))))


def build_model():
    return CandidateModel()


YIELD_CONFIRMED_GRAIN_2021 = [22, 23, 234, 235, 602]


def yield_confirmed_check(table, y, final):
    """Post-selection evidence only (never used for selection or training): the five unlabeled
    2021 corn field-years that the 2021 combine yield coverage marks as grain. Features come from
    their committed per-scene caches. Reports A at 0.5, G (A's probability at the training
    prevalence), and H."""
    import json as _json
    current = rb.build_model().fit(table[rb.FEATURES], y)
    out = []
    for f in YIELD_CONFIRMED_GRAIN_2021:
        path = HERE.parent / 'cache_unlabeled' / f'{f}_2021.json'
        obs = _json.loads(path.read_text())['observations']
        row = pd.DataFrame([{**base_features(daily_series(obs)), **timing_from_observations(obs)}])
        pa, ph = current.predict_proba(row[rb.FEATURES])[0, 1], final.predict_proba(row[FEATURES])[0, 1]
        out.append(dict(OBJECTID=f, year=2021, evidence='2021 combine yield coverage: grain',
                        A_probability=float(pa), A_call='Silage' if pa >= 0.5 else 'Grain',
                        G_call='Silage' if pa >= y.mean() else 'Grain',
                        H_probability=float(ph), H_call='Silage' if ph >= 0.5 else 'Grain'))
    return dict(G_threshold=float(y.mean()), rows=out)


def main():
    rb.verify_originals()
    OUT.mkdir(parents=True, exist_ok=True)
    table, _ = build_table()
    saved = pd.read_csv(BASELINE_OUT / 'heldout_predictions.csv')
    assert (saved[['OBJECTID', 'year', 'label']].to_numpy() == table[['OBJECTID', 'year', 'label']].to_numpy()).all()
    proba, pred, folds, cs = heldout(SPEC, table, REFERENCE_SEED)
    assert (folds == saved.fold.to_numpy()).all()
    out = saved.copy()
    out['silage_probability'] = proba
    out['predicted_label'] = np.where(pred == 1, 'Silage', 'Grain')
    cols = list(saved.columns)
    at = cols.index('early_minus_late') + 1
    for c in TIMING_FEATURES:
        out[c] = table[c].to_numpy()
    out = out[cols[:at] + TIMING_FEATURES + cols[at:]]
    out.to_csv(OUT / 'heldout_predictions_candidate.csv', index=False)

    y = (table.label == 'Silage').astype(int).to_numpy()
    final = build_model().fit(table[FEATURES], y, table.OBJECTID.to_numpy())
    report = dict(candidate='H', description=SPEC.description, features=FEATURES, threshold=0.5,
                  seed=REFERENCE_SEED, C_by_fold=cs, heldout_seed42=rb.metrics(y, pred, proba),
                  baseline_seed42=json.loads((BASELINE_OUT / 'metrics.json').read_text())['logistic'],
                  full_fit=dict(C=final.C_, **final.coefficients()),
                  changed_calls_vs_baseline=[dict(OBJECTID=int(r.OBJECTID), year=int(r.year), label=r.label,
                      baseline=b, candidate=c) for r, b, c in zip(saved.itertuples(), saved.predicted_label,
                      out.predicted_label) if b != c],
                  post_selection_yield_confirmed_grain=yield_confirmed_check(table, y, final))
    (OUT / 'candidate_metrics.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['C_by_fold', 'full_fit', 'changed_calls_vs_baseline']}, indent=2))
    print({k: report['heldout_seed42'][k] for k in ['balanced_accuracy', 'silage_recall', 'silage_precision',
                                                     'brier_score', 'confusion_matrix']})
    rb.verify_originals()


if __name__ == '__main__':
    main()
