import json

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest

from app.brokers.demo import DemoBroker, demo_history
from app.ml.contracts import Forecast, ResearchRequest
from app.ml.features import apply_imputer
from app.ml.research import execute_research
from app.risk.artifacts import frame_payload
from app.risk.engine import aligned_prices


@pytest.fixture(scope="module")
def executed():
    portfolio = DemoBroker().portfolio()
    frame, source = demo_history()
    prices = aligned_prices(frame, [h.instrument for h in portfolio.holdings])
    payload = {"portfolio_history": frame_payload(prices, source), "context_history": None}
    files = {}

    def write(kind, name, content):
        files[kind + "/" + name] = content
        return {"path": kind + "/" + name, "sha256": "test", "bytes": len(content)}

    request = ResearchRequest(max_trees=40, search_candidates=2, test_size=60, validation_size=40)
    result = execute_research(
        portfolio, payload, request, {k: k for k in ("rolling", "ewma", "garch", "lightgbm")}, write
    )
    return portfolio, payload, request, result, files


def test_real_models_matched_oos_and_no_future_fit(executed):
    _, _, request, result, _ = executed
    assert result["comparison"]["matched_observations"] == 60
    assert len(result["forecasts"]) == 240
    for point in result["forecasts"]:
        Forecast.model_validate(point)
        assert point["origin"] == point["feature_available_at"] == point["target_start"]
        assert point["origin"] < point["target_end"]
        assert point["forecast_variance"] > 0
    for kind in ("garch", "lightgbm"):
        refits = result["models"][kind]["refits"]
        for fit in refits:
            assert fit["max_label_available_at"] == fit["forecast_origin"]
            assert fit["training_end"] == fit["forecast_origin"]
        origins = [f["forecast_origin"] for f in refits]
        for point in [p for p in result["forecasts"] if p["model_kind"] == kind]:
            fit = next(f for f in refits if f["id"] == point["training_window_id"])
            assert fit["training_end"] <= point["origin"]
            if kind == "lightgbm":
                assert fit["last_training_feature_origin"] < fit["forecast_origin"]
        assert len(origins) == request.test_size // request.refit_every + 1
    assert result["regimes"]["estimated_through"] < result["protocol"]["validation_start"]


def test_saved_booster_and_contributions_reproduce_forecast(executed):
    _, _, request, result, files = executed
    point = next(p for p in result["forecasts"] if p["model_kind"] == "lightgbm")
    fit = next(
        f for f in result["models"]["lightgbm"]["refits"] if f["id"] == point["training_window_id"]
    )
    booster = lgb.Booster(model_str=files[fit["artifact"]["path"]])
    x = apply_imputer(pd.DataFrame([point["feature_values"]]), fit["imputer"])
    raw = float(booster.predict(x, num_threads=1)[0]) / 10000
    assert max(raw, request.variance_floor) == point["forecast_variance"]
    contributions = booster.predict(x, pred_contrib=True, num_threads=1)[0] / 10000
    assert contributions.sum() == pytest.approx(raw, abs=1e-15)
    assert result["models"]["lightgbm"]["global_importance"]
    assert result["models"]["lightgbm"]["drift"]


def test_same_seed_reproduces_predictions(executed):
    portfolio, payload, request, first, _ = executed
    second = execute_research(
        portfolio,
        payload,
        request,
        {k: k for k in ("rolling", "ewma", "garch", "lightgbm")},
        lambda k, n, s: {"path": k + "/" + n, "sha256": "test", "bytes": len(s)},
    )
    a = [p["forecast_variance"] for p in first["forecasts"]]
    b = [p["forecast_variance"] for p in second["forecasts"]]
    np.testing.assert_array_equal(a, b)
    assert first["protocol"] == second["protocol"]
    json.dumps(first, allow_nan=False)


def test_rolling_window_and_future_target_mutation(executed):
    """Re-execute full pipeline: future target shocks cannot alter earlier predictions."""
    portfolio, payload, original, first, _ = executed
    request = original.model_copy(update={"scheme": "rolling", "rolling_train_window": 240})

    def writer(k, n, s):
        return {"path": k + "/" + n, "sha256": "test", "bytes": len(s)}

    rolling = execute_research(
        portfolio,
        payload,
        request,
        {k: k for k in ("rolling", "ewma", "garch", "lightgbm")},
        writer,
    )
    assert rolling["comparison"]["matched_observations"] == 60
    for kind in ("garch", "lightgbm"):
        for fit in rolling["models"][kind]["refits"]:
            assert fit["training_start"] >= rolling["dataset"]["return_start"]
    mutated = json.loads(json.dumps(payload))
    # Only the final price row changes: its target is unknown at the preceding origin.
    from app.risk.artifacts import payload_frame

    prices, source = payload_frame(mutated["portfolio_history"])
    prices.iloc[-1] *= 1.5
    mutated["portfolio_history"] = frame_payload(prices, source)
    changed = execute_research(
        portfolio,
        mutated,
        original,
        {k: k for k in ("rolling", "ewma", "garch", "lightgbm")},
        writer,
    )
    np.testing.assert_array_equal(
        [p["forecast_variance"] for p in first["forecasts"]],
        [p["forecast_variance"] for p in changed["forecasts"]],
    )
    assert first["regimes"]["thresholds"] == changed["regimes"]["thresholds"]
