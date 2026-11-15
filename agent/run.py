"""Nemotron analyst agent: a LangGraph loop over the tools in harvest/tools.py.

    run_agent(query, run_id)      # what POST /api/agent/run starts in the background

Graph:  analyst --(tool calls)--> tools --> analyst ... --(draft)--> verifier --(ok)--> writer
                                                         verifier --(unsupported numbers, once)--> analyst
  analyst   Nemotron (NVIDIA's OpenAI-compatible API) plans, calls tools, drafts the answer.
  tools     runs harvest.tools.call(name, args): the saved field-held-out model, as-of refits,
            NASS QuickStats, field time series. Results are the only facts the agent may use.
  verifier  every number in the draft must appear in a tool result; otherwise the draft goes back
            once with the offending numbers named, and any that remain are flagged in the report.
  writer    saves the markdown report (backend tools.write_report) and logs the final `report` step.

Every step is appended to the run's trace (backend tools.log_step), the format the Agent tab polls.
A run always ends with a `report` line, also when something fails, so the UI never waits forever.

Configuration (environment, else the repo-root .env): NVIDIA_API_KEY (required), NEMOTRON_MODEL,
NEMOTRON_BASE_URL, NEMOTRON_THINKING. The key is only sent to NVIDIA, never logged or returned.

Reliability (app/llm_guard.py, shared with the market report): model calls retry 429/5xx/timeouts with
backoff (each retry is a trace step), tool calls the model writes as text are parsed or stripped, null-ish
tool arguments ("none") are dropped, and a report never contains tool-call markup.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from contextvars import ContextVar
from pathlib import Path
from typing import Any, TypedDict

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / 'backend'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from langchain_core.utils.function_calling import convert_to_openai_tool  # noqa: E402
from langgraph.graph import END, StateGraph  # noqa: E402

from app import llm_guard  # noqa: E402
from app.tools import log_step, write_report  # noqa: E402
from harvest import tools as harvest_tools  # noqa: E402

DEFAULT_MODEL = 'nvidia/nemotron-3.5-lightning-30b-a3b'
DEFAULT_BASE = 'https://integrate.api.nvidia.com/v1'
MAX_TOOL_ROUNDS = 6
MAX_CALLS_PER_ROUND = 8  # tool calls run per model turn; any beyond this are skipped with a note
MAX_VERIFY_ROUNDS = 1
AGENT_TOOLS = [t for t in harvest_tools.TOOLS if t.name != 'write_report']  # the writer node saves the report
AGENT_TOOL_NAMES = {t.name for t in AGENT_TOOLS}
NUM = re.compile(r'\d[\d,]*(?:\.\d+)?')
_RUN_ID: ContextVar[str | None] = ContextVar('agent_run_id', default=None)  # where chat() logs its retries

SYSTEM = """You are the analyst agent for a hackathon project that predicts whether corn fields at the BARC
research station (Beltsville, Maryland) were harvested for silage or grain, from Sentinel-2 NDVI.

Use the tools to answer. They read the team's saved, field-held-out model results: classify (calls per field,
optionally as of a date so only satellite months complete by then are used), evaluate (scores against BARC
labels), aggregate (silage acres with a 95% interval), get_fields, get_timeseries, get_quickstats (NASS
county/state acres, context only, never field labels) and get_chip.

Call tools through the tool-calling interface only. Never write a tool call as text (no <tool_call>, <function=...>
or {"name": ..., "arguments": ...} in your answer).

Rules:
- Only use facts from tool results. No outside knowledge. If the tools cannot answer, write "not available"; never guess.
- Quote numbers as a tool returned them. Never compute new ratios, fractions, percentages, differences or counts
  that no tool returned (if evaluate says 6 of 7 are correct, say that; do not derive your own count).
- Round probabilities and shares to 2 decimals (0.59, not 0.5902900420064867) and acres to 1 decimal.
- Field and run IDs exactly as the tool gave them (field 347), never approximate ("347-ish").
- After each number, name the tool it came from in brackets, e.g. [aggregate].
- Explain intervals, CV% and other statistics only as the tool's own method/note text describes them (for
  example aggregate's CV% comes from the field-level Bernoulli variance of the calls; it is not year-to-year
  variability). If the tool gives no explanation, do not invent one.
