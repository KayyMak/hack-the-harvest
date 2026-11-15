/**
 * API contract types — the ONE place to update when Backend freezes the real
 * shapes in `contracts/`. Everything else imports from here.
 */
import type { Feature, FeatureCollection, Geometry } from 'geojson'

export type Label = 'Grain' | 'Silage'
export type PredClass = Label | 'Pending' | 'Insufficient'

/** GET /fields?year= */
export interface FieldProps {
  OBJECTID: number
  label: Label | null
  ACRES?: number
  FIELD?: string
}
export type FieldFeature = Feature<Geometry, FieldProps>
export type FieldsResponse = FeatureCollection<Geometry, FieldProps>

/** POST /predict {year, as_of} -> Pred[] */
export interface PredictRequest {
  year: number
  as_of: string // ISO date, e.g. "2022-10-12"
}
export interface Pred {
  OBJECTID: number
  year: number
  as_of: string
  p_silage: number | null
  class: PredClass
  abstain: boolean
  /** JSON string of FeatureContribution[] — parse with parseTopFeatures() */
  top_features: string
}
export interface FeatureContribution {
  name: string
  value: number
  /** signed contribution; > 0 pushes toward Silage, < 0 toward Grain */
  contrib: number
}

/** GET /evaluate?split= */
export interface Estimate {
  value: number
  lo: number
  hi: number
}
export interface ClassMetrics {
  precision: Estimate
  recall: Estimate
  support: number
}
export interface ConvergencePoint {
  as_of: string
  share_decided: number
  acc_decided: number
  /** balanced accuracy on decided fields, when the source reports it */
  bal_acc?: number | null
}
export interface EvaluateResponse {
  split: string
  /** order of rows/cols in `confusion` */
  labels: Label[]
  /** rows = true label, cols = predicted label */
  confusion: number[][]
  per_class: Record<Label, ClassMetrics>
  convergence: ConvergencePoint[]
  convergence_error?: string
  abstained: number
  n_evaluated?: number
  /** plain-language validation design, e.g. "held out by field" */
  split_label?: string
  protocol?: string
  n_fields?: number
  model_name?: string
  balanced_accuracy?: number
  /** naive comparison model, e.g. always predicting grain */
  baseline?: BaselineSummary
  by_year?: Record<string, { model: BaselineSummary; baseline: BaselineSummary }>
  /** 'v2' when the saved model is model v2 (absent or 'v1' for the original baseline) */
  model_version?: 'v1' | 'v2'
  /** v2 only: how it was chosen and how far to trust its gain over v1 */
  selection?: ModelSelection
  /** v2 only: the v1 model on the same held-out split, for comparison */
  v1_same_split?: BaselineSummary
}
export interface ModelSelection {
  note: string
  nested_selection_mean_balanced_accuracy: number
  v1_mean_balanced_accuracy_same_seeds: number
  gain_vs_v1_field_bootstrap_95ci: [number, number]
  details: string
}
export interface BaselineSummary {
  name?: string
  n: number
  silage_precision: number
  silage_recall: number
  balanced_accuracy: number
  brier_score: number
  confusion_matrix: number[][]
}

/** GET /rollup?year= */
export interface RollupResponse {
  year: number
  region: string
  acres: number
  ci: [number, number]
  cv_pct: number | null
  census_acres: number
  csv_url: string
  /** what `census_acres` is, when it is not the Census (e.g. BARC reference labels) */
  reference_name?: string
  /** scope caveat shown with the roll-up */
  note?: string
}

