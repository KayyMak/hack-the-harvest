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
  cv_pct: number
  census_acres: number
  csv_url: string
  /** what `census_acres` is, when it is not the Census (e.g. BARC reference labels) */
  reference_name?: string
  /** scope caveat shown with the roll-up */
  note?: string
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
