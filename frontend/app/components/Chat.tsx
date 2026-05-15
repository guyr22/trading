"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { sendChatMessage, fetchPortfolio, fetchStatistics, fetchInsights, fetchConversations, upsertConversation, deleteConversationApi, type ChatMessage, type Conversation } from "../api";
import { useAuth } from "../contexts/AuthContext";

const PROVIDERS = [
  { value: "gemini", label: "Gemini 3 Flash", color: "#4285f4" },
  { value: "gemini25", label: "Gemini 2.5 Flash", color: "#4285f4" },
];

const QUESTION_BANK: { category: string; questions: string[] }[] = [
  {
    category: "Portfolio Overview",
    questions: [
      "What's my current portfolio worth and how is it split across positions?",
      "Which position has the highest unrealized P&L right now?",
      "What's my overall win rate and profit factor across all closed trades?",
      "How does my realized P&L compare to a buy-and-hold in SPY over the same period?",
      "What's my maximum drawdown and when did it happen?",
    ],
  },
  {
    category: "Learning From Past Trades",
    questions: [
      "Where am I holding losers too long vs cutting winners short?",
      "Do I have a disposition effect problem? Show me the data.",
      "Which trades did I exit too early — what happened to the price 30, 60, and 90 days after I sold?",
      "What does my holding period look like for winners vs losers on average?",
      "What are the worst trades I've made, and what do they have in common?",
    ],
  },
  {
    category: "Behavioral Patterns & Mistakes",
    questions: [
      "Give me a full coaching summary — what are my biggest behavioral issues right now?",
      "Have I ever traded impulsively after a big loss? Show me any revenge trading patterns.",
      "What does my streak analysis look like — do I overtrade after wins or losses?",
      "Do I trade better or worse in certain months?",
      "What mistakes do I keep repeating?",
    ],
  },
  {
    category: "Specific Stock Analysis",
    questions: [
      "Walk me through my full history with a specific stock — every entry, exit, P&L, and holding period.",
      "How was my entry timing on a specific stock — was I buying near highs or lows?",
      "How did similar past trades in the same sector turn out?",
      "What's my track record with stocks in a specific sector?",
    ],
  },
  {
    category: "Risk & Concentration",
    questions: [
      "Am I too concentrated in any single position?",
      "How correlated are my open positions — am I really diversified?",
      "What sector is most of my portfolio exposed to?",
      "What's my Herfindahl concentration index and what does it mean for my risk?",
      "Which position is my biggest single-stock risk?",
    ],
  },
  {
    category: "Fees & Costs",
    questions: [
      "How much have I paid in total fees, broken down by platform?",
      "What percentage of my gross P&L is being eaten by fees?",
      "Which positions have the worst fee drag relative to their returns?",
    ],
  },
  {
    category: "Coaching & Improvement",
    questions: [
      "What are the top 3 things I should focus on to improve my trading?",
      "Based on my history, what type of setups do I actually perform best in?",
      "What's my average monthly P&L trend — am I improving over time?",
      "What's the one habit that's costing me the most money?",
      "If I keep trading the way I have been, what does my edge look like?",
    ],
  },
];

function makeTitle(messages: ChatMessage[]) {
  const first = messages.find(m => m.role === "user")?.content ?? "New conversation";
  return first.length > 60 ? first.slice(0, 60) + "…" : first;
}

