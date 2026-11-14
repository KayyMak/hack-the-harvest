# Extra BARC silage/grain labels (Kraatz 2023)

`kraatz_labels.csv` adds field-level corn harvest-type labels for BARC (Beltsville, MD)
from the farm's own planting and harvest records, 2017–2021.

Source: Kraatz, S. (2023). *Validating NISAR's cropland mapping approach and the USDA/NASS
Cropland Data Layer against ground truth data in a fragmented urban agricultural region*
(v1.0.0) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.8087301
Built with `build_kraatz_labels.py` (needs the two Zenodo zips in the working directory).

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
| `conflict` | True if planting and harvest records disagree, or harvest records list both types |
| `OBJECTID` | matching polygon in `BARC_Corn.2021-2023.gpkg` (blank = no match) |
| `share` | fraction of the record's outline inside that BARC polygon (matches require ≥ 0.5) |

## How to use
- Use rows with `OBJECTID` filled and `conflict == False`. That's 62 field-years on 34 BARC polygons.
- Prefer `harvest_record` rows. Treat `planting_record` rows as weaker labels (lower weight, or a sensitivity check).
- New years are 2017–2020, so satellite features must be extracted for those years.
- Keep the official 2021–2023 BARC labels as the held-out evaluation set.
- Rows without an `OBJECTID` are other BARC fields. Their geometry is in the Zenodo
  `barc_field_outlines_for_study.zip` (join on `idn` = `id`), which could roughly triple the training data.

## Checks
- Agreement with official BARC labels where both exist: 10/10 (8 Grain, 2 Silage).
- Median harvest day of year: Silage 250 (~Sep 7), Grain 272 (~Sep 29). The ranges overlap
  (Silage 228–308, Grain 253–320), so harvest timing alone does not separate the classes perfectly.
