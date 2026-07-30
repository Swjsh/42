"""Guards for the 2026-07-30 BLIND-SESSION detection layer (DETECTION workstream).

THE INCIDENT: Gamma_LevelRefresh's trigger was misconfigured (next run 16:38 ET, after the
close), so key-levels.json sat un-rewritten for ~19.8h still dated 2026-07-29 with every
level carrying `expires_at` 2026-07-29. heartbeat_core._read_levels correctly dropped them
all and returned ([], []) -- so every one of the day's ~770 RTH decision rows carries
`levels_active: []`.
The engine did not halt or warn; it silently fell through to trendline-only entries (its worst
cohort: -$1,830 / WR .19) and produced 11 ENTER_BEAR verdicts at the LOW of the day. Only the
risk gate stopped the fills. NOTHING reported it -- `engine_health.check_level_feed` is
market_open-suppressed and read "market closed -- refresh idle, quiet OK".

THIS FILE PINS three surfaces:
  1. engine_health  -- `levels_blind` (consumer side) + `levels_file_stale` (producer side),
                       NEITHER market_open-suppressed. That suppression is the bug.
  2. daily_brief    -- the EOD brief LEADS with the blindness alarm, ahead of P&L.
  3. premarket_readiness -- `levels_sanity` also fails on a stale-dated-but-parses file,
                       on disagreeing date fields, on an engine-invisible level set, and on
                       a stale file MTIME (not just the self-reported `as_of`).

Everything here is MONITORING and therefore FAIL-OPEN: the tests assert that a broken checker
degrades to YELLOW/None and never crashes its caller, and that no check can trade-halt.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "setup" / "scripts"

# Import levels_blind_check under its REAL module name so that engine_health.py's own
# `import levels_blind_check` resolves to this same object (sys.modules cache) -- monkeypatching
# its STATE paths then reaches the wiring under test, not a private copy.
sys.path.insert(0, str(_SCRIPTS))
import levels_blind_check as lbc  # noqa: E402


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


eh = _load("engine_health_blind_under_test", "engine_health.py")
db = _load("daily_brief_blind_under_test", "daily_brief.py")
pr = _load("premarket_readiness_blind_under_test", "premarket_readiness.py")

# 2026-07-30 is a Thursday (the incident day). Two moments that matter:
_ET_RTH = dt.datetime(2026, 7, 30, 11, 40, 0)     # mid-session, when the 11 bad ENTERs fired
_ET_AFTER_CLOSE = dt.datetime(2026, 7, 30, 18, 45, 0)  # market CLOSED -- the suppression trap
_ET_SAT = dt.datetime(2026, 8, 1, 12, 0, 0)       # Saturday


# --------------------------------------------------------------------------- #
# Fixtures: synthesize ledgers + level files.
# --------------------------------------------------------------------------- #

def _rth_stamp(day: str, i: int) -> str:
    """i-th minute of RTH (09:30 + i), as a naive-ET ts_et stamp."""
    t = dt.datetime.strptime(f"{day} 09:30:03", "%Y-%m-%d %H:%M:%S") + dt.timedelta(minutes=i)
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def _ledger(tmp_path: Path, day: str, n: int, *, levels, extra: list = None) -> Path:
    """n RTH rows/account for `day`; `levels` is what each row's levels_active carries.
    `extra` appends arbitrary raw rows (used to reproduce the post-close masking case)."""
    p = tmp_path / "core-decisions.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for acct in ("safe", "bold"):
            for i in range(n):
                fh.write(json.dumps({
                    "ts_et": _rth_stamp(day, i),
                    "account": acct, "verdict": "HOLD", "levels_active": list(levels),
                }) + "\n")
        for row in (extra or []):
            fh.write(json.dumps(row) + "\n")
    return p


def _levels_file(tmp_path: Path, *, session_date: str, expires: str,
                 date_field=None, n: int = 6) -> Path:
    p = tmp_path / "key-levels.json"
    p.write_text(json.dumps({
        "as_of": f"{session_date}T09:35:00-04:00",
        "for_session": session_date,
        "date": session_date if date_field is None else date_field,
        "spot_at_compute": 740.0,
        "levels": [{"price": 735.0 + i, "role": "support" if i < n // 2 else "resistance",
                    "expires_at": f"{expires}T16:00:00-04:00"} for i in range(n)],
    }), encoding="utf-8")
    return p


def _touch(p: Path, et_when: dt.datetime) -> None:
    """Set a file's mtime so it reads as `et_when` in NAIVE ET (inverse of lbc.mtime_as_et)."""
    utc = dt.datetime.now(dt.timezone.utc)
    off = lbc._et_offset_hours(utc)
    epoch = (et_when - dt.timedelta(hours=off)).replace(tzinfo=dt.timezone.utc).timestamp()
    import os
    os.utime(p, (epoch, epoch))


