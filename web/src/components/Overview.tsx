import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { EvaluateResponse, Pred, RollupResponse, UnlabeledYearView } from '../api'
import { acres, num, pct, shortDate } from '../format'
import { DATA, useTheme } from '../theme'
import { ChartTip, type TipProps, xTitle, yTitle } from './charts'
import { Pending } from './Pending'

export interface ReviewItem {
  id: number
  kind: 'mismatch' | 'abstained'
  reason: string
  pred?: Pred
}

interface Props {
  year: number
  asOf: string
  /** total = every BARC field; labeled = fields with a BARC Grain/Silage label this year (the only ones scored) */
  counts: { Grain: number; Silage: number; Pending: number; Insufficient: number; total: number; labeled: number }
  rollup: RollupResponse | null
  /** season-end model calls on blank-label fields that CDL marks as corn */
  unlabeled?: UnlabeledYearView | null
  unlabeledError?: Error | null
  /** the selected date is Nov 30; unlabeled calls are season-end calls and get no numbers before it */
  unlabeledAtSeasonEnd?: boolean
  evaluation: EvaluateResponse | null
  review: ReviewItem[]
  onSelect: (id: number) => void
  onOpenQuality: () => void
  onOpenFields: () => void
  /** real data so far: one held-out call per field-year at season end, no as-of history */
  seasonEnd: boolean
}

const REVIEW_ROWS = 3

/** The one-glance screen: four key figures across the top and a rail of season, accuracy and review items. */
export function Overview({ year, asOf, counts, rollup, unlabeled, unlabeledError, unlabeledAtSeasonEnd = false, evaluation, review, onSelect, onOpenQuality, onOpenFields, seasonEnd }: Props) {
  const chart = useTheme().chart
  const decided = counts.Grain + counts.Silage
  const S = evaluation?.per_class.Silage
  const mismatches = review.filter((r) => r.kind === 'mismatch').length
  const abstained = review.length - mismatches
  const split = evaluation?.split_label ?? 'whole years held out'
  const base = evaluation?.baseline
  const balanced = evaluation?.convergence.some((c) => c.bal_acc != null) ?? false
  const w = (n: number) => `${counts.labeled ? (n / counts.labeled) * 100 : 0}%`

  return (
    <>
      <div className="lead">
      <section className="kpis" aria-label="Key figures">
        {rollup || !base ? (
          <article className="glass kpi">
            <h2 className="kpi__label">BARC silage acres</h2>
            <div className="kpi__value">{rollup ? acres(rollup.acres) : '—'}</div>
            {rollup && <div className="kpi__sub">{rollup.region ?? 'Maryland'}, {year}{rollup.reference_name ? ' (Nov 30)' : ''}; 95% range {acres(rollup.ci[0])}–{acres(rollup.ci[1])}</div>}
            {rollup && <div className="kpi__foot">{rollup.reference_name ?? `Census ${rollup.year}`}: {acres(rollup.census_acres)}</div>}
          </article>
        ) : (
          <article className="glass kpi">
            <h2 className="kpi__label">Balanced accuracy</h2>
            <div className="kpi__value">{num(evaluation?.balanced_accuracy)}</div>
            <div className="kpi__sub">{base.name ?? 'Baseline'}: {num(base.balanced_accuracy)}</div>
            <div className="kpi__foot">{evaluation?.n_evaluated} field-years, {split}</div>
          </article>
        )}
        <article className="glass kpi">
          <h2 className="kpi__label">{seasonEnd ? `Fields scored, ${year}` : `Decided by ${shortDate(asOf)}`}</h2>
          <div className="kpi__value">
            {decided} <span className="kpi__of">of {counts.labeled}</span>
          </div>
          <div className="kpi__sub">labeled {year} fields</div>
          <div className="kpi__bar" aria-hidden="true">
            <span style={{ width: w(counts.Silage), background: DATA.silage }} />
            <span style={{ width: w(counts.Grain), background: DATA.grain }} />
            <span style={{ width: w(counts.Insufficient), background: '#c9d3cf' }} />
          </div>
          <div className="kpi__foot">
            {counts.Silage} silage, {counts.Grain} grain{seasonEnd ? `; ${counts.total - counts.labeled} of ${counts.total} fields not labeled` : `, ${counts.Insufficient} abstained`}
          </div>
        </article>
        <article className="glass kpi">
          <h2 className="kpi__label">Silage recall</h2>
          <div className="kpi__value">{S ? num(S.recall.value) : '—'}</div>
          {S && <div className="kpi__sub">Full season, 2021–2023 pooled; 95% range {num(S.recall.lo)}–{num(S.recall.hi)}</div>}
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
          <div className="kpi__foot">{seasonEnd ? 'Open one to see its season' : `${abstained} too cloudy to call`}</div>
        </article>
      </section>
      </div>

      <aside className="glass rail" aria-label="Season and accuracy">
        {evaluation?.convergence_error && <p className="inline-error" role="alert">Season chart unavailable: {evaluation.convergence_error}</p>}
        {evaluation && evaluation.convergence.length < 2 && base ? (
          <section>
            <h2 className="rail__title">Model vs always guessing grain</h2>
            <p className="rail__note">Balanced accuracy by year. 0.50 is a coin flip between the classes.</p>
            <BaselineBars data={evaluation} />
          </section>
        ) : (
          <section>
            <h2 className="rail__title">How the call firms up through the season</h2>
            <p className="rail__note">{balanced ? 'Share of fields called, and balanced accuracy of those calls, pooled over 2021–2023.' : 'Share of fields decided, and accuracy on those decided.'}</p>
            {evaluation ? <Convergence data={evaluation} asOf={asOf} /> : <div className="skeleton skeleton--chart" />}
            <div className="linekey">
              <span><i style={{ background: chart.share }} />Fields decided</span>
              <span><i style={{ background: chart.accuracy }} />{balanced ? 'Balanced accuracy' : 'Accuracy on decided'}</span>
            </div>
          </section>
        )}

        <section>
          <div className="rail__head">
            <h2 className="rail__title">Held-out accuracy, 2021–2023 pooled</h2>
            <button className="link" onClick={onOpenQuality}>
              Model quality
            </button>
          </div>
        {evaluation && <><p className="rail__note">Full-season results (November 30); independent of the selected date.</p><MiniConfusion data={evaluation} /></>}
        </section>

        <section>
          <h2 className="rail__title">Unlabeled corn fields, {year}</h2>
          {!unlabeledAtSeasonEnd ? (
            <p className="unl"><span className="unl__tag">Model call, no label</span> Season-end calls on unlabeled corn fields are shown on Nov 30.</p>
          ) : unlabeled ? <UnlabeledNote data={unlabeled} /> : unlabeledError ? (
            <Pending title="Calls on unlabeled fields">{unlabeledError.message}</Pending>
          ) : <p className="rail__note">Loading…</p>}
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
    <div className="conv">
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={rows} margin={{ top: 12, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={t.grid} vertical={false} />
        <XAxis dataKey="label" stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} tickLine={false} padding={{ left: 12, right: 12 }} height={34} label={xTitle('As-of date', t.muted)} />
        <YAxis domain={[0, 1]} ticks={[0, 0.5, 1]} tickFormatter={(v: number) => `${v * 100}%`} stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} width={58} label={yTitle('Percent', t.muted)} />
        {current && <ReferenceLine x={current.label} stroke={t.share} strokeOpacity={0.35} strokeWidth={28} />}
        <Tooltip content={(p) => <ChartTip {...(p as unknown as TipProps)} title={(l) => `As of ${l}`} value={(v) => pct(v)} />} />
        <Line dataKey="share_decided" name="Fields decided" stroke={t.share} strokeWidth={2.5} dot={{ r: 3.5, strokeWidth: 0, fill: t.share }} isAnimationActive={false} />
        <Line dataKey={rows.some((r) => r.bal_acc != null) ? 'bal_acc' : 'acc_decided'} name={rows.some((r) => r.bal_acc != null) ? 'Balanced accuracy' : 'Accuracy on decided'} stroke={t.accuracy} strokeWidth={2.5} dot={{ r: 3.5, strokeWidth: 0, fill: t.accuracy }} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
    </div>
  )
}

