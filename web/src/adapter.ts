/** Adapt the published FastAPI contract to the dashboard's display types. */
import type { FeatureCollection, Geometry } from 'geojson'
import type { BarcRollupYear, BaselineSummary, ConvergencePoint, EvaluateResponse, FieldsResponse, Label, Pred, RollupResponse, SeriesResponse } from './types'

export interface SavedPrediction {
  field_id: number
  year: number
  reference_label: Label
  predicted_label: Label
  silage_probability: number
  fold: number
  valid_dates: number
}

interface SavedMetrics {
  n: number
  silage_precision: number
  silage_recall: number
  balanced_accuracy: number
  brier_score: number
  confusion_matrix: number[][]
  matrix_order: Label[]
}

export interface SavedSummary {
  protocol: string
  evaluated_field_years: number
  evaluated_fields: number
  excluded_field_years: number
  read_errors: number
  logistic: SavedMetrics
  always_grain: SavedMetrics
}

export type SavedFields = FeatureCollection<Geometry, {
  field_id: number
  field: string | null
  acres: number | null
  reference_2021: Label | null
  reference_2022: Label | null
  reference_2023: Label | null
}>

export function adaptFields(data: SavedFields, year: number): FieldsResponse {
  const reference = `reference_${year}` as 'reference_2021' | 'reference_2022' | 'reference_2023'
  return {
    type: 'FeatureCollection',
    features: data.features.map((f) => ({
      type: 'Feature', geometry: f.geometry,
      properties: { OBJECTID: f.properties.field_id, label: f.properties[reference] ?? null,
        FIELD: f.properties.field ?? undefined, ACRES: f.properties.acres == null ? undefined : Math.round(f.properties.acres * 10) / 10 },
    })),
  }
}

export function adaptPredictions(data: SavedPrediction[], year: number, asOf: string): Pred[] {
  if (asOf !== `${year}-11-30`) throw new Error('Only saved end-of-season predictions are available.')
  return data.filter((p) => p.year === year).map((p) => ({
    OBJECTID: p.field_id, year: p.year, as_of: asOf, p_silage: p.silage_probability,
    class: p.predicted_label, abstain: false, top_features: '[]',
  }))
}

/** GET /api/baseline/asof: calls saved once by `python -m harvest.export_asof`. */
export interface SavedAsOf {
  scope: string
  method: string
  years: number[]
  month_days: string[]
  dates: {
    year: number
    as_of: string
    mode: string
    features: string[]
    predictions: { field_id: number; predicted_label: Label; silage_probability: number; reference_label: Label }[]
    pending_field_ids: number[]
  }[]
  pooled: { month_day: string; field_years: number; decided: number; share_decided: number | null;
    accuracy_decided: number | null; balanced_accuracy: number | null; silage_recall: number | null;
    confusion_matrix: number[][] | null }[]
}

/** One year's calls on one saved date. A date that was never saved is an error, never a guess. */
export function adaptAsOfPredictions(data: SavedAsOf, year: number, asOf: string): Pred[] {
  const entry = data.dates.find((d) => d.year === year && d.as_of === asOf)
  if (!entry) throw new Error(`No saved calls for ${asOf}.`)
  return [
    ...entry.predictions.map((p): Pred => ({
      OBJECTID: p.field_id, year, as_of: asOf, p_silage: p.silage_probability,
      class: p.predicted_label, abstain: false, top_features: '[]',
    })),
    ...entry.pending_field_ids.map((id): Pred => ({
      OBJECTID: id, year, as_of: asOf, p_silage: null, class: 'Pending', abstain: false, top_features: '[]',
    })),
  ]
}

/** Scores pooled over all saved years, dated in `year` so the selected as-of date can be marked. */
export function adaptConvergence(data: SavedAsOf, year: number): ConvergencePoint[] {
  return data.pooled.filter((p) => p.share_decided != null).map((p) => ({
    as_of: `${year}-${p.month_day}`, share_decided: p.share_decided ?? 0,
    acc_decided: p.accuracy_decided ?? 0, bal_acc: p.balanced_accuracy,
  }))
}

export interface SavedRollup {
  scope: string
  method: string
  years: {
    year: number
    field_years: number
    total_acres: number
    reference_silage_acres: number
    expected_silage_acres: number
    expected_silage_acres_95ci: [number, number]
    cv_percent: number | null
    adjusted_silage_acres: number | null
  }[]
}

