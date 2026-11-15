# forecast_v2/data

## quickstats_corn_planted_2005_2026.csv

Corn planted acres (all purposes), USDA NASS Quick Stats export, downloaded by Kyle on 2026-11-15 at 04:27
local time (file `6EF60195-9505-3927-9EDD-A3732A713E88.csv` in Downloads).

Filters, as seen in the columns of the export: Program `SURVEY`; Commodity `CORN`; Data Item
`CORN - ACRES PLANTED`; Domain `TOTAL` / `NOT SPECIFIED`; Geo Level `STATE` (49 states) and `NATIONAL`;
years 2005-2026; every Period NASS publishes for the item (`YEAR`, `YEAR - MAR ACREAGE`, `YEAR - JUN ACREAGE`,
`YEAR - AUG ACREAGE`, `YEAR - OCT ACREAGE`, `YEAR - AUG FORECAST`, `YEAR - SEP FORECAST`, `YEAR - OCT FORECAST`).

Rows removed before committing (text of the kept lines is unchanged):

- the 49 rows of 2025 `YEAR`: final 2025 planted, published in the January 2026 Annual Summary, the same
  release as the 2025 answer key;
- every 2026 row (246 rows: `YEAR` is preliminary and the year is out of scope).

So the committed file has no 2025 final and no 2026 data, despite its name. For 2025 only the pre-January
periods remain (MAR ACREAGE, JUN ACREAGE, AUG FORECAST, SEP FORECAST).

| file | rows | sha256 |
|---|---|---|
| original export (not committed) | 2,999 | `7c06279d7cbca3dea87fc4908a3830e54e20df6d30c89246ca3f32c877b9538c` |
| `quickstats_corn_planted_2005_2026.csv` (committed) | 2,704 | `a76d198481e19732b263209293978c2f68e13129d3b87f3177774d66cfebbd4a` |

Coverage of in-season (pre-January) planted values: MAR ACREAGE 2012-2025; JUN ACREAGE 2018-2025; AUG ACREAGE
2019; OCT ACREAGE 2018-2019; OCT FORECAST 2020-2024 (2020, 2021 and 2024 for most states); SEP FORECAST
2021-2025; AUG FORECAST 2024-2025. Before 2018 the only pre-January planted value is the March intention.

## quickstats_corn_yield_2000_2025.csv

Corn for grain yield (bu/acre), USDA NASS Quick Stats export downloaded by Kyle on 2026-11-15 after round 4 was
pre-registered (commit `ab143f2`; file `FF9CBFFA-9FA2-3666-A72E-38184AF9E205.csv` in Downloads). Data Item
`CORN, GRAIN - YIELD, MEASURED IN BU / ACRE`; Geo Level `STATE` and `NATIONAL`; periods `YEAR`,
`YEAR - AUG FORECAST`, `YEAR - SEP FORECAST`, `YEAR - OCT FORECAST`, `YEAR - NOV FORECAST`. The export starts in
2005, not 2000 (the name follows the pre-registration), so 5-year mean finals exist from 2010 on.

Rows removed before committing (read with `python -I`; kept rows rewritten in the export's quoting):

- the 43 rows of 2025 `YEAR` (the January 2026 final yield, same release as the answer key);
- every 2026 row (167 rows).

For 2025 only `AUG FORECAST`, `SEP FORECAST` and `NOV FORECAST` remain (no 2025 `OCT FORECAST` was published).

| file | rows | sha256 |
|---|---|---|
| original export (not committed) | 3,857 | `fae98058be07d370506ad3eeb3c0ab589f9f4ce6b45595cbc573adaed8a4e452` |
| `quickstats_corn_yield_2000_2025.csv` (committed) | 3,647 | `da5573b2613c079a031088d54773e24164d4c0b3adf3cbe6325ee513a7f0af6f` |
