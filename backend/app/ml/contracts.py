from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from app.portfolios.schemas import StrictModel

MODEL_VERSION = "volatility-research-3.0.0"
FEATURE_VERSION = "daily-close-features-1.0.0"
ModelKind = Literal["rolling", "ewma", "garch", "lightgbm"]


class ResearchRequest(StrictModel):
    mode: Literal["demo", "kite"] = "demo"
    dataset_id: str | None = Field(None, max_length=36)
    context_dataset_id: str | None = Field(None, max_length=36)
    benchmark_instrument: str | None = Field(None, max_length=50)
    scheme: Literal["expanding", "rolling"] = "expanding"
    history_window: int = Field(1260, ge=400, le=5000, strict=True)
    initial_train: int = Field(240, ge=160, le=2000, strict=True)
    validation_size: int = Field(60, ge=30, le=252, strict=True)
    test_size: int = Field(100, ge=20, le=500, strict=True)
    refit_every: int = Field(20, ge=5, le=126, strict=True)
    rolling_train_window: int = Field(252, ge=160, le=2000, strict=True)
    rolling_window: Literal[20, 60] = 60
    ewma_lambda: float = Field(0.94, ge=0.8, le=0.999)
    variance_floor: float = Field(1e-12, ge=1e-14, le=1e-8)
    seed: int = Field(42, ge=0, le=2**31 - 1, strict=True)
    max_trees: int = Field(120, ge=20, le=300, strict=True)
    search_candidates: int = Field(3, ge=1, le=3, strict=True)
    learning_rate: float = Field(0.05, ge=0.01, le=0.2)
    feature_set: Literal["basic", "full"] = "full"
    coverage_minimum: int = Field(100, ge=50, le=500, strict=True)

    @model_validator(mode="after")
    def valid_protocol(self):
        if bool(self.context_dataset_id) != bool(self.benchmark_instrument):
            raise ValueError("Supply both context dataset and explicit benchmark instrument.")
        if self.mode == "demo" and (self.dataset_id or self.context_dataset_id):
            raise ValueError("Demo research uses only its versioned synthetic fixture.")
        if self.scheme == "rolling" and self.rolling_train_window < self.initial_train:
            raise ValueError("Rolling training window must meet the initial-training minimum.")
        if (self.test_size + self.refit_every - 1) // self.refit_every > 25:
            raise ValueError("At most 25 evaluation refits per model are permitted.")
        return self


class JobSummary(StrictModel):
    id: str
    status: Literal["queued", "running", "completed", "partial", "failed", "interrupted"]
    progress: int
    stage: str
    created_at: datetime
    finished_at: datetime | None
    error: dict[str, str] | None
    dataset_hash: str
    synthetic: bool
    reproduction_of: str | None


class Forecast(StrictModel):
    model_id: str
    model_kind: ModelKind
    origin: date
    feature_available_at: date
    target_start: date
    target_end: date
    forecast_variance: float | None
    forecast_volatility: float | None
    realized_variance_proxy: float
    actual_return: float
    realized_loss: float
    var95: float | None
    var99: float | None
    exception95: bool | None
    exception99: bool | None
    regime: Literal["low", "medium", "high"]
    training_window_id: str | None
    model_version: str
    data_version: str
    series_id: str
    source: str
    frequency: Literal["daily"] = "daily"
    adjustment: str
    missing_feature_count: int
    feature_values: dict[str, float | None]
    floor_applied: bool
    failure: str | None


class Coverage(StrictModel):
    confidence: float
    observations: int
    exceptions: int
    exception_rate: float | None
    nominal_rate: float
    expected_exceptions: float
    kupiec_statistic: float | None
    kupiec_p_value: float | None
    independence_statistic: float | None
    independence_p_value: float | None
    conditional_statistic: float | None
    conditional_p_value: float | None
    exact_binomial_p_value: float | None
    transitions: dict[str, int]
    warnings: list[str]


class MetricSet(StrictModel):
    observations: int
    qlike: float | None
    mse: float | None
    mae: float | None
    coverage95: Coverage
    coverage99: Coverage


class ComparisonModel(StrictModel):
    id: str
    kind: ModelKind
    role: Literal["benchmark", "candidate", "champion"]
    status: str
    available_predictions: int
    failures: int
    metrics: MetricSet
    execution_seconds: float
    limitations: list[str]


class Comparison(StrictModel):
    experiment_id: str
    start: date | None
    end: date | None
    requested_observations: int
    matched_observations: int
    excluded_dates: list[date]
    models: list[ComparisonModel]
    policy: str
    uncertainty: list[dict]
    warnings: list[str]


class ExperimentDetail(JobSummary):
    parameters: ResearchRequest
    model_version: str
    feature_version: str
    dataset: dict
    protocol: dict
    runtime: dict
    comparison: Comparison | None
    reproduction_match: bool | None
    warnings: list[str]


class ModelDetail(StrictModel):
    id: str
    experiment_id: str
    kind: ModelKind
    role: Literal["benchmark", "candidate", "champion"]
    status: str
    config: dict
    metrics: MetricSet | None
    latest_forecast: dict | None
    refits: list[dict]
    global_importance: list[dict]
    drift: list[dict]
    execution_seconds: float
    limitations: list[str]
    artifact_files: list[dict]
    governance: list[dict]


class GovernanceRequest(StrictModel):
    role: Literal["benchmark", "candidate", "champion"]
    rationale: str = Field(min_length=20, max_length=2000)
    acknowledge_limitations: Literal[True]


class Explanation(StrictModel):
    model_id: str
    origin: date
    target: date
    training_window_id: str
    base_variance: float
    raw_variance: float
    forecast_variance: float
    floor_adjustment: float
    reconstruction_residual: float
    features: list[dict]
    sensitivity: list[dict]
    note: str


class RegimePoint(StrictModel):
    origin: date
    target: date
    lagged_variance: float
    regime: Literal["low", "medium", "high"]


class RegimeMetric(StrictModel):
    regime: Literal["low", "medium", "high"]
    model_kind: ModelKind
    metrics: MetricSet


class RegimeResponse(StrictModel):
    thresholds: dict[str, float]
    estimated_through: date
    rows: list[RegimePoint]
    metrics: list[RegimeMetric]
    note: str


class ResearchSeriesPoint(StrictModel):
    date: date
    origin: date
    realized_volatility_proxy: float
    realized_loss: float
    regime: Literal["low", "medium", "high"]
    rolling: float | None
    ewma: float | None
    garch: float | None
    lightgbm: float | None
    var95_rolling: float | None
    var99_rolling: float | None
    var95_ewma: float | None
    var99_ewma: float | None
    var95_garch: float | None
    var99_garch: float | None
    var95_lightgbm: float | None
    var99_lightgbm: float | None
    exception95_rolling: bool | None
    exception99_rolling: bool | None
    exception95_ewma: bool | None
    exception99_ewma: bool | None
    exception95_garch: bool | None
    exception99_garch: bool | None
    exception95_lightgbm: bool | None
    exception99_lightgbm: bool | None


class MarkdownReport(StrictModel):
    markdown: str


class ExperimentCompareRequest(StrictModel):
    experiment_ids: list[str] = Field(min_length=2, max_length=4)


class ExperimentComparison(StrictModel):
    experiments: list[ExperimentDetail]
    warnings: list[str]