export default function Chat() {
  const { user } = useAuth();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [provider, setProvider] = useState("gemini");
  const [loading, setLoading] = useState(false);
  const [streamingReply, setStreamingReply] = useState("");
  const [toolStatus, setToolStatus] = useState("");
  const [error, setError] = useState("");
  const [convId, setConvId] = useState(() => crypto.randomUUID());
  const [history, setHistory] = useState<Conversation[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [ideasOpen, setIdeasOpen] = useState(false);
  const [openCategory, setOpenCategory] = useState<string | null>(null);
  const [suggestedChips, setSuggestedChips] = useState<string[]>([]);
  const [insightFlag, setInsightFlag] = useState<string | null>(null);
  const [insightDismissed, setInsightDismissed] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load conversation history from API on mount
  useEffect(() => {
    fetchConversations().then(setHistory).catch(() => {});
  }, []);

  // Fetch behavioral insights on mount for the alert banner
  useEffect(() => {
    fetchInsights()
      .then((data) => {
        if (data.has_insights && data.flags.length > 0) {
          setInsightFlag(data.flags[0]);
        }
      })
      .catch(() => {
        // Silently ignore — banner simply won't appear
      });
  }, []);

  // Fetch portfolio data on mount to generate data-driven chips
  useEffect(() => {
    async function buildChips() {
      const fallback = [
        "What are my biggest open positions right now?",
        "Which trade has my best return?",
        "How much have I paid in fees total?",
        "What behavioral patterns do I have?",
        "How am I doing vs SPY?",
      ];
      try {
        const [portfolio, stats] = await Promise.all([fetchPortfolio(), fetchStatistics()]);

        const chips: string[] = [];

        // Chip 1: largest open position (specific ticker)
        if (portfolio.positions.length > 0) {
          const largest = portfolio.positions.reduce((a, b) =>
            Math.abs(b.market_value) > Math.abs(a.market_value) ? b : a
          );
          chips.push(`My ${largest.ticker} position is my largest — what's my risk?`);
        } else {
          chips.push("What are my biggest open positions right now?");
        }

        // Chip 2: fees total (specific number)
        if (stats.total_fees > 0) {
          chips.push(`I've paid $${stats.total_fees.toFixed(2)} in fees — is that reasonable?`);
        } else {
          chips.push("How much have I paid in fees total?");
        }

        // Chip 3: best or worst closed trade (specific ticker)
        if (stats.closed_lots && stats.closed_lots.length > 0) {
          const best = stats.closed_lots.reduce((a, b) => b.pnl > a.pnl ? b : a);
          if (best.pnl > 0) {
            chips.push(`Which trade has my best return? (${best.ticker} looks promising)`);
          } else {
            chips.push("Which trade has my best return?");
          }
        } else {
          chips.push("Which trade has my best return?");
        }

        // Chip 4: most traded ticker
        if (stats.most_traded_ticker) {
          chips.push(`I trade ${stats.most_traded_ticker} a lot — what patterns do you see?`);
        } else {
          chips.push("What behavioral patterns do I have?");
        }

        // Chip 5: overall P&L vs benchmark
        const totalPnl = stats.total_pnl;
        if (totalPnl !== 0) {
          const sign = totalPnl >= 0 ? "+" : "";
          chips.push(`I'm at ${sign}$${totalPnl.toFixed(0)} total P&L — how am I doing vs SPY?`);
        } else {
          chips.push("How am I doing vs SPY?");
        }

        setSuggestedChips(chips);
      } catch {
        setSuggestedChips(fallback);
      }
    }
    buildChips();
  }, []);


  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingReply, loading]);

  const startNewChat = () => {
    setConvId(crypto.randomUUID());
    setMessages([]);
    setError("");
    setInput("");
    setHistoryOpen(false);
  };

  const loadConversation = (conv: Conversation) => {
    setConvId(conv.id);
    setMessages(conv.messages);
    setProvider(conv.provider);
    setHistoryOpen(false);
    setError("");
  };

  const deleteConversation = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const h = history.filter(c => c.id !== id);
    setHistory(h);
    deleteConversationApi(id).catch(() => {});
    if (id === convId) startNewChat();
  };

  const send = useCallback(async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || loading) return;
    setError("");
    const next: ChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setLoading(true);
    setStreamingReply("");
    setToolStatus("");
    let reply = "";
    try {
      await sendChatMessage(
        next,
        provider,
        (chunk) => { reply += chunk; setStreamingReply(reply); },
        (toolName) => {
          const labels: Record<string, string> = {
            get_portfolio_statistics: "Fetching portfolio statistics...",
            get_ticker_analysis: "Analyzing ticker history...",
            get_behavioral_patterns: "Analyzing behavioral patterns...",
            get_post_exit_prices: "Checking post-exit prices...",
          };
          setToolStatus(labels[toolName] ?? `Running ${toolName}...`);
        },
      );
      const finalMessages: ChatMessage[] = [...next, { role: "assistant", content: reply }];
      setMessages(finalMessages);
      const title = makeTitle(finalMessages);
      upsertConversation(convId, title, finalMessages, provider)
        .then(() => fetchConversations())
        .then(setHistory)
        .catch(() => {});
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setStreamingReply("");
      setToolStatus("");
      setLoading(false);
    }
  }, [input, loading, messages, provider, convId]);

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const activeProvider = PROVIDERS.find(p => p.value === provider)!;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 160px)" }}>
      {/* Toolbar */}
      <div className="chat-toolbar">
      <div className="chat-toolbar-providers">
        {PROVIDERS.map(p => (
          <button
            key={p.value}
            onClick={() => setProvider(p.value)}
            style={{
              padding: "0.35rem 0.85rem",
              borderRadius: "999px",
              border: `1px solid ${provider === p.value ? p.color : "var(--border)"}`,
              background: provider === p.value ? `${p.color}22` : "transparent",
              color: provider === p.value ? p.color : "var(--text-muted)",
              fontSize: "0.8rem",
              cursor: "pointer",
              fontWeight: provider === p.value ? 600 : 400,
              transition: "all 0.15s",
            }}
          >
            {p.label}
          </button>
        ))}
      </div>
        <div className="chat-toolbar-actions">
          <button
            onClick={() => { setIdeasOpen(o => !o); setHistoryOpen(false); }}
            style={{
              padding: "0.35rem 0.85rem",
              borderRadius: "999px",
              border: `1px solid ${ideasOpen ? "var(--accent)" : "var(--border)"}`,
              background: ideasOpen ? "var(--accent)22" : "transparent",
              color: ideasOpen ? "var(--accent)" : "var(--text-muted)",
              fontSize: "0.8rem",
              cursor: "pointer",
            }}
          >
            Ideas
          </button>
          <button
            onClick={() => { setHistoryOpen(o => !o); setIdeasOpen(false); }}
            style={{
              padding: "0.35rem 0.85rem",
              borderRadius: "999px",
              border: `1px solid ${historyOpen ? "var(--accent)" : "var(--border)"}`,
              background: historyOpen ? "var(--accent)22" : "transparent",
              color: historyOpen ? "var(--accent)" : "var(--text-muted)",
              fontSize: "0.8rem",
              cursor: "pointer",
            }}
          >
            History {history.length > 0 && `(${history.length})`}
          </button>
          <button
            onClick={startNewChat}
            style={{
              padding: "0.35rem 0.85rem",
              borderRadius: "999px",
              border: "1px solid var(--border)",
              background: "transparent",
              color: "var(--text-muted)",
              fontSize: "0.8rem",
              cursor: "pointer",
            }}
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
                  {new Date(conv.created_at).toLocaleDateString()} · {conv.messages.length} messages
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

      {/* Ideas panel */}
      {ideasOpen && (
        <div style={{
          marginBottom: "0.75rem",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          background: "var(--surface)",
          maxHeight: "280px",
          overflowY: "auto",
        }}>
          {QUESTION_BANK.map(({ category, questions }) => (
            <div key={category}>
              <button
                onClick={() => setOpenCategory(c => c === category ? null : category)}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "0.5rem 0.85rem",
                  background: "transparent",
                  border: "none",
                  borderBottom: "1px solid var(--border)",
                  color: "var(--text)",
                  fontSize: "0.82rem",
                  fontWeight: 600,
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                {category}
                <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.75rem" }}>
                  {openCategory === category ? "▲" : "▼"}
                </span>
              </button>
              {openCategory === category && questions.map((q) => (
                <div
                  key={q}
                  onClick={() => { send(q); setIdeasOpen(false); }}
                  style={{
                    padding: "0.45rem 1.2rem",
                    fontSize: "0.82rem",
                    color: "var(--text-muted)",
                    borderBottom: "1px solid var(--border)",
                    cursor: "pointer",
                    lineHeight: "1.4",
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLDivElement).style.background = "var(--accent)11";
                    (e.currentTarget as HTMLDivElement).style.color = "var(--text)";
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLDivElement).style.background = "transparent";
                    (e.currentTarget as HTMLDivElement).style.color = "var(--text-muted)";
                  }}
                >
                  {q}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Behavioral insight banner */}
      {insightFlag && !insightDismissed && (
        <div style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "0.5rem",
          marginBottom: "0.75rem",
          padding: "0.55rem 0.85rem",
          borderLeft: "3px solid var(--accent)",
          borderRadius: "0 var(--radius) var(--radius) 0",
          background: "var(--surface)",
          color: "var(--text-muted)",
          fontSize: "0.82rem",
          lineHeight: "1.45",
        }}>
          <span><strong style={{ color: "var(--text)", fontWeight: 600 }}>Insight:</strong> {insightFlag}</span>
          <button
            onClick={() => setInsightDismissed(true)}
            title="Dismiss"
            style={{
              background: "none",
              border: "none",
              color: "var(--text-muted)",
              cursor: "pointer",
              fontSize: "0.9rem",
              lineHeight: 1,
              padding: "0 0.2rem",
              flexShrink: 0,
            }}
          >×</button>
        </div>
      )}

      {/* Messages */}
      <div style={{
        flex: 1,
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        padding: "0.5rem 0 1rem",
      }}>
        {messages.length === 0 && (
          <div style={{ color: "var(--text-muted)", textAlign: "center", marginTop: "3rem" }}>
            <p style={{ fontSize: "1.1rem", marginBottom: "1.25rem" }}>Ask anything about your portfolio</p>
            <div style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "0.5rem",
              justifyContent: "center",
              maxWidth: "620px",
              margin: "0 auto",
            }}>
              {suggestedChips.map((chip, idx) => (
                <button
                  key={idx}
                  onClick={() => send(chip)}
                  style={{
                    padding: "0.4rem 0.9rem",
                    borderRadius: "999px",
                    border: "1px solid var(--border)",
                    background: "var(--surface)",
                    color: "var(--text-muted)",
                    fontSize: "0.8rem",
                    cursor: "pointer",
                    transition: "border-color 0.15s, color 0.15s",
                    textAlign: "left",
                    lineHeight: "1.4",
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--accent)";
                    (e.currentTarget as HTMLButtonElement).style.color = "var(--accent)";
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)";
                    (e.currentTarget as HTMLButtonElement).style.color = "var(--text-muted)";
                  }}
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
            <div style={{
              maxWidth: "75%",
              padding: "0.65rem 1rem",
              borderRadius: "12px",
              fontSize: "0.9rem",
              lineHeight: "1.5",
              whiteSpace: m.role === "user" ? "pre-wrap" : undefined,
              background: m.role === "user" ? "var(--accent)" : "var(--surface)",
              color: m.role === "user" ? "#fff" : "var(--text)",
              border: m.role === "assistant" ? `1px solid var(--border)` : "none",
              borderBottomRightRadius: m.role === "user" ? "4px" : "12px",
              borderBottomLeftRadius: m.role === "assistant" ? "4px" : "12px",
            }}>
              {m.role === "assistant"
                ? <div className="md-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
                : m.content}
            </div>
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
            <div style={{
              padding: "0.65rem 1rem",
              borderRadius: "12px",
              borderBottomLeftRadius: "4px",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              color: "var(--text-muted)",
              fontSize: "0.9rem",
            }}>
              {toolStatus || `${activeProvider.label} is thinking...`}
            </div>
          </div>
        )}
        {error && <p className="msg msg-error">{error}</p>}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ display: "flex", gap: "0.5rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border)" }}>
        <textarea
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask about your portfolio..."
          disabled={loading}
          style={{
            flex: 1,
            resize: "none",
            padding: "0.6rem 0.85rem",
            borderRadius: "var(--radius)",
            border: "1px solid var(--border)",
            background: "var(--surface)",
            color: "var(--text)",
            fontSize: "0.9rem",
            fontFamily: "inherit",
            outline: "none",
          }}
        />
        <button
          onClick={() => send()}
          disabled={!input.trim() || loading}
          className="btn-primary"
          style={{ padding: "0.6rem 1.25rem", alignSelf: "flex-end" }}
        >
          Send
        </button>
      </div>
    </div>
  );
}
