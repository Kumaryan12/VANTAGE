"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Check,
  Database,
  Download,
  ExternalLink,
  FileUp,
  LockKeyhole,
} from "lucide-react";
import { api, dateLabel, type Source } from "@/lib/api";
import { ErrorNotice } from "./error-notice";

export function Sources({
  connected,
  configured,
  onDisconnect,
  onImport,
}: {
  connected: boolean;
  configured: boolean;
  onDisconnect: () => void;
  onImport: (id: string) => void;
}) {
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: () => api<Source[]>("/sources"),
  });
  const [importError, setImportError] = useState<Error | null>(null);
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [mapping, setMapping] = useState("");
  const [attested, setAttested] = useState(false);
  const [fxPair, setFxPair] = useState("USD");
  const [fxEnabled, setFxEnabled] = useState(false);
  const [macroId, setMacroId] = useState("VIXCLS");
  const [macroEnabled, setMacroEnabled] = useState(false);
  const fx = useQuery({
    queryKey: ["fx", fxPair],
    queryFn: () =>
      api<{ rate: number; date: string; source: string; retrieved_at: string }>(
        `/context/fx?base=${fxPair}&quote=INR`,
      ),
    enabled: fxEnabled,
  });
  const macro = useQuery({
    queryKey: ["macro", macroId],
    queryFn: () =>
      api<{
        series_id: string;
        vintage: string;
        observations: { date: string; value: number | null }[];
      }>(`/context/macro?series_id=${macroId}`),
    enabled: macroEnabled,
  });
  async function upload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setImportError(null);
    setSuccess("");
    try {
      const result = await api<{ id: string; rows: number }>(
        "/history/import",
        { method: "POST", body: new FormData(event.currentTarget) },
      );
      onImport(result.id);
      setSuccess(
        `Imported ${result.rows.toLocaleString()} validated observations. Select Kite Mode and this dataset to run risk.`,
      );
    } catch (error) {
      setImportError(error as Error);
    } finally {
      setBusy(false);
    }
  }
  async function importAlpha() {
    setBusy(true);
    setImportError(null);
    setSuccess("");
    try {
      const parsed = JSON.parse(mapping);
      const result = await api<{ id: string; rows: number }>(
        "/history/alpha-vantage",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mapping: parsed,
            currency: "INR",
            currency_and_venue_verified: attested,
          }),
        },
      );
      onImport(result.id);
      setSuccess(
        `Imported ${result.rows.toLocaleString()} adjusted observations from Alpha Vantage.`,
      );
    } catch (error) {
      setImportError(
        error instanceof SyntaxError
          ? new Error(
              "Enter a valid JSON object mapping canonical instruments to provider symbols.",
            )
          : (error as Error),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="sources-view">
      <section className="panel broker-panel">
        <div>
          <span className="eyebrow">BROKER CONNECTION</span>
          <h2>Zerodha Kite Connect</h2>
          <p>
            Authorize access on Zerodha. Credentials and tokens stay on the
            server.
          </p>
          <small>
            Holdings, positions, margins and instrument metadata. Trading is
            disabled.
          </small>
        </div>
        <div>
          {connected ? (
            <>
              <span className="connection-status">
                <Check size={14} />
                Account connected
              </span>
              <button className="button secondary" onClick={onDisconnect}>
                Disconnect
              </button>
            </>
          ) : configured ? (
            <a className="button primary" href="/api/auth/kite/login">
              Connect Zerodha
              <ExternalLink size={14} />
            </a>
          ) : (
            <div className="setup-note">
              <LockKeyhole size={17} />
              <span>
                Server configuration required
                <small>Set KITE_API_KEY and KITE_API_SECRET in .env</small>
              </span>
            </div>
          )}
        </div>
      </section>
      {sources.error && <ErrorNotice error={sources.error} />}
      <div className="source-cards">
        {sources.data?.map((s) => (
          <article className="panel source-card" key={s.id}>
            <div className="source-card-top">
              <Database size={18} />
              <span className={`source-status ${s.configured ? "ready" : ""}`}>
                {s.configured ? "CONFIGURED" : "KEY REQUIRED"}
              </span>
            </div>
            <h3>{s.name}</h3>
            <strong>{s.purpose}</strong>
            <p>{s.note}</p>
          </article>
        ))}
      </div>
      {importError && <ErrorNotice error={importError} />}
      {success && (
        <div className="success-notice" role="status">
          <Check size={18} />
          {success}
        </div>
      )}
      <div className="source-forms">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>
                <FileUp size={17} />
                Import historical data
              </h2>
              <p>Permitted CSV or Parquet · maximum 5 MB</p>
            </div>
          </div>
          <form onSubmit={upload} className="data-form">
            <label>
              History file
              <input type="file" name="file" accept=".csv,.parquet" required />
            </label>
            <div className="schema-example">
              date,instrument,close,currency
              <br />
              YYYY-MM-DD,NSE:SYMBOL,123.45,INR
            </div>
            <label>
              Source and permission description
              <input
                name="source"
                minLength={3}
                maxLength={250}
                placeholder="Provider / dataset / license or permission"
                required
              />
            </label>
            <label>
              Corporate-action adjustment
              <select name="adjustment" defaultValue="unknown">
                <option value="unknown">Unknown · ineligible for risk</option>
                <option value="split_dividend_adjusted">
                  I confirm split and dividend adjusted
                </option>
                <option value="unadjusted">
                  Unadjusted · ineligible for risk
                </option>
              </select>
            </label>
            <p className="form-help">
              Every holding must share the same observation dates. At least 60
              daily returns are required. Uploaded data is real-data mode only.
            </p>
            <button className="button primary" disabled={busy}>
              <FileUp size={15} />
              {busy ? "Importing…" : "Validate and import"}
            </button>
          </form>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Alpha Vantage adjusted history</h2>
              <p>Optional · premium endpoint entitlement required</p>
            </div>
          </div>
          <div className="data-form">
            <label>
              Explicit symbol mapping (JSON)
              <textarea
                value={mapping}
                onChange={(e) => setMapping(e.target.value)}
                placeholder={'{"BSE:RELIANCE": "RELIANCE.BSE"}'}
                rows={5}
              />
            </label>
            <p className="form-help">
              Verify the exact security, exchange and INR denomination with your
              provider. BSE history must not be silently mapped to an NSE
              holding.
            </p>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={attested}
                onChange={(e) => setAttested(e.target.checked)}
              />
              I have verified the venue, security identity, currency and data
              permissions.
            </label>
            <button
              className="button secondary"
              disabled={busy || !attested || !mapping.trim()}
              onClick={importAlpha}
            >
              <Download size={15} />
              Fetch adjusted prices
            </button>
            <small className="form-help">
              Set ALPHA_VANTAGE_API_KEY server-side. Rate limits or entitlement
              failures display an error; partial imports are never saved.
            </small>
          </div>
        </section>
      </div>
      <div className="source-forms">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>FX reference context</h2>
              <p>Frankfurter · no API key · daily reference rates</p>
            </div>
          </div>
          <div className="data-form">
            <div className="context-controls">
              <select
                aria-label="FX base currency"
                value={fxPair}
                onChange={(e) => {
                  setFxPair(e.target.value);
                  setFxEnabled(false);
                }}
              >
                <option>USD</option>
                <option>EUR</option>
                <option>GBP</option>
              </select>
              <span>→ INR</span>
              <button
                className="button secondary"
                disabled={fx.isFetching}
                onClick={() => {
                  setFxEnabled(true);
                  if (fxEnabled) void fx.refetch();
                }}
              >
                {fx.isFetching ? "Fetching…" : "Fetch reference"}
              </button>
            </div>
            {fx.error && <ErrorNotice error={fx.error} compact />}
            {fx.data && fxEnabled && (
              <div className="context-result">
                <strong>
                  1 {fxPair} = {fx.data.rate.toFixed(4)} INR
                </strong>
                <p>
                  Observed {dateLabel(fx.data.date)} · {fx.data.source}
                </p>
              </div>
            )}
            <p className="form-help">
              Reference context only. Portfolio values remain INR; these rates
              are never silently used for conversion.
            </p>
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Macroeconomic context</h2>
              <p>FRED · observations retain vintage metadata</p>
            </div>
          </div>
          <div className="data-form">
            <div className="context-controls">
              <select
                aria-label="FRED series"
                value={macroId}
                onChange={(e) => {
                  setMacroId(e.target.value);
                  setMacroEnabled(false);
                }}
              >
                <option value="VIXCLS">VIX close (index)</option>
                <option value="DGS10">US 10Y Treasury yield (%)</option>
                <option value="DFF">Federal funds rate (%)</option>
              </select>
              <button
                className="button secondary"
                disabled={macro.isFetching}
                onClick={() => {
                  setMacroEnabled(true);
                  if (macroEnabled) void macro.refetch();
                }}
              >
                {macro.isFetching ? "Fetching…" : "Fetch observations"}
              </button>
            </div>
            {macro.error && <ErrorNotice error={macro.error} compact />}
            {macro.data && macroEnabled && (
              <div className="context-result">
                <strong>
                  {macro.data.series_id} · {macro.data.observations.length}{" "}
                  observations
                </strong>
                <p>Vintage {dateLabel(macro.data.vintage)}</p>
                <div className="macro-observations">
                  {macro.data.observations.slice(-5).map((o) => (
                    <div key={o.date}>
                      <span>{o.date}</span>
                      <strong>{o.value ?? "Missing"}</strong>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <p className="form-help">
              Requires FRED_API_KEY. Context only; release-calendar validation
              is required before model use.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
