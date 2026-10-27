import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import UTC, datetime
from threading import BoundedSemaphore, Event
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.database.models import AgentEvidence, AgentInvestigation, AgentStep, AgentToolCall
from app.portfolios.schemas import Portfolio
from app.risk.artifacts import persist_inputs

from .contracts import (
    WORKFLOW_VERSION,
    Activity,
    InvestigationDetail,
    InvestigationRequest,
    InvestigationSummary,
    WorkflowState,
)
from .provider import configured_provider
from .security import prohibited, redact
from .tools import REGISTRY, ToolContext, invoke
from .verification import default_selection, verify_and_compose

RUNNER_ID = str(uuid4())
logger = logging.getLogger("vantage.agent")


def classify(question):
    q = question.lower()
    if prohibited(q) or any(
        s in q for s in ("guaranteed profit", "guarantee returns", "should i buy", "should i sell")
    ):
        return "unsupported"
    models = any(
        s in q
        for s in (
            "model",
            "forecast",
            "qlike",
            "lightgbm",
            "garch",
            "ewma",
            "99%",
            "shap",
            "regime",
        )
    )
    docs = any(
        s in q
        for s in (
            "document",
            "report",
            "disclosure",
            "filing",
            "liquidity",
            "debt",
            "covenant",
            "presentation",
        )
    )
    portfolio = any(
        s in q for s in ("portfolio", "holdings", "allocation", "exposure", "concentrat")
    )
    stress = bool(
        re.search(r"\b(?:falls?|falling|drops?|dropping|shocks?|scenarios?|declines?)\b", q)
    )
    risk = any(
        s in q for s in ("var", "expected shortfall", "contribut", "volatility", "risk calculation")
    )
    if re.search(r"\bchang(?:e|es|ed)\b.{0,12}\btime\b", q) and not stress:
        return "changes"
    if (
        any(
            s in q
            for s in (
                "changed",
                "change over time",
                "why did my allocation",
                "why is my portfolio concentrated",
            )
        )
        and not stress
    ):
        return "changes"
    if (docs and (models or portfolio or stress or risk)) or (models and portfolio):
        return "combined"
    if stress:
        return "stress"
    if models:
        return "models"
    if docs:
        return "documents"
    if risk:
        return "risk"
    if portfolio:
        return "portfolio"
    return "unsupported"


def plan_for(intent, question="", run_ids=None):
    if intent == "models":
        result = ["list_research_experiments", "compare_forecasting_models"]
        if "shap" in question.lower() or "explanation" in question.lower():
            result.append("get_model_explanation")
        return result
    if intent == "documents":
        return ["search_financial_documents"]
    if intent == "portfolio":
        return ["get_portfolio_snapshot", "get_portfolio_exposures"]
    if intent == "risk":
        return [
            "get_portfolio_snapshot",
            "get_risk_contributions"
            if "contribut" in question.lower()
            else "calculate_portfolio_risk",
        ]
    if intent == "stress":
        return ["get_portfolio_snapshot", "get_portfolio_exposures", "run_stress_scenario"]
    if intent == "changes":
        return ["compare_risk_runs"] if run_ids else []
    if intent == "combined":
        plan = ["get_portfolio_snapshot", "get_portfolio_exposures", "get_risk_contributions"]
        q = question.lower()
        if any(word in q for word in ("model", "forecast", "qlike", "lightgbm")):
            plan.append("compare_forecasting_models")
        if any(
            word in q
            for word in ("document", "report", "filing", "disclosure", "liquidity", "debt")
        ):
            plan.append("search_financial_documents")
        if any(word in q for word in ("fall", "drop", "shock")):
            plan.append("run_stress_scenario")
        return plan
    return []


def allowed_tools(intent):
    model_tools = {
        "list_research_experiments",
        "compare_forecasting_models",
        "get_model_evaluation",
        "get_conditional_var_backtest",
        "get_model_explanation",
    }
    doc_tools = {"search_financial_documents", "get_document_evidence"}
    portfolio_tools = {"get_portfolio_snapshot", "get_portfolio_exposures"}
    risk_tools = {
        "calculate_portfolio_risk",
        "get_risk_contributions",
        "get_saved_risk_run",
        "compare_risk_runs",
    }
    return {
        "models": model_tools,
        "documents": doc_tools,
        "portfolio": portfolio_tools,
        "risk": portfolio_tools | risk_tools,
        "stress": portfolio_tools | {"run_stress_scenario"},
        "combined": model_tools
        | doc_tools
        | portfolio_tools
        | risk_tools
        | {"run_stress_scenario"},
        "changes": {"get_saved_risk_run", "compare_risk_runs"},
        "unsupported": set(),
    }[intent]


