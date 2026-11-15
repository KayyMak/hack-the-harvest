"""The committed field polygons are reproducible, valid after rounding, and keep the source areas."""
from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geopandas as gpd
from export_fields_geojson import LAYER, OUT, SOURCE, build


class FieldPolygons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.committed = json.loads(OUT.read_text(encoding='utf-8'))
        cls.fields = gpd.read_file(OUT)

    def test_committed_file_is_reproducible(self):
        collection, _ = build()
        self.assertEqual(json.loads(json.dumps(collection)), self.committed)

    def test_every_polygon_is_valid_after_rounding(self):
        bad = self.fields.loc[~self.fields.is_valid, 'field_id'].tolist()
        self.assertEqual(bad, [])
        self.assertEqual(len(self.fields), 83)
        self.assertEqual(set(self.fields.geom_type), {'MultiPolygon'})

    def test_areas_match_source_acres(self):
        source = gpd.read_file(SOURCE, layer=LAYER).sort_values('OBJECTID')
        acres = self.fields.to_crs(source.crs).area.values / 43560
        rel = abs(acres - source['ACRES'].values) / source['ACRES'].values
        self.assertLess(float(rel.max()), 0.005)


if __name__ == '__main__':
    unittest.main()
