# Local research model governance

The Phase 5 registry links owned feasible single-allocation models and Phase 3 forecasting models without changing their original experiments, metrics, roles or reports. A source initially registers as **candidate**, including automatic feasible-allocation candidate registration. This is not automatic validation, approval or champion selection.

| Current status | Permitted next status |
| --- | --- |
| candidate | under_review, rejected, retired |
| under_review | validated, rejected, retired |
| validated | approved_research, under_review, rejected, retired |
| approved_research | under_review, retired |
| rejected | under_review, retired |
| retired | terminal |

Only the owning active browser session can register/read/review its model. Every review POST requires an explicit human acknowledgement, research-only acknowledgement and substantive written rationale. The backend sets the reviewer session from its authorization boundary; client-supplied owner/identity is not trusted. No durable user identity or independent reviewer role exists. This is locally meaningful session audit, not enterprise maker-checker or regulatory approval.

A validated transition requires current source/integrity checks and an actual successful saved-input reproduction. Optimization requires optimal termination and independently checked constraints; an inaccurate optimum cannot pass this gate. Forecasting requires a complete matched evaluation of at least 100 targets, original snapshot/history/checkpoint integrity and reproduction; this count is a software evidence minimum, not proof of economic superiority. Eight written assessments are mandatory:

1. Out-of-sample performance and its gaps.
2. VaR coverage, sparse tests and their gaps.
3. Statistical uncertainty.
4. Data quality/permissions/source limitations.
5. Leakage risk and point-in-time assumptions.
6. Regime stability and missing regimes.
7. Model complexity/estimation sensitivity.
8. Reproducibility and operational limitations.

Unavailable real-market/out-of-sample evidence must be described explicitly; mathematical feasibility cannot replace it. Only **methodology_research** approval scope is supported. Even imported actual histories do not enable an investment-use approval endpoint. Synthetic evidence is insufficient for real-market approval. `approved_research` requires prior assessments and current evidence gates. Low QLIKE alone never grants approval or changes Phase 3 champion roles.

Events preserve previous/new status, UTC time, actor/session, written rationale, assessments, scope and evidence snapshot. Current evidence is re-evaluated rather than copied blindly from an earlier review. Source corruption makes validation/approval unavailable. Candidate registration identifies its actor as system registration, not a human decision.

The dashboard provides explicit permitted actions and blank human-authored notes; it never manufactures a favorable review. Browser/unit tests simulate acknowledgements solely to exercise the contract; these fixtures are not actual investment approvals. The assistant can read governance status only. Its registry has no registration, review, promotion, holdings mutation or execution tool.
