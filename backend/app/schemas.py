"""Public API response types. FastAPI publishes these at /openapi.json."""
from datetime import date, datetime
from typing import Any, Literal

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


class ModelSelection(BaseModel):
    """How model v2 was chosen and how far to trust its gain over v1 (baseline/model_v2/results.md)."""
    model_config = ConfigDict(extra='allow')
    note: str
    nested_selection_mean_balanced_accuracy: float
    v1_mean_balanced_accuracy_same_seeds: float
    gain_vs_v1_field_bootstrap_95ci: tuple[float, float]
    details: str


class BaselineSummary(BaseModel):
    protocol: str
    evaluated_field_years: int
    evaluated_fields: int
    excluded_field_years: int
    read_errors: int
    cloud_or_nodata_rejections: int
    missing_feature_counts: dict[str, int]
    logistic: Metrics  # the saved model's held-out metrics (v1 or v2; the key predates v2)
    always_grain: Metrics
    # Present when the saved model is v2; absent (None) for v1 outputs.
    model_version: Literal['v1', 'v2'] | None = None
    model: str | None = None
    features: list[str] | None = None
    selection: ModelSelection | None = None
    v1_logistic_same_split: Metrics | None = None


class Prediction(BaseModel):
    field_id: int
    year: int
    reference_label: HarvestType
    predicted_label: HarvestType
    silage_probability: float = Field(ge=0, le=1)
    fold: int = Field(ge=1)
    valid_dates: int = Field(ge=0)


class SignalContribution(BaseModel):
    """One feature's push on one field-year's saved call: coefficient x standardized value (log-odds).
    Positive pushes toward Silage. intercept + sum(contribution) = the model's log-odds."""
    field_id: int
    year: int
    as_of: str | None = None  # None = saved season-end model; else the as-of date of a saved mid-season call
    feature: str
    value: float | None
    contribution: float
    intercept: float
    fold: int = Field(ge=1)


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


class MarketStatus(BaseModel):
    configured: bool
    model: str
    how_to_configure: str


class MarketOutlook(BaseModel):
    """Season timeline known on `as_of`, from saved forecasts, model calls and NASS data. Values are display
    strings except `timeline.series`, which carries numbers for the chart."""
    season: int
    as_of: date
    dates: list[str]
    sources: dict[str, str]
    timeline: dict[str, Any]


class MarketToolCall(BaseModel):
    name: str
    args: dict[str, Any]
    ok: bool
    summary: str


class MarketCitation(BaseModel):
    id: str
    kind: Literal['tool', 'doc']
    label: str
    excerpt: str


class MarketUngroundedClaim(BaseModel):
    text: str
    kind: Literal['uncited', 'unsupported', 'miscited', 'verifier']
    reason: str
    removed: bool = False


class MarketGrounding(BaseModel):
    """Every sentence must cite a retrieved tool result or document passage, and its numbers must appear there."""
    claims_checked: int
    ungrounded: list[MarketUngroundedClaim]
    verifier: Literal['nemotron', 'unavailable']


class MarketReport(BaseModel):
    year: int
    as_of: date
    model: str
    generated_at: datetime
    mode: Literal['tools', 'context']
    markdown: str
    tool_calls: list[MarketToolCall]
    citations: list[MarketCitation]
    grounding: MarketGrounding
    disclaimer: str
    sources: list[str]


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


class _Forecast(BaseModel):
    """Saved forecast sections keep any extra fields the forecast writes."""
    model_config = ConfigDict(extra='allow')


class ForecastSource(_Forecast):
    title: str
    released: str | None
    url: str


class ForecastBacktest(_Forecast):
    """Percent errors are already in percent (11.5 = 11.5%); coverage is a fraction."""
    state_years: int = Field(ge=0)
    median_abs_pct_error: float = Field(ge=0)
    mean_abs_pct_error: float = Field(ge=0)
    covered_by_95_interval: float = Field(ge=0, le=1)


class ForecastBacktests(_Forecast):
    silage: ForecastBacktest
    grain: ForecastBacktest


class ForecastUs(_Forecast):
    silage: float = Field(ge=0)
    silage_se: float = Field(ge=0)
    silage_low: float = Field(ge=0)
    silage_high: float = Field(ge=0)
    grain: float = Field(ge=0)
    grain_se: float = Field(ge=0)
    grain_low: float | None = Field(default=None, ge=0)
    grain_high: float | None = Field(default=None, ge=0)