# =========================================================================== #
# 1. CONSUMER SIDE -- assess_rows / check_day
# =========================================================================== #

def test_empty_levels_active_all_day_is_BLIND(tmp_path):
    """THE 2026-07-30 SIGNATURE: a populated RTH where every row carries levels_active: []."""
    p = _ledger(tmp_path, "2026-07-30", 386, levels=[])
    res = lbc.check_day("2026-07-30", path=p)
    assert res["status"] == lbc.STATUS_BLIND
    # 385/account, not 386: the 15:55 row falls outside the RTH window (09:30 <= t < 15:55),
    # which is the flatten minute, not a decision minute.
    assert res["n_total"] == 770 and res["n_sighted"] == 0
    assert "BLIND" in res["reason"]


def test_normal_ledger_with_levels_is_SIGHTED(tmp_path):
    p = _ledger(tmp_path, "2026-07-30", 386, levels=[738.1, 741.4])
    res = lbc.check_day("2026-07-30", path=p)
    assert res["status"] == lbc.STATUS_SIGHTED
    assert res["n_sighted"] == 770


def test_late_first_refresh_is_not_called_blind(tmp_path):
    """Levels arriving a few minutes into the session is NORMAL -- calling that BLIND would
    cry wolf every morning and get the alarm ignored. 10 blind then 350 sighted = 97%."""
    p = tmp_path / "core-decisions.jsonl"
    rows = ([{"ts_et": _rth_stamp("2026-07-30", i), "account": "safe", "levels_active": []}
             for i in range(10)]
            + [{"ts_et": _rth_stamp("2026-07-30", 10 + i), "account": "safe",
                "levels_active": [740.0]} for i in range(350)])
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert lbc.check_day("2026-07-30", path=p)["status"] == lbc.STATUS_SIGHTED


def test_post_close_rows_cannot_mask_a_blind_session(tmp_path):
    """REGRESSION, found live while building this on 2026-07-30. The first draft asked "did
    ANY row all day carry levels?" over the WHOLE day. A concurrent repair re-ran the level
    refresher at 18:57 ET, and TWO post-close ticks flipped a 776-blind-row session from
    BLIND to SIGHTED. A verdict about the trading session must come from the trading session."""
    p = _ledger(tmp_path, "2026-07-30", 386, levels=[], extra=[
        {"ts_et": "2026-07-30T18:57:56", "account": "safe", "levels_active": [749.5, 751.2]},
        {"ts_et": "2026-07-30T18:58:56", "account": "bold", "levels_active": [749.5, 751.2]},
    ])
    res = lbc.check_day("2026-07-30", path=p)
    assert res["status"] == lbc.STATUS_BLIND, "post-close ticks must never vote on the session"
    assert res["n_total"] == 770 and res["n_sighted"] == 0, "RTH-scoped counts"
    assert res["n_sighted_all_day"] == 2, "the all-day count is still reported for context"


