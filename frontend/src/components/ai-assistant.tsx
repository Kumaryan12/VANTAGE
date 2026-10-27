"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  CheckCheck,
  FileSearch,
  LoaderCircle,
  Play,
  Square,
} from "lucide-react";
import { api } from "@/lib/api";
import type { RiskSelection } from "@/lib/advanced-risk";
import type { OptimizationJob } from "@/lib/optimization";
import type { Job } from "@/lib/research";
import {
  factValue,
  modelQuestion,
  type AgentActivity,
  type AgentDetail,
  type AgentEvidence,
  type AgentJob,
  type AIStatus,
} from "@/lib/agent";
import { ErrorNotice } from "./error-notice";
import { CitationEvidence, DocumentLibrary } from "./document-library";
import { AgentEvaluation } from "./agent-evaluation";

export function AIAssistant({
  selection,
  ready,
}: {
  selection: RiskSelection;
  ready: boolean;
}) {
  const client = useQueryClient();
  const [question, setQuestion] = useState(modelQuestion);
  const [engine, setEngine] = useState("demo");
  const [consent, setConsent] = useState(false);
  const [experiment, setExperiment] = useState("");
  const [active, setActive] = useState("");
  const [optimization, setOptimization] = useState("");
  const optimizations = useQuery({
    queryKey: ["optimization-history"],
    queryFn: () => api<OptimizationJob[]>("/v1/optimization/runs"),
    enabled: ready,
  });
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const status = useQuery({
    queryKey: ["ai-status"],
    queryFn: () => api<AIStatus>("/v1/agent/status"),
    enabled: ready,
  });
  const experiments = useQuery({
    queryKey: ["research-experiments"],
    queryFn: () => api<Job[]>("/v1/ml/experiments"),
    enabled: ready,
  });
  const history = useQuery({
    queryKey: ["agent-history"],
    queryFn: () => api<AgentJob[]>("/v1/agent/investigations"),
    enabled: ready,
    refetchInterval: (query) =>
      query.state.data?.some((j) => ["queued", "running"].includes(j.status))
        ? 800
        : false,
  });
  const result = useQuery({
    queryKey: ["agent", active],
    queryFn: () => api<AgentDetail>(`/v1/agent/investigations/${active}`),
    enabled: ready && !!active,
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.status ?? "")
        ? 500
        : false,
  });
  const busy = ["queued", "running"].includes(result.data?.status ?? "");
  const trace = useQuery({
    queryKey: ["agent-trace", active, result.data?.status],
    queryFn: () =>
      api<AgentActivity[]>(`/v1/agent/investigations/${active}/trace`),
    enabled: !!active,
    refetchInterval: busy ? 700 : false,
  });
  const evidence = useQuery({
    queryKey: ["agent-evidence", active, result.data?.status],
    queryFn: () =>
      api<AgentEvidence[]>(`/v1/agent/investigations/${active}/evidence`),
    enabled: !!active,
    refetchInterval: busy ? 700 : false,
  });
  const start = useMutation({
    mutationFn: () =>
      api<AgentJob>("/v1/agent/investigate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          engine,
          mode: selection.mode,
          dataset_id: selection.dataset_id ?? null,
          experiment_id: experiment || null,
          optimization_run_id: optimization || null,
          document_ids: documentIds,
          confidence: selection.confidence,
          window: selection.window,
          external_data_consent: consent,
        }),
      }),
    onSuccess: (job) => {
      setActive(job.id);
      void client.invalidateQueries({ queryKey: ["agent-history"] });
    },
  });
  const cancel = useMutation({
    mutationFn: () =>
      api<AgentJob>(`/v1/agent/investigations/${active}/cancel`, {
        method: "POST",
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["agent", active] });
    },
  });
  const answer = result.data?.answer;
  return (
    <div className="agent-terminal">
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>
              <Bot size={18} />
              AI financial investigation
            </h2>
            <p>
              Authorized tools · verified financial values · inspectable
              evidence
            </p>
          </div>
          <span className="subtle-badge">READ ONLY</span>
        </div>
        <div
          className={`agent-provider ${status.data?.configured ? "configured" : ""}`}
        >
          <strong>
            {status.data?.configured
              ? "Configured AI provider"
              : "AI provider not configured"}
          </strong>
          <p>
            {status.data?.message ?? "Checking backend provider availability…"}
          </p>
        </div>
        {status.error && <ErrorNotice error={status.error} />}
        <form
          className="agent-request"
          onSubmit={(e) => {
            e.preventDefault();
            start.mutate();
          }}
        >
          <div className="agent-request-controls">
            <label>
              Execution mode
              <select
                aria-label="Investigation execution mode"
                value={engine}
                onChange={(e) => setEngine(e.target.value)}
              >
                <option value="demo">
                  Deterministic demonstration · no LLM
                </option>
                <option value="llm" disabled={!status.data?.configured}>
                  Configured AI · {status.data?.model ?? "unavailable"}
                </option>
              </select>
            </label>
            <label>
              Research context
              <select
                aria-label="Investigation experiment"
                value={experiment}
                onChange={(e) => setExperiment(e.target.value)}
              >
                <option value="">Latest accessible completed experiment</option>
                {experiments.data
                  ?.filter((j) => ["completed", "partial"].includes(j.status))
                  .map((j) => (
                    <option key={j.id} value={j.id}>
                      {j.id.slice(0, 8)} ·{" "}
                      {j.synthetic ? "Synthetic" : "Imported"} ·{" "}
                      {new Date(j.created_at).toLocaleDateString("en-GB")}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <label>
            Optimization context
            <select
              aria-label="Investigation optimization"
              value={optimization}
              onChange={(e) => setOptimization(e.target.value)}
            >
              <option value="">
                No pinned optimization · new calculations use explicit question
                limits
              </option>
              {optimizations.data
                ?.filter(
                  (r) =>
                    ["completed", "partial"].includes(r.status) &&
                    r.synthetic === (selection.mode === "demo"),
                )
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.id.slice(0, 8)} · {r.kind} · {r.solver_status}
                  </option>
                ))}
            </select>
          </label>
          {experiments.data?.length === 0 && (
            <p className="form-help">
              No saved research is accessible in this session. Run an experiment
              in Quantitative Research first; results owned by an expired
              session cannot be reassigned.
            </p>
          )}
          <label>
            Investigation question
            <textarea
              aria-label="Investigation question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={4}
              minLength={8}
              maxLength={1600}
              required
            />
          </label>
          <button
            type="button"
            className="text-button"
            onClick={() => {
              setOptimization("");
              setQuestion(
                "Can we reduce portfolio volatility by 15% without selling more than 10% of the portfolio?",
              );
            }}
          >
            Risk-reduction feasibility example
          </button>
          {engine === "llm" && (
            <label className="agent-checkbox">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                required
              />
              Allow this request to send relevant redacted financial evidence to
              the configured external AI provider.
            </label>
          )}
          <div className="heading-actions">
            <button
              className="button primary"
              disabled={!ready || start.isPending || busy}
            >
              {start.isPending ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <Play size={15} />
              )}
              Start investigation
            </button>
            <button
              type="button"
              className="button secondary"
              onClick={() => setQuestion(modelQuestion)}
            >
              Model comparison example
            </button>
            <button
              type="button"
              className="button secondary"
              onClick={() =>
                setQuestion(
                  "Which holdings contribute most to my portfolio risk?",
                )
              }
            >
              Portfolio risk example
            </button>
            <button
              type="button"
              className="button secondary"
              onClick={() =>
                setQuestion(
                  "Why is my portfolio concentrated in technology stocks, and what happens if that sector falls 15%?",
                )
              }
            >
              Sector shock example
            </button>
            <button
              type="button"
              className="button secondary"
              onClick={() =>
                setQuestion(
                  "Summarize liquidity and debt risks in the uploaded annual report.",
                )
              }
            >
              Document research example
            </button>
            {busy && (
              <button
                type="button"
                className="button secondary"
                disabled={cancel.isPending}
                onClick={() => cancel.mutate()}
              >
                <Square size={13} />
                Cancel investigation
              </button>
            )}
          </div>
          <p className="form-help">
            The demonstration uses deterministic routing and actual authorized
            backend results. Live AI selects tools; the backend verifies all
            published values and citations. Neither mode can execute trades or
            change model governance.
          </p>
        </form>
      </section>
      {start.error && <ErrorNotice error={start.error} />}
      {cancel.error && <ErrorNotice error={cancel.error} />}
      {result.error && <ErrorNotice error={result.error} />}
      {result.data && (
        <section className="panel agent-status" role="status">
          <strong>{result.data.status.toUpperCase()}</strong>
          <span>{result.data.stage}</span>
          <small>
            {result.data.id} · {result.data.engine} ·{" "}
            {result.data.workflow_version}
          </small>
          {result.data.error && (
            <p className="negative">
              {result.data.error.code}: {result.data.error.message}
            </p>
          )}
        </section>
      )}
      {answer && (
        <section className="panel agent-answer">
          <div className="panel-heading">
            <div>
              <h2>{answer.title}</h2>
              <p>{answer.execution_mode}</p>
            </div>
            <span className="verification-badge">
              <CheckCheck size={15} />
              Values: {answer.numerical_verification} · citations:{" "}
              {answer.citation_verification}
            </span>
          </div>
          <div className="evidence-body">
            <ul className="agent-findings">
              {answer.findings.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </div>
          {answer.claims.length > 0 && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>VERIFIED FINANCIAL FACT</th>
                    <th className="numeric">VALUE</th>
                    <th>UNIT / INTERPRETATION</th>
                    <th>AS OF</th>
                    <th>SOURCE</th>
                  </tr>
                </thead>
                <tbody>
                  {answer.claims.map((f) => (
                    <tr key={f.evidence_id + f.key}>
                      <td>{f.label}</td>
                      <td className="numeric">{factValue(f.value, f.unit)}</td>
                      <td>{f.unit}</td>
                      <td>{f.as_of}</td>
                      <td>
                        <a href={`#agent-evidence-${f.evidence_id}`}>
                          {f.source_id.slice(0, 12)}
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="evidence-body">
            {answer.citations.length > 0 && (
              <div className="agent-citations">
                <h3>Cited disclosure evidence</h3>
                {answer.citations.map((c, i) => (
                  <CitationEvidence key={c.chunk_id + i} citation={c} />
                ))}
              </div>
            )}
            <ul className="risk-warnings">
              {answer.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
            <p className="panel-footnote">{answer.financial_validity}</p>
          </div>
        </section>
      )}
      {active && (
        <div className="risk-detail-grid">
          <section className="panel agent-activity">
            <div className="panel-heading">
              <div>
                <h2>Investigation steps</h2>
                <p>Execution activity, not private model reasoning</p>
              </div>
            </div>
            <ol>
              {trace.data?.map((step) => (
                <li key={step.sequence}>
                  <strong>{step.summary}</strong>
                  <small>
                    {step.kind} · {(step.elapsed_ms / 1000).toFixed(3)} seconds
                    since start
                  </small>
                </li>
              ))}
            </ol>
            {trace.error && <ErrorNotice error={trace.error} />}
          </section>
          <section className="panel agent-evidence">
            <div className="panel-heading">
              <div>
                <h2>
                  <FileSearch size={17} />
                  Evidence panel
                </h2>
                <p>
                  Authorized sources, immutable references and original
                  provenance
                </p>
              </div>
            </div>
            {evidence.data?.map((e) => (
              <article id={`agent-evidence-${e.id}`} key={e.id}>
                <strong>{e.tool}</strong>
                <small>
                  {e.source_type} · {e.source_id} · {e.as_of}
                </small>
                <span className="subtle-badge">
                  {e.synthetic ? "SYNTHETIC" : "AUTHORIZED SOURCE"}
                </span>
                <details>
                  <summary>Inspect source metadata and evidence</summary>
                  <pre>
                    {JSON.stringify(
                      {
                        checksum: e.checksum,
                        provenance: e.provenance,
                        data: e.data,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </article>
            ))}
            {evidence.error && <ErrorNotice error={evidence.error} />}
          </section>
        </div>
      )}
      <DocumentLibrary
        ready={ready}
        configured={status.data?.configured ?? false}
        selected={documentIds}
        onSelected={setDocumentIds}
      />
      <section className="panel agent-history">
        <div className="panel-heading">
          <div>
            <h2>Investigation history</h2>
            <p>
              Private saved answers, verification outcomes and tool activity
            </p>
          </div>
        </div>
        {history.error && <ErrorNotice error={history.error} />}
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>QUESTION</th>
                <th>MODE / STATUS</th>
                <th>CREATED</th>
                <th>RESULT</th>
              </tr>
            </thead>
            <tbody>
              {history.data?.map((j) => (
                <tr key={j.id}>
                  <td>{j.question}</td>
                  <td>
                    {j.engine} · {j.status}
                  </td>
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
                      Open investigation
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {history.data?.length === 0 && (
            <div className="empty-state">
              No investigations saved in this session.
            </div>
          )}
        </div>
      </section>
      <AgentEvaluation ready={ready} />
    </div>
  );
}
