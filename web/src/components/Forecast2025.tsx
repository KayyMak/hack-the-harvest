import type { Forecast2025, ForecastCrop } from '../api'
import { acres, pct, signedAcres, signedPct } from '../format'
import type { AsyncState } from '../hooks'
import { Pending } from './Pending'

/** "2023–24" from the saved backtest years; empty when the forecast did not save them. */
const backtestSpan = (years: string[]) =>
  years.length === 0 ? '' : years.length === 1 ? years[0] : `${years[0]}–${years.at(-1)!.slice(-2)}`

const range = (c: ForecastCrop) => (c.low != null && c.high != null ? `${acres(c.low)}–${acres(c.high)}` : 'not published')

/** The Overview's first row: the graded 2025 Maryland forecast next to NASS 2025 acres harvested. */
export function ForecastCards({ state }: { state: AsyncState<Forecast2025> }) {
  if (state.error) {
    return (
      <section className="kpis kpis--headline" aria-label="Maryland 2025 forecast">
        <article className="glass kpi kpi--wide">
          <Pending title="Maryland 2025 silage and grain acres, forecast">
            The saved 2025 forecast is not available, so no number is shown. {state.error.message}
          </Pending>
        </article>
      </section>
    )
  }
  const data = state.data
  const span = data ? backtestSpan(data.backtest_years) : ''
  return (
    <section className="kpis kpis--headline" aria-label="Maryland 2025 forecast">
      {(['silage', 'grain'] as const).map((crop) => {
        const c = data?.maryland[crop]
        return (
          <article className="glass kpi" key={crop}>
            <h2 className="kpi__label">Maryland 2025 {crop} acres, forecast</h2>
            {!data || !c ? (
              <div className="skeleton skeleton--chart kpi__skeleton" />
            ) : (
              <>
                <div className="kpi__value">{acres(c.value)}</div>
                <div className="kpi__sub">95% range {range(c)}</div>
                <div className="kpi__foot">
                  {c.nass == null || c.error == null || c.relative_error == null ? (
                    'NASS 2025 comparison unavailable'
                  ) : (
                    <>
                      NASS 2025: {acres(c.nass)} <span className="kpi__err">Error {signedAcres(c.error)} acres ({signedPct(c.relative_error)})</span>
                    </>
                  )}
                </div>
                <div className="kpi__foot kpi__note">
                  From NASS reports published before Jan 2026{span ? `; backtested ${span}` : ''}
                </div>
              </>
            )}
          </article>
        )
      })}
    </section>
  )
}

/** Model quality section for the graded 2025 forecast: method, backtest, Maryland and US, sources. */
export function Forecast2025Panel({ state }: { state: AsyncState<Forecast2025> }) {
  if (state.error) {
    return (
      <Pending title="2025 forecast">
        The saved 2025 forecast is not available, so nothing is shown here. {state.error.message}
      </Pending>
    )
  }
  if (!state.data) return <div className="skeleton skeleton--panel" />
  const { summary: s, maryland, us } = state.data
  const rows = [
    { name: 'Maryland, silage', c: maryland.silage },
    { name: 'Maryland, grain', c: maryland.grain },
    { name: 'US, silage', c: us.silage },
    { name: 'US, grain', c: us.grain },
  ]
  return (
    <div className="est">
      <p className="muted small">
        The graded 2025 output: harvested acres forecast from NASS reports published before January 2026, compared with NASS 2025 survey acres harvested.
      </p>
      <p className="est__text">{s.method}</p>
      <p className="est__partial" role="note">{s.answer_key_excluded}</p>

      <section className="block">
        <div className="block__head">
          <h3>Maryland and US, 2025</h3>
          <span className="block__note">error = forecast − NASS</span>
        </div>
        <div className="est__scroll">
          <table className="mini-table">
            <thead>
              <tr>
                <th>Forecast</th>
                <th className="num">Acres</th>
                <th className="num">95% range</th>
                <th className="num">NASS 2025<span className="est__sm-only"> and error</span></th>
                <th className="num est__lg-only">Error</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ name, c }) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td className="num">{acres(c.value)}</td>
                  <td className="num est__range">
                    {c.low != null && c.high != null ? <>{acres(c.low)}–<wbr />{acres(c.high)}</> : 'not published'}
                  </td>
                  <td className="num">
                    {c.nass == null ? '—' : acres(c.nass)}
                    {c.error != null && c.relative_error != null && (
                      <span className="est__sm-only">
                        {signedAcres(c.error)} <span className="muted est__pct">({signedPct(c.relative_error)})</span>
                      </span>
                    )}
                  </td>
                  <td className="num est__lg-only">
                    {c.error == null || c.relative_error == null ? '—' : (
                      <>
                        {signedAcres(c.error)} <span className="muted est__pct">({signedPct(c.relative_error)})</span>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          {state.data.nass_source ? `${state.data.nass_source}; used only for this comparison, never as a forecast input.` : 'NASS 2025 reference acres could not be read, so no error is shown.'} The US grain forecast has no published range.
        </p>
      </section>

      <section className="block">
        <div className="block__head">
          <h3>Backtest on earlier years</h3>
          <span className="block__note">state-years forecast the same way, scored against NASS finals</span>
        </div>
        <div className="est__scroll">
          <table className="mini-table">
            <thead>
              <tr>
                <th>Crop</th>
                <th className="num">State-years</th>
                <th className="num">Median abs. error</th>
                <th className="num">Mean abs. error</th>
                <th className="num">Inside 95% range</th>
              </tr>
            </thead>
            <tbody>
              {(['silage', 'grain'] as const).map((crop) => {
                const b = s.backtest[crop]
                return (
                  <tr key={crop}>
                    <td>{crop === 'silage' ? 'Silage' : 'Grain'}</td>
                    <td className="num">{b.state_years}</td>
                    <td className="num">{b.median_abs_pct_error.toFixed(1)}%</td>
                    <td className="num">{b.mean_abs_pct_error.toFixed(1)}%</td>
                    <td className="num">{pct(b.covered_by_95_interval, 1)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          These are the forecast's own backtest figures. A longer, independent check over 2012–2024 (analysis/forecast_backtest)
          found the grain range holds up for large states but is too narrow for small ones, and that states without a November
          report were scored against their final value in this backtest, which flatters the grain row.
        </p>
      </section>

      <section className="block">
        <div className="block__head">
          <h3>Sources</h3>
        </div>
        <ul className="est__list">
          {Object.entries(s.sources).map(([id, src]) => (
            <li key={id}>
              <a href={src.url} target="_blank" rel="noreferrer">{src.title}</a>{' '}
              <span className="muted">{src.released ? `released ${src.released}` : 'release date not recorded'}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
