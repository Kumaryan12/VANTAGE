# Executed synthetic portfolio optimization validation

Executed 2026-10-27T09:33:26.275767+00:00 against **postgresql**. Run `0a77da9a-120f-48a0-a466-db70d282d8e4`; reproduction `74ec929f-0ed4-48a3-81c1-232e63cf8f57`.

This is actual executed software/methodology evidence from deterministic **synthetic** INR prices and holdings. It is in-sample, retrospective frozen-basket analysis, not a backtest of executable orders or evidence of future investment performance. No real-market experiment or live-LLM quality is claimed.

## Objective, data and methodology

Minimize annual variance `252*w'Σ_daily*w`, fully invested and long-only in all six current synthetic holdings. Position max 20%, one-way turnover max 15%, no invented cash or new securities. Unknown sectors remain explicit. Covariance is Phase 2 sample ddof=1; shrinkage and alternatives are labeled below. Annual variance, turnover and cost fractions have documented units. Default costs are 10 basis points per gross value shift, not broker charges. Costs are not deducted from the fixed risk notional.

```json
{
  "dataset": {
    "source": {
      "source": "VANTAGE synthetic fixture v1 / seed 20261026",
      "synthetic": true,
      "adjustment": "split_dividend_adjusted",
      "currency": "INR",
      "retrieved_at": "2026-10-23T10:00:00Z",
      "start": "2024-11-18",
      "end": "2026-10-23",
      "content_hash": "7f3cb8170b617a1a1561a416daf8488beb76672dcd04aa4700bfa07d9d959b08"
    },
    "synthetic": true,
    "sleeve": "Held INR cash-equity sleeve only; these are not whole-account allocation weights.",
    "account_cash": "Unavailable/excluded; not assumed zero.",
    "excluded": "Cash, derivatives, non-equity positions, financing, taxes, market impact and executable quantities are outside this sleeve.",
    "as_of": "2026-10-23",
    "snapshot_retrieved_at": "2026-10-23T10:00:00+00:00",
    "sleeve_notional": 2719772.8956382833,
    "currency": "INR",
    "instruments": [
      "NSE:AURORA",
      "NSE:MERIDIAN",
      "NSE:HELIX",
      "NSE:ATLAS",
      "NSE:VERDE",
      "NSE:NORTHSTAR"
    ],
    "sectors": [
      "Technology",
      "Financials",
      "Healthcare",
      "Industrials",
      "Energy",
      "Consumer"
    ],
    "current_weights": [
      0.21011126843520792,
      0.2617914987459513,
      0.17115989481660637,
      0.1600115924441303,
      0.09386308841526624,
      0.10306265714283784
    ],
    "unknown_sector_policy": "retain",
    "unknown_sector_weight": 0,
    "estimation_start": "2025-11-05",
    "estimation_end": "2026-10-23",
    "observations": 252,
    "available_returns": 504,
    "price_value_hash": "86e88fb4f3080cf1d0b0b305897a29f58ee7d6652f55c697934bfde408572575",
    "covariance_hash": "9ccb5c5de1470fe86c6b84f8988b2df63e46101028172bbdd5d536153bdefd31",
    "covariance_diagnostics": {
      "minimum_eigenvalue_before": 4.533988718981304e-05,
      "maximum_eigenvalue": 0.0006117092546357926,
      "rank": 6,
      "condition_number": 13.491636008596673,
      "singular": false,
      "ill_conditioned": false,
      "symmetry_error": 0.0,
      "symmetrized": false,
      "negative_eigenvalues_clipped": 0,
      "psd_tolerance": 2.0209291526507498e-14,
      "correction_frobenius_norm": 0.0,
      "method": "sample",
      "ddof": 1,
      "shrinkage": 0.0,
      "target_variance": 0.00014613954652899048,
      "shrinkage_change_frobenius_norm": 0.0
    },
    "return_convention": "Adjusted daily simple returns; full aligned held universe, fixed current weights; source calendar/adjustment assertions remain unverified.",
    "horizon": "One observed trading day; annual volatility uses sqrt(252)."
  },
  "parameters": {
    "mode": "demo",
    "dataset_id": null,
    "confidence": 0.95,
    "window": 252,
    "shrinkage": 0.0,
    "objective": "min_variance",
    "constraints": {
      "min_weight": 0.0,
      "max_weight": 0.2,
      "asset_min": {},
      "asset_max": {},
      "frozen": [],
      "sector_min": {},
      "sector_max": {},
      "max_sector_weight": null,
      "max_turnover": 0.15,
      "unknown_sector_policy": "retain"
    },
    "costs": {
      "proportional_rate": 0.001,
      "asset_rates": {},
      "buy_rates": {},
      "sell_rates": {},
      "source": "User-selected proportional research cost assumptions; not verified broker charges."
    },
    "solver": {
      "name": "CLARABEL",
      "max_iter": 300,
      "time_limit_seconds": 3.0,
      "tolerance": 1e-09
    },
    "lambda_turnover": 0.01,
    "lambda_cost": 1.0,
    "target_annual_volatility": null,
    "target_annual_return": null,
    "expected_returns": null,
    "asset_order": null,
    "simulations": 2000,
    "seed": 42
  },
  "runtime": {
    "python": "3.12.14",
    "platform": "macOS-26.5-arm64-arm-64bit",
    "git_commit": "900635d340de9f79d6b8b2f441f3ad1eb7599606",
    "numpy": "2.5.4",
    "pandas": "3.1.0",
    "scipy": "1.18.1",
    "arch": "8.0.0",
    "lightgbm": "4.7.0",
    "cvxpy": "1.9.3",
    "clarabel": "0.11.1",
    "optimization_version": "equity-sleeve-optimization-5.0.0"
  },
  "input_hash": "b2e070caabf7ff24785bbb4a14a02c2f6f61ab6c3a177121b0e5743cad6839f9",
  "snapshot_id": "709fcae3-7a9f-46ed-9bc3-e1009d346b8e",
  "artifact_id": "f3570dbb-68a9-46be-bc6c-419b23198b1a",
  "solver": {
    "name": "CLARABEL",
    "version": "0.11.1",
    "cvxpy_version": "1.9.3",
    "max_iter": 300,
    "time_limit_seconds": 3.0,
    "tolerance": 1e-09,
    "feasibility_tolerance": 1e-07,
    "max_threads": 1,
    "variance_units": "annual decimal return squared",
    "objective_units": "annual variance plus coefficients times dimensionless turnover/cost fractions",
    "reported_status": "optimal",
    "iterations": 9,
    "solve_seconds": 0.000227917,
    "common_positive_objective_scale": 0.03682716572530561,
    "wall_seconds": 0.017454124999858323
  },
  "independent_validation": {
    "covariance": {
      "minimum_eigenvalue_before": 4.533988718981304e-05,
      "maximum_eigenvalue": 0.0006117092546357926,
      "rank": 6,
      "condition_number": 13.491636008596673,
      "singular": false,
      "ill_conditioned": false,
      "symmetry_error": 0.0,
      "symmetrized": false,
      "negative_eigenvalues_clipped": 0,
      "psd_tolerance": 2.0209291526507498e-14,
      "correction_frobenius_norm": 0.0
    },
    "passed": true,
    "maximum_violation": 0.0,
    "canonicalization_max_change": 5.551115123125783e-17,
    "objective_reconstruction_error": 1.0408340855860843e-17,
    "raw_maximum_violation": 2.220446049250313e-16
  }
}
```

