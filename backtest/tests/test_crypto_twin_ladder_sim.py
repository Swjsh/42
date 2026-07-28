"""Tests for setup/scripts/crypto_twin_ladder_sim.py -- the LADDER-VARIANT SIM LANE (15m-
HTF-gate vs ribbon-stack-gate, both lanes fully simulated, never a real order).

Mirrors test_crypto_twin_sim_bear.py's isolation conventions (tmp_path-scoped TwinConfig,
a local fake-quote fixture for the ONE broker call this lane ever makes: get_crypto_
quote_hilo, read-only). Covers: the 15m aggregation/HTF-ribbon primitive, the variant
evaluator's gating (enters on 5m-MIXED + 15m-aligned + level-reaction, refuses when 15m
disagrees), baseline<->live-signal parity, fail-open isolation (a variant-lane crash never
masks the baseline lane or propagates to the caller), the no-broker-order guard, full BULL
and BEAR round trips through the REAL exit_manager core with realized round-trip P&L, and
the "never blended with LIVE" file-separation guarantee.
"""
from __future__ import annotations

import ast
import json
import sys
from dataclasses import replace as _replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", "automation/state/fleet", "backtest", ""):
    sys.path.insert(0, str(REPO / _p) if _p else str(REPO))

import crypto_twin_core as ctc  # noqa: E402
import crypto_twin_ladder_sim as lad  # noqa: E402
import crypto_twin_levels as tl  # noqa: E402
import crypto_twin_signal as sig  # noqa: E402


def _twin_cfg(tmp_path: Path, **overrides) -> ctc.TwinConfig:
    state_dir = tmp_path / "automation" / "state" / "crypto-twin"
    return ctc.TwinConfig(state_dir=state_dir, **overrides)


