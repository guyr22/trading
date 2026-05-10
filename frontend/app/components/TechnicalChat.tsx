"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { sendTechnicalChatMessage, fetchTaPrompt, saveTaPrompt, type ChatMessage } from "../api";

const PROVIDERS = [
  { value: "claude",   label: "Claude (Sonnet)",  color: "#d97706" },
  { value: "openai",   label: "ChatGPT (4o)",     color: "#10a37f" },
  { value: "gemini",   label: "Gemini 3 Flash",   color: "#4285f4" },
  { value: "gemini25", label: "Gemini 2.5 Flash", color: "#4285f4" },
];

interface TechnicalMessage extends ChatMessage {
  imageUrls?: string[];  // data URLs for display only
}

const STORAGE_KEY = "analyst_chat_history";
const MAX_HISTORY = 30;

interface Conversation {
  id: string;
  createdAt: number;
  title: string;
  // imageUrls stripped — too large for localStorage
  messages: ChatMessage[];
  provider: string;
}

function loadHistory(): Conversation[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function saveHistory(history: Conversation[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(0, MAX_HISTORY)));
  } catch {}
}

function makeTitle(messages: TechnicalMessage[]) {
  const first = messages.find(m => m.role === "user");
  const text = first?.content?.trim() || (first?.imageUrls?.length ? "[chart]" : "New conversation");
  return text.length > 60 ? text.slice(0, 60) + "…" : text;
}

