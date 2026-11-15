# BARC logistic regression baseline

New code, numerical caches, and outputs live in this directory. The original
GeoPackage, notebooks, and data-source guide are unchanged. The original root
README is preserved byte for byte at `../docs/original/README.md`; the current
root README documents the whole project. Source SHA-256 hashes are in
`original_sha256.json` and checked before and after runs.

## What the supplied notebooks do

`barc_fields_explorer.ipynb` reads the GeoPackage's
`barc_silage_grain_corn20212023` layer, reshapes three yearly label columns into
field-years, excludes unlabeled records, summarizes class counts and acreage,
and maps fields and label counts. It does not extract satellite observations
or train a classifier.

`sentinel-2_starter_notebook.ipynb` reads one example GeoJSON, searches the
Microsoft Planetary Computer Sentinel-2 L2A catalog for July–November 2022
scenes with less than 40% scene cloud cover, loads red, NIR, and SCL, masks
selected SCL classes, plots median NDVI, and derives peak and late-season
features. It does not obtain reference labels, train a classifier, or evaluate
predictions. The plotted September line is a visual reference, not a learned
harvest threshold. Its features are hypotheses, not ground-truth labels.

## Verified source labels and missing files

| Year | Grain | Silage | Blank |
| --- | ---: | ---: | ---: |
| 2021 | 14 | 4 | 65 |
| 2022 | 3 | 4 | 76 |
| 2023 | 15 | 4 | 64 |
| Total field-years | 32 | 12 | 205 |

There are 83 valid, nonempty multipolygons, 83 unique `OBJECTID` values, and
44 labeled field-years on 34 distinct fields. Blank labels mean unknown;
they are never converted to Grain or included in supervised training.
Unexpected nonblank labels would stop the pipeline.

`data_sources.md` supplies source and evaluation guidance. The starter's
`field_aoi.geojson` is absent. No satellite rasters, numerical satellite cache,
package environment, or dependency file was supplied. The GeoPackage provides
the required boundaries and labels, so no extra boundary file or API key is
needed by this baseline. Satellite observations require public network access.

## Packages and environment

The explorer requests `geopandas`, `matplotlib`, `pandas`, and `pyogrio`.
The starter requests `geopandas`, `matplotlib`, `numpy`, `odc-stac`,
`planetary-computer`, `pystac-client`, and `xarray`. Executing notebooks also
requires a Jupyter environment/kernel.

This command-line baseline uses GeoPandas/pyogrio and pyproj for geometry,
Rasterio for small COG reads and polygon masking, pystac-client and
planetary-computer for public catalog/asset access, NumPy/pandas for numerical
summaries, and scikit-learn for the model and validation. It does not need
Jupyter, matplotlib, odc-stac, or xarray. Direct requirements are in
`requirements.txt`; `requirements-lock.txt` records the exact installed versions.

Initially only Python 3.15 was installed, with none of these analysis packages.
A local Python 3.12.10 runtime and packages were downloaded into `.runtime/`.
That environment is ignored by Git. For a new Python 3.12 environment:

```powershell
python -m venv baseline/.venv
baseline/.venv/Scripts/python.exe -m pip install -r baseline/requirements-lock.txt
```

From the project root, using this machine's existing runtime:

```powershell
baseline/.runtime/python.exe baseline/test_baseline.py
baseline/.runtime/python.exe baseline/run_baseline.py pilot
baseline/.runtime/python.exe baseline/run_baseline.py extract
baseline/.runtime/python.exe baseline/verify_calibration.py
baseline/.runtime/python.exe baseline/run_baseline.py evaluate
```

The pilot must pass before full extraction. Existing field-year caches are
reused; evaluation is offline. To retry an explicitly failed/partial field-year,
move its JSON cache outside `cache/` and rerun extraction. Changing the source
or extraction configuration invalidates caches and the pilot gate rather than
silently mixing results. Source changes require a new reviewed hash manifest.

## Using BARC polygons in the starter

In a **copy** of the starter, replace its GeoJSON-loading block with:

```python
fields = gpd.read_file(
    'BARC_Corn.2021-2023.gpkg', layer='barc_silage_grain_corn20212023'
)
field_id, year = 1, 2021
aoi = fields.loc[fields.OBJECTID.eq(field_id)].to_crs('EPSG:4326')
assert len(aoi) == 1
assert aoi.iloc[0][f'Corn_{year}'] in ['Grain', 'Silage']
START_DATE, END_DATE = f'{year}-07-01', f'{year}-11-30'
```

