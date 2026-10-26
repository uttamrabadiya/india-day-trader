"""Opening-range entry timing and an indicative long-only exit plan."""

from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from .calendar import IST, Session
from .models import Asset, Bar, Instrument, aware, money
from .research_io import session_bars


def exit_plan(entry: Decimal, stop: Decimal, tick: Decimal, reward_risk=Decimal(2)) -> dict:
    entry, stop, tick, reward_risk = (money(x) for x in (entry, stop, tick, reward_risk))
    stop = (stop / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
    if not 0 < stop < entry:
        raise ValueError("Long stop must be positive and below entry")
    target = entry + (entry - stop) * reward_risk
    target = (target / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    return {
        "entry": str(entry),
        "stop": str(stop),
        "target": str(target),
        "risk_per_share": str(entry - stop),
        "mode": "paper_proposal",
    }


def check_entry(item: Instrument, data: tuple[Bar, ...], as_of: datetime, session: Session) -> dict:
    aware(as_of)
    if as_of.astimezone(IST).date() != session.day:
        raise ValueError("Entry observation must match the reviewed session date")
    result = {"instrument": item.key, "as_of": as_of.isoformat(), "status": "waiting"}
    wall = as_of.astimezone(IST).time()
    if wall >= session.entry_cutoff:
        return result | {"status": "expired"}
    closed = session_bars(data, session, as_of)
    if len(closed) < 4:
        return result | {"reason": "Need opening range and a later completed candle"}
    if as_of - closed[-1].end > timedelta(minutes=5):
        return result | {"status": "stale"}
    high = max(b.high for b in closed[:3])
    low = min(b.low for b in closed[:3])
    signal = next((b for b in closed[3:] if b.close > high), None)
    if signal is None:
        return result | {"opening_high": str(high), "opening_low": str(low)}
    result |= {
        "status": "triggered" if signal == closed[-1] else "already_triggered",
        "signal_at": signal.end.isoformat(),
        "opening_high": str(high),
        "opening_low": str(low),
    }
    if item.asset is Asset.EQUITY:
        result["plan"] = exit_plan(signal.close, (high + low) / 2, item.tick_size)
    else:
        result["reason"] = "Index signal is analysis-only; no executable plan"
    return result
