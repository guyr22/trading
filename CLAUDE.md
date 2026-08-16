# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

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
| backend  | `PORT` | set to `8000` to pin it |
| backend  | `ADMIN_EMAIL` | your email — creates the first admin user on startup |
| backend  | `ADMIN_PASSWORD` | your password for the admin account |
| backend  | `JWT_SECRET_KEY` | random secret for signing JWTs (`openssl rand -hex 32`) |
| backend  | `SECURE_COOKIES` | `true` in production (Railway uses HTTPS) |
| backend  | `FRONTEND_URL` | your Railway frontend public URL |
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
- `app/components/` — Dashboard, TradeForm, History, Statistics, QuickTradeModal, NavBar, IndexDashboard
- `app/api.ts` — Typed API client (fetchPortfolio, fetchTrades, fetchStatistics, createTrade)
- `app/globals.css` — Dark theme using CSS custom properties
- `next.config.ts` — Proxies `/api` requests to `BACKEND_URL` env var (default: `http://localhost:8000`); baked in at build time so Docker passes it as a build arg

## API Endpoints

- `POST /api/trades` — Record a trade (validates sell qty against holdings)
- `GET /api/trades` — All trades, newest first
- `GET /api/portfolio` — Market value, unrealized P&L, realized P&L, and per-ticker positions
- `GET /api/statistics` — Win rate, profit factor, drawdown, monthly P&L timeseries, cumulative P&L, per-ticker stats

## Key Design Decisions

- No cash/account management — the app tracks positions and P&L only
- Live prices fetched via yfinance by a single background thread — see **Price fetching** below
- Positions are computed dynamically from the trades table (no separate positions table)
- Database is SQLite locally / PostgreSQL in Docker; schema managed by **Alembic** — migrations run automatically on startup via `alembic upgrade head`
- **Index funds** (`VOO`, `SPY`, `QQQ`, `IBIT`, `ETHA`) are tracked but excluded from all statistics and dashboard totals — see `INDEX_TICKERS_SET` in `core/config.py`

### Price fetching

Yahoo rate-limits per IP, and Railway's egress IP is shared, so the budget is
tight. Everything below exists to keep upstream request volume proportional to
actual use. The rules:

- **One fetcher.** Only `PriceService._refresh_loop` calls Yahoo for quotes.
  Request handlers use `get_cached_prices()`, which never touches the network —
  otherwise N open browser tabs become N concurrent fetch storms.
- **`CACHE_TTL` is the request rate; `PRICE_LOOP_TICK` is the responsiveness.**
  The thread wakes every 15s but only fetches tickers whose price has aged past
  90s. A newly-online user's holdings get priced within a tick. Tune `CACHE_TTL`
  to trade freshness against upstream volume — it scales the request count
  linearly, and market-hours gating already removes ~80% of the old traffic.
- **What gets fetched** (`PriceService.tickers_to_refresh`): active alert
  tickers always, plus open positions of users seen in the last `ACTIVITY_WINDOW`.
  An idle deployment makes zero upstream calls.
- **Index funds are scoped to their own page.** They're excluded from the
  dashboard, so nothing else asks for their prices. `GET /api/index-portfolio`
  records `SCOPE_INDEXES` activity (`core/activity.py`) and the refresh thread
  prices `index_trades` holdings only while that scope is warm. The Indexes page
  must therefore keep polling — a single fetch would only ever render the cold
  response. Same applies to any future page with its own ticker set.
- **Market hours only** (`core/market_hours.py`), with a one-shot warm pass
  while closed: any refresh-set ticker not priced since the last session close
  (`last_session_close`) gets a single fetch, so an out-of-hours deploy or a
  user opening the site in the evening sees the closing price instead of a
  stale one. One attempt per ticker per closed period, tracked in
  `_warmed_while_closed` so a failure can't loop.
- **Rate-limit handling.** A failed ticker is negative-cached for
  `NEGATIVE_CACHE_TTL`; a rate-limit response opens a service-wide cooldown
  (`BREAKER_BASE_COOLDOWN`, doubling to `BREAKER_MAX_COOLDOWN`). Cached prices
  are served throughout. Never remove the negative cache — without it a failure
  leaves no cache entry, every caller counts a miss and refetches immediately,
  and one 429 becomes permanent.

Note that `yf.Tickers()` is **not** a batch request — it issues one HTTP call
per ticker. Don't assume adding tickers to a "batch" is free.

### FIFO Logic

All cost basis and P&L calculations use FIFO via two functions in `main.py`:
- `_fifo_from_trades(trades, ticker)` → `(avg_cost, realized_pnl)`: used for live position cost basis
- `_fifo_closed_lots(trades, ticker)` → `list[ClosedLot]`: returns each individual lot closure with `ticker`, `pnl`, `cost_basis`, `open_date`, `close_date`, `quantity` — used for statistics

Both functions maintain separate long/short lot queues. Fees are deducted proportionally per share when lots are consumed (open leg carries fee-per-share; close leg deducts at consumption).

### Schema Changes (Alembic)

**Never use `create_all` or manual `ALTER TABLE` to change the schema.** All schema changes must go through Alembic:

1. Edit `backend/models.py` with the desired change
2. Generate a migration from the `backend/` directory:
   ```bash
   python -m alembic revision --autogenerate -m "describe the change"
   ```
3. Review the generated file in `backend/alembic/versions/` — confirm the `upgrade()` and `downgrade()` functions are correct
4. Commit the migration file alongside the model change

Migrations run automatically on every deploy (`alembic upgrade head` in the FastAPI lifespan). To apply locally without restarting the server:
```bash
cd backend
python -m alembic upgrade head
```

### Never insert, modify, or leave test/placeholder data in the database. Only the user decides what goes into the DB.

### Always commit and push changes with a detailed commit message after completing a task. The message should explain *what* changed and *why* (motivation, context, side effects), not just a one-line summary. Push to `origin/main` so Railway picks up the deploy.
