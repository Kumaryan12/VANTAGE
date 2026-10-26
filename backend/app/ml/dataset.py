import numpy as np
import pandas as pd

from app.core.errors import AppError
from app.ingestion.history import load_history
from app.ml.contracts import FEATURE_VERSION, ResearchRequest
from app.ml.features import LOOKBACK, build_features
from app.portfolios.schemas import Portfolio
from app.risk.artifacts import digest, frame_payload, payload_frame
from app.risk.engine import aligned_prices, asset_returns
from app.risk.service import resolve_prices


def capture_dataset(db, portfolio: Portfolio, owner: str, parameters: ResearchRequest):
    prices, provenance = resolve_prices(db, portfolio, owner, parameters.dataset_id)
    prices = prices.tail(parameters.history_window + 1)
    context = None
    if parameters.context_dataset_id:
        frame, source = load_history(db, parameters.context_dataset_id, owner)
        if (
            source.synthetic != portfolio.synthetic
            or source.adjustment != "split_dividend_adjusted"
        ):
            raise AppError("CONTEXT_SOURCE", "Benchmark must match mode and use adjusted prices.")
        benchmark = aligned_prices(frame, [parameters.benchmark_instrument])
        if not benchmark.index.equals(prices.index):
            raise AppError(
                "BENCHMARK_ALIGNMENT",
                "Select a benchmark history with exactly the portfolio's selected price dates; no filling or trimming is inferred.",
            )
        context = frame_payload(benchmark, source)
    payload = {
        "kind": "ml_research",
        "portfolio_history": frame_payload(prices, provenance),
        "context_history": context,
    }
    prepare_dataset(portfolio, payload, parameters)
    return payload


def prepare_dataset(portfolio: Portfolio, payload: dict, parameters: ResearchRequest):
    prices, provenance = payload_frame(payload["portfolio_history"])
    if (
        provenance.synthetic != portfolio.synthetic
        or provenance.adjustment != "split_dividend_adjusted"
    ):
        raise AppError(
            "RESEARCH_SOURCE", "Portfolio and adjusted historical source must have matching modes."
        )
    if list(prices.columns) != [h.instrument for h in portfolio.holdings]:
        raise AppError("RESEARCH_UNIVERSE", "Price columns must match the saved portfolio order.")
    weights = np.array([h.weight for h in portfolio.holdings])
    r = pd.Series(asset_returns(prices) @ weights, index=prices.index[1:], name="portfolio_return")
    required = parameters.initial_train + parameters.validation_size + parameters.test_size
    if len(r) < required:
        raise AppError(
            "RESEARCH_SAMPLE",
            f"This protocol needs at least {required} daily returns; selected data has {len(r)}.",
        )
    benchmark = None
    if payload.get("context_history"):
        market, _ = payload_frame(payload["context_history"])
        if not market.index.equals(prices.index):
            raise AppError(
                "BENCHMARK_ALIGNMENT", "Saved benchmark dates do not match portfolio dates."
            )
        benchmark = pd.Series(asset_returns(market)[:, 0], index=r.index)
    sector_returns = {}
    matrix = asset_returns(prices)
    for sector in sorted({h.sector for h in portfolio.holdings if h.sector != "Unknown"}):
        mask = np.array([h.sector == sector for h in portfolio.holdings])
        sector_returns[sector] = matrix[:, mask] @ (weights[mask] / weights[mask].sum())
    sector_frame = pd.DataFrame(sector_returns, index=r.index) if sector_returns else None
    features = build_features(
        r,
        decay=parameters.ewma_lambda,
        feature_set=parameters.feature_set,
        benchmark=benchmark,
        sectors=sector_frame,
    )
    test_start = len(r) - parameters.test_size
    validation_start = test_start - parameters.validation_size
    data_hash = digest(
        {"history": payload, "weights": weights.tolist(), "feature_version": FEATURE_VERSION}
    )
    info = {
        "snapshot_value": portfolio.total_value,
        "snapshot_as_of": portfolio.as_of.isoformat(),
        "series_id": f"frozen-portfolio:{data_hash[:16]}",
        "data_version": data_hash,
        "source": provenance.source,
        "synthetic": provenance.synthetic,
        "adjustment": provenance.adjustment,
        "frequency": "daily",
        "price_start": prices.index[0].date().isoformat(),
        "return_start": r.index[0].date().isoformat(),
        "end": r.index[-1].date().isoformat(),
        "price_observations": len(prices),
        "return_observations": len(r),
        "features": list(features.columns),
        "sector_context": "Frozen current-holdings sector baskets, not broad sector indices; unavailable for Unknown classifications.",
        "feature_version": FEATURE_VERSION,
        "warmup_observations": LOOKBACK,
        "portfolio_construction": "Frozen current snapshot weights applied to historical asset returns; not reconstructed historical holdings or account performance.",
        "availability_assumption": "Origin features available after close on their observation date; publication timestamps and common-date calendar gaps are source assertions.",
        "unavailable_features": [
            "Reliable volume is absent from the validated source schema.",
            "Macro/FX context lacks verified historical release availability and is excluded.",
        ]
        + (
            []
            if benchmark is not None
            else [
                "No explicit aligned benchmark supplied; market/sector benchmark features unavailable."
            ]
        ),
        "missing_price_policy": "Strict alignment; no fill, resampling, or invented observations.",
        "universe_limitation": "Current holdings imply retrospective universe selection/survivorship bias; delisted and past holdings are not reconstructed.",
    }
    protocol = {
        "target": "Next observed daily portfolio return squared; zero-mean conditional variance approximation",
        "horizon": "One observed trading day",
        "mean_model": "zero",
        "variance_units": "decimal return squared",
        "volatility_units": "decimal daily standard deviation",
        "loss_units": "INR using fixed saved snapshot notional",
        "train_start": r.index[0].date().isoformat(),
        "development_train_end": r.index[validation_start - 1].date().isoformat(),
        "validation_start": r.index[validation_start].date().isoformat(),
        "validation_end": r.index[test_start - 1].date().isoformat(),
        "test_start": r.index[test_start].date().isoformat(),
        "test_end": r.index[-1].date().isoformat(),
        "initial_train_observations": validation_start,
        "requested_initial_minimum": parameters.initial_train,
        "scheme": parameters.scheme,
        "refit_every": parameters.refit_every,
        "feature_availability": "At origin close; target interval (origin close, next observed close].",
        "selection_policy": "Bounded pre-test validation search/early stopping only; hyperparameters/iterations and regime thresholds locked before test.",
        "online_update_policy": "Earlier test labels may enter later prequential refits only after their target close is observed.",
        "purging": "One-day non-overlapping target; discard each origin's unobserved next label. No multi-day target or extra embargo.",
    }
    return r, features, info, protocol
