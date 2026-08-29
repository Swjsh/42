"""SUPER-tier label guard (TWO-ACCOUNT-CONSOLIDATION-HANDOFF-2026-08-29 s3/s6.3).

Three things are pinned here:

1. **C14 drift guard.** `build_shared_signal._classify_tier` is a deliberate COPY of
   `backtest/tools/elite_bear_level_reject_gate_ab.classify_tier` (copied so the 1-minute
   live producer takes no pandas/numpy backtest import). A copy that can drift silently is
   exactly the C14 anti-pattern, so this asserts behavioural equivalence across the FULL
   power-set of the trigger vocabulary, not a hand-picked sample.

2. **The reason the label exists at all.** The rule must reproduce the tier actually stored
   on the historical ledger, or the "preserved" signal is not the signal that was measured.

3. **The blast-radius invariant.** `quality` must stay "ELITE"/"BASE".
   `fleet_executor._gate_block_for_entry` synthesises confluence via `quality == "ELITE"`;
   writing "SUPER" into `quality` would flip that False and change GATING. The label is
   additive, in `quality_tier`, and read by nothing in the execution path.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import build_shared_signal as bss  # noqa: E402

VOCAB = [
    "confluence", "ribbon_flip", "level_rejection", "level_reclaim",
    "sequence_rejection", "sequence_reclaim", "trendline_rejection",
]


def _canonical(triggers):
    """Inlined canonical rule (orchestrator.py's tier logic, extracted in
    elite_bear_level_reject_gate_ab.classify_tier). Inlined rather than imported so this
    guard does not itself require the pandas-heavy backtest tree to be importable."""
    trig = set(triggers or [])
    has_conf = "confluence" in trig
    has_seq = "sequence_rejection" in trig or "sequence_reclaim" in trig
    has_flip = "ribbon_flip" in trig
    has_level = any(t in ("level_rejection", "level_reclaim") for t in trig)
    has_trendline = "trendline_rejection" in trig
    n = len(trig)
    if (has_conf and has_flip) or n >= 3:
        return "SUPER"
    elif has_conf or has_seq:
        return "ELITE"
    elif has_level:
        return "LEVEL"
    elif has_trendline:
        return "TRENDLINE"
    else:
        return "BASE"


def test_classify_tier_matches_canonical_over_full_power_set():
    """RED-proof: change any branch of _classify_tier and this fails."""
    checked = 0
    for r in range(len(VOCAB) + 1):
        for combo in itertools.combinations(VOCAB, r):
            assert bss._classify_tier(list(combo)) == _canonical(list(combo)), combo
            checked += 1
    assert checked == 2 ** len(VOCAB) == 128


def test_classify_tier_is_none_and_junk_safe():
    for junk in (None, [], ["", "  "], ["not_a_real_trigger"]):
        assert bss._classify_tier(junk) in {
            "SUPER", "ELITE", "LEVEL", "TRENDLINE", "BASE"}
    assert bss._classify_tier(None) == "BASE"
    # 3+ unknown triggers still escalate -- the rule is count-based by design
    assert bss._classify_tier(["a", "b", "c"]) == "SUPER"


def test_classify_tier_reproduces_the_historical_ledger_labels():
    """The preserved label must BE the measured label, or Section 3's p=0.021 is about a
    different quantity than the thing now being logged."""
    ledger = REPO / "analysis" / "trades-enriched.jsonl"
    if not ledger.exists():
        pytest.skip("trades-enriched.jsonl not present")
    rows = []
    with ledger.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("_meta"):
                continue
            if r.get("tier") and r.get("triggers") is not None:
                rows.append(r)
    assert len(rows) >= 80, f"unexpectedly few labelled rows: {len(rows)}"
    bad = [(r["date"], r["arm"], r["triggers"], r["tier"], bss._classify_tier(r["triggers"]))
           for r in rows if bss._classify_tier(r["triggers"]) != r["tier"]]
    assert not bad, f"tier mismatches vs stored ledger: {bad[:5]}"


def test_super_rows_all_carry_confluence_so_fleet_would_call_them_elite():
    """Pins the handoff's own self-correction: SUPER signals are NOT structurally absent
    from the survivors. Every SUPER row carries `confluence`, so the fleet path admits them
    as ELITE. Retiring safe-2/bold-2 removes VISIBILITY of the label, not the population."""
    ledger = REPO / "analysis" / "trades-enriched.jsonl"
    if not ledger.exists():
        pytest.skip("trades-enriched.jsonl not present")
    supers = []
    with ledger.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            if not r.get("_meta") and r.get("tier") == "SUPER":
                supers.append(r)
    assert supers, "no SUPER rows found -- the premise of the change is gone, re-verify"
    assert all("confluence" in (r.get("triggers") or []) for r in supers)


def test_quality_stays_elite_or_base_and_tier_is_additive():
    """THE blast-radius invariant. If `quality` ever carries "SUPER",
    fleet_executor._gate_block_for_entry's `quality == "ELITE"` test silently goes False
    and gating changes. This is the assertion that must never be weakened.

    Both side-block shapes are exercised, because `elite` is derived from the block's
    `confluence` BOOLEAN (which build() sets at line ~747 as `bool(passed and has_conf)`),
    NOT from the presence of "confluence" in triggers_fired. `quality` therefore legitimately
    differs between the two; `quality_tier` must be SUPER in both, and `quality` must be
    neither SUPER nor otherwise changed by this feature in either.
    """
    trigs = ["confluence", "ribbon_flip", "level_reclaim"]
    for confluence_flag, expected_quality in ((True, "ELITE"), (False, "BASE")):
        bear = {
            "passed": True,
            "triggers_fired": trigs,
            "confluence": confluence_flag,
            "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        }
        entries = bss._ribbon_strategy_entries(bear, {"passed": False}, 640.0)
        assert len(entries) == 1
        e = entries[0]
        assert e["quality_tier"] == "SUPER"
        assert e["quality"] != "SUPER"
        assert e["quality"] == expected_quality, (confluence_flag, e["quality"])
        # every key the executor actually reads is still present and unchanged in shape
        for k in ("name", "side", "setup", "triggers", "quality", "spot"):
            assert k in e


def test_production_side_block_shape_yields_elite_for_super_signals():
    """Pins the handoff's self-correction end-to-end on the REAL block shape: build() sets
    `confluence` from the triggers (`_has_confluence`), so a SUPER-tier signal reaches the
    fleet as quality=ELITE and is ADMITTED -- the population does not disappear when the
    arms are retired, only the SUPER label does. That is precisely why it is logged."""
    trigs = ["confluence", "ribbon_flip", "level_reclaim"]
    assert bss._has_confluence(trigs) is True
    bear = {
        "passed": True,
        "triggers_fired": trigs,
        "confluence": bool(True and bss._has_confluence(trigs)),  # build()'s own expression
        "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
    }
    e = bss._ribbon_strategy_entries(bear, {"passed": False}, 640.0)[0]
    assert e["quality"] == "ELITE"        # admitted by the fleet gate
    assert e["quality_tier"] == "SUPER"   # ...but now VISIBLE as SUPER


def test_super_day_warning_is_deduped_and_failsafe(tmp_path, monkeypatch):
    """The sink runs on the 1-minute path: it must append per (date, side, setup), not per
    tick, and must never raise."""
    led = tmp_path / "super-tier-days.jsonl"
    monkeypatch.setattr(bss, "SUPER_DAYS", led)
    bear = {
        "passed": True,
        "triggers_fired": ["confluence", "ribbon_flip", "level_reclaim"],
        "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
    }
    for _ in range(25):  # 25 "ticks" on the same day
        bss._ribbon_strategy_entries(bear, {"passed": False}, 640.0)
    lines = [x for x in led.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(lines) == 1, f"expected 1 deduped row, got {len(lines)}"
    row = json.loads(lines[0])
    assert row["tier"] == "SUPER"
    assert row["kind"] == "day_warning"
    assert "none" in row["effect"]
    assert row["triggers"] == ["confluence", "level_reclaim", "ribbon_flip"]

    # fail-safe: an unwritable sink must not propagate
    monkeypatch.setattr(bss, "SUPER_DAYS", tmp_path / "no" / "such" / "dir" / "x.jsonl")
    bss._ribbon_strategy_entries(bear, {"passed": False}, 640.0)  # must not raise


def test_non_super_writes_nothing(tmp_path, monkeypatch):
    led = tmp_path / "super-tier-days.jsonl"
    monkeypatch.setattr(bss, "SUPER_DAYS", led)
    bear = {"passed": True, "triggers_fired": ["level_rejection"],
            "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON"}
    entries = bss._ribbon_strategy_entries(bear, {"passed": False}, 640.0)
    assert entries[0]["quality_tier"] == "LEVEL"
    assert not led.exists()
