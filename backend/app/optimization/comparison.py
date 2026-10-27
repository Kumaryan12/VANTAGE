"""Matched comparisons delegate all tail/attribution/stress mathematics to Phase 2."""

import numpy as np

from app.risk.advanced import attribution_result
from app.risk.parametric import gaussian_risk
from app.risk.simulation import monte_carlo
from app.risk.tails import empirical_tail

from .contracts import VirtualHolding, VirtualPortfolio


def virtual_portfolio(portfolio, weights):
    holdings = []
    sectors = {}
    for h, w in zip(portfolio.holdings, weights, strict=True):
        value = portfolio.total_value * float(w)
        holdings.append(
            VirtualHolding(
                **{
                    **h.model_dump(),
                    "quantity": value / h.last_price,
                    "value": value,
                    "weight": float(w),
                    "average_price": h.last_price,
                    "unrealized_pnl": 0,
                }
            )
        )
        sectors[h.sector] = sectors.get(h.sector, 0) + float(w)
    return VirtualPortfolio(
        **{
            **portfolio.model_dump(),
            "holdings": holdings,
            "sectors": sectors,
            "total_cost": portfolio.total_value,
            "unrealized_pnl": 0,
            "largest_weight": float(max(weights)),
            "hhi": float(np.asarray(weights) @ np.asarray(weights)),
            "source": portfolio.source
            + " / continuous counterfactual sleeve (not account inventory)",
            "warnings": [
                *portfolio.warnings,
                "Virtual fractional units support risk/stress analysis only; no executable shares or costs deducted from notional.",
            ],
        }
    )


def risk_metrics(portfolio, weights, returns, covariance, parameters):
    virtual = virtual_portfolio(portfolio, weights)
    mean = returns.mean(axis=0)
    gaussian = gaussian_risk(
        mean, covariance, weights, portfolio.total_value, parameters.confidence
    )
    historical = empirical_tail(-portfolio.total_value * (returns @ weights), parameters.confidence)
    simulation = monte_carlo(
        mean,
        covariance,
        weights,
        portfolio.total_value,
        parameters.confidence,
        parameters.simulations,
        parameters.seed,
    )
    return {
        "notional": portfolio.total_value,
        "daily_variance": gaussian["daily_volatility"] ** 2,
        "annual_variance": 252 * gaussian["daily_volatility"] ** 2,
        "annual_volatility": np.sqrt(252) * gaussian["daily_volatility"],
        "historical_var": historical["var"],
        "historical_es": historical["expected_shortfall"],
        "gaussian_var": gaussian["var"],
        "gaussian_es": gaussian["expected_shortfall"],
        "monte_carlo_var": simulation["var"],
        "monte_carlo_es": simulation["expected_shortfall"],
        "position_hhi": virtual.hhi,
        "sector_hhi": sum(v * v for v in virtual.sectors.values()),
        "sector_weights": virtual.sectors,
        "attribution": attribution_result(virtual, covariance).model_dump(mode="json"),
        "confidence": parameters.confidence,
        "observations": len(returns),
        "seed": parameters.seed,
        "simulations": parameters.simulations,
        "gaussian_mean_model": "Historical sample daily means; not the optional user-supplied annual expected-return assumptions.",
    }


def compare_allocations(
    portfolio, current, proposed, returns, covariance, parameters, current_metrics=None
):
    before = (
        current_metrics
        if current_metrics is not None
        else risk_metrics(portfolio, current, returns, covariance, parameters)
    )
    after = risk_metrics(portfolio, proposed, returns, covariance, parameters)
    metrics = (
        "annual_volatility",
        "annual_variance",
        "historical_var",
        "historical_es",
        "gaussian_var",
        "gaussian_es",
        "monte_carlo_var",
        "monte_carlo_es",
        "position_hhi",
        "sector_hhi",
    )
    return {
        "current": before,
        "proposed": after,
        "delta": {key: after[key] - before[key] for key in metrics},
        "volatility_reduction_fraction": 1
        - after["annual_volatility"] / before["annual_volatility"]
        if before["annual_volatility"] > 0
        else None,
        "policy": "Same sleeve notional, valuation date, ordered historical returns, observation window, covariance policy, confidence, horizon and seeded Gaussian asset draws. Costs are reported separately, not subtracted from fixed risk notional.",
        "warnings": [
            "In-sample minimum variance does not guarantee lower historical VaR, ES or every scenario loss, nor future risk reduction.",
            "Current/optimized historical baskets are retrospective continuous allocations, not realized account performance.",
            "Transaction costs are assumptions, not verified broker fees, executable quotes or liquidity/market-impact estimates.",
        ],
    }
