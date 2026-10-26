from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.portfolios.schemas import StrictModel


class DocumentMetadata(StrictModel):
    source: str = Field(min_length=3, max_length=200)
    company: str | None = Field(None, max_length=80)
    reporting_period: str | None = Field(None, max_length=50)
    publication_date: date | None = None
    permitted: Literal[True]
    semantic_index: bool = False
    external_data_consent: bool = False


class DocumentSummary(StrictModel):
    id: str
    filename: str
    content_hash: str
    source: str
    company: str | None
    reporting_period: str | None
    publication_date: date | None
    uploaded_at: datetime
    status: Literal["queued", "processing", "ready", "failed", "deleted", "interrupted"]
    page_count: int
    chunk_count: int
    version: str
    metadata: dict
    error: dict | None


class Passage(StrictModel):
    chunk_id: str
    document_id: str
    document_name: str
    company: str | None
    page: int
    section: str
    text: str
    content_hash: str
    source: str
    reporting_period: str | None
    keyword_score: float
    semantic_score: float | None
    score: float
    rank: int
    table_structure: str


class SearchRequest(StrictModel):
    query: str = Field(min_length=3, max_length=500)
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    company: str | None = Field(None, max_length=80)
    limit: int = Field(5, ge=1, le=8, strict=True)
    semantic: bool = False
    external_data_consent: bool = False


class SearchResult(StrictModel):
    passages: list[Passage]
    method: str
    warnings: list[str]
    index_version: str
    embedding_usage: dict | None