/** GET /api/forecast_2025: `summary` is forecast/outputs/summary.json as saved (the graded output). */
export interface ForecastStateRow {
  state: string
  silage: number
  silage_low: number
  silage_high: number
  silage_se: number
  /** null where NASS published no grain area for the state */
  grain: number | null
  grain_low: number | null
  grain_high: number | null
  grain_se: number | null
}
/** Percent errors are already percent (11.5 = 11.5%); coverage is a 0-1 fraction. */
export interface ForecastBacktest {
  state_years: number
  median_abs_pct_error: number
  mean_abs_pct_error: number
  covered_by_95_interval: number
  us_total?: Record<string, { est: number; truth: number; pct_error: number }>
}
export interface Forecast2025Summary {
  method: string
  answer_key_excluded: string
  sources: Record<string, { title: string; released: string | null; url: string }>
  backtest: { silage: ForecastBacktest; grain: ForecastBacktest }
  /** the US total has no published grain range */
  us: { silage: number; silage_se: number; silage_low: number; silage_high: number; grain: number; grain_se: number; grain_low?: number | null; grain_high?: number | null }
  states: ForecastStateRow[]
  convergence: { as_of: string; source: string }[]
}
export interface NassAcres {
  silage: number | null
  grain: number | null
}
/** One forecast figure next to NASS 2025 acres harvested; null comparison when NASS is unavailable. */
export interface ForecastCrop {
  value: number
  low: number | null
  high: number | null
  nass: number | null
  /** forecast - NASS, in acres */
  error: number | null
  /** error / NASS */
  relative_error: number | null
}
export interface Forecast2025 {
  summary: Forecast2025Summary
  nass_source: string | null
  maryland: { silage: ForecastCrop; grain: ForecastCrop }
  us: { silage: ForecastCrop; grain: ForecastCrop }
  /** years of the saved US backtest, e.g. ["2023", "2024"] */
  backtest_years: string[]
}

/** GET /api/estimate_2025: `summary` is baseline/outputs/estimate_2025/summary.json as saved. */
export interface EstimateAcres {
  silage_acres: number
  silage_acres_95ci: [number, number]
  grain_acres: number
  grain_acres_95ci: [number, number]
  silage_share: number
}
/** error = model estimate - NASS, in acres; relative_error = error / NASS */
export interface EstimateError {
  error: number
  relative_error: number
}
export interface EstimateErrors {
  silage: EstimateError
  grain: EstimateError
}
export interface Estimate2025Summary {
  year: number
  state: string
  generated_utc: string
  headline: 'calibrated' | 'raw'
  population: {
    source: string; corn_rule: string; csb_fields_maryland: number; corn_fields_2025: number; corn_acres_2025: number
    /** all Maryland CDL 2025 corn pixels, for context */
    cdl_corn_acres_2025?: number
  }
  sample: {
    seed: number; stratified_by: string; requested_fields: number
    sampled_fields: number; sampled_acres: number
    scored_fields: number; scored_acres: number
    skipped_fields: number; skipped_reasons: Record<string, number>
    min_valid_dates: number
    /** the sample is drawn in random batches; the estimate uses whole finished batches only */
    batches_used?: number[]
    batches_drawn?: number
  }
  model: {
    name: string; training_field_years: number; features: string[]; threshold: number
    training_silage_field_years?: number
    sample_fields_called_silage?: number
  }
  raw: EstimateAcres
  /** null when the misclassification adjustment is undefined; the raw numbers are then the headline */
  calibrated: (EstimateAcres & {
    method: string; tpr: number | null; fpr: number | null
    predicted_silage_acre_share?: number
    undefined_bootstrap_draws?: number
  }) | null
  nass_2025: { silage_acres: number; grain_acres: number; source: string }
  benchmark: { raw: EstimateErrors; calibrated: EstimateErrors | null }
  method: string
  limitations: string[]
  sources: { name: string; url: string; accessed: string }[]
}
/** One crop's headline: our model estimate next to NASS survey acres harvested. */
export interface EstimateCrop {
  acres: number
  ci: [number, number]
  nass_acres: number
  error: number
  relative_error: number
  /** the uncalibrated figures, always present */
  raw: { acres: number; ci: [number, number]; error: number; relative_error: number }
}
export interface Estimate2025 {
  summary: Estimate2025Summary
  /** unmodified `python -m harvest.benchmark` report, or null when it was not saved */
  benchmark: Record<string, unknown> | null
  /** false when calibration is unavailable and the headline is the raw estimate */
  calibrated: boolean
  silage: EstimateCrop
  grain: EstimateCrop
}

