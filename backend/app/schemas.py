"""Public API response types. FastAPI publishes these at /openapi.json."""
from typing import Literal

from pydantic import BaseModel, Field

HarvestType = Literal['Grain', 'Silage']


class Metrics(BaseModel):
    n: int
    silage_precision: float
    silage_recall: float
    silage_f1: float
    false_positive_rate: float | None
    balanced_accuracy: float
    brier_score: float
    confusion_matrix: list[list[int]]
    matrix_order: list[HarvestType]
    matrix_rows: str
    matrix_columns: str


class BaselineSummary(BaseModel):
    protocol: str
    evaluated_field_years: int
    evaluated_fields: int
    excluded_field_years: int
    read_errors: int
    cloud_or_nodata_rejections: int
    missing_feature_counts: dict[str, int]
    logistic: Metrics
    always_grain: Metrics


class Prediction(BaseModel):
    field_id: int
    year: int
    reference_label: HarvestType
    predicted_label: HarvestType
    silage_probability: float = Field(ge=0, le=1)
    fold: int = Field(ge=1)
    valid_dates: int = Field(ge=0)


class BarcField(BaseModel):
    field_id: int
    farm: str | None
    field: str | None
    acres: float | None = Field(ge=0)


class Observation(BaseModel):
    date: str
    ndvi: float | None
    clear_fraction: float | None = Field(ge=0, le=1)
    scene_cloud_percent: float | None
    status: str


class YearRollup(BaseModel):
    year: int
    field_years: int
    total_acres: float
    reference_silage_acres: float
    predicted_silage_acres: float
    expected_silage_acres: float
    expected_silage_acres_95ci: tuple[float, float]
    cv_percent: float | None
    predicted_silage_share: float
    adjusted_silage_share: float | None
    adjusted_silage_acres: float | None
    adjustment_rates: dict[str, float | None]
    missing_acres_field_years: int


class Rollup(BaseModel):
    scope: str
    method: str
    years: list[YearRollup]


class QuickStatsRow(BaseModel):
    year: int | None
    state: str | None
    item: str | None
    value: float | None
    suppressed: bool
