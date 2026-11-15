"""Actual as-of tool calls and artifact-failure regressions (optional agent dependencies)."""
import csv
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harvest import asof
from app import artifacts


@unittest.skipUnless(importlib.util.find_spec('langchain_core') and importlib.util.find_spec('sklearn'),
                     'requires optional agent and analysis dependencies')
class AsOfTools(unittest.TestCase):
    def setUp(self):
        from harvest import tools
        self.tools = tools

    def test_actual_tools_and_cli_agree(self):
        from harvest.run import run
        wrapped = {t.name: t for t in self.tools.TOOLS}
        args = {'year': 2022, 'as_of': '2022-10-12'}
        classified = json.loads(wrapped['classify'].invoke(args))
        self.assertEqual(classified['n'], 7)
        self.assertEqual(classified['features'], ['ndvi_07', 'ndvi_08', 'ndvi_09'])
        for row in classified['predictions']:
            self.assertEqual(set(row['evidence']), set(classified['features']))
        score = json.loads(wrapped['evaluate'].invoke(args))
        self.assertEqual(sum(map(sum, score['confusion_matrix'])), 7)
        roll = json.loads(wrapped['aggregate'].invoke(args))
        with tempfile.TemporaryDirectory() as directory:
            result = run(2022, '2022-10-12', Path(directory))
        self.assertEqual(result['silage_acres_expected'], roll['years'][0]['expected_silage_acres'])
        self.assertEqual(result['balanced_accuracy'], score['balanced_accuracy'])

    def test_compatibility_pending_and_bad_arguments(self):
        self.assertEqual(self.tools.call('classify')['n'], 44)
        self.assertEqual(self.tools.call('classify', {'field_ids': []})['n'], 0)
        early = self.tools.call('classify', {'year': 2022, 'as_of': '2022-07-15'})
        self.assertEqual((early['n'], early['n_pending']), (0, 7))
        for args in [{'as_of': '2022-10-12'}, {'year': 2022, 'as_of': '2023-10-12'},
                     {'year': 2022, 'as_of': 'bad'}, {'year': 'bad'}, {'unexpected': True}]:
            self.assertIn('error', self.tools.call('classify', args))
        tool = next(t for t in self.tools.TOOLS if t.name == 'classify')
        self.assertIsInstance(tool.invoke({'year': 'bad'}), str)

    def test_regenerated_or_missing_artifacts_are_not_cached(self):
        self.tools.call('classify', {'year': 2022, 'as_of': '2022-10-12'})
        with tempfile.TemporaryDirectory() as directory, patch.object(artifacts, 'OUTPUT_DIR', Path(directory)):
            self.assertIn('error', self.tools.call('classify', {'year': 2022, 'as_of': '2022-10-12'}))

    def test_invalid_labels_and_cross_field_folds_stop_refit(self):
        source = artifacts.OUTPUT_DIR
        with (source / 'heldout_predictions.csv').open(newline='') as file:
            rows = list(csv.DictReader(file))
        for invalid in ['label', 'fold']:
            altered = [dict(r) for r in rows]
            if invalid == 'label':
                altered[0]['label'] = ''
            else:
                repeated = next(r for r in altered[1:] if r['OBJECTID'] == altered[0]['OBJECTID'])
                repeated['fold'] = str((int(altered[0]['fold']) + 1) % 5)
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                (output / 'metrics.json').write_bytes((source / 'metrics.json').read_bytes())
                with (output / 'heldout_predictions.csv').open('w', newline='') as file:
                    writer = csv.DictWriter(file, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(altered)
                with patch.object(artifacts, 'OUTPUT_DIR', output):
                    result = self.tools.call('classify', {'year': 2022, 'as_of': '2022-10-12'})
                self.assertIn('error', result)


if __name__ == '__main__':
    unittest.main()
