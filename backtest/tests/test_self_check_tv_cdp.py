"""Guard for self_check.check_tv_cdp -- the TradingView CDP liveness VISIBILITY instrument
(D1-TV-CDP-ROOT-CAUSE queue item, part 3; OVERNIGHT-READ-D1-2026-07-09.md Finding #1/#3).

Motivation: TV/CDP went dead for 41+ hours 2026-07-07/09, degrading premarket bias to a real
'no-trade-tv-fail' framing on 2026-07-08 -- and self_check.py (the surface J's STATUS.md /
engine-health.json morning brief actually reads) had ZERO tv/cdp/9222/TradingView awareness the
entire time, confirmed by grep 12 days after the audit flagged this as an effort=S fix.
preopen_readiness.py's assess_tv_cdp/fetch_tv_cdp already existed and already caught this class
correctly -- this pins the PORTED (not imported -- see check_macro_calendar_freshness's docstring
for the standalone-observer rationale) copy in self_check.py.

Mirrors test_self_check_trendline_draw_freshness.py's import convention and structure, but this
check is RED/BROKEN (unlike trendline-draw's DEGRADED) since a dead CDP has a real, disclosed
trading-relevant cost.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "self_check.py"

_spec = importlib.util.spec_from_file_location("self_check", MOD_PATH)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


def _fake_probe(reachable: bool, detail: str = ""):
    def _probe():
        return reachable, detail
    return _probe


# ---- weekend / outside-window: never flags, never even calls the probe ----

def test_weekend_never_flags():
    now = dt.datetime(2026, 7, 18, 12, 0)  # Saturday
    calls = []
    def probe():
        calls.append(1)
        return False, "should never be called"
    assert sc.check_tv_cdp(now, fetch=probe) == []
    assert calls == [], "weekend must short-circuit before probing"


def test_before_window_never_flags():
    now = dt.datetime(2026, 7, 20, 8, 0)  # Monday, before 08:10 slack expiry
    calls = []
    def probe():
        calls.append(1)
        return False, "should never be called"
    assert sc.check_tv_cdp(now, fetch=probe) == []
    assert calls == [], "before the 08:10 slack window must short-circuit before probing"


def test_after_window_never_flags():
    now = dt.datetime(2026, 7, 20, 16, 5)  # Monday, after 16:00
    calls = []
    def probe():
        calls.append(1)
        return False, "should never be called"
    assert sc.check_tv_cdp(now, fetch=probe) == []
    assert calls == [], "after 16:00 must short-circuit before probing"


# ---- inside the window: probe result drives the verdict ----

def test_reachable_produces_no_problem():
    now = dt.datetime(2026, 7, 20, 10, 0)  # Monday, mid-window
    assert sc.check_tv_cdp(now, fetch=_fake_probe(True, "CDP responding on :9222")) == []


def test_unreachable_flags_red_and_broken():
    now = dt.datetime(2026, 7, 20, 10, 0)
    problems = sc.check_tv_cdp(now, fetch=_fake_probe(False, "CDP unreachable on :9222: TimeoutError"))
    assert len(problems) == 1
    assert "TV-CDP UNREACHABLE" in problems[0]
    assert "RED" in problems[0]
    assert "TimeoutError" in problems[0]
    assert sc._problem_is_broken(problems[0]), "a dead CDP has a real trading-relevant cost -- must be BROKEN"


def test_at_exact_window_boundaries_is_inside():
    # 08:10 and 16:00 are inclusive per the check's own >=/<= framing
    now_open = dt.datetime(2026, 7, 20, 8, 10)
    now_close = dt.datetime(2026, 7, 20, 16, 0)
    assert len(sc.check_tv_cdp(now_open, fetch=_fake_probe(False, "down"))) == 1
    assert len(sc.check_tv_cdp(now_close, fetch=_fake_probe(False, "down"))) == 1


# ---- default probe (no fetch injected) never raises, even with no live CDP present ----

def test_default_probe_fail_open_never_raises():
    now = dt.datetime(2026, 7, 20, 10, 0)
    # No fetch injected -- exercises the real _fetch_tv_cdp_reachable against whatever (if
    # anything) is on :9222 in this test environment. Must never raise regardless of outcome.
    problems = sc.check_tv_cdp(now)
    assert isinstance(problems, list)


# ---- wiring: run() must call the check and feed it into problems ----

def test_run_source_wires_tv_cdp_check():
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_tv_cdp(now)" in src
    assert "problems.extend(check_tv_cdp(now))" in src