def summary(row):
    return InvestigationSummary(
        id=row.id,
        question=row.question,
        status=row.status,
        stage=row.stage,
        intent=row.intent,
        engine=row.engine,
        created_at=row.created_at,
        finished_at=row.finished_at,
        elapsed_seconds=row.elapsed_seconds,
        error=row.error,
    )


def owned(db, ident, owner):
    row = db.get(AgentInvestigation, ident)
    if row is None or row.owner != owner:
        raise AppError("INVESTIGATION_NOT_FOUND", "Investigation not found in this session.", 404)
    if row.status in ("queued", "running") and row.runner_id != RUNNER_ID:
        row.status = "interrupted"
        row.stage = "Original process unavailable; submit a fresh investigation"
        row.finished_at = datetime.now(UTC)
        row.error = {
            "code": "WORKER_INTERRUPTED",
            "message": "Worker restarted; no completed answer is claimed.",
        }
        db.commit()
    return row


def detail(row):
    return InvestigationDetail(
        **summary(row).model_dump(),
        workflow_version=row.provider["workflow_version"],
        provider=row.provider,
        context=row.context,
        answer=row.answer,
        usage=row.usage,
        budgets={k: row.request[k] for k in ("max_tools", "max_steps", "timeout_seconds")},
        verification=row.verification,
    )


