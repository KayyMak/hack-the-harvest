import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { AgentTraceResponse, TraceLine } from '../api'

const DEFAULT_QUERY =
  "Classify BARC's 2022 fields as of October 12, score them against the labels, and roll Maryland up against the 2022 Census."
const POLL_MS = 1000

export function AgentPanel() {
  const [query, setQuery] = useState(DEFAULT_QUERY)
  const [runId, setRunId] = useState<string | null>(null)
  const [trace, setTrace] = useState<AgentTraceResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const listRef = useRef<HTMLOListElement>(null)

  const run = async () => {
    setError(null)
    setTrace(null)
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

  useEffect(() => {
    listRef.current?.lastElementChild?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [trace?.lines.length])

  const status = starting ? 'starting' : (trace?.status ?? (runId ? 'running' : 'idle'))
  const flags = trace?.lines.filter((l) => l.type === 'flag').length ?? 0

  return (
    <div className="agent">
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
          <span className={`status status--${status}`}>
            <span className="status__dot" />
            {status}
          </span>
          {trace && (
            <span className="muted">
              {trace.lines.length} steps · {flags} Verifier flag{flags === 1 ? '' : 's'}
            </span>
          )}
        </div>
      </form>

      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}

      {trace ? (
        <ol className="trace" ref={listRef} aria-live="polite">
          {trace.lines.map((l) => (
            <TraceItem key={l.step} line={l} />
          ))}
        </ol>
      ) : (
        !error && <p className="muted">The trace shows each plan step, tool call and Verifier check as the agent runs. Every number comes from a tool.</p>
      )}
    </div>
  )
}

function TraceItem({ line }: { line: TraceLine }) {
  const isFlag = line.type === 'flag'
  return (
    <li className={`trace__item${isFlag ? ' flag' : ''}`}>
      <div className="trace__step">{line.step}</div>
      <div className="trace__body">
        <div className="trace__meta">
          <span className={`node node--${String(line.node).toLowerCase()}`}>{line.node}</span>
          <span className="trace__type">{isFlag ? '⚑ Verifier flag' : line.type.replace('_', ' ')}</span>
          {line.tool && <code className="trace__tool">{line.tool}</code>}
        </div>
        <p className="trace__summary">{line.summary}</p>
        {line.args && <code className="trace__args">{JSON.stringify(line.args)}</code>}
      </div>
    </li>
  )
}
