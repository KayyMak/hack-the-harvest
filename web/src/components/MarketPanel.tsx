import { useState } from 'react'
import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, STATIC } from '../api'
import type { MarketOutlook, MarketReport } from '../api'
import { shortDate } from '../format'
import { useAsync } from '../hooks'
import { DATA, useTheme } from '../theme'
import { Markdown } from './Markdown'
import { Pending } from './Pending'

type Dict = Record<string, unknown>
const SEASONS = [
  { season: 2025, label: '2025 outlook (US and Maryland)' },
  { season: 2023, label: '2023 (BARC model)' },
  { season: 2022, label: '2022 (BARC model)' },
  { season: 2021, label: '2021 (BARC model)' },
]
const str = (v: unknown) => (typeof v === 'string' || typeof v === 'number' ? String(v) : '—')

/** Optional sample market outlook: month by month, using only what was known on each date. Nemotron reads
 *  our forecasts, model calls and NASS data through server-side tools and writes the report. */
export function MarketPanel() {
  const [season, setSeason] = useState(2025)
  const [asOf, setAsOf] = useState<string | null>(null) // null = latest date for the season
  const [statusKey, setStatusKey] = useState(0)
  const status = useAsync(() => api.marketStatus(), [statusKey])
  const outlook = useAsync(() => api.marketOutlook(season, asOf), [season, asOf])
  const [report, setReport] = useState<MarketReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (STATIC) return <Pending title="Market outlook">Market outlooks need the live backend; this static snapshot cannot run Nemotron.</Pending>

  const o = outlook.data
  const shownAsOf = o?.as_of ?? asOf
  const generate = async () => {
    setBusy(true)
    setError(null)
    setReport(null)
    try {
      setReport(await api.marketReport(season, shownAsOf))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
      setStatusKey((k) => k + 1)
    }
  }
  const shownReport = report && report.year === season && report.as_of === shownAsOf ? report : null

  return (
    <div className="market">
      <p className="sheet__lede">
        A sample, forward-looking corn market outlook that updates month by month. Pick a season and a date: everything shown
        uses only what was known on that date. NVIDIA Nemotron can then write the outlook from our model and USDA data.
      </p>

      <div className="market__controls">
        <label className="yearpick">
          Season
          <select value={season} onChange={(e) => { setAsOf(null); setSeason(Number(e.target.value)) }}>
            {SEASONS.map((x) => (
              <option key={x.season} value={x.season}>{x.label}</option>
            ))}
          </select>
        </label>
        {o && (
          <div className="seg" role="group" aria-label="Outlook as of">
            {o.dates.map((d) => (
              <button key={d} className={`seg__btn${d === o.as_of ? ' is-on' : ''}`} aria-pressed={d === o.as_of} onClick={() => setAsOf(d)}>
                {shortDate(d)}
              </button>
            ))}
          </div>
        )}
      </div>

      {outlook.error ? (
        <p className="inline-error" role="alert">Outlook unavailable: {outlook.error.message}</p>
      ) : !o ? (
        <div className="skeleton skeleton--chart" />
      ) : (
        <>
          <OutlookCards outlook={o} />
          <OutlookChart outlook={o} />
          <p className="muted small">{str(o.timeline.what_is_ours ?? o.timeline.scope)} {str(o.timeline.next_official_numbers)}</p>
        </>
      )}

      <div className="market__actions">
        <button className="button" onClick={() => void generate()} disabled={busy || !o}>
          {busy ? 'Nemotron is writing…' : shownReport ? 'Regenerate outlook' : `Write outlook as of ${shownAsOf ? shortDate(shownAsOf) : '…'}`}
        </button>
        {status.data && (
          <span className={`status status--${status.data.configured ? 'done' : 'error'}`}>
            <span className="status__dot" />
            {status.data.configured ? status.data.model : 'No NVIDIA key on the server'}
          </span>
        )}
        {busy && <span className="muted">Calling tools, writing and checking every sentence; this can take up to a minute.</span>}
      </div>

      {status.data && !status.data.configured && !error && (
        <Pending title="Connect Nemotron">
          {status.data.how_to_configure} Get a free key on build.nvidia.com. The key stays on the server and is never sent to this page.
        </Pending>
      )}
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}

      {shownReport && <Report report={shownReport} />}
    </div>
  )
}

