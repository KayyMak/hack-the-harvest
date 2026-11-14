"""Start both local services, verify the frontend/API proxy, then stop them.

Run with the backend Python environment after `npm ci` in frontend/.
This checks HTTP integration; it is not a browser rendering test.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def wait_for(url, process):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'Service exited with code {process.returncode}: {url}')
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return response.read().decode()
        except urllib.error.URLError:
            time.sleep(0.2)
    raise RuntimeError(f'Service failed to start: {url}')


def main():
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('Install Node.js first')
    processes = []
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    try:
        backend = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
            '--app-dir', 'backend', '--host', '127.0.0.1', '--port', '8000'],
            cwd=ROOT, creationflags=flags, stdout=subprocess.DEVNULL)
        processes.append(backend)
        assert json.loads(wait_for('http://127.0.0.1:8000/api/health', backend)) == {'status': 'ok'}
        frontend = subprocess.Popen([node, 'node_modules/vite/bin/vite.js',
            '--host', '127.0.0.1'], cwd=ROOT / 'frontend', creationflags=flags,
            stdout=subprocess.DEVNULL)
        processes.append(frontend)
        html = wait_for('http://127.0.0.1:5173', frontend)
        assert '<title>Hack the Harvest</title>' in html
        summary = json.loads(wait_for('http://127.0.0.1:5173/api/baseline/summary', frontend))
        rows = json.loads(wait_for('http://127.0.0.1:5173/api/baseline/predictions', frontend))
        expected = json.loads((ROOT / 'baseline/outputs/metrics.json').read_text())
        assert summary['logistic'] == expected['logistic']
        assert len(rows) == summary['evaluated_field_years']
        print(f'PASS: frontend HTML, proxied metrics, and {len(rows)} held-out predictions.')
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    main()
