"""Split accounting and authenticated APIs; all data stays in in-memory SQLite."""
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations, ops
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth.dependencies import get_current_user
from core.activity import ActivityTracker, SCOPE_INDEXES
from database import Base, get_db
from domain.finance import fifo_full
from models import IndexTrade, StockSplit, Trade, TradeAction, User
from repositories.trade_repository import TradeRepository
from repositories.etf_repository import EtfRepository
from routers import splits, trades, index_trades
from services.portfolio_service import PortfolioService
from services.price_service import PriceService
from services.statistics_service import StatisticsService


def trade(action="BUY", qty=10, price=100, day=1, fees=0, platform="IBI", ticker="AAA", id=None):
    return Trade(id=id, user_id=1, ticker=ticker, action=TradeAction(action), quantity=qty,
                 price=price, fees=fees, platform=platform, executed_at=date(2024, 1, day))


def split(new=2, old=1, day=3, ticker="AAA"):
    return StockSplit(user_id=1, ticker=ticker, new_shares=new, old_shares=old, executed_at=date(2024, 1, day))


def test_forward_split_keeps_cost_and_original_trades():
    original = trade(fees=10)
    result = fifo_full([original], "AAA", [split()])
    assert result.quantity == 20
    assert result.avg_cost == 50
    assert result.quantity * result.avg_cost == 1000
    assert result.closed_lots == []
    assert (original.quantity, original.price, original.fees) == (10, 100, 10)


def test_partial_sale_before_split_stays_unchanged_and_fees_scale():
    history = [trade(fees=10), trade("SELL", 4, 120, day=2, fees=4),
               trade("SELL", 6, 60, day=4, fees=3)]
    result = fifo_full(history, "AAA", [split()])
    first, second = result.closed_lots
    assert (first.quantity, first.avg_buy_price, first.pnl) == (4, 100, 72)
    assert (second.quantity, second.avg_buy_price, second.cost_basis, second.pnl) == (6, 50, 300, 54)
    assert result.realized_pnl == 126
    assert result.quantity == 6
    assert result.avg_cost == 50


def test_reverse_split_retains_fractional_shares():
    result = fifo_full([trade(qty=15, price=20)], "AAA", [split(1, 10)])
    assert result.quantity == 1.5
    assert result.avg_cost == 200
    assert result.quantity * result.avg_cost == 300


def test_multiple_splits_only_change_open_lots_and_same_day_buys_use_new_units():
    history = [trade(qty=10, price=100), trade(qty=5, price=50, day=3),
               trade("SELL", qty=10, price=60, day=4)]
    result = fifo_full(history, "AAA", [split(), split(1, 5, day=5), split(ticker="OTHER")])
    assert result.quantity == 3
    assert result.avg_cost == 250
    assert result.realized_pnl == 100
    assert result.closed_lots[0].quantity == 10


def test_split_applies_across_platforms_without_cross_matching():
    history = [trade(qty=10), trade(qty=5, price=200, platform="Interactive Brokers"),
               trade("SELL", qty=20, price=60, day=4)]
    result = fifo_full(history, "AAA", [split()])
    assert result.quantity == 10
    assert result.avg_cost == 100
    assert result.quantities_by_platform == {"IBI": 0, "Interactive Brokers": 10}
    assert len(result.closed_lots) == 1
    assert result.closed_lots[0].platform == "IBI"


def test_split_adjusts_short_lots_and_opening_fees():
    result = fifo_full([trade("SELL", fees=10), trade("BUY", qty=20, price=40, day=4, fees=10)], "AAA", [split()])
    assert result.quantity == 0
    assert result.realized_pnl == 180
    assert result.closed_lots[0].cost_basis == 1000


