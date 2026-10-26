from typing import Protocol

from app.portfolios.schemas import Portfolio


class Broker(Protocol):
    def portfolio(self) -> Portfolio: ...
