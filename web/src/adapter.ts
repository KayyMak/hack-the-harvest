/** Adapt the published FastAPI contract to the dashboard's display types. */
import type { FeatureCollection, Geometry } from 'geojson'
import type { ConvergencePoint, Estimate2025, Estimate2025Summary, EstimateAcres, EstimateCrop, EstimateErrors, EvaluateResponse, FieldsResponse, Label, ModelSelection, Pred, RollupResponse, SeriesResponse, Forecast2025, Forecast2025Summary, ForecastCrop, NassAcres, UnlabeledCallView, UnlabeledYearView } from './types'

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
  /** present when the saved model is v2 */
  model_version?: 'v1' | 'v2' | null
  model?: string | null
  selection?: ModelSelection | null
  v1_logistic_same_split?: SavedMetrics | null
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

/** GET /api/baseline/contributions: per-field signal breakdown of the saved season-end calls. */
export interface SavedContribution {
  field_id: number
  year: number
  /** null = saved season-end model; otherwise the as-of date of a saved mid-season call */
  as_of: string | null
  feature: string
  value: number | null
  contribution: number
}

/** The six strongest signals for one field-year, in the dashboard's FeatureContribution shape. */
function topFeatures(rows: SavedContribution[] | undefined): string {
  if (!rows?.length) return '[]'
  const top = [...rows].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution)).slice(0, 6)
  return JSON.stringify(top.map((r) => ({ name: r.feature, value: r.value ?? Number.NaN, contrib: r.contribution })))
}

export function adaptPredictions(data: SavedPrediction[], year: number, asOf: string,
  contributions: SavedContribution[] = []): Pred[] {
  if (asOf !== `${year}-11-30`) throw new Error('Only saved end-of-season predictions are available.')
  const byField = groupContributions(contributions, null)
  return data.filter((p) => p.year === year).map((p) => ({
    OBJECTID: p.field_id, year: p.year, as_of: asOf, p_silage: p.silage_probability,
    class: p.predicted_label, abstain: false, top_features: topFeatures(byField.get(`${p.field_id}:${p.year}`)),
  }))
}

