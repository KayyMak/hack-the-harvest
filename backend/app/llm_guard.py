"""Shared guards for the two Nemotron loops (agent/run.py and app/market.py).

    post_json(req, timeout, on_retry)   one HTTP call with retries for 429 / 5xx / timeouts, and a
                                        process-wide cap on concurrent model calls
    text_tool_calls(text, offered)      tool calls the model wrote as text instead of `tool_calls`
    strip_tool_markup(text)             the same markup removed, so it never reaches a report
    clean_args(args, int_params)        drop null-ish values ("none", "null", "", "n/a"), coerce int strings
    round_long_floats(text)             0.5902900420064867 -> 0.59 in prose
"""
import json
import os
import random
import re
import socket
import threading
import time
import typing
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime

# ---------------------------------------------------------------- HTTP with retries

RETRY_ATTEMPTS = 7          # total tries per model call (NVIDIA's free tier limits requests per minute)
RETRY_MAX_WAIT = 75.0       # seconds of backoff in total, Retry-After included; spans a per-minute window
RETRY_BASE = 2.0            # first backoff; doubles each retry (capped at 20 s), plus up to 50% jitter
MODEL_SLOTS = threading.BoundedSemaphore(max(1, int(os.environ.get('NEMOTRON_CONCURRENCY', '1') or 1)))
_sleep = time.sleep         # tests replace this


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    headers = getattr(exc, 'headers', None)
    value = headers.get('Retry-After') if headers is not None else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _retryable(exc: BaseException) -> str | None:
    """A short reason when the error is worth retrying (rate limit, server error, timeout, connection), else None."""
    if isinstance(exc, urllib.error.HTTPError):  # before URLError/OSError: HTTPError subclasses both
        return f'HTTP {exc.code}' if exc.code == 429 or exc.code >= 500 else None
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return 'timeout'
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        return 'timeout' if isinstance(reason, (TimeoutError, socket.timeout)) else f'connection error ({type(reason).__name__})'
    if isinstance(exc, (ConnectionError, OSError)):
        return f'connection error ({type(exc).__name__})'
    return None


def post_json(req: urllib.request.Request, timeout: float, on_retry=None,
              attempts: int = RETRY_ATTEMPTS, max_wait: float = RETRY_MAX_WAIT) -> dict:
    """Send `req`, parse the JSON reply. Retries 429/5xx/timeouts/connection errors with exponential backoff
    plus jitter, honouring Retry-After, for at most `attempts` tries and `max_wait` seconds of waiting.
    Anything else (401, 403, 400, ...) and the last failure are re-raised unchanged (HTTPError body unread).
    on_retry(attempt, wait_seconds, reason) is called before each wait; the reason never holds headers or keys."""
    waited = 0.0
    for attempt in range(1, attempts + 1):
        try:
            with MODEL_SLOTS:  # held only for the call itself, never while backing off
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.load(r)
        except Exception as exc:  # noqa: BLE001 - classified below; non-retryable errors re-raise as-is
            reason = _retryable(exc)
            if reason is None or attempt == attempts:
                raise
            backoff = min(20.0, RETRY_BASE * 2 ** (attempt - 1)) * (1 + random.random() * 0.5)
            hint = _retry_after(exc) if isinstance(exc, urllib.error.HTTPError) else None
            wait = min(max(backoff, hint or 0.0), max_wait - waited)
            if wait <= 0:
                raise
            if on_retry is not None:
                on_retry(attempt, wait, reason)
            _sleep(wait)
            waited += wait
    raise RuntimeError('unreachable')  # pragma: no cover


# ---------------------------------------------------------------- tool calls written as text

_TAG = re.compile(r'</?(?:tool_call|tool_calls|function_call|function|parameter)\b|<(?:function|parameter)=', re.I)
_BLOCK = re.compile(r'<tool_call>(.*?)(?:</tool_call>|\Z)', re.S | re.I)
_FUNCTION = re.compile(r'<function=\s*([^>\s]+)\s*>(.*?)(?:</function>|\Z)', re.S | re.I)
_PARAM = re.compile(r'<parameter=\s*([^>\s]+)\s*>(.*?)(?:</parameter>|(?=<parameter=)|\Z)', re.S | re.I)
_FENCE = re.compile(r'```(?:json|tool_call|tool_code)?\s*(.*?)```', re.S | re.I)


def _json_objects(text: str):
    """Every top-level {...} JSON object embedded in text, with its span."""
    dec = json.JSONDecoder()
    i = text.find('{')
    while i != -1:
        try:
            obj, end = dec.raw_decode(text, i)
        except ValueError:
            i = text.find('{', i + 1)
            continue
        yield obj, i, end
        i = text.find('{', end)


