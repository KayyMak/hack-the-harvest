"""Hosted-image checks: the judges' QuickStats file and the saved decline-rule baseline."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app import artifacts

ROOT = Path(__file__).resolve().parents[2]
JUDGES = ROOT / 'data' / 'reference' / 'quickstats_2025_judges.csv'
DECLINE = ROOT / 'baseline' / 'outputs' / 'decline_rule' / 'metrics.json'


class QuickStatsJudgesFile(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_dockerfile_sets_the_env_var_to_a_file_it_copies(self):
        text = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIn('ENV QUICKSTATS_CSV=/app/data/reference/quickstats_2025_judges.csv', text)
        self.assertIn('COPY data/reference/quickstats_2025_judges.csv', text)

    def test_maryland_2025_totals_from_the_judges_file(self):
        with patch.dict(os.environ, {'QUICKSTATS_CSV': str(JUDGES)}):
            response = self.client.get('/api/quickstats', params={'state': 'MARYLAND', 'year': 2025})
            by_use = {r['crop_use']: r for r in response.json()}
            state_only = self.client.get('/api/quickstats',
                params={'state': 'MARYLAND', 'year': 2025, 'level': 'STATE', 'crop_use': 'silage'}).json()
            other_year = self.client.get('/api/quickstats', params={'state': 'MARYLAND', 'year': 2022})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((by_use['silage']['value'], by_use['grain']['value']), (40000.0, 410000.0))
        self.assertEqual([r['value'] for r in state_only], [40000.0])
        self.assertEqual(state_only[0]['source'], 'SURVEY')
        self.assertEqual(other_year.json(), [])  # the file has no 2022 Census rows; empty, not invented

    def test_unset_env_explains_which_file_is_needed(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.get('/api/quickstats')
        self.assertEqual(response.status_code, 503)


class DeclineRuleRoute(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_serves_the_saved_file_unchanged(self):
        saved = json.loads(DECLINE.read_text(encoding='utf-8'))
        response = self.client.get('/api/baseline/decline_rule')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['decline_rule'], saved['decline_rule'])
        self.assertEqual(body['always_grain_same_rows']['balanced_accuracy'], 0.5)
        self.assertEqual(sorted(body['by_year']), ['2021', '2022', '2023'])
        for matrix in (body['decline_rule'], body['logistic_same_rows']):
            self.assertEqual(sum(map(sum, matrix['confusion_matrix'])), body['evaluated_field_years'])

    def test_missing_file_is_503_not_zeros(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('app.artifacts.OUTPUT_DIR', Path(directory)):
                response = self.client.get('/api/baseline/decline_rule')
        self.assertEqual(response.status_code, 503)
        self.assertIn('decline_rule/metrics.json', response.json()['detail'])


class ConvergenceRoute(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_matches_rollup_at_season_end_and_has_ordered_dates(self):
        body = self.client.get('/api/baseline/convergence').json()
        rollup = {y['year']: y for y in self.client.get('/api/baseline/rollup').json()['years']}
        self.assertEqual([y['year'] for y in body['years']], [2021, 2022, 2023])
        for year in body['years']:
            dates = [p['as_of'] for p in year['points']]
            self.assertEqual(dates, sorted(dates))
            self.assertEqual(len(dates), 5)
            last = year['points'][-1]
            self.assertEqual(last['as_of'], f"{year['year']}-11-30")
            expected = rollup[year['year']]
            # as-of file stores probabilities to 6 decimals, so allow rounding noise
            self.assertAlmostEqual(last['expected_silage_acres'], expected['expected_silage_acres'], delta=0.1)
            for got, want in zip(last['expected_silage_acres_95ci'], expected['expected_silage_acres_95ci']):
                self.assertAlmostEqual(got, want, delta=0.1)
            for point in year['points']:
                low, high = point['expected_silage_acres_95ci']
                self.assertLessEqual(low, point['expected_silage_acres'])
                self.assertLessEqual(point['expected_silage_acres'], high)
                self.assertEqual(point['reference_silage_acres'], expected['reference_silage_acres'])

    def test_missing_as_of_file_is_503(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('app.artifacts.OUTPUT_DIR', Path(directory)):
                self.assertEqual(self.client.get('/api/baseline/convergence').status_code, 503)

    def test_missing_acreage_is_explicit(self):
        fields = artifacts.read_fields()
        with patch('app.artifacts.read_fields', return_value=[f.model_copy(update={'acres': None}) for f in fields]):
            response = self.client.get('/api/baseline/convergence')
        self.assertEqual(response.status_code, 503)
        self.assertIn('known acreage', response.json()['detail'])
        partial = [f.model_copy(update={'acres': None}) if f.field_id == 1 else f for f in fields]
        with patch('app.artifacts.read_fields', return_value=partial):
            response = self.client.get('/api/baseline/convergence')
        self.assertEqual(response.status_code, 200)
        point = next(y for y in response.json()['years'] if y['year'] == 2021)['points'][0]
        self.assertEqual(point['missing_acres_field_years'], 1)


if __name__ == '__main__':
    unittest.main()
