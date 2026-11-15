/**
 * Score the submitted 2025 forecast against a NASS Quick Stats export, entirely in the browser.
 *
 * A TypeScript port of the matching rules in backend/app/benchmark.py (read_rows and compare),
 * so a judge's file gives the same per-row errors as `python -m harvest.benchmark`:
 *
 *   Year       four digits
 *   Geo Level  NATIONAL (State = US TOTAL) or STATE
 *   State      state name, matched exactly after trimming and upper-casing
 *   Data Item  exactly "CORN, GRAIN - ACRES HARVESTED" or "CORN, SILAGE - ACRES HARVESTED"
 *   Domain     TOTAL
 *   Period     YEAR, when the column is present
 *   Value      acres; (D), (S), (NA), NA or blank mean unknown, never zero
 *
 * Rows that state another item, unit, scope or geography are set aside with a reason. NATIONAL,
 * STATE and the "OTHER STATES" aggregate are matched only to their own kind and never added up.
 * The upload view also sets aside rows for years other than the forecast year.
 *
 * Pure logic: no React, DOM or network.
 */
import type { Forecast } from './components/forecastTypes'

export type GeoKind = 'NATIONAL' | 'STATE' | 'OTHER STATES'
export type CropUse = 'Grain' | 'Silage'
export type Status =
  | 'scored'
  | 'missing_prediction'
  | 'unmatched_prediction'
  | 'reference_unknown'
  | 'prediction_unknown'
  | 'duplicate'

export const STATUSES: Status[] = ['scored', 'missing_prediction', 'unmatched_prediction', 'reference_unknown', 'prediction_unknown', 'duplicate']
export const FORECAST_YEAR = 2025
const NATIONAL_NAME = 'US TOTAL'

/** The file cannot be read as a Quick Stats table at all. */
export class ScoreError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ScoreError'
  }
}

export interface Row {
  line: number
  year: number
  geoKind: GeoKind
  geography: string
  cropUse: CropUse
  value: number | null
  unknownCode: string | null
}

export interface Rejected {
  line: number
  reasons: string[]
  year: string
  geoLevel: string
  state: string
  dataItem: string
  value: string
}

export interface Table {
  rowsRead: number
  rows: Row[]
  rejected: Rejected[]
}

export interface Comparison {
  year: number
  geoKind: GeoKind
  geography: string
  cropUse: CropUse
  status: Status
  referenceValue: number | null
  predictionValue: number | null
  /** prediction - reference, acres */
  signedError: number | null
  absoluteError: number | null
  /** (prediction - reference) / reference; null when the reference is 0 */
  relativeError: number | null
  referenceUnknownCode: string | null
  predictionUnknownCode: string | null
  referenceLines: number[]
  predictionLines: number[]
}

export interface Summary {
  geoKind: GeoKind
  cropUse: CropUse
  referenceKeys: number
  scoredRows: number
  meanSignedError: number | null
  meanAbsoluteError: number | null
  /** unweighted mean of |relative error| over scored rows with a nonzero reference */
  meanAbsoluteRelativeError: number | null
  relativeErrorRows: number
}

export interface Report {
  comparisons: Comparison[]
  statusCounts: Record<Status, number>
  summaries: Summary[]
}

// ---------------------------------------------------------------- CSV

/** RFC 4180 CSV: quoted fields may hold commas, quotes ("") and line breaks. Strips a UTF-8 BOM; skips blank lines. */
export function parseCsv(text: string): string[][] {
  const s = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let started = false // the current field has content or an opening quote
  let quoted = false
  const endField = () => {
    row.push(field)
    field = ''
    started = false
  }
  const endRow = () => {
    endField()
    if (!(row.length === 1 && row[0] === '')) rows.push(row)
    row = []
  }
  for (let i = 0; i < s.length; i++) {
    const c = s[i]
    if (quoted) {
      if (c !== '"') field += c
      else if (s[i + 1] === '"') {
        field += '"'
        i++
      } else quoted = false
    } else if (c === '"' && !started) {
      quoted = true
      started = true
    } else if (c === ',') endField()
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && s[i + 1] === '\n') i++
      endRow()
    } else {
      field += c
      started = true
    }
  }
  if (quoted) throw new ScoreError('The file ends inside a quoted field, so it is not a complete CSV.')
  if (started || row.length > 0) endRow()
  return rows
}

// ---------------------------------------------------------------- one table

type Field = 'year' | 'geo_level' | 'state' | 'item' | 'domain' | 'value' | 'cv' | 'program' | 'period' | 'county' | 'ag_district' | 'zip_code' | 'region' | 'watershed'