export default function TechnicalChat() {
  const [messages, setMessages] = useState<TechnicalMessage[]>([]);
  const [input, setInput] = useState("");
  const [provider, setProvider] = useState("claude");
  const [loading, setLoading] = useState(false);
  const [streamingReply, setStreamingReply] = useState("");
  const [error, setError] = useState("");
  const [pendingImages, setPendingImages] = useState<string[]>([]);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  const [convId, setConvId] = useState(() => crypto.randomUUID());
  const [history, setHistory] = useState<Conversation[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);

  // System prompt
  const [systemPrompt, setSystemPrompt] = useState("");
  const [promptOpen, setPromptOpen] = useState(false);
  const [promptSaved, setPromptSaved] = useState(false);
  const [promptLoading, setPromptLoading] = useState(false);

  // Image
  const fileInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchTaPrompt().then(setSystemPrompt).catch(() => {});
    const h = loadHistory();
    setHistory(h);
    if (h.length > 0) {
      const latest = h[0];
      setConvId(latest.id);
      setMessages(latest.messages);
      setProvider(latest.provider);
    }
  }, []);

  useEffect(() => {
    if (!lightboxSrc) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setLightboxSrc(null); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [lightboxSrc]);

  // Persist current conversation (strip imageUrls to keep localStorage small)
  useEffect(() => {
    if (messages.length === 0) return;
    const stripped: ChatMessage[] = messages.map(({ role, content }) => ({ role, content }));
    const updated: Conversation = { id: convId, createdAt: Date.now(), title: makeTitle(messages), messages: stripped, provider };
    const h = loadHistory();
    const idx = h.findIndex(c => c.id === convId);
    if (idx >= 0) h[idx] = updated; else h.unshift(updated);
    saveHistory(h);
    setHistory(h);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingReply, loading]);

  const handleSavePrompt = async () => {
    setPromptLoading(true);
    try {
      await saveTaPrompt(systemPrompt);
      setPromptSaved(true);
      setTimeout(() => setPromptSaved(false), 2000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save prompt");
    } finally {
      setPromptLoading(false);
    }
  };

  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    files.forEach(file => {
      const reader = new FileReader();
      reader.onload = () => setPendingImages(prev => [...prev, reader.result as string]);
      reader.readAsDataURL(file);
    });
    e.target.value = "";
  };

  const startNewChat = () => {
    setConvId(crypto.randomUUID());
    setMessages([]);
    setError("");
    setInput("");
    setPendingImages([]);
    setHistoryOpen(false);
  };

  const loadConversation = (conv: Conversation) => {
    setConvId(conv.id);
    setMessages(conv.messages);
    setProvider(conv.provider);
    setHistoryOpen(false);
    setError("");
    setPendingImages([]);
  };

  const deleteConversation = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const h = history.filter(c => c.id !== id);
    saveHistory(h);
    setHistory(h);
    if (id === convId) startNewChat();
  };

  const send = useCallback(async () => {
    const text = input.trim();
    if ((!text && pendingImages.length === 0) || loading) return;
    setError("");

    const newMsg: TechnicalMessage = { role: "user", content: text || "Analyze these charts.", imageUrls: pendingImages.length ? [...pendingImages] : undefined };
    const next = [...messages, newMsg];
    setMessages(next);
    setInput("");
    const imagesToSend = [...pendingImages];
    setPendingImages([]);
    setLoading(true);
    setStreamingReply("");
    let reply = "";

    try {
      const chatMessages: ChatMessage[] = next.map(m => ({ role: m.role, content: m.content }));
      await sendTechnicalChatMessage(chatMessages, provider, (chunk) => {
        reply += chunk;
        setStreamingReply(reply);
      }, imagesToSend.length ? imagesToSend : undefined);
      setMessages([...next, { role: "assistant", content: reply }]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setStreamingReply("");
      setLoading(false);
    }
  }, [input, pendingImages, loading, messages, provider]);

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const imageItems = Array.from(e.clipboardData.items).filter(item => item.type.startsWith("image/"));
    if (!imageItems.length) return;
    e.preventDefault();
    imageItems.forEach(item => {
      const file = item.getAsFile();
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => setPendingImages(prev => [...prev, reader.result as string]);
      reader.readAsDataURL(file);
    });
  };

  const activeProvider = PROVIDERS.find(p => p.value === provider)!;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 160px)" }}>

      {/* System prompt (collapsible) */}
      <div style={{ marginBottom: "0.75rem", border: "1px solid var(--border)", borderRadius: "var(--radius)", overflow: "hidden" }}>
        <button
          onClick={() => setPromptOpen(o => !o)}
          style={{
            width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "0.5rem 0.75rem", background: "var(--surface)", border: "none", cursor: "pointer",
            color: "var(--text-muted)", fontSize: "0.8rem",
          }}
        >
          <span>System Prompt {systemPrompt ? `(${systemPrompt.length} chars)` : "(empty)"}</span>
          <span>{promptOpen ? "▲" : "▼"}</span>
        </button>
        {promptOpen && (
          <div style={{ padding: "0.75rem", borderTop: "1px solid var(--border)", background: "var(--bg)" }}>
            <textarea
              value={systemPrompt}
              onChange={e => setSystemPrompt(e.target.value)}
              placeholder="Paste your technical analysis system prompt here..."
              rows={6}
              style={{
                width: "100%", resize: "vertical", padding: "0.5rem", borderRadius: "var(--radius)",
                border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)",
                fontSize: "0.85rem", fontFamily: "inherit", boxSizing: "border-box",
              }}
            />
            <button
              onClick={handleSavePrompt}
              disabled={promptLoading}
              className="btn-primary"
              style={{ marginTop: "0.5rem", padding: "0.35rem 1rem", fontSize: "0.85rem" }}
            >
              {promptSaved ? "Saved!" : "Save"}
            </button>
          </div>
        )}
      </div>

      {/* Toolbar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {PROVIDERS.map(p => (
            <button key={p.value} onClick={() => setProvider(p.value)} style={{
              padding: "0.35rem 0.85rem", borderRadius: "999px",
              border: `1px solid ${provider === p.value ? p.color : "var(--border)"}`,
              background: provider === p.value ? `${p.color}22` : "transparent",
              color: provider === p.value ? p.color : "var(--text-muted)",
              fontSize: "0.8rem", cursor: "pointer", fontWeight: provider === p.value ? 600 : 400,
            }}>{p.label}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button
            onClick={() => setHistoryOpen(o => !o)}
            style={{
              padding: "0.35rem 0.85rem", borderRadius: "999px",
              border: `1px solid ${historyOpen ? "var(--accent)" : "var(--border)"}`,
              background: historyOpen ? "var(--accent)22" : "transparent",
              color: historyOpen ? "var(--accent)" : "var(--text-muted)",
              fontSize: "0.8rem", cursor: "pointer",
            }}
          >
            History {history.length > 0 && `(${history.length})`}
          </button>
          <button
            onClick={startNewChat}
            style={{ padding: "0.35rem 0.85rem", borderRadius: "999px", border: "1px solid var(--border)", background: "transparent", color: "var(--text-muted)", fontSize: "0.8rem", cursor: "pointer" }}
          >
            + New Chat
          </button>
        </div>
      </div>

      {/* History panel */}
      {historyOpen && (
        <div style={{
          marginBottom: "0.75rem",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          background: "var(--surface)",
          maxHeight: "220px",
          overflowY: "auto",
        }}>
          {history.length === 0 ? (
            <p style={{ padding: "0.75rem 1rem", color: "var(--text-muted)", fontSize: "0.85rem", margin: 0 }}>No past conversations</p>
          ) : history.map(conv => (
            <div
              key={conv.id}
              onClick={() => loadConversation(conv)}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "0.55rem 0.85rem",
                cursor: "pointer",
                borderBottom: "1px solid var(--border)",
                background: conv.id === convId ? "var(--accent)11" : "transparent",
                borderLeft: conv.id === convId ? "2px solid var(--accent)" : "2px solid transparent",
              }}
            >
              <div style={{ overflow: "hidden" }}>
                <div style={{ fontSize: "0.85rem", color: "var(--text)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{conv.title}</div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                  {new Date(conv.createdAt).toLocaleDateString()} · {conv.messages.length} messages
                </div>
              </div>
              <button
                onClick={(e) => deleteConversation(conv.id, e)}
                title="Delete"
                style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: "0.85rem", padding: "0.2rem 0.4rem", flexShrink: 0 }}
              >✕</button>
            </div>
          ))}
        </div>
      )}

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "1rem", padding: "0.5rem 0 1rem" }}>
        {messages.length === 0 && (
          <div style={{ color: "var(--text-muted)", textAlign: "center", marginTop: "3rem" }}>
            <p style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>Upload a chart and ask for analysis</p>
            <p style={{ fontSize: "0.85rem" }}>Paste a chart (Ctrl+V), attach with 📎, or type a question</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: m.role === "user" ? "flex-end" : "flex-start" }}>
            {m.imageUrls?.map((url, idx) => (
              <img
                key={idx}
                src={url}
                alt={`chart ${idx + 1}`}
                onClick={() => setLightboxSrc(url)}
                style={{ maxWidth: "75%", maxHeight: "320px", borderRadius: "8px", marginBottom: "0.4rem", objectFit: "contain", border: "1px solid var(--border)", cursor: "zoom-in", display: "block" }}
              />
            ))}
            {(m.content || !m.imageUrls?.length) && (
              <div style={{
                maxWidth: "75%", padding: "0.65rem 1rem", borderRadius: "12px", fontSize: "0.9rem",
                lineHeight: "1.5", whiteSpace: m.role === "user" ? "pre-wrap" : undefined,
                background: m.role === "user" ? "var(--accent)" : "var(--surface)",
                color: m.role === "user" ? "#fff" : "var(--text)",
                border: m.role === "assistant" ? "1px solid var(--border)" : "none",
                borderBottomRightRadius: m.role === "user" ? "4px" : "12px",
                borderBottomLeftRadius: m.role === "assistant" ? "4px" : "12px",
              }}>
                {m.role === "assistant"
                  ? <div className="md-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
                  : m.content}
              </div>
            )}
          </div>
        ))}
        {streamingReply && (
          <div style={{ display: "flex", justifyContent: "flex-start" }}>
            <div style={{ maxWidth: "75%", padding: "0.65rem 1rem", borderRadius: "12px", borderBottomLeftRadius: "4px", background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)", fontSize: "0.9rem" }}>
              <div className="md-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingReply}</ReactMarkdown></div>
            </div>
          </div>
        )}
        {loading && !streamingReply && (
          <div style={{ display: "flex", justifyContent: "flex-start" }}>
            <div style={{ padding: "0.65rem 1rem", borderRadius: "12px", borderBottomLeftRadius: "4px", background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text-muted)", fontSize: "0.9rem" }}>
              {activeProvider.label} is analyzing...
            </div>
          </div>
        )}
        {error && <p className="msg msg-error">{error}</p>}
        <div ref={bottomRef} />
      </div>

      {/* Pending images preview */}
      {pendingImages.length > 0 && (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          {pendingImages.map((src, idx) => (
            <div key={idx} style={{ position: "relative", display: "inline-block" }}>
              <img src={src} alt={`pending ${idx + 1}`} style={{ maxHeight: "80px", maxWidth: "120px", borderRadius: "6px", border: "1px solid var(--border)", objectFit: "cover" }} />
              <button
                onClick={() => setPendingImages(prev => prev.filter((_, i) => i !== idx))}
                style={{
                  position: "absolute", top: "-6px", right: "-6px", width: "18px", height: "18px",
                  borderRadius: "50%", border: "none", background: "#ef4444", color: "#fff",
                  fontSize: "0.7rem", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", lineHeight: 1,
                }}
              >✕</button>
            </div>
          ))}
        </div>
      )}

      {/* Input */}
      <div style={{ display: "flex", gap: "0.5rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border)", alignItems: "flex-end" }}>
        <input ref={fileInputRef} type="file" accept="image/*" multiple style={{ display: "none" }} onChange={handleImageSelect} />
        <button
          onClick={() => fileInputRef.current?.click()}
          title="Attach chart images"
          style={{
            padding: "0.6rem 0.75rem", borderRadius: "var(--radius)", border: "1px solid var(--border)",
            background: pendingImages.length ? "var(--accent)22" : "var(--surface)",
            color: pendingImages.length ? "var(--accent)" : "var(--text-muted)",
            cursor: "pointer", fontSize: "1rem", flexShrink: 0,
          }}
        >
          📎{pendingImages.length > 0 && ` ${pendingImages.length}`}
        </button>
        <textarea
          rows={1} value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKey} onPaste={handlePaste}
          placeholder={pendingImages.length ? "Add a comment or just send the images..." : "Paste a chart or ask about a setup..."}
          disabled={loading}
          style={{
            flex: 1, resize: "none", padding: "0.6rem 0.85rem", borderRadius: "var(--radius)",
            border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)",
            fontSize: "0.9rem", fontFamily: "inherit", outline: "none",
          }}
        />
        <button onClick={send} disabled={(!input.trim() && pendingImages.length === 0) || loading} className="btn-primary"
          style={{ padding: "0.6rem 1.25rem", alignSelf: "flex-end" }}>
          Send
        </button>
      </div>

      {lightboxSrc && (
        <div
          onClick={() => setLightboxSrc(null)}
          style={{
            position: "fixed", inset: 0, zIndex: 200,
            background: "rgba(0,0,0,0.85)",
            display: "flex", alignItems: "center", justifyContent: "center",
            cursor: "zoom-out",
          }}
        >
          <img
            src={lightboxSrc}
            alt="chart fullscreen"
            onClick={e => e.stopPropagation()}
            style={{ maxWidth: "90vw", maxHeight: "90vh", borderRadius: "8px", objectFit: "contain", cursor: "default" }}
          />
        </div>
      )}
    </div>
  );
}
