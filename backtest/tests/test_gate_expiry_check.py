"""Guards for backtest/autoresearch/gate_expiry_check.py -- THE GATE-EXPIRY INSTRUMENT
(J directive 2026-07-31: every armed gate/veto needs a re-validation clock, and the
system must SAY SO when evidence goes stale or the recent window stops supporting it).

Pin, in order:
  1. the registry file itself is well-formed (every gate row carries the columns the
     checker + a human both need);
  2. the pure logic helpers (event clustering, stale-bar detection, the RED/YELLOW/GREEN
     costing verdict, evidence-age parsing) behave correctly in isolation, with NO real
     market data or network access -- fast, $0, always runnable;
  3. the no-respam transition logic (compute_newly_red) fires exactly once per NEW red,
     never on a persisting one;
  4. the RED-PROOF: a synthetic costing-money gate flips overall="RED" end-to-end through
     check_gate() (mining swapped for a fake via monkeypatch -- no real OPRA data needed)
     and flag_status_md() writes exactly one new loud line under STATUS.md's "## Known
     broken" marker, then a second call with the SAME gate still RED writes NOTHING new;
  5. fail-open: a mining exception for one gate never raises out of check_gate -- it
     degrades to overall="ERROR", exactly like guard_runner_slow.py's own philosophy
     (one broken producer can never silently kill the others' visibility);
  6. this checker NEVER touches market data for the categories it declares NOT_MEASURED
     (safety_doctrine / fleet_config) -- proven by calling check_gate with spy=ribbon=
     spy_ts=None and confirming no exception.
"""
from __future__ import annotations

import datetime as dt
import json

import pandas as pd
import pytest

from autoresearch import gate_expiry_check as gec

REGISTRY_PATH = gec.REPO.parent / "automation" / "state" / "gate-registry.json"

