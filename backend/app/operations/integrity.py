"""Compute private database evidence fingerprints without emitting financial records."""

import hashlib
import json

from sqlalchemy import inspect, text

# Legacy evidence, including child records without direct owner columns.
FINANCIAL_TABLES = (
    "datasets",
    "risk_runs",
    "portfolio_snapshots",
    "risk_input_artifacts",
    "research_experiments",
    "forecast_models",
    "research_forecasts",
    "model_governance_events",
    "agent_investigations",
    "agent_steps",
    "agent_tool_calls",
    "agent_evidence",
    "agent_evaluations",
    "research_documents",
    "research_document_chunks",
    "optimization_runs",
    "optimization_counterfactuals",
    "governance_models",
    "governance_review_events",
)


def evidence_fingerprints(engine):
    existing = set(inspect(engine).get_table_names())
    result = {}
    with engine.connect() as connection:
        for table in FINANCIAL_TABLES:
            if table not in existing:
                continue
            # Identifiers come from the static allowlist, not a request or model.
            rows = connection.execute(text(f'SELECT * FROM "{table}" ORDER BY id')).mappings()
            checksum = hashlib.sha256()
            count = 0
            for row in rows:
                checksum.update(
                    json.dumps(
                        dict(row),
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                        allow_nan=False,
                    ).encode()
                )
                checksum.update(b"\n")
                count += 1
            result[table] = {"rows": count, "sha256": checksum.hexdigest()}
    return result
