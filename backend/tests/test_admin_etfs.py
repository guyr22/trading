"""ETF mappings are shared: only admins may change them. No database writes."""
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth.dependencies import get_current_user
from database import get_db
from dependencies import get_etf_repo
from models import LeveragedEtf, User
from routers.leveraged_etfs import router


def client_for(is_admin=None):
    app = FastAPI()
    app.include_router(router)
    repo = MagicMock()
    repo.get_all_ordered.return_value = []
    app.dependency_overrides[get_etf_repo] = lambda: repo
    app.dependency_overrides[get_db] = lambda: None
    if is_admin is not None:
        app.dependency_overrides[get_current_user] = lambda: User(id=1, is_admin=is_admin)
    return TestClient(app), repo


def test_regular_user_can_read_but_cannot_modify_shared_etf_mappings():
    client, repo = client_for(False)
    with client:
        assert client.get("/api/leveraged-etfs").status_code == 200
        assert client.post("/api/leveraged-etfs", json={"ticker": "TSLL", "underlying": "TSLA", "leverage_factor": 2}).status_code == 403
        assert client.delete("/api/leveraged-etfs/TSLL").status_code == 403
    repo.add.assert_not_called()
    repo.delete.assert_not_called()


def test_admin_can_create_and_remove_etf_mapping():
    client, repo = client_for(True)
    mapping = LeveragedEtf(id=1, ticker="TSLL", underlying="TSLA", leverage_factor=2, name=None)
    repo.find_by_ticker.return_value = None
    repo.add.return_value = mapping
    with client:
        response = client.post("/api/leveraged-etfs", json={"ticker": "tsll", "underlying": "tsla", "leverage_factor": 2})
        assert response.status_code == 201
        assert response.json()["ticker"] == "TSLL"
        repo.find_by_ticker.return_value = mapping
        assert client.delete("/api/leveraged-etfs/TSLL").status_code == 204
    repo.add.assert_called_once()
    repo.delete.assert_called_once_with(mapping)


def test_anonymous_requests_cannot_read_or_change_mappings():
    client, repo = client_for()
    with client:
        assert client.get("/api/leveraged-etfs").status_code == 401
        assert client.post("/api/leveraged-etfs", json={"ticker": "TSLL", "underlying": "TSLA", "leverage_factor": 2}).status_code == 401
        assert client.delete("/api/leveraged-etfs/TSLL").status_code == 401
    repo.get_all_ordered.assert_not_called()
    repo.add.assert_not_called()
    repo.delete.assert_not_called()
