import io
import json
import time
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from kiteconnect.exceptions import TokenException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.sessions import COOKIE, store
from app.brokers.demo import DemoBroker
from app.core.config import settings
from app.database.models import RiskRun
from app.main import app


def csv_bytes():
    return b"date,instrument,close,currency\n2026-01-01,NSE:A,100,INR\n2026-01-02,NSE:A,102,INR\n"


def upload(client, content=None, filename="history.csv", adjustment="split_dividend_adjusted"):
    return client.post(
        "/api/history/import",
        files={"file": (filename, content or csv_bytes())},
        data={"source": "Permitted test history", "adjustment": adjustment},
    )


def test_demo_workflow_and_audit(client, database):
    assert client.get("/api/health").json()["status"] == "ok"
    response = client.get("/api/session")
    assert response.cookies.get(COOKIE)
    assert "httponly" in response.headers["set-cookie"].lower()
    p = client.get("/api/portfolio").json()
    assert p["mode"] == "demo" and p["synthetic"] is True
    assert sum(h["weight"] for h in p["holdings"]) == pytest.approx(1)
    a = client.get("/api/risk").json()
    b = client.get("/api/risk").json()
    assert a["historical_var"] == b["historical_var"]
    assert a["run_id"] != b["run_id"]
    assert a["sample_size"] == 252
    assert a["historical_var_amount"] == pytest.approx(p["total_value"] * a["historical_var"])
    with Session(database) as db:
        runs = db.scalars(select(RiskRun)).all()
        assert len(runs) == 2
        assert runs[0].input_hash == runs[1].input_hash
        assert COOKIE not in json.dumps(runs[0].result)


