import json
from datetime import date

import httpx
import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.integrations.providers import ProviderClient


def provider(payload, status=200):
    return ProviderClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload))
    )


def test_fx_normalization_cache_and_pair_validation():
    client = provider({"date": "2026-01-02", "base": "USD", "quote": "INR", "rate": 85.5})
    first = client.fx("USD", "INR")
    assert first["rate"] == 85.5 and first["source"].startswith("Frankfurter")
    assert not first["cached"]
    assert client.fx("USD", "INR")["cached"]
    with pytest.raises(AppError):
        client.fx("EUR", "INR")


@pytest.mark.parametrize(
    "payload",
    [
        {"date": "bad", "base": "USD", "quote": "INR", "rate": 1},
        {"date": "2026-01-02", "base": "USD", "quote": "INR", "rate": -1},
        {},
    ],
)
def test_malformed_fx(payload):
    with pytest.raises(AppError) as error:
        provider(payload).fx("USD", "INR")
    assert error.value.code == "PROVIDER_SCHEMA"


def test_provider_errors_are_sanitized():
    with pytest.raises(AppError) as error:
        provider({"private": "api-secret"}, 429).fx("USD", "INR")
    assert error.value.code == "PROVIDER_UNAVAILABLE"
    assert "api-secret" not in error.value.message


def test_optional_credentials_are_explicit(client, monkeypatch):
    monkeypatch.setattr(settings(), "fred_api_key", "")
    monkeypatch.setattr(settings(), "alpha_vantage_api_key", "")
    assert client.get("/api/context/macro").json()["error"]["code"] == "FRED_NOT_CONFIGURED"
    response = client.post(
        "/api/history/alpha-vantage",
        json={
            "mapping": {"BSE:ABC": "ABC.BSE"},
            "currency": "INR",
            "currency_and_venue_verified": True,
        },
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ALPHA_VANTAGE_NOT_CONFIGURED"


def test_adjusted_history_uses_adjusted_close_and_correct_symbol(monkeypatch):
    monkeypatch.setattr(settings(), "alpha_vantage_api_key", "private-key")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "Meta Data": {"2. Symbol": "ABC.BSE"},
                "Time Series (Daily)": {
                    "2026-01-02": {"4. close": "100", "5. adjusted close": "50"}
                },
            },
        )

    frame = ProviderClient(transport=httpx.MockTransport(handler)).adjusted_history(
        {"BSE:ABC": "ABC.BSE"}, "INR"
    )
    assert frame.iloc[0].close == 50
    assert frame.iloc[0].instrument == "BSE:ABC"
    assert seen[0].url.params["function"] == "TIME_SERIES_DAILY_ADJUSTED"
    assert seen[0].url.params["outputsize"] == "full"


@pytest.mark.parametrize(
    "payload",
    [
        {"Information": "premium-only private-key"},
        {"Note": "rate limit"},
        {"Error Message": "invalid key"},
        {},
    ],
)
def test_alpha_entitlement_rate_limit_and_schema_errors(monkeypatch, payload):
    monkeypatch.setattr(settings(), "alpha_vantage_api_key", "private-key")
    with pytest.raises(AppError) as error:
        provider(payload).adjusted_history({"BSE:ABC": "ABC.BSE"}, "INR")
    assert error.value.code in ("ALPHA_VANTAGE_ACCESS", "PROVIDER_SCHEMA")
    assert "private-key" not in error.value.message


def test_fred_vintage_and_missing_values_retained(monkeypatch):
    monkeypatch.setattr(settings(), "fred_api_key", "private-key")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "observations": [
                    {
                        "date": "2025-12-31",
                        "value": ".",
                        "realtime_start": "2026-01-02",
                        "realtime_end": "2026-01-02",
                    },
                    {
                        "date": "2026-01-01",
                        "value": "4.2",
                        "realtime_start": "2026-01-02",
                        "realtime_end": "2026-01-02",
                    },
                ]
            },
        )

    result = ProviderClient(transport=httpx.MockTransport(handler)).macro("DGS10", date(2026, 1, 2))
    assert seen[0].url.params["realtime_start"] == "2026-01-02"
    assert seen[0].url.params["realtime_end"] == "2026-01-02"
    assert result["observations"][0]["value"] is None
    assert result["observations"][1]["value"] == 4.2
    assert "private-key" not in json.dumps(result)
