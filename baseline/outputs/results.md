# Measured BARC baseline results

All predictions below are held out by field: five stratified group folds, 34 field groups, seed 42. All years of a field share one fold. Imputation, scaling, and model fitting occur inside each training fold.

| Metric | Logistic regression | Always Grain |
| --- | ---: | ---: |
| Silage precision | 0.8750 | 0.0000 |
| Silage recall | 0.5833 | 0.0000 |
| Silage F1 | 0.7000 | 0.0000 |
| False positive rate | 0.0312 | 0.0000 |
| Balanced accuracy | 0.7760 | 0.5000 |
| Brier score (lower is better) | 0.0826 | 0.2727 |

Silage is the positive class. For the always-Grain predictor, precision has a zero denominator and is reported as 0 by convention.

## Confusion matrices

Rows are reference labels; columns are predictions.

| Logistic regression | Predicted Grain | Predicted Silage |
| --- | ---: | ---: |
| True Grain | 31 | 1 |
| True Silage | 5 | 7 |

| Always Grain | Predicted Grain | Predicted Silage |
| --- | ---: | ---: |
| True Grain | 32 | 0 |
| True Silage | 12 | 0 |

## By year, using the same held-out predictions

| Year | n | Silage precision | Recall | F1 | FPR | Balanced accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2021 | 18 | 0.7500 | 0.7500 | 0.7500 | 0.0714 | 0.8393 |
| 2022 | 7 | 1.0000 | 0.5000 | 0.6667 | 0.0000 | 0.7500 |
| 2023 | 19 | 1.0000 | 0.5000 | 0.6667 | 0.0000 | 0.7500 |

The always-Grain balanced accuracy is 0.5 in every year; its Silage precision, recall, F1, and false positive rate are 0.

## Missing data and failures

- 44 labeled field-years, of which 44 were evaluated and 0 excluded for no usable dates.
- 205 blank source labels excluded before any supervised processing.
- 1322 field-scene records, 1151 accepted and 171 rejected for insufficient clear pixels.
- 0 read errors. Read errors are separate from cloud/nodata rejections.
- 833 usable field-dates after duplicate-date aggregation; 12–28 per field-year.
- 0 missing final feature cells out of 396. Missingness is preserved until fold-level imputation.
- No feature was entirely missing in a training fold.

The pilot was field 1 / 2021: 27 candidate scenes, 23 usable dates, 3 rejected scene observations, no read failures, and 667 polygon-center pixels. The full extraction started only after this gate passed. The four observed processing baselines were checked against product XML (calibration_verification.json).

The original machine lacked the analysis packages. A local Python 3.12.10 environment resolved this. Network access required sandbox approval; all requested satellite reads then completed successfully.

## Interpretation

The model identifies 7 of 12 Silage examples while misclassifying 1 of 32 Grain examples. The improvement over always-Grain is useful for an initial baseline, but five missed Silage examples remain. The sample is small and all fields are near BARC. Nearby fields can share imagery and management. Field grouping does not demonstrate transfer to other regions or future years. No tuning or threshold selection was performed using held-out predictions.

See ../README.md for methods, package requirements, CRS checks, references, and commands. Numerical predictions, split IDs, and metrics are saved alongside this file.
