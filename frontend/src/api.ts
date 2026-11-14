// Keep in sync with backend/app/schemas.py; /openapi.json is authoritative.
export type HarvestType = 'Grain' | 'Silage';

export interface Metrics {
  n: number;
  silage_precision: number;
  silage_recall: number;
  silage_f1: number;
  false_positive_rate: number | null;
  balanced_accuracy: number;
  brier_score: number;
  confusion_matrix: number[][];
  matrix_order: HarvestType[];
  matrix_rows: string;
  matrix_columns: string;
}

export interface BaselineSummary {
  protocol: string;
  evaluated_field_years: number;
  evaluated_fields: number;
  excluded_field_years: number;
  read_errors: number;
  cloud_or_nodata_rejections: number;
  missing_feature_counts: Record<string, number>;
  logistic: Metrics;
  always_grain: Metrics;
}

export interface Prediction {
  field_id: number;
  year: number;
  reference_label: HarvestType;
  predicted_label: HarvestType;
  silage_probability: number;
  fold: number;
  valid_dates: number;
}

export interface BarcField {
  field_id: number;
  farm: string | null;
  field: string | null;
  acres: number | null;
}

export interface Observation {
  date: string;
  ndvi: number | null;
  clear_fraction: number | null;
  scene_cloud_percent: number | null;
  status: string;
}

export interface YearRollup {
  year: number;
  field_years: number;
  total_acres: number;
  reference_silage_acres: number;
  predicted_silage_acres: number;
  expected_silage_acres: number;
  expected_silage_acres_95ci: [number, number];
  cv_percent: number | null;
  predicted_silage_share: number;
  adjusted_silage_share: number | null;
  adjusted_silage_acres: number | null;
  adjustment_rates: Record<string, number | null>;
  missing_acres_field_years: number;
}

export interface Rollup {
  scope: string;
  method: string;
  years: YearRollup[];
}

export interface QuickStatsRow {
  year: number | null;
  state: string | null;
  item: string | null;
  value: number | null;
  suppressed: boolean;
}

async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  if (!response.ok) throw new Error(`Results are unavailable (HTTP ${response.status}).`);
  return response.json() as Promise<T>;
}

export async function loadBaseline(signal: AbortSignal) {
  const [summary, predictions] = await Promise.all([
    get<BaselineSummary>('/api/baseline/summary', signal),
    get<Prediction[]>('/api/baseline/predictions', signal),
  ]);
  return { summary, predictions };
}

export const loadFields = (signal: AbortSignal) => get<BarcField[]>('/api/fields', signal);
export const loadRollup = (signal: AbortSignal) => get<Rollup>('/api/baseline/rollup', signal);
export const loadQuickStats = (signal: AbortSignal, state = 'MARYLAND') =>
  get<QuickStatsRow[]>(`/api/quickstats?state=${encodeURIComponent(state)}`, signal);
export const loadObservations = (fieldId: number, year: number, signal: AbortSignal) =>
  get<Observation[]>(`/api/fields/${fieldId}/observations?year=${year}`, signal);

export interface TraceStep {
  ts: string;
  run_id: string;
  step: number;
  [key: string]: unknown;
}

export async function startAgentRun(query: string): Promise<{ run_id: string }> {
  const response = await fetch('/api/agent/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });
  if (!response.ok) throw new Error(`Agent is unavailable (HTTP ${response.status}).`);
  return response.json() as Promise<{ run_id: string }>;
}
export const loadTrace = (runId: string, signal: AbortSignal) =>
  get<TraceStep[]>(`/api/agent/trace/${encodeURIComponent(runId)}`, signal);
