"""Public API response types. FastAPI publishes these at /openapi.json."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class _Estimate(BaseModel):
    """Saved estimate sections keep any extra fields the analysis writes."""
    model_config = ConfigDict(extra='allow')


class EstimatePopulation(_Estimate):
    source: str
    corn_rule: str
    csb_fields_maryland: int = Field(ge=0)
    corn_fields_2025: int = Field(ge=0)
    corn_acres_2025: float = Field(ge=0)
    cdl_corn_acres_2025: float | None = Field(default=None, ge=0)


class EstimateSample(_Estimate):
    seed: int
    stratified_by: str
    requested_fields: int = Field(ge=0)
    sampled_fields: int = Field(ge=0)
    sampled_acres: float = Field(ge=0)
    scored_fields: int = Field(ge=0)
    scored_acres: float = Field(ge=0)
    skipped_fields: int = Field(ge=0)
    skipped_reasons: dict[str, int]
    min_valid_dates: int = Field(ge=0)
    batches_used: list[int] | None = None
    batches_drawn: int | None = Field(default=None, ge=0)


class EstimateModel(_Estimate):
    name: str
    training_field_years: int = Field(ge=0)
    features: list[str]
    threshold: float = Field(ge=0, le=1)
    training_silage_field_years: int | None = Field(default=None, ge=0)
    sample_fields_called_silage: int | None = Field(default=None, ge=0)


class EstimateAcres(_Estimate):
    silage_acres: float = Field(ge=0)
    silage_acres_95ci: tuple[float, float]
    grain_acres: float = Field(ge=0)
    grain_acres_95ci: tuple[float, float]
    silage_share: float = Field(ge=0, le=1)


class EstimateCalibrated(EstimateAcres):
    method: str
    tpr: float | None
    fpr: float | None
    predicted_silage_acre_share: float | None = Field(default=None, ge=0, le=1)
    undefined_bootstrap_draws: int | None = Field(default=None, ge=0)


class EstimateNass(_Estimate):
    silage_acres: float = Field(gt=0)
    grain_acres: float = Field(gt=0)
    source: str


class EstimateError(_Estimate):
    """error = model estimate - NASS, in acres; relative_error = error / NASS."""
    error: float
    relative_error: float


class EstimateErrors(_Estimate):
    silage: EstimateError
    grain: EstimateError


class EstimateBenchmark(_Estimate):
    raw: EstimateErrors
    calibrated: EstimateErrors | None


class EstimateSource(_Estimate):
    name: str
    url: str
    accessed: str


class Estimate2025Summary(_Estimate):
    """Model estimate from a sample of Maryland corn fields; not a USDA/NASS release."""
    year: int
    state: str
    generated_utc: str
    headline: Literal['calibrated', 'raw']
    population: EstimatePopulation
    sample: EstimateSample
    model: EstimateModel
    raw: EstimateAcres
    calibrated: EstimateCalibrated | None
    nass_2025: EstimateNass
    benchmark: EstimateBenchmark
    method: str
    limitations: list[str]
    sources: list[EstimateSource]

    @model_validator(mode='after')
    def headline_has_numbers(self):
        if self.headline == 'calibrated' and (self.calibrated is None or self.benchmark.calibrated is None):
            raise ValueError('A calibrated headline needs calibrated acres and their benchmark')
        return self


class Estimate2025(BaseModel):
    summary: Estimate2025Summary
    benchmark: dict | None
