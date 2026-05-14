"use client";

import { useEffect, useState, useMemo } from "react";
import { fetchTrades, fetchStatistics, deleteTrade, updateTrade, type Trade, type ClosedLot, type TradePayload } from "../api";

const fmt = (n: number) => n.toLocaleString("en-US", { style: "currency", currency: "USD" });
const pnlClass = (n: number) => (n >= 0 ? "positive" : "negative");
const INDEX_TICKERS = new Set(["VOO", "SPY", "QQQ", "IBIT", "ETHA"]);

type View = "transactions" | "closed";

interface EditState {
  trade: Trade;
  action: "BUY" | "SELL";
  ticker: string;
  quantity: string;
  price: string;
  fees: string;
  platform: string;
  executed_at: string;
  saving: boolean;
  error: string | null;
}

export default function History() {
  const [view, setView] = useState<View>("closed");
  const [trades, setTrades] = useState<Trade[]>([]);
  const [closedLots, setClosedLots] = useState<ClosedLot[]>([]);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [editState, setEditState] = useState<EditState | null>(null);

  const defaultTxFilter = { ticker: "", action: "All", platform: "All", dateFrom: "", dateTo: "" };
  const [txFilter, setTxFilter] = useState(defaultTxFilter);

  const defaultClosedFilter = { ticker: "", result: "All", dateFrom: "", dateTo: "" };
  const [closedFilter, setClosedFilter] = useState(defaultClosedFilter);

  const loadTrades = () => fetchTrades().then(setTrades).catch(console.error);

  useEffect(() => {
    loadTrades();
    fetchStatistics().then(s => setClosedLots(s.closed_lots)).catch(console.error);
  }, []);

  const isLocked = (t: Trade): boolean =>
    trades.some(
      other =>
        other.ticker === t.ticker &&
        other.action !== t.action &&
        (other.executed_at > t.executed_at ||
          (other.executed_at === t.executed_at && other.id > t.id))
    );

  const openEdit = (t: Trade) => {
    setEditState({
      trade: t,
      action: t.action,
      ticker: t.ticker,
      quantity: String(t.quantity),
      price: String(t.price),
      fees: t.fees ? String(t.fees) : "",
      platform: t.platform || "",
      executed_at: t.executed_at.slice(0, 10),
      saving: false,
      error: null,
    });
  };

  const closeEdit = () => setEditState(null);

  const handleEditSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editState) return;
    setEditState(prev => prev && { ...prev, saving: true, error: null });
    const payload: Partial<TradePayload> = {
      action: editState.action,
      ticker: editState.ticker.toUpperCase().trim(),
      quantity: parseFloat(editState.quantity),
      price: parseFloat(editState.price),
      fees: editState.fees ? parseFloat(editState.fees) : 0,
      platform: editState.platform || null,
      executed_at: editState.executed_at,
    };
    try {
      await updateTrade(editState.trade.id, payload);
      await loadTrades();
      closeEdit();
    } catch (err) {
      setEditState(prev => prev && {
        ...prev,
        saving: false,
        error: err instanceof Error ? err.message : "Failed to update trade",
      });
    }
  };

  const handleDelete = async (t: Trade) => {
    if (!window.confirm(`Delete ${t.action} ${t.quantity} ${t.ticker} on ${new Date(t.executed_at).toLocaleDateString("en-GB")}?`)) return;
    setDeleteError(null);
    try {
      await deleteTrade(t.id);
      await loadTrades();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete trade");
    }
  };

  const filtered = trades.filter(t => !INDEX_TICKERS.has(t.ticker));

  const platformOptions = useMemo(() => {
    const seen = new Set<string>();
    for (const t of trades) {
      if (t.platform) seen.add(t.platform);
    }
    return Array.from(seen).sort();
  }, [trades]);

  const txFiltered = useMemo(() => {
    return filtered.filter(t => {
      if (txFilter.ticker && !t.ticker.toLowerCase().includes(txFilter.ticker.toLowerCase())) return false;
      if (txFilter.action !== "All" && t.action !== txFilter.action) return false;
      if (txFilter.platform !== "All" && t.platform !== txFilter.platform) return false;
      const dateStr = t.executed_at.slice(0, 10);
      if (txFilter.dateFrom && dateStr < txFilter.dateFrom) return false;
      if (txFilter.dateTo && dateStr > txFilter.dateTo) return false;
      return true;
    });
  }, [filtered, txFilter]);

  const closedFiltered = useMemo(() => {
    return closedLots.filter(lot => {
      if (closedFilter.ticker && !lot.ticker.toLowerCase().includes(closedFilter.ticker.toLowerCase())) return false;
      if (closedFilter.result === "Win" && lot.pnl <= 0) return false;
      if (closedFilter.result === "Loss" && lot.pnl > 0) return false;
      if (closedFilter.dateFrom && lot.close_date < closedFilter.dateFrom) return false;
      if (closedFilter.dateTo && lot.close_date > closedFilter.dateTo) return false;
      return true;
    });
  }, [closedLots, closedFilter]);

  return (
    <>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.75rem", marginBottom: "1.5rem" }}>
        <h2 style={{ margin: 0 }}>{view === "transactions" ? "Transaction History" : "Closed Trades"}</h2>
        <div style={{ display: "flex", marginLeft: "auto", border: "1px solid var(--border)", borderRadius: "var(--radius)", overflow: "hidden" }}>
          {(["closed", "transactions"] as View[]).map((v, i) => (
            <button
              key={v}
              onClick={() => { setView(v); setDeleteError(null); }}
              style={{
                padding: "0.4rem 1rem",
                fontSize: "0.85rem",
                fontWeight: 500,
                border: "none",
                borderLeft: i > 0 ? "1px solid var(--border)" : "none",
                borderRadius: 0,
                cursor: "pointer",
                background: view === v ? "var(--accent)" : "var(--surface)",
                color: view === v ? "#fff" : "var(--text-muted)",
                transition: "background 0.15s, color 0.15s",
              }}
            >
              {v === "transactions" ? "Transactions" : "Closed Trades"}
            </button>
          ))}
        </div>
      </div>

      {deleteError && (
        <p style={{ color: "var(--negative, #ef4444)", marginBottom: "0.75rem", fontSize: "0.875rem" }}>
          {deleteError}
        </p>
      )}

      {view === "transactions" && (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center", marginBottom: "1rem" }}>
            <input
              type="text"
              placeholder="Ticker"
              value={txFilter.ticker}
              onChange={e => setTxFilter(prev => ({ ...prev, ticker: e.target.value }))}
              style={{ width: "7rem", padding: "0.3rem 0.5rem", fontSize: "0.82rem", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}
            />
            <select
              value={txFilter.action}
              onChange={e => setTxFilter(prev => ({ ...prev, action: e.target.value }))}
              style={{ padding: "0.3rem 0.5rem", fontSize: "0.82rem", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}
            >
              <option value="All">All Actions</option>
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
            </select>
            <select
              value={txFilter.platform}
              onChange={e => setTxFilter(prev => ({ ...prev, platform: e.target.value }))}
              style={{ padding: "0.3rem 0.5rem", fontSize: "0.82rem", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}
            >
              <option value="All">All Platforms</option>
              {platformOptions.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
            <input
              type="date"
              value={txFilter.dateFrom}
              onChange={e => setTxFilter(prev => ({ ...prev, dateFrom: e.target.value }))}
              style={{ padding: "0.3rem 0.5rem", fontSize: "0.82rem", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}
            />
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>to</span>
            <input
              type="date"
              value={txFilter.dateTo}
              onChange={e => setTxFilter(prev => ({ ...prev, dateTo: e.target.value }))}
              style={{ padding: "0.3rem 0.5rem", fontSize: "0.82rem", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}
            />
            <button
              onClick={() => setTxFilter(defaultTxFilter)}
              style={{ padding: "0.3rem 0.65rem", fontSize: "0.82rem", background: "transparent", color: "var(--text-muted)", border: "1px solid var(--border)", borderRadius: "var(--radius)", cursor: "pointer" }}
            >
              Clear
            </button>
          </div>
          {txFiltered.length === 0 ? (
            <p className="empty-msg">{filtered.length === 0 ? "No trades recorded yet." : "No trades match the current filters."}</p>
          ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Action</th>
                  <th>Ticker</th>
                  <th>Qty</th>
                  <th>Price</th>
                  <th>Total</th>
                  <th>Fees</th>
                  <th>Platform</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {txFiltered.map((t) => {
                  const locked = isLocked(t);
                  return (
                    <tr key={t.id}>
                      <td>{new Date(t.executed_at).toLocaleDateString("en-GB")}</td>
                      <td><span className={`tag ${t.action === "BUY" ? "tag-buy" : "tag-sell"}`}>{t.action}</span></td>
                      <td><strong>{t.ticker}</strong></td>
                      <td>{t.quantity % 1 === 0 ? t.quantity : t.quantity.toFixed(2)}</td>
                      <td>{fmt(t.price)}</td>
                      <td>{fmt(t.quantity * t.price)}</td>
                      <td>{t.fees ? fmt(t.fees) : "—"}</td>
                      <td>{t.platform || "—"}</td>
                      <td style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                        <button
                          onClick={() => openEdit(t)}
                          disabled={locked}
                          title={locked ? "Cannot edit: a later trade depends on this one" : "Edit trade"}
                          style={{
                            padding: "0.25rem 0.6rem",
                            fontSize: "0.78rem",
                            border: "1px solid var(--border)",
                            borderRadius: "var(--radius)",
                            background: "transparent",
                            color: locked ? "var(--text-muted)" : "var(--accent)",
                            cursor: locked ? "not-allowed" : "pointer",
                            opacity: locked ? 0.4 : 1,
                          }}
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDelete(t)}
                          disabled={locked}
                          title={locked ? "Cannot delete: a later trade depends on this one" : "Delete trade"}
                          style={{
                            padding: "0.25rem 0.6rem",
                            fontSize: "0.78rem",
                            border: "1px solid var(--border)",
                            borderRadius: "var(--radius)",
                            background: "transparent",
                            color: locked ? "var(--text-muted)" : "#ef4444",
                            cursor: locked ? "not-allowed" : "pointer",
                            opacity: locked ? 0.4 : 1,
                          }}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          )}
        </>
      )}

      {editState && (
        <div
          onClick={(e) => e.target === e.currentTarget && closeEdit()}
          style={{
            position: "fixed", inset: 0, zIndex: 1000,
            background: "rgba(0,0,0,0.6)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <div style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            padding: "1.5rem",
            width: "min(420px, 90vw)",
            display: "flex", flexDirection: "column", gap: "1rem",
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h3 style={{ margin: 0, fontSize: "1.05rem" }}>Edit Trade</h3>
              <button
                onClick={closeEdit}
                style={{ background: "none", border: "none", fontSize: "1.4rem", cursor: "pointer", color: "var(--text-muted)", lineHeight: 1 }}
              >&times;</button>
            </div>
            <form onSubmit={handleEditSave} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              <div className="form-row">
                <label>Action</label>
                <select
                  value={editState.action}
                  onChange={e => setEditState(prev => prev && { ...prev, action: e.target.value as "BUY" | "SELL" })}
                  required
                >
                  <option value="BUY">BUY</option>
                  <option value="SELL">SELL</option>
                </select>
              </div>
              <div className="form-row">
                <label>Ticker</label>
                <input
                  type="text"
                  required
                  value={editState.ticker}
                  onChange={e => setEditState(prev => prev && { ...prev, ticker: e.target.value })}
                />
              </div>
              <div className="form-row">
                <label>Quantity</label>
                <input
                  type="number" min="0.0001" step="any" required
                  value={editState.quantity}
                  onChange={e => setEditState(prev => prev && { ...prev, quantity: e.target.value })}
                />
              </div>
              <div className="form-row">
                <label>Price ($)</label>
                <input
                  type="number" min="0.0001" step="any" required
                  value={editState.price}
                  onChange={e => setEditState(prev => prev && { ...prev, price: e.target.value })}
                />
              </div>
              <div className="form-row">
                <label>Fees ($)</label>
                <input
                  type="number" min="0" step="0.01" placeholder="0.00"
                  value={editState.fees}
                  onChange={e => setEditState(prev => prev && { ...prev, fees: e.target.value })}
                />
              </div>
              <div className="form-row">
                <label>Platform</label>
                <select
                  value={editState.platform}
                  onChange={e => setEditState(prev => prev && { ...prev, platform: e.target.value })}
                >
                  <option value="">— Select —</option>
                  <option value="Interactive Brokers">Interactive Brokers</option>
                  <option value="IBI">IBI</option>
                </select>
              </div>
              <div className="form-row">
                <label>Date</label>
                <input
                  type="date" required
                  value={editState.executed_at}
                  onChange={e => setEditState(prev => prev && { ...prev, executed_at: e.target.value })}
                />
              </div>
              {editState.error && (
                <p style={{ margin: 0, color: "var(--negative, #ef4444)", fontSize: "0.85rem" }}>{editState.error}</p>
              )}
              <button
                type="submit"
                disabled={editState.saving}
                className="btn-primary"
                style={{ marginTop: "0.25rem" }}
              >
                {editState.saving ? "Saving…" : "Save Changes"}
              </button>
            </form>
          </div>
        </div>
      )}

      {view === "closed" && (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center", marginBottom: "1rem" }}>
            <input
              type="text"
              placeholder="Ticker"
              value={closedFilter.ticker}
              onChange={e => setClosedFilter(prev => ({ ...prev, ticker: e.target.value }))}
              style={{ width: "7rem", padding: "0.3rem 0.5rem", fontSize: "0.82rem", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}
            />
            <select
              value={closedFilter.result}
              onChange={e => setClosedFilter(prev => ({ ...prev, result: e.target.value }))}
              style={{ padding: "0.3rem 0.5rem", fontSize: "0.82rem", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}
            >
              <option value="All">All Results</option>
              <option value="Win">Win</option>
              <option value="Loss">Loss</option>
            </select>
            <input
              type="date"
              value={closedFilter.dateFrom}
              onChange={e => setClosedFilter(prev => ({ ...prev, dateFrom: e.target.value }))}
              style={{ padding: "0.3rem 0.5rem", fontSize: "0.82rem", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}
            />
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>to</span>
            <input
              type="date"
              value={closedFilter.dateTo}
              onChange={e => setClosedFilter(prev => ({ ...prev, dateTo: e.target.value }))}
              style={{ padding: "0.3rem 0.5rem", fontSize: "0.82rem", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}
            />
            <button
              onClick={() => setClosedFilter(defaultClosedFilter)}
              style={{ padding: "0.3rem 0.65rem", fontSize: "0.82rem", background: "transparent", color: "var(--text-muted)", border: "1px solid var(--border)", borderRadius: "var(--radius)", cursor: "pointer" }}
            >
              Clear
            </button>
          </div>
          {closedFiltered.length === 0 ? (
            <p className="empty-msg">{closedLots.length === 0 ? "No closed trades yet." : "No trades match the current filters."}</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th>Qty</th>
                    <th>Opened</th>
                    <th>Closed</th>
                    <th>Avg Buy</th>
                    <th>Avg Sell</th>
                    <th>P&amp;L</th>
                    <th>Return</th>
                  </tr>
                </thead>
                <tbody>
                  {closedFiltered.map((lot, i) => (
                    <tr key={i}>
                      <td><strong>{lot.ticker}</strong></td>
                      <td>{lot.quantity % 1 === 0 ? lot.quantity : lot.quantity.toFixed(2)}</td>
                      <td>{lot.open_date.split("-").reverse().join("-")}</td>
                      <td>{lot.close_date.split("-").reverse().join("-")}</td>
                      <td>{fmt(lot.avg_buy_price)}</td>
                      <td>{fmt(lot.avg_sell_price)}</td>
                      <td className={pnlClass(lot.pnl)}>{fmt(lot.pnl)}</td>
                      <td className={pnlClass(lot.pnl_pct)}>{lot.pnl_pct >= 0 ? "+" : ""}{lot.pnl_pct.toFixed(2)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}
