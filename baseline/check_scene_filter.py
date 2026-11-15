"""Check whether scene-wide cloud filtering discarded usable field observations.

Diagnostic only: two previously identified gaps, one processing version per date.
No source, baseline cache, feature table, labels, or predictions are modified.
"""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import geopandas as gpd
from pystac_client import Client
from pystac_client.stac_api_io import StacApiIO

from run_baseline import CATALOG, CONFIG, LAYER, SOURCE, extract_scene, verify_originals, write_json

OUT = HERE / 'outputs' / 'diagnostics' / 'scene_filter_gaps'
GAPS = [(323, 2023, '2023-09-08', '2023-10-01'),
        (327, 2021, '2021-10-03', '2021-11-15')]


def main():
    verify_originals()
    fields = gpd.read_file(SOURCE, layer=LAYER).to_crs(4326)
    client = Client.open(CATALOG, stac_io=StacApiIO(timeout=30))
    results = []
    for field_id, year, start, end in GAPS:
        job = fields.loc[fields.OBJECTID.eq(field_id), ['OBJECTID', 'geometry']].copy()
        assert len(job) == 1
        job['year'] = year
        geom = job.geometry.iloc[0].__geo_interface__
        items = list(client.search(collections=[CONFIG['collection']], intersects=geom,
                                   datetime=f'{start}/{end}').items())
        write_json(OUT / f'catalog_{field_id}_{year}.json', dict(
            query=dict(collection=CONFIG['collection'], intersects=geom, datetime=f'{start}/{end}',
                       scene_cloud_filter=None), items=[i.to_dict() for i in items]))
        # Later processing version wins for the same date; all candidate metadata is retained.
        by_date = {}
        for item in sorted(items, key=lambda i: (
                float(i.properties['s2:processing_baseline']),
                i.properties.get('s2:generation_time', ''), i.id)):
            by_date[item.datetime.date().isoformat()] = item
        print(f'Field {field_id} / {year}: {len(items)} items, {len(by_date)} sensing dates.', flush=True)
        for date, item in sorted(by_date.items()):
            records = extract_scene(item, job)
            if len(records) != 1:
                raise ValueError('Expected exactly one field-scene record')
            record = records[0]
            record['old_scene_filter_would_keep'] = item.properties['eo:cloud_cover'] < CONFIG['scene_cloud_lt']
            record['scene_cloud_percent'] = item.properties['eo:cloud_cover']
            results.append(record)
            write_json(OUT / 'observations.json', results)
            print(f'  {date}: tile cloud {record["scene_cloud_percent"]:.1f}%, '
                  f'field clear {record.get("clear_fraction", 0):.0%}, '
                  f'{record["status"]}, NDVI {record["ndvi"]}', flush=True)
        accepted = [r for r in results if r['OBJECTID'] == field_id and r['status'] == 'ok']
        discarded = [r for r in accepted if not r['old_scene_filter_would_keep']]
        print(f'  {len(discarded)} usable field-dates were excluded by the original scene filter.', flush=True)
    write_json(OUT / 'summary.json', dict(
        method='No scene-wide cloud threshold; original per-pixel masking and acceptance unchanged; latest processing per date',
        total_dates=len(results), read_errors=sum(r['status'] == 'read_error' for r in results),
        recovered_dates=[dict(field_id=r['OBJECTID'], year=r['year'], date=r['date'],
            ndvi=r['ndvi'], clear_fraction=r['clear_fraction'], scene_cloud_percent=r['scene_cloud_percent'])
            for r in results if r['status'] == 'ok' and not r['old_scene_filter_would_keep']]))
    verify_originals()
    if any(r['status'] == 'read_error' for r in results):
        raise RuntimeError('Diagnostic reads failed; see observations.json')


if __name__ == '__main__':
    main()
