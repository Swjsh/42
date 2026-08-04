"""Guard for premarket_readiness.py -- the ONE deterministic morning readiness gate (WS2,
2026-07-27). Locks the RED-proofing this build was explicitly required to have:

  * a missing/unreachable fleet arm REDs and NAMES the arm (the exact "missed 3 of 6
    accounts" class of miss that motivated this build -- a vague aggregate row must never
    be able to hide which account is dark).
  * an all-resistance (or all-support) key-levels.json REDs check 3.
  * TV/CDP down degrades the OVERALL verdict to YELLOW, never RED, when every other check
    is GREEN (the engine trades headless via sight_beacon even with TV dead).
  * a checker that raises internally degrades to ONE UNKNOWN row, never crashes the report.

Imports the script by path (matches this repo's engine_health.py / preopen_readiness.py test
convention) so it works whether or not setup/scripts is on sys.path as a package.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "setup" / "scripts" / "premarket_readiness.py"
_spec = importlib.util.spec_from_file_location("premarket_readiness_under_test", _SCRIPT)
pr = importlib.util.module_from_spec(_spec)
sys.modules["premarket_readiness_under_test"] = pr
_spec.loader.exec_module(pr)  # type: ignore


def _et(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- #
# fuse() -- the overall-verdict contract.
# --------------------------------------------------------------------------- #

def test_fuse_all_green_is_green():
    checks = [pr._chk("a", "GREEN", "ok", True), pr._chk("b", "GREEN", "ok", False)]
    assert pr.fuse(checks) == "GREEN"


def test_fuse_critical_red_is_red():
    checks = [pr._chk("a", "GREEN", "ok", True), pr._chk("b", "RED", "bad", True)]
    assert pr.fuse(checks) == "RED"


def test_fuse_noncritical_red_is_yellow_not_red():
    """TV/CDP down (non-critical) with everything else GREEN must read YELLOW, never RED --
    the explicit guard this build was proofed against."""
    checks = [pr._chk("engine_health", "GREEN", "ok", True),
              pr._chk("tv_cdp", "RED", "down", False)]
    assert pr.fuse(checks) == "YELLOW"


def test_fuse_unknown_is_yellow_not_red_and_not_silently_green():
    checks = [pr._chk("a", "GREEN", "ok", True), pr._chk("b", "UNKNOWN", "crashed", True)]
    assert pr.fuse(checks) == "YELLOW"


# --------------------------------------------------------------------------- #
# _safe_checks -- a crashing assessor must degrade, never propagate.
# --------------------------------------------------------------------------- #

def test_safe_checks_catches_exception_as_unknown():
    def _boom():
        raise ValueError("synthetic failure")
    rows = pr._safe_checks("some_check", True, _boom)
    assert len(rows) == 1
    assert rows[0]["status"] == "UNKNOWN"
    assert rows[0]["critical"] is True
    assert "synthetic failure" in rows[0]["detail"]


def test_safe_checks_passthrough_list_and_single():
    assert pr._safe_checks("x", True, lambda: pr._chk("x", "GREEN", "ok", True)) == \
        [pr._chk("x", "GREEN", "ok", True)]
    two = [pr._chk("a", "GREEN", "ok", True), pr._chk("b", "GREEN", "ok", True)]
    assert pr._safe_checks("x", True, lambda: two) == two


# --------------------------------------------------------------------------- #
# assess_fleet_liveness -- check 1, the load-bearing per-arm naming guard.
# --------------------------------------------------------------------------- #

_ARMS = [{"id": "safe-2", "execution": "mcp_heartbeat"},
         {"id": "safe-3", "execution": "fleet_rest"},
         {"id": "risky-1", "execution": "fleet_rest"}]


def _snap(status="ACTIVE", equity=2000.0, blocked=False):
    return {"status": status, "equity": equity, "trading_blocked": blocked, "account_blocked": False}


def test_fleet_liveness_all_reachable_before_open_is_green_without_ledger_check():
    snapshots = {a["id"]: _snap() for a in _ARMS}
    checks = pr.assess_fleet_liveness(_ARMS, snapshots, {}, _et("2026-07-28 08:00:00"), after_open=False)
    assert len(checks) == 3
    assert all(c["status"] == "GREEN" for c in checks)
    assert {c["name"] for c in checks} == {"fleet:safe-2", "fleet:safe-3", "fleet:risky-1"}


def test_fleet_liveness_missing_arm_ledger_after_open_reds_and_names_the_arm():
    """The bite: risky-1 is broker-reachable but has ZERO decision rows today, after 09:35
    ET on a weekday -- must RED and the detail/name must identify risky-1 specifically."""
    snapshots = {a["id"]: _snap() for a in _ARMS}
    decision_counts = {"safe-2": (400, "2026-07-28"), "safe-3": (50, "2026-07-28"),
                        "risky-1": (0, "2026-07-25")}  # dark since Friday
    checks = pr.assess_fleet_liveness(_ARMS, snapshots, decision_counts,
                                       _et("2026-07-28 10:00:00"), after_open=True)
    by_name = {c["name"]: c for c in checks}
    assert by_name["fleet:risky-1"]["status"] == "RED"
    assert "risky-1" in by_name["fleet:risky-1"]["detail"]
    assert "NO decision rows" in by_name["fleet:risky-1"]["detail"]
    assert by_name["fleet:safe-2"]["status"] == "GREEN"
    assert by_name["fleet:safe-3"]["status"] == "GREEN"
    assert pr.fuse(checks) == "RED"


def test_fleet_liveness_unreachable_broker_reds_and_names_the_arm():
    snapshots = {"safe-2": _snap(), "safe-3": {"_error": "HTTP 401"}, "risky-1": _snap()}
    checks = pr.assess_fleet_liveness(_ARMS, snapshots, {}, _et("2026-07-28 08:00:00"), after_open=False)
    by_name = {c["name"]: c for c in checks}
    assert by_name["fleet:safe-3"]["status"] == "RED"
    assert "safe-3" in by_name["fleet:safe-3"]["detail"]
    assert "401" in by_name["fleet:safe-3"]["detail"]


def test_fleet_liveness_blocked_account_is_red():
    snapshots = {a["id"]: _snap() for a in _ARMS}
    snapshots["safe-2"] = _snap(blocked=True)
    checks = pr.assess_fleet_liveness(_ARMS, snapshots, {}, _et("2026-07-28 08:00:00"), after_open=False)
    by_name = {c["name"]: c for c in checks}
    assert by_name["fleet:safe-2"]["status"] == "RED"


# --------------------------------------------------------------------------- #
# assess_core_mcp -- check 2.
# --------------------------------------------------------------------------- #

def test_core_mcp_both_reachable_is_green():
    snapshots = {"safe-2": _snap(), "bold-2": _snap()}
    servers = {"alpaca": True, "alpaca_aggressive": True}
    checks = pr.assess_core_mcp(snapshots, servers)
    assert len(checks) == 2
    assert all(c["status"] == "GREEN" for c in checks)


def test_core_mcp_missing_server_key_is_red():
    servers = {"alpaca": True, "alpaca_aggressive": False}
    checks = pr.assess_core_mcp({"safe-2": _snap()}, servers)
    by_name = {c["name"]: c for c in checks}
    assert by_name["core_mcp:alpaca_aggressive"]["status"] == "RED"
    assert "bold-2" in by_name["core_mcp:alpaca_aggressive"]["detail"]


def test_core_mcp_unreachable_account_is_red():
    servers = {"alpaca": True, "alpaca_aggressive": True}
    snapshots = {"safe-2": _snap(), "bold-2": {"_error": "timeout"}}
    checks = pr.assess_core_mcp(snapshots, servers)
    by_name = {c["name"]: c for c in checks}
    assert by_name["core_mcp:alpaca_aggressive"]["status"] == "RED"


# --------------------------------------------------------------------------- #
# assess_levels_sanity -- check 3, RED-proofed guards from the spec.
# --------------------------------------------------------------------------- #

def _good_levels(today="2026-07-28", spot=740.0):
    return {
        "for_session": today,
        "as_of": f"{today}T09:00:00-04:00",
        "spot_at_compute": spot,
        "levels": [
            {"price": 735.0, "type": "support", "expires_at": f"{today}T16:00:00-04:00"},
            {"price": 736.0, "type": "support", "expires_at": f"{today}T16:00:00-04:00"},
            {"price": 744.0, "type": "resistance", "expires_at": f"{today}T16:00:00-04:00"},
            {"price": 745.0, "type": "resistance", "expires_at": f"{today}T16:00:00-04:00"},
        ],
    }


def test_levels_sanity_good_file_is_green():
    check = pr.assess_levels_sanity(_good_levels(), _et("2026-07-28 09:10:00"))
    assert check["status"] == "GREEN"


def test_levels_sanity_missing_file_is_red():
    check = pr.assess_levels_sanity(None, _et("2026-07-28 09:10:00"))
    assert check["status"] == "RED"


def test_levels_sanity_wrong_session_date_is_red():
    data = _good_levels(today="2026-07-25")
    check = pr.assess_levels_sanity(data, _et("2026-07-28 09:10:00"))
    assert check["status"] == "RED"
    assert "for_session" in check["detail"]


def test_levels_sanity_all_resistance_is_red():
    """The explicit spec guard: an all-resistance level file must RED check 3."""
    data = _good_levels()
    data["levels"] = [lv for lv in data["levels"] if lv["type"] == "resistance"] + [
        {"price": 746.0, "type": "resistance", "expires_at": "2026-07-28T16:00:00-04:00"},
        {"price": 747.0, "type": "resistance", "expires_at": "2026-07-28T16:00:00-04:00"},
    ]
    check = pr.assess_levels_sanity(data, _et("2026-07-28 09:10:00"))
    assert check["status"] == "RED"
    assert "one-sided" in check["detail"]


def test_levels_sanity_too_few_valid_levels_is_red():
    data = _good_levels()
    data["levels"] = data["levels"][:2]  # only 2, below the 4-minimum
    check = pr.assess_levels_sanity(data, _et("2026-07-28 09:10:00"))
    assert check["status"] == "RED"
    assert "non-expired valid level" in check["detail"]


def test_levels_sanity_degenerate_entries_dont_count():
    data = _good_levels()
    data["levels"].append({"price": -5.0, "type": "support"})  # degenerate: negative price
    data["levels"].append({"type": "support"})  # degenerate: no price at all
    check = pr.assess_levels_sanity(data, _et("2026-07-28 09:10:00"))
    assert check["status"] == "GREEN"  # the 4 good ones still clear the bar
    assert "4 valid levels" in check["detail"]


def test_levels_sanity_expired_levels_excluded():
    data = _good_levels()
    for lv in data["levels"]:
        lv["expires_at"] = "2026-07-27T16:00:00-04:00"  # expired by the time we check
    check = pr.assess_levels_sanity(data, _et("2026-07-28 09:10:00"))
    assert check["status"] == "RED"  # all 4 expired -> 0 valid


def test_levels_sanity_stale_age_is_red():
    data = _good_levels()
    data["as_of"] = "2026-07-28T06:00:00-04:00"  # 3h10m before the 09:10 check -- > 90m
    check = pr.assess_levels_sanity(data, _et("2026-07-28 09:10:00"))
    assert check["status"] == "RED"
    assert "stale" in check["detail"]


# --------------------------------------------------------------------------- #
# assess_bias_freshness -- check 4, advisory-only (never RED).
# --------------------------------------------------------------------------- #

def test_bias_freshness_missing_is_yellow_not_red():
    check = pr.assess_bias_freshness(None, _et("2026-07-28 09:10:00"))
    assert check["status"] == "YELLOW"
    assert check["critical"] is False


def test_bias_freshness_stale_date_is_yellow():
    check = pr.assess_bias_freshness({"date": "2026-07-25", "bias": "bullish"}, _et("2026-07-28 09:10:00"))
    assert check["status"] == "YELLOW"


def test_bias_freshness_fresh_is_green():
    check = pr.assess_bias_freshness({"date": "2026-07-28", "bias": "bullish"}, _et("2026-07-28 09:10:00"))
    assert check["status"] == "GREEN"


# --------------------------------------------------------------------------- #
# assess_trendline_watch -- check 8 (LANE-4 2026-08-03), carried-overnight visibility.
# VISIBILITY-ONLY: advisory (never RED, never critical) -- the trendline entry-signal
# form is graveyarded; this row only makes the overnight carry VISIBLE at 09:00.
# --------------------------------------------------------------------------- #

_TL_WATCH = {
    "live_state_date_et": "2026-08-03",
    "active_lines": [{"kind": "support", "flavor": "wick", "status": "TESTING",
                      "current_value": 757.58, "respect_count": 60}],
    "nearest_active": {"kind": "support", "flavor": "wick", "status": "TESTING",
                       "current_value": 757.58},
}


def test_trendline_watch_carried_overnight_is_green_and_names_the_line():
    """Tuesday 09:00 reading Monday's carry: GREEN, detail carries the line essence."""
    check = pr.assess_trendline_watch(_TL_WATCH, _et("2026-08-04 09:00:00"))
    assert check["status"] == "GREEN"
    assert check["critical"] is False
    assert "1 line(s) carried from 2026-08-03" in check["detail"]
    assert "757.58" in check["detail"]
    assert "resumes 09:30 ET" in check["detail"]