Use that geometry for STAC `intersects`. Give odc-stac an explicitly tagged
geographic geometry, e.g. `odc.geo.geom.Geometry(aoi.geometry.iloc[0].__geo_interface__,
crs='EPSG:4326')`. After loading, use `rasterio.features.geometry_mask` on the
cube's grid so only centers inside the actual polygon enter the median:
requesting a geopolygon extent alone does not establish a field-only mask.
Cast bands to floating point before arithmetic and apply reflectance calibration,
including the additive offset for Sentinel-2 processing baseline 04.00 onward.
Update every hardcoded 2022 date, including late-season filtering and the plot
annotation. Repeat for each **labeled** `(OBJECTID, year)` instead of merging
different fields into one AOI. The separate script implements this full path.

## CRS verification

The GeoPackage uses custom SRS ID `100000`, named **NAD83 / Maryland (ftUS)**.
It is appropriate for these Maryland field boundaries. Its WKT has no EPSG
authority and is not exactly equal to the database's EPSG:2248 definition:
the standard parallels are reversed and false easting differs by about
0.0001 meter. Transforming the actual bounds using either definition differs
by only `1.18e-9` degrees (about 0.1 mm). Preserve its declared CRS; do not
overwrite it with an EPSG label.

Transformed bounds are approximately longitude `-76.9385` to `-76.8117`,
latitude `39.0038` to `39.0430`, near Beltsville. EPSG:4326 is used for STAC
queries. The starter's **EPSG:32618 (WGS 84 / UTM zone 18N)** is appropriate
here: Maryland BARC lies in zone 18, in the northern hemisphere. Satellite
assets are confirmed to use that grid. Measurements use 10-meter imagery;
10 in the GeoPackage's native CRS would mean 10 feet, not 10 meters.

## Extraction and features

The pilot processes field 1 / 2021 before any other field-year. It must yield
at least three usable dates and no read errors. Full extraction then processes
the other 43 labeled field-years. Each year is searched separately, using its
actual field polygons and July 1–November 30, with scene cloud cover <40%.

For each scene, the script reads only a shared bounding window for that year's
requested fields from the B04 (red), B08 (NIR), and SCL COGs. It keeps pixel
centers within each individual polygon; outside pixels never enter summaries.
SCL's native 20-meter classes are aligned to the 10-meter red grid using
nearest-neighbor resampling. Classes 4, 5, 6, and 7 are retained, matching the
starter; these include vegetation, bare soil, water, and unclassified pixels.
Cloud, shadow, cirrus, snow, invalid, and nodata pixels are rejected. SCL is
imperfect, particularly near clouds and field edges.

Reflectance uses explicit STAC scale/offset when available, otherwise the ESA
Sentinel-2 convention: scale 0.0001 and offset 0 before processing baseline
04.00, offset -0.1 from 04.00 onward (equivalent to subtracting 1000 DN).
The processing baseline and applied calibration are recorded per observation.
`verify_calibration.py` checks one original product XML for each processing
baseline present in the manifests; all four observed baselines passed.
Floating-point NDVI rejects nonpositive denominators and values outside [-1, 1].
A field-scene median is accepted only with at least three valid pixels and
20% valid field pixels. All rejected observations remain in the cache as
missing, with counts and reasons. Scenes on the same date are collapsed to
one median, preventing duplicate tile/processing entries from counting as
independent dates. No temporal interpolation is applied.

Nine predictors: five monthly NDVI medians (July–November), peak NDVI, day of
year of that observed peak, median NDVI from September onward, and the
July–August median minus the October–November median. Peak day refers to the
observed July–November window, not necessarily the true crop-season peak.
Labels, IDs, year, acreage, observation counts, and cloud coverage are not
predictors. Numerical caches retain accepted/rejected scene measurements,
item IDs, dates, calibration, and failures. Unsigned STAC manifests preserve
query geometry and original asset URLs; expiring access tokens are not stored.

## Evaluation and limitations

Five-fold stratified group cross-validation uses `OBJECTID` groups and seed
42. Every year of a field belongs to one held-out fold, checked by assertions.
Each fold fits its own median imputer, standard scaler, and logistic regression
(`C=1`, default class weights, threshold 0.5). No hyperparameter tuning or
threshold selection uses held-out results. A feature entirely missing in a
training fold is filled with zero by that fold's imputer and explicitly listed.
Field-years with no usable dates are excluded and reported as abstentions;
individual missing features are imputed using training data only.

**Model versions.** The paragraph above describes v1, the original baseline,
which is kept unchanged as a backup. The saved outputs now come from model v2
(`baseline/model_version.py`, `MODEL_VERSION = 'v2'`): the nine predictors plus
four harvest-timing features from the same NDVI series (`decline_doy`,
`drop_doy`, `drop_size`, `regrowth`), L1 logistic regression with `C` chosen by
field-grouped inner cross-validation inside each training fold, threshold 0.5.
It is candidate H of a pre-registered comparison (`model_v2/results.md`), so
its seed-42 scores are optimistic; the selection-corrected estimate and the
bootstrap interval for its gain are in `outputs/results.md`. Mid-season (as-of)
calls still refit v1 on the months available. `HTH_MODEL_VERSION=v1` rebuilds
every v1 output; see `outputs/v1_backup/README.md`.

