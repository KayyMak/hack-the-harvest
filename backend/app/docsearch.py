"""Keyword retrieval (BM25) over the team's own analysis write-ups, for grounding the market report.

Standard library only. The index is built lazily and rebuilt when a source file changes. Chunk ids
look like `docs/MODEL_REVIEW.md#2` so a report sentence can cite the exact passage it rests on.
"""
import json
import math
import re
from collections import Counter
from pathlib import Path

from . import artifacts

ROOT = artifacts.ROOT
# Analysis and results documents only (not contributor/process docs).
CORPUS = [
    'data_sources.md',
    'data/README.md',
    'docs/MODEL_REVIEW.md',
    'docs/ML_EXPERIMENTS.md',
    'baseline/README.md',
    'baseline/outputs/results.md',
    'baseline/outputs/decline_rule/results.md',
    'baseline/NEMOTRON_COMPARISON.md',
    'baseline/SCENE_FILTER_EXPERIMENT.md',
    'baseline/outputs/experiments/no_scene_cloud_filter/results.md',
    'baseline/outputs/diagnostics/field_323_and_327/findings.md',
    'market/README.md',
]
FORECAST_SUMMARY = 'forecast/outputs/summary.json'  # its method text is indexed as one passage
CHUNK, OVERLAP = 800, 150
TOKEN = re.compile(r'[a-z0-9]+')
STOP = set('the a an and or of to in for on at by with from is are was were be as it its this that these those '
           'not no but if than then so we our they their into per each only also can may'.split())

_cache: dict = {'key': None, 'chunks': [], 'df': Counter(), 'avg': 1.0}


def _tokens(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP]


def _chunks(path: str, text: str) -> list[dict]:
    out, start, n = [], 0, 0
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    while start < len(text):
        end = min(len(text), start + CHUNK)
        if end < len(text):  # end on a paragraph or sentence boundary when one is close
            cut = max(text.rfind('\n\n', start + CHUNK // 2, end), text.rfind('. ', start + CHUNK // 2, end))
            end = cut + 1 if cut > 0 else end
        out.append({'id': f'{path}#{n}', 'source': path, 'text': text[start:end].strip()})
        n += 1
        if end >= len(text):
            break
        start = max(end - OVERLAP, start + 1)
    return out


def _sources() -> list[tuple[str, str]]:
    docs = []
    for rel in CORPUS:
        p = ROOT / rel
        if p.exists():
            docs.append((rel, p.read_text(encoding='utf-8', errors='replace')))
    p = ROOT / FORECAST_SUMMARY
    if p.exists():
        try:
            s = json.loads(p.read_text(encoding='utf-8'))
            docs.append((FORECAST_SUMMARY, f"2025 state acreage forecast method. {s.get('method', '')} "
                                           f"Silage method: {s.get('silage_method', '')}"))
        except ValueError:
            pass
    return docs


def _index() -> dict:
    key = tuple((rel, (ROOT / rel).stat().st_mtime) for rel in CORPUS + [FORECAST_SUMMARY] if (ROOT / rel).exists())
    if _cache['key'] != key:
        chunks = [c for rel, text in _sources() for c in _chunks(rel, text)]
        for c in chunks:
            c['tf'] = Counter(_tokens(c['text']))
            c['len'] = sum(c['tf'].values()) or 1
        df = Counter(t for c in chunks for t in c['tf'])
        _cache.update(key=key, chunks=chunks, df=df, avg=sum(c['len'] for c in chunks) / max(1, len(chunks)))
    return _cache


def search(query: str, k: int = 4) -> list[dict]:
    """Top-k passages by BM25. Returns [] when nothing matches (never invented text)."""
    idx = _index()
    n, q = len(idx['chunks']), set(_tokens(query))
    if not n or not q:
        return []
    k1, b = 1.5, 0.75
    scored = []
    for c in idx['chunks']:
        s = 0.0
        for t in q:
            f = c['tf'].get(t)
            if f:
                idf = math.log(1 + (n - idx['df'][t] + 0.5) / (idx['df'][t] + 0.5))
                s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * c['len'] / idx['avg']))
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [{'id': c['id'], 'source': c['source'], 'text': c['text']} for _, c in scored[:k]]


def corpus_files() -> list[str]:
    return [rel for rel, _ in _sources()]
