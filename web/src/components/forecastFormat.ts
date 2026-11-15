/** Number formats and the error color scale for the 2025 estimate view. */

/** 6,886,596 -> "6.89M"; 37,595 -> "37.6k"; 900 -> "900" */
export function fmtAcres(x: number | null | undefined): string {
  if (x == null || !Number.isFinite(x)) return '—'
  if (x === 0) return '<1k'
  const a = Math.abs(x)
  if (a >= 1e6) return `${(x / 1e6).toFixed(2)}M`
  if (a >= 1e4) return `${(x / 1e3).toFixed(1)}k`
  if (a >= 1e3) return `${(x / 1e3).toFixed(2)}k`
  return `${Math.round(x)}`
}

export const fmtFull = (x: number | null | undefined) => (x == null ? '—' : Math.round(x).toLocaleString('en-US'))

/** signed percent, e.g. "+11.3%" */
export function fmtPct(x: number | null | undefined, digits = 1): string {
  if (x == null || !Number.isFinite(x)) return '—'
  const v = x * 100
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(digits)}%`
}

/** Diverging: blue = below NASS, orange = above NASS; stronger color = bigger miss. Steps at 5 / 15 / 30%. */
export const ERROR_STEPS = [
  { max: 0.05, under: '#cfe3ee', over: '#f3dcc0', label: 'within 5%' },
  { max: 0.15, under: '#8fc1e3', over: '#f2b36b', label: '5–15%' },
  { max: 0.3, under: '#4a8fc7', over: '#e07b39', label: '15–30%' },
  { max: Infinity, under: '#1f5c99', over: '#b84a1a', label: 'over 30%' },
]

export function errorColor(err: number): string {
  const step = ERROR_STEPS.find((s) => Math.abs(err) <= s.max) ?? ERROR_STEPS[ERROR_STEPS.length - 1]
  return err < 0 ? step.under : step.over
}

export const titleCase = (s: string) => s.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase())

export const releaseDate = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
}