class InvestigationQueue:
    def __init__(self):
        self.capacity = BoundedSemaphore(1)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vantage-investigator")
        self.tool_capacity = BoundedSemaphore(1)
        self.tool_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="vantage-financial-tool"
        )
        self.futures = {}
        self.cancellations = {}

    def submit(self, db, portfolio, owner, request, *, internal_evaluation=False):
        if request.engine == "llm" and not settings().openai_api_key:
            raise AppError(
                "AI_NOT_CONFIGURED",
                "AI provider not configured. Select the explicitly labeled deterministic demonstration.",
                503,
            )
        recent = db.scalars(
            select(AgentInvestigation.created_at)
            .where(AgentInvestigation.owner == owner)
            .order_by(AgentInvestigation.created_at.desc())
            .limit(12)
        ).all()
        if (
            not internal_evaluation
            and len(recent) >= 12
            and (datetime.now(UTC) - recent[-1].replace(tzinfo=UTC)).total_seconds() < 60
        ):
            raise AppError(
                "AGENT_RATE_LIMIT",
                "At most 12 investigations per minute are permitted in this local session.",
                429,
            )
        if not self.capacity.acquire(blocking=False):
            raise AppError(
                "AGENT_BUSY", "One bounded investigation is active; wait for it to finish.", 503
            )
        try:
            request = request.model_copy(update={"question": redact(request.question)})
            snap, _ = persist_inputs(db, portfolio, {"kind": "investigation_snapshot"}, owner)
            row = AgentInvestigation(
                id=str(uuid4()),
                owner=owner,
                status="queued",
                stage="Queued for authorized investigation",
                runner_id=RUNNER_ID,
                question=request.question,
                intent=classify(request.question),
                engine=request.engine,
                request=request.model_dump(mode="json"),
                context={
                    "snapshot_id": snap.id,
                    "portfolio": portfolio.model_dump(mode="json"),
                    "experiment_id": request.experiment_id,
                    "document_ids": request.document_ids,
                },
                provider={
                    "name": "deterministic" if request.engine == "demo" else "openai",
                    "model": None if request.engine == "demo" else settings().llm_model,
                    "workflow_version": WORKFLOW_VERSION,
                },
                usage={
                    "input_tokens": None,
                    "output_tokens": None,
                    "estimated_cost_usd": None,
                    "provider_requests": 0,
                    "tool_calls": 0,
                },
                verification={},
                answer=None,
                error=None,
                cancel_requested=0,
                created_at=datetime.now(UTC),
                finished_at=None,
                elapsed_seconds=None,
            )
            db.add(row)
            db.commit()
            result = summary(row)
            event = Event()
            self.cancellations[row.id] = event
            self.futures[row.id] = self.executor.submit(self.execute, db.get_bind(), row.id, event)
            for key in list(self.futures)[:-64]:
                if self.futures[key].done():
                    self.futures.pop(key, None)
                    self.cancellations.pop(key, None)
            return result
        except Exception:
            self.capacity.release()
            raise

    def cancel(self, db, row):
        if row.status in ("queued", "running"):
            row.cancel_requested = 1
            db.commit()
            if row.id in self.cancellations:
                self.cancellations[row.id].set()
        return summary(row)

    def run_tool(self, engine, owner, request, portfolio, snapshot_id, name, arguments):
        with Session(engine) as db:
            try:
                return invoke(
                    ToolContext(db, owner, request, portfolio, snapshot_id), name, arguments
                )
            except ValidationError as error:
                raise AppError(
                    "TOOL_ARGUMENTS", "Tool arguments do not match the approved strict schema.", 403
                ) from error

    def execute(self, engine, ident, cancel):
        started = time.monotonic()
        try:
            with Session(engine) as db:
                row = db.get(AgentInvestigation, ident)
                request = InvestigationRequest.model_validate(row.request)
                state = WorkflowState(
                    question=row.question,
                    intent=row.intent,
                    plan=plan_for(row.intent, row.question, request.run_ids),
                )
                row.status = "running"
                db.commit()
                deadline = started + request.timeout_seconds

                def checkpoint(kind, message, data=None):
                    if cancel.is_set():
                        raise AppError(
                            "INVESTIGATION_CANCELLED",
                            "Investigation cancelled; no further tools or answer published.",
                            409,
                        )
                    if time.monotonic() >= deadline:
                        raise AppError(
                            "AGENT_TIMEOUT", "Investigation execution deadline exceeded.", 504
                        )
                    state.steps += 1
                    if state.steps > request.max_steps:
                        raise AppError(
                            "GRAPH_STEP_LIMIT", "Investigation exceeded its graph-step budget."
                        )
                    state.stage = kind
                    row.stage = message
                    payload = Activity(
                        sequence=state.steps,
                        kind=kind,
                        status="completed",
                        summary=message,
                        elapsed_ms=round((time.monotonic() - started) * 1000, 3),
                        data=data or {},
                    ).model_dump(mode="json")
                    db.add(
                        AgentStep(
                            id=str(uuid4()),
                            investigation_id=ident,
                            sequence=state.steps,
                            payload=payload,
                        )
                    )
                    db.commit()

                checkpoint("validate", "Validated request and execution budgets")
                checkpoint("authorize", "Bound tools to the current session and selected inputs")
                checkpoint(
                    "plan",
                    "Selected a bounded read-only investigation plan",
                    {"intent": state.intent, "planned_tools": state.plan, "mode": request.engine},
                )
                permitted_tools = allowed_tools(state.intent)
                provider = configured_provider() if request.engine == "llm" else None
                selection = None
                plan_index = 0
                while True:
                    checkpoint("route", "Selected the next approved action")
                    if state.intent == "unsupported" or (
                        state.intent == "changes" and not state.plan
                    ):
                        selection = default_selection(state.evidence)
                        break
                    if provider:
                        turn = provider.next(
                            row.question,
                            state.evidence,
                            [spec for name, spec in REGISTRY.items() if name in permitted_tools],
                            state.errors,
                            deadline - time.monotonic(),
                        )
                        usage = dict(row.usage)
                        usage.update(
                            input_tokens=(usage["input_tokens"] or 0) + turn.input_tokens,
                            output_tokens=(usage["output_tokens"] or 0) + turn.output_tokens,
                            provider_requests=usage["provider_requests"] + 1,
                        )
                        config = settings()
                        if (
                            config.llm_input_usd_per_million is not None
                            and config.llm_output_usd_per_million is not None
                        ):
                            usage["estimated_cost_usd"] = (
                                usage["input_tokens"] * config.llm_input_usd_per_million
                                + usage["output_tokens"] * config.llm_output_usd_per_million
                            ) / 1e6
                        row.usage = usage
                        db.commit()
                        if (usage["input_tokens"] or 0) + (usage["output_tokens"] or 0) > 64_000:
                            raise AppError(
                                "TOKEN_BUDGET",
                                "Investigation exceeded its cumulative token budget.",
                            )
                        if turn.final is not None:
                            selection = turn.final
                            break
                        name, arguments = turn.tool, turn.arguments
                    elif plan_index < len(state.plan):
                        name = state.plan[plan_index]
                        arguments = {}
                        plan_index += 1
                    else:
                        selection = default_selection(state.evidence)
                        break
                    if name not in REGISTRY or name not in permitted_tools:
                        db.add(
                            AgentToolCall(
                                id=str(uuid4()),
                                investigation_id=ident,
                                sequence=state.tool_count + 1,
                                payload={
                                    "name": str(name)[:80],
                                    "arguments": json.loads(redact(json.dumps(arguments))),
                                    "status": "denied",
                                    "elapsed_ms": 0,
                                    "error": {
                                        "code": "TOOL_NOT_ALLOWED",
                                        "message": "Operation is outside the request allowlist.",
                                    },
                                    "evidence_id": None,
                                },
                            )
                        )
                        db.commit()
                        raise AppError(
                            "TOOL_NOT_ALLOWED",
                            "Provider requested an operation outside the read-only allowlist.",
                            403,
                        )
                    if state.tool_count >= request.max_tools:
                        raise AppError(
                            "TOOL_CALL_LIMIT", "Investigation exceeded its tool-call budget."
                        )
                    state.tool_count += 1
                    call_id = str(uuid4())
                    call_started = time.monotonic()
                    call = {
                        "name": name,
                        "arguments": json.loads(redact(json.dumps(arguments))),
                        "status": "running",
                        "elapsed_ms": None,
                        "error": None,
                        "evidence_id": None,
                    }
                    record = AgentToolCall(
                        id=call_id, investigation_id=ident, sequence=state.tool_count, payload=call
                    )
                    db.add(record)
                    db.commit()
                    checkpoint("tool", f"Executing {name}", {"tool": name})
                    if not self.tool_capacity.acquire(blocking=False):
                        raise AppError(
                            "TOOL_BUSY",
                            "A prior bounded tool is still finishing; retry later.",
                            503,
                        )
                    future = self.tool_executor.submit(
                        self.run_tool,
                        engine,
                        row.owner,
                        request,
                        Portfolio.model_validate(row.context["portfolio"]),
                        row.context["snapshot_id"],
                        name,
                        arguments,
                    )
                    future.add_done_callback(lambda _: self.tool_capacity.release())
                    tool_deadline = min(deadline, time.monotonic() + REGISTRY[name].timeout_seconds)
                    try:
                        while True:
                            if cancel.is_set():
                                raise AppError(
                                    "INVESTIGATION_CANCELLED",
                                    "Investigation cancelled; in-flight bounded work may finish but its output will not be published.",
                                    409,
                                )
                            if time.monotonic() >= tool_deadline:
                                raise AppError(
                                    "TOOL_TIMEOUT",
                                    "Approved tool exceeded its execution deadline.",
                                    504,
                                )
                            try:
                                result = future.result(
                                    timeout=min(0.1, max(0.001, tool_deadline - time.monotonic()))
                                )
                                break
                            except TimeoutError:
                                continue
                        state.evidence.append(result)
                        db.add(
                            AgentEvidence(
                                id=result.id,
                                investigation_id=ident,
                                payload=result.model_dump(mode="json"),
                            )
                        )
                        call.update(status="completed", evidence_id=result.id)
                    except AppError as error:
                        call.update(
                            status="failed",
                            error={"code": error.code, "message": redact(error.message)},
                        )
                        state.errors.append(call["error"])
                        if error.status in (403, 409, 504) or error.code in ("TOOL_NOT_ALLOWED",):
                            raise
                    finally:
                        call["elapsed_ms"] = round((time.monotonic() - call_started) * 1000, 3)
                        record.payload = call
                        row.usage = {**row.usage, "tool_calls": state.tool_count}
                        db.commit()
                checkpoint(
                    "verify", "Checked authoritative financial values, units, dates and sources"
                )
                answer = verify_and_compose(
                    state, selection, request.engine, self.document_resolver(db, row.owner)
                )
                checkpoint(
                    "compose",
                    "Composed the verified evidence response; no hidden reasoning exposed",
                )
                row.answer = answer.model_dump(mode="json")
                row.verification = {
                    "numerical": answer.numerical_verification,
                    "citations": answer.citation_verification,
                    "unsupported_values_published": 0,
                }
                row.status = (
                    "limited"
                    if state.errors or (not answer.claims and not answer.citations)
                    else "completed"
                )
                row.stage = "Validated investigation saved"
                row.finished_at = datetime.now(UTC)
                row.elapsed_seconds = time.monotonic() - started
                db.commit()
        except Exception as error:
            with Session(engine) as db:
                row = db.get(AgentInvestigation, ident)
                row.status = (
                    "cancelled"
                    if isinstance(error, AppError) and error.code == "INVESTIGATION_CANCELLED"
                    else "failed"
                )
                row.error = {
                    "code": error.code if isinstance(error, AppError) else "AGENT_FAILED",
                    "message": redact(error.message)
                    if isinstance(error, AppError)
                    else "Investigation could not produce a verified response; no answer published.",
                }
                for pending in db.scalars(
                    select(AgentToolCall).where(AgentToolCall.investigation_id == ident)
                ).all():
                    if pending.payload.get("status") == "running":
                        pending.payload = {
                            **pending.payload,
                            "status": "cancelled" if row.status == "cancelled" else "failed",
                            "error": row.error,
                        }
                row.answer = None
                row.verification = {"status": "rejected", "unsupported_values_published": 0}
                row.stage = row.error["message"][:100]
                row.finished_at = datetime.now(UTC)
                row.elapsed_seconds = time.monotonic() - started
                db.commit()
            logger.warning(
                json.dumps(
                    {
                        "event": "investigation_stopped",
                        "id": ident,
                        "error_type": type(error).__name__,
                    }
                )
            )
        finally:
            self.capacity.release()

    def document_resolver(self, db, owner):
        from app.documents.service import resolve_passage

        return lambda passage: resolve_passage(db, owner, passage)


queue = InvestigationQueue()
