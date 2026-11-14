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
  EvaluateResponse,
  FieldsResponse,
  Pred,
  RollupResponse,
  SeriesResponse,
  SnapshotMeta,
} from './types'

export * from './types'

export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')
export const STATIC = import.meta.env.VITE_STATIC === '1'
const SNAPSHOT_BASE = `${import.meta.env.BASE_URL}snapshot/`

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

/* In static mode the agent trace is revealed line by line, so the offline demo still "runs". */
const staticRunStarted = new Map<string, number>()
const STATIC_MS_PER_LINE = 900

export const api = {
  /** Static mode only: describes the snapshot (stub or real, which years / dates exist). */
  meta: (): Promise<SnapshotMeta | null> =>
    STATIC ? fromSnapshot<SnapshotMeta>(snap.meta()).catch(() => null) : Promise.resolve(null),

  fields: (year: number) =>
    STATIC
      ? fromSnapshot<FieldsResponse>(snap.fields(year))
      : getJson<FieldsResponse>(`${API_URL}/fields?year=${year}`),

  predict: (year: number, asOf: string) =>
    STATIC
      ? fromSnapshot<Pred[]>(snap.predict(year, asOf))
      : post<Pred[]>('/predict', { year, as_of: asOf }),

  evaluate: (split = 'strict') =>
    STATIC
      ? fromSnapshot<EvaluateResponse>(snap.evaluate(split))
      : getJson<EvaluateResponse>(`${API_URL}/evaluate?split=${encodeURIComponent(split)}`),

  rollup: (year: number) =>
    STATIC
      ? fromSnapshot<RollupResponse>(snap.rollup(year))
      : getJson<RollupResponse>(`${API_URL}/rollup?year=${year}`),

  series: (id: number, year: number) =>
    STATIC
      ? fromSnapshot<SeriesResponse>(snap.series(id, year))
      : getJson<SeriesResponse>(`${API_URL}/fields/${id}/series?year=${year}`),

  agentRun: async (query: string): Promise<AgentRunResponse> => {
    if (!STATIC) return post<AgentRunResponse>('/agent/run', { query })
    const res = await fromSnapshot<AgentRunResponse>(snap.agentRun())
    staticRunStarted.set(res.run_id, Date.now())
    return res
  },

  agentTrace: async (runId: string): Promise<AgentTraceResponse> => {
    if (!STATIC) return getJson<AgentTraceResponse>(`${API_URL}/agent/trace/${encodeURIComponent(runId)}`)
    const full = await fromSnapshot<AgentTraceResponse>(snap.agentTrace(runId))
    const started = staticRunStarted.get(runId) ?? 0
    const shown = Math.min(full.lines.length, 1 + Math.floor((Date.now() - started) / STATIC_MS_PER_LINE))
    return { ...full, lines: full.lines.slice(0, shown), status: shown < full.lines.length ? 'running' : full.status }
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