def _raw_bar(ts: datetime, o: float, h: float, l: float, c: float, v: float = 1.0) -> dict:
    return {"t": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": o, "h": h, "l": l, "c": c, "v": v}


def _flat_bars(now: datetime, price: float = 64000.0, n: int = 80) -> list[dict]:
    """Perfectly flat OHLC series -> the 5m ribbon converges to fast==pivot==slow ==
    MIXED (deterministic, no hand-tuned EMA math needed), and every level built from it
    sits exactly at `price` -- a trivial HOLD reaction on the trigger bar."""
    return [_raw_bar(now - timedelta(minutes=5 * i), price, price, price, price, 1.0)
           for i in range(n, 0, -1)]


def _paths(cfg: ctc.TwinConfig) -> dict:
    return {"journal_path": cfg.state_dir / lad.LADDER_JOURNAL_FILENAME,
           "positions_path": cfg.state_dir / lad.LADDER_POSITIONS_FILENAME}


@pytest.fixture
def fake_quote(monkeypatch):
    """The ONLY broker call this lane ever makes: get_crypto_quote_hilo (read-only)."""
    box = {"quote": None}
    monkeypatch.setattr(lad.broker, "get_crypto_quote_hilo", lambda symbol=None: box["quote"])
    return box


# ============================================================================
# 15m aggregation
# ============================================================================
def test_aggregate_bars_groups_of_three_ohlc_correct():
    now = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    bars5 = []
    for i in range(6):
        t = now + timedelta(minutes=5 * i)
        bars5.append(lad.Bar(open_time=t, open=100 + i, high=105 + i, low=95 + i,
                             close=102 + i, volume=1.0, granularity_seconds=300, source="test"))
    agg = lad.aggregate_bars(bars5, factor=3)
    assert len(agg) == 2
    assert agg[0].open == bars5[0].open
    assert agg[0].close == bars5[2].close
    assert agg[0].high == max(b.high for b in bars5[0:3])
    assert agg[0].low == min(b.low for b in bars5[0:3])
    assert agg[0].granularity_seconds == 900
    assert agg[1].open_time == bars5[3].open_time


def test_aggregate_bars_trims_leftover_from_the_front_not_the_back():
    now = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    bars5 = [lad.Bar(open_time=now + timedelta(minutes=5 * i), open=i, high=i, low=i,
                     close=i, volume=1.0, granularity_seconds=300, source="test")
            for i in range(7)]  # 7 bars -> 2 complete groups of 3, 1 leftover (dropped from FRONT)
    agg = lad.aggregate_bars(bars5, factor=3)
    assert len(agg) == 2
    assert agg[-1].close == bars5[-1].close  # newest bar always lands in a complete group


def test_aggregate_bars_empty_when_fewer_than_factor():
    now = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    bars5 = [lad.Bar(open_time=now, open=1, high=1, low=1, close=1, volume=1.0,
                     granularity_seconds=300, source="test")]
    assert lad.aggregate_bars(bars5, factor=3) == []


def test_compute_htf_15m_stack_none_on_insufficient_history():
    now = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    bars5 = [lad.Bar(open_time=now + timedelta(minutes=5 * i), open=100, high=101, low=99,
                     close=100, volume=1.0, granularity_seconds=300, source="test")
            for i in range(10)]  # far short of RIBBON_SLOW_15M+1 aggregated bars
    assert lad.compute_htf_15m_stack(bars5) is None


def test_compute_htf_15m_stack_bull_on_a_real_uptrend():
    """Integration proof (not monkeypatched): a genuinely trending 5m series aggregates to
    a BULL 15m ribbon -- the mechanism itself works, not just the gating logic around it."""
    now = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    n = 200
    bars5 = []
    price = 60000.0
    for i in range(n):
        price += 15.0  # steady climb
        t = now + timedelta(minutes=5 * i)
        bars5.append(lad.Bar(open_time=t, open=price - 5, high=price + 5, low=price - 5,
                             close=price, volume=1.0, granularity_seconds=300, source="test"))
    assert lad.compute_htf_15m_stack(bars5) == "BULL"


# ============================================================================
# evaluate_variant -- the gating logic
# ============================================================================
def test_variant_enters_on_5m_mixed_plus_15m_aligned_plus_level_reaction(monkeypatch):
    """THE guard: variant enters on ribbon-MIXED + level-reaction + 15m-aligned -- the
    exact shape the baseline (ribbon-stack-gated) signal refuses."""
    now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    raw = _flat_bars(now, price=64000.0, n=80)
    bars = [ctc._to_bar(r, 300) for r in raw]
    levels = tl.build_level_set(bars, now)

    baseline = sig.evaluate(bars, levels)
    assert baseline.verdict == "HOLD"
    assert baseline.ribbon_stack == "MIXED"

    monkeypatch.setattr(lad, "compute_htf_15m_stack", lambda b: "BULL")
    variant = lad.evaluate_variant(bars, levels)
    assert variant.verdict == "ENTER_BULL"
    assert variant.side == "bull"
    assert variant.ribbon_stack == "MIXED"   # 5m ribbon logged, never gated on
    assert variant.htf_15m == "BULL"


def test_variant_does_not_enter_when_15m_disagrees(monkeypatch):
    """15m HTF reads MIXED (neither BULL nor BEAR aligned) -- the variant lane must HOLD
    even though a level-reaction exists on the trigger bar (flat bars put a level, with a
    HOLD reaction, at spot in BOTH directions -- MIXED is the one HTF read neither branch
    of evaluate_variant accepts)."""
    now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    raw = _flat_bars(now, price=64000.0, n=80)
    bars = [ctc._to_bar(r, 300) for r in raw]
    levels = tl.build_level_set(bars, now)

    monkeypatch.setattr(lad, "compute_htf_15m_stack", lambda b: "MIXED")
    variant = lad.evaluate_variant(bars, levels)
    assert variant.verdict == "HOLD"
    assert variant.htf_15m == "MIXED"


def test_variant_holds_on_htf_none_insufficient_warmup(monkeypatch):
    now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    raw = _flat_bars(now, price=64000.0, n=80)
    bars = [ctc._to_bar(r, 300) for r in raw]
    levels = tl.build_level_set(bars, now)

    monkeypatch.setattr(lad, "compute_htf_15m_stack", lambda b: None)
    variant = lad.evaluate_variant(bars, levels)
    assert variant.verdict == "HOLD"
    assert variant.htf_15m is None


def test_variant_bear_side_mirrors_bull_gating(monkeypatch):
    now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    raw = _flat_bars(now, price=64000.0, n=80)
    bars = [ctc._to_bar(r, 300) for r in raw]
    levels = tl.build_level_set(bars, now)

    monkeypatch.setattr(lad, "compute_htf_15m_stack", lambda b: "BEAR")
    variant = lad.evaluate_variant(bars, levels)
    assert variant.verdict == "ENTER_BEAR"
    assert variant.side == "bear"


# ============================================================================
# baseline lane <-> live signal parity
# ============================================================================
def test_baseline_tagging_matches_live_signal_verdict_on_same_tick(tmp_path, fake_quote):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    raw = _flat_bars(now, price=64000.0, n=80)

    result = lad.run_ladder_tick(cfg, now_utc=now, raw_bars=raw, **_paths(cfg))

    bars = [ctc._to_bar(r, 300) for r in raw]
    levels = tl.build_level_set(bars, now)
    expected = sig.evaluate(bars, levels)

    assert result["lanes"]["baseline"]["verdict"] == expected.verdict
    assert result["lanes"]["baseline"]["side"] == expected.side


# ============================================================================
# fail-open isolation
# ============================================================================
def test_variant_lane_crash_does_not_propagate_and_baseline_still_processes(tmp_path, fake_quote, monkeypatch):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    raw = _flat_bars(now, price=64000.0, n=80)

    def _boom(bars, levels):
        raise RuntimeError("synthetic variant-lane crash")
    monkeypatch.setattr(lad, "evaluate_variant", _boom)

    result = lad.run_ladder_tick(cfg, now_utc=now, raw_bars=raw, **_paths(cfg))  # must not raise
    assert result["action"] == "OK"
    assert "TICK_ERROR" not in json.dumps(result)  # the whole tick never degrades
    assert result["lanes"]["variant"]["action"] == "LANE_ERROR"
    assert "synthetic variant-lane crash" in result["lanes"]["variant"]["error"]
    assert result["lanes"]["baseline"]["action"] in ("HOLD", "LADDER_ENTERED")  # unaffected


def test_whole_module_crash_never_raises_out_of_run_ladder_tick(tmp_path, monkeypatch):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)

    def _boom(*a, **k):
        raise RuntimeError("synthetic SEE-stage crash")
    monkeypatch.setattr(lad.ctc, "fetch_closed_bars", _boom)

    result = lad.run_ladder_tick(cfg, now_utc=now, raw_bars=[], **_paths(cfg))  # must not raise
    assert result["action"] == "TICK_ERROR"
    assert "synthetic SEE-stage crash" in result["error"]


