import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { adaptAsOfPredictions, adaptConvergence, adaptFields, adaptPredictions, adaptRollup, adaptSummary, adaptUnlabeled, fieldLayerKey, unlabeledCallsAt } from '../src/adapter.ts'
import { api } from '../src/api.ts'

const artifact = (name) => JSON.parse(readFileSync(new URL(`../../baseline/outputs/${name}`, import.meta.url), 'utf8'))
const fields = artifact('fields.geojson')
const metrics = artifact('metrics.json')
const asof = artifact('asof.json')

test('a missing as-of artifact is explicit while full-season summary remains usable', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url) => {
    if (url === '/api/baseline/summary') return Response.json(metrics)
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
      '/api/baseline/contributions': [
        { field_id: 327, year: 2021, feature: 'ndvi_09', value: 0.25, contribution: 1.8 },
        { field_id: 327, year: 2021, feature: 'late_ndvi', value: 0.27, contribution: -0.9 },
      ],
      '/api/baseline/convergence': { scope: 'Labeled BARC field-years only', method: 'm', years: [{ year: 2022, points: [] }] },
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
  const seasonEnd = (await api.predict(2021, '2021-11-30'))[0]
  assert.equal(seasonEnd.OBJECTID, 327)
  assert.deepEqual(JSON.parse(seasonEnd.top_features).map((c) => [c.name, c.contrib]), [['ndvi_09', 1.8], ['late_ndvi', -0.9]])
  assert.equal((await api.evaluate()).n_evaluated, 44)
  const series = await api.series(327, 2021)
  assert.deepEqual(series.points, [{ date: '2021-08-01', ndvi: 0.8, ndti: null }])
  await assert.rejects(api.agentRun('test'), (error) => error.status === 501)
  assert.deepEqual(calls.at(-1), ['/api/agent/run', 'POST'])
  assert.equal((await api.rollup(2022)).reference_name, 'BARC reference labels')
  await assert.rejects(api.rollup(2019), /No saved roll-up/)
  assert.equal((await api.predict(2022, '2022-10-12')).length, 7)
  assert.equal((await api.evaluate('strict', 2022)).convergence.length, 5)
  assert.equal((await api.convergenceAcres()).years[0].year, 2022)
  const meta = await api.meta()
  assert.equal(meta.season_end_only, false)
  assert.equal(meta.as_of_dates.length, 15)
})

const unlabeledFixture = {
  caveat: 'These are model calls on BARC field-years that have no silage/grain label.',
  by_year: [{ year: 2022, field_years_called: 2, total_acres: 30, called_silage: 1, called_grain: 1,
    called_silage_acres: 10, no_usable_dates: 1, expected_silage_acres: 12.5, expected_silage_acres_95ci: [2.1, 22.9] }],
  calls: [
    { field_id: 7, year: 2022, acres: 10, corn_share: 0.9, status: 'called', predicted_label: 'Silage', silage_probability: 0.8 },
    { field_id: 8, year: 2022, acres: 20, corn_share: 0.7, status: 'called', predicted_label: 'Grain', silage_probability: 0.2 },
    { field_id: 9, year: 2022, acres: 5, corn_share: 0.6, status: 'no_usable_dates', predicted_label: null, silage_probability: null },
    { field_id: 7, year: 2021, acres: 10, corn_share: 0.9, status: 'called', predicted_label: 'Grain', silage_probability: 0.1 },
  ],
}

test('unlabeled calls stay separate: one year, called only, uncalled field-years counted not filled', () => {
  const view = adaptUnlabeled(unlabeledFixture, 2022)
  assert.deepEqual(view.calls.map((c) => [c.OBJECTID, c.label]), [[7, 'Silage'], [8, 'Grain']])
  assert.equal(view.corn_field_years, 3)
  assert.equal(view.no_usable_dates, 1)
  assert.deepEqual(view.ci, [2.1, 22.9])
  assert.ok(view.calls.every((c) => !('reference_label' in c)), 'a model call is never presented as a label')
  assert.throws(() => adaptUnlabeled(unlabeledFixture, 2019), /No saved unlabeled calls/)
})

test('unlabeled calls come from /api/unlabeled; a missing artifact is an error, never zeros', async (t) => {
  let status = 200
  t.mock.method(globalThis, 'fetch', async (url) => {
    assert.equal(url, '/api/unlabeled')
    return status === 200 ? Response.json(unlabeledFixture) : new Response('{}', { status })
  })
  assert.equal((await api.unlabeled(2022)).silage, 1)
  status = 503
  await assert.rejects(api.unlabeled(2022), (error) => error.status === 503)
})

test('unlabeled calls are season-end only: shown on Nov 30, hidden on every mid-season date', () => {
  const view = adaptUnlabeled(unlabeledFixture, 2022)
  assert.equal(unlabeledCallsAt(view, 2022, '2022-11-30').length, 2)
  for (const asOf of ['2022-08-12', '2022-09-12', '2022-10-12', '2022-11-12']) assert.deepEqual(unlabeledCallsAt(view, 2022, asOf), [])
  assert.deepEqual(unlabeledCallsAt(view, 2023, '2023-11-30'), [], 'another year\'s calls are never shown')
  assert.deepEqual(unlabeledCallsAt(null, 2022, '2022-11-30'), [])
})
