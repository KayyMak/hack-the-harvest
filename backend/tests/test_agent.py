"""LangGraph agent (agent/run.py) on real saved outputs, with Nemotron replaced by a script."""
import io
import json
import sys
import tempfile
import urllib.error
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
        # Still unsupported after the retry: removed from the report (no warning footer), noted in the trace.
        self.assertNotIn('0.97', steps[-1]['summary'])
        self.assertNotIn('Verifier', steps[-1]['summary'])
        self.assertIn('Summary of tool results', steps[-1]['summary'])  # nothing left: the tool-result summary
        self.assertIn('removed 1 sentence', steps[-2]['summary'])

    def test_unsupported_sentences_are_removed_and_supported_ones_kept(self):
        fc = json.dumps(agent.harvest_tools.call('forecast_2025', {}))
        script = Script(
            {'content': None, 'tool_calls': [call(1, 'forecast_2025')]},
            {'content': '## 2025 Maryland silage\n### Findings\n- Maryland silage estimate: 31.5 acres [forecast_2025]\n'
                        '- CI 22.1 to 40.9 [forecast_2025]\n### Uncertainty\n- Invented spread 12.34 [forecast_2025]\n'
                        '### Sources (tools used)\n- forecast_2025'},
            {'content': '## 2025 Maryland silage\n### Findings\n- Maryland silage estimate: 36,648 acres, CV 22% '
                        '[forecast_2025].\nThat is solid [forecast_2025]. Still 31.5 acres somewhere.\n'
                        '- The calls were as follows:\n'
                        '  - field 9999: 0.4242 [classify]\n### Uncertainty\n- Invented spread 12.34 [forecast_2025]\n'
                        '### Sources (tools used)\n- forecast_2025\n\n| region | acres [forecast_2025] |\n|---|---|\n'
                        '| Maryland | 31.5 |'},
        )
        with patch.object(agent, 'chat', script):
            agent.run_agent('What is our 2025 Maryland silage estimate and how sure are we?', 'r-drop')
        steps = self.trace('r-drop')
        self.assertIn('36648', fc)
        report = steps[-1]['summary']
        self.assertEqual(steps[-1]['type'], 'report')
        self.assertIn('36,648 acres, CV 22%', report)  # supported bullet kept (whole bullet is one unit)
        self.assertIn('That is solid [forecast_2025].', report)  # prose: only the unsupported sentence goes
        for gone in ('31.5', '12.34', '9999', '0.4242', 'as follows', '| region', '|---|', 'Verifier'):
            self.assertNotIn(gone, report)
        self.assertIn('### Uncertainty\nNot available from the tools.', report)
        self.assertIn('### Findings', report)
        self.assertTrue(report.startswith('## 2025 Maryland silage'))

    def test_drop_unsupported_splits_prose_and_keeps_headings(self):
        results = ['{"balanced_accuracy": 0.69}']
        out, removed = agent.drop_unsupported('## Rule\nThe rule scored 0.69 [x]. The model scored 0.95 [x].\n## Next\n- 7.7 [x]',
                                              results, '')
        self.assertEqual(out, '## Rule\nThe rule scored 0.69 [x].\n## Next\nNot available from the tools.')
        self.assertEqual(removed, ['The model scored 0.95 [x].', '- 7.7 [x]'])

    def test_forecast_2025_tool_returns_the_submitted_forecast(self):
        out = agent.harvest_tools.call('forecast_2025', {})
        self.assertNotIn('error', out)
        self.assertEqual((out['year'], out['state']), (2025, 'MARYLAND'))
        self.assertEqual(out['maryland']['silage'], 36648)
        for k in ('silage_se', 'silage_cv_pct', 'silage_low', 'silage_high', 'grain', 'grain_low', 'grain_high'):
            self.assertIn(k, out['maryland'])
            self.assertIn(k, out['us'])
        self.assertIn('before January 2026', out['note'])
        self.assertIn('method', out)
        self.assertIn('silage', out['nass_2025_final']['maryland'])
        self.assertEqual(out['margin_of_error']['silage']['rmse_pct'], 3.9)
        self.assertEqual(out['margin_of_error']['grain']['margin90_pct'], 1.7)
        self.assertEqual(agent.harvest_tools.call('forecast_2025', {'state': 'iowa'})['state'], 'IOWA')
        self.assertIn('error', agent.harvest_tools.call('forecast_2025', {'state': 'ATLANTIS'}))
        self.assertEqual(agent.harvest_tools.call('forecast_2025', {'state': 'US'})['state'], 'MARYLAND')
        names = {t['function']['name'] for t in agent.tool_specs()}
        self.assertTrue({'forecast_2025', 'decline_rule_baseline'} <= names)
        summary = agent._summary(out)  # trace line and fallback-report finding
        self.assertIn('MARYLAND silage=36648', summary)
        self.assertIn('US silage=', summary)
        rule = agent._summary(agent.harvest_tools.call('decline_rule_baseline', {}))
        self.assertIn('decline rule balanced_accuracy=0.69', rule)
        self.assertIn('model balanced_accuracy=0.90', rule)
        self.assertIn('n=44', rule)

    def test_forecast_2025_without_the_dashboard_reliability_file(self):
        with patch.object(agent.harvest_tools, 'RELIABILITY_JSON', Path(self.tmp.name) / 'missing.json'):
            out = agent.harvest_tools.call('forecast_2025', {})
        self.assertNotIn('error', out)
        self.assertNotIn('margin_of_error', out)
        self.assertEqual(out['maryland']['silage'], 36648)

    def test_decline_rule_baseline_tool_returns_the_saved_comparison(self):
        out = agent.harvest_tools.call('decline_rule_baseline', {})
        self.assertNotIn('error', out)
        self.assertAlmostEqual(out['decline_rule']['balanced_accuracy'], 0.6927, places=4)
        self.assertAlmostEqual(out['logistic_same_rows']['balanced_accuracy'], 0.9010, places=4)
        self.assertEqual(out['evaluated_field_years'], 44)
        self.assertIn('Season-end', out['scope'])
        self.assertIn('error', agent.harvest_tools.call('decline_rule_baseline', {'as_of': '2022-10-12'}))

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

    def test_tool_arguments_that_are_not_an_object_are_a_tool_error_not_a_crash(self):
        bad = {'id': 'c1', 'type': 'function', 'function': {'name': 'evaluate', 'arguments': '[2022]'}}
        script = Script({'content': None, 'tool_calls': [bad]}, {'content': 'Could not evaluate.'})
        with patch.object(agent, 'chat', script):
            agent.run_agent('score 2022', 'r-g')
        steps = self.trace('r-g')
        self.assertNotIn('error', [s['type'] for s in steps])
        result = next(s for s in steps if s['type'] == 'tool_result')
        self.assertFalse(result['ok'])
        self.assertIn('JSON object', result['summary'])
        self.assertEqual(steps[-1]['type'], 'report')
        self.assertIn('Could not evaluate.', steps[-1]['summary'])

    def test_tool_calls_per_round_are_capped_with_a_note(self):
        many = [call(i, 'get_fields') for i in range(agent.MAX_CALLS_PER_ROUND + 3)]
        script = Script({'content': None, 'tool_calls': many}, {'content': 'Done.'})
        with patch.object(agent, 'chat', script):
            agent.run_agent('fields', 'r-h')
        steps = self.trace('r-h')
        self.assertEqual(sum(s['type'] == 'tool_result' for s in steps), agent.MAX_CALLS_PER_ROUND)
        self.assertTrue(any('only the first' in (s.get('summary') or '') for s in steps if s['type'] == 'plan'))
        sent = script.sent[1][0]
        self.assertEqual(len(sent[2]['tool_calls']), agent.MAX_CALLS_PER_ROUND)  # each kept call has a reply
        self.assertEqual(sum(m['role'] == 'tool' for m in sent), agent.MAX_CALLS_PER_ROUND)

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


