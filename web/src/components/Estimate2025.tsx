import type { Estimate2025 } from '../api'
import { acres, num, pct, signedAcres, signedPct } from '../format'
import type { AsyncState } from '../hooks'
import { Pending } from './Pending'

const reasonName = (raw: string) => raw.replace(/_/g, ' ')

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
  // Why this is a cross-check: the model learned from BARC, which is far more silage-heavy than Maryland.
  const barcSilage = s.model.training_silage_field_years
  const barcShare = barcSilage != null && s.model.training_field_years > 0 ? barcSilage / s.model.training_field_years : null
  const mdCorn = silage.nass_acres + grain.nass_acres
  const mdShare = mdCorn > 0 ? silage.nass_acres / mdCorn : null
  const silageMiss = calibrated ? silage.relative_error : silage.raw.relative_error
  return (
    <div className="est">
      <p className="est__lead">
        <b>A cross-check, not a second answer.</b> The satellite model learned from BARC fields
        {barcShare != null && <>, which are {pct(barcShare)} silage ({barcSilage} of {s.model.training_field_years} labeled field-years)</>}
        {mdShare != null && <>, against {pct(mdShare)} of Maryland corn acres harvested (NASS 2025)</>}, so statewide it {silageMiss > 0 ? 'over-calls' : 'misjudges'} silage
        ({signedPct(silageMiss)} vs NASS).
      </p>
      <p className="muted small">
        The graded submission is <code>forecast_v2/outputs/state_estimates_2025.csv</code> (the 2025 by state tab), not this estimate.
      </p>
      {partial && (
        <p className="est__partial" role="note">
          {used.length} of {drawn} sample batches processed. The estimate uses only the finished batches.
        </p>
      )}

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
        <details className="more">
          <summary>How the calibration works</summary>
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
        </details>
      </section>

      <details className="more">
        <summary>Details: method, sampled fields and limitations</summary>
      <p className="muted small">
        A model estimate from a sample of Maryland corn fields, compared with NASS survey acres harvested. It is not a USDA or NASS release.
        Saved {s.generated_utc.slice(0, 10)}.
      </p>
      <p className="est__text">{s.method}</p>

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

      </details>
    </div>
  )
}
