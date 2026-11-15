# Data handoff: what the dashboard still needs

The Cutline dashboard (`web/`) already shows the real BARC field outlines, labels,
held-out predictions, metrics vs always-grain, and per-date NDVI from `baseline/outputs/`.
Four pieces are still missing. Each one is a file you save into `baseline/outputs/`.
When it exists, the frontend rebuild picks it up automatically:

```bash
python3 web/scripts/build-real-snapshot.py   # needs: pip install pyproj
```

Nothing below needs new modeling ideas. It is the same logistic model and the same
field-held-out folds, saved in a few more shapes. Keep IDs as `OBJECTID` and years as ints.

---

## 1. Mid-season calls → `baseline/outputs/asof_predictions.csv`

Lets the dashboard show the as-of buttons (Aug 12 / Sep 12 / Oct 12 / Nov 12) and the
"how the call firms up through the season" chart.

For each as-of date, refit the model using only the NDVI features available by that
date (for example by Sep 12, use `ndvi_07`, `ndvi_08` and the part of `ndvi_09` before the
12th). Keep the same folds, and predict the held-out field-years.

| column | type | example | notes |
|---|---|---|---|
| `OBJECTID` | int | `231` | |
| `year` | int | `2022` | |
| `as_of` | date | `2022-09-12` | use the same 4 dates every year: `MM-DD` = 08-12, 09-12, 10-12, 11-12 |
| `status` | text | `decided` | `decided`, `pending` (no harvest signal yet), or `insufficient` (too few clear looks) |
| `predicted_label` | text | `Grain` | blank unless `status = decided` |
| `silage_probability` | float 0–1 | `0.38` | blank unless `status = decided` |
| `fold` | int | `3` | |

If you don't have a rule for `pending` yet, mark everything `decided`. The chart still works.

## 2. Per-field "why" → `baseline/outputs/feature_contributions.csv`

Fills the "Why the model decided" bars in the field panel. For the logistic model this is
`coefficient × standardized feature value` for each feature, computed with the fold's own
fitted model and scaler (the one that did not see that field).

| column | type | example | notes |
|---|---|---|---|
| `OBJECTID` | int | `231` | |
| `year` | int | `2022` | |
| `feature` | text | `late_ndvi` | same names as `metrics.json` → `features` |
| `value` | float | `0.36` | the raw feature value |
| `contribution` | float | `-1.21` | in log-odds; positive pushes toward Silage, negative toward Grain |
| `as_of` | date | `2022-11-30` | optional; leave blank for the season-end model |

About 10 lines after `model.fit(...)` in each fold:
`contrib = model.coef_[0] * scaler.transform(X_test)` and then one row per (field-year, feature).

## 3. Maryland acres vs Census → `baseline/outputs/rollup.json`

Fills the first headline card and the Maryland roll-up section. Run the classifier on
Maryland corn fields beyond BARC (CDL corn pixels or Crop Sequence Boundaries), sum the
silage-probability-weighted acres, and compare with the lab's QuickStats CSV.

```json
{
  "year": 2022,
  "region": "Maryland",
  "acres": 64800,
  "ci_lo": 55100,
  "ci_hi": 74600,
  "cv_pct": 7.6,
  "census_acres": 61200,
  "census_source": "2022 Census of Agriculture, corn for silage, acres harvested",
  "fields_classified": 12345,
  "method": "sum of P(silage) x acres over CDL corn fields; 95% interval by bootstrap over fields"
}
```

One file per year is fine too: `rollup_2021.json`, `rollup_2022.json`, `rollup_2023.json`.

## 4. Before/after images → `baseline/outputs/chips/`

Fills "Before and after" in the field panel. These are true-color Sentinel-2 cutouts of
each scored field: one clear scene before the greenness drop and one after.

- File names: `chips/<OBJECTID>_<year>_pre.png` and `chips/<OBJECTID>_<year>_post.png`
- Size around 256×256 px, 10 m pixels, field outline drawn or field centered, small PNGs
- Optional `chips/chip_dates.csv`: `OBJECTID,year,pre_date,post_date`

---

Questions or a different shape that's easier for you: tell Karthik. The script only needs
the column names above.
