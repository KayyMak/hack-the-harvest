"""The committed signal breakdown reproduces every saved probability and is current."""
from pathlib import Path
import csv
import math
import sys
import unittest
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_contributions import OUT_DIR, compute  # noqa: E402


class SignalBreakdown(unittest.TestCase):
    def test_breakdown_adds_up_to_saved_probabilities(self):
        with (OUT_DIR / 'feature_contributions.csv').open(encoding='utf-8', newline='') as f:
            rows = list(csv.DictReader(f))
        logodds = defaultdict(float)
        intercept = {}
        for r in rows:
            if r['as_of']:
                continue  # mid-season rows are checked against asof.json by the exporter itself
            key = (r['OBJECTID'], r['year'])
            logodds[key] += float(r['contribution'])
            intercept[key] = float(r['intercept'])
        with (OUT_DIR / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as f:
            saved = {(r['OBJECTID'], r['year']): float(r['silage_probability']) for r in csv.DictReader(f)}
        self.assertEqual(set(logodds), set(saved))
        for key, p in saved.items():
            self.assertAlmostEqual(1 / (1 + math.exp(-(intercept[key] + logodds[key]))), p, places=4, msg=key)

    def test_committed_file_matches_a_fresh_export(self):
        fresh = {(r['OBJECTID'], r['year'], r['as_of'], r['feature']): r['contribution'] for r in compute()}
        with (OUT_DIR / 'feature_contributions.csv').open(encoding='utf-8', newline='') as f:
            committed = {(int(r['OBJECTID']), int(r['year']), r['as_of'], r['feature']): float(r['contribution'])
                         for r in csv.DictReader(f)}
        self.assertEqual(fresh, committed)


if __name__ == '__main__':
    unittest.main()
