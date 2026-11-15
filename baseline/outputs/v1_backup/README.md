# v1 model outputs (backup)

These are the shared outputs exactly as they were committed with the v1 model (logistic
regression on the nine NDVI features, C = 1, threshold 0.5) before the switch to model v2
(candidate H from `baseline/model_v2/`: the same nine features plus four harvest-timing
features, L1 logistic regression, C chosen by field-grouped inner CV, threshold 0.5).

Paths below are relative to `baseline/outputs/`, except `web_snapshot/`, which mirrors the
top-level JSON files of `web/public/snapshot/` (the per-field `series_*.json` files and chips
do not depend on the model and are not copied).

Nothing reads this folder at run time. It exists so reverting is trivial and so tests can
check that the v1 code path still reproduces these files.

## Switch back to v1

Either restore the files:

```sh
cp -r baseline/outputs/v1_backup/{features.csv,heldout_predictions.csv,metrics.json,results.md,missing_features.csv,asof.json,feature_contributions.csv} baseline/outputs/
cp baseline/outputs/v1_backup/unlabeled/* baseline/outputs/unlabeled/
cp baseline/outputs/v1_backup/estimate_2025/* baseline/outputs/estimate_2025/
cp baseline/outputs/v1_backup/decline_rule/* baseline/outputs/decline_rule/
cp baseline/outputs/v1_backup/web_snapshot/*.json web/public/snapshot/
```

or regenerate with the v1 code path. Set `MODEL_VERSION = 'v1'` in `baseline/model_version.py`
(or export `HTH_MODEL_VERSION=v1` for one shell) and run, from the repo root with the analysis
environment:

```sh
python baseline/run_baseline.py evaluate          # features.csv, heldout_predictions.csv, metrics.json, results.md
python -m harvest.export_asof                     # asof.json (follows the saved metrics.json)
python baseline/export_contributions.py           # feature_contributions.csv
cd baseline && python unlabeled_calls.py predict && cd ..
python baseline/export_unlabeled_imagery.py observations
python baseline/estimate_2025/estimate.py         # 2025 satellite check + benchmark
python baseline/decline_rule_baseline.py          # decline-rule comparison on the same rows
python web/scripts/build-real-snapshot.py         # static web snapshot
```

`run_baseline.build_model()` is the v1 pipeline and was never changed; every script keeps a
v1 branch that writes the same columns and prose as before.
