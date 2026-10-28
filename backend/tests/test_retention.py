from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session
from test_identity import account

from app.core.config import settings
from app.database.models import PrivateArtifact
from app.storage.maintenance import sweep
from app.storage.service import store


def test_retention_dry_run_expired_exports_and_preserved_source_evidence(
    agent_client, monkeypatch, tmp_path
):
    client, engine = agent_client
    me = account(client)
    monkeypatch.setattr(settings(), "private_storage_dir", str(tmp_path))
    with Session(engine) as db:
        expired = store(db, me["workspace_id"], "export", b"SYNTHETIC expired export")
        source = store(db, me["workspace_id"], "dataset", b"SYNTHETIC preserved source")
        db.commit()
        for ident in (expired["object_id"], source["object_id"]):
            db.get(PrivateArtifact, ident).expires_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()
        assert sweep(db)["expired_exports_reports"] == 1
        assert db.get(PrivateArtifact, expired["object_id"]).status == "published"
        assert sweep(db, apply=True)["expired_exports_reports"] == 1
        assert db.get(PrivateArtifact, expired["object_id"]).status == "deleted"
        assert db.get(PrivateArtifact, source["object_id"]).status == "published"
        assert sweep(db, apply=True)["expired_exports_reports"] == 0
