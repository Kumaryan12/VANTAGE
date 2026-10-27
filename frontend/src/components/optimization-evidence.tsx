"use client";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { api, money, pct } from "@/lib/api";
import type {
  OptimizationDetail,
  OptimizationJob,
  OptimizationPoint,
  SleeveRisk,
} from "@/lib/optimization";
import { ErrorNotice } from "./error-notice";
const percentTick = (v: number) => pct(v, 1);
const pretty = (v: unknown) =>
  typeof v === "number" ? pct(v, 3) : String(v ?? "Unavailable");
export function OptimizationEvidence({ point }: { point: OptimizationPoint }) {
  const c = point.comparison;
  const metrics: {
    key: keyof SleeveRisk;
    label: string;
    format: (v: number) => string;
  }[] = [
    {
      key: "annual_volatility",
      label: "Annual volatility",
      format: (v) => pct(v, 3),
    },
    {
      key: "annual_variance",
      label: "Annual variance (decimal²)",
      format: (v) => v.toFixed(7),
    },
    ...[
      "historical_var",
      "historical_es",
      "gaussian_var",
      "gaussian_es",
      "monte_carlo_var",
      "monte_carlo_es",
    ].map((key) => ({
      key: key as keyof SleeveRisk,
      label: key.replaceAll("_", " ").toUpperCase() + " · INR one-day loss",
      format: money,
    })),
    { key: "position_hhi", label: "Position HHI", format: (v) => v.toFixed(5) },
    { key: "sector_hhi", label: "Sector HHI", format: (v) => v.toFixed(5) },
  ];
  return (
    <>
      <section className="panel optimization-risk-comparison">
        <div className="panel-heading">
          <div>
            <h2>Matched risk comparison</h2>
            <p>
              {c?.policy ??
                "Current risk remains available; no proposed metrics exist for this outcome."}
            </p>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>METRIC</th>
                <th className="numeric">CURRENT</th>
                <th className="numeric">PROPOSED</th>
                <th className="numeric">ABSOLUTE CHANGE</th>
                <th className="numeric">RELATIVE CHANGE</th>
              </tr>
            </thead>
            <tbody>
              {metrics.map((m) => (
                <tr key={m.key}>
                  <td>{m.label}</td>
                  <td className="numeric">
                    {m.format(point.current_metrics[m.key] as number)}
                  </td>
                  <td className="numeric">
                    {c ? m.format(c.proposed[m.key] as number) : "Unavailable"}
                  </td>
                  <td className="numeric">
                    {c ? m.format(c.delta[m.key]) : "Unavailable"}
                  </td>
                  <td className="numeric">
                    {c && c.relative_delta[m.key] !== null
                      ? pct(c.relative_delta[m.key] as number, 3)
                      : "Unavailable"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="evidence-body">
          <p className="form-help">
            Tail losses can increase despite lower variance. Signed changes
            retain unfavorable results. Monte Carlo sampling error excludes
            parameter uncertainty. Current and proposed baskets are
            retrospective frozen allocations, not account performance.
          </p>
          {c?.warnings.map((w) => (
            <p className="form-help" key={w}>
              {w}
            </p>
          ))}
        </div>
      </section>
      {c && (
        <>
          <section className="panel">
            <div className="panel-heading">
              <h2>Allocation and sector exposure</h2>
            </div>
            <div className="optimization-chart">
              <ResponsiveContainer width="100%" height={290}>
                <BarChart data={point.allocations}>
                  <CartesianGrid stroke="#263329" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                  <YAxis tickFormatter={percentTick} />
                  <Tooltip formatter={(v) => pretty(v)} />
                  <Legend />
                  <Bar
                    name="Current sleeve weight"
                    dataKey="current_weight"
                    fill="#6d83a0"
                    isAnimationActive={false}
                  />
                  <Bar
                    name="Proposed sleeve weight"
                    dataKey="proposed_weight"
                    fill="#64d9b4"
                    isAnimationActive={false}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>SECTOR</th>
                    <th className="numeric">CURRENT WEIGHT</th>
                    <th className="numeric">PROPOSED WEIGHT</th>
                    <th className="numeric">CURRENT VOL CONTRIBUTION</th>
                    <th className="numeric">PROPOSED VOL CONTRIBUTION</th>
                  </tr>
                </thead>
                <tbody>
                  {c.current.attribution.sectors.map((s) => (
                    <tr key={s.sector}>
                      <td>{s.sector}</td>
                      <td className="numeric">{pct(s.weight, 3)}</td>
                      <td className="numeric">
                        {pct(c.proposed.sector_weights[s.sector], 3)}
                      </td>
                      <td className="numeric">
                        {pct(s.component_annualized_volatility, 4)}
                      </td>
                      <td className="numeric">
                        {pct(
                          c.proposed.attribution.sectors.find(
                            (a) => a.sector === s.sector,
                          )?.component_annualized_volatility ?? 0,
                          4,
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Security-level volatility attribution</h2>
                <p>
                  Signed component annual volatility · same covariance ·
                  negative contributions retained
                </p>
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>SECURITY</th>
                    <th className="numeric">CURRENT COMPONENT</th>
                    <th className="numeric">PROPOSED COMPONENT</th>
                    <th className="numeric">PROPOSED SHARE</th>
                  </tr>
                </thead>
                <tbody>
                  {c.current.attribution.assets.map((a) => {
                    const p = c.proposed.attribution.assets.find(
                      (b) => b.instrument === a.instrument,
                    );
                    return (
                      <tr key={a.instrument}>
                        <td>{a.name}</td>
                        <td className="numeric">
                          {pct(a.component_annualized_volatility, 4)}
                        </td>
                        <td className="numeric">
                          {p
                            ? pct(p.component_annualized_volatility, 4)
                            : "Unavailable"}
                        </td>
                        <td className="numeric">
                          {p?.percentage_contribution != null
                            ? pct(p.percentage_contribution, 3)
                            : "Unavailable"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="panel-footnote">{c.proposed.attribution.note}</p>
          </section>
        </>
      )}
    </>
  );
}
export function OptimizationStudy({
  result,
  selected,
  select,
}: {
  result: OptimizationDetail;
  selected: number;
  select: (i: number) => void;
}) {
  if (!result.result || result.kind === "single") return null;
  const study = result.result;
  return (
    <section className="panel optimization-study">
      <div className="panel-heading">
        <div>
          <h2>
            {result.kind === "sensitivity"
              ? "Sensitivity explorer"
              : study.frontier_mode === "efficient"
                ? "Sourced risk–return frontier"
                : "Risk–turnover trade-off curve"}
          </h2>
          <p>
            Every point is an actual saved solve. Select a row to inspect its
            allocation, risk metrics and residuals.
          </p>
        </div>
      </div>
      {result.kind === "frontier" && (
        <div className="optimization-chart">
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={study.plot}>
              <CartesianGrid stroke="#263329" />
              <XAxis
                dataKey="x"
                type="number"
                domain={["auto", "auto"]}
                tickFormatter={percentTick}
                name={
                  study.frontier_mode === "efficient"
                    ? "Assumed expected annual return"
                    : "Maximum one-way turnover"
                }
              />
              <YAxis tickFormatter={percentTick} name="Annual volatility" />
              <Tooltip
                formatter={(v) => pretty(v)}
                labelFormatter={(v) => `Budget / assumed return ${pretty(v)}`}
              />
              <Line
                name="Fitted annual volatility"
                dataKey="annual_volatility"
                stroke="#64d9b4"
                connectNulls={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>ASSUMPTIONS</th>
              <th>STATUS</th>
              <th className="numeric">ANNUAL VOLATILITY</th>
              <th className="numeric">ONE-WAY TURNOVER</th>
              <th className="numeric">ESTIMATED COST</th>
              <th className="numeric">DISTANCE FROM BASE</th>
              <th>INSPECT</th>
            </tr>
          </thead>
          <tbody>
            {study.points.map((p, i) => (
              <tr key={i} className={selected === i ? "selected-row" : ""}>
                <td>
                  {p.label}
                  <small className="cell-note">
                    {JSON.stringify(p.changes)}
                  </small>
                </td>
                <td>{p.solution.status}</td>
                <td className="numeric">
                  {p.solution.annual_volatility === null
                    ? "Unavailable"
                    : pct(p.solution.annual_volatility, 3)}
                </td>
                <td className="numeric">
                  {p.solution.turnover === null
                    ? "Unavailable"
                    : pct(p.solution.turnover, 3)}
                </td>
                <td className="numeric">
                  {p.solution.cost_inr === null
                    ? "Unavailable"
                    : money(p.solution.cost_inr)}
                </td>
                <td className="numeric">
                  {p.allocation_stability?.one_way_distance_from_base == null
                    ? "—"
                    : pct(p.allocation_stability.one_way_distance_from_base, 3)}
                </td>
                <td>
                  <button className="text-button" onClick={() => select(i)}>
                    Inspect point {i + 1}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="panel-footnote">
        Covariance windows and assumptions differ only as labeled. Large weight
        changes can indicate instability. Numerical precision is not forecast
        certainty. Infeasible points have no plotted volatility.
      </p>
    </section>
  );
}
type Stress = {
  id: string;
  point_index: number;
  scenario: Record<string, unknown>;
  source: Record<string, unknown>;
  current: { pnl: number; loss: number };
  proposed: { pnl: number; loss: number };
  pnl_difference: number;
  loss_improvement: number;
  warnings: string[];
  asset_changes: {
    instrument: string;
    sector: string;
    mapping: string;
    current_pnl: number;
    proposed_pnl: number;
    pnl_difference: number;
    current_weight: number;
    proposed_weight: number;
  }[];
};
export function OptimizationStress({
  result,
  pointIndex,
}: {
  result: OptimizationDetail;
  pointIndex: number;
}) {
  const [kind, setKind] = useState("sector");
  const [sector, setSector] = useState("");
  const [shock, setShock] = useState("-15");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const point = result.result?.points[pointIndex];
  const saved = useQuery({
    queryKey: ["optimization-stress", result.id],
    queryFn: () =>
      api<Stress[]>(`/v1/optimization/runs/${result.id}/counterfactuals`),
  });
  const run = useMutation({
    mutationFn: () =>
      api<Stress>("/v1/optimization/counterfactual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          run_id: result.id,
          point_index: pointIndex,
          scenario: {
            mode: result.synthetic ? "demo" : "kite",
            ...(point?.parameters.dataset_id
              ? { dataset_id: point.parameters.dataset_id }
              : {}),
            ...(kind === "historical"
              ? { kind: "historical", start: start, end: end }
              : kind === "synthetic"
                ? { kind: "historical", scenario_id: "synthetic_2026" }
                : {
                    kind: "hypothetical",
                    ...(kind === "market"
                      ? { market_shock: Number(shock) / 100 }
                      : {
                          sector_shocks: {
                            [sector || point?.dataset.sectors[0] || ""]:
                              Number(shock) / 100,
                          },
                        }),
                  }),
          },
        }),
      }),
    onSuccess: () => {
      void saved.refetch();
    },
  });
  if (!point?.solution.feasible) return null;
  const comparison = saved.data?.filter((s) => s.point_index === pointIndex)[0];
  return (
    <section className="panel optimization-stress">
      <div className="panel-heading">
        <div>
          <h2>Counterfactual stress comparison</h2>
          <p>
            Identical scenario definitions and fixed current notional for both
            allocations
          </p>
        </div>
      </div>
      <div className="evidence-body">
        <div className="optimization-controls">
          <label>
            Scenario
            <select
              aria-label="Optimization stress kind"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              <option value="sector">Direct sector shock</option>
              <option value="market">Direct broad shock</option>
              {result.synthetic && (
                <option value="synthetic">Synthetic 2026 replay fixture</option>
              )}
              <option value="historical">
                Exact covered historical endpoints
              </option>
            </select>
          </label>
          {kind === "sector" && (
            <label>
              Sector
              <select
                aria-label="Optimization stress sector"
                value={sector || point.dataset.sectors[0]}
                onChange={(e) => setSector(e.target.value)}
              >
                {[...new Set(point.dataset.sectors)].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
          )}
          {["sector", "market"].includes(kind) && (
            <label>
              Direct price shock (%)
              <input
                aria-label="Optimization stress shock"
                type="number"
                min="-100"
                max="100"
                step="0.1"
                value={shock}
                onChange={(e) => setShock(e.target.value)}
              />
            </label>
          )}
          {kind === "historical" && (
            <>
              <label>
                Start observation date
                <input
                  type="date"
                  aria-label="Optimization scenario start"
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                />
              </label>
              <label>
                End observation date
                <input
                  type="date"
                  aria-label="Optimization scenario end"
                  value={end}
                  onChange={(e) => setEnd(e.target.value)}
                />
              </label>
            </>
          )}
        </div>
        <button
          className="button secondary"
          disabled={
            run.isPending || (kind === "historical" && (!start || !end))
          }
          onClick={() => run.mutate()}
        >
          Compare identical stress scenario
        </button>
        {run.error && <ErrorNotice error={run.error} />}
        {saved.error && <ErrorNotice error={saved.error} />}
      </div>
      {comparison && (
        <>
          <div className="simulation-stats">
            <div>
              Current scenario P&amp;L
              <strong>{money(comparison.current.pnl)}</strong>
            </div>
            <div>
              Proposed scenario P&amp;L
              <strong>{money(comparison.proposed.pnl)}</strong>
            </div>
            <div>
              P&amp;L difference / loss improvement
              <strong>{money(comparison.pnl_difference)}</strong>
            </div>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>HOLDING / SHOCK MAPPING</th>
                  <th className="numeric">CURRENT P&amp;L</th>
                  <th className="numeric">PROPOSED P&amp;L</th>
                  <th className="numeric">DIFFERENCE</th>
                  <th className="numeric">CURRENT / PROPOSED WEIGHT</th>
                </tr>
              </thead>
              <tbody>
                {comparison.asset_changes.map((a) => (
                  <tr key={a.instrument}>
                    <td>
                      {a.instrument}
                      <small className="cell-note">
                        {a.sector} · {a.mapping}
                      </small>
                    </td>
                    <td className="numeric">{money(a.current_pnl)}</td>
                    <td className="numeric">{money(a.proposed_pnl)}</td>
                    <td className="numeric">{money(a.pnl_difference)}</td>
                    <td className="numeric">
                      {pct(a.current_weight, 3)} / {pct(a.proposed_weight, 3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="evidence-body">
            <details>
              <summary>Scenario definition and source</summary>
              <pre>
                {JSON.stringify(
                  { scenario: comparison.scenario, source: comparison.source },
                  null,
                  2,
                )}
              </pre>
            </details>
            {comparison.warnings.map((w) => (
              <p className="form-help" key={w}>
                {w}
              </p>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
export function OptimizationHistoryComparison({
  runs,
}: {
  runs: OptimizationJob[];
}) {
  const [chosen, setChosen] = useState<string[]>([]);
  const compare = useMutation({
    mutationFn: () =>
      api<{
        policy: string;
        runs: {
          id: string;
          point: OptimizationPoint;
          annual_volatility_delta: number;
        }[];
      }>("/v1/optimization/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_ids: chosen }),
      }),
  });
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Compare saved allocations</h2>
          <p>
            Select 2–4 feasible single runs; the backend requires matching
            economic data and risk settings.
          </p>
        </div>
      </div>
      <div className="evidence-body">
        <div className="optimization-controls">
          {runs
            .filter(
              (r) =>
                r.kind === "single" &&
                r.status === "completed" &&
                ["optimal", "optimal_inaccurate"].includes(
                  r.solver_status ?? "",
                ),
            )
            .map((r) => (
              <label className="agent-checkbox" key={r.id}>
                <input
                  type="checkbox"
                  aria-label={`Compare saved run ${r.id.slice(0, 8)}`}
                  checked={chosen.includes(r.id)}
                  disabled={!chosen.includes(r.id) && chosen.length >= 4}
                  onChange={(e) => {
                    setChosen(
                      e.target.checked
                        ? [...chosen, r.id]
                        : chosen.filter((x) => x !== r.id),
                    );
                    compare.reset();
                  }}
                />
                {r.id.slice(0, 8)} ·{" "}
                {new Date(r.created_at).toLocaleTimeString("en-GB")}
              </label>
            ))}
        </div>
        <button
          className="button secondary"
          disabled={chosen.length < 2 || compare.isPending}
          onClick={() => compare.mutate()}
        >
          Compare selected allocations
        </button>
        {compare.error && <ErrorNotice error={compare.error} />}
      </div>
      {compare.data && (
        <>
          <p className="panel-footnote">{compare.data.policy}</p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>RUN</th>
                  <th>ANNUAL VOLATILITY</th>
                  <th>CHANGE FROM FIRST SELECTED</th>
                  <th>TURNOVER</th>
                  <th>ESTIMATED COST</th>
                </tr>
              </thead>
              <tbody>
                {compare.data.runs.map((r) => (
                  <tr key={r.id}>
                    <td>{r.id.slice(0, 8)}</td>
                    <td>{pretty(r.point.solution.annual_volatility)}</td>
                    <td>{pct(r.annual_volatility_delta, 4)}</td>
                    <td>{pretty(r.point.solution.turnover)}</td>
                    <td>
                      {r.point.solution.cost_inr === null
                        ? "Unavailable"
                        : money(r.point.solution.cost_inr)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
