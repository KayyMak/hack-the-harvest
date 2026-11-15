"""The lab's QuickStats export mixes all-corn rows (acres planted) with grain and silage rows."""
import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import artifacts


class AllCornRowsAreSkipped(unittest.TestCase):
    def test_filter_by_use_skips_rows_without_a_grain_or_silage_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'lab.csv'
            with path.open('w', encoding='utf-8', newline='') as f:
                w = csv.writer(f)
                w.writerow(['year', 'aggregation_level', 'state_name', 'crop_use', 'short_description', 'value', 'domain'])
                w.writerow([2022, 'STATE', 'MARYLAND', 'all_corn', 'CORN - ACRES PLANTED', '460,000', 'TOTAL'])
                w.writerow([2022, 'STATE', 'MARYLAND', 'silage', 'CORN, SILAGE - ACRES HARVESTED', '40,000', 'TOTAL'])
                w.writerow([2022, 'STATE', 'MARYLAND', 'grain', 'CORN, GRAIN - ACRES HARVESTED', '360,000', 'TOTAL'])
            with patch.dict(os.environ, {'QUICKSTATS_CSV': str(path)}):
                rows = artifacts.read_quickstats('MARYLAND', 2022, crop_use='silage', level='STATE')
        self.assertEqual([(r.crop_use, r.value) for r in rows], [('silage', 40000.0)])


if __name__ == '__main__':
    unittest.main()
