from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Holding(StrictModel):
    instrument: str
    name: str
    sector: str
    quantity: Positive
    last_price: Positive
    average_price: NonNegative
    value: Positive
    weight: Annotated[float, Field(gt=0, le=1)]
    unrealized_pnl: float


class Portfolio(StrictModel):
    mode: Literal["demo", "kite"]
    synthetic: bool
    currency: Literal["INR"] = "INR"
    source: str
    as_of: date
    retrieved_at: datetime
    price_timestamp_note: str
    holdings: list[Holding]
    total_value: Positive
    total_cost: NonNegative
    unrealized_pnl: float
    largest_weight: float
    hhi: float
    sectors: dict[str, float]
    warnings: list[str]


class Provenance(StrictModel):
    source: str
    synthetic: bool
    adjustment: Literal["split_dividend_adjusted", "unadjusted", "unknown"]
    currency: Literal["INR"] = "INR"
    retrieved_at: datetime
    start: date
    end: date
    content_hash: str


class RiskPoint(StrictModel):
    date: date
    scenario_index: float
    daily_return: float | None
    drawdown: float
    rolling_volatility: float | None


class RiskResult(StrictModel):
    run_id: str
    methodology: str
    mode: Literal["demo", "kite"]
    confidence: float
    horizon: str
    loss_convention: str
    weighting: str
    sample_size: int
    requested_window: int
    start: date
    end: date
    annualized_volatility: float
    historical_var: float
    historical_var_amount: float
    maximum_drawdown: float
    tail_sample_mass: float
    provenance: Provenance
    series: list[RiskPoint]
    instruments: list[str]
    covariance: list[list[float]]
    correlation: list[list[float | None]]
    warnings: list[str]