def test_premarket_rows_cannot_mask_a_blind_session(tmp_path):
    p = _ledger(tmp_path, "2026-07-30", 386, levels=[], extra=[
        {"ts_et": "2026-07-30T08:31:00", "account": "safe", "levels_active": [740.0]},
    ])
    assert lbc.check_day("2026-07-30", path=p)["status"] == lbc.STATUS_BLIND


def test_mostly_blind_session_is_BLIND(tmp_path):
    """Blind for the first 2/3 of RTH then sighted: the engine spent most of the session in
    its worst entry mode. That is an outage, not a warm-up."""
    p = tmp_path / "core-decisions.jsonl"
    rows = ([{"ts_et": _rth_stamp("2026-07-30", i), "account": "safe", "levels_active": []}
             for i in range(260)]
            + [{"ts_et": _rth_stamp("2026-07-30", 260 + i), "account": "safe",
                "levels_active": [740.0]} for i in range(100)])
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    res = lbc.check_day("2026-07-30", path=p)
    assert res["status"] == lbc.STATUS_BLIND
    assert "MOSTLY BLIND" in res["reason"]


def test_bite_ratio_floor_is_non_vacuous(tmp_path):
    """Drop the floor to 0 and the mostly-blind day reads SIGHTED -- proving the RATIO branch
    (not the zero-sighted branch) is what produces that verdict."""
    p = tmp_path / "core-decisions.jsonl"
    rows = ([{"ts_et": _rth_stamp("2026-07-30", i), "account": "safe", "levels_active": []}
             for i in range(260)]
            + [{"ts_et": _rth_stamp("2026-07-30", 260 + i), "account": "safe",
                "levels_active": [740.0]} for i in range(100)])
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert lbc.check_day("2026-07-30", path=p)["status"] == lbc.STATUS_BLIND
    assert lbc.check_day("2026-07-30", path=p, blind_ratio=0.0)["status"] == lbc.STATUS_SIGHTED


def test_thin_day_is_INSUFFICIENT_not_blind(tmp_path):
    """A handful of rows (warm-up / half-session) must not be enough to call the day blind."""
    p = _ledger(tmp_path, "2026-07-30", 5, levels=[])
    assert lbc.check_day("2026-07-30", path=p)["status"] == lbc.STATUS_INSUFFICIENT


def test_weekend_is_not_applicable(tmp_path):
    p = _ledger(tmp_path, "2026-08-01", 386, levels=[])
    assert lbc.check_day("2026-08-01", path=p)["status"] == lbc.STATUS_NOT_APPLICABLE


def test_unreadable_ledger_is_UNKNOWN_never_raises(tmp_path):
    res = lbc.check_day("2026-07-30", path=tmp_path / "nope.jsonl")
    assert res["status"] == lbc.STATUS_UNKNOWN


def test_malformed_rows_never_raise(tmp_path):
    p = tmp_path / "core-decisions.jsonl"
    p.write_text("not json\n" + json.dumps(["a", "list"]) + "\n"
                 + json.dumps({"ts_et": "2026-07-30T10:00:00", "levels_active": []}) + "\n",
                 encoding="utf-8")
    assert lbc.check_day("2026-07-30", path=p)["status"] in (
        lbc.STATUS_INSUFFICIENT, lbc.STATUS_BLIND)


def test_bite_min_rows_threshold_is_non_vacuous(tmp_path):
    """Raise the evidence floor above the row count and the BLIND day reads INSUFFICIENT --
    proving the ZERO-sighted branch (not some other path) produces the verdict."""
    p = _ledger(tmp_path, "2026-07-30", 386, levels=[])
    assert lbc.check_day("2026-07-30", path=p)["status"] == lbc.STATUS_BLIND
    assert lbc.check_day("2026-07-30", path=p, min_rows=10_000)["status"] == lbc.STATUS_INSUFFICIENT


# =========================================================================== #
# 2. PRODUCER SIDE -- assess_levels_file / check_levels_file
# =========================================================================== #

