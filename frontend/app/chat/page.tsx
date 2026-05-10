"use client";

import { useState } from "react";
import Chat from "../components/Chat";
import TechnicalChat from "../components/TechnicalChat";

const MODES = [
  { value: "portfolio", label: "Portfolio Assistant" },
  { value: "technical", label: "Technical Analysis" },
];

export default function ChatPage() {
  const [mode, setMode] = useState<"portfolio" | "technical">("portfolio");

  return (
    <>
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
        {MODES.map(m => (
          <button
            key={m.value}
            onClick={() => setMode(m.value as typeof mode)}
            style={{
              padding: "0.4rem 1.1rem",
              borderRadius: "999px",
              border: `1px solid ${mode === m.value ? "var(--accent)" : "var(--border)"}`,
              background: mode === m.value ? "var(--accent)" : "transparent",
              color: mode === m.value ? "#fff" : "var(--text-muted)",
              fontSize: "0.85rem",
              fontWeight: mode === m.value ? 600 : 400,
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            {m.label}
          </button>
        ))}
      </div>

      {mode === "portfolio" ? <Chat /> : <TechnicalChat />}
    </>
  );
}
