# Feature Ideas

Suggested feature backlog for the trading portfolio tracker, each graded 1–10 on
benefit to the app. Grades weigh user value against how much it leverages
infrastructure that already exists.

**Status legend:** ✅ Shipped · 🔭 Proposed

| # | Feature | Grade | Status |
|---|---------|:-----:|--------|
| 1 | Price alerts + push notifications | 9 | ✅ Shipped |
| 2 | Benchmark — "did I beat the index?" | 9 | ✅ Shipped |
| 3 | Tax / realized-gains report (with export) | 8 | 🔭 Proposed |
| 4 | Trade journaling — rationale, tags, screenshots | 8 | 🔭 Proposed |
| 5 | Dividend tracking | 7 | 🔭 Proposed |
| 6 | Broker CSV import | 7 | 🔭 Proposed |
| 7 | Stop-loss / target price tracking | 7 | 🔭 Proposed |
| 8 | Per-position weekly digest email | 6 | 🗑️ Removed |
| 9 | Watchlist for not-yet-owned tickers | 5 | 🔭 Proposed |
| 10 | Multi-currency / FX support | 4 | 🔭 Proposed |

---

## High value (8–10)

### 1. Price alerts + push notifications — 9/10 ✅
Let users set "notify me if NVDA crosses $X" or "position down 10%." Turns the app
from a passive ledger into something that pulls users back daily — the single
biggest engagement lever, and most of the plumbing (PWA service worker + price
polling) already exists.

> **Shipped this session.** Alerts tab with price-above/price-below targets, a
> background checker that fires on a genuine *crossing* (one-shot, re-armable),
> and Web Push via VAPID. Needs `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` /
> `VAPID_SUBJECT` on the Railway backend.

### 2. Benchmark — "did I beat the index?" — 9/10 ✅
Overlay cumulative realized P&L against a buy-and-hold of the same capital in
SPY/QQQ. Answers the question every trader actually cares about: *would I have
done better just buying the index?* High insight-per-effort since cumulative P&L
and index prices are already available.

> **Shipped this session.** "vs S&P 500/Nasdaq-100" cards (Your P&L / Index
> equivalent / Alpha / Beat rate) plus a benchmark overlay line on the Cumulative
> P&L chart, with an SPY/QQQ selector. Benchmarks closed lots over each lot's
> exact holding window.

### 3. Tax / realized-gains report (with export) — 8/10 🔭
The FIFO closed-lot data is a Schedule-D / capital-gains report waiting to happen.
Add short-vs-long-term classification (>365-day hold), yearly grouping, and
CSV/PDF export. Real-world utility at tax time; almost no new data model needed.

### 4. Trade journaling — rationale, tags, screenshots — 8/10 🔭
Add a notes/tags/conviction field per trade ("breakout," "earnings play," "FOMO").
Then the existing behavioral analytics can segment win-rate *by strategy tag* —
e.g. "your FOMO trades lose 70% of the time." Compounds the value of the analytics
engine already built.

## Solid (6–7)

### 5. Dividend tracking — 7/10 🔭
No dividend support today. For anyone holding ETFs/dividend stocks, total return is
materially understated without it. yfinance exposes dividend history, so it can be
semi-automated.

### 6. Broker CSV import — 7/10 🔭
There's a one-time Google Sheets importer but no self-serve broker-statement
import. A "drop your IBKR/Schwab CSV here" flow with column mapping removes the
biggest onboarding friction (manual trade entry).

### 7. Stop-loss / target price tracking — 7/10 🔭
Let users attach a planned stop and target to open positions, then have analytics
measure discipline: "you blew through your stop on 8 of 12 losers." Pairs naturally
with the disposition-effect analysis and with price alerts (#1).

### 8. Per-position weekly digest email — 6/10 🗑️
A scheduled weekly summary (portfolio value, per-position 1-week move, biggest
mover, closed trades, realized P&L, behavioral red flags). Re-engagement with
near-zero new analytics — it packages numbers already computed.

> **Removed.** Shipped earlier as an opt-in weekly email (Resend/SMTP transport,
> scheduler thread, `users.digest_opt_in` column, Alerts-tab UI) but later
> removed entirely — backend services/router, email transport, config, schema
> column, and frontend controls all deleted.

## Lower priority (4–5)

### 9. Watchlist for not-yet-owned tickers — 5/10 🔭
Useful but adds a new entity and overlaps conceptually with alerts; lower marginal
value given the app's P&L-tracking focus.

### 10. Multi-currency / FX support — 4/10 🔭
Only worth it if non-USD instruments are actually traded. Otherwise it's complexity
without payoff — skip unless there's a concrete need.

---

## Suggested next build order

Of what remains, the highest value-to-effort picks are **#3 Tax/realized-gains
report** (rides on existing FIFO closed-lot data) and **#6 Broker CSV import**
(removes onboarding friction). **#7 Stop-loss/target tracking** pairs well with the
price-alerts work already shipped.
