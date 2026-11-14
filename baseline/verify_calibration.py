"""Check the NDVI offset convention against one product XML per processing baseline."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import planetary_computer as pc
import requests

here = Path(__file__).resolve().parent
examples = {}
for path in sorted((here / 'cache/catalog').glob('*.json')):
    for item in json.loads(path.read_text())['items']:
        examples.setdefault(item['properties']['s2:processing_baseline'], item)
results = []
for baseline, item in sorted(examples.items()):
    url = item['assets']['product-metadata']['href']
    response = requests.get(pc.sign(url), timeout=60)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    quantification, offsets = {}, {}
    for node in root.iter():
        tag = node.tag.split('}')[-1]
        if tag == 'BOA_QUANTIFICATION_VALUE':
            quantification[tag] = float(node.text)
        if tag == 'BOA_ADD_OFFSET':
            offsets[node.attrib['band_id']] = float(node.text)
    assert quantification['BOA_QUANTIFICATION_VALUE'] == 10000
    expected = -1000 if float(baseline) >= 4 else 0
    # ESA band IDs are zero-based: B04=3, B08=7. Old XML omits zero offsets.
    for band_id in ['3', '7']:
        assert offsets.get(band_id, 0) == expected, (baseline, band_id, offsets)
    result = dict(processing_baseline=baseline, item_id=item['id'], metadata_url=url,
        quantification=quantification, boa_add_offsets=offsets, expected_dn_offset=expected,
        passed=True)
    results.append(result)
    print(f'Baseline {baseline}: quantification 10000, red/NIR offset {expected}, verified.', flush=True)
(here / 'outputs/calibration_verification.json').write_text(
    json.dumps(results, indent=2), encoding='utf-8')
