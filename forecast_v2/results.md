# forecast_v2: results

A pre-registered rerun of the 2025 state forecast, mainly for corn-for-silage acres harvested. It is not
adopted anywhere. Kyle decides. `forecast/` is unchanged.

## What was fixed in advance, and in what order (git proves the order)

| commit | what |
|---|---|
| `894096a` | `PREREGISTRATION.md`: 6 silage + 2 grain candidates, windows, metric, selection rule, interval rule. Planted file added without its 2025 `YEAR` rows |
| `5deadd5` | backtest run and winner fixed: silage **S5**, grain **G1** |
| `5fdd6da` | amendment 1, at the user's request: a separate range for each as-of release, plus a US rule |
| `c3262cf` | 2025 estimates committed, not yet scored |
| `6c25b5a` | 2025 scored once (`outputs/benchmark.json`), compared with the current forecast |

Candidates. Every one uses only finals for years before t, plus NASS in-season values for t.

- **S1, D (the current method):** imported from `forecast/estimate_2025.py`.
- **S2, PERSIST:** last year's silage.
- **S3, PLANTSCALE:** last year's silage × planted_t / planted_{t-1}.
- **S4, RATIO3:** the 3-year median of silage/grain × grain_t.
- **S5, BLEND_PD:** (D + PERSIST) / 2.
- **S6, BLEND_PR:** (PERSIST + RATIO3) / 2.
- **G1:** NASS's latest pre-January grain forecast as is.
- **G2:** G1 × the state's median final/forecast ratio.

The rule: the lowest acre-weighted mean absolute % error (MAPE) over the window wins, and the simplest candidate within 0.20 pp is preferred. G2 had to beat G1 by at least 0.05 pp.

S1 inside this harness reproduces all 48 of the current forecast's 2025 silage values exactly (MD 37,595). This
is checked by `test_forecast_v2.py`.

**Deviations, stated plainly**
- **Window.** The selection window is 2018–2024, not the brief's example of 2013–2024. Before 2018, the planted file's only pre-January planted figure is the March intention. **The window choice changed the winner.** S5 has the lowest error on both windows, but on 2013–2024 S6 (14.53) is within 0.20 pp of S5 (14.46). S6 ranks simpler in the pre-registered order, so the rule applied to 2013–2024 would have picked S6. S6 was not scored on 2025 (the score was computed once, for S5). It can be scored on request, labelled post hoc.
- **Late amendment.** Amendment 1 came after the winner was fixed and after the November interval had been computed. It changes only the ranges, not the estimates. Its silage calibration also uses 2018–2024, not the 2013–2024 the user suggested.
- **Disclosure.** The candidate list was drafted knowing the current forecast's 2025 headline errors (from the brief). Shrinkage toward regional shares and longer or median windows were not among the candidates, so they are untested.

## Backtest: silage (state-years with a final for t and t-1)

| candidate | acre-wtd MAPE 2018–24 (n=336) | median APE | mean APE | within 10% | acre-wtd 2013–24 (n=576) | first-print check 2023–24 (n=96) |
|---|---|---|---|---|---|---|
| S1 D (current) | 13.78 | 12.4 | 17.7 | 46% | 16.38 | **10.65** |
| S2 PERSIST | 14.81 | **10.3** | 16.5 | **50%** | 15.18 | 13.19 |
| S3 PLANTSCALE | 16.23 | 12.8 | 18.6 | 41% | 16.18 | 14.79 |
| S4 RATIO3 | 16.92 | 15.0 | 20.1 | 38% | 17.39 | 15.64 |
| **S5 (D + PERSIST)/2** | **13.30** | 10.6 | **15.8** | 49% | **14.46** | 10.73 |
| S6 (PERSIST + RATIO3)/2 | 14.23 | 12.6 | 16.8 | 46% | 14.53 | 12.41 |

**Winner: S5.** Its acre-weighted MAPE is 0.48 pp below D's, and no simpler candidate is within 0.20 pp.

