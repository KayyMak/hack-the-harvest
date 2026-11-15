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
}
/** Acres on BARC's own labeled fields: model estimate vs BARC's labels (not statewide). */
export interface BarcRollupYear {
  year: number
  scope: string
  method: string
  field_years: number
  total_acres: number
  labeled_silage_acres: number
  expected_silage_acres: number
  ci: [number, number]
  cv_pct: number | null
  adjusted_silage_acres: number | null
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
