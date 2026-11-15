"""The spatial hold-out never trains on a test block's fields and reports every k."""
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import spatial_holdout as sh


class SpatialHoldout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fields, cls.table = sh.load()

    def test_blocks_keep_every_year_of_a_field_together(self):
        block, _ = sh.blocks_for(self.fields, self.table, 5)
        per_field = {}
        for oid, b in zip(self.table.OBJECTID, block):
            per_field.setdefault(int(oid), set()).add(int(b))
        self.assertTrue(all(len(v) == 1 for v in per_field.values()))

    def test_saved_report_lists_every_k_and_scores_all_44(self):
        report = json.loads((HERE / 'outputs' / 'spatial_holdout.json').read_text())
        self.assertEqual([r['k'] for r in report['results']], list(sh.K))
        for r in report['results']:
            self.assertEqual(r['logistic']['n'], len(self.table))
            self.assertEqual(sum(f['test_field_years'] for f in r['folds']), len(self.table))
            self.assertTrue(all(f['min_gap_to_training_m'] > 0 for f in r['folds']))


if __name__ == '__main__':
    unittest.main()
