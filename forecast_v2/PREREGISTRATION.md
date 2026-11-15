# forecast_v2 pre-registration

Written and committed before any backtest score was computed. Nothing below may change after the first
score is seen; any deviation will be listed in `results.md` as a deviation.

## Disclosure

The candidate list was drafted by someone who had been told the current forecast's headline 2025 errors
(US silage about +11% high, Plains states 45-70% high, state mean absolute error about 19%). No 2025 final
value, the judges' file, or `forecast/outputs/benchmark.json` is read by any code here before the winner is
fixed and committed. The choice among the candidates below is made only by the backtest rule. The user has
decided that the backtest winner is submitted even if it scores worse on 2025.

## Inputs (all committed in the repo)

- Finals, years up to 2024: `analysis/forecast_backtest/quickstats_corn_harvested_1990_2026.csv`
  (Period `YEAR`; grain and silage acres harvested by state) and
  `forecast_v2/data/quickstats_corn_planted_2005_2026.csv` (Period `YEAR`; corn planted, all purposes).
  2025 and 2026 `YEAR` rows are excluded (answer key / preliminary). Any 2026 row is excluded.
- In-season information for backtest year t (released before January of t+1):
  - grain: the latest of NOV, OCT, SEP, AUG FORECAST, JUN ACREAGE for t in the harvested file;
  - planted: the latest of OCT FORECAST, OCT ACREAGE, SEP FORECAST, AUG FORECAST, AUG ACREAGE, JUN ACREAGE
    for t in the planted file. The file has no June-or-later planted estimate before 2018, so for 2013-2017
    the only pre-January planted value is MAR ACREAGE (Prospective Plantings), which is used there.
- 2025 run: grain from the cached NASS reports in `forecast/cache/` (Nov 14 2025 Crop Production; Sep 12 2025
  for states November omits; the harvested CSV has no 2025 rows); planted from the planted file's 2025
  SEP FORECAST (else AUG FORECAST, else JUN ACREAGE). Finals for 2022-2024 come from the January 2025 Annual
  Summary (`forecast/cache/cropan25.txt`) instead of Quick Stats, because Quick Stats may hold 2024 values
  revised in the January 2026 release that carries the answer. Earlier finals come from Quick Stats.
  `cropan26` is never read.
- Backtest finals for years before t come from Quick Stats as published today. Some were revised after
  January of t (a small look-ahead that affects all candidates); this cannot be undone with these files.

## Silage candidates (6)

All use only finals for years < t and in-season values for t. If a candidate cannot produce a value for a
state-year (missing input), it uses S2 for that state-year, so every candidate is scored on the same rows.

| id | name | definition |
|---|---|---|
| S1 | D (baseline) | the current method D, run by importing `forecast/estimate_2025.py::estimate_state(method='D')` with 3 prior years: average of A = mean[silage/(planted-grain)] x (planted_t - grain_t) and C = mean[silage/planted] x planted_t |
| S2 | PERSIST | silage_t = silage_{t-1} |
| S3 | PLANTSCALE | silage_{t-1} x planted_t / planted_{t-1} |
| S4 | RATIO3 | median over t-3..t-1 of (silage/grain) x grain_t (needs a grain forecast for t) |
| S5 | BLEND_PD | (S1 + S2) / 2 |
| S6 | BLEND_PR | (S2 + S4) / 2 |

Simplicity order for ties (simplest first): S2, S3, S4, S1, S6, S5.

## Grain candidates (2)

| id | name | definition |
|---|---|---|
| G1 | NASS | the latest pre-January NASS grain forecast for t, as is |
| G2 | NASS_BC | G1 x median over the state's years 2012..t-1 of (final / forecast of the same Period as the one G1 uses for t, e.g. NOV FORECAST); used only when the state has at least 3 such years, otherwise G1. US: the same rule on the US rows |

## Backtest years, rows and metric

- Silage, primary window: **2018-2024** (7 years), the years where the planted file has a June-or-later
  planted estimate, the same kind of information the 2025 run has. Robustness window (reported, not used to
  select): 2013-2024 with March planted intentions for 2013-2017.
- Grain: **2013-2024** (G2 differs from G1 only from 2015, once 3 prior years exist).
- Scored rows: state-years with a positive final for t; silage also needs a final for t-1 (so S2 exists).
- Primary metric: acre-weighted mean absolute % error, 100 x sum|est - truth| / sum truth, pooled over the
  window's state-years.
