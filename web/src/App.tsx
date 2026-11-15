import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { unlabeledCallsAt } from './adapter'
import type { FieldLandcover, Pred, UnlabeledCallView } from './api'
import { AgentPanel } from './components/AgentPanel'
import { Estimate2025Panel } from './components/Estimate2025'
import { DeclineRulePanel, PerYearPanel } from './components/DeclineRule'
import { FieldPanel } from './components/FieldPanel'
import { buildRows, FieldsTable, rowsToCsv } from './components/FieldsTable'
import { LogoMark } from './components/Logo'
import { MapView } from './components/MapView'
import { ForecastKey, ForecastPanels } from './components/Forecast'
import type { Crop, Forecast } from './components/forecastTypes'
import { USMap } from './components/USMap'
import { MarketPanel } from './components/MarketPanel'
import { MetricsPanel } from './components/MetricsPanel'
import { Overview, type ReviewItem } from './components/Overview'
import { Pending } from './components/Pending'
import { AcresConvergence } from './components/AcresConvergence'
import { RollupPanel } from './components/RollupPanel'
import { shortDate } from './format'
import { useAsync } from './hooks'
import { THEMES, ThemeContext, applyTheme, modeById, themeById, withMode } from './theme'
import type { Mode } from './theme'

// Number keys 1–6 follow this order; the graded 2025 answer is the landing view.
const VIEWS = [
  { id: 'states', label: '2025 by state' },
  { id: 'overview', label: 'BARC validation' },
  { id: 'fields', label: 'Fields' },
  { id: 'quality', label: 'Model quality' },
  { id: 'agent', label: 'Agent' },
  { id: 'market', label: 'Market' },
] as const
type ViewId = (typeof VIEWS)[number]['id']
/** Views driven by the BARC As-of date and Year controls; on the others those controls have no effect. */
const BARC_VIEWS: ReadonlySet<ViewId> = new Set(['overview', 'fields', 'quality'])

const CHECKPOINT_TIP = 'Aug–Nov 12: what the model could call on roughly each NASS report day, using only imagery to that date; Nov 30: full-season final call (model v2)'
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

function initialMode(): Mode {
  const fromUrl = new URLSearchParams(window.location.search).get('mode')
  if (fromUrl) return modeById(fromUrl)
  try {
    return modeById(window.localStorage.getItem('htw-mode'))
  } catch {
    return 'dark'
  }
}

