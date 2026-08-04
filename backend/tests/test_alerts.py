"""Tests for the price-alert background checker — crossing detection and one-shot firing.

Uses an in-memory SQLite DB and mocked price/push services so it is hermetic.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import MagicMock

from database import Base
from models import AlertCondition, PriceAlert
from services.alert_checker import AlertChecker


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _add(db, **kw) -> PriceAlert:
    defaults = dict(user_id=1, ticker="NVDA", condition=AlertCondition.ABOVE,
                    target_price=150.0, active=True, last_price=145.0)
    defaults.update(kw)
    alert = PriceAlert(**defaults)
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def _checker(prices: dict):
    price_svc = MagicMock()
    # The checker reads the shared cache and never fetches — the refresh thread
    # owns all upstream calls. A ticker absent from `prices` models "not priced
    # yet", which must be skipped rather than evaluated.
    price_svc.get_cached_prices.side_effect = lambda tickers: {
        t: prices.get(t) for t in tickers
    }
    push_svc = MagicMock()
    push_svc.send_to_user.return_value = 1
    return AlertChecker(price_svc, push_svc), push_svc


class TestAlertChecker:
    def test_above_crossing_fires_once_and_pauses(self, db):
        alert = _add(db, last_price=145.0, target_price=150.0)
        checker, push = _checker({"NVDA": 151.0})

        assert checker.check_once(db) == 1
        db.refresh(alert)
        assert alert.active is False              # one-shot: auto-paused
        assert alert.triggered_at is not None
        push.send_to_user.assert_called_once()
        # Notification text references the ticker.
        args = push.send_to_user.call_args.args
        assert "NVDA" in args[2]                   # title

    def test_no_cross_just_updates_baseline(self, db):
        alert = _add(db, last_price=145.0, target_price=150.0)
        checker, push = _checker({"NVDA": 148.0})

        assert checker.check_once(db) == 0
        db.refresh(alert)
        assert alert.active is True
        assert alert.last_price == 148.0          # baseline moved up, still below target
        push.send_to_user.assert_not_called()

    def test_already_past_target_does_not_insta_fire(self, db):
        # last_price already above the target — only a fresh crossing should fire.
        alert = _add(db, last_price=160.0, target_price=150.0)
        checker, push = _checker({"NVDA": 165.0})

        assert checker.check_once(db) == 0
        db.refresh(alert)
        assert alert.active is True
        push.send_to_user.assert_not_called()

    def test_below_crossing_fires(self, db):
        alert = _add(db, condition=AlertCondition.BELOW, last_price=105.0, target_price=100.0)
        checker, push = _checker({"NVDA": 99.0})

        assert checker.check_once(db) == 1
        db.refresh(alert)
        assert alert.active is False
        push.send_to_user.assert_called_once()

    def test_first_observation_seeds_without_firing(self, db):
        # A never-priced alert (last_price NULL) should seed, not insta-fire.
        alert = _add(db, last_price=None, target_price=150.0)
        checker, push = _checker({"NVDA": 200.0})

        assert checker.check_once(db) == 0
        db.refresh(alert)
        assert alert.last_price == 200.0
        push.send_to_user.assert_not_called()

    def test_fired_alert_is_not_re_evaluated(self, db):
        _add(db, last_price=145.0, target_price=150.0)
        checker, push = _checker({"NVDA": 151.0})

        assert checker.check_once(db) == 1        # fires, pauses
        assert checker.check_once(db) == 0        # now inactive — excluded
        push.send_to_user.assert_called_once()    # not spammed

    def test_missing_price_is_skipped(self, db):
        alert = _add(db, last_price=145.0)
        checker, push = _checker({})              # price fetch returned nothing

        assert checker.check_once(db) == 0
        db.refresh(alert)
        assert alert.active is True
        assert alert.last_price == 145.0          # untouched
