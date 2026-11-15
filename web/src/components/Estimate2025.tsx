import type { Estimate2025, EstimateCrop } from '../api'
import { acres, num, pct, signedAcres, signedPct } from '../format'
import type { AsyncState } from '../hooks'
import { Pending } from './Pending'

const reasonName = (raw: string) => raw.replace(/_/g, ' ')

/** Two headline cards for the Overview: our 2025 Maryland silage and grain acres next to NASS. */
export function EstimateCards({ state }: { state: AsyncState<Estimate2025> }) {
  if (state.error) {
    return (
      <section className="kpis kpis--estimate" aria-label="Maryland 2025 estimate">
        <article className="glass kpi kpi--wide">
          <Pending title="Maryland 2025 silage and grain acres">
            The saved 2025 estimate is not available, so no number is shown. {state.error.message}
          </Pending>
        </article>
      </section>
    )
  }
  const data = state.data
  const scored = data?.summary.sample.scored_fields
  return (
    <section className="kpis kpis--estimate" aria-label="Maryland 2025 estimate">
      {(['silage', 'grain'] as const).map((crop) => {
        const c: EstimateCrop | undefined = data?.[crop]
        return (
          <article className="glass kpi" key={crop}>
            <h2 className="kpi__label">Maryland 2025 {crop} acres, model estimate</h2>
            {!data || !c ? (
              <div className="skeleton skeleton--chart kpi__skeleton" />
            ) : (
              <>
                <div className="kpi__value">{acres(c.acres)}</div>
                <div className="kpi__sub">
                  95% range {acres(c.ci[0])}–{acres(c.ci[1])}, from {acres(scored ?? 0)} sampled fields
                </div>
                <div className="kpi__foot">
                  NASS 2025: {acres(c.nass_acres)} <span className="kpi__err">Error {signedAcres(c.error)} acres ({signedPct(c.relative_error)})</span>
                </div>
                <div className="kpi__foot kpi__raw">
                  {data.calibrated
                    ? `Raw (uncalibrated): ${acres(c.raw.acres)}, ${signedPct(c.raw.relative_error)} vs NASS`
                    : 'Raw (uncalibrated) estimate; calibration is unavailable for this run.'}
                </div>
              </>
            )}
          </article>
        )
      })}
    </section>
  )
}

