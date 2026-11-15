"""Public API response types. FastAPI publishes these at /openapi.json."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

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


class AsOfPrediction(BaseModel):
    field_id: int
    predicted_label: HarvestType
    reference_label: HarvestType
    silage_probability: float = Field(ge=0, le=1)


class AsOfDate(BaseModel):
    year: int
    as_of: date
    mode: str
    features: list[str]
    predictions: list[AsOfPrediction]
    pending_field_ids: list[int]

    @model_validator(mode='after')
    def date_matches_year(self):
        if self.as_of.year != self.year:
            raise ValueError('As-of date must match its year')
        return self


class AsOfPooled(BaseModel):
    month_day: str = Field(pattern=r'^\d{2}-\d{2}$')
    field_years: int = Field(ge=0)
    decided: int = Field(ge=0)
    share_decided: float | None = Field(ge=0, le=1)
    accuracy_decided: float | None = Field(ge=0, le=1)
    balanced_accuracy: float | None = Field(ge=0, le=1)
    silage_recall: float | None = Field(ge=0, le=1)
    confusion_matrix: list[list[int]] | None


class AsOfResults(BaseModel):
    scope: str
    method: str
    years: list[int] = Field(min_length=1)
    month_days: list[str] = Field(min_length=1)
    dates: list[AsOfDate] = Field(min_length=1)
    pooled: list[AsOfPooled] = Field(min_length=1)


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
    county: str | None = None
    aggregation_level: str | None = None
    crop_use: str | None = None
    source: str | None = None
    item: str | None
    value: float | None
    cv_percent: float | None = None
    suppressed: bool


class RuleMetrics(BaseModel):
    n: int
    silage_precision: float
    silage_recall: float
    silage_f1: float
    false_positive_rate: float | None
    balanced_accuracy: float
    confusion_matrix: list[list[int]]
    matrix_order: list[HarvestType]
    matrix_rows: str
    matrix_columns: str


class DeclineRuleYear(BaseModel):
    decline_rule: RuleMetrics
    logistic: RuleMetrics


class DeclineRuleBaseline(BaseModel):
    protocol: str
    drop: float
    threshold_grid: list[int]
    thresholds_by_fold: dict[str, int]
    evaluated_field_years: int
    no_sustained_decline: int
    decline_rule: RuleMetrics
    logistic_same_rows: RuleMetrics
    always_grain_same_rows: RuleMetrics
    by_year: dict[str, DeclineRuleYear]
    limitations: list[str]


class ConvergencePoint(BaseModel):
    as_of: date
    mode: str
    field_years: int = Field(ge=0)
    expected_silage_acres: float = Field(ge=0)
    expected_silage_acres_95ci: tuple[float, float]
    cv_percent: float | None
    predicted_silage_acres: float = Field(ge=0)
    reference_silage_acres: float = Field(ge=0)
    total_acres: float = Field(ge=0)
    missing_acres_field_years: int = Field(ge=0)


class ConvergenceYear(BaseModel):
    year: int
    points: list[ConvergencePoint]


class Convergence(BaseModel):
    scope: str
    method: str
    years: list[ConvergenceYear]
