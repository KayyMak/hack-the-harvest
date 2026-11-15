import assert from 'node:assert/strict'
import test from 'node:test'
import { api } from '../src/api.ts'

test('market report posts the year and surfaces the backend setup message on 503', async (t) => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls.push({ url, init })
    return Response.json({ detail: 'NVIDIA_API_KEY is not set. Add it to the .env file in the repository root.' }, { status: 503 })
  })
  await assert.rejects(api.marketReport(2022, '2022-09-12'), (err) => {
    assert.equal(err.status, 503)
    assert.match(err.message, /NVIDIA_API_KEY is not set/)
    return true
  })
  assert.equal(calls[0].url, '/api/market/report')
  assert.equal(calls[0].init.method, 'POST')
  assert.deepEqual(JSON.parse(calls[0].init.body), { year: 2022, as_of: '2022-09-12' })
})

test('market outlook requests the season and as-of date (latest when omitted)', async (t) => {
  const urls = []
  t.mock.method(globalThis, 'fetch', async (url) => {
    urls.push(url)
    return Response.json({ season: 2025, as_of: '2025-09-12', dates: [], sources: {}, timeline: {} })
  })
  await api.marketOutlook(2025, '2025-09-12')
  await api.marketOutlook(2025, null)
  assert.deepEqual(urls, ['/api/market/outlook?season=2025&as_of=2025-09-12', '/api/market/outlook?season=2025'])
})
