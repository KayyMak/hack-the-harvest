import { useMemo, useState } from 'react'
import { Area, Bar, CartesianGrid, Cell as BarCell, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useTheme } from '../theme'
import { xTitle, yTitle } from './charts'
import type { Cell, Crop, Forecast, Reliability, StateRow } from './forecastTypes'
import { ERROR_STEPS, fmtAcres, fmtFull, fmtPct, releaseDate, titleCase } from './forecastFormat'
import { ScoreUpload } from './ScoreUpload'

const NASS_RELEASE_TIP = '2025 NASS releases: Jun 30 Acreage; Aug 12, Sep 12, Nov 14 Crop Production (no October report in 2025)'
const CROP_SHORT: Record<Crop, string> = { silage: 'silage', grain: 'grain' }

interface Props {
  data: Forecast
  crop: Crop
  selected: string | null
  onSelect: (s: string | null) => void
  showTable: boolean
  onTable: (v: boolean) => void
}

/** The graded view: 2025 acres by state vs NASS. Map, headline numbers, convergence, misses, and state detail. */
export function ForecastPanels({ data, crop, selected, onSelect, showTable, onTable }: Props) {
  const t = useTheme().chart
  const md = data.states.find((s) => s.state === 'MARYLAND')
  const sel = data.states.find((s) => s.state === selected) ?? null
  const fsa = fsaBacktest(data)
  return (
    <>
      <div className="lead">
        <section className="kpis" aria-label="2025 headline numbers">
          <UsCard crop="silage" cell={data.us.silage} rel={data.reliability?.silage ?? null} />
          <UsCard crop="grain" cell={data.us.grain} rel={data.reliability?.grain ?? null} />
          <article className="glass kpi">
            <h2 className="kpi__label">States within 10%</h2>
            <div className="kpi__value">
              {data.scores.grain.within_10pct}
              <span className="kpi__of">/{data.scores.grain.states} grain</span>
            </div>
            <div className="kpi__sub">
              {data.scores.silage.within_10pct}/{data.scores.silage.states} silage
            </div>
            <div className="kpi__foot">
              Weighted error: grain {data.scores.grain.acre_weighted_abs_pct_error.toFixed(1)}%, silage {data.scores.silage.acre_weighted_abs_pct_error.toFixed(1)}%
            </div>
          </article>
          {md && (
            <button className="glass kpi kpi--button" onClick={() => onSelect('MARYLAND')}>
              <h2 className="kpi__label">Maryland {CROP_SHORT[crop]} acres</h2>
              <div className="kpi__value">{fmtAcres(md[crop]?.est)}</div>
              <div className="kpi__sub">
                NASS {fmtAcres(md[crop]?.nass)} <ErrTag err={md[crop]?.err ?? null} />
              </div>
              <div className="kpi__foot">Home of the BARC fields</div>
            </button>
          )}
        </section>
      </div>

      {!showTable && (
        <aside className="glass rail" aria-label="How the estimate was built">
          <section>
            <h2 className="rail__title" title={NASS_RELEASE_TIP}>US {crop} estimate by NASS release</h2>
            <div title={NASS_RELEASE_TIP}><ConvergenceChart data={data} crop={crop} /></div>
            <div className="linekey">
              <span><i style={{ background: t.share }} />Our estimate</span>
              <span><i style={{ background: t.share, opacity: 0.35, height: 8 }} />95% range</span>
              <span><i className="linekey__dash" style={{ borderColor: t.accuracy }} />NASS final</span>
            </div>
          </section>
          <TrackRecord data={data} crop={crop} />
          <section>
            <div className="rail__head">
              <h2 className="rail__title">How close we came, 2025</h2>
              <button className="link" onClick={() => onTable(true)}>All states</button>
            </div>
            <ul className="closeness">
              <li><b>{data.scores.silage.inside_95_interval} of {data.scores.silage.states}</b> silage states: NASS final inside our 95% range</li>
              <li><b>{data.scores.grain.inside_95_interval} of {data.scores.grain.states}</b> grain states: NASS final inside our 95% range</li>
            </ul>
            <h3 className="rail__sub">Largest {crop} states (acres, ours vs NASS)</h3>
            <MissList rows={data.states} crop={crop} onSelect={onSelect} />
          </section>
          {crop === 'silage' && <WhyMisses data={data} onSelect={onSelect} />}
          <ScoreUpload data={data} crop={crop} />
          <section>
            <h2 className="rail__title">How it works</h2>
            <p className="rail__note rail__note--keep">
              Grain: NASS's Nov 14, 2025 forecast. Silage: half from each state's 5-year median silage shares applied to its 2025 planted and grain acres, half from last year's silage acres.
            </p>
            {fsa ? (
              <p className="rail__note rail__note--keep">
                FSA intended-use acres lost the silage backtest ({fsa.fsa.toFixed(1)}% vs {fsa.chosen.toFixed(1)}% error), so aren't used; nor is RMA data.
              </p>
            ) : (
              <p className="rail__note rail__note--keep">
                FSA intended-use acres were tried in the team's first forecast and lost its backtest, so aren't used; nor is RMA data.
              </p>
            )}
            <details className="more">
              <summary>Details</summary>
              <p className="rail__note rail__note--keep">
                Silage method chosen by a rule written down before scoring: lowest acre-weighted error when each year 2018–2024 is forecast with only what was known then
                {backtestPair(data) ? ` (${backtestPair(data)})` : ''}. 2025 NASS numbers were never used to choose it.
                No January 2026 data used (data cutoff {data.data_cutoff}). Click a state on the map for its numbers, or open All states for the table.
              </p>
              <table className="mini-table backtest">
                <caption>Backtest on earlier state-years, forecast the same way</caption>
                <thead><tr><th>Crop</th><th className="num">State-years</th><th className="num">Median error</th><th className="num">Mean error</th><th className="num">In 95% range</th></tr></thead>
                <tbody>
                  {(['silage', 'grain'] as const).map((c) => {
                    const b = data.backtest[c]
                    return (
                      <tr key={c}>
                        <td>{c === 'silage' ? 'Silage' : 'Grain'}</td><td className="num">{b.state_years}</td><td className="num">{b.median_abs_pct_error.toFixed(1)}%</td>
                        <td className="num">{b.mean_abs_pct_error.toFixed(1)}%</td><td className="num">{Math.round(b.covered_by_95_interval * 100)}%</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </details>
          </section>
        </aside>
      )}

      {showTable && (
        <section className="glass sheet" aria-label="All states">
          <div className="sheet__headrow">
            <h1 className="sheet__title">All states, 2025</h1>
            <div className="sheet__actions">
              <button className="ghost-btn" onClick={() => onTable(false)}>Back to map</button>
            </div>
          </div>
          <p className="sheet__lede">Acres harvested, our estimate vs NASS final. Hover an estimate for its 95% range; <b className="ftable__flag">!</b> = NASS fell outside it. Click a state for detail.</p>
          <StateTable rows={data.states} onSelect={onSelect} selected={selected} />
        </section>
      )}

      {sel && <StateDrawer row={sel} data={data} onClose={() => onSelect(null)} />}
    </>
  )
}

/** Backtest error of the FSA-based silage candidate next to the chosen method, from forecast_2025.json. */
function fsaBacktest(data: Forecast): { fsa: number; chosen: number } | null {
  const m = data.silage_method
  const err = m?.backtest_acre_weighted_abs_pct_error ?? {}
  const key = Object.entries(m?.candidates ?? {}).find(([, text]) => text.startsWith('FSA'))?.[0]
  const fsa = key ? err[key] : undefined
  const chosen = m ? err[m.chosen] : undefined
  return fsa != null && chosen != null ? { fsa, chosen } : null
}

function UsCard({ crop, cell, rel }: { crop: Crop; cell: Cell; rel: Reliability | null }) {
  return (
    <article className="glass kpi">
      <h2 className="kpi__label">US {CROP_SHORT[crop]} acres</h2>
      <div className="kpi__value">{fmtAcres(cell.est)}</div>
      <div className="kpi__sub">
        NASS {fmtAcres(cell.nass)} <ErrTag err={cell.err} />
      </div>
      {rel && (
        <div
          className="kpi__foot"
          title={`NASS reliability format, from the ${rel.years} backtest (${rel.n} years, each forecast with only what was known then): root-mean-square error ${rel.rmse_pct}%; 9 times in 10 the miss is no more than ±${rel.margin90_pct}% (Student t ${rel.t} × RMSE). Largest miss: ${rel.max_abs_pct}%.`}
        >
          <span className="nowrap">Margin of error ±{rel.margin90_pct}% (90%)</span> · <span className="nowrap">RMSE {rel.rmse_pct}%</span>
        </div>
      )}
      <div className="kpi__foot">
        95% range {fmtAcres(cell.low)}–{fmtAcres(cell.high)}
      </div>
    </article>
  )
}

function ErrTag({ err }: { err: number | null }) {
  if (err == null) return null
  const good = Math.abs(err) <= 0.1
  return <span className={`errtag ${good ? 'is-good' : 'is-off'}`}>{fmtPct(err)}</span>
}

function ConvergenceChart({ data, crop }: { data: Forecast; crop: Crop }) {
  const t = useTheme().chart
  const nass = data.us[crop].nass
  const rows = data.convergence
    .map((c) => {
      const est = crop === 'silage' ? c.us_silage : c.us_grain
      const low = crop === 'silage' ? c.us_silage_low : c.us_grain_low
      const high = crop === 'silage' ? c.us_silage_high : c.us_grain_high
      return low == null || high == null ? null : { label: releaseDate(c.as_of), est, low, high, band: [low, high] as [number, number] }
    })
    .filter((r): r is NonNullable<typeof r> => r != null)
  const lo = Math.min(...rows.map((r) => r.low), nass ?? Infinity)
  const hi = Math.max(...rows.map((r) => r.high), nass ?? 0)
  return (
    <div className="conv">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={t.grid} vertical={false} />
          <XAxis dataKey="label" stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} tickLine={false} padding={{ left: 10, right: 10 }} height={34} label={xTitle('NASS release, 2025', t.muted)} />
          <YAxis domain={crop === 'silage' ? [Math.floor(lo * 0.95 / 5e5) * 5e5, Math.ceil(hi * 1.03 / 5e5) * 5e5] : [Math.floor(lo * 0.99 / 1e6) * 1e6, Math.ceil(hi * 1.01 / 1e6) * 1e6]} tickFormatter={(v: number) => `${(v / 1e6).toFixed(1)}M`} stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} width={58} label={yTitle('Acres', t.muted)} />
          <Area dataKey="band" stroke="none" fill={t.share} fillOpacity={0.14} isAnimationActive={false} />
          <Line dataKey="high" stroke={t.share} strokeDasharray="3 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
          <Line dataKey="low" stroke={t.share} strokeDasharray="3 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
          <Line dataKey="est" stroke={t.share} strokeWidth={2.5} dot={{ r: 3.5, strokeWidth: 0, fill: t.share }} isAnimationActive={false} />
          {nass != null && <ReferenceLine y={nass} stroke={t.accuracy} strokeDasharray="6 4" label={{ value: `NASS ${fmtAcres(nass)}`, position: 'insideBottomRight', fill: t.muted, fontSize: 11 }} />}
          <Tooltip
            content={({ active, payload, label }) => {
              const p = (payload?.[0] as { payload?: (typeof rows)[number] } | undefined)?.payload
              if (!active || !p) return null
              return (
                <div className="chart-tip">
                  <div className="chart-tip__title">As of {label}</div>
                  <div className="chart-tip__row">Estimate <span className="chart-tip__value">{fmtAcres(p.est)}</span></div>
                  <div className="chart-tip__row">95% range <span className="chart-tip__value">{fmtAcres(p.low)}–{fmtAcres(p.high)}</span></div>
                </div>
              )
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function MissList({ rows, crop, onSelect }: { rows: StateRow[]; crop: Crop; onSelect: (s: string) => void }) {
  const misses = useMemo(
    // the states that carry the most acres (what an acre-weighted score weighs most), largest first
    () => rows.filter((r) => r[crop]?.nass != null).sort((a, b) => b[crop]!.nass! - a[crop]!.nass!).slice(0, 5),
    [rows, crop],
  )
  return (
    <ul className="review">
      {misses.map((r) => {
        const c = r[crop]!
        return (
          <li key={r.state}>
            <button className="review__row" onClick={() => onSelect(r.state)}>
              <span className="review__id">{titleCase(r.state)}</span>
              <span className="review__why">{fmtAcres(c.est)} vs NASS {fmtAcres(c.nass)}</span>
              <span className="review__val"><ErrTag err={c.err} /></span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

type SortKey = 'state' | 'silage' | 'silage_err' | 'grain' | 'grain_err'

function StateTable({ rows, onSelect, selected }: { rows: StateRow[]; onSelect: (s: string) => void; selected: string | null }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'silage', dir: -1 })
  const val = (r: StateRow, k: SortKey): number | string =>
    k === 'state' ? r.state : k === 'silage' ? r.silage?.est ?? -1 : k === 'grain' ? r.grain?.est ?? -1 : k === 'silage_err' ? Math.abs(r.silage?.err ?? -1) : Math.abs(r.grain?.err ?? -1)
  const sorted = [...rows].sort((a, b) => (val(a, sort.key) < val(b, sort.key) ? -1 : val(a, sort.key) > val(b, sort.key) ? 1 : 0) * sort.dir)
  const head = (k: SortKey, label: string, num = true) => (
    <th className={num ? 'is-num' : undefined} aria-sort={sort.key === k ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
      <button onClick={() => setSort((s) => ({ key: k, dir: s.key === k ? ((-s.dir) as 1 | -1) : -1 }))}>
        {label}
        <span aria-hidden="true" className="sort">{sort.key === k ? (sort.dir === 1 ? '▲' : '▼') : ''}</span>
      </button>
    </th>
  )
  const cells = (c: Cell | null, first: string) =>
    c ? (
      <>
        <td className={`is-num ${first}`} title={c.low != null && c.high != null ? `95% range ${fmtFull(c.low)}–${fmtFull(c.high)}` : undefined}>{fmtFull(c.est)}</td>
        <td className="is-num ftable__nass">{fmtFull(c.nass)}</td>
        <td className="is-num ftable__err"><ErrTag err={c.err} />{c.inside === false && <span className="ftable__flag" title="NASS outside our 95% range">!</span>}</td>
      </>
    ) : (
      <><td className={`is-num ${first}`}>—</td><td className="is-num ftable__nass">—</td><td className="is-num ftable__err">—</td></>
    )
  return (
    <div className="ftable ftable--states">
      <div className="ftable__scroll">
        <table>
          <thead>
            <tr className="ftable__groups">
              <th />
              <th colSpan={3} className="grp grp--silage"><i className="dot dot--silage" />Silage</th>
              <th colSpan={3} className="grp grp--grain"><i className="dot dot--grain" />Grain</th>
            </tr>
            <tr className="ftable__cols">
              {head('state', 'State', false)}
              {head('silage', 'Ours')}
              <th className="is-num"><span className="th__plain">NASS</span></th>
              {head('silage_err', 'Error')}
              {head('grain', 'Ours')}
              <th className="is-num"><span className="th__plain">NASS</span></th>
              {head('grain_err', 'Error')}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.state} className={r.state === selected ? 'is-selected' : undefined} onClick={() => onSelect(r.state)}>
                <td className="ftable__state"><button className="link" onClick={() => onSelect(r.state)}>{titleCase(r.state)}</button></td>
                {cells(r.silage, 'grp-start')}
                {cells(r.grain, 'grp-start')}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function StateDrawer({ row, data, onClose }: { row: StateRow; data: Forecast; onClose: () => void }) {
  return (
    <aside className="glass drawer" aria-label={titleCase(row.state)}>
      <button className="drawer__close" aria-label="Close state" onClick={onClose}>
        <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" stroke="currentColor" strokeWidth="2"><path d="M2 2l10 10M12 2L2 12" /></svg>
      </button>
      <div className="eyebrow">2025, acres harvested</div>
      <h2 className="field__title">{titleCase(row.state)}</h2>
      {(['silage', 'grain'] as Crop[]).map((crop) => {
        const c = row[crop]
        return (
          <section className="block" key={crop}>
            <div className="block__head"><h3>Corn for {crop}</h3>{c && <ErrTag err={c.err} />}</div>
            {!c ? (
              <p className="muted">No {crop} estimate: NASS publishes no 2025 {crop} area for this state.</p>
            ) : (
              <>
                <RangeBar cell={c} />
                <dl className="statgrid">
                  <div><dt>Our estimate</dt><dd>{fmtFull(c.est)}</dd></div>
                  <div><dt>NASS 2025</dt><dd>{fmtFull(c.nass)}</dd></div>
                  <div><dt>95% range</dt><dd>{fmtAcres(c.low)}–{fmtAcres(c.high)}</dd></div>
                  <div><dt>Std. error / CV</dt><dd>{fmtAcres(c.se)}{c.se && c.est ? ` / ${((100 * c.se) / c.est).toFixed(1)}%` : ''}</dd></div>
                </dl>
                <p className="muted small">
                  {c.nass == null ? 'NASS publishes no row for this state.' : c.inside ? 'NASS final falls inside our 95% range.' : 'NASS final falls outside our 95% range.'}
                </p>
              </>
            )}
          </section>
        )
      })}
      <p className="muted small">{data.estimate_note}</p>
    </aside>
  )
}

/** One axis: our 95% range as a bar, our estimate as a tick, NASS as a diamond. */
function RangeBar({ cell }: { cell: Cell }) {
  const lo = Math.min(cell.low ?? cell.est, cell.nass ?? cell.est)
  const hi = Math.max(cell.high ?? cell.est, cell.nass ?? cell.est)
  const pad = (hi - lo) * 0.08 || cell.est * 0.05
  const x = (v: number) => `${((v - (lo - pad)) / (hi - lo + 2 * pad)) * 100}%`
  return (
    <div className="rangebar" aria-hidden="true">
      <div className="rangebar__track" />
      {cell.low != null && cell.high != null && <div className="rangebar__band" style={{ left: x(cell.low), width: `calc(${x(cell.high)} - ${x(cell.low)})` }} />}
      <div className="rangebar__est" style={{ left: x(cell.est) }} />
      {cell.nass != null && <div className="rangebar__nass" style={{ left: x(cell.nass) }} title="NASS" />}
      <div className="rangebar__labels"><span>ours</span><span>◆ NASS</span></div>
    </div>
  )
}

export function ForecastKey({ crop }: { crop: Crop }) {
  return (
    <div className="glass mapkey">
      <span className="mapkey__title">Our 2025 {crop} estimate vs NASS</span>
      <span className="errkey">
        {[...ERROR_STEPS].reverse().map((s) => <i key={`u${s.label}`} style={{ background: s.under }} title={`under by ${s.label}`} />)}
        <b>0</b>
        {ERROR_STEPS.map((s) => <i key={`o${s.label}`} style={{ background: s.over }} title={`over by ${s.label}`} />)}
      </span>
      <span className="mapkey__note">Blue = below NASS, orange = above; steps 5 / 15 / 30%. Grey = no NASS row.</span>
      <span className="mapkey__fine">Estimate uses only reports released by Dec 1, 2025. Prototype, not a USDA or NASS release.</span>
    </div>
  )
}

/** "12.7% vs 13.8% for the first forecast's method", from the saved backtest; null when not recorded. */
function backtestPair(data: { silage_method?: unknown }): string | null {
  const m = data.silage_method as { chosen?: string; backtest_acre_weighted_abs_pct_error?: Record<string, number> } | undefined
  const err = m?.backtest_acre_weighted_abs_pct_error
  const chosen = m?.chosen && err ? err[m.chosen] : undefined
  const first = err ? err['S1'] : undefined
  if (chosen == null) return null
  return first != null ? `${chosen.toFixed(1)}% vs ${first.toFixed(1)}% for the first forecast's method` : `${chosen.toFixed(1)}%`
}

/** Our US error in every backtest year (each forecast with only what was known then) and in 2025, against the
 *  NASS-style 90% margin: shows 2025 is a typical year for the method, not a lucky or unlucky one. */
function TrackRecord({ data, crop }: { data: Forecast; crop: Crop }) {
  const t = useTheme().chart
  const rel = data.reliability?.[crop] ?? null
  const now = data.us[crop].err
  const rows = [
    ...Object.entries(data.backtest[crop].us_total)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([year, v]) => ({ year, err: v.pct_error, is2025: false })),
    ...(now == null ? [] : [{ year: '2025', err: Math.round(now * 1000) / 10, is2025: true }]),
  ]
  if (!rows.length) return null
  const m = rel?.margin90_pct ?? null
  const top = Math.ceil(Math.max(m ?? 0, ...rows.map((r) => Math.abs(r.err))) + 1)
  const inside = m == null ? null : rows.filter((r) => !r.is2025 && Math.abs(r.err) <= m).length
  const past = rows.filter((r) => !r.is2025).length
  return (
    <section>
      <h2 className="rail__title">Track record: our US {crop} error by year</h2>
      <div className="track">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={t.grid} vertical={false} />
            {m != null && <ReferenceArea y1={-m} y2={m} fill={t.share} fillOpacity={0.12} stroke="none" />}
            <ReferenceLine y={0} stroke={t.axis} />
            <XAxis dataKey="year" stroke={t.axis} tick={{ fill: t.muted, fontSize: 11 }} tickLine={false} interval={0} height={30}
              tickFormatter={(y: string) => (rows.length > 9 && y !== '2025' && Number(y) % 2 ? '' : `'${y.slice(2)}`)} label={xTitle('Year (2025 = submitted)', t.muted)} />
            <YAxis domain={[-top, top]} ticks={trackTicks(top)} tickFormatter={(v: number) => `${v > 0 ? '+' : ''}${v}%`} stroke={t.axis} tick={{ fill: t.muted, fontSize: 11 }} width={46} label={yTitle('vs NASS final', t.muted)} />
            <Bar dataKey="err" isAnimationActive={false} radius={[2, 2, 2, 2]}>
              {rows.map((r) => <BarCell key={r.year} fill={r.is2025 ? t.accuracy : t.share} fillOpacity={r.is2025 ? 1 : 0.75} />)}
            </Bar>
            <Tooltip cursor={{ fill: 'rgba(255,255,255,0.05)' }}
              content={({ active, payload }) => {
                const p = (payload?.[0] as { payload?: (typeof rows)[number] } | undefined)?.payload
                if (!active || !p) return null
                return (
                  <div className="chart-tip">
                    <div className="chart-tip__title">{p.year}{p.is2025 ? ' (submitted)' : ' (backtest)'}</div>
                    <div className="chart-tip__row">Our US {crop} vs NASS final <span className="chart-tip__value">{p.err > 0 ? '+' : ''}{p.err.toFixed(1)}%</span></div>
                  </div>
                )
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="rail__note rail__note--keep">
        {m != null && <>Shaded band = our ±{m}% margin of error (90%). </>}
        {inside != null && <>{inside} of {past} backtest years fell inside it{now != null ? `; 2025 came in at ${now > 0 ? '+' : ''}${(now * 100).toFixed(1)}%` : ''}. </>}
        Each year was forecast with only what was known before January.
      </p>
    </section>
  )
}

/** Symmetric round ticks for the track-record axis: steps of 2% up to 6%, else 4%. */
function trackTicks(top: number): number[] {
  const step = top > 6 ? 4 : 2
  const n = Math.floor(top / step)
  return Array.from({ length: 2 * n + 1 }, (_, i) => (i - n) * step)
}

/** Why the silage misses: 2025 silage broke from each state's own recent history, which no pre-January report shows.
 *  Uses NASS 2025 only to explain after the fact (never to build or choose the forecast). */
function WhyMisses({ data, onSelect }: { data: Forecast; onSelect: (s: string) => void }) {
  const w = data.why_silage
  const rows = useMemo(
    () => data.states
      .filter((r) => r.silage?.nass != null && r.silage.hist5 != null && (r.silage.err ?? 0) > w!.threshold_pct / 100)
      .sort((a, b) => (b.silage!.est - b.silage!.nass!) - (a.silage!.est - a.silage!.nass!))
      .slice(0, 4),
    [data, w],
  )
  if (!w || !rows.length) return null
  return (
    <section>
      <h2 className="rail__title">Why the silage misses</h2>
      <p className="rail__note rail__note--keep">
        In <b>{w.over_below_history} of {w.over}</b> states we over-called by more than {w.threshold_pct}%, 2025 silage fell below that
        state's own {w.history_years.replace('-', '–')} average; in <b>{w.under_above_history} of {w.under}</b> we under-called, it rose above it.
        2025 broke from recent history, and no report before January shows that.
      </p>
      <table className="mini-table whymiss">
        <thead><tr><th>State</th><th className="num">Ours</th><th className="num">{w.history_years.replace('-', '–')} avg</th><th className="num">NASS 2025</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.state} onClick={() => onSelect(r.state)}>
              <td>{titleCase(r.state)}</td>
              <td className="num">{fmtAcres(r.silage!.est)}</td>
              <td className="num">{fmtAcres(r.silage!.hist5!)}</td>
              <td className="num">{fmtAcres(r.silage!.nass)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
