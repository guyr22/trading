# Edit & Delete Transactions — Quick Plan

## Problem

The History page's Transactions tab is read-only. Users need to fix data entry mistakes (wrong price, qty, date) and remove erroneous records. The backend has no `PUT` or `DELETE` route for individual trades, and the frontend has no UI for either operation.

**Touches:** `backend/routers/trades.py`, `backend/repositories/trade_repository.py`, `backend/schemas.py`, `frontend/app/api.ts`, `frontend/app/components/History.tsx`

**Constraints:** A trade is locked (cannot be edited or deleted) if a later trade of the opposite action exists for the same ticker. Example: a BUY is locked if a SELL for the same ticker was recorded after it; a SELL is locked if a BUY for the same ticker was recorded after it. "Later" means `executed_at` is greater, or same date with a higher `id`. This is enforced on both backend (400 error) and frontend (buttons disabled/hidden).

**Assumptions:** Edit opens an inline modal reusing the existing `TradeCreate` schema shape. Delete requires a confirmation prompt. Index-ticker trades are also editable/deletable since they live in the same DB table.

## Approach

Add `PUT /api/trades/{id}` and `DELETE /api/trades/{id}` to the backend router, backed by `get_by_id`, `update`, `delete`, and `has_later_opposite_trade` methods on `TradeRepository`. Before any edit or delete, the backend checks whether a later trade of the opposite action exists for the same ticker and returns HTTP 409 if so. The `GET /api/trades` response already includes enough data for the frontend to compute this client-side: for each trade, if any later trade (higher `executed_at` or same date + higher `id`) with the opposite action exists for the same ticker, its Edit and Delete buttons are rendered as disabled. After a successful edit or delete the trade list is refreshed.

## Touchpoints

| File | Change |
|---|---|
| `backend/repositories/trade_repository.py` | Add `get_by_id`, `update`, `delete`, `has_later_opposite_trade` methods |
| `backend/schemas.py` | Add `TradeUpdate` schema (same fields as `TradeCreate`, all optional) |
| `backend/routers/trades.py` | Add `PUT /api/trades/{id}` and `DELETE /api/trades/{id}`; enforce locked-trade check (HTTP 409) |
| `frontend/app/api.ts` | Add `updateTrade(id, payload)` and `deleteTrade(id)` functions |
| `frontend/app/components/History.tsx` | Edit/Delete buttons per row; disable buttons for locked trades computed from the full trade list |

## Milestones

| # | Milestone | Definition of done |
|---|---|---|
| 1 | Backend endpoints | `PUT` and `DELETE` return correct status codes; locked-trade check returns HTTP 409; sell qty validation works on edit |
| 2 | Frontend delete | Delete button (disabled for locked trades) with confirm dialog removes the row and refreshes the list |
| 3 | Frontend edit | Edit button (disabled for locked trades) opens modal pre-filled with trade data; save updates the row |

## Risks

1. **Locked-trade detection must be symmetric** — The `has_later_opposite_trade` check applies to both BUY and SELL directions. A SELL is also locked if a BUY for the same ticker came after it (short-covering scenario). Use a single query comparing `(executed_at, id)` tuples.
2. No other significant risks.

---

## Execution Summary — 2026-04-22

Branch: `plan/edit-delete-transactions`
Milestones completed: 3 of 3
Final verdict: READY_TO_MERGE (after post-validation fix)
Unresolved risks:
- `loadTrades()` after edit/delete does not re-fetch `closedLots`; the Closed Trades tab shows stale data until page refresh. Low severity, UX only.
- Platform dropdown hardcoded to "Interactive Brokers"/"IBI"; trades with other platform values will show "" in the edit modal on open. Low severity, accepted.
Next steps: Review branch `plan/edit-delete-transactions`, merge to main, rebuild both services (`docker compose up --build backend frontend -d`).

See `docs/plans/edit-delete-transactions.execution.md` for milestone-by-milestone detail.
