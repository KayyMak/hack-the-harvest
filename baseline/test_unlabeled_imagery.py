"""Saved series and chips for every unlabeled (blank-label) field-year."""
import csv
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import export_unlabeled_imagery as ui

OUT = HERE / 'outputs'


def keys_in(path, oid='OBJECTID'):
    with path.open(encoding='utf-8', newline='') as f:
        return [(int(r[oid]), int(r['year'])) for r in csv.DictReader(f)]


def unlabeled_rows():
    with (OUT / 'unlabeled' / 'observations.csv').open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def coverage():
    return json.loads((OUT / 'unlabeled' / 'observations_coverage.json').read_text(encoding='utf-8'))


class UnlabeledImagery(unittest.TestCase):
    def test_every_field_year_has_a_saved_series_or_is_listed(self):
        """All 249 field-years: labeled observations, unlabeled observations with a usable look, or listed."""
        every = set(keys_in(OUT / 'unlabeled' / 'corn_check.csv', 'field_id'))
        self.assertEqual(len(every), 249)
        ok = {(int(r['OBJECTID']), int(r['year'])) for r in unlabeled_rows() if r['status'] == 'ok'}
        with (OUT / 'observations.csv').open(encoding='utf-8', newline='') as f:
            ok |= {(int(r['OBJECTID']), int(r['year'])) for r in csv.DictReader(f) if r['status'] == 'ok'}
        with (OUT / 'excluded_no_observations.csv').open(encoding='utf-8', newline='') as f:
            listed = {(int(r['OBJECTID']), int(r['year'])) for r in csv.DictReader(f)}
        c = coverage()
        listed |= {tuple(int(x) for x in k.split('_')) for k in c['missing_cache'] + c['no_usable_looks']}
        self.assertEqual(every - ok - listed, set())

    def test_observations_cover_every_blank_field_year_and_no_labeled_one(self):
        keys = set(ui.blank_field_years())
        self.assertEqual(len(keys), 205)
        self.assertTrue(set(ui.called_field_years()) <= keys)
        rows = unlabeled_rows()
        seen = {(int(r['OBJECTID']), int(r['year'])) for r in rows}
        missing = {tuple(int(x) for x in k.split('_')) for k in coverage()['missing_cache']}
        self.assertEqual(seen, keys - missing)
        self.assertFalse(seen & ui.labeled_field_years())
        self.assertEqual(list(rows[0].keys()), ui.COLUMNS)

    def test_coverage_file_matches_the_observations(self):
        c = coverage()
        self.assertEqual(c['blank_field_years'], 205)
        self.assertEqual(c['with_series'], 205 - len(c['missing_cache']))
        self.assertEqual(c['with_model_call'] + c['evidence_only'], 205)
        self.assertEqual(c['with_model_call'], len(ui.called_field_years()))
        errors = {}
        for r in unlabeled_rows():
            if r['status'] == 'read_error':
                errors.setdefault(f"{r['OBJECTID']}_{r['year']}", []).append(r['item_id'])
        self.assertEqual({k: sorted(v) for k, v in errors.items()}, c['scenes_still_failing_to_read'])

    def test_rows_match_the_extraction_cache(self):
        rows = {}
        for r in unlabeled_rows():
            rows.setdefault((int(r['OBJECTID']), int(r['year'])), []).append(r)
        for (oid, year), got in rows.items():
            cached = json.loads((ui.CACHE / f'{oid}_{year}.json').read_text(encoding='utf-8'))
            self.assertIsNone(cached['label'], f'{oid}_{year}')
            obs = cached['observations']
            self.assertEqual(len(got), len(obs), f'{oid}_{year}')
            self.assertEqual(sum(r['status'] == 'ok' for r in got), sum(o['status'] == 'ok' for o in obs))

    def test_every_chip_in_the_index_exists_and_every_field_year_is_indexed_or_listed(self):
        index = json.loads((OUT / 'chips' / 'index_unlabeled.json').read_text(encoding='utf-8'))
        self.assertEqual(index['skipped'], [])
        for key, entry in index['chips'].items():
            self.assertEqual(set(entry), {'pre', 'post'}, key)
            for which in entry:
                self.assertTrue((OUT / 'chips' / f'{key}_{which}.png').exists(), key)
        indexed = {tuple(int(x) for x in k.split('_')) for k in index['chips']}
        too_few = {tuple(int(x) for x in k.split(':')[0].split('_')) for k in index['too_few_usable_looks']}
        self.assertFalse(indexed & too_few)
        series = {(int(r['OBJECTID']), int(r['year'])) for r in unlabeled_rows()}
        self.assertEqual(indexed | too_few, series)
        self.assertFalse(indexed & ui.labeled_field_years())

    def test_labeled_chip_index_is_separate(self):
        labeled = json.loads((OUT / 'chips' / 'index.json').read_text(encoding='utf-8'))['chips']
        unlabeled = json.loads((OUT / 'chips' / 'index_unlabeled.json').read_text(encoding='utf-8'))['chips']
        self.assertFalse(set(labeled) & set(unlabeled))


if __name__ == '__main__':
    unittest.main()
