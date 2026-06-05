"""Tests for the weekly digest — scheduler timing/idempotency and the email builder.

Hermetic: in-memory SQLite, mocked price/email services, and a patched clock.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Trade, TradeAction, User
from services.digest_scheduler import DigestScheduler
from services.digest_service import DigestService

# 2026-06-07 is a Sunday (weekday 6); the default schedule is Sunday 18:00.
SUNDAY_6PM = datetime(2026, 6, 7, 18, 30)
SUNDAY_5PM = datetime(2026, 6, 7, 17, 0)
MONDAY_6PM = datetime(2026, 6, 8, 18, 30)
NEXT_SUNDAY_6PM = datetime(2026, 6, 14, 18, 30)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _scheduler():
    digest = MagicMock()
    digest.send_weekly_batch.return_value = 1
    email = MagicMock()
    email.enabled = True
    return DigestScheduler(digest, email), digest


class TestScheduler:
    def test_sends_in_window_and_is_idempotent_within_week(self, db):
        sched, digest = _scheduler()
        with patch.object(DigestScheduler, "_now", staticmethod(lambda: SUNDAY_6PM)):
            assert sched.maybe_send(db) is True
            assert sched.maybe_send(db) is False        # already sent this ISO week
        digest.send_weekly_batch.assert_called_once()

    def test_before_hour_does_not_send(self, db):
        sched, digest = _scheduler()
        with patch.object(DigestScheduler, "_now", staticmethod(lambda: SUNDAY_5PM)):
            assert sched.maybe_send(db) is False
        digest.send_weekly_batch.assert_not_called()

    def test_wrong_weekday_does_not_send(self, db):
        sched, digest = _scheduler()
        with patch.object(DigestScheduler, "_now", staticmethod(lambda: MONDAY_6PM)):
            assert sched.maybe_send(db) is False
        digest.send_weekly_batch.assert_not_called()

    def test_next_week_sends_again(self, db):
        sched, digest = _scheduler()
        with patch.object(DigestScheduler, "_now", staticmethod(lambda: SUNDAY_6PM)):
            sched.maybe_send(db)
        with patch.object(DigestScheduler, "_now", staticmethod(lambda: NEXT_SUNDAY_6PM)):
            assert sched.maybe_send(db) is True
        assert digest.send_weekly_batch.call_count == 2


def _price_service():
    ps = MagicMock()
    ps.get_live_prices.return_value = {"NVDA": 151.0}
    ps.get_live_price.return_value = 151.0
    # close ~a week ago resolves to 145.0
    ps.get_historical_closes.return_value = [("2026-05-25", 140.0), ("2026-05-30", 145.0)]
    return ps


def _user(db, **kw) -> User:
    defaults = dict(email="trader@example.com", password_hash="x", is_admin=True, digest_opt_in=True)
    defaults.update(kw)
    u = User(**defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


class TestDigestBuilder:
    def test_builds_and_sends_email_with_position(self, db):
        user = _user(db)
        db.add(Trade(user_id=user.id, action=TradeAction.BUY, ticker="NVDA",
                     quantity=100, price=100.0, fees=0, executed_at=date(2026, 1, 2)))
        db.commit()

        email = MagicMock()
        email.send_html.return_value = True
        svc = DigestService(_price_service(), email)

        assert svc.send_for_user(db, user) is True
        email.send_html.assert_called_once()
        to, subject, html = email.send_html.call_args.args[:3]
        assert to == "trader@example.com"
        assert "weekly portfolio digest" in subject.lower()
        assert "NVDA" in html
        assert "Unrealized" in html

    def test_empty_portfolio_skipped_in_batch_but_sendable_directly(self, db):
        user = _user(db)  # no trades
        email = MagicMock()
        email.send_html.return_value = True
        svc = DigestService(_price_service(), email)

        # batch skips users with nothing to report...
        assert svc.send_weekly_batch(db) == 0
        email.send_html.assert_not_called()
        # ...but a direct (test) send still goes out with a friendly empty state.
        assert svc.send_for_user(db, user) is True
        assert "No open positions" in email.send_html.call_args.args[2]

    def test_batch_only_emails_opted_in_users(self, db):
        opted = _user(db, email="yes@example.com", digest_opt_in=True)
        _user(db, email="no@example.com", digest_opt_in=False)
        for u_id in (opted.id,):
            db.add(Trade(user_id=u_id, action=TradeAction.BUY, ticker="NVDA",
                         quantity=10, price=100.0, fees=0, executed_at=date(2026, 1, 2)))
        db.commit()

        email = MagicMock()
        email.send_html.return_value = True
        svc = DigestService(_price_service(), email)

        assert svc.send_weekly_batch(db) == 1
        assert email.send_html.call_args.args[0] == "yes@example.com"
