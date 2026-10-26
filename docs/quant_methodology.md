# Quantitative methodology v1

All risk is computed in Python with simple decimal returns, float64 arithmetic, and unrounded intermediate values. The UI formats output only. Phase 1 covers long-only cash-equity holdings in INR, excluding cash balances, derivatives, leverage, taxes, fees, and realized trading cash flows.

## Snapshot and alignment

For quantity q_i and last observed price P_i: V_i = q_i P_i; total V = Σ V_i; current weight w_i = V_i/V. Sector exposure is the sum of constituent weights. Concentration HHI = Σ w_i²; largest position is max(w_i). Kite quantities include settled plus T1 holdings less used quantities; negative normalized holdings are rejected. Positions are exposed separately and are explicitly excluded from holding-portfolio risk.

Every held instrument must have the same strictly increasing, unique sequence of daily dates. No missing values or fill is allowed. Require at least 61 prices (60 daily returns); at 99% require at least 100 returns. Analysis dates cannot exceed the snapshot valuation date, and the last history observation must be within seven calendar days of the snapshot. All historical data must be split/dividend adjusted; metadata is an importer assertion for user uploads. No currency conversion is performed.

## Historical scenarios for today's portfolio

r_i,t = P_i,t / P_i,t−1 − 1. Scenario portfolio return r_p,t = Σ w_i r_i,t. These are constant-current-weight historical scenarios, **not the actual historical performance of the account**. The normalized scenario index is I_0 = 100; I_t = 100 ∏(1+r_p,t). The UI labels this distinction. No daily rebalancing/trading is actually executed.

Daily covariance uses sample ddof=1. Annualized volatility σ_ann = sqrt(252) × sample_std(r_p). Security covariance and correlation matrices use identically aligned returns. Undefined correlations for zero-variance assets are returned as null.

Historical loss L_t = −r_p,t. VaR_c is the inverse empirical CDF: sort ascending losses and select order ceil(c n) (NumPy `method="inverted_cdf"`). Monetary VaR = V × VaR_c. Positive values indicate loss; negative VaR is possible for an all-gain sample and is not silently clamped. Horizon is exactly one observed trading day; no square-root-of-time horizon scaling is offered. Defaults: 95% confidence and 252 return observations (or explicit smaller eligible window). All outputs include confidence, horizon, sample size, dates, sign convention, and methodology version.

Drawdown D_t = I_t / max(I_0… I_t) − 1. Maximum drawdown is −min(D_t), including the initial wealth baseline. Rolling volatility uses 21 returns, ddof=1, and sqrt(252); insufficient early values are null.

## Limitations

Historical simulation assumes past return scenarios inform future risk; it does not model liquidity, structural breaks, intraday gaps, execution costs, or guarantee coverage. VaR is not maximum possible loss. A small empirical tail is unstable; tail sample mass is displayed. Snapshot last prices may be stale and retrieval time is not price observation time. Unknown Kite sector classifications are shown as Unknown. Sharpe/Sortino/beta, Expected Shortfall, attribution, stress, optimization, and forecasting are future work; no numerical claims are made for them.
