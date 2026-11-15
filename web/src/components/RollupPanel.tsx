import { api } from '../api'
import type { RollupResponse } from '../api'
import { acres } from '../format'
import { useTheme } from '../theme'

interface Props {
  data: RollupResponse | null
  error: Error | null
}

export function RollupPanel({ data, error }: Props) {
  if (error) return <p className="inline-error">Roll-up unavailable: {error.message}</p>
  if (!data) return <div className="skeleton skeleton--panel" />
  const [lo, hi] = data.ci
  const inside = data.census_acres >= lo && data.census_acres <= hi
  const diff = data.census_acres ? (data.acres - data.census_acres) / data.census_acres : null
  const refName = data.reference_name ?? `Census of Agriculture ${data.year}`
  const refShort = data.reference_name ?? 'Census'
  return (
    <div className="rollup">
      <div className="eyebrow">{data.region} · corn for silage · {data.year}</div>
      {data.reference_name && <p className="muted small">Full-season results as of November 30, {data.year}. The selected mid-season date does not change this estimate.</p>}
      <div className="rollup__hero">
        <div>
          <div className="rollup__label">Our estimate</div>
          <div className="rollup__value">
            {acres(data.acres)} <span className="rollup__unit">acres</span>
          </div>
          <div className="rollup__ci">
            95% CI {acres(lo)} – {acres(hi)} · CV {data.cv_pct == null ? 'Unavailable' : `${data.cv_pct.toFixed(1)}%`}
          </div>
        </div>
        <div>
          <div className="rollup__label">{refName}</div>
          <div className="rollup__value rollup__value--ref">
            {acres(data.census_acres)} <span className="rollup__unit">acres</span>
          </div>
          <div className="rollup__ci">
            {diff == null ? 'No reference acres to compare' : `${diff >= 0 ? '+' : ''}${(diff * 100).toFixed(1)}% vs. ${refShort}`}
          </div>
        </div>
      </div>

      <DotWhisker data={data} />

      <p className={`rollup__verdict ${inside ? 'is-ok' : 'is-off'}`}>
        {inside ? `✓ The ${refShort} value falls inside our 95% interval.` : `✗ The ${refShort} value falls outside our 95% interval.`}
      </p>

      <a className="button" href={api.csvUrl(data.csv_url)} download>
        Download QuickStats CSV
      </a>
      <p className="muted small">{data.note ?? 'County totals are a sanity check on the roll-up, never field-level truth.'}</p>
    </div>
  )
}

/** One axis, two rows: our estimate with its CI whisker, and the Census point. */
function DotWhisker({ data }: { data: RollupResponse }) {
  const t = useTheme().chart
  const [lo, hi] = data.ci
  const minV = Math.min(lo, data.census_acres)
  const maxV = Math.max(hi, data.census_acres)
  const pad = (maxV - minV) * 0.25 || 1000
  const a = minV - pad
  const b = maxV + pad
  const W = 560
  const L = 132
  const R = 24
  const x = (v: number) => L + ((v - a) / (b - a)) * (W - L - R)
  const ticks = niceTicks(a, b, 4)
  return (
    <svg className="dotwhisker" viewBox={`0 0 ${W} 150`} role="img" aria-label={`Our estimate with 95% interval compared with ${data.reference_name ?? 'the Census value'}`}>
      {ticks.map((v) => (
        <g key={v}>
          <line x1={x(v)} x2={x(v)} y1={14} y2={104} stroke={t.grid} />
          <text x={x(v)} y={124} textAnchor="middle" fontSize={13} fill={t.muted}>
            {acres(v)}
          </text>
        </g>
      ))}
      <text x={(L + W - R) / 2} y={146} textAnchor="middle" fontSize={12} fill={t.muted}>Silage acres</text>
      <text x={0} y={44} fontSize={15} fill={t.ink} fontWeight={600}>Our estimate</text>
      <line x1={x(lo)} x2={x(hi)} y1={40} y2={40} stroke={t.ink} strokeWidth={2} />
      <line x1={x(lo)} x2={x(lo)} y1={32} y2={48} stroke={t.ink} strokeWidth={2} />
      <line x1={x(hi)} x2={x(hi)} y1={32} y2={48} stroke={t.ink} strokeWidth={2} />
      <circle cx={x(data.acres)} cy={40} r={7} fill={t.ink} stroke={t.surface} strokeWidth={2} />
      <text x={0} y={84} fontSize={15} fill={t.ink} fontWeight={600}>{data.reference_name ? 'Labels' : `Census ${data.year}`}</text>
      <rect x={x(data.census_acres) - 6} y={74} width={12} height={12} transform={`rotate(45 ${x(data.census_acres)} 80)`} fill={t.surface} stroke={t.ink} strokeWidth={2} />
    </svg>
  )
}

function niceTicks(a: number, b: number, n: number) {
  const step0 = (b - a) / n
  const mag = 10 ** Math.floor(Math.log10(step0))
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= step0) ?? step0
  const out: number[] = []
  for (let v = Math.ceil(a / step) * step; v <= b; v += step) out.push(v)
  return out
}
