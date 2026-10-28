"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ErrorNotice } from "./error-notice";
export type Identity = {
  authenticated: boolean;
  authentication_required?: boolean;
  registration_enabled: boolean;
  user?: { id: string; email: string; roles: string[] };
  workspace_id?: string;
  session_id?: string;
  expires?: number;
};
export function AccountSecurity() {
  const client = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [token, setToken] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [message, setMessage] = useState("");
  const me = useQuery({
    queryKey: ["identity"],
    queryFn: () => api<Identity>("/auth/me"),
    staleTime: 0,
  });
  const authenticated = !!me.data?.authenticated;
  const scopes = useQuery({
    queryKey: ["account-workspaces"],
    queryFn: () =>
      api<{ id: string; name: string; kind: string }[]>("/auth/workspaces"),
    enabled: authenticated,
  });
  const sessions = useQuery({
    queryKey: ["account-sessions"],
    queryFn: () =>
      api<
        {
          id: string;
          current: boolean;
          expires: number;
          last_seen: number;
          revoked: boolean;
        }[]
      >("/auth/sessions"),
    enabled: authenticated,
  });
  const legacy = useQuery({
    queryKey: ["account-legacy"],
    queryFn: () =>
      api<{ proof_available: boolean; limitation: string }>(
        "/auth/legacy-status",
      ),
    enabled: authenticated,
  });
  const events = useQuery({
    queryKey: ["account-events"],
    queryFn: () =>
      api<{ id: string; action: string; created_at: string }[]>(
        "/auth/security-events",
      ),
    enabled: authenticated,
  });
  function changed() {
    client.clear();
    window.location.reload();
  }
  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) =>
      api<{ message?: string }>(`/auth/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        ...(body ? { body: JSON.stringify(body) } : {}),
      }),
    onSuccess: (data, variables) => {
      setPassword("");
      setNewPassword("");
      setToken("");
      if (
        variables.path.startsWith("sessions/") ||
        ["login", "logout", "workspace", "claim-legacy", "password"].includes(
          variables.path,
        )
      )
        changed();
      else {
        setMessage(data.message ?? "Security action recorded.");
        void sessions.refetch();
        void events.refetch();
      }
    },
  });
  return (
    <div className="account-terminal">
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Account &amp; security</h2>
            <p>
              Durable identity · private workspaces · explicit research
              permissions
            </p>
          </div>
          <span className="subtle-badge">NO TRADING</span>
        </div>
        <div className="evidence-body">
          {me.error && <ErrorNotice error={me.error} />}
          {action.error && <ErrorNotice error={action.error} />}
          {message && <p role="status">{message}</p>}
          {authenticated ? (
            <>
              <p>
                Signed in as <strong>{me.data?.user?.email}</strong>
              </p>
              <p className="form-help">
                Roles: {me.data?.user?.roles.join(", ")}. Platform
                administration does not grant confidential research or
                credential access.
              </p>
              <p className="form-help">
                Workspace {me.data?.workspace_id?.slice(0, 12)} · account{" "}
                {me.data?.user?.id}. Re-login preserves ownership after a
                service restart; brokerage authorization has a separate expiry.
              </p>
              <button
                className="button secondary"
                disabled={action.isPending}
                onClick={() => action.mutate({ path: "logout" })}
              >
                Sign out of account
              </button>
            </>
          ) : (
            <>
              <p>
                Sign in to retain access to your own saved research after logout
                or backend restart. Local guest work remains temporary unless
                explicitly claimed with a live original session.
              </p>
              <form
                className="account-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  action.mutate({ path: "login", body: { email, password } });
                }}
              >
                <label>
                  Email
                  <input
                    aria-label="Account email"
                    type="email"
                    autoComplete="username"
                    maxLength={254}
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </label>
                <label>
                  Password
                  <input
                    aria-label="Account password"
                    type="password"
                    autoComplete="current-password"
                    maxLength={128}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </label>
                <div className="heading-actions">
                  <button
                    className="button primary"
                    disabled={action.isPending}
                  >
                    Sign in to account
                  </button>
                  {me.data?.registration_enabled && (
                    <button
                      type="button"
                      className="button secondary"
                      disabled={
                        action.isPending || !email || password.length < 15
                      }
                      onClick={() =>
                        action.mutate({
                          path: "register",
                          body: { email, password },
                        })
                      }
                    >
                      Register research account
                    </button>
                  )}
                </div>
                <p className="form-help">
                  New passwords need 15–128 characters and must avoid
                  common/repetitive text or your email name. Registration never
                  grants reviewer or administrator roles. Sign in after
                  registration.
                </p>
              </form>
              {me.error && (
                <button
                  className="button secondary"
                  onClick={() => action.mutate({ path: "logout" })}
                >
                  Clear expired session
                </button>
              )}
            </>
          )}
        </div>
      </section>
      {authenticated && (
        <>
          <section className="panel">
            <div className="panel-heading">
              <h2>Private research workspaces</h2>
            </div>
            <div className="evidence-body">
              {scopes.error && <ErrorNotice error={scopes.error} />}
              <form
                className="account-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  action.mutate({
                    path: "workspace",
                    body: { scope_id: workspace || me.data?.workspace_id },
                  });
                }}
              >
                <label>
                  Active research workspace
                  <select
                    aria-label="Account workspace"
                    value={workspace || me.data?.workspace_id || ""}
                    onChange={(e) => setWorkspace(e.target.value)}
                  >
                    {scopes.data?.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} · {s.id.slice(0, 8)}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="button secondary"
                  disabled={action.isPending}
                >
                  Switch research workspace
                </button>
              </form>
              <p className="form-help">
                Workspaces keep their original owner keys and evidence hashes.
                Claiming does not merge or rewrite financial results.
              </p>
              {legacy.data?.proof_available && (
                <button
                  className="button secondary"
                  disabled={action.isPending}
                  onClick={() => action.mutate({ path: "claim-legacy" })}
                >
                  Claim this live legacy workspace
                </button>
              )}
              <p className="form-help">{legacy.data?.limitation}</p>
            </div>
          </section>
          <section className="panel">
            <div className="panel-heading">
              <h2>Sessions and password</h2>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>SESSION</th>
                    <th>EXPIRATION</th>
                    <th>STATUS</th>
                    <th>ACTION</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.data?.map((s) => (
                    <tr key={s.id}>
                      <td>
                        {s.id.slice(0, 12)} {s.current ? "· current" : ""}
                      </td>
                      <td>
                        {new Date(s.expires * 1000).toLocaleString("en-GB")}
                      </td>
                      <td>
                        {s.revoked
                          ? "Revoked"
                          : "Issued (expiry and idle checks apply)"}
                      </td>
                      <td>
                        {!s.revoked && (
                          <button
                            className="text-button"
                            disabled={action.isPending}
                            onClick={() =>
                              action.mutate({ path: `sessions/${s.id}/revoke` })
                            }
                          >
                            Revoke session
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="evidence-body">
              <form
                className="account-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  action.mutate({
                    path: "password",
                    body: {
                      current_password: password,
                      new_password: newPassword,
                    },
                  });
                }}
              >
                <label>
                  Current password
                  <input
                    aria-label="Account current password"
                    type="password"
                    autoComplete="current-password"
                    required
                    maxLength={128}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </label>
                <label>
                  New password
                  <input
                    aria-label="Account new password"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={15}
                    maxLength={128}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                  />
                </label>
                <button
                  className="button secondary"
                  disabled={action.isPending}
                >
                  Change password and revoke other sessions
                </button>
              </form>
            </div>
          </section>
          <section className="panel">
            <div className="panel-heading">
              <h2>Security audit</h2>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>ACTION</th>
                    <th>TIME</th>
                  </tr>
                </thead>
                <tbody>
                  {events.data?.map((e) => (
                    <tr key={e.id}>
                      <td>{e.action}</td>
                      <td>{new Date(e.created_at).toLocaleString("en-GB")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
      {!authenticated && (
        <section className="panel">
          <div className="panel-heading">
            <h2>Account recovery</h2>
          </div>
          <div className="evidence-body">
            <p className="form-help">
              An authorized operator can issue a private, single-use recovery
              capability after verifying your identity out of band. It expires
              in 15 minutes. No public email/account lookup reveals whether an
              account exists. Lost legacy sessions cannot establish ownership.
            </p>
            <form
              className="account-form"
              onSubmit={(e) => {
                e.preventDefault();
                action.mutate({
                  path: "recover",
                  body: { token, new_password: newPassword },
                });
              }}
            >
              <label>
                Recovery capability
                <input
                  aria-label="Account recovery capability"
                  type="password"
                  autoComplete="off"
                  required
                  minLength={32}
                  maxLength={128}
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                />
              </label>
              <label>
                New password
                <input
                  aria-label="Account recovery password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={15}
                  maxLength={128}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </label>
              <button className="button secondary" disabled={action.isPending}>
                Recover account
              </button>
            </form>
          </div>
        </section>
      )}
    </div>
  );
}
