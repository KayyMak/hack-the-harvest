"""Contract checks against actual baseline outputs and unavailable artifacts."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class ApiChecks(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_saved_results_contract(self):
        summary = self.client.get('/api/baseline/summary')
        predictions = self.client.get('/api/baseline/predictions')
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(predictions.status_code, 200)
        report, rows = summary.json(), predictions.json()
        self.assertEqual(len(rows), report['evaluated_field_years'])
        self.assertEqual(len({(r['field_id'], r['year']) for r in rows}), len(rows))
        self.assertEqual(sum(map(sum, report['logistic']['confusion_matrix'])), len(rows))
        field_folds = {}
        for row in rows:
            self.assertIn(row['reference_label'], ['Grain', 'Silage'])
            self.assertEqual(field_folds.setdefault(row['field_id'], row['fold']), row['fold'])

    def test_missing_or_malformed_artifacts_return_503(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('app.artifacts.OUTPUT_DIR', Path(directory)):
                for endpoint in ['summary', 'predictions']:
                    self.assertEqual(self.client.get(f'/api/baseline/{endpoint}').status_code, 503)
                (Path(directory) / 'metrics.json').write_text('{broken', encoding='utf-8')
                (Path(directory) / 'heldout_predictions.csv').write_text('wrong\nvalue\n', encoding='utf-8')
                for endpoint in ['summary', 'predictions']:
                    self.assertEqual(self.client.get(f'/api/baseline/{endpoint}').status_code, 503)


if __name__ == '__main__':
    unittest.main()
