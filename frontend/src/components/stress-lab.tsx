"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FlaskConical, LoaderCircle, Play } from "lucide-react";
import {
  Area,
  AreaChart,
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
import {
  api,
  dateLabel,
  money,
  pct,
  type Dataset,
  type Portfolio,
} from "@/lib/api";
import type {
  RiskSelection,
  Scenario,
  Stress,
  StressParameters,
} from "@/lib/advanced-risk";
import { chartTooltip } from "@/lib/chart-theme";
import { ErrorNotice } from "./error-notice";
import { exportResult, RunEvidence } from "./advanced-risk";

export function StressLab({
  portfolio,
  selection,
  datasets,
}: {
  portfolio: Portfolio;
  selection: RiskSelection;
  datasets: Dataset[];
}) {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<"hypothetical" | "historical">(
    "hypothetical",
  );
  const [name, setName] = useState("Broad equity shock");
  const [market, setMarket] = useState("-10");
  const [sectors, setSectors] = useState<Record<string, string>>({});
  const [securities, setSecurities] = useState<Record<string, string>>({});
  const [scenarioId, setScenarioId] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [scenarioDataset, setScenarioDataset] = useState(
    selection.dataset_id ?? "",
  );
  const [completed, setCompleted] = useState<Stress[]>([]);
  const catalog = useQuery({
    queryKey: ["stress-scenarios", selection.mode, scenarioDataset],
    queryFn: () =>
      api<Scenario[]>(
        `/v1/risk/scenarios?mode=${selection.mode}${scenarioDataset && selection.mode === "kite" ? `&dataset_id=${encodeURIComponent(scenarioDataset)}` : ""}`,
      ),
  });
  function parameters(): StressParameters {
    if (kind === "historical")
      return {
        ...selection,
        kind,
        name,
        ...(scenarioDataset ? { scenario_dataset_id: scenarioDataset } : {}),
        ...(scenarioId ? { scenario_id: scenarioId } : { start, end }),
      };
    return {
      ...selection,
      kind,
      name,
      ...(market.trim() !== "" ? { market_shock: Number(market) / 100 } : {}),
      sector_shocks: Object.fromEntries(
        Object.entries(sectors)
          .filter(([, v]) => v.trim() !== "")
          .map(([k, v]) => [k, Number(v) / 100]),
      ),
      security_shocks: Object.fromEntries(
        Object.entries(securities)
          .filter(([, v]) => v.trim() !== "")
          .map(([k, v]) => [k, Number(v) / 100]),
      ),
    };
  }
  const stress = useMutation({
    mutationFn: () =>
      api<Stress>("/v1/risk/stress-test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parameters()),
      }),
    onSuccess: (result) => {
      setCompleted((previous) => [result, ...previous].slice(0, 4));
      void queryClient.invalidateQueries({ queryKey: ["risk-runs"] });
    },
  });
  return (
    <div className="stress-lab">
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>
              <FlaskConical size={18} />
              Stress testing laboratory
            </h2>
            <p>
              Direct what-if impacts and current-allocation replay · every
              result is saved
            </p>
          </div>
          <span className="subtle-badge">
            {portfolio.synthetic
              ? "SYNTHETIC PORTFOLIO"
              : "AUTHORIZED SNAPSHOT"}
          </span>
        </div>
        <form
          className="stress-form"
          onSubmit={(event) => {
            event.preventDefault();
            stress.mutate();
          }}
        >
          <div className="stress-primary-controls">
            <label>
              Scenario type
              <select
                aria-label="Scenario type"
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value as typeof kind);
                  setScenarioId("");
                }}
              >
                <option value="hypothetical">Hypothetical direct shocks</option>
                <option value="historical">
                  {portfolio.synthetic
                    ? "Synthetic historical-style replay"
                    : "Historical market replay"}
                </option>
              </select>
            </label>
            <label>
              Scenario name
              <input
                aria-label="Scenario name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                minLength={1}
                maxLength={100}
                required
              />
            </label>
          </div>
          {kind === "hypothetical" ? (
            <>
              <div className="shock-policy">
                <strong>Replacement precedence</strong>
                <p>
                  Security shock replaces its sector shock; sector shock
                  replaces the broad shock. Values are never added. Blank fields
                  inherit the broader shock; without a broad shock, unmatched
                  holdings stay unchanged.
                </p>
              </div>
              <div className="shock-input-grid">
                <label>
                  Broad equity shock (%)
                  <input
                    aria-label="Broad equity shock percent"
                    type="number"
                    min="-100"
                    max="500"
                    step="0.1"
                    value={market}
                    onChange={(e) => setMarket(e.target.value)}
                    placeholder="Unchanged if blank"
                  />
                </label>
                {Object.keys(portfolio.sectors).map((sector) => (
                  <label key={sector}>
                    {sector} override (%)
                    <input
                      aria-label={`${sector} sector shock percent`}
                      type="number"
                      min="-100"
                      max="500"
                      step="0.1"
                      value={sectors[sector] ?? ""}
                      onChange={(e) =>
                        setSectors({ ...sectors, [sector]: e.target.value })
                      }
                      placeholder="Inherit broad shock"
                    />
                  </label>
                ))}
              </div>
              <details className="security-overrides">
                <summary>Optional security overrides</summary>
                <div className="shock-input-grid">
                  {portfolio.holdings.map((h) => (
                    <label key={h.instrument}>
                      {h.instrument} (%)
                      <input
                        aria-label={`${h.instrument} security shock percent`}
                        type="number"
                        min="-100"
                        max="500"
                        step="0.1"
                        value={securities[h.instrument] ?? ""}
                        onChange={(e) =>
                          setSecurities({
                            ...securities,
                            [h.instrument]: e.target.value,
                          })
                        }
                        placeholder="Inherit sector / broad"
                      />
                    </label>
                  ))}
                </div>
              </details>
              <p className="form-help">
                These are user-defined direct returns, not forecasts or
                estimated factors. No market or sector beta is invented.
              </p>
            </>
          ) : (
            <>
              <div className="stress-primary-controls">
                {selection.mode === "kite" && (
                  <label>
                    Historical scenario dataset
                    <select
                      aria-label="Scenario historical dataset"
                      value={scenarioDataset}
                      onChange={(e) => setScenarioDataset(e.target.value)}
                    >
                      <option value="">Select imported history</option>
                      {datasets.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.provenance.source.slice(0, 50)} ·{" "}
                          {d.provenance.start}–{d.provenance.end}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <label>
                  Named replay window
                  <select
                    aria-label="Named replay window"
                    value={scenarioId}
                    onChange={(e) => {
                      setScenarioId(e.target.value);
                      const selected = catalog.data?.find(
                        (s) => s.id === e.target.value,
                      );
                      if (selected) setName(selected.name);
                    }}
                  >
                    <option value="">Custom exact dates</option>
                    {catalog.data?.map((s) => (
                      <option key={s.id} value={s.id} disabled={!s.available}>
                        {s.name}
                        {!s.available ? " · unavailable" : ""}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {catalog.error && <ErrorNotice error={catalog.error} />}
              <div className="scenario-coverage-list">
                {catalog.data?.map((s) => (
                  <div key={s.id}>
                    <span
                      className={`status-dot ${s.available ? "" : "offline"}`}
                    />
                    <div>
                      <strong>{s.name}</strong>
                      <small>
                        {s.start} — {s.end} · {s.reason}
                      </small>
                    </div>
                  </div>
                ))}
              </div>
              {!scenarioId && (
                <div className="stress-primary-controls">
                  <label>
                    Exact start observation
                    <input
                      aria-label="Scenario start date"
                      type="date"
                      value={start}
                      onChange={(e) => setStart(e.target.value)}
                      required
                    />
                  </label>
                  <label>
                    Exact end observation
                    <input
                      aria-label="Scenario end date"
                      type="date"
                      value={end}
                      onChange={(e) => setEnd(e.target.value)}
                      required
                    />
                  </label>
                </div>
              )}
              <p className="form-help">
                {portfolio.synthetic
                  ? "DEMO: replay uses invented fixture observations, never actual pandemic or market-event shocks. "
                  : "Historical replay requires appropriately adjusted observations for every current holding. "}
                Initial allocations are scaled to today’s value; virtual
                adjusted units stay fixed through the window. Exact endpoint
                dates are required; no nearest-date substitution.
              </p>
            </>
          )}
          <button
            className="button primary"
            disabled={
              stress.isPending || (kind === "historical" && catalog.isPending)
            }
          >
            {stress.isPending ? (
              <LoaderCircle className="spin" size={15} />
            ) : (
              <Play size={15} />
            )}
            Run stress scenario
          </button>
        </form>
      </section>
      {stress.error && <ErrorNotice error={stress.error} />}{" "}
      {completed.length > 1 && (
        <section className="panel scenario-comparison">
          <div className="panel-heading">
            <div>
              <h2>Scenario comparison</h2>
              <p>
                Most recent four scenarios in this view; different windows are
                not horizon-normalized
              </p>
            </div>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>SCENARIO</th>
                  <th>TYPE</th>
                  <th className="numeric">P&L</th>
                  <th className="numeric">RETURN</th>
                  <th className="numeric">POST-SHOCK VALUE</th>
                </tr>
              </thead>
              <tbody>
                {completed.map((r) => (
                  <tr key={r.run_id}>
                    <td>{r.name}</td>
                    <td>{r.scenario_kind.replaceAll("_", " ")}</td>
                    <td
                      className={`numeric ${r.pnl < 0 ? "negative" : "positive"}`}
                    >
                      {money(r.pnl)}
                    </td>
                    <td className="numeric">{pct(r.portfolio_return)}</td>
                    <td className="numeric">{money(r.value_after)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {stress.isPending ? (
        <div className="loading-state">
          <LoaderCircle className="spin" size={22} />
          <p>Applying the scenario to the authorized snapshot…</p>
        </div>
      ) : (
        stress.data && <StressView result={stress.data} />
      )}
    </div>
  );
}

export function StressView({ result: r }: { result: Stress }) {
  return (
    <div className="stress-output">
      <div className="result-heading">
        <div>
          <span className="eyebrow">
            {r.scenario_kind.replaceAll("_", " ").toUpperCase()} · SAVED RESULT
          </span>
          <h2>{r.name}</h2>
          <p>
            Run {r.run_id} ·{" "}
            {r.observations
              ? `${r.observations} aligned price observations`
              : "Direct instantaneous shock"}
          </p>
        </div>
        <button className="button secondary" onClick={() => exportResult(r)}>
          <Download size={14} />
          Export scenario
        </button>
      </div>
      <section className="scenario-metrics">
        <div className="panel">
          <span>Value before scenario</span>
          <strong>{money(r.value_before)}</strong>
        </div>
        <div className="panel">
          <span>Portfolio P&L</span>
          <strong className={r.pnl < 0 ? "negative" : "positive"}>
            {money(r.pnl)}
          </strong>
          <small>{pct(r.portfolio_return)} implied return</small>
        </div>
        <div className="panel">
          <span>Value after scenario</span>
          <strong>{money(r.value_after)}</strong>
        </div>
      </section>
      <div className="risk-detail-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Security P&L contributions</h2>
              <p>Direct position impact · negative amounts are losses</p>
            </div>
          </div>
          <div className="contribution-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                layout="vertical"
                data={r.assets}
                margin={{ left: 5, right: 25, top: 10, bottom: 10 }}
              >
                <CartesianGrid stroke="#253137" horizontal={false} />
                <XAxis
                  type="number"
                  tickFormatter={(v) => money(Number(v), true)}
                  tick={{ fill: "#87959c", fontSize: 9 }}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={105}
                  tick={{ fill: "#a1b5bf", fontSize: 9 }}
                />
                <Tooltip
                  contentStyle={chartTooltip}
                  formatter={(v) => [money(Number(v)), "Position P&L"]}
                />
                <ReferenceLine x={0} stroke="#667e89" />
                <Bar dataKey="pnl" isAnimationActive={false}>
                  {r.assets.map((a) => (
                    <Cell
                      key={a.instrument}
                      fill={a.pnl < 0 ? "#df8a96" : "#64d9b4"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>
                {r.path.length
                  ? "Buy-and-hold scenario path"
                  : "Sector P&L contributions"}
              </h2>
              <p>
                {r.path.length
                  ? "Current initial allocation replay; not actual account performance"
                  : "Aggregated direct position P&L; no overlapping shocks"}
              </p>
            </div>
          </div>
          {r.path.length ? (
            <div className="contribution-chart">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={r.path}
                  margin={{ right: 25, left: 0, bottom: 10, top: 15 }}
                >
                  <CartesianGrid stroke="#253137" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(d) => dateLabel(d).slice(0, 6)}
                    minTickGap={40}
                    tick={{ fill: "#87959c", fontSize: 9 }}
                  />
                  <YAxis
                    tickFormatter={(v) => money(Number(v), true)}
                    tick={{ fill: "#87959c", fontSize: 9 }}
                    domain={["auto", "auto"]}
                  />
                  <Tooltip
                    contentStyle={chartTooltip}
                    labelFormatter={(v) => dateLabel(String(v))}
                    formatter={(v) => [money(Number(v)), "Scenario value"]}
                  />
                  <Area
                    dataKey="value"
                    stroke="#779cf5"
                    fill="#779cf515"
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="sector-pnl-list">
              {r.sectors.map((s) => (
                <div key={s.sector}>
                  <span>{s.sector}</span>
                  <strong className={s.pnl < 0 ? "negative" : "positive"}>
                    {money(s.pnl)}
                  </strong>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Affected holdings & shock mapping</h2>
            <p>Position and sector P&L reconcile to the portfolio total</p>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>INSTRUMENT</th>
                <th>MAPPING</th>
                <th className="numeric">IMPLIED RETURN</th>
                <th className="numeric">POSITION P&L</th>
                <th className="numeric">POST-SHOCK VALUE</th>
              </tr>
            </thead>
            <tbody>
              {r.assets.map((a) => (
                <tr key={a.instrument}>
                  <td>
                    {a.instrument}
                    <small className="cell-note">{a.sector}</small>
                  </td>
                  <td>{a.mapping}</td>
                  <td className="numeric">{pct(a.shock_return)}</td>
                  <td
                    className={`numeric ${a.pnl < 0 ? "negative" : "positive"}`}
                  >
                    {money(a.pnl)}
                  </td>
                  <td className="numeric">{money(a.value_after)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-footer">
          <span>
            Sector / portfolio reconciliation residual:{" "}
            {r.pnl_reconciliation_residual.toExponential(2)} INR
          </span>
          <span>
            Loss contributors:{" "}
            {r.largest_loss_contributors.join(", ") || "None"}
          </span>
        </div>
      </section>
      <section className="panel scenario-assumptions">
        <div className="panel-heading">
          <div>
            <h2>Scenario assumptions & current risk comparison</h2>
          </div>
        </div>
        <div className="evidence-body">
          <ul className="risk-warnings">
            {r.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
          {r.reference_risk ? (
            <>
              <p>
                Current historical VaR:{" "}
                <strong>{money(r.reference_risk.historical_var)}</strong> · ES:{" "}
                <strong>{money(r.reference_risk.historical_es)}</strong> ·
                scenario loss / positive one-day VaR:{" "}
                <strong>
                  {r.reference_risk.stress_loss_to_var?.toFixed(2) ??
                    "Undefined"}
                </strong>
              </p>
              <p className="form-help">{r.reference_risk.note}</p>
            </>
          ) : (
            <p className="form-help">
              Current risk comparison is unavailable. Review the validation
              evidence below; scenario impacts do not substitute for missing
              risk history.
            </p>
          )}
        </div>
      </section>
      <RunEvidence metadata={r.metadata} />
    </div>
  );
}
