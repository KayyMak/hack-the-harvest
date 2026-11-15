# First review of the logistic regression baseline

Historical review of model v1. For the submitted model v2, see the
[current results](../baseline/outputs/results.md) and
[model v2 experiment](../baseline/model_v2/results.md).

> **Note:** this review describes the v1 baseline. The submitted model is now model v2 (see `baseline/model_v2/results.md`).

These results use all 44 labeled field-years (32 Grain, 12 Silage) from 34 BARC
fields. Five-fold validation holds out fields, keeping all years of each field
together. Imputation and scaling are fitted only on training folds. The model
uses nine July–November NDVI features, default class weights, C=1, and a 0.5
Silage probability threshold. No tuning was performed against these results.

## What the model achieves

| Metric | Logistic regression | Always Grain |
| --- | ---: | ---: |
| Silage precision | 87.5% | 0% (undefined, reported as zero) |
| Silage recall | 58.3% | 0% |
| Silage F1 | 70.0% | 0% |
| Grain false positive rate | 3.125% | 0% |
| Balanced accuracy | 77.60% | 50.0% |
| Ordinary accuracy | 86.36% | 72.73% |
| Brier score, lower is better | 0.0826 | 0.2727 |

It predicts Silage eight times, seven correctly. It identifies 7 of the 12
reference Silage field-years and misses 5. This is a useful improvement over
always predicting Grain, especially in balanced accuracy. Ordinary accuracy
alone hides the majority-class advantage.

Confusion matrix, actual rows / predicted columns:

| Actual label | Grain | Silage |
| --- | ---: | ---: |
| Grain | 31 | 1 |
| Silage | 5 | 7 |

## Every error

| OBJECTID | Year | Reference | Predicted | Silage probability | Usable dates |
| --- | ---: | --- | --- | ---: | ---: |
| 24 | 2021 | Grain | Silage | 69.27% | 22 |
| 327 | 2021 | Silage | Grain | 1.12% | 12 |
| 231 | 2022 | Silage | Grain | 37.91% | 28 |
| 252 | 2022 | Silage | Grain | 32.95% | 26 |
| 254 | 2023 | Silage | Grain | 41.89% | 22 |
| 323 | 2023 | Silage | Grain | 36.58% | 12 |

Four missed Silage examples have probabilities between about 33% and 42%,
below the 50% threshold. Field 327 / 2021 is a much more confident miss and a
good first case for inspecting the NDVI trajectory, masking, acquisition gaps,
and source label provenance. No cause has been established for any error.
Two misses have only 12 usable dates, but two have 26–28: observation count
alone does not explain failure.

Lowering the threshold could recover some misses while creating more Grain
false positives. Choosing it using these held-out labels would tune to the
evaluation set. Set the desired false-positive/recall tradeoff first, then use
training-only inner grouped validation if threshold tuning is needed.

## Year-level results

| Year | Field-years | Silage found / reference | Silage F1 | Balanced accuracy |
| --- | ---: | ---: | ---: | ---: |
| 2021 | 18 | 3 / 4 | 75.0% | 83.93% |
| 2022 | 7 | 2 / 4 | 66.67% | 75.0% |
| 2023 | 19 | 2 / 4 | 66.67% | 75.0% |

These are subsets of the same held-out-field predictions. They are not
leave-one-year-out experiments: the training folds can contain other fields
from the same year. They do not establish prediction performance in a new year.

## Data quality and limits

- 205 blank labels were excluded; none were assumed to be Grain.
- All 44 labeled field-years were observed, with 12–28 usable dates each.
- 171 field-scene observations were rejected for insufficient clear pixels.
- No satellite read errors, missing final features, or unobserved field-years.
- Processing-baseline offsets were checked against Sentinel-2 product XML.
- Lower Brier error is encouraging, but it does not prove probabilities are
  well calibrated with only 12 Silage examples.

The sample is small, and nearby fields can share imagery, weather, and
management. Repeated field-years also mean the 44 rows are not 44 independent
fields. Exact-field grouping prevents repeated-field leakage but leaves those
spatial similarities. The measurements describe vegetation greenness rather
than directly observing the harvest destination.

## Recommended next experiment

First inspect the six error cases alongside correctly classified fields and
review their cached time series and source labels. Do not edit labels based
solely on model disagreement. Then test a prespecified spatial or farm-level
holdout if defensible grouping metadata supports it. More independently labeled
Silage fields would improve the strength of any evaluation. Keep the existing
baseline and predictions as the comparison point before adding features or
tuning the model.

Sources: `baseline/outputs/metrics.json`, `heldout_predictions.csv`,
`features.csv`, and `observations.csv`. The app displays these saved results.
