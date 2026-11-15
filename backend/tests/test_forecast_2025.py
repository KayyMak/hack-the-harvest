"""Contract checks for the saved 2025 forecast route (the graded output)."""
import copy
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import artifacts
from app.main import app
from app.schemas import Forecast2025Summary

# Synthetic values for shape checks only; these are not results.
SYNTHETIC = {
    'method': 'synthetic', 'answer_key_excluded': 'synthetic',
    'sources': {'a': {'title': 'synthetic', 'released': 'January 1, 2000', 'url': 'https://example.invalid/a'},
                'b': {'title': 'synthetic', 'released': None, 'url': 'https://example.invalid/b'}},
    'backtest': {
        'silage': {'state_years': 4, 'median_abs_pct_error': 10.0, 'mean_abs_pct_error': 12.0,
                   'covered_by_95_interval': 1.0, 'us_total': {'2000': {'est': 1, 'truth': 1, 'pct_error': 0.0}}},
        'grain': {'state_years': 4, 'median_abs_pct_error': 1.0, 'mean_abs_pct_error': 2.0,
                  'covered_by_95_interval': 0.75}},
    'us': {'silage': 100, 'silage_se': 10, 'silage_low': 80, 'silage_high': 120, 'grain': 1000, 'grain_se': 20},
    'states': [
        {'state': 'MARYLAND', 'silage': 10, 'silage_low': 5, 'silage_high': 15, 'silage_se': 2,
         'grain': 100, 'grain_low': 90, 'grain_high': 110, 'grain_se': 5, 'share_base': 'residual'},
        {'state': 'MAINE', 'silage': 3, 'silage_low': 1, 'silage_high': 5, 'silage_se': 1,
         'grain': None, 'grain_low': None, 'grain_high': None, 'grain_se': None},
    ],
    'convergence': [{'as_of': '2000-06-30', 'source': 'synthetic', 'md_silage': 9}],
}
REFERENCE = ('"Program","Year","Period","Geo Level","State","Commodity","Data Item","Domain","Value"\n'
             '"SURVEY","2025","YEAR","NATIONAL","US TOTAL","CORN","CORN, SILAGE - ACRES HARVESTED","TOTAL","200"\n'
             '"SURVEY","2025","YEAR","STATE","MARYLAND","CORN","CORN, SILAGE - ACRES HARVESTED","TOTAL","12"\n'
             '"SURVEY","2025","YEAR","STATE","MARYLAND","CORN","CORN, GRAIN - ACRES HARVESTED","TOTAL","(D)"\n')


class Forecast2025Checks(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def get(self, summary=None, raw_text=None, reference=REFERENCE):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            if summary is not None:
                (folder / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
            if raw_text is not None:
                (folder / 'summary.json').write_text(raw_text, encoding='utf-8')
            if reference is not None:
                (folder / 'reference.csv').write_text(reference, encoding='utf-8')
            with patch('app.artifacts.FORECAST_SUMMARY', folder / 'summary.json'), \
                 patch('app.artifacts.NASS_2025_CSV', folder / 'reference.csv'):
                return self.client.get('/api/forecast_2025')

    def test_saved_forecast_round_trips_with_nass_reference(self):
        response = self.get(SYNTHETIC)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['summary'], json.loads(json.dumps(SYNTHETIC)))
        self.assertEqual(body['nass_2025']['maryland'], {'silage': 12, 'grain': None})  # (D) is unknown, not 0
        self.assertEqual(body['nass_2025']['us'], {'silage': 200, 'grain': None})

    def test_missing_reference_keeps_the_forecast(self):
        response = self.get(SYNTHETIC, reference=None)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['nass_2025'])

    def test_missing_or_invalid_forecast_returns_503(self):
        missing = self.get()
        self.assertEqual(missing.status_code, 503)
        self.assertIn('forecast/outputs/summary.json', missing.json()['detail'])
        self.assertEqual(self.get(raw_text='{broken').status_code, 503)
        for broken in ['backtest', 'states', 'us', 'answer_key_excluded']:
            altered = copy.deepcopy(SYNTHETIC)
            del altered[broken]
            self.assertEqual(self.get(altered).status_code, 503, broken)
        repeated = copy.deepcopy(SYNTHETIC)
        repeated['states'].append(copy.deepcopy(repeated['states'][0]))
        self.assertEqual(self.get(repeated).status_code, 503)
        no_range = copy.deepcopy(SYNTHETIC)
        del no_range['states'][0]['silage_high']
        self.assertEqual(self.get(no_range).status_code, 503)

    @unittest.skipUnless(artifacts.FORECAST_SUMMARY.is_file(), 'forecast/outputs/summary.json is not saved')
    def test_saved_2025_forecast_matches_the_contract(self):
        summary = Forecast2025Summary.model_validate_json(artifacts.FORECAST_SUMMARY.read_text(encoding='utf-8'))
        maryland = [s for s in summary.states if s.state == 'MARYLAND']
        self.assertEqual(len(maryland), 1)
        md = maryland[0]
        self.assertLessEqual(md.silage_low, md.silage)
        self.assertLessEqual(md.silage, md.silage_high)
        self.assertLessEqual(md.grain_low, md.grain)
        self.assertLessEqual(md.grain, md.grain_high)
        response = self.client.get('/api/forecast_2025')
        self.assertEqual(response.status_code, 200)
        if artifacts.NASS_2025_CSV.is_file():
            nass = response.json()['nass_2025']['maryland']
            self.assertEqual((nass['silage'], nass['grain']), (40000, 410000))


if __name__ == '__main__':
    unittest.main()
