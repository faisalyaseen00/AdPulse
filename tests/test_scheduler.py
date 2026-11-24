"""Weekly scheduler: slot maths across time zones / DST, config validation, catch-up and the loop."""
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from adpulse import scheduler as sch
from adpulse.config import get_settings

UTC = ZoneInfo("UTC")
PKT = ZoneInfo("Asia/Karachi")


def mk(day="mon", at="08:00", tz="Asia/Karachi", monkeypatch=None):
    s = get_settings()
    monkeypatch.setattr(s, "report_schedule_day", day)
    monkeypatch.setattr(s, "report_schedule_time", at)
    monkeypatch.setattr(s, "report_timezone", tz)
    return sch.Schedule.from_settings()


def test_next_run_same_week_and_rollover(monkeypatch):
    s = mk(monkeypatch=monkeypatch)
    tue = datetime(2026, 11, 24, 12, 0, tzinfo=PKT)  # Tuesday
    assert s.next_run(tue) == datetime(2026, 11, 30, 8, 0, tzinfo=PKT)
    mon_early = datetime(2026, 11, 30, 7, 59, tzinfo=PKT)
    assert s.next_run(mon_early) == datetime(2026, 11, 30, 8, 0, tzinfo=PKT)
    mon_exact = datetime(2026, 11, 30, 8, 0, tzinfo=PKT)  # strictly after: next week
    assert s.next_run(mon_exact) == datetime(2026, 12, 7, 8, 0, tzinfo=PKT)
    assert s.previous_run(mon_exact) == mon_exact


def test_next_run_from_utc_clock(monkeypatch):
    s = mk(monkeypatch=monkeypatch)
    # Monday 02:30 UTC is Monday 07:30 in Karachi: today's 08:00 slot is still ahead
    now = datetime(2026, 11, 30, 2, 30, tzinfo=UTC)
    assert s.next_run(now).astimezone(UTC) == datetime(2026, 11, 30, 3, 0, tzinfo=UTC)


def test_dst_keeps_local_wall_time(monkeypatch):
    s = mk(day="sun", at="09:00", tz="America/New_York", monkeypatch=monkeypatch)
    before = datetime(2026, 2, 28, tzinfo=UTC)  # US DST starts 02:00 Sun 2026-03-08
    a = s.next_run(before)  # Sun Mar 1, 09:00 EST
    b = s.next_run(a)       # Sun Mar 8, 09:00 EDT
    assert (a.day, b.day) == (1, 8) and a.hour == b.hour == 9  # same wall-clock time
    assert b.astimezone(UTC) - a.astimezone(UTC) == timedelta(days=7) - timedelta(hours=1)


@pytest.mark.parametrize("day,at", [("someday", "08:00"), ("mon", "8am"), ("mon", "25:00")])
def test_bad_config_is_explained(monkeypatch, day, at):
    with pytest.raises(ValueError):
        mk(day=day, at=at, monkeypatch=monkeypatch)


def _run_serve(monkeypatch, now, sent_since, slot_hit=False):
    mk(monkeypatch=monkeypatch)
    calls = []
    stop = threading.Event()
    clock = {"t": now}

    def fake_run():
        calls.append(clock["t"])
        if len(calls) >= (2 if slot_hit else 1):
            stop.set()

    monkeypatch.setattr(sch, "_safe_run", fake_run)
    monkeypatch.setattr(sch, "_sent_since", lambda when: sent_since)

    def fake_wait(seconds):  # time travel instead of sleeping
        clock["t"] = clock["t"] + timedelta(seconds=seconds)
        return stop.is_set()

    monkeypatch.setattr(stop, "wait", fake_wait)
    t = threading.Thread(target=sch.serve, kwargs={"stop": stop, "now": lambda: clock["t"]})
    t.start()
    t.join(5)
    stop.set()
    return calls


def test_catch_up_when_slot_missed(monkeypatch):
    # Monday 10:00 Karachi, nothing sent since 08:00 -> send now, then wait for next Monday
    calls = _run_serve(monkeypatch, datetime(2026, 11, 30, 10, 0, tzinfo=PKT), sent_since=False, slot_hit=True)
    assert calls[0] == datetime(2026, 11, 30, 10, 0, tzinfo=PKT)
    assert calls[1].astimezone(PKT) == datetime(2026, 12, 7, 8, 0, tzinfo=PKT)


def test_no_catch_up_when_already_sent(monkeypatch):
    calls = _run_serve(monkeypatch, datetime(2026, 11, 30, 10, 0, tzinfo=PKT), sent_since=True)
    assert calls == [datetime(2026, 12, 7, 8, 0, tzinfo=PKT)]


def test_no_catch_up_when_slot_is_old(monkeypatch):
    calls = _run_serve(monkeypatch, datetime(2026, 12, 3, 10, 0, tzinfo=PKT), sent_since=False)
    assert calls == [datetime(2026, 12, 7, 8, 0, tzinfo=PKT)]
