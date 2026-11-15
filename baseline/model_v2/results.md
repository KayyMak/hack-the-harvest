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
