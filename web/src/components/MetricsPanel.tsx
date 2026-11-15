import {
  Bar,
  BarChart,
  CartesianGrid,
  ErrorBar,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { EvaluateResponse, Label } from '../api'
import { num, pct, shortDate } from '../format'
import { DATA, useTheme } from '../theme'
import { ChartTip, type TipProps } from './charts'

interface Props {
  data: EvaluateResponse | null
  error: Error | null
  asOf: string
}

export function MetricsPanel({ data, error, asOf }: Props) {
  if (error) return <p className="inline-error">Metrics unavailable: {error.message}</p>
  if (!data) return <div className="skeleton skeleton--panel" />
  const total = data.confusion.flat().reduce((a, b) => a + b, 0)
  const correct = data.labels.reduce((a, _, i) => a + (data.confusion[i]?.[i] ?? 0), 0)
  const si = data.labels.indexOf('Silage')
  const gi = data.labels.indexOf('Grain')
  const sHit = data.confusion[si]?.[si] ?? 0
  const sN = data.confusion[si]?.reduce((a, b) => a + b, 0) ?? 0
  const S = data.per_class.Silage
  const G = data.per_class.Grain
  return (
    <div className="metrics">
      <p className="finding">
        On field-years {data.split_label ?? 'held out by year'} the model recovers <b>{sHit}/{sN}</b> silage field-years (recall <b>{num(S.recall.value)}</b>) and keeps grain recall at{' '}
        <b>{num(G.recall.value)}</b>{gi >= 0 ? '' : ''}.
      </p>
      <section className="reliability" aria-label="Reliability of these scores">
        <h3>Reliability of these scores</h3>
        <p>
          Wilson 95% intervals for these held-out results are <b>{num(S.recall.lo)}</b> to <b>{num(S.recall.hi)}</b> for silage recall and{' '}
          <b>{num(S.precision.lo)}</b> to <b>{num(S.precision.hi)}</b> for silage precision. These intervals do not establish accuracy on new regions or account for repeated years of the same field.
        </p>
        <p className="muted small">
          Based on {data.n_evaluated ?? total} labeled field-years scored out of fold. With few silage examples the ranges are wide; read overlapping ranges as "not yet distinguishable".
        </p>
      </section>
      <div className="tiles">
        <Tile kicker="Evaluated field-years" value={String(data.n_evaluated ?? total)} />
        <Tile kicker="Correct" value={`${correct} / ${total}`} sub={pct(total ? correct / total : null)} />
        <Tile kicker="Abstained" value={String(data.abstained)} sub="too few clear looks" />
        <Tile kicker="Balanced accuracy" value={data.balanced_accuracy != null ? num(data.balanced_accuracy) : '—'} sub={data.baseline ? `${data.baseline.name ?? 'Baseline'}: ${num(data.baseline.balanced_accuracy)}` : (data.split_label ?? '')} />
      </div>

      <section className="block">
        <div className="block__head">
          <h3>Confusion matrix</h3>
          <span className="block__note">rows = BARC label · columns = predicted</span>
        </div>
        <Confusion data={data} />
      </section>

      <section className="block">
        <div className="block__head">
          <h3>Precision and recall</h3>
          <span className="block__note">bars = estimate · whiskers = 95% CI</span>
        </div>
        <PrecisionRecall data={data} />
      </section>

      {data.convergence.length > 1 && <section className="block">
        <div className="block__head">
          <h3>Convergence through the season</h3>
          <span className="block__note">as-of {shortDate(asOf)} marked</span>
        </div>
        <Convergence data={data} asOf={asOf} />
      </section>}
    </div>
  )
}

function Tile({ kicker, value, sub }: { kicker: string; value: string; sub?: string }) {
  return (
    <div className="tile">
      <div className="tile__kicker">{kicker}</div>
      <div className="tile__value">{value}</div>
      {sub && <div className="tile__sub">{sub}</div>}
    </div>
  )
}

function Confusion({ data }: { data: EvaluateResponse }) {
  const max = Math.max(1, ...data.confusion.flat())
  const color = (l: Label) => (l === 'Silage' ? DATA.silage : DATA.grain)
  return (
    <div className="cm" style={{ gridTemplateColumns: `auto repeat(${data.labels.length}, 1fr)` }} role="table" aria-label="Confusion matrix">
      <div className="cm__corner" role="columnheader">
        <span>label ↓</span>
        <span>predicted →</span>
      </div>
      {data.labels.map((l) => (
        <div key={`h-${l}`} className="cm__colhead" role="columnheader">
          <span className="swatch swatch--fill" style={{ background: color(l) }} />
          {l}
        </div>
      ))}
      {data.labels.map((rowLabel, i) => (
        <div key={rowLabel} className="cm__row" role="row">
          <div className="cm__rowhead" role="rowheader">
            <span className="swatch swatch--outline" style={{ borderColor: color(rowLabel) }} />
            {rowLabel}
          </div>
          {data.labels.map((colLabel, j) => {
            const v = data.confusion[i]?.[j] ?? 0
            const diag = i === j
            return (
              <div
                key={colLabel}
                role="cell"
                className={`cm__cell ${diag ? 'cm__cell--diag' : 'cm__cell--off'}`}
                style={{ ['--strength' as string]: String(0.12 + 0.55 * (v / max)) }}
              >
                <span className="cm__n">{v}</span>
                <span className="cm__tag">{diag ? 'correct' : 'wrong'}</span>
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

function PrecisionRecall({ data }: { data: EvaluateResponse }) {
  const t = useTheme().chart
  const g = data.per_class.Grain
  const s = data.per_class.Silage
  const rows = [
    { metric: 'Precision', Grain: g.precision.value, gErr: [g.precision.value - g.precision.lo, g.precision.hi - g.precision.value], Silage: s.precision.value, sErr: [s.precision.value - s.precision.lo, s.precision.hi - s.precision.value] },
    { metric: 'Recall', Grain: g.recall.value, gErr: [g.recall.value - g.recall.lo, g.recall.hi - g.recall.value], Silage: s.recall.value, sErr: [s.recall.value - s.recall.lo, s.recall.hi - s.recall.value] },
  ]
  return (
    <>
      <ResponsiveContainer width="100%" height={230}>
        <BarChart data={rows} margin={{ top: 12, right: 12, bottom: 0, left: -12 }} barGap={6} barCategoryGap="28%">
          <CartesianGrid stroke={t.grid} vertical={false} />
          <XAxis dataKey="metric" stroke={t.axis} tick={{ fill: t.ink, fontSize: 15 }} tickLine={false} />
          <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} stroke={t.axis} tick={{ fill: t.muted, fontSize: 14 }} />
          <Tooltip cursor={{ fill: t.grid, fillOpacity: 0.4 }} content={(p) => <ChartTip {...(p as unknown as TipProps)} title={(l) => l} value={(v) => v.toFixed(2)} />} />
          <Legend verticalAlign="top" height={30} iconType="square" wrapperStyle={{ fontSize: 14, color: t.ink }} />
          <Bar dataKey="Grain" fill={DATA.grain} radius={[4, 4, 0, 0]} isAnimationActive={false}>
            <ErrorBar dataKey="gErr" width={10} strokeWidth={2} stroke={t.ink} />
          </Bar>
          <Bar dataKey="Silage" fill={DATA.silage} radius={[4, 4, 0, 0]} isAnimationActive={false}>
            <ErrorBar dataKey="sErr" width={10} strokeWidth={2} stroke={t.ink} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <table className="mini-table">
        <thead>
          <tr>
            <th>Class</th>
            <th>Precision [95% CI]</th>
            <th>Recall [95% CI]</th>
            <th>n</th>
          </tr>
        </thead>
        <tbody>
          {(['Grain', 'Silage'] as const).map((c) => {
            const m = data.per_class[c]
            return (
              <tr key={c}>
                <td>
                  <span className="swatch swatch--fill" style={{ background: c === 'Silage' ? DATA.silage : DATA.grain }} /> {c}
                </td>
                <td className="num">
                  {num(m.precision.value)} <span className="muted">[{num(m.precision.lo)}, {num(m.precision.hi)}]</span>
                </td>
                <td className="num">
                  {num(m.recall.value)} <span className="muted">[{num(m.recall.lo)}, {num(m.recall.hi)}]</span>
                </td>
                <td className="num">{m.support}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </>
  )
}

function Convergence({ data, asOf }: { data: EvaluateResponse; asOf: string }) {
  const t = useTheme().chart
  const rows = data.convergence.map((c) => ({ ...c, label: shortDate(c.as_of) }))
  const current = rows.find((r) => r.as_of === asOf)
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={rows} margin={{ top: 12, right: 24, bottom: 0, left: -12 }}>
        <CartesianGrid stroke={t.grid} vertical={false} />
        <XAxis dataKey="label" stroke={t.axis} tick={{ fill: t.ink, fontSize: 14 }} tickLine={false} padding={{ left: 16, right: 16 }} />
        <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v: number) => `${v * 100}%`} stroke={t.axis} tick={{ fill: t.muted, fontSize: 14 }} />
        {current && <ReferenceLine x={current.label} stroke={t.muted} strokeDasharray="4 4" />}
        <Tooltip content={(p) => <ChartTip {...(p as unknown as TipProps)} title={(l) => `As of ${l}`} value={(v) => pct(v)} />} />
        <Legend verticalAlign="top" height={30} iconType="plainline" wrapperStyle={{ fontSize: 14, color: t.ink }} />
        <Line dataKey="share_decided" name="Share of fields decided" stroke={t.share} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, fill: t.surface }} activeDot={{ r: 6 }} isAnimationActive={false} />
        <Line dataKey={rows.some((r) => r.bal_acc != null) ? 'bal_acc' : 'acc_decided'} name={rows.some((r) => r.bal_acc != null) ? 'Balanced accuracy (pooled 2021–2023)' : 'Accuracy on decided'} stroke={t.accuracy} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, fill: t.surface }} activeDot={{ r: 6 }} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}
