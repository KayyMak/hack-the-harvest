"""The documented sample trace stays readable by the trace route and in the agreed format."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

SAMPLE = Path(__file__).resolve().parents[2] / 'docs' / 'samples' / 'agent_trace_sample.jsonl'
NODES = {'analyst', 'tools', 'verifier', 'writer'}
TYPES = {'plan', 'tool_call', 'tool_result', 'flag', 'retrieve', 'check', 'report', 'error'}


class TraceSample(unittest.TestCase):
    def test_sample_served_by_trace_route(self):
        with tempfile.TemporaryDirectory() as directory:
            shutil.copy(SAMPLE, Path(directory) / 'r-sample.jsonl')
            with patch('app.tools.TRACES_DIR', Path(directory)):
                steps = TestClient(app).get('/api/agent/trace/r-sample').json()
        self.assertEqual(len(steps), len(SAMPLE.read_text(encoding='utf-8').splitlines()))
        self.assertEqual([s['step'] for s in steps], list(range(1, len(steps) + 1)))
        for s in steps:
            self.assertEqual(s['run_id'], 'r-sample')
            self.assertIn(s['node'], NODES)
            self.assertIn(s['type'], TYPES)
        self.assertEqual(steps[-1]['type'], 'report')
        self.assertTrue({'retrieve', 'flag', 'tool_result'} <= {s['type'] for s in steps})


if __name__ == '__main__':
    unittest.main()
