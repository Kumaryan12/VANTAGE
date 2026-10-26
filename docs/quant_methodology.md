# Quantitative methodology — Phase 2, model version 2.0.1

## Financial conventions

All calculations run in Python/NumPy with float64 intermediates. Asset returns and covariance inputs are canonical row-major arrays, so CSV pivots and JSON-rehydrated frames cannot choose different BLAS reduction paths solely because their memory strides differ. Model patch 2.0.1 records this reproducibility correction. Currency is INR; cash-equity holdings are long-only, excluding cash, derivatives, margin funding, open positions, fees, taxes, and liquidity. The UI formats returned numbers and converts input percentage units only.

For quantity q_i and observed price P_i, position value V_i = q_i P_i, V = Σ V_i, and w_i = V_i/V. Sector capital exposure sums these weights; capital HHI is Σw_i². Risk estimates treat V and today's weights as the initial allocation for a future **one observed trading day**. They do not reconstruct past account holdings or trades. Kite price observation timestamps are unavailable: retrieval time and valuation date are retained without claiming prices were observed at that exact instant. Unknown sectors remain Unknown.

Use daily split/dividend-adjusted simple returns r_i,t = P_i,t/P_i,t−1 − 1, and portfolio scenarios r_p,t = Σw_i r_i,t. All assets must share exactly the same unique daily dates; no forward fill, resampling, venue substitution, currency conversion, or fabricated observations. Daily dates must be valid, midnight, timezone-free observations. Source calendars must represent consecutive trading observations; common missing dates and exchange holidays cannot be independently certified by this phase. That limitation is recorded in validation metadata.

Current estimation history must end no more than seven calendar days before the snapshot, never after it. Retain the last W+1 prices for W requested returns; W ranges 60–1260. Available eligible history shorter than W is explicitly reported. Confidence α is 0.90–0.995. Require n ≥ max(60, ceil(1/(1−α))) with roundoff-safe integer evaluation, so at least one empirical tail observation exists. Flag effective tail mass n(1−α) < 20 as unstable, including the usual 252-day 99% estimate. A minimum is an eligibility rule, not a claim of precision.

Define **loss L = −V r_p**. Positive values mean loss; negative values mean gain. Both VaR and ES can be negative for an all-gain distribution; neither is silently floored at zero. API tail estimates explicitly carry INR and decimal-return units. No horizon scaling is offered. Annualized volatility alone uses sqrt(252), with sample ddof=1; means remain daily.

## Historical VaR and Expected Shortfall

For ascending losses L_(1)…L_(n), VaR_α = L_(ceil(nα)), the inverse empirical CDF (`inverted_cdf`), not an interpolated percentile.

For descending losses D_1 ≥ … ≥ D_n, let m=n(1−α), k=floor(m), f=m−k:

**ES_α = (Σ[j=1..k] D_j + f D_(k+1)) / m.**

Omit the fractional term if f=0. This integrates exactly the upper (1−α) probability mass. It handles ties, constant distributions, fractional cutoffs, and m<1. Conditional averaging over all L ≥ VaR is generally different for discrete samples and is not used.

Estimator illustration: losses 0…24 INR, α=.90, m=2.5 → VaR=22 INR and ES=(24+23+0.5×22)/2.5=23.2 INR. This short illustration does not meet the application’s production minimum. With eighteen losses of 1 and losses 2 and 4, α=.90 gives VaR=1 and ES=3, whereas averaging everything ≥ VaR would give 1.2.

The historical method preserves empirical tails and dependencies but cannot represent losses absent from its sample. Window and tail sample size materially affect the estimates; source survivorship/corporate-action quality remains relevant.

## Gaussian mean/covariance risk

The daily mean vector is the arithmetic sample mean. The sample covariance is S = Σ_t (r_t−r̄)(r_t−r̄)'/(n−1). Optional **user-selected** identity-target linear shrinkage uses Σ_λ=(1−λ)S+λτI, τ=trace(S)/d, 0≤λ≤1. This is a fixed-intensity regularizer, not a fitted Ledoit–Wolf estimator or an optimized financial model. Default λ=0. Historical VaR/ES continue using observed returns; Gaussian risk, simulation, and attribution use the same selected Σ_λ.

Record λ, target variance, method, and Frobenius change from S. Shrinkage can assign variance to a constant asset and changes correlations; the UI explains this. It improves conditioning without evidence that any λ improves out-of-sample calibration.

Covariance validation requires finite square input and symmetry within ε=1e−10×max(max|Σ_ij|, float64.tiny). Material asymmetry or eigenvalues below −ε are errors. Symmetrization and clipping tiny negative eigenvalues to zero are recorded, including count, tolerance, and correction Frobenius norm. Rank uses d×machine_epsilon×largest_eigenvalue. Condition number is null for numerical singularity; rank and singular flags disambiguate null. Condition numbers >1e8 trigger an ill-conditioning warning. No inverse is needed for these models; singularity is supported without forcing shrinkage.