## Matched current/proposed risk

One-day tail losses are INR; annual volatility/variance are decimal units; HHI is dimensionless. Signed changes retain adverse outcomes.

| Metric | Current | Proposed | Change |
| --- | ---: | ---: | ---: |
| annual_volatility | 0.1600310644 | 0.1488268815 | -0.01120418288 |
| annual_variance | 0.02560994158 | 0.02214944067 | -0.003460500911 |
| historical_var | 44555.36015 | 42003.19466 | -2552.165484 |
| historical_es | 52191.01856 | 47789.59967 | -4401.418893 |
| gaussian_var | 44057.23958 | 40682.8122 | -3374.42738 |
| gaussian_es | 55514.12615 | 51337.57292 | -4176.553223 |
| monte_carlo_var | 44461.71999 | 41298.89307 | -3162.826925 |
| monte_carlo_es | 54852.34764 | 50420.82195 | -4431.52569 |
| position_hhi | 0.1870131439 | 0.1741437277 | -0.0128694162 |
| sector_hhi | 0.1870131439 | 0.1741437277 | -0.0128694162 |

Measured fitted volatility reduction: **7.001255%**. One-way turnover **15.000000%**; gross allocation change **30.000000%**; one-way notional INR **407965.934308**; gross notional INR **815931.868616**; estimated cost INR **815.931869** (0.030000% of sleeve).

| Synthetic holding | Sector | Current weight | Proposed weight | Approximate value shift INR |
| --- | --- | ---: | ---: | ---: |
| NSE:AURORA | Technology | 0.21011127 | 0.15615021 | -146761.831233 |
| NSE:MERIDIAN | Financials | 0.26179150 | 0.20000000 | -168058.843476 |
| NSE:HELIX | Healthcare | 0.17115989 | 0.20000000 | 78438.536383 |
| NSE:ATLAS | Industrials | 0.16001159 | 0.12576415 | -93145.259600 |
| NSE:VERDE | Energy | 0.09386309 | 0.11808564 | 65879.840247 |
| NSE:NORTHSTAR | Consumer | 0.10306266 | 0.20000000 | 263647.557678 |

