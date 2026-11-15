# Experiment: extra public BARC harvest labels for model v2

**Verdict: the extra labels do not help.** Harvest-record extras lower mean balanced accuracy by
0.034, about one field-year per split. All extras lower it by 0.016. Both differences are inside
row-sampling noise: the field-bootstrap 95% intervals include 0. The submitted model and its
outputs are unchanged.

Code: `baseline/experiments/extra_labels/extract_extra.py` (Sentinel-2 pull) and
`run_experiment.py` (CV). Full numbers, including all per-seed scores: `results.json`.
Labels: `data/extra_labels/` (see its README for sources).

## Method

- **Test rows.** Only the 44 official labeled field-years (32 Grain, 12 Silage). The outer splits
  are the saved v2 ones: 5-fold `StratifiedGroupKFold` by OBJECTID over the 44 rows. Main seeds are
  0-19 (the v2 selection seeds), seed 42 is the saved split, and seeds 0-99 are a sensitivity check.
- **Training rows.**
  - For each outer fold: the official training rows plus extra rows.
  - Every extra row (any year) of a field in the test fold is removed. The code asserts this.
  - Extra rows whose (field, year) is one of the 44 official field-years are dropped. There are
    none: the CSV keeps those as `test_official`.
- **Model.** The unchanged v2 code path (`model_v2/experiment.fit`, candidate H):
  - the 9 NDVI and 4 timing features, computed by the same `features.py` functions;
  - training-fold median imputation and scaling;
  - L1 logistic regression, with C chosen by field-grouped inner CV on the training rows.
- **Reproduction check.** Condition (a) reproduces the saved v2 per-seed balanced accuracy
  exactly for all 21 seeds, including seed 42 = 0.901 (10/12 silage, 1/32 false alarms).
- **Series.**
  - 2021-2023 extras: the existing `baseline/cache_unlabeled` series.
  - 2017-2020 extras: pulled into `baseline/cache_extra` with the unchanged `run_baseline.extract` recipe:
    - Planetary Computer `sentinel-2-l2a`, Jul 1-Nov 30, scene cloud below 40%;
    - SCL mask;
    - reflectance offset from the STAC metadata or the processing baseline. Every 2017-2020 scene
      is baseline 2.12, so the offset is 0.
  - All 15 pulls succeeded with 0 read errors and 22-31 clear dates each. The official rows have
    12-28 clear dates.

## Extra rows used

| year | Grain (harvest rec.) | Silage (harvest rec.) | Grain (planting rec.) | Silage (planting rec.) |
|---|---|---|---|---|
| 2017 | 0 | 0 | 0 | 1 |
| 2018 | 1 | 1 | 2 | 1 |
| 2019 | 3 | 1 | 0 | 0 |
| 2020 | 0 | 2 | 2 | 1 |
| 2021 | 3 | 1 | 0 | 0 |
| 2022 | 1 | 0 | 0 | 0 |
| 2023 | 1 | 0 | 0 | 0 |
| **total** | **9** | **5** | **4** | **3** |

- (b) uses the 14 harvest-record rows (9 Grain, 5 Silage).
- (c) uses all 21 rows (13 Grain, 8 Silage).
- Per training fold, (b) adds 10-14 rows and (c) adds 16-21, after the test-field exclusion.
  Five extra fields (230, 231, 238, 248, 251) also have official rows, so they are excluded
  whenever those fields are tested.

**Skipped:** 35/2015, 235/2015 and 248/2015 (all Grain, harvest records). Extraction for 2015
was not attempted, per the plan. No 2017-2023 row was skipped.

## Results (held out on the 44 official field-years)

