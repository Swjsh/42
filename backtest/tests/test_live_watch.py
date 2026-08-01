"""Guard tests for setup/scripts/live_watch.py -- the WS7 LIVE WATCH canonical state
surface (automation/state/live-watch.json + Gamma_LiveWatch).

Covers the build brief's explicit requirements:
  1. Synthetic injected position -> EVERY required field populates (direct view AND the
     full assemble_arm path) -- the weekend-runnable capability proof in guard form.
  2. Stop/TP/HWM math: premium + structure modes, TP phase flip after tp1_filled,
     structure-level distance sign per side (OCC fallback when side absent).
  3. CLOSED no-spam: exactly ONE write when the market is closed; the second tick is a
     no-op (RED-proof: deleting the already-CLOSED skip re-introduces per-minute churn).
  4. Fail-open (C7): a raising broker degrades the arm, never sinks the tick; a crashing
     build still exits 0 and leaves a loud error snapshot.
  5. Kill-switch normalization across the THREE breaker vocabularies (C9 symmetry trap:
     aggressive uses trip_reason/equity_start_of_day, safe/fleet use tripped_reason/
     starting_equity_today). RED-proof: reading safe keys on the bold file nulls out.
  6. Decision routing: core ledger split by account for safe-2/bold-2, per-arm fleet
     ledger otherwise; age computed.
  7. Entry-time cache: same symbol in the previous snapshot -> broker orders endpoint is
     NOT re-asked; new symbol -> it is.
  8. theta-clock.json link-in is READ-ONLY (mtime unchanged) and absent-tolerant.
  9. Atomic write leaves valid JSON and no .tmp turd (dashboard polls every 3s).
 10. Market window edges + active-arm filter (retired/futures arms excluded).

Pure-logic + tmp_path only -- no network, no real credentials, no live state touched.
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for p in (str(SCRIPTS), str(FLEET_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _lw():
    return importlib.import_module("live_watch")


NOW = dt.datetime(2026, 8, 3, 10, 15, 0)  # Monday mid-RTH


# --------------------------------------------------------------------------- #
# 1. synthetic capability proof
# --------------------------------------------------------------------------- #
def test_synthetic_every_required_field_populates_direct_view():
    lw = _lw()
    arm, creds, broker = lw.synthetic_fixture()
    view = lw.build_position_view(
        pos_raw=broker.positions(creds)[0], exit_rec=lw.SYNTHETIC_EXIT_REC,
        mid=0.71, mid_source="option_quote_mid", spy_last=746.79,
        entry_time_et="2026-08-03T09:52:00", now_et=NOW)
    missing = [k for k in lw.REQUIRED_POSITION_FIELDS if view.get(k) is None]
    assert missing == [], f"fields failed to populate: {missing}"
    # spot-check the values are REAL numbers, not just non-None
    assert view["qty"] == 5 and view["entry_premium"] == 0.62
    assert view["time_in_trade_min"] == pytest.approx(23.0)
    assert view["exit_state_found"] is True


def test_synthetic_every_required_field_populates_assembly_path():
    lw = _lw()
    arm, creds, broker = lw.synthetic_fixture()
    entry = lw.assemble_arm(
        arm=arm, creds=creds, broker=broker, spy_last=746.79, now_et=NOW,
        core_lines=[json.dumps({"account": "safe", "verdict": "HOLD",
                                "reason": "no trigger", "ts_et": "2026-08-03T10:14:03"})],
        prev_arm=None,
        exit_state_override={lw.SYNTHETIC_EXIT_REC["symbol"]: lw.SYNTHETIC_EXIT_REC})
    assert entry["in_trade"] is True
    pos = entry["position"]
    assert isinstance(pos, dict)
    missing = [k for k in lw.REQUIRED_POSITION_FIELDS if pos.get(k) is None]
    assert missing == [], f"assembly-path fields failed to populate: {missing}"
    # decision + age wired through the same assembly
    assert entry["last_decision"]["verdict"] == "HOLD"
    assert entry["last_decision"]["age_min"] == pytest.approx(1.0, abs=0.1)


# --------------------------------------------------------------------------- #
# 2. stop / TP / HWM math
# --------------------------------------------------------------------------- #
def _mk_exit_rec(**over):
    rec = dict(symbol="SPY260803C00745000", side="C", entry_premium=1.00, total_qty=3,
               tp1_qty=2, runner_qty=1, premium_stop_pct=-0.50, tp1_premium_pct=0.30,
               profit_lock_mode="trailing", runner_target_pct=2.5, trail_pct=0.15,
               profit_lock_arm_pct=0.05, tp1_filled=False, runner_stop_premium=0.50,
               hwm_premium=1.20, profit_lock_armed=False, strategy="ribbon_ride",
               stop_mode="premium", trigger_level=None, catastrophe_stop_pct=-0.50,
               profit_lock_arm_scope="post_tp1")
    rec.update(over)
    return rec


def _pos_raw(**over):
    p = {"symbol": "SPY260803C00745000", "qty": "3", "avg_entry_price": "1.00",
         "current_price": "1.10", "unrealized_pl": "30.0", "unrealized_plpc": "0.10"}
    p.update(over)
    return p


def test_premium_mode_distances_and_tp1_phase():
    lw = _lw()
    v = lw.build_position_view(pos_raw=_pos_raw(), exit_rec=_mk_exit_rec(), mid=1.10,
                               mid_source="option_quote_mid", spy_last=746.0,
                               entry_time_et="2026-08-03T10:00:00", now_et=NOW)
    assert v["stop_mode"] == "premium"
    # (1.10 - 0.50) / 1.10 = 54.5% cushion to the stop
    assert v["dist_to_stop_pct"] == pytest.approx(54.5, abs=0.1)
    # TP1 target 1.00 * 1.30 = 1.30 -> (1.30-1.10)/1.10 = +18.2% to travel
    assert v["tp_phase"] == "TP1"
    assert v["tp_target_premium"] == pytest.approx(1.30)
    assert v["dist_to_tp_pct"] == pytest.approx(18.2, abs=0.1)
    # HWM 1.20 on 1.00 entry = +20%
    assert v["hwm_gain_pct"] == pytest.approx(20.0)
    # broker P&L preferred verbatim
    assert v["unrealized_pnl_usd"] == 30.0 and v["unrealized_pnl_pct"] == 10.0


def test_tp_phase_flips_to_runner_after_tp1_filled():
    lw = _lw()
    v = lw.build_position_view(pos_raw=_pos_raw(), exit_rec=_mk_exit_rec(tp1_filled=True),
                               mid=1.10, mid_source="option_quote_mid", spy_last=746.0,
                               entry_time_et="2026-08-03T10:00:00", now_et=NOW)
    assert v["tp_phase"] == "RUNNER"
    assert v["tp_target_premium"] == pytest.approx(3.50)  # 1.00 * (1 + 2.5)


def test_structure_mode_level_distance_sign_and_occ_fallback():
    lw = _lw()
    rec = _mk_exit_rec(stop_mode="structure", trigger_level=744.50)
    v = lw.build_position_view(pos_raw=_pos_raw(), exit_rec=rec, mid=1.10,
                               mid_source="option_quote_mid", spy_last=745.20,
                               entry_time_et="2026-08-03T10:00:00", now_et=NOW)
    assert v["dist_to_stop_level_pts"] == pytest.approx(0.70)  # call: spy - trigger
    # put side: cushion flips
    rec_p = _mk_exit_rec(stop_mode="structure", trigger_level=744.50, side="P",
                         symbol="SPY260803P00745000")
    v_p = lw.build_position_view(pos_raw=_pos_raw(symbol="SPY260803P00745000"),
                                 exit_rec=rec_p, mid=1.10, mid_source="option_quote_mid",
                                 spy_last=745.20, entry_time_et="2026-08-03T10:00:00",
                                 now_et=NOW)
    assert v_p["dist_to_stop_level_pts"] == pytest.approx(-0.70)
    # side absent -> OCC right decides (C symbol => call math)
    rec_n = _mk_exit_rec(stop_mode="structure", trigger_level=744.50, side=None)
    v_n = lw.build_position_view(pos_raw=_pos_raw(), exit_rec=rec_n, mid=1.10,
                                 mid_source="option_quote_mid", spy_last=745.20,
                                 entry_time_et="2026-08-03T10:00:00", now_et=NOW)
    assert v_n["dist_to_stop_level_pts"] == pytest.approx(0.70)


def test_missing_exit_state_yields_honest_nones_not_fabrications():
    lw = _lw()
    v = lw.build_position_view(pos_raw=_pos_raw(), exit_rec=None, mid=1.10,
                               mid_source="option_quote_mid", spy_last=746.0,
                               entry_time_et=None, now_et=NOW)
    assert v["exit_state_found"] is False
    for k in ("stop_premium", "dist_to_stop_pct", "tp_target_premium", "hwm_premium",
              "time_in_trade_min"):
        assert v[k] is None
    # broker-sourced fields still populate
    assert v["mid"] == 1.10 and v["unrealized_pnl_usd"] == 30.0


# --------------------------------------------------------------------------- #
# 3. CLOSED no-spam
# --------------------------------------------------------------------------- #
def test_closed_writes_once_then_silent(tmp_path, monkeypatch, capsys):
    lw = _lw()
    out = tmp_path / "live-watch.json"
    monkeypatch.setattr(lw, "OUT_PATH", out)
    monkeypatch.setattr(lw, "THETA_PATH", tmp_path / "absent-theta.json")
    monkeypatch.setattr(lw, "market_state_for", lambda now: "CLOSED")
    writes = []
    orig = lw._atomic_write_json
    monkeypatch.setattr(lw, "_atomic_write_json",
                        lambda p, d: (writes.append(str(p)), orig(p, d)))
    assert lw.run_once() == 0
    assert lw.run_once() == 0
    assert len(writes) == 1, "second CLOSED tick must NOT rewrite (no-spam contract)"
    snap = json.loads(out.read_text(encoding="utf-8"))
    assert snap["market_state"] == "CLOSED" and snap["arms"] == {}


def test_closed_replaces_a_stale_rth_snapshot_exactly_once(tmp_path, monkeypatch):
    lw = _lw()
    out = tmp_path / "live-watch.json"
    out.write_text(json.dumps({"market_state": "RTH", "arms": {"safe-2": {}}}),
                   encoding="utf-8")
    monkeypatch.setattr(lw, "OUT_PATH", out)
    monkeypatch.setattr(lw, "THETA_PATH", tmp_path / "absent-theta.json")
    monkeypatch.setattr(lw, "market_state_for", lambda now: "CLOSED")
    assert lw.run_once() == 0
    assert json.loads(out.read_text(encoding="utf-8"))["market_state"] == "CLOSED"


# --------------------------------------------------------------------------- #
# 4. fail-open
# --------------------------------------------------------------------------- #
def _raising_broker(lw):
    def boom(*a, **k):
        raise RuntimeError("broker down")
    return lw.Broker(positions=boom, option_mid=boom, entry_fill_utc=boom)


def test_raising_broker_degrades_arm_never_raises():
    lw = _lw()
    arm = {"id": "risky-1", "display_name": "FLEET-FULLSEND-R (8G19)",
           "execution": "fleet_rest", "status": "active",
           "instrument": "SPY_0DTE_OPTION"}
    entry = lw.assemble_arm(arm=arm, creds={"key": "x", "secret": "y", "base_url": "z"},
                            broker=_raising_broker(lw), spy_last=746.0, now_et=NOW,
                            core_lines=[], prev_arm=None, exit_state_override={})
    assert entry["status"].startswith("degraded:")
    assert "positions read failed" in entry["status"]
    assert entry["in_trade"] is False and entry["position"] is None


def test_one_bad_arm_never_sinks_the_snapshot(monkeypatch, tmp_path):
    lw = _lw()
    monkeypatch.setattr(lw, "SIGHT_BEACON_PATH", tmp_path / "absent.json")
    monkeypatch.setattr(lw, "CORE_DECISIONS_PATH", tmp_path / "absent.jsonl")
    monkeypatch.setattr(lw, "THETA_PATH", tmp_path / "absent-theta.json")
    accounts = {"arms": [
        {"id": "safe-2", "display_name": "CORE-SAFE", "execution": "mcp_heartbeat",
         "status": "active", "instrument": "SPY_0DTE_OPTION"},
        {"id": "risky-1", "display_name": "FULLSEND", "execution": "fleet_rest",
         "status": "active", "instrument": "SPY_0DTE_OPTION"},
    ]}
    snap = lw.build_snapshot(now_et=NOW, broker=_raising_broker(lw),
                             creds_by_arm={"safe-2": {"key": "k", "secret": "s",
                                                      "base_url": "b"}},
                             accounts=accounts, prev=None)
    assert set(snap["arms"]) == {"safe-2", "risky-1"}
    assert snap["arms"]["risky-1"]["status"].startswith("degraded:")  # no creds
    assert snap["market_state"] == "RTH"


def test_run_once_exits_zero_and_writes_loud_error_on_build_crash(tmp_path, monkeypatch):
    lw = _lw()
    out = tmp_path / "live-watch.json"
    monkeypatch.setattr(lw, "OUT_PATH", out)
    monkeypatch.setattr(lw, "market_state_for", lambda now: "RTH")
    monkeypatch.setattr(lw, "build_snapshot",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("kaboom")))
    monkeypatch.setattr(lw, "_live_broker", lambda: lw.Broker(
        positions=lambda c: [], option_mid=lambda c, s: None,
        entry_fill_utc=lambda c, s: None))
    assert lw.run_once() == 0, "production tick must ALWAYS exit 0 (fail-open)"
    snap = json.loads(out.read_text(encoding="utf-8"))
    assert any("kaboom" in e for e in snap["errors"]), \
        "a crashed build must leave a LOUD error in the output (C7), not silence"


# --------------------------------------------------------------------------- #
# 5. breaker vocabulary normalization (C9)
# --------------------------------------------------------------------------- #
def test_breaker_safe_and_fleet_vocab():
    lw = _lw()
    raw = {"tripped": True, "tripped_reason": "daily loss -31%",
           "starting_equity_today": 1160.36, "daily_loss_limit_pct": 0.3}
    ks = lw.normalize_breaker(raw, "safe", "automation/state/circuit-breaker.json")
    assert ks == {"present": True, "tripped": True, "reason": "daily loss -31%",
                  "sod_equity": 1160.36, "loss_limit_pct": 0.3,
                  "source": "automation/state/circuit-breaker.json"}


def test_breaker_aggressive_divergent_vocab():
    """RED-proof: route the bold file through the 'safe' mapping and reason/sod_equity
    read None -- exactly the C9 cross-account null trap this normalization exists for."""
    lw = _lw()
    raw = {"tripped": True, "trip_reason": "daily loss -52%",
           "equity_start_of_day": 1197.52, "daily_loss_kill_switch_pct": 0.5}
    ks = lw.normalize_breaker(raw, "aggressive", "aggressive/circuit-breaker.json")
    assert ks["tripped"] is True
    assert ks["reason"] == "daily loss -52%"
    assert ks["sod_equity"] == 1197.52
    assert ks["loss_limit_pct"] == 0.5
    # the trap the mapping prevents:
    wrong = lw.normalize_breaker(raw, "safe", "x")
    assert wrong["reason"] is None and wrong["sod_equity"] is None


def test_breaker_missing_file_reports_absent_not_fake_ok():
    lw = _lw()
    ks = lw.normalize_breaker(None, "safe", "fleet/safe-3/circuit-breaker.json")
    assert ks["present"] is False and ks["tripped"] is None


def test_breaker_routing_per_arm():
    lw = _lw()
    p, f = lw._breaker_for_arm("safe-2", "mcp_heartbeat")
    assert p.name == "circuit-breaker.json" and "aggressive" not in str(p) and f == "safe"
    p, f = lw._breaker_for_arm("bold-2", "mcp_heartbeat")
    assert "aggressive" in str(p) and f == "aggressive"
    p, f = lw._breaker_for_arm("risky-3", "fleet_rest")
    assert "risky-3" in str(p) and f == "safe"


# --------------------------------------------------------------------------- #
# 6. decision routing
# --------------------------------------------------------------------------- #
def test_core_ledger_split_by_account():
    lw = _lw()
    lines = [
        json.dumps({"account": "safe", "verdict": "HOLD", "reason": "old",
                    "ts_et": "2026-08-03T10:00:03"}),
        json.dumps({"account": "bold", "verdict": "ENTER_BULL", "reason": "level_reclaim",
                    "ts_et": "2026-08-03T10:14:03"}),
        json.dumps({"account": "safe", "verdict": "SKIP_ELITE_BULL_LEVEL_RECLAIM",
                    "reason": "blocked by entry gate block_elite_bull",
                    "ts_et": "2026-08-03T10:14:04"}),
        "NOT-JSON-GARBAGE",
    ]
    safe = lw.pick_core_decision(lines, "safe")
    bold = lw.pick_core_decision(lines, "bold")
    assert safe["verdict"] == "SKIP_ELITE_BULL_LEVEL_RECLAIM"
    assert bold["verdict"] == "ENTER_BULL"
    assert lw.pick_core_decision(["garbage"], "safe") is None


def test_fleet_ledger_maps_action_and_risk_code():
    lw = _lw()
    row = {"ts_et": "2026-08-03T10:12:03.329895-04:00", "arm_id": "risky-1",
           "action": "HOLD", "side": "C", "setup_name": "BULLISH_RECLAIM",
           "risk_code": "SKIP_MIN_PREMIUM_FLOOR", "reason": None}
    dec = lw.pick_fleet_decision([json.dumps(row)])
    assert dec["verdict"] == "HOLD"
    assert dec["reason"] == "SKIP_MIN_PREMIUM_FLOOR"  # risk_code fallback when reason null
    assert dec["setup"] == "BULLISH_RECLAIM"


# --------------------------------------------------------------------------- #
# 7. entry-time cache
# --------------------------------------------------------------------------- #
def test_entry_time_cache_prevents_reask_same_symbol():
    lw = _lw()
    calls = {"n": 0}

    def counting_fill(creds, sym):
        calls["n"] += 1
        return "2026-08-03T13:52:00Z"

    arm = {"id": "safe-3", "display_name": "T", "execution": "fleet_rest",
           "status": "active", "instrument": "SPY_0DTE_OPTION"}
    broker = lw.Broker(positions=lambda c: [_pos_raw()],
                       option_mid=lambda c, s: 1.10, entry_fill_utc=counting_fill)
    prev = {"position": {"symbol": "SPY260803C00745000",
                         "entry_time_et": "2026-08-03T09:52:00"}}
    entry = lw.assemble_arm(arm=arm, creds={"key": "k", "secret": "s", "base_url": "b"},
                            broker=broker, spy_last=746.0, now_et=NOW, core_lines=[],
                            prev_arm=prev, exit_state_override={})
    assert calls["n"] == 0, "cached entry time must prevent a broker orders re-ask"
    assert entry["position"]["entry_time_et"] == "2026-08-03T09:52:00"
    # a NEW symbol (no cache hit) -> broker IS asked
    prev2 = {"position": {"symbol": "SPY260803C00999000",
                          "entry_time_et": "2026-08-03T09:00:00"}}
    lw.assemble_arm(arm=arm, creds={"key": "k", "secret": "s", "base_url": "b"},
                    broker=broker, spy_last=746.0, now_et=NOW, core_lines=[],
                    prev_arm=prev2, exit_state_override={})
    assert calls["n"] == 1


# --------------------------------------------------------------------------- #
# 8. theta link-in read-only
# --------------------------------------------------------------------------- #
def test_theta_link_reads_subset_and_never_writes(tmp_path, monkeypatch):
    lw = _lw()
    theta = tmp_path / "theta-clock.json"
    theta.write_text(json.dumps({"ts_et": "2026-08-03T10:14:47", "n_positions": 2,
                                 "n_alerts": 1, "positions": [{"x": 1}],
                                 "accounts_checked": ["safe-2"]}), encoding="utf-8")
    before = theta.stat().st_mtime_ns
    monkeypatch.setattr(lw, "THETA_PATH", theta)
    link = lw.read_theta_link()
    assert link["n_positions"] == 2 and link["ts_et"] == "2026-08-03T10:14:47"
    assert "read-only" in link["source"]
    assert theta.stat().st_mtime_ns == before, "theta-clock.json must NEVER be written"
    monkeypatch.setattr(lw, "THETA_PATH", tmp_path / "absent.json")
    assert lw.read_theta_link() is None


# --------------------------------------------------------------------------- #
# 9. atomic write
# --------------------------------------------------------------------------- #
def test_atomic_write_leaves_valid_json_and_no_tmp(tmp_path):
    lw = _lw()
    out = tmp_path / "live-watch.json"
    lw._atomic_write_json(out, {"a": 1})
    assert json.loads(out.read_text(encoding="utf-8")) == {"a": 1}
    assert list(tmp_path.glob("*.tmp")) == []


# --------------------------------------------------------------------------- #
# 10. window + arm filter + brief
# --------------------------------------------------------------------------- #
def test_market_state_window_edges():
    lw = _lw()
    mon = dt.datetime(2026, 8, 3, 9, 25)
    assert lw.market_state_for(mon) == "RTH"
    assert lw.market_state_for(mon.replace(hour=9, minute=24)) == "CLOSED"
    assert lw.market_state_for(mon.replace(hour=16, minute=5)) == "RTH"
    assert lw.market_state_for(mon.replace(hour=16, minute=6)) == "CLOSED"
    sat = dt.datetime(2026, 8, 1, 12, 0)
    assert lw.market_state_for(sat) == "CLOSED"


def test_active_spy_arms_excludes_retired_and_futures():
    lw = _lw()
    accounts = {"arms": [
        {"id": "safe-2", "status": "active", "instrument": "SPY_0DTE_OPTION"},
        {"id": "safe-1", "status": "retired", "instrument": "SPY_0DTE_OPTION"},
        {"id": "mes-mnq-div-futures", "status": "dormant", "instrument": "MNQ_FUTURES"},
        {"id": "mes-linear-sim", "status": "pending_build", "instrument": "MES_FUTURES"},
    ]}
    assert [a["id"] for a in lw.active_spy_arms(accounts)] == ["safe-2"]
    assert lw.active_spy_arms(None) == []


def test_render_brief_in_trade_and_flat_and_closed():
    lw = _lw()
    pos = lw.build_position_view(pos_raw=_pos_raw(), exit_rec=_mk_exit_rec(), mid=1.10,
                                 mid_source="option_quote_mid", spy_last=746.0,
                                 entry_time_et="2026-08-03T10:00:00", now_et=NOW)
    snap = {"schema_version": 1, "written_at_et": "2026-08-03T10:15:00",
            "market_state": "RTH", "spy": {"last": 746.0},
            "in_trade_count": 1,
            "arms": {
                "safe-2": {"display_name": "CORE-SAFE", "in_trade": True,
                           "position": pos, "last_decision": None,
                           "kill_switch": {"tripped": False}, "status": "ok"},
                "bold-2": {"display_name": "CORE-BOLD", "in_trade": False,
                           "position": None,
                           "last_decision": {"verdict": "HOLD", "reason": "no trigger",
                                             "age_min": 2.0},
                           "kill_switch": {"tripped": True}, "status": "ok"},
            }}
    text = lw.render_brief(snap)
    assert "IN TRADE SPY260803C00745000 x3" in text
    assert "stop 0.5" in text and "TP1 1.3" in text and "HWM 1.2" in text
    assert "FLAT | last: HOLD (no trigger) 2m ago" in text
    assert "KS:TRIPPED" in text  # bold's tripped switch is loud
    closed = lw.render_brief({"market_state": "CLOSED",
                              "written_at_et": "2026-08-01T12:46:02"})
    assert "CLOSED" in closed
    assert lw.render_brief(None).startswith("LIVE WATCH: no snapshot")
