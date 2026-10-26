# Upstream workflow coverage

This repository does not bundle or port the upstream eleven tools. These are original,
limited equivalents where stated. Planned items below are not implemented functionality.

| Upstream skill | Initial Indian toolkit coverage |
| --- | --- |
| trader-scanner | Per-instrument indicators only; universe and setup scanning planned |
| trader-news | Not implemented; needs licensed Indian company/news sources |
| trader-entry | No dedicated entry timer; current engine accepts explicit paper proposals |
| trader-exit | Explicit stop/target plans and quote-polled stop/target/time exits |
| trader-timemachine | Not implemented; historical replay/backtesting planned, no forecast probabilities |
| trader-risk | Original deterministic pre-fill risk checks |
| trader-budget | Indicative whole-share sizing plus enforced cash/position limits |
| trader-broker | Original in-memory paper broker; read-only Zerodha data; all live orders disabled |
| trader-alerts | No persistent notification/alert service; manage() only simulates exits while polled |
| trader-analyst | Not implemented; Indian company filings/earnings analysis planned |
| trader-pelosi | No US congressional tracker; any Indian disclosure workflow needs separate design |

No US regulatory rules, disclosure assumptions or data fixtures have been transplanted.
Read [the focused audit](reference-audit.md) for licensing and architecture decisions.
