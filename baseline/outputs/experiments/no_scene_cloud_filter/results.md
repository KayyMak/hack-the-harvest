# Removing the whole-scene cloud cutoff: exploratory results

The original query discarded every Sentinel-2 scene with >=40% tile-wide cloud
cover before inspecting the actual BARC field. A targeted input investigation
found useful field pixels inside some of those scenes. This experiment restores
those scenes while keeping the per-pixel mask and model setup fixed.

All **44 labeled field-years** were evaluated using the **same saved field
folds**. Every year of each field stays together. Imputation, scaling, and
logistic coefficients are refitted within training folds only. Feature
definitions, C=1, default class weights, and the 0.5 threshold are unchanged.

## Held-out field classification

| Metric | Original | No tile-cloud cutoff |
| --- | ---: | ---: |
| Silage precision | 87.5% | 90.0% |
| Silage recall | 58.3% | 75.0% |
| Silage F1 | 70.0% | 81.8% |
| False positive rate | 3.125% | 3.125% |
| Balanced accuracy | 77.60% | 85.94% |
| Brier score (lower is better) | 0.08257 | 0.08076 |

Confusion matrices: actual rows / predicted columns, ordered Grain, Silage.

```text
Original:              Experiment:
          Grain Silage             Grain Silage
Grain        31      1  Grain         31      1
Silage        5      7  Silage         3      9
```

Fields **231 / 2022** and **252 / 2022** changed from incorrect Grain
predictions to correct Silage predictions. Their new Silage probabilities are
53.64% and 55.49%, respectively, so these are still near-threshold predictions.
No previously correct class prediction became wrong. All seven 2022 examples
are now classified correctly; seven cases are too few for a strong reliability
claim. Class decisions for 2021 and 2023 are unchanged, while probabilities
and probability errors differ.

## Remaining errors and counterexamples

| Field / year | Reference | Predicted | New Silage probability |
| --- | --- | --- | ---: |
| 24 / 2021 | Grain | Silage | 57.61% |
| 327 / 2021 | Silage | Grain | 1.10% |
| 254 / 2023 | Silage | Grain | 38.52% |
| 323 / 2023 | Silage | Grain | 13.67% |

Importantly, the two initially inspected fields are **not fixed**. Field 323's
probability decreases from 36.58% to 13.67% despite recovering its September
decline. Its extra observations also change other features, and the classifier
is refitted on changed training inputs. Thus finding a coverage problem does
not establish that it alone caused an individual prediction error.

Field 327 remains approximately 1.1% Silage. Better sampling alone does not
resolve this case. Monthly summaries, correlated features, mask imperfections,
and limited/locally clustered training labels remain potential limitations.
No reference labels were edited, and no rule was tuned to make these cases pass.

## Input-quality evidence

- All 44 field-years gain usable dates: **833 -> 1,139 field-dates**, an increase
  of **306**. Individual field-years now have 14–37 usable dates.
- **1,448 additional field-scene records** were processed, with **zero read
  failures**. The combined table has 1,565 accepted and 1,205 rejected scene
  records. Accepted same-date duplicates are collapsed before feature summaries.
- Field 323 / September 12, 2023: the tile is **59.0% cloudy**, but about
  **69% of field pixels** pass the unchanged quality mask; NDVI is **0.258**.
  This fills the original September 7–October 2 gap with an observed decline
  by September 12. Field 323's whole-season usable dates increase **12 -> 17**.
- Field 327 / October 7, 2021: tile cloud is **50.2%**, but about **95% of field
  pixels** pass; NDVI is **0.418**. It gains two dates overall, **12 -> 14**.
- Eleven diagnostic image windows reproduce saved field/clear-pixel counts
  exactly and NDVI within 1e-6. Original field outlines appear aligned to the
  visible parcels. Imagery supports vegetation change, not proof of harvest use.
- The original pipeline is reconstructed before comparison: every saved
  baseline probability matches within 1e-10. Original sources, caches, baseline
  results, and frozen Nemotron responses are preserved.

The accepted mask still permits SCL classes 4/5/6/7, at least three valid
pixels, and at least 20% usable field coverage. Some accepted observations can
therefore remain noisy or unrepresentative. Coverage improvement is not a
guarantee of cloud-free measurements or increased model accuracy in every year.

## Labeled-field acreage, not statewide estimates

Expected acres are the sum of field area times held-out Silage probability.

| Year | Reference Silage acres | Original expected | Experiment expected |
| --- | ---: | ---: | ---: |
| 2021 | 76.49 | 88.32 | 90.42 |
| 2022 | 74.44 | 54.14 | 64.95 |
| 2023 | 107.98 | 85.94 | 85.35 |

The mean absolute expected-acreage error across these three years decreases
from **18.06 to 15.35 acres**. It improves in 2022 but worsens in 2021 and 2023.
For hard Grain/Silage class assignments, mean absolute error decreases from
33.19 to 20.08 acres. The large 2023 undercount remains. These errors cover only
the labeled BARC fields and cannot be compared directly to 2025 statewide
Quick Stats totals. Estimated probabilities have not been established as
well calibrated for statewide acreage inference.

## What this supports

The tile-wide prefilter demonstrably loses usable field observations. Removing
it is a promising input-policy candidate on this dataset. This is not an
independent final test: the small BARC dataset has already been inspected.
Keep the original run as a baseline, retain this separate experiment, and
validate on independently labeled fields/years before claiming broad improvement.
Next model work should examine whether temporal decline and coverage information
are represented adequately, without repeatedly tuning to these four errors.

See `../../../SCENE_FILTER_EXPERIMENT.md` for commands and the frozen
comparison policy. `metrics.json`, `changed_predictions.csv`, and `coverage.csv`
contain the measured numerical results. Diagnostic imagery is under
`../../diagnostics/imagery_323_327/`.
