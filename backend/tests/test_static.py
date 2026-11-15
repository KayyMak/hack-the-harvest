"""HTTP integration checks for the standard-library snapshot fallback."""
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.export_static import export, make_server
from app import artifacts


class StaticSnapshot(unittest.TestCase):
    def test_snapshot_contract_filters_traversal_and_reexport(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / 'snapshot'
            qs = root / 'quickstats.csv'
            qs.write_text('Year,State,Data Item,Value,aggregation_level\n'
                '2022,MARYLAND,"CORN, SILAGE - ACRES HARVESTED",123,STATE\n'
                '2023,MARYLAND,"CORN, GRAIN - ACRES HARVESTED",456,COUNTY\n')
            with patch.dict(os.environ, {'QUICKSTATS_CSV': str(qs)}):
                result = export(out)
            # The satellite estimate is optional until baseline/outputs/estimate_2025/ is saved.
            skipped = dict(result['skipped'])
            if not (artifacts.OUTPUT_DIR / 'estimate_2025' / 'summary.json').is_file():
                self.assertEqual(skipped.pop('/api/estimate_2025', None), 503)
            self.assertFalse(skipped)
            server = make_server(out, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def get(path, method='GET'):
                connection = http.client.HTTPConnection(*server.server_address)
                connection.request(method, path)
                response = connection.getresponse()
                result = response.status, response.read()
                connection.close()
                return result
            try:
                status, body = get('/api/baseline/rollup')
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body), artifacts.compute_rollup().model_dump(mode='json'))
                status, body = get('/api/quickstats?state=MARYLAND&year=2022&crop_use=silage&level=STATE')
                self.assertEqual(status, 200)
                self.assertEqual([r['value'] for r in json.loads(body)], [123])
                self.assertEqual(get('/api/quickstats?state=IOWA')[0], 503)
                (root / 'private.csv').write_text('private')
                for path in ['/../private.csv', '/api/fields/1/observations?year=../../private',
                             '/api/fields/1/observations?year=C:/private']:
                    self.assertNotEqual(get(path)[0], 200)
                self.assertEqual(get('/api/baseline/rollup.csv', 'HEAD')[0], 501)
                self.assertEqual(get('/api/agent/run', 'POST')[0], 501)
                self.assertEqual(get('/api/fields/231/observations?year=2022')[0], 200)
                with patch.dict(os.environ, {'QUICKSTATS_CSV': str(root / 'missing.csv')}):
                    export(out)
                self.assertEqual(get('/api/quickstats')[0], 503)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
