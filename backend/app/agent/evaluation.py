"""Executed, isolated synthetic workflow/probe evaluation, never a live-LLM accuracy claim."""

import hashlib
import json
import math
import statistics
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import BoundedSemaphore
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brokers.demo import DemoBroker
from app.core.config import ROOT
from app.core.errors import AppError
from app.database.models import (
    AgentEvaluation,
    AgentEvidence,
    AgentInvestigation,
    AgentStep,
    AgentToolCall,
)
from app.documents.contracts import DocumentMetadata
from app.documents.service import queue as document_queue
from app.ml.artifacts import runtime_versions
from app.ml.contracts import ResearchRequest
from app.ml.service import ResearchQueue

from .contracts import CitationChoice, FinalSelection, InvestigationRequest, WorkflowState
from .fixtures import CONFLICT, DEBT, INJECTION, LIQUIDITY, pdf_bytes
from .security import redact
from .service import InvestigationQueue, owned
from .tools import ToolContext, fact, invoke, sealed
from .verification import default_selection, verify_and_compose

GOLDEN_PATH = ROOT / "data/evaluations/agent_golden_v1.json"


def owned_evaluation(db, ident, owner):
    row = db.get(AgentEvaluation, ident)
    if row is None or row.owner != owner:
        raise AppError("EVALUATION_NOT_FOUND", "Evaluation not found in this session.", 404)
    if row.status in ("queued", "running") and ident not in queue.futures:
        row.status = "interrupted"
        row.payload = {
            **row.payload,
            "error": "Evaluation process restarted; no completed score is claimed.",
        }
        db.commit()
    return row


def fixture_document(db, owner, texts, company):
    metadata = DocumentMetadata(
        source="Permitted SYNTHETIC evaluation fixture",
        company=company,
        reporting_period="Synthetic FY2026",
        permitted=True,
    )
    doc = document_queue.submit(
        db, owner, "SYNTHETIC-evaluation.pdf", "application/pdf", pdf_bytes(texts), metadata
    )
    document_queue.futures[doc.id].result(timeout=30)
    from app.documents.service import owned_document

    if owned_document(db, doc.id, owner).status != "ready":
        raise AppError("EVALUATION_FIXTURE", "Synthetic PDF fixture did not index.")
    return doc.id


def probe(case, db, fixture_owner, experiment_id, document_id, baseline_investigation):
    which = case["probe"]
    context = ToolContext(
        db,
        fixture_owner,
        InvestigationRequest(question=case["question"]),
        DemoBroker().portfolio(),
        "synthetic-evaluation",
    )
    if which in ("shell", "sql", "governance"):
        try:
            invoke(
                context,
                {
                    "shell": "execute_shell",
                    "sql": "execute_sql",
                    "governance": "set_model_governance",
                }[which],
                {},
            )
        except AppError as error:
            return error.status == 403
        return False
    if which in ("foreign_document", "foreign_experiment", "foreign_investigation"):
        context.owner = "f" * 64
        try:
            if which == "foreign_document":
                from app.documents.service import owned_document

                owned_document(db, document_id, context.owner)
            elif which == "foreign_experiment":
                from app.ml.service import owned_experiment

                owned_experiment(db, experiment_id, context.owner)
            else:
                owned(db, baseline_investigation, context.owner)
        except AppError as error:
            return error.status == 404
        return False
    if which == "redaction":
        return "fixture-super-secret" not in redact(
            "access_token=fixture-super-secret"
        ) and "sk-abcdef0123456789" not in redact("sk-abcdef0123456789")
    if which == "freeform_claim":
        try:
            FinalSelection.model_validate(
                {
                    "claims": [],
                    "citations": [],
                    "commentary": "This caused the market crash and guarantees returns.",
                }
            )
        except ValidationError:
            return True
        return False
    evidence = sealed(
        "fixture",
        "snapshot",
        "synthetic-snapshot",
        True,
        "2026-10-23",
        {},
        [fact("value", "Portfolio value", 2719772.8956382833, "INR", "2026-10-23")],
        [],
    )
    state = WorkflowState(intent="portfolio", evidence=[evidence])
    selection = default_selection([evidence])
    changes = {
        "wrong_value": {"value": 1e9},
        "wrong_unit": {"unit": "USD"},
        "wrong_date": {"as_of": "2020-01-01"},
        "wrong_source": {"evidence_id": "nonexistent"},
    }
    if which in changes:
        selection.claims[0] = selection.claims[0].model_copy(update=changes[which])
    elif which == "evidence_tamper":
        evidence.facts[0].value = 1e9
    elif which in ("fake_citation", "fake_quote"):
        selection.citations = [
            CitationChoice(
                evidence_id=evidence.id,
                chunk_id="fake-page-source",
                quote="An invented financial statement is not evidence.",
            )
        ]
    try:
        verify_and_compose(state, selection, "demo")
    except AppError:
        return True
    return False


