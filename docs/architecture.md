# Architecture

`models` defines immutable exchange-qualified instruments, bars, orders, fills and positions.
`analysis` computes descriptive indicators only from completed bars at a supplied observation time.
`calendar` accepts explicit reviewed sessions, including special-session overrides.
`risk` checks entries and permits inventory-reducing exits after an entry halt.

`MarketData` is an independent quote/history protocol. `ZerodhaAdapter` is its first GET-only
implementation. `Broker` describes submission; `PaperBroker` serializes check-and-fill with
a lock and owns cash, positions, per-day counters and idempotent client order IDs.
`TradingEngine` refuses every broker other than the built-in paper broker. Real-broker adapter
submission methods always throw, so no API key or environment variable enables live orders.

Flow: supplied data → normalized bars/quotes → research or proposed Order → locked risk check
→ synthetic paper fill → cash/position update. Skills provide the research workflow around
this core. A skill instruction is not a cryptographic or operating-system enforcement boundary.

Paper fills use the current quote adjusted for adverse slippage and charge configurable fees.
They are immediate full fills. Entry risk reserves stop distance, estimated slippage and fees.
Daily loss uses realized losing exits plus open planned stop risk; winners do not reset it.
Position exposure uses entry cost. Reducing exits require fresh quotes and an open reviewed
session, but are not blocked by entry limits or the kill switch. Short selling is always blocked.

Duplicate client IDs replay the original fill only if the complete immutable order matches.
Changed orders with reused IDs are rejected. Rejected orders do not alter the ledger.
The clock may not move backwards after a fill. Prior-session inventory blocks new entries
until it is closed. The ledger is in memory and cannot detect positions from a previous process.

No AI-generated action bypasses deterministic checks. No background process monitors positions:
call `manage` on each open instrument. A stop gap fills at the quote, not at the planned stop.
Market gaps, process failures and cost/model errors can exceed configured risk budgets.

Future work: durable transactional ledger, session ingestion per exchange, data quality monitoring,
liquidity-aware replay and adapter integrations. These require separate designs and tests.

Version 0.2 research modules are independent of submission: `scanner`, `entry`, `news`,
`replay`, `filings` and `alerts`, with shared normalized inputs in `research_io` and CLI
routing in `research_cli`. Publication and first-observation timestamps bound available
filing/news revisions. Replay uses signal-close/next-open chronology and explicit
intrabar assumptions; its research sizing model is separate from the paper risk policy.
The SQLite event journal stores local alert/news events only, not trading positions.
