"""Offline checks for the Quick Stats backtest: pinned input, no 2025, 2026 not a final, a hand-checked revision."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import backtest as bt  # noqa: E402


class BacktestChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = bt.load()          # also verifies the committed CSV's sha256
        cls.res = bt.compute()

    def test_no_2025_rows(self):
        self.assertFalse((self.d['Year'] == 2025).any())
        self.assertEqual(sum(1 for line in bt.CSV.read_text(encoding='utf-8').splitlines() if line.startswith('"SURVEY","2025"')), 0)

    def test_2026_is_not_a_final(self):
        for item in (bt.GRAIN, bt.SILAGE):
            self.assertLessEqual(max(bt.finals(self.d, item).columns), 2024)
        p = bt.grain_panel(self.d)
        self.assertLessEqual(p['Year'].max(), 2024)
        # 2026 'YEAR' rows are the Nov 2026 forecast, which is why they are excluded
        g26 = self.d[(self.d['Year'] == 2026) & (self.d['Data Item'] == bt.GRAIN)]
        yr = g26[g26['Period'] == 'YEAR'].set_index('State')['acres']
        nov = g26[g26['Period'] == 'YEAR - NOV FORECAST'].set_index('State')['acres']
        common = yr.index.intersection(nov.index)
        self.assertGreater(len(common), 30)
        self.assertTrue((yr[common] == nov[common]).all())

    def test_hand_checked_maryland_2023(self):
        p = bt.grain_panel(self.d).set_index(['State', 'Year'])
        self.assertEqual(p.at[('MARYLAND', 2023), 'nov'], 420_000)
        self.assertEqual(p.at[('MARYLAND', 2023), 'final'], 440_000)
        self.assertAlmostEqual(p.at[('MARYLAND', 2023), 'rev_nov'], 20_000 / 420_000)
        md = {x['year']: x for x in self.res['maryland']}
        self.assertEqual(md[2023]['silage_final'], 30_000)
        self.assertEqual(md[2023]['grain_rev_nov'], round(20_000 / 420_000, 4))

    def test_aggregates_excluded_from_state_stats(self):
        n_states = self.res['grain']['pooled_2012_2024']['nov']['n']
        p = bt.grain_panel(self.d)
        self.assertNotIn('OTHER STATES', set(p['State']))
        self.assertEqual(n_states, int(p[(p['State'] != 'US TOTAL')]['nov'].notna().sum()))

    def test_silage_baselines_use_only_earlier_years(self):
        rows = self.res['silage']['maryland_rows']
        s = bt.finals(self.d, bt.SILAGE).loc['MARYLAND']
        for x in rows:
            t = x['year']
            self.assertEqual(x['persistence'], s[t - 1])
            self.assertEqual(x['mean3'], round((s[t - 1] + s[t - 2] + s[t - 3]) / 3))

    def test_forecast_constants_match_summary(self):
        s = json.loads((HERE.parents[1] / 'forecast' / 'outputs' / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(s['grain_revision_rel_sd'], bt.FORECAST['grain_revision_rel_sd'])
        self.assertEqual(s['interval_z']['grain'], bt.FORECAST['interval_z_grain'])
        self.assertEqual(s['backtest']['silage']['median_abs_pct_error'], bt.FORECAST['silage_backtest']['median_abs_pct_error'])
        self.assertEqual(s['backtest']['silage']['mean_abs_pct_error'], bt.FORECAST['silage_backtest']['mean_abs_pct_error'])
        self.assertEqual(s['silage_method']['backtest_acre_weighted_abs_pct_error']['D'],
                         bt.FORECAST['silage_backtest']['acre_weighted_abs_pct_error']['D'])

    def test_committed_outputs_are_current(self):
        committed = json.loads((bt.OUT / 'backtest.json').read_text(encoding='utf-8'))
        self.assertEqual(committed, json.loads(json.dumps(self.res)))


if __name__ == '__main__':
    unittest.main()