@pytest.fixture
def setup(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)  # Isolated test schema, never the application DB.
    db = sessionmaker(bind=engine)()
    db.add_all([User(id=1, email="one@test.invalid", password_hash="unused"),
                User(id=2, email="two@test.invalid", password_hash="unused")])
    db.commit()
    app = FastAPI()
    app.include_router(splits.router)
    app.include_router(trades.router)
    app.include_router(index_trades.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
    tracker = ActivityTracker()
    monkeypatch.setattr("core.activity.activity_tracker", tracker)
    with TestClient(app) as client:
        yield db, client, app, tracker
    db.close()
    engine.dispose()


def record(client, ticker="AAA", new=2, old=1, day="2024-01-03"):
    return client.post("/api/splits", json={"ticker": ticker, "new_shares": new, "old_shares": old, "executed_at": day})


def test_api_portfolio_statistics_and_sell_limit_use_adjusted_shares(setup):
    db, client, _, tracker = setup
    db.add(trade(fees=10))
    db.commit()
    response = record(client, ticker=" aaa ")
    assert response.status_code == 201
    assert response.json()["ticker"] == "AAA"
    price = MagicMock()
    price.get_cached_prices.return_value = {"AAA": 60}
    portfolio = PortfolioService(db, price, 1)
    pos = portfolio.build_summary().positions[0]
    assert (pos.quantity, pos.avg_cost, pos.market_value, pos.unrealized_pnl) == (20, 50, 1200, 200)
    stats = StatisticsService(db, portfolio, EtfRepository(db), price, 1)
    assert stats.compute().total_trades == 1  # Splits are not trades or wins.
    sale = {"action": "SELL", "ticker": "AAA", "quantity": 15, "price": 60, "platform": "IBI", "fees": 5,
            "executed_at": "2024-01-04"}
    assert client.post("/api/trades", json=sale).status_code == 201
    assert portfolio.build_summary().positions[0].quantity == 5
    assert stats.compute().closed_lots[0].pnl == 137.5
    assert stats.compute().total_trades == 2
    assert client.post("/api/trades", json={**sale, "quantity": 6}).status_code == 400
    tracker.touch(1)
    assert PriceService.tickers_to_refresh(db) == ["AAA"]
    split_id = response.json()["id"]
    assert client.delete(f"/api/splits/{split_id}").status_code == 409


def test_sale_before_split_cannot_use_post_split_shares(setup):
    db, client, _, _ = setup
    db.add(trade())
    db.commit()
    assert record(client).status_code == 201
    assert client.post("/api/trades", json={"action": "SELL", "ticker": "AAA", "quantity": 15,
        "price": 100, "platform": "IBI", "executed_at": "2024-01-02"}).status_code == 400


def test_backdated_sale_cannot_invalidate_a_later_post_split_sale(setup):
    db, client, _, _ = setup
    db.add(trade())
    db.commit()
    assert record(client).status_code == 201
    sale = {"action": "SELL", "ticker": "AAA", "quantity": 10,
            "price": 60, "platform": "IBI", "executed_at": "2024-01-04"}
    assert client.post("/api/trades", json=sale).status_code == 201
    # Eight old shares would leave only four new shares for the later sale.
    assert client.post("/api/trades", json={**sale, "quantity": 8, "executed_at": "2024-01-02"}).status_code == 409
    assert TradeRepository(db, 1).shares_held("AAA") == 10


def test_duplicate_future_invalid_ratio_and_no_holdings_rejected(setup):
    db, client, _, _ = setup
    db.add(trade())
    db.commit()
    assert record(client).status_code == 201
    assert record(client).status_code == 409
    for new, old in [(0, 1), (1, 0), (-2, 1), (1, 1)]:
        assert record(client, new=new, old=old).status_code == 422
    assert record(client, day=(date.today() + timedelta(days=1)).isoformat()).status_code == 422
    assert record(client, ticker="OTHER").status_code == 400
    assert record(client, day="2024-01-01").status_code == 400


def test_user_isolation_and_removal_restores_original_holdings(setup):
    db, client, app, _ = setup
    db.add_all([trade(), Trade(user_id=2, ticker="AAA", action=TradeAction.BUY, quantity=7,
                            price=80, executed_at=date(2024, 1, 1))])
    db.commit()
    response = record(client)
    split_id = response.json()["id"]
    assert TradeRepository(db, 1).shares_held("AAA") == 20
    assert TradeRepository(db, 2).shares_held("AAA") == 7
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 2)
    assert client.get("/api/splits").json() == []
    assert client.delete(f"/api/splits/{split_id}").status_code == 404
    assert record(client).status_code == 201  # Another user's event is independent.
    assert TradeRepository(db, 2).shares_held("AAA") == 14
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
    assert client.delete(f"/api/splits/{split_id}").status_code == 204
    assert TradeRepository(db, 1).shares_held("AAA") == 10
    assert TradeRepository(db, 2).shares_held("AAA") == 14


