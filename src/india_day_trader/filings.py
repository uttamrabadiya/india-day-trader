"""Indian financial-result comparisons and public promoter/director disclosures.

Inputs are normalized, source-linked exports; this module does not scrape exchanges
or provide interpretations of legal disclosure obligations.
"""

from calendar import monthrange
from datetime import date, datetime

from .calendar import IST
from .models import aware, money
from .research_io import available, instrument, number, timestamp


def _growth(current, previous):
    return str((current - previous) / previous * 100) if previous > 0 else None


def earnings(
    rows: list[dict], key: str, as_of: datetime, *, basis: str = "consolidated", months: int = 3
) -> dict:
    aware(as_of)
    if basis not in {"consolidated", "standalone"} or months not in {3, 12}:
        raise ValueError("Use consolidated/standalone and a 3- or 12-month period")
    selected = {}
    for row in rows:
        if instrument(row["instrument"]).key != key or not available(row, as_of):
            continue
        if row["basis"] != basis or row["months"] != months:
            continue
        period = date.fromisoformat(row["period_end"])
        if period.day != monthrange(period.year, period.month)[1]:
            raise ValueError("Financial periods must end on a calendar month-end")
        if period > timestamp(row["published_at"]).astimezone(IST).date():
            raise ValueError("Financial period ends after publication")
        values = {field: number(row[field]) for field in ("revenue_inr", "profit_inr", "eps_inr")}
        observed = timestamp(row["observed_at"])
        previous = selected.get(period)
        if previous and previous[0] == observed and previous[1] != row:
            raise ValueError("Ambiguous financial revisions at the same observation time")
        if previous is None or previous[0] < observed:
            selected[period] = (observed, row, values)
    if not selected:
        raise ValueError("No available financial results for this instrument and reporting basis")
    period = max(selected)
    _, latest, values = selected[period]
    comparisons = {}
    for label, distance in (("previous_period", months), ("year_ago", 12)):
        month_index = period.year * 12 + period.month - 1 - distance
        year, zero_month = divmod(month_index, 12)
        prior_date = date(year, zero_month + 1, monthrange(year, zero_month + 1)[1])
        prior = selected.get(prior_date)
        comparisons[label] = (
            None
            if prior is None
            else {
                "period_end": prior_date.isoformat(),
                "source_url": prior[1]["source_url"],
                "growth_pct": {field: _growth(values[field], prior[2][field]) for field in values},
                "profit_change_inr": str(values["profit_inr"] - prior[2]["profit_inr"]),
            }
        )
    return {
        "instrument": key,
        "as_of": as_of.isoformat(),
        "basis": basis,
        "months": months,
        "period_end": period.isoformat(),
        "values": {k: str(v) for k, v in values.items()},
        "net_margin_pct": str(values["profit_inr"] / values["revenue_inr"] * 100)
        if values["revenue_inr"] > 0
        else None,
        "source_url": latest["source_url"],
        "published_at": latest["published_at"],
        "observed_at": latest["observed_at"],
        "comparisons": comparisons,
        "caveats": [
            "All monetary inputs must be normalized to INR, not lakhs/crores.",
            "Growth is null for zero/negative comparison bases; inspect absolute changes.",
            "Compare the same basis, duration and accounting definitions; verify restatements.",
        ],
    }


def disclosures(
    rows: list[dict], as_of: datetime, *, since: datetime, watchlist: set[str] | None = None
) -> dict:
    aware(as_of)
    aware(since)
    if since > as_of:
        raise ValueError("since must not be after as_of")
    selected = {}
    for row in rows:
        item = instrument(row["instrument"])
        if not available(row, as_of) or timestamp(row["published_at"]) < since:
            continue
        if watchlist is not None and item.key not in watchlist:
            continue
        identity = (item.key, row["filing_id"], row["record_id"])
        if not isinstance(row["filing_id"], str) or not row["filing_id"]:
            raise ValueError("Disclosure filing_id required")
        if not isinstance(row["record_id"], str) or not row["record_id"]:
            raise ValueError("Disclosure record_id required for each transaction within a filing")
        if row["actor_category"] not in {
            "promoter",
            "promoter_group",
            "director",
            "designated_person",
            "other",
        }:
            raise ValueError("Unknown disclosure actor category")
        if not isinstance(row["actor"], str) or not row["actor"].strip():
            raise ValueError("Disclosure actor required")
        if row["transaction"] not in {"BUY", "SELL", "PLEDGE", "UNPLEDGE", "OTHER"}:
            raise ValueError("Unknown transaction classification")
        if row["mode"] not in {"market", "off_market", "gift", "pledge", "other"}:
            raise ValueError("Unknown acquisition/disposal mode")
        if type(row["quantity"]) is not int or row["quantity"] < 0:
            raise ValueError("Disclosure quantity must be nonnegative whole shares")
        value = money(row["value_inr"], positive=False)
        trade_date = date.fromisoformat(row["transaction_date"])
        published = timestamp(row["published_at"])
        if trade_date > published.astimezone(IST).date():
            raise ValueError("Transaction date is later than publication")
        normalized = dict(
            row,
            instrument=item.key,
            value_inr=str(value),
            publication_lag_days=(published.astimezone(IST).date() - trade_date).days,
        )
        previous = selected.get(identity)
        if previous:
            old_at, new_at = timestamp(previous["observed_at"]), timestamp(row["observed_at"])
            if old_at == new_at and previous != normalized:
                raise ValueError("Conflicting disclosure revisions")
            if old_at > new_at:
                continue
        selected[identity] = normalized
    records = sorted(selected.values(), key=lambda r: timestamp(r["published_at"]), reverse=True)
    totals = {}
    for row in records:
        if row["mode"] != "market" or row["transaction"] not in {"BUY", "SELL"}:
            continue
        summary = totals.setdefault(row["instrument"], {"BUY": number(0), "SELL": number(0)})
        summary[row["transaction"]] += number(row["value_inr"])
    return {
        "as_of": as_of.isoformat(),
        "records": records,
        "market_transaction_values_inr": {
            k: {s: str(v) for s, v in t.items()} for k, t in totals.items()
        },
        "caveat": "Public filings may be delayed or amended. Gifts/pledges are not market buys. "
        "Reported activity is not a trading signal or evidence of misconduct.",
    }
