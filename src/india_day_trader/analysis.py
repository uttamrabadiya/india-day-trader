"""Closed-bar descriptive indicators for equities, NIFTY 50 and NIFTY BANK."""

from datetime import datetime, time
from decimal import Decimal

from .calendar import IST
from .models import Bar, Instrument, aware


def analyze(instrument: Instrument, bars: tuple[Bar, ...], as_of: datetime) -> dict:
    aware(as_of)
    if any(a.end >= b.end for a, b in zip(bars, bars[1:], strict=False)):
        raise ValueError("Bars must be unique and chronologically increasing")
    closed = [bar for bar in bars if bar.end <= as_of]
    if not closed:
        raise ValueError("No completed candles as of requested time")
    closes = [b.close for b in closed]
    last = closed[-1]
    sma = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    rsi = None
    if len(closes) >= 15:
        changes = [b - a for a, b in zip(closes, closes[1:], strict=False)]
        gains = [max(x, Decimal(0)) for x in changes]
        losses = [max(-x, Decimal(0)) for x in changes]
        gain, loss = sum(gains[:14]) / 14, sum(losses[:14]) / 14
        for next_gain, next_loss in zip(gains[14:], losses[14:], strict=True):
            gain, loss = (gain * 13 + next_gain) / 14, (loss * 13 + next_loss) / 14
        rsi = (
            (Decimal(50) if gain == loss == 0 else Decimal(100))
            if not loss
            else (100 - 100 / (1 + gain / loss))
        )
    day = as_of.astimezone(IST).date()
    today = [b for b in closed if b.end.astimezone(IST).date() == day]
    volume = sum(b.volume for b in today)
    vwap = (
        sum((b.high + b.low + b.close) / 3 * b.volume for b in today) / volume if volume else None
    )
    opening = [b for b in today if time(9, 15) < b.end.astimezone(IST).time() <= time(9, 30)]
    complete_range = {b.end.astimezone(IST).time() for b in opening} == {
        time(9, 20),
        time(9, 25),
        time(9, 30),
    } and len(opening) == 3
    or_high = max(b.high for b in opening) if complete_range else None
    or_low = min(b.low for b in opening) if complete_range else None
    return {
        "instrument": instrument.key,
        "as_of": as_of.isoformat(),
        "last_bar_end": last.end.isoformat(),
        "completed_bars": len(closed),
        "close": str(last.close),
        "sma20": str(sma) if sma is not None else None,
        "rsi14": str(rsi) if rsi is not None else None,
        "session_vwap": str(vwap) if vwap is not None else None,
        "opening_range_high": str(or_high) if or_high is not None else None,
        "opening_range_low": str(or_low) if or_low is not None else None,
        "trend": "insufficient_data"
        if sma is None
        else (
            "above_sma20" if last.close > sma else "below_sma20" if last.close < sma else "at_sma20"
        ),
        "caveats": [
            "Descriptive research, not a price forecast.",
            "VWAP needs traded volume; index volume may be unavailable.",
            "Opening range needs three complete five-minute bars from 09:15 IST.",
        ],
    }
