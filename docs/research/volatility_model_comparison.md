# VANTAGE — volatility model comparison

Experiment `05b2e5b4-d7a2-4971-a316-27574b112e71` · status **completed** · model `volatility-research-3.0.0`

## Research question
Can ML conditional variance forecasts improve out-of-sample portfolio risk calibration over rolling, EWMA and GARCH?

## Motivation
Conditional risk forecasts should earn their complexity against simple benchmarks through matched out-of-sample losses and tail calibration, including cases where ML performs worse.

## Data and portfolio construction
Source: VANTAGE synthetic fixture v1 / seed 20261026. **SYNTHETIC — software/protocol experiment, not real-market evidence**.
Price coverage 2024-11-18–2026-10-23; 504 daily portfolio returns; dataset SHA-256 `0c6494700501bc8f8d5c96f9f0a67a7ead6e8c7824699ac041e83ee3cfac8ed7`.
Frozen current snapshot weights applied to historical asset returns; not reconstructed historical holdings or account performance.
Fixed saved snapshot notional: INR 2,719,772.90; valuation as of 2026-10-23.
Current holdings imply retrospective universe selection/survivorship bias; delisted and past holdings are not reconstructed.
Origin features available after close on their observation date; publication timestamps and common-date calendar gaps are source assertions.

## Target and features
Next observed daily portfolio return squared; zero-mean conditional variance approximation. A single squared return is a noisy ex-post variance proxy, not observed latent volatility.
Features available after origin close: return_lag_0, squared_lag_0, return_lag_1, squared_lag_1, return_lag_2, squared_lag_2, return_lag_5, squared_lag_5, second_moment_5, mean_return_5, second_moment_10, mean_return_10, second_moment_20, mean_return_20, second_moment_60, mean_return_60, ewma_variance, absolute_return, drawdown_20, momentum_20, variance_ratio_5_60, volatility_of_variance_20, frozen_sector_dispersion_lag1, frozen_sector_second_moment_20.
Reliable volume is absent from the validated source schema.
Macro/FX context lacks verified historical release availability and is excluded.
No explicit aligned benchmark supplied; market/sector benchmark features unavailable.

## Protocol
Development training 2024-11-19–2026-03-13; validation 2026-03-16–2026-06-05; final evaluation 2026-06-08–2026-10-23.
Scheme expanding; refit every 20 origins; seed 42.
Bounded pre-test validation search/early stopping only; hyperparameters/iterations and regime thresholds locked before test.
Earlier test labels may enter later prequential refits only after their target close is observed.
This is a retrospective development demonstration. The final period is excluded from fitting/tuning at each origin; repeated engineering inspection of this synthetic dataset is not a prospective untouched market study.

## Model specifications
Rolling: zero-mean rolling second moment. EWMA: fixed-decay second moment with historical initialization. GARCH: ARCH Gaussian zero-mean GARCH(1,1), percent-return scaling. LightGBM: L2 regression on scaled squared returns, training-only imputation, pre-test early stopping and bounded search; no exponentiated log-target bias.

## Out-of-sample results
Requested targets: 100; common valid targets: 100. Excluded dates: none.

| Model | N | QLIKE | MSE (variance) | MAE (variance) | 95% exceptions | 99% exceptions | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rolling | 100 | -8.33498733 | 1.20343242e-08 | 8.70826381e-05 | 5/100 | 0/100 | 0.0015 |
| ewma | 100 | -8.32796203 | 1.21275483e-08 | 8.76576103e-05 | 3/100 | 0/100 | 0.0000 |
| garch | 100 | -8.32901589 | 1.22218457e-08 | 9.19381591e-05 | 2/100 | 0/100 | 0.0801 |
| lightgbm | 100 | -8.31810563 | 1.25798025e-08 | 9.49205718e-05 | 3/100 | 0/100 | 0.0635 |

## Conditional VaR backtesting
Gaussian zero-mean one-day loss quantiles use the existing Phase 2 engine with predicted **portfolio** variance and fixed snapshot notional. Exceptions require realized loss strictly greater than VaR.

| Model / confidence | Kupiec LR | Kupiec p | Independence p | Conditional coverage p | Expected violations |
| --- | ---: | ---: | ---: | ---: | ---: |
| rolling / 95% | 0 | 1 | 0.465697647 | 0.766375514 | 5 |
| rolling / 99% | 2.01006717 | 0.1562584 | unavailable | unavailable | 1 |
| ewma / 95% | 0.976859117 | 0.322975472 | 0.664979933 | 0.558670836 | 5 |
| ewma / 99% | 2.01006717 | 0.1562584 | unavailable | unavailable | 1 |
| garch / 95% | 2.42859214 | 0.119139857 | 0.77396421 | 0.284923059 | 5 |
| garch / 99% | 2.01006717 | 0.1562584 | unavailable | unavailable | 1 |
| lightgbm / 95% | 0.976859117 | 0.322975472 | 0.664979933 | 0.558670836 | 5 |
| lightgbm / 99% | 2.01006717 | 0.1562584 | unavailable | unavailable | 1 |

No high-regime conclusions are possible when its observation count is zero. Sparse expected violations/transition counts limit asymptotic p-values. Missing states make independence/conditional coverage unavailable; non-rejection does not prove a correct model.

## Regimes
Trailing 60-observation second-moment indicator at each origin; thresholds fixed from development training. No crash-prediction claim.
Pre-validation thresholds: {'low_upper': 9.093180257987594e-05, 'high_lower': 0.00011154205641789788}; estimated through 2026-03-12.

