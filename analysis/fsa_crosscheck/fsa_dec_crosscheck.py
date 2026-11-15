"""After-the-fact cross-check (does not change the submitted forecast): did FSA's December 2025 crop acreage release
(public, released before January 2026) already show the 2025 silage shift in the states we over-called?

Compares corn planted for SILAGE (FSA intended use) in the December 2025 and December 2024 releases (same vintage), by
state, with our 2025 silage error. Downloads the two workbooks (~22 MB each) into analysis/fsa_crosscheck/cache/.

    python analysis/fsa_crosscheck/fsa_dec_crosscheck.py      (needs pandas + openpyxl)

Source page: https://www.fsa.usda.gov/news-room/efoia/electronic-reading-room/frequently-requested-information/crop-acreage-data/index
"""
import json
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = HERE / 'cache'
FILES = {  # release "as of" date -> data zip linked from FSA's crop acreage page
    '2025-12': 'https://www.fsa.usda.gov/sites/default/files/2025-12/UhYA3k5AKxVM.zip',  # 2025_fsa_acres_web_120125.xlsx
    '2024-12': 'https://www.fsa.usda.gov/sites/default/files/2024-12/kUE2Z66bQlHK.zip',  # 2024_fsa_acres_web_120224.xlsx
}
FORECAST = ROOT / 'web' / 'public' / 'forecast_2025.json'


def silage_by_state(tag: str) -> pd.Series:
    path = CACHE / f'{tag}.zip'
    if not path.exists():
        CACHE.mkdir(exist_ok=True)
        req = urllib.request.Request(FILES[tag], headers={'User-Agent': 'Mozilla/5.0'})
        path.write_bytes(urllib.request.urlopen(req, timeout=300).read())
    z = zipfile.ZipFile(path)
    df = pd.read_excel(z.open(z.namelist()[0]), sheet_name='county_data', header=1, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    corn = df[(df['Crop'].str.strip().str.upper() == 'CORN') & (df['Intended Use'].str.strip().str.upper() == 'SILAGE')].copy()
    corn['acres'] = pd.to_numeric(corn['Planted Acres'], errors='coerce').fillna(0)
    return corn.groupby(corn['State'].str.strip().str.upper())['acres'].sum()


def main():
    a, b = silage_by_state('2025-12'), silage_by_state('2024-12')
    fc = json.loads(FORECAST.read_text(encoding='utf-8'))
    rows = []
    for s in fc['states']:
        c = s['silage']
        if not c or c.get('nass') is None or c.get('err') is None or s['state'] not in a or s['state'] not in b:
            continue
        if b[s['state']] < 500:
            continue
        rows.append(dict(state=s['state'], our_error_pct=round(100 * c['err'], 1),
                         fsa_dec2024=int(round(b[s['state']])), fsa_dec2025=int(round(a[s['state']])),
                         fsa_change_pct=float(round(100 * (a[s['state']] / b[s['state']] - 1), 1))))
    rows.sort(key=lambda r: -r['our_error_pct'])
    over = [r for r in rows if r['our_error_pct'] > 10]
    under = [r for r in rows if r['our_error_pct'] < -10]
    out = dict(states=len(rows), over_called=len(over), over_called_fsa_down=int(sum(r['fsa_change_pct'] < 0 for r in over)),
               under_called=len(under), under_called_fsa_up=int(sum(r['fsa_change_pct'] > 0 for r in under)),
               us_fsa_dec2024=int(round(b.sum())), us_fsa_dec2025=int(round(a.sum())),
               us_fsa_change_pct=float(round(100 * (a.sum() / b.sum() - 1), 1)), rows=rows)
    (HERE / 'results.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in out.items() if k != 'rows'}, indent=1))


if __name__ == '__main__':
    main()
