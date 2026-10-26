"""Synthetic offline session: no API keys and no live orders."""

from datetime import date, datetime
from decimal import Decimal

from india_day_trader.brokers import PaperBroker
from india_day_trader.calendar import Session, TradingCalendar
from india_day_trader.engine import TradingEngine
from india_day_trader.models import Exchange, Instrument, Order, Quote, Side
from india_day_trader.risk import RiskManager

# Supply real reviewed exchange sessions for your own experiments. No holiday guesses.
calendar = TradingCalendar([Session(date(2026, 10, 26))])
broker = PaperBroker(RiskManager(calendar))
engine = TradingEngine(broker)
stock = Instrument(Exchange.NSE, "DEMO")
now = datetime.fromisoformat("2026-10-26T10:00:00+05:30")
order = Order("example-entry", stock, Side.BUY, 10, Decimal("98"), Decimal("106"))
print(engine.submit(order, Quote(stock, Decimal("100"), now), now))

# In an application, poll every open instrument; time exits are not a daemon.
later = now.replace(hour=15, minute=15)
print(engine.manage(Quote(stock, Decimal("104"), later), later))
print("Paper cash INR:", broker.cash)
print("Open positions:", broker.positions)
