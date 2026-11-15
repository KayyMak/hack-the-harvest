import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { adaptBarcRollup, adaptFields, adaptPredictions, adaptSummary, byYearFromPredictions, fieldLayerKey } from '../src/adapter.ts'
import { api } from '../src/api.ts'

const artifact = (name) => JSON.parse(readFileSync(new URL(`../../baseline/outputs/${name}`, import.meta.url), 'utf8'))
const fields = artifact('fields.geojson')
const metrics = artifact('metrics.json')

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

test('live client uses existing /api routes and the published response shapes', async (t) => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls.push([url, init?.method ?? 'GET'])
    const fixtures = {
      '/api/fields.geojson': fields,
      '/api/baseline/summary': metrics,
      '/api/baseline/predictions': [{ field_id: 327, year: 2021, predicted_label: 'Grain', silage_probability: 0.01 }],
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
  await assert.rejects(api.rollup(2022), /BARC fields only/)
  assert.equal((await api.meta()).season_end_only, true)
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
