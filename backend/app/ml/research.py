"""Controlled one-step walk-forward experiment. No broker/network/DB calls."""

import json
import time

import numpy as np

from app.core.errors import AppError
from app.ml.contracts import FEATURE_VERSION, MODEL_VERSION, ResearchRequest
from app.ml.dataset import prepare_dataset
from app.ml.evaluation import metric_set, paired_uncertainty, variance_losses
from app.ml.features import LOOKBACK, apply_imputer, ewma_path, training_pairs
from app.ml.models import SCALE, fit_garch, fit_lightgbm, garch_update, select_lightgbm
from app.risk.parametric import gaussian_risk

KINDS = ("rolling", "ewma", "garch", "lightgbm")
LIMITATIONS = {
    "rolling": ["Zero-mean rolling second moment; fixed window can lag regime changes."],
    "ewma": ["Fixed decay selected before test; no leverage or heavy-tail model."],
    "garch": [
        "Gaussian zero-mean GARCH(1,1); estimation/convergence and persistence risk; no claimed superiority."
    ],
    "lightgbm": [
        "L2 regression on percent-return-squared target; no log-target retransformation bias, but model/selection bias and variance floors remain.",
        "Tree contributions explain fitted predictions, not market causation.",
    ],
}


def compare_forecasts(forecasts, models, request, experiment_id, start=None, end=None):
    groups = {
        kind: [
            p
            for p in forecasts
            if p["model_kind"] == kind
            and (not start or p["target_end"] >= str(start))
            and (not end or p["target_end"] <= str(end))
        ]
        for kind in KINDS
    }
    valid = {
        k: {p["target_end"]: p for p in rows if p["forecast_variance"] is not None}
        for k, rows in groups.items()
    }
    dates = sorted({p["target_end"] for rows in groups.values() for p in rows})
    common = set.intersection(*(set(v) for v in valid.values()))
    matched = sorted(common)
    rows = []
    for kind in KINDS:
        model = models[kind]
        rows.append(
            {
                "id": model["id"],
                "kind": kind,
                "role": model.get("role", "candidate" if kind == "lightgbm" else "benchmark"),
                "status": model["status"],
                "available_predictions": len(valid[kind]),
                "failures": len(groups[kind]) - len(valid[kind]),
                "metrics": metric_set([valid[kind][d] for d in matched], request.coverage_minimum),
                "execution_seconds": model["execution_seconds"],
                "limitations": LIMITATIONS[kind],
            }
        )
    uncertainty = []
    if matched:
        ml = variance_losses(
            [valid["lightgbm"][d]["realized_variance_proxy"] for d in matched],
            [valid["lightgbm"][d]["forecast_variance"] for d in matched],
        )["qlike"]
        for kind in KINDS[:-1]:
            base = variance_losses(
                [valid[kind][d]["realized_variance_proxy"] for d in matched],
                [valid[kind][d]["forecast_variance"] for d in matched],
            )["qlike"]
            uncertainty.append({"benchmark": kind, **paired_uncertainty(ml, base, request.seed)})
    notes = [
        "Squared daily returns are noisy variance proxies; QLIKE is applied to variance, not standard deviation.",
        "No automatic winner: QLIKE, variance errors, VaR calibration, regime stability, complexity and sampling uncertainty must be reviewed together.",
        "Repeated research choices against this test period would invalidate its locked-final-period interpretation.",
    ]
    if len(common) != len(dates):
        notes.append(
            "Some predictions failed. All leaderboard metrics use the common valid date intersection; exclusions are explicit."
        )
    return {
        "experiment_id": experiment_id,
        "start": dates[0] if dates else None,
        "end": dates[-1] if dates else None,
        "requested_observations": len(dates),
        "matched_observations": len(common),
        "excluded_dates": [d for d in dates if d not in common],
        "models": rows,
        "policy": "Matched out-of-sample target dates; no metric-only champion or mismatched-window ranking.",
        "uncertainty": uncertainty,
        "warnings": notes,
    }


