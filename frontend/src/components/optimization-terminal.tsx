"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Play, RotateCcw, SlidersHorizontal } from "lucide-react";
import { api, money, pct } from "@/lib/api";
import type { RiskSelection } from "@/lib/advanced-risk";
import type { OptimizationDetail, OptimizationJob } from "@/lib/optimization";
import { ErrorNotice } from "./error-notice";

export function OptimizationTerminal({
  selection,
  ready,
}: {
  selection: RiskSelection;
  ready: boolean;
}) {
  const client = useQueryClient();
  const [maximum, setMaximum] = useState("20");
  const [turnover, setTurnover] = useState("15");
  const [active, setActive] = useState("");
  const history = useQuery({
    queryKey: ["optimization-history"],
    queryFn: () => api<OptimizationJob[]>("/v1/optimization/runs"),
    enabled: ready,
    refetchInterval: (q) =>
      q.state.data?.some((r) => ["queued", "running"].includes(r.status))
        ? 800
        : false,
  });
  const detail = useQuery({
    queryKey: ["optimization", active],
    queryFn: () => api<OptimizationDetail>(`/v1/optimization/runs/${active}`),
    enabled: ready && !!active,
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.status ?? "") ? 500 : false,
  });
  const busy = ["queued", "running"].includes(detail.data?.status ?? "");
  const run = useMutation({
    mutationFn: () =>
      api<OptimizationJob>("/v1/optimization/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...selection,
          constraints: {
            max_weight: Number(maximum) / 100,
            max_turnover: Number(turnover) / 100,
          },
        }),
      }),
    onSuccess: (r) => {
      setActive(r.id);
      void client.invalidateQueries({ queryKey: ["optimization-history"] });
    },
  });
  const reproduce = useMutation({
    mutationFn: () =>
      api<OptimizationJob>(`/v1/optimization/runs/${active}/reproduce`, {
        method: "POST",
      }),
    onSuccess: (r) => {
      setActive(r.id);
      void client.invalidateQueries({ queryKey: ["optimization-history"] });
    },
  });
  const result = detail.data;
  const point = result?.result?.points[0];
  function download() {
    if (!result) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `vantage-optimization-${result.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="optimization-terminal">
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
            run.mutate();
          }}
        >
          <div className="optimization-controls">
            <label>
              Maximum position weight (%)
              <input
                aria-label="Optimization maximum position percent"
                type="number"
                min="1"
                max="100"
                step="0.1"
                value={maximum}
                onChange={(e) => setMaximum(e.target.value)}
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
                required
              />
            </label>
          </div>
          <p className="form-help">
            Minimum annual variance using the selected historical window and
            covariance. One-way turnover is half the gross absolute weight
            change. Unknown account cash is excluded, not assumed zero.
            Constraints are never relaxed to produce an allocation.
          </p>
          <button
            className="button primary"
            disabled={!ready || run.isPending || busy}
          >
            <Play size={15} />
            Run portfolio optimization
          </button>
        </form>
      </section>
      {run.error && <ErrorNotice error={run.error} />}
      {detail.error && <ErrorNotice error={detail.error} />}
      {reproduce.error && <ErrorNotice error={reproduce.error} />}
      {result && (
        <section className="panel optimization-job" role="status">
          <strong>
            {result.status.toUpperCase()} ·{" "}
            {result.solver_status ?? "awaiting solver"}
          </strong>
          <p>{result.stage}</p>
          <progress max={100} value={result.progress} />
          <small>
            {result.id} · {result.version}
          </small>
          {result.error && (
            <p className="negative">
              {result.error.code}: {result.error.message}
            </p>
          )}
          {result.result?.reproduction_match !== null && result.result && (
            <p>
              Saved-input optimization reproduction match:{" "}
              {String(result.result.reproduction_match)}
            </p>
          )}
        </section>
      )}
      {point && (
        <>
          <div className="result-heading">
            <div>
              <h2>Verified allocation evidence</h2>
              <p>
                {result?.synthetic ? "SYNTHETIC" : "IMPORTED"} ·{" "}
                {point.dataset.observations} daily returns ·{" "}
                {point.dataset.estimation_start}–{point.dataset.estimation_end}
              </p>
            </div>
            <div className="heading-actions">
              <button className="button secondary" onClick={download}>
                <Download size={14} />
                Export optimization
              </button>
              <button
                className="button secondary"
                disabled={busy || reproduce.isPending}
                onClick={() => reproduce.mutate()}
              >
                <RotateCcw size={14} />
                Reproduce optimization
              </button>
            </div>
          </div>
          <section className="panel optimization-overview">
            <div className="simulation-stats">
              <div>
                Equity sleeve notional
                <strong>{money(point.dataset.sleeve_notional)}</strong>
              </div>
              <div>
                Current annual volatility
                <strong>
                  {pct(point.current_metrics.annual_volatility, 3)}
                </strong>
              </div>
              <div>
                Proposed annual volatility
                <strong>
                  {point.solution.annual_volatility === null
                    ? "Unavailable"
                    : pct(point.solution.annual_volatility, 3)}
                </strong>
              </div>
              <div>
                One-way turnover / estimated cost
                <strong>
                  {point.solution.turnover === null
                    ? "Unavailable"
                    : pct(point.solution.turnover, 3)}{" "}
                  /{" "}
                  {point.solution.cost_inr === null
                    ? "Unavailable"
                    : money(point.solution.cost_inr)}
                </strong>
              </div>
            </div>
            <p className="panel-footnote">
              {point.dataset.sleeve} {point.dataset.account_cash}
            </p>
            <ul className="risk-warnings">
              {point.solution.diagnostics.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          </section>
          {point.solution.feasible && (
            <section className="panel optimization-allocation">
              <div className="panel-heading">
                <div>
                  <h2>Current versus proposed allocation</h2>
                  <p>
                    Approximate value shifts at the fixed sleeve notional, not
                    executable orders
                  </p>
                </div>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>HOLDING / SECTOR</th>
                      <th className="numeric">CURRENT WEIGHT</th>
                      <th className="numeric">PROPOSED WEIGHT</th>
                      <th className="numeric">CHANGE</th>
                      <th className="numeric">APPROXIMATE VALUE SHIFT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {point.allocations.map((a) => (
                      <tr key={a.instrument}>
                        <td>
                          {a.name}
                          <small className="cell-note">
                            {a.instrument} · {a.sector}
                          </small>
                        </td>
                        <td className="numeric">{pct(a.current_weight, 3)}</td>
                        <td className="numeric">{pct(a.proposed_weight, 3)}</td>
                        <td className="numeric">{pct(a.change, 3)}</td>
                        <td className="numeric">
                          {money(a.approximate_notional_change)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          <section className="panel optimization-residuals">
            <div className="panel-heading">
              <div>
                <h2>Independent constraint validation</h2>
                <p>
                  Original bounds, frozen positions, sector allocations and
                  one-way turnover
                </p>
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>CONSTRAINT</th>
                    <th>GROUP</th>
                    <th className="numeric">VALUE</th>
                    <th className="numeric">LOWER / UPPER</th>
                    <th className="numeric">VIOLATION</th>
                    <th>STATE</th>
                  </tr>
                </thead>
                <tbody>
                  {point.solution.residuals.map((r, i) => (
                    <tr key={r.group + r.name + i}>
                      <td>{r.name}</td>
                      <td>{r.group}</td>
                      <td className="numeric">{r.value.toFixed(8)}</td>
                      <td className="numeric">
                        {r.lower?.toFixed(5) ?? "—"} /{" "}
                        {r.upper?.toFixed(5) ?? "—"}
                      </td>
                      <td className="numeric">
                        {r.violation.toExponential(2)}
                      </td>
                      <td>{r.binding ? "Binding" : "Within bounds"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="evidence-body">
              <details>
                <summary>Solver, source and numerical audit evidence</summary>
                <pre>
                  {JSON.stringify(
                    {
                      solver: point.solution.solver,
                      validation: point.solution.validation,
                      covariance: point.dataset.covariance_diagnostics,
                      covariance_hash: point.dataset.covariance_hash,
                      input_hash: result?.input_hash,
                      runtime: result?.runtime,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
              <p className="form-help">
                An in-sample minimum-variance allocation does not guarantee
                lower VaR, Expected Shortfall, every stress loss or future
                investment risk.
              </p>
            </div>
          </section>
        </>
      )}
      <section className="panel optimization-history">
        <div className="panel-heading">
          <div>
            <h2>Optimization history</h2>
            <p>
              Private saved inputs, solver outcomes and reproducible allocations
            </p>
          </div>
        </div>
        {history.error && <ErrorNotice error={history.error} />}
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>RUN</th>
                <th>KIND / STATUS</th>
                <th>SOLVER OUTCOME</th>
                <th>CREATED</th>
                <th>RESULT</th>
              </tr>
            </thead>
            <tbody>
              {history.data?.map((r) => (
                <tr key={r.id}>
                  <td>{r.id.slice(0, 8)}</td>
                  <td>
                    {r.kind} · {r.status}
                  </td>
                  <td>{r.solver_status ?? "Pending"}</td>
                  <td>
                    {new Date(r.created_at).toLocaleString("en-GB", {
                      timeZone: "Asia/Kolkata",
                    })}
                  </td>
                  <td>
                    <button
                      className="text-button"
                      onClick={() => setActive(r.id)}
                    >
                      Open optimization
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {history.data?.length === 0 && (
            <p className="empty-state">
              No saved optimization runs in this session.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
