const API = "/api";

const OPTS: RequestInit = { credentials: "include" };

function json(body: unknown): RequestInit {
  return { ...OPTS, method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export interface AuthUser {
  id: number;
  email: string;
  is_admin: boolean;
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const res = await fetch(`${API}/auth/login`, json({ email, password }));
  if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Login failed"); }
  return res.json();
}

export async function logout(): Promise<void> {
  await fetch(`${API}/auth/logout`, { ...OPTS, method: "POST" });
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  const res = await fetch(`${API}/auth/me`, OPTS);
  if (!res.ok) throw new Error("Not authenticated");
  return res.json();
}

export async function createInvite(): Promise<string> {
  const res = await fetch(`${API}/auth/invite`, { ...OPTS, method: "POST" });
  if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Failed to create invite"); }
  const data = await res.json();
  return data.token;
}

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  leveraged_underlying: string | null;
  leverage_factor: number | null;
}

export interface LeveragedEtf {
  id: number;
  ticker: string;
  underlying: string;
  leverage_factor: number;
  name: string | null;
}

export interface LeveragedEtfPayload {
  ticker: string;
  underlying: string;
  leverage_factor: number;
  name?: string;
}

export interface PortfolioSummary {
  total_market_value: number;
  total_unrealized_pnl: number;
  total_realized_pnl: number;
  positions: Position[];
}

export interface Trade {
  id: number;
  action: "BUY" | "SELL";
  ticker: string;
  quantity: number;
  price: number;
  fees: number;
  platform: string | null;
  executed_at: string;
  created_at: string;
}

export interface TradePayload {
  action: "BUY" | "SELL";
  ticker: string;
  quantity: number;
  price: number;
  fees?: number;
  platform?: string | null;
  executed_at?: string;
}

export interface ClosedLot {
  ticker: string;
  open_date: string;
  close_date: string;
  quantity: number;
  cost_basis: number;
  avg_buy_price: number;
  avg_sell_price: number;
  pnl: number;
  pnl_pct: number;
}

export interface TickerStat {
  ticker: string;
  realized_pnl: number;
  total_fees: number;
  win_rate: number;
  trades_count: number;
}

export interface MonthlyPnl {
  month: string;
  realized_pnl: number;
}

export interface CumulativePoint {
  date: string;
  cumulative_pnl: number;
}

export interface BenchmarkPoint {
  date: string;
  your_pnl: number;
  benchmark_pnl: number;
}

export interface BenchmarkComparison {
  benchmark_ticker: string;
  your_realized_pnl: number;
  benchmark_pnl: number;
  alpha: number;
  lots_total: number;
  lots_beat: number;
  beat_rate: number;
  cumulative: BenchmarkPoint[];
  available: boolean;
}

export interface PortfolioStatistics {
  total_pnl: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
  best_trade: number;
  worst_trade: number;
  max_drawdown: number;
  avg_holding_days: number;
  largest_position_pct: number;
  total_trades: number;
  total_fees: number;
  avg_fees_per_trade: number;
  most_traded_ticker: string;
  ticker_stats: TickerStat[];
  monthly_pnl: MonthlyPnl[];
  cumulative_pnl: CumulativePoint[];
  closed_lots: ClosedLot[];
}

export interface DispositionSummary {
  hold_ratio: number;
  avg_winner_hold_days: number;
  avg_loser_hold_days: number;
  interpretation: string;
}

export interface ChatInsights {
  flags: string[];
  has_insights: boolean;
  disposition_summary: DispositionSummary | null;
}

export async function fetchInsights(): Promise<ChatInsights> {
  const res = await fetch(`${API}/chat/insights`, OPTS);
  if (!res.ok) throw new Error("Failed to fetch insights");
  return res.json();
}

export async function fetchPortfolio(): Promise<PortfolioSummary> {
  const res = await fetch(`${API}/portfolio`, OPTS);
  if (!res.ok) throw new Error("Failed to fetch portfolio");
  return res.json();
}

export async function fetchIndexPortfolio(): Promise<PortfolioSummary> {
  const res = await fetch(`${API}/index-portfolio`, OPTS);
  if (!res.ok) throw new Error("Failed to fetch index portfolio");
  return res.json();
}

export async function fetchTrades(): Promise<Trade[]> {
  const res = await fetch(`${API}/trades`, OPTS);
  if (!res.ok) throw new Error("Failed to fetch trades");
  return res.json();
}

export async function fetchIndexTrades(): Promise<Trade[]> {
  const res = await fetch(`${API}/index-trades`, OPTS);
  if (!res.ok) throw new Error("Failed to fetch index trades");
  return res.json();
}

export async function createIndexTrade(payload: TradePayload): Promise<Trade> {
  const res = await fetch(`${API}/index-trades`, json(payload));
  if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Trade failed"); }
  return res.json();
}

export async function fetchStatistics(): Promise<PortfolioStatistics> {
  const res = await fetch(`${API}/statistics`, OPTS);
  if (!res.ok) throw new Error("Failed to fetch statistics");
  return res.json();
}

export async function fetchBenchmark(ticker: string): Promise<BenchmarkComparison> {
  const res = await fetch(`${API}/benchmark?ticker=${encodeURIComponent(ticker)}`, OPTS);
  if (!res.ok) throw new Error("Failed to fetch benchmark");
  return res.json();
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  provider: string;
  created_at: string;
  updated_at: string;
}

export async function fetchConversations(): Promise<Conversation[]> {
  const res = await fetch(`${API}/chat/conversations`, OPTS);
  if (!res.ok) throw new Error("Failed to fetch conversations");
  return res.json();
}

export async function upsertConversation(id: string, title: string, messages: ChatMessage[], provider: string): Promise<void> {
  await fetch(`${API}/chat/conversations/${id}`, {
    ...OPTS, method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, messages, provider }),
  });
}

