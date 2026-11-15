# Model v2 experiment: can the silage-vs-grain classifier be made genuinely better?

## Pre-registration (written and committed before any candidate was scored)

Data: the 44 labeled BARC field-years (32 Grain / 12 Silage, 34 fields) in the baseline's
row order, from committed `baseline/outputs/features.csv` and `observations.csv` only. No
unlabeled fields, yield-coverage rows, 2025 data, or NASS values are read. The nine
baseline features rebuilt from `observations.csv` match `features.csv` exactly.

Timing features (definitions and constants in `features.py`, fixed now): `decline_doy`
(sustained decline >= 0.25 below the smoothed peak; 335 when none), `drop_doy` and
`drop_size` (largest decrease between consecutive 3-date-median-smoothed values), and
`regrowth` (rise after the post-peak smoothed minimum).

Candidates (all: training-fold median imputation, training-fold standard scaling,
logistic regression, `max_iter=2000`, `random_state=42`):

| ID | Features | Model change vs current |
| --- | --- | --- |
| A | baseline 9 | none: current model, C=1, threshold 0.5 |
| B | baseline 9 | `class_weight='balanced'` |
| C | baseline 9 + 4 timing | none |
| D | baseline 9 + 4 timing | `class_weight='balanced'` |
| E | baseline features recomputed from Jul-Oct observations only (8: no ndvi_11) | none |
| F | baseline 9 | L2 C chosen by inner CV |
| G | baseline 9 | threshold = training-fold silage prevalence (probabilities unchanged) |
| H | baseline 9 + 4 timing | L1 (liblinear), C chosen by inner CV |

Inner CV (F, H): grid C in {0.01, 0.03, 0.1, 0.3, 1, 3, 10}; 4-fold StratifiedGroupKFold
by field on the outer training fold only (shuffle, same seed as the outer split); pooled
inner log loss; ties to the smaller C. A single-class inner training fold falls back to C=1.

Evaluation: outer 5-fold StratifiedGroupKFold by OBJECTID, shuffle. Seed 42 (the saved
baseline split, already seen) is reported separately. Selection uses 20 fresh seeds 0-19.
Every candidate uses the same split per seed, so differences are paired. Metrics per seed
on pooled held-out predictions: balanced accuracy, silage recall, precision, F1, Brier.

Selection rule: among B-H, the winner has the highest mean balanced accuracy over seeds
0-19 among candidates whose mean Brier is at most A's mean Brier + 0.01. It counts as
better than A only if its mean paired balanced-accuracy difference (candidate minus A,
per seed) exceeds the seed-to-seed sd of that paired difference, and its mean paired Brier
difference is at most +0.01. Otherwise A stays.

Optimism: the selection step (best inner balanced accuracy subject to the Brier guard,
ties to A, then list order) is repeated inside every outer training fold with inner
grouped CV, and the pick is scored on the outer test fold. The gap between the winner's
apparent mean balanced accuracy and this nested score estimates selection optimism.

Label 327/2021 (suspect: 2021 combine data covers it as grain) stays Silage. As a
sensitivity check only, every candidate is rerun with that row removed from training and
scoring (folds differ as a result). The sensitivity run never drives selection.

## Results

Reproduce: `python baseline/model_v2/experiment.py` then `python baseline/model_v2/candidate.py`
(about 40 s; reads only committed outputs; writes only `baseline/model_v2/outputs/`).
Candidate A at seed 42 reproduces the saved baseline exactly (same folds, same probabilities,
BA 0.776, Brier 0.083). Per-seed numbers: `outputs/seed_metrics.csv`; per-field-year call
rates: `outputs/row_calls.csv`; everything else: `outputs/summary.json`.

### Selection seeds 0-19 (mean ± sd across seeds; all 44 rows, 327/2021 kept as Silage)

| ID | Balanced acc. | Silage recall | Precision | F1 | Brier | ΔBA vs A (paired) | ΔBrier vs A | Seeds better/worse BA |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A current | 0.803 ± 0.035 | 0.658 ± 0.076 | 0.826 ± 0.052 | 0.730 ± 0.049 | 0.083 ± 0.007 | - | - | - |
| B balanced | 0.884 ± 0.025 | 0.862 ± 0.056 | 0.778 ± 0.039 | 0.816 ± 0.030 | 0.090 ± 0.007 | +0.082 ± 0.026 | +0.0065 | 20/0 |
| C +timing | 0.901 ± 0.032 | 0.867 ± 0.050 | 0.836 ± 0.066 | 0.850 ± 0.049 | 0.064 ± 0.010 | +0.098 ± 0.041 | -0.0190 | 20/0 |
| D +timing, balanced | 0.908 ± 0.012 | 0.917 ± 0.000 | 0.777 ± 0.043 | 0.840 ± 0.025 | 0.077 ± 0.011 | +0.106 ± 0.037 | -0.0059 | 20/0 |
| E Jul-Oct only | 0.832 ± 0.033 | 0.696 ± 0.068 | 0.888 ± 0.020 | 0.779 ± 0.048 | 0.118 ± 0.008 | +0.029 ± 0.057 | +0.0350 | 14/4 |
| F inner-CV C | 0.802 ± 0.037 | 0.650 ± 0.075 | 0.840 ± 0.048 | 0.731 ± 0.053 | 0.090 ± 0.008 | -0.001 ± 0.020 | +0.0067 | 3/3 |
| G prevalence threshold | 0.904 ± 0.017 | 0.908 ± 0.026 | 0.774 ± 0.035 | 0.836 ± 0.026 | 0.083 ± 0.007 | +0.102 ± 0.038 | +0.0000 | 20/0 |
| **H +timing, L1, inner-CV C** | **0.925 ± 0.022** | 0.896 ± 0.037 | 0.886 ± 0.066 | 0.889 ± 0.037 | **0.062 ± 0.010** | **+0.123 ± 0.040** | **-0.0215** | 20/0 |

