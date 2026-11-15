# Hack the Harvest

This repository is the starting point for Hack the Harvest.

## Getting started

Clone the repository:

```sh
git clone https://github.com/KayyMak/hack-the-harvest.git
cd hack-the-harvest
```

Project setup and usage instructions will be added as development progresses.

## Data sources
- **USDA Crop Sequence Boundaries (CSB)**: field polygons for the contiguous US
  with 2023 crop type. From https://source.coop/fiboa/us-usda-cropland (public domain).
  Download with: `bash data/download_csb.sh`
  Note: the crop codes don't separate corn silage from corn grain. We use this
  dataset for field boundaries and to find corn fields (crop:code = 1).