/** Model quality section: how the 2025 Maryland estimate was made and how it compares with NASS. */
export function Estimate2025Panel({ state }: { state: AsyncState<Estimate2025> }) {
  if (state.error) {
    return (
      <Pending title="2025 Maryland estimate">
        The saved 2025 estimate is not available, so nothing is shown here. {state.error.message}
      </Pending>
    )
  }
  if (!state.data) return <div className="skeleton skeleton--panel" />
  const { summary: s, calibrated, silage, grain } = state.data
  const rows: { name: string; acres: number; ci: [number, number]; nass: number; error: number; rel: number; headline: boolean }[] = []
  for (const [label, c] of [['Silage', silage], ['Grain', grain]] as const) {
    if (calibrated) rows.push({ name: `${label}, calibrated`, acres: c.acres, ci: c.ci, nass: c.nass_acres, error: c.error, rel: c.relative_error, headline: true })
    rows.push({ name: `${label}, raw`, acres: c.raw.acres, ci: c.raw.ci, nass: c.nass_acres, error: c.raw.error, rel: c.raw.relative_error, headline: !calibrated })
  }
  const reasons = Object.entries(s.sample.skipped_reasons)
  const { batches_used: used, batches_drawn: drawn } = s.sample
  const partial = used != null && drawn != null && used.length < drawn
  return (
    <div className="est">
      <p className="muted small">
        A model estimate from a sample of Maryland corn fields, compared with NASS survey acres harvested. It is not a USDA or NASS release.
        Saved {s.generated_utc.slice(0, 10)}.
      </p>
      {partial && (
        <p className="est__partial" role="note">
          {used.length} of {drawn} sample batches processed. The estimate uses only the finished batches.
        </p>
      )}
      <p className="est__text">{s.method}</p>

      <section className="block">
        <div className="block__head">
          <h3>Estimate and NASS 2025</h3>
          <span className="block__note">error = our estimate − NASS</span>
        </div>
        <div className="est__scroll">
          <table className="mini-table">
            <thead>
              <tr>
                <th>Estimate</th>
                <th className="num">Acres</th>
                <th className="num">95% range</th>
                <th className="num">NASS 2025</th>
                <th className="num">Error</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name} className={r.headline ? 'est__headline' : undefined}>
                  <td>{r.name}</td>
                  <td className="num">{acres(r.acres)}</td>
                  <td className="num est__range">{acres(r.ci[0])}–<wbr />{acres(r.ci[1])}</td>
                  <td className="num">{acres(r.nass)}</td>
                  <td className="num">
                    {signedAcres(r.error)} <span className="muted est__pct">({signedPct(r.rel)})</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {s.calibrated ? (
          <p className="muted small">
            Calibrated rows are the headline. {s.calibrated.method}
            {s.calibrated.tpr != null && s.calibrated.fpr != null && ` Silage detection rate ${num(s.calibrated.tpr)}, false silage rate ${num(s.calibrated.fpr)}.`}
            {s.calibrated.predicted_silage_acre_share != null && ` Share of scored acres called silage before adjustment: ${pct(s.calibrated.predicted_silage_acre_share, 1)}.`}
            {s.calibrated.undefined_bootstrap_draws != null && s.calibrated.undefined_bootstrap_draws > 0 && ` ${acres(s.calibrated.undefined_bootstrap_draws)} resampling draws had no defined adjustment and are left out of the range.`}
          </p>
        ) : (
          <p className="muted small">Calibration is unavailable for this run, so the raw (uncalibrated) estimate is the headline.</p>
        )}
        <p className="muted small">NASS 2025: {s.nass_2025.source}</p>
      </section>

      <section className="block">
        <div className="block__head">
          <h3>Fields behind the estimate</h3>
          <span className="block__note">{s.population.source}</span>
        </div>
        <div className="est__scroll">
          <table className="mini-table est__facts">
            <tbody>
              <tr>
                <td>Maryland field boundaries</td>
                <td className="num">{acres(s.population.csb_fields_maryland)}</td>
              </tr>
              <tr>
                <td>Corn fields, 2025</td>
                <td className="num">{acres(s.population.corn_fields_2025)}</td>
              </tr>
              <tr>
                <td>Corn acres, 2025</td>
                <td className="num">{acres(s.population.corn_acres_2025)}</td>
              </tr>
              {s.population.cdl_corn_acres_2025 != null && (
                <tr>
                  <td>Corn acres in the 2025 Cropland Data Layer, all pixels</td>
                  <td className="num">{acres(s.population.cdl_corn_acres_2025)}</td>
                </tr>
              )}
              <tr>
                <td>Fields sampled (by {s.sample.stratified_by}, seed {s.sample.seed})</td>
                <td className="num">
                  {acres(s.sample.sampled_fields)} <span className="muted">(of {acres(s.sample.requested_fields)} requested, {acres(s.sample.sampled_acres)} acres)</span>
                </td>
              </tr>
              <tr>
                <td>Fields scored</td>
                <td className="num">
                  {acres(s.sample.scored_fields)} <span className="muted">({acres(s.sample.scored_acres)} acres)</span>
                </td>
              </tr>
              {s.model.sample_fields_called_silage != null && (
                <tr>
                  <td>Scored fields called silage</td>
                  <td className="num">{acres(s.model.sample_fields_called_silage)}</td>
                </tr>
              )}
              <tr>
                <td>Fields skipped, not scored</td>
                <td className="num">
                  {acres(s.sample.skipped_fields)}
                  {reasons.length > 0 && <span className="muted"> ({reasons.map(([k, v]) => `${reasonName(k)}: ${acres(v)}`).join(', ')})</span>}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="muted small">
          Corn rule: {s.population.corn_rule} A field needs at least {s.sample.min_valid_dates} clear satellite dates to be scored.
        </p>
        <p className="muted small">
          Model: {s.model.name}, trained on {s.model.training_field_years} labeled field-years{s.model.training_silage_field_years != null && ` (${s.model.training_silage_field_years} silage)`}; silage is called at probability {num(s.model.threshold)} or higher. Features: {s.model.features.join(', ')}.
        </p>
      </section>

      <section className="block">
        <div className="block__head">
          <h3>Limitations</h3>
        </div>
        <ul className="est__list">
          {s.limitations.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      </section>

      <section className="block">
        <div className="block__head">
          <h3>Sources</h3>
        </div>
        <ul className="est__list">
          {s.sources.map((src) => (
            <li key={`${src.name}-${src.url}`}>
              <a href={src.url} target="_blank" rel="noreferrer">{src.name}</a> <span className="muted">accessed {src.accessed}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
