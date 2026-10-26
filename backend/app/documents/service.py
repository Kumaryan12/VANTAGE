import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import BoundedSemaphore
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.agent.security import redact
from app.core.config import ROOT, settings
from app.core.errors import AppError
from app.database.models import (
    AgentEvidence,
    AgentInvestigation,
    ResearchDocument,
    ResearchDocumentChunk,
)

from .contracts import DocumentSummary
from .embeddings import configured_embedder

INDEX_VERSION = "page-bm25-rrf-cosine-1.0.0"
MAX_BYTES = 5 * 1024 * 1024
STOP = {
    "the",
    "and",
    "or",
    "a",
    "an",
    "of",
    "in",
    "to",
    "for",
    "this",
    "that",
    "my",
    "what",
    "which",
    "is",
    "are",
    "with",
    "from",
    "on",
    "our",
    "please",
    "summarize",
    "explain",
}


def tokens(text):
    return [w for w in re.findall(r"(?u)\b\w{2,}\b", text.casefold()) if w not in STOP]


def private_path(ident):
    root = Path(settings().document_storage_dir).resolve()
    path = (root / f"{ident}.pdf").resolve()
    if not path.is_relative_to(root):
        raise AppError("DOCUMENT_PATH", "Private document path is invalid.", 403)
    return path


def owned_document(db, ident, owner, allow_deleted=False):
    row = db.get(ResearchDocument, ident)
    if row is None or row.owner != owner or (row.status == "deleted" and not allow_deleted):
        raise AppError("DOCUMENT_NOT_FOUND", "Document not found in this session.", 404)
    if row.status in ("queued", "processing") and ident not in queue.futures:
        row.status = "interrupted"
        row.error = {
            "code": "DOCUMENT_INTERRUPTED",
            "message": "Parser process restarted; delete and upload again.",
        }
        db.commit()
    return row


def document_summary(row):
    return DocumentSummary(
        id=row.id,
        filename=row.filename,
        content_hash=row.content_hash,
        source=row.source,
        company=row.company,
        reporting_period=row.reporting_period,
        publication_date=row.publication_date,
        uploaded_at=row.uploaded_at,
        status=row.status,
        page_count=row.page_count,
        chunk_count=row.chunk_count,
        version=row.version,
        metadata=row.processing,
        error=row.error,
    )


