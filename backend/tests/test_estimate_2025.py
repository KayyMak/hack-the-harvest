"""Contract checks for the saved 2025 Maryland estimate route."""
import copy
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import artifacts
from app.main import app
from app.schemas import Estimate2025Summary

REAL_SUMMARY = artifacts.OUTPUT_DIR / 'estimate_2025' / 'summary.json'

# Synthetic values for shape checks only; these are not results.
SYNTHETIC = {
    'year': 2025, 'state': 'MARYLAND', 'generated_utc': '2000-01-01T00:00:00+00:00', 'headline': 'calibrated',
    'population': {'source': 'synthetic', 'corn_rule': 'synthetic', 'csb_fields_maryland': 100,
                   'corn_fields_2025': 40, 'corn_acres_2025': 1000.0},
    'sample': {'seed': 1, 'stratified_by': 'county', 'requested_fields': 10, 'sampled_fields': 10,
               'sampled_acres': 250.0, 'scored_fields': 8, 'scored_acres': 200.0, 'skipped_fields': 2,
               'skipped_reasons': {'too_few_clear_dates': 1, 'read_error': 1}, 'min_valid_dates': 3},
    'model': {'name': 'synthetic', 'training_field_years': 4, 'features': ['ndvi_07'], 'threshold': 0.5},
    'raw': {'silage_acres': 300.0, 'silage_acres_95ci': [200.0, 400.0],
            'grain_acres': 700.0, 'grain_acres_95ci': [600.0, 800.0], 'silage_share': 0.3},
    'calibrated': {'silage_acres': 250.0, 'silage_acres_95ci': [100.0, 400.0],
                   'grain_acres': 750.0, 'grain_acres_95ci': [600.0, 900.0], 'silage_share': 0.25,
                   'method': 'synthetic', 'tpr': 0.5, 'fpr': 0.1},
    'nass_2025': {'silage_acres': 200, 'grain_acres': 800, 'source': 'synthetic'},
    'benchmark': {
        'raw': {'silage': {'error': 100.0, 'relative_error': 0.5}, 'grain': {'error': -100.0, 'relative_error': -0.125}},
        'calibrated': {'silage': {'error': 50.0, 'relative_error': 0.25},
                       'grain': {'error': -50.0, 'relative_error': -0.0625}}},
    'method': 'synthetic', 'limitations': ['synthetic'],
    'sources': [{'name': 'synthetic', 'url': 'https://example.invalid/', 'accessed': '2000-01-01'}],
}


class Estimate2025Checks(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def get(self, summary=None, benchmark=None, raw_text=None):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'estimate_2025'
            folder.mkdir()
            if summary is not None:
                (folder / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
            if raw_text is not None:
                (folder / 'summary.json').write_text(raw_text, encoding='utf-8')
            if benchmark is not None:
                (folder / 'benchmark.json').write_text(json.dumps(benchmark), encoding='utf-8')
            with patch('app.artifacts.OUTPUT_DIR', Path(directory)):
                return self.client.get('/api/estimate_2025')

    def test_saved_summary_round_trips(self):
        report = {'model_name': 'synthetic', 'benchmarks': [{'year': 2025}]}
        response = self.get(SYNTHETIC, report)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'summary': SYNTHETIC, 'benchmark': report})

    def test_optional_and_unknown_keys_are_kept(self):
        extended = copy.deepcopy(SYNTHETIC)
        extended['population']['cdl_corn_acres_2025'] = 1100.0
        extended['sample'].update(batches_used=[0, 1], batches_drawn=6)
        extended['model'].update(training_silage_field_years=1, sample_fields_called_silage=2)
        extended['calibrated'].update(predicted_silage_acre_share=0.3, undefined_bootstrap_draws=0)
        extended['sample']['a_later_key'] = 'kept'
        response = self.get(extended)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['summary'], extended)
        extended['sample']['batches_drawn'] = 'six'
        self.assertEqual(self.get(extended).status_code, 503)

    def test_benchmark_report_is_null_when_not_saved(self):
        response = self.get(SYNTHETIC)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['benchmark'])

    def test_missing_or_invalid_summary_returns_503(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('app.artifacts.OUTPUT_DIR', Path(directory)):
                missing = self.client.get('/api/estimate_2025')
        self.assertEqual(missing.status_code, 503)
        self.assertIn('estimate_2025/summary.json', missing.json()['detail'])
        self.assertEqual(self.get(raw_text='{broken').status_code, 503)
        incomplete = copy.deepcopy(SYNTHETIC)
        del incomplete['nass_2025']
        self.assertEqual(self.get(incomplete).status_code, 503)
        self.assertEqual(self.get(SYNTHETIC, ['not', 'an', 'object']).status_code, 503)

    def test_unavailable_calibration_is_accepted_only_with_a_raw_headline(self):
        raw_only = copy.deepcopy(SYNTHETIC)
        raw_only['headline'] = 'raw'
        raw_only['calibrated'] = None
        raw_only['benchmark']['calibrated'] = None
        response = self.get(raw_only)
        self.assertEqual(response.status_code, 200)
        summary = response.json()['summary']
        self.assertIsNone(summary['calibrated'])
        self.assertIsNone(summary['benchmark']['calibrated'])
        self.assertEqual(summary['raw'], SYNTHETIC['raw'])
        raw_only['headline'] = 'calibrated'
        self.assertEqual(self.get(raw_only).status_code, 503)

    @unittest.skipUnless(REAL_SUMMARY.is_file(),
                         'baseline/outputs/estimate_2025/summary.json has not been generated yet')
    def test_saved_2025_estimate_matches_the_contract(self):
        summary = Estimate2025Summary.model_validate_json(REAL_SUMMARY.read_text(encoding='utf-8'))
        self.assertEqual((summary.year, summary.state), (2025, 'MARYLAND'))
        self.assertEqual((summary.nass_2025.silage_acres, summary.nass_2025.grain_acres), (40000, 410000))
        shown = summary.calibrated if summary.headline == 'calibrated' else summary.raw
        for crop in ['silage', 'grain']:
            low, high = getattr(shown, f'{crop}_acres_95ci')
            self.assertLessEqual(low, getattr(shown, f'{crop}_acres'))
            self.assertLessEqual(getattr(shown, f'{crop}_acres'), high)
        response = self.client.get('/api/estimate_2025')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['summary']['nass_2025']['silage_acres'], 40000)


if __name__ == '__main__':
    unittest.main()
