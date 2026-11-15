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
import { ChartTip, type TipProps, xTitle, yTitle } from './charts'

interface Props {
  data: EvaluateResponse | null
  error: Error | null
  asOf: string
}

export function MetricsPanel({ data, error, asOf }: Props) {
  if (error) return <p className="inline-error">Metrics unavailable: {error.message}</p>
  if (!data) return <div className="skeleton skeleton--panel" />
  const total = data.confusion.flat().reduce((a, b) => a + b, 0)
  const si = data.labels.indexOf('Silage')
  const sHit = data.confusion[si]?.[si] ?? 0
  const sN = data.confusion[si]?.reduce((a, b) => a + b, 0) ?? 0
  const S = data.per_class.Silage
  const G = data.per_class.Grain
  const n = data.n_evaluated ?? total
  const bal = data.convergence.some((c) => c.bal_acc != null)
  const early = data.convergence.map((c) => `${shortDate(c.as_of)} ${num(bal ? (c.bal_acc ?? null) : c.acc_decided)}`).join(' · ')
  return (
    <div className="metrics">
      {data.convergence_error && <p className="inline-error" role="alert">Season chart unavailable: {data.convergence_error}</p>}
      <p className="muted small">{n} labeled BARC field-years, 2021–2023, {data.split_label ?? 'held out by field'}; full-season (Nov 30) calls.</p>
      <dl className="facts" aria-label="Held-out accuracy">
        <div><dt>Balanced accuracy</dt><dd>{num(data.balanced_accuracy ?? null)}</dd><span>{data.baseline ? `${data.baseline.name ?? 'Always grain'}: ${num(data.baseline.balanced_accuracy)}` : ''}</span></div>
        <div><dt>Silage recall</dt><dd>{num(S.recall.value)}</dd><span>95% {num(S.recall.lo)}–{num(S.recall.hi)}; {sHit} of {sN} found</span></div>
        <div><dt>Silage precision</dt><dd>{num(S.precision.value)}</dd><span>95% {num(S.precision.lo)}–{num(S.precision.hi)}</span></div>
        <div><dt>Grain recall</dt><dd>{num(G.recall.value)}</dd><span>95% {num(G.recall.lo)}–{num(G.recall.hi)}</span></div>
      </dl>

      <section className="block">
        <div className="block__head">
          <h3>Confusion matrix, 2021–2023 pooled</h3>
          <span className="block__note">rows = BARC label · columns = predicted</span>
        </div>
        <Confusion data={data} />
      </section>

      {data.convergence.length > 1 && <section className="block">
        <div className="block__head">
          <h3>How early the call is reliable</h3>
          <span className="block__note">as-of {shortDate(asOf)} marked</span>
        </div>
        <p className="facts__line">{bal ? 'Balanced accuracy' : 'Accuracy on decided fields'} by date: {early}</p>
        <Convergence data={data} asOf={asOf} />
      </section>}

      <section className="block">
        <div className="block__head"><h3>Key limits</h3></div>
        <ul className="limits">
          <li><b>One research farm.</b> All {n} labeled field-years ({sN} silage) come from BARC, Beltsville MD; not tested on other farms or states.</li>
          <li><b>Farm hold-out.</b> Holding out Central Farm, which has nearly all the silage, finds none of its silage.</li>
          <li><b>Mid-season dates use v1.</b> Before Nov 30 each date refits the v1 model on the months available; v2 needs the full season.</li>
        </ul>
      </section>

      <h2 className="sheet__h2">Details</h2>
      <details className="more section">
        <summary>Precision and recall with 95% ranges</summary>
        <PrecisionRecall data={data} />
        <p className="muted small">Wilson 95% intervals; they do not establish accuracy on new regions or account for repeated years of the same field. Abstained: {data.abstained}.</p>
      </details>
    </div>
  )
}

/** The model v2 note as its own collapsed section (placed by the Model quality tab). */
export function ModelV2Section({ data }: { data: EvaluateResponse | null }) {
  if (data?.model_version !== 'v2' || !data.selection) return null
  return (
    <details className="more section">
      <summary>Model v2: what changed and how far to trust the gain</summary>
      <ModelV2Note data={data} />
    </details>
  )
}

