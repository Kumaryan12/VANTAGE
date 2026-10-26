# Data sources

| Source | Purpose | Credentials | Adjustment/limitations |
| --- | --- | --- | --- |
| Versioned demo fixture | Repeatable portfolio/risk development | None | Synthetic INR prices and invented securities; no claims about actual markets |
| Zerodha Kite Connect | Authenticated holdings, positions, margins, instruments | Server API key + secret; interactive authorization | Holdings last prices are valuation observations, never historical candles |
| Uploaded CSV/Parquet | Independent permitted daily history | Session cookie | User attests source/license and split/dividend adjustment; strict schema and complete coverage |
| Alpha Vantage | Optional daily adjusted history | Server API key with endpoint entitlement | Explicit venue/symbol mapping; adjusted endpoint may require paid entitlement; currency verified by importer, not inferred |
| FRED | Macro context (e.g. VIXCLS, DGS10) | Server API key | Observation and vintage dates retained; not automatically safe for historical ML |
| Frankfurter v2 | Currency reference context | None | Daily institutional reference rates; not executable quotes or intraday prices |

## Official references checked 2026-10-26

- [Kite authentication](https://kite.trade/docs/connect/v3/user/), [portfolio](https://kite.trade/docs/connect/v3/portfolio/), [instruments](https://kite.trade/docs/connect/v3/market-quotes/), [plans](https://zerodha.com/products/api/).
- [Alpha Vantage documentation](https://www.alphavantage.co/documentation/) (`TIME_SERIES_DAILY_ADJUSTED`, full output; endpoint access depends on subscription).
- [FRED observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html) and [terms](https://fred.stlouisfed.org/legal/).
- [Frankfurter documentation](https://frankfurter.dev/) (v2 rate endpoint).

Kite Personal access does not imply independent historical or streaming market-data access. The application intentionally never requests those endpoints. Review provider agreements before storing, displaying, or redistributing real data. API keys do not themselves grant redistribution rights.

## Import contract

CSV/Parquet columns: `date,instrument,close,currency`. Instrument is exchange-qualified (e.g. `NSE:INFY`); dates are ISO calendar dates; close is finite and strictly positive; currency must be INR for this phase. Each instrument/date is unique. Supply a source description and `adjustment=split_dividend_adjusted`; unknown/raw histories may be stored for inspection but are ineligible for risk. Imports are limited to 5 MB and 50,000 rows, with a maximum of 50 instruments. No filesystem paths or arbitrary remote URLs are accepted.

Dataset provenance records synthetic status, source, adjustment, observation bounds, retrieval timestamp, and content hash. The demo uses weekdays rather than an exchange holiday calendar and is explicitly synthetic. Real histories must consist of consecutive trading observations according to their permitted source; this phase cannot independently certify exchange holidays or user adjustment assertions.
