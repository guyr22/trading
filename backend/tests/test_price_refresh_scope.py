"""Tests for which tickers the background refresh thread decides to price.

This is the rule that keeps upstream traffic proportional to actual use: alert
tickers are always priced (an alert must fire with nobody watching), holdings
are priced only for users who have recently made a request, and a fully idle
deployment issues no calls at all.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.activity import ActivityTracker
from core.config import ACTIVITY_WINDOW
from database import Base
from models import AlertCondition, PriceAlert, Trade, TradeAction
from services.price_service import PriceService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def fresh_tracker(monkeypatch):
    """Swap in a clean tracker so tests can't see each other's activity."""
    tracker = ActivityTracker()
    monkeypatch.setattr("core.activity.activity_tracker", tracker)
    return tracker


def _trade(db, user_id: int, ticker: str, qty: float, action=TradeAction.BUY) -> None:
    db.add(Trade(user_id=user_id, ticker=ticker, quantity=qty, price=10.0, action=action))
    db.commit()


def _alert(db, user_id: int, ticker: str, active: bool = True) -> None:
    db.add(PriceAlert(user_id=user_id, ticker=ticker, condition=AlertCondition.ABOVE,
                      target_price=100.0, active=active, last_price=90.0))
    db.commit()


class TestActivityScoping:
    def test_idle_deployment_refreshes_nothing(self, db):
        _trade(db, 1, "AAA", 10)
        assert PriceService.tickers_to_refresh(db) == []

    def test_online_user_gets_their_holdings(self, db, fresh_tracker):
        _trade(db, 1, "AAA", 10)
        fresh_tracker.touch(1)
        assert PriceService.tickers_to_refresh(db) == ["AAA"]

    def test_offline_users_holdings_are_excluded(self, db, fresh_tracker):
        _trade(db, 1, "AAA", 10)
        _trade(db, 2, "BBB", 5)
        fresh_tracker.touch(1)
        assert PriceService.tickers_to_refresh(db) == ["AAA"]

    def test_activity_expires(self, db, fresh_tracker):
        _trade(db, 1, "AAA", 10)
        fresh_tracker.touch(1)
        fresh_tracker._last_seen[1] -= ACTIVITY_WINDOW + 1
        assert PriceService.tickers_to_refresh(db) == []

    def test_fully_closed_position_is_not_refreshed(self, db, fresh_tracker):
        _trade(db, 1, "AAA", 10)
        _trade(db, 1, "AAA", 10, action=TradeAction.SELL)
        fresh_tracker.touch(1)
        assert PriceService.tickers_to_refresh(db) == []

    def test_partially_sold_position_is_still_refreshed(self, db, fresh_tracker):
        _trade(db, 1, "AAA", 10)
        _trade(db, 1, "AAA", 4, action=TradeAction.SELL)
        fresh_tracker.touch(1)
        assert PriceService.tickers_to_refresh(db) == ["AAA"]

    def test_one_users_position_is_not_cancelled_by_anothers(self, db, fresh_tracker):
        # Both online and both hold AAA, but user 2's net is negative. Summing
        # across users would zero the ticker out and silently stop pricing it.
        _trade(db, 1, "AAA", 10)
        _trade(db, 2, "AAA", 30, action=TradeAction.SELL)
        fresh_tracker.touch(1)
        fresh_tracker.touch(2)
        assert PriceService.tickers_to_refresh(db) == ["AAA"]


class TestAlertScoping:
    def test_active_alerts_are_refreshed_with_nobody_online(self, db):
        _alert(db, 1, "ZZZ")
        assert PriceService.tickers_to_refresh(db) == ["ZZZ"]

    def test_inactive_alerts_are_ignored(self, db):
        _alert(db, 1, "ZZZ", active=False)
        assert PriceService.tickers_to_refresh(db) == []

    def test_alert_and_holding_sets_are_merged_without_duplicates(self, db, fresh_tracker):
        _trade(db, 1, "AAA", 10)
        _alert(db, 1, "AAA")
        _alert(db, 1, "ZZZ")
        fresh_tracker.touch(1)
        assert PriceService.tickers_to_refresh(db) == ["AAA", "ZZZ"]