def test_split_routes_require_authentication(setup):
    _, client, app, _ = setup
    del app.dependency_overrides[get_current_user]
    assert client.get("/api/splits").status_code == 401
    assert record(client).status_code == 401
    assert client.delete("/api/splits/1").status_code == 401


def test_edit_post_split_sell_uses_adjusted_limit(setup):
    db, client, _, _ = setup
    db.add(trade())
    db.commit()
    assert record(client).status_code == 201
    sale = client.post("/api/trades", json={"action": "SELL", "ticker": "AAA", "quantity": 5,
        "price": 60, "platform": "IBI", "executed_at": "2024-01-04"})
    sale_id = sale.json()["id"]
    assert client.put(f"/api/trades/{sale_id}", json={"quantity": 20}).status_code == 200
    assert TradeRepository(db, 1).shares_held("AAA") == 0
    assert client.put(f"/api/trades/{sale_id}", json={"quantity": 21}).status_code == 400


def test_index_splits_portfolio_sales_and_refresh_scope(setup):
    db, client, _, tracker = setup
    db.add(IndexTrade(user_id=1, ticker="VOO", action=TradeAction.BUY, quantity=10,
                      price=400, platform="IBI", executed_at=date(2024, 1, 1)))
    db.commit()
    assert record(client, ticker="VOO").status_code == 201
    price = MagicMock()
    price.get_cached_prices.return_value = {"VOO": 210}
    service = PortfolioService(db, price, 1)
    summary = service.build_index_summary(db.query(IndexTrade).all())
    assert summary.positions[0].quantity == 20
    assert summary.positions[0].avg_cost == 200
    sale = {"action": "SELL", "ticker": "VOO", "quantity": 15, "price": 210, "platform": "IBI",
            "executed_at": "2024-01-04"}
    assert client.post("/api/index-trades", json={**sale, "platform": "Other"}).status_code == 400
    assert client.post("/api/index-trades", json=sale).status_code == 201
    tracker.touch(1, SCOPE_INDEXES)
    assert PriceService.tickers_to_refresh(db) == ["VOO"]
    assert service.build_summary().positions == []


def test_reverse_split_cannot_invalidate_existing_sales(setup):
    db, client, _, _ = setup
    db.add_all([trade(), trade("SELL", qty=8, price=100, day=4)])
    db.commit()
    assert record(client, new=1, old=2).status_code == 409
    assert db.query(StockSplit).count() == 0


def test_benchmark_uses_split_adjusted_lot_cost_basis(setup):
    db, client, _, _ = setup
    db.add_all([trade(), trade("SELL", qty=20, price=60, day=4)])
    db.commit()
    assert record(client).status_code == 201  # Backdated entry repairs post-split units.
    price = MagicMock()
    price.get_historical_closes.return_value = [("2024-01-01", 100), ("2024-01-04", 110)]
    portfolio = PortfolioService(db, price, 1)
    result = StatisticsService(db, portfolio, EtfRepository(db), price, 1).compute_benchmark("SPY")
    assert result.your_realized_pnl == 200
    assert result.benchmark_pnl == 100
    assert result.alpha == 100


def test_legacy_startup_stamp_runs_real_split_migration_and_is_idempotent(monkeypatch):
    import importlib
    startup = importlib.import_module("startup.lifespan")
    engine = create_engine("sqlite://", poolclass=StaticPool)
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    # Empty legacy schema prepared entirely through Alembic operations.
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        for table in Base.metadata.sorted_tables:
            if table.name != "stock_splits":
                operations.invoke(ops.CreateTableOp.from_table(table))
        cfg.attributes["connection"] = connection
        command.stamp(cfg, "e4f5a6b7c8d9")
        connection.execute(text("UPDATE alembic_version SET version_num = 'b2c3d4e5f6a7'"))
    cfg.attributes.pop("connection")
    monkeypatch.setattr(startup, "engine", engine)
    assert "stock_splits" not in inspect(engine).get_table_names()
    startup._upgrade_legacy_schema(cfg)
    assert "stock_splits" in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "d3762534ca7a"
        assert connection.execute(text("SELECT COUNT(*) FROM stock_splits")).scalar() == 0
    startup._upgrade_legacy_schema(cfg)
    assert "connection" not in cfg.attributes
    engine.dispose()
