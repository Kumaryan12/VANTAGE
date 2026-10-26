"use client";

import { useState } from "react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { money, pct, type Portfolio } from "@/lib/api";
import { colors, chartTooltip } from "@/lib/chart-theme";

export function Metric({
  title,
  value,
  detail,
  icon,
  tag,
  accent,
}: {
  title: string;
  value: string;
  detail: string;
  icon: React.ReactNode;
  tag: string;
  accent?: boolean;
}) {
  return (
    <article className={`metric ${accent ? "accent" : ""}`}>
      <div className="metric-top">
        <span>{title}</span>
        {icon}
      </div>
      <strong>{value}</strong>
      <div className="metric-bottom">
        <span>{detail}</span>
        <small>{tag}</small>
      </div>
    </article>
  );
}

export function SectorPanel({ portfolio }: { portfolio: Portfolio }) {
  const data = Object.entries(portfolio.sectors).map(([name, value]) => ({
    name,
    value,
  }));
  return (
    <section className="panel sector-panel">
      <div className="panel-heading">
        <div>
          <h2>Sector allocation</h2>
          <p>Exposure by current market value</p>
        </div>
        <span className="subtle-badge">{data.length} SECTORS</span>
      </div>
      <div className="donut-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={64}
              outerRadius={82}
              paddingAngle={4}
              stroke="none"
              isAnimationActive={false}
            >
              {data.map((d, i) => (
                <Cell key={d.name} fill={colors[i % colors.length]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={chartTooltip}
              formatter={(v) => pct(Number(v))}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="donut-center">
          <strong>{portfolio.holdings.length}</strong>
          <span>SECURITIES</span>
        </div>
      </div>
      <div className="sector-list">
        {data.map((d, i) => (
          <div key={d.name}>
            <span>
              <i style={{ background: colors[i % colors.length] }} />
              {d.name}
            </span>
            <strong>{pct(d.value, 1)}</strong>
          </div>
        ))}
      </div>
      <div className="sector-footer">
        <span>Concentration index (HHI)</span>
        <strong>{portfolio.hhi.toFixed(3)}</strong>
      </div>
    </section>
  );
}

export function Holdings({
  portfolio: p,
  expanded,
}: {
  portfolio: Portfolio;
  expanded: boolean;
}) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<"weight" | "name">("weight");
  const rows = [...p.holdings]
    .filter((h) =>
      `${h.instrument} ${h.name} ${h.sector}`
        .toLowerCase()
        .includes(search.toLowerCase()),
    )
    .sort((a, b) =>
      sort === "weight" ? b.weight - a.weight : a.name.localeCompare(b.name),
    );
  return (
    <section className="panel holdings-panel">
      <div className="panel-heading">
        <div>
          <h2>
            Portfolio holdings
            <span className="count-badge">{p.holdings.length}</span>
          </h2>
          <p>Security-level valuation and allocation</p>
        </div>
        <div className="table-tools">
          {expanded && (
            <input
              aria-label="Search holdings"
              placeholder="Search securities…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          )}
          <select
            aria-label="Sort holdings"
            value={sort}
            onChange={(e) => setSort(e.target.value as "weight" | "name")}
          >
            <option value="weight">By allocation</option>
            <option value="name">By name</option>
          </select>
        </div>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>SECURITY</th>
              <th>SECTOR</th>
              <th className="numeric">QUANTITY</th>
              <th className="numeric">LAST PRICE</th>
              <th className="numeric">MARKET VALUE</th>
              <th className="numeric">UNREALIZED P&L</th>
              <th className="numeric">WEIGHT</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((h, i) => (
              <tr key={h.instrument}>
                <td>
                  <div className="security-cell">
                    <span
                      className="security-avatar"
                      style={{
                        color: colors[i % colors.length],
                        background: `${colors[i % colors.length]}13`,
                      }}
                    >
                      {h.instrument.split(":")[1].slice(0, 2)}
                    </span>
                    <div>
                      <strong>{h.instrument.split(":")[1]}</strong>
                      <small>{h.name}</small>
                    </div>
                  </div>
                </td>
                <td>
                  <span className="sector-tag">{h.sector}</span>
                </td>
                <td className="numeric">
                  {h.quantity.toLocaleString("en-IN")}
                </td>
                <td className="numeric">{money(h.last_price)}</td>
                <td className="numeric value-cell">{money(h.value)}</td>
                <td
                  className={`numeric ${h.unrealized_pnl >= 0 ? "positive" : "negative"}`}
                >
                  <span className="pnl">
                    {h.unrealized_pnl >= 0 ? (
                      <ArrowUpRight size={12} />
                    ) : (
                      <ArrowDownRight size={12} />
                    )}{" "}
                    {money(h.unrealized_pnl)}
                  </span>
                </td>
                <td className="numeric">
                  <div className="weight-cell">
                    <span>{pct(h.weight, 1)}</span>
                    <div>
                      <i style={{ width: pct(h.weight, 2) }} />
                    </div>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <div className="empty-state">No securities match your search.</div>
        )}
      </div>
      <div className="table-footer">
        <span>
          {p.synthetic
            ? "Synthetic securities · Demo dataset v1"
            : "Kite holdings · positions excluded"}
        </span>
        <span>
          Total value<strong>{money(p.total_value)}</strong>
        </span>
      </div>
    </section>
  );
}
