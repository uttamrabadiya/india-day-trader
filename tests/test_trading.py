import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal as D

from india_day_trader.brokers import LiveTradingDisabled, PaperBroker, ZerodhaAdapter
from india_day_trader.brokers.angel_one import AngelOneAdapter
from india_day_trader.brokers.fyers import FyersAdapter
from india_day_trader.brokers.upstox import UpstoxAdapter
from india_day_trader.calendar import Session, TradingCalendar
from india_day_trader.engine import TradingEngine
from india_day_trader.models import BANK_NIFTY, NIFTY, Exchange, Instrument, Order, Quote, Side
from india_day_trader.risk import RiskLimits, RiskManager, RiskRejected, position_size

AT = datetime.fromisoformat("2026-10-26T10:00:00+05:30")
STOCK = Instrument(Exchange.NSE, "INFY")


class TradingTests(unittest.TestCase):
    def setUp(self):
        self.calendar = TradingCalendar([Session(date(2026, 10, 26)), Session(date(2026, 10, 27))])
        self.broker = PaperBroker(RiskManager(self.calendar), fee_bps=D(0), slippage_bps=D(0))
        self.order = Order("buy-1", STOCK, Side.BUY, 10, D(98), D(106))
        self.quote = Quote(STOCK, D(100), AT)

    def submit(self, order=None, quote=None, now=AT):
        return self.broker.submit(order or self.order, quote or self.quote, now)

    def test_cash_and_partial_exit_accounting(self):
        self.submit()
        self.assertEqual(self.broker.cash, D(99000))
        self.submit(Order("sell-1", STOCK, Side.SELL, 4), Quote(STOCK, D(103), AT))
        self.assertEqual(self.broker.cash, D(99412))
        self.assertEqual(self.broker.positions[0].quantity, 6)

    def test_idempotent_under_concurrent_retry(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.submit(), range(20)))
        self.assertTrue(all(r == results[0] for r in results))
        self.assertEqual(len(self.broker.fills), 1)
        self.assertEqual(self.broker.cash, D(99000))

    def test_mutated_duplicate_id_is_rejected(self):
        self.submit()
        with self.assertRaisesRegex(RiskRejected, "reused"):
            self.submit(replace(self.order, quantity=11))

    def test_kill_switch_blocks_entries_but_allows_exit(self):
        self.submit()
        self.broker.halt_entries()
        other = Instrument(Exchange.BSE, "500209")
        with self.assertRaisesRegex(RiskRejected, "Kill"):
            self.submit(
                replace(self.order, client_id="other", instrument=other), Quote(other, D(100), AT)
            )
        self.submit(Order("exit", STOCK, Side.SELL, 10))
        self.assertFalse(self.broker.positions)

    def test_bad_quotes_do_not_mutate_ledger(self):
        for delta in [timedelta(seconds=-31), timedelta(seconds=1)]:
            with self.assertRaisesRegex(RiskRejected, "Stale or future"):
                self.submit(quote=replace(self.quote, at=AT + delta))
        with self.assertRaisesRegex(RiskRejected, "mismatch"):
            self.submit(quote=Quote(Instrument(Exchange.BSE, "INFY"), D(100), AT))
        self.assertEqual(self.broker.cash, D(100000))
        self.assertFalse(self.broker.fills)

    def test_market_windows_and_unknown_calendar(self):
        for at in [
            AT.replace(hour=9, minute=14),
            AT.replace(hour=15),
            AT.replace(day=28),
            AT.replace(hour=15, minute=30),
        ]:
            with self.assertRaises(RiskRejected):
                self.submit(quote=replace(self.quote, at=at), now=at)

    def test_exit_allowed_after_entry_cutoff(self):
        self.submit()
        at = AT.replace(hour=15, minute=10)
        self.submit(Order("exit", STOCK, Side.SELL, 10), replace(self.quote, at=at), at)
        self.assertFalse(self.broker.positions)

    def test_short_and_oversell_rejected(self):
        with self.assertRaisesRegex(RiskRejected, "Short"):
            self.submit(Order("short", STOCK, Side.SELL, 1))
        self.submit()
        with self.assertRaisesRegex(RiskRejected, "Short"):
            self.submit(Order("oversell", STOCK, Side.SELL, 11))

    def test_indices_analysis_only(self):
        for instrument in (NIFTY, BANK_NIFTY):
            with self.assertRaisesRegex(RiskRejected, "analysis-only"):
                self.submit(
                    replace(self.order, instrument=instrument), Quote(instrument, D(100), AT)
                )

    def test_stops_targets_and_ticks(self):
        for stop, target in [
            (None, D(106)),
            (D(101), D(106)),
            (D(98), D(99)),
            (D("98.01"), D(106)),
            (D(98), D(101)),
        ]:
            with self.assertRaises(RiskRejected):
                self.submit(replace(self.order, stop=stop, target=target))

    def test_risk_limits(self):
        for change in [
            dict(max_order_value=D(999)),
            dict(max_position_value=D(999)),
            dict(max_trade_loss=D(19)),
            dict(max_total_exposure=D(999)),
            dict(max_daily_loss=D(19)),
            dict(cash_reserve=D(99500)),
        ]:
            self.broker = PaperBroker(
                RiskManager(self.calendar, replace(RiskLimits(), **change)),
                fee_bps=D(0),
                slippage_bps=D(0),
            )
            with self.assertRaises(RiskRejected):
                self.submit()

    def test_daily_entry_limit_and_reset(self):
        self.broker = PaperBroker(
            RiskManager(self.calendar, replace(RiskLimits(), max_entries_per_day=1)),
            fee_bps=D(0),
            slippage_bps=D(0),
        )
        self.submit()
        self.submit(Order("exit", STOCK, Side.SELL, 10))
        with self.assertRaisesRegex(RiskRejected, "entry limit"):
            self.submit(replace(self.order, client_id="second"))
        tomorrow = AT + timedelta(days=1)
        self.submit(
            replace(self.order, client_id="tomorrow"), replace(self.quote, at=tomorrow), tomorrow
        )

    def test_daily_reserved_risk_is_cumulative(self):
        self.broker = PaperBroker(
            RiskManager(self.calendar, replace(RiskLimits(), max_daily_loss=D(30))),
            fee_bps=D(0),
            slippage_bps=D(0),
        )
        self.submit()
        other = Instrument(Exchange.BSE, "500209")
        with self.assertRaisesRegex(RiskRejected, "reserved"):
            self.submit(
                replace(self.order, client_id="two", instrument=other), Quote(other, D(100), AT)
            )

    def test_realized_loss_stops_entries_but_not_exits(self):
        self.broker = PaperBroker(
            RiskManager(self.calendar, replace(RiskLimits(), max_daily_loss=D(30))),
            fee_bps=D(0),
            slippage_bps=D(0),
        )
        self.submit()
        self.submit(Order("exit", STOCK, Side.SELL, 10), replace(self.quote, price=D(95)))
        with self.assertRaisesRegex(RiskRejected, "Daily loss"):
            self.submit(replace(self.order, client_id="second"))

    def test_fee_slippage_and_gap_loss(self):
        self.broker = PaperBroker(RiskManager(self.calendar), fee_bps=D(10), slippage_bps=D(5))
        fill = self.submit()
        self.assertEqual(fill.price, D("100.05"))
        self.assertEqual(fill.fee, D("1.0005"))
        exit_fill = TradingEngine(self.broker).manage(replace(self.quote, price=D(95)), AT)
        self.assertEqual(exit_fill.price, D("94.9525"))
        self.assertLess(self.broker.cash, D(99950))

    def test_fees_included_in_risk_budget(self):
        self.broker = PaperBroker(
            RiskManager(self.calendar, replace(RiskLimits(), max_trade_loss=D(20))),
            fee_bps=D(10),
            slippage_bps=D(5),
        )
        with self.assertRaisesRegex(RiskRejected, "Per-trade"):
            self.submit()

    def test_poll_flatten(self):
        engine = TradingEngine(self.broker)
        self.submit()
        self.assertIsNone(engine.manage(self.quote, AT))
        at = AT.replace(hour=15, minute=15)
        self.assertEqual(engine.manage(replace(self.quote, at=at), at).side, Side.SELL)
        self.assertFalse(self.broker.positions)

    def test_prior_session_positions_block_entry(self):
        self.submit()
        tomorrow = AT + timedelta(days=1)
        with self.assertRaisesRegex(RiskRejected, "prior-session"):
            self.submit(
                replace(self.order, client_id="next"), replace(self.quote, at=tomorrow), tomorrow
            )
        self.submit(Order("exit", STOCK, Side.SELL, 10), replace(self.quote, at=tomorrow), tomorrow)

    def test_pyramiding_rejected(self):
        self.submit()
        with self.assertRaisesRegex(RiskRejected, "pyramiding"):
            self.submit(replace(self.order, client_id="add"))

    def test_backwards_clock_rejected(self):
        self.submit()
        at = AT - timedelta(seconds=1)
        with self.assertRaisesRegex(RiskRejected, "backwards"):
            self.submit(Order("exit", STOCK, Side.SELL, 10), replace(self.quote, at=at), at)

    def test_live_modes_and_adapters_hard_block(self):
        with self.assertRaises(LiveTradingDisabled):
            TradingEngine(self.broker, mode="live")
        for adapter in [
            ZerodhaAdapter("key", "token"),
            UpstoxAdapter(),
            FyersAdapter(),
            AngelOneAdapter(),
        ]:
            with self.assertRaises(LiveTradingDisabled):
                adapter.submit(self.order, self.quote, AT)
            with self.assertRaises(LiveTradingDisabled):
                TradingEngine(adapter)

    def test_sizing_and_bad_values(self):
        self.assertEqual(position_size(D(50), D(100), D(98), D(1000)), 10)
        for value in ("NaN", "Infinity", "-1", "0"):
            with self.assertRaises(ValueError):
                Quote(STOCK, D(value), AT)
        for qty in (True, 0, -1, 1.5):
            with self.assertRaises(ValueError):
                replace(self.order, quantity=qty)
        with self.assertRaises(ValueError):
            replace(self.quote, at=AT.replace(tzinfo=None))


if __name__ == "__main__":
    unittest.main()
