#!/usr/bin/env python3
"""
2025 corn-for-grain and corn-for-silage harvested acres, every state + US, from public NASS reports
published BEFORE the January 2026 Annual Summary (which holds the answer and is never read here).

Method (per state):
  grain_2025  = NASS's latest pre-January grain-area forecast (Crop Production, Nov 14 2025;
                Sep 12 2025 for states the November table omits).
  silage_2025 = share_s x (planted_2025 - grain_2025)
                share_s = the state's mean over the three prior years of
                          silage / (planted - grain)      (the part of corn not harvested for grain
                                                           that historically went to silage)
                States with no published grain area (silage-only states) use silage / planted.
Uncertainty:
  SE combines (a) the year-to-year spread of share_s and (b) the typical November-to-final revision of
  grain area; both are measured, not assumed. The same method is backtested on 2023 and 2024 using those
  years' November reports, and the 95% interval width is scaled so the backtest coverage is honest.
Convergence: the same estimate as of each 2025 release (June Acreage, Aug, Sep, Nov Crop Production).

Standard library only (+ downloads from esmis.nal.usda.gov). Run from the repo root:
    python3 forecast/estimate_2025.py
Outputs in forecast/outputs/. Score with:
    python -m harvest.benchmark --predictions forecast/outputs/state_estimates_2025.csv --out forecast/outputs/benchmark.json
"""
import csv
import hashlib
import json
import math
import re
import statistics
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / 'cache'          # downloaded report text (gitignored; pinned by sha256 below)
OUT = HERE / 'outputs'
SOURCES = json.loads((HERE / 'sources.json').read_text(encoding='utf-8'))
FORBIDDEN = ('cropan26',)        # Jan 2026 Annual Summary = the 2025 answer. Never fetch or read it.

STATES = ['ALABAMA', 'ALASKA', 'ARIZONA', 'ARKANSAS', 'CALIFORNIA', 'COLORADO', 'CONNECTICUT', 'DELAWARE', 'FLORIDA',
          'GEORGIA', 'HAWAII', 'IDAHO', 'ILLINOIS', 'INDIANA', 'IOWA', 'KANSAS', 'KENTUCKY', 'LOUISIANA', 'MAINE', 'MARYLAND',
          'MASSACHUSETTS', 'MICHIGAN', 'MINNESOTA', 'MISSISSIPPI', 'MISSOURI', 'MONTANA', 'NEBRASKA', 'NEVADA',
          'NEW HAMPSHIRE', 'NEW JERSEY', 'NEW MEXICO', 'NEW YORK', 'NORTH CAROLINA', 'NORTH DAKOTA', 'OHIO', 'OKLAHOMA',
          'OREGON', 'PENNSYLVANIA', 'RHODE ISLAND', 'SOUTH CAROLINA', 'SOUTH DAKOTA', 'TENNESSEE', 'TEXAS', 'UTAH',
          'VERMONT', 'VIRGINIA', 'WASHINGTON', 'WEST VIRGINIA', 'WISCONSIN', 'WYOMING', 'UNITED STATES']
# A state name, an optional footnote like "2/", any dot leaders (long names get none), then the colon.
STATE_RE = re.compile(r'^(' + '|'.join(sorted((n.title() for n in STATES), key=len, reverse=True)) + r')\s*(?:\d/)?\s*\.*\s*:(.*)$')
NUM_RE = re.compile(r'^-?[\d,]+(?:\.\d+)?$')


# ---------------------------------------------------------------- inputs
def fetch(name: str) -> str:
    if any(name.startswith(f) for f in FORBIDDEN):
        raise RuntimeError(f'{name} is the 2025 answer key and must not be used')
    src = SOURCES['reports'][name]
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f'{name}.txt'
    if not path.exists():
        req = urllib.request.Request(src['url'], headers={'User-Agent': 'cutline-forecast/1.0 (hackathon research)'})
        with urllib.request.urlopen(req, timeout=120) as r:
            path.write_bytes(r.read())
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if src.get('sha256') and src['sha256'] != digest:
        raise RuntimeError(f'{name}: checksum changed ({digest}); re-verify the source before using it')
    return data.decode('latin-1')


