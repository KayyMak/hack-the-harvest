"""Checks for the Maryland 2025 scale-up arithmetic and its saved outputs. Offline."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'estimate_2025'))
sys.path.insert(0, str(HERE.parent / 'backend'))
import numpy as np
import pandas as pd

import estimate
from app.benchmark import score_files

OUT = HERE / 'outputs' / 'estimate_2025'
REFERENCE = HERE.parent / 'data' / 'reference' / 'quickstats_2025_judges.csv'


class ScaleUpArithmetic(unittest.TestCase):
    def test_adjustment_recovers_a_known_share(self):
        # 30% true silage, 60% of silage found, 10% of grain called silage -> q = 0.25.
        q = 0.3 * 0.6 + 0.7 * 0.1
        self.assertAlmostEqual(estimate.adjusted_share(q, 0.6, 0.1), 0.3)

    def test_adjustment_is_clipped_and_undefined_without_separation(self):
        self.assertEqual(estimate.adjusted_share(0.05, 0.6, 0.1), 0.0)
        self.assertEqual(estimate.adjusted_share(0.9, 0.6, 0.1), 1.0)
        self.assertIsNone(estimate.adjusted_share(0.2, 0.1, 0.1))
        self.assertIsNone(estimate.adjusted_share(0.2, None, 0.1))

    def test_rates_are_acre_weighted(self):
        heldout = pd.DataFrame(dict(
            label=['Silage', 'Silage', 'Grain', 'Grain'],
            predicted_label=['Silage', 'Grain', 'Silage', 'Grain'],
            acres=[30.0, 10.0, 5.0, 45.0]))
        tpr, fpr = estimate.rates(heldout)
        self.assertAlmostEqual(tpr, 0.75)
        self.assertAlmostEqual(fpr, 0.1)

    def test_saved_barc_rates_use_every_heldout_field_year_with_acres(self):
        heldout = estimate.barc_heldout()
        self.assertEqual(len(heldout), 44)
        tpr, fpr = estimate.rates(heldout)
        self.assertTrue(0 < fpr < tpr < 1)

    def test_grain_and_silage_always_add_up_to_corn_acres(self):
        b = estimate.block(1000.0, 10000.0, 0.1, np.array([0.05, 0.1, 0.2]))
        self.assertAlmostEqual(b['silage_acres'] + b['grain_acres'], 10000.0)
        self.assertLessEqual(b['silage_acres_95ci'][0], b['silage_acres_95ci'][1])
        self.assertAlmostEqual(b['silage_acres_95ci'][0] + b['grain_acres_95ci'][1], 10000.0)

    def test_prediction_file_is_scored_by_the_judge_benchmark(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state_estimates.csv'
            estimate.write_predictions(path, 41500.4, 400000.6)
            report = score_files(REFERENCE, path)
        scored = {c['crop_use']: c for c in report['comparisons'] if c['status'] == 'scored'}
        self.assertEqual(report['predictions']['rows_rejected'], 0)
        self.assertEqual(scored['Silage']['prediction_value'], 41500)
        self.assertEqual(scored['Silage']['signed_error'], 1500)
        self.assertEqual(scored['Grain']['signed_error'], -9999)

    def test_reference_is_the_judges_maryland_rows(self):
        self.assertEqual(estimate.nass_reference(), {'silage': 40000, 'grain': 410000})


@unittest.skipUnless((OUT / 'summary.json').exists(), 'No saved 2025 estimate yet')
class SavedEstimate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = json.loads((OUT / 'summary.json').read_text(encoding='utf-8'))

    def test_counts_are_consistent_and_nothing_is_filled_in(self):
        sample = self.s['sample']
        self.assertEqual(sample['scored_fields'] + sample['skipped_fields'], sample['sampled_fields'])
        self.assertEqual(sum(sample['skipped_reasons'].values()), sample['skipped_fields'])
        predictions = pd.read_csv(OUT / 'predictions.csv')
        self.assertEqual(len(predictions), sample['scored_fields'])
        self.assertTrue((predictions.valid_dates >= sample['min_valid_dates']).all())
        self.assertTrue(predictions.silage_probability.between(0, 1).all())

    def test_acres_add_up_and_errors_match_the_reference(self):
        corn = self.s['population']['corn_acres_2025']
        for name in ('raw', 'calibrated'):
            block = self.s[name]
            if block is None:
                continue
            self.assertAlmostEqual(block['silage_acres'] + block['grain_acres'], corn, places=0)
            lo, hi = block['silage_acres_95ci']
            self.assertLessEqual(lo, hi)
            error = self.s['benchmark'][name]
            self.assertAlmostEqual(error['silage']['error'], round(block['silage_acres']) - 40000)
            self.assertAlmostEqual(error['grain']['error'], round(block['grain_acres']) - 410000)
        self.assertEqual(self.s['nass_2025']['silage_acres'], 40000)
        self.assertEqual(self.s['nass_2025']['grain_acres'], 410000)


if __name__ == '__main__':
    unittest.main()
