"""Protect chronological holdings when a historical split or trade changes."""
from domain.finance import accounting_events
from models import StockSplit, TradeAction


def sell_shortages(trades, splits, ticker):
    balances = {}
    shortages = {}
    for event in accounting_events(trades, splits, ticker):
        if isinstance(event, StockSplit):
            ratio = event.new_shares / event.old_shares
            balances = {platform: qty * ratio for platform, qty in balances.items()}
            continue
        platform = event.platform
        qty = balances.get(platform, 0.0)
        qty += event.quantity if event.action == TradeAction.BUY else -event.quantity
        balances[platform] = qty
        if event.action == TradeAction.SELL:
            shortages[event.id] = max(-qty, 0.0)
    return shortages


def introduces_oversell(before_trades, before_splits, after_trades, after_splits, ticker):
    """Allow legacy short history, but never introduce/increase a sell shortage."""
    before = sell_shortages(before_trades, before_splits, ticker)
    after = sell_shortages(after_trades, after_splits, ticker)
    return any(qty > before.get(trade_id, 0.0) + 1e-9 for trade_id, qty in after.items())
