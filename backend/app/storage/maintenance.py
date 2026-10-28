"""Bounded, dry-run-first retention. No inference of ownership or automatic legacy erasure."""

import argparse
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import AuthSession, PrivateArtifact, ProviderCredential, RecoveryToken
from app.storage.service import delete


def sweep(db, *, apply=False, now=None):
    now = now or datetime.now(UTC)
    epoch = int(now.timestamp())
    # Successful model/source artifacts have no automatic expiry: reproducibility needs them.
    expired = db.scalars(
        select(PrivateArtifact)
        .where(
            PrivateArtifact.status != "deleted",
            PrivateArtifact.expires_at.is_not(None),
            PrivateArtifact.expires_at < now,
            PrivateArtifact.category.in_(["export", "report"]),
        )
        .limit(1000)
    ).all()
    credentials = db.scalars(
        select(ProviderCredential)
        .where(ProviderCredential.expires < epoch, ProviderCredential.revoked == 0)
        .limit(1000)
    ).all()
    sessions = db.scalars(
        select(AuthSession).where(AuthSession.expires < epoch - 30 * 86400).limit(1000)
    ).all()
    recovery = db.scalars(
        select(RecoveryToken).where(RecoveryToken.expires < epoch - 86400).limit(1000)
    ).all()
    result = {
        "mode": "apply" if apply else "dry_run",
        "expired_exports_reports": len(expired),
        "expired_credentials": len(credentials),
        "expired_sessions_over_30_days": len(sessions),
        "expired_recovery_over_1_day": len(recovery),
        "batch_limit_each": 1000,
        "automatic_orphan_financial_deletion": False,
    }
    if apply:
        from app.auth.identity import security_event

        for row in expired:
            delete(db, row)
        for row in credentials:
            row.ciphertext = ""
            row.revoked = 1
            security_event(db, "expired_credential_erased", target=row.id)
        for row in sessions + recovery:
            db.delete(row)
        security_event(db, "retention_batch", **result)
        db.commit()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation", choices=["retention", "rotate-credential-keys", "reconcile-files"]
    )
    parser.add_argument(
        "--apply", action="store_true", help="Explicitly execute; default is dry run"
    )
    args = parser.parse_args()
    from app.database.session import engine

    with Session(engine) as db:
        if args.operation == "retention":
            result = sweep(db, apply=args.apply)
        elif args.operation == "reconcile-files":
            from app.storage.reconcile import reconcile_files

            result = reconcile_files(db, apply=args.apply)
        elif args.apply:
            from app.security.vault import rotate

            result = {"rotated": rotate(db)}
        else:
            result = {
                "mode": "dry_run",
                "rotation": "Load old and new external keys; --apply re-encrypts authenticated credentials transactionally.",
            }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
