"""Guard: the strike-tier tables' boundaries match RESET-PLAN-2026-08-01.md's assumptions.

WHY (WS12, 2026-08-01): the paper-reset normalization plan
(analysis/deep-research/RESET-PLAN-2026-08-01.md) recommends $2,500 per SPY arm on the
strength of exactly these facts:

  1. every tier table breaks at 0 / 2,000 / 10,000 / 25,000;
  2. `pick_tier` is half-open [min, max) -> equity $2,000.00 EXACTLY lands in the
     [2K,10K) bracket (the plan's "one cent flips the strike class" boundary call-out);
  3. the strike each table resolves at the $2,500 target (SAFE=ATM, BOLD=OTM-2,
     BOLD_CORE=OTM-2, PROBE=ATM);
  4. the ceiling-formula inputs (safe 30%/3ct, bold 50%/5ct -> $2.50 ceiling at $2,500).

If any future tier retune moves a boundary or an offset, this suite RED-fails and the
reset plan (and the targets baked into .claude/skills/alpaca-paper-reset/SKILL.md) must be
re-derived -- loudly, not silently. Pure-python, no network, no live state.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("crypto/lib", "automation/state/fleet"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import strike_selection as ss  # noqa: E402

RESET_PLAN = REPO / "analysis" / "deep-research" / "RESET-PLAN-2026-08-01.md"
TARGET = 2_500.0  # the plan's per-arm reset target
BOUNDARIES = (0.0, 2_000.0, 10_000.0, 25_000.0)


def _table_boundaries(tiers) -> tuple[float, ...]:
    return tuple(t.equity_min for t in tiers)


def _offsets(tiers) -> tuple[int, ...]:
    return tuple(t.strike_offset for t in tiers)


# ---------------------------------------------------------------- boundary sets


def test_safe_table_boundaries_and_offsets():
    assert _table_boundaries(ss.V15_SAFE_TIERS) == BOUNDARIES
    assert _offsets(ss.V15_SAFE_TIERS) == (0, 0, 1, 2)


def test_bold_table_boundaries_and_offsets():
    assert _table_boundaries(ss.V15_BOLD_TIERS) == BOUNDARIES
    assert _offsets(ss.V15_BOLD_TIERS) == (-3, -2, -1, 2)


def test_bold_core_table_boundaries_and_offsets():
    # (0, 0, -1, 2) since ATM-TIER-EXTENSION-2K-10K 2026-08-04 (was (0, -2, -1, 2);
    # prereg analysis/recommendations/atm-tier-extension-2k10k-prereg-2026-08-03.json).
    assert _table_boundaries(ss.V15_BOLD_CORE_TIERS) == BOUNDARIES
    assert _offsets(ss.V15_BOLD_CORE_TIERS) == (0, 0, -1, 2)


def test_probe_table_boundaries_and_offsets():
    import fleet_executor as fx

    assert _table_boundaries(fx.PROBE_STRIKE_TIERS) == BOUNDARIES
    assert _offsets(fx.PROBE_STRIKE_TIERS) == (0, 0, 1, 2)


# ------------------------------------------- the half-open $2,000 boundary semantic


def test_2000_exactly_lands_in_the_upper_bracket():
    """The plan's §4 rests on pick_tier's [min, max) semantics: $2,000.00 -> [2K,10K)."""
    for tiers in (ss.V15_SAFE_TIERS, ss.V15_BOLD_TIERS, ss.V15_BOLD_CORE_TIERS):
        t = ss.pick_tier(2_000.00, tiers)
        assert (t.equity_min, t.equity_max) == (2_000.0, 10_000.0)


def test_one_cent_below_2000_lands_in_the_lower_bracket():
    """$1,999.99 vs $2,000.00: since ATM-TIER-EXTENSION-2K-10K (2026-08-04) the boundary
    no longer flips the strike class on bold_core (ATM both sides of $2K; the class flip
    moved to $10K) -- the V15_BOLD_TIERS witness still flips OTM-3 -> OTM-2 here."""
    below = ss.pick_tier(1_999.99, ss.V15_BOLD_CORE_TIERS)
    at = ss.pick_tier(2_000.00, ss.V15_BOLD_CORE_TIERS)
    assert below.strike_offset == 0 and below.label == "ATM"
    assert at.strike_offset == 0 and at.label == "ATM"   # was -2/OTM-2 pre-2026-08-04
    assert ss.pick_tier(9_999.99, ss.V15_BOLD_CORE_TIERS).strike_offset == 0
    assert ss.pick_tier(10_000.00, ss.V15_BOLD_CORE_TIERS).strike_offset == -1  # the flip now lives at $10K
    assert ss.pick_tier(1_999.99, ss.V15_BOLD_TIERS).strike_offset == -3  # OTM-3
    assert ss.pick_tier(2_000.00, ss.V15_BOLD_TIERS).strike_offset == -2  # OTM-2 (bold table still flips)


# ------------------------------------------------- what the $2,500 target resolves


def test_target_2500_resolves_the_planned_strikes():
    import fleet_executor as fx

    assert ss.pick_tier(TARGET, ss.V15_SAFE_TIERS).label == "ATM"          # safe-2
    assert ss.pick_tier(TARGET, ss.V15_BOLD_TIERS).label == "OTM-2"        # safe-1 (retired)
    assert ss.pick_tier(TARGET, ss.V15_BOLD_CORE_TIERS).label == "ATM"     # bold-2/safe-3/r1/r3 (ATM-TIER-EXTENSION-2K-10K 2026-08-04; was OTM-2)
    assert ss.pick_tier(TARGET, fx.PROBE_STRIKE_TIERS).label == "ATM"      # full-send/ladder


def test_target_and_2000_share_a_tier():
    """$2,500 buys buffer INSIDE the same [2K,10K) bracket $2,000 sits on the edge of."""
    for tiers in (ss.V15_SAFE_TIERS, ss.V15_BOLD_TIERS, ss.V15_BOLD_CORE_TIERS):
        assert ss.pick_tier(TARGET, tiers) is ss.pick_tier(2_000.00, tiers)


# ----------------------------------------------------- ceiling-formula inputs


def test_ceiling_inputs_match_plan():
    """equity x cap / (min_contracts x 100) = $2.50 at the $2,500 target, both profiles."""
    safe = json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
    bold = json.loads(
        (REPO / "automation" / "state" / "aggressive" / "params.json").read_text(encoding="utf-8")
    )
    assert (safe["per_trade_risk_cap_pct"], safe["min_contracts"]) == (0.3, 3)
    assert (bold["per_trade_risk_cap_pct"], bold["min_contracts"]) == (0.5, 5)
    for p in (safe, bold):
        ceiling = TARGET * p["per_trade_risk_cap_pct"] / (p["min_contracts"] * 100)
        assert abs(ceiling - 2.50) < 1e-9


def test_reset_plan_doc_exists_and_names_the_target():
    text = RESET_PLAN.read_text(encoding="utf-8")
    assert "$2,500" in text and "[2K,10K)" in text