class ForecastState(_Forecast):
    state: str
    silage: float = Field(ge=0)
    silage_low: float = Field(ge=0)
    silage_high: float = Field(ge=0)
    silage_se: float = Field(ge=0)
    # null where NASS published no grain area for the state before January 2026
    grain: float | None = Field(ge=0)
    grain_low: float | None = Field(ge=0)
    grain_high: float | None = Field(ge=0)
    grain_se: float | None = Field(ge=0)


class ForecastStep(_Forecast):
    as_of: date
    source: str


class Forecast2025Summary(_Forecast):
    """2025 harvested-acre forecast built from NASS reports published before January 2026."""
    method: str
    answer_key_excluded: str
    sources: dict[str, ForecastSource]
    backtest: ForecastBacktests
    us: ForecastUs
    states: list[ForecastState] = Field(min_length=1)
    convergence: list[ForecastStep]

    @model_validator(mode='after')
    def one_row_per_state(self):
        names = [s.state for s in self.states]
        if len(names) != len(set(names)):
            raise ValueError('Each state must appear once')
        return self


class NassAcres(BaseModel):
    """NASS 2025 acres harvested; null when the reference row is missing or suppressed."""
    silage: float | None
    grain: float | None


class Nass2025(BaseModel):
    source: str
    maryland: NassAcres
    us: NassAcres


class Forecast2025(BaseModel):
    summary: Forecast2025Summary
    # null when the NASS 2025 reference file cannot be read; the forecast itself is still served
    nass_2025: Nass2025 | None


class FieldLandcover(BaseModel):
    """USDA Cropland Data Layer cover inside one BARC field-year (baseline/outputs/unlabeled/corn_check.csv).
    Satellite land cover, never a BARC reference label and never a model call."""
    field_id: int
    year: int
    crop: str = Field(description='Most common CDL class inside the field (top_class_name)')
    crop_share: float = Field(ge=0, le=1, description='Share of the CDL pixels in the field in that class')
    corn_share: float = Field(ge=0, le=1, description='Share of the CDL pixels in the field that are corn')
    category: Literal['likely_corn', 'mixed', 'not_corn']


class UnlabeledCall(BaseModel):
    """Model call on a field-year with a blank BARC label. Not a reference label."""
    field_id: int
    year: int
    acres: float | None = Field(default=None, ge=0)
    corn_share: float = Field(ge=0, le=1)
    valid_dates: int = Field(ge=0)
    missing_features: list[str]
    status: Literal['called', 'no_usable_dates']
    predicted_label: HarvestType | None
    silage_probability: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode='after')
    def _call_matches_status(self):
        called = self.predicted_label is not None and self.silage_probability is not None
        if called != (self.status == 'called'):
            raise ValueError('A call needs a label and probability; a field-year without usable dates has neither')
        return self


class UnlabeledYear(BaseModel):
    year: int
    field_years_called: int = Field(ge=0)
    total_acres: float = Field(ge=0)
    called_silage: int = Field(ge=0)
    called_grain: int = Field(ge=0)
    called_silage_acres: float = Field(ge=0)
    called_grain_acres: float = Field(ge=0)
    no_usable_dates: int = Field(ge=0)
    expected_silage_acres: float = Field(ge=0)
    expected_silage_acres_95ci: tuple[float, float]
    cv_percent: float | None


class UnlabeledCounts(BaseModel):
    blank_field_years: int = Field(ge=0)
    blank_likely_corn: int = Field(ge=0)
    blank_mixed: int = Field(ge=0)
    blank_not_corn: int = Field(ge=0)
    blank_uncertain: int = Field(ge=0)
    called: int = Field(ge=0)
    no_usable_dates: int = Field(ge=0)


class UnlabeledCalls(BaseModel):
    generated_utc: str
    scope: str
    caveat: str
    method: str
    counts: UnlabeledCounts
    corn_rule: dict
    cdl_sanity_check_on_labeled: dict
    by_year: list[UnlabeledYear]
    heldout_accuracy_for_context: dict
    farm_record_spot_check: dict
    sources: list[dict]
    calls: list[UnlabeledCall]
