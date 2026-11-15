import { useMemo, useState } from 'react'
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useTheme } from '../theme'
import type { Cell, Crop, Forecast, StateRow } from './forecastTypes'
import { ERROR_STEPS, fmtAcres, fmtFull, fmtPct, releaseDate, titleCase } from './forecastFormat'
import { ScoreUpload } from './ScoreUpload'

const CROP_LABEL: Record<Crop, string> = { silage: 'corn for silage', grain: 'corn for grain' }

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
  const md = data.states.find((s) => s.state === 'MARYLAND')
  const sel = data.states.find((s) => s.state === selected) ?? null
  return (
    <>
      <div className="lead">
        <section className="kpis" aria-label="2025 headline numbers">
          <UsCard crop="silage" cell={data.us.silage} />
          <UsCard crop="grain" cell={data.us.grain} />
          <article className="glass kpi">
            <h2 className="kpi__label">States within 10% of NASS</h2>
            <div className="kpi__value">
              {data.scores.grain.within_10pct}
              <span className="kpi__of">/{data.scores.grain.states} grain</span>
            </div>
            <div className="kpi__sub">
              {data.scores.silage.within_10pct}/{data.scores.silage.states} silage
            </div>
            <div className="kpi__foot">
              Acre-weighted error: grain {data.scores.grain.acre_weighted_abs_pct_error}%, silage {data.scores.silage.acre_weighted_abs_pct_error}%
            </div>
          </article>
          {md && (
            <button className="glass kpi kpi--button" onClick={() => onSelect('MARYLAND')}>
              <h2 className="kpi__label">Maryland, {CROP_LABEL[crop]}</h2>
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
            <h2 className="rail__title">US silage estimate through the season</h2>
            <p className="rail__note">Re-estimated at each 2025 NASS release. Band = 95% range; dashed = NASS final.</p>
            <ConvergenceChart data={data} />
          </section>
          <section>
            <div className="rail__head">
              <h2 className="rail__title">Biggest misses, {crop}</h2>
              <button className="link" onClick={() => onTable(true)}>All states</button>
            </div>
            <MissList rows={data.states} crop={crop} onSelect={onSelect} />
          </section>
          <section>
            <h2 className="rail__title">How it works</h2>
            <p className="rail__note rail__note--keep">
              Grain: NASS's Nov 14, 2025 forecast. Silage: each state's usual share of non-grain corn, 2022–2024. Chosen by backtest
              on 2023–2024 (US silage {fmtPct(data.backtest.silage.us_total['2023'].pct_error / 100)} and {fmtPct(data.backtest.silage.us_total['2024'].pct_error / 100)}).
              No January 2026 data used.
            </p>
          </section>
          <ScoreUpload data={data} crop={crop} />
        </aside>
      )}

      {showTable && (
        <section className="glass sheet" aria-label="All states">
          <div className="sheet__headrow">
            <h1 className="sheet__title">All states, 2025</h1>
            <button className="ghost-btn" onClick={() => onTable(false)}>Back to map</button>
          </div>
          <p className="sheet__lede">{data.estimate_note} {data.reference_note}</p>
          <StateTable rows={data.states} onSelect={onSelect} selected={selected} />
        </section>
      )}

      {sel && <StateDrawer row={sel} data={data} onClose={() => onSelect(null)} />}
    </>
  )
}

function UsCard({ crop, cell }: { crop: Crop; cell: Cell }) {
  return (
    <article className="glass kpi">
      <h2 className="kpi__label">US {CROP_LABEL[crop]}, 2025</h2>
      <div className="kpi__value">{fmtAcres(cell.est)}</div>
      <div className="kpi__sub">
        NASS {fmtAcres(cell.nass)} <ErrTag err={cell.err} />
      </div>
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

function ConvergenceChart({ data }: { data: Forecast }) {
  const t = useTheme().chart
  const nass = data.us.silage.nass
  const rows = data.convergence.map((c) => ({
    label: releaseDate(c.as_of),
    est: c.us_silage,
    low: c.us_silage_low,
    high: c.us_silage_high,
    band: [c.us_silage_low, c.us_silage_high] as [number, number],
  }))
  const lo = Math.min(...rows.map((r) => r.low), nass ?? Infinity)
  const hi = Math.max(...rows.map((r) => r.high), nass ?? 0)
  return (
    <div className="conv">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 10, right: 12, bottom: 0, left: -6 }}>
          <CartesianGrid stroke={t.grid} vertical={false} />
          <XAxis dataKey="label" stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} tickLine={false} padding={{ left: 10, right: 10 }} />
          <YAxis domain={[Math.floor(lo * 0.95 / 5e5) * 5e5, Math.ceil(hi * 1.03 / 5e5) * 5e5]} tickFormatter={(v: number) => `${(v / 1e6).toFixed(1)}M`} stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} width={44} />
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
    () => rows.filter((r) => r[crop]?.nass != null).sort((a, b) => Math.abs(b[crop]!.est - b[crop]!.nass!) - Math.abs(a[crop]!.est - a[crop]!.nass!)).slice(0, 4),
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
              <span className="review__why">ours {fmtAcres(c.est)} vs NASS {fmtAcres(c.nass)}</span>
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
    k === 'state' ? r.state : k === 'silage' ? r.silage?.nass ?? -1 : k === 'grain' ? r.grain?.nass ?? -1 : k === 'silage_err' ? Math.abs(r.silage?.err ?? -1) : Math.abs(r.grain?.err ?? -1)
  const sorted = [...rows].sort((a, b) => (val(a, sort.key) < val(b, sort.key) ? -1 : val(a, sort.key) > val(b, sort.key) ? 1 : 0) * sort.dir)
  const head = (k: SortKey, label: string, num = true) => (
    <th className={num ? 'is-num' : undefined} aria-sort={sort.key === k ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
      <button onClick={() => setSort((s) => ({ key: k, dir: s.key === k ? ((-s.dir) as 1 | -1) : -1 }))}>
        {label}
        <span aria-hidden="true" className="sort">{sort.key === k ? (sort.dir === 1 ? '▲' : '▼') : ''}</span>
      </button>
    </th>
  )
  const cells = (c: Cell | null) =>
    c ? (
      <>
        <td className="is-num">{fmtFull(c.est)}<div className="ftable__range">{fmtAcres(c.low)}–{fmtAcres(c.high)}</div></td>
        <td className="is-num">{fmtFull(c.nass)}</td>
        <td className="is-num"><ErrTag err={c.err} />{c.inside === false && <span className="ftable__flag" title="NASS outside our 95% range">!</span>}</td>
      </>
    ) : (
      <><td className="is-num">—</td><td className="is-num">—</td><td className="is-num">—</td></>
    )
  return (
    <div className="ftable">
      <div className="ftable__scroll">
        <table>
          <thead>
            <tr>
              {head('state', 'State', false)}
              {head('silage', 'Silage, ours')}
              <th className="is-num">NASS</th>
              {head('silage_err', 'Error')}
              {head('grain', 'Grain, ours')}
              <th className="is-num">NASS</th>
              {head('grain_err', 'Error')}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.state} className={r.state === selected ? 'is-selected' : undefined} onClick={() => onSelect(r.state)}>
                <td><button className="link" onClick={() => onSelect(r.state)}>{titleCase(r.state)}</button></td>
                {cells(r.silage)}
                {cells(r.grain)}
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
