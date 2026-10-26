"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  FlaskConical,
  GitCompareArrows,
  LoaderCircle,
  Play,
  RotateCcw,
} from "lucide-react";
import { api, type Dataset } from "@/lib/api";
import type { RiskSelection } from "@/lib/advanced-risk";
import {
  modelNames,
  metric,
  type Experiment,
  type ExperimentComparison,
  type Job,
  type ResearchParameters,
} from "@/lib/research";
import { ErrorNotice } from "./error-notice";
import { ResearchResults } from "./research-results";

export function ResearchTerminal({
  selection,
  datasets,
  ready,
}: {
  selection: RiskSelection;
  datasets: Dataset[];
  ready: boolean;
}) {
  const queryClient = useQueryClient();
  const [active, setActive] = useState("");
  const [form, setForm] = useState({
    scheme: "expanding",
    history: "1260",
    initial: "240",
    validation: "60",
    test: "100",
    refit: "20",
    trainWindow: "252",
    rolling: "60",
    decay: "0.94",
    seed: "42",
    trees: "120",
    search: "3",
    features: "full",
    context: "",
    benchmark: "",
  });
  const [selected, setSelected] = useState<string[]>([]);
  const jobs = useQuery({
    queryKey: ["research-experiments"],
    queryFn: () => api<Job[]>("/v1/ml/experiments"),
    enabled: ready,
    refetchInterval: (query) =>
      query.state.data?.some(
        (j) => j.status === "running" || j.status === "queued",
      )
        ? 1000
        : false,
  });
  const experiment = useQuery({
    queryKey: ["research-experiment", active],
    queryFn: () => api<Experiment>(`/v1/ml/experiments/${active}`),
    enabled: ready && !!active,
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.status ?? "")
        ? 750
        : false,
  });
  function parameters(): ResearchParameters {
    return {
      mode: selection.mode,
      ...(selection.dataset_id ? { dataset_id: selection.dataset_id } : {}),
      scheme: form.scheme as "expanding" | "rolling",
      history_window: Number(form.history),
      initial_train: Number(form.initial),
      validation_size: Number(form.validation),
      test_size: Number(form.test),
      refit_every: Number(form.refit),
      rolling_train_window: Number(form.trainWindow),
      rolling_window: Number(form.rolling) as 20 | 60,
      ewma_lambda: Number(form.decay),
      seed: Number(form.seed),
      max_trees: Number(form.trees),
      search_candidates: Number(form.search),
      feature_set: form.features as "basic" | "full",
      ...(form.context
        ? {
            context_dataset_id: form.context,
            benchmark_instrument: form.benchmark,
          }
        : {}),
    };
  }
  const train = useMutation({
    mutationFn: () =>
      api<Job>("/v1/ml/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parameters()),
      }),
    onSuccess: (job) => {
      setActive(job.id);
      void queryClient.invalidateQueries({
        queryKey: ["research-experiments"],
      });
    },
  });
  const reproduce = useMutation({
    mutationFn: () =>
      api<Job>(`/v1/ml/experiments/${active}/reproduce`, { method: "POST" }),
    onSuccess: (job) => {
      setActive(job.id);
      void queryClient.invalidateQueries({
        queryKey: ["research-experiments"],
      });
    },
  });
  const compare = useMutation({
    mutationFn: () =>
      api<ExperimentComparison>("/v1/ml/experiments/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ experiment_ids: selected }),
      }),
  });
  const report = useMutation({
    mutationFn: () =>
      api<{ markdown: string }>(`/v1/ml/experiments/${active}/report`),
    onSuccess: (result) => {
      const url = URL.createObjectURL(
        new Blob([result.markdown], { type: "text/markdown" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `vantage-research-${active}.md`;
      link.click();
      URL.revokeObjectURL(url);
    },
  });
  const jobActive =
    experiment.data?.status === "queued" ||
    experiment.data?.status === "running";
  const set = (key: keyof typeof form, value: string) =>
    setForm((previous) => ({ ...previous, [key]: value }));
  return (
    <div className="research-terminal">
      <section className="panel research-protocol">
        <div className="panel-heading">
          <div>
            <h2>
              <FlaskConical size={18} />
              Conditional volatility research
            </h2>
            <p>
              Four challengers · one-day portfolio variance · chronological
              validation and walk-forward evaluation
            </p>
          </div>
          <span className="subtle-badge">PHASE 3 · READ ONLY</span>
        </div>
        <div className="research-question">
          Can LightGBM improve risk calibration over rolling, EWMA and GARCH?
          This terminal measures the trade-offs; it never assigns a winner
          automatically.
        </div>
        <form
          className="research-form"
          onSubmit={(e) => {
            e.preventDefault();
            train.mutate();
          }}
        >
          <div className="research-form-grid">
            <label>
              Training scheme
              <select
                aria-label="Research training scheme"
                value={form.scheme}
                onChange={(e) => set("scheme", e.target.value)}
              >
                <option value="expanding">Expanding window</option>
                <option value="rolling">Rolling window</option>
              </select>
            </label>
            <label>
              Maximum history returns
              <input
                aria-label="Research maximum history"
                type="number"
                min="400"
                max="5000"
                step="1"
                value={form.history}
                onChange={(e) => set("history", e.target.value)}
                required
              />
            </label>
            <label>
              Initial training minimum
              <input
                aria-label="Research initial training"
                type="number"
                min="160"
                max="2000"
                value={form.initial}
                onChange={(e) => set("initial", e.target.value)}
                required
              />
            </label>
            <label>
              Validation observations
              <input
                aria-label="Research validation size"
                type="number"
                min="30"
                max="252"
                value={form.validation}
                onChange={(e) => set("validation", e.target.value)}
                required
              />
            </label>
            <label>
              Final test observations
              <input
                aria-label="Research test size"
                type="number"
                min="20"
                max="500"
                value={form.test}
                onChange={(e) => set("test", e.target.value)}
                required
              />
            </label>
            <label>
              Refit every (origins)
              <input
                aria-label="Research refit interval"
                type="number"
                min="5"
                max="126"
                value={form.refit}
                onChange={(e) => set("refit", e.target.value)}
                required
              />
            </label>
            <label>
              Rolling training length
              <input
                aria-label="Research rolling training length"
                type="number"
                min="160"
                max="2000"
                value={form.trainWindow}
                onChange={(e) => set("trainWindow", e.target.value)}
                required
              />
            </label>
            <label>
              Rolling benchmark
              <select
                aria-label="Rolling baseline window"
                value={form.rolling}
                onChange={(e) => set("rolling", e.target.value)}
              >
                <option value="20">20 daily returns</option>
                <option value="60">60 daily returns</option>
              </select>
            </label>
            <label>
              EWMA decay
              <input
                aria-label="EWMA decay"
                type="number"
                min="0.8"
                max="0.999"
                step="0.001"
                value={form.decay}
                onChange={(e) => set("decay", e.target.value)}
                required
              />
            </label>
            <label>
              Research seed
              <input
                aria-label="Research seed"
                type="number"
                min="0"
                max="2147483647"
                value={form.seed}
                onChange={(e) => set("seed", e.target.value)}
                required
              />
            </label>
            <label>
              Maximum boosting rounds
              <input
                aria-label="Maximum boosting rounds"
                type="number"
                min="20"
                max="300"
                value={form.trees}
                onChange={(e) => set("trees", e.target.value)}
                required
              />
            </label>
            <label>
              Validation candidates
              <select
                aria-label="Validation candidates"
                value={form.search}
                onChange={(e) => set("search", e.target.value)}
              >
                <option value="1">1 constrained configuration</option>
                <option value="2">2 constrained configurations</option>
                <option value="3">3 constrained configurations</option>
              </select>
            </label>
            <label>
              Feature set
              <select
                aria-label="Research feature set"
                value={form.features}
                onChange={(e) => set("features", e.target.value)}
              >
                <option value="full">Full lagged features</option>
                <option value="basic">Basic return / variance features</option>
              </select>
            </label>
          </div>
          {selection.mode === "kite" && (
            <details>
              <summary>Optional independently sourced benchmark</summary>
              <div className="stress-primary-controls">
                <label>
                  Aligned context dataset
                  <select
                    aria-label="Research benchmark dataset"
                    value={form.context}
                    onChange={(e) => set("context", e.target.value)}
                  >
                    <option value="">Unavailable / excluded</option>
                    {datasets.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.provenance.source}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Explicit benchmark instrument
                  <input
                    aria-label="Research benchmark instrument"
                    placeholder="NSE:PERMITTED_INDEX"
                    value={form.benchmark}
                    onChange={(e) => set("benchmark", e.target.value)}
                    required={!!form.context}
                  />
                </label>
              </div>
            </details>
          )}
          <p className="form-help">
            Features use information through each origin close; the target is
            the next observed daily return squared. Validation locks model
            choices before the test. Earlier test labels may enter later refits
            only after observation. Frozen current weights are retrospective,
            not reconstructed historical account performance.
          </p>
          <button
            className="button primary"
            disabled={!ready || train.isPending || jobActive}
          >
            {train.isPending ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <Play size={15} />
            )}
            Run controlled experiment
          </button>
        </form>
      </section>
      {train.error && <ErrorNotice error={train.error} />}{" "}
      {experiment.error && <ErrorNotice error={experiment.error} />}{" "}
      {experiment.data && (
        <>
          <section className="panel research-job" role="status">
            <div>
              <span
                className={`status-dot ${experiment.data.status === "failed" || experiment.data.status === "interrupted" ? "offline" : ""}`}
              />
              <strong>{experiment.data.status.toUpperCase()}</strong>
              <span>{experiment.data.stage}</span>
              <small>{experiment.data.progress}%</small>
            </div>
            <progress value={experiment.data.progress} max={100} />
            <p>
              Experiment {experiment.data.id} · model{" "}
              {experiment.data.model_version} ·{" "}
              {experiment.data.synthetic
                ? "SYNTHETIC DATA"
                : "PERMITTED IMPORT"}
            </p>
            {experiment.data.error && (
              <div className="error-notice">
                {experiment.data.error.code}: {experiment.data.error.message}
              </div>
            )}
            {experiment.data.reproduction_match !== null && (
              <div
                className={
                  experiment.data.reproduction_match
                    ? "research-reproduction positive"
                    : "research-reproduction negative"
                }
              >
                Saved-input reproduction match:{" "}
                {String(experiment.data.reproduction_match)}
              </div>
            )}
          </section>
          {(experiment.data.status === "completed" ||
            experiment.data.status === "partial") && (
            <>
              <div className="result-heading">
                <div>
                  <h2>Executed research evidence</h2>
                  <p>
                    {experiment.data.protocol.test_start} —{" "}
                    {experiment.data.protocol.test_end} ·{" "}
                    {experiment.data.dataset.return_observations} source returns
                    · {experiment.data.parameters.scheme} refits
                  </p>
                </div>
                <div className="heading-actions">
                  <button
                    className="button secondary"
                    onClick={() => report.mutate()}
                    disabled={report.isPending}
                  >
                    <BookOpen size={14} />
                    Download research report
                  </button>
                  <button
                    className="button secondary"
                    onClick={() => reproduce.mutate()}
                    disabled={reproduce.isPending || jobActive}
                  >
                    <RotateCcw size={14} />
                    Reproduce experiment
                  </button>
                </div>
              </div>
              {report.error && <ErrorNotice error={report.error} />}{" "}
              {reproduce.error && <ErrorNotice error={reproduce.error} />}
              <ResearchResults
                key={experiment.data.id}
                experiment={experiment.data}
              />
            </>
          )}
        </>
      )}
      <section className="panel research-history">
        <div className="panel-heading">
          <div>
            <h2>Experiment history</h2>
            <p>
              Private saved configurations, datasets, code versions and
              evaluation evidence
            </p>
          </div>
          <button
            className="button secondary"
            disabled={selected.length < 2 || compare.isPending}
            onClick={() => compare.mutate()}
          >
            <GitCompareArrows size={14} />
            Compare experiments ({selected.length})
          </button>
        </div>
        {jobs.error && <ErrorNotice error={jobs.error} />}
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>COMPARE</th>
                <th>EXPERIMENT</th>
                <th>STATUS</th>
                <th>DATASET</th>
                <th>CREATED (IST)</th>
                <th>RESULTS</th>
              </tr>
            </thead>
            <tbody>
              {jobs.data?.map((j) => (
                <tr key={j.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Compare experiment ${j.id}`}
                      checked={selected.includes(j.id)}
                      disabled={
                        (j.status !== "completed" && j.status !== "partial") ||
                        (!selected.includes(j.id) && selected.length >= 4)
                      }
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, j.id]
                            : selected.filter((id) => id !== j.id),
                        )
                      }
                    />
                  </td>
                  <td>
                    {j.id.slice(0, 8)}
                    <small className="cell-note">
                      {j.synthetic ? "Synthetic" : "Imported"}
                      {j.reproduction_of ? " · reproduction" : ""}
                    </small>
                  </td>
                  <td>{j.status}</td>
                  <td className="numeric">{j.dataset_hash.slice(0, 12)}</td>
                  <td>
                    {new Date(j.created_at).toLocaleString("en-GB", {
                      timeZone: "Asia/Kolkata",
                    })}
                  </td>
                  <td>
                    <button
                      className="text-button"
                      onClick={() => setActive(j.id)}
                    >
                      Load experiment
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {jobs.data?.length === 0 && (
            <div className="empty-state">
              No executed research in this session. Run an experiment to create
              actual evaluation results.
            </div>
          )}
        </div>
      </section>
      {compare.error && <ErrorNotice error={compare.error} />}{" "}
      {compare.data && (
        <section className="panel experiment-comparison">
          <div className="panel-heading">
            <div>
              <h2>Experiment configuration comparison</h2>
              <p>{compare.data.warnings.join(" ")}</p>
            </div>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>EXPERIMENT</th>
                  <th>SCHEME / SEED</th>
                  <th>FEATURE SET</th>
                  <th>TEST DATES</th>
                  <th>MODEL</th>
                  <th className="numeric">MATCHED QLIKE</th>
                </tr>
              </thead>
              <tbody>
                {compare.data.experiments.flatMap(
                  (e) =>
                    e.comparison?.models.map((m) => (
                      <tr key={`${e.id}-${m.kind}`}>
                        <td>{e.id.slice(0, 8)}</td>
                        <td>
                          {e.parameters.scheme} / {e.parameters.seed}
                        </td>
                        <td>{e.parameters.feature_set}</td>
                        <td>
                          {e.protocol.test_start}–{e.protocol.test_end}
                        </td>
                        <td>{modelNames[m.kind]}</td>
                        <td className="numeric">{metric(m.metrics.qlike)}</td>
                      </tr>
                    )) ?? [],
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
