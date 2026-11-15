import { useEffect, useState } from 'react'
import { api, keyMissing, recordedAgentRun, STATIC } from '../api'
import type { AgentTraceResponse, TraceLine } from '../api'
import { useAsync } from '../hooks'
import { Markdown } from './Markdown'

const DEFAULT_QUERY =
  "Score BARC's 2022 fields as of October 12 against the labels. Then look up NASS 2025 Maryland corn acres harvested for silage and for grain, and say whether BARC's labeled fields look more silage-heavy than Maryland as a whole."
const POLL_MS = 1000
/** A typical run: plan, a few tool calls and results, the Verifier check and the report. */
const TYPICAL_STEPS = 8

/** "2026-11-15T12:17:43Z" -> "2026-11-15 12:17 UTC" (the recording's own timestamp, never the current time). */
const recordedTime = (ts: string | null) => (ts ? `${ts.slice(0, 10)} ${ts.slice(11, 16)} UTC` : 'time not recorded')

export function AgentPanel() {
  const [query, setQuery] = useState(DEFAULT_QUERY)
  const [runId, setRunId] = useState<string | null>(null)
  const [trace, setTrace] = useState<AgentTraceResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  // The live agent needs the server's NVIDIA key (the market status route reports whether one is configured).
  const keyStatus = useAsync(() => api.marketStatus(), [])
  const recorded = useAsync(() => recordedAgentRun(), [])

  const run = async () => {
    setError(null)
    setTrace(null)
    setRunId(null)
    setStarting(true)
    try {
      const res = await api.agentRun(query)
      setRunId(res.run_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setStarting(false)
    }
  }

  // Poll the trace every second until the run finishes.
  useEffect(() => {
    if (!runId) return
    let live = true
    let timer: number | undefined
    const tick = async () => {
      try {
        const res = await api.agentTrace(runId)
        if (!live) return
        setTrace(res)
        if (res.status === 'running') timer = window.setTimeout(tick, POLL_MS)
      } catch (e) {
        if (live) setError(e instanceof Error ? e.message : String(e))
      }
    }
    void tick()
    return () => {
      live = false
      window.clearTimeout(timer)
    }
  }, [runId])

  const status = starting ? 'starting' : error ? 'error' : (trace?.status ?? (runId ? 'running' : 'idle'))
  const liveKeyMissing = keyMissing(error) || (trace?.lines.some((l) => l.type === 'error' && keyMissing(l.summary)) ?? false)
  const noKey = STATIC || keyStatus.data?.configured === false || liveKeyMissing
  const showRecorded = noKey && !!recorded.data && (!runId || liveKeyMissing)

  return (
    <div className="agent">
      {!STATIC && (
        <form
          className="agent__form"
          onSubmit={(e) => {
            e.preventDefault()
            void run()
          }}
        >
          <label htmlFor="agent-q" className="eyebrow">
            Ask the analyst agent
          </label>
          <textarea id="agent-q" value={query} onChange={(e) => setQuery(e.target.value)} rows={3} />
          <div className="agent__actions">
            <button className="button" type="submit" disabled={starting || status === 'running' || !query.trim()}>
              {status === 'running' ? 'Running…' : 'Run'}
            </button>
            {status !== 'idle' && (
              <span className={`status status--${status}`}>
                <span className="status__dot" />
                {status}
              </span>
            )}
          </div>
        </form>
      )}

      {error && !liveKeyMissing && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
      {liveKeyMissing && (
        <p className="inline-error" role="alert">
          The live run could not start: the NVIDIA key is not configured on this server. A recorded run is shown below.
        </p>
      )}

      {trace && !liveKeyMissing && <RunView trace={trace} running={status === 'running'} />}

      {showRecorded && recorded.data && (
        <section className="agent__recorded" aria-label="Recorded agent run">
          <p className="agent__badge" role="note">
            Recorded run · {recordedTime(recorded.data.recorded_at)} · {STATIC ? 'live agent not available in this static build' : 'live Nemotron key not configured on this server'}
          </p>
          <p className="muted small">Question: {recorded.data.query}</p>
          <RunView trace={recorded.data} running={false} />
        </section>
      )}

      {!trace && !showRecorded && !error && (
        <p className="muted">The answer appears here first; the agent's plan, tool calls and Verifier checks are listed below it. Every number comes from a tool.</p>
      )}
    </div>
  )
}

/** Results first: the report card, then the step-by-step trace collapsed underneath. */
function RunView({ trace, running }: { trace: AgentTraceResponse; running: boolean }) {
  const report = trace.lines.findLast((l) => l.type === 'report')
  const flags = trace.lines.filter((l) => l.type === 'flag').length
  const last = trace.lines.at(-1)
  return (
    <>
      {running && (
        <p className="agent__working" role="status">
          Working… step {trace.lines.length + 1} of ~{Math.max(TYPICAL_STEPS, trace.lines.length + 1)}
          {last ? `: ${last.tool ? `calling ${last.tool}` : last.type.replace('_', ' ')}` : ': planning'}
        </p>
      )}
      {report && (
        <article className={`agent__report${trace.status === 'error' ? ' is-error' : ''}`} aria-label="Agent report">
          <p className="eyebrow">{trace.status === 'error' ? 'Run failed' : 'Report'}</p>
          <Markdown text={String(report.summary ?? '')} className="md agent__md" />
        </article>
      )}
      <details className="more section agent__steps">
        <summary>
          Show the agent's steps ({trace.lines.length}){flags ? ` · ${flags} Verifier flag${flags === 1 ? '' : 's'}` : ''}
        </summary>
        <ol className="trace">
          {trace.lines.map((l, i) => (
            <TraceItem key={`${l.step}-${i}`} line={l} />
          ))}
        </ol>
      </details>
    </>
  )
}

function TraceItem({ line }: { line: TraceLine }) {
  const isFlag = line.type === 'flag'
  const args = line.args
  return (
    <li className={`trace__item${isFlag ? ' flag' : ''}`}>
      <div className="trace__step">{line.step}</div>
      <div className="trace__body">
        <div className="trace__meta">
          <span className={`node node--${String(line.node).toLowerCase()}`}>{line.node}</span>
          <span className="trace__type">{isFlag ? '⚑ Verifier flag' : line.type.replace('_', ' ')}</span>
          {line.tool && <code className="trace__tool">{line.tool}</code>}
        </div>
        <p className="trace__summary">{line.type === 'report' ? reportTitle(String(line.summary ?? '')) : line.summary}</p>
        {args && <code className="trace__args">{typeof args.args === 'string' && Object.keys(args).length === 1 ? args.args : JSON.stringify(args)}</code>}
      </div>
    </li>
  )
}

/** The report is rendered in full above the trace; its trace step just names it. */
function reportTitle(md: string) {
  const first = md.split('\n').find((l) => l.trim()) ?? ''
  return `Report written: ${first.replace(/^#+\s*/, '').replace(/\*\*/g, '').trim() || 'see above'}`
}