def chunks_for_pages(pages, size, overlap):
    if not 400 <= size <= 3000 or not 0 <= overlap < min(500, size // 2):
        raise AppError(
            "CHUNK_CONFIGURATION",
            "Chunk size must be 400–3000 chars and overlap below half the size / 500 chars.",
        )
    chunks = []
    for page in pages:
        text = redact(page["text"])
        for start in range(0, len(text), size - overlap):
            part = text[start : start + size].strip()
            if len(part) < 20:
                continue
            section = next(
                (line.strip()[:150] for line in text.splitlines() if line.strip()),
                "Unspecified section",
            )
            chunks.append({"page": page["page"], "section": section, "text": part, "offset": start})
    if len(chunks) > 600:
        raise AppError(
            "DOCUMENT_CHUNK_LIMIT", "A document may contain at most 600 bounded text chunks."
        )
    return chunks


class DocumentQueue:
    def __init__(self):
        self.capacity = BoundedSemaphore(1)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vantage-pdf")
        self.futures = {}

    def submit(self, db, owner, filename, content_type, content, metadata):
        if not content or len(content) > MAX_BYTES:
            raise AppError("DOCUMENT_SIZE", "PDF must be nonempty and no larger than 5 MB.", 413)
        filename = Path(filename.replace("\\", "/")).name
        filename = re.sub(r"[\x00-\x1f]", "", filename)[:200]
        if (
            not filename.lower().endswith(".pdf")
            or not content.startswith(b"%PDF-")
            or content_type not in ("application/pdf", "application/octet-stream")
        ):
            raise AppError(
                "DOCUMENT_TYPE", "Only a permitted PDF file with a valid PDF header is accepted."
            )
        if metadata.semantic_index and (
            not metadata.external_data_consent or not settings().openai_api_key
        ):
            raise AppError(
                "EMBEDDING_CONSENT",
                "Semantic indexing requires a configured embedding provider and explicit permission to send extracted text.",
                422,
            )
        count = db.scalar(
            select(func.count())
            .select_from(ResearchDocument)
            .where(ResearchDocument.owner == owner, ResearchDocument.status != "deleted")
        )
        if count >= 20:
            raise AppError(
                "DOCUMENT_QUOTA",
                "At most 20 active documents are permitted per local session.",
                429,
            )
        content_hash = hashlib.sha256(content).hexdigest()
        duplicate = db.scalar(
            select(ResearchDocument).where(
                ResearchDocument.owner == owner,
                ResearchDocument.content_hash == content_hash,
                ResearchDocument.status != "deleted",
            )
        )
        if duplicate:
            raise AppError(
                "DOCUMENT_DUPLICATE", "This PDF is already present in the current session.", 409
            )
        if not self.capacity.acquire(blocking=False):
            raise AppError(
                "DOCUMENT_BUSY", "One PDF is being processed; retry after it finishes.", 503
            )
        try:
            ident = str(uuid4())
            path = private_path(ident)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(content)
            temporary.replace(path)
            config = settings()
            row = ResearchDocument(
                id=ident,
                owner=owner,
                filename=redact(filename),
                content_hash=content_hash,
                source=redact(metadata.source),
                company=redact(metadata.company) if metadata.company else None,
                reporting_period=redact(metadata.reporting_period)
                if metadata.reporting_period
                else None,
                publication_date=metadata.publication_date,
                uploaded_at=datetime.now(UTC),
                status="queued",
                page_count=0,
                chunk_count=0,
                version=f"pdf-text-1:{content_hash[:12]}",
                processing={
                    "index_version": INDEX_VERSION,
                    "chunk_chars": config.document_chunk_chars,
                    "chunk_overlap": config.document_chunk_overlap,
                    "publication_date_verification": "Uploader assertion only; not independently verified.",
                    "semantic_requested": metadata.semantic_index,
                    "external_data_consent": metadata.external_data_consent,
                    "embedding_status": "queued" if metadata.semantic_index else "not_requested",
                    "warnings": [
                        "Document text is untrusted historical evidence; no commands, links, or embedded instructions are executed.",
                        "Table structure and extracted numerical cells are unverified; no document arithmetic is inferred.",
                    ],
                },
                error=None,
            )
            db.add(row)
            db.commit()
            result = document_summary(row)
            self.futures[ident] = self.executor.submit(self.process, db.get_bind(), ident)
            for key in list(self.futures)[:-64]:
                if self.futures[key].done():
                    self.futures.pop(key, None)
            return result
        except Exception:
            self.capacity.release()
            raise

    def process(self, engine, ident):
        try:
            with Session(engine) as db:
                row = db.get(ResearchDocument, ident)
                if row.status == "deleted":
                    return
                row.status = "processing"
                db.commit()
                # No shell expansion. Child receives no application secrets or network credentials.
                result = subprocess.run(
                    [sys.executable, "-m", "app.documents.extract", str(private_path(ident))],
                    env={
                        "PATH": os.environ.get("PATH", ""),
                        "PYTHONPATH": str(ROOT / "backend"),
                        "PYTHONIOENCODING": "utf-8",
                    },
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                if result.returncode != 0 or len(result.stdout) > 4_000_000:
                    raise AppError(
                        "PDF_EXTRACTION",
                        "PDF could not be safely extracted; malformed, active, encrypted, oversized or image-only input may be unsupported.",
                    )
                parsed = json.loads(result.stdout)["result"]
                chunks = chunks_for_pages(
                    parsed["pages"], row.processing["chunk_chars"], row.processing["chunk_overlap"]
                )
                if not chunks:
                    raise AppError("PDF_TEXT_MISSING", "No usable text chunks were extracted.")
                vectors = [None] * len(chunks)
                processing = {
                    **row.processing,
                    "pdf_metadata": json.loads(redact(json.dumps(parsed["pdf_metadata"]))),
                    "table_structure": parsed["table_structure"],
                }
                if processing["semantic_requested"]:
                    embedding_usage = []
                    try:
                        deadline = time.monotonic() + 45
                        for start in range(0, len(chunks), 64):
                            if time.monotonic() >= deadline:
                                raise AppError(
                                    "EMBEDDING_TIMEOUT", "Indexing embedding budget expired.", 504
                                )
                            batch, usage = configured_embedder().embed(
                                [c["text"] for c in chunks[start : start + 64]],
                                timeout=min(12, deadline - time.monotonic()),
                            )
                            vectors[start : start + len(batch)] = batch
                            embedding_usage.append(usage)
                        processing.update(
                            embedding_status="ready",
                            embedding_usage=embedding_usage,
                            embedding_model=settings().embedding_model,
                        )
                    except AppError as error:
                        vectors = [None] * len(chunks)
                        processing.update(
                            embedding_status="failed",
                            embedding_error={"code": error.code, "message": error.message},
                            embedding_usage=embedding_usage,
                        )
                        processing["warnings"] = [
                            *processing["warnings"],
                            "Semantic index unavailable; keyword retrieval remains available.",
                        ]
                db.refresh(row)
                if row.status == "deleted":
                    return
                existing = db.scalar(
                    select(func.count())
                    .select_from(ResearchDocumentChunk)
                    .where(ResearchDocumentChunk.owner == row.owner)
                )
                if existing + len(chunks) > 2500:
                    raise AppError(
                        "INDEX_QUOTA",
                        "Session index exceeds 2,500 chunks; remove older documents first.",
                        429,
                    )
                for i, c in enumerate(chunks):
                    db.add(
                        ResearchDocumentChunk(
                            id=str(
                                uuid5(
                                    NAMESPACE_URL,
                                    f"{ident}:{row.version}:{c['page']}:{c['offset']}",
                                )
                            ),
                            owner=row.owner,
                            document_id=ident,
                            page=c["page"],
                            section=c["section"],
                            text=c["text"],
                            content_hash=hashlib.sha256(c["text"].encode()).hexdigest(),
                            token_counts=dict(Counter(tokens(c["text"]))),
                            embedding=vectors[i],
                            embedding_model=settings().embedding_model
                            if vectors[i] is not None
                            else None,
                        )
                    )
                row.page_count = len(parsed["pages"])
                row.chunk_count = len(chunks)
                row.status = "ready"
                row.processing = processing
                db.commit()
        except Exception as error:
            with Session(engine) as db:
                row = db.get(ResearchDocument, ident)
                if row is not None and row.status != "deleted":
                    row.status = "failed"
                    row.error = {
                        "code": error.code
                        if isinstance(error, AppError)
                        else "DOCUMENT_PROCESSING",
                        "message": error.message
                        if isinstance(error, AppError)
                        else "Document processing failed safely; no index published.",
                    }
                    db.commit()
        finally:
            self.capacity.release()


queue = DocumentQueue()


def resolve_passage(db, owner, passage):
    document = owned_document(db, passage["document_id"], owner)
    chunk = db.get(ResearchDocumentChunk, passage["chunk_id"])
    if (
        document.status != "ready"
        or chunk is None
        or chunk.owner != owner
        or chunk.document_id != document.id
    ):
        raise AppError("CITATION_SOURCE", "Cited page/chunk is unavailable in this session.", 409)
    if hashlib.sha256(chunk.text.encode()).hexdigest() != chunk.content_hash:
        raise AppError("CITATION_INTEGRITY", "Cited text failed its content hash.", 409)
    return {"text": chunk.text, "page": chunk.page, "content_hash": chunk.content_hash}


def delete_document(db, row):
    db.execute(
        delete(ResearchDocumentChunk).where(
            ResearchDocumentChunk.document_id == row.id, ResearchDocumentChunk.owner == row.owner
        )
    )
    private_path(row.id).unlink(missing_ok=True)
    row.status = "deleted"
    row.chunk_count = 0
    row.processing = {"deleted": True, "index_version": INDEX_VERSION}
    row.error = None
    # Purge copied passages/quotes from historical responses; retain only audit identifiers.
    for e in db.scalars(
        select(AgentEvidence)
        .join(AgentInvestigation, AgentEvidence.investigation_id == AgentInvestigation.id)
        .where(AgentInvestigation.owner == row.owner)
    ).all():
        passages = e.payload.get("data", {}).get("passages", [])
        if any(p.get("document_id") == row.id for p in passages):
            from app.risk.artifacts import digest

            payload = {k: v for k, v in e.payload.items() if k != "checksum"}
            payload["data"] = {
                **payload["data"],
                "passages": [p for p in passages if p.get("document_id") != row.id],
                "deleted_source_ids": [*payload["data"].get("deleted_source_ids", []), row.id],
            }
            payload["warnings"] = [
                *payload["warnings"],
                "A supporting document was deleted; its passages are no longer available.",
            ]
            e.payload = {**payload, "checksum": digest(payload)}
    for investigation in db.scalars(
        select(AgentInvestigation).where(
            AgentInvestigation.owner == row.owner, AgentInvestigation.answer.is_not(None)
        )
    ).all():
        answer = investigation.answer
        if any(c["document_id"] == row.id for c in answer.get("citations", [])):
            investigation.answer = {
                **answer,
                "citations": [
                    {**c, "quote": "", "unavailable": True} if c["document_id"] == row.id else c
                    for c in answer["citations"]
                ],
                "citation_verification": "not_applicable"
                if all(
                    c["document_id"] == row.id or c.get("unavailable") for c in answer["citations"]
                )
                else "passed",
                "warnings": [
                    *answer["warnings"],
                    "A cited document was deleted; affected citations are unavailable.",
                ],
            }
    db.commit()
    return document_summary(row)