def test_stale_dated_file_is_STALE_during_rth(tmp_path):
    p = _levels_file(tmp_path, session_date="2026-07-29", expires="2026-07-29")
    _touch(p, dt.datetime(2026, 7, 29, 22, 43))
    res = lbc.check_levels_file(_ET_RTH, path=p)
    assert res["status"] == lbc.STATUS_STALE
    assert res["file_date"] == "2026-07-29"
    assert res["n_visible"] == 0


def test_stale_dated_file_STILL_reds_after_the_close(tmp_path):
    """THE LOAD-BEARING ANTI-SUPPRESSION TEST. `check_level_feed` says "market closed --
    refresh idle, quiet OK" here, which is exactly how a full blind day read GREEN. This
    check must stay asserted after 15:55."""
    p = _levels_file(tmp_path, session_date="2026-07-29", expires="2026-07-29")
    _touch(p, dt.datetime(2026, 7, 29, 22, 43))
    res = lbc.check_levels_file(_ET_AFTER_CLOSE, path=p)
    assert res["status"] == lbc.STATUS_STALE, "market-closed must NEVER suppress this check"


def test_fresh_file_dated_today_is_FRESH(tmp_path):
    p = _levels_file(tmp_path, session_date="2026-07-30", expires="2026-07-30")
    _touch(p, dt.datetime(2026, 7, 30, 11, 35))
    res = lbc.check_levels_file(_ET_RTH, path=p)
    assert res["status"] == lbc.STATUS_FRESH
    assert res["n_visible"] == 6


def test_dated_today_but_every_level_expired_is_STALE(tmp_path):
    """Parses fine, dated today -- and the engine still sees NOTHING. The subtle half of the
    incident: a date stamp is not proof the level set survives the engine's expiry rule."""
    p = _levels_file(tmp_path, session_date="2026-07-30", expires="2026-07-29")
    _touch(p, dt.datetime(2026, 7, 30, 11, 35))
    res = lbc.check_levels_file(_ET_RTH, path=p)
    assert res["status"] == lbc.STATUS_STALE
    assert res["n_visible"] == 0
    assert "EMPTY TO THE ENGINE" in res["reason"]


def test_disagreeing_date_fields_is_STALE(tmp_path):
    p = _levels_file(tmp_path, session_date="2026-07-30", expires="2026-07-30",
                     date_field="2026-07-29")
    _touch(p, dt.datetime(2026, 7, 30, 11, 35))
    assert lbc.check_levels_file(_ET_RTH, path=p)["status"] == lbc.STATUS_STALE


def test_unrewritten_file_during_rth_is_STALE_on_mtime(tmp_path):
    """Dated today, levels visible -- but nothing has TOUCHED the file for an hour. The
    producer is dead even though the content still looks plausible."""
    p = _levels_file(tmp_path, session_date="2026-07-30", expires="2026-07-30")
    _touch(p, dt.datetime(2026, 7, 30, 10, 30))  # 70m before _ET_RTH
    res = lbc.check_levels_file(_ET_RTH, path=p)
    assert res["status"] == lbc.STATUS_STALE
    assert "NOT REWRITTEN" in res["reason"]


def test_open_warmup_does_not_cry_wolf(tmp_path):
    p = _levels_file(tmp_path, session_date="2026-07-30", expires="2026-07-30")
    _touch(p, dt.datetime(2026, 7, 30, 8, 35))
    assert lbc.check_levels_file(dt.datetime(2026, 7, 30, 9, 36), path=p)["status"] == lbc.STATUS_FRESH


def test_pre_open_does_not_cry_wolf(tmp_path):
    p = _levels_file(tmp_path, session_date="2026-07-29", expires="2026-07-29")
    _touch(p, dt.datetime(2026, 7, 29, 22, 43))
    assert lbc.check_levels_file(dt.datetime(2026, 7, 30, 6, 0), path=p)["status"] == lbc.STATUS_FRESH


