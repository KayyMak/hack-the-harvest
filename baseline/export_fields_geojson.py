"""Export BARC field polygons for web maps: baseline/outputs/fields.geojson (EPSG:4326).

    python baseline/export_fields_geojson.py

Reads the source GeoPackage read-only (NAD83 / Maryland ftUS), reprojects to WGS84
longitude/latitude, rounds coordinates to 6 decimals (about 0.1 m), and keeps the field
attributes plus the reference labels per year. Labels are named reference_<year> so they are
never confused with model predictions; blank source labels stay null (unknown, not Grain).
"""
import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'BARC_Corn.2021-2023.gpkg'
LAYER = 'barc_silage_grain_corn20212023'
OUT = ROOT / 'baseline' / 'outputs' / 'fields.geojson'
YEARS = (2021, 2022, 2023)


def _round(coords):
    if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
        return [round(float(c), 6) for c in coords[:2]]
    return [_round(c) for c in coords]


def _label(value):
    if value is None or (isinstance(value, float) and value != value):  # None or NaN = blank
        return None
    value = str(value).strip()
    if value == '':
        return None
    if value not in ('Grain', 'Silage'):
        raise ValueError(f'unexpected label {value!r}')
    return value


def main() -> dict:
    fields = gpd.read_file(SOURCE, layer=LAYER)
    if fields.crs is None:
        raise ValueError('source GeoPackage has no CRS')
    if not fields.is_valid.all() or fields.geometry.is_empty.any():
        raise ValueError('invalid or empty field geometry')
    if fields['OBJECTID'].duplicated().any():
        raise ValueError('duplicate OBJECTID')
    wgs = fields.to_crs(4326).sort_values('OBJECTID')
    features = []
    for _, row in wgs.iterrows():
        geom = mapping(row.geometry)
        props = {'field_id': int(row['OBJECTID']), 'farm': row['FARM'], 'field': row['FIELD'],
                 'acres': round(float(row['ACRES']), 4)}
        props.update({f'reference_{y}': _label(row[f'Corn_{y}']) for y in YEARS})
        features.append({'type': 'Feature', 'id': props['field_id'],
                         'geometry': {'type': geom['type'], 'coordinates': _round(geom['coordinates'])},
                         'properties': props})
    collection = {'type': 'FeatureCollection',
                  'source': {'file': SOURCE.name, 'layer': LAYER, 'source_crs': fields.crs.name,
                             'output_crs': 'EPSG:4326 (longitude, latitude)', 'coordinate_decimals': 6},
                  'features': features}
    OUT.write_text(json.dumps(collection, separators=(',', ':')), encoding='utf-8')
    return {'out': str(OUT.relative_to(ROOT)), 'features': len(features),
            'bounds': [round(float(b), 5) for b in wgs.total_bounds], 'bytes': OUT.stat().st_size}


if __name__ == '__main__':
    print(json.dumps(main(), indent=2))
