import type { Estimate2025 } from '../api'
import { acres, pct, signedPct } from '../format'
import type { AsyncState } from '../hooks'
import { Pending } from './Pending'

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
        <b>A cross-check, not our answer.</b> Applied to {acres(s.sample.scored_fields)} sampled Maryland corn fields, the
        BARC-trained model {silageMiss > 0 ? 'over-calls' : 'misjudges'} silage by {signedPct(silageMiss)}
        {barcShare != null && mdShare != null && <>: BARC is {pct(barcShare)} silage, Maryland corn {pct(mdShare)}</>}.
      </p>
      {partial && (
        <p className="est__partial" role="note">
          {used.length} of {drawn} sample batches processed. The estimate uses only the finished batches.
        </p>
      )}
      <div className="est__scroll">
        <table className="mini-table">
          <thead>
            <tr>
              <th>Maryland 2025</th>
              <th className="num">Ours</th>
              <th className="num">95% range</th>
              <th className="num">NASS</th>
              <th className="num">Error</th>
            </tr>
          </thead>
          <tbody>
            {rows.filter((r) => r.headline).map((r) => (
              <tr key={r.name}>
                <td>{r.name.split(',')[0]}</td>
                <td className="num">{acres(r.acres)}</td>
                <td className="num est__range">{acres(r.ci[0])}–<wbr />{acres(r.ci[1])}</td>
                <td className="num">{acres(r.nass)}</td>
                <td className="num">{signedPct(r.rel)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="more">
        <summary>Method and limits</summary>
        <p className="est__text">{s.method}</p>
        {calibrated && s.calibrated && <p className="muted small">{s.calibrated.method}</p>}
        <ul className="est__list">
          {s.limitations.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      </details>
    </div>
  )
}
