"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ErrorNotice } from "./error-notice";
type ReviewModel = {
  id: string;
  source_type: string;
  source_id: string;
  model_type: string;
  model_version: string;
  intended_use: string;
  status: string;
  allowed_transitions: string[];
  payload: Record<string, unknown>;
  current_validation: {
    validation_ready: boolean;
    synthetic: boolean;
    automated_checks: Record<string, boolean>;
    limitations: string[];
    [key: string]: unknown;
  };
};
const areas = [
  "out_of_sample",
  "var_coverage",
  "uncertainty",
  "data_quality",
  "leakage",
  "regime_stability",
  "complexity",
  "reproducibility_operations",
];
export function ModelGovernance({
  ready,
  refreshKey,
}: {
  ready: boolean;
  refreshKey: string;
}) {
  const client = useQueryClient();
  const [selected, setSelected] = useState("");
  const [next, setNext] = useState("");
  const [rationale, setRationale] = useState("");
  const [human, setHuman] = useState(false);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [source, setSource] = useState("");
  const models = useQuery({
    queryKey: ["governance-models", refreshKey],
    queryFn: () => api<ReviewModel[]>("/v1/governance/models"),
    enabled: ready,
  });
  const sources = useQuery({
    queryKey: ["governance-sources", refreshKey],
    queryFn: () =>
      api<{ source_id: string; label: string }[]>("/v1/governance/sources"),
    enabled: ready,
  });
  const model = models.data?.find((m) => m.id === selected) ?? models.data?.[0];
  const events = useQuery({
    queryKey: ["governance-events", model?.id, model?.status],
    queryFn: () =>
      api<
        {
          id: string;
          created_at: string;
          payload: {
            previous_status: string | null;
            new_status: string;
            rationale: string;
            reviewer_session: string;
          };
        }[]
      >(`/v1/governance/events?model_id=${model?.id}`),
    enabled: !!model,
  });
  const decision = next || model?.allowed_transitions[0] || "";
  function refresh() {
    void client.invalidateQueries({ queryKey: ["governance-models"] });
    void client.invalidateQueries({ queryKey: ["governance-events"] });
  }
  const register = useMutation({
    mutationFn: () =>
      api("/v1/governance/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_type: "forecast", source_id: source }),
      }),
    onSuccess: refresh,
  });
  const review = useMutation({
    mutationFn: () =>
      api(`/v1/governance/models/${model?.id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: decision,
          rationale,
          human_review: human,
          research_only: human,
          assessments: decision === "validated" ? notes : {},
        }),
      }),
    onSuccess: () => {
      setNext("");
      setRationale("");
      setHuman(false);
      refresh();
    },
  });
  return (
    <section className="panel model-governance">
      <div className="panel-heading">
        <div>
          <h2>Model governance</h2>
          <p>
            Explicit human methodological review · authorized session audit · no
            automatic promotion
          </p>
        </div>
        <span className="subtle-badge">RESEARCH USE ONLY</span>
      </div>
      <div className="evidence-body">
        <p className="form-help">
          Feasible single allocations register as candidates. Synthetic and
          in-sample results cannot establish real-market approval. This
          session-bound workflow has no durable reviewer identity or enterprise
          maker-checker. The assistant can read status; it cannot submit
          decisions.
        </p>
        {models.error && <ErrorNotice error={models.error} />}
        <label>
          Registered model
          <select
            aria-label="Governance model"
            value={model?.id ?? ""}
            onChange={(e) => {
              setSelected(e.target.value);
              setNext("");
              review.reset();
            }}
          >
            <option value="" disabled>
              Select a registered model
            </option>
            {models.data?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.model_type} · {m.source_id.slice(0, 8)} · {m.status}
              </option>
            ))}
          </select>
        </label>
        {sources.data && sources.data.length > 0 && (
          <div className="optimization-controls">
            <label>
              Phase 3 forecasting source
              <select
                aria-label="Governance forecasting source"
                value={source}
                onChange={(e) => setSource(e.target.value)}
              >
                <option value="">Select an owned forecasting model</option>
                {sources.data.map((s) => (
                  <option key={s.source_id} value={s.source_id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="button secondary"
              disabled={!source || register.isPending}
              onClick={() => register.mutate()}
            >
              Register forecasting candidate
            </button>
          </div>
        )}
        {register.error && <ErrorNotice error={register.error} />}
        {model ? (
          <>
            <div className="governance-status">
              <strong>Review status: {model.status}</strong>
              <p>
                {model.model_version} · {model.intended_use}
              </p>
              <p>
                Evidence gate:{" "}
                {model.current_validation.validation_ready
                  ? "Ready for methodological human assessment"
                  : "Incomplete; checked saved-input reproduction and source evidence required"}
              </p>
              <div className="optimization-controls">
                {Object.entries(model.current_validation.automated_checks).map(
                  ([key, ok]) => (
                    <span key={key}>
                      {key.replaceAll("_", " ")}:{" "}
                      {ok ? "Passed" : "Missing / failed"}
                    </span>
                  ),
                )}
              </div>
            </div>
            <details>
              <summary>
                Validation evidence, evaluation period and dependencies
              </summary>
              <pre>
                {JSON.stringify(
                  {
                    registered: model.payload,
                    current: model.current_validation,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
            {model.current_validation.limitations.map((l, i) => (
              <p className="form-help" key={i}>
                {l}
              </p>
            ))}
            {model.allowed_transitions.length > 0 && (
              <form
                className="governance-review"
                onSubmit={(e) => {
                  e.preventDefault();
                  review.mutate();
                }}
              >
                <label>
                  Human review decision
                  <select
                    aria-label="Governance decision"
                    value={decision}
                    onChange={(e) => setNext(e.target.value)}
                  >
                    {model.allowed_transitions.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </label>
                {decision === "validated" && (
                  <>
                    <p className="form-help">
                      Document all eight review areas, including evidence gaps.
                      Mathematical feasibility does not substitute for
                      out-of-sample performance or VaR coverage. Approval scope
                      is methodological research only.
                    </p>
                    {areas.map((area) => (
                      <label key={area}>
                        {area.replaceAll("_", " ")}
                        <textarea
                          aria-label={`Governance assessment ${area}`}
                          minLength={20}
                          maxLength={2000}
                          required
                          rows={2}
                          value={notes[area] ?? ""}
                          onChange={(e) =>
                            setNotes({ ...notes, [area]: e.target.value })
                          }
                        />
                      </label>
                    ))}
                  </>
                )}
                <label>
                  Written decision rationale
                  <textarea
                    aria-label="Governance rationale"
                    minLength={20}
                    maxLength={2000}
                    required
                    rows={3}
                    value={rationale}
                    onChange={(e) => setRationale(e.target.value)}
                  />
                </label>
                <label className="agent-checkbox">
                  <input
                    aria-label="Governance human research acknowledgement"
                    type="checkbox"
                    required
                    checked={human}
                    onChange={(e) => setHuman(e.target.checked)}
                  />
                  I am explicitly recording this human decision for
                  methodological research only. This does not approve investment
                  use, execution, or real-market validity.
                </label>
                <button
                  className="button secondary"
                  disabled={review.isPending || !human}
                >
                  Record human review decision
                </button>
              </form>
            )}
            {review.error && <ErrorNotice error={review.error} />}
            <h3>Review audit events</h3>
            {events.error && <ErrorNotice error={events.error} />}
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>TRANSITION</th>
                    <th>RATIONALE</th>
                    <th>SESSION / TIME</th>
                  </tr>
                </thead>
                <tbody>
                  {events.data?.map((e) => (
                    <tr key={e.id}>
                      <td>
                        {e.payload.previous_status ?? "Unregistered"} →{" "}
                        {e.payload.new_status}
                      </td>
                      <td>{e.payload.rationale}</td>
                      <td>
                        {e.payload.reviewer_session?.slice(0, 12)}
                        <small className="cell-note">
                          {new Date(e.created_at).toLocaleString("en-GB", {
                            timeZone: "Asia/Kolkata",
                          })}
                        </small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p>
            No owned candidates yet. Complete a feasible allocation or register
            an accessible forecasting source.
          </p>
        )}
      </div>
    </section>
  );
}
