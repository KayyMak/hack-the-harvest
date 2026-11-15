import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { adaptAsOfPredictions, adaptBarcRollup, adaptConvergence, adaptEstimate2025, adaptFields, adaptPredictions, adaptRollup, adaptSummary, byYearFromPredictions, fieldLayerKey } from '../src/adapter.ts'
import { api } from '../src/api.ts'

const artifact = (name) => JSON.parse(readFileSync(new URL(`../../baseline/outputs/${name}`, import.meta.url), 'utf8'))
const fields = artifact('fields.geojson')
const metrics = artifact('metrics.json')
const asof = artifact('asof.json')

test('a missing as-of artifact is explicit while full-season summary remains usable', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url) => {
    if (url === '/api/baseline/summary') return Response.json(metrics)
    if (url === '/api/baseline/predictions') return Response.json([])
    assert.equal(url, '/api/baseline/asof')
    return new Response('{}', { status: 503 })
  })
  const result = await api.evaluate('strict', 2022)
  assert.equal(result.n_evaluated, 44)
  assert.deepEqual(result.convergence, [])
  assert.match(result.convergence_error, /503/)
})

test('real API polygons select reference labels by year, preserving unknown labels', () => {
  const a = adaptFields(fields, 2022)
  const b = adaptFields(fields, 2023)
  assert.equal(a.features.length, 83)
  assert.equal(a.features.find((f) => f.properties.OBJECTID === 231).properties.label, 'Silage')
  assert.equal(b.features.find((f) => f.properties.OBJECTID === 231).properties.label, 'Grain')
  assert.equal(a.features.find((f) => f.properties.OBJECTID === 1).properties.label, null)
  assert.notEqual(fieldLayerKey(a), fieldLayerKey(b), 'Leaflet must remount when reference labels change')
})

test('public summary supplies the same confusion matrix and scores as saved results', () => {
  const result = adaptSummary(metrics)
  assert.deepEqual(result.confusion, metrics.logistic.confusion_matrix)
  assert.equal(result.per_class.Silage.recall.value, metrics.logistic.silage_recall)
  assert.equal(result.per_class.Silage.precision.value, metrics.logistic.silage_precision)
  assert.equal(result.baseline.balanced_accuracy, metrics.always_grain.balanced_accuracy)
  assert.ok(result.per_class.Silage.recall.lo < result.per_class.Silage.recall.value)
  assert.ok(result.per_class.Silage.recall.hi > result.per_class.Silage.recall.value)
})

test('saved predictions do not imply mid-season inference or score other years', () => {
  const rows = [{ field_id: 327, year: 2021, predicted_label: 'Grain', silage_probability: 0.01 }]
  assert.equal(adaptPredictions(rows, 2021, '2021-11-30')[0].OBJECTID, 327)
  assert.deepEqual(adaptPredictions(rows, 2022, '2022-11-30'), [])
  assert.throws(() => adaptPredictions(rows, 2021, '2021-10-12'), /end-of-season/)
})

test('mid-season calls come only from saved as-of results, never from season-end predictions', () => {
  const oct = adaptAsOfPredictions(asof, 2022, '2022-10-12')
  assert.equal(oct.length, 7)  // the seven labeled 2022 field-years
  assert.ok(oct.every((p) => p.year === 2022 && p.as_of === '2022-10-12' && ['Grain', 'Silage'].includes(p.class)))
  assert.throws(() => adaptAsOfPredictions(asof, 2022, '2022-10-01'), /No saved calls/)
  assert.throws(() => adaptAsOfPredictions(asof, 2024, '2024-10-12'), /No saved calls/)
  const season = adaptConvergence(asof, 2022)
  assert.deepEqual(season.map((p) => p.as_of), ['2022-08-12', '2022-09-12', '2022-10-12', '2022-11-12', '2022-11-30'])
  assert.equal(season[0].bal_acc, 0.5)  // July alone is no better than always-Grain
  assert.equal(season.at(-1).bal_acc, metrics.logistic.balanced_accuracy)
  assert.deepEqual(adaptSummary(metrics, season).convergence, season)
})

