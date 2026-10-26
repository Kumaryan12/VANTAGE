"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  GitCompareArrows,
  History,
  LoaderCircle,
  RotateCcw,
} from "lucide-react";
import { api, money, pct } from "@/lib/api";
import type {
  Replay,
  RunComparison,
  RunSummary,
  SavedRun,
} from "@/lib/advanced-risk";
import { AnalysisView } from "./advanced-risk";
import { StressView } from "./stress-lab";
import { ErrorNotice } from "./error-notice";

export function RiskRuns({ mode }: { mode: "demo" | "kite" }) {
  const queryClient = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [opened, setOpened] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const runs = useQuery({
    queryKey: ["risk-runs", mode, offset],
    queryFn: () =>
      api<RunSummary[]>(`/v1/risk/runs?mode=${mode}&limit=20&offset=${offset}`),
  });
  const detail = useQuery({
    queryKey: ["saved-risk-run", opened],
    queryFn: () => api<SavedRun>(`/v1/risk/runs/${opened}`),
    enabled: !!opened,
  });
  const compare = useMutation({
    mutationFn: () =>
      api<RunComparison>("/v1/risk/runs/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_ids: selected }),
      }),
  });
  const replay = useMutation({
    mutationFn: () =>
      api<Replay>(`/v1/risk/runs/${opened}/replay`, { method: "POST" }),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["risk-runs"] }),
  });
  return (
    <div className="risk-run-view">
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>
              <History size={17} />
              Historical risk runs
            </h2>
            <p>
              Private to this active browser session · immutable inputs, model
              versions and parameters
            </p>
          </div>
          <button
            className="button secondary"
            onClick={() => compare.mutate()}
            disabled={selected.length < 2 || compare.isPending}
          >
            <GitCompareArrows size={14} />
            Compare selected ({selected.length})
          </button>
        </div>
        {runs.error && <ErrorNotice error={runs.error} />}
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>COMPARE</th>
                <th>RUN / METHOD</th>
                <th>CALCULATED (IST)</th>
                <th className="numeric">CONFIDENCE / SAMPLE</th>
                <th className="numeric">HISTORICAL VAR / P&L</th>
                <th>DETAILS</th>
              </tr>
            </thead>
            <tbody>
              {runs.data?.map((r) => (
                <tr key={r.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Compare run ${r.id}`}
                      checked={selected.includes(r.id)}
                      disabled={
                        !selected.includes(r.id) && selected.length >= 4
                      }
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, r.id]
                            : selected.filter((id) => id !== r.id),
                        )
                      }
                    />
                  </td>
                  <td>
                    <strong>{r.name}</strong>
                    <small className="cell-note">
                      {r.id.slice(0, 8)} · {r.kind} · {r.mode}
                    </small>
                  </td>
                  <td>
                    {new Date(r.created_at).toLocaleString("en-GB", {
                      timeZone: "Asia/Kolkata",
                    })}
                  </td>
                  <td className="numeric">
                    {pct(r.confidence, 1)} / {r.sample_size}
                  </td>
                  <td className="numeric">
                    {r.historical_var !== null
                      ? money(r.historical_var)
                      : r.stress_pnl !== null
                        ? money(r.stress_pnl)
                        : "N/A"}
                  </td>
                  <td>
                    <button
                      className="text-button"
                      onClick={() => {
                        setOpened(r.id);
                        replay.reset();
                      }}
                    >
                      Open run
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {runs.isPending ? (
            <div className="empty-state">Loading saved runs…</div>
          ) : (
            runs.data?.length === 0 && (
              <div className="empty-state">
                No Phase 2 runs in this session. Calculate advanced risk or
                execute a stress scenario to save one.
              </div>
            )
          )}
        </div>
        <div className="table-footer">
          <span>
            Showing records {offset + 1}–{offset + (runs.data?.length ?? 0)} ·
            select 2–4 of the same kind
          </span>
          <div className="pagination-actions">
            <button
              className="button secondary"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 20))}
            >
              Previous
            </button>
            <button
              className="button secondary"
              disabled={!runs.data || runs.data.length < 20}
              onClick={() => setOffset(offset + 20)}
            >
              Next
            </button>
          </div>
        </div>
      </section>
      {compare.error && <ErrorNotice error={compare.error} />}{" "}
      {compare.data && (
        <section className="panel saved-comparison">
          <div className="panel-heading">
            <div>
              <h2>Saved run comparison</h2>
              <p>
                Baseline {compare.data.baseline_id.slice(0, 8)} · INR deltas
                calculated by the backend
              </p>
            </div>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>RUN</th>
                  <th className="numeric">VALUE</th>
                  <th className="numeric">HISTORICAL VAR</th>
                  <th className="numeric">VAR Δ</th>
                  <th className="numeric">ES Δ</th>
                  <th className="numeric">SCENARIO P&L Δ</th>
                </tr>
              </thead>
              <tbody>
                {compare.data.rows.map((r) => (
                  <tr key={r.id}>
                    <td>{r.id.slice(0, 8)}</td>
                    <td className="numeric">
                      {r.portfolio_value === null
                        ? "Unknown"
                        : money(r.portfolio_value)}
                    </td>
                    <td className="numeric">
                      {r.historical_var === null
                        ? "N/A"
                        : money(r.historical_var)}
                    </td>
                    <td className="numeric">
                      {r.var_delta === null ? "N/A" : money(r.var_delta)}
                    </td>
                    <td className="numeric">
                      {r.es_delta === null ? "N/A" : money(r.es_delta)}
                    </td>
                    <td className="numeric">
                      {r.pnl_delta === null ? "N/A" : money(r.pnl_delta)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="risk-warnings comparison-warnings">
            {compare.data.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </section>
      )}
      {detail.error && <ErrorNotice error={detail.error} />}{" "}
      {detail.isFetching && (
        <div className="empty-state">
          <LoaderCircle className="spin" size={20} />
          Loading immutable run…
        </div>
      )}
      {detail.data && (
        <>
          <div className="archive-heading">
            <div>
              <h2>Archived snapshot · {detail.data.id.slice(0, 8)}</h2>
              <p>
                These results use their saved portfolio and parameters,
                independently of current dashboard controls.
              </p>
            </div>
            <button
              className="button primary"
              disabled={!detail.data.replayable || replay.isPending}
              onClick={() => replay.mutate()}
            >
              <RotateCcw size={14} className={replay.isPending ? "spin" : ""} />
              Replay saved inputs
            </button>
          </div>
          {replay.error && <ErrorNotice error={replay.error} />}{" "}
          {replay.data && (
            <div
              className={
                replay.data.numerical_results_match &&
                replay.data.input_hash_matches
                  ? "success-notice"
                  : "error-notice"
              }
              role="status"
            >
              <Check size={17} />
              <div>
                <strong>
                  {replay.data.numerical_results_match &&
                  replay.data.input_hash_matches
                    ? "Reproducibility verified"
                    : "Replay differs from the saved result"}
                </strong>
                <p>
                  Input hash matches: {String(replay.data.input_hash_matches)} ·
                  numerical results match:{" "}
                  {String(replay.data.numerical_results_match)} · new run{" "}
                  {replay.data.replayed_run_id.slice(0, 8)}
                </p>
                <small>{replay.data.note}</small>
              </div>
            </div>
          )}
          {detail.data.result.kind === "analysis" ? (
            <AnalysisView result={detail.data.result} />
          ) : (
            <StressView result={detail.data.result} />
          )}
        </>
      )}
    </div>
  );
}