def test_bad_bars_holds_without_crashing(tmp_path, fake_quote):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    result = lad.run_ladder_tick(cfg, now_utc=now, raw_bars=[], **_paths(cfg))
    assert result["action"] == "HOLD_BAD_BARS"
    assert result["error"] is None


# ============================================================================
# full round trips through the REAL exit_manager core (both sides)
# ============================================================================
_TIGHT_TP1_TRAIL_SHAPE = {
    "stop_mode": "premium", "premium_stop_pct": -0.02, "tp1_premium_pct": 0.0015,
    "tp1_qty_fraction": 0.667, "profit_lock_mode": "trailing", "trail_pct": 0.0015,
    "profit_lock_arm_pct": 0.0005, "runner_target_pct": 0.20,
}


def test_bull_variant_round_trip_tp1_then_trail_never_touches_live_ledgers(tmp_path, fake_quote):
    cfg = _twin_cfg(tmp_path, exit_shape=_TIGHT_TP1_TRAIL_SHAPE)
    now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg)

    verdict = lad.VariantVerdict("ENTER_BULL", "bull", "LADDER_HTF_LEVEL_RECLAIM",
                                 triggers=["test"], reason="forced test entry",
                                 trigger_level_exact=None, ribbon_stack="MIXED", htf_15m="BULL")
    position = lad._place_ladder_entry(cfg, lane="variant", verdict=verdict, now=now,
                                       price=64000.0, journal_path=paths["journal_path"])
    entry = position["exit_state"]["entry_premium"]
    assert entry == 64000.0
    assert not (cfg.state_dir / "exit-state.json").exists()
    assert not (cfg.state_dir / "journal.jsonl").exists()
    assert not (cfg.state_dir / "decisions.jsonl").exists()

    # tick 2: price up 0.2% -> TP1 fires (tp1_premium_pct=0.0015), runner ratchets to BE
    fake_quote["quote"] = (entry * 1.002, entry * 0.9985)
    now2 = now + timedelta(minutes=5)
    exit_pass2, action2, position = lad._manage_ladder_position(
        cfg, lane="variant", position=position, now=now2, price=entry, bar_open=entry,
        ribbon_stack="MIXED", journal_path=paths["journal_path"])
    assert action2 == "LADDER_MANAGED"
    kinds2 = [a["kind"] for a in exit_pass2[0]["actions"]]
    assert "SELL_PARTIAL" in kinds2
    tp1_leg = [a for a in exit_pass2[0]["actions"] if a["kind"] == "SELL_PARTIAL"][0]
    assert tp1_leg["leg_pct"] > 0  # bull + price up -> profit

    # tick 3: price pulls back through the trailing floor -> SELL_ALL closes the runner
    fake_quote["quote"] = (entry * 0.999, entry * 0.998)
    now3 = now2 + timedelta(minutes=5)
    exit_pass3, action3, position = lad._manage_ladder_position(
        cfg, lane="variant", position=position, now=now3, price=entry, bar_open=entry,
        ribbon_stack="MIXED", journal_path=paths["journal_path"])
    assert action3 == "LADDER_CLOSED"
    assert position is None

    journal_rows = [json.loads(l) for l in
                    paths["journal_path"].read_text(encoding="utf-8").splitlines()]
    closed_rows = [r for r in journal_rows if r["event"] == "LADDER_CLOSED"]
    assert len(closed_rows) == 1
    assert closed_rows[0]["lane"] == "variant"
    assert closed_rows[0]["round_trip_pct"] is not None
    # never blended with LIVE
    assert not (cfg.state_dir / "exit-state.json").exists()
    assert not (cfg.state_dir / "journal.jsonl").exists()
    assert not (cfg.state_dir / "decisions.jsonl").exists()