export default function App() {
  const [theme, setTheme] = useState(initialTheme)
  const [mode, setMode] = useState<Mode>(initialMode)
  const shownTheme = useMemo(() => withMode(theme, mode), [theme, mode])
  const [year, setYear] = useState(2022)
  // -1 = the last date, Nov 30 (season end): v2 calls, unlabeled-field calls and before/after chips all show there.
  const [asOfIdx, setAsOfIdx] = useState(-1)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [view, setView] = useState<ViewId>('states')
  const [crop, setCrop] = useState<Crop>('silage')
  const [usState, setUsState] = useState<string | null>(null)
  const [stateTable, setStateTable] = useState(false)
  const byState = useAsync(async () => {
    const r = await fetch(`${import.meta.env.BASE_URL ?? '/'}forecast_2025.json`)
    if (!r.ok) throw new Error(`forecast_2025.json → ${r.status}`)
    return (await r.json()) as Forecast
  }, [])
  const usShapes = useAsync(async () => (await fetch(`${import.meta.env.BASE_URL ?? '/'}us-states.geojson`)).json(), [])
  const byStateRows = useMemo(() => new Map((byState.data?.states ?? []).map((r) => [r.state, r])), [byState.data])

  useEffect(() => {
    applyTheme(theme, mode)
    try {
      window.localStorage.setItem('htw-theme-v3', theme.id)
      window.localStorage.setItem('htw-mode', mode)
    } catch {
      /* storage unavailable */
    }
  }, [theme, mode])

  const meta = useAsync(() => api.meta(), [])
  const years = meta.data?.years ?? LIVE_YEARS
  const asOfDates = useMemo(() => {
    const fromMeta = meta.data?.as_of_dates.filter((d) => d.startsWith(String(year)))
    return fromMeta?.length ? fromMeta : asOfDatesFor(year)
  }, [meta.data, year])
  const asOfAt = (i: number) => (i < 0 ? asOfDates.length - 1 : Math.min(i, asOfDates.length - 1))
  const asOf = meta.loading ? `${year}-11-30` : asOfDates[asOfAt(asOfIdx)]

  const seasonEnd = meta.data?.season_end_only === true || asOfDates.length === 1
  const fields = useAsync(() => api.fields(year), [year])
  const preds = useAsync(() => api.predict(year, asOf), [year, asOf])
  const evaluation = useAsync(() => api.evaluate('strict', year), [year])
  const rollup = useAsync(() => api.rollup(year), [year])
  const acresConv = useAsync(() => api.convergenceAcres(), [])
  const estimate = useAsync(() => api.estimate2025(), [])
  const declineRule = useAsync(() => api.declineRule(), [])
  const unlabeled = useAsync(() => api.unlabeled(year), [year])
  const landcover = useAsync(() => api.landcover(year), [year])
  const coverMap = useMemo(() => new Map<number, FieldLandcover>((landcover.data ?? []).map((c) => [c.field_id, c])), [landcover.data])
  // Season-end calls: shown only when Nov 30 is selected, never on a mid-season date.
  const atSeasonEnd = asOf === `${year}-11-30`
  const unlabeledMap = useMemo(() => new Map<number, UnlabeledCallView>(unlabeledCallsAt(unlabeled.data, year, asOf).map((c) => [c.OBJECTID, c])), [unlabeled.data, year, asOf])

  const predMap = useMemo(() => new Map<number, Pred>((preds.data ?? []).map((p) => [p.OBJECTID, p])), [preds.data])
  const selected = fields.data?.features.find((f) => f.properties.OBJECTID === selectedId) ?? null

  const counts = useMemo(() => {
    const total = fields.data?.features.length ?? 0
    const labeled = fields.data?.features.filter((f) => f.properties.label).length ?? 0
    const c = { Grain: 0, Silage: 0, Pending: 0, Insufficient: 0, total, labeled }
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

  // Measure where the right-hand panels start so the map key and zoom buttons stay in the visible map.
  const shellRef = useRef<HTMLDivElement>(null)
  const panelsOpen = `${view}-${selectedId != null}`
  useLayoutEffect(() => {
    const shell = shellRef.current
    if (!shell) return
    const measure = () => {
      const lefts = ['.rail', '.sheet', '.drawer']
        .map((sel) => shell.querySelector(sel)?.getBoundingClientRect())
        .filter((r): r is DOMRect => !!r && r.width > 0)
        .map((r) => r.left)
      const freeRight = lefts.length ? window.innerWidth - Math.min(...lefts) + 16 : 16
      shell.style.setProperty('--free-right', `${freeRight}px`)
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [panelsOpen])

  const downloadCsv = () => {
    const csv = rowsToCsv(buildRows(fields.data, predMap, unlabeledMap, coverMap, atSeasonEnd), year, asOf)
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `silage-or-grain_${year}_as-of_${asOf}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Presenter shortcuts: 1–6 switch views (in tab order), ←/→ step the as-of date, Esc closes a field.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (el.closest('input, textarea, select')) return
      const n = Number(e.key)
      if (n >= 1 && n <= VIEWS.length) setView(VIEWS[n - 1].id)
      const last = asOfDates.length - 1
      const at = (i: number) => (i < 0 ? last : Math.min(i, last))
      if (e.key === 'ArrowRight') setAsOfIdx((i) => Math.min(at(i) + 1, last))
      if (e.key === 'ArrowLeft') setAsOfIdx((i) => Math.max(at(i) - 1, 0))
      if (e.key === 'Escape') {
        setSelectedId(null)
        setUsState(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [asOfDates.length])

  return (
    <ThemeContext.Provider value={shownTheme}>
      <div ref={shellRef} className={`shell shell--${view}`}>
        {meta.error && <p className="map-card map-error" role="alert">Snapshot metadata unavailable: {meta.error.message}</p>}
        {meta.data?.stub && <p className="map-card map-error" role="alert">Demonstration data: these values are fabricated and are not model results.</p>}
        {view === 'states' ? (
          <USMap shapes={usShapes.data} rows={byStateRows} crop={crop} selected={usState} onSelect={setUsState} dark={mode === 'dark'} layoutKey={`${usState ?? ''}-${stateTable}-${!!byState.data}`} />
        ) : <MapView fields={fields.data} preds={predMap} unlabeled={unlabeledMap} cover={coverMap} seasonEnd={atSeasonEnd} selectedId={selectedId} onSelect={select} error={fields.error ?? preds.error} layoutKey={`${view}-${selected ? 'open' : 'closed'}`} />}
        {view === 'states' && byState.data && (
          <>
            <ForecastPanels data={byState.data} crop={crop} selected={usState} onSelect={setUsState} showTable={stateTable} onTable={setStateTable} />
            <ForecastKey crop={crop} />
          </>
        )}
        {view === 'states' && byState.error && <p className="map-card map-error" role="alert">2025 by-state estimate unavailable: {byState.error.message}</p>}

        <header className="glass topbar">
          <div className="brand">
            <LogoMark size={30} />
            <div>
              <div className="brand__title">Cutline</div>
              <div className="brand__sub">Silage or grain, BARC fields, Beltsville MD</div>
            </div>
          </div>
          <nav className="views" aria-label="Views">
            {VIEWS.map((v) => (
              <button key={v.id} aria-current={view === v.id ? 'page' : undefined} className={`views__btn${view === v.id ? ' is-on' : ''}`} onClick={() => setView(v.id)}>
                {v.label}
              </button>
            ))}
          </nav>
          <div className="topbar__spacer" />
          {BARC_VIEWS.has(view) && <>
          <div className="asof" role="group" aria-label="Satellite checkpoint" title={CHECKPOINT_TIP}>
            <span className="asof__label">{seasonEnd ? 'Calls' : 'Satellite checkpoint'}</span>
            {seasonEnd ? (
              <span className="season-pill" title="Mid-season calls are pending">End of season {year}</span>
            ) : (
            <div className="seg">
              {asOfDates.map((d, i) => (
                <button key={d} className={`seg__btn${d === asOf ? ' is-on' : ''}`} aria-pressed={d === asOf} onClick={() => setAsOfIdx(i)} title={CHECKPOINT_TIP}>
                  {shortDate(d)}
                </button>
              ))}
            </div>
            )}
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
          </>}
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
          {view === 'states' && byState.data && <>
            <div className="seg statecrop-top" role="group" aria-label="Crop">
              {(['silage', 'grain'] as Crop[]).map((c) => (
                <button key={c} className={`seg__btn${crop === c ? ' is-on' : ''}`} aria-pressed={crop === c} onClick={() => setCrop(c)}><i className={`dot dot--${c}`} aria-hidden="true" />{c === 'silage' ? 'Silage' : 'Grain'}</button>
              ))}
            </div>
            <a className="ghost-btn" href={`${import.meta.env.BASE_URL ?? '/'}forecast_state_estimates_2025.csv`} download="state_estimates_2025.csv">
              <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M7 1.5v8M3.5 6.5L7 10l3.5-3.5M2 12.5h10" />
              </svg>
              Download 2025 CSV
            </a>
          </>}
          {BARC_VIEWS.has(view) && <button className="ghost-btn" onClick={downloadCsv} disabled={!fields.data || preds.loading || !!preds.error}>
            <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M7 1.5v8M3.5 6.5L7 10l3.5-3.5M2 12.5h10" />
            </svg>
            Download BARC fields CSV
          </button>}
          {theme.id === 'glass' && <ModeToggle mode={mode} onToggle={() => setMode((m) => (m === 'dark' ? 'light' : 'dark'))} />}
        </header>

        {view === 'overview' && (
          <Overview
            year={year}
            asOf={asOf}
            counts={counts}
            rollup={rollup.data}
            unlabeled={unlabeled.data}
            unlabeledError={unlabeled.error}
            unlabeledAtSeasonEnd={atSeasonEnd}
            evaluation={evaluation.data}
            review={review}
            onSelect={select}
            onOpenQuality={() => setView('quality')}
            onOpenFields={() => setView('fields')}
            seasonEnd={seasonEnd}
          />
        )}

        {view !== 'overview' && view !== 'states' && (
          <section className="glass sheet" aria-label={VIEWS.find((v) => v.id === view)?.label}>
            {view === 'fields' && (
              <>
                <h1 className="sheet__title">Fields</h1>
                <p className="sheet__lede">BARC-labeled fields for {year}, called as of {shortDate(asOf)}; tick "Show unlabeled" for the rest. Click a row for its evidence.</p>
                <details className="more">
                  <summary>What the columns mean</summary>
                  <p className="muted small">BARC label is the reference label. Model call is our held-out call; "no label" marks season-end calls on fields BARC did not label but the Cropland Data Layer shows as corn, with nothing to check them against. CDL crop is the USDA Cropland Data Layer's satellite crop map for that year (hover a cell for detail): context only, never a BARC label or a model call.</p>
                </details>
                <FieldsTable fields={fields.data} preds={predMap} unlabeled={unlabeledMap} cover={coverMap} coverError={landcover.error} seasonEnd={atSeasonEnd} onSelect={select} selectedId={selectedId} />
              </>
            )}
            {view === 'quality' && (
              <>
                <h1 className="sheet__title">Model quality</h1>
                <MetricsPanel data={evaluation.data} error={evaluation.error} asOf={asOf} />
                {seasonEnd && (
                  <Pending title="Mid-season calls">
                    Calls as of Aug 12, Sep 12, Oct 12 and Nov 12, showing how many fields are decided and how accurate those calls are at each date.
                  </Pending>
                )}
                <details className="more section">
                  <summary>Per-year results</summary>
                  <PerYearPanel state={declineRule} />
                </details>
                <details className="more section">
                  <summary>Silage acres through the season</summary>
                  <AcresConvergence data={acresConv.data} error={acresConv.error} year={year} onYear={setYear} />
                </details>
                <details className="more section">
                  <summary>Acre roll-up, {year}</summary>
                  {rollup.error ? (
                    <Pending title="Silage acres roll-up">
                      {rollup.error.message}
                    </Pending>
                  ) : (
                    <RollupPanel data={rollup.data} error={rollup.error} />
                  )}
                </details>
                <details className="more section">
                  <summary>Decline-rule baseline</summary>
                  <DeclineRulePanel state={declineRule} />
                </details>
                <details className="more section">
                  <summary>Satellite cross-check, Maryland 2025</summary>
                  <Estimate2025Panel state={estimate} />
                </details>
              </>
            )}
            {view === 'market' && (
              <>
                <h1 className="sheet__title">Market outlook</h1>
                <MarketPanel />
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

        {view !== 'states' && selected && (
          <aside className="glass drawer" aria-label={`Field ${selected.properties.OBJECTID}`}>
            <button className="drawer__close" aria-label="Close field" onClick={() => setSelectedId(null)}>
              <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" stroke="currentColor" strokeWidth="2">
                <path d="M2 2l10 10M12 2L2 12" />
              </svg>
            </button>
            <FieldPanel field={selected} pred={predMap.get(selected.properties.OBJECTID)} year={year} asOf={asOf} stub={false} showChips={meta.data ? meta.data.has_chips !== false : true} unlabeledCall={unlabeledMap.get(selected.properties.OBJECTID)} cover={coverMap.get(selected.properties.OBJECTID)} />
          </aside>
        )}

        {view !== 'states' && <div className="glass mapkey">
          <span><i className="k k--silage" />Silage</span>
          <span><i className="k k--grain" />Grain</span>
          <span><i className="k k--pending" />{seasonEnd || atSeasonEnd ? 'No label, no call' : 'Not yet decided'}</span>
          {unlabeledMap.size > 0 && <span><i className="k k--unlabeled" />Model call, no label</span>}
          {!seasonEnd && <span><i className="k k--abstain" />Abstained</span>}
          <span className="mapkey__note">Fill is the model's call, outline is the BARC label{coverMap.size > 0 ? '; hover a field for its USDA Cropland Data Layer crop' : ''}</span>
          <span className="mapkey__fine">
            Sentinel-2 imagery. Scores {evaluation.data?.split_label ?? 'held out'}. Prototype, not a USDA or NASS release.
          </span>
        </div>}
      </div>
    </ThemeContext.Provider>
  )
}

function ModeToggle({ mode, onToggle }: { mode: Mode; onToggle: () => void }) {
  const next = mode === 'dark' ? 'light' : 'dark'
  const label = `Switch to ${next} mode`
  return (
    <button className="ghost-btn mode-btn" onClick={onToggle} aria-label={label} title={label}>
      {next === 'light' ? (
        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <circle cx="12" cy="12" r="4.5" />
          <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" />
        </svg>
      ) : (
        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
          <path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11z" />
        </svg>
      )}
    </button>
  )
}
