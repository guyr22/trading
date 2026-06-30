"use client";

import { useState } from "react";
import { createTrade } from "../api";

interface Props {
  onTradeCreated: () => void;
}

export default function TradeForm({ onTradeCreated }: Props) {
  const [action, setAction] = useState<"BUY" | "SELL">("BUY");
  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [platform, setPlatform] = useState("");

  const calcFees = (plat: string, qty: string): string => {
    if (plat === "IBI") return "7.50";
    if (plat === "Interactive Brokers") {
      const q = parseFloat(qty);
      if (!isNaN(q) && q > 0) return Math.max(1.5, 0.007 * q).toFixed(2);
    }
    return "";
  };

  const fees = calcFees(platform, quantity);
  const [executedAt, setExecutedAt] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await createTrade({
        action,
        ticker: ticker.trim().toUpperCase(),
        quantity: parseFloat(quantity),
        price: parseFloat(price),
        fees: fees ? parseFloat(fees) : 0,
        platform: platform || null,
        executed_at: executedAt || undefined,
      });
      setAction("BUY");
      setTicker("");
      setQuantity("");
      setPrice("");
      setPlatform("");
      setExecutedAt("");
      onTradeCreated();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Trade failed");
    }
  };

  return (
    <>
      <h2>Record a Trade</h2>
      <form className="trade-form" onSubmit={handleSubmit}>
        <div className="form-row">
          <label>Action</label>
          <select value={action} onChange={(e) => setAction(e.target.value as "BUY" | "SELL")} required>
            <option value="BUY">Buy</option>
            <option value="SELL">Sell</option>
          </select>
        </div>
        <div className="form-row">
          <label>Ticker</label>
          <input type="text" placeholder="e.g. AAPL" required maxLength={10} value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} />
        </div>
        <div className="form-row">
          <label>Quantity</label>
          <input type="number" min="0.0001" step="any" required value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        </div>
        <div className="form-row">
          <label>Price ($)</label>
          <input type="number" min="0.001" step="any" required value={price} onChange={(e) => setPrice(e.target.value)} />
        </div>
        <div className="form-row">
          <label>Platform</label>
          <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
            <option value="">— Select —</option>
            <option value="Interactive Brokers">Interactive Brokers</option>
            <option value="IBI">IBI</option>
          </select>
        </div>
        <div className="form-row">
          <label>Fees ($)</label>
          <input type="number" min="0" step="0.01" placeholder="0.00" value={fees} disabled />
        </div>
        <div className="form-row">
          <label>Date</label>
          <div className="date-row">
            <input type="date" value={executedAt} onChange={(e) => setExecutedAt(e.target.value)} />
            <button type="button" className="btn-today" onClick={() => setExecutedAt(new Date().toISOString().slice(0, 10))}>Today</button>
          </div>
        </div>
        <button type="submit" className="btn-primary">Submit Trade</button>
        {error && <p className="msg msg-error">{error}</p>}
      </form>
    </>
  );
}
