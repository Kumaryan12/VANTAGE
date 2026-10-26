from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.portfolios.schemas import StrictModel
from app.risk.contracts import StressRequest

WORKFLOW_VERSION = "financial-investigator-4.0.0"
Status = Literal["queued", "running", "completed", "limited", "failed", "cancelled", "interrupted"]
Intent = Literal[
    "portfolio", "risk", "models", "stress", "documents", "combined", "changes", "unsupported"
]


class InvestigationRequest(StrictModel):
    question: str = Field(min_length=8, max_length=1600)
    engine: Literal["demo", "llm"] = "demo"
    mode: Literal["demo", "kite"] = "demo"
    dataset_id: str | None = Field(None, max_length=36)
    experiment_id: str | None = Field(None, max_length=36)
    run_ids: list[str] = Field(default_factory=list, max_length=4)
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    company: str | None = Field(None, max_length=80)
    confidence: float = Field(0.95, ge=0.9, le=0.995)
    window: int = Field(252, ge=60, le=1260, strict=True)
    shrinkage: float = Field(0, ge=0, le=1)
    scenario: StressRequest | None = None
    external_data_consent: bool = False
    max_tools: int = Field(8, ge=1, le=8, strict=True)
    max_steps: int = Field(24, ge=4, le=24, strict=True)
    timeout_seconds: int = Field(60, ge=5, le=90, strict=True)

    @model_validator(mode="after")
    def consent(self):
        if self.engine == "llm" and not self.external_data_consent:
            raise ValueError(
                "Live AI requires explicit consent to send bounded redacted evidence to the configured provider."
            )
        if self.scenario and (
            self.scenario.mode != self.mode or self.scenario.dataset_id != self.dataset_id
        ):
            raise ValueError(
                "Scenario mode/dataset must match the authorized investigation context."
            )
        return self


class Fact(StrictModel):
    key: str
    label: str
    value: float | int | str | None
    unit: str
    as_of: str


class ToolEvidence(StrictModel):
    id: str
    tool: str
    source_type: str
    source_id: str
    synthetic: bool
    as_of: str
    provenance: dict
    data: dict
    facts: list[Fact]
    warnings: list[str]
    checksum: str


class Claim(StrictModel):
    evidence_id: str
    fact_key: str
    value: float | int | str | None
    unit: str
    as_of: str


class CitationChoice(StrictModel):
    evidence_id: str
    chunk_id: str
    quote: str = Field(min_length=20, max_length=900)


class FinalSelection(StrictModel):
    claims: list[Claim] = Field(max_length=100)
    citations: list[CitationChoice] = Field(max_length=8)


class VerifiedClaim(Fact):
    evidence_id: str
    source_id: str


class Citation(StrictModel):
    document_id: str
    chunk_id: str
    page: int
    section: str
    quote: str
    content_hash: str
    source: str
    evidence_id: str
    unavailable: bool = False


class ValidatedAnswer(StrictModel):
    title: str
    execution_mode: str
    findings: list[str]
    claims: list[VerifiedClaim]
    citations: list[Citation]
    warnings: list[str]
    numerical_verification: Literal["passed", "not_applicable"]
    citation_verification: Literal["passed", "not_applicable"]
    financial_validity: str


class InvestigationSummary(StrictModel):
    id: str
    question: str
    status: Status
    stage: str
    intent: Intent
    engine: str
    created_at: datetime
    finished_at: datetime | None
    elapsed_seconds: float | None
    error: dict | None


class InvestigationDetail(InvestigationSummary):
    workflow_version: str
    provider: dict
    context: dict
    answer: ValidatedAnswer | None
    usage: dict
    budgets: dict
    verification: dict


class Activity(StrictModel):
    sequence: int
    kind: str
    status: str
    summary: str
    elapsed_ms: float
    data: dict


class ProviderStatus(StrictModel):
    configured: bool
    provider: str
    model: str
    demo_available: bool
    embeddings_available: bool
    message: str


class WorkflowState(StrictModel):
    question: str = ""
    stage: str = "validate"
    steps: int = 0
    tool_count: int = 0
    intent: Intent
    evidence: list[ToolEvidence] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    plan: list[str] = Field(default_factory=list)
