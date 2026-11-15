import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

let server
let AcresConvergence
before(async () => {
  server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  ;({ AcresConvergence } = await server.ssrLoadModule('/src/components/AcresConvergence.tsx'))
})
after(async () => { await server?.close() })

test('an empty year does not crash the acreage chart', () => {
  const html = renderToStaticMarkup(createElement(AcresConvergence, {
    year: 2022, error: null, data: { scope: 'BARC', method: 'saved', years: [{ year: 2022, points: [] }] },
  }))
  assert.match(html, /No saved acre estimates for 2022/)
})

test('a missing selected year never substitutes a different year', () => {
  const html = renderToStaticMarkup(createElement(AcresConvergence, {
    year: 2022, error: null, data: { scope: 'BARC', method: 'saved', years: [{ year: 2021, points: [] }] },
  }))
  assert.match(html, /No saved acre estimates for 2022/)
})

test('partial acreage coverage remains visible with the chart', () => {
  const point = { as_of: '2022-08-12', mode: 'saved', field_years: 7,
    expected_silage_acres: 10, expected_silage_acres_95ci: [0, 20], cv_percent: 30,
    predicted_silage_acres: 12, reference_silage_acres: 15, total_acres: 100,
    missing_acres_field_years: 1 }
  const html = renderToStaticMarkup(createElement(AcresConvergence, {
    year: 2022, error: null, data: { scope: 'BARC', method: 'saved', years: [{ year: 2022, points: [point] }] },
  }))
  assert.match(html, /omit fields without acreage/)
  assert.match(html, /1 field-years per date/)
})