def test_bear_baseline_round_trip_structure_stop(tmp_path, fake_quote):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg)
    entry_price = 64000.0
    trigger_level = entry_price * 0.9996  # planted just BELOW spot (bear structure)

    verdict = lad.VariantVerdict("ENTER_BEAR", "bear", "LADDER_HTF_LEVEL_REJECT",
                                 triggers=["test"], reason="forced test entry",
                                 trigger_level_exact=trigger_level, ribbon_stack="BEAR", htf_15m="BEAR")
    # exit_shape must resolve stop_mode="structure" (cfg default already does)
    position = lad._place_ladder_entry(cfg, lane="baseline", verdict=verdict, now=now,
                                       price=entry_price, journal_path=paths["journal_path"])
    assert position["exit_state"]["stop_mode"] == "structure"
    assert position["exit_state"]["side"] == "P"

    # tick 2: a closed 5m bar's close is ABOVE the trigger_level (bear structure-stop
    # fires when close > trigger_level) -- last_closed_5m_close is passed as `price` here.
    # price/bar_open are ALSO above entry_price (a genuine adverse move for a bear), so
    # the gap-aware fill lands strictly worse than entry -- a real loss, not a wash.
    fake_quote["quote"] = (entry_price * 1.0001, entry_price * 0.9999)
    now2 = now + timedelta(minutes=5)
    exit_pass2, action2, position = lad._manage_ladder_position(
        cfg, lane="baseline", position=position, now=now2, price=64100.0, bar_open=64080.0,
        ribbon_stack=None, journal_path=paths["journal_path"])
    assert action2 == "LADDER_CLOSED"
    assert position is None
    assert exit_pass2[0]["actions"][0]["stage"] == "structure_stop"

    journal_rows = [json.loads(l) for l in
                    paths["journal_path"].read_text(encoding="utf-8").splitlines()]
    closed = [r for r in journal_rows if r["event"] == "LADDER_CLOSED"][0]
    assert closed["lane"] == "baseline"
    assert closed["round_trip_pct"] is not None
    # bear + spot rose through the stop -> a loss
    assert closed["round_trip_pct"] < 0


def test_max_hold_flatten_closes_and_journals_round_trip(tmp_path, fake_quote):
    cfg = _twin_cfg(tmp_path, max_hold_hours=1.0)
    now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    paths = _paths(cfg)
    verdict = lad.VariantVerdict("ENTER_BULL", "bull", "LADDER_HTF_LEVEL_RECLAIM",
                                 trigger_level_exact=None, ribbon_stack="MIXED", htf_15m="BULL")
    position = lad._place_ladder_entry(cfg, lane="variant", verdict=verdict, now=now,
                                       price=64000.0, journal_path=paths["journal_path"])
    fake_quote["quote"] = (64010.0, 63990.0)
    later = now + timedelta(hours=1, minutes=1)
    exit_pass, action, position = lad._manage_ladder_position(
        cfg, lane="variant", position=position, now=later, price=64010.0, bar_open=64000.0,
        ribbon_stack="MIXED", journal_path=paths["journal_path"])
    assert action == "LADDER_MAX_HOLD_FLATTEN"
    assert position is None
    journal_rows = [json.loads(l) for l in
                    paths["journal_path"].read_text(encoding="utf-8").splitlines()]
    closed = [r for r in journal_rows if r["event"] == "LADDER_CLOSED"][0]
    assert closed["reason"] == "max_hold_flatten"
    assert closed["round_trip_pct"] is not None


