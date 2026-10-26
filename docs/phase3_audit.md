# Phase 2 audit and Phase 3 implementation protocol

Audited 2026-10-26 at `0cf7dcf` before Phase 3 implementation. All 133 baseline tests and backend lint/format pass; frontend lint/type/build checks pass. Phase 2's inverse-ECDF VaR, fractional empirical ES, canonical float64 return construction, PSD validation, immutable inputs, owner checks, and Gaussian loss convention are reusable. Model version 2.0.1 remains unchanged.

## Relevant gaps

- There is no forecast-origin/label-availability dataset, walk-forward evaluator, statistical calibration service, model registry or training queue.
- Current frozen weights applied to past returns are retrospective scenarios, not a point-in-time holdings reconstruction. Research must preserve that distinction and document current-universe survivorship bias.
- Imported daily adjusted closes have source assertions about calendar continuity and availability; actual historical publication timestamps are not independently verified. No market observations or release dates may be invented.
- FRED/FX context must remain excluded from ML: vintage data alone does not establish release-time availability. Volume is not in the current validated source schema and must remain explicitly unavailable.
- Conditional portfolio variance can enter the existing `gaussian_risk` function as a one-dimensional covariance with zero mean and weight one. Do not aggregate independent asset forecasts.
- Existing sessions are ephemeral. Preserve ownership/auth mechanisms; models/experiments remain private to the originating active session, with durable identity/recovery still future work.

## Locked primary protocol

Target is next observed trading-day squared portfolio return, under an explicit zero-mean approximation; a single square is a noisy latent-variance proxy. Features at close t use data through t; the label belongs to (t,t+1] and becomes available at the next observation. No five-day overlapping target is implemented.

Rolling uses the historical second moment; EWMA uses documented historical initialization; Gaussian GARCH(1,1) uses ARCH with percent-return scaling; LightGBM predicts scaled squared returns directly with L2 loss, avoiding log-target retransformation bias. Positive floors are numerical safeguards and are counted.

The last configurable observations form the locked test period. A preceding chronological validation period selects a bounded LightGBM configuration and early-stopping iteration count. Final test labels never select hyperparameters or regime thresholds. Expanding/rolling prequential refits may use earlier test labels only after those labels become observable. All four models predict identical target dates; failures remain explicit and leaderboard metrics use the common valid intersection, reporting any exclusions.

Regimes use lagged trailing variance at each origin with thresholds fixed from pre-validation training. Conditional 95%/99% VaR uses Phase 2's positive-loss convention and fixed snapshot notional. Implement QLIKE on variance, MSE/MAE, Kupiec and Christoffersen diagnostics with small-sample/unidentified-transition guards. No automatic champion or predictive-superiority claim.

## Delivery sequence

1. Leakage-safe datasets, features and chronological split tests.
2. Four real forecasting implementations, bounded validation search and walk-forward evaluation.
3. Calibration metrics, regimes, matched challenger results, and actual model explanations.
4. Additive migrations, bounded background jobs, text/JSON model artifacts with checksums, private registry and reproducibility.
5. Typed research APIs and a working research terminal within the existing design.
6. Execute demo experiments and generate a Markdown report from those exact results; verify regression/API/browser/PostgreSQL/CI checks and document limits.

No Phase 4 agents, live execution, invented data, or unsupported model-ranking claims are authorized.