/** Honest note on the v2 switch: what changed, how it was chosen, and how uncertain the gain is. */
function ModelV2Note({ data }: { data: EvaluateResponse }) {
  const sel = data.selection!
  const v1 = data.v1_same_split
  const silage = (cm: number[][] | undefined) => {
    const i = data.labels.indexOf('Silage')
    return cm && i >= 0 ? `${cm[i][i]}/${cm[i].reduce((a, b) => a + b, 0)}` : '—'
  }
  const [lo, hi] = sel.gain_vs_v1_field_bootstrap_95ci
  return (
    <section className="reliability" aria-label="About model v2">
      <h3>Model v2</h3>
      <p>
        NDVI plus harvest-timing features.{v1 && <> Recovers <b>{silage(data.confusion)}</b> silage field-years (balanced accuracy <b>{num(data.balanced_accuracy ?? null)}</b>) vs <b>{silage(v1.confusion_matrix)}</b> (<b>{num(v1.balanced_accuracy)}</b>) for v1; optimistic, since this split was seen when v2 was picked.</>}
      </p>
      <div>
        <p>
          {data.model_name}: the nine NDVI features plus four harvest-timing features (when greenness falls, how sharply, and whether it regrows), chosen from eight candidates in a comparison written down before any was scored.
        </p>
        <p>
          Repeating the selection inside each training fold gives about <b>{num(sel.nested_selection_mean_balanced_accuracy)}</b> balanced accuracy against <b>{num(sel.v1_mean_balanced_accuracy_same_seeds)}</b> for v1, and a 95% bootstrap range for the gain of <b>{num(lo, 3)}</b> to <b>{num(hi, 3)}</b>, which touches zero. The gain rests on three or four silage field-years.
        </p>
        <p className="muted small">Details: {sel.details}. Mid-season dates still use the v1 model, refit on the months available by each date.</p>
      </div>
    </section>
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
        <BarChart data={rows} margin={{ top: 12, right: 12, bottom: 0, left: 0 }} barGap={6} barCategoryGap="28%">
          <CartesianGrid stroke={t.grid} vertical={false} />
          <XAxis dataKey="metric" stroke={t.axis} tick={{ fill: t.ink, fontSize: 13 }} tickLine={false} height={36} label={xTitle('Held-out score, pooled 2021–2023', t.muted)} />
          <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} width={58} label={yTitle('Score (0–1)', t.muted)} />
          <Tooltip cursor={{ fill: t.grid, fillOpacity: 0.4 }} content={(p) => <ChartTip {...(p as unknown as TipProps)} title={(l) => l} value={(v) => v.toFixed(2)} />} />
          <Legend verticalAlign="top" height={30} iconType="square" wrapperStyle={{ fontSize: 13, color: t.ink }} />
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
      <LineChart data={rows} margin={{ top: 12, right: 24, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={t.grid} vertical={false} />
        <XAxis dataKey="label" stroke={t.axis} tick={{ fill: t.ink, fontSize: 13 }} tickLine={false} padding={{ left: 16, right: 16 }} height={36} label={xTitle('As-of date', t.muted)} />
        <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v: number) => `${v * 100}%`} stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} width={58} label={yTitle('Percent', t.muted)} />
        {current && <ReferenceLine x={current.label} stroke={t.muted} strokeDasharray="4 4" />}
        <Tooltip content={(p) => <ChartTip {...(p as unknown as TipProps)} title={(l) => `As of ${l}`} value={(v) => pct(v)} />} />
        <Legend verticalAlign="top" height={30} iconType="plainline" wrapperStyle={{ fontSize: 13, color: t.ink }} />
        <Line dataKey="share_decided" name="Share of fields decided" stroke={t.share} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, fill: t.surface }} activeDot={{ r: 6 }} isAnimationActive={false} />
        <Line dataKey={rows.some((r) => r.bal_acc != null) ? 'bal_acc' : 'acc_decided'} name={rows.some((r) => r.bal_acc != null) ? 'Balanced accuracy (pooled 2021–2023)' : 'Accuracy on decided'} stroke={t.accuracy} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, fill: t.surface }} activeDot={{ r: 6 }} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}