function OutlookCards({ outlook }: { outlook: MarketOutlook }) {
  const t = outlook.timeline as Dict
  const latest = (t.latest_release as Dict | undefined) ?? {}
  const date = shortDate(outlook.as_of)
  if (t.kind === 'statewide_and_us_outlook') {
    const moves = (latest.us_price_pressure_from_supply_change as Dict[] | undefined) ?? []
    const base = t.baseline_2024_official as Dict
    return (
      <section className="kpis market__kpis" aria-label="Outlook figures">
        <Kpi label={`US grain supply vs 2024, as of ${date}`} value={str(latest.us_grain_supply_change_vs_2024 ?? 'Not yet')}
          sub={latest.us_grain_production_forecast ? `${str(latest.us_grain_production_forecast)} forecast` : 'NASS yield forecasts start in August'}
          foot={`2024: ${str(base?.us_grain_production)}`} />
        <Kpi label="Price pressure from that supply" value={moves.length ? `${str(moves[moves.length - 1].price_change)} to ${str(moves[0].price_change)}` : '—'}
          sub={moves.length ? `${str(moves[moves.length - 1].implied_price)} to ${str(moves[0].implied_price)} vs ${str(base?.us_grain_price_received)}` : 'Needs a production forecast'}
          foot="Assumed elasticity −1.0 to −0.2" />
        <Kpi label="Our US silage estimate" value={str(latest.us_silage_acres_estimate)} sub={`95%: ${str(latest.us_silage_95pct_range)} acres`}
          foot={latest.change_in_grain_kept_off_market_vs_2024 ? `${str(latest.change_in_grain_kept_off_market_vs_2024)} kept off grain market vs 2024` : `2024: ${str(base?.us_silage_acres)} acres`} />
        <Kpi label="Our Maryland silage share" value={str(latest.md_silage_share_estimate)} sub={`${str(latest.md_silage_acres_estimate)} acres (95%: ${str(latest.md_silage_95pct_range)})`}
          foot={`2024: ${str(base?.md_silage_acres)} silage acres`} />
      </section>
    )
  }
  const baseline = (t.latest_official_baseline ?? {}) as Dict
  return (
    <section className="kpis market__kpis" aria-label="Outlook figures">
      <Kpi label={`BARC model silage estimate, as of ${date}`} value={`${str(latest.barc_expected_silage_acres)} ac`}
        sub={`95%: ${str(latest.range_95pct)} acres`} foot={`${str(latest.fields_decided)} labeled fields decided`} />
      <Kpi label={`Latest official Maryland silage share (${str(baseline.year)})`} value={str(baseline.maryland_silage_share_of_harvested_corn)}
        sub={`${str(baseline.maryland_silage_acres_harvested)} silage vs ${str(baseline.maryland_grain_acres_harvested)} grain acres`} foot="USDA NASS, prior season" />
      <Kpi label={`Grain kept off the market by silage (${str(baseline.year)})`} value={`${str(baseline.grain_bushels_not_produced_because_of_silage_acres)} bu`}
        sub={`at ${str(baseline.maryland_grain_price_received)}`} foot="Prior season, official" />
    </section>
  )
}

function OutlookChart({ outlook }: { outlook: MarketOutlook }) {
  const t = useTheme().chart
  const tl = outlook.timeline as Dict
  const series = (tl.series as Dict[]) ?? []
  const grid = <CartesianGrid stroke={t.grid} vertical={false} />
  const x = <XAxis dataKey="label" stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} />
  const tip = <Tooltip contentStyle={{ background: t.surface, border: `1px solid ${t.grid}`, color: t.ink }} />
  if (tl.kind === 'statewide_and_us_outlook') {
    const rows = series.map((r) => ({ label: shortDate(String(r.as_of)), supply: r.us_production_change_pct, md: r.md_silage_share_pct }))
    return (
      <figure className="market__chart" role="img" aria-label="US grain supply change versus 2024 and our Maryland silage share, by release date">
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={rows} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
            {grid}{x}
            <YAxis stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} width={44} unit="%" />
            {tip}
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="supply" name="US grain supply vs 2024 (NASS forecast)" stroke={DATA.grain} strokeWidth={2.5} dot={{ r: 3 }} connectNulls isAnimationActive={false} unit="%" />
            <Line type="monotone" dataKey="md" name="Maryland silage share (our estimate)" stroke={DATA.silage} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} unit="%" />
          </ComposedChart>
        </ResponsiveContainer>
      </figure>
    )
  }
  const rows = series.map((r) => ({
    label: shortDate(String(r.as_of)), est: r.barc_expected_silage_acres, lo: r.barc_low,
    band: Number(r.barc_high) - Number(r.barc_low),
  }))
  return (
    <figure className="market__chart" role="img" aria-label="BARC model silage acre estimate with 95% range, by date">
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={rows} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
          {grid}{x}
          <YAxis stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} width={44} />
          {tip}
          <Area type="monotone" dataKey="lo" stackId="b" stroke="none" fill="transparent" isAnimationActive={false} legendType="none" tooltipType="none" />
          <Area type="monotone" dataKey="band" stackId="b" stroke="none" fill={DATA.silage} fillOpacity={0.14} isAnimationActive={false} name="95% range" tooltipType="none" />
          <Line type="monotone" dataKey="est" name="BARC silage acres (our model)" stroke={DATA.silage} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
        </ComposedChart>
      </ResponsiveContainer>
    </figure>
  )
}

