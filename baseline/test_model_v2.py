"""Tests for the model-v2 experiment: feature function and no leakage across field folds."""
import math
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / 'model_v2'))
import candidate  # noqa: E402
import experiment as ex  # noqa: E402
from features import (BASE_FEATURES, BASELINE_OUT, NO_DECLINE_DOY, build_table, daily_series,  # noqa: E402
                      timing_features)


def obs(day, ndvi, status='ok'):
    return dict(date=day, ndvi='' if ndvi is None else str(ndvi), status=status)


class TimingFeatureTest(unittest.TestCase):
    def test_hand_checked_series(self):
        # Raw:      .80  .85  .84  .30  .25  .40  .60
        # Smoothed: .825 .84  .84  .30  .30  .40  .50   (centered 3-date median)
        records = [obs('2022-07-10', 0.80), obs('2022-07-20', 0.85), obs('2022-08-10', 0.84),
                   obs('2022-08-30', 0.30), obs('2022-09-10', 0.25), obs('2022-10-01', 0.40),
                   obs('2022-11-01', 0.60),
                   obs('2022-09-20', 0.99, status='insufficient_clear_pixels'),  # ignored
                   obs('2022-09-25', None, status='read_error')]                # ignored
        f = timing_features(daily_series(records))
        # Peak .84 (first max, Jul 20); first sustained value <= .59 is Aug 30 = day 242.
        self.assertEqual(f['decline_doy'], 242.0)
        # Largest consecutive smoothed drop .84 -> .30, ending Aug 30.
        self.assertEqual(f['drop_doy'], 242.0)
        self.assertAlmostEqual(f['drop_size'], 0.54, places=12)
        # Post-peak minimum .30 (Aug 30); later maximum .50.
        self.assertAlmostEqual(f['regrowth'], 0.20, places=12)

    def test_duplicate_dates_count_once(self):
        series = daily_series([obs('2021-07-01', 0.7), obs('2021-07-01', 0.9), obs('2021-07-05', 0.5)])
        self.assertEqual(series, [('2021-07-01', 0.8), ('2021-07-05', 0.5)])

    def test_no_decline_is_censored_and_empty_is_missing(self):
        f = timing_features(daily_series([obs('2021-07-01', 0.8), obs('2021-08-01', 0.8), obs('2021-09-01', 0.8)]))
        self.assertEqual(f['decline_doy'], NO_DECLINE_DOY)
        self.assertTrue(math.isnan(f['drop_doy']) and math.isnan(f['drop_size']))
        self.assertEqual(f['regrowth'], 0.0)
        self.assertTrue(all(math.isnan(v) for v in timing_features([]).values()))

    def test_baseline_features_rebuilt_exactly(self):
        table, base = build_table()
        self.assertEqual(len(table), 44)
        for c in BASE_FEATURES:
            np.testing.assert_allclose(table[c].to_numpy(float), base[c].to_numpy(float), atol=1e-12)


class NoLeakageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table, _ = build_table()
        cls.y = (cls.table.label == 'Silage').astype(int).to_numpy()
        cls.groups = cls.table.OBJECTID.to_numpy()

    def test_test_fields_never_in_training(self):
        for seed in [ex.REFERENCE_SEED] + ex.SELECTION_SEEDS:
            seen = []
            for train, test in ex.splits(self.y, self.groups, seed, 5):
                self.assertFalse(set(self.groups[train]) & set(self.groups[test]))
                seen.extend(test)
            self.assertEqual(sorted(seen), list(range(len(self.y))))

    def test_corrupting_test_rows_does_not_change_fitted_model(self):
        spec = ex.BY_NAME['H']  # most training-dependent: inner-CV C plus imputation and scaling
        cols = list(spec.features)
        for train, test in ex.splits(self.y, self.groups, ex.REFERENCE_SEED, 5):
            bad = self.table.copy()
            bad.loc[test, cols] = 999.0
            y_bad = self.y.copy()
            y_bad[test] = 1 - y_bad[test]
            clean = ex.fit(spec, self.table[cols].to_numpy(float)[train], self.y[train], self.groups[train], 42)
            dirty = ex.fit(spec, bad[cols].to_numpy(float)[train], y_bad[train], self.groups[train], 42)
            self.assertEqual(clean.C, dirty.C)
            np.testing.assert_array_equal(clean.model[0].statistics_, dirty.model[0].statistics_)
            np.testing.assert_array_equal(clean.model[1].mean_, dirty.model[1].mean_)
            np.testing.assert_array_equal(clean.model[-1].coef_, dirty.model[-1].coef_)

    def test_heldout_equals_fit_without_test_rows(self):
        spec = ex.BY_NAME['H']
        cols = list(spec.features)
        proba, _, _, _ = ex.heldout(spec, self.table, ex.REFERENCE_SEED)
        for train, test in ex.splits(self.y, self.groups, ex.REFERENCE_SEED, 5):
            rest = self.table.drop(index=test).reset_index(drop=True)
            m = ex.fit(spec, rest[cols].to_numpy(float), (rest.label == 'Silage').astype(int).to_numpy(),
                       rest.OBJECTID.to_numpy(), ex.REFERENCE_SEED)
            np.testing.assert_allclose(m.predict_proba(self.table[cols].to_numpy(float)[test]), proba[test])

    def test_candidate_a_reproduces_saved_baseline(self):
        _, ref = ex.run_seed(self.table, ex.REFERENCE_SEED)
        ex.check_reference(self.table, ref)


class CandidateTest(unittest.TestCase):
    def test_fit_requires_groups(self):
        table, _ = build_table()
        with self.assertRaises(ValueError):
            candidate.build_model().fit(table[candidate.FEATURES], (table.label == 'Silage').astype(int))

    def test_saved_candidate_predictions_match_experiment(self):
        path = ex.OUT / 'heldout_predictions_candidate.csv'
        saved = pd.read_csv(path)
        base = pd.read_csv(BASELINE_OUT / 'heldout_predictions.csv')
        self.assertEqual([c for c in saved.columns if c not in candidate.TIMING_FEATURES], list(base.columns))
        table, _ = build_table()
        proba, pred, folds, _ = ex.heldout(candidate.SPEC, table, ex.REFERENCE_SEED)
        np.testing.assert_allclose(saved.silage_probability.to_numpy(), proba, atol=1e-12)
        np.testing.assert_array_equal(saved.fold.to_numpy(), base.fold.to_numpy())


if __name__ == '__main__':
    unittest.main()