For portfolio mean μ_p=w'μ and σ_p=sqrt(w'Σw), μ_L=−Vμ_p and σ_L=Vσ_p. Let z=Φ⁻¹(α), φ(z)=exp(−z²/2)/sqrt(2π):

- **Gaussian VaR = μ_L + σ_L z.**
- **Gaussian ES = μ_L + σ_L φ(z)/(1−α).**

When σ_p=0, both equal deterministic loss μ_L. Known analytical test: V=1,000,000 INR, μ_p=.001, σ_p=.02, α=.95 gives VaR=31,897.072539 INR and ES=40,254.256150 INR. Tests also cover perfectly correlated, uncorrelated, zero-volatility, singular, concentrated, and negatively correlated assets.

Gaussian tails are thin and unbounded; historical means/covariance are uncertain and regime-sensitive. These outputs are unconditional fitted-model estimates, not predictive superiority claims.

## Correlated Monte Carlo and numerical uncertainty

Use the same fitted μ and full Σ as the analytical Gaussian. Spectral decomposition Σ=Q diag(λ)Q' gives A=Q diag(sqrt(max(λ,0))). Generate independent standard normal rows Z with NumPy `Generator(PCG64(seed))`, and R=μ+ZA'. This preserves cross-asset covariance, including singular matrices, without a failed-Cholesky fallback or independence assumption. Material indefiniteness is rejected; recorded roundoff corrections follow the covariance policy above.

For each row: r_p=Rw, P&L=V r_p, terminal value=V+P&L, loss=−P&L. Monte Carlo VaR and ES use the same empirical estimators as historical risk. Default 10,000 simulations; API range 2,000–100,000, seed 0–2³²−1, and at most five million asset draws. One bounded advanced calculation runs per backend process; excess concurrent requests get a typed 503. This makes synchronous vectorized work practical without adding an unnecessary worker service.

Gaussian simple returns can fall below −100% and imply nonpositive values. Report counts and warnings; never clip or resample them because that changes the model. Persist a 60-bin histogram, tail-bin counts, P&L/return/value quantiles, and compact summary statistics. Full asset matrices and raw portfolio simulation draws are transient and never stored in database rows. Tail-bin coloring highlights bins containing P&L ≤ −VaR; a boundary bin can contain both tail and non-tail observations. ES still uses exact fractional mass.

For N draws and q=1−α, conditional asymptotic Monte Carlo standard errors are:

SE(VaR) = σ_L sqrt(αq/N)/φ(z).

SE(ES) = σ_L/sqrt(N) × sqrt( ((1+z²)q−zφ(z))/q² − (φ(z)/q−z)² ).

The ES expression follows the variance of the normal stop-loss influence function (L−VaR)_+/q. Report ±1.96 SE intervals as **sampling intervals conditional on the fitted Gaussian**, not future-return intervals or parameter-uncertainty bounds. Zero σ gives zero sampling error. Analytical-vs-Monte-Carlo tests use a deterministic seed, N=100,000, and a six-asymptotic-SE tolerance (scale-aware statistical tolerance; roughly a 2e−9 two-sided Gaussian exceedance rate under the asymptotic approximation). Separate exact reproducibility tests do not use a statistical tolerance.

## Volatility attribution and concentration

For nonzero σ_p, marginal daily volatility MRC_i=(Σw)_i/σ_p; component RC_i=w_i MRC_i; percentage RC_i/σ_p. Euler homogeneity implies ΣRC_i=σ_p. Store and display the daily reconciliation residual; aggregate sector components by direct summation; annualized components equal sqrt(252)×daily components. Negative components and percentages can be valid hedging effects and are retained. These are **volatility contributions, not VaR contributions**.

For exactly zero σ_p, component contributions are zero and marginal/percentage contributions are null (undefined). Capital HHI remains Σw². Positive-component risk HHI normalizes only max(RC_i,0) and sums squared positive shares; it is null with no positive components and deliberately excludes negative hedging terms. Correlation diagnostics use the selected covariance; zero-variance correlations are null. The legacy correlation chart continues to show the raw sample.

## Historical and synthetic scenario replay

Named scenarios specify **dates only**, never hardcoded shocks. Actual historical events require real mode and adjusted data covering all current holdings on exactly the selected start/end dates. Missing source coverage disables the scenario and explains why. No nearest-date endpoint substitution is allowed. A separate older imported scenario dataset may be selected; it need not satisfy current-estimation freshness, while any current VaR comparison must satisfy freshness independently.

Replay keeps today's initial allocation V_i but holds **virtual adjusted-series units** V_i/P_i,start fixed through the window (buy-and-hold, no rebalancing). Asset return = P_i,end/P_i,start−1; P&L_i=V_i×asset_return; portfolio P&L=ΣP&L_i and return=P&L/V. Dated scenario value path sums these fixed virtual units. This is current-allocation replay, not actual historical account performance or actual past share quantities. Adjusted ratios serve as total-return proxies, with no raw/adjusted price mixing. Sector P&L sums positions, and the residual is recorded.