def test_trendline_watch_missing_is_yellow_never_red():
    check = pr.assess_trendline_watch(None, _et("2026-08-04 09:00:00"))
    assert check["status"] == "YELLOW"
    assert check["critical"] is False


def test_trendline_watch_week_stale_is_yellow_dead_producer():
    stale = dict(_TL_WATCH, live_state_date_et="2026-07-27")
    check = pr.assess_trendline_watch(stale, _et("2026-08-04 09:00:00"))
    assert check["status"] == "YELLOW"
    assert "STALE" in check["detail"]


def test_trendline_watch_weekend_carry_is_green():
    """Monday reading Friday's state (3 calendar days) is normal carry, not staleness."""
    fri = dict(_TL_WATCH, live_state_date_et="2026-07-31")
    check = pr.assess_trendline_watch(fri, _et("2026-08-03 09:00:00"))
    assert check["status"] == "GREEN"


def test_trendline_watch_can_never_red_the_gate():
    """RED-proof of the visibility-only contract: even a maximally-broken watch payload
    fused with all-GREEN critical checks can only ever YELLOW the verdict."""
    broken = pr.assess_trendline_watch({"live_state_date_et": "garbage"}, _et("2026-08-04 09:00:00"))
    assert broken["status"] in ("YELLOW", "GREEN")
    fused = pr.fuse([
        {"name": "fleet:x", "status": "GREEN", "detail": "", "critical": True},
        broken,
    ])
    assert fused != "RED"


