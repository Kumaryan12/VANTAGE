from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    provenance: Mapped[dict] = mapped_column(JSON)
    records: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RiskRun(Base):
    __tablename__ = "risk_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    methodology: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    kind: Mapped[str] = mapped_column(String(16), default="legacy", server_default="legacy")
    snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("portfolio_snapshots.id"))
    input_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("risk_input_artifacts.id"))
    parameters: Mapped[dict | None] = mapped_column(JSON)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (UniqueConstraint("owner", "content_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RiskInputArtifact(Base):
    __tablename__ = "risk_input_artifacts"
    __table_args__ = (UniqueConstraint("owner", "content_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchExperiment(Base):
    __tablename__ = "research_experiments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20))
    stage: Mapped[str] = mapped_column(String(150))
    progress: Mapped[int] = mapped_column(Integer)
    runner_id: Mapped[str] = mapped_column(String(36))
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("portfolio_snapshots.id"))
    input_artifact_id: Mapped[str] = mapped_column(ForeignKey("risk_input_artifacts.id"))
    dataset_hash: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict] = mapped_column(JSON)
    data_info: Mapped[dict] = mapped_column(JSON)
    protocol: Mapped[dict] = mapped_column(JSON)
    runtime: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[dict | None] = mapped_column(JSON)
    reproduction_of: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ForecastModel(Base):
    __tablename__ = "forecast_models"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("research_experiments.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)


class ResearchForecast(Base):
    __tablename__ = "research_forecasts"
    __table_args__ = (UniqueConstraint("model_id", "target_date"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("forecast_models.id"), index=True)
    target_date: Mapped[date] = mapped_column(Date)
    payload: Mapped[dict] = mapped_column(JSON)


class ModelGovernanceEvent(Base):
    __tablename__ = "model_governance_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("forecast_models.id"), index=True)
    owner: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentInvestigation(Base):
    __tablename__ = "agent_investigations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20))
    stage: Mapped[str] = mapped_column(String(100))
    runner_id: Mapped[str] = mapped_column(String(36))
    question: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(20))
    engine: Mapped[str] = mapped_column(String(20))
    request: Mapped[dict] = mapped_column(JSON)
    context: Mapped[dict] = mapped_column(JSON)
    provider: Mapped[dict] = mapped_column(JSON)
    usage: Mapped[dict] = mapped_column(JSON)
    verification: Mapped[dict] = mapped_column(JSON)
    answer: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[dict | None] = mapped_column(JSON)
    cancel_requested: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    elapsed_seconds: Mapped[float | None] = mapped_column(Float)


class AgentStep(Base):
    __tablename__ = "agent_steps"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("agent_investigations.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"
    sequence: Mapped[int | None] = mapped_column(Integer)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("agent_investigations.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class AgentEvidence(Base):
    __tablename__ = "agent_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("agent_investigations.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class AgentEvaluation(Base):
    __tablename__ = "agent_evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchDocument(Base):
    __tablename__ = "research_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(200))
    content_hash: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(200))
    company: Mapped[str | None] = mapped_column(String(80))
    reporting_period: Mapped[str | None] = mapped_column(String(50))
    publication_date: Mapped[date | None] = mapped_column(Date)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    page_count: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer)
    version: Mapped[str] = mapped_column(String(100))
    processing: Mapped[dict] = mapped_column(JSON)
    error: Mapped[dict | None] = mapped_column(JSON)


class ResearchDocumentChunk(Base):
    __tablename__ = "research_document_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("research_documents.id"), index=True)
    page: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(150))
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    token_counts: Mapped[dict] = mapped_column(JSON)
    embedding: Mapped[list | None] = mapped_column(JSON)
    embedding_model: Mapped[str | None] = mapped_column(String(100))


class OptimizationRun(Base):
    __tablename__ = "optimization_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    stage: Mapped[str] = mapped_column(String(150))
    progress: Mapped[int] = mapped_column(Integer)
    runner_id: Mapped[str] = mapped_column(String(36))
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("portfolio_snapshots.id"))
    artifact_id: Mapped[str] = mapped_column(ForeignKey("risk_input_artifacts.id"))
    input_hash: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict] = mapped_column(JSON)
    dataset: Mapped[dict] = mapped_column(JSON)
    runtime: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[dict | None] = mapped_column(JSON)
    reproduction_of: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OptimizationCounterfactual(Base):
    __tablename__ = "optimization_counterfactuals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("optimization_runs.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
