import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

from india_day_trader.alerts import EventJournal, poll
from india_day_trader.calendar import Session
from india_day_trader.cli import main
from india_day_trader.entry import check_entry, exit_plan
from india_day_trader.filings import disclosures, earnings
from india_day_trader.models import NIFTY, Bar, Exchange, Instrument, Quote
from india_day_trader.news import digest, import_rss
from india_day_trader.replay import bootstrap, replay
from india_day_trader.research_io import available, session_bars
from india_day_trader.scanner import scan

ITEM = Instrument(Exchange.NSE, "DEMO")
SPEC = {"exchange": "NSE", "symbol": "DEMO"}
OPEN = datetime.fromisoformat("2026-10-26T09:15:00+05:30")
AT = OPEN.replace(hour=10, minute=0)
SESSION = Session(OPEN.date())
SOURCE = "https://example.org/synthetic"


def candles():
    result = []
    for i in range(1, 76):
        prices = (
            (D(100), D(102), D(98), D(100))
            if i <= 3
            else ((D(100), D(104), D(99), D(103)) if i == 4 else (D(104), D(105), D(103), D(104)))
        )
        result.append(Bar(OPEN + timedelta(minutes=5 * i), *prices, 10000))
    return tuple(result)


def news_row(**changes):
    return {
        "instrument": SPEC,
        "title": "Synthetic quarterly results and dividend",
        "source_url": SOURCE,
        "published_at": AT.isoformat(),
        "observed_at": AT.isoformat(),
    } | changes


def financial(period, revenue, profit, **changes):
    return (
        news_row(
            period_end=period,
            basis="consolidated",
            months=3,
            revenue_inr=str(revenue),
            profit_inr=str(profit),
            eps_inr="2",
        )
        | changes
    )


def disclosure(**changes):
    return (
        news_row(
            filing_id="filing-1",
            record_id="transaction-1",
            actor="Synthetic Promoter",
            actor_category="promoter",
            transaction="BUY",
            mode="market",
            quantity=10,
            value_inr="1000",
            transaction_date="2026-10-23",
        )
        | changes
    )


class EntryScanTests(unittest.TestCase):
    def test_wait_trigger_consumed_expired_and_stale(self):
        data = candles()
        self.assertEqual(check_entry(ITEM, data, data[2].end, SESSION)["status"], "waiting")
        result = check_entry(ITEM, data, data[3].end, SESSION)
        self.assertEqual(result["status"], "triggered")
        self.assertEqual(result["plan"]["stop"], "100")
        self.assertEqual(D(result["plan"]["target"]), D(109))
        self.assertEqual(check_entry(ITEM, data, AT, SESSION)["status"], "already_triggered")
        self.assertEqual(check_entry(ITEM, data, AT.replace(hour=15), SESSION)["status"], "expired")
        self.assertEqual(check_entry(ITEM, data[:4], AT, SESSION)["status"], "stale")

    def test_no_future_candle_signal_and_no_index_plan(self):
        data = candles()
        at = data[3].end
        self.assertEqual(
            check_entry(ITEM, data, at, SESSION), check_entry(ITEM, data[:4], at, SESSION)
        )
        self.assertNotIn("plan", check_entry(NIFTY, data, at, SESSION))

    def test_missing_or_wrong_session_candles_rejected(self):
        with self.assertRaisesRegex(ValueError, "Missing"):
            session_bars(candles()[1:], SESSION, AT)
        with self.assertRaises(ValueError):
            check_entry(ITEM, candles(), AT + timedelta(days=1), SESSION)

    def test_plan_rounds_outward(self):
        plan = exit_plan(D("103.02"), D("100.03"), D("0.05"))
        self.assertEqual(D(plan["stop"]), D(100))
        self.assertEqual(D(plan["target"]), D("109.10"))

    def test_scan_filters_and_isolates_bad_instrument_data(self):
        other = Instrument(Exchange.BSE, "500001")
        result = scan([(ITEM, candles()), (other, candles()[1:])], AT, SESSION)
        self.assertIn("opening_range_breakout", result["candidates"][0]["setups"])
        self.assertEqual(result["excluded"][0]["instrument"], other.key)
        self.assertFalse(scan([(ITEM, candles())], AT, SESSION, min_volume=1000000)["candidates"])
        with self.assertRaises(ValueError):
            scan([(ITEM, candles()), (ITEM, candles())], AT, SESSION)