class MalformedToolCallNames(unittest.TestCase):
    """A malformed model reply (non-string name, missing function) is a tool error, never a crash."""

    def test_non_string_and_missing_names_become_tool_errors(self):
        import importlib
        run = importlib.import_module('agent.run')
        state = {'run_id': 'r-malformed', 'messages': [], 'pending': [
            {'id': 'a', 'function': {'name': ['x'], 'arguments': '{}'}},
            {'id': 'b', 'function': None},
            {'id': 'c'},
        ]}
        with patch.object(run, 'log_step'):
            out = run.run_tools(state)
        replies = [m for m in out['messages'] if m.get('role') == 'tool']
        self.assertEqual(len(replies), 3)
        self.assertTrue(all('unknown tool' in m['content'] for m in replies))

    def test_market_run_tool_rejects_non_string_names(self):
        from app import market
        self.assertIn('error', market.run_tool(['x'], {}))
        self.assertIn('error', market.run_tool({'a': 1}, {}))


def nvidia_reply(message):
    return io.BytesIO(json.dumps({'choices': [{'message': message}]}).encode())


def http_error(code, headers=None):
    return urllib.error.HTTPError('https://x/v1/chat/completions', code, 'err', headers or {}, io.BytesIO(b'{"detail":"x"}'))


def scripted_urlopen(replies, attempts=None):
    def urlopen(req, timeout):
        if attempts is not None:
            attempts.append(req.full_url)
        r = replies.pop(0) if len(replies) > 1 else replies[0]
        if isinstance(r, Exception):
            raise r
        return r
    return urlopen