test('the roll-up is labeled as BARC fields and compared with BARC labels, not the Census', () => {
  const saved = { scope: 's', years: [{ year: 2022, reference_silage_acres: 74.44, expected_silage_acres: 54.1,
    expected_silage_acres_95ci: [40.2, 68.0], cv_percent: 13.1 }] }
  const r = adaptRollup(saved, 2022)
  assert.equal(r.region, 'Labeled BARC fields')
  assert.equal(r.reference_name, 'BARC reference labels')
  assert.equal(r.census_acres, 74.44)
  assert.match(r.note, /not a Maryland statewide estimate/)
  assert.match(r.note, /Full-season estimate as of November 30/)
  const unknown = { ...saved, years: [{ ...saved.years[0], cv_percent: null }] }
  assert.equal(adaptRollup(unknown, 2022).cv_pct, null, 'unknown uncertainty must not become 0%')
  assert.throws(() => adaptRollup(saved, 2021), /No saved roll-up/)
})

test('live client uses existing /api routes and the published response shapes', async (t) => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls.push([url, init?.method ?? 'GET'])
    const fixtures = {
      '/api/fields.geojson': fields,
      '/api/baseline/summary': metrics,
      '/api/baseline/predictions': [{ field_id: 327, year: 2021, predicted_label: 'Grain', silage_probability: 0.01 }],
      '/api/baseline/asof': asof,
      '/api/baseline/rollup': { scope: 's', years: [{ year: 2022, reference_silage_acres: 74.44, expected_silage_acres: 54.1,
        expected_silage_acres_95ci: [40.2, 68.0], cv_percent: 13.1 }] },
      '/api/fields/327/observations?year=2021': [
        { date: '2021-08-01', ndvi: 0.8, status: 'ok' },
        { date: '2021-08-02', ndvi: null, status: 'cloud_or_nodata' },
      ],
    }
    if (url === '/api/agent/run') return new Response('{}', { status: 501 })
    assert.ok(url in fixtures, `Unexpected API route: ${url}`)
    return Response.json(fixtures[url])
  })
  assert.equal((await api.fields(2022)).features.length, 83)
  assert.equal((await api.predict(2021, '2021-11-30'))[0].OBJECTID, 327)
  assert.equal((await api.evaluate()).n_evaluated, 44)
  const series = await api.series(327, 2021)
  assert.deepEqual(series.points, [{ date: '2021-08-01', ndvi: 0.8, ndti: null }])
  await assert.rejects(api.agentRun('test'), (error) => error.status === 501)
  assert.deepEqual(calls.at(-1), ['/api/agent/run', 'POST'])
  assert.equal((await api.rollup(2022)).reference_name, 'BARC reference labels')
  await assert.rejects(api.rollup(2019), /No saved roll-up/)
  assert.equal((await api.predict(2022, '2022-10-12')).length, 7)
  assert.equal((await api.evaluate('strict', 2022)).convergence.length, 5)
  const meta = await api.meta()
  assert.equal(meta.season_end_only, false)
  assert.equal(meta.as_of_dates.length, 15)
})

test('per-year scores computed from saved predictions match the saved by-year metrics', () => {
  const rows = []
  for (const line of readFileSync(new URL('../../baseline/outputs/heldout_predictions.csv', import.meta.url), 'utf8').trim().split(/\r?\n/).slice(1)) {
    const c = line.trim().split(',')
    rows.push({ field_id: +c[0], year: +c[1], reference_label: c[2], predicted_label: c[c.length - 3], silage_probability: +c[c.length - 2], fold: +c[c.length - 4], valid_dates: +c[3] })
  }
  const head = readFileSync(new URL('../../baseline/outputs/heldout_predictions.csv', import.meta.url), 'utf8').split(/\r?\n/)[0].trim().split(',')
  assert.deepEqual(head.slice(-4), ['fold', 'predicted_label', 'silage_probability', 'always_grain_prediction'])
  const byYear = byYearFromPredictions(rows)
  for (const [year, saved] of Object.entries(metrics.by_year)) {
    assert.deepEqual(byYear[year].model.confusion_matrix, saved.logistic.confusion_matrix, year)
    assert.ok(Math.abs(byYear[year].model.balanced_accuracy - saved.logistic.balanced_accuracy) < 1e-9, year)
    assert.ok(Math.abs(byYear[year].model.silage_recall - saved.logistic.silage_recall) < 1e-9, year)
    assert.equal(byYear[year].baseline.balanced_accuracy, saved.always_grain.balanced_accuracy, year)
  }
})

test('BARC roll-up adapter keeps BARC-only scope and picks the requested year', () => {
  const data = { scope: 'Labeled BARC field-years with saved held-out predictions only', method: 'm', years: [
    { year: 2022, field_years: 7, total_acres: 110.35, reference_silage_acres: 74.44, expected_silage_acres: 54.14,
      expected_silage_acres_95ci: [20.72, 87.56], cv_percent: 31.5, adjusted_silage_acres: 55.94 }] }
  const r = adaptBarcRollup(data, 2022)
  assert.equal(r.labeled_silage_acres, 74.44)
  assert.deepEqual(r.ci, [20.72, 87.56])
  assert.match(r.scope, /BARC/)
  assert.equal(adaptBarcRollup(data, 2021), null)
})

