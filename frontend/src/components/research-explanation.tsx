"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, ShieldCheck, Sparkles } from "lucide-react";
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
import { api, pct } from "@/lib/api";
import { chartTooltip } from "@/lib/chart-theme";
import {
  metric,
  modelNames,
  scientific,
  type Experiment,
  type Explanation,
  type ForecastModel,
} from "@/lib/research";
import { ErrorNotice } from "./error-notice";

export function ResearchExplanation({
  model,
  experiment,
}: {
  model: ForecastModel;
  experiment: Experiment;
}) {
  const queryClient = useQueryClient();
  const [target, setTarget] = useState("");
  const [role, setRole] = useState(model.role);
  const [rationale, setRationale] = useState("");
  const [ack, setAck] = useState(false);
  const explanation = useMutation({
    mutationFn: () =>
      api<Explanation>(
        `/v1/ml/models/${model.id}/explain${target ? `?target=${target}` : ""}`,
      ),
  });
  const governance = useMutation({
    mutationFn: () =>
      api<ForecastModel>(`/v1/ml/models/${model.id}/governance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, rationale, acknowledge_limitations: ack }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["research-models", experiment.id],
      });
      void queryClient.invalidateQueries({
        queryKey: ["research-comparison", experiment.id],
      });
    },
  });
  return (
    <div className="research-explanation">
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Model evidence · {modelNames[model.kind]}</h2>
            <p>
              {model.status} · current role {model.role} ·{" "}
              {model.id.slice(0, 8)}
            </p>
          </div>
          {model.artifact_files.length > 0 && (
            <a
              className="button secondary"
              href={`/api/v1/ml/models/${model.id}/artifact`}
            >
              <Download size={14} />
              Download saved artifacts
            </a>
          )}
        </div>
        <div className="evidence-body">
          <ul className="risk-warnings">
            {model.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
          <details>
            <summary>Saved configuration and refit chronology</summary>
            <pre>
              {JSON.stringify(
                { config: model.config, refits: model.refits },
                null,
                2,
              )}
            </pre>
          </details>
        </div>
      </section>
      {model.kind === "lightgbm" && (
        <>
          <div className="risk-detail-grid">
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Global LightGBM feature importance</h2>
                  <p>
                    Actual final-refit gain share; not causal influence or
                    past-origin explanations
                  </p>
                </div>
              </div>
              <div className="research-importance-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    layout="vertical"
                    data={[...model.global_importance]
                      .sort((a, b) => b.gain - a.gain)
                      .slice(0, 12)}
                    margin={{ left: 0, right: 30, top: 15, bottom: 10 }}
                  >
                    <CartesianGrid stroke="#253137" horizontal={false} />
                    <XAxis
                      type="number"
                      tickFormatter={(v) => pct(Number(v), 0)}
                      tick={{ fill: "#87959c", fontSize: 9 }}
                    />
                    <YAxis
                      type="category"
                      dataKey="feature"
                      width={155}
                      tick={{ fill: "#a3b6c0", fontSize: 9 }}
                    />
                    <Tooltip
                      contentStyle={chartTooltip}
                      formatter={(v) => [pct(Number(v), 2), "Gain share"]}
                    />
                    <Bar
                      dataKey="gain_share"
                      fill="#64d9b4"
                      isAnimationActive={false}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Feature distribution drift</h2>
                  <p>
                    Training reference from the first test refit · diagnostic
                    only
                  </p>
                </div>
              </div>
              <div className="table-scroll research-drift-table">
                <table>
                  <thead>
                    <tr>
                      <th>FEATURE</th>
                      <th className="numeric">STANDARDIZED MEAN Δ</th>
                      <th className="numeric">OUTSIDE TRAIN 5–95%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {model.drift.map((d) => (
                      <tr key={d.feature}>
                        <td>{d.feature}</td>
                        <td className="numeric">
                          {metric(d.standardized_mean_difference, 3)}
                        </td>
                        <td className="numeric">
                          {pct(d.outside_training_5_95_fraction, 1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
          <section className="panel research-local-explanation">
            <div className="panel-heading">
              <div>
                <h2>
                  <Sparkles size={17} />
                  Saved prediction explanation
                </h2>
                <p>
                  Built-in LightGBM TreeSHAP on the exact saved model and origin
                  feature values
                </p>
              </div>
            </div>
            <form
              className="research-explain-controls"
              onSubmit={(event) => {
                event.preventDefault();
                explanation.mutate();
              }}
            >
              <label>
                Target observation (blank = latest scored)
                <input
                  aria-label="Explanation target date"
                  type="date"
                  min={experiment.protocol.test_start}
                  max={experiment.protocol.test_end}
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                />
              </label>
              <button
                className="button secondary"
                disabled={explanation.isPending}
              >
                Explain saved prediction
              </button>
            </form>
            {explanation.error && <ErrorNotice error={explanation.error} />}{" "}
            {explanation.data && (
              <div className="evidence-body">
                <div className="simulation-stats">
                  <div>
                    Origin / target
                    <strong>
                      {explanation.data.origin} / {explanation.data.target}
                    </strong>
                  </div>
                  <div>
                    Forecast variance
                    <strong>
                      {scientific(explanation.data.forecast_variance)}
                    </strong>
                  </div>
                  <div>
                    Bias / floor adjustment
                    <strong>
                      {scientific(explanation.data.base_variance)} /{" "}
                      {scientific(explanation.data.floor_adjustment)}
                    </strong>
                  </div>
                  <div>
                    Reconstruction residual
                    <strong>
                      {scientific(explanation.data.reconstruction_residual)}
                    </strong>
                  </div>
                </div>
                <div className="research-importance-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      layout="vertical"
                      data={explanation.data.features.slice(0, 12)}
                      margin={{ left: 0, right: 25, top: 15, bottom: 10 }}
                    >
                      <CartesianGrid stroke="#253137" horizontal={false} />
                      <XAxis
                        type="number"
                        tickFormatter={(v) => Number(v).toExponential(1)}
                        tick={{ fill: "#87959c", fontSize: 9 }}
                      />
                      <YAxis
                        type="category"
                        dataKey="feature"
                        width={155}
                        tick={{ fill: "#a3b6c0", fontSize: 9 }}
                      />
                      <Tooltip
                        contentStyle={chartTooltip}
                        formatter={(v) => [
                          scientific(Number(v)),
                          "Variance contribution",
                        ]}
                      />
                      <ReferenceLine x={0} stroke="#6c8594" />
                      <Bar
                        dataKey="variance_contribution"
                        isAnimationActive={false}
                      >
                        {explanation.data.features.slice(0, 12).map((f) => (
                          <Cell
                            key={f.feature}
                            fill={
                              f.variance_contribution < 0
                                ? "#df8a96"
                                : "#64d9b4"
                            }
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>FEATURE</th>
                        <th className="numeric">MODEL INPUT</th>
                        <th className="numeric">
                          CONTRIBUTION TO RAW VARIANCE
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {explanation.data.features.map((f) => (
                        <tr key={f.feature}>
                          <td>{f.feature}</td>
                          <td className="numeric">
                            {scientific(f.model_input)}
                          </td>
                          <td className="numeric">
                            {scientific(f.variance_contribution)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <details>
                  <summary>
                    One-training-standard-deviation feature sensitivity
                  </summary>
                  <pre>
                    {JSON.stringify(explanation.data.sensitivity, null, 2)}
                  </pre>
                </details>
                <p className="panel-footnote">{explanation.data.note}</p>
              </div>
            )}
          </section>
        </>
      )}
      <section className="panel research-governance">
        <div className="panel-heading">
          <div>
            <h2>
              <ShieldCheck size={17} />
              Documented model-role review
            </h2>
            <p>
              A champion designation requires recorded evaluation, at least 100
              common observations and an explicit rationale; it does not
              establish superiority.
            </p>
          </div>
        </div>
        <form
          className="research-review-form"
          onSubmit={(event) => {
            event.preventDefault();
            governance.mutate();
          }}
        >
          <label>
            Desired role
            <select
              aria-label="Research model role"
              value={role}
              onChange={(e) => setRole(e.target.value as typeof role)}
            >
              <option value="benchmark">Benchmark</option>
              <option value="candidate">Candidate</option>
              <option value="champion">Champion for this experiment</option>
            </select>
          </label>
          <label>
            Evaluation rationale
            <textarea
              aria-label="Model review rationale"
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              minLength={20}
              maxLength={2000}
              required
              rows={3}
              placeholder="Review QLIKE, calibration, regime stability, complexity and data limitations."
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
            />
            I acknowledge the evaluation and data limitations; this is a
            research role, not trading authorization.
          </label>
          <button
            className="button secondary"
            disabled={!ack || rationale.length < 20 || governance.isPending}
          >
            Save documented role review
          </button>
        </form>
        {governance.error && <ErrorNotice error={governance.error} />}{" "}
        {governance.data && (
          <div className="success-notice">
            Documented model role saved: {governance.data.role}
          </div>
        )}
        <div className="evidence-body">
          <details>
            <summary>Role-review history</summary>
            <pre>
              {JSON.stringify(
                governance.data?.governance ?? model.governance,
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