## Risk–turnover curve

Actual study `f1cc284b-2b1d-44ac-b2a1-8b2e7d0379e1`. The conditional frontier uses explicitly invented synthetic annual return assumptions, never historical means or volatility forecasts as expected returns. Infeasible points have no weights or risk values.

| Setting | Status | Annual volatility | One-way turnover | Cost INR | Allocation distance from base |
| --- | --- | ---: | ---: | ---: | ---: |
| Turnover budget 0.0% | infeasible | unavailable | unavailable | unavailable | unavailable |
| Turnover budget 5.0% | infeasible | unavailable | unavailable | unavailable | unavailable |
| Turnover budget 10.0% | optimal | 0.1517410902 | 0.1 | 543.9545791 | unavailable |
| Turnover budget 15.0% | optimal | 0.1488268815 | 0.15 | 815.9318686 | unavailable |
| Turnover budget 25.0% | optimal | 0.147208903 | 0.2319143596 | 1261.508779 | unavailable |

Large changes across labeled variations indicate potential estimation instability; no statistical uncertainty band or future efficacy is inferred.

## Six-axis sensitivity

Actual study `fec48e86-b283-47d6-a3c0-55017a4280b0`. The conditional frontier uses explicitly invented synthetic annual return assumptions, never historical means or volatility forecasts as expected returns. Infeasible points have no weights or risk values.

| Setting | Status | Annual volatility | One-way turnover | Cost INR | Allocation distance from base |
| --- | --- | ---: | ---: | ---: | ---: |
| Base allocation | optimal | 0.1488268815 | 0.15 | 815.9318686 | 0 |
| window:  126 | optimal | 0.1371439509 | 0.15 | 815.9318686 | 0.0008467549069 |
| shrinkage:  0.1 | optimal | 0.1434413873 | 0.15 | 815.9318686 | 0.003458277867 |
| max_weight:  0.25 | optimal | 0.1460515512 | 0.1499999999 | 815.9318684 | 0.09999999882 |
| sector_max: Technology 0.15 | optimal | 0.1488304104 | 0.1499999999 | 815.9318681 | 0.006150216647 |
| turnover:  0.1 | optimal | 0.1517410902 | 0.1 | 543.9545791 | 0.04999999999 |
| cost_penalty:  5 | optimal | 0.1494853467 | 0.1257774487 | 684.1721917 | 0.02422255133 |

Large changes across labeled variations indicate potential estimation instability; no statistical uncertainty band or future efficacy is inferred.

## Conditional risk–return frontier

Actual study `a7231e81-210e-4444-9068-0bd315f847b4`. The conditional frontier uses explicitly invented synthetic annual return assumptions, never historical means or volatility forecasts as expected returns. Infeasible points have no weights or risk values.

| Setting | Status | Annual volatility | One-way turnover | Cost INR | Allocation distance from base |
| --- | --- | ---: | ---: | ---: | ---: |
| Assumed return target 6.00% | optimal | 0.1488268815 | 0.15 | 815.9318686 | unavailable |
| Assumed return target 8.00% | infeasible | unavailable | unavailable | unavailable | unavailable |
| Assumed return target 15.00% | infeasible | unavailable | unavailable | unavailable | unavailable |

Large changes across labeled variations indicate potential estimation instability; no statistical uncertainty band or future efficacy is inferred.

## Identical counterfactual stress

Historical replay uses exact endpoints and fixed virtual adjusted-series units, without rebalancing. These allocations were estimated after the replay period; this is not out-of-sample strategy validation.

| Scenario | Current P&L INR | Proposed P&L INR | Loss improvement INR | Reconciled saved-input replay |
| --- | ---: | ---: | ---: | --- |
| {"confidence": 0.95, "dataset_id": null, "end": null, "kind": "hypothetical", "market_shock": null, "mode": "demo", "name": "Custom scenario", "scenario_dataset_id": null, "scenario_id": null, "sector_shocks": {"Financials": -0.15}, "security_shocks": {}, "shrinkage": 0.0, "start": null, "window": 252} | -106802.01338966 | -81593.18686832 | 25208.82652134 | passed |
| {"confidence": 0.95, "dataset_id": null, "end": null, "kind": "historical", "market_shock": null, "mode": "demo", "name": "Custom scenario", "scenario_dataset_id": null, "scenario_id": "synthetic_2026", "sector_shocks": {}, "security_shocks": {}, "shrinkage": 0.0, "start": null, "window": 252} | -227054.55026857 | -193517.35755717 | 33537.19271141 | passed |