/** Normalised field -> accepted headers (lower case). First is the Quick Stats export name; the rest are lab file aliases. */
const ALIASES: Record<Field, string[]> = {
  year: ['year'],
  geo_level: ['geo level', 'aggregation_level', 'agg_level_desc'],
  state: ['state', 'state_name'],
  item: ['data item', 'short_description', 'short_desc'],
  domain: ['domain', 'domain_desc'],
  value: ['value'],
  cv: ['cv (%)', 'cv_percent'],
  program: ['program', 'source', 'source_desc'],
  period: ['period', 'reference_period'],
  county: ['county', 'county_name'],
  ag_district: ['ag district', 'asd_desc'],
  zip_code: ['zip code', 'zip_5'],
  region: ['region', 'region_desc'],
  watershed: ['watershed', 'watershed_desc'],
}
const REQUIRED: Field[] = ['year', 'geo_level', 'state', 'item', 'domain', 'value']
/** A STATE or NATIONAL row must leave these blank (the watershed code is not checked: the export writes 00000000). */
const SUB_STATE: Field[] = ['county', 'ag_district', 'zip_code', 'region', 'watershed']
const ITEM = /^CORN, (GRAIN|SILAGE) - ACRES HARVESTED$/
const UNKNOWN_WORDS = new Set(['NA', 'N/A', 'NAN', 'NULL', 'NONE'])
const NUMBER = /^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/
const NON_FINITE = /^[+-]?(inf|infinity|nan)$/i

/** Required-column names as a judge would see them in the export header. */
export const REQUIRED_HEADERS = ['Year', 'Geo Level', 'State', 'Data Item', 'Domain', 'Value']

function columns(header: string[], label: string): Partial<Record<Field, number>> {
  const found: Partial<Record<Field, number>> = {}
  header.forEach((name, index) => {
    const key = name.trim().toLowerCase()
    for (const field of Object.keys(ALIASES) as Field[]) {
      if (!ALIASES[field].includes(key)) continue
      if (found[field] != null) throw new ScoreError(`${label}: columns "${header[found[field]!]}" and "${name}" both give ${field}.`)
      found[field] = index
    }
  })
  const missing = REQUIRED.filter((f) => found[f] == null).map((f) => REQUIRED_HEADERS[REQUIRED.indexOf(f)])
  if (missing.length) throw new ScoreError(`${label}: missing required column(s): ${missing.join(', ')}.`)
  return found
}

/** Exactly one of value, unknown code or problem describes the cell. */
export function parseValue(raw: string): { value: number | null; unknown: string | null; problem: string | null } {
  const text = raw.trim()
  if (!text) return { value: null, unknown: 'blank', problem: null }
  if ((text.startsWith('(') && text.endsWith(')')) || UNKNOWN_WORDS.has(text.toUpperCase())) return { value: null, unknown: text, problem: null }
  const bare = text.replace(/,/g, '')
  const number = NUMBER.test(bare) ? Number(bare) : NON_FINITE.test(bare) ? Number.NaN : null
  if (number == null) return { value: null, unknown: null, problem: `Value "${text}" is not a number or a suppression code` }
  if (!Number.isFinite(number) || number < 0) return { value: null, unknown: null, problem: `Value "${text}" is not a finite, non-negative acreage` }
  return { value: number, unknown: null, problem: null }
}

function geography(level: string, state: string): { kind: GeoKind | null; name: string | null; problem: string | null } {
  if (level === 'NATIONAL') {
    if (state !== NATIONAL_NAME) return { kind: null, name: null, problem: `Geo Level NATIONAL with State "${state}" (expected ${NATIONAL_NAME})` }
    return { kind: 'NATIONAL', name: NATIONAL_NAME, problem: null }
  }
  if (level === 'STATE') {
    if (!state || state === NATIONAL_NAME) return { kind: null, name: null, problem: `Geo Level STATE with State "${state}"` }
    return { kind: state === 'OTHER STATES' ? 'OTHER STATES' : 'STATE', name: state, problem: null }
  }
  return { kind: null, name: null, problem: `Geo Level "${level}" is not NATIONAL or STATE` }
}