def evaluate(engine, report_id):
    started = time.monotonic()
    golden = json.loads(GOLDEN_PATH.read_text())
    cases = []
    fixture_owner = hashlib.sha256(f"isolated-golden-fixture:{report_id}".encode()).hexdigest()
    investigator = InvestigationQueue()
    research = ResearchQueue()
    try:
        with Session(engine) as db:
            row = db.get(AgentEvaluation, report_id)
            row.status = "running"
            db.commit()
            portfolio = DemoBroker().portfolio()
            job = research.submit(
                db, portfolio, fixture_owner, ResearchRequest(max_trees=40, search_candidates=2)
            )
            research.futures[job.id].result(timeout=60)
            from app.database.models import ResearchExperiment

            db.expire_all()
            if db.get(ResearchExperiment, job.id).status != "completed":
                raise AppError("EVALUATION_FIXTURE", "Synthetic research fixture failed.")
            base = fixture_document(db, fixture_owner, [LIQUIDITY, DEBT], "SYNTHETIC_CO")
            conflict = fixture_document(db, fixture_owner, [CONFLICT], "SYNTHETIC_CO")
            malicious = fixture_document(db, fixture_owner, [INJECTION], "MALICIOUS_SYNTHETIC_CO")
            baseline = None
            for case in golden["cases"]:
                if time.monotonic() - started > 150:
                    raise AppError(
                        "EVALUATION_TIMEOUT", "Golden evaluation exceeded its suite deadline.", 504
                    )
                case_started = time.monotonic()
                checks = {}
                actual = {}
                failure = None
                try:
                    if case["probe"]:
                        checks = {
                            "task": probe(case, db, fixture_owner, job.id, base, baseline),
                            "safety": True,
                        }
                        checks["safety"] = checks["task"]
                        actual = {
                            "mode": "deterministic backend security/verifier probe",
                            "tools": [],
                            "trace": [],
                        }
                    else:
                        setup = case["setup"]
                        request = InvestigationRequest(
                            question=case["question"],
                            experiment_id="missing-model" if setup == "missing_model" else job.id,
                            document_ids=["missing-document"]
                            if setup == "missing_document"
                            else [malicious]
                            if setup == "malicious"
                            else [base, conflict]
                            if setup == "conflict"
                            else [base],
                            company="ABSENT_COMPANY" if setup == "no_documents" else None,
                            run_ids=["missing-run-a", "missing-run-b"]
                            if setup == "missing_runs"
                            else [],
                        )
                        submitted = investigator.submit(
                            db, portfolio, fixture_owner, request, internal_evaluation=True
                        )
                        investigator.futures[submitted.id].result(timeout=65)
                        db.expire_all()
                        investigation = db.get(AgentInvestigation, submitted.id)
                        if baseline is None:
                            baseline = submitted.id
                        answer = investigation.answer or {}
                        calls = [
                            c.payload
                            for c in db.scalars(
                                select(AgentToolCall)
                                .where(AgentToolCall.investigation_id == submitted.id)
                                .order_by(
                                    AgentToolCall.sequence.asc().nulls_last(), AgentToolCall.id
                                )
                            ).all()
                        ]
                        evidence = [
                            e.payload
                            for e in db.scalars(
                                select(AgentEvidence).where(
                                    AgentEvidence.investigation_id == submitted.id
                                )
                            ).all()
                        ]
                        trace = [
                            s.payload
                            for s in db.scalars(
                                select(AgentStep)
                                .where(AgentStep.investigation_id == submitted.id)
                                .order_by(AgentStep.sequence)
                            ).all()
                        ]
                        facts = {f["key"]: f for f in answer.get("claims", [])}
                        checks["status"] = investigation.status == case["expected_status"]
                        checks["tools"] = [c["name"] for c in calls] == case["expected_tools"]
                        if case["reference_numeric"]:
                            checks["numerical"] = all(
                                key in facts
                                and isinstance(facts[key]["value"], (int, float))
                                and math.isclose(
                                    facts[key]["value"], expected, rel_tol=1e-9, abs_tol=1e-9
                                )
                                for key, expected in case["reference_numeric"].items()
                            )
                        if case["citation_required"]:
                            from app.documents.service import resolve_passage

                            citations = answer.get("citations", [])
                            checks["retrieval"] = bool(citations)
                            checks["citations"] = bool(citations) and all(
                                c["quote"] in resolve_passage(db, fixture_owner, c)["text"]
                                and 1 <= c["page"] <= 2
                                for c in citations
                            )
                            if setup == "conflict":
                                checks["conflicting_sources"] = (
                                    len({c["document_id"] for c in citations}) == 2
                                )
                        if case["required_warning_terms"]:
                            warnings = " ".join(answer.get("warnings", [])).casefold()
                            checks["limitations"] = all(
                                term.casefold() in warnings
                                for term in case["required_warning_terms"]
                            )
                        checks["bounded"] = len(calls) <= 8 and len(trace) <= 24
                        checks["grounded"] = (
                            investigation.verification.get("unsupported_values_published") == 0
                        )
                        if setup == "malicious":
                            checks["safety"] = "private-injected-token" not in json.dumps(
                                answer
                            ) and [c["name"] for c in calls] == ["search_financial_documents"]
                        checks["task"] = all(checks.values())
                        actual = {
                            "mode": "deterministic workflow; no live LLM",
                            "investigation_id": submitted.id,
                            "status": investigation.status,
                            "tools": [c["name"] for c in calls],
                            "trace": trace,
                            "error": investigation.error,
                            "claims": answer.get("claims", []),
                            "citations": answer.get("citations", []),
                            "warnings": answer.get("warnings", []),
                            "evidence_references": [
                                {
                                    "id": e["id"],
                                    "source_id": e["source_id"],
                                    "checksum": e["checksum"],
                                }
                                for e in evidence
                            ],
                        }
                    if not all(checks.values()):
                        failure = "; ".join(key for key, passed in checks.items() if not passed)
                except Exception as error:
                    checks["task"] = False
                    failure = (
                        error.code + ": " + error.message
                        if isinstance(error, AppError)
                        else type(error).__name__
                    )
                cases.append(
                    {
                        **case,
                        "checks": checks,
                        "passed": all(checks.values()),
                        "failure": failure,
                        "elapsed_seconds": time.monotonic() - case_started,
                        "actual": actual,
                    }
                )
                row.payload = {**row.payload, "completed_cases": len(cases), "cases": cases}
                db.commit()
            metrics = {}
            for metric, key in [
                ("task_success", "task"),
                ("tool_correctness", "tools"),
                ("numerical_accuracy", "numerical"),
                ("citation_correctness", "citations"),
                ("retrieval_quality", "retrieval"),
                ("groundedness", "grounded"),
                ("safety", "safety"),
            ]:
                values = [case["checks"][key] for case in cases if key in case["checks"]]
                metrics[metric] = {
                    "passed": sum(values),
                    "total": len(values),
                    "rate": sum(values) / len(values) if values else None,
                }
            accepted = all(
                metrics[key]["rate"] is not None and metrics[key]["rate"] >= value
                for key, value in golden["thresholds"].items()
                if key != "unsupported_values_published"
            )
            latencies = [c["elapsed_seconds"] for c in cases]
            row.status = "completed"
            row.payload = {
                **row.payload,
                "version": golden["version"],
                "dataset_sha256": hashlib.sha256(GOLDEN_PATH.read_bytes()).hexdigest(),
                "runtime": runtime_versions(),
                "fixture_experiment_id": job.id,
                "fixture_owner_scope": "isolated synthetic evaluation workspace; no user broker records",
                "metrics": metrics,
                "acceptance_passed": accepted,
                "thresholds": golden["thresholds"],
                "failures": [
                    {"id": c["id"], "category": c["category"], "failure": c["failure"]}
                    for c in cases
                    if not c["passed"]
                ],
                "categories": dict(Counter(c["category"] for c in cases)),
                "efficiency": {
                    "elapsed_seconds": time.monotonic() - started,
                    "median_case_seconds": statistics.median(latencies),
                    "max_case_seconds": max(latencies),
                    "tool_calls": sum(len(c["actual"].get("tools", [])) for c in cases),
                    "input_tokens": None,
                    "output_tokens": None,
                    "estimated_cost_usd": None,
                },
                "limitations": [
                    "Executed deterministic fixture workflows and security/verifier probes; not a live-LLM benchmark or real-world financial validity assessment.",
                    "Provider transports are separately mock-tested; paid opt-in live-provider quality is unmeasured.",
                    "Evaluation cases are curated development/regression examples, not an independent unbiased natural-language test set.",
                ],
            }
            db.commit()
    except Exception as error:
        with Session(engine) as db:
            row = db.get(AgentEvaluation, report_id)
            row.status = "failed"
            row.payload = {
                **row.payload,
                "cases": cases,
                "error": error.message
                if isinstance(error, AppError)
                else "Evaluation infrastructure failed; no completed score claimed.",
            }
            db.commit()
    finally:
        investigator.executor.shutdown(wait=True)
        investigator.tool_executor.shutdown(wait=True)
        research.executor.shutdown(wait=True)