def test_weekend_file_is_not_applicable(tmp_path):
    p = _levels_file(tmp_path, session_date="2026-07-31", expires="2026-07-31")
    assert lbc.check_levels_file(_ET_SAT, path=p)["status"] == lbc.STATUS_NOT_APPLICABLE


def test_missing_or_garbled_file_is_UNKNOWN_never_raises(tmp_path):
    assert lbc.check_levels_file(_ET_RTH, path=tmp_path / "nope.json")["status"] == lbc.STATUS_UNKNOWN
    bad = tmp_path / "key-levels.json"
    bad.write_text("{not json", encoding="utf-8")
    assert lbc.check_levels_file(_ET_RTH, path=bad)["status"] == lbc.STATUS_UNKNOWN


def test_bite_mtime_threshold_is_non_vacuous(tmp_path):
    p = _levels_file(tmp_path, session_date="2026-07-30", expires="2026-07-30")
    _touch(p, dt.datetime(2026, 7, 30, 10, 30))
    assert lbc.check_levels_file(_ET_RTH, path=p)["status"] == lbc.STATUS_STALE
    assert lbc.check_levels_file(_ET_RTH, path=p, stale_min=10_000)["status"] == lbc.STATUS_FRESH


# =========================================================================== #
# 3. ENGINE PARITY + the timezone trap
# =========================================================================== #

def test_expiry_predicate_matches_heartbeat_core():
    """levels_blind_check.level_expired is a CLONE of heartbeat_core._level_expired. If the
    engine's expiry rule ever changes, this must RED rather than let the monitor silently
    disagree with the consumer it exists to watch (C14)."""
    hc = _load("heartbeat_core_parity_probe", "heartbeat_core.py")
    cases = [
        ({"expires_at": "2026-07-29T16:00:00-04:00"}, "2026-07-30"),
        ({"expires_at": "2026-07-30T16:00:00-04:00"}, "2026-07-30"),
        ({"expires_at": "2026-07-31"}, "2026-07-30"),
        ({"expires_at": None}, "2026-07-30"),
        ({}, "2026-07-30"),
        ({"expires_at": "garbage"}, "2026-07-30"),
        ({"expires_at": 12345}, "2026-07-30"),
    ]
    for lv, today in cases:
        assert lbc.level_expired(lv, today) == hc._level_expired(lv, today), lv


def test_mtime_is_read_as_ET_not_naive_local(tmp_path):
    """This rig runs MOUNTAIN (ET = local + 2). A raw datetime.fromtimestamp(mtime) would
    report every file 120 minutes FRESHER than it is and silently neuter the staleness
    branch -- the project's standing 'TIME = et_clock, never a naive local read' scar."""
    p = tmp_path / "f.json"
    p.write_text("{}", encoding="utf-8")
    target = dt.datetime(2026, 7, 30, 11, 0, 0)
    _touch(p, target)
    got = lbc.mtime_as_et(p)
    assert abs((got - target).total_seconds()) < 2, f"mtime_as_et returned {got}, expected {target}"
    naive_local = dt.datetime.fromtimestamp(p.stat().st_mtime)
    if naive_local != got:  # true on any host whose local tz != ET
        assert abs((got - naive_local).total_seconds()) > 60, \
            "mtime_as_et must not be a raw naive-local read"


def test_mtime_missing_file_is_none(tmp_path):
    assert lbc.mtime_as_et(tmp_path / "nope") is None


# =========================================================================== #
# 4. WIRING -- engine_health checks
# =========================================================================== #

@pytest.fixture
def blind_state(monkeypatch, tmp_path):
    """Point the SHARED levels_blind_check module at a synthetic blind day."""
    ledger = _ledger(tmp_path, "2026-07-30", 386, levels=[])
    levels = _levels_file(tmp_path, session_date="2026-07-29", expires="2026-07-29")
    _touch(levels, dt.datetime(2026, 7, 29, 22, 43))
    monkeypatch.setattr(lbc, "CORE_DECISIONS", ledger)
    monkeypatch.setattr(lbc, "KEY_LEVELS", levels)
    return tmp_path


