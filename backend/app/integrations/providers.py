import math
import threading
import time
from datetime import UTC, date, datetime, timedelta
from typing import Literal

import httpx
import pandas as pd
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.core.errors import AppError


class FXRate(BaseModel):
    date: date
    base: str
    quote: str
    rate: float = Field(gt=0, allow_inf_nan=False)


class ProviderClient:
    """Hardcoded hosts, bounded time/size, sanitized errors, small context cache."""

    def __init__(self, transport=None):
        self.transport = transport
        self.cache: dict[tuple, tuple[float, dict]] = {}
        self.lock = threading.Lock()

    def _json(self, url: str, params: dict):
        try:
            with httpx.Client(
                timeout=20, transport=self.transport, follow_redirects=False
            ) as client:
                with client.stream("GET", url, params=params) as response:
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > 10 * 1024 * 1024:
                            raise AppError(
                                "PROVIDER_RESPONSE_SIZE",
                                "Provider response exceeded size limit.",
                                502,
                            )
                    return httpx.Response(200, content=bytes(content)).json()
        except AppError:
            raise
        except (httpx.HTTPError, ValueError):
            raise AppError(
                "PROVIDER_UNAVAILABLE",
                "Data provider request failed. Check configuration, entitlement, and availability.",
                502,
            ) from None

    def fx(self, base: str, quote: str):
        key = ("fx", base, quote)
        with self.lock:
            cached = self.cache.get(key)
        if cached and cached[0] > time.monotonic():
            return {**cached[1], "cached": True}
        data = self._json(f"https://api.frankfurter.dev/v2/rate/{base.lower()}/{quote.lower()}", {})
        try:
            rate = FXRate.model_validate(data)
            if rate.base.upper() != base or rate.quote.upper() != quote:
                raise ValueError
        except (ValidationError, ValueError, TypeError):
            raise AppError(
                "PROVIDER_SCHEMA", "FX provider returned an invalid currency-pair observation.", 502
            ) from None
        result = {
            **rate.model_dump(mode="json"),
            "source": "Frankfurter v2 / blended reference rate",
            "retrieved_at": datetime.now(UTC).isoformat(),
            "cached": False,
            "note": "Daily reference context only; not used to convert portfolio valuations.",
        }
        with self.lock:
            if len(self.cache) >= 100:
                self.cache.clear()
            self.cache[key] = (time.monotonic() + 3600, result)
        return result

    def macro(self, series_id: str, vintage: date):
        if not settings().fred_api_key:
            raise AppError(
                "FRED_NOT_CONFIGURED",
                "Set FRED_API_KEY on the backend to fetch macroeconomic observations.",
                503,
            )
        now = datetime.now(UTC)
        if vintage > now.date():
            raise AppError("FUTURE_VINTAGE", "FRED vintage cannot be in the future.")
        data = self._json(
            "https://api.stlouisfed.org/fred/series/observations",
            {
                "api_key": settings().fred_api_key,
                "file_type": "json",
                "series_id": series_id,
                "realtime_start": vintage.isoformat(),
                "realtime_end": vintage.isoformat(),
                "observation_start": (vintage - timedelta(days=365)).isoformat(),
                "observation_end": vintage.isoformat(),
                "limit": 1000,
                "sort_order": "asc",
            },
        )
        try:
            observations = []
            for item in data["observations"]:
                value = None if item["value"] == "." else float(item["value"])
                if value is not None and not math.isfinite(value):
                    raise ValueError
                observations.append(
                    {
                        "date": date.fromisoformat(item["date"]).isoformat(),
                        "value": value,
                        "realtime_start": date.fromisoformat(item["realtime_start"]).isoformat(),
                        "realtime_end": date.fromisoformat(item["realtime_end"]).isoformat(),
                    }
                )
        except (KeyError, ValueError, TypeError):
            raise AppError(
                "PROVIDER_SCHEMA", "FRED returned an invalid observations response.", 502
            ) from None
        return {
            "source": "FRED",
            "series_id": series_id,
            "vintage": vintage.isoformat(),
            "retrieved_at": now.isoformat(),
            "observations": observations,
            "note": "Context only. Release calendars and vintage validation are required before ML use.",
        }

    def adjusted_history(self, mapping: dict[str, str], currency: Literal["INR"]):
        if not settings().alpha_vantage_api_key:
            raise AppError(
                "ALPHA_VANTAGE_NOT_CONFIGURED",
                "Set ALPHA_VANTAGE_API_KEY with adjusted-daily endpoint entitlement.",
                503,
            )
        records = []
        for instrument, provider_symbol in mapping.items():
            data = self._json(
                "https://www.alphavantage.co/query",
                {
                    "function": "TIME_SERIES_DAILY_ADJUSTED",
                    "symbol": provider_symbol,
                    "outputsize": "full",
                    "apikey": settings().alpha_vantage_api_key,
                },
            )
            if not isinstance(data, dict) or any(
                key in data for key in ("Note", "Information", "Error Message")
            ):
                raise AppError(
                    "ALPHA_VANTAGE_ACCESS",
                    "Alpha Vantage denied data or rate-limited the request. Verify symbol, key, quota, and adjusted-daily entitlement.",
                    502,
                )
            try:
                if data["Meta Data"]["2. Symbol"].upper() != provider_symbol.upper():
                    raise ValueError
                for dt, values in data["Time Series (Daily)"].items():
                    records.append(
                        {
                            "date": dt,
                            "instrument": instrument,
                            "close": float(values["5. adjusted close"]),
                            "currency": currency,
                        }
                    )
            except (KeyError, ValueError, TypeError, AttributeError):
                raise AppError(
                    "PROVIDER_SCHEMA",
                    "Alpha Vantage returned invalid adjusted history or a mismatched symbol.",
                    502,
                ) from None
        return pd.DataFrame(records)


providers = ProviderClient()
