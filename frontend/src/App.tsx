import { useEffect, useState } from 'react';
import { loadBaseline, type Metrics } from './api';

const percent = (value: number | null) => value === null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`;
const metrics: [string, keyof Pick<Metrics, 'silage_precision' | 'silage_recall' | 'silage_f1' | 'false_positive_rate' | 'balanced_accuracy'>][] = [
  ['Silage precision', 'silage_precision'],
  ['Silage recall', 'silage_recall'],
  ['Silage F1', 'silage_f1'],
  ['False positive rate', 'false_positive_rate'],
  ['Balanced accuracy', 'balanced_accuracy'],
];

export default function App() {
  const [data, setData] = useState<Awaited<ReturnType<typeof loadBaseline>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    loadBaseline(controller.signal).then(setData).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Could not load results.');
    });
    return () => controller.abort();
  }, []);

  return <main>
    <header>
      <p className="eyebrow">BARC · Maryland · 2021–2023</p>
      <h1>Hack the Harvest</h1>
      <p>Exploring whether satellite vegetation patterns can distinguish corn harvested for silage or grain.</p>
    </header>
    {error ? <section role="alert"><h2>Results unavailable</h2><p>{error} Check that the backend is running and saved baseline outputs are present.</p></section>
      : !data ? <p role="status">Loading saved baseline results…</p>
      : <>
        <section>
          <h2>Logistic regression baseline</h2>
          <p>{data.summary.evaluated_field_years} labeled field-years across {data.summary.evaluated_fields} fields. Predictions come from five-fold validation that keeps all years of each field together.</p>
          <div className="table-scroll"><table>
            <caption>Held-out performance; Silage is the positive class</caption>
            <thead><tr><th scope="col">Metric</th><th scope="col">Logistic regression</th><th scope="col">Always Grain</th></tr></thead>
            <tbody>{metrics.map(([name, key]) => <tr key={key}><th scope="row">{name}</th><td>{percent(data.summary.logistic[key])}</td><td>{percent(data.summary.always_grain[key])}</td></tr>)}</tbody>
          </table></div>
          <p className="note">Always-Grain precision is reported as zero by convention because it makes no Silage predictions. These results describe a small, single-site dataset.</p>
        </section>
        <section>
          <h2>Confusion matrix</h2>
          <div className="table-scroll"><table>
            <caption>Logistic regression: reference labels in rows, predictions in columns</caption>
            <thead><tr><th scope="col">Reference label</th>{data.summary.logistic.matrix_order.map(label => <th scope="col" key={label}>Predicted {label}</th>)}</tr></thead>
            <tbody>{data.summary.logistic.matrix_order.map((label, i) => <tr key={label}><th scope="row">{label}</th>{data.summary.logistic.confusion_matrix[i].map((count, j) => <td key={j}>{count}</td>)}</tr>)}</tbody>
          </table></div>
        </section>
        <section>
          <h2>Observation quality</h2>
          <p>{data.summary.cloud_or_nodata_rejections} field-scene observations rejected for insufficient clear pixels; {data.summary.read_errors} read failures; {data.summary.excluded_field_years} field-years excluded for no usable observations.</p>
          <p>{Object.values(data.summary.missing_feature_counts).reduce((sum, count) => sum + count, 0)} missing final feature values. Blank source labels are excluded from supervised training.</p>
        </section>
        <section>
          <h2>Held-out field predictions</h2>
          <p>Silage probability is a model estimate, not proof of harvest type. Reference labels come from the supplied BARC dataset.</p>
          <div className="table-scroll"><table>
            <caption>One row per labeled field-year</caption>
            <thead><tr>{['Field ID', 'Year', 'Reference', 'Prediction', 'Silage probability', 'Clear dates', 'Fold'].map(name => <th scope="col" key={name}>{name}</th>)}</tr></thead>
            <tbody>{data.predictions.map(row => <tr key={`${row.field_id}-${row.year}`}>
              <th scope="row">{row.field_id}</th><td>{row.year}</td><td>{row.reference_label}</td><td>{row.predicted_label}</td><td>{percent(row.silage_probability)}</td><td>{row.valid_dates}</td><td>{row.fold}</td>
            </tr>)}</tbody>
          </table></div>
        </section>
      </>}
  </main>;
}
