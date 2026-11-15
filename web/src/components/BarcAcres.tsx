import type { BarcRollupYear } from '../api'
import { acres } from '../format'

const ac = (x: number) => acres(Math.round(x * 10) / 10)

/** Silage acres on BARC's own labeled fields: the model's estimate next to BARC's labels. Not statewide. */
export function BarcAcres({ data }: { data: BarcRollupYear }) {
  const [lo, hi] = data.ci
  const inside = data.labeled_silage_acres >= lo && data.labeled_silage_acres <= hi
  return (
    <div className="barc">
      <p className="barc__scope">
        BARC's labeled fields only, {data.field_years} field-years and {ac(data.total_acres)} acres of corn in {data.year}. This checks the
        acre math on fields with known answers; it is not a statewide estimate.
      </p>
      <div className="tiles barc__tiles">
        <div className="tile">
          <div className="tile__kicker">BARC labeled silage</div>
          <div className="tile__value">{ac(data.labeled_silage_acres)} ac</div>
          <div className="tile__sub">reference</div>
        </div>
        <div className="tile">
          <div className="tile__kicker">Model estimate</div>
          <div className="tile__value">{ac(data.expected_silage_acres)} ac</div>
          <div className="tile__sub">
            95% range {ac(lo)}–{ac(hi)}
            {data.cv_pct != null ? `, CV ${data.cv_pct.toFixed(0)}%` : ''}
          </div>
        </div>
        {data.adjusted_silage_acres != null && (
          <div className="tile">
            <div className="tile__kicker">Adjusted for misses</div>
            <div className="tile__value">{ac(data.adjusted_silage_acres)} ac</div>
            <div className="tile__sub">corrects for silage the model tends to miss</div>
          </div>
        )}
      </div>
      <p className={`barc__verdict ${inside ? 'is-ok' : 'is-off'}`}>
        {inside ? 'BARC’s labeled acres fall inside the model’s 95% range.' : 'BARC’s labeled acres fall outside the model’s 95% range.'}
      </p>
    </div>
  )
}
