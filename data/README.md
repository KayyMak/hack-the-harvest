# Additional data sources

## Candidate field boundaries: USDA Crop Sequence Boundaries

The [fiboa USDA cropland collection](https://source.coop/fiboa/us-usda-cropland)
is a candidate source of field boundaries and crop codes for the contiguous US.
Corn crop codes do not distinguish corn harvested for silage from corn harvested
for grain, so these boundaries cannot supply harvest-type training labels.

This collection has not been integrated into the baseline. No CSB download script
is included in this repository; consult the source collection for downloads,
year coverage, metadata, and license details before using it.

# Extra BARC silage/grain labels (Kraatz 2023)

[`kraatz_labels.csv`](../kraatz_labels.csv) adds field-level corn harvest-type labels for BARC (Beltsville, MD)
from the farm's own planting and harvest records, 2017–2021.

Source: Kraatz, S. (2023). *Validating NISAR's cropland mapping approach and the USDA/NASS
Cropland Data Layer against ground truth data in a fragmented urban agricultural region*
(v1.0.0) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.8087301
Rebuild from the repository root with `python build_kraatz_labels.py`, using the
GeoPandas/pandas analysis environment in `baseline/README.md`. The script reads the two
versioned Zenodo ZIPs in `data/` and the original root GeoPackage, and writes the root CSV.

## Columns
| column | meaning |
|---|---|
| `idn` | field name in the farm records (also the `id` column of the Zenodo field outlines) |
| `year` | crop year |
| `harvest_type` | `Grain` (record crop "Corn Field / FLDCRN") or `Silage` ("Corn Silage / CSIL") |
| `label_source` | `harvest_record` (what was actually harvested) or `planting_record` (planned use only, weaker) |
| `harvest_date`, `harvest_doy` | earliest recorded harvest date / day of year |
| `planting_date` | earliest recorded planting date |
| `plant_type` | crop type in the planting record |
| `planting_n_types` | number of distinct corn types in planting records for this field-year |
| `conflict` | True if planting and harvest records disagree, or either lists both types |
| `OBJECTID` | matching polygon in `BARC_Corn.2021-2023.gpkg` (blank = no match) |
| `share` | fraction of the record's outline inside that BARC polygon (matches require ≥ 0.5) |

## How to use
- Use rows with `OBJECTID` filled and `conflict == False`. That's 61 field-years on 34 BARC polygons
  (62 matched rows before excluding one conflicting planting record).
- Prefer `harvest_record` rows. Treat `planting_record` rows as weaker labels (lower weight, or a sensitivity check).
- New years are 2017–2020, so satellite features must be extracted for those years.
- For evaluation, keep every year of an `OBJECTID` in the same fold, including these
  earlier years. Do not train on 2017–2020 records for a field held out in 2021–2023.
  Fit imputation and scaling on training folds only. A future-year test on previously
  seen fields answers a different question and must be reported separately.
- Rows without an `OBJECTID` are other BARC fields. Their geometry is in the Zenodo
  `barc_field_outlines_for_study.zip` (join on `idn` = `id`), which could roughly triple the training data.

## Checks
- Agreement with official BARC labels where both exist: 10/10 (8 Grain, 2 Silage).
- Median harvest day of year among rows with a harvest date: Silage 250 (~Sep 7), Grain 286 (~Oct 13). The ranges overlap
  (Silage 228–308, Grain 253–320), so harvest timing alone does not separate the classes perfectly.
