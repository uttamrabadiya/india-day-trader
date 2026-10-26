# Upstream workflow coverage

Version 0.2 provides original Indian-market counterparts for all eleven upstream roles.
This is workflow coverage, not a port or exact feature-parity claim. New research commands
use supplied exports; they do not claim automatic exchange-wide coverage or live delivery.

| Upstream skill | Indian counterpart | Boundary |
| --- | --- | --- |
| trader-scanner | `scan`, `india-scanner` | Supplied universe, price/volume filters, ORB/SMA/RSI; no full-listing download |
| trader-news | `news`, `import-rss`, `india-news` | Export/RSS digest, keyword tags, durable optional dedup; no subscription |
| trader-entry | `entry`, `india-entry` | Reviewed-session, closed-five-minute ORB timing; no daemon |
| trader-exit | `entry.exit_plan`, existing `engine.manage` | Paper stop/target proposals and polled exits; no broker bracket orders |
| trader-timemachine | `replay`, `india-replay` | Next-open history replay, costs/gaps and seeded P&L resampling; no future odds |
| trader-risk | `RiskManager`, `india-paper-trading` | Deterministic pre-fill paper risk checks |
| trader-budget | `position_size` and paper cash limits | Indicative sizing before costs; actual synthetic fills still checked |
| trader-broker | Paper broker, read-only Zerodha | In-memory trading ledger; all live submission disabled |
| trader-alerts | `alerts`, `india-alerts` | Persistent local quote/time events; no outbound messaging or scheduler |
| trader-analyst | `earnings`, `india-earnings` | Comparable source-linked financial periods; no PDF/XBRL extraction |
| trader-pelosi | `disclosures`, `india-disclosures` | Public promoter/director/designated-person filings; different legal framework |

Read [research-tools.md](research-tools.md) for runnable examples, schemas and assumptions.
The original `india-market-analysis` skill supports general indicator research, while
`india-paper-trading` covers budget, risk, broker and exit workflows.

Inspiration: [Jake Schincariol's day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill),
MIT. No upstream source, skill text or data fixtures were copied. See
[ACKNOWLEDGEMENTS.md](../ACKNOWLEDGEMENTS.md) and [the audit](reference-audit.md).