# --------------------------------------------------------------------------- #
# assess_tv_cdp -- check 5, the "down -> YELLOW never RED" guard.
# --------------------------------------------------------------------------- #

def test_tv_cdp_down_is_yellow_not_red():
    check = pr.assess_tv_cdp({"reachable": False, "detail": "connection refused"})
    assert check["status"] == "YELLOW"
    assert check["critical"] is False


def test_tv_cdp_up_is_green():
    check = pr.assess_tv_cdp({"reachable": True, "detail": "CDP responding on :9222"})
    assert check["status"] == "GREEN"


# --------------------------------------------------------------------------- #
# assess_engine_health -- check 6, reuse-not-reimplement.
# --------------------------------------------------------------------------- #

def test_engine_health_passthrough_verdict():
    for v in ("GREEN", "YELLOW", "RED"):
        check = pr.assess_engine_health({"verdict": v, "reds": ["x"] if v == "RED" else []})
        assert check["status"] == v
        assert check["critical"] is True


def test_engine_health_none_is_unknown():
    check = pr.assess_engine_health(None)
    assert check["status"] == "UNKNOWN"


# --------------------------------------------------------------------------- #
# assess_heartbeat_task -- check 7.
# --------------------------------------------------------------------------- #

def test_heartbeat_task_missing_is_red():
    check = pr.assess_heartbeat_task(None)
    assert check["status"] == "RED"


def test_heartbeat_task_ready_is_green():
    check = pr.assess_heartbeat_task({"state": "Ready", "last_result": 0})
    assert check["status"] == "GREEN"


def test_heartbeat_task_disabled_is_red():
    check = pr.assess_heartbeat_task({"state": "Disabled", "last_result": 0})
    assert check["status"] == "RED"


# --------------------------------------------------------------------------- #
# fetch_active_arms -- the "enabled" filter against the REAL accounts.json (integration,
# no network -- proves the frozen safe-1 (status="retired") is excluded by construction).
# --------------------------------------------------------------------------- #

def test_fetch_active_arms_excludes_retired_safe1_and_pending_futures():
    arms = pr.fetch_active_arms()
    ids = {a["id"] for a in arms}
    assert "safe-1" not in ids, "frozen safe-1 (status=retired) must never be treated as enabled"
    assert "mes-linear-sim" not in ids
    assert "mes-mnq-div-futures" not in ids
    # The 5 real active equity arms as of this build (2026-07-27) must all be present.
    assert {"safe-2", "safe-3", "bold-2", "risky-1", "risky-3"} <= ids
