"""Deterministic opening-range historical replay, never a future probability forecast."""

from datetime import datetime, timedelta
from decimal import Decimal
from random import Random

from .calendar import IST, Session
from .entry import check_entry, exit_plan
from .models import Asset, Bar, Instrument, aware, money
from .research_io import session_bars


def bootstrap(pnl: list[Decimal], *, simulations: int = 1000, seed: int = 19) -> dict:
    """Resample the observed trades; these percentiles are not forecast confidence bounds."""
    if type(simulations) is not int or not 1 <= simulations <= 10000 or type(seed) is not int:
        raise ValueError("Use 1–10000 simulations and an integer seed")
    if len(pnl) * simulations > 1_000_000:
        raise ValueError("Resampling work exceeds one million trade draws")
    if any(not p.is_finite() for p in pnl):
        raise ValueError("Non-finite P&L sample")
    random = Random(seed)
    samples = (
        sorted(sum((random.choice(pnl) for _ in pnl), Decimal(0)) for _ in range(simulations))
        if pnl
        else []
    )
    return {
        "seed": seed,
        "simulations": simulations,
        "sample_trades": len(pnl),
        "resampled_total_pnl_percentiles_inr": {
            str(p): str(samples[(len(samples) - 1) * p // 100]) for p in (5, 50, 95)
        }
        if samples
        else None,
        "caveat": "IID resampling of supplied outcomes ignores regimes and serial dependence; "
        "not future odds or confidence intervals. Tiny samples are uninformative.",
    }


def replay(
    item: Instrument,
    data: tuple[Bar, ...],
    sessions: list[Session],
    as_of: datetime,
    *,
    cash=Decimal(100000),
    risk_budget=Decimal(500),
    fee_bps=Decimal(10),
    slippage_bps=Decimal(5),
    simulations: int = 1000,
    seed: int = 19,
) -> dict:
    aware(as_of)
    if item.asset is not Asset.EQUITY:
        raise ValueError("Replay execution is cash equities only; indices remain analysis-only")
    cash, risk_budget = money(cash), money(risk_budget)
    fee_bps, slippage_bps = money(fee_bps, positive=False), money(slippage_bps, positive=False)
    if max(fee_bps, slippage_bps) >= 10000:
        raise ValueError("Costs must be below 10000 basis points")
    if len({s.day for s in sessions}) != len(sessions):
        raise ValueError("Duplicate reviewed sessions")
    trades, skipped = [], []
    fee_rate, slip = fee_bps / 10000, slippage_bps / 10000
    for session in sorted(sessions, key=lambda s: s.day):
        flatten = datetime.combine(session.day, session.flatten_at, IST)
        opens = datetime.combine(session.day, session.opens, IST)
        if (flatten - opens).total_seconds() % 300:
            raise ValueError("Replay flatten time must align with five-minute candles")
        try:
            closed = session_bars(data, session, as_of)
        except ValueError as exc:
            skipped.append({"day": str(session.day), "reason": str(exc)})
            continue
        if not closed or closed[-1].end < flatten or as_of < flatten:
            skipped.append(
                {"day": str(session.day), "reason": "Incomplete session through flatten time"}
            )
            continue
        for i, bar in enumerate(closed[:-1]):
            signal = check_entry(item, closed[: i + 1], bar.end, session)
            if signal["status"] != "triggered":
                continue
            next_bar = closed[i + 1]
            entry_at = next_bar.end - timedelta(minutes=5)
            if entry_at.astimezone(IST).time() >= session.entry_cutoff:
                break
            entry = next_bar.open * (1 + slip)
            stop = Decimal(signal["plan"]["stop"])
            if entry <= stop:
                skipped.append(
                    {"day": str(session.day), "reason": "Next open invalidates long stop"}
                )
                break
            target = Decimal(exit_plan(entry, stop, item.tick_size)["target"])
            # Size using adverse stop fill and round-trip costs, without portfolio compounding.
            per_share_risk = entry - stop * (1 - slip) + fee_rate * (entry + stop * (1 - slip))
            quantity = min(
                int(cash // (entry * (1 + fee_rate))), int(risk_budget // per_share_risk)
            )
            if quantity < 1:
                skipped.append(
                    {"day": str(session.day), "reason": "Insufficient cash or risk budget"}
                )
                break
            for exit_bar in closed[i + 1 :]:
                reason, raw_exit = None, None
                if exit_bar.open <= stop:
                    reason, raw_exit = "stop_gap", exit_bar.open
                elif exit_bar.open >= target:
                    reason, raw_exit = "target_gap", target
                elif exit_bar.low <= stop:
                    # Stop first if both stop and target are inside the same candle.
                    reason, raw_exit = "stop", stop
                elif exit_bar.high >= target:
                    reason, raw_exit = "target", target
                elif exit_bar.end >= flatten:
                    reason, raw_exit = "time", exit_bar.close
                if reason is None:
                    continue
                fill = raw_exit * (1 - slip)
                fees = quantity * fee_rate * (entry + fill)
                trades.append(
                    {
                        "day": str(session.day),
                        "signal_at": signal["signal_at"],
                        "entry_at": entry_at.isoformat(),
                        "exit_bar_end": exit_bar.end.isoformat(),
                        "entry": str(entry),
                        "stop": str(stop),
                        "target": str(target),
                        "exit": str(fill),
                        "quantity": quantity,
                        "reason": reason,
                        "fees_inr": str(fees),
                        "pnl_inr": str((fill - entry) * quantity - fees),
                    }
                )
                break
            break  # At most one trade per reviewed session.
    pnl = [Decimal(t["pnl_inr"]) for t in trades]
    return {
        "instrument": item.key,
        "as_of": as_of.isoformat(),
        "trades": trades,
        "skipped": skipped,
        "sessions_reviewed": len(sessions),
        "net_pnl_inr": str(sum(pnl, Decimal(0))),
        "observed_win_fraction": str(Decimal(sum(p > 0 for p in pnl)) / len(pnl)) if pnl else None,
        "resampling": bootstrap(pnl, simulations=simulations, seed=seed),
        "assumptions": [
            "One ORB long per session; signal close then next candle open.",
            "Independent daily cash/risk budgets; not a portfolio equity curve.",
            "Stop-first intrabar ambiguity, adverse slippage, approximate fees.",
            "No liquidity model; complete five-minute data through flatten required.",
            "Historical sample outcomes are not probabilities of future returns.",
            "Research simulation does not run the paper broker's full risk policy.",
        ],
    }
