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
  7. SOUNDNESS FIX (self-caught incident, 2026-08-08 evening): evaluate_gate_pnl's forward
     replay uses backtest/lib/exit_manager_walk.walk_exit_manager (via a lazy import of
     backtest/tools/gate_revalidation_ab.py's replay_row/account_config/build_ribbon_lookup),
     NEVER lib.simulator_real.simulate_trade_real -- proven by monkeypatching
     gec.simulate_trade_real to raise if called, spying on the sound replay path instead, and
     confirming the resulting EV record carries "replay_engine"/"replay_soundness" provenance.
  8. mining-layer outputs (load_decision_rows, cluster_events, bar_idx_for_ts,
     _stop_level_for_row -- the layer GATE-REVALIDATION-2026-08-08 certified sound and this
     fix keeps EXACTLY as-is) are pinned against a frozen fixture so a future edit can't
     silently regress them while "fixing" the replay layer.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

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


def test_costing_verdict_red_when_positive_over_floor_and_survives_drop_top3():
    """UPDATED 2026-08-23 (concentration-term fix -- see gate_expiry_check.py's costing_verdict
    docstring): this test used to pass a bare {"n", "exp_per_trade"} dict and expect RED. That
    encoded the exact naive-mean-only bug two independent G-batteries disproved this weekend
    (structure_veto_enabled, require_bearish_fill_bar). RED is now only reachable when the
    cohort's drop_top3 figure is supplied AND positive (survives dropping its top-3 winners) --
    the test now supplies that field explicitly instead of relying on its absence."""
    verdict, reason = gec.costing_verdict(
        {"n": 12, "exp_per_trade": 50.0, "drop_top3": 80.0, "n_dropped_for_drop_top3": 3},
        floor=10,
    )
    assert verdict == "RED"
    assert "COSTING" in reason


def test_costing_verdict_naive_red_when_concentration_data_missing():
    """FAIL-CLOSED (2026-08-23): a bare {"n", "exp_per_trade"} dict -- no drop_top3 field at
    all -- can no longer earn an actionable RED. Unknown concentration is treated as UNPROVEN,
    never as an automatic pass; this is the exact silent-pass shape that produced both false
    alarms (naive mean-only, no robustness check)."""
    verdict, reason = gec.costing_verdict({"n": 12, "exp_per_trade": 50.0}, floor=10)
    assert verdict == "NAIVE_RED_CONCENTRATED"
    assert "battery" in reason.lower()
    assert "UNKNOWN" in reason


def test_costing_verdict_naive_red_when_fails_drop_top3():
    """Mirrors the real 2026-08-23 incident numbers (structure_veto_enabled: n=15, mean
    +$7.43/tr, drop_top3=-$588.00) -- a positive over-floor mean that does NOT survive dropping
    its top-3 winners must downgrade to NAIVE_RED_CONCENTRATED, never a bare RED."""
    verdict, reason = gec.costing_verdict(
        {"n": 15, "exp_per_trade": 7.43, "drop_top3": -588.0, "n_dropped_for_drop_top3": 3},
        floor=10,
    )
    assert verdict == "NAIVE_RED_CONCENTRATED"
    assert "NAIVE-RED" in reason
    assert "battery" in reason.lower()


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


# ─────────────────────────────────────────────────────────────────────────────
# 8. SOUNDNESS FIX (2026-08-08): sound replay engine + provenance stamping
# ─────────────────────────────────────────────────────────────────────────────

class _FakeSoundReplayModule:
    """Stands in for the lazily-imported backtest/tools/gate_revalidation_ab.py -- lets these
    tests prove evaluate_gate_pnl's WIRING (which function it calls, what it does with the
    result) without needing the real OPRA cache / production exit_manager the real module
    would touch. replay_calls records every call so tests can assert the sound path actually
    ran, exactly once per clustered event."""

    def __init__(self, pnl_by_ts: dict[str, float] | None = None):
        self.replay_calls: list[dict] = []
        self._pnl_by_ts = pnl_by_ts or {}

    def account_config(self):
        return {
            "safe": {"qty": 3, "structure_stop_enabled": True, "time_stop_et": dt.time(15, 40)},
            "bold": {"qty": 5, "structure_stop_enabled": True, "time_stop_et": dt.time(15, 40)},
        }

    def build_ribbon_lookup(self, spy):
        return "FAKE_RIBBON_LOOKUP"

    def drop_top_n(self, pnls: list[float], n_drop: int = 3) -> tuple[float, int]:
        """Mirrors backtest/tools/gate_revalidation_ab.py::drop_top_n's real semantics EXACTLY
        (2026-08-23 concentration-term fix): only drops actual winners (pnl > 0), never the
        least-negative losers. evaluate_gate_pnl calls this via `grab.drop_top_n(...)` on the
        real module -- this fake must behave identically or the wiring tests below would pass
        for the wrong reason."""
        if not pnls:
            return 0.0, 0
        winners = sorted([p for p in pnls if p > 0], reverse=True)
        k = min(n_drop, len(winners))
        dropped_sum = sum(winners[:k])
        return round(sum(pnls) - dropped_sum, 2), k

    def replay_row(self, row, *, spy, spy_ts, spy_by_date, ribbon_lookup, cfg):
        self.replay_calls.append({"row": row, "cfg": cfg, "ribbon_lookup": ribbon_lookup})
        ts = row["ts_et"]
        pnl = self._pnl_by_ts.get(ts, 10.0)
        return {"status": "ok", "date": ts[:10], "pnl": pnl, "ts_et": ts}


def _tiny_spy_df():
    return pd.DataFrame({
        "date": [dt.date(2026, 7, 31)],
        "close": [450.0],
        "timestamp_et": pd.to_datetime(["2026-07-31 11:00:00"]),
    })


def _write_core_decisions(path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_evaluate_gate_pnl_uses_sound_replay_never_simulate_trade_real(monkeypatch, tmp_path):
    """THE core soundness proof: evaluate_gate_pnl must route through the sound replay module
    (walk_exit_manager, via the lazy gate_revalidation_ab import) and must NEVER touch
    lib.simulator_real.simulate_trade_real -- monkeypatched here to raise if it's ever called,
    so any regression back to the old unsound path fails loudly, not silently."""
    gec._REPLAY_CTX_CACHE.clear()
    fake_grab = _FakeSoundReplayModule(pnl_by_ts={"2026-07-31T11:00:00": 42.0})
    monkeypatch.setattr(gec, "_sound_replay_module", lambda: fake_grab)

    def _boom(*args, **kwargs):
        raise AssertionError("simulate_trade_real must NEVER be called by evaluate_gate_pnl "
                              "post-2026-08-08 soundness fix")
    monkeypatch.setattr(gec, "simulate_trade_real", _boom)

    core_decisions = tmp_path / "core-decisions.jsonl"
    _write_core_decisions(core_decisions, [
        {"ts_et": "2026-07-31T11:00:00", "side": "C", "account": "safe",
         "verdict": "SKIP_FAKE_TEST_GATE", "armed": True},
    ])
    monkeypatch.setattr(gec, "CORE_DECISIONS", core_decisions)

    gate = {"id": "_test_sound_replay_gate", "skip_action": "SKIP_FAKE_TEST_GATE",
            "accounts_armed": {"safe": True, "bold": False}}
    spy = _tiny_spy_df()

    result = gec.evaluate_gate_pnl(gate, spy, None, pd.Series(dtype="datetime64[ns]"),
                                    dt.date(2026, 7, 1), dt.date(2026, 7, 31), floor=1)

    assert len(fake_grab.replay_calls) == 1, "sound replay must run exactly once for the one clustered event"
    assert fake_grab.replay_calls[0]["cfg"]["qty"] == 3, "must pass the SAFE account's live cfg, not a hardcoded qty"
    assert result["combined"]["n"] == 1
    assert result["combined"]["exp_per_trade"] == 42.0
    # UPDATED 2026-08-23 (concentration-term fix): a cohort of exactly ONE trade can never
    # survive drop-top3 (dropping its only winner leaves $0.00) -- this is the correct,
    # honest outcome, not a bug. Wiring proof: drop_top3 was actually computed (0.0, not
    # missing) and costing_verdict correctly downgraded it instead of emitting a bare RED
    # off a single lucky fill.
    assert result["combined"]["drop_top3"] == 0.0
    assert result["verdict"] == "NAIVE_RED_CONCENTRATED"


def test_evaluate_gate_pnl_stamps_replay_provenance_on_every_ev_record():
    """SCHEMA: every EV-bearing record evaluate_gate_pnl produces (RED/YELLOW/GREEN AND the
    n=0 INSUFFICIENT_DATA case -- it still ran the sound replay and found nothing) carries
    replay_engine="walk_exit_manager" + replay_soundness="sound" so a future reader can never
    mistake a freshly-computed number for the retired simulate_trade_real-backed one."""
    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        gec._REPLAY_CTX_CACHE.clear()
        fake_grab = _FakeSoundReplayModule()
        mp.setattr(gec, "_sound_replay_module", lambda: fake_grab)
        core_decisions_dir = gec.REPO  # any real dir; file itself is monkeypatched below
        mp.setattr(gec, "CORE_DECISIONS", core_decisions_dir / "_does_not_exist_.jsonl")

        gate = {"id": "_test_empty_gate", "skip_action": "SKIP_FAKE_TEST_GATE",
                "accounts_armed": {"safe": True, "bold": False}}
        spy = _tiny_spy_df()
        result = gec.evaluate_gate_pnl(gate, spy, None, pd.Series(dtype="datetime64[ns]"),
                                        dt.date(2026, 7, 1), dt.date(2026, 7, 31), floor=10)

        assert result["combined"]["n"] == 0
        assert result["verdict"] == "INSUFFICIENT_DATA"
        assert result["replay_engine"] == "walk_exit_manager"
        assert result["replay_soundness"] == "sound"


def test_not_measured_and_inert_gates_carry_no_replay_provenance_stamp():
    """A gate that never reaches the replay path (NOT_MEASURED: no skip_action; INERT: not
    armed on either account) must NOT carry replay_engine/replay_soundness -- stamping a path
    that never replayed anything would be a FALSE provenance claim, the exact class of error
    this fix exists to prevent."""
    not_measured = gec.evaluate_gate_pnl(
        {"id": "_test_nm", "skip_action": None, "accounts_armed": {"safe": True}},
        None, None, None, dt.date(2026, 7, 1), dt.date(2026, 7, 31), floor=10)
    assert not_measured["verdict"] == "NOT_MEASURED"
    assert "replay_engine" not in not_measured
    assert "replay_soundness" not in not_measured

    inert = gec.evaluate_gate_pnl(
        {"id": "_test_inert", "skip_action": "SKIP_X", "accounts_armed": {"safe": False, "bold": False}},
        None, None, None, dt.date(2026, 7, 1), dt.date(2026, 7, 31), floor=10)
    assert inert["verdict"] == "INERT"
    assert "replay_engine" not in inert
    assert "replay_soundness" not in inert


def test_core_strategy_category_routes_around_replay_and_carries_no_stamp(monkeypatch):
    """category=="core_strategy" rows (core_strategy_bear/bull) are a SEPARATE, already-sound
    instrument (real broker fills, autoresearch.core_strategy_recency) -- check_gate must
    route them there, never through evaluate_gate_pnl, and their pnl_check must carry no
    replay_engine/replay_soundness stamp (that field means something SPECIFIC -- 'this number
    came from the walk_exit_manager sim replay' -- and would misdescribe a real-fills read)."""
    def _fake_csr(gate, floor):
        return {"verdict": "GREEN", "reason": "fake real-fills read", "core_strategy_verdict": "GREEN"}
    monkeypatch.setattr("autoresearch.core_strategy_recency.evaluate_for_registry", _fake_csr)

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("core_strategy category must never call evaluate_gate_pnl")
    monkeypatch.setattr(gec, "evaluate_gate_pnl", _must_not_be_called)

    gate = {"id": "core_strategy_bear", "category": "core_strategy",
            "skip_action": "n/a", "accounts_armed": {"safe": True, "bold": True}}
    today = dt.date(2026, 8, 8)
    result = gec.check_gate(gate, None, None, None, today, today, 10, today)
    assert result["pnl_check"]["verdict"] == "GREEN"
    assert "replay_engine" not in result["pnl_check"]
    assert "replay_soundness" not in result["pnl_check"]


def test_sound_replay_module_lazy_import_resolves_and_is_cached():
    """The real (non-faked) lazy import must actually succeed -- proves backtest/tools is on
    sys.path and gate_revalidation_ab.py imports cleanly from gate_expiry_check.py's own
    process, catching an import-time regression the mocked tests above can't see. Also proves
    the module-level cache returns the SAME object on a second call (no re-import cost)."""
    gec._SOUND_REPLAY_MODULE = None
    mod1 = gec._sound_replay_module()
    assert hasattr(mod1, "replay_row")
    assert hasattr(mod1, "account_config")
    assert hasattr(mod1, "build_ribbon_lookup")
    mod2 = gec._sound_replay_module()
    assert mod1 is mod2


# ─────────────────────────────────────────────────────────────────────────────
# 9. mining-layer frozen fixture (unchanged by the soundness fix -- pin it explicitly)
# ─────────────────────────────────────────────────────────────────────────────

def test_mining_layer_frozen_fixture_load_cluster_stop_unchanged():
    """Combined fixture pinning load_decision_rows + cluster_events + bar_idx_for_ts +
    _stop_level_for_row's OUTPUT SHAPE together against a frozen small ledger -- the exact
    four functions GATE-REVALIDATION-RESULTS-2026-08-08.md certified sound and this fix's
    mission explicitly said to keep EXACTLY as-is. A future refactor that touches this layer
    while 'improving' the replay engine regresses here first."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "core-decisions.jsonl"
        rows = [
            {"ts_et": "2026-07-06T10:00:00", "account": "safe", "verdict": "SKIP_STRUCTURE_VETO",
             "armed": True, "side": "P", "trigger_level_exact": 448.5},
            {"ts_et": "2026-07-06T10:04:00", "account": "safe", "verdict": "SKIP_STRUCTURE_VETO",
             "armed": True, "side": "P", "trigger_level_exact": 448.5},  # same cluster (4min < 15)
            {"ts_et": "2026-07-06T10:25:00", "account": "safe", "verdict": "SKIP_STRUCTURE_VETO",
             "armed": True, "side": "P", "trigger_level_exact": 448.5},  # new cluster (21min gap)
            {"ts_et": "2026-06-30T09:00:00", "account": "safe", "verdict": "SKIP_STRUCTURE_VETO",
             "armed": True, "side": "P", "trigger_level_exact": 448.5},  # before `since` -> dropped
        ]
        with path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

        loaded = gec.load_decision_rows(path, since=dt.date(2026, 7, 1))
        assert len(loaded) == 3, "the 2026-06-30 row must be dropped by the `since` filter"

        events = gec.cluster_events(loaded, gap_minutes=15)
        assert len(events) == 2, "10:00/10:04 fold into one event; 10:25 (21min gap) is a new one"
        assert events[0]["ts_et"] == "2026-07-06T10:00:00"
        assert events[1]["ts_et"] == "2026-07-06T10:25:00"

        spy_ts = pd.Series(pd.to_datetime([
            "2026-07-06 09:55:00", "2026-07-06 10:00:00", "2026-07-06 10:05:00",
            "2026-07-06 10:20:00", "2026-07-06 10:25:00",
        ]))
        idx0, stale0 = gec.bar_idx_for_ts(spy_ts, dt.datetime(2026, 7, 6, 10, 0))
        assert idx0 == 1 and stale0 is False
        idx1, stale1 = gec.bar_idx_for_ts(spy_ts, dt.datetime(2026, 7, 6, 10, 25))
        assert idx1 == 4 and stale1 is False

        spy_df = pd.DataFrame({"close": [449.0, 449.2, 449.4, 449.6, 449.8]})
        stop = gec._stop_level_for_row(events[0], spy_df, idx0, "P")
        assert stop == 448.5, "trigger_level_exact must win over any _swing_stop fallback"
