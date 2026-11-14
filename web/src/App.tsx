import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import type { Pred } from './api'
import { AgentPanel } from './components/AgentPanel'
import { FieldPanel } from './components/FieldPanel'
import { buildRows, FieldsTable, rowsToCsv } from './components/FieldsTable'
import { LogoMark } from './components/Logo'
import { MapView } from './components/MapView'
import { MetricsPanel } from './components/MetricsPanel'
import { Overview, type ReviewItem } from './components/Overview'
import { RollupPanel } from './components/RollupPanel'
import { shortDate } from './format'
import { useAsync } from './hooks'
import { THEMES, ThemeContext, applyTheme, themeById } from './theme'

const VIEWS = [
  { id: 'overview', label: 'Overview' },
  { id: 'fields', label: 'Fields' },
  { id: 'quality', label: 'Model quality' },
  { id: 'agent', label: 'Agent' },
] as const
type ViewId = (typeof VIEWS)[number]['id']

const SHOW_DESIGN = new URLSearchParams(window.location.search).has('design')
const LIVE_YEARS = [2021, 2022, 2023]
const asOfDatesFor = (year: number) => ['08-12', '09-12', '10-12', '11-12'].map((md) => `${year}-${md}`)

function initialTheme() {
  const fromUrl = new URLSearchParams(window.location.search).get('theme')
  if (fromUrl) return themeById(fromUrl)
  try {
    return themeById(window.localStorage.getItem('htw-theme-v3'))
  } catch {
    return themeById(null)
  }
}

