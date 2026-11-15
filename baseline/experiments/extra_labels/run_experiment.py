"""Experiment only: does adding public BARC harvest labels to TRAINING improve model v2?

    python baseline/experiments/extra_labels/run_experiment.py

Test rows are only the 44 official labeled field-years, split exactly as the saved model-v2
evaluation (5-fold StratifiedGroupKFold by OBJECTID over the 44 rows, seeds 0-19 = the v2
selection seeds, seed 42 = the saved split). For each outer fold, extra rows are appended to
the TRAINING rows only, after dropping every extra row whose field (OBJECTID) is in that test
fold. The model is the unchanged v2 code path (experiment.fit with candidate H: 13 features,
median imputation, scaling, L1 logistic, C by field-grouped inner CV on the training rows).

Conditions:
  a  v2, no extras (must reproduce the saved candidate-H per-seed scores)
  b  v2 + harvest-record extras (barc_mgmt_harvest_record, kraatz_harvest_record)
  c  v2 + all extras (also kraatz_planting_record = intended use at planting, weaker)

Writes only baseline/outputs/experiments/extra_labels/. Does not touch the submitted model.
"""
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

HERE = Path(__file__).resolve().parent
BASELINE = HERE.parents[1]
ROOT = BASELINE.parent
sys.path.insert(0, str(BASELINE / 'model_v2'))
sys.path.insert(0, str(BASELINE))
from features import BASE_FEATURES, TIMING_FEATURES, base_features, build_table, daily_series, timing_features  # noqa: E402
from experiment import BY_NAME, SELECTION_SEEDS, REFERENCE_SEED, fit, splits  # noqa: E402

SPEC = BY_NAME['H']
FEATURES = list(SPEC.features)
assert FEATURES == BASE_FEATURES + TIMING_FEATURES
LABELS = ROOT / 'data' / 'extra_labels' / 'labels_combined.csv'
CACHES = [BASELINE / 'cache_unlabeled', BASELINE / 'cache_extra']
OUT = BASELINE / 'outputs' / 'experiments' / 'extra_labels'
HARVEST = {'barc_mgmt_harvest_record', 'kraatz_harvest_record'}
EXTRA_SEEDS = list(range(100))  # sensitivity: more fresh splits than the 20 selection seeds
N_BOOT = 500  # draws per seed, as in model_v2/experiment.field_bootstrap


def load_extras(official):
    """Extra rows with features, plus a list of skipped rows and why."""
    import run_baseline as rb
    sig = rb.signature()
    lab = pd.read_csv(LABELS)
    lab = lab[(lab.split == 'train_extra') & lab.use_for_training].copy()
    official_keys = set(zip(official.OBJECTID, official.year))
    rows, skipped = [], []
    for r in lab.itertuples():
        key = dict(OBJECTID=int(r.OBJECTID), year=int(r.year), label=r.label, label_source=r.label_source)
        if (key['OBJECTID'], key['year']) in official_keys:
            skipped.append(dict(key, reason='is one of the 44 official field-years (official label wins)'))
            continue
        if key['year'] < 2017:
            skipped.append(dict(key, reason='2015: Sentinel-2 L2A extraction not attempted (per plan)'))
            continue
        path = next((c / f"{key['OBJECTID']}_{key['year']}.json" for c in CACHES
                     if (c / f"{key['OBJECTID']}_{key['year']}.json").exists()), None)
        if path is None:
            skipped.append(dict(key, reason='no Sentinel-2 series cached (extraction not finished or failed)'))
            continue
        cached = json.loads(path.read_text())
        if cached['signature'] != sig:
            skipped.append(dict(key, reason=f'stale cache signature: {path.name}'))
            continue
        series = daily_series(cached['observations'])
        read_errors = sum(o['status'] == 'read_error' for o in cached['observations'])
        if not series:
            skipped.append(dict(key, reason='no accepted (cloud-free) observations'))
            continue
        rows.append(dict(key, cache=f'{path.parent.name}/{path.name}', valid_dates=len(series),
                         read_errors=read_errors, **base_features(series), **timing_features(series)))
    return pd.DataFrame(rows), skipped


def score(y, pred):
    tp, fn = int(((pred == 1) & (y == 1)).sum()), int(((pred == 0) & (y == 1)).sum())
    fp, tn = int(((pred == 1) & (y == 0)).sum()), int(((pred == 0) & (y == 0)).sum())
    return dict(balanced_accuracy=0.5 * (tp / (tp + fn) + tn / (tn + fp)), silage_hits=tp, silage_total=tp + fn,
                grain_false_alarms=fp, grain_total=fp + tn)


