"""The model switch: v2 is what is saved, and v1 still reproduces its backed-up outputs exactly."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import model_version as mv  # noqa: E402

OUT = HERE / 'outputs'
BACKUP = OUT / 'v1_backup'
CANDIDATE = HERE / 'model_v2' / 'outputs' / 'heldout_predictions_candidate.csv'


class Switch(unittest.TestCase):
    def test_environment_override_and_validation(self):
        with patch.dict(os.environ, {mv.ENV: 'V1 '}):
            self.assertEqual(mv.current(), 'v1')
            self.assertEqual(mv.features(), mv.BASE_FEATURES)
        with patch.dict(os.environ, {mv.ENV: 'v3'}):
            with self.assertRaises(ValueError):
                mv.current()
        self.assertEqual(mv.features('v2'), mv.BASE_FEATURES + mv.TIMING_FEATURES)

    def test_saved_outputs_match_their_recorded_version(self):
        saved = pd.read_csv(OUT / 'heldout_predictions.csv')
        version = mv.saved_version()
        reference = pd.read_csv(CANDIDATE if version == 'v2' else BACKUP / 'heldout_predictions.csv')
        self.assertEqual(list(saved.columns), list(reference.columns))
        np.testing.assert_allclose(saved.silage_probability, reference.silage_probability, atol=1e-12, rtol=0)
        self.assertEqual(saved.predicted_label.tolist(), reference.predicted_label.tolist())
        self.assertEqual(saved.fold.tolist(), pd.read_csv(BACKUP / 'heldout_predictions.csv').fold.tolist())
        metrics = json.loads((OUT / 'metrics.json').read_text(encoding='utf-8'))
        self.assertEqual(metrics['features'], mv.features(version))
        self.assertIn('logistic', metrics)  # the API schema reads this key for either version

    def test_v1_switch_reproduces_the_backup_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            code = ('import sys; from pathlib import Path; import run_baseline as rb; '
                    'rb.OUT = Path(sys.argv[1]); rb.evaluate(rb.read_labels())')
            env = {**os.environ, mv.ENV: 'v1'}
            subprocess.run([sys.executable, '-c', code, directory], cwd=HERE, env=env, check=True,
                           stdout=subprocess.DEVNULL)
            for name in ['heldout_predictions.csv', 'metrics.json', 'features.csv', 'results.md',
                         'missing_features.csv', 'excluded_no_observations.csv']:
                self.assertEqual((Path(directory) / name).read_bytes(), (BACKUP / name).read_bytes(), name)


if __name__ == '__main__':
    unittest.main()
