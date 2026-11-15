"""Offline regression checks for a resumable, baseline-preserving input experiment."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
import experiment_scene_filter as experiment


class SceneFilterChecks(unittest.TestCase):
    def test_published_experiment_preserves_its_source_fingerprints(self):
        out = experiment.HERE / 'outputs/experiments/no_scene_cloud_filter'
        protocol = json.loads((out / 'protocol.json').read_text())
        import hashlib
        for name, expected in protocol['inputs'].items():
            self.assertEqual(hashlib.sha256((experiment.REFERENCE / name).read_bytes()).hexdigest(), expected)
        for key, expected in protocol['original_cache_hashes'].items():
            source = json.loads((experiment.HERE / 'cache' / f'{key}.json').read_text())
            self.assertEqual(experiment.fingerprint(source), expected)
        signature = experiment.fingerprint(protocol)
        for path in (out / 'additional_scenes').glob('*.json'):
            self.assertEqual(json.loads(path.read_text())['signature'], signature)

    def test_merge_preserves_original_and_rejects_repeated_scene(self):
        original = {'observations': [{'item_id': 'old', 'date': '2023-09-02'}]}
        added = [{'item_id': 'new', 'date': '2023-09-12'}]
        merged = experiment.combined(original, added)
        self.assertEqual(len(merged['observations']), 2)
        self.assertEqual(len(original['observations']), 1)
        with self.assertRaises(ValueError):
            experiment.combined(original, original['observations'])

    def test_pilot_cache_does_not_omit_other_fields_in_full_run(self):
        item = SimpleNamespace(id='test-scene')

        def extract(_, jobs):
            return [dict(OBJECTID=int(fid), year=2023, item_id=item.id,
                         date='2023-09-12', status='ok') for fid in jobs.OBJECTID]

        with tempfile.TemporaryDirectory() as directory, \
             patch.object(experiment, 'OUT', Path(directory)), \
             patch.object(experiment.baseline, 'extract_scene', side_effect=extract) as reader:
            pilot = experiment.scene_records(item, pd.DataFrame({'OBJECTID': [323]}), 'signature')
            self.assertEqual([r['OBJECTID'] for r in pilot], [323])
            full = experiment.scene_records(item, pd.DataFrame({'OBJECTID': [323, 327]}), 'signature')
            self.assertEqual({r['OBJECTID'] for r in full}, {323, 327})
            self.assertEqual(reader.call_count, 2)
            self.assertEqual(reader.call_args.args[1].OBJECTID.tolist(), [327])
            experiment.scene_records(item, pd.DataFrame({'OBJECTID': [323, 327]}), 'signature')
            self.assertEqual(reader.call_count, 2)
            with self.assertRaises(ValueError):
                experiment.scene_records(item, pd.DataFrame({'OBJECTID': [323]}), 'stale')

    def test_saved_fold_refit_reproduces_baseline(self):
        table = pd.read_csv(experiment.REFERENCE / 'features.csv')
        saved = pd.read_csv(experiment.REFERENCE / 'heldout_predictions.csv')
        metadata = json.loads((experiment.REFERENCE / 'metrics.json').read_text())
        rebuilt = experiment.fit_on_saved_folds(table, metadata)
        np.testing.assert_allclose(rebuilt.silage_probability, saved.silage_probability, atol=1e-10, rtol=0)
        self.assertEqual(rebuilt.predicted_label.tolist(), saved.predicted_label.tolist())
        self.assertEqual(rebuilt.fold.tolist(), saved.fold.tolist())
        self.assertEqual(rebuilt.groupby('OBJECTID').fold.nunique().max(), 1)


if __name__ == '__main__':
    unittest.main()
