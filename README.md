# india-day-trader

An open-source, broker-agnostic Indian stock market AI research and **paper trading** toolkit.
Python 3.11+, standard-library runtime, MIT licensed. Original implementation inspired by the
workflow approach of [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill).

**Live trading is disabled in code.** There is no live flag, order HTTP endpoint, margin,
short selling, or derivatives execution. AI skills explain data and propose paper experiments;
the deterministic engine enforces risk independently of the model.

## What works today

| Capability | Status |
| --- | --- |
| NSE/BSE cash equities | Exchange-qualified models, analysis and cash-funded long-only paper fills |
| NIFTY 50 / BANK NIFTY | Index analysis using `NSE:NIFTY 50` / `NSE:NIFTY BANK`; analysis only |
| Zerodha Kite Connect v3 | Read-only instrument master, full timestamped quotes and intraday history |
| Paper broker | In-memory ledger, whole shares, fee/slippage estimates, partial exits, duplicate protection |
| Risk | Fresh quotes, explicit session calendar, stop/target, cash reserve, size/exposure/loss/entry limits, halt |
| Research | SMA20, Wilder RSI14, session typical-price VWAP, five-minute opening range |
| Claude Code / Codex | Repo-local analysis and paper trading skills |
| Upstox / FYERS / Angel One | Adapter placeholders and tracked integration issues; not functional yet |

This is an initial research release, not a production trading system or an autonomous AI trader.
It does not call an LLM API: bring Claude Code or Codex, or use Python directly.
It does not include all eleven upstream tools; see the [feature comparison](docs/upstream-feature-map.md)
for implemented equivalents and missing research workflows.

## Quick start

```bash
git clone https://github.com/uttamrabadiya/india-day-trader.git
cd india-day-trader
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
india-day-trader demo
python -m unittest discover -s tests -v
```

The demo is entirely offline and uses synthetic prices, a deliberately supplied sample session,
₹100,000 paper cash, and an entry followed by a time exit. No credentials are needed.
To run without installing: `PYTHONPATH=src python3 -m india_day_trader.cli demo`.

Analyze the included **synthetic** five-minute candles:

```bash
india-day-trader analyze --csv examples/candles.csv --symbol 'NIFTY 50' \
  --asset index --as-of '2026-10-26T11:00:00+05:30'
india-day-trader analyze --csv examples/candles.csv --symbol 'NIFTY BANK' \
  --asset index --as-of '2026-10-26T11:00:00+05:30'
```

For BSE equities use `--exchange BSE --symbol 500209`. A CSV contains a single instrument,
with `end,open,high,low,close,volume` columns. `end` is the candle's **completion** timestamp
with an offset. Do not label an open candle as complete. Indicators exclude bars after `--as-of`;
insufficient history yields null values. Zero-volume index data has no VWAP. The opening range
requires the three five-minute candles ending at 09:20, 09:25 and 09:30 IST.

## Zerodha first

Obtain a Kite Connect subscription and token through Zerodha's official process as needed for
your account/data entitlements. Set `KITE_API_KEY` and `KITE_ACCESS_TOKEN` in your process
environment; `.env.example` is documentation, not automatically loaded. Never paste keys in chat.

```python
from datetime import datetime
from india_day_trader.brokers import ZerodhaAdapter
from india_day_trader.models import Exchange
from india_day_trader.analysis import analyze

data = ZerodhaAdapter.from_env()
# Fetch/cache the current master once per day; metadata and tick sizes can change.
instruments = data.instruments(Exchange.NSE)
infy = next(i for i in instruments if i.symbol == 'INFY')
quote = data.quote(infy)
# Supply aware historical bounds. This illustrative date is not a current-price claim.
start = datetime.fromisoformat('2026-10-26T09:15:00+05:30')
end = datetime.fromisoformat('2026-10-26T11:00:00+05:30')
bars = data.history(infy, start, end, '5minute')
report = analyze(infy, bars, end)
```