def _json_call(obj) -> tuple[str, dict] | None:
    """{"name": ..., "arguments"|"parameters": {...}} (or wrapped in "function") -> (name, args)."""
    if not isinstance(obj, dict):
        return None
    if isinstance(obj.get('function'), dict):
        obj = obj['function']
    name, args = obj.get('name'), obj.get('arguments', obj.get('parameters'))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return None
    if not isinstance(name, str) or not isinstance(args, dict):
        return None
    return name, args


def _param_value(raw: str):
    raw = raw.strip()
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def has_tool_markup(text: str | None, offered: set[str] | None = None) -> bool:
    text = text or ''
    if _TAG.search(text):
        return True
    return any(_json_call(o) and (offered is None or _json_call(o)[0] in offered) for o, _, _ in _json_objects(text))


def text_tool_calls(text: str | None, offered: set[str]) -> list[tuple[str, dict]]:
    """Tool calls written as text: <tool_call><function=NAME><parameter=K>V</parameter>...</function></tool_call>,
    <tool_call>{"name": ..., "arguments": {...}}</tool_call>, or a bare/fenced {"name": ..., "arguments": {...}}.
    JSON-ish calls count only when they name an offered tool; tag-style calls are returned whatever the name
    (the caller's allow-list rejects unknown ones as tool errors)."""
    text = text or ''
    out = []
    blocks = _BLOCK.findall(text) or ([text] if _FUNCTION.search(text) else [])
    for block in blocks:
        fns = _FUNCTION.findall(block)
        for name, body in fns:
            out.append((name.strip(), {k.strip(): _param_value(v) for k, v in _PARAM.findall(body)}))
        if not fns:
            out += [c for c in (_json_call(o) for o, _, _ in _json_objects(block)) if c]
    if not out:
        out = [c for c in (_json_call(o) for o, _, _ in _json_objects(text)) if c and c[0] in offered]
    return out


def strip_tool_markup(text: str | None, offered: set[str] | None = None) -> str:
    """Remove tool-call markup (tag style, and JSON tool-call objects) from model prose."""
    text = text or ''
    text = re.sub(r'<tool_call>.*?(?:</tool_call>|\Z)', ' ', text, flags=re.S | re.I)
    text = re.sub(r'<function=[^>]*>.*?(?:</function>|\Z)', ' ', text, flags=re.S | re.I)
    text = re.sub(r'</?(?:tool_calls?|function_call|function|parameter)\b[^>]*>|<parameter=[^>]*>', ' ', text, flags=re.I)

    def drop_json(t: str) -> str:
        for obj, start, end in sorted(_json_objects(t), key=lambda x: -x[1]):
            call = _json_call(obj)
            if call and (offered is None or call[0] in offered):
                t = t[:start] + ' ' + t[end:]
        return t

    text = _FENCE.sub(lambda m: '' if not drop_json(m.group(1)).strip() else m.group(0), text)
    text = drop_json(text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


# ---------------------------------------------------------------- tool arguments

NULLISH = {'none', 'null', '', 'n/a', 'undefined'}


def _is_nullish(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip().lower() in NULLISH)


def _to_int(v):
    if isinstance(v, str) and re.fullmatch(r'\s*-?\d+(?:\.0+)?\s*', v):
        return int(float(v))
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def int_kind(annotation) -> str | None:
    """'int' for int / int | None, 'list' for list[int] (optionally | None), else None."""
    args = typing.get_args(annotation)
    if annotation is int or int in args:
        return 'int'
    for a in (annotation, *args):
        if typing.get_origin(a) is list and typing.get_args(a) == (int,):
            return 'list'
    return None


def clean_args(args: dict, int_params: dict[str, str] | None = None) -> dict:
    """Drop arguments whose value is null-ish (None, "none", "null", "", "n/a"): the tool then uses its default.
    Coerce numeric strings for int parameters ({'year': 'int', 'field_ids': 'list'})."""
    out = {}
    for k, v in args.items():
        if isinstance(v, str):
            v = v.strip()
        if _is_nullish(v):
            continue
        kind = (int_params or {}).get(k)
        if kind == 'int':
            v = _to_int(v)
        elif kind == 'list':
            if isinstance(v, str):
                v = [p for p in re.split(r'[\s,\[\]]+', v) if p]
            if isinstance(v, list):
                v = [_to_int(x) for x in v if not _is_nullish(x)]
        out[k] = v
    return out


# ---------------------------------------------------------------- prose

_LONG_FLOAT = re.compile(r'(?<![\d.])(-?\d+)\.(\d{5,})(?![\d.])')


def round_long_floats(text: str) -> str:
    """Numbers with more than 4 decimals become 2 decimals (more only when 2 would show 0.00)."""
    def fix(m: re.Match) -> str:
        v = float(m.group(0))
        r = round(v, 2)
        d = 2
        while round(v, d) == 0 and v != 0 and d < 6:
            d += 1  # a tiny value keeps its first significant digit instead of showing 0.00
        return f'{round(v, d):.{d}f}'
    return _LONG_FLOAT.sub(fix, text)
