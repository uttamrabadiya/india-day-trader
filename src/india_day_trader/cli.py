"""Offline CLI. Network data access is explicit through the Zerodha Python API."""

import argparse
import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from .analysis import analyze
from .brokers.paper import PaperBroker
from .calendar import Session, TradingCalendar
from .engine import TradingEngine
from .models import Asset, Bar, Exchange, Instrument, Order, Quote, Side
from .risk import RiskManager


def demo() -> dict:
    """Synthetic historical session with no credentials or network required."""
    at = datetime.fromisoformat("2026-10-26T10:00:00+05:30")
    instrument = Instrument(Exchange.NSE, "DEMO")
    broker = PaperBroker(RiskManager(TradingCalendar([Session(date(2026, 10, 26))])))
    engine = TradingEngine(broker)
    engine.submit(
        Order("demo-buy", instrument, Side.BUY, 10, Decimal("98"), Decimal("106")),
        Quote(instrument, Decimal("100"), at),
        at,
    )
    exit_at = at.replace(hour=15, minute=15)
    engine.manage(Quote(instrument, Decimal("104"), exit_at), exit_at)
    return {
        "mode": "paper",
        "data": "synthetic",
        "cash_inr": str(broker.cash),
        "open_positions": len(broker.positions),
        "fills": [
            {
                "id": f.client_id,
                "side": f.side.value,
                "quantity": f.quantity,
                "price_inr": str(f.price),
                "fee_inr": str(f.fee),
                "at": f.at.isoformat(),
            }
            for f in broker.fills
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Indian equity analysis and paper-only toolkit")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Run a synthetic offline paper session")
    report = commands.add_parser("analyze", help="Analyze completed candles from a CSV")
    report.add_argument("--csv", type=Path, required=True)
    report.add_argument("--exchange", choices=[e.value for e in Exchange], default="NSE")
    report.add_argument("--symbol", required=True)
    report.add_argument("--asset", choices=[a.value for a in Asset], default="equity")
    report.add_argument("--as-of", required=True, help="ISO timestamp with timezone offset")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = demo()
        else:
            with args.csv.open(newline="", encoding="utf-8") as handle:
                bars = tuple(
                    Bar(
                        datetime.fromisoformat(r["end"]),
                        r["open"],
                        r["high"],
                        r["low"],
                        r["close"],
                        int(r["volume"]),
                    )
                    for r in csv.DictReader(handle)
                )
            result = analyze(
                Instrument(Exchange(args.exchange), args.symbol, Asset(args.asset)),
                bars,
                datetime.fromisoformat(args.as_of),
            )
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
