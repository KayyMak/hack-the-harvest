# forecast_v2: round 4 results (yield-adjusted silage; run AFTER round 2's 2025 score was seen)

**Selection risk, disclosed.** Round 4 was written after the team had seen the 2025 errors of the submitted
forecast (US silage +5.2%, Plains over-calls). It was pre-registered in `PREREGISTRATION_ROUND4.md` (commit
`ab143f2`) before the yield data was downloaded and before any round-4 score existed. The yield file was committed
in `9f82d22` with every 2025 `YEAR` row and every 2026 row removed. The winner was chosen on the 2018-2024 backtest only
and committed in `54778b2`. No round-4 code reads a 2025 final, and a test (`Round4`) checks that `backtest_round4.py` never
names the answer key.

## Method

Each candidate starts from R2 (the submitted silage method). R2 is unchanged and computed by the existing
`backtest.silage_rows`.

| id | definition |
|---|---|
| R2 (incumbent) | (D' + silage_{t-1}) / 2, D' shares = 5-year medians |
| Y1 state yield anomaly | R2 x (1 + beta_t x a), clipped to [0.5, 1.5] x R2; a = state in-season yield_t / mean(state final yield t-5..t-1) - 1, needs >= 3 finals |
| Y2 national yield anomaly | same, with a = US in-season yield_t / US 5-year mean final - 1, the same for every state |

- **In-season yield.** The latest of the NOV, OCT, SEP and AUG FORECAST values for year t. Final yields are from Quick Stats as
  published today.
- **beta_t.** The acre-weighted least-squares slope through the origin of (final silage / R2 - 1) on a. The weights are
  previous-year silage acres. The fit pools the state-years 2013..t-1 where both are defined, so it uses only years before t.
  beta_t = 0 when there are fewer than 30 such state-years. R2 for 2013-2017 comes from the same code, with planted acres
  from March Prospective Plantings in those years.
- **Rule (pre-registered).**
  - The best challenger is the lower of Y1 and Y2 on 2018-2024 acre-weighted absolute % error. Y2 wins if it is within
    0.20 pp of Y1.
  - The challenger replaces R2 only if it is >= 0.50 pp lower on that error AND its median APE is no more than 0.50 pp
    higher.

## Backtest

Silage, 2018-2024. There are n = 336 state-years, the same rows as rounds 1-3. US RMSE is the RMS of the yearly
sum-of-states % errors.

| method | acre-wtd APE 2018-24 | median APE | within 10% | US RMSE 2018-24 | acre-wtd 2013-24 (reported only) |
|---|---|---|---|---|---|
| **R2 (incumbent)** | 12.68 | 10.26 | 49.1% | 3.94% | 14.03 |
| Y1 state anomaly | **12.43** | **9.87** | **50.6%** | **3.28%** | **13.83** |
| Y2 national anomaly | 12.63 | 10.21 | 48.5% | 3.71% | 15.48 |

US silage error by year (sum of states vs sum of finals, %), with each year's acre-weighted APE in brackets:

| year | R2 | Y1 | Y2 |
|---|---|---|---|
| 2018 | +3.59 (17.46) | +2.66 (16.39) | +3.28 (17.32) |
| 2019 | -4.09 (14.93) | -3.65 (14.46) | -3.82 (14.94) |
| 2020 | +1.55 (9.62) | +0.72 (10.52) | +1.38 (9.63) |
| 2021 | +2.79 (12.78) | +1.55 (11.24) | +2.58 (12.70) |
| 2022 | -6.62 (14.18) | -6.21 (13.67) | -6.55 (14.19) |
| 2023 | +2.96 (9.62) | +2.19 (9.95) | +2.84 (9.58) |
| 2024 | +4.04 (10.25) | +2.93 (10.87) | +3.37 (10.16) |

beta_t by year (number of state-years in the fit). beta_t is 0 only in 2013, which has no earlier year in the
2013.. window. From 2014 on every fit has >= 30 state-years.

| t | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | (2025) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Y1 | 0 (0) | -0.660 (32) | -0.323 (64) | -0.265 (96) | -0.250 (128) | -0.173 (160) | -0.300 (192) | -0.330 (224) | -0.291 (256) | -0.353 (288) | -0.403 (320) | -0.384 (352) | -0.357 (383) |
| Y2 | 0 (0) | -1.821 (48) | -0.390 (96) | -0.306 (144) | -0.149 (192) | -0.055 (240) | -0.079 (288) | -0.092 (336) | -0.094 (384) | -0.102 (432) | -0.108 (480) | -0.113 (528) | -0.134 (576) |

Every beta is negative, as the salvage hypothesis predicts: a good yield means less silage and a poor yield means more. Y1
pulls every year's US error toward zero, but only by about 0.4-1.2 pp. Its gain in acre-weighted state error is small, and
in 2020, 2023 and 2024 it is worse than R2 at the state level.

## Winner

**R2 stays.** The best challenger is **Y1**: 12.43 vs R2's 12.68, a gain of **0.25 pp**. The rule needs 0.50 pp. Y1's
median APE is 0.39 pp better, so the median condition is met, but the gain condition is not. Y2 is only 0.045 pp better
than R2. Under the pre-registered rule the submission is unchanged: silage = R2, grain = G1. No `round4/` estimate files
are built; the only round-4 output is `outputs/round4/backtest_round4.json`. 2025 was not scored for Y1 or Y2.

## 2025, after the fact

The round-4 pick is the round-2 submission, so its 2025 numbers are R2's. They were scored earlier with
`python -m harvest.benchmark` on `forecast_v2/outputs/state_estimates_2025.csv` and are not re-run here:

| | R2 (submitted) = round 4 pick |
|---|---|
| US silage | +5.18% |
| Maryland silage | -8.38% (36,648) |
| silage states within 10% | 22 / 48 |
| state silage acre-weighted error | 14.62% |
| 95% coverage (silage) | 48 / 48 |

## Deviations and interpretations (none change the outcome)

1. **Yield data starts in 2005.** The pre-registration and the file name say 2000, but the Quick Stats export starts in 2005.
   A 5-year mean final therefore exists from 2010 on. Every year that needs one (2013 onward) has it.
2. **No anomaly means R2.** When a is undefined (the state has no in-season NASS yield forecast, or fewer than 3
   finals), Y1 = R2, i.e. beta x 0. The pre-registration does not state this case explicitly. 223 of the 336 backtest
   rows have a state anomaly; Y2 has one for every row.
3. **Tie window.** Y2 missed the 0.20 pp simplicity window by 0.004 pp (12.634 vs 12.430 + 0.20), so the best
   challenger is Y1. This is immaterial: neither challenger clears the 0.50 pp bar.
4. **R2 for 2013-2017.** R2 for these years came from the existing code (`backtest.silage_rows` over 2013-2024), so the
   30-state-year fallback applied only to 2013.
5. **Robustness column.** The 2013-2024 column uses the beta_t values above, including beta_2013 = 0 and the
   small-sample 2014 fit. It is reported only and was not used for selection.

## Files

- `forecast_v2/PREREGISTRATION_ROUND4.md`: disclosure, candidates and rule (committed first, `ab143f2`).
- `forecast_v2/data/quickstats_corn_yield_2000_2025.csv` and its README section (`9f82d22`).
- `forecast_v2/backtest_round4.py` writes `forecast_v2/outputs/round4/backtest_round4.json` (`54778b2`).
- `forecast_v2/test_forecast_v2.py`, class `Round4`. It checks four things: the round-4 code never names the answer key, the
  yield file has no 2025 final and no 2026 row, beta_t ignores finals from t on, and the winner follows the rule.
