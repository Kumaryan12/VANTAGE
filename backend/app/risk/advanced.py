"""Single shared service for historical, Gaussian, and Monte Carlo comparisons."""

from uuid import uuid4

import numpy as np
from sqlalchemy.orm import Session

from app.portfolios.schemas import Portfolio
from app.risk.artifacts import frame_payload, metadata, payload_frame, persist_inputs, persist_run
from app.risk.contracts import AnalysisRequest, AnalysisResult, Attribution, TailEstimate
from app.risk.covariance import correlation_matrix, estimate_covariance
from app.risk.engine import asset_returns, calculate
from app.risk.parametric import gaussian_risk, volatility_attribution
from app.risk.service import resolve_prices
from app.risk.simulation import monte_carlo
from app.risk.tails import empirical_tail


def attribution_result(portfolio: Portfolio, covariance) -> Attribution:
    output = volatility_attribution(covariance, [h.weight for h in portfolio.holdings])
    assets, sectors = [], {}
    for i, h in enumerate(portfolio.holdings):
        component = output["component"][i]
        assets.append(
            {
                "instrument": h.instrument,
                "name": h.name,
                "sector": h.sector,
                "weight": h.weight,
                "marginal_daily_volatility": output["marginal"][i],
                "component_daily_volatility": component,
                "component_annualized_volatility": component * np.sqrt(252),
                "percentage_contribution": output["percentage"][i],
            }
        )
        sector = sectors.setdefault(
            h.sector,
            {
                "sector": h.sector,
                "weight": 0.0,
                "component_daily_volatility": 0.0,
                "component_annualized_volatility": 0.0,
                "percentage_contribution": None if output["daily_volatility"] == 0 else 0.0,
            },
        )
        sector["weight"] += h.weight
        sector["component_daily_volatility"] += component
        sector["component_annualized_volatility"] += component * np.sqrt(252)
        if sector["percentage_contribution"] is not None:
            sector["percentage_contribution"] += output["percentage"][i]
    positive = np.maximum(output["component"], 0)
    return Attribution(
        daily_volatility=output["daily_volatility"],
        annualized_volatility=output["daily_volatility"] * np.sqrt(252),
        assets=assets,
        sectors=list(sectors.values()),
        weight_hhi=portfolio.hhi,
        positive_component_hhi=float(np.sum((positive / positive.sum()) ** 2))
        if positive.sum() > 0
        else None,
        reconciliation_residual=output["reconciliation_residual"],
        note=output["note"],
    )


def estimate(method: str, result: dict, value: float, assumptions: list[str]) -> TailEstimate:
    return TailEstimate(
        method=method,
        var=result["var"],
        expected_shortfall=result["expected_shortfall"],
        var_return=result["var"] / value,
        es_return=result["expected_shortfall"] / value,
        tail_sample_mass=result.get("tail_sample_mass"),
        assumptions=assumptions,
    )


def run_analysis(
    db: Session,
    portfolio: Portfolio,
    owner: str,
    parameters: AnalysisRequest,
    *,
    replay_payload: dict | None = None,
):
    if replay_payload is None:
        prices, provenance = resolve_prices(db, portfolio, owner, parameters.dataset_id)
    else:
        prices, provenance = payload_frame(replay_payload["estimation"])
    weights = np.array([h.weight for h in portfolio.holdings])
    # The Phase 1 engine is also the shared date/window/minimum-sample validator.
    legacy = calculate(prices, weights, parameters.confidence, parameters.window)
    prices = prices.tail(parameters.window + 1)
    returns = asset_returns(prices)
    covariance, diagnostics = estimate_covariance(returns, parameters.shrinkage)
    means = returns.mean(axis=0)
    historical = empirical_tail(-portfolio.total_value * (returns @ weights), parameters.confidence)
    gaussian = gaussian_risk(
        means, covariance, weights, portfolio.total_value, parameters.confidence
    )
    simulation = monte_carlo(
        means,
        covariance,
        weights,
        portfolio.total_value,
        parameters.confidence,
        parameters.simulations,
        parameters.seed,
    )
    payload = {"kind": "analysis", "estimation": frame_payload(prices, provenance)}
    snapshot, artifact = persist_inputs(db, portfolio, payload, owner)
    warnings = list(portfolio.warnings) + [
        "VaR is not maximum loss; no confidence level guarantees future coverage.",
        "Gaussian simulation and analytical Gaussian risk share the same fitted model; simulation does not remove model risk.",
        "Current-weight return scenarios are not actual account performance. No liquidity, cash, position, fee or tax effects.",
        "Historical means/covariance and tail estimates have parameter uncertainty not included in Monte Carlo sampling errors.",
    ]
    if historical["tail_sample_mass"] < 20:
        warnings.append(
            "Fewer than 20 empirical tail observations: historical tail estimates are statistically unstable."
        )
    if legacy["sample_size"] < parameters.window:
        warnings.append("Available history is shorter than the requested estimation window.")
    if diagnostics["ill_conditioned"]:
        warnings.append(
            "Covariance is singular or ill-conditioned. Spectral PSD sampling is used without an inverse; optional explicit shrinkage is available."
        )
    if diagnostics["negative_eigenvalues_clipped"] or diagnostics["symmetrized"]:
        warnings.append(
            "Covariance roundoff correction was applied and recorded in covariance diagnostics."
        )
    if parameters.shrinkage:
        warnings.append(
            "Explicit identity-target covariance shrinkage changes correlations and can assign variance to an otherwise constant asset."
        )
    if simulation["asset_returns_below_minus_one"]:
        warnings.append(
            "Some Gaussian asset draws fell below -100%; unbounded simple-return model limitations are visible and draws are not clipped."
        )
    meta = metadata(
        portfolio,
        parameters,
        snapshot,
        artifact,
        methodology="risk_comparison",
        sample_size=len(returns),
        provenance=provenance,
        start=prices.index[0].date(),
        end=prices.index[-1].date(),
        covariance_method=diagnostics["method"],
        warnings=warnings,
    )
    result = AnalysisResult(
        run_id=str(uuid4()),
        portfolio=portfolio,
        parameters=parameters,
        metadata=meta,
        provenance=provenance,
        expected_daily_return=gaussian["expected_return"],
        daily_volatility=gaussian["daily_volatility"],
        annualized_volatility=gaussian["daily_volatility"] * np.sqrt(252),
        sample_annualized_volatility=legacy["annualized_volatility"],
        models={
            "historical": estimate(
                "Historical inverse empirical CDF / quantile-integral ES",
                historical,
                portfolio.total_value,
                [
                    "Equal probability on aligned historical daily current-weight returns.",
                    "ES integrates exactly the upper (1-alpha) mass, including fractional observations.",
                ],
            ),
            "gaussian": estimate(
                "Gaussian analytical",
                gaussian,
                portfolio.total_value,
                [
                    "Sample historical mean and full covariance, with explicitly selected shrinkage.",
                    "Normal one-day simple returns; heavy tails and regime changes are not modeled.",
                ],
            ),
            "monte_carlo": estimate(
                "Correlated Gaussian Monte Carlo",
                simulation,
                portfolio.total_value,
                simulation["assumptions"],
            ),
        },
        covariance=covariance.tolist(),
        correlation=correlation_matrix(covariance),
        covariance_diagnostics=diagnostics,
        attribution=attribution_result(portfolio, covariance),
        simulation=simulation,
    )
    return persist_run(db, result, owner)
