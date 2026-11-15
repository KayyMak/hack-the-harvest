import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { createElement } from 'react'
import { renderToString } from 'react-dom/server'
import { createServer } from 'vite'

// Renders the field panel on the server (effects do not run, so the series stays loading) and checks the
// no-call states read in plain words: never "— —", "Pending" or a raw API error.
let server
let FieldPanel
let noCallReason
before(async () => {
  server = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom', logLevel: 'error' })
  ;({ FieldPanel } = await server.ssrLoadModule('/src/components/FieldPanel.tsx'))
  ;({ noCallReason } = await server.ssrLoadModule('/src/format.ts'))
})
after(async () => { await server?.close() })

const field = (label) => ({ type: 'Feature', geometry: null, properties: { OBJECTID: 317, ACRES: 12.3, label } })
const cover = (category, crop, corn) => ({ field_id: 317, year: 2022, crop, crop_share: 0.6, corn_share: corn, category })
const render = (props) =>
  renderToString(createElement(FieldPanel, { year: 2022, asOf: '2022-11-30', stub: false, pred: undefined, ...props }))
    .replace(/<!-- -->/g, '')

test('a non-corn field-year with no label says why there is no call, from the Cropland Data Layer', () => {
  const html = render({ field: field(null), cover: cover('not_corn', 'Other Hay/Non Alfalfa', 0.03) })
  assert.match(html, /No call/)
  assert.match(html, /USDA Cropland Data Layer 2022/)
  assert.match(html, /Other Hay\/Non Alfalfa \(3% corn\): not corn this year, so no silage\/grain call\./)
  assert.match(html, /Not applicable: no model call for a non-corn field-year\./)
  assert.doesNotMatch(html, /—\s*—|Pending|GET \/api|→ 404/)
})

test('a mixed field-year is too mixed to call, and a corn one without a call says so', () => {
  assert.match(render({ field: field(null), cover: cover('mixed', 'Corn', 0.26) }), /Partly corn \(26%\): too mixed to call reliably\./)
  const corn = render({ field: field(null), cover: cover('likely_corn', 'Corn', 0.81), asOf: '2022-10-12' })
  assert.match(corn, /Calls on unlabeled corn fields are made at season end \(Nov 30\)\./)
  assert.match(corn, /Shown on Nov 30/)
  assert.doesNotMatch(corn, /Pending/)
})

test('a labeled field keeps its BARC label and model call apart from the land cover', () => {
  const pred = { OBJECTID: 317, class: 'Silage', p_silage: 0.81, abstain: false, top_features: undefined }
  const html = render({ field: field('Grain'), pred, cover: cover('likely_corn', 'Corn', 0.9) })
  assert.match(html, /BARC label/)
  assert.match(html, /Corn, 90% of field \(CDL 2022\)/)
  assert.doesNotMatch(html, /No call/)
  assert.match(html, /No signal breakdown is saved for this call\./)
})

test('no-call reasons are null without land cover, never invented', () => {
  assert.equal(noCallReason(undefined, true), null)
})
