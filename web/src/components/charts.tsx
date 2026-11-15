/** Shared chart pieces: one tooltip style for every Recharts chart. */
import type { ReactNode } from 'react'

export interface TipItem {
  name?: string | number
  value?: number | string | ReadonlyArray<number | string>
  color?: string
  stroke?: string
  fill?: string
}
export interface TipProps {
  active?: boolean
  payload?: ReadonlyArray<TipItem>
  label?: string | number
}

export function ChartTip({
  active,
  payload,
  label,
  title,
  value,
}: TipProps & { title?: (label: string | number | undefined) => ReactNode; value?: (v: number) => string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tip">
      {title && <div className="chart-tip__title">{title(label)}</div>}
      {payload.map((p, i) => {
        const v = typeof p.value === 'number' ? (value ? value(p.value) : String(p.value)) : String(p.value ?? '—')
        return (
          <div className="chart-tip__row" key={i}>
            <span className="chart-tip__dot" style={{ background: p.stroke ?? p.color ?? p.fill }} />
            <span className="chart-tip__name">{p.name}</span>
            <span className="chart-tip__value">{v}</span>
          </div>
        )
      })}
    </div>
  )
}