ΔBA is mean ± sd over seeds of (candidate - A) on the same split. The always-Grain predictor
scores BA 0.5. One silage row is worth 0.042 BA; one grain row 0.016.

### Seed 42 (the saved baseline split; already seen, not used for selection)

| ID | BA | Recall | Precision | F1 | Brier | Confusion [[TN, FP], [FN, TP]] |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| A | 0.776 | 0.583 | 0.875 | 0.700 | 0.083 | [[31, 1], [5, 7]] |
| B | 0.870 | 0.833 | 0.769 | 0.800 | 0.092 | [[29, 3], [2, 10]] |
| C | 0.901 | 0.833 | 0.909 | 0.870 | 0.068 | [[31, 1], [2, 10]] |
| D | 0.896 | 0.917 | 0.733 | 0.815 | 0.083 | [[28, 4], [1, 11]] |
| E | 0.818 | 0.667 | 0.889 | 0.762 | 0.121 | [[31, 1], [4, 8]] |
| F | 0.776 | 0.583 | 0.875 | 0.700 | 0.098 | [[31, 1], [5, 7]] |
| G | 0.896 | 0.917 | 0.733 | 0.815 | 0.083 | [[28, 4], [1, 11]] |
| H | 0.901 | 0.833 | 0.909 | 0.870 | 0.065 | [[31, 1], [2, 10]] |

### Decision (pre-registered rule)

- Brier guard (mean Brier <= 0.083 + 0.01): E fails (0.118); B, C, D, F, G, H pass.
- Winner: **H** (highest mean BA, 0.925). Paired ΔBA +0.123 vs a seed-to-seed sd of 0.040, so it
  clears the bar; ΔBrier -0.0215 (better calibrated, not worse). **H counts as better than A.**
- Two simpler changes also clear the bar and are worth knowing: G (same model, threshold at the
  training silage prevalence, about 0.27; Brier unchanged by construction) gives +0.102, and C
  (timing features, ordinary L2) gives +0.098 with better Brier. The common thread: the current
  model's 0.5 threshold is too high for a 27% class, and the timing features add real signal.

### How much of this is optimism

- **Selection optimism.** Running the whole selection rule inside each outer training fold
  (inner grouped CV over all 8 candidates, pick by the same rule, score the pick on the outer
  test fold) gives a mean BA of **0.869 ± 0.054** (Brier 0.079) over seeds 0-19, versus the
  winner's apparent 0.925: estimated optimism **0.056**. The honest expectation for "pick the
  best of these 8 the same way" is therefore about 0.87, still about +0.07 over A (0.803).
  The inner rule picked H in 31 of 100 outer folds, C 22, D 18, A 8, others fewer.
- **Row-sampling uncertainty (post hoc, added after scores were seen).** The seed sd only
  measures split noise on the same 44 rows, so the pre-registered bar is lenient. A field-level
  bootstrap of the paired held-out calls (500 resamples x 20 seeds, no refits) gives ΔBA for H
  of +0.123, 95% interval **[0.000, 0.285]**, with 5.6% of draws <= 0. For G: [-0.031, 0.258],
  9.8% <= 0; for C: [-0.020, 0.263], 10.8% <= 0. The improvement is consistent across splits
  but rests on 3-4 silage field-years, so its size is very uncertain.
- **Feature provenance.** The timing features were defined before scoring, but not blind: the
  physical story (silage chopped green Aug-Sep, regrowth in Nov) and the list of missed fields
  were known, and the decline rule (same 0.25 drop) had already been scored on these rows.

### Label 327/2021 sensitivity (row removed from training and scoring; folds differ)

