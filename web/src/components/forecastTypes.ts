/** Shape of web/public/forecast_2025.json, written by forecast/export_dashboard.py. */
export type Crop = 'silage' | 'grain'

export interface Cell {
  est: number
  se: number | null
  low: number | null
  high: number | null
  /** NASS 2025 acres from the judges' reference file; null when NASS publishes no row */
  nass: number | null
  /** (est - nass) / nass */
  err: number | null
  inside: boolean | null
}

export interface StateRow {
  state: string
  silage: Cell | null
  grain: Cell | null
}

export interface ConvergencePoint {
  as_of: string
  source: string
  us_silage: number
  us_silage_se: number
  us_silage_low: number
  us_silage_high: number
  us_grain: number
  us_grain_se: number
}

export interface CropScore {
  states: number
  within_10pct: number
  acre_weighted_abs_pct_error: number
  median_abs_pct_error: number
  inside_95_interval: number
}

export interface BacktestCrop {
  state_years: number
  median_abs_pct_error: number
  mean_abs_pct_error: number
  covered_by_95_interval: number
  us_total: Record<string, { est: number; truth: number; pct_error: number }>
}

/** NASS "Reliability" format from the US backtest: RMSE and the 90% margin (Student t x RMSE). */
export interface Reliability {
  years: string
  n: number
  rmse_pct: number
  t: number
  margin90_pct: number
  max_abs_pct: number
}

export interface Forecast {
  reliability?: { silage: Reliability | null; grain: Reliability | null }
  title: string
  data_cutoff: string
  estimate_note: string
  reference_note: string
  method: string
  silage_method: { chosen: string; description: string; backtest_acre_weighted_abs_pct_error: Record<string, number>; candidates: Record<string, string>; rule: string }
  backtest: { silage: BacktestCrop; grain: BacktestCrop }
  us: { silage: Cell; grain: Cell }
  scores: { silage: CropScore; grain: CropScore }
  convergence: ConvergencePoint[]
  states: StateRow[]
  sources: Record<string, { title: string; released: string | null; url: string }>
}
