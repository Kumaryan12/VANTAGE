"use client";
import { useState } from "react";
import Link from "next/link";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Activity,
  FlaskConical,
  History,
  ArrowRight,
  BarChart3,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Database,
  Download,
  Layers3,
  LayoutDashboard,
  LoaderCircle,
  LockKeyhole,
  Menu,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  api,
  dateLabel,
  money,
  pct,
  type Portfolio,
  type Risk,
  type Dataset,
} from "@/lib/api";
import { chartTooltip } from "@/lib/chart-theme";
import { ErrorNotice } from "./error-notice";
import { Metric, SectorPanel, Holdings } from "./portfolio-panels";
import { RiskDetail } from "./risk-panels";
import { Sources } from "./data-sources";
import { AdvancedRisk } from "./advanced-risk";
import { StressLab } from "./stress-lab";
import { RiskRuns } from "./risk-runs";

type Tab =
  | "Overview"
  | "Portfolio"
  | "Risk Analytics"
  | "Stress Testing"
  | "Risk Runs"
  | "Data Sources";
const nav = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Portfolio", icon: Layers3 },
  { name: "Risk Analytics", icon: Activity },
  { name: "Stress Testing", icon: FlaskConical },
  { name: "Risk Runs", icon: History },
  { name: "Data Sources", icon: Database },
] as const;

export default function Dashboard() {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
            refetchOnWindowFocus: false,
            staleTime: 60_000,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <Workspace />
    </QueryClientProvider>
  );
}