The always-Grain model is evaluated on exactly the same held-out rows.
Silage is positive. False positive rate is Grain predicted as Silage divided
by all true Grain examples. Confusion matrices use true rows and predicted
columns, ordered Grain, Silage. Brier scores supplement the requested
classification metrics as a limited check of probability quality; this small
dataset cannot support a strong calibration claim. Year-level metrics reuse
the same held-out predictions rather than refitting on that year.

Field grouping prevents repeated-field leakage, but nearby held-out fields can
still share imagery, soils, weather, or management. This is an exploratory
single-site baseline, not evidence of generalization to other farms, regions,
or future years. No buffered spatial validation, external dataset, CDL mask,
weather features, or harvest-date ground truth was added. Source provenance
and label licensing/meaning remain those supplied in the explorer and guide.

## Outputs

- `outputs/audit.json`: independently checked counts, geometry/CRS evidence,
  source hash, and extraction configuration.
- `outputs/pilot.json`: the one-field-year acceptance result.
- `cache/<OBJECTID>_<year>.json`: numerical scene records, status, calibration.
- `cache/catalog/`: unsigned STAC metadata and query provenance.
- `outputs/labels.csv`, `features.csv`, `missing_features.csv`: reference labels,
  numerical predictors, and explicit feature missingness.
- `outputs/observations.csv`: per-scene measurements and failure reasons.
- `outputs/excluded_no_observations.csv`: labeled field-years without usable dates.
- `outputs/heldout_predictions.csv`: fold IDs, observed labels, predictions,
  and Silage probabilities.
- `outputs/metrics.json`: pooled, by-year, and by-fold metrics and split records.
- `outputs/results.md`: readable measured results and data quality summary.

## Calls on unlabeled field-years

`unlabeled_calls.py` gives model calls for blank-label field-years. A blank label is
unknown, and BARC rotates crops, so most blanks were not corn that year. The script
first checks each field-year against the USDA Cropland Data Layer (CDL, Maryland,
30 m; only a clip around BARC is read, into the gitignored `data/raw/cdl/`). It then
extracts Sentinel-2 features for the blank field-years that are at least 50% CDL
corn, with `run_baseline.py`'s own functions and configuration, into
`cache_unlabeled/`. Last, it fits `build_model()` on the labeled field-years and calls
them. Labeled field-years are refused, and blanks never enter training.

```powershell
baseline/.runtime/python.exe baseline/unlabeled_calls.py corn
baseline/.runtime/python.exe baseline/unlabeled_calls.py pilot --field 235 --year 2021
baseline/.runtime/python.exe baseline/unlabeled_calls.py extract
baseline/.runtime/python.exe baseline/unlabeled_calls.py predict
baseline/.runtime/python.exe baseline/unlabeled_calls.py extract-all
baseline/.runtime/python.exe baseline/export_unlabeled_imagery.py observations
baseline/.runtime/python.exe baseline/export_unlabeled_imagery.py chips
```

`extract-all` runs the same extraction for every blank field-year, including the
not-corn and mixed ones, so the field panel has a greenness series and before/after
chips for all 249 field-years. Failed scene reads are retried with backoff and any
that still fail stay `read_error` records. These field-years get no model call:
`predict` still calls only the likely-corn blanks. `export_unlabeled_imagery.py`
writes `outputs/unlabeled/observations.csv` (with `observations_coverage.json`
listing any field-year without a cache, without a usable look, or with failed reads)
and `outputs/chips/index_unlabeled.json` (with field-years that have fewer than two
usable looks listed, not drawn).

Outputs are in `outputs/unlabeled/`: `corn_check.csv`/`.json` (CDL corn share for all
249 field-years, including the CDL rule checked on the 44 labeled ones),
`predictions.csv` and `summary.json` (calls, acres by year with the roll-up's
Bernoulli 95% interval, caveat, held-out accuracy for context, farm-record spot
check, sources). `predict` first re-runs the saved cross-validation from
`features.csv` and stops unless it reproduces `heldout_predictions.csv`. There is no
reference label for these calls, so they cannot be scored.

Read failures are recorded per scene; fatal failures also write
`outputs/last_failure.txt` and stop with a nonzero exit status. A partially
observed field-year can still be scored; its failed scenes and missing features
remain visible. No failed observation is substituted with fabricated imagery.

Please cite the BARC publications and datasets listed in
`../barc_fields_explorer.ipynb`, including Dulaney et al. (2024),
https://doi.org/10.1002/agg2.20474, and Kraatz et al. (2023),
https://doi.org/10.3390/s23208595, plus their linked Ag Data Commons and Zenodo
datasets. Sentinel-2 L2A access is via
https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a.
