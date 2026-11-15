"""Offline checks for forecast_v2: no answer-key rows, no look-ahead in the backtest, graded-row coverage.

    python -m unittest forecast_v2/test_forecast_v2.py      (from the repo root)
"""
import csv
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import backtest as bt  # noqa: E402
import estimate_2025 as est  # noqa: E402
from common import FC1, HARVESTED_CSV, PLANTED_CSV, SIMPLICITY, load_quickstats, silage_candidates  # noqa: E402

FINALS, INSEASON = load_quickstats()


def scrambled(finals, t):
    """Every final for year >= t multiplied by an odd factor: a forecast for t must not move."""
    return {k: ({kk: (vv * 1.37 + 11 if vv else vv) for kk, vv in v.items()} if k[1] >= t else v)
            for k, v in finals.items()}


class NoAnswerKey(unittest.TestCase):
    def test_no_2025_or_2026_final_is_loaded(self):
        self.assertTrue(FINALS)
        self.assertLessEqual(max(y for (_, y) in FINALS), 2024)

    def test_committed_files_hold_no_2025_final(self):
        for path in (HARVESTED_CSV, PLANTED_CSV):
            with open(path, encoding='utf-8-sig', newline='') as f:
                for r in csv.DictReader(f):
                    self.assertFalse(r['Year'] == '2025' and r['Period'] == 'YEAR', path)
        with open(PLANTED_CSV, encoding='utf-8-sig', newline='') as f:
            self.assertFalse(any(r['Year'] == '2026' for r in csv.DictReader(f)))

    def test_answer_key_sources_are_never_named(self):
        with self.assertRaises(RuntimeError):
            FC1.fetch('cropan26')
        for py in HERE.glob('*.py'):
            if py.name == Path(__file__).name:
                continue
            text = py.read_text(encoding='utf-8')
            self.assertNotIn('quickstats_2025_judges', text, py.name)
            self.assertNotIn("annual('cropan26')", text, py.name)

    def test_2025_history_stops_at_2024(self):
        hist = est.history_2025(FINALS)
        self.assertEqual(max(y for (_, y) in hist), 2024)