- **The win is narrow.** On the first-print check (priors as printed in January of t, and first-print truth, which is how the 2025 run works), D is marginally ahead: 10.65 vs 10.73. By the pre-registered rule, that check does not change the winner.
- **The silage-to-grain ratio is the worst candidate.** It scores worst on every window.
- **Coverage.** S5's 95% state range covers 95.2% of the backtest state-years in sample and 94.6% leave-one-year-out (z = 2.05). The range is wider for small states: the relative RMS is 28.9% under 20k acres, 21.8% at 20–100k and 20.4% at 100k and over.
- **US totals.** The backtest US silage error, sum of states, was within ±7.3% in all 7 years (RMS 4.3%).

## Backtest: grain (2013–2024, n=483 state-years)

| candidate | acre-wtd MAPE | median APE | mean APE | within 10% |
|---|---|---|---|---|
| **G1 NASS as is** | **1.60** | **2.31** | **6.14** | **82.2%** |
| G2 bias-corrected | 1.71 | 2.59 | 6.56 | 80.7% |

**Winner: G1.** The bias correction makes the forecast worse, so the 2025 grain values are identical to the current forecast's.

- **Coverage.** G1's 95% range covers 95.0% in sample and 94.4% leave-one-year-out (z = 2.27).
- **The range depends on state size.** The relative RMS is 14.4% under 500k acres, 5.1% at 500k–2M and 2.4% at 2M and over. The small-state class pools states whose latest forecast is June or September, so Maryland's grain range (273k–537k) is much wider than the current forecast's (Maryland's own Nov→final RMS is about 4.6%). This was pre-registered, so it was left as is.

## Ranges per as-of release (amendment 1)

Each release is re-run on the backtest with only what was known at that date. US range = est ± t(0.975, n−1) ×
est × RMS of that release's backtest US errors. Silage uses n = 7 years and grain up to 12.

| release | silage acre-wtd MAPE | silage state coverage (LOYO) | US silage ± | grain acre-wtd MAPE | grain state coverage (LOYO) | US grain ± |
|---|---|---|---|---|---|---|
| Jun Acreage | 13.34 | 94.9% | 9.37% | 3.58 | 94.2% | 3.86% |
| Aug Crop Prod. | 13.28 | 94.6% | 9.87% | 3.09 | 94.6% | 3.33% |
| Sep Crop Prod. | 13.39 | 94.6% | 10.92% | 2.60 | 94.8% | 2.66% |
| Nov Crop Prod. | 13.30 | 94.6% | 10.44% | 1.60 | 94.4% | 1.98% |

All 7 backtest years' US silage totals fall inside the US range at every release, both in sample and leave-one-year-out.
This is weak evidence: a t multiplier on 7 points almost guarantees it. For grain, 10/11, 11/12, 11/12 and 11/12 of the years fall inside leave-one-year-out.

**The silage band does not narrow through the season, and it should not.** Silage accuracy in the backtest is
flat at about 13.3% from June to November. The later grain and planted numbers do not improve the silage
estimate, so the US silage band stays at about ±10% and the small rise from June to September is noise. Grain
narrows as it should, from ±3.9% to ±2.0%. The 2025 US silage band at each date:

| as of | forecast_v2 estimate | forecast_v2 95% range | current estimate | current range |
|---|---|---|---|---|
| 2025-06-30 | 6,402,972 | 5,802,716 – 7,003,228 (±9.4%) | 6,705,944 | 5,452,647 – 7,959,241 (±18.7%) |
| 2025-08-12 | 6,442,660 | 5,806,454 – 7,078,867 (±9.9%) | 6,785,321 | 5,505,046 – 8,065,596 (±18.9%) |
| 2025-09-12 | 6,493,298 | 5,783,914 – 7,202,682 (±10.9%) | 6,886,596 | 5,585,674 – 8,187,519 (±18.9%) |
| 2025-11-14 | 6,493,298 | 5,815,462 – 7,171,134 (±10.4%) | 6,886,596 | 5,585,674 – 8,187,519 (±18.9%) |

Per-state ranges for each date are in `outputs/convergence_by_state_2025.csv`.

## 2025 score (computed once, after the commits above)

| | current (`forecast/`) | forecast_v2 |
|---|---|---|
| US silage | +11.31% | **+4.95%** |
| US grain | −0.99% | −0.99% (identical) |
| Maryland silage | **−6.01%** (37,595) | −9.26% (36,297) |
| Maryland grain | −1.22% | −1.22% |
| states within 10%, silage | 23 / 48 | 24 / 48 |
| states within 10%, grain | 33 / 41 | 33 / 41 |
| state mean abs % error, silage | 19.0% | **16.4%** |
| state mean abs % error, grain | 8.8% | 8.8% |
| state median abs % error, silage | 10.3% | 10.5% |
| acre-weighted state error, silage | 17.0% | **15.6%** |
| silage truths inside the 95% range | 45 / 48 | 48 / 48 |
| grain truths inside the 95% range | 32 / 41 | 38 / 41 |

Plains silage, current vs v2:

| state | current | v2 |
|---|---|---|
| North Dakota | +69% | +61% |
| Kansas | +54% | +45% |
| Oklahoma | +51% | +15% |
| South Dakota | +46% | +25% |
| Nebraska | +43% | +35% |
| Texas | −2.5% | −19.6% |

The benchmark matched 91 rows. The one unmatched reference row is OTHER STATES grain, which neither forecast predicts.

**Plainly:**
- **Better:** v2 improves US silage, the state silage mean and acre-weighted errors, and range coverage.
- **Worse:** Maryland silage (−9.3% vs −6.0%), Texas, and the silage median (10.5% vs 10.3%).
- **Still far off:** the Plains states remain badly over-forecast.
- **Grain:** unchanged.

## Caveats

- **The winner beat D narrowly and is a blend.** It is the 2018–2024 winner by 0.48 pp, and D is marginally ahead on the first-print check. 2025 is one year. Its better 2025 score is consistent with the backtest, but does not prove S5 is generally better.
- **First-print history matters.** The 2025 run takes 2022–2024 finals from the January 2025 Annual Summary (`cropan25`). Quick Stats now shows some 2024 values revised in the January 2026 release, which carried the answer. For example, Maryland's 2024 silage is 35,000 in `cropan25` and 40,000 in Quick Stats today. Using the Quick Stats value would have been a leak.
- **The backtest look-ahead is small.** Backtest finals for t-1 come from Quick Stats as published today, which includes revisions released alongside t's first print. This slightly favours the candidates anchored on t-1, which is why the first-print check exists.
- **Planted inputs differ slightly.** For 2025 the latest planted value is September (there was no October 2025 report). In the backtest, the November release used October planted where it existed.
- **The dashboard would show a slightly different US grain range.** `export_dashboard.py` builds it from `interval_z.grain × us.grain_se` (2.27 × SE). forecast_v2's own `us.grain_low/high` uses the t rule (2.20 × SE).
- **Not a contest score.** The benchmark labels its output descriptive only.
- **Housekeeping.**
  - `outputs/backtest.json` from `5deadd5` was extended in `c3262cf` with `per_release`. Its `silage` and `grain` sections were checked to be unchanged.
  - The top-level `silage.us_rel_rms` (4.19%) uses (est − truth)/truth. The ranges use the pre-registered (truth − est)/est, which gives 4.27%.
  - Running `forecast/test_estimate.py` rewrites `forecast/outputs/summary.json`. It was restored after a test run here.

## Files

| file | contents |
|---|---|
| `backtest.py` | writes `outputs/backtest.json` |
| `estimate_2025.py` | writes `outputs/state_estimates_2025.csv`, `summary.json` and `convergence_by_state_2025.csv` |
| `compare_2025.py` | after the fact only |
| `test_forecast_v2.py` | 12 tests: no 2025/2026 final loaded; mutation test (scrambling finals for years >= t leaves forecasts for t unchanged); S1 reproduces the current forecast; winner follows the rule; CSV rows equal the current CSV's; summary schema |
