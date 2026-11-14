"""Focused checks for NDVI arithmetic, duplicate dates, and fold preprocessing."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from run_baseline import build_model, daily_series, ndvi_values, reflectance


class BaselineChecks(unittest.TestCase):
    def test_unsigned_ndvi_and_invalid_denominator(self):
        result = ndvi_values(np.array([3000, 0], dtype='uint16'),
            np.array([1000, 0], dtype='uint16'), np.array([True, True]))
        self.assertAlmostEqual(float(result[0]), -0.5)
        self.assertTrue(np.isnan(result[1]))

    def test_processing_baseline_offset(self):
        class Asset:
            extra_fields = {}
        old, _ = reflectance(np.array([2000]), Asset(), 3)
        new, _ = reflectance(np.array([3000]), Asset(), 4)
        np.testing.assert_allclose(old, new, atol=1e-7)

    def test_polygon_mask_excludes_bbox_corners(self):
        triangle = {'type': 'Polygon', 'coordinates': [[(0, 0), (3, 0), (0, 3), (0, 0)]]}
        mask = geometry_mask([triangle], (3, 3), from_origin(0, 3, 1, 1), invert=True)
        self.assertFalse(mask[0, 2])
        self.assertTrue(mask[2, 0])
        self.assertLess(mask.sum(), 9)

    def test_duplicate_dates_and_missing_are_not_zero(self):
        series = daily_series([
            dict(date='2021-07-01', ndvi=0.6, status='ok'),
            dict(date='2021-07-01', ndvi=0.8, status='ok'),
            dict(date='2021-07-02', ndvi=None, status='insufficient_clear_pixels')])
        self.assertEqual(len(series), 1)
        self.assertAlmostEqual(float(series.iloc[0]), 0.7)

    def test_imputer_fits_training_only(self):
        model = build_model()
        train = np.array([[10., 1.], [30., 3.], [np.nan, 5.], [20., 7.]])
        model.fit(train, np.array([0, 1, 0, 1]))
        before = model[0].statistics_.copy()
        model.predict(np.array([[10000., np.nan], [np.nan, 10000.]]))
        np.testing.assert_array_equal(model[0].statistics_, before)
        np.testing.assert_allclose(before, [20., 4.])
        np.testing.assert_allclose(model[1].mean_, [20., 4.])


if __name__ == '__main__':
    unittest.main()
