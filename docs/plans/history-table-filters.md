# History Table Filters — Quick Plan

## Problem
Add per-table filter controls to `History.tsx`. The Transactions table has ticker, action, date range, and platform as natural filter axes. The Closed Trades table has ticker, win/loss, and date range. No backend changes needed — all data is already loaded in state.

## Approach
Add a filter bar beneath the view toggle for each table. Each bar renders as a row of compact inputs (ticker text, dropdowns, date pickers) stored in two separate filter-state objects — one per view. Filtering is a pure `useMemo` derivation over the already-loaded `filtered`/`closedLots` arrays, so no fetching or debouncing is needed. A "Clear" button resets both filter states to their defaults. No new components — everything stays in `History.tsx`.

## Touchpoints
- `frontend/app/components/History.tsx` — add two filter state objects, a filter bar for each view, and two `useMemo` calls replacing the direct array references in the table renders

## Milestones

| # | Milestone | Definition of done |
|---|-----------|-------------------|
| 1 | Transactions filters | Ticker text, Action (All/BUY/SELL), Platform dropdown (dynamic), Date from/to — all filter the transactions table live |
| 2 | Closed Trades filters | Ticker text, Result (All/Win/Loss), Close date from/to — all filter the closed trades table live |

## Risks
1. **Platform dropdown options depend on loaded data** — derive them with `useMemo` from `trades` to avoid stale values on first render.
2. **Date string comparison** — date inputs are `type="date"` strings; compare as strings (ISO format sorts correctly) to avoid timezone issues.

## Constraints
None.

## Assumptions
- Filters are client-side only (no new API calls)
- Date filter on Transactions uses `executed_at`; on Closed Trades uses `close_date`
- Platform options derived dynamically from loaded trades (no hardcoding)

## Execution Summary — 2026-04-28

- Branch: plan/history-table-filters
- Milestones completed: 2 of 2
- Waves executed: 2 (linear, one milestone each)
- Final verdict: READY_TO_MERGE
- Unresolved risks: Minor UX edge case (index-ticker platforms in dropdown); negligible perf note on non-memoized `filtered`; both low severity
- Next steps: Review branch and merge to main; rebuild frontend Docker image after merge

See docs/plans/history-table-filters.execution.md for milestone-by-milestone detail.
See docs/plans/history-table-filters.context.md for the codebase context used during execution.
