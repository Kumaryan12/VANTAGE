"""BM25 plus optional exact cosine flat index; authorization precedes all scoring."""

import math
from collections import Counter

import numpy as np
from sqlalchemy import func, select

from app.core.config import settings
from app.core.errors import AppError
from app.database.models import ResearchDocument, ResearchDocumentChunk

from .contracts import Passage, SearchResult
from .embeddings import configured_embedder
from .service import INDEX_VERSION, owned_document, tokens


def search(db, owner, request):
    for ident in request.document_ids:
        owned_document(db, ident, owner)
    query = (
        select(ResearchDocumentChunk, ResearchDocument)
        .join(ResearchDocument, ResearchDocumentChunk.document_id == ResearchDocument.id)
        .where(
            ResearchDocumentChunk.owner == owner,
            ResearchDocument.owner == owner,
            ResearchDocument.status == "ready",
        )
    )
    if request.document_ids:
        query = query.where(ResearchDocument.id.in_(request.document_ids))
    if request.company:
        query = query.where(func.lower(ResearchDocument.company) == request.company.casefold())
    rows = db.execute(
        query.order_by(
            ResearchDocument.id, ResearchDocumentChunk.page, ResearchDocumentChunk.id
        ).limit(2501)
    ).all()
    if len(rows) > 2500:
        raise AppError(
            "INDEX_QUOTA", "Narrow the query to a document/company before searching this index."
        )
    terms = Counter(tokens(request.query))
    warnings = [
        "Disclosures are historical source evidence, not real-time market data or independently verified financial statements.",
        "Extracted table structure is uncertain; no missing cells or arithmetic are inferred.",
    ]
    if not rows or not terms:
        return SearchResult(
            passages=[],
            method="keyword BM25",
            warnings=[
                *warnings,
                "Insufficient authorized document evidence for this query/filter.",
            ],
            index_version=INDEX_VERSION,
            embedding_usage=None,
        )
    lengths = np.array([sum(c.token_counts.values()) for c, _ in rows], dtype=float)
    average = max(float(lengths.mean()), 1)
    scores = np.zeros(len(rows))
    for word, query_frequency in terms.items():
        frequency = np.array([c.token_counts.get(word, 0) for c, _ in rows], dtype=float)
        n = int(np.sum(frequency > 0))
        idf = math.log(1 + (len(rows) - n + 0.5) / (n + 0.5))
        scores += (
            idf
            * (frequency * 2.5)
            / (frequency + 1.5 * (0.25 + 0.75 * lengths / average))
            * min(query_frequency, 2)
        )
    keyword = sorted(
        [i for i, s in enumerate(scores) if s > 0], key=lambda i: (-scores[i], rows[i][0].id)
    )
    fused = {i: 1 / (60 + rank) for rank, i in enumerate(keyword, 1)}
    semantic_scores = {}
    usage = None
    method = "keyword BM25"
    if request.semantic:
        if not request.external_data_consent:
            raise AppError(
                "EMBEDDING_CONSENT",
                "Semantic queries require explicit external-processing consent.",
            )
        candidates = [
            i
            for i, (c, _) in enumerate(rows)
            if c.embedding is not None and c.embedding_model == settings().embedding_model
        ]
        if candidates:
            try:
                from app.jobs.quotas import reserve

                reserve(db.get_bind(), owner, "embeddings", token_reservation=1_000_000)
                vectors, usage = configured_embedder().embed([request.query])
                vector = np.asarray(vectors[0], dtype=float)
                matrix = np.asarray([rows[i][0].embedding for i in candidates], dtype=float)
                if (
                    vector.ndim != 1
                    or matrix.ndim != 2
                    or matrix.shape[1] != len(vector)
                    or not np.isfinite(matrix).all()
                ):
                    raise AppError(
                        "VECTOR_INDEX",
                        "Stored vector dimensions/data are incompatible; reindex the source.",
                        409,
                    )
                norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(vector)
                values = np.divide(
                    matrix @ vector, norms, out=np.zeros(len(matrix)), where=norms > 0
                )
                semantic_scores = {i: float(values[j]) for j, i in enumerate(candidates)}
                ranked = sorted(
                    [i for i in candidates if semantic_scores[i] >= 0.2],
                    key=lambda i: (-semantic_scores[i], rows[i][0].id),
                )
                for rank, i in enumerate(ranked, 1):
                    fused[i] = fused.get(i, 0) + 1 / (60 + rank)
                method = "hybrid BM25 + exact cosine / reciprocal rank fusion"
            except AppError as error:
                warnings.append(
                    f"Semantic retrieval unavailable ({error.code}); keyword results only."
                )
        else:
            warnings.append(
                "No compatible semantic index is available for the authorized documents; keyword results only."
            )
    ordered = sorted(fused, key=lambda i: (-fused[i], rows[i][0].id))
    result = []
    seen = []
    for i in ordered:
        chunk, document = rows[i]
        content_terms = set(chunk.token_counts)
        if any(
            doc_id == document.id
            and page == chunk.page
            and len(content_terms.intersection(previous))
            / max(len(content_terms.union(previous)), 1)
            > 0.85
            for doc_id, page, previous in seen
        ):
            continue
        seen.append((document.id, chunk.page, content_terms))
        result.append(
            Passage(
                chunk_id=chunk.id,
                document_id=document.id,
                document_name=document.filename,
                company=document.company,
                page=chunk.page,
                section=chunk.section,
                text=chunk.text,
                content_hash=chunk.content_hash,
                source=document.source,
                reporting_period=document.reporting_period,
                keyword_score=float(scores[i]),
                semantic_score=semantic_scores.get(i),
                score=float(fused[i]),
                rank=len(result) + 1,
                table_structure="Unverified text; do not infer reliable cells or calculations.",
            )
        )
        if len(result) >= request.limit:
            break
    if not result:
        warnings.append("Insufficient authorized document evidence for this query/filter.")
    return SearchResult(
        passages=result,
        method=method,
        warnings=warnings,
        index_version=INDEX_VERSION,
        embedding_usage=usage,
    )
