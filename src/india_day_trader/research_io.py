"""Validated offline research inputs shared by CLI tools. No network side effects."""

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from .calendar import IST, Session
from .models import Asset, Bar, Exchange, Instrument, aware


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    aware(result)
    return result


def number(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid decimal value") from None
    if not result.is_finite():
        raise ValueError("Non-finite research value")
    return result


def source_url(value: str) -> str:
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("A credential-free HTTPS source URL is required")
    return value


def instrument(row: dict) -> Instrument:
    asset = Asset(row.get("asset", "equity"))
    return Instrument(
        Exchange(row["exchange"]),
        row["symbol"],
        asset,
        row.get("tick_size", "0" if asset is Asset.INDEX else "0.05"),
    )


def bars(rows: list[dict]) -> tuple[Bar, ...]:
    result = tuple(
        Bar(timestamp(r["end"]), r["open"], r["high"], r["low"], r["close"], r["volume"])
        for r in rows
    )
    if any(a.end >= b.end for a, b in zip(result, result[1:], strict=False)):
        raise ValueError("Candles must be unique and increasing")
    return result


def available(row: dict, as_of: datetime) -> bool:
    """Publication alone does not prove the data was available to the researcher."""
    aware(as_of)
    published, observed = timestamp(row["published_at"]), timestamp(row["observed_at"])
    if observed < published:
        raise ValueError("observed_at cannot precede publication")
    source_url(row["source_url"])
    return published <= as_of and observed <= as_of


def session_bars(data: tuple[Bar, ...], session: Session, as_of: datetime) -> tuple[Bar, ...]:
    """Require contiguous aligned five-minute candles from the reviewed session open."""
    aware(as_of)
    if any(a.end >= b.end for a, b in zip(data, data[1:], strict=False)):
        raise ValueError("Candles must be unique and increasing")
    start = datetime.combine(session.day, session.opens, IST)
    end = datetime.combine(session.day, session.closes, IST)
    selected = tuple(b for b in data if start < b.end <= min(end, as_of))
    for i, bar in enumerate(selected, 1):
        if bar.end != start + timedelta(minutes=5 * i):
            raise ValueError("Missing or misaligned five-minute session candles")
    return selected