class NoLookAhead(unittest.TestCase):
    def test_silage_predictions_ignore_finals_from_t_on(self):
        keys = ['state', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6']
        for t in (2013, 2018, 2022, 2024):
            a = [{k: r[k] for k in keys} for r in bt.silage_rows(FINALS, INSEASON, [t])]
            b = [{k: r[k] for k in keys} for r in bt.silage_rows(scrambled(FINALS, t), INSEASON, [t])]
            self.assertTrue(a)
            self.assertEqual(a, b, t)

    def test_grain_predictions_ignore_finals_from_t_on(self):
        for t in (2015, 2020, 2024):
            a, _ = bt.grain_rows(FINALS, INSEASON, [t])
            b, _ = bt.grain_rows(scrambled(FINALS, t), INSEASON, [t])
            self.assertEqual([(r['state'], r['G1'], r['G2']) for r in a], [(r['state'], r['G1'], r['G2']) for r in b], t)

    def test_candidates_refuse_history_from_t(self):
        with self.assertRaises(AssertionError):
            silage_candidates('MARYLAND', 2020, {('MARYLAND', 2020): dict(planted=1, grain=1, silage=1)}, 1, 1)


class Outputs(unittest.TestCase):
    def test_baseline_reproduces_the_current_forecast(self):
        hist = {**FC1.annual('cropan23'), **FC1.annual('cropan24'), **FC1.annual('cropan25')}
        hist = {k: v for k, v in hist.items() if k[1] < 2025}
        sep, nov = FC1.planted_grain_report('crop0925'), FC1.grain_report('crop1125')
        old = {r['State']: float(r['Value'].replace(',', ''))
               for r in csv.DictReader((HERE.parent / 'forecast/outputs/state_estimates_2025.csv').open(encoding='utf-8'))
               if r['Geo Level'] == 'STATE' and 'SILAGE' in r['Data Item']}
        for st, v in old.items():
            c = silage_candidates(st, 2025, hist, sep[st]['planted'], nov.get(st) or sep[st]['grain'])
            self.assertEqual(round(c['S1']), v, st)

    def test_winner_follows_the_preregistered_rule(self):
        b = json.loads((HERE / 'outputs/backtest.json').read_text(encoding='utf-8'))
        p = {m: v['acre_weighted_mape'] for m, v in b['silage']['pooled'].items()}
        floor = min(p.values())
        self.assertEqual(b['silage']['winner'], next(m for m in SIMPLICITY if p[m] <= floor + 0.20))
        g = {m: v['acre_weighted_mape'] for m, v in b['grain']['pooled'].items()}
        self.assertEqual(b['grain']['winner'], 'G2' if g['G2'] <= g['G1'] - 0.05 else 'G1')
        fresh, _ = bt.run()
        self.assertEqual((fresh['silage']['winner'], fresh['grain']['winner']), (b['silage']['winner'], b['grain']['winner']))

    def test_csv_has_every_row_of_the_current_forecast(self):
        def read(p):
            with open(p, encoding='utf-8', newline='') as f:
                return list(csv.DictReader(f))
        new = read(HERE / 'outputs/state_estimates_2025.csv')
        old = read(HERE.parent / 'forecast/outputs/state_estimates_2025.csv')
        self.assertEqual(list(new[0]), list(old[0]))
        self.assertEqual([(r['State'], r['Data Item']) for r in new], [(r['State'], r['Data Item']) for r in old])
        self.assertIn(('US TOTAL', 'CORN, SILAGE - ACRES HARVESTED'), {(r['State'], r['Data Item']) for r in new})
        self.assertIn(('MARYLAND', 'CORN, GRAIN - ACRES HARVESTED'), {(r['State'], r['Data Item']) for r in new})
        for r in new:
            self.assertEqual((r['Year'], r['Domain']), ('2025', 'TOTAL'))
            self.assertGreater(float(r['Value'].replace(',', '')), 0)

    def test_summary_has_the_current_schema(self):
        new = json.loads((HERE / 'outputs/summary.json').read_text(encoding='utf-8'))
        old = json.loads((HERE.parent / 'forecast/outputs/summary.json').read_text(encoding='utf-8'))
        # same keys as the current forecast's summary; forecast_v2 only adds keys (US grain range, per-date ranges)
        self.assertEqual(set(new), set(old))
        for k in ('interval_z', 'silage_method', 'backtest'):
            self.assertEqual(set(new[k]), set(old[k]), k)
        self.assertLessEqual(set(old['us']), set(new['us']))
        self.assertEqual(set(new['states'][0]), set(old['states'][0]))
        self.assertLessEqual(set(old['convergence'][0]), set(new['convergence'][0]))
        self.assertEqual([c['as_of'] for c in new['convergence']], [c['as_of'] for c in old['convergence']])

    def test_round2_share_code_reproduces_method_d(self):
        from common import d_prime, latest, prior
        for t in (2018, 2021, 2024):
            hist = prior(FINALS, t)
            for st in ('MARYLAND', 'WISCONSIN', 'NORTH DAKOTA', 'TEXAS', 'VERMONT'):
                p, _ = latest(INSEASON, st, t, 'planted')
                g, _ = latest(INSEASON, st, t, 'grain')
                c = silage_candidates(st, t, hist, p, g)
                self.assertAlmostEqual(d_prime(st, t, hist, p, g, 3, 'mean', False), c['S1'], places=6)

    def test_round2_follows_its_preregistered_rule(self):
        r = json.loads((HERE / 'outputs/backtest_round2.json').read_text(encoding='utf-8'))
        p = r['pooled']
        floor = min(p[m]['acre_weighted_mape'] for m in ('R1', 'R2', 'R3'))
        w = next(m for m in ('R2', 'R1', 'R3') if p[m]['acre_weighted_mape'] <= floor + 0.20)
        ok = (p['S5']['acre_weighted_mape'] - p[w]['acre_weighted_mape'] >= 0.50
              and p[w]['median_ape'] - p['S5']['median_ape'] <= 0.50)
        self.assertEqual((r['round2_winner'], r['final_silage_method']), (w, w if ok else 'S5'))
        if ok:
            rows = list(csv.DictReader((HERE / 'outputs/round2/state_estimates_2025.csv').open(encoding='utf-8')))
            old = list(csv.DictReader((HERE / 'outputs/state_estimates_2025.csv').open(encoding='utf-8')))
            self.assertEqual([(x['State'], x['Data Item']) for x in rows], [(x['State'], x['Data Item']) for x in old])

    def test_every_date_has_its_own_range(self):
        new = json.loads((HERE / 'outputs/summary.json').read_text(encoding='utf-8'))
        for c in new['convergence']:
            self.assertLess(c['us_silage_low'], c['us_silage'])
            self.assertLess(c['us_silage'], c['us_silage_high'])
            self.assertLess(c['us_grain_low'], c['us_grain'])
            self.assertLess(c['us_grain'], c['us_grain_high'])
        nov = new['convergence'][-1]
        self.assertEqual((nov['us_silage_low'], nov['us_silage_high']), (new['us']['silage_low'], new['us']['silage_high']))


if __name__ == '__main__':
    unittest.main()