/** GET /fields/{id}/series?year= */
export interface SeriesPoint {
  date: string
  ndvi: number | null
  ndti: number | null
}
export interface SeriesResponse {
  OBJECTID: number
  year: number
  points: SeriesPoint[]
  decline_date: string | null
}

/** POST /agent/run {query} -> {run_id};  GET /agent/trace/{id} */
export interface AgentRunResponse {
  run_id: string
}
export type AgentNode = 'Analyst' | 'Verifier' | 'Writer' | string
export type TraceType = 'plan' | 'tool_call' | 'observation' | 'flag' | 'report' | string
export interface TraceLine {
  step: number
  node: AgentNode
  type: TraceType
  tool: string | null
  args: Record<string, unknown> | null
  summary: string
}
export interface AgentTraceResponse {
  run_id: string
  status: 'running' | 'done' | 'error'
  lines: TraceLine[]
}

/** public/snapshot/_meta.json — only used in static mode */
export interface SnapshotMeta {
  stub: boolean
  note: string
  years: number[]
  as_of_dates: string[]
  /** real data so far has one call per field-year, at season end */
  season_end_only?: boolean
  has_chips?: boolean
  has_rollup?: boolean
  has_contributions?: boolean
}

export function parseTopFeatures(raw: string | null | undefined): FeatureContribution[] {
  if (!raw) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as FeatureContribution[]) : []
  } catch {
    return []
  }
}

/** GET /api/baseline/convergence (also written to snapshot/convergence_acres.json) */
export interface ConvergenceAcresPoint {
  as_of: string
  mode: string
  field_years: number
  expected_silage_acres: number
  expected_silage_acres_95ci: [number, number]
  cv_percent: number | null
  predicted_silage_acres: number
  reference_silage_acres: number
  total_acres: number
  missing_acres_field_years: number
}
export interface ConvergenceAcres {
  scope: string
  method: string
  years: { year: number; points: ConvergenceAcresPoint[] }[]
}

/** GET /api/market/status: whether the server has an NVIDIA key (the key never reaches the browser). */
export interface MarketStatus {
  configured: boolean
  model: string
  how_to_configure: string
}

/** GET /api/market/outlook?season=&as_of=: a season's timeline known on `as_of` (no LLM). Values are display
 *  strings except `timeline.series`, which carries numbers for the chart. */
export interface MarketOutlook {
  season: number
  as_of: string
  dates: string[]
  sources: Record<string, string>
  timeline: Record<string, unknown>
}

export interface MarketToolCall {
  name: string
  args: Record<string, unknown>
  ok: boolean
  summary: string
}

export interface MarketCitation {
  id: string
  kind: 'tool' | 'doc'
  label: string
  excerpt: string
}

/** POST /api/market/report {year}: Nemotron-written sample report. Every sentence cites a retrieved
 *  tool result or project-document passage; sentences that fail the check are listed in `grounding.ungrounded`. */
export interface MarketReport {
  year: number
  as_of: string
  model: string
  generated_at: string
  mode: 'tools' | 'context'
  markdown: string
  tool_calls: MarketToolCall[]
  citations: MarketCitation[]
  grounding: {
    claims_checked: number
    /** uncited / unsupported / verifier = not backed by our data; miscited = correct figure, wrong source id */
    ungrounded: { text: string; kind: 'uncited' | 'unsupported' | 'miscited' | 'verifier'; reason: string; removed: boolean }[]
    verifier: 'nemotron' | 'unavailable'
  }
  disclaimer: string
  sources: string[]
}

/** One model call on a field-year with no BARC label (CDL says it was corn). Not a reference label. */
export interface UnlabeledCallView {
  OBJECTID: number
  label: Label
  p_silage: number
  acres: number | null
  corn_share: number
}

/** GET /api/unlabeled, narrowed to one year for display. */
export interface UnlabeledYearView {
  year: number
  /** blank-label field-years that CDL marks as corn this year, called or not */
  corn_field_years: number
  called: number
  acres: number
  silage: number
  grain: number
  silage_acres: number
  expected_silage_acres: number
  ci: [number, number]
  no_usable_dates: number
  caveat: string
  calls: UnlabeledCallView[]
}
