"""Deterministic long-only, cash-funded equity entry checks."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from .calendar import TradingCalendar
from .models import Asset, Order, Position, Quote, Side, aware, money


class RiskRejected(ValueError):
    pass


@dataclass(frozen=True)
class RiskLimits:
    max_order_value: Decimal = Decimal("25000")
    max_position_value: Decimal = Decimal("25000")
    max_total_exposure: Decimal = Decimal("50000")
    max_trade_loss: Decimal = Decimal("500")
    max_daily_loss: Decimal = Decimal("1500")
    min_reward_risk: Decimal = Decimal("1.5")
    cash_reserve: Decimal = Decimal("1000")
    max_entries_per_day: int = 5
    max_quote_age: timedelta = timedelta(seconds=30)

    def __post_init__(self) -> None:
        for name in (
            "max_order_value",
            "max_position_value",
            "max_total_exposure",
            "max_trade_loss",
            "max_daily_loss",
            "min_reward_risk",
            "cash_reserve",
        ):
            object.__setattr__(
                self, name, money(getattr(self, name), positive=name != "cash_reserve")
            )
        if type(self.max_entries_per_day) is not int or self.max_entries_per_day < 1:
            raise ValueError("Entry limit must be a positive integer")
        if self.max_quote_age <= timedelta(0):
            raise ValueError("Quote age must be positive")


class RiskManager:
    def __init__(self, calendar: TradingCalendar, limits: RiskLimits | None = None):
        self.calendar, self.limits = calendar, limits if limits is not None else RiskLimits()

    def validate(
        self,
        order: Order,
        quote: Quote,
        now: datetime,
        *,
        price: Decimal,
        fee: Decimal,
        cash: Decimal,
        positions: tuple[Position, ...],
        daily_loss: Decimal,
        entries: int,
        killed: bool,
        fee_bps: Decimal,
        slippage_bps: Decimal,
    ) -> None:
        aware(now)
        limit = self.limits
        if order.instrument != quote.instrument:
            raise RiskRejected("Quote instrument mismatch")
        if order.instrument.asset is not Asset.EQUITY:
            raise RiskRejected("Indices are analysis-only; derivatives are unsupported")
        age = now - quote.at
        if not timedelta(0) <= age <= limit.max_quote_age:
            raise RiskRejected("Stale or future quote")
        try:
            self.calendar.check(now, entry=order.side is Side.BUY)
        except ValueError as exc:
            raise RiskRejected(str(exc)) from exc
        current = next((p for p in positions if p.instrument.key == order.instrument.key), None)
        if current and current.instrument != order.instrument:
            raise RiskRejected("Instrument metadata changed")
        if order.side is Side.SELL:
            if current is None or order.quantity > current.quantity:
                raise RiskRejected("Short selling is disabled")
            return  # A risk-reducing exit remains available after a loss halt or kill switch.
        if killed:
            raise RiskRejected("Kill switch blocks new entries")
        if current:
            raise RiskRejected("One open position per instrument; pyramiding is disabled")
        if entries >= limit.max_entries_per_day:
            raise RiskRejected("Daily entry limit reached")
        if order.stop is None or order.target is None or not order.stop < price < order.target:
            raise RiskRejected("Entry needs stop < simulated fill < target")
        if any(p % order.instrument.tick_size != 0 for p in (order.stop, order.target)):
            raise RiskRejected("Stop and target must respect instrument tick size")
        value = price * order.quantity
        # Reserve entry/exit fees and slippage at the planned stop. This is still not a guarantee.
        stop_fill = order.stop * (Decimal(1) - slippage_bps / 10000)
        loss = (
            (price - stop_fill) * order.quantity
            + fee
            + stop_fill * order.quantity * fee_bps / 10000
        )
        target_fill = order.target * (1 - slippage_bps / 10000)
        reward = (target_fill - price) * order.quantity - fee
        reward -= target_fill * order.quantity * fee_bps / 10000
        if loss > limit.max_trade_loss:
            raise RiskRejected("Per-trade loss budget exceeded")
        if reward / loss < limit.min_reward_risk:
            raise RiskRejected("Reward/risk below minimum after estimated fees")
        reserved = sum(
            (p.entry - p.stop * (1 - slippage_bps / 10000)) * p.quantity
            + p.entry_fee
            + p.stop * p.quantity * fee_bps / 10000
            for p in positions
        )
        if daily_loss + reserved + loss > limit.max_daily_loss:
            raise RiskRejected("Daily loss plus reserved stop risk budget exceeded")
        if value > min(limit.max_order_value, limit.max_position_value):
            raise RiskRejected("Order or position value limit exceeded")
        if sum(p.entry * p.quantity for p in positions) + value > limit.max_total_exposure:
            raise RiskRejected("Total exposure limit exceeded")
        if cash - value - fee < limit.cash_reserve:
            raise RiskRejected("Insufficient unlevered cash after reserve and fees")


def position_size(budget: Decimal, entry: Decimal, stop: Decimal, cash: Decimal) -> int:
    """Indicative whole-share size before costs; submit still enforces every risk rule."""
    budget, entry, stop, cash = (money(x) for x in (budget, entry, stop, cash))
    if stop >= entry:
        raise ValueError("A long stop must be below entry")
    return int(min(budget // (entry - stop), cash // entry))
