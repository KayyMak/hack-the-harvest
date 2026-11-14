"""Regression checks for PR #2's acreage, filtering, and agent evidence paths."""
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import artifacts, tools
from app.main import app
from app.schemas import BarcField, Prediction


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_acreage_adjustment_uses_acre_weighted_error_rates(self):
        fields = [BarcField(field_id=i, farm=None, field=None, acres=area)
                  for i, area in [(1, 10), (2, 90), (3, 100)]]
        predictions = [Prediction(field_id=i, year=year, reference_label=label,
            predicted_label=pred, silage_probability=prob, fold=i, valid_dates=10)
            for year in [2021, 2022] for i, label, pred, prob in
            [(1, 'Silage', 'Silage', 0.9), (2, 'Silage', 'Grain', 0.1),
             (3, 'Grain', 'Grain', 0.1)]]
        with patch('app.artifacts.read_fields', return_value=fields):
            rollup = artifacts.compute_rollup(predictions)
        for year in rollup.years:
            self.assertAlmostEqual(year.adjustment_rates['tpr'], 0.1)
            self.assertEqual(year.adjusted_silage_acres, 100)
            self.assertEqual(year.adjusted_silage_acres, year.reference_silage_acres)
        # Without a separate year's calibration data, no correction is available.
        with patch('app.artifacts.read_fields', return_value=fields):
            single = artifacts.compute_rollup(predictions[:3]).years[0]
        self.assertIsNone(single.adjusted_silage_acres)

    def test_crop_use_filter_infers_labels_from_standard_data_item(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'qs.csv'
            path.write_text('Year,State,Data Item,Value\n'
                '2022,MARYLAND,"CORN, SILAGE - ACRES HARVESTED",45000\n'
                '2022,MARYLAND,"CORN, GRAIN - ACRES HARVESTED",400000\n', encoding='utf-8')
            with patch.dict(os.environ, {'QUICKSTATS_CSV': str(path)}):
                for use, expected in [('silage', 45000), ('grain', 400000)]:
                    response = self.client.get('/api/quickstats', params={'crop_use': use})
                    self.assertEqual(response.status_code, 200)
                    rows = response.json()
                    self.assertEqual(len(rows), 1)
                    self.assertEqual((rows[0]['crop_use'], rows[0]['value']), (use, expected))

    def test_quickstats_rejects_filters_it_cannot_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'qs.csv'
            path.write_text('Year,State,Value\n2022,MARYLAND,45000\n', encoding='utf-8')
            with patch.dict(os.environ, {'QUICKSTATS_CSV': str(path)}):
                for params in [{'crop_use': 'silage'}, {'level': 'STATE'}]:
                    self.assertEqual(self.client.get('/api/quickstats', params=params).status_code, 503)

    def test_runs_started_in_same_second_have_distinct_ids(self):
        agent = types.ModuleType('agent')
        agent.__path__ = []
        runner = types.ModuleType('agent.run')
        calls = []
        runner.run_agent = lambda query, run_id: calls.append((query, run_id))
        with patch.dict(sys.modules, {'agent': agent, 'agent.run': runner}), \
             patch('time.strftime', return_value='r-20261114-120000'):
            responses = [self.client.post('/api/agent/run', json={'query': query})
                         for query in ['first', 'second']]
        self.assertTrue(all(r.status_code == 200 for r in responses))
        ids = [r.json()['run_id'] for r in responses]
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual([run_id for _, run_id in calls], ids)
        for run_id in ids:
            self.assertEqual(tools._check_run_id(run_id), run_id)

    def test_classify_returns_every_model_feature(self):
        features = json.loads((artifacts.OUTPUT_DIR / 'metrics.json').read_text())['features']
        result = tools.classify(year=2021, field_ids=[327])
        self.assertEqual(result['n'], 1)
        evidence = result['predictions'][0]['evidence']
        self.assertEqual(set(evidence), set(features))
        self.assertAlmostEqual(evidence['ndvi_11'], 0.396776, places=5)
        self.assertIsNotNone(evidence['peak_ndvi'])

    def test_classify_reports_missing_feature_metadata(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('app.artifacts.OUTPUT_DIR', Path(directory)):
            result = tools.call_tool('classify', {'year': 2021, 'field_ids': [327]})
            self.assertIn('error', result)

    def test_trace_poll_ignores_only_an_unfinished_final_record(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('app.tools.TRACES_DIR', Path(directory)):
            tools.log_step('r-test', node='Analyst')
            path = Path(directory) / 'r-test.jsonl'
            with path.open('a', encoding='utf-8') as file:
                file.write('{"step":')
            response = self.client.get('/api/agent/trace/r-test')
            self.assertEqual(response.status_code, 200)
            self.assertEqual([r['step'] for r in response.json()], [1])
            with path.open('a', encoding='utf-8') as file:
                file.write('2,"node":"Verifier"}\n')
            self.assertEqual(len(self.client.get('/api/agent/trace/r-test').json()), 2)
            # A malformed, newline-terminated record is corruption, not a pending write.
            with path.open('a', encoding='utf-8') as file:
                file.write('{broken}\n')
            self.assertEqual(self.client.get('/api/agent/trace/r-test').status_code, 503)


if __name__ == '__main__':
    unittest.main()
