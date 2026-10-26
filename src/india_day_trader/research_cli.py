"""Offline CLI commands for the modular research workflows."""

import json
from datetime import date, time, timedelta
from pathlib import Path

from .alerts import EventJournal, poll
from .calendar import IST, Session
from .entry import check_entry
from .filings import disclosures, earnings
from .models import Quote
from .news import digest, import_rss
from .replay import replay
from .research_io import bars, instrument, timestamp
from .scanner import scan

COMMANDS = ("scan", "news", "entry", "replay", "alerts", "earnings", "disclosures")


def register(commands) -> None:
    for name in COMMANDS:
        parser = commands.add_parser(
            name, help=f"Offline {name} research; see docs/research-tools.md"
        )
        parser.add_argument(
            "--input", type=Path, required=True, help="Normalized research bundle JSON"
        )
        parser.add_argument("--as-of", required=True, help="ISO observation time with timezone")
        if name in {"entry", "replay", "earnings"}:
            parser.add_argument("--instrument", required=True, help="Exchange-qualified identity")
        if name in {"news", "disclosures"}:
            parser.add_argument("--watch", nargs="*", help="Exact exchange-qualified identities")
        if name == "scan":
            parser.add_argument("--min-volume", type=int, default=10000)
        if name == "replay":
            parser.add_argument("--simulations", type=int, default=1000)
            parser.add_argument("--seed", type=int, default=19)
        if name == "news":
            parser.add_argument("--hours", type=int, default=24)
            parser.add_argument(
                "--state", type=Path, help="Optional SQLite journal for unseen items"
            )
        if name == "disclosures":
            parser.add_argument("--days", type=int, default=30)
        if name == "earnings":
            parser.add_argument(
                "--basis", choices=["consolidated", "standalone"], default="consolidated"
            )
            parser.add_argument("--months", type=int, choices=[3, 12], default=3)
        if name == "alerts":
            parser.add_argument(
                "--state", type=Path, required=True, help="Durable local SQLite journal"
            )
    rss = commands.add_parser("import-rss", help="Import a supplied single-company RSS 2.0 export")
    rss.add_argument("--rss", type=Path, required=True)
    rss.add_argument("--exchange", choices=["NSE", "BSE"], required=True)
    rss.add_argument("--symbol", required=True)
    rss.add_argument(
        "--observed-at", required=True, help="Actual feed observation time with offset"
    )


def _sessions(rows: list[dict]) -> list[Session]:
    result = [
        Session(
            date.fromisoformat(r["day"]),
            **{
                field: time.fromisoformat(r[field])
                for field in ("opens", "entry_cutoff", "flatten_at", "closes")
                if field in r
            },
        )
        for r in rows
    ]
    if len({s.day for s in result}) != len(result):
        raise ValueError("Duplicate reviewed sessions")
    return result


def run(args) -> dict:
    if args.command == "import-rss":
        if args.rss.stat().st_size > 2_000_000:
            raise ValueError("RSS file exceeds 2 MB")
        return {
            "news": import_rss(
                args.rss.read_text(encoding="utf-8"),
                instrument({"exchange": args.exchange, "symbol": args.symbol}),
                timestamp(args.observed_at),
            )
        }
    if args.input.stat().st_size > 20_000_000:
        raise ValueError("Research bundle exceeds 20 MB")
    bundle = json.loads(args.input.read_text(encoding="utf-8"))
    at = timestamp(args.as_of)
    if args.command == "news":
        report = digest(
            bundle["news"],
            at,
            hours=args.hours,
            watchlist=set(args.watch) if args.watch is not None else None,
        )
        if args.state:
            journal = EventJournal(args.state)
            report["items"] = [r for r in report["items"] if journal.emit("news", r["id"], r)]
        return report
    if args.command == "earnings":
        return earnings(
            bundle["earnings"], args.instrument, at, basis=args.basis, months=args.months
        )
    if args.command == "disclosures":
        if args.days <= 0:
            raise ValueError("Lookback days must be positive")
        return disclosures(
            bundle["disclosures"],
            at,
            since=at - timedelta(days=args.days),
            watchlist=set(args.watch) if args.watch is not None else None,
        )
    if args.command == "alerts":
        quotes = [
            Quote(instrument(r["instrument"]), r["price"], timestamp(r["at"]))
            for r in bundle["quotes"]
        ]
        return {
            "as_of": at.isoformat(),
            "events": poll(bundle["alerts"], quotes, at, EventJournal(args.state)),
        }
    universe = [(instrument(r["instrument"]), bars(r["bars"])) for r in bundle["universe"]]
    if len({i.key for i, _ in universe}) != len(universe):
        raise ValueError("Duplicate universe instruments")
    sessions = _sessions(bundle["sessions"])
    if args.command == "replay":
        item, data = next(((i, b) for i, b in universe if i.key == args.instrument), (None, None))
        if item is None:
            raise ValueError("Requested instrument absent from supplied universe")
        return replay(item, data, sessions, at, simulations=args.simulations, seed=args.seed)
    session = next((s for s in sessions if s.day == at.astimezone(IST).date()), None)
    if session is None:
        raise ValueError("No reviewed session for observation date")
    if args.command == "scan":
        return scan(universe, at, session, min_volume=args.min_volume)
    item, data = next(((i, b) for i, b in universe if i.key == args.instrument), (None, None))
    if item is None:
        raise ValueError("Requested instrument absent from supplied universe")
    return check_entry(item, data, at, session)
