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

    def test_all_blanks_covers_every_blank_and_only_blanks(self):
        corn = pd.read_csv(uc.OUT / 'corn_check.csv')
        blanks = uc.all_blanks()
        self.assertEqual(len(blanks), int((corn.label == 'blank').sum()))
        self.assertTrue(set(uc.likely_corn_blanks()) <= set(blanks))
        labeled = set(zip(corn[corn.label != 'blank'].field_id, corn[corn.label != 'blank'].year))
        self.assertFalse(set(blanks) & labeled)

    def test_retry_replaces_only_scenes_that_now_read_and_never_fills(self):
        import json
        import tempfile
        from unittest import mock

        def record(oid, item, status):
            return dict(OBJECTID=oid, year=2022, item_id=item, date=f'2022-08-0{ord(item) - 64}',
                        ndvi=0.5 if status == 'ok' else None, status=status)

        def fake_scene(item, sel):  # scene B reads on retry, scene C never does
            return [record(int(r.OBJECTID), item, 'ok' if item == 'B' else 'read_error') for r in sel.itertuples()]

        jobs = pd.DataFrame([dict(OBJECTID=1, year=2022, label=None), dict(OBJECTID=4, year=2022, label=None)])
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(uc.rb, 'CACHE', Path(tmp)), \
                mock.patch.object(uc.rb, 'signature', lambda: 'sig'), \
                mock.patch.object(uc.rb, 'extract_scene', fake_scene), \
                mock.patch.object(uc, 'catalog_items', lambda year: {'B': 'B', 'C': 'C'}):
            for oid, obs in ((1, [record(1, 'A', 'ok'), record(1, 'B', 'read_error')]),
                             (4, [record(4, 'B', 'read_error'), record(4, 'C', 'read_error')])):
                (Path(tmp) / f'{oid}_2022.json').write_text(json.dumps(dict(
                    signature='sig', OBJECTID=oid, year=2022, label=None, observations=obs)), encoding='utf-8')
            failing = uc.retry_read_errors(jobs, waits=(0, 0))
            after = {oid: json.loads((Path(tmp) / f'{oid}_2022.json').read_text(encoding='utf-8'))['observations']
                     for oid in (1, 4)}
        self.assertEqual(failing, {'4_2022': ['C']})
        self.assertEqual([(o['item_id'], o['status']) for o in after[1]], [('A', 'ok'), ('B', 'ok')])
        self.assertEqual([(o['item_id'], o['status']) for o in after[4]], [('B', 'ok'), ('C', 'read_error')])


if __name__ == '__main__':
    unittest.main()
