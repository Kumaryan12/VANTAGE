"""Identity, revocation, ownership migration and independent review are backend boundaries."""

import time

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_optimization_api import completed

from app.auth import identity
from app.auth.sessions import COOKIE, store
from app.core.config import settings
from app.database.models import (
    AuthSession,
    GovernanceReviewEvent,
    OwnershipScope,
    SecurityEvent,
    User,
    UserRoleAssignment,
)
from app.optimization.service import queue

PASSWORD = "Separate synthetic research password 47!"
SECOND_PASSWORD = "Another synthetic recovery passphrase 92!"


def account(client, email="researcher@example.com"):
    response = client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 202, response.text
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def grant(engine, user_id, *roles):
    with Session(engine) as db:
        for role in roles:
            identity.insert_ignore(
                db, UserRoleAssignment, {"user_id": user_id, "role": role}, ["user_id", "role"]
            )
        db.commit()


def test_durable_sessions_rotate_revoke_and_do_not_depend_on_legacy_memory(agent_client):
    client, engine = agent_client
    me = account(client)
    raw = client.cookies.get(identity.AUTH_COOKIE)
    assert "password" not in str(me).lower() and raw not in str(me)
    with Session(engine) as db:
        user = db.get(User, me["user"]["id"])
        assert user.password_hash.startswith("$argon2id$")
        session = db.scalar(select(AuthSession))
        assert session.token_hash == identity.token_hash(raw) and raw not in session.token_hash
        assert db.get(OwnershipScope, session.scope_id).user_id == user.id
    store.items.clear()
    assert client.get("/api/auth/me").json()["workspace_id"] == me["workspace_id"]
    rotated = client.post("/api/auth/rotate")
    assert rotated.status_code == 200 and client.cookies.get(identity.AUTH_COOKIE) != raw
    with TestClient(client.app) as stolen:
        stolen.cookies.set(identity.AUTH_COOKIE, raw)
        assert stolen.get("/api/portfolio").status_code == 401
    current = rotated.json()["session_id"]
    assert client.post(f"/api/auth/sessions/{current}/revoke").status_code == 200
    assert client.get("/api/portfolio").status_code == 401
    assert client.post("/api/auth/logout").status_code == 200
    assert not client.cookies.get(identity.AUTH_COOKIE)


def test_recovery_single_use_and_password_change_revoke_all_sessions(agent_client):
    client, engine = agent_client
    me = account(client)
    with TestClient(client.app) as device:
        assert (
            device.post(
                "/api/auth/login", json={"email": "researcher@example.com", "password": PASSWORD}
            ).status_code
            == 200
        )
        with Session(engine) as db:
            token = identity.issue_recovery(db, me["user"]["id"])
        recovered = client.post(
            "/api/auth/recover", json={"token": token, "new_password": SECOND_PASSWORD}
        )
        assert recovered.status_code == 200 and token not in recovered.text
        assert device.get("/api/auth/me").status_code == 401
        assert (
            client.post(
                "/api/auth/recover", json={"token": token, "new_password": SECOND_PASSWORD}
            ).status_code
            == 400
        )
    assert (
        client.post(
            "/api/auth/login", json={"email": "researcher@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": "researcher@example.com", "password": SECOND_PASSWORD}
        ).status_code
        == 200
    )
    old = client.cookies.get(identity.AUTH_COOKIE)
    assert (
        client.post(
            "/api/auth/password",
            json={"current_password": SECOND_PASSWORD, "new_password": PASSWORD},
        ).status_code
        == 200
    )
    with TestClient(client.app) as revoked:
        revoked.cookies.set(identity.AUTH_COOKIE, old)
        assert revoked.get("/api/auth/me").status_code == 401


