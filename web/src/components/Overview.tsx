import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { EvaluateResponse, Pred, RollupResponse } from '../api'
import { acres, num, pct, shortDate } from '../format'
import { DATA, useTheme } from '../theme'
import { ChartTip, type TipProps } from './charts'

export interface ReviewItem {
  id: number
  kind: 'mismatch' | 'abstained'
  reason: string
  pred?: Pred
}

interface Props {
  year: number
  asOf: string
  counts: { Grain: number; Silage: number; Pending: number; Insufficient: number; total: number }
  rollup: RollupResponse | null
  evaluation: EvaluateResponse | null
  review: ReviewItem[]
  onSelect: (id: number) => void
  onOpenQuality: () => void
  onOpenFields: () => void
}

const REVIEW_ROWS = 3

/** The one-glance screen: four key figures across the top and a rail of season, accuracy and review items. */
export function Overview({ year, asOf, counts, rollup, evaluation, review, onSelect, onOpenQuality, onOpenFields }: Props) {
  const decided = counts.Grain + counts.Silage
  const S = evaluation?.per_class.Silage
  const mismatches = review.filter((r) => r.kind === 'mismatch').length
  const abstained = review.length - mismatches
  const w = (n: number) => `${counts.total ? (n / counts.total) * 100 : 0}%`

  return (
    <>
      <div className="lead">
      <section className="glass summary" aria-label="Season summary">
        <h1 className="summary__title">
          {year} season, as of {shortDate(asOf)}
        </h1>
        <p className="summary__text">
          {decided} of {counts.total} BARC corn fields are called so far: {counts.Silage} silage and {counts.Grain} grain.{' '}
          {counts.Pending > 0 && <>{counts.Pending} are still waiting on a harvest signal. </>}
          {counts.Insufficient > 0 && <>{counts.Insufficient} are too cloudy to call. </>}
          {rollup && (
            <>
              Scaled up, {rollup.region} grew about {acres(rollup.acres)} acres of corn for silage,{' '}
              {Math.abs(((rollup.acres - rollup.census_acres) / rollup.census_acres) * 100).toFixed(0)}% {rollup.acres >= rollup.census_acres ? 'above' : 'below'} the {rollup.year} Census.
            </>
          )}
        </p>
        <ul className="summary__meta" aria-label="About the data">
          <li>Imagery: Sentinel-2, 10 m</li>
          <li>Labels: BARC 2021 to 2023</li>
          <li>Scores: whole years held out</li>
          <li>Prototype, not a USDA or NASS release</li>
        </ul>
      </section>
      <section className="kpis" aria-label="Key figures">
        <article className="glass kpi">
          <h2 className="kpi__label">{rollup?.region ?? 'Maryland'} silage acres, {year}</h2>
          <div className="kpi__value">{rollup ? acres(rollup.acres) : '—'}</div>
          {rollup && <div className="kpi__sub">95% range {acres(rollup.ci[0])}–{acres(rollup.ci[1])}</div>}
          {rollup && <div className="kpi__foot">Census {rollup.year} reported {acres(rollup.census_acres)}</div>}
        </article>
        <article className="glass kpi">
          <h2 className="kpi__label">Fields decided by {shortDate(asOf)}</h2>
          <div className="kpi__value">
            {decided} <span className="kpi__of">of {counts.total}</span>
          </div>
          <div className="kpi__bar" aria-hidden="true">
            <span style={{ width: w(counts.Silage), background: DATA.silage }} />
            <span style={{ width: w(counts.Grain), background: DATA.grain }} />
            <span style={{ width: w(counts.Insufficient), background: '#c9d3cf' }} />
          </div>
          <div className="kpi__foot">
            {counts.Silage} silage, {counts.Grain} grain, {counts.Insufficient} abstained
          </div>
        </article>
        <article className="glass kpi">
          <h2 className="kpi__label">Silage recall, held-out years</h2>
          <div className="kpi__value">{S ? num(S.recall.value) : '—'}</div>
          {S && <div className="kpi__sub">95% range {num(S.recall.lo)}–{num(S.recall.hi)}</div>}
          {evaluation && (
            <div className="kpi__foot">
              {evaluation.confusion[evaluation.labels.indexOf('Silage')]?.[evaluation.labels.indexOf('Silage')] ?? 0} of {S?.support ?? 0} silage field-years found
            </div>
          )}
        </article>
        <article className="glass kpi">
          <h2 className="kpi__label">Needs a second look</h2>
          <div className="kpi__value kpi__value--warn">{review.length}</div>
          <div className="kpi__sub">{mismatches} disagree with BARC</div>
          <div className="kpi__foot">{abstained} too cloudy to call</div>
        </article>
      </section>
      </div>

      <aside className="glass rail" aria-label="Season and accuracy">
        <section>
          <h2 className="rail__title">How the call firms up through the season</h2>
          <p className="rail__note">Share of fields decided, and accuracy on those decided.</p>
          {evaluation ? <Convergence data={evaluation} asOf={asOf} /> : <div className="skeleton skeleton--chart" />}
          <div className="linekey">
            <span><i style={{ background: '#8fcdf2' }} />Fields decided</span>
            <span><i style={{ background: '#f0eee6' }} />Accuracy on decided</span>
          </div>
        </section>

        <section>
          <div className="rail__head">
            <h2 className="rail__title">Held-out accuracy</h2>
            <button className="link" onClick={onOpenQuality}>
              Model quality
            </button>
          </div>
          {evaluation && <MiniConfusion data={evaluation} />}
        </section>

        <section>
          <h2 className="rail__title">Needs a second look</h2>
          {review.length === 0 ? (
            <p className="rail__note">Nothing to review at this date.</p>
          ) : (
            <ul className="review">
              {review.slice(0, REVIEW_ROWS).map((r) => (
                <li key={r.id}>
                  <button className="review__row" onClick={() => onSelect(r.id)}>
                    <span className={`review__mark review__mark--${r.kind}`} aria-hidden="true" />
                    <span className="review__id">Field {r.id}</span>
                    <span className="review__why">{r.reason}</span>
                    <span className="review__val">{r.kind === 'abstained' ? 'Abstained' : `P ${num(r.pred?.p_silage)}`}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {review.length > REVIEW_ROWS && (
            <button className="link review__more" onClick={onOpenFields}>
              See all {review.length} in Fields
            </button>
          )}
        </section>
      </aside>
    </>
  )
}

function Convergence({ data, asOf }: { data: EvaluateResponse; asOf: string }) {
  const t = useTheme().chart
  const rows = data.convergence.map((c) => ({ ...c, label: shortDate(c.as_of) }))
  const current = rows.find((r) => r.as_of === asOf)
  return (
    <ResponsiveContainer width="100%" height={150}>
      <LineChart data={rows} margin={{ top: 16, right: 16, bottom: 0, left: -18 }}>
        <CartesianGrid stroke={t.grid} vertical={false} />
        <XAxis dataKey="label" stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} tickLine={false} padding={{ left: 12, right: 12 }} />
        <YAxis domain={[0, 1]} ticks={[0, 0.5, 1]} tickFormatter={(v: number) => `${v * 100}%`} stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} />
        {current && <ReferenceLine x={current.label} stroke={t.share} strokeOpacity={0.35} strokeWidth={28} />}
        <Tooltip content={(p) => <ChartTip {...(p as unknown as TipProps)} title={(l) => `As of ${l}`} value={(v) => pct(v)} />} />
        <Line dataKey="share_decided" name="Fields decided" stroke={t.share} strokeWidth={2.5} dot={{ r: 3.5, strokeWidth: 0, fill: t.share }} isAnimationActive={false} />
        <Line dataKey="acc_decided" name="Accuracy on decided" stroke={t.accuracy} strokeWidth={2.5} dot={{ r: 3.5, strokeWidth: 0, fill: t.accuracy }} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

function MiniConfusion({ data }: { data: EvaluateResponse }) {
  const total = data.confusion.flat().reduce((a, b) => a + b, 0)
  const correct = data.labels.reduce((a, _, i) => a + (data.confusion[i]?.[i] ?? 0), 0)
  return (
    <>
      <p className="rail__note">
        {correct} of {total} labeled field-years correct, whole years held out.
      </p>
      <div className="mcm" role="table" aria-label="Confusion matrix">
        <div role="row" className="mcm__row">
          <span role="columnheader" />
          {data.labels.map((l) => (
            <span role="columnheader" key={l} className="mcm__col">
              Called {l.toLowerCase()}
            </span>
          ))}
        </div>
        {data.labels.map((row, i) => (
          <div role="row" className="mcm__row" key={row}>
            <span role="rowheader" className="mcm__rowhead">
              {row}
            </span>
            {data.labels.map((col, j) => (
              <span role="cell" key={col} className={`mcm__cell ${i === j ? 'is-right' : 'is-wrong'}`}>
                {data.confusion[i]?.[j] ?? 0}
              </span>
            ))}
          </div>
        ))}
      </div>
    </>
  )
}
