# Forecast backtest from a NASS Quick Stats history export

A longer backtest for the 2025 state forecast in `forecast/` (which this directory only reads).
Results and interpretation: [`results.md`](results.md). Full tables: [`outputs/tables.md`](outputs/tables.md).

## Input data

`quickstats_corn_harvested_1990_2026.csv` is an unmodified USDA NASS Quick Stats export
(<https://quickstats.nass.usda.gov/>). It was downloaded on 2026-11-14 at about 22:35 PST and
saved as `B55E6C85-3F63-3A0F-9D3E-5320C6E39867.csv`.

- sha256 `88a894586ecfba4bb6816e884eda87e1a97dcbf54ff03a777961b7d15dfaebe4`, 5,750 data rows, LF line endings.
  `backtest.py` refuses to run if the hash differs. The local `.gitattributes` marks the file `-text` so
  checkouts keep these bytes.
- These filters are inferred from the columns; the query itself was not saved:
  - Program = SURVEY; Commodity = CORN.
  - Data Item = `CORN, GRAIN - ACRES HARVESTED` and `CORN, SILAGE - ACRES HARVESTED`.
  - Domain = TOTAL; Geo Level = NATIONAL and STATE; Years 1990–2026.
  - Periods = `YEAR`, `YEAR - JUN ACREAGE`, and `YEAR - AUG`/`SEP`/`OCT`/`NOV FORECAST`.
- Grain: finals (`YEAR`) for 1990–2024 and 2026, plus in-season forecasts for 2012–2026. Silage: finals only, 1990–2024.
- **2025 is absent by design.** It is the graded year, and nothing here adds, looks up, or tunes to a 2025 value.
- **The 2026 `YEAR` rows equal the November 2026 forecast**, so they are preliminary and excluded from every final.
- A `YEAR` value is NASS's *currently published* number. It can include revisions made after the first January
  print. For example, 13 of the 31 November-forecast states have 2024 grain finals here that differ from the January
  2025 Annual Summary that the forecast used. See `outputs/crosscheck_forecast.json`.
- There are no planted acres in this export, so the forecast's silage method D cannot be re-run from it.
- `OTHER STATES` is an aggregate whose final is printed as 0, so it is dropped. `US TOTAL` is kept out of the state statistics.

## Run

```
python analysis/forecast_backtest/backtest.py              # reads only the CSV -> outputs/backtest.json, outputs/tables.md
python analysis/forecast_backtest/crosscheck_forecast.py   # reads forecast/ (read only) -> outputs/crosscheck_forecast.json
python -m unittest analysis/forecast_backtest/test_backtest.py -v
```

Needs pandas. The cross-check imports `forecast/estimate_2025.py` and uses its committed report cache. It never
touches the January 2026 Annual Summary.
