"""Saved series and chips for unlabeled field-years with model calls."""
import csv
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import export_unlabeled_imagery as ui

OUT = HERE / 'outputs'


class UnlabeledImagery(unittest.TestCase):
    def test_observations_cover_every_called_field_year_and_no_labeled_one(self):
        keys = set(ui.called_field_years())
        with (OUT / 'unlabeled' / 'observations.csv').open(encoding='utf-8', newline='') as f:
            rows = list(csv.DictReader(f))
        seen = {(int(r['OBJECTID']), int(r['year'])) for r in rows}
        self.assertEqual(seen, keys)
        with (OUT / 'labels.csv').open(encoding='utf-8', newline='') as f:
            labeled = {(int(r['OBJECTID']), int(r['year'])) for r in csv.DictReader(f)}
        self.assertFalse(seen & labeled)
        self.assertEqual(list(rows[0].keys()), ui.COLUMNS)

    def test_rows_match_the_extraction_cache(self):
        oid, year = ui.called_field_years()[0]
        cached = json.loads((ui.CACHE / f'{oid}_{year}.json').read_text(encoding='utf-8'))['observations']
        with (OUT / 'unlabeled' / 'observations.csv').open(encoding='utf-8', newline='') as f:
            rows = [r for r in csv.DictReader(f) if (int(r['OBJECTID']), int(r['year'])) == (oid, year)]
        self.assertEqual(len(rows), len(cached))
        self.assertEqual(sum(r['status'] == 'ok' for r in rows), sum(o['status'] == 'ok' for o in cached))

    def test_every_chip_in_the_index_exists(self):
        index = json.loads((OUT / 'chips' / 'index_unlabeled.json').read_text(encoding='utf-8'))
        self.assertEqual(index['skipped'], [])
        for key, entry in index['chips'].items():
            for which in entry:
                self.assertTrue((OUT / 'chips' / f'{key}_{which}.png').exists(), key)


if __name__ == '__main__':
    unittest.main()
