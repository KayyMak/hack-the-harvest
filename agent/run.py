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
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, TypedDict

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / 'backend'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from langchain_core.utils.function_calling import convert_to_openai_tool  # noqa: E402
from langgraph.graph import END, StateGraph  # noqa: E402

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

SYSTEM = """You are the analyst agent for a hackathon project that predicts whether corn fields at the BARC
research station (Beltsville, Maryland) were harvested for silage or grain, from Sentinel-2 NDVI.

Use the tools to answer. They read the team's saved, field-held-out model results: classify (calls per field,
optionally as of a date so only satellite months complete by then are used), evaluate (scores against BARC
labels), aggregate (silage acres with a 95% interval), get_fields, get_timeseries, get_quickstats (NASS
county/state acres, context only, never field labels) and get_chip.

Rules:
- Only use facts from tool results. No outside knowledge. If the tools cannot answer, say so.
- Copy numbers exactly as a tool returned them; do not compute new ones.
- After each fact, name the tool it came from in brackets, e.g. [aggregate].
- Keep model predictions and BARC reference labels clearly distinct.
- BARC is one research station: never present its numbers as Maryland or US totals.
- Answer in short markdown: a title, the findings, then one line on uncertainty."""


class AgentState(TypedDict, total=False):
    run_id: str
    query: str
    messages: list[dict]
    pending: list[dict]
    results: list[str]
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
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)['choices'][0]['message']
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', 'replace')[:300]
        if exc.code in (401, 403):
            raise AgentError(f'NVIDIA rejected the API key (HTTP {exc.code}).') from exc
        raise AgentError(f'NVIDIA API error (HTTP {exc.code}): {body}') from exc
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError) as exc:
        raise AgentError(f'Could not get a reply from the NVIDIA API: {exc}') from exc


def _clean(text: str | None) -> str:
    return re.sub(r'<think>.*?</think>', '', text or '', flags=re.S).strip()


def tool_specs() -> list[dict]:
    return [convert_to_openai_tool(t) for t in AGENT_TOOLS]


def _fn(tc) -> dict:
    """The 'function' part of a tool call, or {} when the reply is malformed."""
    fn = tc.get('function') if isinstance(tc, dict) else None
    return fn if isinstance(fn, dict) else {}


def _args(tc: dict) -> tuple[dict, str | None]:
    """A tool call's arguments as a dict, or ({}, error) when they are not a JSON object."""
    raw = _fn(tc).get('arguments') or '{}'
    try:
        args = raw if isinstance(raw, dict) else json.loads(raw)
    except (ValueError, TypeError):
        return {}, 'tool arguments are not valid JSON; send a JSON object'
    if not isinstance(args, dict):
        return {}, 'tool arguments must be a JSON object'
    return args, None


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
    msg = chat(state['messages'], tool_specs() if rounds < MAX_TOOL_ROUNDS else None)
    calls = msg.get('tool_calls') or []
    if rounds >= MAX_TOOL_ROUNDS:
        calls = []  # no tools were offered this round: a call the model makes anyway is not run
    if calls:
        if len(calls) > MAX_CALLS_PER_ROUND:
            log_step(run_id, node='analyst', type='plan',
                     summary=f'only the first {MAX_CALLS_PER_ROUND} of {len(calls)} tool calls in this round are run')
            calls = calls[:MAX_CALLS_PER_ROUND]  # every call kept in the assistant message gets a tool reply
        state['messages'].append({'role': 'assistant', 'content': msg.get('content') or '', 'tool_calls': calls})
        for tc in calls:
            log_step(run_id, node='analyst', type='tool_call', tool=_fn(tc).get('name'), args=_args(tc)[0])
        state['pending'] = calls
        state['tool_rounds'] = rounds + 1
    else:
        state['draft'] = _clean(msg.get('content'))
        state['pending'] = []
    return state


def run_tools(state: AgentState) -> AgentState:
    run_id = state['run_id']
    for tc in state.get('pending', []):
        name = _fn(tc).get('name', '')
        if not isinstance(name, str):  # a malformed reply must be a tool error, never a crash
            name = repr(name)
        args, bad = _args(tc)
        args = {k: v for k, v in args.items() if v is not None}
        if name not in AGENT_TOOL_NAMES:  # only tools offered to the model run (not write_report: it takes a run_id)
            out = {'error': f'unknown tool {name!r}; available: {sorted(AGENT_TOOL_NAMES)}'}
        elif bad:
            out = {'error': bad}
        else:
            out = harvest_tools.call(name, args)
        text = json.dumps(out, default=str)
        state.setdefault('results', []).append(text)
        state['messages'].append({'role': 'tool', 'tool_call_id': tc.get('id', name), 'name': name, 'content': text})
        log_step(run_id, node='tools', type='tool_result', tool=name, args=args, ok='error' not in out,
                 summary=_summary(out))
    state['pending'] = []
    return state


def _norm(t: str) -> str:
    t = t.replace(',', '').rstrip('.')
    return t if '.' in t else (t.lstrip('0') or '0')


def unsupported_numbers(draft: str, results: list[str], query: str) -> list[str]:
    """Numbers in the draft that match no tool result (nor the user's own request). A draft number with k
    decimals counts as supported when some tool value rounds to it at k decimals (0.833 from 0.8333...,
    40 from 40.13), so sensible rounding passes but invented or altered figures do not."""
    source = ' '.join(results) + ' ' + query
    exact = {_norm(n) for n in NUM.findall(source)}
    values = [float(_norm(n)) for n in NUM.findall(source)]
    text = re.sub(r'\[[^\]]*\]', ' ', draft)  # ignore [tool] tags

    def supported(n: str) -> bool:
        t = _norm(n)
        if t in exact:
            return True
        k = len(t.split('.')[1]) if '.' in t else 0
        d = float(t)
        return any(round(v, k) == d for v in values)

    return sorted({n for n in NUM.findall(text) if not supported(n)}, key=lambda n: (len(n), n))


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
    report = state.get('draft') or 'The agent could not produce an answer from the tool results.'
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
    try:
        GRAPH.invoke({'run_id': run_id, 'query': query, 'messages': [], 'results': []},
                     {'recursion_limit': 4 * (MAX_TOOL_ROUNDS + MAX_VERIFY_ROUNDS) + 10})
    except Exception as exc:  # noqa: BLE001 - any failure must still end the trace with a report line
        message = str(exc) or type(exc).__name__
        log_step(run_id, node='writer', type='error', summary=message)
        log_step(run_id, node='writer', type='report', summary=f'The agent stopped before finishing: {message}')
