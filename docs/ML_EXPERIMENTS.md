# Published ML experiment snapshot

Historical snapshot of the early experiments. The project later adopted model v2
and submitted the `forecast_v2/` acreage forecast. See the
[submission summary](../SUBMISSION.md) for final deliverables and the
[documentation index](README.md) for current guides.

This branch shares the cached numerical experiments and input diagnostics so
teammates can review them without API keys, GPU instances, or satellite downloads.
It does not replace the app's saved baseline outputs or promote an experimental
model into production.

| Run | Silage precision | Recall | F1 | Balanced accuracy |
| --- | ---: | ---: | ---: | ---: |
| Original logistic baseline | 87.5% | 58.3% | 70.0% | 77.6% |
| Nemotron, same original nine features/folds | 100% | 41.7% | 58.8% | 70.8% |
| Logistic, restored high-tile-cloud scenes | 90.0% | 75.0% | 81.8% | 85.9% |

All runs cover the same 44 labeled BARC field-years. Nemotron has not been
rerun on the changed satellite inputs, so the latter two rows are not a
same-input model comparison. The scene-filter change preserves field-pixel
masking, feature definitions, model setup, and saved field groups; coefficients
and preprocessing are refitted inside each training fold.

## Transparent rule baseline

The challenge names a rule on the date of sustained NDVI decline as the baseline to beat.
`python baseline/decline_rule_baseline.py` scores that rule on the same 44 held-out field-years
and saved field folds, from the saved observations only (standard library, no satellite access).
The NDVI drop (0.25) was fixed beforehand; the day-of-year threshold is fitted on training fields.

| Run | Silage precision | Recall | F1 | Balanced accuracy |
| --- | ---: | ---: | ---: | ---: |
| Decline-date rule | 39.3% | 91.7% | 55.0% | 69.3% |
| Original logistic baseline | 87.5% | 58.3% | 70.0% | 77.6% |

The rule finds 11 of 12 Silage field-years but calls 17 of 32 Grain field-years Silage: an early
decline alone does not separate the classes here. The logistic regression is ahead on F1 and
balanced accuracy and behind on recall. Results:
[decline_rule/results.md](../baseline/outputs/decline_rule/results.md). Same limits as below:
already-inspected data, twelve Silage rows.

## Evidence and commands

- [Numerical Nemotron protocol](../baseline/NEMOTRON_COMPARISON.md) and
  [measured results](../baseline/outputs/nemotron/metrics.json).
- [Scene-filter protocol](../baseline/SCENE_FILTER_EXPERIMENT.md) and
  [results with remaining errors and acreage breakdown](../baseline/outputs/experiments/no_scene_cloud_filter/results.md).
- [Original field-case investigation](../baseline/outputs/diagnostics/field_323_and_327/findings.md).
- [Field 323 imagery](../baseline/outputs/diagnostics/imagery_323_327/field_323.png)
  and [field 327 imagery](../baseline/outputs/diagnostics/imagery_323_327/field_327.png).
- [Work breakdown](WORK_BREAKDOWN.md).

Create a Python 3.12 analysis environment using baseline/requirements-lock.txt.
The offline suite makes no hosted model or satellite requests:

```sh
python -m unittest discover -s baseline -p "test_*.py" -v
```

Plots additionally need baseline/requirements-diagnostics.txt. The scripts
`inspect_field_cases.py`, `inspect_satellite_inputs.py`, `check_scene_filter.py`,
and `experiment_scene_filter.py` document their own entry points. Use cached
outputs for review; a fresh extraction is unnecessary for reproducing the tests.

## Immutable bytes and provenance

The existing snapshots were generated on Windows and some have CRLF line
endings. Their protocols record SHA-256 over exact bytes. `.gitattributes` keeps
baseline/outputs/ and data/reference/ snapshots unnormalized across platforms.
The baseline output files changed from the previously normalized Git versions
only in line endings; their values/predictions remain identical. No source hash
or cached inference/extraction signature was rewritten. Tests verify the
published inputs still match the original run protocols and response requests.

## Judge reference and new labels

[The frozen judge CSV](../data/reference/quickstats_2025_judges.csv) is copied
unchanged from the public export, with URLs, SHA-256, and snapshot metadata in
the neighboring `.source.json` file. It contains 92 rows for 2025: 42 state-level
Grain, 48 state-level Silage, and two national rows. Some state entries are
OTHER STATES aggregates. The exact contest scoring scope/metric is unconfirmed.
Do not use these aggregate totals as field labels or force estimates to match.

`python -m harvest.benchmark --predictions FILE --out report.json` compares an
aggregate prediction CSV (same headers: Year, Geo Level, State, Data Item,
Domain, Value) with that file, offline and with the standard library only. It
matches year, geography, crop use, and harvested acres exactly; keeps NATIONAL,
STATE, and OTHER STATES rows apart; treats suppressed or blank values as
unknown; and lists rejected, missing, unmatched, and duplicate rows. The report
gives per-row signed, absolute, and relative errors with descriptive means per
geography kind and crop use. It is not a contest score. No statewide 2025
prediction file exists yet, and the BARC roll-up export is rejected as out of
scope rather than compared with the MARYLAND row.

The merged [Kraatz label documentation](../data/README.md) and root
`kraatz_labels.csv` already provide additional BARC label candidates. Audit
harvest-versus-planting provenance, conflicts, overlapping field-years, and
polygon matches before training. Those labels are not yet integrated into the
44-row experiments here. More years on the same field remain one validation
group, not a new independent field.

## Limits

The dataset has already been inspected during development. Improvements are
exploratory and need independent field/year validation. The no-cloud-cutoff
experiment fixes two 2022 errors but still misses fields 327/2021, 254/2023,
and 323/2023, and still has the Grain false positive at 24/2021. Some probability
and acreage errors worsen. BARC acreage subtotals are not statewide 2025 outputs.
Nemotron's 44 valid class responses do not verify its tool-calling or multi-agent
workflow reliability.