def run(official, extras, seed, peak_filter=False):
    """Held-out calls on the 44 official rows; extras only ever join training folds.

    peak_filter (post-hoc sensitivity, label-blind): also drop extras whose peak_ndvi is below
    the lowest peak_ndvi among that fold's official TRAINING rows (series that do not look like
    a corn canopy, e.g. a polygon that no longer matches the field in earlier years)."""
    X = official[FEATURES].to_numpy(float)
    y = (official.label == 'Silage').astype(int).to_numpy()
    g = official.OBJECTID.to_numpy()
    peak = official.peak_ndvi.to_numpy(float)
    Xe = extras[FEATURES].to_numpy(float) if len(extras) else np.zeros((0, len(FEATURES)))
    ye = (extras.label == 'Silage').astype(int).to_numpy() if len(extras) else np.zeros(0, int)
    ge = extras.OBJECTID.to_numpy() if len(extras) else np.zeros(0, int)
    pe = extras.peak_ndvi.to_numpy(float) if len(extras) else np.zeros(0)
    proba, pred, folds, cs, n_extra = np.full(len(y), np.nan), np.full(len(y), -1), np.full(len(y), -1), [], []
    for k, (train, test) in enumerate(splits(y, g, seed, 5), 1):
        keep = ~np.isin(ge, g[test])  # no extra row (any year) of a test field
        if peak_filter:
            keep &= pe >= np.nanmin(peak[train])
        assert not set(ge[keep]) & set(g[test]), 'Field leakage from extras'
        Xt, yt, gt = np.vstack([X[train], Xe[keep]]), np.r_[y[train], ye[keep]], np.r_[g[train], ge[keep]]
        m = fit(SPEC, Xt, yt, gt, seed)
        proba[test], pred[test], folds[test] = m.predict_proba(X[test]), m.predict(X[test]), k
        cs.append(m.C)
        n_extra.append(int(keep.sum()))
    assert np.isfinite(proba).all() and (pred >= 0).all()
    return dict(score=score(y, pred), proba=proba, pred=pred, folds=folds, C=cs, n_extra_by_fold=n_extra)


def field_bootstrap(official, res_a, res_x, seeds, rng_seed=0):
    """Resample official fields with replacement over each seed's pooled held-out calls;
    BA(x) - BA(a). Adds row-sampling uncertainty that the seed spread ignores (no refits)."""
    rng = np.random.default_rng(rng_seed)
    y = (official.label == 'Silage').astype(int).to_numpy()
    fields = official.OBJECTID.unique()
    rows_of = {f: np.flatnonzero(official.OBJECTID.to_numpy() == f) for f in fields}
    diffs = []
    for s in seeds:
        a, c = res_a[s]['pred'], res_x[s]['pred']
        for _ in range(N_BOOT):
            idx = np.concatenate([rows_of[f] for f in rng.choice(fields, len(fields))])
            yy = y[idx]
            if len(set(yy)) < 2:
                continue
            ba = lambda p: 0.5 * (p[idx][yy == 1].mean() + (1 - p[idx][yy == 0]).mean())
            diffs.append(ba(c) - ba(a))
    d = np.array(diffs)
    return dict(mean=float(d.mean()), ci95=[float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))],
                share_le_zero=float((d <= 0).mean()), draws=int(len(d)))