@pytest.fixture
def sighted_state(monkeypatch, tmp_path):
    ledger = _ledger(tmp_path, "2026-07-30", 386, levels=[738.1])
    levels = _levels_file(tmp_path, session_date="2026-07-30", expires="2026-07-30")
    _touch(levels, dt.datetime(2026, 7, 30, 11, 35))
    monkeypatch.setattr(lbc, "CORE_DECISIONS", ledger)
    monkeypatch.setattr(lbc, "KEY_LEVELS", levels)
    return tmp_path


def test_engine_health_levels_blind_reds_on_a_blind_day(blind_state):
    chk = eh.check_levels_blind(_ET_RTH)
    assert chk["name"] == "levels_blind"
    assert chk["status"] == "RED"
    assert chk["critical"] is True


def test_engine_health_levels_blind_is_NOT_market_closed_suppressed(blind_state):
    """The whole point. At 18:45 ET every other check says "market closed -- quiet OK";
    this one must still shout, or the 2026-07-30 outage reads GREEN again."""
    chk = eh.check_levels_blind(_ET_AFTER_CLOSE)
    assert chk["status"] == "RED", "market-closed must NEVER suppress the blindness check"


def test_engine_health_levels_blind_green_on_a_normal_day(sighted_state):
    assert eh.check_levels_blind(_ET_RTH)["status"] == "GREEN"


def test_engine_health_levels_file_stale_reds_after_close(blind_state):
    chk = eh.check_levels_file_stale(_ET_AFTER_CLOSE)
    assert chk["name"] == "levels_file_stale"
    assert chk["status"] == "RED"
    assert chk["critical"] is False, "a producer-side stall must never be a critical trade-halt"


def test_engine_health_levels_file_stale_green_when_fresh(sighted_state):
    assert eh.check_levels_file_stale(_ET_RTH)["status"] == "GREEN"


def test_engine_health_both_checks_fail_open_when_module_is_broken(monkeypatch):
    """A broken MONITOR must degrade to a benign YELLOW, never crash the beacon (house rule)."""
    monkeypatch.setattr(eh, "_import_levels_blind", lambda: None)
    for fn in (eh.check_levels_blind, eh.check_levels_file_stale):
        chk = fn(_ET_RTH)
        assert chk["status"] == "YELLOW" and chk["critical"] is False


def test_engine_health_checks_survive_a_raising_assessor(monkeypatch):
    class Boom:
        STATUS_BLIND = "BLIND"
        STATUS_STALE = "STALE"
        STATUS_UNKNOWN = "UNKNOWN"
        STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
        STATUS_INSUFFICIENT = "INSUFFICIENT"

        @staticmethod
        def check_day(_day):
            raise RuntimeError("boom")

        @staticmethod
        def check_levels_file(_et):
            raise RuntimeError("boom")

    monkeypatch.setattr(eh, "_import_levels_blind", lambda: Boom)
    assert eh.check_levels_blind(_ET_RTH)["status"] == "YELLOW"
    assert eh.check_levels_file_stale(_ET_RTH)["status"] == "YELLOW"


def test_blind_red_drives_the_fused_verdict_red():
    checks = [eh._chk("heartbeat_safe", "GREEN", "ok", critical=True),
              eh._chk("levels_blind", "RED", "ENGINE TRADED BLIND", critical=True)]
    verdict, reds = eh.fuse(checks)
    assert verdict == "RED"
    assert any("levels_blind" in r for r in reds)


def test_file_stale_red_only_degrades_to_yellow():
    checks = [eh._chk("heartbeat_safe", "GREEN", "ok", critical=True),
              eh._chk("levels_file_stale", "RED", "STALE-DATED", critical=False)]
    assert eh.fuse(checks)[0] == "YELLOW"


