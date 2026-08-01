"""crypto_twin_signal -- the twin's SEE->DECIDE stage (ribbon + level-reaction trigger).

MECHANISM, not edge (per the spec doc's kill criteria: "If twin behavior diverges from
SPY-engine behavior... that's a FINDING, not a tuning opportunity" -- this module is NOT
a candidate SPY strategy and is never scored in any edge ledger). Its only job is to
exercise the SAME SHAPE of pipeline production runs -- ribbon stack + level reaction ->
scored trigger -> ENTER/HOLD verdict -- on a 24/7 instrument, so the downstream
gate -> risk_gate -> order -> exit_manager -> journal chain gets real, continuous reps.

Deliberately NOT routed through backtest.lib.engine.engine_cli: that engine's 15 gates
(filter_9/filter_10 volume multipliers, PDT, VIX regime, RTH entry-time floors/ceilings,
option-premium economics) are SPY-0DTE-options-specific by construction -- forcing a spot
BTC bar_ctx through it would either no-op every gate (meaningless exercise) or require
faking option-premium fields that don't exist for a spot position. Per HARD RAILS, the
reusable pieces here are the primitive detectors themselves (crypto.lib.ribbon,
crypto_twin_levels), not the SPY-specific gate stack built on top of them elsewhere.

Ribbon periods (fast=13, pivot=20, slow=48) are fingerprinted from backtest/lib/
ribbon_config.json -- "same ribbon EMA math" as production, verbatim periods, just
running crypto.lib.ribbon's Bar-based implementation instead of backtest/lib's
pandas-based one (same math, different plumbing -- see crypto_twin_core module docstring
for why crypto.lib is the correct reuse target here, not a heartbeat_core extraction).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.ribbon import RibbonState, compute_ribbon  # noqa: E402
from crypto.lib.levels import Level, LevelEvent  # noqa: E402

import crypto_twin_levels as tl  # noqa: E402

RIBBON_FAST, RIBBON_PIVOT, RIBBON_SLOW = 13, 20, 48  # fingerprinted, backtest/lib/ribbon_config.json
MIN_STACK_BARS = 2  # "most important filter -- do not lower" (prior crypto-heartbeat.md config)


@dataclass(frozen=True, slots=True)
class TwinVerdict:
    verdict: str                 # "ENTER_BULL" | "ENTER_BEAR" | "HOLD"
    side: Optional[str]          # "bull" | "bear" | None
    setup: Optional[str]         # named trigger pattern, or None
    triggers: list[str] = field(default_factory=list)
    reason: str = ""
    trigger_level_exact: Optional[float] = None
    ribbon_stack: str = "MIXED"
    ribbon_spread: float = 0.0
    stack_bars: int = 0


def _stack_duration(ribbons: Sequence[RibbonState], idx: int) -> int:
    """Consecutive bars (counting back from idx) sharing ribbons[idx].status."""
    if idx < 0 or idx >= len(ribbons):
        return 0
    status = ribbons[idx].status
    n = 0
    i = idx
    while i >= 0 and ribbons[i].status == status:
        n += 1
        i -= 1
    return n


def evaluate(bars: Sequence[Bar], levels: tl.TwinLevelSet, *,
            min_stack_bars: int = MIN_STACK_BARS) -> TwinVerdict:
    """ONE tick's SEE->DECIDE verdict. `bars` must already be closed-bars-only (C6 --
    crypto_twin_core enforces this via crypto.lib.bar_reader before calling here); the
    LAST bar in `bars` is the trigger bar (mirrors heartbeat_core's "2nd-to-last bar is
    the trigger" convention MINUS the forward-confirmation bar -- the twin has no RTH
    next-tick guarantee to rely on a held-back confirmation bar the way SPY's 5-min
    cadence does, so it scores the latest CLOSED bar directly).

    Trigger definition (deliberately simple -- mechanism, not a candidate edge):
      BULL: ribbon BULL-stacked >= min_stack_bars AND trigger bar's close reclaims (or
            holds above) a level at/below spot -> ENTER_BULL.
      BEAR: ribbon BEAR-stacked >= min_stack_bars AND trigger bar rejects (or holds
            below) a level at/above spot -> ENTER_BEAR.
      Anything else -> HOLD.
    """
    if len(bars) < max(RIBBON_SLOW, min_stack_bars) + 1:
        return TwinVerdict("HOLD", None, None, reason="insufficient bar history for ribbon warmup")

    ribbons = compute_ribbon(bars, fast_len=RIBBON_FAST, pivot_len=RIBBON_PIVOT, slow_len=RIBBON_SLOW)
    trig_idx = len(bars) - 1
    rib = ribbons[trig_idx]
    trig_bar = bars[trig_idx]
    if rib.status == "MIXED" or rib.fast != rib.fast:  # NaN check (warmup)
        return TwinVerdict("HOLD", None, None, ribbon_stack=rib.status,
                           reason="ribbon MIXED or still warming up")

    stack_n = _stack_duration(ribbons, trig_idx)
    spot = trig_bar.close
    triggers: list[str] = []
    # STARVATION-FIX HOLD-REASON PRECISION (2026-08-01, J drill): track the nearest
    # candidate level even when its reaction doesn't qualify, so the fallback reason
    # below can distinguish "no candidate at all" from "a candidate WAS in range but
    # this bar didn't react at it" -- purely diagnostic text, ZERO change to the
    # ENTER/HOLD verdict itself (every early return above is untouched). Without this,
    # widening the level set (crypto_twin_levels.py) could populate levels_active with
    # real candidates on every tick while the HOLD reason still always read "no level in
    # range" -- silently false once a candidate exists but the bar's own shape doesn't
    # qualify (e.g. reaction is BREAK/NONE, not RECLAIM/REJECT/HOLD).
    nearest_seen: Optional[Level] = None
    nearest_reaction: Optional[LevelEvent] = None

    if rib.status == "BULL" and stack_n >= min_stack_bars:
        lvl = tl.nearest_directional_level(levels.all_levels, spot, side="bull")
        if lvl is not None:
            reaction = tl.classify_reactions(trig_bar, [lvl])[lvl.price]
            nearest_seen, nearest_reaction = lvl, reaction
            if reaction in (LevelEvent.RECLAIM, LevelEvent.HOLD):
                triggers.append(f"bull_ribbon_stack_{stack_n}bars")
                triggers.append(f"level_{reaction.value}_{lvl.label}")
                return TwinVerdict("ENTER_BULL", "bull", "RIBBON_LEVEL_RECLAIM", triggers,
                                   reason=f"BULL stack {stack_n}b + {reaction.value} of {lvl.label} @ {lvl.price}",
                                   trigger_level_exact=lvl.price, ribbon_stack=rib.status,
                                   ribbon_spread=rib.spread, stack_bars=stack_n)
    elif rib.status == "BEAR" and stack_n >= min_stack_bars:
        lvl = tl.nearest_directional_level(levels.all_levels, spot, side="bear")
        if lvl is not None:
            reaction = tl.classify_reactions(trig_bar, [lvl])[lvl.price]
            nearest_seen, nearest_reaction = lvl, reaction
            if reaction in (LevelEvent.REJECT, LevelEvent.HOLD):
                triggers.append(f"bear_ribbon_stack_{stack_n}bars")
                triggers.append(f"level_{reaction.value}_{lvl.label}")
                return TwinVerdict("ENTER_BEAR", "bear", "RIBBON_LEVEL_REJECT", triggers,
                                   reason=f"BEAR stack {stack_n}b + {reaction.value} of {lvl.label} @ {lvl.price}",
                                   trigger_level_exact=lvl.price, ribbon_stack=rib.status,
                                   ribbon_spread=rib.spread, stack_bars=stack_n)

    if nearest_seen is not None:
        reason = (f"nearest level {nearest_seen.label} @ {nearest_seen.price} in range "
                 f"but bar showed {nearest_reaction.value}, not a qualifying reaction")
    else:
        reason = ("no level in range for the current ribbon stack" if rib.status != "MIXED"
                  else "ribbon MIXED")
    return TwinVerdict("HOLD", None, None, reason=reason,
                       ribbon_stack=rib.status, ribbon_spread=rib.spread, stack_bars=stack_n)
