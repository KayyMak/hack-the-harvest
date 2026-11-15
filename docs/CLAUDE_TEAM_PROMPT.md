# Claude Code lead-agent prompt

Use Claude Code signed in with the teammate's Claude Max account. Subagents
share that account's usage limits. A separate Anthropic API key can select API
billing instead. Ordinary subagents are sufficient; experimental Agent Teams
are not required for these tasks.

While the publication PR is open, check out `feat/ml-experiments` before
starting. After it is merged, use current `main`. Paste the following prompt
into an interactive Claude Code session in the repository root.

---

Act as the engineering lead for KayyMak/hack-the-harvest. Use up to three
focused subagents in parallel. Give them bounded tasks, explicit acceptance
criteria, and separate ownership. Do not create a recursive agent hierarchy or
build a new orchestration service. You own coordination, validation, and the
final synthesis; do not merely relay unverified worker claims.

First read AGENTS.md, START_HERE.md, docs/ARCHITECTURE.md,
docs/ML_EXPERIMENTS.md, data/README.md, baseline/SCENE_FILTER_EXPERIMENT.md,
baseline/NEMOTRON_COMPARISON.md, and their referenced measured results. Inspect
current branches, PRs, and local changes before editing. Teammates have already
merged as-of support, submission tooling, and extra Kraatz labels; reuse that
work rather than rebuilding it. Coordinate with the separate Codex PR reviewer.

## Current facts to preserve

- Original BARC baseline: 44 field-years on 34 fields, 32 Grain / 12 Silage.
  Silage F1 0.7000, recall 0.5833, balanced accuracy 0.7760.
- Frozen numerical Nemotron comparison: 44/44 valid responses, F1 0.5882,
  recall 0.4167, balanced accuracy 0.7083. This was in-context prediction, not
  fine-tuning, image inference, or a demonstrated tool-calling workflow.
- Separate no-scene-cloud-cutoff experiment: same features/model setup/folds,
  306 additional usable field-dates, no read failures, F1 0.8182, recall 0.7500,
  balanced accuracy 0.8594. Original runs remain unchanged.
- Fields 231 and 252 / 2022 were corrected. Fields 24 / 2021, 327 / 2021,
  254 / 2023, and 323 / 2023 remain wrong. Field 323's Silage probability
  worsened despite better coverage. Expected-acreage errors improved in 2022
  but worsened in 2021 and 2023. Do not report uniform improvement.
- These are exploratory results on already-inspected BARC data. More years
  from the same fields are not an independent new-farm test.
- The judges provided 2025 Quick Stats Grain/Silage harvested-acre totals at
  STATE/NATIONAL levels. A frozen CSV and source/hash metadata are under
  data/reference/. The exact scored geographies and error formula remain
  unconfirmed. These aggregate targets are never individual-field labels.

## Worker 1: data provenance and label audit

Begin read-only. Inspect kraatz_labels.csv, build_kraatz_labels.py, data/README.md,
and the two source ZIPs already in data/. Verify how harvest records, planting
records, conflicts, polygon matches, and overlaps with the original BARC labels
are handled. Do not treat planned planting use as equivalent to confirmed harvest
use, or model agreement as label verification.

Deliver a source-cited inventory: available field-years by label/source/year,
duplicate/conflicting field-years, polygon linkage confidence, and unresolved
questions. Distinguish usable training candidates from weaker/uncertain labels
and possible independent evaluation data. If independent labels are still
needed, search original public sources and report evidence/coverage/license;
never invent a harvest label from an AI summary. Do not silently modify labels
or start satellite extraction. Explain that 2017-2020 features are not already
available merely because labels exist.

Acceptance: every claimed label source is traceable; counts are reproducible;
overlapping years/fields are identified; uncertain rows remain explicit.

## Worker 2: judge-format benchmark adapter and scoring

Use an isolated Git worktree and a unique role/claude-benchmark branch. Inspect
the existing Quick Stats reader, harvest modules, and tests first. Reuse or
extend the responsible layer. Work toward a small offline adapter/evaluator
for data/reference/quickstats_2025_judges.csv and aggregate prediction files.

Support the real headers, including Geo Level, Program, State, Year, Data Item,
Domain, Value, and CV (%). Match year/geography/crop use and harvested ACRES
explicitly. Keep STATE, NATIONAL, and OTHER STATES aggregate rows distinct;
do not double-count them. Preserve suppression and missing values as unknown,
never zero. Clearly report unmatched/missing prediction rows.

Report signed error, absolute error, and relative error where the denominator
is defined. Keep the scoring formula selectable only if actual judge guidance
requires it; do not invent a final contest metric. A labeled-BARC subtotal is
not a Maryland statewide prediction. No statewide 2025 predictions currently
exist: test with clearly synthetic fixtures instead of fabricating estimates.
Do not tune outputs to reproduce the judges' totals.

Acceptance: focused tests cover actual CSV headers, both crop uses, state versus
national matching, missing/suppressed values, duplicate rows, and unit/scope
mismatches. No model fitting or satellite access occurs inside API requests.
Coordinate public response changes and update matching TypeScript types/tests
if an API change is necessary. Keep unrelated backend/UI work untouched.

## Worker 3: independent ML/evaluation review

Begin read-only. Audit the new experiment scripts and saved evidence under
baseline/outputs/{nemotron,experiments,diagnostics}. Check all years of each
field stay in one fold, held-out labels/IDs/predictions do not enter Nemotron
target prompts, preprocessing is fitted on training folds, and comparison rows
and acreage weights are consistent. Check partial clear coverage, duplicate
processing entries, temporal gaps, as-of availability, and provenance hashes.

Run the offline tests in the configured analysis environment when available.
No paid inference or satellite downloads are required to audit these artifacts.
Return prioritized findings with file/line evidence, reproducible checks,
uncertainty, and the smallest appropriate fixes. Recommend at most one next
prespecified timing/coverage-feature experiment; do not repeatedly tune against
these already-inspected error cases. Do not rewrite the saved baseline or prompt.

Acceptance: claims are supported by actual files/checks; failures and limits
are explicit; a proposed new independent test is distinguished from more BARC
training years. Agent consensus is not ground truth.

## Lead responsibilities

- Keep all source notebooks, original polygons/GeoJSON, data_sources.md, and
  root README unchanged. Never rewrite source hashes to hide changes. Preserve
  snapshot bytes; .gitattributes protects fingerprinted outputs/reference data.
- Keep every year of a field grouped across both original and added datasets.
  Blank labels remain unknown. Keep reference labels separate from predictions.
- Let read-only workers return evidence before assigning fixes. Give any writing
  worker its own worktree/branch and disjoint files. Identify PR dependencies
  when work is based on feat/ml-experiments before it merges.
- Validate worker output and run relevant checks. Create scoped reviewable PRs
  using type(scope): imperative summary commits. Do not merge PRs, force-push,
  overwrite teammate changes, or add AI signatures/co-author trailers.
- Use cached evidence. Do not run GPU jobs, buy services, change authentication,
  or repeat NVIDIA/other hosted inference without an explicitly authorized need.
  No credentials are needed for the offline work above.
- Report completed deliverables, tests actually run, findings, remaining blockers,
  and the next concrete task. Do not claim data/model success from plausible text.

---

This is a development workflow. Nemotron orchestration inside the application
is a separate task; the existing Python agent-tool library is the starting
point if that task is later assigned.
