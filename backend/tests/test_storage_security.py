import json
import time
from io import BytesIO

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_documents import uploaded
from test_identity import account
from test_optimization_api import completed

from app.core.config import settings
from app.core.errors import AppError
from app.database.models import (
    OwnershipScope,
    PrivateArtifact,
    ProviderCredential,
    ResearchDocumentChunk,
)
from app.security import vault
from app.storage.backends import LocalStorage, S3Storage
from app.storage.service import read_manifest, store


def keys(monkeypatch):
    ring = {"v1": Fernet.generate_key().decode()}
    monkeypatch.setattr(settings(), "master_key_file", "")
    monkeypatch.setattr(settings(), "master_keys", json.dumps(ring))
    monkeypatch.setattr(settings(), "master_key_active", "v1")
    return ring


def test_vault_authenticated_binding_expiry_rotation_revocation_and_metadata(
    agent_client, monkeypatch
):
    client, engine = agent_client
    me = account(client)
    ring = keys(monkeypatch)
    secret = "synthetic-broker-fixture-never-expose"
    with Session(engine) as db:
        row = vault.put(db, me["workspace_id"], secret, actor=me["user"]["id"])
        ident = row.id
        assert secret not in row.ciphertext
        assert vault.get(db, me["workspace_id"], actor=me["user"]["id"]) == secret
        ring["v2"] = Fernet.generate_key().decode()
        monkeypatch.setattr(settings(), "master_keys", json.dumps(ring))
        monkeypatch.setattr(settings(), "master_key_active", "v2")
        assert vault.rotate(db) == 1
        assert db.get(ProviderCredential, ident).key_id == "v2"
        monkeypatch.setattr(settings(), "master_keys", json.dumps({"v2": ring["v2"]}))
        assert vault.get(db, me["workspace_id"], actor=me["user"]["id"]) == secret
    projection = client.get("/api/auth/credentials")
    assert (
        projection.status_code == 200
        and secret not in projection.text
        and "ciphertext" not in projection.text
    )
    with TestClient(client.app) as stranger:
        account(stranger, "other@example.com")
        assert stranger.post(f"/api/auth/credentials/{ident}/revoke").status_code == 404
    assert client.post(f"/api/auth/credentials/{ident}/revoke").status_code == 200
    with Session(engine) as db:
        assert vault.get(db, me["workspace_id"], actor=me["user"]["id"]) is None
        assert db.get(ProviderCredential, ident).ciphertext == ""


def test_corrupt_missing_key_and_swapped_ciphertexts_fail_closed(agent_client, monkeypatch):
    client, engine = agent_client
    me = account(client)
    ring = keys(monkeypatch)
    with Session(engine) as db:
        row = vault.put(db, me["workspace_id"], "synthetic-token", actor=me["user"]["id"])
        original = row.ciphertext
        row.ciphertext = original[:-5] + "BAD!!"
        db.commit()
        with pytest.raises(AppError, match="authenticated"):
            vault.get(db, me["workspace_id"], actor=me["user"]["id"])
        row.ciphertext = original
        db.commit()
        monkeypatch.setattr(
            settings(), "master_keys", json.dumps({"v1": Fernet.generate_key().decode()})
        )
        with pytest.raises(AppError):
            vault.get(db, me["workspace_id"], actor=me["user"]["id"])
        monkeypatch.setattr(settings(), "master_keys", json.dumps(ring))
        row.revision += 1
        db.commit()
        with pytest.raises(AppError):
            vault.get(db, me["workspace_id"], actor=me["user"]["id"])
        row.revision -= 1
        original_expiry = row.expires
        row.expires += 3600
        db.commit()
        with pytest.raises(AppError):
            vault.get(db, me["workspace_id"], actor=me["user"]["id"])
        row.expires = original_expiry
        db.commit()
        with pytest.raises(AppError):
            vault.revoke(db, me["workspace_id"], actor="foreign-actor")
        row.expires = int(time.time()) - 1
        db.commit()
        assert vault.get(db, me["workspace_id"], actor=me["user"]["id"]) is None


