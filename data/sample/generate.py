"""Regenerate SYNTHETIC development data. No actual securities or prices."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent


def generate():
    rng = np.random.default_rng(20261026)
    dates = pd.bdate_range(end="2026-10-23", periods=505)
    market = rng.normal(0.0003, 0.010, len(dates) - 1)
    securities = [
        ("AURORA", "Aurora Technologies", "Technology", 420, 2150, 1.1),
        ("MERIDIAN", "Meridian Bank", "Financials", 800, 980, 0.95),
        ("HELIX", "Helix Healthcare", "Healthcare", 300, 1850, 0.6),
        ("ATLAS", "Atlas Industries", "Industrials", 260, 2350, 1.2),
        ("VERDE", "Verde Energy", "Energy", 500, 650, 1.05),
        ("NORTHSTAR", "Northstar Consumer", "Consumer", 350, 920, 0.55),
    ]
    records, holdings = [], []
    for symbol, name, sector, quantity, initial, beta in securities:
        returns = beta * market + rng.normal(0.00005, 0.007, len(market))
        prices = np.r_[initial, initial * np.cumprod(1 + returns)]
        records.extend(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "instrument": f"NSE:{symbol}",
                "close": float(price),
                "currency": "INR",
            }
            for dt, price in zip(dates, prices, strict=True)
        )
        holdings.append(
            {
                "instrument": f"NSE:{symbol}",
                "name": name,
                "sector": sector,
                "quantity": quantity,
                "last_price": float(prices[-1]),
                "average_price": initial,
            }
        )
    frame = pd.DataFrame(records).sort_values(["date", "instrument"])
    frame.to_csv(HERE / "prices.csv", index=False, float_format="%.12f")
    timestamp = "2026-10-23T10:00:00+00:00"
    (HERE / "portfolio.json").write_text(
        json.dumps(
            {
                "source": "VANTAGE synthetic fixture v1 / seed 20261026",
                "as_of": "2026-10-23",
                "retrieved_at": timestamp,
                "holdings": holdings,
            },
            indent=2,
        )
        + "\n"
    )
    # Hash the actual checked-in bytes, not the unrounded generator values.
    (HERE / "provenance.json").write_text(
        json.dumps(
            {
                "source": "VANTAGE synthetic fixture v1 / seed 20261026",
                "synthetic": True,
                "adjustment": "split_dividend_adjusted",
                "currency": "INR",
                "retrieved_at": timestamp,
                "start": dates[0].strftime("%Y-%m-%d"),
                "end": dates[-1].strftime("%Y-%m-%d"),
                "content_hash": hashlib.sha256(
                    (HERE / "prices.csv").read_bytes()
                ).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    generate()
