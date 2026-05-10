"use client";

import { useEffect, useState } from "react";
import { fetchLeveragedEtfs, createLeveragedEtf, deleteLeveragedEtf, type LeveragedEtf } from "../api";

export default function LeveragedEtfsPage() {
  const [etfs, setEtfs] = useState<LeveragedEtf[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ ticker: "", underlying: "", leverage_factor: "", name: "" });
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    try {
      setEtfs(await fetchLeveragedEtfs());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  };

  useEffect(() => { load(); }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    const factor = parseFloat(form.leverage_factor);
    if (isNaN(factor) || factor === 0) { setError("Leverage factor must be a non-zero number (e.g. 2, -3)"); return; }
    setSubmitting(true);
    try {
      await createLeveragedEtf({
        ticker: form.ticker.trim().toUpperCase(),
        underlying: form.underlying.trim().toUpperCase(),
        leverage_factor: factor,
        name: form.name.trim() || undefined,
      });
      setForm({ ticker: "", underlying: "", leverage_factor: "", name: "" });
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to add");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (ticker: string) => {
    setError("");
    try {
      await deleteLeveragedEtf(ticker);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to delete");
    }
  };

  const inputStyle = {
    padding: "0.5rem 0.75rem",
    borderRadius: "var(--radius)",
    border: "1px solid var(--border)",
    background: "var(--surface)",
    color: "var(--text)",
    fontSize: "0.9rem",
  };

  return (
    <div>
      <h2 style={{ marginBottom: "1.5rem" }}>Leveraged ETF Mappings</h2>

      {/* Add form */}
      <form onSubmit={handleAdd} style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1.5rem", alignItems: "flex-end" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>ETF Ticker</label>
          <input style={{ ...inputStyle, width: "90px" }} placeholder="TSLL" value={form.ticker}
            onChange={e => setForm(f => ({ ...f, ticker: e.target.value }))} required />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Underlying</label>
          <input style={{ ...inputStyle, width: "90px" }} placeholder="TSLA" value={form.underlying}
            onChange={e => setForm(f => ({ ...f, underlying: e.target.value }))} required />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Leverage (e.g. 2, -3)</label>
          <input style={{ ...inputStyle, width: "100px" }} placeholder="2" type="number" step="0.5" value={form.leverage_factor}
            onChange={e => setForm(f => ({ ...f, leverage_factor: e.target.value }))} required />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", flex: 1, minWidth: "160px" }}>
          <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Name (optional)</label>
          <input style={{ ...inputStyle, width: "100%" }} placeholder="Direxion Daily TSLA Bull 2X" value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
        </div>
        <button type="submit" className="btn-primary" disabled={submitting} style={{ padding: "0.5rem 1.25rem", alignSelf: "flex-end" }}>
          Add
        </button>
      </form>

      {error && <p className="msg msg-error" style={{ marginBottom: "1rem" }}>{error}</p>}

      {/* Table */}
      {etfs.length === 0 ? (
        <p className="empty-msg">No mappings yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>ETF</th>
              <th>Underlying</th>
              <th>Leverage</th>
              <th>Name</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {etfs.map(etf => (
              <tr key={etf.id}>
                <td><strong>{etf.ticker}</strong></td>
                <td>{etf.underlying}</td>
                <td style={{ color: etf.leverage_factor > 0 ? "#4ade80" : "#f87171" }}>
                  {etf.leverage_factor > 0 ? "+" : ""}{etf.leverage_factor}x
                </td>
                <td style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{etf.name ?? "—"}</td>
                <td>
                  <button
                    onClick={() => handleDelete(etf.ticker)}
                    style={{
                      padding: "0.25rem 0.6rem",
                      borderRadius: "4px",
                      border: "1px solid #dc262655",
                      background: "#dc262611",
                      color: "#f87171",
                      cursor: "pointer",
                      fontSize: "0.8rem",
                    }}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
