"use client";

import { useEffect, useState, type ReactNode } from "react";
import { fetchStatistics, type PortfolioStatistics, type CumulativePoint } from "../api";

const fmt = (n: number) => n.toLocaleString("en-US", { style: "currency", currency: "USD" });
const pnlClass = (n: number) => (n >= 0 ? "positive" : "negative");

function StatCard({ label, value, valueClass, tip }: { label: string; value: ReactNode; valueClass?: string; tip: string }) {
  return (
    <div className="card">
      <div className="card-info">
        i
        <div className="card-tooltip">{tip}</div>
      </div>
      <span className="card-label">{label}</span>
      <span className={`card-value ${valueClass ?? ""}`}>{value}</span>
    </div>
  );
}

function CumulativeChart({ data }: { data: CumulativePoint[] }) {
  const [hovered, setHovered] = useState<{ i: number; x: number; y: number } | null>(null);

  if (data.length < 2) return <p className="empty-msg">Not enough closed trades for chart.</p>;

  const W = 800, H = 200, PX = 40, PY = 20;
  const values = data.map(d => d.cumulative_pnl);
  const minY = Math.min(0, ...values);
  const maxY = Math.max(0, ...values);
  const rangeY = maxY - minY || 1;

  const toX = (i: number) => PX + (i / (data.length - 1)) * (W - PX * 2);
  const toY = (v: number) => PY + ((maxY - v) / rangeY) * (H - PY * 2);

  const pts = data.map((d, i) => `${toX(i)},${toY(d.cumulative_pnl)}`).join(" ");
  const zeroY = toY(0);
  const lastVal = values[values.length - 1];
  const color = lastVal >= 0 ? "var(--green)" : "var(--red)";
  const fillColor = lastVal >= 0 ? "rgba(52,211,153,0.1)" : "rgba(248,113,113,0.1)";

  const labelIdxs = [0, Math.floor(data.length * 0.25), Math.floor(data.length * 0.5), Math.floor(data.length * 0.75), data.length - 1];

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const svgX = ((e.clientX - rect.left) / rect.width) * W;
    const chartX = Math.max(0, Math.min(svgX - PX, W - PX * 2));
    const i = Math.round((chartX / (W - PX * 2)) * (data.length - 1));
    const clamped = Math.max(0, Math.min(i, data.length - 1));
    setHovered({ i: clamped, x: toX(clamped), y: toY(data[clamped].cumulative_pnl) });
  };

  const hp = hovered ? data[hovered.i] : null;
  const tipW = 130, tipH = 36;
  const tipX = hovered ? Math.min(hovered.x + 8, W - tipW - 4) : 0;
  const tipY = hovered ? Math.max(hovered.y - tipH - 6, 4) : 0;

  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: "1rem", marginBottom: "2rem" }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", height: "200px", display: "block", cursor: "crosshair" }}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHovered(null)}
      >
        <line x1={PX} y1={zeroY} x2={W - PX} y2={zeroY} stroke="var(--border)" strokeWidth="1" />
        <polygon points={`${toX(0)},${zeroY} ${pts} ${toX(data.length - 1)},${zeroY}`} fill={fillColor} />
        <polyline points={pts} fill="none" stroke={color} strokeWidth="2" />
        {labelIdxs.map(i => (
          <text key={i} x={toX(i)} y={H - 2} textAnchor="middle" fontSize="10" fill="var(--text-muted)">
            {data[i].date.slice(8)}/{data[i].date.slice(5, 7)}/{data[i].date.slice(2, 4)}
          </text>
        ))}
        <text x={PX - 4} y={toY(maxY)} textAnchor="end" fontSize="10" fill="var(--text-muted)" dominantBaseline="middle">
          {fmt(maxY)}
        </text>
        <text x={PX - 4} y={toY(minY)} textAnchor="end" fontSize="10" fill="var(--text-muted)" dominantBaseline="middle">
          {fmt(minY)}
        </text>

        {hovered && hp && (
          <>
            <line x1={hovered.x} y1={PY} x2={hovered.x} y2={H - PY} stroke="var(--border)" strokeWidth="1" strokeDasharray="3 3" />
            <circle cx={hovered.x} cy={hovered.y} r={4} fill={color} stroke="var(--bg)" strokeWidth="1.5" />
            <rect x={tipX} y={tipY} width={tipW} height={tipH} rx="4" fill="var(--surface-alt, #1e1e2e)" stroke="var(--border)" strokeWidth="1" />
            <text x={tipX + tipW / 2} y={tipY + 13} textAnchor="middle" fontSize="10" fill="var(--text-muted)">
              {hp.date.slice(8)}/{hp.date.slice(5, 7)}/{hp.date.slice(2, 4)}
            </text>
            <text x={tipX + tipW / 2} y={tipY + 27} textAnchor="middle" fontSize="11" fontWeight="600" fill={hp.cumulative_pnl >= 0 ? "var(--green)" : "var(--red)"}>
              {fmt(hp.cumulative_pnl)}
            </text>
          </>
        )}
      </svg>
    </div>
  );
}

