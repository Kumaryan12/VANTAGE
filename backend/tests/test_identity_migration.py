"""Upgrade a genuine legacy schema with data; orphan ownership is never inferred."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.database.models import OwnershipScope, PortfolioSnapshot, RiskInputArtifact
from app.risk.artifacts import digest

ROOT = Path(__file__).resolve().parents[2]


def test_legacy_schema_upgrade_preserves_payload_hashes_and_foreign_keys(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    env = {**os.environ, "DATABASE_URL": url}
    command = [sys.executable, "-m", "alembic", "-c", str(ROOT / "backend/alembic.ini"), "upgrade"]
    subprocess.run([*command, "0008"], env=env, cwd=ROOT, check=True, capture_output=True)
    engine = create_engine(url)
    from datetime import UTC, datetime

    from sqlalchemy import text

    payload = {
        "synthetic": True,
        "description": "Immutable legacy migration fixture, not real account data.",
    }
    original = digest(payload)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO portfolio_snapshots(id,owner,content_hash,payload,created_at) VALUES(:id,:owner,:hash,:payload,:created)"
            ),
            {
                "id": "legacy-snapshot",
                "owner": "a" * 64,
                "hash": original,
                "payload": __import__("json").dumps(payload),
                "created": datetime.now(UTC).isoformat(),
            },
        )
        connection.execute(
            text(
                "INSERT INTO risk_input_artifacts(id,owner,content_hash,payload,created_at) VALUES(:id,:owner,:hash,:payload,:created)"
            ),
            {
                "id": "legacy-artifact",
                "owner": "b" * 64,
                "hash": original,
                "payload": __import__("json").dumps(payload),
                "created": datetime.now(UTC).isoformat(),
            },
        )
    subprocess.run([*command, "head"], env=env, cwd=ROOT, check=True, capture_output=True)
    with Session(engine) as db:
        scopes = db.scalars(select(OwnershipScope)).all()
        assert {r.id for r in scopes} == {"a" * 64, "b" * 64}
        assert all(r.user_id is None for r in scopes)
        for model, ident in (
            (PortfolioSnapshot, "legacy-snapshot"),
            (RiskInputArtifact, "legacy-artifact"),
        ):
            row = db.get(model, ident)
            assert row.content_hash == original and digest(row.payload) == original
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    assert any(
        f["referred_table"] == "ownership_scopes"
        for f in inspect(engine).get_foreign_keys("portfolio_snapshots")
    )
    from app.auth.identity import create_user

    with Session(engine) as db:
        assert create_user(db, "migration@example.com", "Restorable synthetic evidence fixture 51!")
    rollback = subprocess.run(
        command[:-1] + ["downgrade", "0008"], env=env, cwd=ROOT, capture_output=True
    )
    assert rollback.returncode != 0
    assert b"Populated identity migration is forward-only" in rollback.stderr
    with Session(engine) as db:
        assert db.get(PortfolioSnapshot, "legacy-snapshot").content_hash == original
    engine.dispose()
