"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { dateLabel, pct, type Risk } from "@/lib/api";
import { chartTooltip } from "@/lib/chart-theme";

export function RiskDetail({ risk: r }: { risk: Risk }) {
  return (
    <>
      <div className="risk-detail-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Rolling realized volatility</h2>
              <p>21 observed returns · annualized</p>
            </div>
            <strong>{pct(r.annualized_volatility)}</strong>
          </div>
          <div className="mini-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={r.series} margin={{ right: 20, left: 0 }}>
                <CartesianGrid stroke="#253137" vertical={false} />
                <XAxis dataKey="date" hide />
                <YAxis
                  tickFormatter={(v) => pct(v, 0)}
                  tick={{ fill: "#87959c", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={chartTooltip}
                  labelFormatter={(v) => dateLabel(String(v))}
                  formatter={(v) => [pct(Number(v)), "Volatility"]}
                />
                <Line
                  type="linear"
                  dataKey="rolling_volatility"
                  stroke="#779cf5"
                  dot={false}
                  strokeWidth={1.8}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Scenario drawdown</h2>
              <p>Includes the initial wealth baseline</p>
            </div>
            <strong className="negative">{pct(r.maximum_drawdown)}</strong>
          </div>
          <div className="mini-chart">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={r.series} margin={{ right: 20, left: 0 }}>
                <CartesianGrid stroke="#253137" vertical={false} />
                <XAxis dataKey="date" hide />
                <YAxis
                  tickFormatter={(v) => pct(v, 0)}
                  tick={{ fill: "#87959c", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={chartTooltip}
                  labelFormatter={(v) => dateLabel(String(v))}
                  formatter={(v) => [pct(Number(v)), "Drawdown"]}
                />
                <Area
                  type="linear"
                  dataKey="drawdown"
                  stroke="#df8a96"
                  fill="#df8a9615"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>
      <section className="panel correlation-panel">
        <div className="panel-heading">
          <div>
            <h2>Return correlation</h2>
            <p>Aligned observations · sample covariance uses ddof = 1</p>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>INSTRUMENT</th>
                {r.instruments.map((i) => (
                  <th className="numeric" key={i}>
                    {i.split(":")[1]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {r.correlation.map((row, i) => (
                <tr key={r.instruments[i]}>
                  <td>{r.instruments[i]}</td>
                  {row.map((v, j) => (
                    <td
                      className="numeric correlation-cell"
                      key={j}
                      style={{
                        background:
                          v === null
                            ? undefined
                            : `rgba(100,217,180,${Math.abs(v) * 0.16})`,
                      }}
                    >
                      {v === null ? "N/A" : v.toFixed(2)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-footer">
          <span>Undefined zero-variance correlations display N/A</span>
          <span>Run {r.run_id.slice(0, 8)}</span>
        </div>
      </section>
    </>
  );
}