/** Normalise one CSV text: comparable rows, rejected rows (with reasons) and a row count. */
export function readQuickStats(text: string, label = 'file'): Table {
  const records = parseCsv(text)
  if (records.length === 0) throw new ScoreError(`${label}: the file is empty.`)
  const [header, ...body] = records
  const cols = columns(header, label)
  const rows: Row[] = []
  const rejected: Rejected[] = []
  body.forEach((record, i) => {
    const line = i + 2
    const get = (f: Field) => (cols[f] == null ? '' : (record[cols[f]!] ?? '').trim())
    const level = get('geo_level').toUpperCase()
    const state = get('state').toUpperCase()
    const item = get('item').toUpperCase()
    const year = get('year')
    const geo = geography(level, state)
    const val = parseValue(get('value'))
    const match = ITEM.exec(item)
    const reasons: string[] = []
    if (!/^\d{4}$/.test(year)) reasons.push(`Year "${year}" is not four digits`)
    if (geo.problem) reasons.push(geo.problem)
    if (!match) reasons.push(`Data Item "${item}" is not CORN, GRAIN|SILAGE - ACRES HARVESTED`)
    if (get('domain').toUpperCase() !== 'TOTAL') reasons.push(`Domain "${get('domain')}" is not TOTAL`)
    if (cols.period != null && get('period').toUpperCase() !== 'YEAR') reasons.push(`Period "${get('period')}" is not YEAR`)
    for (const f of SUB_STATE) if (get(f)) reasons.push(`${header[cols[f]!]} "${get(f)}" is set on a ${level} row`)
    if (val.problem) reasons.push(val.problem)
    if (reasons.length) {
      rejected.push({ line, reasons, year, geoLevel: level, state, dataItem: item, value: get('value') })
      return
    }
    const use = match![1]
    rows.push({
      line,
      year: Number(year),
      geoKind: geo.kind!,
      geography: geo.name!,
      cropUse: (use[0] + use.slice(1).toLowerCase()) as CropUse,
      value: val.value,
      unknownCode: val.unknown,
    })
  })
  return { rowsRead: body.length, rows, rejected }
}

// ---------------------------------------------------------------- compare

const KIND_ORDER: Record<GeoKind, number> = { NATIONAL: 0, STATE: 1, 'OTHER STATES': 2 }
const keyOf = (r: Pick<Row, 'year' | 'geoKind' | 'geography' | 'cropUse'>) => JSON.stringify([r.year, r.geoKind, r.geography, r.cropUse])
const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null)

/** Match two normalised tables key by key: (year, geography kind, geography, crop use). Same statuses as benchmark.py. */
export function compare(reference: Row[], predictions: Row[]): Report {
  const group = (rows: Row[]) => {
    const m = new Map<string, Row[]>()
    for (const r of rows) m.set(keyOf(r), [...(m.get(keyOf(r)) ?? []), r])
    return m
  }
  const ref = group(reference)
  const pred = group(predictions)
  const keys = [...new Set([...ref.keys(), ...pred.keys()])].map((k) => JSON.parse(k) as [number, GeoKind, string, CropUse])
  keys.sort((a, b) => a[0] - b[0] || KIND_ORDER[a[1]] - KIND_ORDER[b[1]] || (a[2] < b[2] ? -1 : a[2] > b[2] ? 1 : 0) || (a[3] < b[3] ? -1 : a[3] > b[3] ? 1 : 0))
  const comparisons = keys.map(([year, geoKind, geographyName, cropUse]): Comparison => {
    const k = keyOf({ year, geoKind, geography: geographyName, cropUse })
    const r = ref.get(k) ?? []
    const p = pred.get(k) ?? []
    const c: Comparison = {
      year, geoKind, geography: geographyName, cropUse,
      status: 'scored', referenceValue: null, predictionValue: null,
      signedError: null, absoluteError: null, relativeError: null,
      referenceUnknownCode: null, predictionUnknownCode: null,
      referenceLines: r.map((x) => x.line), predictionLines: p.map((x) => x.line),
    }
    // Ambiguous: never pick the first row, average, or add duplicates up.
    if (r.length > 1 || p.length > 1) return { ...c, status: 'duplicate' }
    if (r.length) Object.assign(c, { referenceValue: r[0].value, referenceUnknownCode: r[0].unknownCode })
    if (p.length) Object.assign(c, { predictionValue: p[0].value, predictionUnknownCode: p[0].unknownCode })
    if (!p.length) c.status = 'missing_prediction'
    else if (!r.length) c.status = 'unmatched_prediction'
    else if (c.referenceValue == null) c.status = 'reference_unknown'
    else if (c.predictionValue == null) c.status = 'prediction_unknown'
    else {
      const error = c.predictionValue - c.referenceValue
      Object.assign(c, { signedError: error, absoluteError: Math.abs(error), relativeError: c.referenceValue ? error / c.referenceValue : null })
    }
    return c
  })

  const summaries: Summary[] = []
  for (const geoKind of ['NATIONAL', 'STATE', 'OTHER STATES'] as GeoKind[]) {
    for (const cropUse of ['Grain', 'Silage'] as CropUse[]) {
      const g = comparisons.filter((c) => c.geoKind === geoKind && c.cropUse === cropUse)
      if (!g.length) continue
      const scored = g.filter((c) => c.status === 'scored')
      const relative = scored.filter((c) => c.relativeError != null).map((c) => Math.abs(c.relativeError!))
      summaries.push({
        geoKind, cropUse,
        referenceKeys: g.filter((c) => c.referenceLines.length).length,
        scoredRows: scored.length,
        meanSignedError: mean(scored.map((c) => c.signedError!)),
        meanAbsoluteError: mean(scored.map((c) => c.absoluteError!)),
        meanAbsoluteRelativeError: mean(relative),
        relativeErrorRows: relative.length,
      })
    }
  }
  const statusCounts = Object.fromEntries(STATUSES.map((s) => [s, comparisons.filter((c) => c.status === s).length])) as Record<Status, number>
  return { comparisons, statusCounts, summaries }
}

