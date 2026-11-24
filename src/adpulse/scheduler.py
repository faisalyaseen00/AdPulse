"""Weekly report scheduler: `adpulse scheduler` runs forever and sends the report every week.

Default: Monday 08:00 in REPORT_TIMEZONE. Each run refreshes the pause/scale recommendations,
builds the report (AI commentary when an LLM is configured) and delivers it to Slack and/or email.
If the process was down at the scheduled time (laptop asleep, server restart), it catches up on
start as long as the missed slot is less than REPORT_CATCHUP_HOURS old and no report was sent since.
"""
from __future__ import annotations

import logging
import signal
import threading
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .config import get_settings

log = logging.getLogger("adpulse.scheduler")
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass(frozen=True)
class Schedule:
    weekday: int  # 0 = Monday
    at: time
    tz: ZoneInfo

    @classmethod
    def from_settings(cls) -> Schedule:
        s = get_settings()
        day = s.report_schedule_day.strip().lower()[:3]
        if day not in DAYS:
            raise ValueError(f"REPORT_SCHEDULE_DAY must be one of {', '.join(DAYS)} (got {s.report_schedule_day!r})")
        try:
            hh, mm = (int(x) for x in s.report_schedule_time.split(":"))
            at = time(hh, mm)
        except ValueError as e:
            raise ValueError(f"REPORT_SCHEDULE_TIME must be HH:MM (got {s.report_schedule_time!r})") from e
        return cls(DAYS[day], at, ZoneInfo(s.report_timezone))

    def next_run(self, now: datetime) -> datetime:
        """First scheduled slot strictly after `now` (aware datetime)."""
        local = now.astimezone(self.tz)
        days_ahead = (self.weekday - local.weekday()) % 7
        slot = datetime.combine(local.date() + timedelta(days=days_ahead), self.at, self.tz)
        if slot <= local:
            slot = datetime.combine(slot.date() + timedelta(days=7), self.at, self.tz)
        return slot

    def previous_run(self, now: datetime) -> datetime:
        """Most recent scheduled slot at or before `now`."""
        return self.next_run(now) - timedelta(days=7)

    def describe(self) -> str:
        day = next(k for k, v in DAYS.items() if v == self.weekday).title()
        return f"every {day} at {self.at:%H:%M} {self.tz.key}"


def run_weekly(send: bool = True) -> dict[str, str]:
    """One scheduled job: refresh recommendations, build the report, deliver it."""
    from .actions import recommendations as recs
    from .llm import LLMError, get_llm
    from .reports import weekly

    s = get_settings()
    if s.report_sync_first:
        from .pipeline import ingest, transform
        ingest.ingest("auto", progress=log.info)
        transform.run_models(progress=log.info)
    n = recs.save(recs.rule_recommendations(30))
    log.info("recommendations refreshed: %d new", n)
    try:
        llm = get_llm()
    except LLMError:
        llm = None
    rep = weekly.build(llm=llm)
    if not send:
        weekly.save(rep, [], "generated")
        return {"report": "generated (not sent)"}
    results = weekly.deliver(rep)
    log.info("weekly report %s: %s", rep.id, results)
    return results


def _sent_since(when: datetime) -> bool:
    from . import warehouse
    df = warehouse.query_df(
        "SELECT count() AS n FROM app_reports WHERE status = 'sent' AND created_at >= {t:DateTime}",
        {"t": when.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)})
    return bool(df.iloc[0]["n"])


def serve(stop: threading.Event | None = None, now=lambda: datetime.now(ZoneInfo("UTC"))) -> None:
    """Block forever, running the weekly job on schedule. Ctrl+C / SIGTERM stops it cleanly."""
    s = get_settings()
    sched = Schedule.from_settings()
    stop = stop or threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: stop.set())
        except ValueError:  # not in main thread (tests)
            pass
    log.info("scheduler started: %s", sched.describe())

    prev = sched.previous_run(now())
    if now() - prev < timedelta(hours=s.report_catchup_hours):
        try:
            if not _sent_since(prev):
                log.info("missed the %s run, catching up now", prev.isoformat())
                _safe_run()
        except Exception:
            log.exception("catch-up check failed")

    while not stop.is_set():
        nxt = sched.next_run(now())
        log.info("next report: %s", nxt.isoformat())
        # wake at least hourly so clock changes / long sleeps don't drift
        while not stop.is_set() and now() < nxt:
            stop.wait(min(3600.0, max(1.0, (nxt - now()).total_seconds())))
        if stop.is_set():
            break
        _safe_run()
    log.info("scheduler stopped")


def _safe_run() -> None:
    try:
        res = run_weekly()
        if any(v.startswith("error") for v in res.values()):
            log.error("delivery problem: %s", res)
    except Exception:
        log.exception("weekly report failed")
