"""Guard: trades_enriched.load_context() reads extra_exec[] PLACED entries (queue
SETUP-TAXONOMY-UNNORMALIZED-ACROSS-PNL-SURFACES, 2026-09-02 -- the "36 blank enriched
rows" half of that item).

ROOT CAUSE: a single core-decisions.jsonl tick can PLACE more than one setup -- the
top-level verdict/exec fields cover only the FIRST; additional placed setups land in
extra_exec[] with their own action="PLACED" + their own broker order id. load_context()
previously read ONLY the top-level exec, so any trade whose ENTIRE core-tick verdict was
HOLD (a different setup didn't pass scoring) but which still had an extra_exec PLACED
entry got zero context -- ctx_matched=False, setup="" in trades-enriched.jsonl.
Confirmed real case (2026-07-02T09:55:03, safe): verdict=HOLD, but
extra_exec[0]={"setup": "vwap_continuation", "action": "PLACED", "exec": {... "broker":
{"id": "ea281aa6-..."}}} -- this fill's order_id exact-matches that id and was
previously unjoinable. Fixed against the REAL 2026-09-02 tape: 36/36 previously-blank
engine-attributed rows now resolve a setup (ctx_match_rate 0.8983 -> 0.9876); the
remaining 5 unmatched rows are all attribution="manual" (no decision row ever existed
for a manually-placed trade -- correctly unattributable, not a join bug)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import trades_enriched as te  # noqa: E402


def test_extra_exec_placed_entry_resolves_when_top_level_verdict_is_hold(tmp_path):
    core = tmp_path / "core-decisions.jsonl"
    core.write_text(
        '{"ts_et": "2026-07-02T09:55:03", "account": "safe", "verdict": "HOLD", '
        '"setup": null, "bull_score": 10, "bear_score": 5, "vix": 16.03, "ribbon": "BULL", '
        '"spread_cents": 45.4, "htf_15m": "BULL", "triggers": [], '
        '"extra_exec": [{"setup": "vwap_continuation", "action": "PLACED", '
        '"exec": {"symbol": "SPY260702C00750000", "quality_tier": "BASE", "stop": 1.52, '
        '"tp": 2.15, "broker": {"id": "ea281aa6-order"}}}]}\n',
        encoding="utf-8")
    fleet_dir = tmp_path / "no-fleet"

    ctx_by_order, ctx_by_key, _ = te.load_context(core_path=core, fleet_dir=fleet_dir)

    assert "ea281aa6-order" in ctx_by_order
    assert ctx_by_order["ea281aa6-order"]["setup"] == "vwap_continuation"
    assert ("2026-07-02", "safe-2", "SPY260702C00750000") in ctx_by_key


def test_extra_exec_entries_that_are_not_placed_are_ignored(tmp_path):
    core = tmp_path / "core-decisions.jsonl"
    core.write_text(
        '{"ts_et": "2026-07-02T09:55:03", "account": "safe", "verdict": "HOLD", '
        '"extra_exec": [{"setup": "vix_regime_dayside", "action": "SKIP_TICK_ENTRY_TAKEN"}]}\n',
        encoding="utf-8")
    ctx_by_order, ctx_by_key, _ = te.load_context(core_path=core, fleet_dir=tmp_path / "no-fleet")
    assert ctx_by_order == {}
    assert ctx_by_key == {}


def test_main_verdict_and_extra_exec_both_resolve_from_the_same_row(tmp_path):
    """A tick that BOTH enters its main verdict AND places an extra_exec setup must
    index both -- the extra_exec loop must not short-circuit the main-verdict path."""
    core = tmp_path / "core-decisions.jsonl"
    core.write_text(
        '{"ts_et": "2026-07-02T09:30:03", "account": "safe", "verdict": "ENTER_BULL", '
        '"setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON", "reason": "tier BASE", '
        '"exec": {"symbol": "SPY260702C00751000", "broker": {"id": "main-order"}}, '
        '"extra_exec": [{"setup": "vwap_continuation", "action": "PLACED", '
        '"exec": {"symbol": "SPY260702C00750000", "broker": {"id": "extra-order"}}}]}\n',
        encoding="utf-8")
    ctx_by_order, _, _ = te.load_context(core_path=core, fleet_dir=tmp_path / "no-fleet")
    assert ctx_by_order["main-order"]["setup"] == "BULLISH_RECLAIM_RIDE_THE_RIBBON"
    assert ctx_by_order["extra-order"]["setup"] == "vwap_continuation"


def test_real_tape_36_previously_blank_engine_rows_now_resolve():
    """End-to-end RED-PROOF against the real repo state (read-only, write=False -- never
    touches analysis/trades-enriched.jsonl on disk)."""
    out = te.rebuild(write=False)
    meta = out["meta"]
    blank_engine = [r for r in out["rows"]
                    if not (r.get("setup") or "").strip() and r.get("attribution") == "engine"]
    blank_manual = [r for r in out["rows"]
                    if not (r.get("setup") or "").strip() and r.get("attribution") == "manual"]
    assert blank_engine == [], f"{len(blank_engine)} engine rows still unattributed: {blank_engine[:2]}"
    # manual trades have no decision row by construction -- correctly still unattributed
    assert len(blank_manual) >= 1
    assert meta["ctx_match_rate"] >= 0.98


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