export async function deleteConversationApi(id: string): Promise<void> {
  await fetch(`${API}/chat/conversations/${id}`, { ...OPTS, method: "DELETE" });
}

async function _readNdjsonStream(res: Response, onChunk: (text: string) => void): Promise<void> {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try { const e = await res.json(); if (e.detail) detail = e.detail; } catch { /* non-JSON */ }
    throw new Error(detail);
  }
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const msg = JSON.parse(line);
      if (msg.error) throw new Error(msg.error);
      if (msg.done) return;
      if (msg.t) onChunk(msg.t);
    }
  }
}

export async function sendChatMessage(
  messages: ChatMessage[],
  provider: string,
  onChunk: (text: string) => void,
  onToolCall?: (toolName: string) => void,
): Promise<void> {
  const res = await fetch(`${API}/chat`, {
    ...json({ messages, provider }),
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try { const e = await res.json(); if (e.detail) detail = e.detail; } catch { /* non-JSON */ }
    throw new Error(detail);
  }
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const msg = JSON.parse(line);
      if (msg.error) throw new Error(msg.error);
      if (msg.done) return;
      if (msg.tool_call) { onToolCall?.(msg.tool_call); continue; }
      if (msg.t) onChunk(msg.t);
    }
  }
}

// ---- Price alerts & push notifications -------------------------------------

export type AlertCondition = "ABOVE" | "BELOW";

export interface PriceAlert {
  id: number;
  ticker: string;
  condition: AlertCondition;
  target_price: number;
  note: string | null;
  active: boolean;
  current_price: number | null;
  triggered_at: string | null;
  created_at: string;
}

export interface AlertPayload {
  ticker: string;
  condition: AlertCondition;
  target_price: number;
  note?: string | null;
}

export interface VapidKey {
  public_key: string | null;
  enabled: boolean;
}

export interface BrowserSubscriptionJSON {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}

export async function fetchAlerts(): Promise<PriceAlert[]> {
  const res = await fetch(`${API}/alerts`, OPTS);
  if (!res.ok) throw new Error("Failed to fetch alerts");
  return res.json();
}

export async function createAlert(payload: AlertPayload): Promise<PriceAlert> {
  const res = await fetch(`${API}/alerts`, json(payload));
  if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Failed to create alert"); }
  return res.json();
}

export async function updateAlert(id: number, active: boolean): Promise<PriceAlert> {
  const res = await fetch(`${API}/alerts/${id}`, {
    ...OPTS, method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ active }),
  });
  if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Failed to update alert"); }
  return res.json();
}

export async function deleteAlert(id: number): Promise<void> {
  const res = await fetch(`${API}/alerts/${id}`, { ...OPTS, method: "DELETE" });
  if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Failed to delete alert"); }
}

export async function fetchVapidKey(): Promise<VapidKey> {
  const res = await fetch(`${API}/push/vapid-public-key`, OPTS);
  if (!res.ok) throw new Error("Failed to fetch push config");
  return res.json();
}

export async function subscribePush(sub: BrowserSubscriptionJSON): Promise<void> {
  const res = await fetch(`${API}/push/subscribe`, json(sub));
  if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Failed to subscribe"); }
}

export async function unsubscribePush(endpoint: string): Promise<void> {
  await fetch(`${API}/push/unsubscribe`, json({ endpoint }));
}

export async function sendTestPush(): Promise<{ sent: number }> {
  const res = await fetch(`${API}/push/test`, { ...OPTS, method: "POST" });
  if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Failed to send test"); }
  return res.json();
}

export interface DigestPreference {
  enabled: boolean;
  email_configured: boolean;
}

export async function fetchDigestPreference(): Promise<DigestPreference> {
  const res = await fetch(`${API}/digest/preference`, OPTS);
  if (!res.ok) throw new Error("Failed to fetch digest preference");
  return res.json();
}

export async function updateDigestPreference(enabled: boolean): Promise<DigestPreference> {
  const res = await fetch(`${API}/digest/preference`, {
    ...OPTS, method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled }),
  });
  if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Failed to update preference"); }
  return res.json();
}

export async function sendDigestTest(): Promise<{ sent: boolean }> {
  const res = await fetch(`${API}/digest/test`, { ...OPTS, method: "POST" });
  if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Failed to send digest"); }
  return res.json();
}

export async function fetchLeveragedEtfs(): Promise<LeveragedEtf[]> {
  const res = await fetch(`${API}/leveraged-etfs`, OPTS);
  if (!res.ok) throw new Error("Failed to fetch leveraged ETFs");
  return res.json();
}

export async function createLeveragedEtf(payload: LeveragedEtfPayload): Promise<LeveragedEtf> {
  const res = await fetch(`${API}/leveraged-etfs`, json(payload));
  if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Failed to add ETF"); }
  return res.json();
}

export async function deleteLeveragedEtf(ticker: string): Promise<void> {
  const res = await fetch(`${API}/leveraged-etfs/${ticker}`, { ...OPTS, method: "DELETE" });
  if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Failed to delete ETF"); }
}

export async function deleteTrade(id: number): Promise<void> {
  const res = await fetch(`${API}/trades/${id}`, { ...OPTS, method: "DELETE" });
  if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Failed to delete trade"); }
}

export async function updateTrade(id: number, payload: Partial<TradePayload>): Promise<Trade> {
  const res = await fetch(`${API}/trades/${id}`, {
    ...OPTS, method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Failed to update trade"); }
  return res.json();
}

export async function createTrade(payload: TradePayload): Promise<Trade> {
  const res = await fetch(`${API}/trades`, json(payload));
  if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Trade failed"); }
  return res.json();
}
