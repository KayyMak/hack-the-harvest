# Hack the Harvest: team submission

**What we submit:** [`forecast_v2/outputs/state_estimates_2025.csv`](forecast_v2/outputs/state_estimates_2025.csv), 2025 corn acres
harvested for grain and for silage, US total and every state, in the QuickStats columns the judges' file uses. It covers 91 of
the 92 rows in `data/reference/quickstats_2025_judges.csv`; the one row without a prediction is the "OTHER STATES" grain
aggregate, whose reference value is 0.

- Live dashboard: https://hack-the-harvest.onrender.com
- Notebook with every chart and table, already run: [`Submission/harvest_submission.ipynb`](Submission/harvest_submission.ipynb)
- The root `README.md` is the organizers' original and is kept byte-for-byte (checked against `baseline/original_sha256.json`).

The submission has two parts:

1. **The graded 2025 numbers** come from a forecast built only from USDA NASS reports released before the January 2026
   Annual Summary (`forecast_v2/estimate_2025.py`). Grain is NASS's November 14, 2025 forecast (or September 12 where
   November omits the state). Silage averages two estimates: each state's 5-year median silage shares applied to 2025
   planted and grain acres, and last year's silage acres. The method was chosen by a pre-registered rule on a 2018-2024
   backtest, never on 2025 (`forecast_v2/PREREGISTRATION.md`, `forecast_v2/results.md`). The team's first forecast
   (`forecast/`, 2022-2024 shares only) is kept for comparison.
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
| US corn for grain, 2025 | 90,047,000 vs NASS 90,948,000 acres: **-1.0%** | `forecast_v2/outputs/benchmark.json` |
| US corn for silage, 2025 | 6,507,289 vs NASS 6,187,000 acres: **+5.2%** (first forecast: +11.3%) | `forecast_v2/outputs/benchmark.json` |
| Margin of error, NASS reliability format | US silage **±7.7%** at 90% (root-mean-square error 3.9%, 2018-2024); US grain **±1.7%** (RMSE 0.9%, 2013-2024). 2025 fell inside both | `web/public/forecast_2025.json` (`reliability`), from `forecast_v2/outputs/summary.json` |
| Maryland grain, 2025 | 405,000 vs 410,000: **-1.2%** | `forecast_v2/outputs/benchmark.json` |
| Maryland silage, 2025 | 36,648 vs 40,000: **-8.4%** (first forecast: -6.0%) | `forecast_v2/outputs/benchmark.json` |
| States within 10% of NASS | grain **33 of 41**, silage **22 of 48** | `forecast_v2/outputs/compare_2025.json` |
| State error, acre-weighted | grain **1.6%**, silage **14.6%** (first forecast: 17.0%); unweighted mean grain 8.8%, silage 16.4% | `forecast_v2/outputs/compare_2025.json` |
| NASS inside our 95% range | silage **48 of 48** states, grain **38 of 41** (first forecast: 45 of 48, 32 of 41) | `forecast_v2/outputs/compare_2025.json` |
| BARC classifier, held out by field | **41 of 44** field-years right (10 of 12 silage, 1 false alarm in 32 grain), balanced accuracy **0.90** | `baseline/outputs/metrics.json` |
| Same, corrected for model selection | balanced accuracy about **0.87** (the first model, v1, scores 0.80 on the same splits) | `baseline/outputs/metrics.json` (`selection`) |

`benchmark.json` reports per-row errors only; the judges' exact scoring formula was not published to us. The margin of
error follows NASS's "Reliability" sections: Student t on n-1 degrees of freedom times the root-mean-square percent error
of the US forecast in the backtest, each year forecast with only what was known then, so 9 years in 10 the miss is no
larger (`forecast_v2/export_dashboard.py`).

## Reproduce (from the repo root)

