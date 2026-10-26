"""Real ARCH and LightGBM models; all fit boundaries supplied explicitly."""

import warnings

import numpy as np

from app.core.errors import AppError
from app.ml.evaluation import variance_losses
from app.ml.features import apply_imputer, fit_imputer

SCALE = 10_000.0


def fit_garch(history):
    from arch import arch_model

    r = np.ascontiguousarray(history, dtype=float)
    if len(r) < 150 or not np.isfinite(r).all() or np.ptp(r) < 1e-12:
        raise AppError("GARCH_SAMPLE", "GARCH needs at least 150 finite, nonconstant returns.")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fitted = arch_model(
            100 * r, mean="Zero", vol="GARCH", p=1, q=1, dist="normal", rescale=False
        ).fit(disp="off", show_warning=False, options={"maxiter": 300, "ftol": 1e-9})
    if fitted.convergence_flag != 0:
        raise AppError(
            "GARCH_CONVERGENCE",
            f"ARCH optimizer did not converge (flag {fitted.convergence_flag}).",
        )
    params = {
        "omega": float(fitted.params["omega"]) / SCALE,
        "alpha": float(fitted.params["alpha[1]"]),
        "beta": float(fitted.params["beta[1]"]),
    }
    h = float(fitted.forecast(horizon=1, reindex=False).variance.iloc[-1, 0]) / SCALE
    if (
        not np.isfinite([h, *params.values()]).all()
        or h <= 0
        or params["omega"] <= 0
        or min(params["alpha"], params["beta"]) < 0
        or params["alpha"] + params["beta"] > 1 + 1e-7
    ):
        raise AppError(
            "GARCH_VARIANCE", "ARCH returned invalid Gaussian GARCH variance/parameters."
        )
    notes = [f"{w.category.__name__}: {str(w.message)[:240]}" for w in caught]
    if params["alpha"] + params["beta"] >= 0.999:
        notes.append("GARCH persistence is near the unit boundary; long-run variance is unstable.")
    return params, h, notes


def garch_update(parameters, observed_return, previous_variance):
    return (
        parameters["omega"]
        + parameters["alpha"] * observed_return**2
        + parameters["beta"] * previous_variance
    )


def lgb_parameters(request, leaves):
    return {
        "objective": "regression_l2",
        "metric": "None",
        "learning_rate": request.learning_rate,
        "num_leaves": leaves,
        "max_depth": 5,
        "min_data_in_leaf": 20,
        "lambda_l2": 1.0,
        "feature_pre_filter": False,
        "seed": request.seed,
        "feature_fraction_seed": request.seed,
        "bagging_seed": request.seed,
        "deterministic": True,
        "force_col_wise": True,
        "num_threads": 1,
        "verbosity": -1,
    }


def select_lightgbm(train_x, train_y, validation_x, validation_y, request):
    import lightgbm as lgb

    imputer = fit_imputer(train_x)
    x = apply_imputer(train_x, imputer)
    v = apply_imputer(validation_x, imputer)
    names = list(imputer["medians"])
    search = []
    for leaves in (7, 15, 31)[: request.search_candidates]:

        def qlike(predictions, dataset):
            h = np.maximum(predictions / SCALE, request.variance_floor)
            y = dataset.get_label().astype(float) / SCALE
            return "qlike", float(variance_losses(y, h)["qlike"].mean()), False

        booster = lgb.train(
            lgb_parameters(request, leaves),
            lgb.Dataset(x, label=train_y * SCALE, feature_name=names),
            num_boost_round=request.max_trees,
            valid_sets=[
                lgb.Dataset(v, label=validation_y * SCALE, reference=None, feature_name=names)
            ],
            valid_names=["validation"],
            feval=qlike,
            callbacks=[lgb.early_stopping(15, first_metric_only=True, verbose=False)],
        )
        prediction = np.maximum(booster.predict(v, num_threads=1) / SCALE, request.variance_floor)
        score = float(variance_losses(validation_y, prediction)["qlike"].mean())
        search.append(
            {
                "num_leaves": leaves,
                "iterations": max(1, booster.best_iteration),
                "validation_qlike": score,
                "max_trees": request.max_trees,
                "early_stopping_rounds": 15,
                "training_rows": len(train_x),
                "validation_rows": len(validation_x),
            }
        )
    selected = min(search, key=lambda row: row["validation_qlike"])
    return selected, search


def fit_lightgbm(features, targets, request, selected):
    import lightgbm as lgb

    imputer = fit_imputer(features)
    values = apply_imputer(features, imputer)
    booster = lgb.train(
        lgb_parameters(request, selected["num_leaves"]),
        lgb.Dataset(values, label=targets * SCALE, feature_name=list(imputer["medians"])),
        num_boost_round=selected["iterations"],
    )
    stats = {}
    for i, name in enumerate(imputer["medians"]):
        stats[name] = {
            "mean": float(values[:, i].mean()),
            "std": float(values[:, i].std(ddof=0)),
            "p05": float(np.quantile(values[:, i], 0.05)),
            "p95": float(np.quantile(values[:, i], 0.95)),
        }
    return booster, imputer, stats
