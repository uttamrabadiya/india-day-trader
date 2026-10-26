# Adding broker data adapters

Implement `MarketData.quote(instrument)` and `history(instrument, start, end, interval)`.
Normalize to immutable shared models. Inherit `DisabledLiveBroker` to preserve the live order block.
Upstox, FYERS and Angel One modules are explicit placeholders; do not mistake them for working APIs.

1. Confirm the current official authentication and data-entitlement requirements. Use environment
   credentials, bounded request timeouts and fixed HTTPS hosts. Never log raw auth errors or tokens.
2. Map cash-market instruments by exchange plus symbol, keeping broker tokens private to the
   adapter. Refresh masters daily; do not hardcode tokens, tick sizes or derivative lots.
3. Preserve source quote timestamps. Reject missing timestamps, absent instruments, invalid
   OHLC, non-finite numbers and ambiguous timezone values. Never stamp stale data as fresh.
4. Convert candle opening times to completion times with the real interval and omit incomplete
   candles. Keep histories chronological and unique. Explain coverage, holidays and gaps.
5. Add offline synthetic fixtures for NSE, BSE, NIFTY 50 and NIFTY BANK; cover missing symbols,
   expired auth, rate limits, malformed responses, timezones and derivative filtering.
6. Provide read-only usage docs, dependency/license review and cost/rate-limit notes. Never
   require a funded account to run CI. Add no broker write endpoints or execution SDK wrappers.

Zerodha currently supports intraday intervals through 60 minutes, not daily candles or websockets.
It caps response size, sets a timeout and disallows redirects to prevent forwarding credentials.
HTTP failures are redacted and surfaced without automatic retry. Callers must handle pacing,
market-data entitlements and explicit recovery. There is no guarantee of compatibility until
validated with entitled broker accounts; current tests use documented response shapes.

Official starting points (verify these again when implementing):

- [Kite Connect](https://kite.trade/docs/connect/v3/)
- [Upstox developer documentation](https://upstox.com/developer/api-documentation/)
- [FYERS API](https://myapi.fyers.in/docsv3)
- [Angel One SmartAPI](https://smartapi.angelone.in/docs)