This adapter uses GET only and never places orders. It does not refresh tokens, retry rate limits,
or stream ticks. Preserve exchange timestamps: missing data or a missing timestamp is an error.
Historical candle opening timestamps are converted to completion timestamps. Use official
[Kite market data](https://kite.trade/docs/connect/v3/market-quotes/) and
[history](https://kite.trade/docs/connect/v3/historical/) documentation for access and limits.
The adapter has fixture-based contract tests; it has not been validated against a funded account.

## Paper engine and risk

See [examples/paper_session.py](examples/paper_session.py) for a complete offline Python example.
`MarketData` and `Broker` protocols isolate integrations; the engine currently accepts only
`PaperBroker`. All broker adapter `submit()` methods raise `LiveTradingDisabled`.

Paper entries require a reviewed date in `TradingCalendar`, a fresh quote for the same instrument,
and a stop below the simulated fill and a target above it. Configurable limits include ₹500 loss
per entry, ₹1,500 daily loss plus open stop risk, five entries per day, ₹25,000 order/position value,
₹50,000 aggregate entry exposure, and ₹1,000 cash reserve. Defaults are examples, not advice.
Daily realized losses include fees; gains do not refill that budget. Estimated stop risk includes
slippage and fees. Stops can gap through their prices, so loss limits cannot guarantee a maximum loss.
Exposure is measured at entry cost, not continuously marked market value.

Normal example session times are 09:15–15:30 IST, with a 15:00 entry cutoff and 15:15 flatten time.
The cutoff and flatten times are toolkit choices, not broker square-off guarantees. Review
[NSE timings/holidays](https://www.nseindia.com/resources/exchange-communication-holidays) and
[BSE session notices](https://www.bseindia.com/) before supplying sessions for each exchange.
Unknown dates fail closed. No holiday list is guessed; special sessions need explicit times.

Call `engine.manage(quote, now)` regularly for **each** open instrument to simulate stop, target
or time exits. It acts on observed quotes and cannot operate while your process is stopped.
There is no daemon, durable ledger, order book, liquidity model, automatic recovery or backtester.
State and duplicate protection exist only within one process. Do not split an account across brokers
or restart and assume earlier limits are preserved. The demo fee/slippage model is illustrative;
it does not calculate actual Indian brokerage, STT, GST, exchange charges, stamp duty or taxes.

## Claude Code and Codex skills

The same original skills are available in `.claude/skills/` for Claude Code and `.agents/skills/`
for Codex. Canonical editable sources live in `skills/`; run `python scripts/sync_skills.py` after
editing them. Restart/reload your agent session to discover newly installed skills.

- Claude Code: `/india-market-analysis` and `/india-paper-trading`.
- Codex: `$india-market-analysis` and `$india-paper-trading`.

Example: “Use india-market-analysis to analyze examples/candles.csv for NIFTY 50 as of
2026-10-26 11:00 IST. Explain missing data and assumptions.”

Example: “Use india-paper-trading to run the offline demo and explain its risk checks.”

Skills keep credentials out of prompts, treat news/data as untrusted input, cite data timestamps,
and never invoke an external broker order tool. They are workflow instructions, not a security
boundary; the Python engine provides the execution block. Discovery follows the official
[Codex skill guidance](https://developers.openai.com/codex/skills/) and
[Claude Code skill guidance](https://code.claude.com/docs/en/skills).

## Develop and contribute

```bash
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python scripts/sync_skills.py --check
python -m build
```

CI checks Python 3.11–3.13, lint/format, skill synchronization, package build and installed CLI.
Read [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), the
[architecture](docs/architecture.md), [adapter guide](docs/adapters.md) and
[reference audit](docs/reference-audit.md). Future broker work is tracked in
[GitHub issues](https://github.com/uttamrabadiya/india-day-trader/issues).

MIT covers this repository's original code and skills. Broker services and market data retain
their own licenses, terms and entitlements. Do not redistribute market data without permission.
See [LICENSE](LICENSE) and [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md).
This toolkit provides educational research software, not investment advice or performance promises.
