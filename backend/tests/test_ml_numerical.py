import math

import numpy as np
import pandas as pd
import pytest

from app.core.errors import AppError
from app.ml.contracts import ResearchRequest
from app.ml.evaluation import coverage_tests, variance_losses
from app.ml.features import apply_imputer, build_features, ewma_path, fit_imputer, training_pairs
from app.ml.models import fit_garch, garch_update
from app.risk.parametric import gaussian_risk


def series(n=320):
    return pd.Series(
        np.random.default_rng(42).normal(0, 0.01, n), index=pd.bdate_range("2024-01-01", periods=n)
    )


def test_ewma_hand_recurrence_and_initialization():
    # Initial h at origin 1 is (.01²+.02²)/2=.00025; update with .03².
    result = ewma_path([0.01, 0.02, 0.03, 0.04], 0.5, 2)
    assert np.isnan(result[0])
    assert result[1] == pytest.approx(0.00025)
    assert result[2] == pytest.approx(0.000575)
    assert result[3] == pytest.approx(0.0010875)
    assert np.array_equal(ewma_path([0] * 30)[19:], np.zeros(11))


def test_feature_lags_and_future_mutation_cannot_change_past():
    r = series()
    x = build_features(r)
    origin = 180
    changed = r.copy()
    changed.iloc[origin + 1 :] = 0.5
    after = build_features(changed)
    pd.testing.assert_frame_equal(x.iloc[: origin + 1], after.iloc[: origin + 1])
    assert x.iloc[origin].return_lag_0 == r.iloc[origin]
    assert x.iloc[origin].return_lag_1 == r.iloc[origin - 1]
    assert x.iloc[origin].second_moment_5 == pytest.approx(
        np.mean(r.iloc[origin - 4 : origin + 1].to_numpy() ** 2)
    )
    tx, ty = training_pairs(x, r, origin)
    assert tx.index[-1] == r.index[origin - 1]
    assert ty[-1] == r.iloc[origin] ** 2
    assert len(tx) == len(ty)


def test_training_imputer_never_uses_evaluation_values():
    train = pd.DataFrame({"a": [1.0, 3.0, np.nan], "b": [np.nan] * 3})
    fit = fit_imputer(train)
    assert fit == {"medians": {"a": 2.0}, "dropped_features": ["b"]}
    test = pd.DataFrame({"a": [10000.0, np.nan], "b": [8.0, 10.0]})
    assert apply_imputer(test, fit).tolist() == [[10000.0], [2.0]]


@pytest.mark.parametrize("change", ["nan", "duplicate", "unsorted", "minus_one"])
def test_bad_research_returns(change):
    r = series()
    if change == "nan":
        r.iloc[2] = np.nan
    elif change == "duplicate":
        r.index = pd.DatetimeIndex([r.index[0]] * len(r))
    elif change == "unsorted":
        r = r.iloc[::-1]
    else:
        r.iloc[2] = -1
    with pytest.raises(AppError):
        build_features(r)


def test_qlike_variance_units_known_values():
    output = variance_losses([0.0001, 0.0004], [0.0001, 0.0002])
    assert output["qlike"].tolist() == pytest.approx([math.log(0.0001) + 1, math.log(0.0002) + 2])
    assert output["squared_error"].tolist() == pytest.approx([0, 4e-8])
    assert output["absolute_error"].tolist() == pytest.approx([0, 0.0002])


@pytest.mark.parametrize(
    "y,h",
    [([], []), ([1], [0]), ([1], [-1]), ([-1], [1]), ([float("nan")], [1]), ([1], [float("inf")])],
)
def test_qlike_invalid(y, h):
    with pytest.raises(AppError):
        variance_losses(y, h)


def test_kupiec_independent_binomial_examples_and_edges():
    exact = coverage_tests([True] * 5 + [False] * 95, 0.95)
    assert exact["kupiec_statistic"] == pytest.approx(0, abs=1e-12)
    assert exact["kupiec_p_value"] == pytest.approx(1)
    zero = coverage_tests([False] * 100, 0.95)
    assert zero["kupiec_statistic"] == pytest.approx(-200 * math.log(0.95), abs=1e-12)
    assert zero["independence_p_value"] is None
    assert zero["conditional_p_value"] is None
    all_ = coverage_tests([True] * 100, 0.99)
    assert math.isfinite(all_["kupiec_statistic"])
    assert all_["independence_statistic"] is None
    assert coverage_tests([False] * 10, 0.95)["kupiec_p_value"] is None
    assert coverage_tests([], 0.95)["exception_rate"] is None


def test_christoffersen_known_independent_transition_table():
    # n00=4,n01=2,n10=2,n11=1 -> each row and pooled transition probability 1/3.
    e = [0, 0, 1, 0, 0, 1, 1, 0, 0, 0]
    output = coverage_tests(e, 0.95, min_n=10)
    assert output["transitions"] == {"n00": 4, "n01": 2, "n10": 2, "n11": 1}
    assert output["independence_statistic"] == pytest.approx(0, abs=1e-12)
    assert output["independence_p_value"] == pytest.approx(1)
    assert output["conditional_statistic"] == pytest.approx(output["kupiec_statistic"])
    # Chi-square df2 survival has the independent analytical form exp(-x/2).
    assert output["conditional_p_value"] == pytest.approx(
        math.exp(-output["conditional_statistic"] / 2)
    )


def test_conditional_loss_sign_and_strict_exception():
    value = 1000.0
    h = 0.0004
    var = gaussian_risk([0], [[h]], [1], value, 0.95)["var"]
    assert var == pytest.approx(32.89707253902944)
    assert -value * (-0.04) > var
    assert -value * (0.04) < var
    assert not var > var


def test_garch_real_fit_scaling_and_update_alignment():
    r = series().to_numpy()
    params, forecast, _ = fit_garch(r)
    from arch import arch_model

    reference = arch_model(
        100 * r, mean="Zero", vol="GARCH", p=1, q=1, dist="normal", rescale=False
    ).fit(disp="off", show_warning=False, options={"maxiter": 300, "ftol": 1e-9})
    expected = float(reference.forecast(horizon=1, reindex=False).variance.iloc[-1, 0]) / 10000
    assert forecast == pytest.approx(expected, rel=1e-12)
    assert forecast > 0
    manual = params["omega"] + params["alpha"] * 0.02**2 + params["beta"] * forecast
    assert garch_update(params, 0.02, forecast) == manual
    with pytest.raises(AppError):
        fit_garch(np.zeros(200))


@pytest.mark.parametrize(
    "body",
    [
        {"test_size": 1},
        {"initial_train": 100},
        {"search_candidates": 4},
        {"seed": True},
        {"scheme": "rolling", "rolling_train_window": 160},
        {"context_dataset_id": "x"},
        {"mode": "demo", "dataset_id": "x"},
    ],
)
def test_research_protocol_validation(body):
    with pytest.raises(ValueError):
        ResearchRequest(**body)
