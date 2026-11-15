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
  BarcRollupYear,
  EvaluateResponse,
  FieldsResponse,
  Pred,
  RollupResponse,
  SeriesResponse,
  SnapshotMeta,
} from './types'
import { adaptBarcRollup, adaptFields, adaptPredictions, adaptSeries, adaptSummary, byYearFromPredictions } from './adapter.ts'
import type { SavedFields, SavedPrediction, SavedRollup, SavedSummary } from './adapter'

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

export const api = {
  /** Static mode only: describes the snapshot (stub or real, which years / dates exist). */
  meta: (): Promise<SnapshotMeta | null> =>
    STATIC ? fromSnapshot<SnapshotMeta>(snap.meta()) : Promise.resolve({
      stub: false, note: 'Saved BARC baseline results; held out by field.',
      years: [2021, 2022, 2023], as_of_dates: [2021, 2022, 2023].map((y) => `${y}-11-30`),
      season_end_only: true, has_chips: false, has_rollup: false, has_contributions: false,
    }),

  fields: (year: number) =>
    STATIC
      ? fromSnapshot<FieldsResponse>(snap.fields(year))
      : getJson<SavedFields>(`${API_URL}/api/fields.geojson`).then((data) => adaptFields(data, year)),

  predict: (year: number, asOf: string) =>
    STATIC
      ? fromSnapshot<Pred[]>(snap.predict(year, asOf))
      : getJson<SavedPrediction[]>(`${API_URL}/api/baseline/predictions`).then((data) => adaptPredictions(data, year, asOf)),

  evaluate: (split = 'strict') =>
    STATIC
      ? fromSnapshot<EvaluateResponse>(snap.evaluate(split))
      : Promise.all([
          getJson<SavedSummary>(`${API_URL}/api/baseline/summary`),
          getJson<SavedPrediction[]>(`${API_URL}/api/baseline/predictions`),
        ]).then(([summary, preds]) => ({ ...adaptSummary(summary), by_year: byYearFromPredictions(preds) })),

  /** Acre roll-up over BARC's labeled fields for one year. Live: /api/baseline/rollup; snapshot: barc_rollup.json. */
  barcRollup: (year: number): Promise<BarcRollupYear | null> =>
    (STATIC ? fromSnapshot<SavedRollup>('barc_rollup') : getJson<SavedRollup>(`${API_URL}/api/baseline/rollup`))
      .then((data) => adaptBarcRollup(data, year)),

  rollup: (year: number) =>
    STATIC
      ? fromSnapshot<RollupResponse>(snap.rollup(year))
      : Promise.reject<RollupResponse>(new ApiError('Statewide estimates are unavailable. The saved rollup covers labeled BARC fields only; it cannot be compared with statewide Census acres.', 503)),

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