/** The saved roll-up covers labeled BARC fields only: compare it with their labels, never the Census. */
export function adaptRollup(data: SavedRollup, year: number): RollupResponse {
  const y = data.years.find((row) => row.year === year)
  if (!y) throw new Error(`No saved roll-up for ${year}.`)
  return {
    year, region: 'Labeled BARC fields', acres: y.expected_silage_acres, ci: y.expected_silage_acres_95ci,
    cv_pct: y.cv_percent, census_acres: y.reference_silage_acres, csv_url: 'api/baseline/rollup.csv',
    reference_name: 'BARC reference labels',
    note: `Full-season estimate as of November 30, ${year}; it does not change with the selected mid-season date. Labeled BARC fields only, scored held out by field. This is not a Maryland statewide estimate and is not compared with the Census.`,
  }
}

function wilson(k: number, n: number) {
  if (!n) return { value: 0, lo: 0, hi: 0 }
  const z = 1.959964
  const p = k / n
  const d = 1 + z * z / n
  const c = (p + z * z / (2 * n)) / d
  const h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
  return { value: p, lo: Math.max(0, c - h), hi: Math.min(1, c + h) }
}

export function adaptSummary(data: SavedSummary, convergence: ConvergencePoint[] = []): EvaluateResponse {
  const m = data.logistic
  const cm = m.confusion_matrix
  const perClass = (label: Label) => {
    const i = m.matrix_order.indexOf(label)
    const support = cm[i].reduce((a, b) => a + b, 0)
    const called = cm.reduce((a, row) => a + row[i], 0)
    return { precision: wilson(cm[i][i], called), recall: wilson(cm[i][i], support), support }
  }
  return {
    split: 'field', split_label: 'held out by field', protocol: data.protocol,
    labels: m.matrix_order, confusion: cm,
    per_class: { Grain: perClass('Grain'), Silage: perClass('Silage') },
    convergence, abstained: data.excluded_field_years,
    n_evaluated: data.evaluated_field_years, n_fields: data.evaluated_fields,
    model_name: 'Logistic regression on NDVI', balanced_accuracy: m.balanced_accuracy,
    baseline: { ...data.always_grain, name: 'Always grain' },
  }
}

export function adaptSeries(data: { date: string; ndvi: number | null; status: string }[], id: number, year: number): SeriesResponse {
  return { OBJECTID: id, year, decline_date: null,
    points: data.filter((p) => p.status === 'ok' && p.ndvi != null)
      .map((p) => ({ date: p.date, ndvi: p.ndvi, ndti: null })) }
}

/** Leaflet data is immutable; remount when the year's reference labels change. */
export function fieldLayerKey(data: FieldsResponse): string {
  return data.features.map((f) => `${f.properties.OBJECTID}:${f.properties.label ?? ''}`).join('|')
}

/** Scores for one set of held-out rows, in the same shape as the saved metrics. */
function score(rows: { truth: Label; call: Label; p: number }[]): BaselineSummary {
  const order: Label[] = ['Grain', 'Silage']
  const cm = order.map((t) => order.map((c) => rows.filter((r) => r.truth === t && r.call === c).length))
  const [[gg, gs], [sg, ss]] = cm
  const recallG = gg + gs ? gg / (gg + gs) : 0
  const recallS = sg + ss ? ss / (sg + ss) : 0
  return {
    n: rows.length,
    silage_precision: gs + ss ? ss / (gs + ss) : 0,
    silage_recall: recallS,
    balanced_accuracy: (recallG + recallS) / 2,
    brier_score: rows.length ? rows.reduce((a, r) => a + (r.p - (r.truth === 'Silage' ? 1 : 0)) ** 2, 0) / rows.length : 0,
    confusion_matrix: cm,
  }
}

/**
 * Per-year model vs always-grain scores, computed from the same saved held-out predictions
 * (the public summary route only carries the pooled numbers).
 */
export function byYearFromPredictions(data: SavedPrediction[]): NonNullable<EvaluateResponse['by_year']> {
  const out: NonNullable<EvaluateResponse['by_year']> = {}
  for (const year of [...new Set(data.map((p) => p.year))].sort()) {
    const rows = data.filter((p) => p.year === year)
    out[String(year)] = {
      model: score(rows.map((p) => ({ truth: p.reference_label, call: p.predicted_label, p: p.silage_probability }))),
      baseline: { ...score(rows.map((p) => ({ truth: p.reference_label, call: 'Grain' as Label, p: 0 }))), name: 'Always grain' },
    }
  }
  return out
}

/** The saved BARC-only acre roll-up for one year (labeled BARC fields; not a statewide estimate). */
export function adaptBarcRollup(data: SavedRollup, year: number): BarcRollupYear | null {
  const y = data.years.find((r) => r.year === year)
  if (!y) return null
  return {
    year, scope: data.scope, method: data.method, field_years: y.field_years, total_acres: y.total_acres,
    labeled_silage_acres: y.reference_silage_acres, expected_silage_acres: y.expected_silage_acres,
    ci: y.expected_silage_acres_95ci, cv_pct: y.cv_percent, adjusted_silage_acres: y.adjusted_silage_acres,
  }
}