| condition | mean BA ± sd (seeds 0-19) | silage hits /12, mean (range) | grain false alarms /32, mean (range) | paired ΔBA vs (a), mean ± sd [range] | seeds better/worse/tied | field-bootstrap ΔBA 95% CI | seed 42 BA (silage, FA) |
|---|---|---|---|---|---|---|---|
| (a) v2, no extras | 0.925 ± 0.022 | 10.75 (10-11) | 1.45 (0-3) | — | — | — | 0.901 (10/12, 1/32) |
| (b) + harvest-record extras | 0.891 ± 0.033 | 10.10 (8-11) | 1.90 (1-4) | −0.034 ± 0.028 [−0.099, 0.000] | 0/16/4 | [−0.165, +0.050] | 0.901 (10/12, 1/32) |
| (c) + all extras | 0.910 ± 0.014 | 10.90 (10-11) | 2.85 (2-4) | −0.016 ± 0.020 [−0.047, +0.042] | 3/16/1 | [−0.071, +0.067] | 0.911 (11/12, 3/32) |
| *post hoc:* (b) with peak filter | 0.890 ± 0.043 | 10.05 (8-11) | 1.85 (1-5) | −0.035 ± 0.041 [−0.130, +0.026] | 1/13/6 | [−0.193, +0.070] | 0.885 (10/12, 2/32) |
| *post hoc:* (c) with peak filter | 0.919 ± 0.020 | 10.90 (10-11) | 2.25 (0-5) | −0.006 ± 0.018 [−0.047, +0.031] | 4/10/6 | [−0.071, +0.071] | 0.943 (11/12, 1/32) |

**Seeds 0-99 (sensitivity):**

| condition | mean BA | mean ΔBA vs (a) | seeds better/worse |
|---|---|---|---|
| (a) | 0.919 | — | — |
| (b) | 0.894 | −0.025 | 17/63 |
| (c) | 0.909 | −0.010 | 26/64 |
| (b) with peak filter | 0.890 | −0.029 | 14/63 |
| (c) with peak filter | 0.922 | +0.003 | 32/39 |

**Why seed 42 differs from the seeds 0-19 mean.** Seed 42 is the one saved split: it gives 0.901
and 10/12. The 0.925 mean is the average over 20 fresh splits of the same 44 rows. The baseline
has not moved.

**Scale of a field-year.** One silage field-year is 1/24 = 0.042 BA; one grain field-year is
1/64 = 0.016 BA. So (b)'s −0.034 is about one field-year per split:

- 0.65 fewer silage hits and 0.45 more false alarms on average;
- mostly 323/2023 (Silage), called silage in 100% of splits under (a) but 35% under (b).

(c) gains 0.15 silage hits but adds 1.4 grain false alarms per split: 24/2021 rises from 30% to
100% silage calls, and 1/2021 from 20% to 75%.

**Peak filter.** This sensitivity was added after seeing results and is label-blind. In each fold,
it drops extras whose peak NDVI is below the lowest peak among that fold's official training rows
(0.781-0.788). It always removes 235/2018 (peak 0.48) and 235/2019 (0.44). It removes 230/2020
(0.784) only in the 20 of 100 folds where the 0.781 official row is in the test fold. It does not
change the verdict.

## Noise and verdict

**Seed spread.** Seeds re-split the same 44 rows; they are not independent replicates. "16 of 20
seeds worse" shows a consistent direction, not significance.

**Field bootstrap.** It resamples official fields over the pooled held-out calls (500 draws per
seed, no refits). It is the better noise yardstick, and every interval includes 0.

**Verdict:**

- Harvest-record extras hurt by about 0.03 BA (one field-year), within noise.
- All extras hurt by about 0.016, within noise.
- Neither is an improvement, and nothing here argues for changing the submitted model.

## Caveats

- **Polygons.** 2017-2020 series use the 2021-2023 GeoPackage polygons; field boundaries are
  assumed unchanged.
- **Non-corn-looking series.**
  - 235/2018 (Silage, planting record) and 235/2019 (Grain, Kraatz harvest record) never exceed
    about 0.48 NDVI.
  - 238/2017 has its highest NDVI in mid-November (doy 321); this looks like regrowth after a
    harvest by early October.
  - 271/2018 is low in July.
  - These may be polygon or OBJECTID mismatches in earlier years, or simply weak records. They were
    not pruned from (b) or (c), so (b) is not free of label noise.
- **Planting-record labels** (7 rows) give intended use at planting, not what was harvested.
- **Inner-CV C.** C is chosen on pooled official and extra training rows, so the extras also move
  C. It differs from (a) in 47% of folds for (b) and 68% for (c), and (c) favours smaller C:
  mean log10 C is −0.28 vs +0.18 for (a).
- **Bootstrap scope.** The bootstrap reuses each seed's held-out calls (no refits). It ignores
  which extras were drawn.
- **Sample size.** 14-21 extra rows on top of 35 training rows per fold is small. A null or
  negative result here does not rule out benefit from many more labels.
