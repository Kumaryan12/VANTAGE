import json

import pytest
from document_fixtures import DEBT, INJECTION, LIQUIDITY, pdf_bytes
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_agent_core import investigation

from app.agent.contracts import CitationChoice, WorkflowState
from app.agent.verification import default_selection, verify_and_compose
from app.core.config import settings
from app.core.errors import AppError
from app.database.models import ResearchDocumentChunk
from app.documents.service import MAX_BYTES, chunks_for_pages, queue, resolve_passage


def uploaded(client, pages=None, content=None, **metadata):
    response = client.post(
        "/api/v1/research/documents",
        files={
            "file": (
                "synthetic-disclosure.pdf",
                content or pdf_bytes(pages or [LIQUIDITY, DEBT]),
                "application/pdf",
            )
        },
        data={
            "source": "Permitted synthetic fixture",
            "company": "SYNTHETIC_CO",
            "reporting_period": "FY2026",
            "permitted": "true",
            **metadata,
        },
    )
    assert response.status_code == 202, response.text
    ident = response.json()["id"]
    queue.futures[ident].result(timeout=30)
    return client.get(f"/api/v1/research/documents/{ident}").json()


def test_pdf_pages_retrieval_citations_and_deletion(agent_client):
    client, engine = agent_client
    doc = uploaded(client)
    assert doc["status"] == "ready", doc
    assert doc["page_count"] == 2 and doc["chunk_count"] == 2
    assert doc["metadata"]["embedding_status"] == "not_requested"
    result = client.post(
        "/api/v1/research/search",
        json={"query": "Liquidity refinancing risk", "document_ids": [doc["id"]]},
    )
    assert result.status_code == 200, result.text
    passages = result.json()["passages"]
    assert passages and passages[0]["page"] == 1
    assert "Cash reserves" in passages[0]["text"]
    assert passages[0]["document_id"] == doc["id"]
    c = client.get(f"/api/v1/research/documents/{doc['id']}/chunks/{passages[0]['chunk_id']}")
    assert c.status_code == 200 and c.json()["content_hash"] == passages[0]["content_hash"]
    file = client.get(f"/api/v1/research/documents/{doc['id']}/file")
    assert file.status_code == 200 and file.content.startswith(b"%PDF-")
    assert "attachment" in file.headers["content-disposition"]
    answer = investigation(
        client,
        question="Summarize liquidity and debt risks in the uploaded report.",
        document_ids=[doc["id"]],
    )
    assert answer["status"] == "completed", answer
    assert answer["answer"]["citation_verification"] == "passed"
    assert answer["answer"]["citations"]
    with TestClient(client.app) as other:
        assert other.get(f"/api/v1/research/documents/{doc['id']}").status_code == 404
        assert other.get(f"/api/v1/research/documents/{doc['id']}/file").status_code == 404
        assert other.delete(f"/api/v1/research/documents/{doc['id']}").status_code == 404
        assert (
            other.post(
                "/api/v1/research/search", json={"query": "liquidity", "document_ids": [doc["id"]]}
            ).status_code
            == 404
        )
        assert (
            other.post("/api/v1/research/search", json={"query": "liquidity"}).json()["passages"]
            == []
        )
    assert client.delete(f"/api/v1/research/documents/{doc['id']}").status_code == 200
    assert client.get(f"/api/v1/research/documents/{doc['id']}").status_code == 404
    assert (
        client.post("/api/v1/research/search", json={"query": "liquidity"}).json()["passages"] == []
    )
    history = client.get(f"/api/v1/agent/investigations/{answer['id']}").json()
    assert all(c["unavailable"] and not c["quote"] for c in history["answer"]["citations"])
    with Session(engine) as db:
        assert db.scalar(select(ResearchDocumentChunk)) is None