@pytest.mark.parametrize("params", [{"confidence": 0.5}, {"window": 2}, {"mode": "bad"}])
def test_bad_risk_params(client, params):
    response = client.get("/api/risk", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("confidence,window", [(0.95, 126), (0.99, 126), (0.95, 252), (0.99, 504)])
def test_browser_query_parameters_parse_as_numbers(client, confidence, window):
    response = client.get(
        "/api/risk", params={"mode": "demo", "confidence": str(confidence), "window": str(window)}
    )
    assert response.status_code == 200, response.text
    assert response.json()["confidence"] == confidence
    assert response.json()["sample_size"] == window


def test_import_ownership_and_demo_separation(client):
    response = upload(client)
    assert response.status_code == 201, response.text
    dataset_id = response.json()["id"]
    assert len(client.get("/api/history").json()) == 1
    result = client.get("/api/risk", params={"dataset_id": dataset_id})
    assert result.json()["error"]["code"] == "SOURCE_MODE_MISMATCH"
    with TestClient(app) as other:
        assert other.get("/api/history").json() == []


def test_parquet_upload(client):
    frame = pd.read_csv(io.BytesIO(csv_bytes()))
    data = io.BytesIO()
    frame.to_parquet(data, index=False)
    response = upload(client, data.getvalue(), "history.parquet")
    assert response.status_code == 201


@pytest.mark.parametrize(
    "content,code",
    [
        (b"date,instrument,close,currency\n2026-01-01,NSE:A,0,INR", "HISTORY_VALUES"),
        (b"date,instrument,close,currency\n2026-01-01,NSE:A,inf,INR", "HISTORY_VALUES"),
        (b"date,instrument,close,currency\n2026-01-01,NSE:A,1,USD", "HISTORY_CURRENCY"),
        (b"date,instrument,close,currency\n2026-01-01,A,1,INR", "INSTRUMENT_ID"),
        (
            b"date,instrument,close,currency\n2026-01-01,NSE:A,1,INR\n2026-01-01,NSE:A,2,INR",
            "DUPLICATE_OBSERVATION",
        ),
        (b"date,close\n2026-01-01,100", "HISTORY_SCHEMA"),
    ],
)
def test_bad_history(client, content, code):
    response = upload(client, content)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_auth_required_and_cross_origin_rejected(client):
    assert client.get("/api/portfolio?mode=kite").status_code == 401
    assert client.get("/api/kite/positions").status_code == 401
    assert client.get("/api/kite/margins").status_code == 401
    assert client.get("/api/kite/instruments").status_code == 401
    response = client.post("/api/auth/kite/logout", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert (
        client.post(
            "/api/auth/kite/logout", headers={"Origin": "http://localhost:3000"}
        ).status_code
        == 200
    )
    assert client.post("/api/orders").status_code == 404


def test_callback_state_single_use_server_only_token_and_logout(client, monkeypatch):
    monkeypatch.setattr(settings(), "kite_api_key", "test-key")
    monkeypatch.setattr(settings(), "kite_api_secret", "test-secret")

    class FakeKite:
        def login_url(self):
            return "https://kite.zerodha.com/connect/login?v=3&api_key=test-key"

        def generate_session(self, request_token, api_secret):
            assert request_token == "one-use-request"
            assert api_secret == "test-secret"
            return {"access_token": "private-access-token"}

    monkeypatch.setattr("app.api.routes.new_client", FakeKite)
    login = client.get("/api/auth/kite/login", follow_redirects=False)
    params = parse_qs(urlparse(login.headers["location"]).query)
    state = parse_qs(params["redirect_params"][0])["state"][0]
    response = client.get(
        "/api/auth/kite/callback",
        params={"request_token": "one-use-request", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "private-access-token" not in response.text + str(response.headers)
    assert client.get("/api/session").json()["kite_connected"]
    assert store.items[client.cookies.get(COOKIE)].kite_token == "private-access-token"
    replay = client.get(
        "/api/auth/kite/callback", params={"request_token": "one-use-request", "state": state}
    )
    assert replay.status_code == 400
    assert "one-use-request" not in replay.text
    monkeypatch.setattr("app.brokers.kite.new_client", lambda: FakeLogoutKite())
    assert client.post("/api/auth/kite/logout").json()["connected"] is False
    assert client.get("/api/session").json()["kite_connected"] is False


class FakeLogoutKite:
    def set_access_token(self, token):
        pass

    def invalidate_access_token(self):
        return True


def test_invalid_state_and_expired_session(client):
    client.get("/api/session")
    response = client.get("/api/auth/kite/callback?state=bad&request_token=secret")
    assert response.status_code == 400
    assert "secret" not in response.text
    session = store.items[client.cookies.get(COOKIE)]
    session.kite_token = "private"
    session.expires = time.time() - 1
    assert client.get("/api/session").json()["kite_connected"] is False


def live_portfolio(monkeypatch):
    p = DemoBroker().portfolio().model_copy(update={"mode": "kite", "synthetic": False})
    monkeypatch.setattr("app.api.routes.snapshot", lambda mode, session: p)
    return p


def test_real_holdings_never_fall_back_to_demo(client, monkeypatch):
    live_portfolio(monkeypatch)
    response = client.get("/api/risk?mode=kite")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "HISTORY_REQUIRED"
    assert response.json().get("series") is None


def test_real_history_validation_and_owner_check(client, monkeypatch):
    live_portfolio(monkeypatch)
    imported = upload(client).json()["id"]
    response = client.get(f"/api/risk?mode=kite&dataset_id={imported}")
    assert response.json()["error"]["code"] == "MISSING_COVERAGE"
    unadjusted = upload(client, adjustment="unknown").json()["id"]
    assert (
        client.get(f"/api/risk?mode=kite&dataset_id={unadjusted}").json()["error"]["code"]
        == "ADJUSTMENT_REQUIRED"
    )
    with TestClient(app) as other:
        assert other.get(f"/api/risk?mode=kite&dataset_id={imported}").status_code == 404


def test_expired_kite_token_clears_server_access(client, monkeypatch):
    monkeypatch.setattr(settings(), "kite_api_key", "test")
    monkeypatch.setattr(settings(), "kite_api_secret", "test")

    class ExpiredKite:
        def set_access_token(self, token):
            pass

        def holdings(self):
            raise TokenException("secret upstream detail")

    monkeypatch.setattr("app.brokers.kite.new_client", ExpiredKite)
    client.get("/api/session")
    store.items[client.cookies.get(COOKIE)].kite_token = "private"
    response = client.get("/api/portfolio?mode=kite")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "KITE_SESSION_EXPIRED"
    assert "secret upstream detail" not in response.text
    assert client.get("/api/session").json()["kite_connected"] is False


def test_real_full_import_risk_and_staleness(client, monkeypatch):
    p = live_portfolio(monkeypatch)
    # Deliberately constructed synthetic test data, never supplied to live app users.
    dates = pd.bdate_range(end=p.as_of, periods=101)
    records = [
        {
            "date": d.strftime("%Y-%m-%d"),
            "instrument": h.instrument,
            "close": 100 + i,
            "currency": "INR",
        }
        for h in p.holdings
        for i, d in enumerate(dates)
    ]
    frame = pd.DataFrame(records)
    imported = upload(client, frame.to_csv(index=False).encode()).json()["id"]
    result = client.get(f"/api/risk?mode=kite&dataset_id={imported}")
    assert result.status_code == 200, result.text
    assert result.json()["provenance"]["synthetic"] is False
    frame["date"] = (pd.to_datetime(frame.date) - timedelta(days=20)).dt.strftime("%Y-%m-%d")
    stale = upload(client, frame.to_csv(index=False).encode()).json()["id"]
    assert (
        client.get(f"/api/risk?mode=kite&dataset_id={stale}").json()["error"]["code"]
        == "STALE_HISTORY"
    )


def test_validation_error_does_not_echo_secrets(client):
    response = client.get(
        "/api/auth/kite/callback", params={"request_token": "secret" * 100, "state": "x"}
    )
    assert response.status_code == 422
    assert "secret" not in response.text
