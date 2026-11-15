import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { createServer } from 'vite'

let server
let featureName
before(async () => {
  server = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' })
  ;({ featureName } = await server.ssrLoadModule('/src/format.ts'))
})
after(async () => { await server?.close() })

test('model v2 timing features have readable names', () => {
  assert.equal(featureName('decline_doy'), 'Decline date')
  assert.equal(featureName('drop_doy'), 'Largest drop date')
  assert.equal(featureName('drop_size'), 'Largest drop size')
  assert.equal(featureName('regrowth'), 'Regrowth after low')
  assert.equal(featureName('peak_ndvi'), 'peak ndvi')  // unnamed features fall back to spaces
})

test('big numbers are shown to three significant figures with k, M or B', async () => {
  const { compact, compactText } = await server.ssrLoadModule('/src/format.ts')
  const { fmtAcres } = await server.ssrLoadModule('/src/components/forecastFormat.ts')
  assert.equal(compact(6886596), '6.89M')
  assert.equal(compact(187176856), '187M')
  assert.equal(compact(15100000000), '15.1B')
  assert.equal(compact(37595), '37.6k')
  assert.equal(compact(999600), '1.00M')
  assert.equal(compact(-1234567), '-1.23M')
  assert.equal(compact(900), '900')
  assert.equal(fmtAcres(82697000), '82.7M')
  assert.equal(compactText('187,176,856 bu'), '187M bu')
  assert.equal(compactText('6,500,000 to 7,250,400'), '6.50M to 7.25M')
  assert.equal(compactText('+1,234,567 bu kept'), '+1.23M bu kept')
  assert.equal(compactText('2,500 acres at $4.10/bu'), '2,500 acres at $4.10/bu')
})
