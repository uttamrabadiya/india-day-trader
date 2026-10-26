"""Zerodha Kite Connect v3, GET-only transport with no order endpoint.

Supply environment credentials explicitly via from_env(). No login, token refresh,
redirect following, or credential persistence is performed by this package.
"""

import csv
import io
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..calendar import IST
from ..models import Asset, Bar, Exchange, Instrument, Quote, aware, money
from .base import DisabledLiveBroker


class MarketDataError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ZerodhaAdapter(DisabledLiveBroker):
    INTERVALS = {
        "minute": 1,
        "3minute": 3,
        "5minute": 5,
        "10minute": 10,
        "15minute": 15,
        "30minute": 30,
        "60minute": 60,
    }

    def __init__(self, api_key: str, access_token: str):
        if not api_key or not access_token or any(c.isspace() for c in api_key + access_token):
            raise ValueError("Kite API key and access token are required without whitespace")
        self._authorization = f"token {api_key}:{access_token}"
        self._instruments: dict[str, tuple[Instrument, str]] = {}

    @classmethod
    def from_env(cls) -> "ZerodhaAdapter":
        return cls(os.environ.get("KITE_API_KEY", ""), os.environ.get("KITE_ACCESS_TOKEN", ""))

    def _get(self, path: str, params: list[tuple[str, str]] = ()) -> str:
        # Paths are constructed internally from validated identifiers, never user URLs.
        url = "https://api.kite.trade" + path
        if params:
            url += "?" + urlencode(params)
        request = Request(
            url,
            headers={
                "X-Kite-Version": "3",
                "Authorization": self._authorization,
                "User-Agent": "india-day-trader/0.1.0",
            },
            method="GET",
        )
        try:
            with build_opener(_NoRedirect()).open(request, timeout=15) as response:
                payload = response.read(20_000_001)
            if len(payload) > 20_000_000:
                raise MarketDataError("Kite response exceeds size limit")
            return payload.decode("utf-8")
        except HTTPError as exc:
            # Never echo request headers, tokens, response body, or URL query.
            raise MarketDataError(f"Kite HTTP {exc.code}; verify access or retry later") from None
        except (URLError, TimeoutError, UnicodeDecodeError):
            raise MarketDataError("Kite transport or response encoding failure") from None

    def _data(self, path: str, params=()):
        try:
            payload = json.loads(self._get(path, params), parse_float=Decimal)
            if payload.get("status") != "success":
                raise MarketDataError("Kite returned a non-success response")
            return payload["data"]
        except (ValueError, KeyError, AttributeError, TypeError):
            raise MarketDataError("Malformed Kite JSON response") from None

    def instruments(self, exchange: Exchange) -> tuple[Instrument, ...]:
        if not isinstance(exchange, Exchange):
            raise ValueError("Only NSE and BSE cash-market instruments are supported")
        found = {}
        try:
            for row in csv.DictReader(io.StringIO(self._get(f"/instruments/{exchange.value}"))):
                if row["exchange"] != exchange.value:
                    continue
                kind, segment = row["instrument_type"], row["segment"]
                if kind == "EQ" and segment == exchange.value:
                    asset = Asset.EQUITY
                elif segment == "INDICES":
                    asset = Asset.INDEX
                else:
                    continue
                token = row["instrument_token"]
                if not token.isdigit():
                    raise ValueError("Invalid instrument token")
                tick = money(row["tick_size"], positive=asset is Asset.EQUITY)
                item = Instrument(exchange, row["tradingsymbol"], asset, tick)
                found[item.key] = (item, token)
        except (KeyError, ValueError, TypeError):
            raise MarketDataError("Malformed Kite instrument master") from None
        if not found:
            raise MarketDataError("No supported instruments in Kite master")
        self._instruments = {
            k: v for k, v in self._instruments.items() if v[0].exchange is not exchange
        } | found
        return tuple(item for item, _ in found.values())

    def _resolve(self, instrument: Instrument) -> str:
        if instrument.key not in self._instruments:
            self.instruments(instrument.exchange)
        record = self._instruments.get(instrument.key)
        if record is None or record[0] != instrument:
            raise MarketDataError("Instrument absent or metadata differs; use current master")
        return record[1]

    def quote(self, instrument: Instrument) -> Quote:
        self._resolve(instrument)
        try:
            row = self._data("/quote", [("i", instrument.key)])[instrument.key]
            # Full quotes carry an exchange timestamp; receipt time is never substituted.
            at = datetime.fromisoformat(row["timestamp"])
            if at.tzinfo is None:
                at = at.replace(tzinfo=IST)
            return Quote(instrument, row["last_price"], at)
        except (KeyError, TypeError, ValueError):
            raise MarketDataError("Missing or invalid timestamped Kite quote") from None

    def history(
        self, instrument: Instrument, start: datetime, end: datetime, interval: str = "5minute"
    ) -> tuple[Bar, ...]:
        aware(start)
        aware(end)
        if start >= end or interval not in self.INTERVALS:
            raise ValueError("Use increasing aware dates and a supported intraday interval")
        token = self._resolve(instrument)
        params = [
            ("from", start.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")),
            ("to", end.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")),
        ]
        data = self._data(f"/instruments/historical/{token}/{interval}", params)
        try:
            bars = []
            for row in data["candles"]:
                at = datetime.fromisoformat(row[0])
                aware(at)
                closed_at = at + timedelta(minutes=self.INTERVALS[interval])
                if start <= at and closed_at <= end:
                    bars.append(Bar(closed_at, *row[1:6]))
            if any(a.end >= b.end for a, b in zip(bars, bars[1:], strict=False)):
                raise ValueError("Non-increasing candles")
            return tuple(bars)
        except (KeyError, TypeError, ValueError, IndexError):
            raise MarketDataError("Malformed Kite candles") from None