# ============================================================================
# summarize() / report()
# ============================================================================
def test_summarize_and_report_read_closed_rows_per_lane(tmp_path):
    journal = tmp_path / "ladder-sim.jsonl"
    rows = [
        {"event": "LADDER_ENTERED", "lane": "variant"},
        {"event": "LADDER_CLOSED", "lane": "variant", "round_trip_pct": 1.5},
        {"event": "LADDER_CLOSED", "lane": "variant", "round_trip_pct": -0.5},
        {"event": "LADDER_CLOSED", "lane": "baseline", "round_trip_pct": 2.0},
    ]
    journal.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    s = lad.summarize(journal)
    assert s["variant"]["n"] == 2
    assert s["variant"]["wins"] == 1
    assert s["baseline"]["n"] == 1
    text = lad.report(journal)
    assert "variant" in text and "baseline" in text


def test_summarize_empty_journal_reports_zero_not_crash(tmp_path):
    journal = tmp_path / "does-not-exist.jsonl"
    s = lad.summarize(journal)
    assert s["variant"]["n"] == 0
    assert s["baseline"]["n"] == 0
    assert lad.report(journal)  # renders without raising


# ============================================================================
# no-broker-order guard (mirrors test_dojo_no_broker.py's AST pattern). AST-scoped to
# actual CALL expressions (not a raw substring/regex scan of the whole file) so the
# module's own docstring -- which spells out these exact names to document what it must
# NEVER call -- can't false-positive the detector. This is what test_dojo_no_broker.py's
# own two-detector split guards against too: a broken detector must not be able to
# silently pass by matching too little (or, here, fail by matching too much).
# ============================================================================
MODULE_PATH = REPO / "setup" / "scripts" / "crypto_twin_ladder_sim.py"
BANNED_CALLS = frozenset({"place_crypto_order", "market_sell_crypto", "close_all_crypto",
                          "place_option_order", "place_stock_order"})


def _called_names(source: str, filename: str = "<test>") -> set[str]:
    """Every function/method name that appears as the callee of an ast.Call in `source` --
    i.e. genuinely INVOKED, never a name merely mentioned in a string/comment/docstring."""
    tree = ast.parse(source, filename=filename)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute):
                names.add(f.attr)
            elif isinstance(f, ast.Name):
                names.add(f.id)
    return names


def test_ladder_sim_source_never_calls_order_placing_broker_functions():
    """STATIC: the variant/baseline SIM lanes must NEVER CALL a real order-placing broker
    function -- get_crypto_quote_hilo (read-only) is the only broker call permitted, same
    contract crypto_twin_scenarios.py's own SIM bear lane documents for itself. AST-based
    (call sites only) so this module's own docstring -- which names these exact functions
    to document that it must never call them -- cannot trip the detector."""
    hits = _called_names(MODULE_PATH.read_text(encoding="utf-8"), str(MODULE_PATH)) & BANNED_CALLS
    assert not hits, f"crypto_twin_ladder_sim.py CALLS order-placing broker function(s): {hits}"


def test_order_call_detector_would_catch_a_real_violation():
    """RED-proof: a synthetic snippet with a realistic order-placing CALL must be flagged,
    and a clean read-only call (get_crypto_quote_hilo, or the same name merely mentioned
    in a string/comment) must NOT be."""
    bad = "res = broker.place_crypto_order(creds, symbol='BTC/USD', side='buy', qty=1)\n"
    assert _called_names(bad) & BANNED_CALLS

    clean = ("hilo = broker.get_crypto_quote_hilo(symbol)\n"
            "# NEVER call broker.place_crypto_order or market_sell_crypto here\n"
            "doc = 'this string mentions place_crypto_order but never calls it'\n")
    assert not (_called_names(clean) & BANNED_CALLS)


def test_ladder_sim_imports_no_order_placing_names_via_ast():
    """A second, independent detector (AST-level, not just substring) -- mirrors test_dojo_
    no_broker.py's two-detector discipline so a broken detector can't silently pass both."""
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"), filename=str(MODULE_PATH))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
    banned = {"place_crypto_order", "market_sell_crypto", "close_all_crypto"}
    assert not (imported_names & banned), f"banned order-placing name(s) imported: {imported_names & banned}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
