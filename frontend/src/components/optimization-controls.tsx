"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Play, SlidersHorizontal } from "lucide-react";
import { api } from "@/lib/api";
import type { RiskSelection } from "@/lib/advanced-risk";

type PortfolioUniverse = {
  holdings: { instrument: string; sector: string; name: string }[];
};
export function OptimizationControls({
  selection,
  disabled,
  submit,
}: {
  selection: RiskSelection;
  disabled: boolean;
  submit: (path: string, body: Record<string, unknown>) => void;
}) {
  const [maximum, setMaximum] = useState("20");
  const [minimum, setMinimum] = useState("0");
  const [turnover, setTurnover] = useState("15");
  const [sectorCap, setSectorCap] = useState("");
  const [window, setWindow] = useState(String(selection.window));
  const [shrinkage, setShrinkage] = useState("0");
  const [objective, setObjective] = useState("min_variance");
  const [coefficient, setCoefficient] = useState("1");
  const [target, setTarget] = useState("10");
  const [rate, setRate] = useState("0.10");
  const [bounds, setBounds] = useState(
    '{"asset_min": {}, "asset_max": {}, "frozen": [], "sector_min": {}, "sector_max": {}, "unknown_sector_policy": "retain"}',
  );
  const [costs, setCosts] = useState(
    '{"asset_rates": {}, "buy_rates": {}, "sell_rates": {}}',
  );
  const [returns, setReturns] = useState("");
  const [source, setSource] = useState("");
  const [budgets, setBudgets] = useState("0, 5, 10, 15, 25");
  const [targets, setTargets] = useState("5, 8, 10");
  const [variations, setVariations] = useState(
    '[{"kind":"window","value":126},{"kind":"shrinkage","value":0.1},{"kind":"max_weight","value":0.25},{"kind":"turnover","value":0.1},{"kind":"cost_penalty","value":5}]',
  );
  const [error, setError] = useState("");
  const universe = useQuery({
    queryKey: ["optimization-universe", selection.mode],
    queryFn: () => api<PortfolioUniverse>(`/portfolio?mode=${selection.mode}`),
    enabled: !disabled,
  });
  function calculate(kind: string) {
    try {
      setError("");
      const extra = JSON.parse(bounds);
      const extraCosts = JSON.parse(costs);
      if (
        !extra ||
        Array.isArray(extra) ||
        typeof extra !== "object" ||
        !extraCosts ||
        Array.isArray(extraCosts) ||
        typeof extraCosts !== "object"
      )
        throw Error("Policy inputs must be JSON objects.");
      // Reject collisions so every visible scalar control has one unambiguous source.
      if (
        Object.keys(extra).some(
          (k) =>
            ![
              "asset_min",
              "asset_max",
              "frozen",
              "sector_min",
              "sector_max",
              "unknown_sector_policy",
            ].includes(k),
        )
      )
        throw Error(
          "Use the scalar controls for global limits; advanced policy keys are listed below.",
        );
      if (
        Object.keys(extraCosts).some(
          (k) => !["asset_rates", "buy_rates", "sell_rates"].includes(k),
        )
      )
        throw Error(
          "Cost overrides accept asset_rates, buy_rates and sell_rates only.",
        );
      const base: Record<string, unknown> = {
        ...selection,
        window: Number(window),
        shrinkage: Number(shrinkage),
        objective,
        constraints: {
          ...extra,
          min_weight: Number(minimum) / 100,
          max_weight: Number(maximum) / 100,
          max_turnover: turnover === "" ? null : Number(turnover) / 100,
          max_sector_weight: sectorCap === "" ? null : Number(sectorCap) / 100,
        },
        costs: { ...extraCosts, proportional_rate: Number(rate) / 100 },
        lambda_turnover: Number(coefficient),
        lambda_cost: Number(coefficient),
        ...(objective === "target_risk"
          ? { target_annual_volatility: Number(target) / 100 }
          : {}),
        ...(objective === "target_return"
          ? { target_annual_return: Number(target) / 100 }
          : {}),
        ...(returns.trim()
          ? {
              expected_returns: { annual_returns: JSON.parse(returns), source },
            }
          : {}),
      };
      if (kind === "run") submit("run", base);
      else if (kind === "sensitivity")
        submit("sensitivity", { base, variations: JSON.parse(variations) });
      else
        submit("frontier", {
          base: { ...base, objective: "min_variance" },
          mode: kind,
          ...(kind === "risk_turnover"
            ? {
                turnover_budgets: budgets
                  .split(",")
                  .map((s) => Number(s.trim()) / 100),
              }
            : {
                return_targets: targets
                  .split(",")
                  .map((s) => Number(s.trim()) / 100),
              }),
        });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid configuration.");
    }
  }
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>
            <SlidersHorizontal size={17} />
            Portfolio decision laboratory
          </h2>
          <p>
            Continuous long-only equity-sleeve allocation · independent
            feasibility checks · no trading
          </p>
        </div>
        <span className="subtle-badge">RESEARCH ONLY</span>
      </div>
      <form
        className="optimization-form"
        onSubmit={(e) => {
          e.preventDefault();
          calculate("run");
        }}
      >
        <div className="optimization-controls">
          <label>
            Objective
            <select
              aria-label="Optimization objective"
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
            >
              <option value="min_variance">A · Minimum annual variance</option>
              <option value="risk_turnover">
                B · Variance + turnover penalty
              </option>
              <option value="risk_cost">
                C · Variance + cost fraction penalty
              </option>
              <option value="target_risk">
                D · Target annual volatility feasibility
              </option>
              <option value="target_return">
                E · Sourced expected-return target
              </option>
            </select>
          </label>
          <label>
            Maximum position weight (%)
            <input
              aria-label="Optimization maximum position percent"
              type="number"
              min="0.1"
              max="100"
              step="0.1"
              value={maximum}
              onChange={(e) => setMaximum(e.target.value)}
              required
            />
          </label>
          <label>
            Minimum per-position weight (%)
            <input
              aria-label="Optimization minimum position percent"
              type="number"
              min="0"
              max="100"
              step="0.1"
              value={minimum}
              onChange={(e) => setMinimum(e.target.value)}
              required
            />
          </label>
          <label>
            Maximum one-way turnover (%)
            <input
              aria-label="Optimization turnover percent"
              type="number"
              min="0"
              max="100"
              step="0.1"
              value={turnover}
              onChange={(e) => setTurnover(e.target.value)}
              placeholder="Blank = unconstrained"
            />
          </label>
          <label>
            Maximum per-sector weight (%)
            <input
              aria-label="Optimization sector cap percent"
              type="number"
              min="0.1"
              max="100"
              step="0.1"
              value={sectorCap}
              onChange={(e) => setSectorCap(e.target.value)}
              placeholder="Blank = no global cap"
            />
          </label>
          <label>
            Historical daily returns
            <input
              aria-label="Optimization estimation window"
              type="number"
              min="60"
              max="1260"
              step="1"
              value={window}
              onChange={(e) => setWindow(e.target.value)}
              required
            />
          </label>
          <label>
            Covariance policy
            <select
              aria-label="Optimization covariance shrinkage"
              value={shrinkage}
              onChange={(e) => setShrinkage(e.target.value)}
            >
              <option value="0">Sample covariance</option>
              <option value="0.05">5% identity shrinkage</option>
              <option value="0.1">10% identity shrinkage</option>
              <option value="0.25">25% identity shrinkage</option>
            </select>
          </label>
          <label>
            Assumed cost per gross value shift (%)
            <input
              aria-label="Optimization cost percent"
              type="number"
              min="0"
              max="10"
              step="0.01"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
              required
            />
          </label>
          {["risk_cost", "risk_turnover"].includes(objective) && (
            <label>
              Penalty coefficient
              <input
                aria-label="Optimization penalty coefficient"
                type="number"
                min="0"
                max="100"
                step="0.01"
                value={coefficient}
                onChange={(e) => setCoefficient(e.target.value)}
                required
              />
            </label>
          )}
          {["target_risk", "target_return"].includes(objective) && (
            <label>
              {objective === "target_risk"
                ? "Target annual volatility (%)"
                : "Target assumed annual return (%)"}
              <input
                aria-label="Optimization annual target percent"
                type="number"
                step="0.1"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                required
              />
            </label>
          )}
        </div>
        <p className="form-help">
          Annual variance = 252 × daily variance. Penalty terms use decimal
          one-way turnover or cost / sleeve notional; the coefficient applies in
          these stated units. One-way turnover is half the gross absolute weight
          change. Costs are research assumptions, not verified broker charges.
          Cash is excluded, not assumed zero.
        </p>
        <details className="optimization-advanced">
          <summary>
            Asset, sector, frozen-position and asymmetric cost policies
          </summary>
          <p className="form-help">
            Exact held instrument / sector keys only; all JSON weights and cost
            rates are decimals. Per-asset bounds intersect global limits.
            Unknown sectors remain explicit or can be rejected.
          </p>
          <label>
            Advanced allocation policies (JSON)
            <textarea
              aria-label="Optimization advanced constraints"
              rows={5}
              value={bounds}
              onChange={(e) => setBounds(e.target.value)}
            />
          </label>
          <label>
            Asset and asymmetric cost overrides (JSON)
            <textarea
              aria-label="Optimization cost overrides"
              rows={3}
              value={costs}
              onChange={(e) => setCosts(e.target.value)}
            />
          </label>
          <p className="form-help">
            Available held universe:{" "}
            {universe.data?.holdings
              .map((h) => `${h.instrument} (${h.sector})`)
              .join(" · ") ?? "Select an accessible portfolio."}
          </p>
        </details>
        <details className="optimization-advanced">
          <summary>Optional documented expected-return assumptions</summary>
          <p className="form-help">
            A complete user-supplied vector is required for the risk–return
            frontier. Volatility forecasts do not supply expected returns.
            Estimates can be unstable and do not guarantee future performance.
          </p>
          <label>
            Annual arithmetic return assumptions by instrument (decimal JSON)
            <textarea
              aria-label="Optimization expected returns"
              value={returns}
              onChange={(e) => setReturns(e.target.value)}
              rows={3}
              placeholder='{"EXCHANGE:HELD_KEY": 0.05}'
            />
          </label>
          <label>
            Assumption source / methodology
            <input
              aria-label="Optimization return source"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              minLength={20}
            />
          </label>
        </details>
        {error && (
          <p role="alert" className="negative">
            {error}
          </p>
        )}
        <button className="button primary" disabled={disabled}>
          <Play size={15} />
          Run portfolio optimization
        </button>
      </form>
      <div className="evidence-body">
        <h3>Trade-off and sensitivity experiments</h3>
        <p className="form-help">
          Curves explicitly solve pure minimum variance using the constraints
          above; each budget or target is labeled. Sensitivities retain the
          selected base objective except a labeled cost-penalty variation.
          Failed or infeasible points have no allocation.
        </p>
        <div className="optimization-controls">
          <label>
            Turnover budgets (%)
            <input
              aria-label="Optimization curve budgets"
              value={budgets}
              onChange={(e) => setBudgets(e.target.value)}
            />
          </label>
          <label>
            Expected-return targets (%)
            <input
              aria-label="Optimization return targets"
              value={targets}
              onChange={(e) => setTargets(e.target.value)}
            />
          </label>
        </div>
        <div className="heading-actions">
          <button
            className="button secondary"
            disabled={disabled}
            onClick={() => calculate("risk_turnover")}
          >
            Calculate risk–turnover curve
          </button>
          <button
            className="button secondary"
            disabled={disabled || !returns.trim() || source.trim().length < 20}
            onClick={() => calculate("efficient")}
          >
            Calculate sourced efficient frontier
          </button>
        </div>
        <label>
          Sensitivity variations (JSON)
          <textarea
            aria-label="Optimization sensitivity variations"
            value={variations}
            onChange={(e) => setVariations(e.target.value)}
            rows={3}
          />
        </label>
        <p className="form-help">
          Supports window, shrinkage, max_weight, sector_max (with an exact
          sector key), turnover and cost_penalty. Values use decimals; window
          uses an integer. Only change the assumptions you intend to compare.
        </p>
        <button
          className="button secondary"
          disabled={disabled}
          onClick={() => calculate("sensitivity")}
        >
          Run sensitivity study
        </button>
      </div>
    </section>
  );
}
