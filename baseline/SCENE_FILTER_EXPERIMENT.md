# Scene-cloud filter input experiment

The starter excludes Sentinel-2 scenes with tile-wide cloud cover >=40% before
checking the actual field pixels. Inspection found a discarded September 12,
2023 scene for field 323 with about 69% usable field pixels and NDVI 0.258.
That observation falls inside the original September 7–October 2 gap. A
discarded October 7, 2021 scene for field 327 also has about 95% usable pixels.

This motivates one controlled, exploratory experiment: remove the whole-scene
cloud cutoff while keeping the field-pixel quality rules unchanged. This is
not a change to reference labels, the model threshold, or the Nemotron prompt.

## Fixed comparison

- All 44 labeled BARC field-years, not just the inspected errors.
- Original July–November dates, polygon-center masks, reflectance calibration,
  SCL classes 4/5/6/7, three-pixel minimum, and 20% clear-field threshold.
- The same nine feature definitions from `run_baseline.summarize`.
- The same logistic pipeline from `run_baseline.build_model`: training-fold
  median imputation and scaling, C=1, default class weights, threshold 0.5.
- Exactly the saved field-grouped training/test memberships. Every year of a
  field stays together.
- Original observations are reused. Additional >=40%-cloud scene measurements
  come from the same extraction helper. No original files or caches are edited.
- Same-date entries are collapsed by the original feature summarization rule.
- Scores are reported whether improved or worse. Expected/hard Silage acreage
  errors are reported on the labeled BARC fields; these are not 2025 state totals.

Before fitting the changed inputs, the experiment reconstructs every original
fold and checks all saved probabilities within 1e-10. This checks that a model
implementation change cannot masquerade as an input-coverage improvement.

## Run

Use the baseline analysis environment. On this machine, from the project root:

```powershell
baseline/.runtime/python.exe baseline/experiment_scene_filter.py pilot
baseline/.runtime/python.exe baseline/experiment_scene_filter.py run
```

The pilot processes field 323 / 2023 first. It passes on increased usable
observation coverage with no read errors, never on prediction correctness.
It increased usable dates from 12 to 17. Extraction caches are resumable;
an item processed for only the pilot field is extended for the remaining
fields during the full run. Catalog results and protocol/input fingerprints
are stored separately under `baseline/outputs/experiments/no_scene_cloud_filter/`.

Read errors are recorded and prevent a model comparison from being presented
as complete. A changed input protocol invalidates cached experimental records.
The saved original baseline and Nemotron results are preserved.

Outputs include `features.csv`, `observations.csv`, `coverage.csv`,
`heldout_predictions.csv`, `changed_predictions.csv`, and `metrics.json`.
The metrics include classification, per-year results, labeled-field acreage,
coverage additions, and all changed labels/probabilities.

## Diagnostic imagery

```powershell
baseline/.runtime/python.exe baseline/check_scene_filter.py
baseline/.runtime/python.exe baseline/inspect_satellite_inputs.py pilot
baseline/.runtime/python.exe baseline/inspect_satellite_inputs.py run
```

The scene-filter check queries two identified gaps without a tile-cloud cutoff,
retaining one latest processing version per sensing date for that diagnostic.
The imagery check uses the original scene entries plus those recovered dates.
It checks field-pixel counts, clear-pixel counts, and NDVI against each numerical
record, and exports true-color / masked NDVI / SCL comparisons. These diagnostic
queries are separate from the full experiment, which retains all original
entries and all additional item IDs to preserve the baseline grouping rule.

Plots need `baseline/requirements-diagnostics.txt`. Their RGB display uses a
fixed reflectance stretch across scenes; it is not a harvest-type classifier.
Pink outlines are the original field boundaries. SCL masks are imperfect and
the accepted 20% coverage threshold can still leave unrepresentative samples.

Offline checks:

```powershell
baseline/.runtime/python.exe baseline/test_scene_filter_experiment.py
baseline/.runtime/python.exe baseline/test_baseline.py
```

## Interpretation limit

The 44 BARC cases have been inspected during development. An improvement here
would be exploratory evidence, not a new untouched test. Independently labeled
new fields/years are still needed. Removing a tile-cloud prefilter can improve
coverage but does not prove that every accepted field pixel is truly clear,
nor that the model can distinguish harvest purpose across regions.
