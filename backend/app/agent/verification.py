"""Deterministic fact/citation validation and response composition; no second-LLM grading."""

import math

from app.core.errors import AppError
from app.risk.artifacts import digest

from .contracts import Citation, FinalSelection, ValidatedAnswer, VerifiedClaim


def default_selection(evidence):
    facts = [(e, f) for e in evidence for f in e.facts]
    facts.sort(
        key=lambda pair: (
            pair[1].key
            not in ("lowest_qlike_model", "matched_observations", "high_regime_observations"),
            not pair[1].key.endswith(".qlike"),
        )
    )
    claims = [
        {"evidence_id": e.id, "fact_key": f.key, "value": f.value, "unit": f.unit, "as_of": f.as_of}
        for e, f in facts[:100]
    ]
    citations = []
    for e in evidence:
        for passage in e.data.get("passages", []):
            if len(citations) >= 8:
                break
            quote = passage["text"][:800]
            if len(quote.strip()) >= 20:
                citations.append(
                    {"evidence_id": e.id, "chunk_id": passage["chunk_id"], "quote": quote}
                )
    return FinalSelection(claims=claims, citations=citations)


def verify_and_compose(state, selection, engine, document_resolver=None):
    evidence = {e.id: e for e in state.evidence}
    for e in evidence.values():
        if digest(e.model_dump(mode="json", exclude={"checksum"})) != e.checksum:
            raise AppError(
                "EVIDENCE_INTEGRITY", "Approved tool evidence changed before verification.", 409
            )
    verified = []
    seen = set()
    for claim in selection.claims:
        key = (claim.evidence_id, claim.fact_key)
        if key in seen:
            raise AppError("DUPLICATE_CLAIM", "Repeated fact references are not a valid response.")
        seen.add(key)
        e = evidence.get(claim.evidence_id)
        f = next((f for f in e.facts if f.key == claim.fact_key), None) if e else None
        if f is None or f.unit != claim.unit or f.as_of != claim.as_of:
            raise AppError(
                "UNSUPPORTED_CLAIM",
                "A proposed value, source, date or unit has no approved financial evidence.",
                409,
            )
        if isinstance(f.value, (float, int)) and not isinstance(claim.value, bool):
            valid = isinstance(claim.value, (float, int)) and math.isclose(
                f.value, claim.value, rel_tol=1e-12, abs_tol=1e-14
            )
        else:
            valid = type(claim.value) is type(f.value) and claim.value == f.value
        if not valid:
            raise AppError(
                "NUMERICAL_VERIFICATION",
                "A proposed financial value differs from the authoritative tool result; no answer published.",
                409,
            )
        verified.append(VerifiedClaim(**f.model_dump(), evidence_id=e.id, source_id=e.source_id))
    required = {
        (e.id, f.key)
        for e in evidence.values()
        for f in e.facts
        if f.key == "lowest_qlike_model"
        or f.key == "matched_observations"
        or f.key.endswith(".qlike")
    }
    if not required.issubset(seen):
        raise AppError(
            "INCOMPLETE_MODEL_COMPARISON",
            "Model comparison must include every matched QLIKE and its sample/lowest-value qualification.",
            409,
        )
    if any(e.data.get("passages") for e in evidence.values()) and not selection.citations:
        raise AppError(
            "INCOMPLETE_DOCUMENT_EVIDENCE",
            "Retrieved document conclusions require at least one exact supported citation.",
            409,
        )
    citations = []
    for choice in selection.citations:
        e = evidence.get(choice.evidence_id)
        passage = (
            next((p for p in e.data.get("passages", []) if p["chunk_id"] == choice.chunk_id), None)
            if e
            else None
        )
        if not passage or choice.quote not in passage["text"] or document_resolver is None:
            raise AppError(
                "CITATION_VERIFICATION",
                "A citation does not resolve to an authorized retrieved passage.",
                409,
            )
        source = document_resolver(passage)
        if (
            choice.quote not in source["text"]
            or source["page"] != passage["page"]
            or source["content_hash"] != passage["content_hash"]
        ):
            raise AppError(
                "CITATION_VERIFICATION",
                "The cited source/page/text changed or is unavailable.",
                409,
            )
        citations.append(
            Citation(
                document_id=passage["document_id"],
                chunk_id=choice.chunk_id,
                page=passage["page"],
                section=passage["section"],
                quote=choice.quote,
                content_hash=passage["content_hash"],
                source=passage["source"],
                evidence_id=e.id,
            )
        )
    findings = []
    for e in evidence.values():
        best = next((f for f in e.facts if f.key == "lowest_qlike_model"), None)
        if best:
            findings.extend(
                [
                    f"{best.value} has the lowest observed average QLIKE on the common saved evaluation dates. This descriptive ranking is not a champion decision.",
                    "QLIKE, variance errors, coverage, regimes and uncertainty answer different questions. A better average loss alone does not establish predictive superiority.",
                    "The measured errors do not identify a causal explanation for model differences. Saved SHAP and sensitivity describe fitted predictions, not causes of market risk.",
                ]
            )
            intervals = e.data.get("uncertainty", [])
            if intervals and all(
                u.get("available") and u["interval95"][0] <= 0 <= u["interval95"][1]
                for u in intervals
            ):
                findings.append(
                    "All stored paired QLIKE bootstrap intervals include zero; this experiment does not establish statistically convincing differences."
                )
        if e.data.get("passages"):
            findings.append(
                "The quoted disclosures are historical source evidence. They do not establish current portfolio exposure, present liquidity, or causal market effects. Conflicting disclosures remain separate sources; later reporting periods may differ."
            )
    if state.intent == "unsupported":
        findings.append(
            "This read-only investigator cannot execute trades, reveal secrets, run commands/SQL, change governance or provide unsupported investment recommendations."
        )
    if state.intent == "changes":
        findings.append(
            "A historical cause cannot be established without comparable authorized historical snapshots. Current allocations alone do not explain why holdings changed."
        )
    if not verified and not citations and not findings:
        findings.append(
            "Insufficient authorized evidence. Select accessible research or upload relevant permitted documents; no missing data has been invented."
        )
    warnings = list(dict.fromkeys(w for e in evidence.values() for w in e.warnings))
    warnings += [error["message"] for error in state.errors]
    if any(e.synthetic for e in evidence.values()):
        warnings.append(
            "SYNTHETIC data is a software/research demonstration and does not validate real-world financial claims."
        )
    if engine == "demo":
        warnings.append("Deterministic scripted demonstration; no live AI provider was used.")
    return ValidatedAnswer(
        title={
            "models": "Forecasting model investigation",
            "documents": "Financial disclosure evidence",
            "stress": "Hypothetical scenario investigation",
            "portfolio": "Portfolio exposure investigation",
            "risk": "Quantitative risk investigation",
            "combined": "Combined financial investigation",
            "changes": "Historical comparison limitations",
            "unsupported": "Requested operation unavailable",
        }[state.intent],
        execution_mode="Deterministic demonstration"
        if engine == "demo"
        else "Configured AI with deterministic financial verification",
        findings=list(dict.fromkeys(findings)),
        claims=verified,
        citations=citations,
        warnings=list(dict.fromkeys(warnings)),
        numerical_verification="passed" if verified else "not_applicable",
        citation_verification="passed" if citations else "not_applicable",
        financial_validity="Automated evidence checks establish consistency with approved sources, not real-world financial validity or production readiness.",
    )
