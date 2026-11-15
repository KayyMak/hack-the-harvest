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
CRLF, LF = bytes([13, 10]), bytes([10])


def unix_newlines(data: bytes) -> bytes:
    return data.replace(CRLF, LF)


class Switch(unittest.TestCase):
    def test_environment_override_and_validation(self):
        with patch.dict(os.environ, {mv.ENV: 'V1 '}):
            self.assertEqual(mv.current(), 'v1')
            self.assertEqual(mv.features(), mv.BASE_FEATURES)
        with patch.dict(os.environ, {mv.ENV: 'v3'}):
            with self.assertRaises(ValueError):
                mv.current()
        self.assertEqual(mv.features('v2'), mv.BASE_FEATURES + mv.TIMING_FEATURES)

    def test_v1_pipeline_is_run_baseline_build_model(self):
        import run_baseline
        self.assertEqual(repr(mv.v1_pipeline()), repr(run_baseline.build_model()))
        self.assertEqual(mv.v1_pipeline().get_params().keys(), run_baseline.build_model().get_params().keys())
        for (n1, s1), (n2, s2) in zip(mv.v1_pipeline().steps, run_baseline.build_model().steps):
            self.assertEqual((n1, s1.get_params()), (n2, s2.get_params()))

    def test_building_a_model_does_not_import_the_extraction_stack(self):
        code = ('import sys, model_version as mv; mv.build_model("v2"); mv.build_model("v1"); '
                'bad = [m for m in ("run_baseline", "geopandas", "rasterio", "planetary_computer") if m in sys.modules]; '
                'assert not bad, bad')
        subprocess.run([sys.executable, '-c', code], cwd=HERE, check=True)

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
                fresh, kept = (unix_newlines((p / name).read_bytes()) for p in (Path(directory), BACKUP))
                self.assertEqual(fresh, kept, name)  # line endings may differ by platform


if __name__ == '__main__':
    unittest.main()