TEXT_CALL = """<tool_call>
<function=evaluate>
<parameter=year>
2022
</parameter>
</function>
</tool_call>"""


class Reliability(AgentChecks):
    """Failures seen against the live NVIDIA model, replayed with scripted replies."""

    def report(self, run_id):
        return self.trace(run_id)[-1]['summary']

    # ---- 1. tool calls written as text
    def test_tag_style_text_tool_call_is_run_as_a_real_call(self):
        script = Script({'content': TEXT_CALL}, {'content': '## 2022\n### Findings\n- Balanced accuracy 0.83 [evaluate].'})
        with patch.object(agent, 'chat', script):
            agent.run_agent('Score 2022', 'r-t1')
        steps = self.trace('r-t1')
        result = next(s for s in steps if s['type'] == 'tool_result')
        self.assertEqual((result['tool'], result['args'], result['ok']), ('evaluate', {'year': 2022}, True))
        self.assertTrue(any('as text' in (s.get('summary') or '') for s in steps if s['type'] == 'plan'))
        sent = script.sent[1][0]
        self.assertNotIn('<tool_call>', json.dumps(sent[1:]))  # the stored assistant turn is clean
        self.assertEqual(sum(m['role'] == 'tool' for m in sent), 1)
        self.assertNotIn('tool_call', self.report('r-t1'))

    def test_json_text_tool_call_is_parsed_and_unoffered_names_are_refused(self):
        script = Script({'content': 'Calling: {"name": "evaluate", "arguments": {"year": 2022}}'},
                        {'content': '<tool_call><function=write_report><parameter=run_id>r-x</parameter></function></tool_call>'},
                        {'content': '## Done\n### Findings\n- n=7 [evaluate].'})
        with patch.object(agent, 'chat', script):
            agent.run_agent('Score 2022', 'r-t2')
        results = [s for s in self.trace('r-t2') if s['type'] == 'tool_result']
        self.assertEqual([(r['tool'], r['ok']) for r in results], [('evaluate', True), ('write_report', False)])
        self.assertFalse((Path(self.tmp.name) / 'runs_dir' / 'reports' / 'r-x.md').exists())
        self.assertEqual(self.report('r-t2'), '## Done\n### Findings\n- n=7 [evaluate].')

    def test_markup_after_the_round_limit_is_stripped_and_the_report_re_asked(self):
        rounds = [{'content': None, 'tool_calls': [call(1, 'evaluate', year=2022)]}] * agent.MAX_TOOL_ROUNDS
        script = Script(*rounds, {'content': TEXT_CALL}, {'content': '## 2022\n### Findings\n- n=7 [evaluate].'})
        with patch.object(agent, 'chat', script):
            agent.run_agent('Score 2022', 'r-t3')
        self.assertEqual(sum(s['type'] == 'tool_result' for s in self.trace('r-t3')), agent.MAX_TOOL_ROUNDS)
        self.assertIsNone(script.sent[-1][1])  # the re-ask offers no tools
        self.assertIn('Do not call tools', script.sent[-1][0][-1]['content'])
        self.assertEqual(self.report('r-t3'), '## 2022\n### Findings\n- n=7 [evaluate].')

    def test_writer_falls_back_to_a_tool_summary_when_the_re_ask_also_fails(self):
        script = Script({'content': None, 'tool_calls': [call(1, 'evaluate', year=2022)]},
                        {'content': ''}, {'content': TEXT_CALL.replace('evaluate', 'not_a_tool')})
        with patch.object(agent, 'chat', script):
            agent.run_agent('Score 2022', 'r-t4')
        report = self.report('r-t4')
        for bad in ('<tool_call', '<function', '<parameter', 'not_a_tool'):
            self.assertNotIn(bad, report)
        self.assertIn(agent.FALLBACK, report)
        self.assertIn('n=7', report)
        self.assertIn('balanced_accuracy=0.83', report)  # long float rounded
        self.assertEqual([s['type'] for s in self.trace('r-t4')][-2:], ['check', 'report'])  # verifier passed it
        self.assertFalse(any(ch.isdigit() for ch in agent.FALLBACK))

    def test_strip_and_parse_helpers(self):
        from app import llm_guard
        prose = 'Here is the plan.\n' + TEXT_CALL + '\nDone.'
        self.assertEqual(llm_guard.strip_tool_markup(prose), 'Here is the plan.\n\nDone.')
        self.assertEqual(llm_guard.text_tool_calls(TEXT_CALL, {'evaluate'}), [('evaluate', {'year': 2022})])
        fenced = '```json\n{"name": "aggregate", "arguments": {"year": "2023"}}\n```'
        self.assertEqual(llm_guard.text_tool_calls(fenced, {'aggregate'}), [('aggregate', {'year': '2023'})])
        self.assertEqual(llm_guard.strip_tool_markup(fenced), '')
        self.assertEqual(llm_guard.text_tool_calls('{"name": "x", "arguments": {}}', {'aggregate'}), [])
        self.assertFalse(llm_guard.has_tool_markup('| a | b |\n**bold** {not json}', {'aggregate'}))

    # ---- 2. retries
    def configured(self):
        return patch.object(agent, 'config', lambda: {'key': 'k', 'base': 'https://x/v1', 'model': 'm', 'thinking': False})

    def test_429_is_retried_with_backoff_and_logged_to_the_trace(self):
        from app import llm_guard
        sleeps = []
        urlopen = scripted_urlopen([http_error(429, {'Retry-After': '3'}), nvidia_reply({'content': 'No tools needed.'})])
        with self.configured(), patch.object(llm_guard.urllib.request, 'urlopen', urlopen), \
                patch.object(llm_guard, '_sleep', sleeps.append):
            agent.run_agent('hello', 'r-r1')
        steps = self.trace('r-r1')
        retry = next(s for s in steps if s['type'] == 'retry')
        self.assertIn('HTTP 429', retry['summary'])
        self.assertEqual(len(sleeps), 1)
        self.assertGreaterEqual(sleeps[0], 3)  # Retry-After honoured
        self.assertEqual(steps[-1]['summary'], 'No tools needed.')
        self.assertNotIn('Bearer', json.dumps(steps))

    def test_auth_errors_are_not_retried_and_waits_are_capped(self):
        from app import llm_guard
        sleeps, attempts = [], []
        with self.configured(), patch.object(llm_guard.urllib.request, 'urlopen', scripted_urlopen([http_error(401)], attempts)), \
                patch.object(llm_guard, '_sleep', sleeps.append):
            agent.run_agent('q', 'r-r2')
        self.assertEqual((len(attempts), sleeps), (1, []))
        self.assertIn('rejected the API key', self.report('r-r2'))

        attempts.clear()
        with self.configured(), \
                patch.object(llm_guard.urllib.request, 'urlopen', scripted_urlopen([http_error(503, {'Retry-After': '25'})], attempts)), \
                patch.object(llm_guard, '_sleep', sleeps.append):
            agent.run_agent('q', 'r-r3')
        self.assertTrue(sleeps)
        self.assertLessEqual(sum(sleeps), llm_guard.RETRY_MAX_WAIT)
        self.assertLessEqual(len(attempts), llm_guard.RETRY_ATTEMPTS)
        self.assertIn('HTTP 503', self.report('r-r3'))

    def test_timeouts_and_connection_errors_are_retried(self):
        from app import llm_guard
        urlopen = scripted_urlopen([TimeoutError('timed out'), urllib.error.URLError(ConnectionResetError()),
                                    nvidia_reply({'content': 'ok'})])
        with self.configured(), patch.object(llm_guard.urllib.request, 'urlopen', urlopen), \
                patch.object(llm_guard, '_sleep', lambda s: None):
            agent.run_agent('q', 'r-r4')
        self.assertEqual(sum(s['type'] == 'retry' for s in self.trace('r-r4')), 2)
        self.assertEqual(self.report('r-r4'), 'ok')

    # ---- 3. bad argument strings
    def test_null_ish_arguments_are_dropped_and_int_strings_coerced(self):
        script = Script({'content': None, 'tool_calls': [call(1, 'evaluate', year='2022', as_of='none'),
                                                          call(2, 'aggregate', year=2022, as_of='N/A')]},
                        {'content': 'Done.'})
        with patch.object(agent, 'chat', script):
            agent.run_agent('Score 2022', 'r-a1')
        results = [s for s in self.trace('r-a1') if s['type'] == 'tool_result']
        self.assertEqual([(r['args'], r['ok']) for r in results], [({'year': 2022}, True), ({'year': 2022}, True)])

    def test_clean_args_helper(self):
        from app import llm_guard
        self.assertEqual(llm_guard.clean_args({'year': ' 2022 ', 'as_of': 'NULL', 'x': '', 'field_ids': '[231, 252]',
                                               'q': 'none of it'}, {'year': 'int', 'field_ids': 'list'}),
                         {'year': 2022, 'field_ids': [231, 252], 'q': 'none of it'})

    # ---- 4. verifier
    def test_verifier_accepts_percent_rounding_and_interval_levels(self):
        ev = json.dumps(agent.harvest_tools.call('evaluate', {'year': 2022}))
        agg = json.dumps(agent.harvest_tools.call('aggregate', {'year': 2022}))
        counts = json.dumps({'n_fields': 19, 'n_pending': 4, 'tpr': 0.782, 'share': 0.503})
        ok = ('In 2022, 95% interval 32.3 to 104.8 acres; the Wilson 95% CI; a 90% range. TPR 78.2% and 50.3 percent; '
              '19 fields, 4 pending. Balanced accuracy 0.83, CV 27%.')
        self.assertEqual(agent.unsupported_numbers(ok, [ev, agg, counts], ''), [])

    def test_verifier_still_rejects_invented_numbers(self):
        counts = json.dumps({'n_fields': 19, 'n_pending': 4, 'tpr': 0.782})
        draft = 'TPR 78.3% and 0.78 is 79 in all; 95 fields; 3/7 correct; 0.5902900420064867; 2041; field 347-ish.'
        self.assertEqual(agent.unsupported_numbers(draft, [counts], ''),
                         ['3', '7', '79', '95', '347', '2041', '78.3', '0.5902900420064867'])
        # A real classify result is full of field ids: they must not make arbitrary integers reachable.
        cls = json.dumps(agent.harvest_tools.call('classify', {'year': 2022}), default=str)
        self.assertEqual(agent.unsupported_numbers('Fields 347 and 500 total 612 acres.', [cls], ''), ['347', '500', '612'])

    def test_verifier_rejects_derived_counts_and_free_years(self):
        # Derived counts are not accepted: a wrong "5 of 7 correct" could be built from 1 + 4 in a confusion matrix.
        counts = json.dumps({'n': 7, 'confusion_matrix': [[2, 1], [0, 4]]})
        self.assertEqual(agent.unsupported_numbers('5 of 7 correct; 2031 acres.', [counts], ''), ['5', '2031'])
        self.assertEqual(agent.unsupported_numbers('In 2022, 7 field-years.', [counts], 'Score 2022'), [])

    # ---- 5. report format
    def test_long_floats_are_rounded_and_prompt_has_the_report_rules(self):
        script = Script({'content': None, 'tool_calls': [call(1, 'evaluate', year=2022)]},
                        {'content': '## 2022\n### Findings\n- Balanced accuracy 0.8333333333333333 [evaluate].'})
        with patch.object(agent, 'chat', script):
            agent.run_agent('Score 2022', 'r-f1')
        self.assertIn('0.83 [evaluate]', self.report('r-f1'))
        self.assertNotIn('0.8333', self.report('r-f1'))
        system = script.sent[0][0][0]['content']
        for rule in ('### Findings', '### Uncertainty', '### Sources (tools used)', 'not available', '2 decimals',
                     'Bernoulli', 'Never write a tool call as text'):
            self.assertIn(rule, system)
        from app import llm_guard
        self.assertEqual(llm_guard.round_long_floats('p=0.5902900420064867, 12.345678, 0.000012345, 0.1234, 2022-10-12'),
                         'p=0.59, 12.35, 0.00001, 0.1234, 2022-10-12')



class ModelCallLimits(unittest.TestCase):
    """One model call is bounded in total time and never waits forever for a busy slot."""

    def test_busy_slot_times_out_with_a_clear_error(self):
        import urllib.request
        from app import llm_guard
        with patch.object(llm_guard, 'SLOT_WAIT', 0.05), patch.object(llm_guard, 'MODEL_SLOTS', llm_guard.threading.BoundedSemaphore(1)) as slots:
            slots.acquire()
            try:
                with self.assertRaisesRegex(TimeoutError, 'busy'):
                    llm_guard.post_json(urllib.request.Request('http://127.0.0.1:9/never'), 1)
            finally:
                slots.release()

    def test_total_deadline_stops_retrying(self):
        import urllib.request
        from app import llm_guard
        with patch.object(llm_guard, 'RETRY_DEADLINE', 0.0):
            with self.assertRaisesRegex(TimeoutError, 'within'):
                llm_guard.post_json(urllib.request.Request('http://127.0.0.1:9/never'), 1)


if __name__ == '__main__':
    unittest.main()
