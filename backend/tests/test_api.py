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

    def test_quickstats_lab_format(self):
        header = ('year,aggregation_level,state_name,state_ansi,county_name,county_ansi,commodity,crop_use,'
                  'measurement,statistic,unit,value,cv_percent,source,domain,domain_category,reference_period,'
                  'frequency,short_description\n')
        rows = ('2022,STATE,MARYLAND,24,,,CORN,silage,harvested,AREA HARVESTED,ACRES,"52,000",4.1,CENSUS,TOTAL,'
                'NOT SPECIFIED,YEAR,ANNUAL,"CORN, SILAGE - ACRES HARVESTED"\n'
                '2022,COUNTY,MARYLAND,24,FREDERICK,021,CORN,silage,harvested,AREA HARVESTED,ACRES,'
                '                 (D),(D),CENSUS,TOTAL,NOT SPECIFIED,YEAR,ANNUAL,"CORN, SILAGE - ACRES HARVESTED"\n'
                '2022,STATE,MARYLAND,24,,,CORN,grain,harvested,AREA HARVESTED,ACRES,"400,000",2.0,CENSUS,'
                'IRRIGATION,X,YEAR,ANNUAL,"CORN, GRAIN, IRRIGATED - ACRES HARVESTED"\n')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'qs.csv'
            path.write_text(header + rows, encoding='utf-8')
            with patch.dict('os.environ', {'QUICKSTATS_CSV': str(path)}):
                all_rows = self.client.get('/api/quickstats').json()
                state = self.client.get('/api/quickstats', params={'crop_use': 'silage', 'level': 'STATE'}).json()
        self.assertEqual(len(all_rows), 2)  # irrigated (non-TOTAL) row dropped
        self.assertEqual((state[0]['value'], state[0]['cv_percent'], state[0]['source']), (52000.0, 4.1, 'CENSUS'))
        county = [r for r in all_rows if r['county']][0]
        self.assertEqual((county['value'], county['cv_percent'], county['suppressed']), (None, None, True))
        export = self.client.get('/api/baseline/rollup.csv').text.splitlines()[0]
        self.assertEqual(export, header.strip())

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
            with patch('app.tools.RUNS_DIR', Path(directory)), \
                 patch('app.tools.TRACES_DIR', Path(directory) / 'traces'):
                self.assertEqual(self.client.get('/api/agent/trace/r-1').json(), [])
                tools.log_step('r-1', node='Analyst', tool='classify')
                tools.log_step('r-1', node='Verifier', verdict='ok')
                steps = self.client.get('/api/agent/trace/r-1').json()
                self.assertEqual([s['step'] for s in steps], [1, 2])
                self.assertEqual(steps[1]['node'], 'Verifier')
                self.assertTrue((Path(directory) / 'traces' / 'r-1.jsonl').exists())
                self.assertTrue(Path(tools.write_report('r-1', '# hi')['path']).exists())
                self.assertIn('error', tools.call_tool('write_report', {'run_id': '../x', 'markdown': 'x'}))
                self.assertEqual(self.client.get('/api/agent/trace/bad id!').status_code, 400)

    def test_agent_run_without_agent_returns_501(self):
        response = self.client.post('/api/agent/run', json={'query': 'classify 2022'})
        self.assertEqual(response.status_code, 501)

    def test_rollup_statistics_and_csv(self):
        years = self.client.get('/api/baseline/rollup').json()['years']
        for y in years:
            self.assertGreater(y['cv_percent'], 0)
            if y['adjusted_silage_share'] is not None:
                self.assertTrue(0 <= y['adjusted_silage_share'] <= 1)
        csv_text = self.client.get('/api/baseline/rollup.csv')
        self.assertEqual(csv_text.status_code, 200)
        lines = csv_text.text.strip().splitlines()
        self.assertIn('cv_percent', lines[0])
        self.assertEqual(len(lines), len(years) + 1)

    def test_evaluate_has_both_classes_with_wilson_intervals(self):
        from app import tools
        e = tools.evaluate()
        for cls in ('Grain', 'Silage'):
            low, high = e['per_class'][cls]['recall_95ci']
            self.assertLessEqual(low, e['per_class'][cls]['recall'])
            self.assertLessEqual(e['per_class'][cls]['recall'], high)
        self.assertEqual(sum(sum(c.values()) for c in e['counts_by_year_and_class'].values()), e['n'])
        self.assertEqual(tools.wilson(0, 0), None)

    def test_one_command_full_season_and_too_early(self):
        import json
        import sys
        root = str(Path(__file__).resolve().parents[2])
        if root not in sys.path:
            sys.path.insert(0, root)
        from harvest.run import run
        with tempfile.TemporaryDirectory() as directory:
            full = run(2022, '2022-11-30', Path(directory) / 'full')
            self.assertEqual(full['mode'], 'saved full-season model')
            self.assertEqual(full['decided'], 7)
            names = {p.name for p in (Path(directory) / 'full').iterdir()}
            self.assertTrue({'predictions.csv', 'metrics.json', 'rollup.json', 'quickstats_export.csv',
                             'run.json'} <= names)
            saved = self.client.get('/api/baseline/rollup').json()['years']
            self.assertEqual(full['silage_acres_expected'],
                             next(y['expected_silage_acres'] for y in saved if y['year'] == 2022))
            early = run(2022, '2022-07-15', Path(directory) / 'early')
            self.assertEqual((early['decided'], early['pending']), (0, 7))
            rows = (Path(directory) / 'early' / 'predictions.csv').read_text().splitlines()[1:]
            self.assertTrue(all(',Pending,' in r for r in rows))

    def test_field_polygons(self):
        shapes = self.client.get('/api/fields.geojson')
        self.assertEqual(shapes.status_code, 200)
        features = shapes.json()['features']
        ids = {f['properties']['field_id'] for f in features}
        self.assertEqual(ids, {f['field_id'] for f in self.client.get('/api/fields').json()})
        for f in features:
            for ring in [c for poly in (f['geometry']['coordinates'] if f['geometry']['type'] == 'MultiPolygon'
                                        else [f['geometry']['coordinates']]) for c in poly]:
                for lon, lat in ring:
                    self.assertTrue(-77.5 < lon < -76.0 and 38.5 < lat < 39.5)  # Beltsville, MD
        labels = {(f['properties']['field_id'], y): f['properties'][f'reference_{y}']
                  for f in features for y in (2021, 2022, 2023) if f['properties'][f'reference_{y}']}
        for p in self.client.get('/api/baseline/predictions').json():
            self.assertEqual(labels[(p['field_id'], p['year'])], p['reference_label'])
        self.assertEqual(len(labels), len(self.client.get('/api/baseline/predictions').json()))
        with tempfile.TemporaryDirectory() as directory:
            with patch('app.artifacts.OUTPUT_DIR', Path(directory)):
                self.assertEqual(self.client.get('/api/fields.geojson').status_code, 503)


if __name__ == '__main__':
    unittest.main()