```sh
python forecast_v2/estimate_2025.py     # submitted 2025 estimate from NASS reports before January 2026 -> forecast_v2/outputs/
python forecast_v2/backtest.py          # the 2018-2024 backtest that chose the method (no 2025 data)
python -m harvest.benchmark --predictions forecast_v2/outputs/state_estimates_2025.csv   # score against the judges' 2025 file
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
| Extra training labels (21 public BARC farm-record and Kraatz field-years, 2017-2023, never in a test fold) | no gain: balanced accuracy 0.89-0.91 vs 0.925 without them over 20 seeds, within noise, so the submitted model is unchanged | `baseline/outputs/experiments/extra_labels/results.md` |
| Forecast round 3 (three more silage methods and a grain bias correction, pre-registered before scoring) | the submitted methods still win the backtest: silage 12.7% vs 14.8-15.9%, grain 1.60% vs 1.75%; 2025 numbers unchanged | `forecast_v2/PREREGISTRATION_ROUND3.md`, `forecast_v2/results_round3.md` |
| Forecast backtest (each year 2018-2024 forecast with only what was known then) | silage: acre-weighted error 12.7% (first forecast's method 13.8%), median 10.3%, 95% range covered 94.6% of state-years; grain (2013-2024): acre-weighted 1.6%, covered 94.4% | `forecast_v2/outputs/summary.json`, `forecast_v2/results.md` |

## Limitations

- **Silage is still over-called in several states.** US silage is +5.2% and 22 of 48 states are within 10%. The largest
  over-calls are Arkansas (+73%), North Dakota (+62%), Louisiana (+57%), South Carolina (+52%), Iowa (+43%) and Kansas (+42%)
  (`forecast_v2/outputs/benchmark.json`): in 2025 those states shifted corn toward grain, which past shares cannot see before
  January. Maryland silage moved from -6.0% (first forecast) to -8.4%.
- **Ranges are honest but wide for small states.** NASS fell inside our 95% range for 48 of 48 silage and 38 of 41 grain
  states; ranges are calibrated on the 2018-2024 backtest for each release date, so they narrow only as far as history
  supports (silage accuracy does not improve from June to November; grain does).
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

## Data citation

The BARC field polygons in `BARC_Corn.2021-2023.gpkg` come from the studies below, cited as the organizers' README asks.

**Publications**

- Dulaney, W., Anderson, M., Gao, F., Stern, A., Moglen, G., Meyers, G., Daughtry, C., White, W., Akumaga, U., &
  Showalter, J. (2024). Development of a gridded yield data archive for farm management and research at the USDA
  Beltsville Agricultural Research Center. *Agrosystems, Geosciences & Environment*, 7(1), e20474.
  https://doi.org/10.1002/agg2.20474
- Kraatz, S., Lamb, B., Hively, W., Jennewein, J., Gao, F., Cosh, M., & Siqueira, P. (2023). Comparing NISAR (Using
  Sentinel-1), USDA/NASS CDL, and Ground Truth Crop/Non-Crop Areas in an Urban Agricultural Region. *Sensors*, 23(20),
  8595. https://doi.org/10.3390/s23208595

**Datasets**

- USDA Beltsville Agricultural Research Center (BARC) Gridded Yield Data Archive, version 1. USDA National Agricultural
  Library, Ag Data Commons.
  https://agdatacommons.nal.usda.gov/articles/dataset/USDA_Beltsville_Agricultural_Research_Center_BARC_Gridded_Yield_Data_Archive_version_1/28950746
- Kraatz, S. (2023). Validating NISAR's cropland mapping approach and the USDA/NASS Cropland Data Layer against ground
  truth data in a fragmented urban agricultural region (Version 1.0.0) [Data set]. Zenodo.
  https://doi.org/10.5281/zenodo.8087301

Other public sources: Sentinel-2 Level-2A (Microsoft Planetary Computer), USDA NASS Quick Stats and Crop Production
reports (URLs and checksums in `forecast/sources.json`), USDA Cropland Data Layer.

## Key files

| Path | What it is |
| --- | --- |
| `forecast_v2/outputs/state_estimates_2025.csv` | The submitted 2025 answer |
| `forecast_v2/outputs/summary.json` | Forecast method, ranges, backtest, convergence through 2025 releases |
| `forecast_v2/outputs/benchmark.json`, `compare_2025.json` | Per-row errors against the judges' 2025 NASS file, and the comparison with the first forecast |
| `forecast_v2/PREREGISTRATION.md`, `results.md` | Candidate methods and selection rule written before scoring, and the results |
| `forecast/sources.json`, `forecast/cache/` | NASS report URLs, SHA-256 checksums and cached text; the January 2026 summary is never read |
| `Submission/harvest_submission.ipynb` | Field-level analysis, run with outputs |
| `baseline/outputs/metrics.json` | Held-out classifier scores (model v2) |
| `baseline/model_v2/results.md` | Pre-registered model comparison and the selection correction |
| `baseline/outputs/estimate_2025/summary.json` | Satellite Maryland 2025 cross-check |
| `docs/HOW_TO_RUN.md`, `START_HERE.md` | Setup, API, dashboard and agent |
