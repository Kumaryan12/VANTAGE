"""Typed Phase 2 requests, persisted records, and calculation responses."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.portfolios.schemas import Portfolio, Provenance, RiskResult, StrictModel

Confidence = Annotated[float, Field(ge=0.90, le=0.995, allow_inf_nan=False)]
Shock = Annotated[float, Field(ge=-1, le=5, allow_inf_nan=False)]


class RiskInputs(StrictModel):
    mode: Literal["demo", "kite"] = "demo"
    dataset_id: str | None = Field(None, max_length=36)
    confidence: Confidence = 0.95
    window: int = Field(252, ge=60, le=1260, strict=True)
    shrinkage: float = Field(0, ge=0, le=1)


class AnalysisRequest(RiskInputs):
    simulations: int = Field(10_000, ge=2000, le=100_000, strict=True)
    seed: int = Field(42, ge=0, le=2**32 - 1, strict=True)


class StressRequest(RiskInputs):
    kind: Literal["hypothetical", "historical"]
    name: str = Field("Custom scenario", min_length=1, max_length=100)
    scenario_id: str | None = Field(None, max_length=40)
    scenario_dataset_id: str | None = Field(None, max_length=36)
    start: date | None = None
    end: date | None = None
    market_shock: Shock | None = None
    sector_shocks: dict[str, Shock] = Field(default_factory=dict, max_length=50)
    security_shocks: dict[str, Shock] = Field(default_factory=dict, max_length=50)

    @model_validator(mode="after")
    def scenario_fields(self):
        if self.kind == "historical":
            if self.market_shock is not None or self.sector_shocks or self.security_shocks:
                raise ValueError("Historical replay cannot accept hypothetical shock values.")
            if self.scenario_id and (self.start or self.end):
                raise ValueError("Select a named window or explicit dates, not both.")
            if not self.scenario_id and (not self.start or not self.end or self.start >= self.end):
                raise ValueError(
                    "Historical replay requires a named window or increasing start/end dates."
                )
        elif self.scenario_id or self.start or self.end or self.scenario_dataset_id:
            raise ValueError(
                "Hypothetical scenarios accept direct shocks, not historical dates or datasets."
            )
        elif self.market_shock is None and not self.sector_shocks and not self.security_shocks:
            raise ValueError("Supply at least one direct shock.")
        return self


class CovarianceInfo(StrictModel):
    method: str
    ddof: int
    shrinkage: float
    target_variance: float
    shrinkage_change_frobenius_norm: float
    minimum_eigenvalue_before: float
    maximum_eigenvalue: float
    rank: int
    condition_number: float | None
    singular: bool
    ill_conditioned: bool
    symmetry_error: float
    symmetrized: bool
    negative_eigenvalues_clipped: int
    psd_tolerance: float
    correction_frobenius_norm: float


class TailEstimate(StrictModel):
    method: str
    var: float
    expected_shortfall: float
    var_return: float
    es_return: float
    units: Literal["INR"] = "INR"
    tail_sample_mass: float | None = None
    assumptions: list[str]


class Models(StrictModel):
    historical: TailEstimate
    gaussian: TailEstimate
    monte_carlo: TailEstimate


class HistogramBin(StrictModel):
    left_pnl: float
    right_pnl: float
    center_pnl: float
    count: int
    tail_count: int


class SimulationSummary(StrictModel):
    var: float
    expected_shortfall: float
    tail_sample_mass: float
    simulations: int
    seed: int
    sampling_method: str
    bit_generator: str
    mean_pnl: float
    pnl_standard_deviation: float
    pnl_quantiles: dict[str, float]
    value_quantiles: dict[str, float]
    return_quantiles: dict[str, float]
    histogram: list[HistogramBin]
    var_standard_error: float
    es_standard_error: float
    var_mc_interval_95: list[float]
    es_mc_interval_95: list[float]
    nonpositive_value_count: int
    asset_returns_below_minus_one: int
    uncertainty_note: str
    assumptions: list[str]


class AssetContribution(StrictModel):
    instrument: str
    name: str
    sector: str
    weight: float
    marginal_daily_volatility: float | None
    component_daily_volatility: float
    component_annualized_volatility: float
    percentage_contribution: float | None


class SectorContribution(StrictModel):
    sector: str
    weight: float
    component_daily_volatility: float
    component_annualized_volatility: float
    percentage_contribution: float | None


class Attribution(StrictModel):
    daily_volatility: float
    annualized_volatility: float
    assets: list[AssetContribution]
    sectors: list[SectorContribution]
    weight_hhi: float
    positive_component_hhi: float | None
    reconciliation_residual: float
    note: str


class RunMetadata(StrictModel):
    methodology: str
    model_version: str
    created_at: datetime
    valuation_as_of: date
    snapshot_retrieved_at: datetime
    valuation_timestamp_note: str
    snapshot_id: str
    input_artifact_id: str
    input_hash: str
    artifact_hash: str
    historical_data_hash: str | None
    data_source_ids: list[str]
    horizon: str
    confidence: float
    requested_window: int
    sample_size: int
    estimation_start: date | None
    estimation_end: date | None
    covariance_method: str | None
    shrinkage: float
    random_seed: int | None
    simulation_count: int
    currency: Literal["INR"] = "INR"
    loss_convention: str = "L = -V × simple return; positive means loss, negative means gain"
    runtime: dict[str, str]
    validation: dict[str, str | int | float | bool | None]
    warnings: list[str]


class AnalysisResult(StrictModel):
    kind: Literal["analysis"] = "analysis"
    run_id: str
    portfolio: Portfolio
    parameters: AnalysisRequest
    metadata: RunMetadata
    provenance: Provenance
    expected_daily_return: float
    daily_volatility: float
    annualized_volatility: float
    sample_annualized_volatility: float
    models: Models
    covariance: list[list[float]]
    correlation: list[list[float | None]]
    covariance_diagnostics: CovarianceInfo
    attribution: Attribution
    simulation: SimulationSummary


class StressAsset(StrictModel):
    instrument: str
    name: str
    sector: str
    weight: float
    shock_return: float
    pnl: float
    loss: float
    value_before: float
    value_after: float
    mapping: str


class StressSector(StrictModel):
    sector: str
    pnl: float
    loss: float
    value_before: float
    value_after: float


class StressPoint(StrictModel):
    date: date
    value: float
    pnl: float
    cumulative_return: float


class ReferenceRisk(StrictModel):
    historical_var: float
    historical_es: float
    stress_loss_to_var: float | None
    note: str


class StressResult(StrictModel):
    kind: Literal["stress"] = "stress"
    scenario_kind: Literal["hypothetical", "historical", "synthetic_replay"]
    run_id: str
    name: str
    portfolio: Portfolio
    parameters: StressRequest
    metadata: RunMetadata
    provenance: Provenance | None
    value_before: float
    value_after: float
    portfolio_return: float
    pnl: float
    loss: float
    assets: list[StressAsset]
    sectors: list[StressSector]
    largest_loss_contributors: list[str]
    pnl_reconciliation_residual: float
    path: list[StressPoint]
    observations: int
    assumptions: list[str]
    reference_risk: ReferenceRisk | None


class ScenarioAvailability(StrictModel):
    id: str
    name: str
    start: date
    end: date
    synthetic: bool
    available: bool
    reason: str


class RunSummary(StrictModel):
    id: str
    kind: Literal["analysis", "stress", "legacy"]
    mode: str
    name: str
    created_at: datetime
    confidence: float
    window: int
    sample_size: int
    portfolio_value: float | None
    historical_var: float | None
    historical_es: float | None
    stress_pnl: float | None
    replayable: bool
    gaussian_var: float | None = None
    gaussian_es: float | None = None
    monte_carlo_var: float | None = None
    monte_carlo_es: float | None = None


class SavedRun(StrictModel):
    id: str
    input_hash: str
    replayable: bool
    result: AnalysisResult | StressResult | RiskResult


class CompareRequest(StrictModel):
    run_ids: list[str] = Field(min_length=2, max_length=4)


class ComparisonRow(RunSummary):
    var_delta: float | None
    es_delta: float | None
    pnl_delta: float | None
    gaussian_var_delta: float | None = None
    gaussian_es_delta: float | None = None
    monte_carlo_var_delta: float | None = None
    monte_carlo_es_delta: float | None = None


class RunComparison(StrictModel):
    baseline_id: str
    rows: list[ComparisonRow]
    warnings: list[str]


class ReplayResult(StrictModel):
    original_run_id: str
    replayed_run_id: str
    input_hash_matches: bool
    numerical_results_match: bool
    result: AnalysisResult | StressResult
    note: str
