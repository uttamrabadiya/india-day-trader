"""Explicit reviewed sessions: unknown dates fail closed, including holidays."""

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from .models import aware

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class Session:
    day: date
    opens: time = time(9, 15)
    entry_cutoff: time = time(15, 0)
    flatten_at: time = time(15, 15)
    closes: time = time(15, 30)

    def __post_init__(self) -> None:
        if any(
            t.tzinfo is not None
            for t in (self.opens, self.entry_cutoff, self.flatten_at, self.closes)
        ):
            raise ValueError("Session times must be local wall times")
        if not self.opens < self.entry_cutoff < self.flatten_at < self.closes:
            raise ValueError("Invalid session times")


class TradingCalendar:
    def __init__(self, sessions: list[Session]):
        self._sessions = {s.day: s for s in sessions}
        if len(self._sessions) != len(sessions):
            raise ValueError("Duplicate sessions")

    def session(self, now: datetime) -> Session:
        aware(now)
        session = self._sessions.get(now.astimezone(IST).date())
        if session is None:
            raise ValueError("No reviewed trading session for this IST date")
        return session

    def check(self, now: datetime, *, entry: bool) -> Session:
        session = self.session(now)
        wall = now.astimezone(IST).time()
        if not session.opens <= wall < session.closes:
            raise ValueError("Outside reviewed market session")
        if entry and wall >= session.entry_cutoff:
            raise ValueError("Entry cutoff reached")
        return session
