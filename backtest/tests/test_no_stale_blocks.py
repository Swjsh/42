"""WS2 Stale-block guard (2026-06-26).

Five direction-block gates that were re-validated on the CURRENT real-fills + managed
exit engine (06-26 audit) and found to be stale (originally ratified on the old
BS-sim / OTM / -8% stop engine whose sign FLIPPED on the current engine):

  1. params.json   midday_trendline_gate        true  -> false
  2. params.json   entry_bar_body_pct_min        0.20  -> 0.0
  3. agg/params.json  require_bearish_fill_bar   true  -> false
  4. agg/params.json  block_conf_lvl_rec_afternoon true -> false
  5. params.json   vix_entry_thresholds.bull_hard_cap 18.0 -> 22.0
     + filters.py  VIX_BULL_HARD_CAP            18.0  -> 22.0  (must stay in sync)

WHY THIS FILE EXISTS (anti-re-fix):
Each of these was already fixed once, then re-reverted or got a fresh stale copy in the
params. This guard is the catch so we never silently regress back to the blocked state
without CI failing.

FAILURE mode this test prevents:
  * Someone edits params.json restoring midday_trendline_gate=true → test fails.
  * filters.py VIX_BULL_HARD_CAP drifts from params bull_hard_cap → drift test fails.
  * agg params restored to stale fill-bar / conf-lvl-afternoon gates → test fails.

Guard is PURE STATIC (no backtest data, no network). Fast enough for pre-commit.

Run:
    cd backtest && python -m pytest tests/test_no_stale_blocks.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO))

import lib.filters as _F  # noqa: E402

_PARAMS_PATH = REPO / "automation" / "state" / "params.json"
_PARAMS_AGG_PATH = REPO / "automation" / "state" / "aggressive" / "params.json"


def _safe() -> dict:
    return json.loads(_PARAMS_PATH.read_text(encoding="utf-8"))


def _agg() -> dict:
    return json.loads(_PARAMS_AGG_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. midday_trendline_gate must be FALSE (Safe params)
# ---------------------------------------------------------------------------

def test_midday_trendline_gate_unblocked():
    """midday_trendline_gate was re-validated on the current real-fills + (-50%) +
    chandelier + managed engine (backtest/safe_midday_trendline_gate_revalidate_current_engine.py).
    Old-engine ratification sign-FLIPPED: 102 removed trades NET +$849 / +$8.33/tr / WR 71%.
    Gate costs $371 IS, $40 OOS; 3/4 sub-windows HURT. Stale bear-block removed.
    Anchor PASS (0 bull trades to regress).
    Param diff: params.json midday_trendline_gate true -> false.
    Memory: project_midday_trendline_gate_revalidated.md"""
    p = _safe()
    val = p.get("midday_trendline_gate")
    assert val is False, (
        f"params.json midday_trendline_gate={val!r} — should be False (unblocked). "
        "Re-validation on current engine showed the gate COSTS +$849 IS. "
        "Production diff: set midday_trendline_gate false."
    )


# ---------------------------------------------------------------------------
# 2. entry_bar_body_pct_min must be 0.0 (Safe params)  [STAGED — Wave 2]
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason=(
        "STAGED (Wave 2): entry_bar_body_pct_min unblock is queued but NOT yet applied. "
        "Direct block delta = -$200 (C15 cascade inflates aggregate to +$1,946); "
        "Wave 2 applies this after one trading day of Wave 1 observation. "
        "Remove xfail when Wave 2 ships."
    ),
    strict=True,
)
def test_entry_bar_body_pct_min_unblocked():
    """entry_bar_body_pct_min (gate #13) was a BEAR/P doji block ratified on the OLD
    BS-sim engine. Real-fills re-validation on current engine: direct block delta =
    -$200 (removes 44 net-winner bear entries, suppresses 5 fat-tail winners up to
    +$1,361). Aggregate +$1,946 is a cascade artifact (C15/L15). Unblock = 0.20 -> 0.0.
    Anchor PASS.
    Memory: project_entry_body_gate_bear_stale.md"""
    p = _safe()
    val = p.get("entry_bar_body_pct_min")
    assert val == 0.0, (
        f"params.json entry_bar_body_pct_min={val!r} — should be 0.0 (unblocked). "
        "Stale BEAR doji-block removes fat-tail winners; production diff: set 0.0."
    )


# ---------------------------------------------------------------------------
# 3. require_bearish_fill_bar must be FALSE (Aggressive params)  [STAGED — Wave 2]
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason=(
        "STAGED (Wave 2): require_bearish_fill_bar unblock not yet applied to agg/params.json. "
        "Gate is a look-ahead (bar N+1) so cannot work in production as designed. "
        "WF sign-flip -5.73 on current engine; OOS n=5 thin. "
        "Wave 2 applies after one trading day. Remove xfail when Wave 2 ships."
    ),
    strict=True,
)
def test_require_bearish_fill_bar_unblocked():
    """require_bearish_fill_bar (gates.py #7, agg/params.json) is a look-ahead BEAR/P
    block mislabeled 'bull'; Bold=true, AUTO-RATIFIED 2026-06-17 on OLD bracket-only
    engine. Current real-fills + ITM-2 + chandelier (arm+5/trail15): removed-set nets
    +$917 IS (33 bear, 13W +$2,759 / 20L -$1,841) = suppresses winners. WF -5.73
    sign-flip; SW 2/4 hurt; helps W1 but hurts W2/W3 (largest recent). OOS +$775
    (n=5). Param diff: require_bearish_fill_bar true -> false.
    Memory: project_fill_bar_gate_reval.md"""
    p = _agg()
    val = p.get("require_bearish_fill_bar")
    assert val is False, (
        f"agg/params.json require_bearish_fill_bar={val!r} — should be False (unblocked). "
        "Gate suppresses winners on current engine; production diff: set false."
    )


# ---------------------------------------------------------------------------
# 4. block_conf_lvl_rec_afternoon must be FALSE (Aggressive params)  [STAGED — Wave 2]
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason=(
        "STAGED (Wave 2): block_conf_lvl_rec_afternoon unblock not yet applied to agg/params.json. "
        "Gate costs +$779 IS, protects $0 OOS (keys on bt not entry_time — leaky). "
        "Marked DEAD in agg/params.json doc (superseded by block_conf_lvl_rej_midday_afternoon). "
        "Wave 2 applies after one trading day. Remove xfail when Wave 2 ships."
    ),
    strict=True,
)
def test_block_conf_lvl_rec_afternoon_unblocked():
    """block_conf_lvl_rec_afternoon (gate #12, Bold, bull/C afternoon conf+rec) was
    ratified on the old engine. Re-validation on current real-fills + managed engine:
    sign-FLIPPED — costs +$779 IS, protects $0 OOS (leaky: keys on bt not entry).
    Anchor-neutral (no bear anchors affected).
    Param diff: block_conf_lvl_rec_afternoon true -> false.
    Memory: project_block_conf_lvl_rec_afternoon_revalidated.md"""
    p = _agg()
    val = p.get("block_conf_lvl_rec_afternoon")
    assert val is False, (
        f"agg/params.json block_conf_lvl_rec_afternoon={val!r} — should be False (unblocked). "
        "Gate costs +$779 IS on current engine; production diff: set false."
    )


# ---------------------------------------------------------------------------
# 5a. vix_entry_thresholds.bull_hard_cap must be 22.0 (Safe params)
# ---------------------------------------------------------------------------

def test_vix_bull_hard_cap_params_unblocked():
    """VIX_BULL_HARD_CAP was lowered from 22 -> 18 (Rank 35, 2026-06-17) on the OLD
    BS-sim / OTM / -8% stop engine. Re-validation on current real-fills + managed exit
    engine: block contributes -$471 IS AND -$471 OOS, suppresses 2 bull WINNERS
    (4/09 +$205, 4/22 +$266 @ VIX 18-22 band). EC invariant -1379, anchor PASS.
    Param diff: params.json vix_entry_thresholds.bull_hard_cap 18.0 -> 22.0.
    Memory: project_vix_bull_hard_cap_revalidated.md"""
    p = _safe()
    thresholds = p.get("vix_entry_thresholds", {})
    cap = thresholds.get("bull_hard_cap")
    assert cap == 22.0, (
        f"params.json vix_entry_thresholds.bull_hard_cap={cap!r} — should be 22.0. "
        "Suppresses 2 bull WINNERS in 18-22 band; production diff: set 22.0."
    )


# ---------------------------------------------------------------------------
# 5b. filters.py VIX_BULL_HARD_CAP must be 22.0 (constant in sync with params)
# ---------------------------------------------------------------------------

def test_vix_bull_hard_cap_filters_unblocked():
    """filters.py VIX_BULL_HARD_CAP is a hardcoded constant that MUST stay in sync with
    params.json vix_entry_thresholds.bull_hard_cap. If they diverge the live engine reads
    the wrong cap while the backtest reads the right one — a silent live/backtest split
    (C14 / dead-knob anti-pattern).
    Production diff: backtest/lib/filters.py line ~805 VIX_BULL_HARD_CAP = 18.0 -> 22.0.
    Memory: project_vix_bull_hard_cap_revalidated.md"""
    cap = _F.VIX_BULL_HARD_CAP
    assert cap == 22.0, (
        f"filters.py VIX_BULL_HARD_CAP={cap!r} — should be 22.0. "
        "Hardcoded constant must match params.json bull_hard_cap; production diff: set 22.0."
    )


# ---------------------------------------------------------------------------
# 5c. DRIFT GUARD: params bull_hard_cap == filters.py VIX_BULL_HARD_CAP (always)
# ---------------------------------------------------------------------------

def test_vix_bull_hard_cap_params_filters_in_sync():
    """The params.json value and the filters.py constant must never drift.
    This is the ongoing drift guard — it fires whenever one side is updated
    without updating the other side.

    The v25 validator (P4) already checks this at gym-run time; this guard
    catches it at the faster pre-commit level and provides a more explicit
    failure message scoped to the WS2 unblock context."""
    p = _safe()
    params_cap = p.get("vix_entry_thresholds", {}).get("bull_hard_cap")
    filters_cap = _F.VIX_BULL_HARD_CAP

    assert params_cap == filters_cap, (
        f"DRIFT: params.json bull_hard_cap={params_cap!r} != "
        f"filters.py VIX_BULL_HARD_CAP={filters_cap!r}. "
        "These two must always be updated together. "
        "Production diff: set BOTH to the same value (22.0 per WS2 unblock)."
    )