export default function Statistics() {
  const [data, setData] = useState<PortfolioStatistics | null>(null);

  useEffect(() => {
    fetchStatistics().catch(console.error).then(d => { if (d) setData(d); });
  }, []);

  if (!data) return <p className="empty-msg">Loading...</p>;

  return (
    <>
      <h2 style={{ marginBottom: "1rem" }}>Performance</h2>
      <div className="summary-cards" style={{ marginBottom: "2rem" }}>
        <StatCard label="Total P&L" value={fmt(data.total_pnl)} valueClass={pnlClass(data.total_pnl)} tip="Combined realized and unrealized profit/loss across all positions." />
        <StatCard label="Win Rate" value={`${data.win_rate.toFixed(1)}%`} tip="Percentage of closed lot positions that were profitable." />
        <StatCard label="Profit Factor" value={data.profit_factor.toFixed(2)} valueClass={pnlClass(data.profit_factor - 1)} tip="Total gains divided by total losses. Above 1.0 means overall profitable." />
        <StatCard label="Avg Win" value={fmt(data.avg_win)} valueClass="positive" tip="Average profit on winning closed positions." />
        <StatCard label="Avg Loss" value={fmt(data.avg_loss)} valueClass="negative" tip="Average loss on losing closed positions." />
        <StatCard label="Best Trade" value={fmt(data.best_trade)} valueClass="positive" tip="Highest profit realized in a single lot closure." />
        <StatCard label="Worst Trade" value={fmt(data.worst_trade)} valueClass="negative" tip="Largest loss realized in a single lot closure." />
        <StatCard label="Max Drawdown" value={`-${fmt(data.max_drawdown)}`} valueClass="negative" tip="Largest peak-to-trough decline in cumulative realized P&L over time." />
      </div>

      <h2 style={{ marginBottom: "1rem" }}>Activity &amp; Risk</h2>
      <div className="summary-cards" style={{ marginBottom: "2rem" }}>
        <StatCard label="Total Trades" value={data.total_trades} tip="Total number of individual buy and sell orders recorded." />
        <StatCard label="Total Fees" value={fmt(data.total_fees)} valueClass="negative" tip="Sum of all commissions and fees paid across every trade." />
        <StatCard label="Avg Fees / Trade" value={fmt(data.avg_fees_per_trade)} tip="Average commission paid per individual trade." />
        <StatCard label="Most Traded" value={data.most_traded_ticker || "—"} tip="Ticker with the highest number of recorded trades." />
        <StatCard label="Avg Holding" value={`${data.avg_holding_days.toFixed(1)}d`} tip="Average number of calendar days between opening and closing a lot." />
        <StatCard label="Largest Position" value={`${data.largest_position_pct.toFixed(1)}%`} tip="Largest open position as a percentage of total portfolio market value." />
      </div>

      <h2 style={{ marginBottom: "1rem" }}>Cumulative P&amp;L</h2>
      <CumulativeChart data={data.cumulative_pnl} />

      <h2 style={{ marginBottom: "1rem" }}>Monthly P&amp;L</h2>
      {data.monthly_pnl.length === 0 ? (
        <p className="empty-msg">No closed trades yet.</p>
      ) : (
        <table style={{ marginBottom: "2rem" }}>
          <thead>
            <tr>
              <th>Month</th>
              <th>Realized P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {[...data.monthly_pnl].reverse().map(m => (
              <tr key={m.month}>
                <td>{m.month}</td>
                <td className={pnlClass(m.realized_pnl)}>{fmt(m.realized_pnl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2 style={{ marginBottom: "1rem" }}>Per Ticker</h2>
      {data.ticker_stats.length === 0 ? (
        <p className="empty-msg">No trades yet.</p>
      ) : (
        <table style={{ marginBottom: "2rem" }}>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Closed Trades</th>
              <th>Realized P&amp;L</th>
              <th>Win Rate</th>
              <th>Fees Paid</th>
            </tr>
          </thead>
          <tbody>
            {data.ticker_stats.map(t => (
              <tr key={t.ticker}>
                <td><strong>{t.ticker}</strong></td>
                <td>{t.trades_count}</td>
                <td className={pnlClass(t.realized_pnl)}>{fmt(t.realized_pnl)}</td>
                <td>{t.win_rate.toFixed(1)}%</td>
                <td className="negative">{fmt(t.total_fees)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
