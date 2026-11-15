# Measured BARC results: model v2

All predictions below are held out by field: five stratified group folds, 34 field groups, seed 42. All years of a field share one fold. Imputation, scaling, and model fitting occur inside each training fold.

Model v2: Logistic regression on NDVI and harvest-timing features (L1). The nine NDVI features plus four harvest-timing features (decline_doy, drop_doy, drop_size, regrowth); L1 logistic regression with C chosen by field-grouped inner CV inside each training fold (C by fold: [1.0, 1.0, 10.0, 1.0, 1.0]); threshold 0.5. It is candidate H of the pre-registered experiment in ../model_v2/results.md. The v1 model (nine NDVI features, C = 1) is kept as a backup: v1_backup/.

| Metric | Model v2 | Always Grain |
| --- | ---: | ---: |
| Silage precision | 0.9091 | 0.0000 |
| Silage recall | 0.8333 | 0.0000 |
| Silage F1 | 0.8696 | 0.0000 |
| False positive rate | 0.0312 | 0.0000 |
| Balanced accuracy | 0.9010 | 0.5000 |
| Brier score (lower is better) | 0.0649 | 0.2727 |

Silage is the positive class. For the always-Grain predictor, precision has a zero denominator and is reported as 0 by convention.

## Confusion matrices

Rows are reference labels; columns are predictions.

| Model v2 | Predicted Grain | Predicted Silage |
| --- | ---: | ---: |
| True Grain | 31 | 1 |
| True Silage | 2 | 10 |

| Always Grain | Predicted Grain | Predicted Silage |
| --- | ---: | ---: |
| True Grain | 32 | 0 |
| True Silage | 12 | 0 |

## By year, using the same held-out predictions

| Year | n | Silage precision | Recall | F1 | FPR | Balanced accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2021 | 18 | 1.0000 | 0.5000 | 0.6667 | 0.0000 | 0.7500 |
| 2022 | 7 | 0.8000 | 1.0000 | 0.8889 | 0.3333 | 0.8333 |
| 2023 | 19 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 |

The always-Grain balanced accuracy is 0.5 in every year; its Silage precision, recall, F1, and false positive rate are 0.

## Missing data and failures

- 44 labeled field-years, of which 44 were evaluated and 0 excluded for no usable dates.
- 205 blank source labels excluded before any supervised processing.
- 1322 field-scene records, 1151 accepted and 171 rejected for insufficient clear pixels.
- 0 read errors. Read errors are separate from cloud/nodata rejections.
- 833 usable field-dates after duplicate-date aggregation; 12–28 per field-year.
- 0 missing final feature cells out of 572. Missingness is preserved until fold-level imputation.
- No feature was entirely missing in a training fold.

The pilot was field 1 / 2021: 27 candidate scenes, 23 usable dates, 3 rejected scene observations, no read failures, and 667 polygon-center pixels. The full extraction started only after this gate passed. The four observed processing baselines were checked against product XML (calibration_verification.json).

The original machine lacked the analysis packages. A local Python 3.12.10 environment resolved this. Network access required sandbox approval; all requested satellite reads then completed successfully.

## Interpretation

Model v2 identifies 10 of 12 Silage examples while misclassifying 1 of 32 Grain examples (balanced accuracy 0.901, Brier 0.065). On the same split v1 identified 7 of 12 and misclassified 1 of 32 (balanced accuracy 0.776, Brier 0.083).

How much to trust the gain:

- This seed-42 split was already seen when model v2 was chosen, so the numbers above are optimistic. Model v2 won a pre-registered comparison of eight candidates on 20 fresh field-grouped splits.
- Repeating the whole selection inside each training fold (nested) gives a mean balanced accuracy of about 0.87, against 0.80 for v1 on the same splits: the honest estimate.
- A field-level bootstrap 95% interval for the balanced-accuracy gain over v1 is [0.000, 0.285]: it touches zero. The gain rests on 3-4 silage field-years.
- The sample is small (44 field-years, 34 fields) and all fields are near BARC; nearby fields share imagery and management. Field grouping does not demonstrate transfer to other regions or future years.
- drop_size is the largest NDVI fall between consecutive clear looks, so it grows with the gap between looks; it may shift where cloud gaps differ from those at BARC.

See ../README.md for methods, package requirements, CRS checks, references, and commands. Numerical predictions, split IDs, and metrics are saved alongside this file.
