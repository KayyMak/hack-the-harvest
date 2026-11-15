# Hack the Harvest: team submission

**What we submit:** [`forecast/outputs/state_estimates_2025.csv`](forecast/outputs/state_estimates_2025.csv), 2025 corn acres
harvested for grain and for silage, US total and every state, in the QuickStats columns the judges' file uses. It covers 91 of
the 92 rows in `data/reference/quickstats_2025_judges.csv`; the one row without a prediction is the "OTHER STATES" grain
aggregate, whose reference value is 0.

- Live dashboard: https://hack-the-harvest.onrender.com
- Notebook with every chart and table, already run: [`Submission/harvest_submission.ipynb`](Submission/harvest_submission.ipynb)
- The root `README.md` is the organizers' original and is kept byte-for-byte (checked against `baseline/original_sha256.json`).

The submission has two parts:

1. **The graded 2025 numbers** come from a forecast built only from USDA NASS reports released before the January 2026
   Annual Summary (`forecast/estimate_2025.py`). Grain is NASS's November 14, 2025 forecast (or September 12 where November
   omits the state). Silage averages two 2022-2024 state shares applied to 2025 acres (silage as a share of the corn not
   harvested for grain, and as a share of planted corn); that blend had the lowest error on the 2023-2024 backtest.
2. **The field-level question**, silage or grain for each BARC field, is answered by a small satellite classifier
   validated on the 44 labeled BARC field-years (`baseline/`, documented in the notebook).

## Hypothesis

From the notebook's `## Hypothesis`: **silage corn is chopped green in late summer**, so its NDVI falls sharply between two
clear looks around late August to September and stays low. **Grain corn dries down standing**, so its NDVI fades gradually
into October and November. Monthly NDVI medians from July to November should therefore separate the two classes, with
September carrying most of the signal. A second hypothesis, that grain leaves more crop residue (Sentinel-2 SWIR tillage
index), was **not tested**: the index was not extracted in time.

## Headline results

| Result | Value | Source |
| --- | --- | --- |
| US corn for grain, 2025 | 90,047,000 vs NASS 90,948,000 acres: **-1.0%** | `forecast/outputs/benchmark.json` |
| US corn for silage, 2025 | 6,886,596 vs NASS 6,187,000 acres: **+11.3%** | `forecast/outputs/benchmark.json` |
| Maryland grain, 2025 | 405,000 vs 410,000: **-1.2%** | `forecast/outputs/benchmark.json` |
| Maryland silage, 2025 | 37,595 vs 40,000: **-6.0%** | `forecast/outputs/benchmark.json` |
| States within 10% of NASS | grain **33 of 41**, silage **23 of 48** | counted from the per-row errors in `forecast/outputs/benchmark.json` |
| BARC classifier, held out by field | **41 of 44** field-years right (10 of 12 silage, 1 false alarm in 32 grain), balanced accuracy **0.90** | `baseline/outputs/metrics.json` |
| Same, corrected for model selection | balanced accuracy about **0.87** (the first model, v1, scores 0.80 on the same splits) | `baseline/outputs/metrics.json` (`selection`) |

`benchmark.json` reports per-row errors only; the judges' exact scoring formula was not published to us.

## Reproduce (from the repo root)

```sh
python forecast/estimate_2025.py        # 2025 estimate from cached NASS reports -> forecast/outputs/ (standard library only)
python -m harvest.benchmark --predictions forecast/outputs/state_estimates_2025.csv   # score against the judges' 2025 file
python -m harvest.run --year 2022 --as-of 2022-10-12 --out runs/2022-10-12            # BARC field calls, scores, acres as of a date
```

`harvest.benchmark` and `harvest.run` need `pydantic`; `harvest.run` also needs `scikit-learn` for dates before November 30.
Setup and the API and dashboard commands are in `START_HERE.md` and `docs/HOW_TO_RUN.md`. Classifier outputs are rebuilt
offline from versioned caches with `python baseline/run_baseline.py evaluate`.

## Validation

