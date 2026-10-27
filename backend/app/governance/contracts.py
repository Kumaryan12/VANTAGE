from datetime import datetime
from typing import Literal

from pydantic import Field

from app.portfolios.schemas import StrictModel

ReviewStatus = Literal[
    "candidate", "under_review", "validated", "approved_research", "rejected", "retired"
]
REVIEW_AREAS = (
    "out_of_sample",
    "var_coverage",
    "uncertainty",
    "data_quality",
    "leakage",
    "regime_stability",
    "complexity",
    "reproducibility_operations",
)


class RegisterModel(StrictModel):
    source_type: Literal["optimization", "forecast"]
    source_id: str = Field(min_length=1, max_length=36)
    intended_use: str = Field(
        "Local methodological research only; no real-market investment or execution approval.",
        min_length=20,
        max_length=500,
    )


class ReviewRequest(StrictModel):
    status: ReviewStatus
    rationale: str = Field(min_length=20, max_length=2000)
    human_review: Literal[True]
    research_only: Literal[True]
    approval_scope: Literal["methodology_research"] = "methodology_research"
    assessments: dict[str, str] = Field(default_factory=dict, max_length=8)


class ReviewModel(StrictModel):
    id: str
    source_type: str
    source_id: str
    model_type: str
    model_version: str
    intended_use: str
    status: ReviewStatus
    created_at: datetime
    payload: dict
    current_validation: dict
    allowed_transitions: list[ReviewStatus]


class ReviewEvent(StrictModel):
    id: str
    model_id: str
    created_at: datetime
    payload: dict
