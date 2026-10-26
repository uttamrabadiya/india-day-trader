# Repository guidance

This is an original MIT research and paper trading toolkit for Indian cash equities.
Keep live trading unavailable: no broker order endpoints, opt-in live flags, leverage,
shorts or derivatives execution. Index instruments are analysis-only.

Use Decimal for money and timezone-aware datetimes. Session decisions use Asia/Kolkata.
Do not guess holidays or treat a candle opening timestamp as its completion timestamp.
Risk/accounting changes need offline behavioral tests. Never use real tokens in tests.

Validate with the README development commands. Edit skill sources under skills/ and sync
both agent directories. Follow CONTRIBUTING.md and preserve third-party license notices.