| Regime | Model | N | QLIKE | 95% exceptions | 99% exceptions |
| --- | --- | ---: | ---: | ---: | ---: |
| low | rolling | 46 | -8.16987081 | 4 | 0 |
| low | ewma | 46 | -8.142321 | 3 | 0 |
| low | garch | 46 | -8.18916233 | 2 | 0 |
| low | lightgbm | 46 | -8.17026814 | 2 | 0 |
| medium | rolling | 54 | -8.47564213 | 1 | 0 |
| medium | ewma | 54 | -8.48610068 | 0 | 0 |
| medium | garch | 54 | -8.44815039 | 0 | 0 |
| medium | lightgbm | 54 | -8.44404127 | 1 | 0 |
| high | rolling | 0 | unavailable | 0 | 0 |
| high | ewma | 0 | unavailable | 0 | 0 |
| high | garch | 0 | unavailable | 0 | 0 |
| high | lightgbm | 0 | unavailable | 0 | 0 |

## Challenger comparison and uncertainty
Matched out-of-sample target dates; no metric-only champion or mismatched-window ranking.
LightGBM minus rolling QLIKE: 0.0168816948, descriptive 95% moving-block bootstrap interval [-0.030494700721196873, 0.061268029038692245].
LightGBM minus ewma QLIKE: 0.00985639646, descriptive 95% moving-block bootstrap interval [-0.05751080122862051, 0.08117237109864281].
LightGBM minus garch QLIKE: 0.0109102555, descriptive 95% moving-block bootstrap interval [-0.01409602989960537, 0.040432773392341234].

Lowest observed average QLIKE in this matched experiment: **rolling**. This is not an automatic champion decision or proof of predictive superiority.

## LightGBM selection and explanations
Validation search and selected configuration:
```json
{
  "objective": "L2 direct conditional second moment",
  "target_scale": 10000.0,
  "selected": {
    "num_leaves": 15,
    "iterations": 7,
    "validation_qlike": -8.313857978718222,
    "max_trees": 120,
    "early_stopping_rounds": 15,
    "training_rows": 284,
    "validation_rows": 60
  },
  "search_history": [
    {
      "num_leaves": 7,
      "iterations": 1,
      "validation_qlike": -8.311131118237078,
      "max_trees": 120,
      "early_stopping_rounds": 15,
      "training_rows": 284,
      "validation_rows": 60
    },
    {
      "num_leaves": 15,
      "iterations": 7,
      "validation_qlike": -8.313857978718222,
      "max_trees": 120,
      "early_stopping_rounds": 15,
      "training_rows": 284,
      "validation_rows": 60
    },
    {
      "num_leaves": 31,
      "iterations": 7,
      "validation_qlike": -8.313857978718222,
      "max_trees": 120,
      "early_stopping_rounds": 15,
      "training_rows": 284,
      "validation_rows": 60
    }
  ],
  "feature_set": "full"
}
```
Final-refit gain importance and saved-prediction TreeSHAP explanations are available through the private model API/dashboard. They explain fitted predictions, not causal market drivers. Drift references the first test refit's training distribution and never retunes the model.

## Limitations and conclusions
Synthetic experiments demonstrate software/protocol behavior, not predictive evidence for real markets.
Synthetic data cannot answer whether ML improves real-market risk. These results demonstrate an executed, controlled research process; real-market conclusions require permitted point-in-time data, larger independent evaluation periods and repeated regime-stability assessment.
Gaussian innovations, noisy squared-return targets, current-universe survivorship bias, availability/calendar assertions, finite samples and repeated research selection remain material risks. No live trading or investment recommendation is implemented.

## Reproducibility
Complete request parameters:
```json
{
  "mode": "demo",
  "dataset_id": null,
  "context_dataset_id": null,
  "benchmark_instrument": null,
  "scheme": "expanding",
  "history_window": 1260,
  "initial_train": 240,
  "validation_size": 60,
  "test_size": 100,
  "refit_every": 20,
  "rolling_train_window": 252,
  "rolling_window": 60,
  "ewma_lambda": 0.94,
  "variance_floor": 1e-12,
  "seed": 42,
  "max_trees": 120,
  "search_candidates": 3,
  "learning_rate": 0.05,
  "feature_set": "full",
  "coverage_minimum": 100
}
```
Input data `0c6494700501bc8f8d5c96f9f0a67a7ead6e8c7824699ac041e83ee3cfac8ed7`; feature version `daily-close-features-1.0.0`; runtime:
```json
{
  "python": "3.12.14",
  "platform": "macOS-26.5-arm64-arm-64bit",
  "git_commit": "b971c18d53b8b1d15367650fc7851b8d8694e731",
  "numpy": "2.5.4",
  "pandas": "3.1.0",
  "scipy": "1.18.1",
  "arch": "8.0.0",
  "lightgbm": "4.7.0",
  "model_version": "volatility-research-3.0.0",
  "feature_version": "daily-close-features-1.0.0"
}
```
Run `backend/.venv/bin/python backend/scripts/research_report.py` after installing locked dependencies and applying migration 0003. The script runs the default synthetic protocol and writes this report from actual saved results. Model text/JSON artifacts and checksum manifests live outside database rows in the private configured artifact directory.
Owner-authorized experiment reproduction uses immutable saved inputs, fixed seeds and locked configurations; output tolerances are rtol=1e-8 and atol=1e-14 for decimal variance, with failures/nulls preserved. Exact booster reload predictions are tested separately. Execution timings and platform-specific optimizer details are not deterministic scientific metrics.