class EvaluationQueue:
    def __init__(self):
        self.capacity = BoundedSemaphore(1)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vantage-golden")
        self.futures = {}

    def submit(self, db, owner):
        from app.auth.identity import ensure_scope

        ensure_scope(db, owner)
        previous = db.scalars(
            select(AgentEvaluation.created_at)
            .where(AgentEvaluation.owner == owner)
            .order_by(AgentEvaluation.created_at.desc())
            .limit(2)
        ).all()
        if (
            len(previous) >= 2
            and (datetime.now(UTC) - previous[-1].replace(tzinfo=UTC)).total_seconds() < 3600
        ):
            raise AppError(
                "EVALUATION_RATE_LIMIT",
                "At most two golden evaluations per hour are permitted per local session.",
                429,
            )
        if not self.capacity.acquire(blocking=False):
            raise AppError("EVALUATION_BUSY", "A golden evaluation is already active.", 503)
        try:
            row = AgentEvaluation(
                id=str(uuid4()),
                owner=owner,
                status="queued",
                payload={
                    "suite": "agent-golden-1.0.0",
                    "completed_cases": 0,
                    "total_cases": len(json.loads(GOLDEN_PATH.read_text())["cases"]),
                    "mode": "deterministic synthetic workflow/probe evaluation",
                    "cases": [],
                },
                created_at=datetime.now(UTC),
            )
            db.add(row)
            db.commit()
            self.futures[row.id] = self.executor.submit(evaluate, db.get_bind(), row.id)
            self.futures[row.id].add_done_callback(lambda _: self.capacity.release())
            return {
                "id": row.id,
                "status": "queued",
                "created_at": row.created_at.isoformat(),
                "payload": row.payload,
            }
        except Exception:
            self.capacity.release()
            raise


queue = EvaluationQueue()
