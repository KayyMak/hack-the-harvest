"""The offline dashboard must use one numerical source for calls and acreage."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'baseline' / 'outputs'


class SnapshotSourceChecks(unittest.TestCase):
    def test_alternate_source_is_used_for_predictions_and_convergence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, output = root / 'inputs', root / 'snapshot'
            inputs.mkdir()
            for name in ('metrics.json', 'heldout_predictions.csv', 'observations.csv'):
                (inputs / name).write_bytes((SOURCE / name).read_bytes())
            synthetic = json.loads((SOURCE / 'asof.json').read_text(encoding='utf-8'))
            for entry in synthetic['dates']:
                for row in entry['predictions']:
                    row['silage_probability'] = 0.0
                    row['predicted_label'] = 'Grain'
            (inputs / 'asof.json').write_text(json.dumps(synthetic), encoding='utf-8')
            env = {**os.environ, 'CUTLINE_BASE': str(inputs), 'CUTLINE_OUT': str(output)}
            command = [sys.executable, str(ROOT / 'web' / 'scripts' / 'build-real-snapshot.py')]
            result = subprocess.run(command, env=env, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = json.loads((output / 'predict_2022_2022-10-12.json').read_text(encoding='utf-8'))
            self.assertTrue(calls)
            self.assertTrue(all(p['p_silage'] == 0 for p in calls))
            convergence_path = output / 'convergence_acres.json'
            self.assertTrue(convergence_path.is_file(), result.stdout + result.stderr)
            convergence = json.loads(convergence_path.read_text(encoding='utf-8'))
            self.assertTrue(convergence['years'])
            self.assertTrue(all(p['expected_silage_acres'] == 0 for y in convergence['years'] for p in y['points']))

            # A missing alternate artifact must never fall back to the default baseline.
            (inputs / 'asof.json').unlink()
            result = subprocess.run(command, env=env, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('convergence_acres.json NOT written', result.stdout)
            self.assertFalse((output / 'convergence_acres.json').exists())
            meta = json.loads((output / '_meta.json').read_text(encoding='utf-8'))
            self.assertFalse(meta['has_acres_convergence'])

    def test_mixed_model_versions_stop_the_build_before_clearing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, output = root / 'inputs', root / 'snapshot'
            (inputs / 'estimate_2025').mkdir(parents=True)
            output.mkdir()
            (output / 'keep.json').write_text('{}', encoding='utf-8')
            (inputs / 'metrics.json').write_text(json.dumps({'model_version': 'v2'}), encoding='utf-8')
            (inputs / 'estimate_2025' / 'summary.json').write_text(json.dumps({'model': {'name': 'v1 run'}}),
                                                                   encoding='utf-8')  # v1 records no version
            env = {**os.environ, 'CUTLINE_BASE': str(inputs), 'CUTLINE_OUT': str(output)}
            result = subprocess.run([sys.executable, str(ROOT / 'web' / 'scripts' / 'build-real-snapshot.py')],
                                    env=env, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('estimate_2025/summary.json records model v1 but metrics.json records v2', result.stderr)
            self.assertTrue((output / 'keep.json').exists())


if __name__ == '__main__':
    unittest.main()
