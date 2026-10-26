import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import Request, Response

from app.core.config import settings
from app.core.errors import AppError

COOKIE = "vantage_session"
TTL = 12 * 60 * 60


@dataclass
class BrowserSession:
    id: str
    expires: float
    kite_token: str | None = None
    state: str | None = None
    state_expires: float = 0


class SessionStore:
    def __init__(self):
        self.items: dict[str, BrowserSession] = {}
        self.lock = threading.RLock()

    def get(self, request: Request, response: Response) -> BrowserSession:
        with self.lock:
            now = time.time()
            for key in [key for key, item in self.items.items() if item.expires <= now]:
                del self.items[key]
            item = self.items.get(request.cookies.get(COOKIE, ""))
            if item is None:
                if len(self.items) >= 2000:
                    raise AppError("SESSION_CAPACITY", "Local session capacity reached.", 503)
                item = BrowserSession(secrets.token_urlsafe(32), now + TTL)
                self.items[item.id] = item
                response.set_cookie(
                    COOKIE,
                    item.id,
                    httponly=True,
                    secure=settings().cookie_secure,
                    samesite="lax",
                    max_age=TTL,
                    path="/",
                )
            return item

    def consume_state(self, item: BrowserSession, supplied: str):
        with self.lock:
            valid = (
                item.state
                and time.time() < item.state_expires
                and secrets.compare_digest(item.state, supplied)
            )
            item.state = None
            item.state_expires = 0
            if not valid:
                raise AppError(
                    "INVALID_AUTH_STATE",
                    "Login state is missing, expired, or invalid. Start a fresh Kite login.",
                    400,
                )


store = SessionStore()


def browser_session(request: Request, response: Response) -> BrowserSession:
    return store.get(request, response)
