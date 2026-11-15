"""Production serving keeps the build and API on the same origin."""
import tempfile
from pathlib import Path
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.frontend import mount_frontend


class FrontendChecks(unittest.TestCase):
    def test_build_and_api_routing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            build = root / 'dist'
            build.mkdir()
            (build / 'index.html').write_text('<h1>Dashboard</h1>', encoding='utf-8')
            (build / 'app.js').write_text('console.log("ready")', encoding='utf-8')
            (root / 'private.txt').write_text('private', encoding='utf-8')
            app = FastAPI()

            @app.get('/api/health')
            def health():
                return {'status': 'ok'}

            mount_frontend(app, build)
            client = TestClient(app)
            self.assertIn('Dashboard', client.get('/').text)
            self.assertIn('ready', client.get('/app.js').text)
            self.assertEqual(client.get('/api/health').json(), {'status': 'ok'})
            self.assertEqual(client.get('/docs').status_code, 200)
            self.assertEqual(client.get('/openapi.json').status_code, 200)
            for path in ['/api/missing', '/private.txt', '/%2e%2e/private.txt', '/backend/app/main.py']:
                self.assertEqual(client.get(path).status_code, 404, path)

    def test_missing_build_is_optional(self):
        with tempfile.TemporaryDirectory() as folder:
            app = FastAPI()
            mount_frontend(app, Path(folder) / 'missing')
            self.assertEqual(TestClient(app).get('/').status_code, 404)
