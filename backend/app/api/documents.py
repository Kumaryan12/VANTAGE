import hashlib
from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import select

from app.api.routes import DB, Browser, owner
from app.core.errors import AppError
from app.database.models import ResearchDocument, ResearchDocumentChunk
from app.documents.contracts import (
    DocumentMetadata,
    DocumentSummary,
    Passage,
    SearchRequest,
    SearchResult,
)
from app.documents.retrieval import search
from app.documents.service import (
    MAX_BYTES,
    delete_document,
    document_summary,
    owned_document,
    private_path,
    queue,
)

router = APIRouter(prefix="/api/v1/research", tags=["Financial documents"])


@router.post("/documents", response_model=DocumentSummary, status_code=202)
async def upload(
    session: Browser,
    db: DB,
    file: Annotated[UploadFile, File()],
    source: Annotated[str, Form(min_length=3, max_length=200)],
    permitted: Annotated[bool, Form()],
    company: Annotated[str | None, Form(max_length=80)] = None,
    reporting_period: Annotated[str | None, Form(max_length=50)] = None,
    publication_date: Annotated[date | None, Form()] = None,
    semantic_index: Annotated[bool, Form()] = False,
    external_data_consent: Annotated[bool, Form()] = False,
):
    content = await file.read(MAX_BYTES + 1)
    await file.close()
    if not permitted:
        raise AppError("DOCUMENT_PERMISSION", "Confirm permission to process this document.", 422)
    metadata = DocumentMetadata(
        source=source,
        company=company,
        reporting_period=reporting_period,
        publication_date=publication_date,
        permitted=True,
        semantic_index=semantic_index,
        external_data_consent=external_data_consent,
    )
    return queue.submit(
        db, owner(session), file.filename or "", file.content_type, content, metadata
    )


@router.get("/documents", response_model=list[DocumentSummary])
def documents(
    session: Browser,
    db: DB,
    company: str | None = Query(None, max_length=80),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    query = select(ResearchDocument).where(
        ResearchDocument.owner == owner(session), ResearchDocument.status != "deleted"
    )
    if company:
        query = query.where(ResearchDocument.company == company)
    rows = db.scalars(
        query.order_by(ResearchDocument.uploaded_at.desc()).limit(limit).offset(offset)
    ).all()
    return [document_summary(owned_document(db, r.id, owner(session))) for r in rows]


@router.get("/documents/{ident}", response_model=DocumentSummary)
def document(ident: str, session: Browser, db: DB):
    return document_summary(owned_document(db, ident, owner(session)))


@router.delete("/documents/{ident}", response_model=DocumentSummary)
def remove(ident: str, session: Browser, db: DB):
    return delete_document(db, owned_document(db, ident, owner(session), allow_deleted=True))


@router.get("/documents/{ident}/file")
def original(ident: str, session: Browser, db: DB):
    row = owned_document(db, ident, owner(session))
    if row.status != "ready":
        raise AppError(
            "DOCUMENT_NOT_READY", "Original PDF remains quarantined until extraction succeeds.", 409
        )
    if row.processing.get("storage_object"):
        from app.storage.service import read_manifest

        content = read_manifest(row.processing["storage_object"], row.owner)
        if hashlib.sha256(content).hexdigest() != row.content_hash:
            raise AppError("DOCUMENT_INTEGRITY", "Original PDF failed its content hash.", 409)
        return Response(
            content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.filename)}",
                "Content-Security-Policy": "sandbox; default-src 'none'",
                "X-Content-Type-Options": "nosniff",
            },
        )
    path = private_path(row.id)
    if not path.is_file():
        raise AppError("DOCUMENT_FILE", "Original document is unavailable.", 409)
    if hashlib.sha256(path.read_bytes()).hexdigest() != row.content_hash:
        raise AppError("DOCUMENT_INTEGRITY", "Original PDF failed its content hash.", 409)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=row.filename,
        headers={
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/documents/{ident}/chunks/{chunk_id}", response_model=Passage)
def chunk(ident: str, chunk_id: str, session: Browser, db: DB):
    row = owned_document(db, ident, owner(session))
    c = db.get(ResearchDocumentChunk, chunk_id)
    if c is None or c.document_id != row.id or c.owner != owner(session):
        raise AppError("CHUNK_NOT_FOUND", "Evidence chunk not found in this session.", 404)
    return Passage(
        chunk_id=c.id,
        document_id=row.id,
        document_name=row.filename,
        company=row.company,
        page=c.page,
        section=c.section,
        text=c.text,
        content_hash=c.content_hash,
        source=row.source,
        reporting_period=row.reporting_period,
        keyword_score=0,
        semantic_score=None,
        score=0,
        rank=1,
        table_structure="Unverified text extraction",
    )


@router.post("/search", response_model=SearchResult)
def retrieval(body: SearchRequest, session: Browser, db: DB):
    return search(db, owner(session), body)
