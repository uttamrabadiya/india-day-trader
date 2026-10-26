# Contributing

Open an issue describing a bug or proposed feature before substantial changes. Small fixes
can go directly to a pull request. Include expected behavior, input fixtures, validation and
limitations. Use synthetic data or fixtures you have permission to redistribute.

Use Python 3.11+ and install `python -m pip install -e '.[dev]'`. Run the README development
checks before opening a PR. Add behavioral tests for accounting, risk or adapter changes;
all tests must run offline without real keys or broker accounts. Keep runtime dependencies
small and optional broker dependencies isolated.

Maintain Decimal monetary arithmetic, aware timestamps and exchange-qualified identities.
Never bypass risk checks or add a configuration switch that enables live execution. This
release is paper-only; any future execution proposal needs its own explicit design review
and is outside the current adapter integration scope.

Adapters normalize broker responses at their boundary and preserve source timestamps.
Do not scrape exchange endpoints to bypass access controls or data terms. See
[docs/adapters.md](docs/adapters.md). Do not add credentials to fixtures, issues, logs or PRs.

Edit skills under `skills/`, then run `python scripts/sync_skills.py` to update both agent
discovery directories. Keep skills provider-neutral and keep safety-critical arithmetic in Python.

By contributing you agree to license your original contributions under the repository's MIT
license. Record third-party provenance and retain required notices. Treat contributors respectfully;
explain disagreements with examples and evidence. Report vulnerabilities privately via SECURITY.md.
