"""Durable local alert events. No outbound notifications or execution tools."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from .models import Quote, aware, money
from .research_io import instrument, timestamp


class EventJournal:
    """SQLite uniqueness serializes concurrent pollers; events can be read after restart."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with closing(sqlite3.connect(path, timeout=10)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS events (channel TEXT, identity TEXT, "
                "payload TEXT NOT NULL, PRIMARY KEY(channel, identity))"
            )

    def emit(self, channel: str, identity: str, event: dict) -> bool:
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO events VALUES (?, ?, ?)",
                (channel, identity, json.dumps(event, sort_keys=True)),
            )
            return cursor.rowcount == 1

    def events(self) -> list[dict]:
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            return [
                json.loads(r[0]) for r in db.execute("SELECT payload FROM events ORDER BY rowid")
            ]


def poll(
    alerts: list[dict], quotes: list[Quote], as_of: datetime, journal: EventJournal
) -> list[dict]:
    aware(as_of)
    quote_map = {q.instrument.key: q for q in quotes}
    if len(quote_map) != len(quotes):
        raise ValueError("Duplicate quote instruments")
    # Validate the whole batch before claiming any event.
    prepared, ids = [], set()
    for alert in alerts:
        identity = alert["id"]
        if not isinstance(identity, str) or not identity or identity in ids:
            raise ValueError("Alert ids must be nonempty and unique")
        ids.add(identity)
        kind = alert["kind"]
        item = instrument(alert["instrument"])
        if kind == "time":
            hit = as_of >= timestamp(alert["at"])
        elif kind in {"above", "below"}:
            threshold = money(alert["threshold"])
            quote = quote_map.get(item.key)
            hit = False
            if quote is not None:
                if quote.instrument != item:
                    raise ValueError("Alert quote metadata differs")
                if not timedelta(0) <= as_of - quote.at <= timedelta(seconds=30):
                    raise ValueError("Stale or future alert quote")
                hit = quote.price >= threshold if kind == "above" else quote.price <= threshold
        else:
            raise ValueError("Alert kind must be above, below or time")
        fingerprint = hashlib.sha256(json.dumps(alert, sort_keys=True).encode()).hexdigest()
        if hit:
            prepared.append(
                (
                    fingerprint,
                    {
                        "alert_id": identity,
                        "instrument": item.key,
                        "kind": kind,
                        "fired_at": as_of.isoformat(),
                    },
                )
            )
    return [event for identity, event in prepared if journal.emit("alerts", identity, event)]
