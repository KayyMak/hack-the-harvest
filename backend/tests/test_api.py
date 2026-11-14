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

    def test_fields_and_observations(self):
        fields = self.client.get('/api/fields')
        self.assertEqual(fields.status_code, 200)
        ids = {f['field_id'] for f in fields.json()}
        self.assertEqual(len(ids), len(fields.json()))
        row = self.client.get('/api/baseline/predictions').json()[0]
        self.assertIn(row['field_id'], ids)
        obs = self.client.get(f"/api/fields/{row['field_id']}/observations",
                              params={'year': row['year']})
        self.assertEqual(obs.status_code, 200)
        dates = [o['date'] for o in obs.json()]
        self.assertEqual(dates, sorted(dates))
        self.assertGreaterEqual(len([o for o in obs.json() if o['status'] == 'ok']), row['valid_dates'])
        missing = self.client.get(f"/api/fields/{row['field_id']}/observations", params={'year': 1900})
        self.assertEqual(missing.status_code, 404)

    def test_rollup_matches_predictions(self):
        rollup = self.client.get('/api/baseline/rollup')
        self.assertEqual(rollup.status_code, 200)
        years = rollup.json()['years']
        rows = self.client.get('/api/baseline/predictions').json()
        self.assertEqual(sum(y['field_years'] for y in years), len(rows))
        for y in years:
            low, high = y['expected_silage_acres_95ci']
            self.assertLessEqual(low, y['expected_silage_acres'])
            self.assertLessEqual(y['expected_silage_acres'], high)
            self.assertLessEqual(y['reference_silage_acres'], y['total_acres'])

    def test_quickstats_suppressed_values_are_null(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'qs.csv'
            path.write_text('Year,State,Data Item,Value\n'
                '2022,MARYLAND,"CORN, SILAGE - ACRES HARVESTED","45,000"\n'
                '2022,MARYLAND,"CORN, GRAIN - ACRES HARVESTED",(D)\n'
                '2022,IOWA,"CORN, SILAGE - ACRES HARVESTED","1,000"\n', encoding='utf-8')
            with patch.dict('os.environ', {'QUICKSTATS_CSV': str(path)}):
                rows = self.client.get('/api/quickstats').json()
            self.assertEqual([(r['value'], r['suppressed']) for r in rows], [(45000.0, False), (None, True)])
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(self.client.get('/api/quickstats').status_code, 503)

    def test_new_endpoints_return_503_without_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('app.artifacts.OUTPUT_DIR', Path(directory)), \
                 patch('app.artifacts.FIELDS_GPKG', Path(directory) / 'none.gpkg'):
                for url in ['/api/fields', '/api/baseline/rollup', '/api/fields/1/observations?year=2021']:
                    self.assertEqual(self.client.get(url).status_code, 503, url)

    def test_agent_tools_on_saved_outputs(self):
        from app import tools
        self.assertEqual({s['function']['name'] for s in tools.TOOL_SPECS}, set(tools.TOOLS))
        preds = tools.call_tool('classify', {'year': 2022})
        self.assertTrue(preds['n'] > 0 and all(p['year'] == 2022 for p in preds['predictions']))
        self.assertIn('evidence', preds['predictions'][0])
        overall = tools.call_tool('evaluate')
        self.assertEqual(sum(map(sum, overall['confusion_matrix'])),
                         sum(map(sum, overall['logistic']['confusion_matrix'])))
        self.assertIn('error', tools.call_tool('nope'))
        self.assertIn('error', tools.call_tool('get_timeseries', {'field_id': 1}))
        self.assertIn('error', tools.call_tool('get_timeseries', {'field_id': 1, 'year': 1900}))

    def test_agent_trace_and_report(self):
        from app import tools
        with tempfile.TemporaryDirectory() as directory:
            with patch('app.tools.RUNS_DIR', Path(directory)):
                self.assertEqual(self.client.get('/api/agent/trace/r-1').json(), [])
                tools.log_step('r-1', node='Analyst', tool='classify')
                tools.log_step('r-1', node='Verifier', verdict='ok')
                steps = self.client.get('/api/agent/trace/r-1').json()
                self.assertEqual([s['step'] for s in steps], [1, 2])
                self.assertEqual(steps[1]['node'], 'Verifier')
                self.assertTrue(Path(tools.write_report('r-1', '# hi')['path']).exists())
                self.assertIn('error', tools.call_tool('write_report', {'run_id': '../x', 'markdown': 'x'}))
                self.assertEqual(self.client.get('/api/agent/trace/bad id!').status_code, 400)

    def test_agent_run_without_agent_returns_501(self):
        response = self.client.post('/api/agent/run', json={'query': 'classify 2022'})
        self.assertEqual(response.status_code, 501)


if __name__ == '__main__':
    unittest.main()
