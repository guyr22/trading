"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { fetchPortfolio, type PortfolioSummary, type Position } from "../api";
import QuickTradeModal from "./QuickTradeModal";

const fmt = (n: number) => n.toLocaleString("en-US", { style: "currency", currency: "USD" });
const pnlClass = (n: number) => (n >= 0 ? "positive" : "negative");
const INDEX_TICKERS = new Set(["VOO", "SPY", "QQQ", "IBIT", "ETHA"]);

export default function Dashboard() {
  const [data, setData] = useState<PortfolioSummary | null>(null);
  const [modal, setModal] = useState<{ action: "BUY" | "SELL"; ticker: string; price: number } | null>(null);

  const load = useCallback(async () => {
    try {
      const fresh = await fetchPortfolio();
      setData(fresh);
    } catch (err) {
      console.error("Failed to load portfolio:", err);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, [load]);

  if (!data) return <p className="empty-msg">Loading...</p>;

  return (
    <>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "1rem" }}>
        <Link href="/trade" className="btn-primary" style={{ textDecoration: "none", padding: "0.5rem 1.25rem", fontSize: "0.9rem" }}>
          + New Trade
        </Link>
      </div>
      <div className="summary-cards">
        <div className="card">
          <span className="card-label">Market Value</span>
          <span className="card-value">{fmt(data.total_market_value)}</span>
        </div>
        <div className="card">
          <span className="card-label">Unrealized P&L</span>
          <span className={`card-value ${pnlClass(data.total_unrealized_pnl)}`}>{fmt(data.total_unrealized_pnl)}</span>
        </div>
        <div className="card">
          <span className="card-label">Realized P&L</span>
          <span className={`card-value ${pnlClass(data.total_realized_pnl)}`}>{fmt(data.total_realized_pnl)}</span>
        </div>
      </div>

      <h2>Current Holdings</h2>

      {data.positions.filter(p => !INDEX_TICKERS.has(p.ticker)).length === 0 ? (
        <p className="empty-msg">No open positions yet. Place a trade to get started.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Qty</th>
                <th>Avg Cost</th>
                <th>Price</th>
                <th>Market Value</th>
                <th>P&L</th>
                <th>P&L %</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.positions.filter(p => !INDEX_TICKERS.has(p.ticker)).map((p: Position) => (
                <tr key={p.ticker}>
                  <td>
                    <strong>{p.ticker}</strong>
                    {p.leveraged_underlying && p.leverage_factor && (
                      <span style={{
                        marginLeft: "0.4rem",
                        fontSize: "0.7rem",
                        padding: "0.1rem 0.4rem",
                        borderRadius: "4px",
                        background: p.leverage_factor > 0 ? "#16a34a22" : "#dc262622",
                        color: p.leverage_factor > 0 ? "#4ade80" : "#f87171",
                        border: `1px solid ${p.leverage_factor > 0 ? "#16a34a55" : "#dc262655"}`,
                        whiteSpace: "nowrap",
                      }}>
                        {p.leverage_factor > 0 ? "+" : ""}{p.leverage_factor}x {p.leveraged_underlying}
                      </span>
                    )}
                  </td>
                  <td>{p.quantity % 1 === 0 ? p.quantity : p.quantity.toFixed(2)}</td>
                  <td>{fmt(p.avg_cost)}</td>
                  <td>{fmt(p.current_price)}</td>
                  <td>{fmt(p.market_value)}</td>
                  <td className={pnlClass(p.unrealized_pnl)}>{fmt(p.unrealized_pnl)}</td>
                  <td className={pnlClass(p.unrealized_pnl_pct)}>{p.unrealized_pnl_pct.toFixed(2)}%</td>
                  <td className="quick-actions">
                    <button className="btn-quick btn-quick-buy" onClick={() => setModal({ action: "BUY", ticker: p.ticker, price: p.current_price })}>Buy</button>
                    <button className="btn-quick btn-quick-sell" onClick={() => setModal({ action: "SELL", ticker: p.ticker, price: p.current_price })}>Sell</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modal && (
        <QuickTradeModal
          action={modal.action}
          ticker={modal.ticker}
          currentPrice={modal.price}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); load(); }}
        />
      )}
    </>
  );
}
