from datetime import datetime

import numpy as np

from app.core.errors import AppError
from app.portfolios.schemas import Portfolio


def normalize(rows: list[dict], *, mode: str, source: str, as_of, retrieved_at: datetime):
    if not rows:
        raise AppError("EMPTY_PORTFOLIO", "No positive cash-equity holdings are available.")
    instruments = [r["instrument"] for r in rows]
    if len(set(instruments)) != len(instruments):
        raise AppError("DUPLICATE_INSTRUMENT", "Portfolio contains duplicate instruments.")
    quantities = np.array([r["quantity"] for r in rows], dtype=float)
    prices = np.array([r["last_price"] for r in rows], dtype=float)
    costs = np.array([r["average_price"] for r in rows], dtype=float)
    if (
        not np.isfinite([quantities, prices, costs]).all()
        or (quantities <= 0).any()
        or (prices <= 0).any()
        or (costs < 0).any()
    ):
        raise AppError(
            "INVALID_HOLDINGS",
            "Holdings require positive finite quantities/prices and nonnegative costs.",
        )
    values = quantities * prices
    weights = values / values.sum()
    sectors: dict[str, float] = {}
    holdings = []
    for row, value, weight in zip(rows, values, weights, strict=True):
        sectors[row["sector"]] = sectors.get(row["sector"], 0) + float(weight)
        holdings.append(
            {
                **row,
                "value": float(value),
                "weight": float(weight),
                "unrealized_pnl": float(value - row["quantity"] * row["average_price"]),
            }
        )
    return Portfolio(
        mode=mode,
        synthetic=mode == "demo",
        source=source,
        as_of=as_of,
        retrieved_at=retrieved_at,
        holdings=holdings,
        total_value=float(values.sum()),
        total_cost=float(quantities @ costs),
        unrealized_pnl=float(values.sum() - quantities @ costs),
        largest_weight=float(weights.max()),
        hhi=float(weights @ weights),
        sectors=sectors,
        price_timestamp_note=(
            "Synthetic fixture observation date."
            if mode == "demo"
            else "Broker last-price timestamps are unavailable; as_of is retrieval date, not a verified market-price timestamp."
        ),
        warnings=(
            ["SYNTHETIC DEMO: invented securities and prices; no actual market performance."]
            if mode == "demo"
            else [
                "Holdings only: cash, open positions, derivatives, and execution costs are excluded.",
                "Sector metadata is unavailable and classified as Unknown.",
            ]
        ),
    )
