# forecast_v2: round 3 results (run AFTER round 2's 2025 score was seen)

**Selection risk, disclosed.** The author saw the submitted forecast's 2025 errors before writing round 3:
US silage +5.2%, state silage acre-weighted error 14.6%, Plains over-calls (IA +43%, ND +62%, KS +42%,
NE +30%, SD +25%), grain acre-weighted 1.6%. Round 3 was pre-registered before any round-3 score
(`PREREGISTRATION_ROUND3.md`, commit `a3cc457`), selected by the backtest only (commit `47d12a0`), and scored
on 2025 only after that commit. No round-3 code reads a 2025 final; a test checks that `backtest_round3.py` and
`common.py` never name the answer key.

## Method

Candidates (each forecast for year t uses finals for years < t, rolling 5-year windows t-5..t-1, and NASS
pre-January in-season planted and grain values for t; no parameter fit to the backtest total):

| id | definition |
|---|---|
| R2 (incumbent silage) | (D' + silage_{t-1}) / 2, D' shares = 5-year medians |
| T1 RESID5 | (planted_t - grain_t) x 5-year median of silage / (planted - grain) |
| T2 DAMP50 | silage_{t-1} x (1 + 0.5 x (planted_t / planted_{t-1} - 1)); k = 0.5 only (k = 0, 1 were round 1's S2, S3) |
| T3 RATIO5 | grain_t x 5-year median(silage / grain) |
| G1 (incumbent grain) | latest pre-January NASS grain forecast as is |
| GB5 | G1 x 5-year median(final / same-period forecast) |

Not run: the rolling stacked blend (no time to build its per-release calibration; disclosed in the
pre-registration).

Rule (pre-registered): a silage challenger replaces R2 only if it is at least 0.50 pp better on 2018-2024
acre-weighted absolute % error and its median APE is no more than 0.50 pp worse; GB5 replaces G1 only if at
least 0.05 pp better on 2013-2024.

## Backtest

Silage, 2018-2024 (n = 336 state-years, same rows as rounds 1-2):

| method | acre-wtd MAPE 2018-24 | median APE | within 10% | acre-wtd 2013-24 | first-print 2023-24 |
|---|---|---|---|---|---|
| **R2 (incumbent)** | **12.68** | 10.26 | 49.1% | **14.03** | **10.46** |
| T1 RESID5 | 15.07 | 12.50 | 44.0% | 21.75 | 10.73 |
| T2 DAMP50 | 14.84 | **10.01** | **50.0%** | 15.17 | 13.60 |
| T3 RATIO5 | 15.93 | 14.31 | 38.4% | 15.74 | 15.64 |

Per year (acre-weighted MAPE): R2 beats every challenger in 2018, 2019, 2020 and 2024; T2 is slightly better in
2021 (12.47 vs 12.78) and 2022 (13.89 vs 14.18), T1 in 2023 (9.51 vs 9.62).

Grain, 2013-2024 (n = 483 state-years):

| method | acre-wtd MAPE | median APE | within 10% |
|---|---|---|---|
| **G1 (incumbent)** | **1.601** | **2.31** | **82.2%** |
| GB5 | 1.753 | 2.76 | 80.3% |

## Winner

**Both incumbents stand.** The best silage challenger (T2) is 2.16 pp *worse* than R2; GB5 is 0.15 pp worse
than G1. By the pre-registered rule nothing changes: the submission stays grain = G1, silage = R2, and no
`round3/` estimate files are built (only `outputs/round3/backtest_round3.json`).

## 2025, after the fact (scored once with `python -m harvest.benchmark` after commit `47d12a0`)

The round-3 pick is the round-2 submission, so the 2025 numbers are identical to R2's:

| | round 2 (R2 + G1) | round 3 pick |
|---|---|---|
| US silage | +5.18% | +5.18% (same) |
| US grain | -0.99% | -0.99% (same) |
| Maryland silage | -8.38% (36,648) | same |
| Maryland grain | -1.22% (405,000) | same |
| silage states within 10% | 22 / 48 | same |
| state silage acre-weighted error | 14.62% | same |
| state grain acre-weighted error | 1.64% (33 / 41 within 10%) | same |
| 95% coverage | silage 48 / 48, grain 38 / 41 | same |

The benchmark does not compute coverage. The coverage row comes from `results.md` and uses the same file and ranges.
R2 and G1 also have the lowest error outright, at 12.68 vs 14.84 and 1.601 vs 1.753. The outcome is therefore the
same under the stricter replacement bar pre-registered here or under a plain lowest-wins rule with ties to the incumbent.

The 2025 Plains over-call is a year in which silage did not follow a ~9% planted increase. None of the
simple share or persistence alternatives tested here beat R2 over 2018-2024, so the backtest gives no
defensible reason to change the method.

## Files

- `forecast_v2/PREREGISTRATION_ROUND3.md`: disclosure, candidates and rule (committed first).
- `forecast_v2/common.py`: `round3_silage`, `grain_bc5`, `ROUND3_METHODS`.
- `forecast_v2/backtest_round3.py` writes `forecast_v2/outputs/round3/backtest_round3.json`.
- `forecast_v2/test_forecast_v2.py`, class `Round3`: no answer-key names, no look-ahead, rule reproduced.
