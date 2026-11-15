import { useState } from 'react'
import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, STATIC } from '../api'
import type { MarketOutlook } from '../api'
import { compactText, shortDate } from '../format'
import { useAsync } from '../hooks'
import { DATA, useTheme } from '../theme'
import { xTitle, yTitle } from './charts'
import { Pending } from './Pending'

type Dict = Record<string, unknown>
const SEASONS = [
  { season: 2025, label: '2025 outlook (US and Maryland)' },
  { season: 2023, label: '2023 (BARC model)' },
  { season: 2022, label: '2022 (BARC model)' },
  { season: 2021, label: '2021 (BARC model)' },
]
const NASS_RELEASE_TIP = '2025 NASS releases: Jun 30 Acreage; Aug 12, Sep 12, Nov 14 Crop Production (no October report in 2025)'
const str = (v: unknown) => (typeof v === 'string' || typeof v === 'number' ? String(v) : '—')
/** Backend figures arrive preformatted ("187,176,856 bu"); show them to three significant figures ("187M bu"). */
const big = (v: unknown) => compactText(str(v))

/** Optional sample market outlook: month by month, using only what was known on each date. Nemotron reads
 *  our forecasts, model calls and NASS data through server-side tools and writes the report. */
export function MarketPanel() {
  const [season, setSeason] = useState(2025)
  const [asOf, setAsOf] = useState<string | null>(null) // null = latest date for the season
  const outlook = useAsync(() => api.marketOutlook(season, asOf), [season, asOf])
  const [showOutlook, setShowOutlook] = useState(false)

  if (STATIC) return <Pending title="Market outlook">Market outlooks need the live backend; this static snapshot cannot load them.</Pending>

  const o = outlook.data
  const shownAsOf = o?.as_of ?? asOf

  return (
    <div className="market">
      <p className="sheet__lede">
        A sample corn supply outlook that updates release by release. Pick a season and a date: everything shown uses only
        what was known on that date. NASS forecasts plus our silage estimates; no price forecasts.
      </p>

      <div className="market__controls">
        <label className="yearpick">
          Season
          <select value={season} onChange={(e) => { setAsOf(null); setSeason(Number(e.target.value)) }}>
            {SEASONS.map((x) => (
              <option key={x.season} value={x.season}>{x.label}</option>
            ))}
          </select>
        </label>
        {o && (
          <div className="market__dates" title={season === 2025 ? NASS_RELEASE_TIP : 'Satellite checkpoint dates for the BARC model'}>
          <span className="asof__label">{season === 2025 ? 'NASS release' : 'Satellite checkpoint'}</span>
          <div className="seg" role="group" aria-label={season === 2025 ? 'NASS release' : 'Satellite checkpoint'}>
            {o.dates.map((d) => (
              <button key={d} className={`seg__btn${d === o.as_of ? ' is-on' : ''}`} aria-pressed={d === o.as_of} onClick={() => setAsOf(d)}>
                {shortDate(d)}
              </button>
            ))}
          </div>
          </div>
        )}
      </div>

      {outlook.error ? (
        <p className="inline-error" role="alert">Outlook unavailable: {outlook.error.message}</p>
      ) : !o ? (
        <div className="skeleton skeleton--chart" />
      ) : (
        <>
          <OutlookChart outlook={o} />
          <OutlookCards outlook={o} />
        </>
      )}

      {o && (
        <div className="market__actions">
          <button className="button" onClick={() => setShowOutlook((v) => !v)}>
            {showOutlook ? 'Hide outlook' : `Write outlook as of ${shownAsOf ? shortDate(shownAsOf) : '…'}`}
          </button>
        </div>
      )}
      {showOutlook && o && <CleanOutlook outlook={o} />}
    </div>
  )
}