def summarize(res, seeds, names):
    out = {}
    for n in names:
        ba = np.array([res[n][s]['score']['balanced_accuracy'] for s in seeds])
        hits = np.array([res[n][s]['score']['silage_hits'] for s in seeds])
        fa = np.array([res[n][s]['score']['grain_false_alarms'] for s in seeds])
        d = ba - np.array([res['a'][s]['score']['balanced_accuracy'] for s in seeds])
        out[n] = dict(seeds=len(seeds), ba_mean=float(ba.mean()), ba_sd=float(ba.std(ddof=1)),
                      ba_min=float(ba.min()), ba_max=float(ba.max()),
                      silage_hits_mean=float(hits.mean()), silage_hits_range=[int(hits.min()), int(hits.max())],
                      grain_false_alarms_mean=float(fa.mean()), grain_false_alarms_range=[int(fa.min()), int(fa.max())],
                      paired_dba_mean=float(d.mean()), paired_dba_sd=float(d.std(ddof=1)) if len(d) > 1 else 0.0,
                      paired_dba_range=[float(d.min()), float(d.max())],
                      seeds_better=int((d > 1e-12).sum()), seeds_worse=int((d < -1e-12).sum()),
                      seeds_tied=int((np.abs(d) <= 1e-12).sum()))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    official, _ = build_table()
    assert len(official) == 44 and (official.label == 'Silage').sum() == 12
    extras, skipped = load_extras(official)
    sets = {'a': extras.iloc[0:0], 'b': extras[extras.label_source.isin(HARVEST)].reset_index(drop=True),
            'c': extras}
    sets['b_peak'], sets['c_peak'] = sets['b'], sets['c']  # same rows; peak filter applied per fold
    names = list(sets)
    all_seeds = sorted(set(SELECTION_SEEDS) | {REFERENCE_SEED} | set(EXTRA_SEEDS))
    jobs = [(n, s) for n in names for s in all_seeds]
    flat = Parallel(n_jobs=-1)(delayed(run)(official, sets[n], s, n.endswith('_peak')) for n, s in jobs)
    res = {n: {} for n in names}
    for (n, s), r in zip(jobs, flat):
        res[n][s] = r

    # Sanity: condition a reproduces the saved model-v2 numbers (same folds, same code path).
    saved = pd.read_csv(BASELINE / 'model_v2' / 'outputs' / 'seed_metrics.csv')
    saved = saved[(saved.dataset == 'all_44') & (saved.candidate == 'H')].set_index('seed')
    repro = {int(s): bool(abs(saved.loc[s, 'balanced_accuracy'] - res['a'][s]['score']['balanced_accuracy']) < 1e-12)
             for s in SELECTION_SEEDS + [REFERENCE_SEED] if s in saved.index}
    assert all(repro.values()), f'Condition a does not reproduce saved v2 scores: {repro}'
    saved42 = json.loads((BASELINE / 'outputs' / 'metrics.json').read_text())['logistic']
    assert abs(saved42['balanced_accuracy'] - res['a'][REFERENCE_SEED]['score']['balanced_accuracy']) < 1e-12

    main_seeds = list(SELECTION_SEEDS)
    summary = summarize(res, main_seeds, names)
    summary100 = summarize(res, EXTRA_SEEDS, names)
    seed42 = {n: dict(res[n][REFERENCE_SEED]['score'], C_by_fold=res[n][REFERENCE_SEED]['C'],
                      n_extra_by_fold=res[n][REFERENCE_SEED]['n_extra_by_fold']) for n in names}
    boot = {n: field_bootstrap(official, res['a'], res[n], main_seeds) for n in names if n != 'a'}
    c_shift = {n: dict(mean_log10_C=float(np.mean([np.log10(c) for s in main_seeds for c in res[n][s]['C']])),
                       share_folds_C_differs_from_a=float(np.mean([ca != cn for s in main_seeds
                           for ca, cn in zip(res['a'][s]['C'], res[n][s]['C'])])))
               for n in names}
    n_extra_folds = {n: [int(x) for s in main_seeds for x in res[n][s]['n_extra_by_fold']] for n in names}

    # Which official field-years change call vs a (selection seeds), to show what the extras move.
    y = (official.label == 'Silage').astype(int).to_numpy()
    changes = {}
    for n in [n for n in names if n != 'a']:
        rate_a = np.mean([res['a'][s]['pred'] for s in main_seeds], axis=0)
        rate_n = np.mean([res[n][s]['pred'] for s in main_seeds], axis=0)
        changes[n] = [dict(OBJECTID=int(r.OBJECTID), year=int(r.year), label=r.label,
                           silage_call_rate_a=float(ra), silage_call_rate=float(rn))
                      for r, ra, rn in zip(official.itertuples(), rate_a, rate_n) if abs(ra - rn) > 1e-12]

    def counts(df):
        if df.empty:
            return {}
        return {str(k): int(v) for k, v in df.groupby(['year', 'label', 'label_source']).size().items()}

    report = dict(
        question='Does adding public BARC harvest/planting labels (extra field-years) to training improve '
                 'model v2 on the 44 official labeled field-years?',
        protocol='Outer 5-fold StratifiedGroupKFold by OBJECTID over the 44 official rows only (identical folds '
                 'to the saved v2 evaluation); extras appended to training folds only, minus every extra row of '
                 'a test-fold field; v2 code path (experiment.fit, candidate H) unchanged; main seeds 0-19 '
                 '(v2 selection seeds), seed 42 = saved split, seeds 0-99 sensitivity.',
        conditions={'a': 'v2, no extras', 'b': 'v2 + harvest-record extras (barc_mgmt_harvest_record, '
                    'kraatz_harvest_record)', 'c': 'v2 + all extras (adds kraatz_planting_record)',
                    'b_peak': 'post hoc: b minus extras whose peak_ndvi < min peak_ndvi of the fold'
                              's official training rows (label-blind)',
                    'c_peak': 'post hoc: c with the same peak filter'},
        extras_used=dict(b=dict(n=int(len(sets['b'])), by_year_label_source=counts(sets['b'])),
                         c=dict(n=int(len(sets['c'])), by_year_label_source=counts(sets['c']))),
        extras_rows=extras.drop(columns=FEATURES).to_dict(orient='records'),
        extra_rows_in_training_per_fold={n: dict(min=min(v), max=max(v)) for n, v in n_extra_folds.items() if v},
        skipped=skipped,
        reproduces_saved_v2=dict(seeds_checked=len(repro), all_equal=all(repro.values()),
                                 seed42_ba=res['a'][REFERENCE_SEED]['score']['balanced_accuracy']),
        summary_seeds_0_19=summary, summary_seeds_0_99=summary100, seed42=seed42,
        field_bootstrap_vs_a_seeds_0_19=boot, inner_cv_C_seeds_0_19=c_shift, changed_official_calls_seeds_0_19=changes,
        per_seed={n: {int(s): res[n][s]['score'] for s in all_seeds} for n in names})
    (OUT / 'results.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['extras_used', 'skipped', 'reproduces_saved_v2', 'summary_seeds_0_19',
                                              'summary_seeds_0_99', 'seed42', 'field_bootstrap_vs_a_seeds_0_19',
                                              'inner_cv_C_seeds_0_19', 'changed_official_calls_seeds_0_19', 'extra_rows_in_training_per_fold']},
                     indent=1, default=str))


if __name__ == '__main__':
    main()
