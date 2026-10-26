import hashlib
import json
from datetime import datetime

import pandas as pd

from app.core.config import ROOT
from app.core.errors import AppError
from app.portfolios.normalize import normalize
from app.portfolios.schemas import Provenance


class DemoBroker:
    def portfolio(self):
        fixture = json.loads((ROOT / "data/sample/portfolio.json").read_text())
        return normalize(
            fixture["holdings"],
            mode="demo",
            source=fixture["source"],
            as_of=fixture["as_of"],
            retrieved_at=datetime.fromisoformat(fixture["retrieved_at"]),
        )


def demo_history():
    frame = pd.read_csv(ROOT / "data/sample/prices.csv", parse_dates=["date"])
    provenance = Provenance.model_validate_json((ROOT / "data/sample/provenance.json").read_text())
    if (
        hashlib.sha256((ROOT / "data/sample/prices.csv").read_bytes()).hexdigest()
        != provenance.content_hash
    ):
        raise AppError(
            "SOURCE_INTEGRITY", "Synthetic fixture failed its provenance hash check.", 409
        )
    return frame, provenance
