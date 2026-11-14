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
