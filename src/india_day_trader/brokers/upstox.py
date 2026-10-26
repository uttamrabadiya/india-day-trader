"""Future Upstox adapter. Deliberately unavailable; see GitHub integration issue."""

from .base import DisabledLiveBroker


class UpstoxAdapter(DisabledLiveBroker):
    def quote(self, instrument):
        raise NotImplementedError("Upstox market data integration is planned")

    def history(self, instrument, start, end, interval):
        raise NotImplementedError("Upstox market data integration is planned")
