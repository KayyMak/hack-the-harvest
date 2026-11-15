# Builds extra silage/grain labels from Kraatz (2023), doi:10.5281/zenodo.8087301
import re, zipfile
from pathlib import Path
import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parent
REC_ZIP = ROOT / "data" / "farm_database_annual_planting_harvesting_after_some_screening..zip"
OUTLINE_ZIP = ROOT / "data" / "barc_field_outlines_for_study.zip"
BARC = ROOT / "BARC_Corn.2021-2023.gpkg"
OUT = ROOT / "kraatz_labels.csv"

def corn_type(crop):
    crop = str(crop)
    if "CSIL" in crop:
        return "Silage"
    if "FLDCRN" in crop or crop.startswith("Corn Field"):
        return "Grain"
    return None  # sweet corn, soybeans, etc. are ignored

# 1. Read harvest (hd) and planting (pd) tables straight from the zip
frames = []
with zipfile.ZipFile(REC_ZIP) as z:
    for name in z.namelist():
        m = re.search(r"_(hd|pd)_(\d{4})_filt\.csv$", name)
        if not m:
            continue
        df = pd.read_csv(z.open(name)).rename(columns={m.group(1): "date"})
        df["kind"] = "harvest" if m.group(1) == "hd" else "planting"
        df["year"] = int(m.group(2))
        frames.append(df)
rec = pd.concat(frames, ignore_index=True)
rec["date"] = pd.to_datetime(rec["date"])
rec["harvest_type"] = rec["crop"].map(corn_type)
rec = rec.dropna(subset=["harvest_type"])

# 2. One row per field-year; harvest records win over planting records
harv = (rec[rec.kind == "harvest"].groupby(["idn", "year"])
        .agg(harvest_type=("harvest_type", lambda s: s.mode().iat[0]),
             n_types=("harvest_type", "nunique"),
             harvest_date=("date", "min")).reset_index())
plant = (rec[rec.kind == "planting"].groupby(["idn", "year"])
         .agg(plant_type=("harvest_type", lambda s: s.mode().iat[0]),
              planting_n_types=("harvest_type", "nunique"),
              planting_date=("date", "min")).reset_index())
lab = plant.merge(harv, on=["idn", "year"], how="outer")
lab["label_source"] = lab["harvest_type"].notna().map(
    {True: "harvest_record", False: "planting_record"})
lab["harvest_type"] = lab["harvest_type"].fillna(lab["plant_type"])
lab["conflict"] = (lab["n_types"].fillna(1) > 1) | (lab["planting_n_types"].fillna(1) > 1) | (
    lab["plant_type"].notna() & (lab["plant_type"] != lab["harvest_type"]))
lab["harvest_doy"] = lab["harvest_date"].dt.dayofyear
print(lab.groupby(["year", "label_source", "harvest_type"]).size().unstack(fill_value=0))

# 3. Match record fields to BARC OBJECTIDs by overlap with the study outlines
outlines = gpd.read_file(f"zip://{OUTLINE_ZIP}")
print("Outline columns:", list(outlines.columns))
NAME_COL = next(c for c in outlines.columns
                if c != "geometry" and outlines[c].astype(str).isin(lab["idn"]).any())
print("Matching 'idn' to outline column:", NAME_COL)

barc = gpd.read_file(BARC, layer="barc_silage_grain_corn20212023")
outlines = outlines.to_crs(barc.crs)
outlines["o_area"] = outlines.area
inter = gpd.overlay(outlines[[NAME_COL, "o_area", "geometry"]],
                    barc[["OBJECTID", "geometry"]], how="intersection")
inter["share"] = inter.area / inter["o_area"]
best = (inter.sort_values("share", ascending=False).drop_duplicates(NAME_COL)
        .query("share >= 0.5")[[NAME_COL, "OBJECTID", "share"]]
        .rename(columns={NAME_COL: "idn"}))
lab = lab.merge(best, on="idn", how="left")
print(f"Matched {lab.OBJECTID.notna().sum()} of {len(lab)} field-years to BARC polygons")

# 4. Check agreement with official BARC labels (2021 overlap)
barc_long = barc.melt(id_vars=["OBJECTID"], value_vars=["Corn_2021", "Corn_2022", "Corn_2023"],
                      var_name="col", value_name="barc_label").dropna()
barc_long = barc_long[barc_long.barc_label.isin(['Grain', 'Silage'])]
barc_long["year"] = barc_long["col"].str[-4:].astype(int)
chk = lab.merge(barc_long[["OBJECTID", "year", "barc_label"]], on=["OBJECTID", "year"])
if len(chk):
    print("\nAgreement with BARC labels:")
    print(pd.crosstab(chk["barc_label"], chk["harvest_type"]))

lab.to_csv(OUT, index=False)
print(f"\nWrote {OUT}")
