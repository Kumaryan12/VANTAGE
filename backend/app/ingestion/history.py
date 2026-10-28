import hashlib
import io
import json
import re
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.database.models import Dataset
from app.portfolios.schemas import Provenance

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 50_000
COLUMNS = {"date", "instrument", "close", "currency"}


def parse_upload(content: bytes, filename: str) -> pd.DataFrame:
    if not content or len(content) > MAX_BYTES:
        raise AppError("UPLOAD_SIZE", "History file must be nonempty and at most 5 MB.", 413)
    try:
        if filename.lower().endswith(".csv"):
            frame = pd.read_csv(
                io.BytesIO(content), nrows=MAX_ROWS + 1, dtype={"instrument": str, "currency": str}
            )
        elif filename.lower().endswith(".parquet"):
            parquet = pq.ParquetFile(io.BytesIO(content))
            size = sum(
                parquet.metadata.row_group(i).column(j).total_uncompressed_size
                for i in range(parquet.metadata.num_row_groups)
                for j in range(parquet.metadata.num_columns)
            )
            if parquet.metadata.num_rows > MAX_ROWS or size > 25 * 1024 * 1024:
                raise AppError("UPLOAD_SIZE", "Parquet exceeds row or expanded-size limits.", 413)
            frame = parquet.read().to_pandas()
        else:
            raise AppError("FILE_TYPE", "Only .csv and .parquet history files are accepted.")
    except AppError:
        raise
    except Exception:
        raise AppError(
            "FILE_PARSE", "History file could not be parsed using the documented schema."
        ) from None
    return frame


def validate_history(frame: pd.DataFrame) -> pd.DataFrame:
    if set(frame.columns) != COLUMNS or not 1 <= len(frame) <= MAX_ROWS:
        raise AppError(
            "HISTORY_SCHEMA",
            "Expected 1–50,000 rows with exactly date,instrument,close,currency columns.",
        )
    frame = frame.copy()
    if frame.isna().any().any():
        raise AppError("HISTORY_NULL", "Null historical observations are not permitted.")
    if not frame.instrument.map(
        lambda x: isinstance(x, str) and bool(re.fullmatch(r"(?:NSE|BSE):[A-Z0-9&_.-]{1,40}", x))
    ).all():
        raise AppError("INSTRUMENT_ID", "Use explicit NSE:SYMBOL or BSE:SYMBOL identifiers.")
    if frame.instrument.nunique() > 50 or not frame.currency.eq("INR").all():
        raise AppError(
            "HISTORY_CURRENCY",
            "Phase 1 accepts at most 50 INR instruments; no FX conversion is inferred.",
        )
    try:
        if not frame.date.map(
            lambda x: bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(x)[:10]))
        ).all():
            raise ValueError
        frame["date"] = pd.to_datetime(frame.date, format="ISO8601")
        if frame.date.dt.tz is not None or not frame.date.eq(frame.date.dt.normalize()).all():
            raise ValueError
        frame["close"] = pd.to_numeric(frame.close, errors="raise").astype(float)
    except (ValueError, TypeError, AttributeError):
        raise AppError(
            "HISTORY_VALUES", "Dates must be ISO daily dates and closes numeric."
        ) from None
    if (
        not np.isfinite(frame.close).all()
        or frame.close.le(0).any()
        or frame.date.max().date() > datetime.now(UTC).date()
    ):
        raise AppError(
            "HISTORY_VALUES", "Prices must be finite and positive; dates cannot be in the future."
        )
    if frame.duplicated(["date", "instrument"]).any():
        raise AppError(
            "DUPLICATE_OBSERVATION", "Duplicate instrument/date observations are not permitted."
        )
    return frame.sort_values(["date", "instrument"]).reset_index(drop=True)


def canonical_records(frame: pd.DataFrame) -> str:
    normalized = frame.copy()
    normalized["date"] = normalized.date.dt.strftime("%Y-%m-%d")
    return json.dumps(
        normalized[["date", "instrument", "close", "currency"]].to_dict("records"),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def persist_history(db: Session, frame: pd.DataFrame, source: str, adjustment: str, owner: str):
    from app.auth.identity import ensure_scope

    ensure_scope(db, owner)
    from uuid import uuid4

    frame = validate_history(frame)
    records = canonical_records(frame)
    now = datetime.now(UTC)
    provenance = Provenance(
        source=source,
        synthetic=False,
        adjustment=adjustment,
        retrieved_at=now,
        start=frame.date.min().date(),
        end=frame.date.max().date(),
        content_hash=hashlib.sha256(records.encode()).hexdigest(),
    )
    dataset = Dataset(
        id=str(uuid4()),
        owner=owner,
        provenance=provenance.model_dump(mode="json"),
        records=records,
        created_at=now,
    )
    db.add(dataset)
    db.commit()
    return {
        "id": dataset.id,
        "rows": len(frame),
        "instruments": sorted(frame.instrument.unique()),
        "provenance": provenance.model_dump(mode="json"),
    }


def load_history(db: Session, dataset_id: str, owner: str):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None or dataset.owner != owner:
        raise AppError(
            "DATASET_NOT_FOUND", "Historical dataset not found in this browser session.", 404
        )
    if hashlib.sha256(dataset.records.encode()).hexdigest() != dataset.provenance["content_hash"]:
        raise AppError(
            "SOURCE_INTEGRITY", "Stored historical data failed its provenance hash check.", 409
        )
    frame = pd.DataFrame(json.loads(dataset.records))
    frame["date"] = pd.to_datetime(frame.date)
    return frame, Provenance.model_validate(dataset.provenance)
