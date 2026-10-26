"""Scan a supplied NSE/BSE universe without guessing listings or data entitlements."""

from datetime import datetime
from decimal import Decimal

from .analysis import analyze
from .calendar import Session
from .entry import check_entry
from .models import Bar, Instrument, aware, money
from .research_io import session_bars


def scan(
    universe: list[tuple[Instrument, tuple[Bar, ...]]],
    as_of: datetime,
    session: Session,
    *,
    min_price=Decimal(20),
    min_volume: int = 10000,
) -> dict:
    aware(as_of)
    min_price = money(min_price)
    if type(min_volume) is not int or min_volume < 0:
        raise ValueError("min_volume must be a nonnegative integer")
    seen, candidates, excluded = set(), [], []
    for item, data in universe:
        if item.key in seen:
            raise ValueError("Duplicate instrument in universe")
        seen.add(item.key)
        try:
            report = analyze(item, data, as_of)
            entry = check_entry(item, data, as_of, session)
            today = session_bars(data, session, as_of)
            if Decimal(report["close"]) < min_price or sum(b.volume for b in today) < min_volume:
                excluded.append(
                    {"instrument": item.key, "reason": "Price or session volume filter"}
                )
                continue
            setups = []
            if entry["status"] in {"triggered", "already_triggered"}:
                setups.append("opening_range_breakout")
            if report["trend"] == "above_sma20":
                setups.append("above_sma20")
            if report["rsi14"] is not None and Decimal(report["rsi14"]) < 30:
                setups.append("oversold_rsi14")
            candidates.append(
                {"instrument": item.key, "setups": setups, "analysis": report, "entry": entry}
            )
        except ValueError as exc:
            excluded.append({"instrument": item.key, "reason": str(exc)})
    return {
        "as_of": as_of.isoformat(),
        "scanned": len(seen),
        "candidates": candidates,
        "excluded": excluded,
        "coverage": "Supplied universe only; not all exchange listings",
    }
