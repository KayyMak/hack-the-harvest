"""Offline checks for the 2025 estimate: parsing, leakage guard, output format, honest intervals."""
import csv
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import estimate_2025 as est  # noqa: E402


class ForecastChecks(unittest.TestCase):
    def test_every_table_has_every_corn_state(self):
        for name in ('cropan23', 'cropan24', 'cropan25'):
            text = est.fetch(name)
            pg = est.table(text, 'Corn Area Planted for All Purposes and Harvested for Grain', 'Area planted')
            sil = est.table(text, 'Corn for Silage Area Harvested', 'Area harvested')
            self.assertEqual(set(pg), set(sil), name)
            self.assertGreaterEqual(len(pg), 49, name)
        for name in ('acrg0625', 'crop0825', 'crop0925'):
            self.assertGreaterEqual(len(est.planted_grain_report(name)), 49, name)

    def test_known_values_match_the_printed_reports(self):
        sep = est.planted_grain_report('crop0925')
        self.assertEqual(sep['MARYLAND'], {'planted': 460000.0, 'grain': 405000.0})
        sil = est.table(est.fetch('cropan25'), 'Corn for Silage Area Harvested', 'Area harvested')
        self.assertEqual(sil['NORTH CAROLINA'][:3], [30.0, 30.0, 20.0])

    def test_answer_key_is_never_used(self):
        with self.assertRaises(RuntimeError):
            est.fetch('cropan26')
        released = [v['released'] for v in est.SOURCES['reports'].values() if v.get('released')]
        self.assertTrue(all('2026' not in r for r in released))

    def test_outputs_are_benchmark_ready_and_intervals_are_honest(self):
        est.main()
        rows = list(csv.DictReader((HERE / 'outputs/state_estimates_2025.csv').open(encoding='utf-8')))
        self.assertEqual(set(rows[0]), {'Year', 'Geo Level', 'State', 'Data Item', 'Domain', 'Value'})
        self.assertTrue(all(r['Year'] == '2025' and r['Domain'] == 'TOTAL' for r in rows))
        summary = json.loads((HERE / 'outputs/summary.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(summary['backtest']['silage']['covered_by_95_interval'], 0.95)
        self.assertGreaterEqual(summary['backtest']['grain']['covered_by_95_interval'], 0.95)
        m = summary['silage_method']
        self.assertEqual(m['chosen'], min(m['backtest_acre_weighted_abs_pct_error'], key=m['backtest_acre_weighted_abs_pct_error'].get))


if __name__ == '__main__':
    unittest.main()
