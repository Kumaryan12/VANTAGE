from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.portfolios.schemas import Holding, NonNegative, Portfolio, StrictModel
from app.risk.contracts import RiskInputs, StressRequest

VERSION = "equity-sleeve-optimization-5.0.0"
FEASIBILITY_TOLERANCE = 1e-7


class AllocationConstraints(StrictModel):
    min_weight: float = Field(0, ge=0, le=1)
    max_weight: float = Field(0.2, gt=0, le=1)
    asset_min: dict[str, float] = Field(default_factory=dict, max_length=50)
    asset_max: dict[str, float] = Field(default_factory=dict, max_length=50)
    frozen: list[str] = Field(default_factory=list, max_length=50)
    sector_min: dict[str, float] = Field(default_factory=dict, max_length=50)
    sector_max: dict[str, float] = Field(default_factory=dict, max_length=50)
    max_sector_weight: float | None = Field(None, gt=0, le=1)
    max_turnover: float | None = Field(0.15, ge=0, le=1)
    unknown_sector_policy: Literal["retain", "reject"] = "retain"

    @model_validator(mode="after")
    def bounds(self):
        if self.min_weight > self.max_weight:
            raise ValueError("Global minimum weight exceeds the maximum.")
        for mapping in (self.asset_min, self.asset_max, self.sector_min, self.sector_max):
            if any(not 0 <= value <= 1 for value in mapping.values()):
                raise ValueError(
                    "Every weight bound must be a finite decimal between zero and one."
                )
        if len(set(self.frozen)) != len(self.frozen):
            raise ValueError("Frozen instruments must be unique.")
        return self


class CostAssumptions(StrictModel):
    proportional_rate: float = Field(0.001, ge=0, le=0.1)
    asset_rates: dict[str, float] = Field(default_factory=dict, max_length=50)
    buy_rates: dict[str, float] = Field(default_factory=dict, max_length=50)
    sell_rates: dict[str, float] = Field(default_factory=dict, max_length=50)
    source: str = Field(
        "User-selected proportional research cost assumptions; not verified broker charges.",
        min_length=15,
        max_length=300,
    )

    @model_validator(mode="after")
    def rates(self):
        if any(
            not 0 <= v <= 0.1
            for m in (self.asset_rates, self.buy_rates, self.sell_rates)
            for v in m.values()
        ):
            raise ValueError("Assumed cost rates must be finite decimals from zero to .1.")
        return self


class SolverConfiguration(StrictModel):
    name: Literal["CLARABEL"] = "CLARABEL"
    max_iter: int = Field(300, ge=20, le=1000, strict=True)
    time_limit_seconds: float = Field(3, ge=0.1, le=10)
    tolerance: float = Field(1e-9, ge=1e-12, le=1e-8)


class ReturnAssumptions(StrictModel):
    annual_returns: dict[str, float] = Field(min_length=1, max_length=50)
    source: str = Field(min_length=20, max_length=500)
    convention: Literal["annual_simple_arithmetic_assumption"] = (
        "annual_simple_arithmetic_assumption"
    )

    @model_validator(mode="after")
    def valid_returns(self):
        if any(not -1 <= v <= 5 for v in self.annual_returns.values()):
            raise ValueError(
                "Explicit annual return assumptions must be finite and between -1 and 5."
            )
        return self


class OptimizationRequest(RiskInputs):
    objective: Literal[
        "min_variance", "risk_turnover", "risk_cost", "target_risk", "target_return"
    ] = "min_variance"
    constraints: AllocationConstraints = Field(default_factory=AllocationConstraints)
    costs: CostAssumptions = Field(default_factory=CostAssumptions)
    solver: SolverConfiguration = Field(default_factory=SolverConfiguration)
    lambda_turnover: float = Field(0.01, ge=0, le=100)
    lambda_cost: float = Field(1, ge=0, le=100)
    target_annual_volatility: float | None = Field(None, gt=0, le=5)
    target_annual_return: float | None = Field(None, ge=-1, le=5)
    expected_returns: ReturnAssumptions | None = None
    asset_order: list[str] | None = Field(None, min_length=1, max_length=50)
    simulations: int = Field(2000, ge=2000, le=10000, strict=True)
    seed: int = Field(42, ge=0, le=2**32 - 1, strict=True)

    @model_validator(mode="after")
    def objective_inputs(self):
        if self.objective == "target_risk" and self.target_annual_volatility is None:
            raise ValueError(
                "Target-risk feasibility requires an explicit annual volatility target."
            )
        if self.objective == "target_return" and (
            self.expected_returns is None or self.target_annual_return is None
        ):
            raise ValueError(
                "Target-return research requires a complete sourced return vector and explicit target."
            )
        return self


