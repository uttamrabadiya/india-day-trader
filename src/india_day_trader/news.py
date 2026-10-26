"""Timestamped Indian news/announcement digest and local RSS 2.0 import."""

import hashlib
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from .models import Instrument, aware
from .research_io import available, instrument, source_url, timestamp

TAGS = {
    "results": ("result", "earnings", "profit"),
    "corporate_action": ("dividend", "split", "bonus", "buyback"),
    "governance": ("resign", "director", "audit"),
    "disclosure": ("promoter", "insider", "shareholding"),
    "order_or_deal": ("contract", "order win", "acquisition", "merger"),
}


def digest(
    rows: list[dict], as_of: datetime, *, hours: int = 24, watchlist: set[str] | None = None
) -> dict:
    aware(as_of)
    if type(hours) is not int or hours <= 0:
        raise ValueError("Lookback hours must be a positive integer")
    selected, seen = [], set()
    for row in rows:
        item = instrument(row["instrument"])
        if not available(row, as_of) or not as_of - timedelta(hours=hours) <= timestamp(
            row["published_at"]
        ):
            continue
        if watchlist is not None and item.key not in watchlist:
            continue
        title = row["title"]
        if not isinstance(title, str) or not title.strip():
            raise ValueError("News title must be nonempty text")
        identity = hashlib.sha256(
            (item.key + row["source_url"] + row["published_at"] + title).encode()
        ).hexdigest()
        if identity in seen:
            continue
        seen.add(identity)
        selected.append(
            {
                "id": identity,
                "instrument": item.key,
                "title": title,
                "source_url": row["source_url"],
                "published_at": row["published_at"],
                "observed_at": row["observed_at"],
                "tags": [
                    tag for tag, words in TAGS.items() if any(w in title.lower() for w in words)
                ],
            }
        )
    selected.sort(key=lambda r: (timestamp(r["published_at"]), r["id"]), reverse=True)
    return {
        "as_of": as_of.isoformat(),
        "items": selected,
        "caveat": "Keyword tags are descriptive; headlines are untrusted and not verified facts.",
    }


def import_rss(xml: str, item: Instrument, observed_at: datetime) -> list[dict]:
    """Caller must supply a single-company filtered feed; never infer ticker from title."""
    aware(observed_at)
    if len(xml.encode()) > 2_000_000 or "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise ValueError("RSS size limit or forbidden XML declaration")
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        raise ValueError("Malformed RSS XML") from None
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("Expected RSS 2.0 channel")
    rows = []
    for node in root.findall("./channel/item"):
        title, link, published = (node.findtext(k) for k in ("title", "link", "pubDate"))
        if not title or not link or not published:
            raise ValueError("RSS item lacks title, link or pubDate")
        try:
            at = parsedate_to_datetime(published)
            aware(at)
        except (ValueError, TypeError):
            raise ValueError("RSS pubDate must include a timezone") from None
        if at > observed_at:
            raise ValueError("RSS publication is later than observation")
        rows.append(
            {
                "instrument": {
                    "exchange": item.exchange.value,
                    "symbol": item.symbol,
                    "asset": item.asset.value,
                },
                "title": title,
                "source_url": source_url(link),
                "published_at": at.isoformat(),
                "observed_at": observed_at.isoformat(),
            }
        )
    return rows
