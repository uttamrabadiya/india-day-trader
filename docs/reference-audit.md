# Reference audit and implementation decision

Reviewed on 2026-10-26: [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill).
Scope: README, LICENSE, scanner, risk checker and broker ticket manager. This is a focused design
and license audit, not a complete security audit or verification of upstream trading claims.

## License

The [upstream LICENSE](https://github.com/Jakeschincariol/day-trader-skill/blob/main/LICENSE)
is MIT, identifying Copyright (c) 2026 Jake Schincariol. The inspected LICENSE blob is
`ac31f09aba721de8d139c7bef3d5024421426472`. MIT permits modification and redistribution subject
to retaining its copyright and permission notice in copies or substantial portions.
This independent implementation can use MIT. No upstream source or skill text was copied.
Future reuse must preserve upstream notices; market data and broker services have separate terms.

## Observations

| Area | Evidence | Consequence for this project |
| --- | --- | --- |
| Scope | Eleven AI workflow skills, US symbols and US-specific data sources | Keep modular workflow concept; build Indian identities and research independently |
| Data | Scanner calls Yahoo chart hosts and Nasdaq Trader symbol directories | Use entitled broker data and explicit synthetic fixtures; do not rebrand US feeds as NSE/BSE |
| Risk | US currency thresholds, NYSE calendar, Eastern time and optional PDT checks | Replace with INR, IST and explicit reviewed Indian sessions; import no US regulatory rules |
| Tickets | Fingerprints bind approved tickets to checked orders; ticket module does not itself call a broker | Keep deterministic checks and idempotency together in a locked paper ledger |
| Execution | Upstream workflow uses an external Alpaca connector after approval; paper is a default configuration | Eliminate live submission entirely for this release, including via AI skills |
| Simulation | README describes historical replay and outcome probabilities | Do not inherit unsupported probability or profitability claims; descriptive indicators only |

Inspected source blobs: `trader-scanner/scan.py` at
`3dfc5410f7ac923f7a2ce37eaa2cd32ea4b6f419`, `trader-risk/check.py` at
`2e51047392a491b30d3d49bcb504cd41bcee50fa`, and `trader-broker/ticket.py` at
`721aa2bd73f7973b6ca19d21d047333077a217a7`.

## Decision

Create an original repository rather than fork: the target markets, adapter contracts, cash/position
ledger, risk enforcement and model-neutral skills differ substantially. Preserve acknowledgement
of Jake Schincariol's inspiration without implying affiliation. Do not copy upstream fixture data
or US-specific legal, tax or regulatory claims. Broker data access and any future live-execution
proposal require their own current official documentation and separate review.

## Version 0.2 follow-up

The remaining upstream workflow roles now have original Indian-market counterparts:
supplied-universe scanning, news/RSS digest, ORB entry timing, historical replay and
resampling, durable local alerts, comparable earnings and public promoter/director
disclosures. No upstream implementation, prompts or fixtures were incorporated.
Attribution remains in ACKNOWLEDGEMENTS.md and the feature map. The disclosure tracker
uses a different Indian filing framework; the replay makes no forward-probability claim.
