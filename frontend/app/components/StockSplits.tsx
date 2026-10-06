"use client";

import { useEffect, useState } from "react";
import { createSplit, deleteSplit, fetchSplits, type StockSplit } from "../api";

function localToday() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

export default function StockSplits() {
  const [splits, setSplits] = useState<StockSplit[] | null>(null);
  const [ticker, setTicker] = useState("");
  const [newShares, setNewShares] = useState("2");
  const [oldShares, setOldShares] = useState("1");
  const [executedAt, setExecutedAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [success, setSuccess] = useState("");
  const ratio = Number(newShares) / Number(oldShares);
  const validRatio = Number(newShares) > 0 && Number(oldShares) > 0 && Number.isFinite(ratio) && ratio > 0 && ratio !== 1;
  const number = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 6 });

  const reload = async () => {
    try {
      setSplits(await fetchSplits());
      setLoadError("");
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load splits");
    }
  };

  useEffect(() => { void reload(); }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy || !validRatio) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const split = await createSplit({ ticker: ticker.trim().toUpperCase(), new_shares: Number(newShares),
        old_shares: Number(oldShares), executed_at: executedAt });
      setSuccess(`${split.ticker} ${number(split.new_shares)}:${number(split.old_shares)} split recorded. Holdings and cost basis have been recalculated.`);
      setTicker("");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to record split");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (split: StockSplit) => {
    if (!window.confirm(`Remove the ${split.ticker} ${split.new_shares}:${split.old_shares} split on ${split.executed_at}? Holdings will be recalculated.`)) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await deleteSplit(split.id);
      setSuccess(`${split.ticker} split removed. Holdings and cost basis have been recalculated.`);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove split");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <h2>Record a Stock Split</h2>
      <p className="split-description">
        Adjust shares and average cost for a stock or index fund split. Applies to holdings across all your platforms;
        original trades and total cost basis are preserved. Live prices continue to update automatically.
      </p>
      <form className="trade-form" onSubmit={submit}>
        <div className="form-row">
          <label htmlFor="split-ticker">Ticker</label>
          <input id="split-ticker" required maxLength={10} placeholder="e.g. AAPL" value={ticker}
            onChange={e => setTicker(e.target.value.toUpperCase())} />
        </div>
        <div className="split-ratio">
          <div className="form-row">
            <label htmlFor="split-new">New shares</label>
            <input id="split-new" type="number" min="0.000001" step="any" required value={newShares}
              onChange={e => setNewShares(e.target.value)} />
          </div>
          <span aria-hidden="true">:</span>
          <div className="form-row">
            <label htmlFor="split-old">Old shares</label>
            <input id="split-old" type="number" min="0.000001" step="any" required value={oldShares}
              onChange={e => setOldShares(e.target.value)} />
          </div>
        </div>
        <p className="split-hint" aria-live="polite">
          {validRatio ? `For every ${number(Number(oldShares))} old ${Number(oldShares) === 1 ? "share" : "shares"}, you receive ${number(Number(newShares))} new ${Number(newShares) === 1 ? "share" : "shares"}.
            10 shares at $100 average cost become ${number(10 * ratio)} ${10 * ratio === 1 ? "share" : "shares"} at $${number(100 / ratio)}.` :
            "Enter a positive ratio different from 1:1. Use 1:10 for a reverse split."}
        </p>
        <div className="form-row">
          <label htmlFor="split-date">Effective date</label>
          <input id="split-date" type="date" required max={localToday()} value={executedAt}
            aria-describedby="split-date-help" onChange={e => setExecutedAt(e.target.value)} />
          <p id="split-date-help" className="split-hint">
            The first day trading uses the new share count and price. Trades on this date already use the new units.
          </p>
        </div>
        <button type="submit" className="btn-primary" disabled={busy || !validRatio}>
          {busy ? "Saving…" : "Record Split"}
        </button>
      </form>
      {error && <p className="msg msg-error" role="alert">{error}</p>}
      {success && <p className="msg" role="status">{success}</p>}
      <h2 style={{ marginTop: "2rem", marginBottom: "1rem" }}>Recorded Splits</h2>
      {loadError ? <p className="msg msg-error" role="alert">{loadError} <button className="nav-btn" onClick={reload}>Retry</button></p> :
        splits === null ? <p className="empty-msg">Loading splits…</p> :
        splits.length === 0 ? <p className="empty-msg">No splits recorded yet.</p> : (
          <div className="table-wrap split-history">
            <table>
              <thead><tr><th>Effective date</th><th>Ticker</th><th>New : Old</th><th>Type</th><th>Actions</th></tr></thead>
              <tbody>{splits.map(split => (
                <tr key={split.id}>
                  <td>{split.executed_at.split("-").reverse().join("-")}</td>
                  <td><strong>{split.ticker}</strong></td>
                  <td>{number(split.new_shares)} : {number(split.old_shares)}</td>
                  <td>{split.new_shares > split.old_shares ? "Forward split" : "Reverse split"}</td>
                  <td><button className="nav-btn" disabled={busy} aria-label={`Remove ${split.ticker} split on ${split.executed_at}`}
                    onClick={() => remove(split)}>Remove</button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      <p className="split-description">
        Fractional shares are retained. If your broker sold a fractional remainder, record that sale separately.
      </p>
    </>
  );
}
