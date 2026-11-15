# Numerical Nemotron comparison (protocol v1)

The NVIDIA connection test succeeded with
`nvidia/nemotron-3.5-super-vl-120b-a12b`. The comparison uses its hosted API and
does not launch a Brev instance or fine-tune the model. It uses the same nine
numerical predictors as logistic regression, without image inputs.

Run these from the project root in the **same terminal** where
`NVIDIA_API_KEY` is set. Python's standard library is sufficient; no installation
or changes to the existing baseline are needed.

```powershell
python baseline/compare_nemotron.py pilot
python baseline/compare_nemotron.py run
```

The pilot requests one field-year (the first saved row: field 1 / 2021). Its
gate checks API access and valid Grain/Silage JSON, not whether its prediction
is correct. Do not revise the prompt to improve this example's accuracy.
The full run makes up to 43 additional requests after a successful pilot.
Successful responses are cached and reused; rerunning does not repeat them.
Requests are sequential. A network/HTTP failure stops new requests and leaves
unprocessed rows explicitly pending. After resolving the failure or waiting
for quota availability, retry failed records with:

```powershell
python baseline/compare_nemotron.py run --retry-failures
```

## Inputs and validation

- Saved `heldout_predictions.csv` supplies nine raw features, labels, and fold
  assignments. Split membership is checked against `metrics.json`.
- All years of a field stay together. Every prompt includes labeled examples
  from the training fold only. All fields in the held-out fold are excluded.
- The target prompt includes only its numerical features, never its reference
  label, ID, year, existing probability, or logistic regression prediction.
- Missing features use training-fold medians, with zero for wholly missing
  training columns, matching the baseline imputation rule. Numerical features
  retain their original units; the language model does not need the logistic
  regression's standard scaling transform.
- The system prompt and generation parameters are fixed before evaluation.
  Temperature is 0, seed 42, thinking disabled, maximum answer length 128 tokens.
- This is in-context prediction using a pretrained model. It is not supervised
  parameter training or a test of satellite-image interpretation.

## Outputs and reproducibility

All new artifacts go to `baseline/outputs/nemotron/`:

- `protocol.json`: frozen prompt, model ID, feature list, parameters, input hashes.
- `responses/<field>_<year>.json`: request and its hash, raw answer, parsed
  prediction or error, training field IDs, imputation values, latency, and token
  usage when NVIDIA supplies it. Authorization headers/keys are never stored.
- `predictions.csv`: reference labels, both predictions, folds, and explicit
  pending/error states.
- `metrics.json`: requested classification metrics, confusion matrices,
  coverage/failures, and token usage. Nemotron, logistic regression, and
  always-Grain are compared on exactly the same valid-response rows. The full
  logistic baseline is also retained so partial coverage cannot be hidden.

No model-reported confidence is requested or treated as a calibrated probability.
No monetary cost is assumed; hosted API availability and limits belong to the
NVIDIA account and are separate from Brev compute credits. Prompt/input changes
invalidate the cache rather than mixing experiments. Move old results aside
before starting a deliberately changed protocol. Hosted weights may change
despite an unchanged model ID; reported response model metadata is retained.

The current BARC dataset has already been inspected during development. Treat
this as an exploratory comparison. Reserve independently labeled new fields
before development to obtain a stronger final evaluation. Do not keep changing
the prompt based on these held-out errors and call the result an untouched test.

Offline checks (no API calls):

```powershell
python baseline/test_nemotron_comparison.py
```
