"""Check a running production container: python scripts/check_deployment.py [URL]."""
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def check(base: str) -> None:
    def get(path):
        with urlopen(base + path, timeout=30) as response:
            return response.read()

    html = get('/').decode('utf-8')
    assert 'id="root"' in html, 'Frontend build is missing'
    # Verify the hashed JavaScript asset referenced by the built HTML exists.
    import re
    assets = re.findall(r'src="([^"]+\.js)"', html)
    assert assets, 'No built JavaScript found'
    for asset in assets:
        assert get(asset), f'Empty asset: {asset}'
    assert json.loads(get('/api/health')) == {'status': 'ok'}
    summary = json.loads(get('/api/baseline/summary'))
    rows = json.loads(get('/api/baseline/predictions'))
    assert len(rows) == summary['evaluated_field_years'] > 0
    assert json.loads(get('/api/fields'))
    assert json.loads(get('/api/fields.geojson'))['features']
    assert json.loads(get('/api/baseline/rollup'))['years']
    row = rows[0]
    assert json.loads(get(f"/api/fields/{row['field_id']}/observations?year={row['year']}"))
    assert json.loads(get('/openapi.json'))['paths']
    request = Request(base + '/api/agent/run', data=b'{"query":"test"}',
                      headers={'Content-Type': 'application/json'})
    try:
        urlopen(request, timeout=30)
    except HTTPError as exc:
        assert exc.code == 501, f'Unexpected agent response: {exc.code}'
    else:
        raise AssertionError('This deployment should explicitly report the missing agent')
    print('Deployment checks passed: frontend, assets, saved data, API, and missing agent.')


if __name__ == '__main__':
    check((sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000').rstrip('/'))
