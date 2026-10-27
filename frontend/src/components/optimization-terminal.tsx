"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, RotateCcw } from "lucide-react";
import { api, money, pct } from "@/lib/api";
import type { RiskSelection } from "@/lib/advanced-risk";
import type { OptimizationDetail, OptimizationJob } from "@/lib/optimization";
import { OptimizationControls } from "./optimization-controls";
import {
  OptimizationEvidence,
  OptimizationStudy,
  OptimizationStress,
  OptimizationHistoryComparison,
} from "./optimization-evidence";
import { ModelGovernance } from "./model-governance";
import { ErrorNotice } from "./error-notice";

export function OptimizationTerminal({
  selection,
  ready,
}: {
  selection: RiskSelection;
  ready: boolean;
}) {
  const client = useQueryClient();
  const [pointIndex, setPointIndex] = useState(0);
  const [sort, setSort] = useState("name");
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
    mutationFn: ({
      path,
      body,
    }: {
      path: string;
      body: Record<string, unknown>;
    }) =>
      api<OptimizationJob>(`/v1/optimization/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    onSuccess: (r) => {
      setActive(r.id);
      setPointIndex(0);
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
      setPointIndex(0);
      void client.invalidateQueries({ queryKey: ["optimization-history"] });
    },
  });
  const result = detail.data;
  const point = result?.result?.points[pointIndex];
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
      <OptimizationControls
        selection={selection}
        disabled={!ready || run.isPending || busy}
        submit={(path, body) => run.mutate({ path, body })}
      />
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
      {result?.result && (
        <OptimizationStudy
          result={result}
          selected={pointIndex}
          select={setPointIndex}
        />
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
          <OptimizationEvidence point={point} />
          {point.solution.feasible && (
            <section className="panel optimization-allocation">
              <div className="panel-heading">
                <div>
                  <h2>Current versus proposed allocation</h2>
                  <label>
                    Sort allocation
                    <select
                      aria-label="Sort optimization allocation"
                      value={sort}
                      onChange={(e) => setSort(e.target.value)}
                    >
                      <option value="name">Holding name</option>
                      <option value="proposed_weight">Proposed weight</option>
                      <option value="change">Weight change</option>
                    </select>
                  </label>
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
                    {[...point.allocations]
                      .sort((a, b) =>
                        sort === "name"
                          ? a.name.localeCompare(b.name)
                          : b[sort as "proposed_weight" | "change"] -
                            a[sort as "proposed_weight" | "change"],
                      )
                      .map((a) => (
                        <tr key={a.instrument}>
                          <td>
                            {a.name}
                            <small className="cell-note">
                              {a.instrument} · {a.sector}
                            </small>
                          </td>
                          <td className="numeric">
                            {pct(a.current_weight, 3)}
                          </td>
                          <td className="numeric">
                            {pct(a.proposed_weight, 3)}
                          </td>
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
          {result && (
            <OptimizationStress result={result} pointIndex={pointIndex} />
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
                      <td>
                        {r.binding ? "Binding" : "Within bounds"}
                        {r.utilization !== null && (
                          <small className="cell-note">
                            Utilization {pct(r.utilization, 2)}
                          </small>
                        )}
                      </td>
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
                      source: point.dataset.source,
                      parameters: point.parameters,
                      universe: point.dataset.instruments,
                      monte_carlo: point.comparison,
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
      <OptimizationHistoryComparison runs={history.data ?? []} />
      <ModelGovernance
        ready={ready}
        refreshKey={`${active}:${detail.data?.status}`}
      />
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
                      onClick={() => {
                        setActive(r.id);
                        setPointIndex(0);
                      }}
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
