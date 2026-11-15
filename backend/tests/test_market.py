"""Market report routes against real saved outputs, with the NVIDIA API replaced by a script."""
import io
import json
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import market
from app.main import app

FAKE_KEY = 'nvapi-test-not-a-real-key'
VERIFIED = {'content': '{"results": []}'}  # verifier pass: nothing rejected
IN_SEASON_DOCS = {'data_sources.md', 'market/README.md'}  # methods/data-source docs: no results, no labels


def tool_call(i, name, **args):
    return {'id': f'c{i}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}


class ScriptedNvidia:
    """Replaces market._post: returns queued chat replies and records every request."""

    def __init__(self, replies, models=()):
        self.replies, self.models, self.requests = list(replies), list(models), []

    def __call__(self, cfg, path, payload, timeout=120):
        self.requests.append((path, payload))
        if path == '/models':
            return {'data': [{'id': m} for m in self.models]}
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return {'choices': [{'message': reply}]}


def http_error(code, body):
    return urllib.error.HTTPError('https://x/v1/chat/completions', code, 'err', {}, io.BytesIO(body.encode()))


class MarketChecks(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.tmp = tempfile.TemporaryDirectory()
        self.env = Path(self.tmp.name) / '.env'
        patcher = patch.object(market, 'ENV_FILE', self.env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict('os.environ', {'NVIDIA_API_KEY': '', 'NEMOTRON_MODEL': '', 'NEMOTRON_BASE_URL': ''})
        env.start()
        self.addCleanup(env.stop)

    def configure(self):
        self.env.write_text(f'NVIDIA_API_KEY={FAKE_KEY}\nNEMOTRON_MODEL=nvidia/test-model\n')

    def report(self, script, as_of=None):
        with patch.object(market, '_post', script):
            # Default: 2023 season as of its last model call (2023-11-30, in-season): official 2022 NASS figures
            # are known by then. as_of='2023-12-31' is a post-season report.
            return self.client.post('/api/market/report', json={'year': 2023, **({'as_of': as_of} if as_of else {})})

    # ---- configuration

    def test_status_reflects_env_file_without_restart_and_never_returns_key(self):
        self.assertFalse(self.client.get('/api/market/status').json()['configured'])
        self.configure()
        body = self.client.get('/api/market/status')
        self.assertTrue(body.json()['configured'])
        self.assertEqual(body.json()['model'], 'nvidia/test-model')
        self.assertNotIn(FAKE_KEY, body.text)

    def test_missing_key_is_a_503_with_instructions(self):
        r = self.client.post('/api/market/report', json={'year': 2022})
        self.assertEqual(r.status_code, 503)
        self.assertIn('NVIDIA_API_KEY', r.json()['detail'])

    # ---- tools read our data only

    def test_tools_use_real_nass_and_saved_predictions(self):
        s = market.maryland_supply(2022)
        self.assertEqual(s['maryland_silage_acres_harvested'], '40,000')    # NASS Crop Production 2024 Summary (revised 2022)
        self.assertEqual(s['maryland_grain_price_received'], '$6.53/bu')    # Crop Values
        self.assertEqual(market.barc_predictions(2022)['labeled_field_years'], 7)
        self.assertEqual(market.price_effect(2022, 'one_point_of_maryland_silage_share')['grain_bushels_shifted'], '660,000')

    def test_2025_outlook_month_by_month_uses_only_what_was_known(self):
        r = self.client.get('/api/market/outlook', params={'season': 2025, 'as_of': '2025-09-12'})
        self.assertEqual(r.status_code, 200, r.text)
        t = r.json()['timeline']
        self.assertEqual([x['as_of'] for x in t['earlier_releases']], ['2025-06-30', '2025-08-12'])
        sep = t['latest_release']                                                    # no Nov: not yet published
        self.assertEqual(sep['as_of'], '2025-09-12')
        self.assertEqual(sep['us_grain_production_forecast'], '16,814,371,000 bu')   # NASS Sep 12 forecast
        self.assertEqual(sep['us_grain_supply_change_vs_2024'], '+13.1%')
        self.assertEqual(sep['us_silage_acres_estimate'], '6,507,289')               # team forecast as of Sep 12
        self.assertIn('acres only', t['earlier_releases'][0]['note'])                 # June: no yield forecast yet
        self.assertEqual(len(t['series']), 3)
        june = self.client.get('/api/market/outlook', params={'season': 2025, 'as_of': '2025-06-01'})
        self.assertEqual(june.status_code, 422)

    def test_in_season_report_cannot_see_later_data(self):
        token = market._AS_OF.set(date(2022, 9, 12))
        try:
            self.assertIn('unknown as of 2022-09-12', market.run_tool('maryland_supply', {'year': 2022})['error'])
            self.assertEqual(market.run_tool('maryland_supply', {'year': 2021})['maryland_silage_acres_harvested'], '35,000')
            self.assertIn('error', market.run_tool('model_field_calls', {'year': 2022, 'month_day': '10-12'}))
            conv = market.run_tool('season_convergence', {'year': 2022})
            self.assertEqual([p['as_of'] for p in conv['points']], ['2022-08-12', '2022-09-12'])
            self.assertEqual(market.season_timeline(2022)['latest_official_baseline']['year'], 2021)
            # Ground-truth labels are recorded after harvest: hidden from in-season tools.
            barc = market.barc_predictions(2022)
            self.assertNotIn('reference_silage_acres_from_barc_labels', barc)
            self.assertIn('not known yet', barc['labels'])
            self.assertNotIn('reference_silage_acres', json.dumps(conv))
            calls = market.model_field_calls(2022, '09-12')
            self.assertNotIn('barc_label', json.dumps(calls))
            self.assertNotIn('barc_reference_silage_acres', json.dumps(market.season_timeline(2022)['series']))
            outlook = market.planting_outlook()
            self.assertEqual([h['year'] for h in outlook['maryland_actual_nass']], [2020, 2021])  # 2021 out Feb 2022
        finally:
            market._AS_OF.reset(token)

    def test_in_season_doc_search_cannot_return_results_or_labels(self):
        # docs/MODEL_REVIEW.md#2 lists true labels for 231/2022 and 252/2022 and per-year results; with as-of
        # 2022-09-12 it used to come back. In-season, only methods/data-source documents may be searched.
        for d in (date(2022, 9, 12), date(2023, 11, 30), date(2025, 9, 12)):
            with self.subTest(as_of=d):
                token = market._AS_OF.set(d)
                try:
                    for q in market.FALLBACK_QUERIES + ('true labels 231 2022 252 2022 per-year results',
                                                        'balanced accuracy recall confusion matrix held-out',
                                                        'MODEL_REVIEW model review experiments verified source labels'):
                        out = market.run_tool('search_project_docs', {'query': q})
                        self.assertEqual({p['source'] for p in out['passages']} - IN_SEASON_DOCS, set(), q)
                        self.assertNotIn('MODEL_REVIEW', json.dumps(out['passages']))
                        self.assertIn('project results are hidden for in-season runs', out['hidden'].lower())
                finally:
                    market._AS_OF.reset(token)

    def test_in_season_barc_predictions_withhold_accuracy(self):
        # Accuracy figures are computed from the 2021-2023 labels: unknown on any in-season date, even for a
        # season whose own labels are already known (2022, as of 2023-11-30).
        for d, year in ((date(2022, 9, 12), 2022), (date(2023, 11, 30), 2022), (date(2023, 11, 30), 2023)):
            with self.subTest(as_of=d, year=year):
                token = market._AS_OF.set(d)
                try:
                    out = market.run_tool('barc_predictions', {'year': year})
                finally:
                    market._AS_OF.reset(token)
                text = json.dumps(out).lower()
                for k in ('model_reliability_all_years', 'balanced_accuracy', 'recall', 'precision', 'caught', 'missed'):
                    self.assertNotIn(k, text)
                self.assertIn('withheld until after harvest', out['model_reliability'])
                self.assertIn('model_expected_silage_acres', out)

    def test_post_season_runs_keep_results_and_accuracy(self):
        for d in (None, date(2023, 12, 31)):
            with self.subTest(as_of=d):
                token = market._AS_OF.set(d)
                try:
                    docs = market.search_project_docs('true labels 231 2022 252 2022 per-year results')
                    barc = market.barc_predictions(2023)
                finally:
                    market._AS_OF.reset(token)
                self.assertIn('docs/MODEL_REVIEW.md', {p['source'] for p in docs['passages']})
                self.assertNotIn('hidden', docs)
                self.assertIn('balanced_accuracy', barc['model_reliability_all_years'])
                self.assertIn('reference_silage_acres_from_barc_labels', barc)

    def test_in_season_report_only_retrieves_and_lists_methods_documents(self):
        self.configure()
        script = ScriptedNvidia([http_error(400, '{"detail":"tools are not supported for this model"}'),
                                 {'content': '## Bottom line\nMaryland: 40,000 silage acres [maryland_supply].'}, VERIFIED])
        body = self.report(script).json()  # 2023-11-30: in-season
        context = script.requests[-2][1]['messages'][-1]['content']  # pre-fetched tool results sent to the model
        for doc in ('MODEL_REVIEW', 'ML_EXPERIMENTS', 'baseline/README.md', 'results.md', 'balanced_accuracy'):
            self.assertNotIn(doc, context)
        self.assertIn('withheld until after harvest', context)
        docs_line = next(s for s in body['sources'] if s.startswith('Project documents: '))
        self.assertEqual(set(docs_line.removeprefix('Project documents: ').split(', ')), IN_SEASON_DOCS)

    def test_missing_field_acres_is_an_error_not_zero(self):
        fields = [f for f in market.artifacts.read_fields() if f.field_id != 279]
        with patch.object(market.artifacts, 'read_fields', lambda: fields):
            out = market.run_tool('model_field_calls', {'year': 2022, 'month_day': '10-12'})
        self.assertIn('279', out['error'])

    def test_model_inference_tool_reads_saved_held_out_calls(self):
        out = market.model_field_calls(2022, '10-12')
        self.assertEqual(out['fields_called'], 7)
        f279 = next(f for f in out['fields'] if f['field_id'] == 279)
        self.assertEqual((f279['model_call'], f279['barc_label']), ('Silage', 'Grain'))
        self.assertIn('error', market.run_tool('model_field_calls', {'year': 2022, 'month_day': '07-01'}))

    def test_trend_is_spelled_out(self):
        t = market.season_convergence(2022)['trend']
        self.assertIn('narrowed', t['range_width_change'])
        self.assertEqual(t['highest_estimate'], '74 acres on 2022-10-12')

    def test_doc_search_returns_citable_passages_from_project_docs(self):
        out = market.search_project_docs('model limitations single site')
        self.assertTrue(out['passages'])
        for p in out['passages']:
            self.assertRegex(p['id'], r'^[\w./-]+#\d+$')
            self.assertIn(p['source'], market.docsearch.corpus_files())
        self.assertEqual(market.search_project_docs('zzqqxx')['passages'], [])

    # ---- grounding check

    def test_number_must_come_from_the_cited_source_not_any_source(self):
        ev = market._Evidence()
        ev.add_tool('maryland_supply', {'year': 2022}, market.maryland_supply(2022))
        ev.add_tool('planting_outlook', {}, market.planting_outlook())
        ok = 'Maryland harvested 40,000 silage acres [maryland_supply].'
        wrong = 'Maryland harvested 36,648 silage acres [maryland_supply].'  # real number, but from planting_outlook
        self.assertEqual(market.check_grounding(ok, ev.sources), [])
        flag = market.check_grounding(wrong, ev.sources)[0]
        self.assertEqual((flag['kind'], flag['reason']), ('miscited', 'correct figure, wrong citation: 36648 is in [planting_outlook]'))
        invented = market.check_grounding('Maryland harvested 12,345 silage acres [maryland_supply].', ev.sources)[0]
        self.assertEqual((invented['kind'], invented['reason']), ('unsupported', 'numbers not found in any retrieved data: 12345'))

    def test_sentence_inherits_citations_on_its_line_but_numbers_still_checked(self):
        ev = market._Evidence()
        ev.add_tool('maryland_supply', {'year': 2022}, market.maryland_supply(2022))
        line = 'Maryland harvested 40,000 silage acres. That is 10.0% of harvested corn. [maryland_supply]'
        self.assertEqual(market.check_grounding(line, ev.sources), [])
        line = 'Maryland harvested 41,000 silage acres. That is 10.0% of harvested corn. [maryland_supply]'
        self.assertIn('41000', market.check_grounding(line, ev.sources)[0]['reason'])
        self.assertEqual(market.check_grounding('No citation anywhere on this line.', ev.sources)[0]['reason'], 'no citation')

    def test_miscited_figures_are_kept_but_flagged(self):
        self.configure()
        line = 'Maryland grain sold for $6.53/bu [planting_outlook].'  # 6.53 is only in maryland_supply
        script = ScriptedNvidia([
            {'content': None, 'tool_calls': [tool_call(1, 'maryland_supply', year=2022), tool_call(2, 'planting_outlook')]},
            {'content': line}, VERIFIED, {'content': line}, VERIFIED,
        ])
        body = self.report(script).json()
        flag = body['grounding']['ungrounded'][0]
        self.assertEqual((flag['kind'], flag['removed']), ('miscited', False))
        self.assertEqual(body['markdown'], line)

    def test_numbers_from_another_scenario_are_caught(self):
        ev = market._Evidence()
        for sc in ('one_point_of_maryland_silage_share', 'barc_model_error_applied_statewide'):
            ev.add_tool('price_effect', {'year': 2022, 'scenario': sc}, market.price_effect(2022, sc))
        # A figure from the model-error scenario, cited as the one-point scenario. Read from the current
        # model's output (not hard-coded) so the test holds whichever saved model version is in use.
        other = market.price_effect(2022, 'barc_model_error_applied_statewide')['grain_bushels_shifted']
        mixed = f'One point of share is {other} bushels [price_effect.one_point_of_maryland_silage_share].'
        self.assertEqual(market.check_grounding(mixed, ev.sources)[0]['kind'], 'miscited')

    def test_mixed_scenario_sentence_is_removed_when_verifier_rejects_it(self):
        self.configure()
        other = market.price_effect(2022, 'barc_model_error_applied_statewide')['grain_bushels_shifted']
        line = (f'One point of share is {other} bushels [price_effect.one_point_of_maryland_silage_share]. '
                'Maryland harvested 40,000 silage acres [maryland_supply].')
        reject = {'content': '{"results": [{"i": 0, "supported": false, "reason": "that figure is the model-error scenario"}]}'}
        script = ScriptedNvidia([
            {'content': None, 'tool_calls': [
                tool_call(1, 'price_effect', year=2022, scenario='one_point_of_maryland_silage_share'),
                tool_call(2, 'price_effect', year=2022, scenario='barc_model_error_applied_statewide'),
                tool_call(3, 'maryland_supply', year=2022)]},
            {'content': line}, reject, {'content': line}, reject,
        ])
        body = self.report(script).json()
        verify_prompt = script.requests[2][1]['messages'][1]['content']
        self.assertIn('[price_effect.barc_model_error_applied_statewide]', verify_prompt)  # verifier saw where the number is from
        self.assertEqual([(u['kind'], u['removed']) for u in body['grounding']['ungrounded']], [('verifier', True)])
        self.assertEqual(body['markdown'], 'Maryland harvested 40,000 silage acres [maryland_supply].')

    def test_bold_headings_are_normalised_not_treated_as_claims(self):
        text = market._clean('**## Bottom line**\nA [x].\n**Price impact**\nB [y].')
        self.assertEqual(text, '## Bottom line\nA [x].\n## Price impact\nB [y].')

    def test_bare_tool_name_cites_that_tools_results(self):
        ev = market._Evidence()
        ev.add_tool('model_field_calls', {'year': 2022, 'month_day': '10-12'}, market.model_field_calls(2022, '10-12'))
        self.assertEqual(market.check_grounding('The model called 5 fields silage [model_field_calls].', ev.sources), [])
        bad = market.check_grounding('The model called 123 fields silage [model_field_calls].', ev.sources)
        self.assertEqual(bad[0]['kind'], 'unsupported')

    def test_title_heading_does_not_get_not_covered_line(self):
        out = market.remove_claims('# Title\n## As of 2025-09-12\n## Bottom line\nGone.\n## Price outlook\nKept [a].', {'Gone.'})
        # Required sections left empty say so; an extra empty heading the model added is dropped.
        self.assertEqual(out, '# Title\n## Bottom line\nOur data does not cover this.\n## Price outlook\nKept [a].')

    def test_list_intro_is_dropped_when_its_list_is_removed(self):
        text = ('## Supply outlook\nSupply fell [a]. Maryland silage moved as follows [b]:\n- Gone one [b].\n'
                '- Gone two [b].\n## Price outlook\nPrices are listed below [c]:\n- Kept [c].\n'
                '## How much to trust this\nThe changes were [d]:\n\n- Gone three [d].')
        out = market.remove_claims(text, {'Gone one [b].', 'Gone two [b].', 'Gone three [d].'})
        self.assertEqual(out, '## Supply outlook\nSupply fell [a].\n## Price outlook\nPrices are listed below [c]:\n'
                              '- Kept [c].\n## How much to trust this\nOur data does not cover this.')
        # An intro whose list was never touched stays.
        self.assertEqual(market.remove_claims('## Bottom line\nAs follows [a]:\n- Kept [a].\nGone.', {'Gone.'}),
                         '## Bottom line\nAs follows [a]:\n- Kept [a].')

    def test_claims_split_sentences_bullets_and_skip_headings(self):
        text = '## Bottom line\nFirst claim [a]. Second claim.\n[b]\n- Bullet claim [c]\n'
        # A citation-only fragment (here on its own line) attaches to the sentence before it.
        self.assertEqual(market.claims(text), ['First claim [a].', 'Second claim. [b]', 'Bullet claim [c]'])

    # ---- Nemotron loop

    def test_tool_loop_produces_grounded_cited_report(self):
        self.configure()
        script = ScriptedNvidia([
            {'content': None, 'tool_calls': [tool_call(1, 'maryland_supply', year=2022),
                                             tool_call(2, 'price_effect', year=2022, scenario='one_point_of_maryland_silage_share'),
                                             tool_call(3, 'search_project_docs', query='model limitations single site')]},
            {'content': '<think>scratch 999</think>## Bottom line\nMaryland harvested 40,000 silage acres (10.0%) '
                        '[maryland_supply]. One point of silage share is 660,000 bushels, 0.005% of US supply '
                        '[price_effect.one_point_of_maryland_silage_share].'},
            VERIFIED,
        ])
        r = self.report(script)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body['mode'], 'tools')
        self.assertEqual([c['name'] for c in body['tool_calls']], ['maryland_supply', 'price_effect', 'search_project_docs'])
        self.assertTrue(all(c['ok'] for c in body['tool_calls']))
        self.assertEqual(body['grounding'], {'claims_checked': 2, 'ungrounded': [], 'verifier': 'nemotron'})
        verify = script.requests[-1][1]['messages']
        self.assertIn('CITED SOURCES', verify[1]['content'])  # verifier sees the exact cited text
        self.assertIn('40,000', verify[1]['content'])
        self.assertEqual([c['id'] for c in body['citations']],
                         ['maryland_supply', 'price_effect.one_point_of_maryland_silage_share'])
        self.assertNotIn('999', body['markdown'])  # inline reasoning stripped
        first = script.requests[0][1]
        self.assertEqual(first['chat_template_kwargs'], {'enable_thinking': False})
        self.assertEqual({t['function']['name'] for t in first['tools']}, set(market.TOOLS))
        self.assertIn('Do not use outside knowledge', first['messages'][0]['content'])
        tool_msgs = {m['name']: m['content'] for m in script.requests[1][1]['messages'] if m['role'] == 'tool'}
        self.assertIn('40,000', tool_msgs['maryland_supply'])  # the model saw real tool output
        self.assertEqual(json.loads(tool_msgs['price_effect'])['cite_as'], '[price_effect.one_point_of_maryland_silage_share]')
        self.assertIn('#', json.loads(tool_msgs['search_project_docs'])['passages'][0]['id'])

    def test_tool_arguments_that_are_not_an_object_are_a_tool_error_not_a_crash(self):
        self.configure()
        bad = {'id': 'c1', 'type': 'function', 'function': {'name': 'maryland_supply', 'arguments': '[2022]'}}
        script = ScriptedNvidia([
            {'content': None, 'tool_calls': [bad, tool_call(2, 'maryland_supply', year=2022)]},
            {'content': '## Bottom line\nMaryland harvested 40,000 silage acres [maryland_supply].'}, VERIFIED])
        r = self.report(script)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([c['ok'] for c in r.json()['tool_calls']], [False, True])
        tool_msgs = [m for m in script.requests[1][1]['messages'] if m['role'] == 'tool']
        self.assertIn('JSON object', json.loads(tool_msgs[0]['content'])['error'])

    def test_tool_calls_per_round_are_capped_with_a_note(self):
        self.configure()
        many = [tool_call(i, 'maryland_supply', year=2022) for i in range(market.MAX_CALLS_PER_ROUND + 4)]
        script = ScriptedNvidia([
            {'content': None, 'tool_calls': many},
            {'content': '## Bottom line\nMaryland harvested 40,000 silage acres [maryland_supply].'}, VERIFIED])
        body = self.report(script).json()
        self.assertEqual(len(body['tool_calls']), market.MAX_CALLS_PER_ROUND)
        sent = script.requests[1][1]['messages']
        self.assertEqual(len(sent[2]['tool_calls']), market.MAX_CALLS_PER_ROUND)  # each kept call has a reply
        self.assertEqual(sum(m['role'] == 'tool' for m in sent), market.MAX_CALLS_PER_ROUND)
        self.assertIn('4 more were skipped', sent[-1]['content'])

    def test_doc_passages_are_citable_and_unretrieved_ones_are_not(self):
        self.configure()
        # Post-season report: the full document set (results included) is searchable.
        self.assertIsNone(market._AS_OF.get())
        hit = market.search_project_docs('model limitations single site')['passages'][0]
        script = ScriptedNvidia([
            {'content': None, 'tool_calls': [tool_call(1, 'search_project_docs', query='model limitations single site')]},
            {'content': f'## How much to trust this\nThe team documents its limits [{hit["id"]}]. '
                        'Results generalize to Iowa [docs/NOT_RETRIEVED.md#0].'},
            VERIFIED,
            {'content': f'## How much to trust this\nThe team documents its limits [{hit["id"]}].'},
            VERIFIED,
        ])
        body = self.report(script, as_of='2023-12-31').json()
        self.assertEqual(body['grounding']['ungrounded'], [])
        self.assertEqual(body['citations'][0], {**body['citations'][0], 'kind': 'doc', 'id': hit['id']})
        rewrite = script.requests[3][1]['messages'][-1]['content']
        self.assertIn('not retrieved in this run: docs/NOT_RETRIEVED.md#0', rewrite)

    def test_uncited_or_invented_claims_get_one_rewrite_then_are_flagged(self):
        self.configure()
        bad = 'Corn prices will jump 7.77% [maryland_supply]. Ethanol demand drives prices.'
        script = ScriptedNvidia([
            {'content': None, 'tool_calls': [tool_call(1, 'maryland_supply', year=2022)]},
            {'content': bad}, {'content': bad},
        ])
        body = self.report(script).json()
        reasons = {u['text']: u['reason'] for u in body['grounding']['ungrounded']}
        self.assertTrue(all(u['removed'] for u in body['grounding']['ungrounded']))
        self.assertNotIn('7.77', body['markdown'])          # unsupported sentences are removed, not shown
        self.assertNotIn('Ethanol', body['markdown'])
        self.assertEqual(reasons['Corn prices will jump 7.77% [maryland_supply].'], 'numbers not found in any retrieved data: 7.77')
        self.assertEqual(reasons['Ethanol demand drives prices.'], 'no citation')
        # tools, draft, exactly one rewrite; no verifier call because no claim passed the deterministic check
        self.assertEqual(len(script.requests), 3)
        self.assertIn('Ethanol demand drives prices.', script.requests[2][1]['messages'][-1]['content'])

    def test_endpoint_without_tool_calling_falls_back_to_prefetched_tools_and_docs(self):
        self.configure()
        script = ScriptedNvidia([http_error(400, '{"detail":"tools are not supported for this model"}'),
                                 {'content': '## Bottom line\nMaryland: 40,000 silage acres [maryland_supply].'}, VERIFIED])
        body = self.report(script).json()
        self.assertEqual(body['mode'], 'context')
        names = [c['name'] for c in body['tool_calls']]
        self.assertEqual(names.count('search_project_docs'), len(market.FALLBACK_QUERIES))
        self.assertIn('model_field_calls', names)
        self.assertEqual(body['grounding']['ungrounded'], [])
        last = script.requests[-2][1]  # the report request (the last one is the verifier)
        self.assertNotIn('tools', last)
        self.assertIn('40,000', last['messages'][-1]['content'])
        self.assertIn('Citations are mandatory', last['messages'][0]['content'])
        self.assertNotIn('Gather facts first', last['messages'][0]['content'])

    def test_verifier_flags_cited_claim_its_source_does_not_support(self):
        self.configure()
        script = ScriptedNvidia([
            {'content': None, 'tool_calls': [tool_call(1, 'maryland_supply', year=2022)]},
            {'content': 'Maryland harvested 40,000 silage acres [maryland_supply]. Ethanol demand drives silage choices [maryland_supply].'},
            {'content': '{"results": [{"i": 1, "supported": false, "reason": "source says nothing about ethanol"}]}'},
            {'content': 'Maryland harvested 40,000 silage acres [maryland_supply]. Ethanol demand drives silage choices [maryland_supply].'},
            {'content': '{"results": [{"i": 1, "supported": false, "reason": "source says nothing about ethanol"}]}'},
        ])
        body = self.report(script).json()
        self.assertIn('source says nothing about ethanol', script.requests[3][1]['messages'][-1]['content'])  # fed back
        self.assertEqual(body['grounding']['ungrounded'],
                         [{'text': 'Ethanol demand drives silage choices [maryland_supply].', 'kind': 'verifier',
                           'reason': 'verifier: source says nothing about ethanol', 'removed': True}])
        self.assertEqual(body['markdown'], 'Maryland harvested 40,000 silage acres [maryland_supply].')

    def test_verifier_rejection_is_fixed_by_the_rewrite(self):
        self.configure()
        script = ScriptedNvidia([
            {'content': None, 'tool_calls': [tool_call(1, 'maryland_supply', year=2022)]},
            {'content': 'Maryland harvested 40,000 silage acres, down from last year [maryland_supply].'},
            {'content': '{"results": [{"i": 0, "supported": false, "reason": "no prior-year comparison in source"}]}'},
            {'content': 'Maryland harvested 40,000 silage acres [maryland_supply].'},
            VERIFIED,
        ])
        g = self.report(script).json()['grounding']
        self.assertEqual((g['ungrounded'], g['verifier']), ([], 'nemotron'))

    def test_price_effect_states_which_elasticity_moves_price_most(self):
        rows = market.price_effect(2022, 'one_point_of_maryland_silage_share')['us_price_effect_by_assumed_elasticity']
        self.assertEqual(rows[0]['elasticity'], '-0.2')
        self.assertIn('largest price change', rows[0]['meaning'])
        self.assertIn('smallest price change', rows[-1]['meaning'])

    def test_unparseable_verifier_reply_is_reported_not_hidden(self):
        self.configure()
        script = ScriptedNvidia([
            {'content': None, 'tool_calls': [tool_call(1, 'maryland_supply', year=2022)]},
            {'content': 'Maryland harvested 40,000 silage acres [maryland_supply].'},
            {'content': 'I think it is all fine.'}, {'content': 'Still fine.'},  # one retry, then give up
        ])
        self.assertEqual(self.report(script).json()['grounding']['verifier'], 'unavailable')

    def test_rejected_model_lists_available_nemotron_ids(self):
        self.configure()
        script = ScriptedNvidia([http_error(404, '{"detail":"Function not found"}')],
                                models=['nvidia/nemotron-a', 'meta/llama-x'])
        r = self.report(script)
        self.assertEqual(r.status_code, 503)
        self.assertIn('nvidia/nemotron-a', r.json()['detail'])
        self.assertNotIn('meta/llama-x', r.json()['detail'])

    # ---- failures seen against the live model

    def test_text_tool_calls_are_run_and_never_reach_the_report(self):
        self.configure()
        text_call = ('<tool_call>\n<function=maryland_supply>\n<parameter=year>\n2022\n</parameter>\n'
                     '</function>\n</tool_call>')
        line = 'Maryland harvested 40,000 silage acres [maryland_supply].'
        script = ScriptedNvidia([{'content': text_call}, {'content': line + '\n<tool_call>\n</tool_call>'}, VERIFIED])
        body = self.report(script).json()
        self.assertEqual([(c['name'], c['args'], c['ok']) for c in body['tool_calls']], [('maryland_supply', {'year': 2022}, True)])
        self.assertEqual(body['markdown'], line)
        self.assertNotIn('<tool_call>', json.dumps(script.requests[1][1]['messages'][2:]))

    def test_markup_only_report_is_re_asked_once_without_tools(self):
        self.configure()
        line = 'Maryland harvested 40,000 silage acres [maryland_supply].'
        junk = {'content': '{"name": "maryland_supply", "arguments": {"year": 2022}}'}
        script = ScriptedNvidia([{'content': None, 'tool_calls': [tool_call(1, 'maryland_supply', year=2022)]}]
                                + [junk] * (market.MAX_ROUNDS - 1)
                                + [{'content': '<tool_call><function=maryland_supply></function></tool_call>'},
                                   {'content': line}, VERIFIED])
        body = self.report(script).json()
        reask = script.requests[-2][1]
        self.assertNotIn('tools', reask)
        self.assertIn('Do not call tools', reask['messages'][-1]['content'])
        self.assertEqual(body['markdown'], line)

        script = ScriptedNvidia([{'content': None, 'tool_calls': [tool_call(1, 'maryland_supply', year=2022)]},
                                 {'content': ''}, {'content': '<tool_call></tool_call>'}])
        r = self.report(script)
        self.assertEqual(r.status_code, 503)
        self.assertIn('did not return a written report', r.json()['detail'])

    def test_null_ish_and_string_tool_arguments_are_normalised(self):
        self.configure()
        script = ScriptedNvidia([
            {'content': None, 'tool_calls': [tool_call(1, 'price_effect', year='2022', scenario='none'),
                                             tool_call(2, 'maryland_supply', year='2022', month_day='null')]},
            {'content': 'Maryland harvested 40,000 silage acres [maryland_supply].'}, VERIFIED])
        body = self.report(script).json()
        self.assertEqual([c['args'] for c in body['tool_calls']], [{'year': 2022}, {'year': 2022}])
        self.assertTrue(body['tool_calls'][1]['ok'])
        self.assertNotIn('price_effect.none', json.dumps(body))

    def test_rate_limits_are_retried_inside_post(self):
        self.configure()
        from app import llm_guard
        replies = [http_error(429, 'slow down'), http_error(502, 'bad gateway'),
                   {'content': None, 'tool_calls': [tool_call(1, 'maryland_supply', year=2022)]},
                   {'content': 'Maryland harvested 40,000 silage acres [maryland_supply].'}, VERIFIED]
        sleeps = []

        def urlopen(req, timeout):
            r = replies.pop(0)
            if isinstance(r, Exception):
                raise r
            return io.BytesIO(json.dumps({'choices': [{'message': r}]}).encode())

        with patch.object(llm_guard.urllib.request, 'urlopen', urlopen), patch.object(llm_guard, '_sleep', sleeps.append):
            r = self.client.post('/api/market/report', json={'year': 2023})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['grounding']['ungrounded'], [])
        self.assertEqual(len(sleeps), 2)
        self.assertLessEqual(sum(sleeps), llm_guard.RETRY_MAX_WAIT)
        self.assertNotIn(FAKE_KEY, r.text)

    def test_bad_key_is_explained(self):
        self.configure()
        r = self.report(ScriptedNvidia([http_error(401, 'unauthorized')]))
        self.assertEqual(r.status_code, 503)
        self.assertIn('rejected the API key', r.json()['detail'])
        self.assertNotIn(FAKE_KEY, r.text)


if __name__ == '__main__':
    unittest.main()
