"""Hosted-image checks: the judges' QuickStats file and the saved decline-rule baseline."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

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


if __name__ == '__main__':
    unittest.main()