def test_local_immutable_object_integrity_paths_quota_and_private_api(
    agent_client, monkeypatch, tmp_path
):
    client, engine = agent_client
    me = account(client)
    monkeypatch.setattr(settings(), "private_storage_dir", str(tmp_path / "private"))
    with Session(engine) as db:
        manifest = store(db, me["workspace_id"], "export", b"SYNTHETIC private artifact fixture")
        db.commit()
        assert read_manifest(manifest, me["workspace_id"]).startswith(b"SYNTHETIC")
        path = LocalStorage().path(manifest["storage_key"], "export")
        assert path.stat().st_mode & 0o077 == 0
        assert client.get(f"/api/v1/storage/artifacts/{manifest['object_id']}").status_code == 200
        with pytest.raises(AppError):
            LocalStorage().get("../../.env", "export")
        with pytest.raises(AppError):
            LocalStorage().put(manifest["storage_key"], "export", b"replacement")
        path.write_bytes(b"tampered")
        assert client.get(f"/api/v1/storage/artifacts/{manifest['object_id']}").status_code == 409
        with pytest.raises(AppError):
            read_manifest(manifest, "f" * 64)
        row = db.get(PrivateArtifact, manifest["object_id"])
        row.size = settings().storage_quota_mb * 1024 * 1024
        db.commit()
        with pytest.raises(AppError, match="quota"):
            store(db, me["workspace_id"], "export", b"excess")
    with TestClient(client.app) as stranger:
        account(stranger, "other@example.com")
        assert stranger.get(f"/api/v1/storage/artifacts/{manifest['object_id']}").status_code == 404


def test_s3_adapter_checksums_private_uploads_and_bounded_downloads(monkeypatch):
    monkeypatch.setattr(settings(), "s3_bucket", "synthetic-private-bucket")

    class FakeS3:
        def put_object(self, **kwargs):
            assert kwargs["ServerSideEncryption"] == "AES256" and kwargs["IfNoneMatch"] == "*"
            assert kwargs["ChecksumSHA256"]
            self.data = kwargs["Body"]

        def get_object(self, **kwargs):
            return {"ContentLength": len(self.data), "Body": BytesIO(self.data)}

        def delete_object(self, **kwargs):
            self.data = b""

    adapter = S3Storage(FakeS3())
    key = "a" * 64 + "/" + "b" * 36
    adapter.put(key, "export", b"synthetic")
    assert adapter.get(key, "export") == b"synthetic"
    with pytest.raises(AppError):
        adapter.get(key, "export", limit=2)
    adapter.delete(key, "export")


def test_workspace_deletion_removes_indexes_and_private_results_without_cross_user_effect(
    agent_client,
):
    client, engine = agent_client
    me = account(client)
    optimization = completed(client)
    document = uploaded(client)
    with TestClient(client.app) as stranger:
        account(stranger, "other@example.com")
        other_opt = completed(stranger)
        invalid = client.post(
            "/api/v1/storage/workspace-deletion",
            json={"confirmation": "delete", "acknowledge_backup_retention": True},
        )
        assert invalid.status_code == 422
        result = client.post(
            "/api/v1/storage/workspace-deletion",
            json={"confirmation": "DELETE THIS WORKSPACE", "acknowledge_backup_retention": True},
        )
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "completed"
        assert client.get(f"/api/v1/optimization/runs/{optimization['id']}").status_code == 404
        assert client.get(f"/api/v1/research/documents/{document['id']}").status_code == 404
        assert stranger.get(f"/api/v1/optimization/runs/{other_opt['id']}").status_code == 200
        assert client.get("/api/auth/me").json()["workspace_id"] != me["workspace_id"]
        with Session(engine) as db:
            assert db.get(OwnershipScope, me["workspace_id"]).lifecycle == "deleted"
            assert (
                db.scalar(
                    select(ResearchDocumentChunk.id).where(
                        ResearchDocumentChunk.owner == me["workspace_id"]
                    )
                )
                is None
            )
            assert not db.scalars(
                select(PrivateArtifact).where(
                    PrivateArtifact.owner == me["workspace_id"], PrivateArtifact.status != "deleted"
                )
            ).all()


def test_persistent_broker_authorization_survives_browser_session_rotation(
    agent_client, monkeypatch
):
    from app.auth.sessions import BrowserSession, broker_token, set_broker_token

    client, engine = agent_client
    me = account(client)
    keys(monkeypatch)
    with Session(engine) as db:
        original = BrowserSession(
            id=me["session_id"],
            expires=time.time() + 100,
            user_id=me["user"]["id"],
            owner_id=me["workspace_id"],
            database=db,
        )
        set_broker_token(original, "SYNTHETIC restart-persistent token")
    assert client.post("/api/auth/logout").status_code == 200
    from test_identity import PASSWORD

    signed_in = client.post(
        "/api/auth/login", json={"email": me["user"]["email"], "password": PASSWORD}
    )
    assert signed_in.status_code == 200, signed_in.text
    with Session(engine) as db:
        rotated = BrowserSession(
            id=signed_in.json()["session_id"],
            expires=time.time() + 100,
            user_id=me["user"]["id"],
            owner_id=me["workspace_id"],
            database=db,
        )
        assert rotated.id != original.id
        assert broker_token(rotated) == "SYNTHETIC restart-persistent token"
        set_broker_token(rotated, None)
        assert broker_token(rotated) is None
