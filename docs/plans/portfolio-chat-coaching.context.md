# Context Report: portfolio-chat-coaching

## CONVENTIONS
- Language: Python 3.13 (backend), TypeScript 5 (frontend)
- Framework: FastAPI + SQLAlchemy (backend); Next.js 15 App Router (frontend)
- Lint/format: ruff (backend, no config file found — defaults); no lint script configured in frontend package.json
- Typecheck: tsc --noEmit (frontend); mypy not installed
- Tests: pytest (backend, zero tests currently); none (frontend)

## FILES TO TOUCH

**M1 — Coaching persona + behavioral brief in system prompt**
- `backend/services/chat_context_service.py` — add `COACHING_PERSONA` constant, `_build_behavioral_brief()`, inject into `_build_context()`
- `backend/services/analytics_service.py` — add `get_behavioral_red_flags()`, `get_disposition_effect()`, `get_revenge_trading_indicators()`

**M2 — Guided empty state + suggested question chips**
- `frontend/app/components/Chat.tsx` — add empty-state chip UI, wire chip click to `send()`
- `frontend/app/api.ts` — optionally add `fetchInsights()` if chips are dynamic

**M3 — New coaching tools registered**
- `backend/services/analytics_service.py` — implement `get_disposition_effect()`, `get_revenge_trading_indicators()`, `get_coaching_summary()`
- `backend/chat/tool_registry.py` — add 3 new `_TOOL_DEFS` entries
- `backend/chat/tool_executor.py` — add 3 entries to `_dispatch`

**M4 — GET /api/chat/insights endpoint + alert banner**
- `backend/routers/chat.py` — add `GET /api/chat/insights` route
- `backend/dependencies.py` — wire `AnalyticsService` dep if not already on that route
- `frontend/app/components/Chat.tsx` — add dismissible alert banner
- `frontend/app/api.ts` — add `fetchChatInsights()`

**M5 — Suggested follow-up questions after tool responses**
- `backend/services/chat_context_service.py` — system prompt instruction to append follow-up questions after tool use
- No structural changes; purely a prompt engineering change

## EXISTING PATTERNS

1. **Registry pattern for tools**: `_TOOL_DEFS` list in `chat/tool_registry.py` + `_dispatch` dict in `chat/tool_executor.py`; adding a tool means one entry in each, nothing else.
2. **Dependency injection via FastAPI Depends**: all services wired in `dependencies.py`; new endpoints must add a `Depends(get_analytics_service)` parameter, not instantiate directly.
3. **Cache keyed on `(trade_count, max_id)`**: `_context_cache` in `chat_context_service.py`; behavioral flags must be computed inside `_build_context()` to be covered by this cache automatically.
4. **`INDEX_TICKERS_SET` exclusion**: all analytics and context queries use `trade_repo.get_excluding(INDEX_TICKERS_SET)`; new behavioral methods must do the same.
5. **FIFO via `fifo_closed_lots` / `fifo_full`** in `domain/finance.py`: all P&L and lot calculations must use these, not custom loops.
6. **Streaming NDJSON responses**: `POST /api/chat` returns `StreamingResponse(media_type="application/x-ndjson")`; the new `GET /api/chat/insights` is a plain JSON endpoint — no streaming needed.
7. **Service layer, not routes**: business logic lives in `services/`; routers are thin (delegate immediately to service/executor).
8. **`ChatContextService` has no `AnalyticsService` dependency**: it only holds `TradeRepository` + `PortfolioService`; M1 requires injecting or calling `AnalyticsService` methods, which means either adding it as a constructor arg or duplicating the FIFO pass — the plan's `ChatContextService` calling `AnalyticsService` is the correct approach.

## CONFLICTS

1. **Plan names the new endpoint `GET /api/chat/insights`; existing router prefix**: `routers/chat.py` has no router-level prefix — all routes are manually prefixed with `/api/`. The new route must follow the same manual prefix pattern (`@router.get("/api/chat/insights")`), not rely on an `APIRouter(prefix=...)`.

2. **Plan says `ChatContextService` calls `AnalyticsService.get_behavioral_red_flags()`; current wiring**: `get_chat_context_service` in `dependencies.py` injects only `db` + `PortfolioService`. Adding `AnalyticsService` as a constructor arg requires updating `ChatContextService.__init__` and `get_chat_context_service` in `dependencies.py`. The plan is correct; the wiring just needs updating.

3. **Plan references a `TradeRepository` pattern**: the plan's architecture diagram shows a `TradeRepository` node, which already exists at `repositories/trade_repository.py` — no conflict, just confirmation that the named class is already present.

None beyond the above (no schema conflicts; no DB changes required; all data exists in current `trades` table).

## SETUP STATUS

**Frontend typecheck (`tsc --noEmit`):** PASS — exits 0, no output.

**Frontend lint:** NO SCRIPT — `npm run lint` fails with "Missing script: lint". No ESLint config found; Next.js lint not configured.

**Backend lint (`ruff check .`):** FAIL — 34 errors. Breakdown:
- `E741` ambiguous variable name `l` (loop variable for `ClosedLot`): 29 occurrences across `analytics_service.py`, `chat_context_service.py`, `statistics_service.py`
- `E702` multiple statements on one line (semicolons): 4 in `analytics_service.py:143,145`
- `F401` unused imports: 3 (`sqlalchemy.and_` in `import_indexes.py`; `get_etf_repo`/`EtfRepository` in `routers/trades.py`)
- 3 are auto-fixable with `--fix`

**Backend typecheck (mypy):** NOT INSTALLED — `No module named mypy`.

**Backend tests (pytest):** PASS structurally — pytest runs but **0 tests collected** (no test files exist).

Plan declares no `baseline_known_failures`. All 34 ruff errors are pre-existing; none are introduced by this plan. The `E741` violations in `analytics_service.py` are directly in the file M1/M3 will modify — implementation should avoid extending this pattern.
