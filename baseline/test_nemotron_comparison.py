"""Offline checks: no NVIDIA requests, credentials, or new packages required."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_nemotron as comparison


class NemotronChecks(unittest.TestCase):
    def test_published_responses_match_the_frozen_inputs_and_requests(self):
        rows, features, inputs = comparison.load_inputs()
        output = comparison.HERE / 'outputs/nemotron'
        protocol = json.loads((output / 'protocol.json').read_text())
        self.assertEqual(protocol['inputs'], inputs)
        self.assertEqual(protocol['prompt'], comparison.PROMPT)
        self.assertEqual(protocol['model'], comparison.MODEL)
        self.assertEqual(protocol['features'], features)
        for row in rows:
            record = json.loads((output / 'responses' / f'{row["OBJECTID"]}_{row["year"]}.json').read_text())
            request, fields, _ = comparison.make_request(rows, row, features)
            self.assertEqual(record['status'], 'ok')
            self.assertEqual(record['request_sha256'], comparison.digest(request))
            self.assertEqual(record['request'], request)
            self.assertEqual(record['training_fields'], fields)
            self.assertEqual(comparison.parse_label(record['raw_response']), record['predicted_label'])

    def test_all_saved_folds_exclude_heldout_fields_and_labels(self):
        rows, features, _ = comparison.load_inputs()
        for target in rows:
            payload, fields, _ = comparison.make_request(rows, target, features)
            expected = {r['OBJECTID'] for r in rows if r['fold'] != target['fold']}
            self.assertEqual(set(fields), expected)
            self.assertNotIn(target['OBJECTID'], fields)
            content = json.loads(payload['messages'][1]['content'])
            self.assertEqual(set(content['field_to_classify']), set(features))
            # Changing every held-out reference label cannot change this request.
            changed = [{**r, 'label': 'Silage' if r['label'] == 'Grain' else 'Grain'}
                       if r['fold'] == target['fold'] else dict(r) for r in rows]
            alternate, _, _ = comparison.make_request(changed, target, features)
            self.assertEqual(payload, alternate)

    def test_imputation_uses_only_training_fold(self):
        target = dict(OBJECTID=1, year=2021, fold=1, label='Grain', x=None, empty=None)
        rows = [target, dict(OBJECTID=1, year=2022, fold=1, label='Silage', x=9999, empty=9999),
                dict(OBJECTID=2, year=2021, fold=2, label='Grain', x=2, empty=None),
                dict(OBJECTID=3, year=2021, fold=3, label='Silage', x=4, empty=None)]
        payload, _, medians = comparison.make_request(rows, target, ['x', 'empty'])
        self.assertEqual(medians, {'x': 3, 'empty': 0})
        self.assertEqual(json.loads(payload['messages'][1]['content'])['field_to_classify'], medians)

    def test_strict_label_parsing(self):
        self.assertEqual(comparison.parse_label('{"harvest_type":"Silage"}'), 'Silage')
        self.assertEqual(comparison.parse_label('```json\n{"harvest_type":"Grain"}\n```'), 'Grain')
        for value in ['Grain', '{"harvest_type":"Unknown"}',
                      '{"harvest_type":"Grain","explanation":"test"}']:
            with self.assertRaises(ValueError):
                comparison.parse_label(value)

    def test_scoring_matches_saved_logistic_metrics(self):
        rows, _, _ = comparison.load_inputs()
        actual = comparison.score([r['label'] for r in rows], [r['predicted_label'] for r in rows])
        expected = json.loads((comparison.INPUTS / 'metrics.json').read_text())['logistic']
        for key in ['silage_precision', 'silage_recall', 'silage_f1', 'false_positive_rate', 'balanced_accuracy']:
            self.assertAlmostEqual(actual[key], expected[key])
        self.assertEqual(actual['confusion_matrix'], expected['confusion_matrix'])

    def test_http_error_is_explicit_and_does_not_expose_key(self):
        with patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError(
                comparison.URL, 401, 'Unauthorized', {}, None)):
            record = comparison.complete({}, '_PRIVATE_TEST_KEY_')
        self.assertEqual(record['status'], 'request_error')
        self.assertEqual(record['http_status'], 401)
        self.assertNotIn('_PRIVATE_TEST_KEY_', json.dumps(record))

    def test_pilot_resume_retry_and_comparison_coverage(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(comparison, 'OUT', Path(directory)), \
             patch.dict(os.environ, {'NVIDIA_API_KEY': '_PRIVATE_TEST_KEY_'}), \
             patch('sys.stdout', new_callable=io.StringIO):
            with patch.object(sys, 'argv', ['compare', 'run']):
                with self.assertRaisesRegex(ValueError, 'pilot first'):
                    comparison.main()
            with patch.object(sys, 'argv', ['compare', 'pilot']), \
                 patch.object(comparison, 'complete', return_value={
                     'status': 'ok', 'predicted_label': 'Grain'}) as complete:
                self.assertEqual(comparison.main(), 0)
                self.assertEqual(complete.call_count, 1)
            with patch.object(sys, 'argv', ['compare', 'run']), \
                 patch.object(comparison, 'complete', return_value={
                     'status': 'request_error', 'error': 'NVIDIA HTTP 429'}):
                self.assertEqual(comparison.main(), 1)
            report = json.loads((Path(directory) / 'metrics.json').read_text())
            self.assertEqual(report['coverage'], {'ok': 1, 'request_error': 1, 'invalid_response': 0})
            self.assertEqual(report['pending'], report['total_field_years'] - 2)
            self.assertEqual(report['nemotron']['n'], report['logistic_same_rows']['n'])
            with patch.object(sys, 'argv', ['compare', 'run', '--retry-failures']), \
                 patch.object(comparison, 'complete', return_value={
                     'status': 'ok', 'predicted_label': 'Grain'}) as complete:
                self.assertEqual(comparison.main(), 0)
                self.assertEqual(complete.call_count, report['total_field_years'] - 1)
            with patch.object(sys, 'argv', ['compare', 'run']), \
                 patch.object(comparison, 'complete') as complete:
                self.assertEqual(comparison.main(), 0)
                complete.assert_not_called()
            report = json.loads((Path(directory) / 'metrics.json').read_text())
            self.assertEqual(report['nemotron']['n'], report['total_field_years'])
            self.assertEqual(report['nemotron'], report['always_grain_same_rows'])
            for path in Path(directory).rglob('*.json'):
                self.assertNotIn('_PRIVATE_TEST_KEY_', path.read_text())


if __name__ == '__main__':
    unittest.main()
