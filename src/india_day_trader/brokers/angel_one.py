"""Future Angel One SmartAPI adapter; live execution remains disabled."""

from .base import DisabledLiveBroker


class AngelOneAdapter(DisabledLiveBroker):
    def quote(self, instrument):
        raise NotImplementedError("Angel One market data integration is planned")

    def history(self, instrument, start, end, interval):
        raise NotImplementedError("Angel One market data integration is planned")
