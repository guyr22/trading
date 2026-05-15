"use client";

import { useState } from "react";
import { createTrade, type TradePayload } from "../api";

interface Props {
  action: "BUY" | "SELL";
  ticker: string;
  currentPrice: number;
  defaultPlatform?: string;
  onClose: () => void;
  onSuccess: () => void;
  createFn?: (payload: TradePayload) => Promise<unknown>;
}

const calcFees = (plat: string, qty: string): string => {
  if (plat === "IBI") return "7.50";
  if (plat === "Interactive Brokers") {
    const q = parseFloat(qty);
    if (!isNaN(q) && q > 0) return Math.max(1.5, 0.007 * q).toFixed(2);
  }
  return "";
};

export default function QuickTradeModal({ action, ticker, currentPrice, defaultPlatform = "", onClose, onSuccess, createFn = createTrade }: Props) {
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState(currentPrice.toString());
  const [platform, setPlatform] = useState(defaultPlatform);
  const [error, setError] = useState("");

  const fees = calcFees(platform, quantity);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await createFn({
        action,
        ticker,
        quantity: parseFloat(quantity),
        price: parseFloat(price),
        fees: fees ? parseFloat(fees) : 0,
        platform: platform || null,
        executed_at: new Date().toISOString().slice(0, 10),
      });
      onSuccess();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Trade failed");
    }
  };

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-header">
          <h3>{action === "BUY" ? "Buy" : "Sell"} {ticker}</h3>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <label>Quantity</label>
            <input type="number" min="0.0001" step="any" required value={quantity} onChange={(e) => setQuantity(e.target.value)} autoFocus />
          </div>
          <div className="form-row">
            <label>Price ($)</label>
            <input type="number" min="0.01" step="0.01" required value={price} onChange={(e) => setPrice(e.target.value)} />
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
          <button type="submit" className={`btn-primary ${action === "BUY" ? "btn-modal-buy" : "btn-modal-sell"}`}>
            {action === "BUY" ? "Buy" : "Sell"}
          </button>
          {error && <p className="msg msg-error">{error}</p>}
        </form>
      </div>
    </div>
  );
}