REQUIRED_GATE_KEYS = {
    "id", "category", "description", "where_defined", "params_key", "skip_action",
    "scope", "accounts_armed", "armed_date", "evidence_artifact", "cohort_validated_on",
    "last_revalidated", "revalidation_interval_days", "provenance_type", "notes",
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. registry schema
# ─────────────────────────────────────────────────────────────────────────────

def test_registry_file_loads_and_has_gates():
    registry = gec.load_registry()
    assert "gates" in registry
    assert len(registry["gates"]) >= 15  # the 15 GATE_ORDER gates alone


def test_registry_every_gate_has_required_columns():
    registry = gec.load_registry()
    for gate in registry["gates"]:
        missing = REQUIRED_GATE_KEYS - set(gate.keys())
        assert not missing, f"{gate.get('id')} missing columns: {missing}"


def test_registry_gate_ids_are_unique():
    registry = gec.load_registry()
    ids = [g["id"] for g in registry["gates"]]
    assert len(ids) == len(set(ids)), "duplicate gate id in registry"


def test_registry_gate_order_gates_all_present():
    """The 15 canonical GATE_ORDER gates (backtest/lib/engine/gates.py) must each have
    a registry row -- an entry inventoried but silently dropped defeats the whole point."""
    from lib.engine.gates import GATE_ORDER
    registry_ids = {g["id"] for g in gec.load_registry()["gates"]}
    for gate_id, params_key, _skip_action in GATE_ORDER:
        assert gate_id in registry_ids, f"GATE_ORDER gate {gate_id!r} missing from registry"
        assert params_key == gate_id, "this registry assumes gate_id == params_key (matches gates.py)"


# ─────────────────────────────────────────────────────────────────────────────
# 2. pure logic helpers
# ─────────────────────────────────────────────────────────────────────────────

def test_cluster_events_folds_close_fires_into_one_event():
    rows = [
        {"ts_et": "2026-07-31T11:00:00", "side": "C"},
        {"ts_et": "2026-07-31T11:03:00", "side": "C"},  # 3 min later -> same cluster
        {"ts_et": "2026-07-31T11:08:00", "side": "C"},  # 5 min after prior -> same cluster (<=15)
    ]
    events = gec.cluster_events(rows, gap_minutes=15)
    assert len(events) == 1
    assert events[0]["ts_et"] == "2026-07-31T11:00:00"


def test_cluster_events_splits_on_large_gap():
    rows = [
        {"ts_et": "2026-07-31T11:00:00"},
        {"ts_et": "2026-07-31T11:30:00"},  # 30 min later -> new event
    ]
    events = gec.cluster_events(rows, gap_minutes=15)
    assert len(events) == 2


def test_cluster_events_empty_input():
    assert gec.cluster_events([], gap_minutes=15) == []


def test_bar_idx_for_ts_finds_same_day_bar_not_stale():
    spy_ts = pd.Series(pd.to_datetime([
        "2026-07-31 09:30:00", "2026-07-31 09:35:00", "2026-07-31 09:40:00",
    ]))
    idx, stale = gec.bar_idx_for_ts(spy_ts, dt.datetime(2026, 7, 31, 9, 37))
    assert idx == 1  # last bar at-or-before 09:37 is 09:35
    assert stale is False


def test_bar_idx_for_ts_flags_prior_session_phantom_bar():
    """The GATE-PROVENANCE-SWEEP-2026-07-10 finding this miner is built to avoid: a decision
    timestamped on day N whose nearest bar is actually from day N-1 must be dropped, not
    silently counted as a live fire."""
    spy_ts = pd.Series(pd.to_datetime([
        "2026-07-30 15:55:00",  # yesterday's last bar
        "2026-08-03 09:30:00",  # next real session (gap over a weekend)
    ]))
    idx, stale = gec.bar_idx_for_ts(spy_ts, dt.datetime(2026, 7, 31, 9, 31))
    assert idx == 0
    assert stale is True


def test_bar_idx_for_ts_before_all_bars_returns_none():
    spy_ts = pd.Series(pd.to_datetime(["2026-07-31 09:30:00"]))
    idx, stale = gec.bar_idx_for_ts(spy_ts, dt.datetime(2026, 7, 30, 9, 0))
    assert idx is None
    assert stale is True


def test_costing_verdict_red_when_positive_and_over_floor():
    verdict, reason = gec.costing_verdict({"n": 12, "exp_per_trade": 50.0}, floor=10)
    assert verdict == "RED"
    assert "COSTING" in reason


def test_costing_verdict_yellow_when_positive_but_under_floor():
    verdict, _ = gec.costing_verdict({"n": 3, "exp_per_trade": 50.0}, floor=10)
    assert verdict == "YELLOW"


def test_costing_verdict_green_when_negative_expectancy():
    verdict, reason = gec.costing_verdict({"n": 20, "exp_per_trade": -30.0}, floor=10)
    assert verdict == "GREEN"
    assert "justified" in reason


def test_costing_verdict_insufficient_when_zero_fires():
    verdict, _ = gec.costing_verdict({"n": 0}, floor=10)
    assert verdict == "INSUFFICIENT_DATA"


def test_evidence_age_days_parses_iso_prefix():
    gate = {"last_revalidated": "2026-07-10 (SS-B revalidation, KEEP)"}
    age = gec.evidence_age_days(gate, today=dt.date(2026, 7, 31))
    assert age == 21


def test_evidence_age_days_none_when_missing():
    assert gec.evidence_age_days({"last_revalidated": None}, today=dt.date(2026, 7, 31)) is None


def test_evidence_age_days_none_when_malformed():
    assert gec.evidence_age_days({"last_revalidated": "not-a-date"}, today=dt.date(2026, 7, 31)) is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. no-respam transition logic
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_newly_red_flags_fresh_red_only():
    results = {
        "gate_a": {"id": "gate_a", "overall": "RED"},
        "gate_b": {"id": "gate_b", "overall": "RED"},
        "gate_c": {"id": "gate_c", "overall": "GREEN"},
    }
    prior = {"gate_a": {"overall": "RED"}}  # gate_a was ALREADY red last run
    new_red = gec.compute_newly_red(results, prior)
    assert [r["id"] for r in new_red] == ["gate_b"]


def test_compute_newly_red_empty_when_no_prior_run():
    results = {"gate_a": {"overall": "GREEN"}, "gate_b": {"overall": "RED"}}
    new_red = gec.compute_newly_red(results, prior_gates={})
    assert len(new_red) == 1


def test_compute_newly_red_recovery_is_not_newly_red():
    results = {"gate_a": {"overall": "GREEN"}}
    prior = {"gate_a": {"overall": "RED"}}
    assert gec.compute_newly_red(results, prior) == []


# ─────────────────────────────────────────────────────────────────────────────
# 4. RED-PROOF -- the injected costing gate, end to end through check_gate + STATUS.md
# ─────────────────────────────────────────────────────────────────────────────

_FAKE_GATE = {
    "id": "_test_injected_costing_gate",
    "category": "core_gate_order",
    "skip_action": "SKIP_FAKE_TEST_GATE",
    "accounts_armed": {"safe": True, "bold": False},
    "last_revalidated": "2026-01-01",
    "revalidation_interval_days": 21,
}


def test_red_proof_injected_costing_gate_flips_overall_red(monkeypatch):
    """Inject a gate whose mining result is a clearly-positive, over-floor refused cohort
    and prove check_gate reports overall == RED -- the exact mechanism J's directive asks
    to be proven, not just asserted."""
    def _fake_costing_pnl(gate, spy, ribbon, spy_ts, recent_start, recent_end, floor):
        return {
            "combined": {"n": 25, "exp_per_trade": 200.0, "total_dollar": 5000.0},
            "verdict": "RED",
            "reason": "refused cohort would have EARNED $200.0/tr, n=25 >= floor 10 -- COSTING money",
        }
    monkeypatch.setattr(gec, "evaluate_gate_pnl", _fake_costing_pnl)

    result = gec.check_gate(
        _FAKE_GATE, spy=None, ribbon=None, spy_ts=None,
        recent_start=dt.date(2026, 7, 1), recent_end=dt.date(2026, 7, 31),
        floor=10, today=dt.date(2026, 7, 31),
    )
    assert result["overall"] == "RED"
    assert result["pnl_check"]["verdict"] == "RED"


def test_red_proof_flags_status_md_once_then_never_respams(tmp_path, monkeypatch):
    status_path = tmp_path / "STATUS.md"
    status_path.write_text("## Known broken\n\n---\n\n## [2026-07-31] some entry\n", encoding="utf-8")
    monkeypatch.setattr(gec, "STATUS_MD", status_path)

    def _fake_costing_pnl(gate, spy, ribbon, spy_ts, recent_start, recent_end, floor):
        return {"combined": {"n": 25, "exp_per_trade": 200.0},
                "verdict": "RED", "reason": "COSTING money (fake)"}
    monkeypatch.setattr(gec, "evaluate_gate_pnl", _fake_costing_pnl)

    today = dt.date(2026, 7, 31)
    r1 = gec.check_gate(_FAKE_GATE, None, None, None, today, today, 10, today)
    results_run1 = {_FAKE_GATE["id"]: r1}

    # Run 1: no prior state -> this RED is NEW -> exactly one line written.
    new_red_1 = gec.compute_newly_red(results_run1, prior_gates={})
    assert len(new_red_1) == 1
    gec.flag_status_md(new_red_1)
    text_after_1 = status_path.read_text(encoding="utf-8")
    assert text_after_1.count("GATE-EXPIRY RED") == 1
    assert "_test_injected_costing_gate" in text_after_1

    # Run 2: prior state now shows this gate as RED -> compute_newly_red must be EMPTY,
    # and even if a caller mistakenly called flag_status_md anyway with an empty list,
    # nothing new should land.
    prior_gates_run2 = {_FAKE_GATE["id"]: {"overall": "RED"}}
    r2 = gec.check_gate(_FAKE_GATE, None, None, None, today, today, 10, today)
    results_run2 = {_FAKE_GATE["id"]: r2}
    new_red_2 = gec.compute_newly_red(results_run2, prior_gates_run2)
    assert new_red_2 == []
    gec.flag_status_md(new_red_2)  # must be a true no-op on an empty list
    text_after_2 = status_path.read_text(encoding="utf-8")
    assert text_after_2.count("GATE-EXPIRY RED") == 1  # STILL exactly one -- no respam


def test_flag_status_md_noop_when_marker_absent(tmp_path, monkeypatch):
    status_path = tmp_path / "STATUS.md"
    status_path.write_text("no marker in this file at all\n", encoding="utf-8")
    monkeypatch.setattr(gec, "STATUS_MD", status_path)
    fake_red = [{"id": "x", "pnl_check": {"reason": "test"}}]
    gec.flag_status_md(fake_red)  # must not raise
    assert status_path.read_text(encoding="utf-8") == "no marker in this file at all\n"


def test_flag_status_md_empty_list_is_noop(tmp_path, monkeypatch):
    status_path = tmp_path / "STATUS.md"
    original = "## Known broken\n\n---\n\nrest of file\n"
    status_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(gec, "STATUS_MD", status_path)
    gec.flag_status_md([])
    assert status_path.read_text(encoding="utf-8") == original


# ─────────────────────────────────────────────────────────────────────────────
# 5. fail-open: one gate's mining failure never sinks the run
# ─────────────────────────────────────────────────────────────────────────────

def test_check_gate_fail_open_on_mining_exception(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("simulated real-OPRA-cache failure")
    monkeypatch.setattr(gec, "evaluate_gate_pnl", _boom)

    today = dt.date(2026, 7, 31)
    result = gec.check_gate(_FAKE_GATE, None, None, None, today, today, 10, today)  # must not raise
    assert result["overall"] == "ERROR"
    assert result["pnl_check"]["verdict"] == "ERROR"
    assert "simulated real-OPRA-cache failure" in result["pnl_check"]["reason"]


# ─────────────────────────────────────────────────────────────────────────────
# 6. NOT_MEASURED categories never touch market data
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("category", ["safety_doctrine", "fleet_config"])
def test_not_measured_categories_never_touch_market_data(category):
    gate = {
        "id": f"_test_{category}",
        "category": category,
        "skip_action": "SOME_ACTION",
        "accounts_armed": {"safe": True},
        "last_revalidated": None,
        "revalidation_interval_days": None,
    }
    today = dt.date(2026, 7, 31)
    # spy=ribbon=spy_ts=None -- if this code path ever touched market data it would raise
    # an AttributeError/TypeError immediately; passing here proves the NOT_MEASURED branch
    # short-circuits before any DataFrame access, matching the "never blocks, cheap to run"
    # design goal.
    result = gec.check_gate(gate, None, None, None, today, today, 10, today)
    assert result["pnl_check"]["verdict"] == "NOT_MEASURED"
    assert result["overall"] in ("GREEN", "STALE_UNVERIFIED")


def test_inert_gate_never_touches_market_data():
    gate = {
        "id": "_test_inert",
        "category": "core_gate_order",
        "skip_action": "SOME_ACTION",
        "accounts_armed": {"safe": False, "bold": False},
        "last_revalidated": None,
        "revalidation_interval_days": None,
    }
    today = dt.date(2026, 7, 31)
    result = gec.check_gate(gate, None, None, None, today, today, 10, today)
    assert result["pnl_check"]["verdict"] == "INERT"


# ─────────────────────────────────────────────────────────────────────────────
# 7. sanity: the checker never blocks/kills -- it only reports (static assertion)
# ─────────────────────────────────────────────────────────────────────────────

def test_module_has_no_order_placement_or_arming_calls():
    """Static guard: this file must never import/call anything that places an order or
    flips a gate's armed state -- it is read-only + advisory by design (J directive)."""
    src = (gec.REPO / "autoresearch" / "gate_expiry_check.py").read_text(encoding="utf-8")
    forbidden = ["place_option_order", "place_stock_order", "risk_gate.check_order(",
                 "params.json\", \"w", "aggressive/params.json\", \"w"]
    for token in forbidden:
        assert token not in src, f"gate_expiry_check.py must never contain {token!r}"