def test_invalid_pdf_permissions_size_active_content_and_scan(agent_client):
    client, _ = agent_client
    assert (
        client.post(
            "/api/v1/research/documents",
            files={"file": ("bad.txt", b"%PDF-malformed", "text/plain")},
            data={"source": "Fixture", "permitted": "true"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/research/documents",
            files={"file": ("large.pdf", b"%PDF-" + b"x" * MAX_BYTES, "application/pdf")},
            data={"source": "Fixture", "permitted": "true"},
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/api/v1/research/documents",
            files={"file": ("valid.pdf", pdf_bytes([LIQUIDITY]), "application/pdf")},
            data={"source": "Fixture", "permitted": "false"},
        ).status_code
        == 422
    )
    assert uploaded(client, content=b"%PDF-malformed")["status"] == "failed"
    assert uploaded(client, content=pdf_bytes([LIQUIDITY], active=True))["status"] == "failed"
    assert uploaded(client, pages=[""])["status"] == "failed"


def test_malicious_document_is_evidence_not_instructions(agent_client):
    client, _ = agent_client
    doc = uploaded(client, pages=[INJECTION])
    assert doc["status"] == "ready"
    answer = investigation(
        client,
        question="Find the liquidity risks in this financial disclosure.",
        document_ids=[doc["id"]],
    )
    assert answer["status"] == "completed"
    trace = client.get(f"/api/v1/agent/investigations/{answer['id']}/tool-calls").json()
    assert [c["name"] for c in trace] == ["search_financial_documents"]
    assert "private-injected-token" not in json.dumps(answer)
    assert "[REDACTED]" in json.dumps(answer)
    assert not any(f["key"] == "champion" for f in answer["answer"]["claims"])


def test_chunks_and_fabricated_citations_fail(agent_client):
    client, engine = agent_client
    doc = uploaded(client)
    parts = chunks_for_pages([{"page": 3, "text": "Liquidity " * 150}], 400, 50)
    assert all(c["page"] == 3 and len(c["text"]) <= 400 for c in parts)
    with pytest.raises(AppError):
        chunks_for_pages([], 100, 90)
    answer = investigation(client, question="Find the liquidity risks in the annual report.")
    from app.agent.contracts import ToolEvidence

    evidence = [
        ToolEvidence.model_validate(e)
        for e in client.get(f"/api/v1/agent/investigations/{answer['id']}/evidence").json()
    ]
    state = WorkflowState(intent="documents", evidence=evidence)
    selection = default_selection(evidence)
    with Session(engine) as db:

        def resolver(p):
            return resolve_passage(db, doc_owner(db, doc["id"]), p)

        assert verify_and_compose(state, selection, "demo", resolver).citations
        selection.citations[0] = CitationChoice(
            evidence_id=evidence[0].id,
            chunk_id=selection.citations[0].chunk_id,
            quote="Invented debt disclosure is unsupported.",
        )
        with pytest.raises(AppError, match="citation"):
            verify_and_compose(state, selection, "demo", resolver)
    empty = client.post(
        "/api/v1/research/search", json={"query": "xylophone astronomy", "company": "MISSING"}
    ).json()
    assert not empty["passages"] and any("Insufficient" in w for w in empty["warnings"])


def doc_owner(db, ident):
    from app.database.models import ResearchDocument

    return db.get(ResearchDocument, ident).owner


def test_opt_in_semantic_index_and_hybrid_query_use_only_authorized_rows(agent_client, monkeypatch):
    client, _ = agent_client
    monkeypatch.setattr(settings(), "openai_api_key", "sk-embedding-test-private")
    sent = []

    class MockEmbedder:
        def embed(self, texts, timeout=12):
            sent.extend(texts)
            return [[1.0, 0.0] + [0.0] * 254 for _ in texts], {
                "model": settings().embedding_model,
                "input_tokens": len(texts) * 10,
                "estimated_cost_usd": None,
            }

    monkeypatch.setattr("app.documents.service.configured_embedder", MockEmbedder)
    monkeypatch.setattr("app.documents.retrieval.configured_embedder", MockEmbedder)
    doc = uploaded(client, pages=[LIQUIDITY], semantic_index="true", external_data_consent="true")
    assert doc["metadata"]["embedding_status"] == "ready", doc
    result = client.post(
        "/api/v1/research/search",
        json={"query": "Funding squeeze", "semantic": True, "external_data_consent": True},
    ).json()
    assert result["passages"][0]["document_id"] == doc["id"]
    assert result["passages"][0]["keyword_score"] == 0
    assert result["passages"][0]["semantic_score"] == pytest.approx(1)
    assert result["method"].startswith("hybrid")
    before = len(sent)
    with TestClient(client.app) as stranger:
        other = stranger.post(
            "/api/v1/research/search",
            json={"query": "Funding squeeze", "semantic": True, "external_data_consent": True},
        ).json()
        assert not other["passages"] and len(sent) == before