class ReplayTests(unittest.TestCase):
    def run_replay(self, data=None, **kwargs):
        return replay(
            ITEM,
            data or candles(),
            [SESSION],
            OPEN.replace(hour=15, minute=30),
            fee_bps=D(0),
            slippage_bps=D(0),
            **kwargs,
        )

    def test_next_open_entry_and_time_exit(self):
        trade = self.run_replay()["trades"][0]
        self.assertEqual(D(trade["entry"]), D(104))
        self.assertEqual(trade["entry_at"], candles()[3].end.isoformat())
        self.assertEqual(trade["reason"], "time")
        self.assertEqual(D(trade["pnl_inr"]), 0)

    def test_ambiguous_candle_stop_first(self):
        data = list(candles())
        data[4] = replace(data[4], high=D(115), low=D(99))
        trade = self.run_replay(tuple(data))["trades"][0]
        self.assertEqual(trade["reason"], "stop")
        self.assertEqual(D(trade["exit"]), D(100))
        self.assertEqual(D(trade["pnl_inr"]), D(-500))

    def test_known_gap_chronology_and_stop_gap(self):
        data = list(candles())
        data[5] = replace(data[5], open=D(120), high=D(121), low=D(98), close=D(105))
        self.assertEqual(self.run_replay(tuple(data))["trades"][0]["reason"], "target_gap")
        data[5] = replace(data[5], open=D(90), high=D(105), low=D(89), close=D(100))
        trade = self.run_replay(tuple(data))["trades"][0]
        self.assertEqual(trade["reason"], "stop_gap")
        self.assertLess(D(trade["pnl_inr"]), D(-500))

    def test_incomplete_sessions_not_silently_counted(self):
        report = self.run_replay(candles()[:5])
        self.assertFalse(report["trades"])
        self.assertTrue(report["skipped"])
        self.assertIsNone(report["observed_win_fraction"])
        self.assertIsNone(report["resampling"]["resampled_total_pnl_percentiles_inr"])

    def test_no_lookahead_for_replay_outcomes(self):
        data = candles()
        at = data[71].end
        a = replay(ITEM, data, [SESSION], at)
        b = replay(ITEM, data[:72], [SESSION], at)
        self.assertEqual(a, b)

    def test_replay_costs_and_quantity_obey_research_budgets(self):
        report = replay(ITEM, candles(), [SESSION], OPEN.replace(hour=15, minute=30))
        trade = report["trades"][0]
        self.assertLess(D(trade["pnl_inr"]), 0)
        self.assertGreater(D(trade["fees_inr"]), 0)
        self.assertLessEqual(D(trade["entry"]) * trade["quantity"] * D("1.001"), D(100000))
        self.assertLessEqual(trade["quantity"], 125)

    def test_resampling_is_reproducible_bounded_and_not_a_forecast(self):
        samples = [D(-10), D(20), D(3)]
        self.assertEqual(bootstrap(samples, seed=7), bootstrap(samples, seed=7))
        self.assertEqual(bootstrap([D(2)])["resampled_total_pnl_percentiles_inr"]["50"], "2")
        with self.assertRaises(ValueError):
            bootstrap(samples, simulations=10001)
        with self.assertRaises(ValueError):
            replay(NIFTY, candles(), [SESSION], AT)


class NewsTests(unittest.TestCase):
    def test_digest_dedup_watch_and_observation_time(self):
        row = news_row()
        future = news_row(title="Later", observed_at=(AT + timedelta(hours=1)).isoformat())
        result = digest([row, row, future], AT)
        self.assertEqual(len(result["items"]), 1)
        self.assertIn("results", result["items"][0]["tags"])
        self.assertFalse(digest([row], AT, watchlist={"BSE:DEMO"})["items"])

    def test_stale_news_excluded_and_bad_sources_rejected(self):
        old = (AT - timedelta(days=2)).isoformat()
        self.assertFalse(digest([news_row(published_at=old, observed_at=old)], AT)["items"])
        for url in ["javascript:alert(1)", "https://secret@example.org", "http://example.org"]:
            with self.assertRaises(ValueError):
                digest([news_row(source_url=url)], AT)
        with self.assertRaises(ValueError):
            available(news_row(observed_at=(AT - timedelta(hours=1)).isoformat()), AT)

    def test_rss_import_and_xml_rejection(self):
        xml = (
            '<rss version="2.0"><channel><item><title>DEMO results</title>'
            "<link>https://example.org/a</link><pubDate>Mon, 26 Oct 2026 09:00:00 +0530</pubDate>"
            "</item></channel></rss>"
        )
        rows = import_rss(xml, ITEM, AT)
        self.assertEqual(rows[0]["instrument"]["symbol"], "DEMO")
        self.assertEqual(len(digest(rows, AT)["items"]), 1)
        for invalid in [
            "<!DOCTYPE rss><rss/>",
            "<rss><channel><item/></channel></rss>",
            "<notxml>",
        ]:
            with self.assertRaises(ValueError):
                import_rss(invalid, ITEM, AT)