// ---------------------------------------------------------------- our side

/** Our submitted 2025 rows, from the forecast the tab already shows (estimates only; never its baked-in NASS values). */
export function predictionsFromForecast(data: Forecast, year = FORECAST_YEAR): Row[] {
  const rows: Row[] = []
  const add = (geoKind: GeoKind, geographyName: string, cropUse: CropUse, est: number | null | undefined) =>
    rows.push({
      line: rows.length + 1, year, geoKind, geography: geographyName, cropUse,
      value: est != null && Number.isFinite(est) ? est : null,
      unknownCode: est != null && Number.isFinite(est) ? null : 'blank',
    })
  add('NATIONAL', NATIONAL_NAME, 'Grain', data.us.grain?.est)
  add('NATIONAL', NATIONAL_NAME, 'Silage', data.us.silage?.est)
  for (const s of data.states) {
    const name = s.state.trim().toUpperCase()
    const kind: GeoKind = name === 'OTHER STATES' ? 'OTHER STATES' : 'STATE'
    if (s.grain) add(kind, name, 'Grain', s.grain.est)
    if (s.silage) add(kind, name, 'Silage', s.silage.est)
  }
  return rows
}

// ---------------------------------------------------------------- the upload view

export interface CropTally {
  /** STATE rows scored with a nonzero NASS value */
  states: number
  within10: number
  /** unweighted mean |relative error| over those rows */
  meanAbsPctError: number | null
}

export interface UploadScore {
  rowsRead: number
  /** comparable rows for the forecast year in the uploaded file */
  referenceRows: number
  /** rows set aside: other items, units, geographies or years */
  ignored: Rejected[]
  report: Report
  us: Record<CropUse, Comparison | null>
  maryland: Record<CropUse, Comparison | null>
  tally: Record<CropUse, CropTally>
  /** every scored STATE row */
  states: Comparison[]
}

/** Read an uploaded Quick Stats export and score the forecast against it. Throws ScoreError when it is not a Quick Stats table. */
export function scoreUpload(text: string, data: Forecast, year = FORECAST_YEAR): UploadScore {
  const table = readQuickStats(text, 'This file')
  const otherYears = table.rows.filter((r) => r.year !== year)
  const ignored = [
    ...table.rejected,
    ...otherYears.map((r): Rejected => ({
      line: r.line, reasons: [`Year ${r.year} is not the forecast year ${year}`], year: String(r.year),
      geoLevel: r.geoKind === 'NATIONAL' ? 'NATIONAL' : 'STATE', state: r.geography,
      dataItem: `CORN, ${r.cropUse.toUpperCase()} - ACRES HARVESTED`, value: r.value == null ? r.unknownCode ?? '' : String(r.value),
    })),
  ].sort((a, b) => a.line - b.line)
  const reference = table.rows.filter((r) => r.year === year)
  const report = compare(reference, predictionsFromForecast(data, year))
  const find = (geoKind: GeoKind, name: string, cropUse: CropUse) =>
    report.comparisons.find((c) => c.geoKind === geoKind && c.geography === name && c.cropUse === cropUse && c.referenceLines.length > 0) ?? null
  const states = report.comparisons.filter((c) => c.geoKind === 'STATE' && c.status === 'scored')
  const tally = (cropUse: CropUse): CropTally => {
    const rel = states.filter((c) => c.cropUse === cropUse && c.relativeError != null).map((c) => Math.abs(c.relativeError!))
    return { states: rel.length, within10: rel.filter((e) => e <= 0.1).length, meanAbsPctError: mean(rel) }
  }
  return {
    rowsRead: table.rowsRead,
    referenceRows: reference.length,
    ignored,
    report,
    us: { Grain: find('NATIONAL', NATIONAL_NAME, 'Grain'), Silage: find('NATIONAL', NATIONAL_NAME, 'Silage') },
    maryland: { Grain: find('STATE', 'MARYLAND', 'Grain'), Silage: find('STATE', 'MARYLAND', 'Silage') },
    tally: { Grain: tally('Grain'), Silage: tally('Silage') },
    states,
  }
}
