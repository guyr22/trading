"use client";

import { useCallback, useEffect, useState } from "react";
import { createIndexTrade, fetchIndexPortfolio, fetchIndexTrades, type PortfolioSummary, type Trade } from "../api";
import QuickTradeModal from "./QuickTradeModal";

const INDEX_TICKERS = ["VOO", "SPY", "QQQ", "IBIT", "ETHA"];
const fmt = (n: number) => n.toLocaleString("en-US", { style: "currency", currency: "USD" });
const fmtPrice = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 3 });
const pnlClass = (n: number) => (n >= 0 ? "positive" : "negative");

export default function Indexes() {
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [trades, setTrades] = useState<Trade[] | null>(null);
  const [modal, setModal] = useState<{ action: "BUY" | "SELL"; ticker: string; price: number } | null>(null);

  const reload = useCallback(() => {
    Promise.all([fetchIndexPortfolio(), fetchIndexTrades()])
      .then(([p, t]) => { setPortfolio(p); setTrades(t); })
      .catch(console.error);
  }, []);

  // Poll like the Dashboard does. The backend only fetches index prices while
  // this page is being viewed, and it does so on a background thread — so
  // without a repeat request the first (cold) response would be the only one
  // we ever render, showing avg cost indefinitely.
  useEffect(() => {
    reload();
    const interval = setInterval(reload, 30000);
    return () => clearInterval(interval);
  }, [reload]);

  if (!portfolio || !trades) return <p className="empty-msg">Loading...</p>;

  // Monthly summary: group BUY trades by month per ticker
  const monthlyMap: Record<string, Record<string, { shares: number; invested: number }>> = {};
  for (const t of trades) {
    if (t.action !== "BUY") continue;
    const month = t.executed_at.slice(0, 7);
    if (!monthlyMap[month]) monthlyMap[month] = {};
    if (!monthlyMap[month][t.ticker]) monthlyMap[month][t.ticker] = { shares: 0, invested: 0 };
    monthlyMap[month][t.ticker].shares += t.quantity;
    monthlyMap[month][t.ticker].invested += t.quantity * t.price + (t.fees ?? 0);
  }
  const months = Object.keys(monthlyMap).sort().reverse();

  return (
    <>
      <h2 style={{ marginBottom: "1rem" }}>Index Positions</h2>
      <div className="summary-cards" style={{ marginBottom: "2rem" }}>
        {INDEX_TICKERS.map(ticker => {
          const pos = portfolio.positions.find(p => p.ticker === ticker);
          return (
            <div className="card" key={ticker}>
              <span className="card-label">{ticker}</span>
              {pos ? (
                <>
                  {pos.price_available ? (
                    <span className="card-value">{fmt(pos.market_value)}</span>
                  ) : (
                    <span className="card-value"><span className="skeleton" style={{ width: "6rem" }} /></span>
                  )}
                  <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                    {pos.quantity % 1 === 0 ? pos.quantity : pos.quantity.toFixed(2)} shares @ {fmtPrice(pos.avg_cost)}
                  </span>
                  {pos.price_available ? (
                    <span style={{ fontSize: "0.85rem", marginTop: "0.1rem" }} className={pnlClass(pos.unrealized_pnl)}>
                      {fmt(pos.unrealized_pnl)} ({pos.unrealized_pnl_pct.toFixed(2)}%)
                    </span>
                  ) : (
                    <span style={{ marginTop: "0.1rem" }}><span className="skeleton" /></span>
                  )}
                  <button
                    className="btn-quick btn-quick-buy"
                    style={{ marginTop: "0.75rem", alignSelf: "flex-start" }}
                    onClick={() => setModal({ action: "BUY", ticker, price: pos.current_price })}
                  >
                    Buy
                  </button>
                </>
              ) : (
                <>
                  <span className="card-value" style={{ color: "var(--text-muted)" }}>No position</span>
                  <button
                    className="btn-quick btn-quick-buy"
                    style={{ marginTop: "0.75rem", alignSelf: "flex-start" }}
                    onClick={() => setModal({ action: "BUY", ticker, price: 0 })}
                  >
                    Buy
                  </button>
                </>
              )}
            </div>
          );
        })}
      </div>

      <h2 style={{ marginBottom: "1rem" }}>Monthly Purchases</h2>
      {months.length === 0 ? (
        <p className="empty-msg">No index purchases recorded yet.</p>
      ) : (
        <table style={{ marginBottom: "2rem" }}>
          <thead>
            <tr>
              <th>Month</th>
              {INDEX_TICKERS.map(t => <th key={t}>{t}</th>)}
              <th>Total Invested</th>
            </tr>
          </thead>
          <tbody>
            {months.map(month => {
              const row = monthlyMap[month];
              const total = Object.values(row).reduce((s, v) => s + v.invested, 0);
              return (
                <tr key={month}>
                  <td>{month.slice(5)}/{month.slice(2, 4)}</td>
                  {INDEX_TICKERS.map(t => (
                    <td key={t}>
                      {row[t] ? (
                        <span title={`${row[t].shares} shares`}>{fmt(row[t].invested)}</span>
                      ) : (
                        <span style={{ color: "var(--text-muted)" }}>—</span>
                      )}
                    </td>
                  ))}
                  <td><strong>{fmt(total)}</strong></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <h2 style={{ marginBottom: "1rem" }}>Trade History</h2>
      {trades.length === 0 ? (
        <p className="empty-msg">No index trades recorded yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Action</th>
              <th>Ticker</th>
              <th>Qty</th>
              <th>Price</th>
              <th>Invested</th>
              <th>Fees</th>
            </tr>
          </thead>
          <tbody>
            {trades.map(t => (
              <tr key={t.id}>
                <td>{new Date(t.executed_at).toLocaleDateString("en-GB")}</td>
                <td><span className={`tag ${t.action === "BUY" ? "tag-buy" : "tag-sell"}`}>{t.action}</span></td>
                <td><strong>{t.ticker}</strong></td>
                <td>{t.quantity % 1 === 0 ? t.quantity : t.quantity.toFixed(2)}</td>
                <td>{fmtPrice(t.price)}</td>
                <td>{fmt(t.quantity * t.price)}</td>
                <td>{t.fees ? fmt(t.fees) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {modal && (
        <QuickTradeModal
          action={modal.action}
          ticker={modal.ticker}
          currentPrice={modal.price}
          defaultPlatform="IBI"
          createFn={createIndexTrade}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); reload(); }}
        />
      )}
    </>
  );
}
