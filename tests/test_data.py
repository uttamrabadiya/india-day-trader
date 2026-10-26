import json
import unittest
from datetime import datetime, timedelta
from decimal import Decimal as D
from unittest.mock import patch
from urllib.error import HTTPError

from india_day_trader.analysis import analyze
from india_day_trader.brokers.zerodha import MarketDataError, ZerodhaAdapter
from india_day_trader.cli import demo, main
from india_day_trader.models import BANK_NIFTY, NIFTY, Bar, Exchange, Instrument

AT = datetime.fromisoformat("2026-10-26T09:15:00+05:30")
STOCK = Instrument(Exchange.NSE, "INFY")
MASTER = "instrument_token,tradingsymbol,tick_size,instrument_type,segment,exchange\n" + (
    "408065,INFY,0.05,EQ,NSE,NSE\n"
    "256265,NIFTY 50,0,EQ,INDICES,NSE\n"
    "123,INFY26OCTFUT,0.05,FUT,NFO-FUT,NFO\n"
)


class DataTests(unittest.TestCase):
    def setUp(self):
        self.adapter = ZerodhaAdapter("test-key", "test-token")

    def master(self):
        with patch.object(self.adapter, "_get", return_value=MASTER):
            return self.adapter.instruments(Exchange.NSE)

    def test_master_filters_derivatives_and_separates_indices(self):
        self.assertEqual(self.master(), (STOCK, NIFTY))

    def test_quotes_use_exchange_timestamp(self):
        self.master()
        body = json.dumps(
            {
                "status": "success",
                "data": {"NSE:INFY": {"last_price": 1500.05, "timestamp": "2026-10-26 10:00:00"}},
            }
        )
        with patch.object(self.adapter, "_get", return_value=body) as request:
            quote = self.adapter.quote(STOCK)
        self.assertEqual(quote.price, D("1500.05"))
        self.assertEqual(quote.at.utcoffset(), timedelta(hours=5, minutes=30))
        request.assert_called_once_with("/quote", [("i", "NSE:INFY")])

    def test_missing_and_error_responses_fail_closed(self):
        self.master()
        for body in ["{}", "not json", '{"status":"error"}', '{"status":"success","data":{}}']:
            with patch.object(self.adapter, "_get", return_value=body):
                with self.assertRaises(MarketDataError):
                    self.adapter.quote(STOCK)

    def test_history_normalizes_candle_end_and_excludes_incomplete(self):
        self.master()
        body = json.dumps(
            {
                "status": "success",
                "data": {
                    "candles": [
                        [AT.isoformat(), 100, 103, 99, 102, 100],
                        [(AT + timedelta(minutes=5)).isoformat(), 102, 104, 100, 103, 200],
                    ]
                },
            }
        )
        with patch.object(self.adapter, "_get", return_value=body):
            bars = self.adapter.history(STOCK, AT, AT + timedelta(minutes=7))
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].end, AT + timedelta(minutes=5))

    def test_real_transport_is_get_only_and_redacts_errors(self):
        with patch("india_day_trader.brokers.zerodha.build_opener") as opener:
            opener.return_value.open.side_effect = HTTPError("url", 401, "test-token", {}, None)
            with self.assertRaisesRegex(MarketDataError, "Kite HTTP 401") as exc:
                self.adapter._get("/quote")
            self.assertNotIn("test-token", str(exc.exception))
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.host, "api.kite.trade")

    def test_metadata_mismatch_and_bad_intervals(self):
        self.master()
        with self.assertRaises(MarketDataError):
            self.adapter.quote(Instrument(Exchange.NSE, "INFY", tick_size=D("0.01")))
        with self.assertRaises(ValueError):
            self.adapter.history(STOCK, AT, AT + timedelta(hours=1), "invalid")

    def test_indicators_and_no_lookahead(self):
        bars = tuple(
            Bar(AT + timedelta(minutes=5 * i), D(100 + i), D(102 + i), D(99 + i), D(101 + i), 100)
            for i in range(1, 23)
        )
        for instrument in [STOCK, NIFTY, BANK_NIFTY, Instrument(Exchange.BSE, "500209")]:
            result = analyze(instrument, bars, bars[19].end)
            self.assertEqual(result["completed_bars"], 20)
            self.assertEqual(D(result["sma20"]), D("111.5"))
            self.assertEqual(D(result["rsi14"]), D(100))
            self.assertEqual(result["opening_range_high"], "105")
            self.assertEqual(result["trend"], "above_sma20")
            self.assertEqual(result, analyze(instrument, bars[:20], bars[19].end))

    def test_flat_rsi_zero_volume_and_incomplete_range(self):
        bars = tuple(
            Bar(AT + timedelta(minutes=5 * i), D(100), D(100), D(100), D(100), 0)
            for i in range(1, 17)
        )
        result = analyze(NIFTY, bars, bars[-1].end)
        self.assertEqual(D(result["rsi14"]), D(50))
        self.assertIsNone(result["session_vwap"])
        self.assertIsNone(analyze(NIFTY, bars[1:], bars[-1].end)["opening_range_high"])
        self.assertIsNone(analyze(NIFTY, bars, bars[0].end)["opening_range_high"])

    def test_reject_unsorted_and_bad_bars(self):
        bar = Bar(AT, D(100), D(101), D(99), D(100), 0)
        with self.assertRaises(ValueError):
            analyze(NIFTY, (bar, bar), AT)
        with self.assertRaises(ValueError):
            analyze(NIFTY, (), AT)
        with self.assertRaises(ValueError):
            Bar(AT, D(100), D(99), D(98), D(100), 1)

    def test_demo_and_cli(self):
        result = demo()
        self.assertEqual(result["mode"], "paper")
        self.assertEqual(result["open_positions"], 0)
        self.assertEqual(len(result["fills"]), 2)
        with patch("builtins.print"):
            self.assertEqual(main(["demo"]), 0)


if __name__ == "__main__":
    unittest.main()
