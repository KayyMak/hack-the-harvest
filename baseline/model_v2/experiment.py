"""Model-v2 experiment: pre-registered candidates vs the current logistic baseline.

    python baseline/model_v2/experiment.py

Reads only committed baseline outputs (features.csv, observations.csv, heldout_predictions.csv)
and writes only to baseline/model_v2/outputs/. The candidate list, seeds, inner-CV grid, the
selection rule, and the "better" bar are pre-registered in results.md (committed before any
candidate was scored). Every fit, imputation, scaling, C choice, and threshold uses training
rows only; all years of a field stay in one fold.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
# run_baseline: only FEATURES, metrics, build_model, verify_originals
from features import BASE_FEATURES, TIMING_FEATURES, BASELINE_OUT, V1_REFERENCE, build_table  # noqa: E402

class _LazyRunBaseline:
    """run_baseline imports the extraction stack (geopandas, rasterio, ...); load it only when used,
    so fitting the model needs just numpy, pandas and scikit-learn."""

    def __getattr__(self, name):
        import run_baseline
        return getattr(run_baseline, name)


rb = _LazyRunBaseline()


OUT = HERE / 'outputs'
REFERENCE_SEED = 42
SELECTION_SEEDS = list(range(20))
C_GRID = [0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0]
BRIER_GUARD = 0.01
SUSPECT = (327, 2021)
JULOCT = [f'{f}_juloct' for f in BASE_FEATURES if f != 'ndvi_11']


@dataclass(frozen=True)
class Spec:
    name: str
    features: tuple
    class_weight: object = None
    tune_c: bool = False
    l1: bool = False
    prevalence_threshold: bool = False
    description: str = ''


CANDIDATES = [
    Spec('A', tuple(BASE_FEATURES), description='current: baseline 9, C=1, threshold 0.5'),
    Spec('B', tuple(BASE_FEATURES), class_weight='balanced', description="baseline 9, class_weight='balanced'"),
    Spec('C', tuple(BASE_FEATURES + TIMING_FEATURES), description='baseline 9 + 4 timing'),
    Spec('D', tuple(BASE_FEATURES + TIMING_FEATURES), class_weight='balanced',
         description="baseline 9 + 4 timing, class_weight='balanced'"),
    Spec('E', tuple(JULOCT), description='baseline features from Jul-Oct observations only (8)'),
    Spec('F', tuple(BASE_FEATURES), tune_c=True, description='baseline 9, L2 C by inner CV'),
    Spec('G', tuple(BASE_FEATURES), prevalence_threshold=True,
         description='baseline 9, threshold = training silage prevalence'),
    Spec('H', tuple(BASE_FEATURES + TIMING_FEATURES), tune_c=True, l1=True,
         description='baseline 9 + 4 timing, L1, C by inner CV'),
]
BY_NAME = {s.name: s for s in CANDIDATES}


def pipeline(spec, C=1.0):
    if spec.l1:
        lr = LogisticRegression(C=C, l1_ratio=1.0, solver='liblinear', max_iter=2000,
                                random_state=42, class_weight=spec.class_weight)
    else:
        lr = LogisticRegression(C=C, max_iter=2000, random_state=42, class_weight=spec.class_weight)
    return make_pipeline(SimpleImputer(strategy='median', keep_empty_features=True), StandardScaler(), lr)


def splits(y, groups, seed, n_splits):
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    out = list(cv.split(np.zeros(len(y)), y, groups))
    for train, test in out:
        assert not set(groups[train]) & set(groups[test]), 'Field leakage'
    return out


def choose_c(spec, X, y, groups, seed):
    """Pooled inner grouped-CV log loss over C_GRID on training rows only; ties to smaller C."""
    inner = splits(y, groups, seed, 4)
    if any(len(set(y[tr])) < 2 for tr, _ in inner):
        return 1.0
    losses = []
    for C in C_GRID:
        p = np.zeros(len(y))
        for tr, te in inner:
            p[te] = pipeline(spec, C).fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
        losses.append(log_loss(y, p, labels=[0, 1]))
    return C_GRID[int(np.argmin(losses))]  # argmin returns the first (smallest C) on ties


@dataclass
class Fitted:
    model: object
    threshold: float
    C: float

    def predict_proba(self, X):
        return self.model.predict_proba(X)[:, 1]

    def predict(self, X):
        return (self.predict_proba(X) >= self.threshold).astype(int)


def fit(spec, X, y, groups, seed):
    """Fit one candidate on training rows only. X is a 2-D array in spec.features order."""
    if len(set(y)) < 2:
        raise RuntimeError('Training rows have only one class')
    C = choose_c(spec, X, y, groups, seed) if spec.tune_c else 1.0
    threshold = float(y.mean()) if spec.prevalence_threshold else 0.5
    return Fitted(pipeline(spec, C).fit(X, y), threshold, C)


def heldout(spec, table, seed):
    """Pooled held-out probabilities, predictions, fold ids, and chosen C per fold."""
    X = table[list(spec.features)].to_numpy(float)
    y = (table.label == 'Silage').astype(int).to_numpy()
    groups = table.OBJECTID.to_numpy()
    proba, pred, folds, cs = np.full(len(y), np.nan), np.full(len(y), -1), np.full(len(y), -1), []
    for k, (train, test) in enumerate(splits(y, groups, seed, 5), 1):
        m = fit(spec, X[train], y[train], groups[train], seed)
        proba[test], pred[test], folds[test] = m.predict_proba(X[test]), m.predict(X[test]), k
        cs.append(m.C)
    assert np.isfinite(proba).all() and (pred >= 0).all()
    return proba, pred, folds, cs


def score(y, pred, proba):
    m = rb.metrics(y, pred, proba)
    return {k: m[k] for k in ['balanced_accuracy', 'silage_recall', 'silage_precision',
                              'silage_f1', 'brier_score', 'confusion_matrix']}


def run_seed(table, seed):
    y = (table.label == 'Silage').astype(int).to_numpy()
    out = {}
    for spec in CANDIDATES:
        proba, pred, folds, cs = heldout(spec, table, seed)
        out[spec.name] = dict(score=score(y, pred, proba), proba=proba, pred=pred, folds=folds, C=cs)
    return seed, out


def nested_selection(table, seed):
    """Selection rule applied inside each outer training fold; the pick scored on the outer test fold."""
    y = (table.label == 'Silage').astype(int).to_numpy()
    groups = table.OBJECTID.to_numpy()
    proba, pred, picks = np.full(len(y), np.nan), np.full(len(y), -1), []
    for train, test in splits(y, groups, seed, 5):
        inner = splits(y[train], groups[train], seed, 4)
        inner_scores = {}
        for spec in CANDIDATES:
            X = table[list(spec.features)].to_numpy(float)[train]
            yt, gt = y[train], groups[train]
            p, q = np.zeros(len(yt)), np.zeros(len(yt), dtype=int)
            for tr, te in inner:
                m = fit(spec, X[tr], yt[tr], gt[tr], seed)
                p[te], q[te] = m.predict_proba(X[te]), m.predict(X[te])
            inner_scores[spec.name] = score(yt, q, p)
        guard = inner_scores['A']['brier_score'] + BRIER_GUARD
        eligible = [s.name for s in CANDIDATES if inner_scores[s.name]['brier_score'] <= guard]
        best = max(inner_scores[n]['balanced_accuracy'] for n in eligible)
        pick = next(n for n in eligible if inner_scores[n]['balanced_accuracy'] == best)  # A first, then list order
        spec = BY_NAME[pick]
        X = table[list(spec.features)].to_numpy(float)
        m = fit(spec, X[train], y[train], groups[train], seed)
        proba[test], pred[test] = m.predict_proba(X[test]), m.predict(X[test])
        picks.append(pick)
    return seed, score(y, pred, proba), picks


def summarize(per_seed, seeds):
    names = [s.name for s in CANDIDATES]
    keys = ['balanced_accuracy', 'silage_recall', 'silage_precision', 'silage_f1', 'brier_score']
    summary = {}
    for n in names:
        vals = {k: np.array([per_seed[s][n]['score'][k] for s in seeds]) for k in keys}
        dif = {k: vals[k] - np.array([per_seed[s]['A']['score'][k] for s in seeds]) for k in keys}
        summary[n] = dict(
            mean={k: float(v.mean()) for k, v in vals.items()},
            sd={k: float(v.std(ddof=1)) for k, v in vals.items()},
            paired_diff_vs_A_mean={k: float(v.mean()) for k, v in dif.items()},
            paired_diff_vs_A_sd={k: float(v.std(ddof=1)) for k, v in dif.items()},
            seeds_better_ba=int((dif['balanced_accuracy'] > 1e-12).sum()),
            seeds_worse_ba=int((dif['balanced_accuracy'] < -1e-12).sum()))
    return summary


def select(summary):
    guard = summary['A']['mean']['brier_score'] + BRIER_GUARD
    eligible = [s.name for s in CANDIDATES[1:] if summary[s.name]['mean']['brier_score'] <= guard]
    winner = max(eligible, key=lambda n: summary[n]['mean']['balanced_accuracy']) if eligible else None
    if winner is None:
        return dict(eligible=eligible, winner=None, better=False, reason='no candidate passed the Brier guard')
    d = summary[winner]
    margin_ok = d['paired_diff_vs_A_mean']['balanced_accuracy'] > d['paired_diff_vs_A_sd']['balanced_accuracy']
    brier_ok = d['paired_diff_vs_A_mean']['brier_score'] <= BRIER_GUARD
    return dict(eligible=eligible, winner=winner, better=bool(margin_ok and brier_ok and
                d['paired_diff_vs_A_mean']['balanced_accuracy'] > 0),
                paired_ba_diff_mean=d['paired_diff_vs_A_mean']['balanced_accuracy'],
                paired_ba_diff_sd=d['paired_diff_vs_A_sd']['balanced_accuracy'],
                paired_brier_diff_mean=d['paired_diff_vs_A_mean']['brier_score'])


def run_all(table, seeds, jobs=-1):
    return dict(Parallel(n_jobs=jobs)(delayed(run_seed)(table, s) for s in seeds))


def check_reference(table, ref):
    """Candidate A at seed 42 must reproduce the saved baseline folds and predictions."""
    saved = pd.read_csv(V1_REFERENCE / 'heldout_predictions.csv')
    assert (saved.OBJECTID.to_numpy() == table.OBJECTID.to_numpy()).all()
    assert (saved.year.to_numpy() == table.year.to_numpy()).all()
    a = ref['A']
    assert (a['folds'] == saved.fold.to_numpy()).all(), 'Seed-42 folds differ from the saved baseline'
    assert np.allclose(a['proba'], saved.silage_probability.to_numpy(), atol=1e-9), 'A != saved baseline'
    saved_metrics = json.loads((V1_REFERENCE / 'metrics.json').read_text())['logistic']
    assert abs(a['score']['balanced_accuracy'] - saved_metrics['balanced_accuracy']) < 1e-12
    assert abs(a['score']['brier_score'] - saved_metrics['brier_score']) < 1e-12
    ref_model = rb.build_model()
    assert ref_model.get_params()['logisticregression'].get_params() == \
        pipeline(BY_NAME['A'])[-1].get_params()


def field_bootstrap(table, per_seed, seeds, cand, n_boot=500, rng_seed=0):
    """Post hoc (added after scores were seen; not part of selection): resample fields with
    replacement over each seed's pooled held-out calls and take BA(cand) - BA(A). This adds the
    row-sampling uncertainty that the seed-to-seed sd ignores (it does not refit models)."""
    rng = np.random.default_rng(rng_seed)
    y = (table.label == 'Silage').astype(int).to_numpy()
    fields = table.OBJECTID.unique()
    rows_of = {f: np.flatnonzero(table.OBJECTID.to_numpy() == f) for f in fields}
    diffs = []
    for s in seeds:
        a, c = per_seed[s]['A']['pred'], per_seed[s][cand]['pred']
        for _ in range(n_boot):
            idx = np.concatenate([rows_of[f] for f in rng.choice(fields, len(fields))])
            if len(set(y[idx])) < 2:
                continue
            ba = lambda p: 0.5 * (p[idx][y[idx] == 1].mean() + (1 - p[idx][y[idx] == 0]).mean())
            diffs.append(ba(c) - ba(a))
    diffs = np.array(diffs)
    return dict(mean=float(diffs.mean()), ci95=[float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
                share_le_zero=float((diffs <= 0).mean()), draws=int(len(diffs)))


def fmt(m, s):
    return f'{m:.3f} ± {s:.3f}'


def main():
    rb.verify_originals()
    OUT.mkdir(parents=True, exist_ok=True)
    table, _ = build_table()
    y = (table.label == 'Silage').astype(int).to_numpy()
    assert list(BASE_FEATURES) == list(rb.FEATURES)

    _, ref = run_seed(table, REFERENCE_SEED)
    check_reference(table, ref)
    per_seed = run_all(table, SELECTION_SEEDS)
    summary = summarize(per_seed, SELECTION_SEEDS)
    decision = select(summary)

    nested = Parallel(n_jobs=-1)(delayed(nested_selection)(table, s) for s in SELECTION_SEEDS)
    nested_ba = np.array([n[1]['balanced_accuracy'] for n in nested])
    nested_brier = np.array([n[1]['brier_score'] for n in nested])
    pick_counts = pd.Series([p for n in nested for p in n[2]]).value_counts().to_dict()
    best_apparent = max(summary[n]['mean']['balanced_accuracy'] for n in summary)
    a_ba = np.array([per_seed[s]['A']['score']['balanced_accuracy'] for s in SELECTION_SEEDS])
    nested_diff = nested_ba - a_ba
    pairwise = {f'{x}-{z}': dict(mean=float(d.mean()), sd=float(d.std(ddof=1)), better=int((d > 1e-12).sum()),
                                 worse=int((d < -1e-12).sum()))
                for x, z in [('H', 'G'), ('H', 'C'), ('H', 'D'), ('G', 'B')]
                for d in [np.array([per_seed[s][x]['score']['balanced_accuracy'] -
                                    per_seed[s][z]['score']['balanced_accuracy'] for s in SELECTION_SEEDS])]}

    # Sensitivity only: 327/2021 removed from training and scoring.
    keep = ~((table.OBJECTID == SUSPECT[0]) & (table.year == SUSPECT[1]))
    t2 = table[keep].reset_index(drop=True)
    per_seed2 = run_all(t2, SELECTION_SEEDS)
    summary2 = summarize(per_seed2, SELECTION_SEEDS)
    _, ref2 = run_seed(t2, REFERENCE_SEED)

    # Per-seed metrics table.
    rows = []
    for label, ps, seeds in [('all_44', per_seed, SELECTION_SEEDS), ('excl_327_2021', per_seed2, SELECTION_SEEDS)]:
        for s in seeds:
            for n in ps[s]:
                rows.append(dict(dataset=label, seed=s, candidate=n, C_by_fold=';'.join(map(str, ps[s][n]['C'])),
                                 **{k: v for k, v in ps[s][n]['score'].items() if k != 'confusion_matrix'}))
    for n in ref:
        rows.append(dict(dataset='all_44', seed=REFERENCE_SEED, candidate=n, C_by_fold=';'.join(map(str, ref[n]['C'])),
                         **{k: v for k, v in ref[n]['score'].items() if k != 'confusion_matrix'}))
    pd.DataFrame(rows).to_csv(OUT / 'seed_metrics.csv', index=False)

    # Per-row calls: how often each field-year is called Silage across selection seeds.
    calls = table[['OBJECTID', 'year', 'label']].copy()
    for n in BY_NAME:
        calls[f'{n}_silage_call_rate'] = np.mean([per_seed[s][n]['pred'] for s in SELECTION_SEEDS], axis=0)
        calls[f'{n}_mean_probability'] = np.mean([per_seed[s][n]['proba'] for s in SELECTION_SEEDS], axis=0)
        calls[f'{n}_seed42_probability'] = ref[n]['proba']
    calls.round(4).to_csv(OUT / 'row_calls.csv', index=False)

    report = dict(
        protocol='Pre-registered in results.md. Outer 5-fold StratifiedGroupKFold by OBJECTID; '
                 'selection seeds 0-19; seed 42 reported separately; all fitting inside training folds.',
        candidates={s.name: dict(description=s.description, features=list(s.features)) for s in CANDIDATES},
        c_grid=C_GRID, brier_guard=BRIER_GUARD, selection_seeds=SELECTION_SEEDS,
        seed42={n: ref[n]['score'] for n in ref},
        selection_seeds_summary=summary, decision=decision,
        optimism=dict(best_apparent_mean_ba=best_apparent, nested_selection_mean_ba=float(nested_ba.mean()),
                      nested_selection_sd_ba=float(nested_ba.std(ddof=1)),
                      nested_selection_mean_brier=float(nested_brier.mean()),
                      current_A_mean_ba=summary['A']['mean']['balanced_accuracy'],
                      estimated_optimism=float(best_apparent - nested_ba.mean()),
                      nested_ba_by_seed=dict(zip(SELECTION_SEEDS, map(float, nested_ba))),
                      nested_minus_A=dict(mean=float(nested_diff.mean()), sd=float(nested_diff.std(ddof=1)),
                                          better=int((nested_diff > 1e-12).sum()),
                                          worse=int((nested_diff < -1e-12).sum())),
                      inner_pick_counts=pick_counts),
        pairwise_ba_diff=pairwise,
        sensitivity_excl_327_2021=dict(note='Sensitivity only; never used for selection. Folds differ.',
                                       n=int(len(t2)), summary=summary2,
                                       seed42={n: ref2[n]['score'] for n in ref2}),
        posthoc_field_bootstrap_vs_A={n: field_bootstrap(table, per_seed, SELECTION_SEEDS, n)
                                      for n in BY_NAME if n != 'A'},
        n=int(len(table)), silage=int(y.sum()))
    (OUT / 'summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')

    print('candidate  mean BA  (sd)   recall  precision  F1  Brier | dBA mean (sd)  dBrier  better/worse seeds')
    for n, d in summary.items():
        m, s, dm, ds = d['mean'], d['sd'], d['paired_diff_vs_A_mean'], d['paired_diff_vs_A_sd']
        print(f"{n}  {fmt(m['balanced_accuracy'], s['balanced_accuracy'])}  {fmt(m['silage_recall'], s['silage_recall'])}"
              f"  {fmt(m['silage_precision'], s['silage_precision'])}  {fmt(m['silage_f1'], s['silage_f1'])}"
              f"  {fmt(m['brier_score'], s['brier_score'])} | {dm['balanced_accuracy']:+.3f} ({ds['balanced_accuracy']:.3f})"
              f"  {dm['brier_score']:+.4f}  {d['seeds_better_ba']}/{d['seeds_worse_ba']}")
    print('seed 42:', {n: round(ref[n]['score']['balanced_accuracy'], 3) for n in ref})
    print('decision:', decision)
    print('optimism:', report['optimism'])
    print('excl 327:', {n: round(d['mean']['balanced_accuracy'], 3) for n, d in summary2.items()})
    print('excl 327 dBA:', {n: round(d['paired_diff_vs_A_mean']['balanced_accuracy'], 3) for n, d in summary2.items()})
    print('bootstrap:', report['posthoc_field_bootstrap_vs_A'])
    print('nested - A:', report['optimism']['nested_minus_A'])
    print('pairwise:', pairwise)
    rb.verify_originals()


if __name__ == '__main__':
    main()
