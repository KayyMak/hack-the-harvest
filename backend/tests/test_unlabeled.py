"""GET /api/unlabeled: saved model calls on blank-label field-years, kept apart from labeled results."""
import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
SAVED = ROOT / 'baseline' / 'outputs' / 'unlabeled'


class UnlabeledRoute(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_serves_saved_calls_and_matches_the_summary(self):
        response = self.client.get('/api/unlabeled')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        summary = json.loads((SAVED / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(body['counts'], summary['counts'])
        called = [c for c in body['calls'] if c['status'] == 'called']
        self.assertEqual(len(called), body['counts']['called'])
        labeled = {(int(r['OBJECTID']), int(r['year'])) for r in csv.DictReader(
            (ROOT / 'baseline' / 'outputs' / 'labels.csv').open(encoding='utf-8'))}
        for call in body['calls']:
            self.assertNotIn((call['field_id'], call['year']), labeled, 'a labeled field-year is never an unlabeled call')
            self.assertGreaterEqual(call['corn_share'], summary['corn_rule']['likely_corn_share_at_least'])
            self.assertNotIn('reference_label', call)
        for year in body['by_year']:
            rows = [c for c in called if c['year'] == year['year']]
            self.assertEqual(year['field_years_called'], len(rows))
            self.assertAlmostEqual(year['expected_silage_acres'],
                                   sum(c['silage_probability'] * c['acres'] for c in rows), delta=0.05)
            low, high = year['expected_silage_acres_95ci']
            self.assertLessEqual(low, year['expected_silage_acres'])
            self.assertLessEqual(year['expected_silage_acres'], high)
        self.assertIn('no reference label', body['caveat'])

    def test_missing_artifacts_are_503(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('app.artifacts.OUTPUT_DIR', Path(directory)):
                response = self.client.get('/api/unlabeled')
        self.assertEqual(response.status_code, 503)
        self.assertIn('unlabeled_calls.py', response.json()['detail'])

    def test_a_call_without_probability_is_rejected_not_shown(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'unlabeled'
            shutil.copytree(SAVED, folder)
            path = folder / 'predictions.csv'
            with path.open(encoding='utf-8', newline='') as file:
                rows = list(csv.DictReader(file))
            first = next(r for r in rows if r['status'] == 'called')
            first['silage_probability'] = ''
            with path.open('w', encoding='utf-8', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with patch('app.artifacts.OUTPUT_DIR', Path(directory)):
                self.assertEqual(self.client.get('/api/unlabeled').status_code, 503)

    def test_dockerfile_copies_the_files_the_route_reads(self):
        text = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIn('baseline/outputs/unlabeled/summary.json baseline/outputs/unlabeled/predictions.csv', text)


if __name__ == '__main__':
    unittest.main()


class UnlabeledObservations(unittest.TestCase):
    """Unlabeled field-years with model calls get their saved greenness series too."""

    def test_series_for_an_unlabeled_called_field_year(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        calls = client.get('/api/unlabeled').json()['calls']
        call = next(c for c in calls if c['status'] == 'called')
        obs = client.get(f"/api/fields/{call['field_id']}/observations", params={'year': call['year']})
        self.assertEqual(obs.status_code, 200)
        dates = [o['date'] for o in obs.json()]
        self.assertEqual(dates, sorted(dates))
        self.assertGreaterEqual(sum(o['status'] == 'ok' for o in obs.json()), call['valid_dates'])
