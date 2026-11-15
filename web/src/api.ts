/**
 * Typed API client.
 *
 * Live mode:   calls the FastAPI backend at VITE_API_URL (default http://localhost:8000).
 * Static mode: VITE_STATIC=1 reads public/snapshot/<name>.json instead (offline fallback,
 *              and the Vercel backup build). Snapshot file names are defined in `snap` below.
 *
 * No API keys ever live in the browser.
 */
import type {
  AgentRunResponse,
  AgentTraceResponse,
  ConvergenceAcres,
  EvaluateResponse,
  FieldsResponse,
  Pred,
  RollupResponse,
  SeriesResponse,
  SnapshotMeta,
  UnlabeledYearView,
} from './types'
import { adaptAsOfPredictions, adaptConvergence, adaptFields, adaptPredictions, adaptRollup, adaptSeries, adaptSummary, adaptUnlabeled } from './adapter.ts'
import type { SavedAsOf, SavedFields, SavedPrediction, SavedRollup, SavedSummary, SavedUnlabeled } from './adapter'

export * from './types.ts'

const env = import.meta.env ?? {}
export const API_URL = (env.VITE_API_URL ?? '').replace(/\/$/, '')
export const STATIC = env.VITE_STATIC === '1'
const SNAPSHOT_BASE = `${env.BASE_URL ?? '/'}snapshot/`

/** Snapshot file names (without .json) for every route. Backend's exporter must match these. */
export const snap = {
  meta: () => '_meta',
  fields: (year: number) => `fields_${year}`,
  predict: (year: number, asOf: string) => `predict_${year}_${asOf}`,
  evaluate: (split: string) => `evaluate_${split}`,
  rollup: (year: number) => `rollup_${year}`,
  series: (id: number, year: number) => `series_${id}_${year}`,
  agentRun: () => 'agent_run',
  agentTrace: (runId: string) => `agent_trace_${runId}`,
  convergenceAcres: () => 'convergence_acres',
  unlabeled: () => 'unlabeled',
}

export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) throw new ApiError(`${init?.method ?? 'GET'} ${url} → ${res.status}`, res.status)
  return (await res.json()) as T
}

const fromSnapshot = <T>(name: string) => getJson<T>(`${SNAPSHOT_BASE}${name}.json`)

const post = <T>(path: string, body: unknown) =>
  getJson<T>(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

const LIVE_YEARS = [2021, 2022, 2023]
const LIVE_MONTH_DAYS = ['08-12', '09-12', '10-12', '11-12', '11-30']
const isSeasonEnd = (year: number, asOf: string) => asOf === `${year}-11-30`
const savedAsOf = () => getJson<SavedAsOf>(`${API_URL}/api/baseline/asof`)

export const api = {
  /** Static mode only: describes the snapshot (stub or real, which years / dates exist). */
  meta: (): Promise<SnapshotMeta | null> =>
    STATIC ? fromSnapshot<SnapshotMeta>(snap.meta()) : Promise.resolve({
      stub: false, note: 'Saved BARC baseline results; held out by field.',
      years: LIVE_YEARS, as_of_dates: LIVE_YEARS.flatMap((y) => LIVE_MONTH_DAYS.map((md) => `${y}-${md}`)),
      season_end_only: false, has_chips: false, has_rollup: true, has_contributions: false,
    }),

  fields: (year: number) =>
    STATIC
      ? fromSnapshot<FieldsResponse>(snap.fields(year))
      : getJson<SavedFields>(`${API_URL}/api/fields.geojson`).then((data) => adaptFields(data, year)),

  predict: (year: number, asOf: string) =>
    STATIC
      ? fromSnapshot<Pred[]>(snap.predict(year, asOf))
      : isSeasonEnd(year, asOf)
        ? getJson<SavedPrediction[]>(`${API_URL}/api/baseline/predictions`).then((data) => adaptPredictions(data, year, asOf))
        : savedAsOf().then((data) => adaptAsOfPredictions(data, year, asOf)),

  /** `year` only dates the season chart; the scores themselves are pooled over all saved years. */
  evaluate: (split = 'strict', year = LIVE_YEARS[1]) =>
    STATIC
      ? fromSnapshot<EvaluateResponse>(snap.evaluate(split))
      : Promise.all([
          getJson<SavedSummary>(`${API_URL}/api/baseline/summary`),
          // The season chart is optional: without saved as-of results the scores still show.
          savedAsOf().then((data) => ({ points: adaptConvergence(data, year), error: undefined }))
            .catch((error: unknown) => ({ points: [], error: error instanceof Error ? error.message : String(error) })),
        ]).then(([summary, season]) => ({ ...adaptSummary(summary, season.points), convergence_error: season.error })),

  rollup: (year: number) =>
    STATIC
      ? fromSnapshot<RollupResponse>(snap.rollup(year))
      : getJson<SavedRollup>(`${API_URL}/api/baseline/rollup`).then((data) => adaptRollup(data, year)),

  convergenceAcres: () =>
    STATIC
      ? fromSnapshot<ConvergenceAcres>(snap.convergenceAcres())
      : getJson<ConvergenceAcres>(`${API_URL}/api/baseline/convergence`),

  /** Model calls on blank-label field-years CDL marks as corn: same saved shape live and static. */
  unlabeled: (year: number): Promise<UnlabeledYearView> =>
    (STATIC ? fromSnapshot<SavedUnlabeled>(snap.unlabeled()) : getJson<SavedUnlabeled>(`${API_URL}/api/unlabeled`))
      .then((data) => adaptUnlabeled(data, year)),

  series: (id: number, year: number) =>
    STATIC
      ? fromSnapshot<SeriesResponse>(snap.series(id, year))
      : getJson<{ date: string; ndvi: number | null; status: string }[]>(`${API_URL}/api/fields/${id}/observations?year=${year}`)
        .then((data) => adaptSeries(data, id, year)),

  agentRun: async (query: string): Promise<AgentRunResponse> => {
    if (STATIC) throw new ApiError('Agent execution is unavailable in a static snapshot.', 501)
    return post<AgentRunResponse>('/api/agent/run', { query })
  },

  agentTrace: async (runId: string): Promise<AgentTraceResponse> => {
    if (STATIC) throw new ApiError('No agent ran for this static snapshot.', 501)
    const lines = await getJson<AgentTraceResponse['lines']>(`${API_URL}/api/agent/trace/${encodeURIComponent(runId)}`)
    return { run_id: runId, lines, status: lines.some((line) => line.type === 'report') ? 'done' : 'running' }
  },

  /** Before/after image chip URL for a field-year. */
  chipUrl: (id: number, year: number, which: 'pre' | 'post') =>
    STATIC ? `${SNAPSHOT_BASE}chips/${id}_${year}_${which}.png` : `${API_URL}/chips/${id}_${year}_${which}.png`,

  /** Resolve the roll-up CSV link (absolute URLs pass through; relative ones hit the API or snapshot). */
  csvUrl: (csvUrl: string) => {
    if (/^https?:\/\//.test(csvUrl)) return csvUrl
    const path = csvUrl.replace(/^\//, '')
    return STATIC ? `${SNAPSHOT_BASE}${path}` : `${API_URL}/${path}`
  },
}