export default function App() {
  const [theme, setTheme] = useState(initialTheme)
  const [year, setYear] = useState(2022)
  const [asOfIdx, setAsOfIdx] = useState(2) // Oct 12, the demo date
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [view, setView] = useState<ViewId>('overview')

  useEffect(() => {
    applyTheme(theme)
    try {
      window.localStorage.setItem('htw-theme-v3', theme.id)
    } catch {
      /* storage unavailable */
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

  const counts = useMemo(() => {
    const c = { Grain: 0, Silage: 0, Pending: 0, Insufficient: 0, total: fields.data?.features.length ?? 0 }
    for (const p of predMap.values()) c[p.class] += 1
    return c
  }, [predMap, fields.data])

  const review = useMemo<ReviewItem[]>(() => {
    const out: ReviewItem[] = []
    for (const f of fields.data?.features ?? []) {
      const p = predMap.get(f.properties.OBJECTID)
      const l = f.properties.label
      if (p && l && (p.class === 'Grain' || p.class === 'Silage') && p.class !== l)
        out.push({ id: f.properties.OBJECTID, kind: 'mismatch', reason: `BARC says ${l.toLowerCase()}, model says ${p.class.toLowerCase()}`, pred: p })
    }
    for (const f of fields.data?.features ?? []) {
      const p = predMap.get(f.properties.OBJECTID)
      if (p?.abstain) out.push({ id: f.properties.OBJECTID, kind: 'abstained', reason: 'Too few clear satellite looks', pred: p })
    }
    return out
  }, [fields.data, predMap])

  const select = useCallback((id: number) => setSelectedId(id), [])

  const downloadCsv = () => {
    const csv = rowsToCsv(buildRows(fields.data, predMap), year, asOf)
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `silage-or-grain_${year}_as-of_${asOf}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Presenter shortcuts: 1–4 switch views, ←/→ step the as-of date, Esc closes a field.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (el.closest('input, textarea, select')) return
      const n = Number(e.key)
      if (n >= 1 && n <= VIEWS.length) setView(VIEWS[n - 1].id)
      if (e.key === 'ArrowRight') setAsOfIdx((i) => Math.min(i + 1, asOfDates.length - 1))
      if (e.key === 'ArrowLeft') setAsOfIdx((i) => Math.max(i - 1, 0))
      if (e.key === 'Escape') setSelectedId(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [asOfDates.length])

  return (
    <ThemeContext.Provider value={theme}>
      <div className={`shell shell--${view}`}>
        <MapView fields={fields.data} preds={predMap} selectedId={selectedId} onSelect={select} error={fields.error ?? preds.error} />

        <header className="glass topbar">
          <div className="brand">
            <LogoMark size={30} />
            <div>
              <div className="brand__title">Silage or Grain?</div>
              <div className="brand__sub">BARC corn fields, Beltsville MD</div>
            </div>
          </div>
          <nav className="views" aria-label="Views">
            {VIEWS.map((v, i) => (
              <button key={v.id} title={`Shortcut: ${i + 1}`} aria-current={view === v.id ? 'page' : undefined} className={`views__btn${view === v.id ? ' is-on' : ''}`} onClick={() => setView(v.id)}>
                {v.label}
              </button>
            ))}
          </nav>
          <div className="topbar__spacer" />
          <div className="asof" role="group" aria-label="As-of date">
            <span className="asof__label">As of</span>
            <div className="seg">
              {asOfDates.map((d, i) => (
                <button key={d} className={`seg__btn${d === asOf ? ' is-on' : ''}`} aria-pressed={d === asOf} onClick={() => setAsOfIdx(i)}>
                  {shortDate(d)}
                </button>
              ))}
            </div>
            {preds.loading && <span className="asof__spin" aria-label="Loading predictions" />}
          </div>
          <label className="yearpick">
            Year
            <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
              {years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
          {SHOW_DESIGN && (
            <label className="yearpick">
              Design
              <select value={theme.id} onChange={(e) => setTheme(themeById(e.target.value))}>
                {THEMES.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button className="ghost-btn" onClick={downloadCsv} disabled={!fields.data}>
            Download CSV
          </button>
        </header>

        {view === 'overview' && (
          <Overview
            year={year}
            asOf={asOf}
            counts={counts}
            rollup={rollup.data}
            evaluation={evaluation.data}
            review={review}
            onSelect={select}
            onOpenQuality={() => setView('quality')}
          />
        )}

        {view !== 'overview' && (
          <section className="glass sheet" aria-label={VIEWS.find((v) => v.id === view)?.label}>
            {view === 'fields' && (
              <>
                <h1 className="sheet__title">Fields</h1>
                <p className="sheet__lede">Every BARC field for {year}, called as of {shortDate(asOf)}. Click a row to open its evidence.</p>
                <FieldsTable fields={fields.data} preds={predMap} onSelect={select} selectedId={selectedId} />
              </>
            )}
            {view === 'quality' && (
              <>
                <h1 className="sheet__title">Model quality</h1>
                <MetricsPanel data={evaluation.data} error={evaluation.error} asOf={asOf} />
                <h2 className="sheet__h2">Maryland roll-up</h2>
                <RollupPanel data={rollup.data} error={rollup.error} />
              </>
            )}
            {view === 'agent' && (
              <>
                <h1 className="sheet__title">Agent</h1>
                <AgentPanel />
              </>
            )}
          </section>
        )}

        {selected && (
          <aside className="glass drawer" aria-label={`Field ${selected.properties.OBJECTID}`}>
            <button className="drawer__close" aria-label="Close field" onClick={() => setSelectedId(null)}>
              <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" stroke="currentColor" strokeWidth="2">
                <path d="M2 2l10 10M12 2L2 12" />
              </svg>
            </button>
            <FieldPanel field={selected} pred={predMap.get(selected.properties.OBJECTID)} year={year} asOf={asOf} stub={false} />
          </aside>
        )}

        <div className="glass mapkey">
          <span><i className="k k--silage" />Silage</span>
          <span><i className="k k--grain" />Grain</span>
          <span><i className="k k--pending" />Not yet decided</span>
          <span><i className="k k--abstain" />Abstained</span>
          <span className="mapkey__note">Fill is the model's call, outline is the BARC label</span>
        </div>
      </div>
    </ThemeContext.Provider>
  )
}
