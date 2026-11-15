"""Reconstruct held-out decisions and plot cached observations. No network calls."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from run_baseline import FEATURES, build_model, verify_originals

INPUT = HERE / 'outputs'
OUT = INPUT / 'diagnostics' / 'field_323_and_327'
CASES = [(323, 2023), (327, 2021)]


def main():
    verify_originals()
    OUT.mkdir(parents=True, exist_ok=True)
    features = pd.read_csv(INPUT / 'features.csv')
    predictions = pd.read_csv(INPUT / 'heldout_predictions.csv')
    observations = pd.read_csv(INPUT / 'observations.csv')
    metadata = json.loads((INPUT / 'metrics.json').read_text())
    assert metadata['features'] == FEATURES
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), layout='constrained')
    summaries, contribution_tables, daily_tables = [], [], []
    provenance = {name: hashlib.sha256((INPUT / name).read_bytes()).hexdigest()
                  for name in ['features.csv', 'heldout_predictions.csv', 'metrics.json', 'observations.csv']}
    for column, (field_id, year) in enumerate(CASES):
        saved = predictions[(predictions.OBJECTID == field_id) & (predictions.year == year)].iloc[0]
        target = features[(features.OBJECTID == field_id) & (features.year == year)]
        split = next(f for f in metadata['folds'] if f['fold'] == int(saved.fold))
        train = features[features.OBJECTID.isin(split['training_fields'])]
        test = features[features.OBJECTID.isin(split['test_fields'])]
        assert not set(train.OBJECTID) & set(test.OBJECTID)
        assert field_id not in set(train.OBJECTID)
        model = build_model()
        model.fit(train[FEATURES], train.label.eq('Silage').astype(int))
        expected = predictions.set_index(['OBJECTID', 'year']).loc[
            list(zip(test.OBJECTID, test.year)), 'silage_probability'].to_numpy()
        np.testing.assert_allclose(model.predict_proba(test[FEATURES])[:, 1], expected, rtol=0, atol=1e-10)
        standardized = model[:-1].transform(target[FEATURES])[0]
        contributions = standardized * model[-1].coef_[0]
        intercept = float(model[-1].intercept_[0])
        logit = float(model.decision_function(target[FEATURES])[0])
        np.testing.assert_allclose(intercept + contributions.sum(), logit, rtol=0, atol=1e-12)
        probability = float(model.predict_proba(target[FEATURES])[0, 1])
        explanation = pd.DataFrame(dict(OBJECTID=field_id, year=year, feature=FEATURES,
            raw_value=target[FEATURES].iloc[0].values,
            training_mean=model[1].mean_, training_scale=model[1].scale_,
            standardized_value=standardized, coefficient=model[-1].coef_[0],
            log_odds_contribution=contributions,
            training_grain_median=train[train.label.eq('Grain')][FEATURES].median().values,
            training_silage_median=train[train.label.eq('Silage')][FEATURES].median().values))
        contribution_tables.append(explanation)

        obs = observations[(observations.OBJECTID == field_id) & (observations.year == year)].copy()
        valid = obs[obs.status.eq('ok')]
        daily = valid.groupby('date', as_index=False).agg(ndvi=('ndvi', 'median'),
            clear_fraction=('clear_fraction', 'median'), scene_entries=('ndvi', 'size'))
        daily['date'] = pd.to_datetime(daily.date)
        daily['gap_from_previous_days'] = daily.date.diff().dt.days
        daily['OBJECTID'], daily['year'] = field_id, year
        assert len(daily) == int(saved.valid_dates)
        daily_tables.append(daily)
        month_counts = {str(m): int(daily.date.dt.month.eq(m).sum()) for m in range(7, 12)}
        gaps = [dict(start=daily.iloc[i-1].date.date().isoformat(),
                     end=daily.iloc[i].date.date().isoformat(), days=int(gap))
                for i, gap in enumerate(daily.gap_from_previous_days) if pd.notna(gap) and gap > 14]
        response_path = INPUT / 'nemotron' / 'responses' / f'{field_id}_{year}.json'
        provenance[f'nemotron/responses/{field_id}_{year}.json'] = hashlib.sha256(response_path.read_bytes()).hexdigest()
        nemotron = json.loads(response_path.read_text())
        assert nemotron['status'] == 'ok' and field_id not in nemotron['training_fields']
        prompt_input = json.loads(nemotron['request']['messages'][1]['content'])['field_to_classify']
        np.testing.assert_allclose([prompt_input[f] for f in FEATURES], target[FEATURES].iloc[0].values)
        summary = dict(field_id=field_id, year=year, fold=int(saved.fold), reference_label=saved.label,
            logistic_prediction=saved.predicted_label, logistic_silage_probability=probability,
            nemotron_prediction=nemotron['predicted_label'], nemotron_raw_response=nemotron['raw_response'],
            logistic_intercept=intercept, logistic_logit=logit,
            usable_dates=len(daily), usable_dates_by_month=month_counts,
            rejected_scenes=int(obs.status.eq('insufficient_clear_pixels').sum()),
            read_errors=int(obs.status.eq('read_error').sum()), gaps_over_14_days=gaps)
        summaries.append(summary)

        ax = axes[0, column]
        for i in range(1, len(daily)):
            a, b = daily.iloc[i-1], daily.iloc[i]
            ax.plot([a.date, b.date], [a.ndvi, b.ndvi], color='#245a81',
                    linestyle='--' if (b.date-a.date).days > 14 else '-', linewidth=1.7)
        ax.scatter(daily.date, daily.ndvi, color='#245a81', s=35, zorder=3)
        low = daily[daily.clear_fraction < 0.3]
        ax.scatter(low.date, low.ndvi, facecolors='none', edgecolors='#b45c00', s=110, linewidths=1.8, zorder=4)
        rejected = pd.to_datetime(obs.loc[obs.status.ne('ok'), 'date'].unique())
        ax.scatter(rejected, [-0.06]*len(rejected), marker='x', color='#777777', s=35)
        for gap in gaps:
            start, end = pd.Timestamp(gap['start']), pd.Timestamp(gap['end'])
            ax.axvspan(start, end, color='#b3b3b3', alpha=0.12)
            ax.text(start+(end-start)/2, 0.04, f'{gap["days"]}d gap', ha='center', va='bottom', fontsize=8)
        ax.set(title=f'Field {field_id} / {year} | Reference: Silage\n'
            f'LR: {saved.predicted_label} ({probability:.1%} Silage) | Nemotron: {nemotron["predicted_label"]}',
            ylabel='Field median NDVI', ylim=(-0.1, 1),
            xlim=(pd.Timestamp(year=year, month=7, day=1), pd.Timestamp(year=year, month=12, day=1)))
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        ax.grid(alpha=0.2)

        ax = axes[1, column]
        bars = explanation[['feature', 'log_odds_contribution']].copy()
        bars.loc[len(bars)] = ['intercept (mean features)', intercept]
        bars = bars.sort_values('log_odds_contribution')
        colors = ['#777777' if f.startswith('intercept') else '#b54a3a' if v < 0 else '#238565'
                  for f, v in bars.itertuples(index=False, name=None)]
        ax.barh(bars.feature, bars.log_odds_contribution, color=colors)
        ax.axvline(0, color='#333333', linewidth=0.8)
        ax.set(title=f'Exact held-out LR decomposition (fold {int(saved.fold)})',
               xlabel='Log-odds contribution: negative favors Grain; positive favors Silage')
        ax.grid(axis='x', alpha=0.2)
    fig.suptitle('Two Silage field-years: observed trajectories and reconstructed logistic decisions', fontsize=16)
    limit = 1.1 * max(abs(s['logistic_intercept']) for s in summaries)
    limit = max(limit, 1.1 * max(abs(t.log_odds_contribution).max() for t in contribution_tables))
    for ax in axes[1]:
        ax.set_xlim(-limit, limit)
    fig.legend(handles=[Line2D([], [], color='#245a81', marker='o', label='Usable daily median'),
        Line2D([], [], color='#245a81', linestyle='--', label='Gap >14 days; timing unresolved'),
        Line2D([], [], color='#777777', marker='x', linestyle='', label='Rejected scene; NDVI unknown'),
        Line2D([], [], marker='o', markerfacecolor='none', markeredgecolor='#b45c00', linestyle='',
               label='Accepted day with <30% median clear coverage')], fontsize=9,
               loc='outside lower center', ncols=2)
    fig.savefig(OUT / 'comparison.png', dpi=180)
    fig.savefig(OUT / 'comparison.svg')
    plt.close(fig)
    pd.concat(contribution_tables).to_csv(OUT / 'feature_contributions.csv', index=False)
    pd.concat(daily_tables).to_csv(OUT / 'daily_observations.csv', index=False)
    (OUT / 'summary.json').write_text(json.dumps(dict(cases=summaries, input_sha256=provenance,
        checks=['Held-out field absent from training', 'All predictions in reconstructed folds match saved probabilities',
                'Intercept plus feature contributions equals saved decision logit',
                'Nemotron target inputs match logistic raw features']), indent=2), encoding='utf-8')
    verify_originals()
    print(f'Saved verified offline diagnostics to {OUT}')
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
