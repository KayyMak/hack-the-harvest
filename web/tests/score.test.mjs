import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, before, test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const repo = new URL('../../', import.meta.url)
const judges = readFileSync(new URL('data/reference/quickstats_2025_judges.csv', repo), 'utf8')
const forecast = JSON.parse(readFileSync(new URL('web/public/forecast_2025.json', repo), 'utf8'))
// What `python -m harvest.benchmark --predictions forecast_v2/outputs/state_estimates_2025.csv` reported.
const benchmark = JSON.parse(readFileSync(new URL('forecast_v2/outputs/benchmark.json', repo), 'utf8'))

let server
let score
let ScoreUpload
before(async () => {
  server = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' })
  score = await server.ssrLoadModule('/src/score.ts')
  ;({ ScoreUpload } = await server.ssrLoadModule('/src/components/ScoreUpload.tsx'))
})
after(async () => { await server?.close() })

const pyRow = (geography, crop) => benchmark.comparisons.find((c) => c.geography === geography && c.crop_use === crop)
const pySummary = (kind, crop) => benchmark.summaries.find((s) => s.geo_kind === kind && s.crop_use === crop)

test('the CSV parser keeps quoted commas, escaped quotes and line breaks', () => {
  const rows = score.parseCsv('﻿a,b,c\r\n"90,948,000","say ""hi""","two\nlines"\n\nx,,\n')
  assert.deepEqual(rows, [['a', 'b', 'c'], ['90,948,000', 'say "hi"', 'two\nlines'], ['x', '', '']])
  assert.throws(() => score.parseCsv('a,"b\n'), score.ScoreError)
})

test("the judges' file scores the same rows as harvest.benchmark", () => {
  const s = score.scoreUpload(judges, forecast)
  assert.equal(s.rowsRead, benchmark.reference.rows_read)
  assert.equal(s.ignored.length, benchmark.reference.rows_rejected)
  assert.deepEqual(s.report.statusCounts, benchmark.status_counts)
  assert.equal(s.report.statusCounts.scored, 91)

  const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} vs ${b}`)
  for (const [geo, crop, js] of [
    ['US TOTAL', 'Grain', s.us.Grain], ['US TOTAL', 'Silage', s.us.Silage],
    ['MARYLAND', 'Grain', s.maryland.Grain], ['MARYLAND', 'Silage', s.maryland.Silage],
  ]) {
    const py = pyRow(geo, crop)
    assert.equal(js.status, py.status)
    assert.equal(js.signedError, py.signed_error, `${geo} ${crop}`)
    near(js.relativeError, py.relative_error)
  }
  assert.equal(s.us.Grain.signedError, -901000)
  assert.equal(s.maryland.Silage.signedError, -3352)

  // every comparison, row by row
  assert.equal(s.report.comparisons.length, benchmark.comparisons.length)
  s.report.comparisons.forEach((js, i) => {
    const py = benchmark.comparisons[i]
    assert.deepEqual([js.geoKind, js.geography, js.cropUse, js.status], [py.geo_kind, py.geography, py.crop_use, py.status])
    assert.equal(js.signedError, py.signed_error, `${py.geography} ${py.crop_use}`)
  })
  for (const crop of ['Grain', 'Silage']) {
    const py = pySummary('STATE', crop)
    near(s.tally[crop].meanAbsPctError, py.mean_absolute_relative_error)
    assert.equal(s.tally[crop].states, py.relative_error_rows)
    assert.equal(s.states.filter((c) => c.cropUse === crop).length, py.scored_rows)
  }
  // within 10% matches the dashboard's own 2025 scores (export_dashboard.py: |err| <= 0.10)
  assert.equal(s.tally.Grain.within10, forecast.scores.grain.within_10pct)
  assert.equal(s.tally.Grain.states, forecast.scores.grain.states)
  assert.equal(s.tally.Silage.within10, forecast.scores.silage.within_10pct)
  assert.equal(s.tally.Silage.states, forecast.scores.silage.states)
  // OTHER STATES is its own geography: never a state row
  assert.ok(!s.states.some((c) => c.geography === 'OTHER STATES'))
})

test('our side comes from the forecast estimates, never its stored NASS values', () => {
  const tampered = structuredClone(forecast)
  for (const r of tampered.states) for (const c of [r.grain, r.silage]) if (c) { c.nass = 1; c.err = 99 }
  tampered.us.grain.nass = 1
  const s = score.scoreUpload(judges, tampered)
  assert.equal(s.us.Grain.signedError, -901000)
  assert.equal(s.maryland.Silage.signedError, -3352)
})

test('suppressed values are unknown, other items and years are ignored, lab aliases are read', () => {
  const csv = [
    'year,aggregation_level,state_name,short_description,domain_desc,value',
    '2025,STATE,MARYLAND,"CORN, SILAGE - ACRES HARVESTED",TOTAL,(D)',
    '2025,STATE,MARYLAND,"CORN, GRAIN - ACRES HARVESTED",TOTAL,"400,000"',
    '2025,STATE,MARYLAND,"CORN, GRAIN - YIELD, MEASURED IN BU / ACRE",TOTAL,180',
    '2024,STATE,MARYLAND,"CORN, GRAIN - ACRES HARVESTED",TOTAL,"420,000"',
    '2025,STATE,DELAWARE,"CORN, GRAIN - ACRES HARVESTED",TOTAL,',
  ].join('\n')
  const s = score.scoreUpload(csv, forecast)
  assert.equal(s.rowsRead, 5)
  assert.equal(s.maryland.Silage.status, 'reference_unknown')
  assert.equal(s.maryland.Silage.signedError, null)
  assert.equal(s.maryland.Grain.signedError, 405000 - 400000)
  assert.equal(s.ignored.length, 2)
  assert.match(s.ignored[0].reasons.join(), /YIELD/)
  assert.match(s.ignored[1].reasons.join(), /2024/)
  assert.equal(s.report.comparisons.find((c) => c.geography === 'DELAWARE' && c.cropUse === 'Grain').status, 'reference_unknown')
  assert.equal(s.report.statusCounts.scored, 1)
  assert.equal(s.tally.Silage.states, 0)
})

test('a file that is not a Quick Stats export is a clear error', () => {
  assert.throws(() => score.scoreUpload('field_id,label\n1,Silage\n', forecast), /missing required column\(s\): Year, Geo Level, State, Data Item, Domain, Value/)
  assert.throws(() => score.scoreUpload('', forecast), score.ScoreError)
  assert.throws(() => score.scoreUpload('Year,Value,value,Geo Level,State,Data Item,Domain\n', forecast), /both give value/)
})

test('a duplicated row is never scored', () => {
  const row = '2025,STATE,IOWA,"CORN, GRAIN - ACRES HARVESTED",TOTAL,"13,000,000"'
  const s = score.scoreUpload(['Year,Geo Level,State,Data Item,Domain,Value', row, row].join('\n'), forecast)
  assert.equal(s.report.comparisons.find((c) => c.geography === 'IOWA' && c.cropUse === 'Grain').status, 'duplicate')
  assert.equal(s.report.statusCounts.scored, 0)
})

test('the upload box renders its prompt before any file is read', () => {
  const html = renderToStaticMarkup(createElement(ScoreUpload, { data: forecast }))
  assert.match(html, /Score against your NASS file/)
  assert.match(html, /Nothing is uploaded; it is read in your browser/)
  assert.match(html, /type="file"/)
})