function Kpi({ label, value, sub, foot }: { label: string; value: string; sub: string; foot: string }) {
  return (
    <article className="glass kpi">
      <h2 className="kpi__label">{label}</h2>
      <div className="kpi__value">{value}</div>
      <div className="kpi__sub">{sub}</div>
      <div className="kpi__foot">{foot}</div>
    </article>
  )
}

function Report({ report }: { report: MarketReport }) {
  const cites = new Map(report.citations.map((c) => [c.id, c]))
  const { claims_checked, ungrounded, verifier } = report.grounding
  const serious = ungrounded.filter((u) => u.kind !== 'miscited')
  const miscited = ungrounded.filter((u) => u.kind === 'miscited')
  return (
    <article className="market__report" aria-label={`Sample market report ${report.year}`}>
      <p className="market__badge">Sample report · {report.model} · {new Date(report.generated_at).toLocaleString()}</p>
      {serious.length > 0 && (
        <div className="inline-error" role="alert">
          <strong>
            {serious.length} of {claims_checked} sentences were removed because they are not backed by our data
          </strong>{' '}
          (they would have come from the model itself):
          <ul className="market__ungrounded">
            {serious.map((u, i) => (
              <li key={i}>
                “{u.text}” <span className="muted">({u.reason})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {miscited.length > 0 && (
        <details className="market__miscited">
          <summary>
            {miscited.length} sentence{miscited.length === 1 ? '' : 's'} cite{miscited.length === 1 ? 's' : ''} the wrong source for a figure that is in our data (minor)
          </summary>
          <ul className="market__ungrounded">
            {miscited.map((u, i) => (
              <li key={i}>
                “{u.text}” <span className="muted">({u.reason})</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {ungrounded.length > 0 ? null : (
        <p className="market__grounded">
          All {claims_checked} sentences cite our model outputs or project documents, every number matches its cited source
          {verifier === 'nemotron' ? ', and a second check confirmed each cited source supports its sentence.' : '.'}
        </p>
      )}
      {verifier === 'unavailable' && (
        <p className="inline-error" role="status">The wording check (does each source support its sentence?) could not run; only citations and numbers were verified.</p>
      )}
      <Markdown text={report.markdown} cites={cites} className="md market__md" />
      <section className="market__sources" aria-label="Cited sources">
        <h3>Cited sources</h3>
        <ul>
          {report.citations.map((c) => (
            <li key={c.id}>
              <code className="cite">{c.id}</code> {c.kind === 'doc' ? <span className="muted">project document: {c.label}</span> : <span className="muted">model/data tool: {c.label}</span>}
              {c.excerpt && <blockquote>{c.excerpt}{c.excerpt.length >= 400 ? '…' : ''}</blockquote>}
            </li>
          ))}
        </ul>
      </section>
      <p className="market__disclaimer">{report.disclaimer}</p>
      <details className="market__tools">
        <summary>
          How Nemotron used the model: {report.tool_calls.length} tool call{report.tool_calls.length === 1 ? '' : 's'}
          {report.mode === 'context' ? ' (pre-fetched; this endpoint did not call tools itself)' : ''}
        </summary>
        <ol className="trace">
          {report.tool_calls.map((c, i) => (
            <li key={i} className={`trace__item${c.ok ? '' : ' flag'}`}>
              <div className="trace__step">{i + 1}</div>
              <div className="trace__body">
                <div className="trace__meta">
                  <code className="trace__tool">{c.name}</code>
                  <span className="trace__type">{c.ok ? 'tool result' : 'tool error'}</span>
                </div>
                <p className="trace__summary">{c.summary}</p>
                <code className="trace__args">{JSON.stringify(c.args)}</code>
              </div>
            </li>
          ))}
        </ol>
        <p className="muted">Sources: {report.sources.join('; ')}</p>
      </details>
    </article>
  )
}
