"""Guard for GOAL-EARN-YOUR-KEEP-2026-09-12 item 1 -- the risky-3 challenger's
anchor-class denylist gate (prereg-trigger-anchor-level-class-2026-09-11.md run 15 days
early on a paper challenger).

WHAT THIS PROVES
----------------
(a) risky-3's resolved accounts.json config is risky-1's twin (gate_override/params_patch/
    exit_profile byte-identical) plus exactly ONE new key,
    gate_override.anchor_class_denylist == ["INTRADAY_SWING_"].
(b) fleet_executor._gate_check denies a block whose trigger_anchor_label starts with a
    listed prefix, passes one that doesn't, and passes (fail-open) a None/missing label.
(c) The four untouched arms (risky-1, safe-2, safe-3, bold-2) resolve BYTE-IDENTICAL to
    the committed HEAD version of accounts.json -- this change touches ONLY risky-3.
(d) build_shared_signal.build() emits `trigger_anchor_label` on both the top-level and
    the dual-perception (safe/bold) bear/bull blocks, on the FIX2 strategies[] entries
    (production's live route, EMIT_STRATEGIES=True), with every pre-existing key
    unchanged and the passed-derivation logic untouched.

RAIL-4 CLEAR: test-only. Reads real accounts.json (read-only) and `git show HEAD:...` for
the parity check; imports the real fleet_executor / build_shared_signal modules; mutates
nothing, places no orders.

Run: backtest/.venv/Scripts/python.exe -m pytest \
     backtest/tests/test_challenger_anchor_denylist_2026_09_12.py -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (str(FLEET_DIR), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fleet_executor as fx  # noqa: E402
import build_shared_signal as bss  # noqa: E402

ACCOUNTS_PATH = FLEET_DIR / "accounts.json"
_ACCOUNTS = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
_ARM_MAP = {a["id"]: a for a in _ACCOUNTS["arms"]}

RISKY_1 = _ARM_MAP["risky-1"]
RISKY_3 = _ARM_MAP["risky-3"]

# Config fields a "twin" config must share verbatim (identity fields -- id/display_name/
# account_number/key_ref/status/live/retired_*/revival_blocked_*/twin_doc_* -- are
# deliberately excluded; those are the fields ALLOWED to differ per-arm).
_TWIN_FIELDS = (
    "execution", "fidelity", "broker", "instrument", "config_source",
    "starting_equity", "frozen_at", "exit_profile", "params_patch",
)


# --- (a) twin config + the one new key --------------------------------------------
def test_risky3_resolves_as_risky1_twin_plus_denylist_key():
    for field in _TWIN_FIELDS:
        assert RISKY_3[field] == RISKY_1[field], (
            f"risky-3.{field} diverges from risky-1's twin config: "
            f"{RISKY_3[field]!r} != {RISKY_1[field]!r}"
        )
    # gate_override: identical to risky-1's PLUS exactly the one new key.
    r3_gate = dict(RISKY_3["gate_override"])
    new_key = r3_gate.pop("anchor_class_denylist", None)
    assert r3_gate == RISKY_1["gate_override"], (
        "risky-3.gate_override (minus anchor_class_denylist) must equal risky-1's "
        f"gate_override verbatim: {r3_gate!r} != {RISKY_1['gate_override']!r}"
    )
    assert new_key == ["INTRADAY_SWING_"], (
        f"expected gate_override.anchor_class_denylist == ['INTRADAY_SWING_'], got {new_key!r}"
    )


def test_risky3_has_no_pure_twin_breaking_leftovers():
    for leftover_key in ("probe_arm", "score_ladder_floor"):
        assert leftover_key not in RISKY_3, f"stale key {leftover_key!r} still on risky-3"
        assert leftover_key not in (RISKY_3.get("gate_override") or {}), (
            f"stale gate_override.{leftover_key} still on risky-3"
        )
    # consumes_scoring_peak / gate_params (hard_skip_verdicts override) were the loose
    # cell's identity -- a pure twin of risky-1 (which carries neither) must not have them.
    assert "consumes_scoring_peak" not in RISKY_3
    assert "gate_params" not in RISKY_3


# --- (b) _gate_check denies / passes on the anchor label ---------------------------
def _blk(label):
    return {
        "passed": True,
        "triggers_fired": ["level_reject", "confluence"],
        "confluence": True,
        "trigger_anchor_label": label,
    }


def test_gate_check_denies_intraday_swing_label():
    reason = fx._gate_check(RISKY_3, _blk("INTRADAY_SWING_LOW_2026-09-11"), {})
    assert reason == "anchor_class_denied:INTRADAY_SWING_LOW_2026-09-11"


def test_gate_check_passes_prior_day_high_label():
    reason = fx._gate_check(RISKY_3, _blk("PRIOR_DAY_HIGH_2026-09-11"), {})
    assert reason is None


def test_gate_check_passes_none_label_fail_open():
    reason = fx._gate_check(RISKY_3, _blk(None), {})
    assert reason is None


def test_gate_check_passes_missing_label_key_fail_open():
    blk = _blk("INTRADAY_SWING_LOW_2026-09-11")
    del blk["trigger_anchor_label"]
    reason = fx._gate_check(RISKY_3, blk, {})
    assert reason is None


def test_gate_check_control_arm_never_denied():
    """risky-1 (control) carries no anchor_class_denylist -- an INTRADAY_SWING_ label
    must never be denied for it, even though it shares every other gate key with risky-3."""
    reason = fx._gate_check(RISKY_1, _blk("INTRADAY_SWING_LOW_2026-09-11"), {})
    assert reason is None


# --- (c) the four untouched arms are byte-identical to HEAD ------------------------
@pytest.mark.parametrize("arm_id", ["risky-1", "safe-2", "safe-3", "bold-2"])
def test_untouched_arms_byte_identical_to_head(arm_id):
    head_raw = subprocess.run(
        ["git", "show", "HEAD:automation/state/fleet/accounts.json"],
        cwd=str(REPO), capture_output=True, text=True, check=True,
    ).stdout
    head_accounts = json.loads(head_raw)
    head_arm = next(a for a in head_accounts["arms"] if a["id"] == arm_id)
    working_arm = _ARM_MAP[arm_id]
    assert working_arm == head_arm, (
        f"arm {arm_id!r} changed vs committed HEAD -- only risky-3 may change in this item"
    )


# --- (d) build_shared_signal carries trigger_anchor_label, additively --------------
def test_bold_passed_blocks_from_row_carries_anchor_label():
    row = {
        "action": "ENTER_BULL",
        "bull_score": 6,
        "bear_score": 2,
        "triggers_fired": ["level_reclaim"],
        "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "trigger_level_exact": 764.5,
        "conviction": {"matched_level_label": "INTRADAY_SWING_LOW_2026-09-11", "total": 3},
    }
    blocks = bss._bold_passed_blocks_from_row(row)
    assert blocks["bull"]["trigger_anchor_label"] == "INTRADAY_SWING_LOW_2026-09-11"
    assert blocks["bear"]["trigger_anchor_label"] == "INTRADAY_SWING_LOW_2026-09-11"
    # pre-existing keys/logic untouched
    assert blocks["bull"]["passed"] is True
    assert blocks["bear"]["passed"] is False
    assert blocks["bull"]["setup_name"] == "BULLISH_RECLAIM_RIDE_THE_RIBBON"


def test_bold_passed_blocks_from_row_none_safe_no_conviction():
    row = {
        "action": "HOLD",
        "bull_score": 1,
        "bear_score": 1,
        "triggers_fired": [],
        "conviction": None,
    }
    blocks = bss._bold_passed_blocks_from_row(row)
    assert blocks["bull"]["trigger_anchor_label"] is None
    assert blocks["bear"]["trigger_anchor_label"] is None


def test_ribbon_strategy_entries_carry_anchor_label():
    """FIX2 strategies[] path (production's live route, EMIT_STRATEGIES=True) must carry
    the label too -- fleet_executor._gate_block_for_entry reads entry['trigger_anchor_label'],
    never the raw bear/bull dict, on this path."""
    import datetime as dt
    bear = {"passed": True, "triggers_fired": ["level_reject"], "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
            "confluence": False, "trigger_level_exact": 764.5,
            "trigger_anchor_label": "INTRADAY_SWING_HIGH_2026-09-11"}
    bull = {"passed": False, "triggers_fired": [], "setup_name": None,
            "confluence": False, "trigger_level_exact": None, "trigger_anchor_label": None}
    entries = bss._ribbon_strategy_entries(bear, bull, 764.5, dt.datetime(2026, 9, 11, 13, 26))
    assert len(entries) == 1
    assert entries[0]["trigger_anchor_label"] == "INTRADAY_SWING_HIGH_2026-09-11"


def test_gate_block_for_entry_passes_through_anchor_label():
    # risky-3 (post-twin) requires min_triggers=2 + confluence/sequence -- two triggers
    # incl. one confluence-named trigger clears that gate before the denylist check runs.
    entry = {"triggers": ["level_reject", "multi_day_confluence"], "quality": "ELITE",
             "trigger_anchor_label": "INTRADAY_SWING_LOW_2026-09-11"}
    blk = fx._gate_block_for_entry(entry)
    assert blk["trigger_anchor_label"] == "INTRADAY_SWING_LOW_2026-09-11"
    reason = fx._gate_check(RISKY_3, blk, {})
    assert reason == "anchor_class_denied:INTRADAY_SWING_LOW_2026-09-11"


def test_gate_block_for_entry_none_safe():
    entry = {"triggers": ["level_reject"], "quality": "BASE"}
    blk = fx._gate_block_for_entry(entry)
    assert blk["trigger_anchor_label"] is None


# --- real-row wiring: _map_core_row must carry conviction through, or the whole gate is a
# dead knob (production never reaches _bold_passed_blocks_from_row with a raw core row --
# it always goes through _map_core_row first).
def test_map_core_row_passes_through_conviction():
    raw = {
        "ts_et": "2026-09-11T10:51:04", "verdict": "ENTER_BULL", "action": "ENTER_BULL",
        "spy": 764.6, "bull_score": 6, "bear_score": 1,
        "triggers": ["level_reclaim", "confluence"],
        "conviction": {"matched_level_label": "INTRADAY_SWING_LOW_2026-09-11", "total": 3},
    }
    mapped = bss._map_core_row(raw)
    assert mapped["conviction"] == raw["conviction"]
    blocks = bss._bold_passed_blocks_from_row(mapped)
    assert blocks["bull"]["trigger_anchor_label"] == "INTRADAY_SWING_LOW_2026-09-11"


def test_map_core_row_conviction_absent_is_none_safe():
    raw = {"ts_et": "2026-09-11T09:35:00", "verdict": "HOLD", "action": "HOLD",
           "spy": 760.0, "bull_score": 1, "bear_score": 1, "triggers": []}
    mapped = bss._map_core_row(raw)
    assert mapped["conviction"] is None
    blocks = bss._bold_passed_blocks_from_row(mapped)
    assert blocks["bull"]["trigger_anchor_label"] is None
    assert blocks["bear"]["trigger_anchor_label"] is None