def execute_research(
    portfolio,
    payload,
    request: ResearchRequest,
    model_ids,
    write_artifact,
    progress=lambda *_: None,
    experiment_id="research",
):
    r, x, info, protocol = prepare_dataset(portfolio, payload, request)
    n = len(r)
    test_start = n - request.test_size
    validation_start = test_start - request.validation_size

    def date(i):
        return r.index[i].date().isoformat()

    def start_for(origin):
        return (
            0
            if request.scheme == "expanding"
            else max(0, origin - request.rolling_train_window + 1)
        )

    train_origin = validation_start - 1
    train_x, train_y = training_pairs(x, r, train_origin, start_for(train_origin))
    val_x = x.iloc[validation_start - 1 : test_start - 1]
    val_y = r.iloc[validation_start:test_start].to_numpy() ** 2
    progress(15, "Selecting LightGBM on development validation only")
    selection_started = time.perf_counter()
    selected, search = select_lightgbm(train_x, train_y, val_x, val_y, request)
    selection_seconds = time.perf_counter() - selection_started
    indicator = x.second_moment_60
    threshold_values = indicator.iloc[LOOKBACK - 1 : validation_start - 1].dropna().to_numpy()
    low, high = np.quantile(threshold_values, [1 / 3, 2 / 3]).tolist()

    def regime(i):
        return (
            "low" if indicator.iloc[i] <= low else "high" if indicator.iloc[i] > high else "medium"
        )

    models = {
        k: {
            "id": model_ids[k],
            "kind": k,
            "role": "candidate" if k == "lightgbm" else "benchmark",
            "status": "completed",
            "execution_seconds": 0.0,
            "refits": [],
            "global_importance": [],
            "drift": [],
            "latest_forecast": None,
            "artifact_files": [],
            "config": {},
            "limitations": LIMITATIONS[k],
        }
        for k in KINDS
    }
    models["lightgbm"]["execution_seconds"] = selection_seconds
    models["rolling"]["config"] = {
        "window": request.rolling_window,
        "estimator": "zero-mean population second moment",
    }
    models["ewma"]["config"] = {
        "lambda": request.ewma_lambda,
        "initialization": "mean of first 20 available squared returns",
    }
    models["garch"]["config"] = {
        "mean": "Zero",
        "p": 1,
        "q": 1,
        "innovations": "Gaussian",
        "return_scale": 100,
        "variance_scale_back": SCALE,
    }
    models["lightgbm"]["config"] = {
        "objective": "L2 direct conditional second moment",
        "target_scale": SCALE,
        "selected": selected,
        "search_history": search,
        "feature_set": request.feature_set,
    }
    state = {}
    forecasts = []
    regimes = []
    failures = []
    first_lgb = None
    ewma = ewma_path(r.to_numpy(), request.ewma_lambda)
    for step, origin in enumerate(range(test_start - 1, n)):
        is_latest = origin == n - 1
        scheduled = step % request.refit_every == 0
        # Include a final fit for the next-session forecast; it is never scored as OOS.
        should_refit = scheduled or is_latest
        train_start = start_for(origin)
        fit_meta = {
            "id": f"refit-{date(origin)}",
            "forecast_origin": date(origin),
            "training_start": date(train_start),
            "training_end": date(origin),
            "training_return_observations": origin - train_start + 1,
            "max_label_available_at": date(origin),
            "feature_version": FEATURE_VERSION,
        }
        if should_refit:
            progress(
                30 + int(55 * step / request.test_size), f"Walk-forward refit at {date(origin)}"
            )
            t = time.perf_counter()
            try:
                params, h, notes = fit_garch(r.iloc[train_start : origin + 1].to_numpy())
                state["garch"] = {"params": params, "h": h, "fit_id": fit_meta["id"]}
                content = {
                    "parameters": params,
                    "next_variance": h,
                    "mean": "zero",
                    "training": fit_meta,
                    "warnings": notes,
                }
                file = write_artifact(
                    "garch", f"{fit_meta['id']}.json", json.dumps(content, sort_keys=True)
                )
                models["garch"]["refits"].append({**fit_meta, **content, "artifact": file})
                models["garch"]["artifact_files"].append(file)
            except AppError as error:
                state["garch"] = {"failure": error.message, "fit_id": fit_meta["id"]}
                models["garch"]["refits"].append({**fit_meta, "failure": error.message})
                failures.append(f"GARCH {date(origin)}: {error.message}")
            models["garch"]["execution_seconds"] += time.perf_counter() - t
            t = time.perf_counter()
            tx, ty = training_pairs(x, r, origin, train_start)
            booster, imputer, stats = fit_lightgbm(tx, ty, request, selected)
            text = booster.model_to_string()
            file = write_artifact("lightgbm", f"{fit_meta['id']}.txt", text)
            refit = {
                **fit_meta,
                "training_feature_rows": len(tx),
                "last_training_feature_origin": tx.index[-1].date().isoformat(),
                "imputer": imputer,
                "training_feature_statistics": stats,
                "artifact": file,
                "selected": selected,
            }
            models["lightgbm"]["refits"].append(refit)
            models["lightgbm"]["artifact_files"].append(file)
            state["lightgbm"] = {
                "booster": booster,
                "imputer": imputer,
                "stats": stats,
                "fit_id": fit_meta["id"],
            }
            if first_lgb is None:
                first_lgb = {"imputer": imputer, "stats": stats}
            models["lightgbm"]["execution_seconds"] += time.perf_counter() - t
        elif "params" in state["garch"]:
            state["garch"]["h"] = garch_update(
                state["garch"]["params"], float(r.iloc[origin]), state["garch"]["h"]
            )
        raw = {}
        t = time.perf_counter()
        raw["rolling"] = float(
            np.mean(r.iloc[origin - request.rolling_window + 1 : origin + 1].to_numpy() ** 2)
        )
        models["rolling"]["execution_seconds"] += time.perf_counter() - t
        t = time.perf_counter()
        raw["ewma"] = (
            float(ewma[origin])
            if request.scheme == "expanding"
            else float(
                ewma_path(r.iloc[train_start : origin + 1].to_numpy(), request.ewma_lambda)[-1]
            )
        )
        models["ewma"]["execution_seconds"] += time.perf_counter() - t
        raw["garch"] = state["garch"].get("h")
        t = time.perf_counter()
        lgb = state["lightgbm"]
        raw["lightgbm"] = (
            float(
                lgb["booster"].predict(
                    apply_imputer(x.iloc[[origin]], lgb["imputer"]), num_threads=1
                )[0]
            )
            / SCALE
        )
        models["lightgbm"]["execution_seconds"] += time.perf_counter() - t
        for kind in KINDS:
            value = raw[kind]
            failure = state.get(kind, {}).get("failure")
            if value is not None and (not np.isfinite(value) or (kind == "garch" and value <= 0)):
                value = None
                failure = "Nonfinite or nonpositive model variance."
            floor = value is not None and value < request.variance_floor
            h = max(value, request.variance_floor) if value is not None else None
            var95 = (
                gaussian_risk([0], [[h]], [1], portfolio.total_value, 0.95)["var"]
                if h is not None
                else None
            )
            var99 = (
                gaussian_risk([0], [[h]], [1], portfolio.total_value, 0.99)["var"]
                if h is not None
                else None
            )
            fit_id = state.get(kind, {}).get("fit_id", f"{kind}-{date(train_start)}-{date(origin)}")
            if h is None:
                models[kind]["status"] = "partial"
            if is_latest:
                models[kind]["latest_forecast"] = {
                    "origin": date(origin),
                    "target_date": None,
                    "horizon": "next observed trading session; calendar date not inferred",
                    "forecast_variance": h,
                    "forecast_volatility": float(np.sqrt(h)) if h is not None else None,
                    "var95": var95,
                    "var99": var99,
                    "training_window_id": fit_id,
                    "floor_applied": floor,
                    "failure": failure,
                }
                continue
            loss = -portfolio.total_value * float(r.iloc[origin + 1])
            feature_values = (
                {name: float(v) if np.isfinite(v) else None for name, v in x.iloc[origin].items()}
                if kind == "lightgbm"
                else {}
            )
            forecasts.append(
                {
                    "model_id": model_ids[kind],
                    "model_kind": kind,
                    "origin": date(origin),
                    "feature_available_at": date(origin),
                    "target_start": date(origin),
                    "target_end": date(origin + 1),
                    "forecast_variance": h,
                    "forecast_volatility": float(np.sqrt(h)) if h is not None else None,
                    "realized_variance_proxy": float(r.iloc[origin + 1] ** 2),
                    "actual_return": float(r.iloc[origin + 1]),
                    "realized_loss": loss,
                    "var95": var95,
                    "var99": var99,
                    "exception95": loss > var95 if h is not None else None,
                    "exception99": loss > var99 if h is not None else None,
                    "regime": regime(origin),
                    "training_window_id": fit_id,
                    "model_version": MODEL_VERSION,
                    "data_version": info["data_version"],
                    "series_id": info["series_id"],
                    "source": info["source"],
                    "frequency": "daily",
                    "adjustment": info["adjustment"],
                    "missing_feature_count": int(x.iloc[origin].isna().sum()),
                    "feature_values": feature_values,
                    "floor_applied": floor,
                    "failure": failure,
                }
            )
            if h is None:
                models[kind]["status"] = "partial"
        if not is_latest:
            regimes.append(
                {
                    "origin": date(origin),
                    "target": date(origin + 1),
                    "lagged_variance": float(indicator.iloc[origin]),
                    "regime": regime(origin),
                }
            )
    final = state["lightgbm"]
    gains = final["booster"].feature_importance(importance_type="gain")
    splits = final["booster"].feature_importance(importance_type="split")
    models["lightgbm"]["global_importance"] = [
        {
            "feature": name,
            "gain": float(gain),
            "split_count": int(split),
            "gain_share": float(gain / gains.sum()) if gains.sum() else 0.0,
        }
        for name, gain, split in zip(final["booster"].feature_name(), gains, splits, strict=True)
    ]
    drift_values = apply_imputer(x.iloc[test_start - 1 : n - 1], first_lgb["imputer"])
    for i, name in enumerate(first_lgb["imputer"]["medians"]):
        stats = first_lgb["stats"][name]
        values = drift_values[:, i]
        models["lightgbm"]["drift"].append(
            {
                "feature": name,
                "standardized_mean_difference": float(
                    (values.mean() - stats["mean"]) / stats["std"]
                )
                if stats["std"] > 0
                else None,
                "outside_training_5_95_fraction": float(
                    np.mean((values < stats["p05"]) | (values > stats["p95"]))
                ),
                "note": "First test refit's training-feature reference; retrospective drift diagnostic, never used to select a model.",
            }
        )
    for kind in ("rolling", "ewma"):
        file = write_artifact(
            kind,
            "configuration.json",
            json.dumps(
                {
                    "config": models[kind]["config"],
                    "latest": models[kind]["latest_forecast"],
                    "protocol": protocol,
                },
                sort_keys=True,
            ),
        )
        models[kind]["artifact_files"].append(file)
    comparison = compare_forecasts(forecasts, models, request, experiment_id)
    for row in comparison["models"]:
        models[row["kind"]]["metrics"] = row["metrics"]
    by_regime = []
    common = set(p["target_end"] for p in forecasts) - set(comparison["excluded_dates"])
    for reg in ("low", "medium", "high"):
        for kind in KINDS:
            rows = [
                p
                for p in forecasts
                if p["model_kind"] == kind and p["regime"] == reg and p["target_end"] in common
            ]
            by_regime.append(
                {
                    "regime": reg,
                    "model_kind": kind,
                    "metrics": metric_set(rows, request.coverage_minimum),
                }
            )
    return {
        "dataset": info,
        "protocol": protocol,
        "models": models,
        "forecasts": forecasts,
        "comparison": comparison,
        "regimes": {
            "thresholds": {"low_upper": low, "high_lower": high},
            "estimated_through": date(validation_start - 2),
            "rows": regimes,
            "metrics": by_regime,
            "note": "Trailing 60-observation second-moment indicator at each origin; thresholds fixed from development training. No crash-prediction claim.",
        },
        "warnings": failures
        + [
            "Synthetic experiments demonstrate software/protocol behavior, not predictive evidence for real markets."
        ]
        if portfolio.synthetic
        else failures,
    }