def test_legacy_claim_requires_live_original_cookie_and_preserves_saved_hashes(agent_client):
    client, engine = agent_client
    original = completed(client)
    legacy_cookie = client.cookies.get(COOKIE)
    old_owner = identity.token_hash(legacy_cookie)
    me = account(client)
    assert client.get(f"/api/v1/optimization/runs/{original['id']}").status_code == 404
    claimed = client.post("/api/auth/claim-legacy")
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["workspace_id"] == old_owner
    assert legacy_cookie not in store.items
    reopened = client.get(f"/api/v1/optimization/runs/{original['id']}").json()
    assert (
        reopened["input_hash"] == original["input_hash"]
        and reopened["result"] == original["result"]
    )
    with Session(engine) as db:
        assert db.get(OwnershipScope, old_owner).user_id == me["user"]["id"]
        assert db.scalar(
            select(SecurityEvent).where(SecurityEvent.action == "legacy_workspace_claimed")
        )
    client.post("/api/auth/logout")
    store.items.clear()
    assert (
        client.post(
            "/api/auth/login", json={"email": "researcher@example.com", "password": PASSWORD}
        ).json()["workspace_id"]
        == old_owner
    )
    assert client.get(f"/api/v1/optimization/runs/{original['id']}").status_code == 200
    with TestClient(client.app) as other:
        other_me = account(other, "second@example.com")
        other.cookies.set(COOKIE, legacy_cookie)
        assert other.post("/api/auth/claim-legacy").status_code == 409
        assert other.post("/api/auth/workspace", json={"scope_id": old_owner}).status_code == 404
        assert other.get(f"/api/v1/optimization/runs/{original['id']}").status_code == 404
        assert other_me["user"]["roles"] == ["USER"]


def test_expired_proof_and_missing_auth_never_claim_orphaned_records(agent_client, monkeypatch):
    client, engine = agent_client
    original = completed(client)
    legacy = client.cookies.get(COOKIE)
    account(client)
    store.items[legacy].expires = time.time() - 1
    assert client.post("/api/auth/claim-legacy").status_code == 409
    with Session(engine) as db:
        assert db.get(OwnershipScope, identity.token_hash(legacy)).user_id is None
    monkeypatch.setattr(settings(), "auth_required", True)
    with TestClient(client.app) as anonymous:
        assert anonymous.get("/api/portfolio").status_code == 401
        assert anonymous.get("/api/context/macro").status_code == 401
        assert anonymous.get(f"/api/v1/optimization/runs/{original['id']}").status_code == 401
        assert anonymous.get("/api/health").status_code == 200
        assert anonymous.get("/api/auth/me").json()["authenticated"] is False