def test_build_report_wires_both_checks():
    names = [c["name"] for c in eh.build_report()["checks"]]
    assert "levels_blind" in names and "levels_file_stale" in names


# =========================================================================== #
# 5. WIRING -- daily_brief EOD lead line
# =========================================================================== #

def _eod_facts(day="2026-07-30"):
    return db.gather_eod_facts(day, pnl={"source": "t", "total_pnl": -12.0, "by_arm": []})


def test_eod_brief_leads_with_the_blind_alarm(blind_state, monkeypatch):
    monkeypatch.setattr(db, "_liveness_alarm", lambda _day: None)
    text = db.compose_eod_text(_eod_facts())
    assert "traded blind" in text
    # LEADS: the alarm must appear before any P&L wording.
    assert text.index("traded blind") < text.index("Overall I was"), \
        "J must hear 'I was blind' BEFORE he hears P&L"


def test_eod_brief_silent_on_a_normal_day(sighted_state, monkeypatch):
    monkeypatch.setattr(db, "_liveness_alarm", lambda _day: None)
    assert "traded blind" not in db.compose_eod_text(_eod_facts())


def test_eod_brief_still_composes_when_the_checker_raises(monkeypatch):
    """Fail-open: a broken blindness checker must never break the one surface that reaches J."""
    monkeypatch.setattr(lbc, "check_day", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(db, "_liveness_alarm", lambda _day: None)
    text = db.compose_eod_text(_eod_facts())
    assert "End of day" in text and "Overall I was" in text


def test_blind_alarm_helper_returns_none_on_import_failure(monkeypatch):
    monkeypatch.setitem(sys.modules, "levels_blind_check", None)
    assert db._blind_alarm("2026-07-30") is None


# =========================================================================== #
# 6. WIRING -- premarket_readiness levels_sanity hardening
# =========================================================================== #

def _good(session="2026-07-30", expires="2026-07-30", date_field=None):
    return {
        "as_of": f"{session}T09:00:00-04:00",
        "for_session": session,
        "date": session if date_field is None else date_field,
        "spot_at_compute": 740.0,
        "levels": [{"price": 736.0, "expires_at": f"{expires}T16:00:00-04:00"},
                   {"price": 738.0, "expires_at": f"{expires}T16:00:00-04:00"},
                   {"price": 742.0, "expires_at": f"{expires}T16:00:00-04:00"},
                   {"price": 744.0, "expires_at": f"{expires}T16:00:00-04:00"}],
    }


_ET_PREMARKET = dt.datetime(2026, 7, 30, 9, 0, 0)


def test_levels_sanity_green_on_a_good_file(monkeypatch):
    monkeypatch.setattr(pr, "_levels_file_mtime_age_min", lambda *a, **k: 3.0)
    chk = pr.assess_levels_sanity(_good(), _ET_PREMARKET)
    assert chk["status"] == "GREEN", chk["detail"]


def test_levels_sanity_reds_on_the_2026_07_30_file(monkeypatch):
    """The real incident file: for_session 2026-07-29 on 2026-07-30."""
    monkeypatch.setattr(pr, "_levels_file_mtime_age_min", lambda *a, **k: 3.0)
    chk = pr.assess_levels_sanity(_good(session="2026-07-29", expires="2026-07-29"),
                                  _ET_PREMARKET)
    assert chk["status"] == "RED" and chk["critical"] is True


def test_levels_sanity_reds_when_date_fields_disagree(monkeypatch):
    """Stale-dated even though it parses: a half-written refresh updated for_session only."""
    monkeypatch.setattr(pr, "_levels_file_mtime_age_min", lambda *a, **k: 3.0)
    chk = pr.assess_levels_sanity(_good(date_field="2026-07-29"), _ET_PREMARKET)
    assert chk["status"] == "RED"
    assert "half-written" in chk["detail"]


def test_levels_sanity_reds_when_engine_would_see_zero_levels(monkeypatch):
    """Dated today, 4 levels, straddling spot, fresh as_of -- and every one of them expired
    yesterday, so heartbeat_core's own rule leaves levels_active [] every tick."""
    monkeypatch.setattr(pr, "_levels_file_mtime_age_min", lambda *a, **k: 3.0)
    chk = pr.assess_levels_sanity(_good(expires="2026-07-29"), _ET_PREMARKET)
    assert chk["status"] == "RED" and chk["critical"] is True
    assert "ZERO LEVELS" in chk["detail"]


def test_levels_sanity_reds_on_stale_mtime_despite_fresh_as_of(monkeypatch):
    """`as_of` is a string the writer chose; mtime is what the filesystem observed."""
    monkeypatch.setattr(pr, "_levels_file_mtime_age_min", lambda *a, **k: 600.0)
    chk = pr.assess_levels_sanity(_good(), _ET_PREMARKET)
    assert chk["status"] == "RED"
    assert "NOT REWRITTEN" in chk["detail"]


def test_levels_sanity_tolerates_an_unstattable_file(monkeypatch):
    """Fail-open: if mtime cannot be read the gate falls back to the other evidence, it does
    not block the morning."""
    monkeypatch.setattr(pr, "_levels_file_mtime_age_min", lambda *a, **k: None)
    assert pr.assess_levels_sanity(_good(), _ET_PREMARKET)["status"] == "GREEN"


def test_levels_sanity_never_raises_via_safe_checks():
    """A checker that blows up degrades to ONE UNKNOWN row -- never a crash, never a block."""
    out = pr._safe_checks("levels_sanity", True, pr.assess_levels_sanity,
                          {"levels": "not-a-list"}, _ET_PREMARKET)
    assert len(out) == 1 and out[0]["status"] in ("RED", "UNKNOWN")


def test_engine_visible_count_fails_open_to_none(monkeypatch):
    monkeypatch.setitem(sys.modules, "levels_blind_check", None)
    assert pr._engine_visible_count(_good(), "2026-07-30") is None


def test_levels_sanity_uses_the_engines_date_only_expiry_rule():
    """REGRESSION, found live 2026-07-30 at 19:06 ET. The gate used to re-derive expiry with
    a FULL-DATETIME comparison, so once the wall clock passed a level's time-of-day it
    reported "0 non-expired valid levels" (RED) on a healthy file the ENGINE still read as 19
    levels. Two parallel re-derivations of one rule, drifting exactly as C14 warns. The gate
    must answer "what will the engine see", so it uses heartbeat_core's DATE-ONLY predicate."""
    data = _good(expires="2026-07-30")            # levels expire today at 16:00
    after_their_time = dt.datetime(2026, 7, 30, 19, 6, 0)
    assert pr._level_expired_engine_rule(data["levels"][0], "2026-07-30", after_their_time) is False
    chk = pr.assess_levels_sanity(data, after_their_time)
    assert "0 non-expired" not in chk["detail"], \
        "a level expiring at 16:00 TODAY is still today's level to the engine"


def test_levels_sanity_still_drops_levels_expired_on_a_PRIOR_day():
    """The parity change must not weaken the real check: a prior-DATE expiry is dropped by
    both rules, and a file of only those is still RED."""
    chk = pr.assess_levels_sanity(_good(expires="2026-07-28"),
                                  dt.datetime(2026, 7, 30, 9, 0, 0))
    assert chk["status"] == "RED"


def test_level_expired_engine_rule_falls_back_when_module_missing(monkeypatch):
    """Fail-open must not become fail-SILENT: with the helper gone, the old datetime rule
    still drops a prior-day level rather than waving it through."""
    monkeypatch.setitem(sys.modules, "levels_blind_check", None)
    lv = {"price": 740.0, "expires_at": "2026-07-28T16:00:00-04:00"}
    assert pr._level_expired_engine_rule(lv, "2026-07-30", dt.datetime(2026, 7, 30, 9, 0, 0)) is True
