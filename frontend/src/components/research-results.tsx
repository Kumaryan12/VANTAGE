"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Database, ShieldCheck } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, dateLabel, money, pct } from "@/lib/api";
import { chartTooltip } from "@/lib/chart-theme";
import {
  metric,
  modelColors,
  modelNames,
  scientific,
  type Experiment,
  type ForecastModel,
  type ModelKind,
  type Regimes,
  type ResearchComparison,
  type ResearchPoint,
} from "@/lib/research";
import { ErrorNotice } from "./error-notice";
import { ResearchExplanation } from "./research-explanation";

const kinds: ModelKind[] = ["rolling", "ewma", "garch", "lightgbm"];

export function ResearchResults({ experiment: e }: { experiment: Experiment }) {
  const [draft, setDraft] = useState({
    start: e.protocol.test_start,
    end: e.protocol.test_end,
  });
  const [window, setWindow] = useState(draft);
  const [kind, setKind] = useState<ModelKind>("lightgbm");
  const [confidence, setConfidence] = useState("95");
  const suffix = `experiment_id=${e.id}&start=${window.start}&end=${window.end}`;
  const comparison = useQuery({
    queryKey: ["research-comparison", e.id, window],
    queryFn: () => api<ResearchComparison>(`/v1/ml/comparison?${suffix}`),
  });
  const models = useQuery({
    queryKey: ["research-models", e.id],
    queryFn: () => api<ForecastModel[]>(`/v1/ml/models?experiment_id=${e.id}`),
  });
  const series = useQuery({
    queryKey: ["research-series", e.id, window],
    queryFn: () =>
      api<ResearchPoint[]>(
        `/v1/ml/experiments/${e.id}/series?start=${window.start}&end=${window.end}`,
      ),
  });
  const regimes = useQuery({
    queryKey: ["research-regimes", e.id],
    queryFn: () => api<Regimes>(`/v1/ml/regimes?experiment_id=${e.id}`),
  });
  const selected = models.data?.find((m) => m.kind === kind);
  const row = comparison.data?.models.find((m) => m.kind === kind);
  const coverage =
    confidence === "95" ? row?.metrics.coverage95 : row?.metrics.coverage99;
  const threshold = `var${confidence}_${kind}`;
  const exception = `exception${confidence}_${kind}`;
  return (
    <div className="research-evidence">
      <div className="research-source">
        <Database size={17} />
        <div>
          <strong>
            {e.synthetic ? "SYNTHETIC RESEARCH DATA" : "IMPORTED RESEARCH DATA"}{" "}
            · {e.dataset.source}
          </strong>
          <p>{e.dataset.portfolio_construction}</p>
          <small>
            {e.dataset.price_start} — {e.dataset.end} ·{" "}
            {e.dataset.return_observations} returns ·{" "}
            {e.dataset.features.length} features · {e.model_version}
          </small>
        </div>
      </div>
      <div className="research-model-cards">
        {models.data?.map((model) => (
          <article className="panel research-model-card" key={model.id}>
            <div>
              <span
                className="model-color"
                style={{ background: modelColors[model.kind] }}
              />
              <h3>{modelNames[model.kind]}</h3>
              <span className="subtle-badge">{model.role.toUpperCase()}</span>
            </div>
            <strong>
              {model.latest_forecast?.forecast_volatility == null
                ? "Unavailable"
                : pct(model.latest_forecast.forecast_volatility, 3)}
            </strong>
            <p>Latest one-day volatility forecast</p>
            <small>
              Origin {model.latest_forecast?.origin ?? "Unavailable"} · next
              observed session date not inferred
            </small>
            <div className="research-model-status">
              {model.status} · {model.refits.length} fitted checkpoints
            </div>
          </article>
        ))}
      </div>
      <section className="panel research-window">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            setWindow(draft);
          }}
        >
          <div>
            <h2>Matched evaluation window</h2>
            <p>
              Every model uses the same selected target dates; unavailable
              forecasts are disclosed.
            </p>
          </div>
          <label>
            From
            <input
              aria-label="Research evaluation start"
              type="date"
              min={e.protocol.test_start}
              max={e.protocol.test_end}
              value={draft.start}
              onChange={(v) => setDraft({ ...draft, start: v.target.value })}
              required
            />
          </label>
          <label>
            Through
            <input
              aria-label="Research evaluation end"
              type="date"
              min={e.protocol.test_start}
              max={e.protocol.test_end}
              value={draft.end}
              onChange={(v) => setDraft({ ...draft, end: v.target.value })}
              required
            />
          </label>
          <button className="button secondary" type="submit">
            Apply evaluation window
          </button>
        </form>
      </section>
      {comparison.error && <ErrorNotice error={comparison.error} />}{" "}
      {models.error && <ErrorNotice error={models.error} />}{" "}
      {series.error && <ErrorNotice error={series.error} />}{" "}
      {comparison.data && (
        <section className="panel research-leaderboard">
          <div className="panel-heading">
            <div>
              <h2>Model challenger leaderboard</h2>
              <p>
                {comparison.data.matched_observations} common /{" "}
                {comparison.data.requested_observations} requested targets ·{" "}
                {comparison.data.excluded_dates.length} excluded dates
              </p>
            </div>
            <span className="subtle-badge">NO AUTOMATIC CHAMPION</span>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>MODEL / ROLE</th>
                  <th className="numeric">QLIKE ↓</th>
                  <th className="numeric">MSE ↓</th>
                  <th className="numeric">MAE ↓</th>
                  <th className="numeric">95% EXCEPTIONS</th>
                  <th className="numeric">99% EXCEPTIONS</th>
                  <th className="numeric">KUPIEC P 95 / 99</th>
                  <th className="numeric">FIT / PREDICT SECONDS</th>
                </tr>
              </thead>
              <tbody>
                {comparison.data.models.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <button
                        className="text-button"
                        onClick={() => setKind(m.kind)}
                      >
                        {modelNames[m.kind]}
                      </button>
                      <small className="cell-note">
                        {m.role} · {m.status} · failures {m.failures}
                      </small>
                    </td>
                    <td className="numeric">{metric(m.metrics.qlike)}</td>
                    <td className="numeric">{scientific(m.metrics.mse)}</td>
                    <td className="numeric">{scientific(m.metrics.mae)}</td>
                    <td className="numeric">
                      {m.metrics.coverage95.exceptions}/{m.metrics.observations}
                      <small className="cell-note">
                        {m.metrics.coverage95.exception_rate == null
                          ? "Unavailable"
                          : pct(m.metrics.coverage95.exception_rate, 1)}
                      </small>
                    </td>
                    <td className="numeric">
                      {m.metrics.coverage99.exceptions}/{m.metrics.observations}
                      <small className="cell-note">
                        {m.metrics.coverage99.exception_rate == null
                          ? "Unavailable"
                          : pct(m.metrics.coverage99.exception_rate, 1)}
                      </small>
                    </td>
                    <td className="numeric">
                      {metric(m.metrics.coverage95.kupiec_p_value, 3)} /{" "}
                      {metric(m.metrics.coverage99.kupiec_p_value, 3)}
                    </td>
                    <td className="numeric">
                      {m.execution_seconds.toFixed(3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="panel-footnote">
            {comparison.data.policy} QLIKE uses log(h) + realized return²/h on
            variance; negative values are valid. MSE and MAE use decimal
            variance units. A single squared return is a noisy volatility proxy.
          </p>
        </section>
      )}
      <section className="panel research-forecast-chart">
        <div className="panel-heading">
          <div>
            <h2>Out-of-sample volatility forecast comparison</h2>
            <p>
              Daily standard deviation forecasts versus observed |daily return|
              proxy · common forecast horizon
            </p>
          </div>
          <Activity size={17} />
        </div>
        <div className="research-chart-legend">
          <span style={{ color: "#8a9da8" }}>Observed absolute return</span>
          {kinds.map((k) => (
            <span key={k} style={{ color: modelColors[k] }}>
              {modelNames[k]}
            </span>
          ))}
        </div>
        <div className="research-chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={series.data}
              margin={{ left: 0, right: 25, top: 12, bottom: 12 }}
            >
              <CartesianGrid stroke="#253137" vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={(d) => dateLabel(d).slice(0, 6)}
                minTickGap={65}
                tick={{ fill: "#87959c", fontSize: 10 }}
              />
              <YAxis
                tickFormatter={(v) => pct(Number(v), 1)}
                tick={{ fill: "#87959c", fontSize: 10 }}
              />
              <Tooltip
                contentStyle={chartTooltip}
                labelFormatter={(v) => dateLabel(String(v))}
                formatter={(v, name) => [pct(Number(v), 3), name]}
              />
              <Line
                dataKey="realized_volatility_proxy"
                name="Observed |return| proxy"
                stroke="#8395a0"
                dot={false}
                strokeOpacity={0.55}
                strokeDasharray="3 3"
                isAnimationActive={false}
              />
              {kinds.map((k) => (
                <Line
                  key={k}
                  dataKey={k}
                  name={modelNames[k]}
                  stroke={modelColors[k]}
                  dot={false}
                  strokeWidth={1.6}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
      <section className="panel research-errors">
        <div className="panel-heading">
          <div>
            <h2>Rolling forecast loss diagnostics</h2>
            <p>
              20-target average QLIKE within the selected window; gaps require
              20 consecutive valid predictions. Lower is better.
            </p>
          </div>
        </div>
        <div className="research-chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={series.data}
              margin={{ left: 0, right: 25, top: 12, bottom: 12 }}
            >
              <CartesianGrid stroke="#253137" vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={(d) => dateLabel(d).slice(0, 6)}
                minTickGap={65}
                tick={{ fill: "#87959c", fontSize: 10 }}
              />
              <YAxis tick={{ fill: "#87959c", fontSize: 10 }} />
              <Tooltip
                contentStyle={chartTooltip}
                formatter={(v, name) => [metric(Number(v)), name]}
              />
              {kinds.map((k) => (
                <Line
                  key={k}
                  dataKey={`qlike20_${k}`}
                  name={modelNames[k]}
                  stroke={modelColors[k]}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
      <section className="panel research-calibration">
        <div className="panel-heading">
          <div>
            <h2>Conditional VaR backtesting</h2>
            <p>
              Fixed saved-snapshot INR notional · positive loss · strict
              realized loss &gt; forecast VaR exception
            </p>
          </div>
          <div className="research-chart-selectors">
            <select
              aria-label="Research selected model"
              value={kind}
              onChange={(v) => setKind(v.target.value as ModelKind)}
            >
              {kinds.map((k) => (
                <option key={k} value={k}>
                  {modelNames[k]}
                </option>
              ))}
            </select>
            <select
              aria-label="Research VaR confidence"
              value={confidence}
              onChange={(v) => setConfidence(v.target.value)}
            >
              <option value="95">95% VaR</option>
              <option value="99">99% VaR</option>
            </select>
          </div>
        </div>
        <div className="research-chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={series.data}
              margin={{ left: 0, right: 25, top: 15, bottom: 12 }}
            >
              <CartesianGrid stroke="#253137" vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={(d) => dateLabel(d).slice(0, 6)}
                minTickGap={65}
                tick={{ fill: "#87959c", fontSize: 10 }}
              />
              <YAxis
                tickFormatter={(v) => money(Number(v), true)}
                tick={{ fill: "#87959c", fontSize: 9 }}
              />
              <Tooltip
                contentStyle={chartTooltip}
                labelFormatter={(v) => dateLabel(String(v))}
                formatter={(v, name) => [money(Number(v)), name]}
              />
              <ReferenceLine y={0} stroke="#445e6b" />
              <Line
                dataKey="realized_loss"
                name="Realized loss"
                stroke="#8aa1b0"
                strokeWidth={1}
                dot={(props: {
                  cx?: number;
                  cy?: number;
                  payload?: ResearchPoint;
                }) => (
                  <circle
                    key={props.payload?.date}
                    cx={props.cx}
                    cy={props.cy}
                    r={props.payload?.[exception] === true ? 4 : 0}
                    fill="#ef9a9a"
                  />
                )}
                isAnimationActive={false}
              />
              <Line
                dataKey={threshold}
                name={`${modelNames[kind]} ${confidence}% VaR`}
                stroke={modelColors[kind]}
                dot={false}
                strokeWidth={2}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
        {coverage && (
          <>
            <div className="simulation-stats">
              <div>
                Observed exceptions
                <strong>
                  {coverage.exceptions}/{coverage.observations} ·{" "}
                  {coverage.exception_rate == null
                    ? "Unavailable"
                    : pct(coverage.exception_rate, 1)}
                </strong>
              </div>
              <div>
                Nominal frequency / count
                <strong>
                  {pct(coverage.nominal_rate, 1)} /{" "}
                  {coverage.expected_exceptions.toFixed(2)}
                </strong>
              </div>
              <div>
                Kupiec p / independence p
                <strong>
                  {metric(coverage.kupiec_p_value, 4)} /{" "}
                  {metric(coverage.independence_p_value, 4)}
                </strong>
              </div>
              <div>
                Conditional coverage p
                <strong>{metric(coverage.conditional_p_value, 4)}</strong>
              </div>
            </div>
            <ul className="risk-warnings comparison-warnings">
              {coverage.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </>
        )}
      </section>
      {regimes.error && <ErrorNotice error={regimes.error} />}{" "}
      {regimes.data && (
        <section className="panel research-regimes">
          <div className="panel-heading">
            <div>
              <h2>Volatility regime explorer</h2>
              <p>
                Portfolio regime indicator at each forecast origin; thresholds
                fixed through {regimes.data.estimated_through}
              </p>
            </div>
            <ShieldCheck size={17} />
          </div>
          <div className="research-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={regimes.data.rows}
                margin={{ left: 0, right: 25, top: 15, bottom: 10 }}
              >
                <CartesianGrid stroke="#253137" vertical={false} />
                <XAxis
                  dataKey="target"
                  tickFormatter={(d) => dateLabel(d).slice(0, 6)}
                  minTickGap={65}
                  tick={{ fill: "#87959c", fontSize: 10 }}
                />
                <YAxis
                  tickFormatter={(v) => Number(v).toExponential(1)}
                  tick={{ fill: "#87959c", fontSize: 9 }}
                />
                <Tooltip
                  contentStyle={chartTooltip}
                  labelFormatter={(v) => dateLabel(String(v))}
                  formatter={(v) => [
                    scientific(Number(v)),
                    "Lagged daily second moment",
                  ]}
                />
                <ReferenceLine
                  y={regimes.data.thresholds.low_upper}
                  stroke="#64d9b4"
                  strokeDasharray="4 3"
                />
                <ReferenceLine
                  y={regimes.data.thresholds.high_lower}
                  stroke="#df8a96"
                  strokeDasharray="4 3"
                />
                <Line
                  dataKey="lagged_variance"
                  stroke="#8c9faa"
                  dot={(props: {
                    cx?: number;
                    cy?: number;
                    payload?: { regime: string };
                  }) => (
                    <circle
                      cx={props.cx}
                      cy={props.cy}
                      r={2.5}
                      fill={
                        props.payload?.regime === "high"
                          ? "#df8a96"
                          : props.payload?.regime === "low"
                            ? "#64d9b4"
                            : "#e3b773"
                      }
                    />
                  )}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>REGIME / MODEL</th>
                  <th className="numeric">OBSERVATIONS</th>
                  <th className="numeric">QLIKE</th>
                  <th className="numeric">95% / 99% EXCEPTIONS</th>
                </tr>
              </thead>
              <tbody>
                {regimes.data.metrics.map((r) => (
                  <tr key={`${r.regime}-${r.model_kind}`}>
                    <td>
                      {r.regime} · {modelNames[r.model_kind]}
                    </td>
                    <td className="numeric">{r.metrics.observations}</td>
                    <td className="numeric">{metric(r.metrics.qlike)}</td>
                    <td className="numeric">
                      {r.metrics.coverage95.exceptions} /{" "}
                      {r.metrics.coverage99.exceptions}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="panel-footnote">
            {regimes.data.note} Regime statistics use the full saved test
            period; the window control above applies to the matched leaderboard
            and forecast/calibration charts.
          </p>
        </section>
      )}
      {selected && (
        <ResearchExplanation
          key={selected.id}
          model={selected}
          experiment={e}
        />
      )}
      {comparison.data && (
        <section className="panel research-uncertainty">
          <div className="panel-heading">
            <div>
              <h2>Challenger trade-offs & uncertainty</h2>
              <p>
                Paired LightGBM-minus-benchmark QLIKE · circular moving-block
                bootstrap
              </p>
            </div>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>BENCHMARK</th>
                  <th className="numeric">MEAN QLIKE DIFFERENCE</th>
                  <th className="numeric">DESCRIPTIVE 95% INTERVAL</th>
                </tr>
              </thead>
              <tbody>
                {comparison.data.uncertainty.map((u) => (
                  <tr key={u.benchmark}>
                    <td>{u.benchmark}</td>
                    <td className="numeric">
                      {u.available
                        ? metric(u.mean_qlike_difference)
                        : "Unavailable"}
                    </td>
                    <td className="numeric">
                      {u.interval95?.map((v) => metric(v)).join(" to ") ??
                        u.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="risk-warnings comparison-warnings">
            {comparison.data.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </section>
      )}
      <section className="panel research-audit">
        <div className="panel-heading">
          <div>
            <h2>Research protocol & provenance</h2>
            <p>
              Dataset, feature availability, target windows, source assertions
              and runtime
            </p>
          </div>
        </div>
        <div className="evidence-body">
          <dl className="audit-grid">
            <div>
              <dt>Development training</dt>
              <dd>
                {e.protocol.train_start} — {e.protocol.development_train_end}
              </dd>
            </div>
            <div>
              <dt>Validation</dt>
              <dd>
                {e.protocol.validation_start} — {e.protocol.validation_end}
              </dd>
            </div>
            <div>
              <dt>Final evaluation</dt>
              <dd>
                {e.protocol.test_start} — {e.protocol.test_end}
              </dd>
            </div>
            <div>
              <dt>Target / mean</dt>
              <dd>One-day return² / zero mean</dd>
            </div>
          </dl>
          <div className="hash-note">
            Dataset SHA-256 {e.dataset_hash}
            <br />
            Feature version {e.feature_version} · code{" "}
            {e.runtime.git_commit ?? "Unavailable"}
          </div>
          <ul className="risk-warnings">
            <li>{e.protocol.selection_policy}</li>
            <li>{e.protocol.online_update_policy}</li>
            <li>{e.dataset.availability_assumption}</li>
            <li>{e.dataset.universe_limitation}</li>
            {e.dataset.unavailable_features.map((w) => (
              <li key={w}>{w}</li>
            ))}
            {e.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
          <details>
            <summary>Full parameters and runtime versions</summary>
            <pre>
              {JSON.stringify(
                {
                  parameters: e.parameters,
                  protocol: e.protocol,
                  runtime: e.runtime,
                  features: e.dataset.features,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </div>
      </section>
    </div>
  );
}
