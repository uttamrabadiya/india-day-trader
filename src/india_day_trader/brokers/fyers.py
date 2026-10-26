"""Future FYERS adapter; live execution remains disabled."""

from .base import DisabledLiveBroker


class FyersAdapter(DisabledLiveBroker):
    def quote(self, instrument):
        raise NotImplementedError("FYERS market data integration is planned")

    def history(self, instrument, start, end, interval):
        raise NotImplementedError("FYERS market data integration is planned")
