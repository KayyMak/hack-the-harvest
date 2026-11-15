import { DATA } from './theme'
import type { Label, PredClass } from './types'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "2022-10-12" -> "Oct 12" (parsed as UTC so it never shifts a day). */
export const shortDate = (iso: string | null | undefined) => {
  if (!iso) return '—'
  const [, m, d] = iso.slice(0, 10).split('-').map(Number)
  return `${MONTHS.at(m - 1)} ${d}`
}
export const monthOf = (t: number) => MONTHS.at(new Date(t).getUTCMonth()) ?? ''
export const toTime = (iso: string) => Date.parse(`${iso.slice(0, 10)}T00:00:00Z`)

export const pct = (x: number | null | undefined, digits = 0) => (x == null ? '—' : `${(x * 100).toFixed(digits)}%`)
export const num = (x: number | null | undefined, digits = 2) => (x == null ? '—' : x.toFixed(digits))
export const acres = (x: number) => x.toLocaleString('en-US', { maximumFractionDigits: 0 })
/** Signed differences, e.g. "+1,234" acres and "+3.1%"; a true minus sign for negatives. */
export const signedAcres = (x: number) => `${x < 0 ? '−' : '+'}${acres(Math.abs(x))}`
export const signedPct = (x: number, digits = 1) => `${x < 0 ? '−' : '+'}${(Math.abs(x) * 100).toFixed(digits)}%`

export const classColor = (c: PredClass | Label | null | undefined) =>
  c === 'Silage' ? DATA.silage : c === 'Grain' ? DATA.grain : DATA.undecided

const FEATURE_NAMES: Record<string, string> = {
  ndvi_pre_drop: 'Greenness before drop',
  drop_days: 'Days to drop',
  ndti_post: 'Residue after (NDTI)',
  decline_doy_rel: 'Decline vs. local norm',
  dairy_dist_km: 'Distance to dairy',
  decline_doy: 'Decline date',
  drop_doy: 'Largest drop date',
  drop_size: 'Largest drop size',
  regrowth: 'Regrowth after low',
}
export const featureName = (raw: string) => FEATURE_NAMES[raw] ?? raw.replace(/_/g, ' ')