| ID | BA | Recall | Brier | ΔBA vs A | ΔBrier |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 0.861 ± 0.048 | 0.777 ± 0.091 | 0.054 | - | - |
| B | 0.952 ± 0.035 | 0.968 ± 0.068 | 0.052 | +0.092 ± 0.034 | -0.0012 |
| C | 0.953 ± 0.039 | 0.936 ± 0.073 | 0.030 | +0.093 ± 0.041 | -0.0239 |
| D | 0.971 ± 0.034 | 0.986 ± 0.061 | 0.031 | +0.110 ± 0.045 | -0.0225 |
| E | 0.821 ± 0.027 | 0.673 ± 0.054 | 0.106 | -0.040 ± 0.058 | +0.0525 |
| F | 0.873 ± 0.057 | 0.809 ± 0.110 | 0.056 | +0.013 ± 0.031 | +0.0025 |
| G | 0.952 ± 0.030 | 0.986 ± 0.061 | 0.054 | +0.091 ± 0.045 | +0.0000 |
| H | 0.968 ± 0.031 | 0.968 ± 0.044 | 0.024 | +0.107 ± 0.046 | -0.0300 |

The ranking and the size of the gain over A do not depend on 327/2021. Every model calls
327/2021 Grain in every seed (H's probability about 0.00), consistent with the yield evidence
that its label is wrong; it stays Silage in the data.

### What H changes, in plain words

Fitted on all 44 rows, inner CV picks C = 1 and L1 keeps three features (standardized log-odds
coefficients): **November NDVI +1.45** (green again in November: regrowth after an early
harvest), **largest consecutive NDVI drop +1.22** (an abrupt cut rather than a gradual dry-down),
and **September NDVI -0.48** (already low in September). The other ten coefficients are zero.

Across seeds 0-19 (share of seeds the row is called Silage, A -> H):

- Now caught: 231/2022 (0.55 -> 1.00), 252/2022 (0.20 -> 1.00), 323/2023 (0.05 -> 1.00),
  254/2023 (0.10 -> 0.75).
- Still missed: 327/2021 (0 -> 0; suspect label).
- Fixed false silage: 24/2021 (1.00 -> 0.30).
- New/worse false silage: 279/2022 Grain (0.60 -> 0.80); 1/2021 (0.10 -> 0.20) and 263/2021
  (0 -> 0.15) occasionally.

At seed 42 specifically (`outputs/heldout_predictions_candidate.csv`): H gains 231/2022,
252/2022, 254/2023, 323/2023 and clears 24/2021, but misses 291/2021 (p 0.45; caught in every
other seed, mean p 0.94) and calls 279/2022 Silage: 10/12 recall, 10/11 precision, BA 0.901,
Brier 0.065 (A: 7/12, 7/8, 0.776, 0.083).

## Caveats

- 44 field-years, 12 silage, 34 fields near one research farm, three years. Nearby fields share
  weather and management. Nothing here shows transfer to other regions or to 2025.
- H relies on **November** NDVI and a full-season series. It cannot be used as-is for as-of
  dates before Nov 30; the Jul-Oct candidate (E) was worse and failed the Brier guard.
- The selection bar (seed sd) understates uncertainty; the bootstrap interval touches zero.
- All 8 candidates were run once; no candidate was added or changed after scores were seen.
  The bootstrap is the only post hoc addition and was not used for selection.

## Adoption (the ML owner's call; nothing shared was regenerated here)

`candidate.py` exposes `FEATURES`, `timing_from_observations`, `add_timing_features`, and
`build_model()`. Its `fit(X, y, groups)` **requires field ids** (C is chosen by grouped inner
CV), unlike `run_baseline.build_model()`; `predict_proba` is sklearn-shaped. To adopt:

1. `baseline/run_baseline.py`: add the 4 timing features in `summarize` (from the same daily
   series), swap `build_model`, pass `groups` in `evaluate`; then
   `python baseline/run_baseline.py evaluate` regenerates `features.csv`,
   `heldout_predictions.csv`, `metrics.json`, `results.md`.
2. `baseline/export_contributions.py` (reads `logit.coef_`; works per fold but must pass groups).
3. `harvest/asof.py` hard-codes the baseline pipeline, `>= 0.5`, and month-only features. Before
   Nov 30 it should keep the current month-feature refit (H needs November); from Nov 30 it reads
   the saved predictions. Then `python -m harvest.export_asof` regenerates `asof.json`, and the
   rollup that reads it.
4. `baseline/unlabeled_calls.py predict` calls `rb.build_model().fit(X, y)`; timing features
   for blank field-years come from the per-scene observations in `baseline/cache_unlabeled/`.
5. The 2025 satellite estimate (`baseline/estimate_2025/estimate.py` on role/estimate-2025)
   also calls `rb.build_model()`; its extraction keeps per-scene observations
   (`observations.csv.gz`), so the timing features can be computed. Rerun it and its benchmark.
6. Downstream of `heldout_predictions.csv`: `decline_rule_baseline.py`, `compare_nemotron.py`,
   `inspect_field_cases.py`, `export_chips.py`, the backend artifact tests
   (`backend/tests`), and `scripts/smoke_test.py` should be rerun.

Lowest-risk alternative if the full swap is too much before the deadline: G changes only the
decision threshold (to the training silage prevalence) and keeps every probability, coefficient,
and Brier score identical; it needs a threshold change in `run_baseline.evaluate`,
`harvest/asof.py`, and the unlabeled/2025 callers.
