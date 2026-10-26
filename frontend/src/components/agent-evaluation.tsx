"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import { api } from "@/lib/api";
import type { EvaluationRun } from "@/lib/agent";
import { ErrorNotice } from "./error-notice";

export function AgentEvaluation({ ready }: { ready: boolean }) {
  const client = useQueryClient();
  const [active, setActive] = useState("");
  const runs = useQuery({
    queryKey: ["agent-evaluations"],
    queryFn: () => api<EvaluationRun[]>("/v1/agent/evaluation-runs"),
    enabled: ready,
    refetchInterval: (q) =>
      q.state.data?.some((r) => ["queued", "running"].includes(r.status))
        ? 1200
        : false,
  });
  const result = useQuery({
    queryKey: ["agent-evaluation", active],
    queryFn: () => api<EvaluationRun>(`/v1/agent/evaluation-runs/${active}`),
    enabled: !!active && ready,
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.status ?? "") ? 900 : false,
  });
  const start = useMutation({
    mutationFn: () =>
      api<EvaluationRun>("/v1/agent/evaluation-runs", { method: "POST" }),
    onSuccess: (r) => {
      setActive(r.id);
      void client.invalidateQueries({ queryKey: ["agent-evaluations"] });
    },
  });
  const payload = result.data?.payload;
  const busy = ["queued", "running"].includes(result.data?.status ?? "");
  return (
    <section className="panel agent-evaluation">
      <div className="panel-heading">
        <div>
          <h2>
            <FlaskConical size={17} />
            Agent evaluation dashboard
          </h2>
          <p>
            Executed deterministic synthetic workflows and safety probes · live
            AI quality remains unmeasured
          </p>
        </div>
        <button
          className="button secondary"
          disabled={!ready || busy || start.isPending}
          onClick={() => start.mutate()}
        >
          Run golden evaluation
        </button>
      </div>
      <div className="evidence-body">
        <label>
          Saved evaluation
          <select
            aria-label="Saved agent evaluation"
            value={active}
            onChange={(e) => setActive(e.target.value)}
          >
            <option value="">Select an executed run</option>
            {runs.data?.map((r) => (
              <option key={r.id} value={r.id}>
                {r.id.slice(0, 8)} · {r.status} ·{" "}
                {new Date(r.created_at).toLocaleString("en-GB")}
              </option>
            ))}
          </select>
        </label>
        <p className="form-help">
          The suite uses an isolated synthetic fixture workspace. It never reads
          private broker data or makes paid AI requests. Thresholds are fixed in
          the audit; failed cases are retained. At most two runs per hour per
          session.
        </p>
        {start.error && <ErrorNotice error={start.error} />}
        {runs.error && <ErrorNotice error={runs.error} />}
        {result.error && <ErrorNotice error={result.error} />}
        {payload && (
          <>
            <p role="status">
              {result.data?.status.toUpperCase()} · {payload.completed_cases}/
              {payload.total_cases} cases
              {payload.acceptance_passed !== undefined &&
                ` · acceptance ${payload.acceptance_passed ? "passed" : "failed"}`}
            </p>
            {payload.error && <p className="negative">{payload.error}</p>}
            {payload.metrics && (
              <div className="agent-score-grid">
                {Object.entries(payload.metrics).map(([name, m]) => (
                  <article key={name}>
                    <small>{name.replaceAll("_", " ")}</small>
                    <strong>
                      {m.rate === null
                        ? "Unavailable"
                        : `${(m.rate * 100).toFixed(1)}%`}
                    </strong>
                    <span>
                      {m.passed} / {m.total} applicable cases
                    </span>
                  </article>
                ))}
              </div>
            )}
            {payload.efficiency && (
              <div className="simulation-stats">
                <div>
                  Executed tools<strong>{payload.efficiency.tool_calls}</strong>
                </div>
                <div>
                  Suite duration / median case
                  <strong>
                    {payload.efficiency.elapsed_seconds.toFixed(2)}s /{" "}
                    {payload.efficiency.median_case_seconds.toFixed(3)}s
                  </strong>
                </div>
                <div>
                  LLM tokens
                  <strong>
                    {payload.efficiency.input_tokens ??
                      "Unavailable · no live LLM"}
                  </strong>
                </div>
                <div>
                  Provider cost
                  <strong>
                    {payload.efficiency.estimated_cost_usd ?? "Unavailable"}
                  </strong>
                </div>
              </div>
            )}
            {payload.cases && (
              <div className="agent-evaluation-cases">
                {payload.cases.map((c) => (
                  <details key={c.id}>
                    <summary>
                      <span className={c.passed ? "positive" : "negative"}>
                        {c.passed ? "PASS" : "FAIL"}
                      </span>{" "}
                      {c.id} · {c.category} · {c.question}
                    </summary>
                    <p>
                      {c.failure ?? "All applicable checks passed."} ·{" "}
                      {c.elapsed_seconds.toFixed(3)} seconds
                    </p>
                    <pre>
                      {JSON.stringify(
                        {
                          expected_tools: c.expected_tools,
                          checks: c.checks,
                          actual: c.actual,
                        },
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                ))}
              </div>
            )}
            <ul className="risk-warnings">
              {payload.limitations?.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
            <details>
              <summary>Dataset and runtime provenance</summary>
              <pre>
                {JSON.stringify(
                  {
                    dataset_sha256: payload.dataset_sha256,
                    runtime: payload.runtime,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </>
        )}
        {!payload && (
          <p className="empty-state">
            No evaluation selected. Run the suite to see actual results.
          </p>
        )}
      </div>
    </section>
  );
}