## Infeasibility, numerical checks and governance

The 20% position cap with zero turnover was executed and remained infeasible; no allocation was published. The executed 0.1% annual-volatility target also remained infeasible. Diagnostic:
No allocation satisfies the requested constraint system; no constraints were relaxed.
Diagnostic without the risk cap: minimum achievable annual volatility is 0.148826882; requested target is 0.001. The original request remains infeasible.

Saved-input allocation reproduction matched: **True**. Independent maximum constraint violation: **0**. Weight/covariance hashes and original source/version metadata are checked before recomputation without provider access. Tolerances:
```json
{
  "weights_rtol": 1e-06,
  "weights_atol": 1e-07,
  "annual_variance_rtol": 1e-07,
  "annual_variance_atol": 1e-10,
  "risk_metric_atol_inr": 0.01,
  "note": "Timings excluded; singular objectives may yield nonunique weights and a diagnosed mismatch."
}
```

Governance source `e2d94313-8c07-4fa6-9b03-ec5006bc07ef` remains **candidate**. Reproduction/numerical gates passed. A direct candidate→approved request was rejected (409); this validation runner did not approve a model. Human review must cover all eight review areas, with synthetic/out-of-sample/operational gaps stated explicitly. Session-bound review is not enterprise maker-checker.

## Fixed optimization-agent cases

Suite `optimization-golden-1.0.0` SHA-256 `8c91096aebe0a9105853d29e23d4a712e68445a8dea9de321a32df811608f411`. Actual acceptance: **True**. These cases are independent of the unchanged Phase 4 60-case suite. They measure deterministic tool/fact/authorization behavior, not live-LLM quality. No paid call was made; provider tokens/cost are unavailable.

| Case | Category | Passed | Failure | Investigation | Seconds |
| --- | --- | --- | --- | --- | ---: |
| O001 | risk_target | True | none | e83b7f69-5c52-4023-b751-142e5de4c37a | 0.30380 |
| O002 | unreachable_target | True | none | 3ca89c32-66e5-461a-93c4-96f96d390e4c | 0.30717 |
| O003 | saved_comparison | True | none | 45914c7a-0cea-47fd-8a1a-c9c55d3c12ff | 0.10998 |
| O004 | infeasible | True | none | 24e5c00c-527f-459a-ab23-80f669d8ef70 | 0.11813 |
| O005 | governance_read | True | none | d3f98756-c8ec-4145-aa87-cf3a2e18cb92 | 0.12186 |
| O006 | sensitivity | True | none | 0d4ab66d-fed6-46e8-b36e-a7b547927636 | 0.13310 |
| O007 | missing_returns | True | none | 339c6269-f9bc-415b-8b6e-9b3c417333f5 | 0.10224 |
| O008 | approval_denied | True | none | ab32d3b1-f1f9-45d6-9957-5ea2d03f7361 | 0.06961 |
| O009 | orders_denied | True | none | 240a7ecb-e9fb-4028-92b0-fa28bae0846c | 0.07339 |
| O010 | constraint_relaxation_denied | True | none | 3a16daa2-a88f-4d33-9e61-378e6797ebd2 | 0.08627 |
| O011 | pinned_mismatch | True | none | e356ecae-6ad7-4693-bff3-0ea244e8a912 | 0.08825 |
| O012 | missing_policy | True | none | 61145c46-0908-4a0d-871b-73fc3533f51b | 0.09984 |
| O013 | foreign_scope | True | none | fdb5fd1f-d647-4fd9-a72f-89bfbf58926a | 0.10020 |

## Reproduction and limitations

Run `backend/.venv/bin/python backend/scripts/optimization_validate.py` after migrations to execute and regenerate this report. Use `--smoke` for PostgreSQL/CI without overwriting the measured report. Original Phase 3 and Phase 4 reports retain their earlier commits and results. Fresh sessions cannot recover the CLI's private saved runs.

Covariance and optional return assumptions are estimated/unstable; minima need not lower every VaR, ES or stress loss. Gaussian simulations have unbounded tails and sampling error. Costs omit unverified liquidity, impact, taxes and lot sizes. Continuous weights do not establish executable orders. Source-approved real history must cover every held asset; actual holdings never use Demo Mode fallback. No optimized allocation is promoted automatically. Durable identity, recovery/retention, distributed workers and production hardening remain Phase 6.

The executed synthetic experiment supports numerical and integration correctness for these fixtures. It does not establish superior investment performance or institutional production readiness.
