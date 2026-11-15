"""Checks for calls on blank-label field-years: corn rule, label separation, saved outputs."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd

import unlabeled_calls as uc


class UnlabeledCallChecks(unittest.TestCase):
    def test_corn_rule_categories(self):
        self.assertEqual(uc.classify_corn(40, 0.5), 'likely_corn')
        self.assertEqual(uc.classify_corn(40, 0.49), 'mixed')
        self.assertEqual(uc.classify_corn(40, 0.19), 'not_corn')
        self.assertEqual(uc.classify_corn(5, 1.0), 'uncertain')

    def test_labeled_field_years_are_refused(self):
        with self.assertRaises(ValueError):
            uc.blank_jobs([(1, 2021)])  # field 1 is labeled in 2021
        jobs = uc.blank_jobs([(1, 2022)])  # and blank in 2022
        self.assertEqual(jobs.crs.to_epsg(), 4326)
        self.assertIsNone(jobs.label.iloc[0])

    def test_bernoulli_interval_matches_rollup_formula(self):
        p, a = np.array([0.8, 0.2]), np.array([10.0, 20.0])
        result = uc.bernoulli(p, a)
        sd = np.sqrt(100 * 0.16 + 400 * 0.16)
        self.assertAlmostEqual(result['expected_silage_acres'], 12.0)
        self.assertAlmostEqual(result['expected_silage_acres_95ci'][1], round(12 + 1.96 * sd, 2))

    @unittest.skipUnless((uc.OUT / 'predictions.csv').exists(), 'predictions not generated')
    def test_saved_calls_are_blank_likely_corn_and_never_filled(self):
        pred = pd.read_csv(uc.OUT / 'predictions.csv')
        corn = pd.read_csv(uc.OUT / 'corn_check.csv')
        merged = pred.merge(corn[['field_id', 'year', 'label', 'category']], on=['field_id', 'year'])
        self.assertEqual(len(merged), len(pred))
        self.assertTrue((merged.label == 'blank').all())
        self.assertTrue((merged.category == 'likely_corn').all())
        missing = pred[pred.status == 'no_usable_dates']
        self.assertTrue(missing.silage_probability.isna().all())
        self.assertTrue((pred[pred.status == 'called'].silage_probability.between(0, 1)).all())


if __name__ == '__main__':
    unittest.main()
