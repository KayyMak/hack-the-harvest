import { DATA } from './theme'
import type { FieldLandcover, Label, PredClass } from './types'

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
/** Three significant figures with k / M (billions keep two decimals): 6,886,596 -> "6.89M", 187,176,856 -> "187M",
 *  37,595 -> "37.6k", 16,752,193,000 -> "16.75B"; under 1,000 unchanged. */
export function compact(x: number): string {
  const a = Math.abs(x)
  const [div, unit] = a >= 1e9 ? [1e9, 'B'] : a >= 1e6 ? [1e6, 'M'] : a >= 1e3 ? [1e3, 'k'] : [1, '']
  if (!unit) return acres(x)
  const v = x / div
  const text = v.toFixed(unit === 'B' && Math.abs(v) < 100 ? 2 : Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2)
  if (Math.abs(Number(text)) >= 1000 && unit !== 'B') return compact(Math.sign(x) * 1000 * div) // 999,600 -> "1.00M"
  return `${text}${unit}`
}
/** Rewrites comma-grouped numbers of 10,000 or more inside preformatted text: "187,176,856 bu" -> "187M bu". */
export const compactText = (text: string) =>
  text.replace(/\d{1,3}(?:,\d{3})+(?:\.\d+)?/g, (m) => {
    const n = Number(m.replace(/,/g, ''))
    return n >= 1e4 ? compact(n) : m
  })
/** Signed differences, e.g. "+1,234" acres and "+3.1%"; a true minus sign for negatives. */
export const signedAcres = (x: number) => `${x < 0 ? '−' : '+'}${acres(Math.abs(x))}`
export const signedPct = (x: number, digits = 1) => `${x < 0 ? '−' : '+'}${(Math.abs(x) * 100).toFixed(digits)}%`

/** USDA Cropland Data Layer cover in words: "Soybeans, not corn (CDL 2022)", "Mixed: 35% corn (CDL 2022)". Never a BARC label. */
export function cdlText(c: FieldLandcover): string {
  if (c.category === 'mixed') return `Mixed: ${pct(c.corn_share)} corn (CDL ${c.year})`
  if (c.category === 'likely_corn') return `Corn, ${pct(c.corn_share)} of field (CDL ${c.year})`
  return `${c.crop}, not corn (CDL ${c.year})`
}

/**
 * Why a field-year has no model call, in words, from its USDA Cropland Data Layer cover (null when the cover is
 * unknown). `short` fits a table cell; `text` is the panel sentence. Land cover only: never a label or a call.
 */
export function noCallReason(c: FieldLandcover | undefined, seasonEnd: boolean): { short: string; text: string; na: string } | null {
  if (!c) return null
  const corn = pct(c.corn_share)
  if (c.category === 'not_corn')
    return { short: 'No call (not corn)', text: `${c.crop} (${corn} corn): not corn this year, so no silage/grain call.`, na: 'Not applicable: no model call for a non-corn field-year.' }
  if (c.category === 'mixed')
    return { short: 'No call (mixed)', text: `Partly corn (${corn}): too mixed to call reliably.`, na: 'Not applicable: no model call for a field-year this mixed.' }
  return seasonEnd
    ? { short: 'No call (too few looks)', text: `Corn (${corn} of the field), but too few clear satellite looks to make a call.`, na: 'Not applicable: no model call for this field-year.' }
    : { short: 'No call until Nov 30', text: `Corn (${corn} of the field). Calls on unlabeled corn fields are made at season end (Nov 30).`, na: 'Not applicable until the season-end call (Nov 30).' }
}

/** Table-cell form of the Cropland Data Layer cover: "Corn 96%", "Mixed, 35% corn", "Soybeans". */
export function cdlShort(c: FieldLandcover): string {
  if (c.category === 'likely_corn') return `Corn ${pct(c.corn_share)}`
  if (c.category === 'mixed') return `Mixed, ${pct(c.corn_share)} corn`
  return c.crop
}

export const classColor = (c: PredClass | Label | null | undefined) =>
  c === 'Silage' ? DATA.silage : c === 'Grain' ? DATA.grain : DATA.undecided

const FEATURE_NAMES: Record<string, string> = {
  ndvi_07: 'Jul greenness (NDVI)',
  ndvi_08: 'Aug greenness (NDVI)',
  ndvi_09: 'Sep greenness (NDVI)',
  ndvi_10: 'Oct greenness (NDVI)',
  ndvi_11: 'Nov greenness (NDVI)',
  peak_ndvi: 'Peak greenness',
  peak_doy: 'Peak greenness date',
  late_ndvi: 'Late-season greenness',
  early_minus_late: 'Early minus late greenness',
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
