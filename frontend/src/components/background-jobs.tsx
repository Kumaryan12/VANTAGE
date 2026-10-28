"use client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ErrorNotice } from "./error-notice";

type Job = { id: string; kind: string; target_id: string; status: string; created_at: string; started_at: string | null; finished_at: string | null; attempts: number; max_attempts: number; timeout_seconds: number; failure: { code: string; message: string } | null; result_reference: { target_id?: string; artifact_id?: string } | null; attempt_history: { attempt: number; status: string }[] };
const active = ["queued", "retrying", "running", "cancel_requested"];
export function BackgroundJobs({ selection }: { selection: { mode: string; dataset_id?: string; confidence: number; window: number } }) {
  const query = useQuery({ queryKey: ["background-jobs"], queryFn: () => api<{ backend: string; jobs: Job[]; local_mode: string }>("/v1/jobs"), refetchInterval: 2000 });
  const action = useMutation({ mutationFn: ({ path, body }: { path: string; body?: unknown }) => api(`/v1/jobs${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, ...(body ? { body: JSON.stringify(body) } : {}) }), onSuccess: () => { void query.refetch(); } });
  return <section className="panel background-jobs">
    <div className="panel-heading"><div><h2>Background jobs</h2><p>Private research · bounded execution · saved results</p></div><button className="button secondary" disabled={query.isFetching} onClick={() => void query.refetch()}>Refresh job status</button></div>
    <div className="evidence-body">
      {query.error && <ErrorNotice error={query.error} />}
      {action.error && <ErrorNotice error={action.error} />}
      <p>Execution configured: <strong>{query.data?.backend ?? "Checking"}</strong>. Configuration does not establish current worker availability. Queued work waits for an eligible worker; accepted cancellation prevents late successful publication.</p>
      {query.data?.backend === "local" && <p className="form-help">{query.data.local_mode}</p>}
      <button className="button primary" disabled={action.isPending || query.data?.backend !== "celery"} onClick={() => action.mutate({ path: "/risk", body: { parameters: { ...selection, simulations: 2000 } } })}>Queue saved risk analysis</button>
      <p className="form-help">Uses the current portfolio/history selection. Numerical calculations remain on the backend. Outputs are research evidence, never orders or a future-risk guarantee. A retry uses the original captured inputs and consumes an attempt; provider work is never retried automatically after a crash.</p>
      {query.data?.jobs.length === 0 && <p>No durable jobs in this workspace.</p>}
    </div>
    {query.data?.jobs.map(job => <article className="evidence-body" key={job.id}>
      <h3>{job.kind.toUpperCase()} · {job.status.toUpperCase()}</h3>
      <p className="form-help">Job {job.id} · saved resource {job.result_reference?.target_id ?? job.target_id}</p>
      <p>Attempt {job.attempts} / {job.max_attempts} · execution budget {job.timeout_seconds}s · queued {new Date(job.created_at).toLocaleString("en-GB")}</p>
      {job.failure && <p role="status">{job.failure.code}: {job.failure.message}</p>}
      {job.attempt_history.map(attempt => <span className="subtle-badge" key={attempt.attempt}>{attempt.attempt}: {attempt.status} </span>)}
      <div className="heading-actions">
        {active.includes(job.status) && job.status !== "cancel_requested" && <button className="button secondary" disabled={action.isPending} onClick={() => action.mutate({ path: `/${job.id}/cancel` })}>Cancel job</button>}
        {["failed", "interrupted"].includes(job.status) && job.attempts < 3 && <button className="button secondary" disabled={action.isPending} onClick={() => action.mutate({ path: `/${job.id}/retry` })}>Retry captured job</button>}
        {job.status === "completed" && ["optimization", "risk", "agent"].includes(job.kind) && <button className="button secondary" disabled={action.isPending} onClick={() => action.mutate({ path: "/report", body: { source_type: job.kind === "agent" ? "investigation" : job.kind, source_id: job.result_reference?.target_id ?? job.target_id } })}>Save private evidence export</button>}
        {job.result_reference?.artifact_id && <a className="button secondary" href={`/api/v1/storage/artifacts/${job.result_reference.artifact_id}`}>Download private evidence</a>}
      </div>
    </article>)}
  </section>;
}
