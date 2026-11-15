import type { DeclineRuleBaseline, RuleMetrics } from '../api'
import { num } from '../format'
import type { AsyncState } from '../hooks'
import { Pending } from './Pending'

/** Held-out results by year (the saved model on each year's labeled rows); always grain scores 0.50 every year. */
export function PerYearPanel({ state }: { state: AsyncState<DeclineRuleBaseline> }) {
  if (state.error) return <Pending title="Per-year results">The saved per-year results are not available. {state.error.message}</Pending>
  if (!state.data) return <div className="skeleton skeleton--panel" />
  return (
    <>
      <div className="est__scroll">
        <table className="mini-table">
          <thead><tr><th>Year</th><th className="num">Field-years</th><th className="num">Balanced acc.</th><th className="num">Silage recall</th><th className="num">Silage precision</th><th className="num">Silage found</th></tr></thead>
          <tbody>
            {Object.entries(state.data.by_year).map(([year, { logistic: m }]) => (
              <tr key={year}>
                <td>{year}</td><td className="num">{m.n}</td><td className="num">{num(m.balanced_accuracy)}</td><td className="num">{num(m.silage_recall)}</td><td className="num">{num(m.silage_precision)}</td>
                <td className="num">{m.confusion_matrix[1]?.[1] ?? 0} of {(m.confusion_matrix[1] ?? []).reduce((a, b) => a + b, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">Always grain scores 0.50 balanced accuracy every year by construction. Few silage field-years per year, so single years swing widely.</p>
    </>
  )
}

/** Saved comparison: a simple "NDVI drops early = silage" rule vs the model and always-grain, on the same rows. */
export function DeclineRulePanel({ state }: { state: AsyncState<DeclineRuleBaseline> }) {
  if (state.error) return <Pending title="Decline-rule baseline">The saved comparison is not available. {state.error.message}</Pending>
  if (!state.data) return <div className="skeleton skeleton--panel" />
  const d = state.data
  const rows: [string, RuleMetrics][] = [
    [`Decline rule (NDVI drop of ${d.drop})`, d.decline_rule],
    ['Model, same rows', d.logistic_same_rows],
    ['Always grain', d.always_grain_same_rows],
  ]
  return (
    <>
      <div className="est__scroll">
        <table className="mini-table">
          <thead><tr><th>Method</th><th className="num">Balanced acc.</th><th className="num">Silage recall</th><th className="num">Silage precision</th><th className="num">False silage rate</th></tr></thead>
          <tbody>
            {rows.map(([name, m]) => (
              <tr key={name}><td>{name}</td><td className="num">{num(m.balanced_accuracy)}</td><td className="num">{num(m.silage_recall)}</td><td className="num">{num(m.silage_precision)}</td><td className="num">{num(m.false_positive_rate)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">{d.evaluated_field_years} field-years. {d.protocol}. {d.limitations[0] ?? ''}</p>
    </>
  )
}
