# Context Report: history-table-filters

## CONVENTIONS
- Language: TypeScript (strict mode, `noEmit`)
- Framework: Next.js 16 App Router + React 19, FastAPI backend
- Lint/Format: No ESLint or Prettier configured; no pre-commit hooks
- Tests: pytest (backend only, 77 tests passing); no frontend test framework

## FILES TO TOUCH
- Milestone 1 (Transactions filters): `frontend/app/components/History.tsx`
- Milestone 2 (Closed Trades filters): `frontend/app/components/History.tsx`

## EXISTING PATTERNS
1. All state is colocated in a single component file — `History.tsx` is self-contained with no sub-components.
2. Filtering the index tickers is done via a module-level `Set` constant (`INDEX_TICKERS`) and a `const filtered = trades.filter(...)` expression before the JSX return.
3. Inline `style={}` objects are used for all layout and sizing — no CSS modules or Tailwind; only utility classes from `globals.css` (`.tag`, `.tag-buy`, `.tag-sell`, `.form-row`, `.btn-primary`, etc.).
4. `useMemo` is not currently used in `History.tsx`; state is managed with `useState` only.
5. Platform options in the edit modal are hardcoded (`Interactive Brokers`, `IBI`) — not derived from data.
6. Date values are stored as ISO strings (`executed_at`, `open_date`, `close_date`) and rendered by string manipulation (`.split("-").reverse().join("-")`), not `Date` objects.
7. `fetchStatistics()` is called once on mount; `closedLots` comes from `s.closed_lots` — no separate endpoint.
8. `ClosedLot` type (in `api.ts`) has `close_date` (string) and `pnl` (number) — both directly usable for filter comparisons without transformation.

## CONFLICTS
1. **Platform dropdown options**: The plan says derive platform options dynamically from loaded trades via `useMemo`. The codebase hardcodes `["Interactive Brokers", "IBI"]` in the edit modal select. The plan is correct — dynamic derivation avoids stale/missing values. The hardcoded list in the edit modal is a separate concern and does not need to change.
2. No other conflicts. The plan's single-file constraint, client-side-only approach, and `useMemo` derivation strategy are all consistent with existing patterns.

## SETUP STATUS

**TypeScript (`next build` TypeScript pass):** PASS — `Finished TypeScript in 5.1s`, no errors.

**Build:** PASS — `Compiled successfully`, all 9 static routes generated cleanly.

**Backend tests (`pytest tests/ -q`):** PASS — 77 passed in 9.29s. One deprecation warning (`asyncio_default_fixture_loop_scope` unset in pytest-asyncio) but no failures.

**Frontend tests:** N/A — no test framework is configured.

**Lint:** N/A — no ESLint or Prettier configured; `package.json` has no lint script.

**Baseline known failures:** The plan declares none; current run confirms zero failures.
