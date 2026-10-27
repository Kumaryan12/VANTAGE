# Portfolio optimization methodology

Version `equity-sleeve-optimization-5.0.0`. The financial authority is `backend/app/optimization`, with Phase 2 risk functions reused for comparisons. This is a held INR cash-equity sleeve, not a whole-account allocation. Its fixed notional is the sum of eligible holdings. Unavailable cash is unknown/excluded, never assumed zero. Derivatives, financing, taxes, lot sizes, liquidity, impact and execution are outside scope. No new securities or silent holding exclusions are allowed. Continuous virtual units support research only.

## Data and covariance

Capture the authorized portfolio/as-of and up to 1,261 approved adjusted price observations. Require every held instrument in exact order, matching real/synthetic mode and currency, split/dividend adjustment, finite positive prices, freshness and no future observations. Require the complete requested estimation window plus its preceding price and the Phase 2 confidence-dependent minimum sample. No alignment/filling or real-to-demo fallback. Source permission, adjustment and common-date exchange-calendar continuity remain importer/provider assertions.

Canonical row-major float64 daily simple returns enter the existing sample ddof=1 covariance estimator. Explicit identity shrinkage is `Σ=(1-α)Σ_sample+α tr(Σ_sample)/n I`. Symmetry, eigenvalues, rank, condition number and every correction are retained. Singular PSD covariance is valid and can yield nonunique unstable allocations. Material indefiniteness is rejected. The matrix, ordered instruments, window and shrinkage are hashed. Completed run metadata uses the matrix actually evaluated by its worker, rather than preliminary validation metadata.

## Objectives and units

Let `w0` be current decimal sleeve weights, `w` proposed weights, `V` INR notional and `A=252*w'Σ_daily*w` annual decimal-return variance. Every problem requires `sum(w)=1`, `w>=0` and all selected bounds. Volatility is `sqrt(A)`.

- A: minimize `A`.
- B: minimize `A + λ_turnover * T`, where `T=.5*sum(abs(w-w0))` is one-way turnover.
- C: minimize `A + λ_cost * C/V`, with cost fraction below.
- D: minimize `A` subject also to `A<=target_annual_volatility²`. An unattainable target remains infeasible.
- E: minimize `A` subject also to `μ'w>=target_annual_return`. `μ` is a complete explicitly user-supplied annual arithmetic return-assumption vector with written source; it is never fabricated from Phase 3 volatility forecasts. This is conditional mean-variance research, not a return forecast.

Coefficients apply in these stated annual-variance/fraction units. For numerical conditioning the **whole objective** is divided by positive `max(tr(252Σ)/n,1e-12)`, preserving its minimizer and relative penalties. The scale and unscaled reconstructed objective are recorded. INR costs are never directly added to variance. Large coefficients can keep allocations near current weights; no universal economically correct coefficient is claimed.

Default symmetric research rate is .001 (10 bps) per gross value change. Asset-specific symmetric rates override it; explicit buy/sell rates override each side. `C=V*Σ(c_buy,i*max(w_i-w0_i,0)+c_sell,i*max(w0_i-w_i,0))`. Symmetric rates give `V*Σ c_i*abs(delta_i)`. Gross changes are `2T`; gross notional is `2VT`, one-way notional `VT`. Costs remain separate from the fixed risk notional. These are estimates from assumptions, not verified broker fees or impact forecasts.

## Solver and verification

CVXPY uses CLARABEL, one solver thread, default 300 iterations, 3-second solver time limit and `1e-9` absolute/relative gap and feasibility tolerances. Validated controls bound these settings. A common-positive objective scaling is recorded. No fallback solver or automatic policy relaxation is used. See [CVXPY solvers](https://www.cvxpy.org/tutorial/solvers/) and [CLARABEL settings](https://clarabel.org/stable/api_settings/).

Record reported termination status, dependency versions, iterations, solver/wall time, settings and actual outcome. Distinguish optimal, optimal_inaccurate, infeasible, unbounded, timeout, iteration_limit, solver_failure and validation_failed. Invalid inputs are typed errors before solving. Inaccurate feasibility is never presented as exact optimality. Infeasible/failed outcomes have null proposed weights and risk metrics, while current risk can remain available.

Independently reconstruct budget, nonnegativity, every global/asset/frozen/sector bound, turnover and selected risk/return targets. Acceptance tolerance is `1e-7` in each residual's explicitly recorded units (weights/turnover, annual variance or annual return). Raw and canonical weights are checked. Tiny negative-roundoff clipping/sum normalization is permitted only within `1e-8` maximum change, recorded and followed by all original checks. Independent objective/cost/turnover calculations must agree; precision is not financial forecast confidence.

Necessary prechecks identify bound capacity, frozen conflicts, sector capacity and minimum required turnover. Joint infeasibility may have no unique conflicting group; no irreducible infeasible-set claim is made. A separately labeled diagnostic can omit only the turnover cap to measure necessary turnover, or omit only the target-risk cap to measure the constrained minimum risk. Diagnostic allocations are never published as feasible for the original policy.

## Comparisons and studies

Current/proposed risk uses the same notional/as-of, ordered returns, window, confidence, covariance and seeded Gaussian simulation. Existing fractional empirical ES, Gaussian VaR/ES, Monte Carlo, signed Euler attribution and stress engines supply every financial value. Historical/parametric/simulated losses are one-day INR; volatility is annualized by sqrt(252). Gaussian daily means are historical sample means, distinct from optional annual expected-return assumptions. Monte Carlo sampling intervals and impossible unbounded-tail draw counts remain in exported diagnostics. Minimized variance need not reduce VaR, ES or every scenario loss.

The default risk–turnover curve solves actual minima at explicitly labeled budgets (0%, 5%, 10%, 15%, 25%). It is not a risk–return frontier. A conditional return frontier requires complete sourced `μ` and requested return targets. Infeasible points have null values and are not connected through on the chart. Sensitivity varies window, shrinkage, position cap, explicit sector cap, turnover and cost coefficient on captured inputs. A labeled cost-coefficient variation switches its objective to C. One-way allocation distance from the base is `.5*sum(abs(w_variation-w_base))`; unavailable baselines/results remain null. Large distances suggest instability, not statistical uncertainty intervals.

Identical direct shocks use Phase 2 security > sector > broad replacement, never summed overlapping shocks. Historical replay requires exact covered endpoints and fixed virtual adjusted-series units, no rebalancing. Retrospectively estimated optimized weights applied to an older scenario are not out-of-sample strategy performance. Synthetic series cannot stand for actual market events.