class FilingTests(unittest.TestCase):
    def test_comparable_quarters_and_negative_profit_base(self):
        rows = [
            financial("2026-09-30", 120, 12),
            financial("2026-06-30", 100, -5),
            financial("2025-09-30", 80, 8),
        ]
        report = earnings(rows, ITEM.key, AT)
        self.assertEqual(report["net_margin_pct"], "10.0")
        prior = report["comparisons"]["previous_period"]
        self.assertEqual(D(prior["growth_pct"]["revenue_inr"]), D(20))
        self.assertIsNone(prior["growth_pct"]["profit_inr"])
        self.assertEqual(prior["profit_change_inr"], "17")
        self.assertEqual(D(report["comparisons"]["year_ago"]["growth_pct"]["profit_inr"]), D(50))

    def test_revisions_do_not_leak_and_basis_not_mixed(self):
        current = financial("2026-09-30", 120, 12)
        later = current | {
            "profit_inr": "999",
            "observed_at": (AT + timedelta(hours=1)).isoformat(),
        }
        other_basis = financial("2026-06-30", 100, 8, basis="standalone")
        report = earnings([current, later, other_basis], ITEM.key, AT)
        self.assertEqual(report["values"]["profit_inr"], "12")
        self.assertIsNone(report["comparisons"]["previous_period"])
        self.assertEqual(
            earnings([current, later], ITEM.key, AT + timedelta(hours=1))["values"]["profit_inr"],
            "999",
        )

    def test_disclosure_identity_revisions_and_nonmarket_modes(self):
        row = disclosure()
        gift = disclosure(record_id="gift", mode="gift", value_inr="100000")
        other_actor = disclosure(record_id="director", actor="Director", actor_category="director")
        result = disclosures([row, row, gift, other_actor], AT, since=AT - timedelta(days=30))
        self.assertEqual(len(result["records"]), 3)
        self.assertEqual(result["market_transaction_values_inr"][ITEM.key]["BUY"], "2000")
        self.assertEqual(result["records"][0]["publication_lag_days"], 3)
        amended = row | {"value_inr": "2000", "observed_at": (AT + timedelta(hours=1)).isoformat()}
        result = disclosures([row, amended], AT, since=AT - timedelta(days=30))
        self.assertEqual(result["market_transaction_values_inr"][ITEM.key]["BUY"], "1000")

    def test_future_transaction_and_invalid_values_rejected(self):
        with self.assertRaises(ValueError):
            disclosures([disclosure(transaction_date="2026-10-27")], AT, since=OPEN)
        with self.assertRaises(ValueError):
            earnings([financial("2026-09-30", "NaN", 1)], ITEM.key, AT)


class AlertTests(unittest.TestCase):
    def test_journal_restart_and_concurrent_delivery(self):
        alert = {"id": "target", "instrument": SPEC, "kind": "above", "threshold": "100"}
        quote = Quote(ITEM, D(101), AT)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.sqlite3"
            journal = EventJournal(path)
            with ThreadPoolExecutor(max_workers=6) as pool:
                counts = list(
                    pool.map(lambda _: len(poll([alert], [quote], AT, journal)), range(12))
                )
            self.assertEqual(sum(counts), 1)
            self.assertFalse(poll([alert], [quote], AT, EventJournal(path)))
            self.assertEqual(len(EventJournal(path).events()), 1)

    def test_time_price_and_invalid_batch(self):
        alert = {"id": "stop", "instrument": SPEC, "kind": "below", "threshold": "100"}
        timer = {"id": "flat", "instrument": SPEC, "kind": "time", "at": AT.isoformat()}
        with tempfile.TemporaryDirectory() as folder:
            journal = EventJournal(Path(folder) / "events.sqlite3")
            with self.assertRaises(ValueError):
                poll([timer, alert | {"kind": "bad"}], [], AT, journal)
            self.assertFalse(journal.events())
            with self.assertRaisesRegex(ValueError, "Stale"):
                poll([alert], [Quote(ITEM, D(90), AT - timedelta(minutes=1))], AT, journal)
            self.assertEqual(len(poll([timer, alert], [Quote(ITEM, D(90), AT)], AT, journal)), 2)


class ResearchCliTests(unittest.TestCase):
    def test_news_cli_persists_seen_events(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            args = [
                "news",
                "--input",
                str(root / "examples/research.json"),
                "--as-of",
                AT.isoformat(),
                "--state",
                str(Path(folder) / "news.sqlite3"),
            ]
            for count in (1, 0):
                with redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(main(args), 0)
                self.assertEqual(len(json.loads(out.getvalue())["items"]), count)

    def test_every_research_command_from_synthetic_bundle(self):
        root = Path(__file__).resolve().parents[1]
        sample = root / "examples/research.json"
        with tempfile.TemporaryDirectory() as folder:
            for command in ("scan", "entry", "replay", "news", "earnings", "disclosures", "alerts"):
                at = "2026-10-26T15:30:00+05:30" if command == "replay" else AT.isoformat()
                args = [command, "--input", str(sample), "--as-of", at]
                if command in {"entry", "replay", "earnings"}:
                    args += ["--instrument", "NSE:DEMO"]
                if command == "alerts":
                    args += ["--state", str(Path(folder) / "events.sqlite3")]
                with self.subTest(command=command), redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(main(args), 0)
                    self.assertIsInstance(json.loads(out.getvalue()), dict)

    def test_bad_input_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "bad.json"
            file.write_text('{"news": []}')
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                main(["news", "--input", str(file), "--as-of", "2026-10-26T10:00:00"])
            self.assertEqual(exc.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
