"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Calculator,
  Download,
  LoaderCircle,
  ShieldCheck,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, dateLabel, money, pct } from "@/lib/api";
import type { Analysis, RiskSelection, RunMetadata } from "@/lib/advanced-risk";
import { chartTooltip } from "@/lib/chart-theme";
import { ErrorNotice } from "./error-notice";

export function exportResult(result: Analysis | { run_id: string }) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = `vantage-phase2-${result.run_id}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

export function RunEvidence({ metadata: m }: { metadata: RunMetadata }) {
  return (
    <section className="panel evidence-panel">
      <div className="panel-heading">
        <div>
          <h2>Assumptions & audit evidence</h2>
          <p>
            {m.methodology} · model {m.model_version} · calculated{" "}
            {new Date(m.created_at).toLocaleString("en-GB", {
              timeZone: "Asia/Kolkata",
            })}{" "}
            IST
          </p>
        </div>
      </div>
      <div className="evidence-body">
        <dl className="audit-grid">
          <div>
            <dt>Valuation snapshot</dt>
            <dd>
              {dateLabel(m.valuation_as_of)}
              <small>{m.snapshot_id}</small>
            </dd>
          </div>
          <div>
            <dt>Estimation observations</dt>
            <dd>
              {m.sample_size} / requested {m.requested_window}
              <small>
                {m.estimation_start
                  ? dateLabel(m.estimation_start)
                  : "No reference estimation"}{" "}
                {m.estimation_end ? `— ${dateLabel(m.estimation_end)}` : ""}
              </small>
            </dd>
          </div>
          <div>
            <dt>Horizon / confidence</dt>
            <dd>
              {pct(m.confidence, 1)}
              <small>{m.horizon}</small>
            </dd>
          </div>
          <div>
            <dt>Covariance / seed</dt>
            <dd>
              {m.covariance_method ?? "Not applicable"}
              <small>
                Shrinkage {m.shrinkage} · seed {m.random_seed ?? "N/A"} ·{" "}
                {m.simulation_count.toLocaleString()} draws
              </small>
            </dd>
          </div>
        </dl>
        <div className="hash-note">
          Input SHA-256 {m.input_hash}
          <br />
          Artifact SHA-256 {m.artifact_hash}
        </div>
        <ul className="risk-warnings">
          {m.warnings.map((warning, i) => (
            <li key={i}>{warning}</li>
          ))}
        </ul>
        <details>
          <summary>Runtime and validation metadata</summary>
          <pre>
            {JSON.stringify(
              { runtime: m.runtime, validation: m.validation },
              null,
              2,
            )}
          </pre>
        </details>
      </div>
    </section>
  );
}

export function AdvancedRisk({ selection }: { selection: RiskSelection }) {
  const queryClient = useQueryClient();
  const [confidence, setConfidence] = useState(
    String(selection.confidence * 100),
  );
  const [simulations, setSimulations] = useState("10000");
  const [seed, setSeed] = useState("42");
  const [shrinkage, setShrinkage] = useState("0");
  const analysis = useMutation({
    mutationFn: () =>
      api<Analysis>("/v1/risk/analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...selection,
          confidence: Number(confidence) / 100,
          simulations: Number(simulations),
          seed: Number(seed),
          shrinkage: Number(shrinkage),
        }),
      }),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["risk-runs"] }),
  });
  return (
    <div className="advanced-risk">
      <section className="panel calculation-panel">
        <div className="panel-heading">
          <div>
            <h2>
              <ShieldCheck size={17} />
              Advanced quantitative risk
            </h2>
            <p>
              Historical, analytical Gaussian and correlated Monte Carlo ·
              one-day INR loss
            </p>
          </div>
          <span className="subtle-badge">PHASE 2</span>
        </div>
        <form
          className="risk-controls"
          onSubmit={(event) => {
            event.preventDefault();
            analysis.mutate();
          }}
        >
          <label>
            Confidence (%)
            <input
              aria-label="Advanced confidence percent"
              type="number"
              min="90"
              max="99.5"
              step="0.1"
              required
              value={confidence}
              onChange={(e) => setConfidence(e.target.value)}
            />
          </label>
          <label>
            Simulations
            <input
              aria-label="Simulation count"
              type="number"
              min="2000"
              max="100000"
              step="1000"
              required
              value={simulations}
              onChange={(e) => setSimulations(e.target.value)}
            />
          </label>
          <label>
            Random seed
            <input
              aria-label="Random seed"
              type="number"
              min="0"
              max="4294967295"
              step="1"
              required
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
            />
          </label>
          <label>
            Covariance
            <select
              aria-label="Covariance policy"
              value={shrinkage}
              onChange={(e) => setShrinkage(e.target.value)}
            >
              <option value="0">Sample · no shrinkage</option>
              <option value="0.05">Identity shrinkage · 5%</option>
              <option value="0.1">Identity shrinkage · 10%</option>
              <option value="0.25">Identity shrinkage · 25%</option>
            </select>
          </label>
          <button className="button primary" disabled={analysis.isPending}>
            {analysis.isPending ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <Calculator size={15} />
            )}
            Calculate and save
          </button>
        </form>
        <p className="control-explanation">
          Current snapshot weights, simple adjusted returns, full covariance.
          Controls apply when you calculate; saved results retain their own
          parameters. Simulation standard errors describe sampling noise
          conditional on the fitted model.
        </p>
      </section>
      {analysis.error && <ErrorNotice error={analysis.error} />}{" "}
      {analysis.isPending ? (
        <div className="loading-state">
          <Activity size={24} className="spin" />
          <p>Calculating correlated scenarios and preserving replay inputs…</p>
        </div>
      ) : analysis.data ? (
        <AnalysisView result={analysis.data} />
      ) : (
        <div className="empty-analysis">
          <Calculator size={24} />
          <p>
            Calculate a complete model comparison to inspect tail risk and
            attribution.
          </p>
        </div>
      )}
    </div>
  );
}

export function AnalysisView({ result: r }: { result: Analysis }) {
  const models = [
    { key: "historical" as const, name: "Historical", color: "#64d9b4" },
    { key: "gaussian" as const, name: "Gaussian", color: "#779cf5" },
    { key: "monte_carlo" as const, name: "Monte Carlo", color: "#b297df" },
  ];
  return (
    <div className="analysis-output">
      <div className="result-heading">
        <div>
          <span className="eyebrow">SAVED RISK COMPARISON</span>
          <h2>
            {pct(r.parameters.confidence, 1)} confidence ·{" "}
            {r.metadata.sample_size} daily returns
          </h2>
          <p>
            Snapshot {money(r.portfolio.total_value)} · daily volatility{" "}
            {pct(r.daily_volatility)} · annualized{" "}
            {pct(r.annualized_volatility)} · mean daily return{" "}
            {pct(r.expected_daily_return, 3)}
          </p>
        </div>
        <button className="button secondary" onClick={() => exportResult(r)}>
          <Download size={14} />
          Export comparison
        </button>
      </div>
      <section
        className="model-grid"
        aria-label="VaR and Expected Shortfall comparison"
      >
        {models.map((model) => {
          const estimate = r.models[model.key];
          return (
            <article
              className="panel model-card"
              key={model.key}
              style={{ borderTopColor: model.color }}
            >
              <div>
                <span
                  className="model-color"
                  style={{ background: model.color }}
                />
                {model.name}
                <span className="subtle-badge">1 DAY · INR</span>
              </div>
              <dl>
                <dt>Value-at-Risk</dt>
                <dd>
                  {money(estimate.var)}
                  <small>{pct(estimate.var_return)} of portfolio</small>
                </dd>
                <dt>Expected Shortfall</dt>
                <dd className="es-value">
                  {money(estimate.expected_shortfall)}
                  <small>{pct(estimate.es_return)} of portfolio</small>
                </dd>
              </dl>
              <p>
                {model.key === "historical"
                  ? `${estimate.tail_sample_mass?.toFixed(2)} empirical tail observations · fractional cutoff mass`
                  : model.key === "gaussian"
                    ? "Analytical normal loss quantile and tail mean"
                    : `${r.simulation.simulations.toLocaleString()} correlated draws · seed ${r.simulation.seed}`}
              </p>
              <details>
                <summary>Method assumptions</summary>
                <ul>
                  {estimate.assumptions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </details>
            </article>
          );
        })}
      </section>
      <div className="model-explanation">
        Historical estimates preserve the observed return sample. Gaussian
        estimates use its fitted mean and covariance; Monte Carlo samples that
        same Gaussian model. Differences between the Gaussian and Monte Carlo
        estimates should be interpreted alongside simulation uncertainty, not as
        forecasting superiority.
      </div>
      <section className="panel distribution-panel">
        <div className="panel-heading">
          <div>
            <h2>Correlated Monte Carlo P&L distribution</h2>
            <p>
              {r.simulation.simulations.toLocaleString()} scenarios · spectral
              PSD square root · {r.simulation.bit_generator} · losses lie to the
              left
            </p>
          </div>
          <span className="chart-legend">
            <i />
            P&L frequency
          </span>
        </div>
        <div className="distribution-chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={r.simulation.histogram}
              margin={{ top: 22, right: 28, left: 0, bottom: 15 }}
            >
              <CartesianGrid stroke="#253137" vertical={false} />
              <XAxis
                type="number"
                dataKey="center_pnl"
                domain={["dataMin", "dataMax"]}
                tickFormatter={(v) => money(Number(v), true)}
                tick={{ fill: "#87959c", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                minTickGap={45}
              />
              <YAxis
                tick={{ fill: "#87959c", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={chartTooltip}
                labelFormatter={(v) => `P&L bin near ${money(Number(v))}`}
                formatter={(v) => [Number(v).toLocaleString(), "Simulations"]}
              />
              <Bar dataKey="count" isAnimationActive={false}>
                {r.simulation.histogram.map((bin, i) => (
                  <Cell
                    key={i}
                    fill={bin.tail_count > 0 ? "#df8a96" : "#6f9db5"}
                  />
                ))}
              </Bar>
              <ReferenceLine
                x={-r.models.monte_carlo.var}
                stroke="#e3b773"
                strokeDasharray="4 3"
                label={{
                  value: "−VaR",
                  position: "top",
                  fill: "#e3b773",
                  fontSize: 10,
                }}
              />
              <ReferenceLine
                x={-r.models.monte_carlo.expected_shortfall}
                stroke="#df8a96"
                strokeDasharray="4 3"
                label={{
                  value: "−ES",
                  position: "top",
                  fill: "#df8a96",
                  fontSize: 10,
                }}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="simulation-stats">
          <div>
            VaR sampling SE
            <strong>{money(r.simulation.var_standard_error)}</strong>
          </div>
          <div>
            ES sampling SE
            <strong>{money(r.simulation.es_standard_error)}</strong>
          </div>
          <div>
            Median simulated value
            <strong>{money(r.simulation.value_quantiles.p50)}</strong>
          </div>
          <div>
            Nonpositive portfolio values
            <strong>{r.simulation.nonpositive_value_count}</strong>
          </div>
        </div>
        <p className="panel-footnote">
          {r.simulation.uncertainty_note} Tail-colored bins contain observations
          at or below −VaR; a boundary bin can include both tail and non-tail
          values. Gaussian returns below −100%:{" "}
          {r.simulation.asset_returns_below_minus_one}. No clipping is applied.
        </p>
      </section>
      <div className="risk-detail-grid attribution-charts">
        <ContributionChart
          title="Security volatility contributions"
          data={r.attribution.assets}
          nameKey="name"
        />
        <ContributionChart
          title="Sector volatility contributions"
          data={r.attribution.sectors}
          nameKey="sector"
        />
      </div>
      <section className="panel contribution-table">
        <div className="panel-heading">
          <div>
            <h2>Risk concentration & reconciliation</h2>
            <p>{r.attribution.note}</p>
          </div>
          <span className="subtle-badge">VOLATILITY · NOT VAR</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>SECURITY / SECTOR</th>
                <th className="numeric">CAPITAL WEIGHT</th>
                <th className="numeric">MARGINAL DAILY VOL.</th>
                <th className="numeric">COMPONENT ANN. VOL.</th>
                <th className="numeric">RISK SHARE</th>
              </tr>
            </thead>
            <tbody>
              {r.attribution.assets.map((a) => (
                <tr key={a.instrument}>
                  <td>
                    {a.instrument}
                    <small className="cell-note">{a.sector}</small>
                  </td>
                  <td className="numeric">{pct(a.weight)}</td>
                  <td className="numeric">
                    {a.marginal_daily_volatility === null
                      ? "Undefined"
                      : pct(a.marginal_daily_volatility, 4)}
                  </td>
                  <td className="numeric">
                    {pct(a.component_annualized_volatility, 4)}
                  </td>
                  <td className="numeric">
                    {a.percentage_contribution === null
                      ? "Undefined"
                      : pct(a.percentage_contribution)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-footer">
          <span>
            Daily reconciliation residual:{" "}
            {r.attribution.reconciliation_residual.toExponential(2)}
          </span>
          <span>
            Positive-component HHI
            <strong>
              {r.attribution.positive_component_hhi?.toFixed(4) ?? "Undefined"}
            </strong>
          </span>
        </div>
      </section>
      <section className="panel model-correlation">
        <div className="panel-heading">
          <div>
            <h2>Model correlation diagnostics</h2>
            <p>
              Policy {r.covariance_diagnostics.method} · rank{" "}
              {r.covariance_diagnostics.rank} / {r.portfolio.holdings.length} ·
              condition number{" "}
              {r.covariance_diagnostics.condition_number?.toExponential(2) ??
                "Singular"}{" "}
              · clipped eigenvalues{" "}
              {r.covariance_diagnostics.negative_eigenvalues_clipped}
            </p>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>INSTRUMENT</th>
                {r.portfolio.holdings.map((h) => (
                  <th className="numeric" key={h.instrument}>
                    {h.instrument.split(":")[1]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {r.correlation.map((row, i) => (
                <tr key={i}>
                  <td>{r.portfolio.holdings[i].instrument}</td>
                  {row.map((v, j) => (
                    <td
                      className="numeric"
                      key={j}
                      style={{
                        background:
                          v === null
                            ? undefined
                            : `rgba(${v < 0 ? "223,138,150" : "100,217,180"},${Math.abs(v) * 0.18})`,
                      }}
                    >
                      {v === null ? "N/A" : v.toFixed(3)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-footer">
          <span>
            PSD correction Frobenius norm:{" "}
            {r.covariance_diagnostics.correction_frobenius_norm.toExponential(
              2,
            )}
          </span>
          <span>
            Shrinkage change:{" "}
            {r.covariance_diagnostics.shrinkage_change_frobenius_norm.toExponential(
              2,
            )}
          </span>
        </div>
      </section>
      <RunEvidence metadata={r.metadata} />
    </div>
  );
}

function ContributionChart({
  title,
  data,
  nameKey,
}: {
  title: string;
  data: {
    name?: string;
    sector: string;
    component_annualized_volatility: number;
  }[];
  nameKey: "name" | "sector";
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          <p>
            Annualized volatility percentage points · negative contributions are
            valid
          </p>
        </div>
      </div>
      <div className="contribution-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            layout="vertical"
            data={data}
            margin={{ left: 5, right: 25, top: 10, bottom: 10 }}
          >
            <CartesianGrid stroke="#253137" horizontal={false} />
            <XAxis
              type="number"
              tickFormatter={(v) => pct(Number(v), 1)}
              tick={{ fill: "#87959c", fontSize: 9 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey={nameKey}
              width={110}
              tick={{ fill: "#a1b5bf", fontSize: 9 }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={chartTooltip}
              formatter={(v) => [pct(Number(v), 4), "Component volatility"]}
            />
            <ReferenceLine x={0} stroke="#667e89" />
            <Bar
              dataKey="component_annualized_volatility"
              isAnimationActive={false}
              radius={[0, 3, 3, 0]}
            >
              {data.map((row, i) => (
                <Cell
                  key={i}
                  fill={
                    row.component_annualized_volatility < 0
                      ? "#df8a96"
                      : "#64d9b4"
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
