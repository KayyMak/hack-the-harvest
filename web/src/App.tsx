import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, STATIC, API_URL } from './api'
import type { Pred } from './api'
import { AgentPanel } from './components/AgentPanel'
import { FieldPanel } from './components/FieldPanel'
import { MapView } from './components/MapView'
import { MetricsPanel } from './components/MetricsPanel'
import { RollupPanel } from './components/RollupPanel'
import { shortDate } from './format'
import { useAsync } from './hooks'
import { THEMES, ThemeContext, applyTheme, themeById } from './theme'

const TABS = [
  { id: 'field', label: 'Field' },
  { id: 'metrics', label: 'Metrics' },
  { id: 'rollup', label: 'MD roll-up' },
  { id: 'agent', label: 'Agent' },
] as const
type TabId = (typeof TABS)[number]['id']

const LIVE_YEARS = [2021, 2022, 2023]
const asOfDatesFor = (year: number) => ['08-12', '09-12', '10-12', '11-12'].map((md) => `${year}-${md}`)

function initialTheme() {
  const fromUrl = new URLSearchParams(window.location.search).get('theme')
  if (fromUrl) return themeById(fromUrl)
  try {
    return themeById(window.localStorage.getItem('htw-theme'))
  } catch {
    return themeById(null)
  }
}

