"""Month-by-month 2025 market timeline from what was public on each date, plus the team's silage estimate.

    python3 market/build_timeline.py        # writes market/data/market_timeline.json

At each 2025 release (June Acreage, Aug/Sep/Nov Crop Production) this records:
  - NASS's own forecasts published that day: US and Maryland grain acres, grain yield and grain
    production (no yield/production in June: NASS's first corn yield forecast is in August);
  - the team forecast's silage-acre estimate for that date (forecast/outputs/summary.json, built only
    from reports released before January 2026; the January answer key is never read);
  - the 2024 official baseline (Crop Production 2024 Summary, Crop Values 2024 Summary).
Derived values (supply change vs 2024, grain bushels kept off the market by silage) are computed here,
once, so the report quotes them instead of doing arithmetic. Nothing after each date is used for that date.
Reuses the team forecast's own NASS text parser and cached reports (forecast/cache/), so no network.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'forecast'))
import estimate_2025 as F  # noqa: E402  (team forecast: fetch() reads forecast/cache, table() parses NASS text)

OUT = ROOT / 'market' / 'data' / 'market_timeline.json'
NASS = ROOT / 'market' / 'data' / 'nass_market.csv'
SUMMARY = ROOT / 'forecast' / 'outputs' / 'summary.json'
SEASON, BASE = 2025, 2024
RELEASES = [  # (as_of, label, report name, report kind)
    ('2025-06-30', 'NASS Acreage (June 30)', 'acrg0625', 'acreage'),
    ('2025-08-12', 'NASS Crop Production (Aug 12)', 'crop0825', 'production'),
    ('2025-09-12', 'NASS Crop Production (Sep 12)', 'crop0925', 'production'),
    ('2025-11-14', 'NASS Crop Production (Nov 14)', 'crop1125', 'production'),
]
GRAIN_TABLE = ('Corn for Grain Area Harvested, Yield, and Production', 'Area harvested')
PLANTED_TABLE = ('Corn Area Planted for All Purposes and Harvested for Grain', 'Area planted')


def baseline() -> dict:
    rows = [r for r in csv.DictReader(NASS.open(encoding='utf-8')) if int(r['year']) == BASE]
    b = {('md_' if r['geo'] == 'Maryland' else 'us_') + r['item']: float(r['value']) for r in rows}
    b['price_preliminary'] = any(r['preliminary'] == 'True' for r in rows if r['item'] == 'grain_price')
    return b


def nass_on(name: str, kind: str) -> dict:
    """NASS forecasts for the 2025 crop published in one report (1,000 acres, bu/acre, 1,000 bu)."""
    text = F.fetch(name)
    out = {}
    for geo, key in (('MARYLAND', 'md'), ('UNITED STATES', 'us')):
        if kind == 'acreage':
            v = F.table(text, *PLANTED_TABLE)[geo]  # planted prev, planted cur, grain prev, grain cur
            out[key] = dict(grain_acres=v[3] * 1000, yield_bu=None, production_bu=None)
        else:
            v = F.table(text, *GRAIN_TABLE)[geo]  # area prev, area cur, yield prev, [earlier fcsts...], yield cur, prod prev, prod cur
            out[key] = dict(grain_acres=v[1] * 1000, yield_bu=v[-3], production_bu=v[-1] * 1000)
    return out


def main() -> None:
    b = baseline()
    s = json.loads(SUMMARY.read_text(encoding='utf-8'))
    conv = {p['as_of']: p for p in s['convergence']}
    z = s['interval_z']['silage']
    base_us_silage_bu = b['us_silage_area_harvested'] * 1000 * b['us_grain_yield']
    base_md_silage_bu = b['md_silage_area_harvested'] * 1000 * b['md_grain_yield']
    points = []
    for as_of, label, name, kind in RELEASES:
        n, c = nass_on(name, kind), conv[as_of]
        us, md = n['us'], n['md']
        md_lo, md_hi = max(0, c['md_silage'] - z * c['md_silage_se']), c['md_silage'] + z * c['md_silage_se']
        p = dict(as_of=as_of, source=label, report=name,
                 us_grain_acres=us['grain_acres'], us_grain_yield=us['yield_bu'], us_grain_production=us['production_bu'],
                 us_silage_acres=c['us_silage'], us_silage_low=c['us_silage_low'], us_silage_high=c['us_silage_high'],
                 md_grain_acres=md['grain_acres'], md_grain_yield=md['yield_bu'], md_grain_production=md['production_bu'],
                 md_silage_acres=c['md_silage'], md_silage_low=round(md_lo), md_silage_high=round(md_hi))
        p['md_silage_share'] = c['md_silage'] / (c['md_silage'] + md['grain_acres'])
        if us['production_bu'] is not None:
            p['us_production_change_vs_base'] = us['production_bu'] / (b['us_grain_production'] * 1000) - 1
            # Grain the silage acres would have produced at this month's yield forecast: kept off the grain market.
            p['us_silage_grain_equivalent_bu'] = c['us_silage'] * us['yield_bu']
            p['us_silage_grain_equivalent_change_bu'] = p['us_silage_grain_equivalent_bu'] - base_us_silage_bu
            p['md_silage_grain_equivalent_bu'] = c['md_silage'] * md['yield_bu']
            p['md_silage_grain_equivalent_change_bu'] = p['md_silage_grain_equivalent_bu'] - base_md_silage_bu
        points.append(p)
    out = dict(
        season=SEASON, baseline_year=BASE,
        baseline=dict(us_grain_production=b['us_grain_production'] * 1000, us_grain_yield=b['us_grain_yield'],
                      us_grain_price=b['us_grain_price'], us_silage_acres=b['us_silage_area_harvested'] * 1000,
                      md_grain_acres=b['md_grain_area_harvested'] * 1000, md_silage_acres=b['md_silage_area_harvested'] * 1000,
                      md_grain_yield=b['md_grain_yield'], md_grain_price=b['md_grain_price'],
                      price_preliminary=b['price_preliminary'],
                      us_silage_grain_equivalent_bu=base_us_silage_bu, md_silage_grain_equivalent_bu=base_md_silage_bu,
                      source='USDA NASS Crop Production 2024 Summary and Crop Values 2024 Summary'),
        points=points,
        method=('Grain figures are NASS forecasts published on each date. Silage acres are the team forecast '
                '(forecast/estimate_2025.py) as of each date, 95% range from its standard error x '
                f'{z} (the backtest-calibrated interval). Grain equivalent = silage acres x that date\'s grain-yield forecast.'),
        answer_key_excluded='Crop Production Annual Summary January 2026 (cropan26) is never read.',
    )
    OUT.write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    for p in points:
        print(p['as_of'], 'US grain prod', p['us_grain_production'], 'chg', round(p.get('us_production_change_vs_base') or 0, 4),
              '| US silage', p['us_silage_acres'], '| MD silage', p['md_silage_acres'], 'share', round(p['md_silage_share'], 4))


if __name__ == '__main__':
    main()
