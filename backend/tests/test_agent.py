"""LangGraph agent (agent/run.py) on real saved outputs, with Nemotron replaced by a script."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent import run as agent  # noqa: E402
from app import tools  # noqa: E402
from app.main import app  # noqa: E402


def call(i, name, **args):
    return {'id': f'c{i}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}


class Script:
    """Stands in for agent.chat: returns queued assistant messages, records what it was sent."""

    def __init__(self, *replies):
        self.replies, self.sent = list(replies), []

    def __call__(self, messages, tool_specs):
        self.sent.append((json.loads(json.dumps(messages)), tool_specs))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class AgentChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for target, value in ((tools, 'TRACES_DIR'), (tools, 'RUNS_DIR')):
            p = patch.object(target, value, Path(self.tmp.name) / value.lower())
            p.start()
            self.addCleanup(p.stop)

    def trace(self, run_id):
        return tools.read_trace(run_id)

    def test_loop_calls_real_tools_and_ends_with_report(self):
        script = Script(
            {'content': None, 'tool_calls': [call(1, 'evaluate', year=2022, as_of='2022-10-12')]},
            {'content': '## BARC 2022 as of Oct 12\nBalanced accuracy 0.833 on 7 field-years [evaluate].'},
        )
        with patch.object(agent, 'chat', script):
            agent.run_agent('Score 2022 as of October 12', 'r-a')
        steps = self.trace('r-a')
        self.assertEqual([(s['node'], s['type']) for s in steps],
                         [('analyst', 'plan'), ('analyst', 'tool_call'), ('tools', 'tool_result'),
                          ('verifier', 'check'), ('writer', 'report')])
        self.assertTrue(steps[2]['ok'])
        self.assertIn('n=7', steps[2]['summary'])
        self.assertIn('0.833', steps[-1]['summary'])
        tool_msg = [m for m in script.sent[1][0] if m['role'] == 'tool'][0]
        self.assertIn('0.8333', tool_msg['content'])  # Nemotron saw the real saved result
        names = {t['function']['name'] for t in script.sent[0][1]}
        self.assertIn('classify', names)
        self.assertNotIn('write_report', names)  # the writer node saves reports, not the model
        self.assertTrue((Path(self.tmp.name) / 'runs_dir' / 'reports' / 'r-a.md').exists())

    def test_verifier_sends_invented_numbers_back_once_then_flags_them(self):
        script = Script(
            {'content': None, 'tool_calls': [call(1, 'evaluate', year=2022)]},
            {'content': 'Accuracy is 0.97 [evaluate].'},
            {'content': 'Accuracy is 0.97 [evaluate].'},
        )
        with patch.object(agent, 'chat', script):
            agent.run_agent('How accurate is 2022?', 'r-b')
        steps = self.trace('r-b')
        flags = [s for s in steps if s['type'] == 'flag']
        self.assertEqual(len(flags), 2)
        self.assertIn('0.97', flags[0]['summary'])
        self.assertIn('0.97', script.sent[2][0][-1]['content'])  # named in the retry request
        self.assertEqual(steps[-1]['type'], 'report')
        self.assertIn('Verifier', steps[-1]['summary'])

    def test_rounded_numbers_pass_invented_ones_do_not(self):
        results = ['{"balanced_accuracy": 0.8333333333333333, "ci": [40.13, 107.28]}']
        self.assertEqual(agent.unsupported_numbers('0.833, about 40 to 107, 2022', results, 'year 2022'), [])
        self.assertEqual(agent.unsupported_numbers('0.91 and 55', results, ''), ['55', '0.91'])

    def test_failure_still_ends_the_trace_with_a_report(self):
        with patch.object(agent, 'chat', Script(agent.AgentError('NVIDIA_API_KEY is not set'))):
            agent.run_agent('anything', 'r-c')
        steps = self.trace('r-c')
        self.assertEqual([s['type'] for s in steps], ['plan', 'error', 'report'])
        self.assertIn('NVIDIA_API_KEY', steps[-1]['summary'])

    def test_tool_the_model_was_not_offered_is_not_run(self):
        # write_report takes a run_id: a model must not be able to overwrite another run's report with it.
        script = Script(
            {'content': None, 'tool_calls': [call(1, 'write_report', run_id='r-other', markdown='hijacked')]},
            {'content': 'Nothing to report.'},
        )
        with patch.object(agent, 'chat', script):
            agent.run_agent('try to write a report', 'r-e')
        result = [s for s in self.trace('r-e') if s['type'] == 'tool_result'][0]
        self.assertFalse(result['ok'])
        self.assertFalse((Path(self.tmp.name) / 'runs_dir' / 'reports' / 'r-other.md').exists())

    def test_tool_round_limit_is_enforced(self):
        # Once MAX_TOOL_ROUNDS is used up no tools are offered; calls the model still makes are not executed.
        forever = {'content': 'Partial answer.', 'tool_calls': [call(1, 'get_fields')]}
        script = Script(*[{'content': None, 'tool_calls': [call(1, 'get_fields')]}] * agent.MAX_TOOL_ROUNDS, forever)
        with patch.object(agent, 'chat', script):
            agent.run_agent('loop', 'r-f')
        steps = self.trace('r-f')
        self.assertEqual(sum(s['type'] == 'tool_result' for s in steps), agent.MAX_TOOL_ROUNDS)
        self.assertEqual(steps[-1]['type'], 'report')
        self.assertIn('Partial answer.', steps[-1]['summary'])
        self.assertIsNone(script.sent[-1][1])  # the last request offered no tools

    def test_api_starts_a_run_and_serves_its_trace(self):
        script = Script({'content': 'No tools needed.'})
        with patch.object(agent, 'chat', script):
            client = TestClient(app)
            r = client.post('/api/agent/run', json={'query': 'hello'})
            self.assertEqual(r.status_code, 200)
            run_id = r.json()['run_id']
            steps = client.get(f'/api/agent/trace/{run_id}').json()  # background task ran with the request
        self.assertEqual(steps[-1]['type'], 'report')

    def test_key_comes_from_env_file_and_is_never_logged(self):
        env = Path(self.tmp.name) / '.env'
        env.write_text('NVIDIA_API_KEY=nvapi-secret-test\nNEMOTRON_MODEL=nvidia/x\n')
        with patch.object(agent, 'ROOT', Path(self.tmp.name)), patch.dict('os.environ', {'NVIDIA_API_KEY': ''}):
            c = agent.config()
        self.assertEqual((c['key'], c['model']), ('nvapi-secret-test', 'nvidia/x'))
        with patch.object(agent, 'chat', Script(agent.AgentError('NVIDIA rejected the API key (HTTP 401).'))):
            agent.run_agent('q', 'r-d')
        self.assertNotIn('nvapi-secret-test', json.dumps(self.trace('r-d')))


if __name__ == '__main__':
    unittest.main()
