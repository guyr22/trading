"use client";

import { useEffect, useState } from "react";
import {
  fetchAlerts,
  createAlert,
  updateAlert,
  deleteAlert,
  fetchVapidKey,
  subscribePush,
  unsubscribePush,
  sendTestPush,
  type PriceAlert,
  type AlertCondition,
  type VapidKey,
} from "../api";
import { pushSupported, subscribe, unsubscribe, getExistingSubscription } from "../lib/push";

type Status = { type: "success" | "error" | "info"; text: string } | null;

const condText = (a: PriceAlert) =>
  `${a.condition === "ABOVE" ? "above" : "below"} $${a.target_price.toFixed(2)}`;

const distanceLabel = (a: PriceAlert): string => {
  if (a.current_price == null) return "price unavailable";
  const pct = ((a.target_price - a.current_price) / a.current_price) * 100;
  return `now $${a.current_price.toFixed(2)} · ${Math.abs(pct).toFixed(1)}% away`;
};

const rowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "0.75rem",
  padding: "0.75rem 1rem",
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius)",
  marginBottom: "0.5rem",
  flexWrap: "wrap",
};

export default function Alerts() {
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [vapid, setVapid] = useState<VapidKey | null>(null);
  const [perm, setPerm] = useState<NotificationPermission>("default");
  const [subscribed, setSubscribed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>(null);

  // form
  const [ticker, setTicker] = useState("");
  const [condition, setCondition] = useState<AlertCondition>("ABOVE");
  const [target, setTarget] = useState("");
  const [note, setNote] = useState("");
  const [formError, setFormError] = useState("");

  const load = async () => {
    try {
      setAlerts(await fetchAlerts());
    } catch {
      /* surfaced via empty state */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    fetchVapidKey().then(setVapid).catch(() => setVapid({ public_key: null, enabled: false }));
    if (pushSupported()) {
      setPerm(Notification.permission);
      getExistingSubscription().then((s) => setSubscribed(!!s));
    }
  }, []);

  const enable = async () => {
    setBusy(true);
    setStatus(null);
    try {
      if (!pushSupported()) throw new Error("This browser doesn't support push notifications.");
      if (!vapid?.enabled || !vapid.public_key) throw new Error("Push isn't configured on the server yet.");
      const permission = await Notification.requestPermission();
      setPerm(permission);
      if (permission !== "granted") throw new Error("Notification permission was not granted.");
      const sub = await subscribe(vapid.public_key);
      await subscribePush(sub);
      setSubscribed(true);
      setStatus({ type: "success", text: "Notifications enabled on this device." });
    } catch (e) {
      setStatus({ type: "error", text: e instanceof Error ? e.message : "Failed to enable notifications." });
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    setStatus(null);
    try {
      const endpoint = await unsubscribe();
      if (endpoint) await unsubscribePush(endpoint);
      setSubscribed(false);
      setStatus({ type: "info", text: "Notifications turned off on this device." });
    } catch (e) {
      setStatus({ type: "error", text: e instanceof Error ? e.message : "Failed to turn off notifications." });
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setStatus(null);
    try {
      const { sent } = await sendTestPush();
      setStatus({ type: "success", text: `Test notification sent to ${sent} device(s).` });
    } catch (e) {
      setStatus({ type: "error", text: e instanceof Error ? e.message : "Failed to send test." });
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    const price = parseFloat(target);
    if (!ticker.trim() || isNaN(price) || price <= 0) {
      setFormError("Enter a ticker and a target price greater than 0.");
      return;
    }
    try {
      await createAlert({
        ticker: ticker.trim().toUpperCase(),
        condition,
        target_price: price,
        note: note.trim() || null,
      });
      setTicker("");
      setTarget("");
      setNote("");
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to create alert.");
    }
  };

  const setActive = async (id: number, active: boolean) => {
    try {
      await updateAlert(id, active);
      await load();
    } catch (e) {
      setStatus({ type: "error", text: e instanceof Error ? e.message : "Update failed." });
    }
  };

  const remove = async (id: number) => {
    try {
      await deleteAlert(id);
      setAlerts((prev) => prev.filter((a) => a.id !== id));
    } catch (e) {
      setStatus({ type: "error", text: e instanceof Error ? e.message : "Delete failed." });
    }
  };

  const active = alerts.filter((a) => a.active);
  const inactive = alerts.filter((a) => !a.active);

  return (
    <>
      <h2 style={{ marginBottom: "1rem" }}>Price Alerts</h2>

      {/* Notification permission banner */}
      <NotificationBanner
        supported={pushSupported()}
        serverEnabled={vapid?.enabled ?? null}
        perm={perm}
        subscribed={subscribed}
        busy={busy}
        onEnable={enable}
        onDisable={disable}
        onTest={test}
      />
      {status && (
        <p className={`msg ${status.type === "error" ? "msg-error" : "msg-success"}`} style={{ marginTop: "0.5rem" }}>
          {status.text}
        </p>
      )}

      {/* Create alert */}
      <h2 style={{ margin: "2rem 0 1rem" }}>New alert</h2>
      <form className="trade-form" onSubmit={submit}>
        <div className="form-row">
          <label>Ticker</label>
          <input type="text" placeholder="e.g. NVDA" maxLength={10} value={ticker} onChange={(e) => setTicker(e.target.value)} />
        </div>
        <div className="form-row">
          <label>Condition</label>
          <select value={condition} onChange={(e) => setCondition(e.target.value as AlertCondition)}>
            <option value="ABOVE">Price rises above</option>
            <option value="BELOW">Price falls below</option>
          </select>
        </div>
        <div className="form-row">
          <label>Target ($)</label>
          <input type="number" min="0.01" step="any" placeholder="150.00" value={target} onChange={(e) => setTarget(e.target.value)} />
        </div>
        <div className="form-row">
          <label>Note</label>
          <input type="text" placeholder="optional" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <button type="submit" className="btn-primary">Add alert</button>
        {formError && <p className="msg msg-error">{formError}</p>}
      </form>

      {/* Active alerts */}
      <h2 style={{ margin: "2rem 0 1rem" }}>Active{active.length ? ` (${active.length})` : ""}</h2>
      {loading ? (
        <p className="empty-msg">Loading…</p>
      ) : active.length === 0 ? (
        <p className="empty-msg">No active alerts. Add one above.</p>
      ) : (
        active.map((a) => (
          <div key={a.id} style={rowStyle}>
            <div>
              <strong>{a.ticker}</strong> {condText(a)}
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                {distanceLabel(a)}
                {a.note ? ` · ${a.note}` : ""}
              </div>
            </div>
            <div style={{ display: "flex", gap: "0.4rem" }}>
              <button className="nav-btn" onClick={() => setActive(a.id, false)} title="Pause this alert">Pause</button>
              <button className="nav-btn" onClick={() => remove(a.id)} title="Delete this alert">🗑</button>
            </div>
          </div>
        ))
      )}

      {/* Triggered / paused */}
      {inactive.length > 0 && (
        <>
          <h2 style={{ margin: "2rem 0 1rem" }}>Triggered &amp; paused</h2>
          {inactive.map((a) => (
            <div key={a.id} style={{ ...rowStyle, opacity: 0.75 }}>
              <div>
                <strong>{a.ticker}</strong> {condText(a)}
                <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                  {a.triggered_at
                    ? `✓ fired ${new Date(a.triggered_at).toLocaleString()}`
                    : "paused"}
                  {a.note ? ` · ${a.note}` : ""}
                </div>
              </div>
              <div style={{ display: "flex", gap: "0.4rem" }}>
                <button className="nav-btn" onClick={() => setActive(a.id, true)} title="Re-arm this alert">Re-arm</button>
                <button className="nav-btn" onClick={() => remove(a.id)} title="Delete this alert">🗑</button>
              </div>
            </div>
          ))}
        </>
      )}
    </>
  );
}

function NotificationBanner({
  supported,
  serverEnabled,
  perm,
  subscribed,
  busy,
  onEnable,
  onDisable,
  onTest,
}: {
  supported: boolean;
  serverEnabled: boolean | null;
  perm: NotificationPermission;
  subscribed: boolean;
  busy: boolean;
  onEnable: () => void;
  onDisable: () => void;
  onTest: () => void;
}) {
  const box: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "0.75rem",
    padding: "0.85rem 1rem",
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    flexWrap: "wrap",
  };

  let content: React.ReactNode;
  if (!supported) {
    content = <span>🔕 This browser doesn&apos;t support push notifications.</span>;
  } else if (serverEnabled === false) {
    content = <span>⚙️ Push isn&apos;t configured on the server yet — alerts will still show here in the app.</span>;
  } else if (perm === "denied") {
    content = <span>🔕 Notifications are blocked. Enable them for this site in your browser settings.</span>;
  } else if (subscribed) {
    content = (
      <>
        <span>🔔 Push notifications are <strong>on</strong> for this device.</span>
        <span style={{ display: "flex", gap: "0.4rem" }}>
          <button className="nav-btn" onClick={onTest} disabled={busy}>Send test</button>
          <button className="nav-btn" onClick={onDisable} disabled={busy}>Turn off</button>
        </span>
      </>
    );
  } else {
    content = (
      <>
        <span>🔔 Get notified when a price target hits.</span>
        <button className="btn-primary" onClick={onEnable} disabled={busy} style={{ width: "auto" }}>
          {busy ? "Enabling…" : "Enable notifications"}
        </button>
      </>
    );
  }

  return (
    <div>
      <div style={box}>{content}</div>
      {supported && serverEnabled !== false && (
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: "0.4rem 0 0" }}>
          On iPhone/iPad, add this app to your Home Screen first (Share → Add to Home Screen) to receive notifications.
        </p>
      )}
    </div>
  );
}
