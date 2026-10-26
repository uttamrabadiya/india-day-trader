# Indian research workflows

Version 0.2 adds original counterparts for the remaining upstream roles. All new commands run
offline on supplied exports. They do not subscribe to a news service, scrape exchange endpoints,
fetch arbitrary URLs, send messages or call broker order APIs. Obtain current data through
entitled read-only providers (including the Zerodha adapter) and normalize it to these schemas.

## Runnable examples

Install the package using README. `examples/research.json` contains synthetic data only;
its companies, prices, financials and filings describe no real entity. The example session
is a deliberate demonstration input, not a certified exchange calendar.

```bash
india-day-trader scan --input examples/research.json --as-of '2026-10-26T10:00:00+05:30'
india-day-trader entry --input examples/research.json --instrument NSE:DEMO --as-of '2026-10-26T09:35:00+05:30'
india-day-trader news --input examples/research.json --as-of '2026-10-26T10:00:00+05:30' --watch NSE:DEMO --state state/news.sqlite3
india-day-trader replay --input examples/research.json --instrument NSE:DEMO --as-of '2026-10-26T15:30:00+05:30' --simulations 1000 --seed 19
india-day-trader alerts --input examples/research.json --as-of '2026-10-26T10:00:00+05:30' --state state/alerts.sqlite3
india-day-trader earnings --input examples/research.json --instrument NSE:DEMO --as-of '2026-10-26T10:00:00+05:30'
india-day-trader disclosures --input examples/research.json --as-of '2026-10-26T10:00:00+05:30' --watch NSE:DEMO
```

Without installation, replace `india-day-trader` with `PYTHONPATH=src python3 -m india_day_trader.cli`.
Commands print JSON and exit nonzero on malformed required inputs. Scanner reports instrument-level
data errors in `excluded`. `--watch` matches exact exchange-qualified identities: omit it for all
supplied companies; pass an empty list to match none.

## Bundle schema

Each command reads only its sections. Use strings for monetary values and aware ISO timestamps.
Instrument objects contain `exchange` (`NSE`/`BSE`), `symbol`, optional `asset` (`equity` default or
`index`) and current `tick_size`. Use real instrument metadata rather than guessed default ticks.

| Section | Required contents | Commands |
| --- | --- | --- |
| `sessions` | Reviewed sessions: `day`; optional IST wall times `opens,entry_cutoff,flatten_at,closes` | scan, entry, replay |
| `universe` | `{instrument,bars}` entries; bars have `end,open,high,low,close,volume` | scan, entry, replay |
| `news` | `{instrument,title,source_url,published_at,observed_at}` records | news |
| `quotes` | `{instrument,price,at}` records | alerts |
| `alerts` | `{id,instrument,kind,threshold}` for above/below; `{id,instrument,kind:"time",at}` for time | alerts |
| `earnings` | Source/timestamp/instrument fields plus `period_end,basis,months,revenue_inr,profit_inr,eps_inr` | earnings |
| `disclosures` | Source/timestamp/instrument fields plus `filing_id,record_id,actor,actor_category,transaction,mode,quantity,value_inr,transaction_date` | disclosures |

For scan/entry/replay, `end` is the **completion time of a five-minute candle**. Candles must be
unique, chronological, aligned and contiguous from the reviewed session open. General `analyze`
indicators still accept other intervals. Review sessions for each exchange represented; absent
dates fail closed. Special sessions may override times. Replay flatten times must align to the
five-minute grid. Bundles are capped at 20 MB; partition large universes.

`published_at` is the source release time; `observed_at` is when your collector actually obtained
that exact record/revision. Never backdate observations. Records with either timestamp after
`--as-of` are excluded; observation before publication is invalid. Source links must be HTTPS
without embedded credentials; tools retain them without visiting them. Timestamps do not prove
the truth of the source or the correctness of your normalization. Market-data rights remain separate.

## Scanner and entry timing

`scan` evaluates the supplied universe, applying a minimum close price (₹20 by default) and
cumulative observed session volume (`--min-volume`, default 10,000 shares). Setups are ORB,
above-SMA20 and oversold RSI14. It neither downloads all exchange listings nor guarantees liquidity.
Build universes from current broker masters and entitled candle histories.

`entry` takes the first three completed five-minute candles as a 15-minute opening range. The
first later close above its high is the signal. States are `waiting`, `triggered`, `already_triggered`,
`stale` and `expired`; the latest candle must be at most five minutes old. Future candles are ignored.
A historical signal is not repeated entry permission: track instrument plus `signal_at` when consuming it.
Equity plans use the range midpoint as a stop rounded down to the tick and a 2R target rounded up.
They use the signal close, not a guaranteed fill. Indices get research signals without executable plans.
Any paper order must still pass `TradingEngine` with fresh quotes and its full risk policy.

## News and announcements

`news` filters a lookback window (`--hours`, default 24), deduplicates source/title/time records,
and tags results, corporate actions, governance, disclosures and deals using keywords. Tags can
misclassify negations or ambiguous headlines; they are not sentiment or verified-fact judgments.
Optional `--state` outputs unseen items only using the event journal. Changed article text has a
new identity. This is polling, not an installed background monitor.