test('field acres are rounded to one decimal for display', () => {
  const f = adaptFields(fields, 2022).features.find((x) => x.properties.ACRES != null)
  assert.equal(f.properties.ACRES, Math.round(f.properties.ACRES * 10) / 10)
})

// Synthetic values for shape checks only; these are not results.
const estimateSummary = () => ({
  year: 2025, state: 'MARYLAND', generated_utc: '2000-01-01T00:00:00+00:00', headline: 'calibrated',
  population: { source: 'synthetic', corn_rule: 'synthetic', csb_fields_maryland: 100, corn_fields_2025: 40, corn_acres_2025: 1000 },
  sample: { seed: 1, stratified_by: 'county', requested_fields: 10, sampled_fields: 10, sampled_acres: 250, scored_fields: 8,
    scored_acres: 200, skipped_fields: 2, skipped_reasons: { too_few_clear_dates: 1, read_error: 1 }, min_valid_dates: 3 },
  model: { name: 'synthetic', training_field_years: 4, features: ['ndvi_07'], threshold: 0.5 },
  raw: { silage_acres: 300, silage_acres_95ci: [200, 400], grain_acres: 700, grain_acres_95ci: [600, 800], silage_share: 0.3 },
  calibrated: { silage_acres: 250, silage_acres_95ci: [100, 400], grain_acres: 750, grain_acres_95ci: [600, 900], silage_share: 0.25,
    method: 'synthetic', tpr: 0.5, fpr: 0.1 },
  nass_2025: { silage_acres: 200, grain_acres: 800, source: 'synthetic' },
  benchmark: {
    raw: { silage: { error: 100, relative_error: 0.5 }, grain: { error: -100, relative_error: -0.125 } },
    calibrated: { silage: { error: 50, relative_error: 0.25 }, grain: { error: -50, relative_error: -0.0625 } },
  },
  method: 'synthetic', limitations: ['synthetic'], sources: [{ name: 'synthetic', url: 'https://example.invalid/', accessed: '2000-01-01' }],
})

test('2025 estimate comes from /api/estimate_2025 with the calibrated numbers as the headline', async (t) => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url) => {
    calls.push(url)
    return Response.json({ summary: estimateSummary(), benchmark: { model_name: 'synthetic' } })
  })
  const result = await api.estimate2025()
  assert.deepEqual(calls, ['/api/estimate_2025'])
  assert.equal(result.calibrated, true)
  assert.deepEqual(result.silage, { acres: 250, ci: [100, 400], nass_acres: 200, error: 50, relative_error: 0.25,
    raw: { acres: 300, ci: [200, 400], error: 100, relative_error: 0.5 } })
  assert.deepEqual([result.grain.acres, result.grain.nass_acres, result.grain.error, result.grain.raw.acres], [750, 800, -50, 700])
  assert.deepEqual(result.summary, estimateSummary())
  assert.deepEqual(result.benchmark, { model_name: 'synthetic' })
})

test('without calibration the raw 2025 estimate is the headline and is marked uncalibrated', () => {
  const summary = { ...estimateSummary(), headline: 'raw', calibrated: null }
  summary.benchmark.calibrated = null
  const result = adaptEstimate2025({ summary, benchmark: null })
  assert.equal(result.calibrated, false)
  assert.equal(result.benchmark, null)
  assert.deepEqual([result.silage.acres, result.silage.ci, result.silage.error], [300, [200, 400], 100])
  assert.deepEqual([result.grain.acres, result.grain.relative_error], [700, -0.125])
})

test('a missing or incomplete 2025 estimate rejects instead of showing numbers', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('{"detail":"missing"}', { status: 503 }))
  await assert.rejects(api.estimate2025(), (error) => error.status === 503 && /estimate_2025/.test(error.message))
  assert.throws(() => adaptEstimate2025({}), /incomplete/)
  const noErrors = estimateSummary()
  delete noErrors.benchmark.calibrated
  assert.throws(() => adaptEstimate2025({ summary: noErrors, benchmark: null }), /incomplete/)
  const noRange = estimateSummary()
  delete noRange.raw.grain_acres_95ci
  assert.throws(() => adaptEstimate2025({ summary: noRange, benchmark: null }), /incomplete/)
})