function Workspace() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("Overview");
  const [mode, setMode] = useState<"demo" | "kite">("demo");
  const [confidence, setConfidence] = useState("0.95");
  const [windowSize, setWindowSize] = useState("252");
  const [dataset, setDataset] = useState("");
  const [mobileNav, setMobileNav] = useState(false);
  const [logoutError, setLogoutError] = useState<Error | null>(null);
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () =>
      api<{ kite_configured: boolean; kite_connected: boolean }>("/session"),
  });
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<{ status: string }>("/health"),
    refetchInterval: 60_000,
  });
  const portfolio = useQuery({
    queryKey: ["portfolio", mode],
    queryFn: () => api<Portfolio>(`/portfolio?mode=${mode}`),
    enabled: !!session.data,
  });
  const history = useQuery({
    queryKey: ["history"],
    queryFn: () => api<Dataset[]>("/history"),
    enabled: !!session.data,
  });
  const risk = useQuery({
    queryKey: ["risk", mode, confidence, windowSize, dataset],
    queryFn: () =>
      api<Risk>(
        `/risk?mode=${mode}&confidence=${confidence}&window=${windowSize}${mode === "kite" && dataset ? `&dataset_id=${encodeURIComponent(dataset)}` : ""}`,
      ),
    enabled: !!portfolio.data && !!session.data,
  });
  const p = portfolio.data;
  const r = risk.data;
  const loading = portfolio.isFetching || risk.isFetching;
  const selection = {
    mode,
    dataset_id: mode === "kite" && dataset ? dataset : undefined,
    confidence: Number(confidence),
    window: Number(windowSize),
  };
  const riskKey = `${mode}:${dataset}:${confidence}:${windowSize}:${p?.total_value}:${p?.as_of}`;
  async function disconnect() {
    try {
      const result = await api<{ remote_revocation_confirmed: boolean }>(
        "/auth/kite/logout",
        { method: "POST" },
      );
      setMode("demo");
      await queryClient.invalidateQueries({ queryKey: ["session"] });
      if (!result.remote_revocation_confirmed)
        setLogoutError(
          new Error(
            "Local access cleared. Remote revocation could not be confirmed; revoke the session in Zerodha if needed.",
          ),
        );
    } catch (error) {
      setLogoutError(error as Error);
    }
  }
  function exportRun() {
    if (!r) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(r, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `vantage-risk-${r.run_id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="workspace">
      <aside className={`sidebar ${mobileNav ? "open" : ""}`}>
        <Link href="/" className="brand" aria-label="VANTAGE home">
          <span className="brand-mark">
            V<span />
          </span>
          <span>
            VANTAGE<small>PORTFOLIO INTELLIGENCE</small>
          </span>
        </Link>
        <button
          className="mobile-close icon-button"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        >
          <X size={20} />
        </button>
        <div className="workspace-label">
          WORKSPACE <span>01</span>
        </div>
        <nav aria-label="Primary navigation">
          {nav.map((item) => (
            <button
              key={item.name}
              className={tab === item.name ? "active" : ""}
              onClick={() => {
                setTab(item.name);
                setMobileNav(false);
              }}
            >
              <item.icon size={17} />
              <span>{item.name}</span>
              {tab === item.name && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-section-label">RESEARCH PROGRAM</div>
        <div className="research-note">
          <BarChart3 size={17} />
          <div>
            Quantitative research<small>Planned · Phase 3</small>
          </div>
        </div>
        <div className="research-note">
          <ShieldCheck size={17} />
          <div>
            AI investigations<small>Planned · Phase 4</small>
          </div>
        </div>
        <div className="sidebar-bottom">
          <div className="read-only">
            <LockKeyhole size={15} />
            <div>
              Read-only by design<small>Trading is disabled</small>
            </div>
          </div>
          <div className="system-state">
            <span className={`status-dot ${health.data ? "" : "offline"}`} />
            {health.data
              ? "Analytics API connected"
              : health.isPending
                ? "Connecting to API"
                : "Analytics API unavailable"}
            <span>v0.2</span>
          </div>
          <div className="profile">
            <div className="avatar">VR</div>
            <div>
              VANTAGE Research<small>Local workspace</small>
            </div>
            <ChevronDown size={14} />
          </div>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              onClick={() => setMobileNav(true)}
              aria-label="Open navigation"
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{tab}</strong>
          </div>
          <div className="topbar-right">
            <span className="read-only-pill">
              <LockKeyhole size={12} /> READ ONLY
            </span>
            <span className={`mode-pill ${mode === "demo" ? "demo" : ""}`}>
              <span className="status-dot" />
              {mode === "demo" ? "DEMO ENVIRONMENT" : "KITE ACCOUNT"}
            </span>
            <a
              className="icon-button"
              href="/api/docs"
              target="_blank"
              rel="noreferrer"
              aria-label="API documentation"
            >
              <CircleHelp size={18} />
            </a>
          </div>
        </header>

        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">PORTFOLIO RISK WORKSPACE</div>
              <h1>
                {tab === "Overview"
                  ? "Your portfolio, in perspective."
                  : tab === "Portfolio"
                    ? "A clearer view of your capital."
                    : tab === "Risk Analytics"
                      ? "Understand the shape of risk."
                      : tab === "Stress Testing"
                        ? "Test the limits of your allocation."
                        : tab === "Risk Runs"
                          ? "Every result, reproducible."
                          : "Evidence starts at the source."}
              </h1>
              <p>
                {tab === "Data Sources"
                  ? "Connect permitted data. Preserve provenance. Keep every result traceable."
                  : "Transparent analytics for informed portfolio decisions."}
              </p>
            </div>
            <div className="heading-actions">
              <button
                className="button secondary"
                disabled={!r || loading}
                onClick={exportRun}
              >
                <Download size={15} />
                Export risk run
              </button>
              <button
                className="button primary"
                disabled={loading}
                onClick={() => void queryClient.invalidateQueries()}
              >
                <RefreshCw size={15} className={loading ? "spin" : ""} />
                {loading ? "Calculating" : "Refresh data"}
              </button>
            </div>
          </div>

          <div
            className={`environment-banner ${mode === "kite" ? "live" : ""}`}
          >
            <div>
              <span className="banner-icon">
                {mode === "demo" ? (
                  <Layers3 size={17} />
                ) : (
                  <LockKeyhole size={17} />
                )}
              </span>
              <strong>
                {mode === "demo"
                  ? "Synthetic demo portfolio"
                  : "Authorized Kite holdings"}
              </strong>
              <span>
                {mode === "demo"
                  ? "All securities and prices are synthetic. Explore the full workflow without credentials."
                  : "Read-only access. Risk requires independently sourced, adjusted history."}
              </span>
            </div>
            <button onClick={() => setTab("Data Sources")}>
              Manage sources
              <ArrowRight size={14} />
            </button>
          </div>

          <div className="control-bar">
            <div className="portfolio-select">
              <span className="small-label">PORTFOLIO</span>
              <label className="select-wrap">
                <Layers3 size={15} />
                <select
                  aria-label="Portfolio mode"
                  value={mode}
                  onChange={(e) => setMode(e.target.value as "demo" | "kite")}
                >
                  <option value="demo">Demo · India Equity</option>
                  <option value="kite">Kite · Authorized account</option>
                </select>
                <ChevronDown size={13} />
              </label>
            </div>
            <div className="control-right">
              {mode === "kite" && (
                <label className="control-field">
                  History
                  <select
                    aria-label="History dataset"
                    value={dataset}
                    onChange={(e) => setDataset(e.target.value)}
                  >
                    <option value="">Select imported dataset</option>
                    {history.data?.map((d) => (
                      <option value={d.id} key={d.id}>
                        {d.provenance.source.slice(0, 35)} · {d.provenance.end}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label className="control-field">
                Estimation window
                <select
                  aria-label="Estimation window"
                  value={windowSize}
                  onChange={(e) => setWindowSize(e.target.value)}
                >
                  <option value="126">126 observations</option>
                  <option value="252">252 observations</option>
                  <option value="504">504 observations</option>
                </select>
              </label>
              <label className="control-field">
                Confidence
                <select
                  aria-label="Confidence level"
                  value={confidence}
                  onChange={(e) => setConfidence(e.target.value)}
                >
                  <option value="0.95">95%</option>
                  <option value="0.99">99%</option>
                </select>
              </label>
              <div className="as-of">
                <span className="status-dot" />
                As of {p ? dateLabel(p.as_of) : "—"}
              </div>
            </div>
          </div>

          {session.error && <ErrorNotice error={session.error} />}
          {logoutError && <ErrorNotice error={logoutError} />}
          {tab === "Data Sources" ? (
            <Sources
              connected={session.data?.kite_connected || false}
              configured={session.data?.kite_configured || false}
              onDisconnect={disconnect}
              onImport={(id) => {
                setDataset(id);
                void queryClient.invalidateQueries({ queryKey: ["history"] });
              }}
            />
          ) : tab === "Risk Runs" ? (
            <RiskRuns key={mode} mode={mode} />
          ) : (
            <>
              {portfolio.error && <ErrorNotice error={portfolio.error} />}
              {portfolio.isPending && !portfolio.error && (
                <div className="loading-state">
                  <LoaderCircle className="spin" size={24} />
                  <p>Loading validated portfolio data…</p>
                </div>
              )}
              {p && (
                <>
                  <section className="metrics" aria-label="Portfolio metrics">
                    <Metric
                      title="Total portfolio value"
                      value={money(p.total_value)}
                      detail={`${p.holdings.length} securities · ${p.currency} cash equities`}
                      icon={<Layers3 size={17} />}
                      tag="HOLDINGS"
                    />
                    <Metric
                      title="Annualized volatility"
                      value={r ? pct(r.annualized_volatility) : "—"}
                      detail={
                        r
                          ? `${r.sample_size} daily returns · 252 days / year`
                          : "Historical data required"
                      }
                      icon={<Activity size={17} />}
                      tag="REALIZED"
                    />
                    <Metric
                      title={`Historical VaR · ${Number(confidence) * 100}%`}
                      value={r ? money(r.historical_var_amount) : "—"}
                      detail={
                        r
                          ? `${pct(r.historical_var)} of value · 1 trading day`
                          : "Historical data required"
                      }
                      icon={<ShieldCheck size={17} />}
                      tag="DOWNSIDE"
                      accent
                    />
                    <Metric
                      title="Largest position"
                      value={pct(p.largest_weight)}
                      detail={
                        p.holdings.reduce((a, b) =>
                          a.weight > b.weight ? a : b,
                        ).name
                      }
                      icon={<SlidersHorizontal size={17} />}
                      tag="CONCENTRATION"
                    />
                  </section>
                  {risk.error && <ErrorNotice error={risk.error} />}
                  {(tab === "Overview" || tab === "Risk Analytics") && (
                    <div className="analytics-grid">
                      <section className="panel main-chart">
                        <div className="panel-heading">
                          <div>
                            <h2>
                              Historical scenario path
                              <span className="subtle-badge">
                                {r ? `${r.sample_size}D` : "NO HISTORY"}
                              </span>
                            </h2>
                            <p>
                              Current weights applied to past returns ·
                              normalized to 100
                            </p>
                          </div>
                          <span className="chart-legend">
                            <i />
                            Portfolio
                          </span>
                        </div>
                        {r ? (
                          <>
                            <div className="chart-summary">
                              <strong>
                                {r.series.at(-1)?.scenario_index.toFixed(2)}
                              </strong>
                              <span>
                                Scenario index
                                <small>Not actual account performance</small>
                              </span>
                            </div>
                            <div className="chart-container">
                              <ResponsiveContainer width="100%" height="100%">
                                <AreaChart
                                  data={r.series}
                                  margin={{
                                    top: 12,
                                    right: 8,
                                    left: -20,
                                    bottom: 0,
                                  }}
                                >
                                  <defs>
                                    <linearGradient
                                      id="scenarioFill"
                                      x1="0"
                                      y1="0"
                                      x2="0"
                                      y2="1"
                                    >
                                      <stop
                                        offset="0%"
                                        stopColor="#64d9b4"
                                        stopOpacity={0.2}
                                      />
                                      <stop
                                        offset="100%"
                                        stopColor="#64d9b4"
                                        stopOpacity={0}
                                      />
                                    </linearGradient>
                                  </defs>
                                  <CartesianGrid
                                    stroke="#253137"
                                    vertical={false}
                                    strokeDasharray="3 4"
                                  />
                                  <XAxis
                                    dataKey="date"
                                    tickFormatter={(d) => dateLabel(d).slice(3)}
                                    minTickGap={75}
                                    tickLine={false}
                                    axisLine={false}
                                    tick={{ fill: "#87959c", fontSize: 11 }}
                                    dy={10}
                                  />
                                  <YAxis
                                    domain={["auto", "auto"]}
                                    tickLine={false}
                                    axisLine={false}
                                    tick={{ fill: "#87959c", fontSize: 11 }}
                                    tickFormatter={(v) => Number(v).toFixed(0)}
                                  />
                                  <Tooltip
                                    contentStyle={chartTooltip}
                                    labelFormatter={(v) => dateLabel(String(v))}
                                    formatter={(v) => [
                                      Number(v).toFixed(2),
                                      "Scenario index",
                                    ]}
                                  />
                                  <Area
                                    type="linear"
                                    dataKey="scenario_index"
                                    stroke="#64d9b4"
                                    strokeWidth={2}
                                    fill="url(#scenarioFill)"
                                    isAnimationActive={false}
                                  />
                                </AreaChart>
                              </ResponsiveContainer>
                            </div>
                            <div className="chart-footer">
                              <span>
                                {dateLabel(r.start)} — {dateLabel(r.end)}
                              </span>
                              <span>
                                <span className="status-dot" />
                                {p.synthetic
                                  ? "Synthetic history"
                                  : "Imported adjusted history"}
                              </span>
                            </div>
                          </>
                        ) : (
                          <div className="empty-chart">
                            <Activity size={30} />
                            <h3>Historical coverage needed</h3>
                            <p>
                              Import adjusted daily prices for every holding to
                              calculate risk.
                            </p>
                            <button
                              className="text-button"
                              onClick={() => setTab("Data Sources")}
                            >
                              Open data sources
                              <ArrowRight size={14} />
                            </button>
                          </div>
                        )}
                      </section>
                      <SectorPanel portfolio={p} />
                    </div>
                  )}
                  {tab === "Risk Analytics" && (
                    <AdvancedRisk key={riskKey} selection={selection} />
                  )}
                  {tab === "Risk Analytics" && r && <RiskDetail risk={r} />}
                  {tab === "Stress Testing" && (
                    <StressLab
                      key={riskKey}
                      portfolio={p}
                      selection={selection}
                      datasets={history.data ?? []}
                    />
                  )}
                  {(tab === "Overview" || tab === "Portfolio") && (
                    <Holdings portfolio={p} expanded={tab === "Portfolio"} />
                  )}
                  {tab === "Portfolio" && <SectorPanel portfolio={p} />}
                  <section className="provenance-strip">
                    <Database size={17} />
                    <div>
                      <strong>{p.source}</strong>
                      <p>
                        Snapshot {dateLabel(p.as_of)} · Retrieved{" "}
                        {new Date(p.retrieved_at).toLocaleString("en-GB", {
                          timeZone: "Asia/Kolkata",
                        })}{" "}
                        IST
                      </p>
                      <p>{p.price_timestamp_note}</p>
                      {r && (
                        <p>
                          History:{" "}
                          {r.provenance.adjustment.replaceAll("_", " ")} ·
                          SHA-256 {r.provenance.content_hash.slice(0, 16)}… ·
                          Method {r.methodology}
                        </p>
                      )}
                    </div>
                    <span className="subtle-badge">
                      {p.synthetic ? "SYNTHETIC" : "BROKER SOURCE"}
                    </span>
                  </section>
                  <div className="method-note">
                    <CircleHelp size={14} />
                    <p>
                      {r
                        ? `${r.horizon}. ${r.loss_convention}. Tail sample mass: ${r.tail_sample_mass.toFixed(2)} observations. `
                        : ""}
                      Holdings-only analysis excludes cash, open positions,
                      liquidity and costs. Past scenarios do not guarantee
                      future coverage. VaR is not maximum possible loss.
                    </p>
                  </div>
                </>
              )}
            </>
          )}
          <footer>
            <span>
              VANTAGE <span className="footer-divider">/</span> Precision
              through transparency.
            </span>
            <span>
              Phase 2 · Quantitative risk
              <LockKeyhole size={12} />
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
