# Work breakdown

> **Note:** the submitted model is now model v2 (see `baseline/model_v2/results.md`); v1 numbers below are historical.

How the experiment work after the first baseline was split into three workstreams, each with its own branch,
files and acceptance criteria. Read `ENGINEERING.md`, `START_HERE.md`, `docs/ARCHITECTURE.md`,
`docs/ML_EXPERIMENTS.md`, `data/README.md`, `baseline/SCENE_FILTER_EXPERIMENT.md` and
`baseline/NEMOTRON_COMPARISON.md` first.

## Facts every workstream preserves

- Original BARC baseline: 44 field-years on 34 fields, 32 Grain / 12 Silage. Silage F1 0.7000, recall 0.5833,
  balanced accuracy 0.7760.
- Frozen Nemotron in-context comparison: 44/44 valid responses, F1 0.5882, recall 0.4167, balanced accuracy 0.7083.
  This was in-context prediction, not fine-tuning, image inference, or a tool-calling workflow.
- No-scene-cloud-cutoff experiment: same features, model and folds, 306 more usable field-dates, F1 0.8182, recall
  0.7500, balanced accuracy 0.8594. The original runs remain unchanged.
- Fields 231 and 252 / 2022 were corrected; 24 / 2021, 327 / 2021, 254 / 2023 and 323 / 2023 remain wrong.
  Expected-acreage errors improved in 2022 but worsened in 2021 and 2023. No uniform improvement is claimed.
- These are exploratory results on already-inspected BARC data; more years from the same fields are not an
  independent new-farm test.
- The judges' 2025 Quick Stats grain and silage harvested-acre totals (STATE and NATIONAL) are frozen under
  `data/reference/` with source and hash metadata. They are aggregate targets, never field labels.

## Workstream 1: data provenance and label audit

Read-only first. Inspect `kraatz_labels.csv`, `build_kraatz_labels.py`, `data/README.md` and the two source ZIPs in
`data/`. Check how harvest records, planting records, conflicts, polygon matches and overlaps with the original BARC
labels are handled. Planned planting use is not confirmed harvest use, and model agreement is not label verification.

Deliver a source-cited inventory: field-years by label, source and year; duplicates and conflicts; polygon-link
confidence; open questions. Separate usable training candidates from weaker labels and possible independent
evaluation data. Never invent a label. 2017-2020 features do not exist just because labels do.

Acceptance: every label source is traceable; counts are reproducible; overlapping years and fields are identified;
uncertain rows stay explicit.

## Workstream 2: judge-format benchmark and scoring

Build a small offline scorer for `data/reference/quickstats_2025_judges.csv` and aggregate prediction files
(now `harvest/benchmark.py`). Support the real headers (Geo Level, Program, State, Year, Data Item, Domain, Value,
CV (%)); match year, geography, crop use and harvested ACRES explicitly; keep STATE, NATIONAL and OTHER STATES rows
distinct; keep suppressed and missing values unknown, never zero; report unmatched rows.

Report signed, absolute and relative error where the denominator is defined. Do not invent a contest metric, and do
not tune outputs to the judges' totals.

Acceptance: tests cover the real headers, both crop uses, state versus national matching, missing and suppressed
values, duplicate rows, and unit or scope mismatches.

## Workstream 3: independent ML and evaluation review

Read-only first. Audit the experiment scripts and saved evidence under `baseline/outputs/{nemotron,experiments,
diagnostics}`: all years of a field stay in one fold; held-out labels never enter Nemotron prompts; preprocessing is
fitted on training folds; comparison rows and acreage weights are consistent; coverage gaps, duplicates, as-of
availability and provenance hashes are checked.

Return prioritized findings with file and line evidence, reproducible checks and the smallest fixes. Recommend at
most one next pre-specified experiment, and do not keep tuning against already-inspected error cases.

Acceptance: claims rest on actual files and checks; failures and limits are explicit; a new independent test is kept
distinct from more BARC training years.

## Coordination rules

- Keep the source notebooks, original polygons and GeoJSON, `data_sources.md` and the root README unchanged; never
  rewrite source hashes. Keep every year of a field grouped across original and added data. Blank labels stay unknown.
- Each writing workstream gets its own branch and disjoint files. Run the relevant checks; open scoped PRs with
  `type(scope): imperative summary` commits; do not merge without review or overwrite teammates' changes.
- Use cached evidence: no GPU jobs, paid services or repeated hosted inference without a clear need.
- Report deliverables, checks run, findings, remaining blockers and the next task. Do not claim success without
  evidence.
