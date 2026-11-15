"""Download the public NASS releases the market report needs and extract a tidy table.

    python market/fetch_nass.py

No API key. Sources: USDA NASS via ESMIS (USDA Economics, Statistics and Market Information System).
  - Crop Production Annual Summaries (cropan23/24/25, released each January) — corn area planted,
    area harvested for grain, grain yield and production; corn for silage area, yield and production.
  - Crop Values Annual Summaries (cpvl0223/24/25, released each February) — corn-for-grain
    marketing-year average price received and value of production (latest year preliminary).
Each release covers three years and revises earlier ones, so every value is taken from the NEWEST
release that has it. Coverage: 2020-2024, Maryland and United States.

Writes market/data/nass_market.csv and market/data/nass_sources.json (URLs, SHA-256, fetch date).
Raw downloads go to market/data/raw/ (git-ignored). Tables are found by title, not page number.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'data'
RAW = DATA / 'raw'
ESMIS = 'https://esmis.nal.usda.gov/sites/default/release-files'
PRODUCTION_PAGE = 'https://esmis.nal.usda.gov/concern/publications/k3569432s'
VALUES_PAGE = 'https://esmis.nal.usda.gov/concern/publications/k35694332'
# Oldest first: later releases overwrite the values they revise.
RELEASES = {
    'cropan23': dict(url=f'{ESMIS}/k3569432s/9306v916d/6395xk01g/cropan23.zip', title='Crop Production 2022 Summary', released='2023-01-12', page=PRODUCTION_PAGE),
    'cropan24': dict(url=f'{ESMIS}/k3569432s/ns065v292/br86cq93r/cropan24.zip', title='Crop Production 2023 Summary', released='2024-01-12', page=PRODUCTION_PAGE),
    'cropan25': dict(url=f'{ESMIS}/k3569432s/nk324887m/4j03ft278/cropan25.zip', title='Crop Production 2024 Summary', released='2025-01-10', page=PRODUCTION_PAGE),
    'cpvl0223': dict(url=f'{ESMIS}/k35694332/b85171637/34850w190/cpvl0223.zip', title='Crop Values 2022 Summary', released='2023-02-24', page=VALUES_PAGE),
    'cpvl0224': dict(url=f'{ESMIS}/k35694332/g158d382b/gm80kj25n/cpvl0224.zip', title='Crop Values 2023 Summary', released='2024-02-26', page=VALUES_PAGE),
    'cpvl0225': dict(url=f'{ESMIS}/k35694332/4m90gs04k/5h73rr79v/cpvl0225.zip', title='Crop Values 2024 Summary', released='2025-02-24', page=VALUES_PAGE),
}
# (title prefix, items in column order, units). Each item spans three year columns.
TABLES = [
    ('Corn Area Planted for All Purposes and Harvested for Grain, Yield, and Production', False,
     ['planted_all_purposes', 'grain_area_harvested'], ['1000 acres', '1000 acres']),
    ('Corn Area Planted for All Purposes and Harvested for Grain, Yield, and Production', True,
     ['grain_yield', 'grain_production'], ['bu/acre', '1000 bu']),
    ('Corn for Silage Area Harvested, Yield, and Production', False,
     ['silage_area_harvested', 'silage_yield', 'silage_production'], ['1000 acres', 'tons/acre', '1000 tons']),
    ('Corn for Grain Price per Bushel and Value of Production', False,
     ['grain_price', 'grain_value_of_production'], ['$/bu', '1000 $']),
]
GEOS = ('Maryland', 'United States')


def download(name: str) -> bytes:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f'{name}.zip'
    if not path.exists():
        req = urllib.request.Request(RELEASES[name]['url'], headers={'User-Agent': 'hack-the-harvest-market/1.0'})
        with urllib.request.urlopen(req, timeout=120) as r:
            path.write_bytes(r.read())
    return path.read_bytes()


def tables_of(blob: bytes) -> list[tuple[str, list[list[str]]]]:
    out = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for member in sorted(z.namelist()):
            if member.endswith('.csv'):
                rows = list(csv.reader(io.StringIO(z.read(member).decode('latin-1'))))  # NASS CSVs are Latin-1
                title = next((r[2] for r in rows if len(r) > 2 and r[1] == 't' and 'Summary' not in r[2]), '')
                out.append((title, rows))
    return out


def main() -> None:
    values = {}
    for name in RELEASES:
        for title, rows in tables_of(download(name)):
            for prefix, continued, items, units in TABLES:
                if not title.startswith(prefix) or ('(continued)' in title) != continued:
                    continue
                years_row = next(r for r in rows if len(r) > 3 and r[1] == 'h' and r[3][:2] == '20')
                cols = years_row[3:]
                for r in rows:
                    if len(r) < 4 or r[1] != 'd' or r[2] not in GEOS:
                        continue
                    for i, raw in enumerate(r[3:3 + 3 * len(items)]):
                        item, unit = items[i // 3], units[i // 3]
                        year = int(cols[i].split()[0])
                        num = None if raw.strip() in ('(NA)', '(D)', '(X)', '(Z)', '') else float(raw.replace(',', ''))
                        values[(year, r[2], item)] = dict(year=year, geo=r[2], item=item, value=num, unit=unit,
                                                          preliminary='1/' in cols[i], release=name, raw=raw)
    out = sorted(values.values(), key=lambda v: (v['year'], v['geo'], v['item']))
    years = sorted({v['year'] for v in out})
    assert years == [2020, 2021, 2022, 2023, 2024], years
    for y in years:
        for g in GEOS:
            got = {v['item'] for v in out if v['year'] == y and v['geo'] == g}
            need = {i for _, _, items, _ in TABLES for i in items}
            assert got == need, (y, g, need - got)
    DATA.mkdir(exist_ok=True)
    with (DATA / 'nass_market.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    sources = {name: dict(meta, sha256=hashlib.sha256(download(name)).hexdigest(), fetched=dt.date.today().isoformat())
               for name, meta in RELEASES.items()}
    (DATA / 'nass_sources.json').write_text(json.dumps(sources, indent=1) + '\n', encoding='utf-8')
    print(f'wrote {len(out)} values ({years[0]}-{years[-1]}) to {DATA / "nass_market.csv"}')


if __name__ == '__main__':
    main()