Every classifier split fits imputation and scaling on training rows only and is compared against always-Grain (balanced
accuracy 0.5) on the same rows. The field, spatial-block and farm splits, and the strict year split, keep every year of a
field on one side; the plain year split does not (a test-year field's other seasons can be in training). The last row is
the forecast's backtest, not a classifier split.

| Held out by | Result | Source |
| --- | --- | --- |
| Field (5-fold, grouped by field) | balanced accuracy 0.90; about 0.87 after correcting for model selection | `baseline/outputs/metrics.json` |
| Year (train on two seasons, test the third) | mean balanced accuracy 0.88; 0.77 when fields seen in the test year are also dropped from training | notebook section 4 |
| Spatial blocks (k-means blocks of field centroids, k = 4, 5, 6; model v1) | balanced accuracy 0.76 to 0.78, against 0.78 for v1 held out by field | `baseline/outputs/spatial_holdout.json` |
| Farm (train on the other farms) | **fails for silage**: Central Farm has 11 of the 12 silage field-years; holding it out leaves one silage example to train on, and none of its 11 silage fields is found (balanced accuracy 0.5) | notebook section 4 |
| Organizers' decline-date rule, same rows | rule: balanced accuracy 0.69 (11 of 12 silage, but 17 of 32 grain flagged); model: 0.90 | `baseline/outputs/decline_rule/metrics.json` |
| Forecast backtest (same method on 2023 and 2024) | median absolute error grain 0.5%, silage 11.5% per state-year; 95% interval covered 95.1% (grain) and 95.8% (silage) | `forecast/outputs/summary.json` |

## Limitations

- **Silage is over-called in many states.** US silage is +11.3%, and only 23 of 48 states are within 10%. The largest
  over-calls are Arkansas (+96%), Louisiana (+78%), North Dakota (+69%), South Carolina (+68%), Iowa (+56%), Kansas (+54%),
  Oklahoma (+51%) and South Dakota (+46%) (`forecast/outputs/benchmark.json`).
- **The 2025 grain interval was too narrow.** NASS grain fell inside our 95% interval in 32 of 41 states; silage in 45 of 48
  (counted from `forecast/outputs/summary.json` against `forecast/outputs/benchmark.json`). The intervals were scaled on the
  2023-2024 backtest.
- **One farm of training data.** The classifier learned from 44 field-years on 34 fields at BARC, 12 of them silage, so every
  rate has wide uncertainty. The model-selection gain over v1 has a bootstrap 95% interval of 0.00 to 0.28, which touches zero.
- **The satellite check does not transfer well.** Applied to a 1,500-field sample of Maryland's 2025 corn, the classifier
  puts silage at 55,743 acres against NASS 40,000 (**+39%**) and grain at -5.8% (`baseline/outputs/estimate_2025/summary.json`).
  It is a cross-check, not the answer.
- **Other administrative data.** RMA crop-insurance acreage was not used. FSA December acreage was tried as a silage method
  and lost the 2023-2024 backtest: acre-weighted absolute error 13.27% for the FSA method and 11.19% for the FSA blend,
  against 10.49% for the chosen NASS-only method (`forecast/outputs/summary.json`, `silage_method`).
- **NDVI only.** The residue index (second hypothesis) and double-crop handling are not in the model.
- **Thresholds reflect Maryland timing.** Early harvest is not always silage elsewhere, for example summer grain in Texas.

## Key files

| Path | What it is |
| --- | --- |
| `forecast/outputs/state_estimates_2025.csv` | The submitted 2025 answer |
| `forecast/outputs/summary.json` | Forecast method, intervals, backtest, convergence through 2025 releases |
| `forecast/outputs/benchmark.json` | Per-row errors against the judges' 2025 NASS file |
| `forecast/sources.json`, `forecast/cache/` | NASS report URLs, SHA-256 checksums and cached text; the January 2026 summary is never read |
| `Submission/harvest_submission.ipynb` | Field-level analysis, run with outputs |
| `baseline/outputs/metrics.json` | Held-out classifier scores (model v2) |
| `baseline/model_v2/results.md` | Pre-registered model comparison and the selection correction |
| `baseline/outputs/estimate_2025/summary.json` | Satellite Maryland 2025 cross-check |
| `docs/HOW_TO_RUN.md`, `START_HERE.md` | Setup, API, dashboard and agent |