Demo only offers a clearly labeled synthetic fixture replay. Actual pandemic/2022 windows are unavailable in Demo Mode. Contract tests may construct explicitly labeled synthetic fixtures to test real-mode mechanics; those tests do not verify actual historical market losses.

## Hypothetical direct scenarios

Users set broad, sector, or security simple-return shocks from −100% to +500%. **Security overrides sector, sector overrides broad, and replacement never adds overlapping shocks.** An unmapped asset inherits the broad shock if supplied, otherwise exactly zero (unchanged). Reject unknown instruments/sectors and empty scenarios. All holdings, including unchanged ones, expose the exact applied mapping.

Apply shocks to current values at fixed quantities: P&L_i=V_i s_i; value_after=ΣV_i(1+s_i). Aggregate P&L by sector and identify positive loss contributors. These are explicit what-if assumptions, not predictions or inferred beta/factor exposures. No regression-based multi-factor shocks are implemented without a validated exposure dataset. Security/sector overrides supply the explicit fallback required when factor exposures are unavailable.

Stress outputs may compare with separately eligible current one-day historical VaR/ES. Loss/VaR is null for nonpositive VaR. A multi-day replay and one-day VaR have different horizons: the ratio is descriptive, not a coverage probability or horizon-adjusted risk test. If reference history is missing/stale, stress can still run and explicitly report the unavailable comparison; unauthorized or corrupted datasets are errors, not partial success.

## Persistence and reproducibility

Migration 0002 retains legacy records and adds owner-scoped immutable portfolio snapshots and input artifacts. Store the exact valuation snapshot, dated selected estimation prices, scenario prices/reference prices when used, full original-source provenance/hash, normalized model parameters, version 2.0.1, calculation/retrieval/as-of timestamps, NumPy/Pandas/Python/platform versions, seed, simulation count, covariance policy/diagnostics, results, warnings, and validation metadata. Selected input-artifact hashes differ from full provider-history hashes because an estimation window is a subset.

Replaying uses saved snapshots and selected price inputs only: no current broker, provider, or fixture lookup. Verify snapshot, artifact, and parameter hashes first; reject unsupported model versions. A new run ID records the replay and compares outputs with the original. Same runtime/inputs/seed reproduce exact tested results; eigenvector/BLAS/platform differences can affect bitwise identity across machines. The comparison explicitly uses rtol=1e−12 and atol=1e−10 and reports a mismatch rather than overwriting history.

Run comparisons report backend-computed INR deltas and warn when snapshots, confidence, windows, samples, or scenario horizons differ. They are not a changes-in-risk causal decomposition. Legacy Phase 1 results remain retrievable but lack replay artifacts. Existing session authorization is preserved: private runs belong to the initiating active session; persistence does not yet provide identity recovery after restart/session expiry.

## Scientific interpretation and sources

Model output, Monte Carlo sampling noise, historical parameter uncertainty, model misspecification, and investment decisions are separate concepts. More simulations reduce sampling noise, not missing tails, estimation bias, incorrect source calendars, or structural model risk. Heavy-tailed returns can produce losses far beyond Gaussian VaR. Neither 99% VaR nor ES guarantees coverage or bounds maximum loss. No model superiority claim is made without out-of-sample validation; Phase 3 research below measures conditional forecasts with these limitations.

Primary references: [Acerbi & Tasche, On the coherence of Expected Shortfall](https://arxiv.org/abs/cond-mat/0104295) for the discrete/quantile-integral distinction; [NumPy multivariate normal documentation](https://numpy.org/doc/stable/reference/random/generated/numpy.random.Generator.multivariate_normal.html) for PSD requirements, spectral sampling and runtime reproducibility caveats; [normal PDF/CDF/quantile definitions](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.norm.html). This application does not claim Basel regulatory capital compliance.


## Phase 3 conditional volatility and VaR

The primary target is E[r(t+1)²|F(t)] under zero daily mean, with next observed simple return² as a noisy realized proxy. Rolling uses a zero-mean population second moment; EWMA uses explicitly initialized historical squared returns. Actual zero-mean Gaussian ARCH GARCH fits percent returns and rescales variance by 10,000. LightGBM fits squared percent returns directly, validates pre-test, freezes configuration/iterations and records explicit positive floors. No log-target retransformation is used.

Pure walk-forward execution permits only origin-available labels and training-only preprocessing, with expanding/rolling windows. Conditional VaR reuses `gaussian_risk` on directly predicted portfolio variance: positive INR loss quantile V*z(c)*sqrt(h), with loss=-V*r and strict exceptions. QLIKE log(h)+RV/h and MSE/MAE operate on variance over common valid test dates. Sparse Kupiec/Christoffersen/conditional coverage diagnostics, training-estimated regimes and paired descriptive block-bootstrap uncertainty are reported with their assumptions. Full mathematical/feature/window/edge-case definitions are in [research_protocol.md](research_protocol.md); measured outcomes appear in the [executed report](research/volatility_model_comparison.md). No synthetic experiment establishes real-market predictive superiority.
