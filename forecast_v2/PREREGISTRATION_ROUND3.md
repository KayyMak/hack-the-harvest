# forecast_v2: Round 3 pre-registration (2026-11-15, written before any round-3 score was computed)

## Disclosure

Written AFTER the 2025 score of the submitted forecast (round 2: grain G1, silage R2) was seen by the author:
US silage +5.2%; state silage acre-weighted absolute error 14.6%, with large over-calls in IA (+43%),
ND (+62%), KS (+42%), NE (+30%) and SD (+25%) (2025 corn planted rose ~9% and silage did not follow); grain
acre-weighted error 1.6%. Round 3 exists because of that score, so whatever it selects carries extra selection
risk (a third look at the same answer key). Selection uses the backtest only. No 2025 final, judges' file,
benchmark output or January 2026 Annual Summary is read by any code that builds, tunes or selects a method.
Round 1 and round 2 files and picks are not edited.

## Candidates

All use only inputs the existing code already loads: finals for years < t (`prior(finals, t)` in the backtest;
`history_2025` = Quick Stats to 2021 + January 2025 Annual Summary for 2022-2024, for 2025), and the latest
pre-January in-season planted and grain values for t (same `latest(...)` / `vintages(...)` inputs as round 1-2).
Every window is rolling (years t-5..t-1 only). No parameter is fit to the backtest total.

Silage (incumbent: R2 = (D' + PERSIST) / 2 with 5-year median shares):

| id | name | definition | fallback |
|---|---|---|---|
| T1 | RESID5 | (planted_t - grain_t) x median over y in t-5..t-1 of min(1, silage_y / (planted_y - grain_y)) (years with planted - grain > 0). Silage-only states (no grain final in the window, method D's "planted" kind): planted_t x median(silage_y / planted_y) | planted_t or grain_t missing, residual <= 0, or no share year: silage_{t-1} |
| T2 | DAMP50 | silage_{t-1} x (1 + 0.5 x (planted_t / planted_{t-1} - 1)); the single pre-registered k = 0.5 (k = 0 is S2, k = 1 is S3, both already tested in round 1) | planted_t or planted_{t-1} missing: silage_{t-1} |
| T3 | RATIO5 | grain_t x median over y in t-5..t-1 of silage_y / grain_y (5-year variant of round 1's S4, which used 3 years) | grain_t missing or no ratio year: silage_{t-1} |

Grain (incumbent: G1 = latest pre-January NASS forecast as is):

| id | name | definition | fallback |
|---|---|---|---|
| GB5 | NASS_BC5 | G1 x median over y in t-5..t-1 of final_y / forecast_y, forecast_y = that state's forecast for y from the same release period G1 uses for t (5-year variant of round 1's G2, which used 2012..t-1) | fewer than 3 ratio years: G1 |

The US grain row under GB5 is the NASS US forecast x the US's own 5-year median ratio (same rule applied to
US TOTAL). For 2025, the 2022-2024 finals in the ratios come from the January 2025 Annual Summary.

Not run: the rolling stacked blend of R2's components (not enough time to build its per-release calibration
correctly before the deadline; listed here so its absence is not a silent drop).

## Selection rule (same metric and windows as rounds 1-2; incumbents win ties)

- Silage: score R2, T1, T2, T3 by acre-weighted absolute % error over 2018-2024 state-years (the same rows
  `backtest.silage_rows` builds). The best challenger is the lowest of T1-T3 (simplest within 0.20 pp; order
  T2, T3, T1). It replaces R2 only if (a) its acre-weighted error is at least 0.50 pp below R2's and (b) its
  median APE is no more than 0.50 pp above R2's (round 2's replacement rule). Otherwise R2 stands.
- Grain: score G1 and GB5 by acre-weighted absolute % error over 2013-2024 state-years. GB5 replaces G1 only if
  it is at least 0.05 pp lower (round 1's grain rule). Otherwise G1 stands.
- The winners by this rule are what would be submitted, even if 2025 then gets worse.

## Outputs and order

1. Commit this file. 2. `forecast_v2/backtest_round3.py` -> `forecast_v2/outputs/round3/backtest_round3.json`
(no 2025 value read); commit. 3. If a challenger wins, build its 2025 estimate with round 1's interval rules
(per-release calibration, amendment 1) into `forecast_v2/outputs/round3/` (same files as `estimate_2025.py`);
commit. 4. Only then score 2025 with `python -m harvest.benchmark` and write `forecast_v2/results_round3.md`.
If both incumbents stand, nothing new is built; the 2025 comparison is the incumbent's existing score.
