# forecast_v2 round 4 pre-registration: yield-adjusted silage

Written and committed **before** the yield data was downloaded or any round-4 score was computed. Nothing below may
change after the first score is seen; any deviation is listed in `results_round4.md`.

## Disclosure

Written on 2026-11-15 after the team had seen the 2025 errors (US silage +5.2%; large over-calls in Iowa, North Dakota,
Kansas, Nebraska and South Dakota) and after noticing that the method under-called US silage in the 2022 Plains drought
(-6.6%) and over-called it in the record-yield years 2023 (+3.0%) and 2025 (+5.2%). The hypothesis is the salvage
mechanism: when corn yields are poor, farmers chop more corn for silage; when yields are good, less. The selection rule
below decides; the team decided before seeing any round-4 result that a challenger is submitted only if it clearly wins
the backtest (the same replacement rule as rounds 2-3), whatever it does on 2025.

## Inputs (all public and released before January of the forecast year)

- Everything R2 already uses (`PREREGISTRATION.md`), unchanged.
- NASS Quick Stats `CORN, GRAIN - YIELD, MEASURED IN BU / ACRE`, state and national, 2000-2025, periods `YEAR`,
  `YEAR - AUG FORECAST`, `YEAR - SEP FORECAST`, `YEAR - OCT FORECAST`, `YEAR - NOV FORECAST`, saved as
  `forecast_v2/data/quickstats_corn_yield_2000_2025.csv`. **Rows with Year 2025 and Period `YEAR` (the January 2026
  final) and any 2026 row are deleted before the file is committed and are never read.**
- In-season yield for year t: the latest of NOV, OCT, SEP, AUG FORECAST for t. Final yields for years before t come
  from Quick Stats as published today (a small look-ahead from later revisions, the same caveat as R2's finals).

## Candidates

Let `R2_t(s)` be the submitted R2 silage estimate for state s, year t, computed by the existing code.

| id | name | definition |
|---|---|---|
| R2 | incumbent | unchanged |
| Y1 | state yield anomaly | `a = yf_t(s) / mean(final yield of s, t-5..t-1) - 1` (needs >= 3 finals); `Y1 = R2 x (1 + beta_t x a)`, clipped to [0.5, 1.5] x R2. `beta_t` = least-squares slope through the origin of `(final silage / R2 - 1)` on `a`, weighted by previous-year silage acres, pooled over all state-years in years 2013..t-1 where both are defined; if fewer than 30 such state-years, `beta_t = 0`. |
| Y2 | national yield anomaly | as Y1, but `a` uses the US national yield forecast and US 5-year mean for every state (one anomaly per year). |

`beta_t` uses only years before t. R2 values for 2013-2017 come from the same code (planted from March Prospective
Plantings there, as `PREREGISTRATION.md` already specifies for the grain window).

## Selection rule (same as rounds 2-3; incumbent wins ties)

Silage, acre-weighted absolute % error over 2018-2024 state-years (the rows `backtest.silage_rows` builds). The best
challenger is the lower of Y1 and Y2 (Y2 is simpler; it wins within 0.20 pp). It replaces R2 only if its acre-weighted
error is at least 0.50 pp lower than R2's AND its median absolute % error is not more than 0.50 pp higher. Otherwise R2
stays. The 2025 judges' file is scored only after the winner is committed.

Grain is unchanged (NASS's latest pre-January forecast).
