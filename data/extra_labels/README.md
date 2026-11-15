# Extra BARC corn harvest labels (experiment input only)

`labels_combined.csv` lists silage/grain labels for BARC field-years compiled from public sources:

- **BARC farm-management harvest records**: USDA BARC Gridded Yield Data Archive, Ag Data Commons
  (`label_source = barc_mgmt_harvest_record`).
- **Kraatz 2023**, Zenodo, doi:10.5281/zenodo.8087301 (`kraatz_harvest_record` = harvest record;
  `kraatz_planting_record` = intended use recorded at planting, a weaker label).
- `barc_official` rows repeat the organizers' labels in `BARC_Corn.2021-2023.gpkg`; they are listed
  for cross-checking only (all agree with the GeoPackage).

`OBJECTID` is the GeoPackage `OBJECTID` (our field id). `split = test_official_2021_2023` marks
official labeled field-years; `train_extra` marks the others (2015, 2017-2020, and 2021-2023
field-years that are blank in the GeoPackage).

Used only by `baseline/experiments/extra_labels/` (results under
`baseline/outputs/experiments/extra_labels/`). The submitted model does not use this file.
