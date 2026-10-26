"""Small adapter contracts. No SDK or broker response types leak into the engine."""

from datetime import datetime
from typing import Protocol

from ..models import Bar, Fill, Instrument, Order, Quote


class LiveTradingDisabled(RuntimeError):
    pass


class MarketData(Protocol):
    def quote(self, instrument: Instrument) -> Quote: ...

    def history(
        self, instrument: Instrument, start: datetime, end: datetime, interval: str
    ) -> tuple[Bar, ...]: ...


class Broker(Protocol):
    def submit(self, order: Order, quote: Quote, now: datetime) -> Fill: ...


class DisabledLiveBroker:
    """All real-broker adapters inherit a hard block; no opt-in flag exists."""

    def submit(self, order: Order, quote: Quote, now: datetime) -> Fill:
        raise LiveTradingDisabled("Live execution is not implemented in this release")