function MiniConfusion({ data }: { data: EvaluateResponse }) {
  const total = data.confusion.flat().reduce((a, b) => a + b, 0)
  const correct = data.labels.reduce((a, _, i) => a + (data.confusion[i]?.[i] ?? 0), 0)
  return (
    <>
      <p className="rail__note">
        {correct} of {total} labeled field-years correct, {data.split_label ?? 'whole years held out'}.
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

/** Balanced accuracy per year (and pooled) for the model and the always-grain baseline. */
function BaselineBars({ data }: { data: EvaluateResponse }) {
  const rows = [
    ...Object.entries(data.by_year ?? {}).map(([y, v]) => ({ key: y, label: y, model: v.model.balanced_accuracy, base: v.baseline.balanced_accuracy, n: v.model.n })),
    { key: 'all', label: 'All', model: data.balanced_accuracy ?? 0, base: data.baseline?.balanced_accuracy ?? 0, n: data.n_evaluated ?? 0 },
  ]
  return (
    <div className="bb" role="table" aria-label="Balanced accuracy by year, model and always-grain baseline">
      {rows.map((r) => (
        <div className={`bb__row${r.key === 'all' ? ' bb__row--all' : ''}`} role="row" key={r.key}>
          <span className="bb__year" role="rowheader">
            {r.label}
            <small>{r.n} field-years</small>
          </span>
          <span className="bb__bars" role="cell">
            <span className="bb__track"><span className="bb__fill bb__fill--model" style={{ width: `${r.model * 100}%` }} /></span>
            <span className="bb__track"><span className="bb__fill bb__fill--base" style={{ width: `${r.base * 100}%` }} /></span>
          </span>
          <span className="bb__vals" role="cell">
            <b>{num(r.model)}</b>
            <span>{num(r.base)}</span>
          </span>
        </div>
      ))}
      <div className="linekey">
        <span><i className="bb__key--model" />Model</span>
        <span><i className="bb__key--base" />Always grain</span>
      </div>
    </div>
  )
}

/** Season-end model calls on fields with no BARC label. Kept apart from the scored, labeled results. */
function UnlabeledNote({ data }: { data: UnlabeledYearView }) {
  return (
    <>
      <p className="unl" title={data.caveat}>
        <span className="unl__tag">Model call, no label</span>
        {' '}{data.corn_field_years} unlabeled corn field-year{data.corn_field_years === 1 ? '' : 's'}, {acres(data.acres)} ac.
        {' '}Called {data.silage} silage ({acres(data.silage_acres)} ac), {data.grain} grain.
        {data.called > 0 && <> Expected silage {acres(data.expected_silage_acres)} ac (95% range {acres(data.ci[0])}–{acres(data.ci[1])}).</>}
        {data.no_usable_dates > 0 && <> {data.no_usable_dates} without clear satellite dates, not called.</>}
      </p>
      <p className="rail__note">
        No reference label exists to check these. Corn status comes from the Cropland Data Layer; the range covers only the model's own uncertainty.
      </p>
    </>
  )
}
