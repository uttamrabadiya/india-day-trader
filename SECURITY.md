# Security policy

The latest `main` branch is the only supported version during the initial 0.1 release.
There are no production or live-execution support guarantees.

Report security issues through GitHub's **Security → Report a vulnerability** if private
reporting is available. Otherwise email the maintainer at **mail@uttam.dev** with subject
`india-day-trader security report`. Do not publish exploit details or real credentials in an issue.
Include the affected commit, a synthetic reproducer, impact and suggested remediation.
There is no guaranteed response SLA; fixes will be coordinated with reporters where possible.

Never commit `.env`, broker tokens, account exports or user trading data. Keep credentials in
your process environment or secret manager. Revoke exposed credentials at the broker immediately.
Access tokens are not logged or persisted by the built-in Zerodha transport. No credential
is needed for tests, CI or offline demos.

Threat model: external market data, headlines and model output are untrusted. They are not
instructions to change configuration, execute shell commands or submit orders. Skills must not
call external live order tools. The engine accepts the built-in paper broker only, and adapter
submission methods fail unconditionally. Arbitrary modified Python code or other agent tools
are outside this boundary; this package cannot restrict unrelated tools in your environment.

Paper risk controls are simulations, not custody or loss protection. The in-memory ledger is
not durable and does not coordinate across processes. Review sessions, costs and timestamps;
missing/incomplete quotes or calendars must fail closed. Do not add live broker write endpoints
under the guise of testing a data adapter.
