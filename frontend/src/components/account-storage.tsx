"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ErrorNotice } from "./error-notice";

export function AccountStorage() {
  const client = useQueryClient();
  const [confirmation, setConfirmation] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const credentials = useQuery({ queryKey: ["account-credentials"], queryFn: () => api<{ id: string; provider: string; expires: number; revoked: boolean }[]>("/auth/credentials") });
  const storage = useQuery({ queryKey: ["account-storage"], queryFn: () => api<{ private_object_bytes: number; private_object_quota_bytes: number; sql_source_bytes: number; sql_source_quota_bytes: number; scope: string }>("/v1/storage/usage") });
  const revoke = useMutation({ mutationFn: (id: string) => api(`/auth/credentials/${id}/revoke`, { method: "POST" }), onSuccess: () => { void credentials.refetch(); } });
  const deletion = useMutation({ mutationFn: () => api("/v1/storage/workspace-deletion", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmation, acknowledge_backup_retention: acknowledged }) }), onSuccess: () => { client.clear(); window.location.reload(); } });
  return <section className="panel">
    <div className="panel-heading"><h2>Provider authorization &amp; data retention</h2></div>
    <div className="evidence-body">
      {credentials.error && <ErrorNotice error={credentials.error} />}
      {revoke.error && <ErrorNotice error={revoke.error} />}
      <p className="form-help">Broker credentials are encrypted on the backend with separately managed keys. Account sessions and broker authorization expire independently. Local revocation removes this app&apos;s stored token; remote revocation must be confirmed with the provider.</p>
      {!credentials.data?.length && <p>No persistent provider credentials in this workspace.</p>}
      {credentials.data?.map(c => <p key={c.id}>{c.provider} · {c.revoked ? "Locally revoked" : `Expires ${new Date(c.expires * 1000).toLocaleString("en-GB")}`} {!c.revoked && <button className="text-button" disabled={revoke.isPending} onClick={() => revoke.mutate(c.id)}>Revoke stored authorization</button>}</p>)}
      {storage.error && <ErrorNotice error={storage.error} />}
      {storage.data && <p>Private objects: {(storage.data.private_object_bytes / 1048576).toFixed(2)} / {(storage.data.private_object_quota_bytes / 1048576).toFixed(0)} MiB. {storage.data.scope}</p>}
      {storage.data && <p>SQL sources, histories and snapshots: {(storage.data.sql_source_bytes / 1048576).toFixed(2)} / {(storage.data.sql_source_quota_bytes / 1048576).toFixed(0)} MiB. Other SQL output records and infrastructure disk space require operational monitoring.</p>}
      <p className="form-help">Saved source and model artifacts stay available for reproduction until explicitly deleted. Temporary exports expire after 30 days. Lost legacy ownership cannot be recovered automatically. Encrypted offline backups follow their own retention period; deletion does not erase those copies immediately.</p>
      <details><summary>Delete current workspace data</summary>
        <p>This removes this workspace&apos;s saved risk, models, documents and search indexes, investigations, optimizations, governance evidence and private artifacts. Stop active jobs first. Your account and other workspaces remain available.</p>
        {deletion.error && <ErrorNotice error={deletion.error} />}
        <label>Type DELETE THIS WORKSPACE<input aria-label="Workspace deletion confirmation" value={confirmation} onChange={e => setConfirmation(e.target.value)} /></label>
        <label><input type="checkbox" checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)} /> I understand that offline backups are retained separately.</label>
        <button className="button secondary" disabled={deletion.isPending || confirmation !== "DELETE THIS WORKSPACE" || !acknowledged} onClick={() => deletion.mutate()}>Delete current workspace data</button>
      </details>
    </div>
  </section>;
}