def test_login_failures_generic_throttled_and_sensitive_inputs_are_not_echoed(agent_client):
    client, engine = agent_client
    account(client)
    client.post("/api/auth/logout")
    wrong = client.post(
        "/api/auth/login", json={"email": "researcher@example.com", "password": "wrong"}
    )
    missing = client.post(
        "/api/auth/login", json={"email": "unknown@example.com", "password": "wrong"}
    )
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["error"] == missing.json()["error"]
    for _ in range(9):
        response = client.post(
            "/api/auth/login", json={"email": "researcher@example.com", "password": "wrong"}
        )
    assert response.status_code == 429
    secret = "Never-echo-this-credential-" * 20
    invalid = client.post(
        "/api/auth/login",
        json={"email": "researcher@example.com", "password": secret, "role": "PLATFORM_ADMIN"},
    )
    assert invalid.status_code == 422 and secret not in invalid.text
    evil = client.post(
        "/api/auth/login",
        json={"email": "researcher@example.com", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert evil.status_code == 403 and PASSWORD not in evil.text
    with Session(engine) as db:
        assert PASSWORD not in str([r.payload for r in db.scalars(select(SecurityEvent))])


def test_admin_suspension_is_not_financial_authorization(agent_client):
    client, engine = agent_client
    me = account(client)
    saved = completed(client)
    assert client.get("/api/auth/admin/users").status_code == 403
    with TestClient(client.app) as admin:
        privileged = account(admin, "platform@example.com")
        grant(engine, privileged["user"]["id"], "PLATFORM_ADMIN")
        assert admin.get("/api/auth/admin/users").status_code == 200
        assert admin.get(f"/api/v1/optimization/runs/{saved['id']}").status_code == 404
        assert (
            admin.post(
                f"/api/auth/admin/users/{me['user']['id']}/status", json={"active": False}
            ).status_code
            == 200
        )
        assert client.get("/api/auth/me").status_code == 401
        assert (
            client.post(
                "/api/auth/login", json={"email": "researcher@example.com", "password": PASSWORD}
            ).status_code
            == 401
        )


def test_independent_assigned_reviewer_and_creator_separation(agent_client):
    client, engine = agent_client
    me = account(client)
    saved = completed(client)
    model_id = saved["result"]["governance_model_id"]
    grant(engine, me["user"]["id"], "RESEARCH_ADMIN", "RESEARCH_REVIEWER")
    base = {
        "human_review": True,
        "research_only": True,
        "rationale": "Synthetic independent-review fixture; no real-market approval is asserted.",
    }
    assert (
        client.post(
            f"/api/v1/governance/models/{model_id}/review", json={**base, "status": "under_review"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/governance/models/{model_id}/review", json={**base, "status": "validated"}
        ).status_code
        == 403
    )
    with TestClient(client.app) as reviewer:
        reviewer_me = account(reviewer, "reviewer@example.com")
        uid = reviewer_me["user"]["id"]
        grant(engine, uid, "RESEARCH_REVIEWER")
        assert reviewer.get(f"/api/v1/governance/models/{model_id}").status_code == 404
        assert (
            client.post(
                f"/api/v1/governance/models/{model_id}/assign",
                json={"reviewer_id": me["user"]["id"]},
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/v1/governance/models/{model_id}/assign", json={"reviewer_id": uid}
            ).status_code
            == 200
        )
        assert reviewer.get(f"/api/v1/governance/models/{model_id}/evidence").status_code == 200
        assert reviewer.get(f"/api/v1/optimization/runs/{saved['id']}").status_code == 404
        replay = client.post(f"/api/v1/optimization/runs/{saved['id']}/reproduce").json()
        queue.futures[replay["id"]].result(timeout=30)
        from app.governance.contracts import REVIEW_AREAS

        notes = {
            area: "Synthetic method fixture: this area has no independent real-market evidence and cannot justify investment use."
            for area in REVIEW_AREAS
        }
        assert (
            reviewer.post(
                f"/api/v1/governance/models/{model_id}/review",
                json={**base, "status": "validated", "assessments": notes},
            ).status_code
            == 200
        )
        approved = reviewer.post(
            f"/api/v1/governance/models/{model_id}/review",
            json={**base, "status": "approved_research"},
        )
        assert approved.status_code == 200, approved.text
        with Session(engine) as db:
            event = db.scalars(
                select(GovernanceReviewEvent)
                .where(GovernanceReviewEvent.model_id == model_id)
                .order_by(GovernanceReviewEvent.created_at.desc())
            ).first()
            assert event.payload["reviewer_user_id"] == uid
        assert (
            client.post(
                f"/api/v1/governance/models/{model_id}/assign",
                json={"reviewer_id": uid, "active": False},
            ).status_code
            == 200
        )
        assert reviewer.get(f"/api/v1/governance/models/{model_id}").status_code == 404


def test_authenticated_kite_state_is_persisted_hashed_and_single_use(agent_client, monkeypatch):
    from urllib.parse import parse_qs, urlparse

    client, engine = agent_client
    me = account(client)
    monkeypatch.setattr(settings(), "kite_api_key", "fixture-key")
    monkeypatch.setattr(settings(), "kite_api_secret", "fixture-secret")

    class FakeKite:
        def login_url(self):
            return "https://kite.zerodha.com/connect/login?v=3&api_key=fixture-key"

        def generate_session(self, request_token, api_secret):
            return {"access_token": "private-fixture-broker-token"}

    monkeypatch.setattr("app.api.routes.new_client", FakeKite)
    login = client.get("/api/auth/kite/login", follow_redirects=False)
    assert login.status_code == 303, login.text
    params = parse_qs(urlparse(login.headers["location"]).query)
    state = parse_qs(params["redirect_params"][0])["state"][0]
    with Session(engine) as db:
        session = db.get(AuthSession, me["session_id"])
        assert session.oauth_state_hash == identity.token_hash(state)
    callback = client.get(
        "/api/auth/kite/callback",
        params={"request_token": "fixture-request", "state": state},
        follow_redirects=False,
    )
    assert (
        callback.status_code == 303
        and "private-fixture-broker-token" not in callback.text + str(callback.headers)
    )
    assert client.get("/api/session").json()["kite_connected"]
    assert (
        client.get(
            "/api/auth/kite/callback",
            params={"request_token": "fixture-request", "state": state},
            follow_redirects=False,
        ).status_code
        == 400
    )
    with Session(engine) as db:
        assert db.get(AuthSession, me["session_id"]).oauth_state_hash is None


def test_expiry_and_idle_timeout_do_not_fall_back_to_guest(agent_client):
    client, engine = agent_client
    me = account(client)
    with Session(engine) as db:
        db.get(AuthSession, me["session_id"]).expires = int(time.time()) - 1
        db.commit()
    assert client.get("/api/portfolio").status_code == 401
    logged = client.post(
        "/api/auth/login", json={"email": "researcher@example.com", "password": PASSWORD}
    ).json()
    with Session(engine) as db:
        db.get(AuthSession, logged["session_id"]).last_seen = (
            int(time.time()) - settings().auth_idle_minutes * 60 - 1
        )
        db.commit()
    assert client.get("/api/portfolio").status_code == 401


def test_champion_endpoint_cannot_bypass_independent_governance(agent_client):
    from test_agent_core import completed_research

    client, engine = agent_client
    me = account(client)
    experiment = completed_research(client)
    model = client.get(f"/api/v1/ml/models?experiment_id={experiment}").json()[0]
    body = {
        "role": "champion",
        "acknowledge_limitations": True,
        "rationale": "Synthetic research fixture cannot establish real-market superiority or bypass independent review.",
    }
    assert client.post(f"/api/v1/ml/models/{model['id']}/governance", json=body).status_code == 403
    grant(engine, me["user"]["id"], "RESEARCH_ADMIN")
    assert client.post(f"/api/v1/ml/models/{model['id']}/governance", json=body).status_code == 403


def test_durable_cross_user_scope_covers_each_research_resource_category(agent_client):
    from datetime import UTC, datetime

    from test_agent_core import completed_research, investigation
    from test_documents import uploaded

    from app.database.models import Dataset
    from app.risk.artifacts import digest

    client, engine = agent_client
    me = account(client)
    risk = client.post("/api/v1/risk/analysis", json={"simulations": 2000}).json()
    optimization = completed(client)
    experiment = completed_research(client)
    model = client.get(f"/api/v1/ml/models?experiment_id={experiment}").json()[0]
    document = uploaded(client)
    answer = investigation(client, question="Explain portfolio holdings and sector exposures.")
    dataset_id = "8b3805d3-d8de-4fbe-b2d0-16e19d839949"
    with Session(engine) as db:
        db.add(
            Dataset(
                id=dataset_id,
                owner=me["workspace_id"],
                provenance={
                    "synthetic": True,
                    "source": "Synthetic authorization-only fixture",
                    "content_hash": digest({"fixture": True}),
                },
                records="date,instrument,close,currency\n",
                created_at=datetime.now(UTC),
            )
        )
        db.commit()
    with TestClient(client.app) as stranger:
        other = account(stranger, "isolated@example.com")
        grant(engine, other["user"]["id"], "PLATFORM_ADMIN")
        paths = [
            f"/api/v1/risk/runs/{risk['run_id']}",
            f"/api/v1/ml/experiments/{experiment}",
            f"/api/v1/ml/models/{model['id']}",
            f"/api/v1/ml/models/{model['id']}/artifact",
            f"/api/v1/research/documents/{document['id']}",
            f"/api/v1/research/documents/{document['id']}/file",
            f"/api/v1/agent/investigations/{answer['id']}",
            f"/api/v1/agent/investigations/{answer['id']}/evidence",
            f"/api/v1/optimization/runs/{optimization['id']}",
            f"/api/v1/governance/models/{optimization['result']['governance_model_id']}",
        ]
        for path in paths:
            assert stranger.get(path).status_code == 404, path
        assert dataset_id not in str(stranger.get("/api/history").json())
        assert stranger.get("/api/v1/research/documents").json() == []
        assert stranger.get("/api/v1/optimization/runs").json() == []
        assert stranger.post(f"/api/auth/sessions/{me['session_id']}/revoke").status_code == 404
