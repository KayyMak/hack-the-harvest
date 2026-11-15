#!/usr/bin/env python3
"""
Turn FSA "Crop Acreage Data" (December release, before NASS's January Annual Summary) into state totals of
corn planted acres by intended use. Output: forecast/fsa_corn_by_state.csv (committed; the ~20 MB source
workbooks are not). Re-run to rebuild from the pinned downloads:

    python3 forecast/fsa_extract.py            # needs openpyxl

Source: https://www.fsa.usda.gov/tools/informational/freedom-information-act-foia/electronic-reading-room/frequently-requested/crop-acreage-data
Only field corn is kept (crop CORN; sweet corn types are excluded). "Planted and failed" acres are used.
"""
import csv
import hashlib
import io
import json
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
RAW = HERE / 'cache' / 'fsa'          # zips are large; kept out of git via .gitignore in cache/fsa
OUT = HERE / 'fsa_corn_by_state.csv'
FILES = json.loads((HERE / 'sources.json').read_text(encoding='utf-8'))['fsa']


def download(entry) -> bytes:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / entry['file']
    if not path.exists():
        req = urllib.request.Request(entry['url'], headers={'User-Agent': 'Mozilla/5.0 (cutline research script)'})
        with urllib.request.urlopen(req, timeout=300) as r:
            path.write_bytes(r.read())
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if entry.get('sha256') and entry['sha256'] != digest:
        raise RuntimeError(f"{entry['file']}: checksum changed ({digest})")
    return data


def state_totals(data: bytes):
    z = zipfile.ZipFile(io.BytesIO(data))
    name = next(n for n in z.namelist() if n.lower().endswith('.xlsx'))
    wb = openpyxl.load_workbook(io.BytesIO(z.read(name)), read_only=True, data_only=True)
    ws = wb['county_data']
    rows = ws.iter_rows(values_only=True)
    header = None
    for r in rows:
        if r and 'Crop' in r and 'Intended Use' in r:
            header = list(r)
            break
    col = {h: i for i, h in enumerate(header)}
    tot = defaultdict(float)
    for r in rows:
        if not r or r[col['Crop']] is None or str(r[col['Crop']]).strip().upper() != 'CORN':
            continue
        ctype = str(r[col['Crop Type']] or '').upper()
        if ctype.startswith('SWEET'):
            continue
        use = str(r[col['Intended Use']] or 'Blank').strip().title()
        planted = r[col['Planted Acres']] or 0
        failed = r[col['Failed Acres']] or 0
        try:
            acres = float(planted) + float(failed)
        except (TypeError, ValueError):
            continue
        tot[(str(r[col['State']]).strip().upper(), use)] += acres
    return name, tot


def main():
    out = []
    for entry in FILES:
        name, tot = state_totals(download(entry))
        for (state, use), acres in sorted(tot.items()):
            out.append(dict(year=entry['year'], as_of=entry['as_of'], source_file=name, state=state, intended_use=use, acres=round(acres, 1)))
        print(entry['year'], entry['as_of'], name, len(tot), 'state-use rows')
    with OUT.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)


if __name__ == '__main__':
    main()