- Keep model predictions and BARC reference labels clearly distinct.
- BARC is one research station: never present its numbers as Maryland or US totals.

Answer in markdown with exactly this structure:
## <short title>
### Findings
- one bullet per finding, each number followed by its [tool]
(optional: one compact markdown table of tool values, each column header naming its [tool])
### Uncertainty
- one or two bullets: intervals, sample size, what the tools cannot say
### Sources (tools used)
- each tool used, with the year/as_of it was called with"""

FINAL_ASK = ('Write the final report now in plain prose/markdown with the required sections (title, Findings, '
             'Uncertainty, Sources (tools used)), using only the tool results above. Do not call tools and do not '
             'write any tool-call markup.')
FALLBACK = ('The model did not return a usable written report (its reply was empty or contained only tool-call '
            'markup), so this is an automatic summary of the tool results gathered so far, without interpretation.')


class AgentState(TypedDict, total=False):
    run_id: str
    query: str
    messages: list[dict]
    pending: list[dict]
    results: list[str]
    evidence: list[dict]
    draft: str
    flags: list[str]
    tool_rounds: int
    verify_rounds: int


# ---------------------------------------------------------------- Nemotron

def _env_file() -> dict[str, str]:
    values = {}
    try:
        lines = (ROOT / '.env').read_text(encoding='utf-8').splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def config() -> dict:
    file = _env_file()
    get = lambda k, d='': (os.environ.get(k) or file.get(k) or d).strip()  # noqa: E731
    return {'key': get('NVIDIA_API_KEY'), 'base': get('NEMOTRON_BASE_URL', DEFAULT_BASE).rstrip('/'),
            'model': get('NEMOTRON_MODEL', DEFAULT_MODEL), 'thinking': get('NEMOTRON_THINKING', 'false').lower() == 'true'}


class AgentError(Exception):
    pass


def chat(messages: list[dict], tools: list[dict] | None) -> dict:
    """One Nemotron chat completion; returns the assistant message dict."""
    c = config()
    if not c['key']:
        raise AgentError('NVIDIA_API_KEY is not set (environment or the repo-root .env).')
    payload = {'model': c['model'], 'messages': messages, 'temperature': 0.1, 'max_tokens': 1500,
               'chat_template_kwargs': {'enable_thinking': c['thinking']}}
    if tools:
        payload.update(tools=tools, tool_choice='auto')
    req = urllib.request.Request(f"{c['base']}/chat/completions", data=json.dumps(payload).encode('utf-8'),
                                 headers={'Authorization': f"Bearer {c['key']}", 'Content-Type': 'application/json'})
    run_id = _RUN_ID.get()

    def on_retry(attempt: int, wait: float, reason: str) -> None:
        if run_id:  # reason is e.g. 'HTTP 429' or 'timeout': never headers, body or key
            log_step(run_id, node='nemotron', type='retry',
                     summary=f'NVIDIA API {reason}; retry {attempt} of {llm_guard.RETRY_ATTEMPTS - 1} in {wait:.1f} s')

    try:
        return llm_guard.post_json(req, 120, on_retry)['choices'][0]['message']
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', 'replace')[:300]
        if exc.code in (401, 403):
            raise AgentError(f'NVIDIA rejected the API key (HTTP {exc.code}).') from exc
        raise AgentError(f'NVIDIA API error (HTTP {exc.code}): {body}') from exc
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise AgentError(f'Could not get a reply from the NVIDIA API: {exc}') from exc


def _clean(text: str | None) -> str:
    return re.sub(r'<think>.*?</think>', '', text or '', flags=re.S).strip()


def tool_specs() -> list[dict]:
    return [convert_to_openai_tool(t) for t in AGENT_TOOLS]


def _fn(tc) -> dict:
    """The 'function' part of a tool call, or {} when the reply is malformed."""
    fn = tc.get('function') if isinstance(tc, dict) else None
    return fn if isinstance(fn, dict) else {}


def _int_params(name) -> dict[str, str]:
    schema = harvest_tools.SCHEMAS.get(name) if isinstance(name, str) else None
    if schema is None:
        return {}
    return {k: kind for k, f in schema.model_fields.items() if (kind := llm_guard.int_kind(f.annotation))}


def _args(tc: dict) -> tuple[dict, str | None]:
    """A tool call's arguments as a dict, or ({}, error) when they are not a JSON object. Null-ish values
    ("none", "null", "", "n/a") are dropped so the tool uses its default; numeric strings for int
    parameters (year, field_ids) become ints."""
    raw = _fn(tc).get('arguments') or '{}'
    try:
        args = raw if isinstance(raw, dict) else json.loads(raw)
    except (ValueError, TypeError):
        return {}, 'tool arguments are not valid JSON; send a JSON object'
    if not isinstance(args, dict):
        return {}, 'tool arguments must be a JSON object'
    return llm_guard.clean_args(args, _int_params(_fn(tc).get('name'))), None


def _text_calls(content: str, rounds: int) -> list[dict]:
    """Tool calls the model wrote as text, as structured calls (the allow-list in run_tools still applies)."""
    return [{'id': f'text-{rounds}-{i}', 'type': 'function',
             'function': {'name': name, 'arguments': json.dumps(args, default=str)}}
            for i, (name, args) in enumerate(llm_guard.text_tool_calls(content, AGENT_TOOL_NAMES))]


def _summary(out: dict) -> str:
    if 'error' in out:
        return f"error: {out['error']}"
    keys = [k for k in ('year', 'as_of', 'n', 'n_pending', 'expected_silage_acres', 'balanced_accuracy') if k in out]
    return ', '.join(f'{k}={out[k]}' for k in keys) or ', '.join(list(out)[:5])


# ---------------------------------------------------------------- nodes

def analyst(state: AgentState) -> AgentState:
    run_id = state['run_id']
    if not state.get('messages'):
        log_step(run_id, node='analyst', type='plan', summary=f"request: {state['query']}")
        state['messages'] = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': state['query']}]
    rounds = state.get('tool_rounds', 0)
    can_call = rounds < MAX_TOOL_ROUNDS
    msg = chat(state['messages'], tool_specs() if can_call else None)
    calls = (msg.get('tool_calls') or []) if can_call else []  # no tools offered: a call made anyway is not run
    content = _clean(msg.get('content'))
    markup = llm_guard.has_tool_markup(content, AGENT_TOOL_NAMES)
    if not calls and markup and can_call:
        calls = _text_calls(content, rounds)  # tool calls written as text in `content`
        if calls:
            log_step(run_id, node='analyst', type='plan',
                     summary=f'the model wrote {len(calls)} tool call(s) as text; running them as tool calls')
    if calls:
        if len(calls) > MAX_CALLS_PER_ROUND:
            log_step(run_id, node='analyst', type='plan',
                     summary=f'only the first {MAX_CALLS_PER_ROUND} of {len(calls)} tool calls in this round are run')
            calls = calls[:MAX_CALLS_PER_ROUND]  # every call kept in the assistant message gets a tool reply
        state['messages'].append({'role': 'assistant', 'content': llm_guard.strip_tool_markup(content, AGENT_TOOL_NAMES),
                                  'tool_calls': calls})
        for tc in calls:
            log_step(run_id, node='analyst', type='tool_call', tool=_fn(tc).get('name'), args=_args(tc)[0])
        state['pending'] = calls
        state['tool_rounds'] = rounds + 1
    else:
        draft = llm_guard.strip_tool_markup(content, AGENT_TOOL_NAMES)
        if markup or not draft:
            draft = _final_report(state, draft)
        state['draft'] = llm_guard.round_long_floats(draft)
        state['pending'] = []
    return state


def _usable(text: str) -> bool:
    return bool(text) and not llm_guard.has_tool_markup(text, AGENT_TOOL_NAMES)


def _final_report(state: AgentState, partial: str) -> str:
    """The reply was empty or held tool-call markup we could not run: ask once more for the report with no
    tools offered; if that fails too, fall back to a deterministic summary of the tool results."""
    run_id = state['run_id']
    log_step(run_id, node='writer', type='plan',
             summary='the reply was empty or held tool-call markup; asking once more for the report, with no tools')
    messages = state['messages'] + ([{'role': 'assistant', 'content': partial}] if partial else [])
    try:
        text = _clean(chat(messages + [{'role': 'user', 'content': FINAL_ASK}], None).get('content'))
    except AgentError as exc:
        log_step(run_id, node='writer', type='error', summary=str(exc))
        text = ''
    if _usable(text):
        return text
    log_step(run_id, node='writer', type='plan', summary='still no usable report: writing a summary of the tool results')
    return fallback_report(state)


def fallback_report(state: AgentState) -> str:
    """Deterministic report from the tool results gathered so far (their own numbers only, nothing computed)."""
    lines = ['## Summary of tool results', '', FALLBACK, '', '### Findings']
    found = [(e['tool'], e['summary']) for e in state.get('evidence', []) if e['ok']]
    lines += [f'- {summary} [{tool}]' for tool, summary in found] or ['- No tool returned a result: not available.']
    lines += ['', '### Uncertainty', '- Not interpreted: see each tool result in the trace for its intervals and notes.',
              '', '### Sources (tools used)']
    lines += [f'- {t}' for t in dict.fromkeys(t for t, _ in found)] or ['- none']
    return llm_guard.round_long_floats('\n'.join(lines))


def run_tools(state: AgentState) -> AgentState:
    run_id = state['run_id']
    for tc in state.get('pending', []):
        name = _fn(tc).get('name', '')
        if not isinstance(name, str):  # a malformed reply must be a tool error, never a crash
            name = repr(name)
        args, bad = _args(tc)
        if name not in AGENT_TOOL_NAMES:  # only tools offered to the model run (not write_report: it takes a run_id)
            out = {'error': f'unknown tool {name!r}; available: {sorted(AGENT_TOOL_NAMES)}'}
        elif bad:
            out = {'error': bad}
        else:
            out = harvest_tools.call(name, args)
        text = json.dumps(out, default=str)
        state.setdefault('results', []).append(text)
        state.setdefault('evidence', []).append({'tool': name, 'ok': 'error' not in out, 'summary': _summary(out)})
        state['messages'].append({'role': 'tool', 'tool_call_id': tc.get('id', name), 'name': name, 'content': text})
        log_step(run_id, node='tools', type='tool_result', tool=name, args=args, ok='error' not in out,
                 summary=_summary(out))
    state['pending'] = []
    return state


def _norm(t: str) -> str:
    t = t.replace(',', '').rstrip('.')
    return t if '.' in t else (t.lstrip('0') or '0')


INTERVAL_AFTER = re.compile(r'\s*(?:%|percent)?\s*[-–]?\s*(?:[A-Za-z]+\s+){0,2}?(?:interval|ci\b|confidence|credible|range|bounds?)',
                            re.I)
INTERVAL_BEFORE = re.compile(r'(?:wilson|ci|interval|confidence)\W{0,3}$', re.I)
PERCENT_AFTER = re.compile(r'\s*(?:%|percent\b)', re.I)
_NOT_COUNTS = re.compile(r'(?:^|_)(?:ids?|year|fold|step|pending)$|^\d{4}$', re.I)  # ids, years: not quantities


def _int_leaves(results: list[str]) -> set[int]:
    """Integer values in the tool results that are counts or quantities (not ids, years or folds): the only
    numbers whose sums and differences the verifier accepts."""
    out: set[int] = set()

    def walk(o, key: str) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, str(k))
        elif isinstance(o, list):
            for v in o:
                walk(v, key)
        elif isinstance(o, int) and not isinstance(o, bool) and not _NOT_COUNTS.search(key):
            out.add(o)

    for r in results:
        try:
            walk(json.loads(r), '')
        except (ValueError, TypeError):
            continue
    return out


def unsupported_numbers(draft: str, results: list[str], query: str) -> list[str]:
    """Numbers in the draft that match no tool result (nor the user's own request). Supported forms, and only these:
      * the tool value itself, or rounded to the draft's decimals (0.833 from 0.8333..., 40 from 40.13);
      * a percent of a tool fraction, at the shown decimals, when followed by % or "percent" (0.782 -> 78.2%);
      * 95 or 90 as the level of an interval / CI / range ("95% interval", "Wilson 95%");
      * a year (2000-2035, no decimals or commas);
      * an integer equal to the sum or difference of two integer counts in the results (19 - 4 = 15).
    Invented or altered figures fail."""
    source = ' '.join(results) + ' ' + query
    exact = {_norm(n) for n in NUM.findall(source)}
    values = [float(_norm(n)) for n in NUM.findall(source)]
    ints = sorted(_int_leaves(results))
    combos = {a + b for a in ints for b in ints} | {abs(a - b) for a in ints for b in ints}
    text = re.sub(r'\[[^\]]*\]', ' ', draft)  # ignore [tool] tags

    def supported(m: re.Match) -> bool:
        n = m.group(0)
        t = _norm(n)
        if t in exact:
            return True
        k = len(t.split('.')[1]) if '.' in t else 0
        d = float(t)
        if any(abs(round(v, k) - d) < 1e-9 for v in values):
            return True
        after, before = text[m.end():m.end() + 40], text[max(0, m.start() - 12):m.start()]
        if PERCENT_AFTER.match(after) and any(abs(round(v * 100, k) - d) < 1e-9 for v in values):
            return True
        if t in ('95', '90') and (INTERVAL_AFTER.match(after) or INTERVAL_BEFORE.search(before)):
            return True
        if k == 0 and ',' not in n and (2000 <= d <= 2035 or int(d) in combos):
            return True
        return False

    return sorted({m.group(0) for m in NUM.finditer(text) if not supported(m)}, key=lambda n: (len(n), n))


def verifier(state: AgentState) -> AgentState:
    run_id = state['run_id']
    bad = unsupported_numbers(state.get('draft', ''), state.get('results', []), state['query'])
    rounds = state.get('verify_rounds', 0)
    if not bad:
        log_step(run_id, node='verifier', type='check', summary='every number in the draft appears in a tool result')
        state['flags'] = []
        return state
    log_step(run_id, node='verifier', type='flag',
             summary=f"numbers not found in any tool result: {', '.join(bad)}")
    state['flags'] = bad
    if rounds < MAX_VERIFY_ROUNDS:
        state['messages'] += [{'role': 'assistant', 'content': state['draft']},
                              {'role': 'user', 'content': 'These numbers are not in any tool result: ' + ', '.join(bad)
                               + '. Call tools to get them, or remove them. Then give the full answer again.'}]
        state['verify_rounds'] = rounds + 1
        state['draft'] = ''
    return state


def writer(state: AgentState) -> AgentState:
    run_id = state['run_id']
    report = llm_guard.strip_tool_markup(state.get('draft'))  # a report never shows tool-call markup
    report = llm_guard.round_long_floats(report or fallback_report(state))
    if state.get('flags'):
        report += ('\n\n> **Verifier:** these numbers were not found in any tool result and may be wrong: '
                   + ', '.join(state['flags']))
    write_report(run_id, report)
    log_step(run_id, node='writer', type='report', summary=report)
    return state


# ---------------------------------------------------------------- graph

def _after_analyst(state: AgentState) -> str:
    return 'tools' if state.get('pending') else 'verifier'


def _after_verifier(state: AgentState) -> str:
    return 'analyst' if state.get('flags') and not state.get('draft') else 'writer'


def build_graph():
    g = StateGraph(AgentState)
    g.add_node('analyst', analyst)
    g.add_node('tools', run_tools)
    g.add_node('verifier', verifier)
    g.add_node('writer', writer)
    g.set_entry_point('analyst')
    g.add_conditional_edges('analyst', _after_analyst, {'tools': 'tools', 'verifier': 'verifier'})
    g.add_edge('tools', 'analyst')
    g.add_conditional_edges('verifier', _after_verifier, {'analyst': 'analyst', 'writer': 'writer'})
    g.add_edge('writer', END)
    return g.compile()


GRAPH = build_graph()


def run_agent(query: str, run_id: str) -> None:
    """Run the agent for one request, writing every step to the run's trace. Never raises."""
    token = _RUN_ID.set(run_id)
    try:
        GRAPH.invoke({'run_id': run_id, 'query': query, 'messages': [], 'results': []},
                     {'recursion_limit': 4 * (MAX_TOOL_ROUNDS + MAX_VERIFY_ROUNDS) + 10})
    except Exception as exc:  # noqa: BLE001 - any failure must still end the trace with a report line
        message = str(exc) or type(exc).__name__
        log_step(run_id, node='writer', type='error', summary=message)
        log_step(run_id, node='writer', type='report', summary=f'The agent stopped before finishing: {message}')
    finally:
        _RUN_ID.reset(token)
