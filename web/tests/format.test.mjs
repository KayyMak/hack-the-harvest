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