/** A short, readable outlook built only from the loaded data (NASS forecasts + our estimates): an overview, then tabs. */
function CleanOutlook({ outlook }: { outlook: MarketOutlook }) {
  const [tab, setTab] = useState<'overview' | 'months' | 'sure' | 'sources'>('overview')
  const tl = outlook.timeline as Dict
  const latest = (tl.latest_release as Dict | undefined) ?? {}
  const earlier = ((tl.earlier_releases as Dict[] | undefined) ?? []).filter((r) => r.as_of !== latest.as_of)
  const series = (tl.series as Dict[] | undefined) ?? []
  const supplyAt = (d: unknown) => {
    const v = series.find((r) => r.as_of === d)?.us_production_change_pct
    return typeof v === 'number' ? `${v > 0 ? '+' : ''}${v.toFixed(1)}%` : '—'
  }
  const date = shortDate(outlook.as_of)
  const us = tl.kind === 'statewide_and_us_outlook'
  const base = (us ? tl.baseline_2024_official : tl.latest_official_baseline) as Dict | undefined
  const TABS = [['overview', 'Overview'], ['months', us ? 'Release by release' : 'Checkpoint by checkpoint'], ['sure', 'How sure'], ['sources', 'Sources']] as const
  const rows = us ? [...earlier, latest] : []
  return (
    <section className="glass outlook" aria-label="Outlook">
      <div className="outlook__head">
        <h3>{us ? `Corn supply outlook, as of ${date}, 2025` : `BARC silage outlook, as of ${date}, ${outlook.season}`}</h3>
        <div className="seg" role="tablist">
          {TABS.map(([id, name]) => (
            <button key={id} role="tab" aria-selected={tab === id} className={`seg__btn${tab === id ? ' is-on' : ''}`} onClick={() => setTab(id)}>{name}</button>
          ))}
        </div>
      </div>

      {tab === 'overview' && us && (
        <ul className="outlook__list">
          <li>
            <b>US corn for grain:</b>{' '}
            {latest.us_grain_production_forecast
              ? <>NASS forecasts {str(latest.us_grain_production_forecast)} ({str(latest.us_grain_acres_forecast)} acres at {str(latest.us_grain_yield_forecast)}), {str(latest.us_grain_supply_change_vs_2024)} vs 2024 ({str(base?.us_grain_production)}).</>
              : <>NASS forecasts {str(latest.us_grain_acres_forecast)} acres for grain; its first yield and production forecast comes in August.</>}
          </li>
          <li><b>US corn for silage:</b> our forecast is {str(latest.us_silage_acres_estimate)} acres (95% range {str(latest.us_silage_95pct_range)}). NASS publishes silage acres only in January.</li>
          <li>
            <b>Maryland:</b> our silage forecast is {str(latest.md_silage_acres_estimate)} acres, {str(latest.md_silage_share_estimate)} of its harvested corn
            {latest.md_grain_production_forecast ? <>; NASS forecasts {str(latest.md_grain_production_forecast)} of grain at {str(latest.md_grain_yield_forecast)}.</> : '.'}
          </li>
          {latest.grain_kept_off_market_by_us_silage != null && (
            <li><b>Silage vs grain supply:</b> US silage acres keep about {big(latest.grain_kept_off_market_by_us_silage)} of corn off the grain market (silage acres times the NASS grain yield).</li>
          )}
        </ul>
      )}
      {tab === 'overview' && !us && (
        <ul className="outlook__list">
          <li><b>BARC fields:</b> the satellite model expects {str(latest.barc_expected_silage_acres)} silage acres as of {date} (95% range {str(latest.range_95pct)} acres), with {str(latest.fields_decided)} labeled fields decided.</li>
          {base && <li><b>Maryland, {str(base.year)} (NASS, official):</b> silage was {str(base.maryland_silage_share_of_harvested_corn)} of harvested corn ({str(base.maryland_silage_acres_harvested)} silage vs {str(base.maryland_grain_acres_harvested)} grain acres).</li>}
          <li><b>What this is:</b> the BARC model's call through the season for one research farm; it is not a state estimate.</li>
        </ul>
      )}

      {tab === 'months' && us && (
        <table className="mini-table outlook__table">
          <thead><tr><th>NASS release</th><th className="num">US grain acres</th><th className="num">Grain supply vs 2024</th><th className="num">US silage (ours)</th><th className="num">MD silage share</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={str(r.as_of)}>
                <td>{shortDate(str(r.as_of))}</td>
                <td className="num">{str(r.us_grain_acres_forecast)}</td>
                <td className="num">{supplyAt(r.as_of)}</td>
                <td className="num">{str(r.us_silage_acres_estimate)}</td>
                <td className="num">{str(r.md_silage_share_estimate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {tab === 'months' && !us && (
        <table className="mini-table outlook__table">
          <thead><tr><th>Checkpoint</th><th className="num">BARC silage acres (model)</th><th className="num">95% range</th></tr></thead>
          <tbody>
            {series.map((r) => (
              <tr key={str(r.as_of)}>
                <td>{shortDate(str(r.as_of))}</td>
                <td className="num">{typeof r.barc_expected_silage_acres === 'number' ? r.barc_expected_silage_acres.toFixed(1) : '—'}</td>
                <td className="num">{typeof r.barc_low === 'number' && typeof r.barc_high === 'number' ? `${r.barc_low.toFixed(1)}–${r.barc_high.toFixed(1)}` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === 'sure' && (
        <ul className="outlook__list">
          {us && <li>US silage: 95% range {str(latest.us_silage_95pct_range)} acres, calibrated on the 2018–2024 backtest.</li>}
          {us && <li>Grain acres, yields and production are NASS's own forecasts on each date; they converge to the January final.</li>}
          <li>{str(tl.what_is_ours ?? tl.scope)}</li>
          <li>{str(tl.next_official_numbers)}</li>
        </ul>
      )}

      {tab === 'sources' && (
        <ul className="outlook__list">
          {rows.map((r) => r.source).filter(Boolean).map((s) => <li key={str(s)}>USDA NASS: {str(s)}</li>)}
          {Object.values(outlook.sources ?? {}).map((s) => <li key={String(s)}>{String(s)}</li>)}
        </ul>
      )}
    </section>
  )
}

function OutlookCards({ outlook }: { outlook: MarketOutlook }) {
  const t = outlook.timeline as Dict
  const latest = (t.latest_release as Dict | undefined) ?? {}
  const date = shortDate(outlook.as_of)
  if (t.kind === 'statewide_and_us_outlook') {
    const base = t.baseline_2024_official as Dict
    return (
      <section className="kpis market__kpis" aria-label="Outlook figures">
        <Kpi label="US grain supply" value={str(latest.us_grain_supply_change_vs_2024 ?? 'Not yet')}
          sub={latest.us_grain_production_forecast ? `vs 2024, as of ${date}: ${big(latest.us_grain_production_forecast)} forecast` : `vs 2024, as of ${date}: NASS yield forecasts start in August`}
          foot={`2024: ${big(base?.us_grain_production)}`} />
        <Kpi label="US silage acres" value={big(latest.us_silage_acres_estimate)} sub={`Our estimate, 95%: ${big(latest.us_silage_95pct_range)}`}
          foot={latest.change_in_grain_kept_off_market_vs_2024 ? `${big(latest.change_in_grain_kept_off_market_vs_2024)} kept off grain market vs 2024` : `2024: ${big(base?.us_silage_acres)} acres`} />
        <Kpi label="Maryland silage share" value={str(latest.md_silage_share_estimate)} sub={`Our estimate: ${big(latest.md_silage_acres_estimate)} acres (95%: ${big(latest.md_silage_95pct_range)})`}
          foot={`2024: ${big(base?.md_silage_acres)} silage acres`} />
      </section>
    )
  }
  const baseline = (t.latest_official_baseline ?? {}) as Dict
  return (
    <section className="kpis market__kpis" aria-label="Outlook figures">
      <Kpi label="BARC silage acres" value={`${big(latest.barc_expected_silage_acres)} ac`}
        sub={`Model estimate as of ${date}, 95%: ${big(latest.range_95pct)} acres`} foot={`${str(latest.fields_decided)} labeled fields decided`} />
      <Kpi label={`Maryland silage share, ${str(baseline.year)}`} value={str(baseline.maryland_silage_share_of_harvested_corn)}
        sub={`${big(baseline.maryland_silage_acres_harvested)} silage vs ${big(baseline.maryland_grain_acres_harvested)} grain acres`} foot="USDA NASS, prior season (official)" />
      <Kpi label={`Grain kept off market, ${str(baseline.year)}`} value={`${big(baseline.grain_bushels_not_produced_because_of_silage_acres)} bu`}
        sub={`Bushels not grown because of silage acres, at ${str(baseline.maryland_grain_price_received)}`} foot="Prior season, official" />
    </section>
  )
}

function OutlookChart({ outlook }: { outlook: MarketOutlook }) {
  const t = useTheme().chart
  const tl = outlook.timeline as Dict
  const series = (tl.series as Dict[]) ?? []
  const grid = <CartesianGrid stroke={t.grid} vertical={false} />
  const x = <XAxis dataKey="label" stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} height={36} padding={{ left: 18, right: 18 }} label={xTitle(tl.kind === 'statewide_and_us_outlook' ? 'NASS release date, 2025' : 'Satellite checkpoint', t.muted)} />
  // compact value-only tooltip: short names, one decimal, same style as the other charts
  const SHORT: Record<string, string> = { supply: 'US grain supply vs 2024', md: 'MD silage share', est: 'BARC silage acres' }
  const tip = (
    <Tooltip
      cursor={{ stroke: t.axis, strokeDasharray: '3 3' }}
      content={({ active, payload, label }) => {
        const items = (payload ?? []).filter((p) => p.value != null && SHORT[String(p.dataKey)])
        if (!active || !items.length) return null
        return (
          <div className="chart-tip">
            <div className="chart-tip__title">{label}</div>
            {items.map((p) => {
              const v = Number(p.value)
              const pct = p.dataKey === 'supply' || p.dataKey === 'md'
              const text = pct ? `${p.dataKey === 'supply' && v > 0 ? '+' : ''}${v.toFixed(1)}%` : Math.round(v).toLocaleString('en-US')
              return <div className="chart-tip__row" key={String(p.dataKey)}>{SHORT[String(p.dataKey)]} <span className="chart-tip__value">{text}</span></div>
            })}
          </div>
        )
      }}
    />
  )
  const legend = <Legend verticalAlign="top" align="left" height={58} iconType="plainline" wrapperStyle={{ fontSize: 12, lineHeight: '18px', color: t.ink, paddingBottom: 14 }} />
  if (tl.kind === 'statewide_and_us_outlook') {
    const rows = series.map((r) => ({ label: shortDate(String(r.as_of)), supply: r.us_production_change_pct, md: r.md_silage_share_pct }))
    // The June Acreage report carries no grain production forecast, so the supply line starts at the first one.
    const firstNoSupply = rows.length > 0 && rows[0].supply == null
    return (
      <figure className="market__chart" role="img" aria-label="US grain supply change versus 2024 and our Maryland silage share, by release date">
        <ResponsiveContainer width="100%" height={300}>
          <ComposedChart data={rows} margin={{ top: 4, right: 16, bottom: 4, left: 4 }}>
            {grid}{x}
            <YAxis stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} width={60} unit="%" label={yTitle('Percent', t.muted)} />
            {tip}
            {legend}
            <Line type="monotone" dataKey="supply" name={`US grain supply vs 2024 (NASS forecast${firstNoSupply ? `; none in the ${rows[0].label} Acreage report` : ''})`} stroke={DATA.grain} strokeWidth={2.5} dot={{ r: 3 }} connectNulls isAnimationActive={false} unit="%" />
            <Line type="monotone" dataKey="md" name="Maryland silage share (our estimate)" stroke={DATA.silage} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} unit="%" />
          </ComposedChart>
        </ResponsiveContainer>
      </figure>
    )
  }
  const rows = series.map((r) => ({
    label: shortDate(String(r.as_of)), est: r.barc_expected_silage_acres, lo: r.barc_low,
    band: Number(r.barc_high) - Number(r.barc_low),
  }))
  return (
    <figure className="market__chart" role="img" aria-label="BARC model silage acre estimate with 95% range, by date">
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={rows} margin={{ top: 4, right: 16, bottom: 4, left: 4 }}>
          {grid}{x}
          <YAxis stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} width={60} label={yTitle('Silage acres', t.muted)} />
          {tip}
          <Area type="monotone" dataKey="lo" stackId="b" stroke="none" fill="transparent" isAnimationActive={false} legendType="none" tooltipType="none" />
          <Area type="monotone" dataKey="band" stackId="b" stroke="none" fill={DATA.silage} fillOpacity={0.14} isAnimationActive={false} name="95% range" tooltipType="none" />
          <Line type="monotone" dataKey="est" name="BARC silage acres (our model)" stroke={DATA.silage} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
          {legend}
        </ComposedChart>
      </ResponsiveContainer>
    </figure>
  )
}

function Kpi({ label, value, sub, foot }: { label: string; value: string; sub: string; foot: string }) {
  return (
    <article className="glass kpi">
      <h2 className="kpi__label">{label}</h2>
      <div className="kpi__value">{value}</div>
      <div className="kpi__sub">{sub}</div>
      <div className="kpi__foot">{foot}</div>
    </article>
  )
}