def value(tok: str):
    tok = tok.strip()
    if NUM_RE.match(tok):
        return float(tok.replace(',', ''))
    return None  # (NA), (D), (Z), (X) = unknown, never zero


def table(text: str, title: str, header_hint: str) -> dict[str, list]:
    """State rows of the first real table whose title starts with `title` and whose header mentions
    `header_hint`. Reads across page breaks until the United States row."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith(title):
            continue
        head = '\n'.join(lines[i + 1:i + 12])
        if '-----' not in head or header_hint.lower() not in head.lower():
            continue
        rows: dict[str, list] = {}
        dashes = 0
        for row in lines[i + 1:i + 400]:
            if row.startswith('-----'):
                dashes += 1
                continue
            if dashes < 2:
                continue  # still in the title / column header block
            m = STATE_RE.match(row)
            if not m:
                continue
            name = re.sub(r'\s+', ' ', m.group(1)).strip().upper()
            vals = [value(t) for t in m.group(2).split()]
            if not any(v is not None for v in vals) and not any('(' in t for t in m.group(2).split()):
                continue  # a title line such as "United States: 2022-2024", not a data row
            if name == 'UNITED STATES':
                rows[name] = vals
                return rows
            rows.setdefault(name, vals)
        return rows
    raise ValueError(f'table not found: {title} / {header_hint}')


def k(x):  # report tables are in 1,000 acres
    return None if x is None else x * 1000


def annual(name: str):
    """Annual Summary covering years y-2..y: planted, grain, silage per state per year."""
    text = fetch(name)
    years = SOURCES['reports'][name]['years']
    pg = table(text, 'Corn Area Planted for All Purposes and Harvested for Grain', 'Area planted')
    sil = table(text, 'Corn for Silage Area Harvested', 'Area harvested')
    out = {}
    for st in set(pg) | set(sil):
        p, s = pg.get(st, []), sil.get(st, [])
        for j, y in enumerate(years):
            out[(st, y)] = dict(planted=k(p[j]) if len(p) > j else None,
                                grain=k(p[3 + j]) if len(p) > 3 + j else None,
                                silage=k(s[j]) if len(s) > j else None)
    return out


def planted_grain_report(name: str):
    """Acreage / Aug / Sep Crop Production table: planted (prev, cur), grain (prev, cur)."""
    t = table(fetch(name), 'Corn Area Planted for All Purposes and Harvested for Grain', 'Area planted')
    return {st: dict(planted=k(v[1]) if len(v) > 1 else None, grain=k(v[3]) if len(v) > 3 else None) for st, v in t.items()}


def grain_report(name: str):
    """November Crop Production grain table: area harvested (prev, cur)."""
    t = table(fetch(name), 'Corn for Grain Area Harvested, Yield, and Production', 'Area harvested')
    return {st: k(v[1]) if len(v) > 1 else None for st, v in t.items()}


# ---------------------------------------------------------------- method
def shares(hist: dict, state: str, years: list[int]):
    """Per-year silage share of non-grain corn (or of planted, for silage-only states)."""
    out = []
    for y in years:
        h = hist.get((state, y))
        if not h or h['silage'] is None or h['planted'] is None:
            continue
        resid = h['planted'] - (h['grain'] or 0)
        if h['grain'] is None:
            out.append(('planted', h['silage'] / h['planted']))
        elif resid > 0:
            out.append(('residual', min(1.0, h['silage'] / resid)))
    return out


METHODS = {
    'A': 'share of non-grain acres: mean[silage/(planted-grain)] x (planted - grain)',
    'B': 'persistence: last year silage x planted / last year planted',
    'C': 'share of planted: mean[silage/planted] x planted',
    'D': 'average of A and C',
}


def silage_alternatives(state, planted, grain, hist, years):
    prev = hist.get((state, years[-1]), {})
    sp = [hist[(state, y)]['silage'] / hist[(state, y)]['planted'] for y in years
          if hist.get((state, y), {}).get('silage') is not None and hist.get((state, y), {}).get('planted')]
    out = {}
    if prev.get('silage') is not None and prev.get('planted'):
        out['B'] = prev['silage'] * planted / prev['planted']
    if sp:
        out['C'] = statistics.mean(sp) * planted
    return out


def estimate_state(state, planted, grain, hist, years, grain_rel_sd, method='A'):
    sh = shares(hist, state, years)
    if planted is None or not sh:
        return None
    kinds = {s[0] for s in sh}
    vals = [s[1] for s in sh]
    mean = statistics.mean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else mean * 0.25
    if grain is None or 'planted' in kinds:
        base = planted
        silage = mean * base
        se = sd * base
        grain_out, grain_se = None, None
    else:
        base = max(0.0, planted - grain)
        silage = mean * base
        grain_se = grain * grain_rel_sd
        # grain revisions move the residual one-for-one
        se = math.sqrt((sd * base) ** 2 + (mean * grain_se) ** 2)
        grain_out = grain
    alts = silage_alternatives(state, planted, grain, hist, years)
    alts['A'] = silage
    if 'C' in alts:
        alts['D'] = (silage + alts['C']) / 2
    chosen = alts.get(method, silage)
    return dict(silage=chosen, silage_se=se, alternatives=alts, grain=grain_out, grain_se=grain_se,
                share_mean=mean, share_sd=sd, share_kind=sorted(kinds)[0], share_years=len(vals))


def run_year(target, planted_by, grain_by, hist, years, grain_rel_sd, method='A'):
    res = {}
    for st, planted in planted_by.items():
        if st == 'UNITED STATES':
            continue
        e = estimate_state(st, planted, grain_by.get(st), hist, years, grain_rel_sd, method)
        if e:
            res[st] = e
    return res


# ---------------------------------------------------------------- main
def main():
    a23, a24, a25 = annual('cropan23'), annual('cropan24'), annual('cropan25')
    hist = {**a23, **a24, **a25}  # later reports win on overlapping years (revised values)

    # grain-area revision, November forecast -> final, measured on 2023 and 2024
    revisions = []
    for nov, y in (('crop1123', 2023), ('crop1124', 2024)):
        for st, g in grain_report(nov).items():
            final = hist.get((st, y), {}).get('grain')
            if st != 'UNITED STATES' and g and final:
                revisions.append((final - g) / g)
    grain_rel_sd = math.sqrt(statistics.mean(r * r for r in revisions))

    # choose the silage method on the 2023/2024 backtest only (never on the 2025 answer)
    method_scores = {}
    for m_ in METHODS:
        err = tot = 0.0
        for nov, y in (('crop1123', 2023), ('crop1124', 2024)):
            g_nov = grain_report(nov)
            planted_y = {st: hist[(st, y)]['planted'] for (st, yy) in hist if yy == y and hist[(st, y)]['planted']}
            grain_y = {st: g_nov.get(st, hist.get((st, y), {}).get('grain')) for st in planted_y}
            for st, e in run_year(y, planted_y, grain_y, hist, [y - 3, y - 2, y - 1], 0.0, m_).items():
                truth = hist.get((st, y), {}).get('silage')
                if truth:
                    err += abs(e['silage'] - truth)
                    tot += truth
        method_scores[m_] = round(100 * err / tot, 2)
    method = min(method_scores, key=method_scores.get)

    # backtest the chosen method on 2023 and 2024
    backtest = []
    for nov, y in (('crop1123', 2023), ('crop1124', 2024)):
        g_nov = grain_report(nov)
        planted_y = {st: hist[(st, y)]['planted'] for (st, yy) in hist if yy == y and hist[(st, y)]['planted']}
        grain_y = {st: g_nov.get(st, hist.get((st, y), {}).get('grain')) for st in planted_y}
        est = run_year(y, planted_y, grain_y, hist, [y - 3, y - 2, y - 1], grain_rel_sd, method)
        for st, e in est.items():
            truth = hist.get((st, y), {})
            if truth.get('silage'):
                backtest.append(dict(year=y, state=st, kind='silage', est=e['silage'], se=e['silage_se'], truth=truth['silage']))
            if e['grain'] and truth.get('grain'):
                backtest.append(dict(year=y, state=st, kind='grain', est=e['grain'], se=e['grain_se'], truth=truth['grain']))

    # scale intervals so 95% of backtest truths fall inside (z-scores of backtest errors)
    def zscale(kind):
        zs = sorted(abs(b['truth'] - b['est']) / b['se'] for b in backtest if b['kind'] == kind and b['se'])
        return max(1.96, zs[min(len(zs) - 1, math.ceil(0.95 * len(zs)) - 1)]) if zs else 1.96
    z_sil, z_gr = zscale('silage'), zscale('grain')

    def bt_summary(kind):
        rows = [b for b in backtest if b['kind'] == kind]
        rel = [abs(b['est'] - b['truth']) / b['truth'] for b in rows if b['truth']]
        tot = {}
        for y in (2023, 2024):
            ry = [b for b in rows if b['year'] == y]
            tot[y] = dict(est=sum(b['est'] for b in ry), truth=sum(b['truth'] for b in ry))
        inside = sum(1 for b in rows if abs(b['truth'] - b['est']) <= (z_sil if kind == 'silage' else z_gr) * b['se'])
        return dict(state_years=len(rows), median_abs_pct_error=round(100 * statistics.median(rel), 1),
                    mean_abs_pct_error=round(100 * statistics.mean(rel), 1),
                    covered_by_95_interval=round(inside / len(rows), 3),
                    us_total={y: dict(est=round(v['est']), truth=round(v['truth']),
                                      pct_error=round(100 * (v['est'] - v['truth']) / v['truth'], 2)) for y, v in tot.items()})

    # 2025 as of each pre-January release
    hist_years = [2022, 2023, 2024]
    sep = planted_grain_report('crop0925')
    vintages = [
        ('2025-06-30', 'June Acreage', planted_grain_report('acrg0625'), None),
        ('2025-08-12', 'Aug Crop Production', planted_grain_report('crop0825'), None),
        ('2025-09-12', 'Sep Crop Production', sep, None),
        ('2025-11-14', 'Nov Crop Production', sep, grain_report('crop1125')),
    ]
    by_date = []
    final = None
    for date, label, pg, nov in vintages:
        planted = {st: v['planted'] for st, v in pg.items() if v['planted']}
        grain = {st: (nov.get(st) if nov and nov.get(st) else v['grain']) for st, v in pg.items()}
        est = run_year(2025, planted, grain, hist, hist_years, grain_rel_sd, method)
        us_sil = sum(e['silage'] for e in est.values())
        us_sil_se = math.sqrt(sum(e['silage_se'] ** 2 for e in est.values()))
        # NASS's own US grain row includes states its state table omits
        us_row = (nov or {}).get('UNITED STATES') or pg.get('UNITED STATES', {}).get('grain')
        us_gr = us_row or sum(e['grain'] for e in est.values() if e['grain'])
        us_gr_se = math.sqrt(sum(e['grain_se'] ** 2 for e in est.values() if e['grain_se']))
        by_date.append(dict(as_of=date, source=label, us_silage=round(us_sil), us_silage_se=round(us_sil_se),
                            us_silage_low=round(us_sil - z_sil * us_sil_se), us_silage_high=round(us_sil + z_sil * us_sil_se),
                            us_grain=round(us_gr), us_grain_se=round(us_gr_se),
                            md_silage=round(est['MARYLAND']['silage']) if 'MARYLAND' in est else None,
                            md_silage_se=round(est['MARYLAND']['silage_se']) if 'MARYLAND' in est else None))
        final = est

    OUT.mkdir(exist_ok=True)
    rows, states = [], []
    for st in sorted(final):
        e = final[st]
        rec = dict(state=st, silage=round(e['silage']), silage_se=round(e['silage_se']),
                   silage_cv_pct=round(100 * e['silage_se'] / e['silage'], 1) if e['silage'] else None,
                   silage_low=max(0, round(e['silage'] - z_sil * e['silage_se'])), silage_high=round(e['silage'] + z_sil * e['silage_se']),
                   grain=round(e['grain']) if e['grain'] else None,
                   grain_se=round(e['grain_se']) if e['grain_se'] else None,
                   grain_cv_pct=round(100 * e['grain_se'] / e['grain'], 1) if e['grain'] else None,
                   grain_low=round(e['grain'] - z_gr * e['grain_se']) if e['grain'] else None,
                   grain_high=round(e['grain'] + z_gr * e['grain_se']) if e['grain'] else None,
                   share_of_non_grain=round(e['share_mean'], 4), share_sd=round(e['share_sd'], 4), share_base=e['share_kind'])
        states.append(rec)
        rows.append(['2025', 'STATE', st, 'CORN, SILAGE - ACRES HARVESTED', 'TOTAL', f"{rec['silage']:,}"])
        if rec['grain']:
            rows.append(['2025', 'STATE', st, 'CORN, GRAIN - ACRES HARVESTED', 'TOTAL', f"{rec['grain']:,}"])
    us = by_date[-1]
    rows.append(['2025', 'NATIONAL', 'US TOTAL', 'CORN, SILAGE - ACRES HARVESTED', 'TOTAL', f"{us['us_silage']:,}"])
    rows.append(['2025', 'NATIONAL', 'US TOTAL', 'CORN, GRAIN - ACRES HARVESTED', 'TOTAL', f"{us['us_grain']:,}"])
    with (OUT / 'state_estimates_2025.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Year', 'Geo Level', 'State', 'Data Item', 'Domain', 'Value'])
        w.writerows(rows)

    summary = dict(
        method=('grain = latest pre-January NASS grain-area forecast (Nov 14 2025; Sep 12 2025 where November omits the state). '
                'silage = state share x (planted - grain), share = mean of silage/(planted - grain) over 2022-2024 '
                '(silage/planted for states without published grain area). SE from year-to-year share spread and '
                'measured Nov->final grain revisions; 95% interval scaled so backtest coverage is >= 95%.'),
        answer_key_excluded='Crop Production Annual Summary, January 2026 (cropan26) is never downloaded or read.',
        sources={k_: dict(title=v['title'], released=v['released'], url=v['url']) for k_, v in SOURCES['reports'].items()},
        silage_method=dict(chosen=method, description=METHODS[method],
                           backtest_acre_weighted_abs_pct_error=method_scores, candidates=METHODS,
                           rule='lowest acre-weighted absolute error on the 2023 and 2024 backtests; 2025 answers never used'),
        grain_revision_rel_sd=round(grain_rel_sd, 4), interval_z=dict(silage=round(z_sil, 2), grain=round(z_gr, 2)),
        backtest=dict(silage=bt_summary('silage'), grain=bt_summary('grain')),
        us=dict(silage=us['us_silage'], silage_se=us['us_silage_se'], silage_low=us['us_silage_low'], silage_high=us['us_silage_high'],
                silage_cv_pct=round(100 * us['us_silage_se'] / us['us_silage'], 2),
                grain=us['us_grain'], grain_se=us['us_grain_se'],
                grain_cv_pct=round(100 * us['us_grain_se'] / us['us_grain'], 2)),
        convergence=by_date, states=states)
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(json.dumps(dict(us=summary['us'], backtest=summary['backtest'], maryland=next(s for s in states if s['state'] == 'MARYLAND')), indent=1))


if __name__ == '__main__':
    main()
