"""Guard for the DARK-ARM FIX (2026-08-25, REFUSED-CORE-ENTRY-SHOWS-REASON).

CONFIRMED ROOT CAUSE (setup/scripts/fill_funnel.py): on 2026-08-25 core "bold" fired
5x ENTER_BULL that were all correctly refused by heartbeat_core.py's plan-time
min_entry_premium floor (SPY260825C00767000, premium 0.07-0.11 vs floor 0.30) --
`exec.status = "SKIP_MIN_PREMIUM_FLOOR"`. The refusal WAS journaled, but fill_funnel.py
bucketed every SKIP_* exec status into an anonymous "NOT_ATTEMPTED" in the ENTER-events
list and a generic "ENTRY_GATE_SKIP: refused by an entry gate" in the per-account
dominant-cause column -- indistinguishable from a genuinely dark/silent arm.

THE BITE this guard pins: a synthetic core ENTER row carrying exec.status
SKIP_MIN_PREMIUM_FLOOR must render:
  1. its OWN exact status name (not "NOT_ATTEMPTED") in the ENTER-events list, plus
     the discriminating premium-vs-floor numbers the row already carries;
  2. its OWN exact status name (not the generic "ENTRY_GATE_SKIP" bucket) as the
     per-account dominant cause, again with the premium-vs-floor numbers disclosed.

Non-vacuous: a genuinely dark/silent case (an action-only SKIP_LATE_ENTRY row, which
carries no exec dict at all -- a DIFFERENT, already-instrumented failure stage, see
fill_funnel.py's "ENTER AFTER CEILING" gate-caught check) must still read
NOT_ATTEMPTED / ENTRY_GATE_SKIP unchanged -- this fix must not blur that distinction.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import fill_funnel as ff  # noqa: E402

DAY = "2026-08-25"


def _bold_min_premium_floor_row(ts: str, premium: float) -> dict:
    """Mirrors the REAL 2026-08-25 ground truth row shape verbatim (see
    automation/state/core-decisions.jsonl `13:16:05`-`13:20:05` ET, account bold)."""
    return {
        "ts_et": f"{DAY}T{ts}", "account": "bold", "armed": True,
        "core_tick_id": f"{DAY}T{ts}", "verdict": "ENTER_BULL", "side": "C",
        "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)",
        "exec": {"status": "SKIP_MIN_PREMIUM_FLOOR", "symbol": "SPY260825C00767000",
                 "premium": premium, "min_entry_premium": 0.3},
        "action": "SKIP_MIN_PREMIUM_FLOOR",
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def _empty_fleet(tmp_path: Path) -> Path:
    d = tmp_path / "fleet-empty"
    d.mkdir(exist_ok=True)
    return d


# --------------------------------------------------------------------------- 1. events
def test_skip_status_named_in_enter_events_with_numbers(tmp_path):
    core = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core, [_bold_min_premium_floor_row("13:16:05", 0.11)])
    f = ff.compute_funnel(DAY, core_path=core, fleet_dir=_empty_fleet(tmp_path))
    a = f["accounts"]["core:bold"]
    assert a["enter"] == 1
    assert a["attempted"] == 0, "the floor bailed before the broker -- still not an attempt"
    ev = a["enter_events"][0]
    assert ev["status"] == "SKIP_MIN_PREMIUM_FLOOR", (
        f"a SKIP_* exec status must render by name, not collapse -- got {ev['status']!r}")
    assert ev["status"] != "NOT_ATTEMPTED"
    assert ev.get("skip_detail"), "the premium-vs-floor numbers must be attached"
    assert "premium=0.11" in ev["skip_detail"] and "min_entry_premium=0.3" in ev["skip_detail"]

    md = ff.render_markdown(f, repo=tmp_path)
    assert "SKIP_MIN_PREMIUM_FLOOR" in md
    assert "premium=0.11" in md and "min_entry_premium=0.3" in md
    # the rendered ENTER-events line for THIS row must not say NOT_ATTEMPTED
    line = next(l for l in md.splitlines() if "13:16" in l and "core:bold" in l)
    assert "NOT_ATTEMPTED" not in line, line
    assert "SKIP_MIN_PREMIUM_FLOOR" in line, line


# --------------------------------------------------------------- 2. dominant-cause column
def test_dominant_cause_names_the_skip_status_not_the_generic_bucket(tmp_path):
    core = tmp_path / "core-decisions.jsonl"
    rows = [_bold_min_premium_floor_row(f"13:{16+i}:05", p)
            for i, p in enumerate([0.11, 0.11, 0.08, 0.07, 0.11])]
    _write_jsonl(core, rows)
    f = ff.compute_funnel(DAY, core_path=core, fleet_dir=_empty_fleet(tmp_path))
    why = f["accounts"]["core:bold"]["why"]
    assert why["traded"] is False
    assert why["top_cause"] == "SKIP_MIN_PREMIUM_FLOOR", (
        f"dominant cause must be the exact status, not the generic "
        f"{ff._WHY_SKIP!r} bucket -- got {why['top_cause']!r}")
    assert why["top_cause"] != ff._WHY_SKIP
    assert why["cause_counts"]["SKIP_MIN_PREMIUM_FLOOR"] == 5
    assert "SKIP_MIN_PREMIUM_FLOOR" in why["headline"]
    assert "premium=" in why["headline"] and "min_entry_premium=0.3" in why["headline"]

    md = ff.render_markdown(f, repo=tmp_path)
    assert "`SKIP_MIN_PREMIUM_FLOOR`" in md, "the dominant-cause table column must name it"
    assert "`ENTRY_GATE_SKIP`" not in md


# ------------------------------------------------------------- 3. non-vacuous: other skips
def test_skip_quality_lock_reason_string_disclosed(tmp_path):
    """SKIP_QUALITY_LOCK carries its own human 'reason' inside exec -- _skip_detail
    must prefer that over the generic key=value dump."""
    core = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core, [{
        "ts_et": f"{DAY}T10:00:05", "account": "safe", "armed": True,
        "verdict": "ENTER_BEAR", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "reason": "BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates",
        "exec": {"status": "SKIP_QUALITY_LOCK", "quality_rank": 1, "quality_tier": "TRENDLINE",
                 "prior_quality": 4, "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                 "reason": "blocked by quality lock (downgrade or same-quality after winner)"},
        "action": "SKIP_QUALITY_LOCK",
    }])
    f = ff.compute_funnel(DAY, core_path=core, fleet_dir=_empty_fleet(tmp_path))
    why = f["accounts"]["core:safe"]["why"]
    assert why["top_cause"] == "SKIP_QUALITY_LOCK"
    assert "blocked by quality lock" in why["headline"]


# --------------------------------------------------------- 4. non-vacuous: still dark ok
def test_action_only_ceiling_skip_is_unchanged_not_named(tmp_path):
    """THE NON-VACUOUS BITE the other way: an action-only SKIP_LATE_ENTRY row (no
    `exec` dict at all -- a DIFFERENT, already-instrumented failure stage) must NOT
    be swept into this fix -- it still reads NOT_ATTEMPTED / ENTRY_GATE_SKIP exactly
    as before, so this fix doesn't blur a distinction that was already correct."""
    core = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core, [{
        "ts_et": f"{DAY}T15:41:02", "account": "safe", "verdict": "ENTER_BEAR",
        "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "reason": "BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates",
        "action": "SKIP_LATE_ENTRY", "entry_ceiling_et": "15:00",
        # no "exec" key -- the ceiling branch never reaches _execute
    }])
    f = ff.compute_funnel(DAY, core_path=core, fleet_dir=_empty_fleet(tmp_path))
    a = f["accounts"]["core:safe"]
    assert a["enter_events"][0]["status"] == "NOT_ATTEMPTED"
    assert a["enter_events"][0].get("skip_detail") is None
    assert a["why"]["top_cause"] == ff._WHY_SKIP == "ENTRY_GATE_SKIP"


# --------------------------------------------------------------------- 5. additivity
def test_funnel_stages_and_verdict_unchanged_by_this_fix(tmp_path):
    """VARY-AND-ASSERT (C14): this is REPORTING ONLY -- no funnel STAGE or the
    verdict may move because of it."""
    core = tmp_path / "core-decisions.jsonl"
    rows = [_bold_min_premium_floor_row(f"13:{16+i}:05", p)
            for i, p in enumerate([0.11, 0.11, 0.08, 0.07, 0.11])]
    _write_jsonl(core, rows)
    f = ff.compute_funnel(DAY, core_path=core, fleet_dir=_empty_fleet(tmp_path))
    a = f["accounts"]["core:bold"]
    assert (a["enter"], a["attempted"], a["accepted"], a["rule_blocked"]) == (5, 0, 0, 0)
    assert f["verdict"] == "GREEN", "5 ENTER verdicts fired -- correctly refused, not a fault"
    assert f["flags"] == []
