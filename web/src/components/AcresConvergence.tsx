import { useEffect, useMemo, useState } from 'react'
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { ConvergenceAcres } from '../api'
import { acres, shortDate } from '../format'
import { DATA, useTheme } from '../theme'

interface Props {
  data: ConvergenceAcres | null
  error: Error | null
  year: number
  onYear?: (year: number) => void
}

/** Silage-acre estimate at each saved as-of date, with a 95% interval and the BARC reference. */
export function AcresConvergence({ data, error, year, onYear }: Props) {
  const t = useTheme().chart
  const years = useMemo(() => data?.years.map((y) => y.year) ?? [], [data])
  const [picked, setPicked] = useState(year)
  useEffect(() => setPicked(year), [year])
  if (error) return <p className="inline-error">Acre estimates by date unavailable: {error.message}</p>
  if (!data) return <div className="skeleton skeleton--chart" />
  const current = data.years.find((y) => y.year === picked) ?? data.years[0]
  if (!current) return <p className="muted small">No saved acre estimates yet.</p>
  const rows = current.points.map((p) => ({
    label: shortDate(p.as_of),
    est: p.expected_silage_acres,
    lo: p.expected_silage_acres_95ci[0],
    hi: p.expected_silage_acres_95ci[1],
    band: p.expected_silage_acres_95ci[1] - p.expected_silage_acres_95ci[0],
    cv: p.cv_percent,
  }))
  const reference = current.points[0]?.reference_silage_acres ?? 0
  const top = Math.max(reference, ...rows.map((r) => r.hi)) * 1.1
  const first = rows[0]
  const last = rows[rows.length - 1]
  return (
    <div className="acres-conv">
      <div className="acres-conv__tools">
        <div className="seg" role="group" aria-label="Year">
          {years.map((y) => (
            <button key={y} className={`seg__btn${y === current.year ? ' is-on' : ''}`} aria-pressed={y === current.year}
              onClick={() => { setPicked(y); onYear?.(y) }}>{y}</button>
          ))}
        </div>
        <div className="acres-conv__key">
          <span><i style={{ background: DATA.silage }} />Estimate</span>
          <span><i className="is-dotted" style={{ borderColor: DATA.silage }} />95% interval</span>
          <span><i className="is-dashed" style={{ borderColor: t.ink }} />BARC reference</span>
        </div>
      </div>
      <div className="acres-conv__plot" role="img"
        aria-label={`Silage acres ${current.year}: ${acres(first.est)} acres on ${first.label}, ${acres(last.est)} on ${last.label}; BARC reference ${acres(reference)}`}>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={rows} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={t.grid} vertical={false} />
            <XAxis dataKey="label" stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} />
            <YAxis stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} width={44} domain={[0, Math.ceil(top / 10) * 10]} />
            <Tooltip formatter={(v, name) => [typeof v === 'number' ? `${acres(v)} ac` : '—', name]}
              contentStyle={{ background: t.surface, border: `1px solid ${t.grid}`, color: t.ink }} />
            <Area type="monotone" dataKey="lo" stackId="b" stroke="none" fill="transparent" isAnimationActive={false} legendType="none" name="lower" />
            <Area type="monotone" dataKey="band" stackId="b" stroke="none" fill={DATA.silage} fillOpacity={0.14} isAnimationActive={false} legendType="none" name="band" tooltipType="none" />
            <Line type="monotone" dataKey="hi" name="Upper 95%" stroke={DATA.silage} strokeDasharray="2 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="lo" name="Lower 95%" stroke={DATA.silage} strokeDasharray="2 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="est" name="Estimate" stroke={DATA.silage} strokeWidth={2.5} dot={{ r: 3, fill: DATA.silage }} isAnimationActive={false} />
            <ReferenceLine y={reference} stroke={t.ink} strokeDasharray="6 4" strokeOpacity={0.7}
              label={{ value: `BARC labels ${acres(reference)} ac`, position: 'insideTopRight', fill: t.muted, fontSize: 12 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small">
        {data.scope}. The interval comes from the model's own probabilities and does not include error in those probabilities, so it is narrower than the true uncertainty. 
        Each date refits the model using only months of satellite data complete by then.
      </p>
    </div>
  )
}
