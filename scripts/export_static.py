"""Static fallback: save every API GET response to JSON files, and serve them without FastAPI.

    python scripts/export_static.py snapshot/            # export (uses the backend environment)
    python scripts/export_static.py snapshot/ --serve    # export, then serve on :8000 (stdlib only)
    python scripts/export_static.py snapshot/ --serve-only

Files mirror the routes: /api/baseline/summary -> snapshot/api/baseline/summary.json,
/api/fields/231/observations?year=2022 -> snapshot/api/fields/231/observations/2022.json.
The server answers the same URLs, so the frontend's Vite proxy works unchanged.
Agent runs are not exported: the snapshot is read-only.
"""
import argparse
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ['/api/health', '/api/baseline/summary', '/api/baseline/predictions', '/api/baseline/rollup',
          '/api/fields', '/api/fields.geojson', '/api/quickstats?state=MARYLAND']


def file_for(out: Path, url: str) -> Path:
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')
    year = parse_qs(parsed.query).get('year')
    if path.endswith('/observations') and year:
        return out / f'{path.lstrip("/")}/{year[0]}.json'
    target = out / (path.lstrip('/') if path.endswith('.csv') else f'{path.lstrip("/")}.json')
    return target


def export(out: Path) -> dict:
    sys.path.insert(0, str(ROOT / 'backend'))
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    urls = list(ROUTES)
    preds = client.get('/api/baseline/predictions')
    if preds.status_code == 200:
        urls += [f"/api/fields/{p['field_id']}/observations?year={p['year']}" for p in preds.json()]
    written, skipped = 0, {}
    for url in urls:
        r = client.get(url)
        if r.status_code != 200:
            file_for(out, url).unlink(missing_ok=True)
            skipped[url] = r.status_code  # e.g. QuickStats 503 without QUICKSTATS_CSV
            continue
        f = file_for(out, url)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(r.json(), indent=1), encoding='utf-8')
        written += 1
    else:
        (out / 'api/baseline/rollup.csv').unlink(missing_ok=True)
    csv = client.get('/api/baseline/rollup.csv')
    if csv.status_code == 200:
        (out / 'api/baseline').mkdir(parents=True, exist_ok=True)
        (out / 'api/baseline/rollup.csv').write_text(csv.text, encoding='utf-8')
        written += 1
    return {'out': str(out), 'written': written, 'skipped': skipped}


def make_server(out: Path, port: int) -> ThreadingHTTPServer:
    out = out.resolve()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            allowed = {urlparse(u).path for u in ROUTES} | {'/api/baseline/rollup.csv'}
            observations = re.fullmatch(r'/api/fields/\d+/observations', parsed.path)
            query = parse_qs(parsed.query)
            if parsed.path not in allowed and not observations:
                self.send_error(404, 'Not in snapshot')
                return
            if observations and (len(query.get('year', [])) != 1 or
                                 not re.fullmatch(r'\d{4}', query['year'][0])):
                self.send_error(422, 'A four-digit year is required')
                return
            target = file_for(out, self.path).resolve()
            if not target.is_relative_to(out):
                self.send_error(404, 'Not in snapshot')
                return
            if not target.is_file():
                self.send_error(503, 'Not in snapshot')
                return
            try:
                body = target.read_bytes()
                if parsed.path == '/api/quickstats':
                    if query.get('state', ['MARYLAND']) != ['MARYLAND']:
                        self.send_error(503, 'Only Maryland is exported')
                        return
                    rows = json.loads(body)
                    for key, column, choices in [('year', 'year', None),
                            ('crop_use', 'crop_use', ('grain', 'silage')),
                            ('level', 'aggregation_level', ('STATE', 'COUNTY'))]:
                        if key not in query:
                            continue
                        value = query[key][-1]
                        if (choices and value not in choices) or (key == 'year' and not value.isdigit()):
                            self.send_error(422, 'Invalid QuickStats filter')
                            return
                        if any(r[column] is None for r in rows):
                            self.send_error(503, 'Snapshot cannot apply the requested filter')
                            return
                        rows = [r for r in rows if str(r[column]) == value]
                    body = json.dumps(rows).encode('utf-8')
            except (OSError, ValueError, KeyError, TypeError):
                self.send_error(503, 'Snapshot is unreadable or invalid')
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/csv' if target.suffix == '.csv' else 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.send_error(501, 'Static snapshot is read-only (no agent runs)')

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def serve(out: Path, port: int) -> None:
    print(f'Serving {out} at http://127.0.0.1:{port}/api/...')
    with make_server(out, port) as server:
        server.serve_forever()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('out', type=Path)
    ap.add_argument('--serve', action='store_true')
    ap.add_argument('--serve-only', action='store_true')
    ap.add_argument('--port', type=int, default=8000)
    a = ap.parse_args()
    if not a.serve_only:
        print(json.dumps(export(a.out), indent=2))
    if a.serve or a.serve_only:
        serve(a.out, a.port)


if __name__ == '__main__':
    main()