NSE's [RSS directory](https://www.nseindia.com/static/rss-feed) lists announcements, financial
results and insider trading feeds, and notes possible delivery delays. Obtain permitted exports
from official exchange/issuer sources or entitled vendors; no automatic coverage is claimed.

```bash
india-day-trader import-rss --rss examples/announcements.xml --exchange NSE --symbol DEMO \
  --observed-at '2026-10-26T10:00:00+05:30' > /tmp/demo-news.json
india-day-trader news --input /tmp/demo-news.json --as-of '2026-10-26T10:00:00+05:30'
```

The local RSS 2.0 file must already be company-filtered. The importer does not infer tickers or
assign a market-wide feed to many companies. It requires title, HTTPS link and timezone-bearing
pubDate, rejects DTD/entity declarations, and caps XML at 2 MB. RSS summaries are not extracted
as financial statement or disclosure transaction facts.

## Historical replay and resampling

`replay` simulates one ORB long per reviewed equity session: signal at a completed close, then
entry at the next contiguous candle's open with adverse slippage. Whole shares use independent
₹100,000 daily cash and ₹500 planned loss budgets including approximate costs; Python callers
can change them. The stop is the range midpoint and the 2R target is recomputed from the entry.
No signal-close fill or portfolio compounding is assumed.

An open below a stop fills at that open. An open above a target fills conservatively at the
target. If both barriers occur intrabar and the open resolves neither, stop wins. Remaining
inventory exits at the flatten candle close. Gapped histories and sessions incomplete through
flatten are reported as skipped, not zero-profit trades. `observed_win_fraction` covers completed
trades only. No-signal days remain in `sessions_reviewed` but not in the trade denominator.

Defaults are 10 bps fees each way and 5 bps adverse slippage each way: not a full Indian charge
schedule or liquidity model. Stop gaps can exceed the planned budget. Replay does **not** run
the paper broker's entire portfolio/exposure/cash-reserve/halt policy; it is research and never submits orders.

Seeded resampling draws observed trade P&Ls with replacement and reports 5/50/95 percentiles
of totals over the same trade count. `--simulations` accepts 1–10,000, `--seed` controls repeats;
work is capped at one million draws. These are not future odds or confidence intervals. IID
resampling ignores serial dependence and regimes; tiny samples provide little information.

## Persistent local alerts

`above`/`below` use inclusive thresholds, not a required crossing from an earlier quote. Future
quotes or quotes older than 30 seconds are rejected; a missing quote leaves the price alert pending.
`time` fires once its aware absolute deadline is reached and needs no quote. Poll explicitly.

IDs must be unique per batch. Inputs are validated before claiming events. SQLite records each
canonical JSON specification once across concurrent pollers and restarts; editing a specification
rearms it. Use date-specific time alerts for each reviewed session. Events are stored before
printing; recover them via `EventJournal(path).events()` if output was interrupted. Exactly-once
local recording is not an external delivery guarantee. No email, Slack or broker action occurs.
The event journal does not make the separate paper trading ledger persistent.

## Earnings

`earnings` compares the latest available period with the exact prior period and year-ago month-end.
Select `--basis consolidated|standalone` and `--months 3|12`. Never mix standalone/consolidated,
quarterly/cumulative figures, accounting definitions or monetary scales. Normalize to INR first:
₹1 lakh = ₹100,000; ₹1 crore = ₹10,000,000. EPS is INR per share.

Reports include revenue/profit/EPS growth, absolute profit change, margin, source links and missing
comparisons. Growth is null for zero/negative prior bases. Latest observed revisions replace earlier
records only after their observation time. Verify restatements and units against source reports.
There is no PDF/XBRL extraction or automatic earnings-calendar ingestion.

## Public disclosures

The counterpart to the US congressional tracker follows supplied public promoter, promoter-group,
director and designated-person filings. It is a different disclosure system, not equivalent legal
obligations or public-official coverage. The [SEBI format circular](https://www.sebi.gov.in/legal/circulars/feb-2021/revised-disclosure-formats-under-regulation-7-of-sebi-prohibition-of-insider-trading-regulations-2015_49068.html)
and NSE feed directory identify relevant categories. No regulatory thresholds, compliance judgments
or reporting deadlines are encoded. Check current official requirements separately when needed.

`filing_id` identifies a filing; `record_id` identifies a stable transaction row within it. Amendments
reuse both with a later observation time. Actor categories: `promoter,promoter_group,director,
designated_person,other`. Transactions: `BUY,SELL,PLEDGE,UNPLEDGE,OTHER`. Modes: `market,off_market,
gift,pledge,other`. Quantities are whole shares; values are INR; transaction dates are `YYYY-MM-DD`.

The tracker deduplicates revisions, filters a publication lookback (`--days`, default 30), reports
calendar-day publication lag and aggregates **market-mode BUY/SELL values only**. Gifts, pledges
and off-market transfers remain visible separately. Delayed/amended filings are not timely trading
signals, proof of misconduct or recommendations. No private information or accounts are accessed.
