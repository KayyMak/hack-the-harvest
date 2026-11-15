import type { DeclineRuleBaseline, RuleMetrics } from '../api'
import { num } from '../format'
import type { AsyncState } from '../hooks'
import { Pending } from './Pending'

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
