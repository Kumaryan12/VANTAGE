"""Direct shock/replay P&L, deliberately without invented factor exposures."""

import numpy as np
import pandas as pd

from app.core.errors import AppError
from app.portfolios.schemas import Portfolio
from app.risk.conventions import validate_weights

NAMED_WINDOWS = [
    {
        "id": "pandemic_2020",
        "name": "Pandemic window · February–March 2020",
        "start": "2020-02-19",
        "end": "2020-03-23",
        "synthetic": False,
    },
    {
        "id": "first_half_2022",
        "name": "First half of 2022",
        "start": "2022-01-03",
        "end": "2022-06-30",
        "synthetic": False,
    },
    {
        "id": "synthetic_2026",
        "name": "Synthetic fixture window · May–June 2026",
        "start": "2026-05-01",
        "end": "2026-06-30",
        "synthetic": True,
    },
]


def impact(portfolio: Portfolio, returns, mappings: list[str]) -> dict:
    values = np.array([h.value for h in portfolio.holdings])
    shocks = np.asarray(returns, dtype=float)
    if shocks.shape != values.shape or not np.isfinite(shocks).all() or (shocks < -1).any():
        raise AppError(
            "INVALID_SHOCK", "Each holding requires a finite return no lower than -100%."
        )
    if len(mappings) != len(values):
        raise AppError("SHOCK_MAPPING", "Every security requires a documented shock mapping.")
    weights = validate_weights([h.weight for h in portfolio.holdings], len(values))
    pnl = values * shocks
    sectors: dict[str, dict] = {}
    assets = []
    for holding, shock, amount, mapping in zip(
        portfolio.holdings, shocks, pnl, mappings, strict=True
    ):
        assets.append(
            {
                "instrument": holding.instrument,
                "name": holding.name,
                "sector": holding.sector,
                "weight": holding.weight,
                "shock_return": float(shock),
                "pnl": float(amount),
                "loss": float(-amount),
                "value_before": holding.value,
                "value_after": float(holding.value + amount),
                "mapping": mapping,
            }
        )
        sector = sectors.setdefault(
            holding.sector, {"sector": holding.sector, "pnl": 0.0, "value_before": 0.0}
        )
        sector["pnl"] += float(amount)
        sector["value_before"] += holding.value
    total_pnl = float(pnl.sum())
    sector_rows = [
        {**s, "loss": -s["pnl"], "value_after": s["value_before"] + s["pnl"]}
        for s in sectors.values()
    ]
    return {
        "value_before": portfolio.total_value,
        "value_after": portfolio.total_value + total_pnl,
        "portfolio_return": float(weights @ shocks),
        "pnl": total_pnl,
        "loss": -total_pnl,
        "assets": assets,
        "sectors": sector_rows,
        "largest_loss_contributors": [
            a["instrument"]
            for a in sorted(assets, key=lambda a: a["loss"], reverse=True)
            if a["loss"] > 0
        ][:5],
        "pnl_reconciliation_residual": float(sum(s["pnl"] for s in sector_rows) - total_pnl),
    }


def hypothetical(
    portfolio: Portfolio,
    market_shock: float | None,
    sector_shocks: dict[str, float],
    security_shocks: dict[str, float],
) -> dict:
    universe = {h.instrument for h in portfolio.holdings}
    sectors = {h.sector for h in portfolio.holdings}
    unknown = sorted((set(security_shocks) - universe) | (set(sector_shocks) - sectors))
    if unknown:
        raise AppError(
            "UNKNOWN_SHOCK_TARGET",
            "Shock targets must exist in the authorized portfolio.",
            details=unknown,
        )
    if market_shock is None and not sector_shocks and not security_shocks:
        raise AppError("EMPTY_SCENARIO", "Supply a broad, sector, or security shock.")
    inputs = (
        list(sector_shocks.values())
        + list(security_shocks.values())
        + ([] if market_shock is None else [market_shock])
    )
    if not np.isfinite(inputs).all() or any(v < -1 or v > 5 for v in inputs):
        raise AppError(
            "INVALID_SHOCK", "Hypothetical simple-return shocks must be between -100% and +500%."
        )
    shocks, mappings = [], []
    for h in portfolio.holdings:
        if h.instrument in security_shocks:
            shocks.append(security_shocks[h.instrument])
            mappings.append("security override")
        elif h.sector in sector_shocks:
            shocks.append(sector_shocks[h.sector])
            mappings.append("sector override")
        else:
            shocks.append(market_shock if market_shock is not None else 0)
            mappings.append(
                "broad direct shock" if market_shock is not None else "explicit default: unchanged"
            )
    return {
        **impact(portfolio, shocks, mappings),
        "path": [],
        "observations": 0,
        "assumptions": [
            "User-defined hypothetical direct returns, not predictions or estimated factor sensitivities.",
            "Security overrides sector; sector overrides broad shock; overrides replace rather than add. Unmapped assets are unchanged.",
            "Instantaneous shocks applied to current position values, fixed quantities, no trading/costs/FX conversion.",
        ],
    }


def historical_replay(portfolio: Portfolio, prices: pd.DataFrame, start, end) -> dict:
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start >= end:
        raise AppError("SCENARIO_DATES", "Scenario start must precede end.")
    if end.date() > portfolio.as_of:
        raise AppError("FUTURE_SCENARIO", "Scenario cannot end after the portfolio valuation date.")
    if start not in prices.index or end not in prices.index:
        raise AppError(
            "SCENARIO_COVERAGE",
            "Exact scenario start and end observations are required for every holding; no nearest-date substitution.",
        )
    window = prices.loc[start:end]
    if (
        len(window) < 2
        or not np.isfinite(window.to_numpy()).all()
        or (window.to_numpy() <= 0).any()
    ):
        raise AppError(
            "SCENARIO_COVERAGE",
            "Scenario requires at least two complete, positive aligned price observations.",
        )
    # Scale each adjusted series to today's initial allocated value; hold virtual units fixed.
    ratios = window.to_numpy() / window.iloc[0].to_numpy()
    shocks = ratios[-1] - 1
    result = impact(
        portfolio, shocks, ["adjusted endpoint ratio; fixed initial allocation"] * len(shocks)
    )
    path = ratios @ np.array([h.value for h in portfolio.holdings])
    return {
        **result,
        "path": [
            {
                "date": dt.date().isoformat(),
                "value": float(v),
                "pnl": float(v - portfolio.total_value),
                "cumulative_return": float(v / portfolio.total_value - 1),
            }
            for dt, v in zip(window.index, path, strict=True)
        ],
        "observations": len(window),
        "assumptions": [
            "Current initial allocation replay, not actual historical account performance.",
            "Fixed virtual units of adjusted-price series, scaled to today's initial weights; no rebalancing during the window.",
            "Split/dividend-adjusted endpoint ratios act as total-return proxies. No raw/adjusted price-basis mixing.",
            "Exact endpoints and cross-asset dates checked; exchange-calendar completeness remains a source assertion.",
        ],
    }