export default function App() {
  const [theme, setTheme] = useState(initialTheme)
  const [year, setYear] = useState(2022)
  const [asOfIdx, setAsOfIdx] = useState(2) // Oct 12 — the demo date
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [tab, setTab] = useState<TabId>('field')

  useEffect(() => {
    applyTheme(theme)
    try {
      window.localStorage.setItem('htw-theme', theme.id)
    } catch {
      /* storage unavailable — fine */
    }
  }, [theme])

  const meta = useAsync(() => api.meta(), [])
  const years = meta.data?.years ?? LIVE_YEARS
  const asOfDates = useMemo(() => {
    const fromMeta = meta.data?.as_of_dates.filter((d) => d.startsWith(String(year)))
    return fromMeta?.length ? fromMeta : asOfDatesFor(year)
  }, [meta.data, year])
  const asOf = asOfDates[Math.min(asOfIdx, asOfDates.length - 1)]

  const fields = useAsync(() => api.fields(year), [year])
  const preds = useAsync(() => api.predict(year, asOf), [year, asOf])
  const evaluation = useAsync(() => api.evaluate('strict'), [])
  const rollup = useAsync(() => api.rollup(year), [year])

  const predMap = useMemo(() => new Map<number, Pred>((preds.data ?? []).map((p) => [p.OBJECTID, p])), [preds.data])
  const selected = fields.data?.features.find((f) => f.properties.OBJECTID === selectedId) ?? null

  const shortcuts = useMemo(() => {
    const wrong: number[] = []
    const abstained: number[] = []
    for (const f of fields.data?.features ?? []) {
      const p = predMap.get(f.properties.OBJECTID)
      const l = f.properties.label
      if (p && l && (p.class === 'Grain' || p.class === 'Silage') && p.class !== l) wrong.push(f.properties.OBJECTID)
      if (p?.abstain) abstained.push(f.properties.OBJECTID)
    }
    return [
      { title: `Disagrees with BARC label (${wrong.length})`, ids: wrong },
      { title: `Abstained (X) (${abstained.length})`, ids: abstained },
    ]
  }, [fields.data, predMap])

  const select = useCallback((id: number) => {
    setSelectedId(id)
    setTab('field')
  }, [])

  // Presenter shortcuts: 1–4 switch panels, ←/→ step the as-of date.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (el.closest('input, textarea, select')) return
      const n = Number(e.key)
      if (n >= 1 && n <= TABS.length) setTab(TABS[n - 1].id)
      if (e.key === 'ArrowRight') setAsOfIdx((i) => Math.min(i + 1, asOfDates.length - 1))
      if (e.key === 'ArrowLeft') setAsOfIdx((i) => Math.max(i - 1, 0))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [asOfDates.length])

  const stub = STATIC && meta.data?.stub === true

  return (
    <ThemeContext.Provider value={theme}>
      <div className="app">
        {stub && (
          <div className="stub-banner" role="status">
            FAKE STUB DATA — placeholder numbers and shapes for building the UI. Not results.
          </div>
        )}
        <header className="bar">
          <div className="brand">
            <span className="brand__mark" aria-hidden>
              <span />
              <span />
            </span>
            <div>
              <div className="brand__title">Silage or Grain?</div>
              <div className="brand__sub">BARC fields · Beltsville, Maryland · {year} · Team BetterGreen prototype, not a USDA/NASS release</div>
            </div>
          </div>

          <AsOfSlider dates={asOfDates} index={asOfDates.indexOf(asOf)} onChange={setAsOfIdx} loading={preds.loading} />

          <div className="bar__right">
            <label className="field-select">
              <span>Year</span>
              <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
                {years.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-select">
              <span>Design</span>
              <select value={theme.id} onChange={(e) => setTheme(themeById(e.target.value))} title={theme.blurb}>
                {THEMES.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
            <span className={`mode ${STATIC ? 'mode--static' : 'mode--live'}`} title={STATIC ? 'Reading public/snapshot/*.json' : API_URL}>
              {STATIC ? 'Offline snapshot' : 'Live API'}
            </span>
          </div>
        </header>

        <main className="main">
          <MapView
            fields={fields.data}
            preds={predMap}
            asOf={asOf}
            selectedId={selectedId}
            onSelect={select}
            error={fields.error ?? preds.error}
          />

          <aside className="panel">
            <nav className="tabs" role="tablist" aria-label="Panels">
              {TABS.map((t, i) => (
                <button key={t.id} role="tab" aria-selected={tab === t.id} className={`tab${tab === t.id ? ' is-active' : ''}`} onClick={() => setTab(t.id)}>
                  <span className="tab__key">{i + 1}</span>
                  {t.label}
                </button>
              ))}
            </nav>
            <div className="panel__body" role="tabpanel">
              {tab === 'field' && <FieldPanel shortcuts={shortcuts} onSelect={select} field={selected} pred={selectedId != null ? predMap.get(selectedId) : undefined} year={year} asOf={asOf} stub={stub} />}
              {tab === 'metrics' && <MetricsPanel data={evaluation.data} error={evaluation.error} asOf={asOf} />}
              {tab === 'rollup' && <RollupPanel data={rollup.data} error={rollup.error} />}
              {tab === 'agent' && <AgentPanel />}
            </div>
            <footer className="panel__foot">
              <span><b>(NA)</b> not yet decided by the as-of date</span>
              <span><b>(X)</b> abstained: too few clear satellite looks</span>
              <span>Intervals are 95%</span>
            </footer>
          </aside>
        </main>
      </div>
    </ThemeContext.Provider>
  )
}

function AsOfSlider({ dates, index, onChange, loading }: { dates: string[]; index: number; onChange: (i: number) => void; loading: boolean }) {
  return (
    <div className="asof">
      <div className="asof__label">
        As of <strong>{shortDate(dates[index])}</strong>
        {loading && <span className="asof__spin" aria-label="Loading predictions" />}
      </div>
      <input
        type="range"
        min={0}
        max={dates.length - 1}
        step={1}
        value={index}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label="As-of date"
        aria-valuetext={shortDate(dates[index])}
        list="asof-ticks"
      />
      <div className="asof__ticks" aria-hidden>
        {dates.map((d, i) => (
          <button key={d} className={i === index ? 'is-on' : ''} onClick={() => onChange(i)} tabIndex={-1}>
            {shortDate(d)}
          </button>
        ))}
      </div>
    </div>
  )
}