class Residual(StrictModel):
    name: str
    group: str
    value: float
    lower: float | None
    upper: float | None
    violation: float
    binding: bool
    utilization: float | None
    units: str = "decimal weight"


class SolverResult(StrictModel):
    status: Literal[
        "optimal",
        "optimal_inaccurate",
        "infeasible",
        "unbounded",
        "timeout",
        "iteration_limit",
        "solver_failure",
        "validation_failed",
    ]
    feasible: bool
    weights: list[float] | None
    raw_weights: list[float] | None
    annual_variance: float | None
    annual_volatility: float | None
    objective_value: float | None
    turnover: float | None
    gross_weight_change: float | None
    one_way_notional: float | None
    gross_notional_traded: float | None
    cost_fraction: float | None
    cost_inr: float | None
    expected_annual_return: float | None
    residuals: list[Residual]
    diagnostics: list[str]
    solver: dict
    validation: dict


class VirtualHolding(Holding):
    """Internal continuous sleeve allocation, including zero-weight held assets."""

    quantity: NonNegative
    value: NonNegative
    weight: Annotated[float, Field(ge=0, le=1)]


class VirtualPortfolio(Portfolio):
    holdings: list[VirtualHolding]


class OptimizationJob(StrictModel):
    id: str
    kind: Literal["single", "frontier", "sensitivity"]
    status: Literal[
        "queued", "running", "completed", "partial", "failed", "cancelled", "interrupted"
    ]
    stage: str
    progress: int
    synthetic: bool
    created_at: datetime
    finished_at: datetime | None
    solver_status: str | None
    error: dict | None
    reproduction_of: str | None


class OptimizationDetail(OptimizationJob):
    version: str
    snapshot_id: str
    artifact_id: str
    input_hash: str
    parameters: dict
    dataset: dict
    runtime: dict
    result: dict | None


class FrontierRequest(StrictModel):
    base: OptimizationRequest = Field(default_factory=OptimizationRequest)
    mode: Literal["risk_turnover", "efficient"] = "risk_turnover"
    turnover_budgets: list[float] = Field(
        default_factory=lambda: [0, 0.05, 0.1, 0.15, 0.25], min_length=2, max_length=8
    )
    return_targets: list[float] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def frontier(self):
        if self.base.objective != "min_variance":
            raise ValueError(
                "Select pure minimum variance explicitly before computing a minimum-risk frontier."
            )
        if any(not 0 <= v <= 1 for v in self.turnover_budgets) or len(
            set(self.turnover_budgets)
        ) != len(self.turnover_budgets):
            raise ValueError("Turnover budgets must be unique finite decimal values in [0,1].")
        if self.mode == "efficient" and (
            self.base.expected_returns is None or not 2 <= len(self.return_targets) <= 8
        ):
            raise ValueError(
                "An efficient frontier requires explicit sourced annual return assumptions and 2–8 target returns."
            )
        if any(not -1 <= v <= 5 for v in self.return_targets):
            raise ValueError("Annual target returns must be finite and in [-1,5].")
        return self


class SensitivityVariation(StrictModel):
    kind: Literal["window", "shrinkage", "max_weight", "sector_max", "turnover", "cost_penalty"]
    value: float | int
    sector: str | None = Field(None, max_length=100)


class SensitivityRequest(StrictModel):
    base: OptimizationRequest = Field(default_factory=OptimizationRequest)
    variations: list[SensitivityVariation] = Field(min_length=1, max_length=8)


class OptimizationCompareRequest(StrictModel):
    run_ids: list[str] = Field(min_length=2, max_length=4)


class CounterfactualRequest(StrictModel):
    run_id: str = Field(max_length=36)
    point_index: int = Field(0, ge=0, le=8, strict=True)
    scenario: StressRequest
