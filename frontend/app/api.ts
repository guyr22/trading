const API = "/api";

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
  const res = await fetch(`${API}/chat/insights`);
  if (!res.ok) throw new Error("Failed to fetch insights");
  return res.json();
}

export async function fetchPortfolio(): Promise<PortfolioSummary> {
  const res = await fetch(`${API}/portfolio`);
  if (!res.ok) throw new Error("Failed to fetch portfolio");
  return res.json();
}

export async function fetchTrades(): Promise<Trade[]> {
  const res = await fetch(`${API}/trades`);
  if (!res.ok) throw new Error("Failed to fetch trades");
  return res.json();
}

export async function fetchStatistics(): Promise<PortfolioStatistics> {
  const res = await fetch(`${API}/statistics`);
  if (!res.ok) throw new Error("Failed to fetch statistics");
  return res.json();
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
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
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, provider }),
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

export async function fetchTaPrompt(): Promise<string> {
  const res = await fetch(`${API}/config/ta-prompt`);
  if (!res.ok) throw new Error("Failed to fetch TA prompt");
  const data = await res.json();
  return data.value;
}

export async function saveTaPrompt(value: string): Promise<void> {
  const res = await fetch(`${API}/config/ta-prompt`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  if (!res.ok) throw new Error("Failed to save TA prompt");
}

export async function sendTechnicalChatMessage(
  messages: ChatMessage[],
  provider: string,
  onChunk: (text: string) => void,
  images?: string[],
): Promise<void> {
  const res = await fetch(`${API}/chat/technical`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, provider, images: images ?? [] }),
  });
  await _readNdjsonStream(res, onChunk);
}

export async function fetchLeveragedEtfs(): Promise<LeveragedEtf[]> {
  const res = await fetch(`${API}/leveraged-etfs`);
  if (!res.ok) throw new Error("Failed to fetch leveraged ETFs");
  return res.json();
}

export async function createLeveragedEtf(payload: LeveragedEtfPayload): Promise<LeveragedEtf> {
  const res = await fetch(`${API}/leveraged-etfs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to add ETF");
  }
  return res.json();
}

export async function deleteLeveragedEtf(ticker: string): Promise<void> {
  const res = await fetch(`${API}/leveraged-etfs/${ticker}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to delete ETF");
  }
}

export async function deleteTrade(id: number): Promise<void> {
  const res = await fetch(`${API}/trades/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to delete trade");
  }
}

export async function updateTrade(id: number, payload: Partial<TradePayload>): Promise<Trade> {
  const res = await fetch(`${API}/trades/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to update trade");
  }
  return res.json();
}

export async function createTrade(payload: TradePayload): Promise<Trade> {
  const res = await fetch(`${API}/trades`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Trade failed");
  }
  return res.json();
}
