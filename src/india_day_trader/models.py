"""Immutable, validated broker-neutral values. Monetary arithmetic uses Decimal."""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum


def money(value: object, *, positive: bool = True) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Expected a valid decimal number") from None
    if not number.is_finite() or (number <= 0 if positive else number < 0):
        raise ValueError(
            "Expected a finite positive number" if positive else "Expected nonnegative"
        )
    return number


def aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware datetime required")


class Exchange(str, Enum):
    NSE = "NSE"
    BSE = "BSE"


class Asset(str, Enum):
    EQUITY = "equity"
    INDEX = "index"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Instrument:
    exchange: Exchange
    symbol: str
    asset: Asset = Asset.EQUITY
    tick_size: Decimal = Decimal("0.05")

    def __post_init__(self) -> None:
        if not isinstance(self.exchange, Exchange) or not isinstance(self.asset, Asset):
            raise ValueError("Use Exchange and Asset enum values")
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9 &_.-]{0,39}", self.symbol):
            raise ValueError("Invalid exchange symbol")
        object.__setattr__(
            self, "tick_size", money(self.tick_size, positive=self.asset is Asset.EQUITY)
        )

    @property
    def key(self) -> str:
        return f"{self.exchange.value}:{self.symbol}"


NIFTY = Instrument(Exchange.NSE, "NIFTY 50", Asset.INDEX, Decimal(0))
BANK_NIFTY = Instrument(Exchange.NSE, "NIFTY BANK", Asset.INDEX, Decimal(0))


@dataclass(frozen=True)
class Quote:
    instrument: Instrument
    price: Decimal
    at: datetime

    def __post_init__(self) -> None:
        aware(self.at)
        object.__setattr__(self, "price", money(self.price))


@dataclass(frozen=True)
class Bar:
    """end is the time the candle is complete, never its opening time."""

    end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def __post_init__(self) -> None:
        aware(self.end)
        for field in ("open", "high", "low", "close"):
            object.__setattr__(self, field, money(getattr(self, field)))
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("Invalid OHLC bounds")
        if type(self.volume) is not int or self.volume < 0:
            raise ValueError("Volume must be a nonnegative integer")


@dataclass(frozen=True)
class Order:
    client_id: str
    instrument: Instrument
    side: Side
    quantity: int
    stop: Decimal | None = None
    target: Decimal | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", self.client_id):
            raise ValueError("Invalid client order id")
        if type(self.quantity) is not int or self.quantity <= 0:
            raise ValueError("Quantity must be positive whole shares")
        if not isinstance(self.side, Side):
            raise ValueError("Invalid side")
        for field in ("stop", "target"):
            if getattr(self, field) is not None:
                object.__setattr__(self, field, money(getattr(self, field)))


@dataclass(frozen=True)
class Position:
    instrument: Instrument
    quantity: int
    entry: Decimal
    stop: Decimal
    target: Decimal
    entry_fee: Decimal
    opened_at: datetime


@dataclass(frozen=True)
class Fill:
    client_id: str
    instrument: Instrument
    side: Side
    quantity: int
    price: Decimal
    fee: Decimal
    at: datetime
