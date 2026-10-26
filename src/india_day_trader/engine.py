"""Paper-only orchestration. Poll manage() explicitly; no background scheduler."""

from datetime import datetime
from uuid import uuid4

from .brokers.base import LiveTradingDisabled
from .brokers.paper import PaperBroker
from .calendar import IST
from .models import Fill, Order, Quote, Side


class TradingEngine:
    def __init__(self, broker: PaperBroker, *, mode: str = "paper"):
        if mode != "paper" or type(broker) is not PaperBroker:
            raise LiveTradingDisabled("The engine accepts only the built-in paper broker")
        self.broker = broker

    def submit(self, order: Order, quote: Quote, now: datetime) -> Fill:
        return self.broker.submit(order, quote, now)

    def manage(self, quote: Quote, now: datetime) -> Fill | None:
        """Simulate stop/target/time exits at the observed quote, including gaps."""
        session = self.broker.risk.calendar.check(now, entry=False)
        for position in self.broker.positions:
            if position.instrument.key != quote.instrument.key:
                continue
            if (
                quote.price <= position.stop
                or quote.price >= position.target
                or now.astimezone(IST).time() >= session.flatten_at
            ):
                order = Order(
                    f"exit_{uuid4().hex}", position.instrument, Side.SELL, position.quantity
                )
                return self.submit(order, quote, now)
        return None
