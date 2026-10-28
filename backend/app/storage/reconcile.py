"""Trusted local crash-file reconciliation, dry run first; never infer an account owner."""

import time
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.errors import AppError
from app.database.models import ForecastModel, PrivateArtifact, ResearchDocument
from app.storage.backends import KEY, local_root


def reconcile_files(db, *, apply=False, age_days=7):
    # Resolve every authorized manifest across scopes before walking. Old arbitrary names
    # are kept; only generated object/staging names are candidates after a full grace period.
    references = set()
    for row in db.scalars(
        select(PrivateArtifact).where(
            PrivateArtifact.backend == "local", PrivateArtifact.status != "deleted"
        )
    ):
        references.add(local_root(row.category) / row.storage_key)
    for model in db.scalars(select(ForecastModel)):
        for manifest in model.payload.get("artifact_files", []):
            if not manifest.get("storage_key"):
                references.add(Path(settings().model_artifact_dir).resolve() / manifest["path"])
    for doc in db.scalars(select(ResearchDocument).where(ResearchDocument.status != "deleted")):
        if not doc.processing.get("storage_object"):
            references.add(Path(settings().document_storage_dir).resolve() / f"{doc.id}.pdf")
    cutoff = time.time() - max(age_days, 7) * 86400
    candidates = []
    scanned = 0
    for root in {local_root("model"), local_root("document"), local_root("export")}:
        if not root.exists():
            continue
        for owner_dir in root.iterdir():
            if owner_dir.is_symlink() or not owner_dir.is_dir() or len(owner_dir.name) != 64:
                continue
            for path in owner_dir.iterdir():
                scanned += 1
                if scanned > 100_000:
                    raise AppError(
                        "RECONCILIATION_LIMIT",
                        "Inventory exceeds the bounded local reconciliation budget; no files were deleted.",
                        503,
                    )
                if (
                    path.is_symlink()
                    or not path.is_file()
                    or path in references
                    or path.stat().st_mtime >= cutoff
                ):
                    continue
                if not KEY.fullmatch(f"{owner_dir.name}/{path.name}") and not path.name.startswith(
                    ".staged-"
                ):
                    continue
                candidates.append(path)
    result = {
        "mode": "apply" if apply else "dry_run",
        "scanned": scanned,
        "unindexed_files_older_than_7_days": len(candidates),
        "bytes": sum(p.stat().st_size for p in candidates),
        "s3_reconciliation": "Requires external bucket inventory/version-retention validation; not performed.",
    }
    if apply:
        for path in candidates:
            path.unlink(missing_ok=True)
    return result
