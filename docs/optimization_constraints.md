# Optimization policies and infeasibility

All weights/limits are decimal fractions in the API and advanced JSON fields; scalar UI controls label percentages explicitly. Unknown keys and nonfinite values are rejected. Constraints are the user's selected policy, not inferred financial suitability.

| Policy | Behavior |
| --- | --- |
| Global position min/max | Apply to every held asset; min defaults 0, max .20. Validate ordered bounds and aggregate capacity. |
| Asset min/max | Exact held instrument keys; intersect global limits. Cannot introduce securities. |
| Frozen | Exact held keys, pinned to current weight within recorded numerical tolerance; conflicting caps remain infeasible. |
| Sector min/max | Existing exact sector strings, all holdings retained. Multiple groups supported. |
| Global sector cap | Optional; intersects specific sector caps, never weakens them. |
| Unknown sectors | Retain explicit Unknown group by default or reject the universe by explicit policy. No invented classifications. |
| Maximum turnover | `.5*sum(abs(delta weights))`, defaults .15; null means explicitly unconstrained. Zero preserves current weights and can conflict with position caps. |
| Target risk | Annual volatility cap for objective D; below the achievable constrained minimum remains infeasible. |
| Target expected return | Objective E only with complete sourced annual assumptions; unreachable targets remain infeasible. |

Example body for `POST /api/v1/optimization/run` (Demo Mode; exact keys are from its synthetic universe):

```json
{
  "mode": "demo", "window": 252, "confidence": 0.95, "shrinkage": 0.1,
  "objective": "risk_cost", "lambda_cost": 1,
  "constraints": {
    "max_weight": 0.2, "max_turnover": 0.15,
    "sector_max": {"Technology": 0.18},
    "asset_min": {"NSE:HELIX": 0.05},
    "frozen": [], "unknown_sector_policy": "retain"
  },
  "costs": {"proportional_rate": 0.001, "buy_rates": {}, "sell_rates": {}}
}
```

This example defines assumptions, not a claim of feasibility or a recommendation. Retrieve the actual current universe/coverage from the authorized portfolio and result. A frozen holding above a maximum cannot be repaired without the user choosing different constraints. With six assets, a 10% global cap cannot invest 100%. A 20% cap with zero turnover is infeasible when any current holding exceeds 20%.

Constraint evidence records original lower/upper/value/violation, group, units, binding flag and upper-bound utilization where meaningful. A binding cap is a policy boundary, not evidence that a security is undesirable. Near-zero bounds can have null utilization. No alternative settings are silently solved/presented as the requested allocation. Deliberately selected frontier/sensitivity variations label every policy change.

The assistant accepts no model-supplied constraint arguments. Explicit new-calculation parameters or selected saved runs are server-pinned; parsed percentages must agree. Requests for unparsed sector/frozen policies require selection in the laboratory. Relax/ignore/override requests are refused. Following a failed optimization tool, the workflow stops without borrowing a previous successful allocation.
