#!/bin/bash
# Downloads USDA Crop Sequence Boundaries (CSB) field polygons
# Source: https://source.coop/fiboa/us-usda-cropland
# License: Public domain (USDA NASS)
# Size: ~4 GB
mkdir -p data/raw
curl -L -o data/raw/us_usda_cropland.parquet \
  https://data.source.coop/fiboa/us-usda-cropland/us_usda_cropland.parquet