- Why 2018-2024 and not the brief's example of 2013-2024: before 2018 the planted file's only pre-January
  planted value is the March intention, a weaker input than the 2025 run has, which would handicap S1, S3
  and S5 for reasons that do not apply in 2025. 2013-2024 is still reported.
- First-print check (reported, never used to select): the six silage candidates are rerun for t = 2023 and
  t = 2024 with priors as printed in January of t (`cropan23` for 2023, `cropan24` for 2024) and first-print
  truth (`cropan24`'s 2023 column, `cropan25`'s 2024 column), which is how the 2025 run works. Quick Stats
  t-1 finals include revisions released with t's first print, which favours the t-1-anchored candidates (S2,
  S3, S5, S6). If the ranking differs there, it is reported as a caveat and the winner does not change.
- Also reported (not used to select): median and mean absolute % error, share of state-years within 10%,
  US-total % error by year, and interval coverage.

## Selection rule

- Silage: the candidate with the lowest primary-window acre-weighted MAPE wins. If a simpler candidate (order
  above) is within 0.20 percentage points of the lowest, the simplest such candidate wins.
- Grain: G2 wins only if its acre-weighted MAPE is lower than G1's by at least 0.05 percentage points;
  otherwise G1.
- The winner is committed before the 2025 score is computed. The 2025 score is computed once with
  `python -m harvest.benchmark --predictions forecast_v2/outputs/state_estimates_2025.csv --out forecast_v2/outputs/benchmark.json`.

## Intervals (fixed now)

- Per row: se = est x RMS relative error, (truth - est) / est, of the winner's primary-window backtest rows
  (silage 2018-2024, grain 2013-2024) in the same size class (silage est < 20,000 / 20,000-100,000 /
  >= 100,000 acres; grain est < 500,000 / 500,000-2,000,000 / >= 2,000,000 acres). z = the 95th percentile of
  |truth - est| / se over those rows (at least 1.96), one z per crop. Range = [max(0, est - z se), est + z se].
- `covered_by_95_interval` in `summary.json` is the leave-one-year-out coverage: for each backtest year, the
  RMS and z are refit on the other years and applied to the held-out year. In-sample coverage is also listed.
- US: se = est x RMS of the winner's backtest US-total relative errors; range = est +/- z se with the same z.

## Amendment 1 (2026-11-15 04:37): ranges per as-of release

Added at the user's request after the winner was fixed (commit 5deadd5) and after the November-vintage
interval above had been computed. No 2025 final or judges' data had been read. The winner (S5 silage, G1
grain) does not change; only how ranges are built for each as-of date. This rule replaces the "US" line
above, for every date including November.

- As-of releases (the dates of the current `convergence` list), with the in-season inputs a backtest year t
  had at the same point (each falls back to the earlier release when a state is missing):
  - JUN (June Acreage): grain JUN ACREAGE; planted JUN ACREAGE (MAR ACREAGE where none);
  - AUG (Aug Crop Production): grain AUG FORECAST; planted AUG FORECAST or AUG ACREAGE;
  - SEP (Sep Crop Production): grain SEP FORECAST; planted SEP FORECAST;
  - NOV (Nov Crop Production): grain NOV, else OCT FORECAST; planted OCT FORECAST or OCT ACREAGE
    (this is the main backtest above).
- For each as-of release separately, the winner is run on the backtest years with that release's inputs
  (silage 2018-2024, grain 2013-2024, as above), and the state-level rule above (size-class RMS and one z,
  95th percentile of |error| / se, at least 1.96) is fitted on that release's errors only.
- US level, per release: se = est x RMS of that release's backtest US relative errors (silage: sum of the
  scored states; grain: NASS's US row). With only n = 7 (silage) or up to 12 (grain) years, the 95% range
  is est +/- t(0.975, n - 1) x se (Student t, e.g. 2.447 for n = 7), not a percentile.
- Reported per release: state-level coverage (in-sample and leave-one-year-out), how many backtest years'
  US totals fall inside the US range, and the 2025 US silage range width next to the current forecast's.
- The band narrows from June to November only as far as these backtest errors do; nothing forces it.

## Outputs

`forecast_v2/outputs/state_estimates_2025.csv` has the same headers and the same state x item rows as
`forecast/outputs/state_estimates_2025.csv`; `forecast_v2/outputs/summary.json` follows the schema of
`forecast/outputs/summary.json`.
