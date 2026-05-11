# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

**Docker (recommended):**
```bash
docker compose up --build
# On first run, import trade history:
docker compose exec backend python import_trades.py
```

**After making any code changes, rebuild only the relevant service:**
```bash
# Backend changes only:
docker compose up --build backend -d

# Frontend changes only:
docker compose up --build frontend -d

# Both changed:
docker compose up --build backend frontend -d
```
Claude must run the appropriate rebuild command automatically after every code change without waiting to be asked.

**Local development:**
```bash
# Backend (terminal 1)
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend (terminal 2)
cd frontend
npm install
npm run dev
```

- Backend API: http://localhost:8000/api
- Frontend: http://localhost:3000

## Deployment (Railway)

The app runs on Railway with three services: **backend**, **frontend**, and **PostgreSQL**.

- GitHub repo: https://github.com/guyr22/trading.git — Railway auto-deploys on every push to `main`
- Each service has its own Dockerfile; `backend/railway.toml` and `frontend/railway.toml` configure Railway-specific settings
- Secrets (API keys, DATABASE_URL) are set as environment variables in the Railway dashboard, not in code

**Environment variables required:**

| Service  | Variable | Value |
|----------|----------|-------|
| backend  | `DATABASE_URL` | injected automatically by Railway PostgreSQL add-on |
| backend  | `ANTHROPIC_API_KEY` | from `.env` |
| backend  | `GOOGLE_API_KEY` | from `.env` |
| backend  | `PORT` | set to `8000` to pin it |
| frontend | `BACKEND_URL` | `http://<backend-internal-hostname>.railway.internal:8000` |

**Local → Railway data migration:**
```bash
docker compose exec -e DEST_DATABASE_URL=<railway-postgres-url> backend python migrate_to_railway.py
```

**Railway MCP server** (installed in Claude Code — allows Claude to manage Railway directly):
```bash
claude mcp add railway-mcp-server -- npx -y @railway/mcp-server
```

## Architecture

Full-stack trading portfolio tracker with separate backend and frontend servers.

**Backend** (`backend/`): FastAPI + SQLAlchemy
- `main.py` — App setup, all API routes, live price fetching, and all business logic
- `models.py` — Single `Trade` model (no account/cash tracking); includes `fees` and `platform` fields
- `schemas.py` — Pydantic request/response schemas
- `database.py` — SQLAlchemy engine; reads `DATABASE_URL` env var (defaults to SQLite locally, PostgreSQL in Docker)
- `import_trades.py` — One-time script to seed the DB from Google Sheets trade history

**Frontend** (`frontend/`): Next.js (App Router) + TypeScript
- `app/page.tsx` — Entry point; renders the Dashboard
- `app/components/` — Dashboard, TradeForm, History, Statistics, Chat, QuickTradeModal, NavBar, IndexDashboard
- `app/api.ts` — Typed API client (fetchPortfolio, fetchTrades, fetchStatistics, createTrade, sendChatMessage)
- `app/globals.css` — Dark theme using CSS custom properties
- `next.config.ts` — Proxies `/api` requests to `BACKEND_URL` env var (default: `http://localhost:8000`); baked in at build time so Docker passes it as a build arg

## API Endpoints

- `POST /api/trades` — Record a trade (validates sell qty against holdings)
- `GET /api/trades` — All trades, newest first
- `GET /api/portfolio` — Market value, unrealized P&L, realized P&L, and per-ticker positions
- `GET /api/statistics` — Win rate, profit factor, drawdown, monthly P&L timeseries, cumulative P&L, per-ticker stats
- `POST /api/chat` — Multi-LLM chat; accepts `messages` array and `provider` (`claude`/`openai`/`gemini`/`gemini25`)

## Key Design Decisions

- No cash/account management — the app tracks positions and P&L only
- Live prices fetched via yfinance with 30-second cache; falls back to avg cost on failure
- Positions are computed dynamically from the trades table (no separate positions table)
- Database is SQLite locally / PostgreSQL in Docker; tables auto-created via FastAPI lifespan event; no migrations
- **Index funds** (`VOO`, `SPY`, `QQQ`, `IBIT`, `ETHA`) are tracked but excluded from all statistics, dashboard totals, and chat context — see `INDEX_TICKERS_SET` in `main.py`

### FIFO Logic

All cost basis and P&L calculations use FIFO via two functions in `main.py`:
- `_fifo_from_trades(trades, ticker)` → `(avg_cost, realized_pnl)`: used for live position cost basis
- `_fifo_closed_lots(trades, ticker)` → `list[ClosedLot]`: returns each individual lot closure with `ticker`, `pnl`, `cost_basis`, `open_date`, `close_date`, `quantity` — used for statistics and chat context

Both functions maintain separate long/short lot queues. Fees are deducted proportionally per share when lots are consumed (open leg carries fee-per-share; close leg deducts at consumption).

### Chat / LLM Context

`_build_chat_context(db)` in `main.py` builds the system prompt per request. It includes: portfolio summary (market value, unrealized/realized P&L, total fees), open positions, last 20 trades, and all closed lots sorted by P&L descending with percentage return. This is regenerated on every chat request — no caching.

Supported providers and models: Claude (`claude-haiku-4-5-20251001`), OpenAI (`gpt-4o-mini`), Gemini (`gemini-3-flash-preview`, `gemini-2.5-flash`). API keys are read from environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`).

### Never insert, modify, or leave test/placeholder data in the database. Only the user decides what goes into the DB.
