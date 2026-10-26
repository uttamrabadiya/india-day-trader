"""Atomic in-memory paper ledger; synthetic fills, never exchange orders."""

from datetime import date, datetime
from decimal import Decimal
from threading import RLock

from ..calendar import IST
from ..models import Fill, Order, Position, Quote, Side, aware, money
from ..risk import RiskManager, RiskRejected


class PaperBroker:
    def __init__(
        self,
        risk: RiskManager,
        cash: Decimal = Decimal("100000"),
        *,
        fee_bps: Decimal = Decimal("10"),
        slippage_bps: Decimal = Decimal("5"),
    ):
        self.risk = risk
        self._cash = money(cash)
        self.fee_bps = money(fee_bps, positive=False)
        self.slippage_bps = money(slippage_bps, positive=False)
        if self.slippage_bps >= 10000 or self.fee_bps >= 10000:
            raise ValueError("Costs must be below 10000 basis points")
        self._positions: dict[str, Position] = {}
        self._fills: dict[str, tuple[Order, Fill]] = {}
        self._days: dict[date, tuple[int, Decimal]] = {}
        self._killed = False
        self._last_at: datetime | None = None
        self._lock = RLock()

    @property
    def cash(self) -> Decimal:
        with self._lock:
            return self._cash

    @property
    def positions(self) -> tuple[Position, ...]:
        with self._lock:
            return tuple(self._positions.values())

    @property
    def fills(self) -> tuple[Fill, ...]:
        with self._lock:
            return tuple(f for _, f in self._fills.values())

    def halt_entries(self) -> None:
        with self._lock:
            self._killed = True

    def submit(self, order: Order, quote: Quote, now: datetime) -> Fill:
        with self._lock:
            aware(now)
            previous = self._fills.get(order.client_id)
            if previous:
                if previous[0] != order:
                    raise RiskRejected("Client id reused for a different order")
                return previous[1]  # Idempotent within this ledger, even across sessions.
            if self._last_at is not None and now < self._last_at:
                raise RiskRejected("Paper clock cannot move backwards")
            day = now.astimezone(IST).date()
            entries, daily_loss = self._days.get(day, (0, Decimal(0)))
            if order.side is Side.BUY and any(
                p.opened_at.astimezone(IST).date() < day for p in self._positions.values()
            ):
                raise RiskRejected("Unclosed prior-session positions: flatten before new entries")
            sign = 1 if order.side is Side.BUY else -1
            price = quote.price * (1 + sign * self.slippage_bps / 10000)
            fee = price * order.quantity * self.fee_bps / 10000
            self.risk.validate(
                order,
                quote,
                now,
                price=price,
                fee=fee,
                cash=self._cash,
                positions=self.positions,
                daily_loss=daily_loss,
                entries=entries,
                killed=self._killed,
                fee_bps=self.fee_bps,
                slippage_bps=self.slippage_bps,
            )
            key = order.instrument.key
            if order.side is Side.BUY:
                self._cash -= price * order.quantity + fee
                assert order.stop is not None and order.target is not None
                self._positions[key] = Position(
                    order.instrument, order.quantity, price, order.stop, order.target, fee, now
                )
                entries += 1
            else:
                position = self._positions[key]
                entry_fee = position.entry_fee * order.quantity / position.quantity
                pnl = (price - position.entry) * order.quantity - fee - entry_fee
                daily_loss += max(Decimal(0), -pnl)  # Winners do not replenish the loss budget.
                self._cash += price * order.quantity - fee
                remaining = position.quantity - order.quantity
                if remaining:
                    self._positions[key] = Position(
                        position.instrument,
                        remaining,
                        position.entry,
                        position.stop,
                        position.target,
                        position.entry_fee - entry_fee,
                        position.opened_at,
                    )
                else:
                    del self._positions[key]
            fill = Fill(
                order.client_id, order.instrument, order.side, order.quantity, price, fee, now
            )
            self._days[day] = (entries, daily_loss)
            self._last_at = now
            self._fills[order.client_id] = (order, fill)
            return fill