/** Contributions for one model (season end when asOf is null), keyed "field:year". */
function groupContributions(contributions: SavedContribution[], asOf: string | null) {
  const byField = new Map<string, SavedContribution[]>()
  for (const c of contributions) {
    if ((c.as_of ?? null) !== asOf) continue
    const key = `${c.field_id}:${c.year}`
    byField.set(key, [...(byField.get(key) ?? []), c])
  }
  return byField
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
export function adaptAsOfPredictions(data: SavedAsOf, year: number, asOf: string,
  contributions: SavedContribution[] = []): Pred[] {
  const entry = data.dates.find((d) => d.year === year && d.as_of === asOf)
  if (!entry) throw new Error(`No saved calls for ${asOf}.`)
  const byField = groupContributions(contributions, asOf)
  return [
    ...entry.predictions.map((p): Pred => ({
      OBJECTID: p.field_id, year, as_of: asOf, p_silage: p.silage_probability,
      class: p.predicted_label, abstain: false, top_features: topFeatures(byField.get(`${p.field_id}:${year}`)),
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
  years: {
    year: number
    reference_silage_acres: number
    expected_silage_acres: number
    expected_silage_acres_95ci: [number, number]
    cv_percent: number | null
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
    model_name: data.model ?? 'Logistic regression on NDVI', balanced_accuracy: m.balanced_accuracy,
    baseline: { ...data.always_grain, name: 'Always grain' },
    model_version: data.model_version ?? 'v1',
    ...(data.selection ? { selection: data.selection } : {}),
    ...(data.v1_logistic_same_split ? { v1_same_split: data.v1_logistic_same_split } : {}),
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
export interface SavedEstimate2025 {
  summary: Estimate2025Summary
  benchmark: Record<string, unknown> | null
}

const finite = (...values: unknown[]) => values.every((v) => typeof v === 'number' && Number.isFinite(v))

/**
 * The saved 2025 Maryland estimate. The headline is the calibrated estimate, or the raw one when
 * calibration is unavailable. An incomplete file is an error, never a zero.
 */
export function adaptEstimate2025(data: SavedEstimate2025): Estimate2025 {
  const s = data?.summary
  const shown = s?.calibrated ?? s?.raw
  const errors = s?.calibrated ? s.benchmark?.calibrated : s?.benchmark?.raw
  const crop = (name: 'silage' | 'grain', block: EstimateAcres, err: EstimateErrors | null | undefined) => {
    const acres = block?.[`${name}_acres`]
    const ci = block?.[`${name}_acres_95ci`]
    const e = err?.[name]
    if (!finite(acres, ci?.[0], ci?.[1], e?.error, e?.relative_error)) throw new Error('The saved 2025 estimate is incomplete.')
    return { acres, ci, error: e!.error, relative_error: e!.relative_error }
  }
  if (!s || !shown || !s.raw || !finite(s.nass_2025?.silage_acres, s.nass_2025?.grain_acres)) throw new Error('The saved 2025 estimate is incomplete.')
  const both = (name: 'silage' | 'grain'): EstimateCrop => ({
    ...crop(name, shown, errors), nass_acres: s.nass_2025[`${name}_acres`], raw: crop(name, s.raw, s.benchmark?.raw),
  })
  return { summary: s, benchmark: data.benchmark ?? null, calibrated: s.calibrated != null, silage: both('silage'), grain: both('grain') }
}

export interface SavedForecast2025 {
  summary: Forecast2025Summary
  nass_2025: { source: string; maryland: NassAcres; us: NassAcres } | null
}

function forecastCrop(value: number | null | undefined, low: number | null | undefined, high: number | null | undefined, nass: number | null | undefined): ForecastCrop {
  if (!finite(value)) throw new Error('The saved 2025 forecast is incomplete.')
  const ref = finite(nass) && (nass as number) > 0 ? (nass as number) : null
  const v = value as number
  return {
    value: v, low: finite(low) ? (low as number) : null, high: finite(high) ? (high as number) : null,
    nass: ref, error: ref == null ? null : v - ref, relative_error: ref == null ? null : (v - ref) / ref,
  }
}

/** The graded 2025 forecast for Maryland and the US, next to NASS 2025 acres when they could be read. */
export function adaptForecast2025(data: SavedForecast2025): Forecast2025 {
  const s = data?.summary
  const md = s?.states?.find((row) => row.state === 'MARYLAND')
  if (!s || !md || !s.us) throw new Error('The saved 2025 forecast has no Maryland row.')
  const nass = data.nass_2025
  return {
    summary: s, nass_source: nass?.source ?? null,
    maryland: {
      silage: forecastCrop(md.silage, md.silage_low, md.silage_high, nass?.maryland.silage),
      grain: forecastCrop(md.grain, md.grain_low, md.grain_high, nass?.maryland.grain),
    },
    us: {
      silage: forecastCrop(s.us.silage, s.us.silage_low, s.us.silage_high, nass?.us.silage),
      grain: forecastCrop(s.us.grain, s.us.grain_low, s.us.grain_high, nass?.us.grain),
    },
    backtest_years: Object.keys(s.backtest?.silage?.us_total ?? {}).sort(),
  }
}

/** GET /api/unlabeled: saved model calls on blank-label field-years that CDL marks as corn. */
export interface SavedUnlabeled {
  caveat: string
  by_year: {
    year: number
    field_years_called: number
    total_acres: number
    called_silage: number
    called_grain: number
    called_silage_acres: number
    no_usable_dates: number
    expected_silage_acres: number
    expected_silage_acres_95ci: [number, number]
  }[]
  calls: {
    field_id: number
    year: number
    acres: number | null
    corn_share: number
    status: 'called' | 'no_usable_dates'
    predicted_label: Label | null
    silage_probability: number | null
  }[]
}

/**
 * Unlabeled calls are season-end calls: show them only when the selected date is Nov 30 of that year,
 * so a mid-season view never implies a mid-season result for these fields.
 */
export function unlabeledCallsAt(view: UnlabeledYearView | null | undefined, year: number, asOf: string): UnlabeledCallView[] {
  return view && view.year === year && asOf === `${year}-11-30` ? view.calls : []
}

/** One year's unlabeled calls. Field-years without usable satellite dates are counted, never called. */
export function adaptUnlabeled(data: SavedUnlabeled, year: number): UnlabeledYearView {
  const y = data.by_year.find((row) => row.year === year)
  if (!y) throw new Error(`No saved unlabeled calls for ${year}.`)
  const calls = data.calls
    .filter((c) => c.year === year && c.status === 'called' && c.predicted_label && c.silage_probability != null)
    .map((c) => ({ OBJECTID: c.field_id, label: c.predicted_label as Label, p_silage: c.silage_probability as number,
      acres: c.acres, corn_share: c.corn_share }))
  return {
    year, corn_field_years: y.field_years_called + y.no_usable_dates, called: y.field_years_called,
    acres: y.total_acres, silage: y.called_silage, grain: y.called_grain, silage_acres: y.called_silage_acres,
    expected_silage_acres: y.expected_silage_acres, ci: y.expected_silage_acres_95ci,
    no_usable_dates: y.no_usable_dates, caveat: data.caveat, calls,
  }
}
