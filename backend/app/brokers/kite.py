from datetime import datetime
from zoneinfo import ZoneInfo

from kiteconnect import KiteConnect
from kiteconnect.exceptions import KiteException, TokenException

from app.auth.sessions import BrowserSession, broker_token, set_broker_token
from app.core.config import settings
from app.core.errors import AppError
from app.portfolios.normalize import normalize


def configured():
    return bool(settings().kite_api_key and settings().kite_api_secret)


def new_client():
    if not configured():
        raise AppError(
            "KITE_NOT_CONFIGURED",
            "Configure Kite API credentials on the server to connect an account.",
            503,
        )
    return KiteConnect(api_key=settings().kite_api_key, timeout=15)


class KiteBroker:
    """Allowlisted read methods only. No order interface is exposed."""

    def __init__(self, session: BrowserSession):
        self.session = session

    def _read(self, method: str, **kwargs):
        token = broker_token(self.session)
        if not token:
            raise AppError(
                "KITE_AUTH_REQUIRED", "Connect an authorized Zerodha account first.", 401
            )
        if self.session.user_id:
            from app.jobs.quotas import reserve

            reserve(self.session.database.get_bind(), self.session.owner_id, "kite")
        client = new_client()
        client.set_access_token(token)
        try:
            return getattr(client, method)(**kwargs)
        except TokenException:
            set_broker_token(self.session, None)
            raise AppError(
                "KITE_SESSION_EXPIRED", "Kite session expired. Reconnect your account.", 401
            ) from None
        except (KiteException, OSError, ValueError):
            raise AppError(
                "KITE_UNAVAILABLE", "Kite could not provide the requested read-only data.", 502
            ) from None

    def portfolio(self):
        rows = []
        for item in self._read("holdings"):
            if item.get("discrepancy") or item.get("mtf", {}).get("quantity", 0):
                raise AppError(
                    "UNSUPPORTED_HOLDINGS",
                    "Holdings with broker discrepancies or margin-funded exposure require review and are not supported in Phase 1.",
                )
            if item.get("exchange") not in {"NSE", "BSE"} or item.get("product", "CNC") != "CNC":
                raise AppError(
                    "UNSUPPORTED_HOLDINGS",
                    "Phase 1 supports only NSE/BSE delivery-equity holdings.",
                )
            quantity = (
                item.get("quantity", 0) + item.get("t1_quantity", 0) - item.get("used_quantity", 0)
            )
            if quantity == 0:
                continue
            rows.append(
                {
                    "instrument": f"{item['exchange']}:{item['tradingsymbol']}",
                    "name": item["tradingsymbol"],
                    "sector": "Unknown",
                    "quantity": quantity,
                    "last_price": item["last_price"],
                    "average_price": item["average_price"],
                }
            )
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        return normalize(
            rows,
            mode="kite",
            source="Zerodha Kite Connect / holdings",
            as_of=now.date(),
            retrieved_at=now,
        )

    def positions(self):
        return self._read("positions")

    def margins(self):
        return self._read("margins")

    def instruments(self, exchange: str):
        return self._read("instruments", exchange=exchange)

    def logout(self):
        try:
            return self._read("invalidate_access_token")
        finally:
            set_broker_token(self.session, None)
