"""engine.gates — the ONE entry-gate evaluation point (Phase 2 of the shared library).

Spec: ``markdown/specs/SHARED-DECISION-LIBRARY-MIGRATION.md`` §3 "Phase 2 — Extract Gates
A-I into ``engine/gates.py`` + add the executable parity test".

WHAT THIS LIFTS
---------------
This module is a *faithful, verbatim relocation* — NOT a reimplementation — of the
inline entry-gate blocks that live in ``backtest/lib/orchestrator.py`` in
``run_backtest``'s per-bar loop, lines ~1239-1540 (the contiguous run of
``if <gate> and <condition>: decisions.append({... "action": "SKIP_..."}); continue``
blocks that fire AFTER the winning side / quality tier / trigger flags are
computed). Each gate's predicate, its target SKIP action, and its ``blockers``
label are copied byte-for-byte; the **order is preserved exactly** — the
orchestrator's top-to-bottom sequence *is* the canonical spec, declared here as
``GATE_ORDER``.

The 15 gates lifted (in order), with the exact orchestrator line each came from:

  ===  =====================================  ==========================  =====
  #    params key (predicate)                 SKIP action                 orch.
  ===  =====================================  ==========================  =====
  1    block_level_rejection                  SKIP_LEVEL_REJECTION_GATE   1244
  2    trendline_requires_ribbon_flip         SKIP_TRENDLINE_NO_RIBBON..  1261
  3    block_elite_bull (+vix band)           SKIP_ELITE_BULL_LEVEL_RE..  1281
  4    block_bull_ribbon_flip                 SKIP_BULL_RIBBON_FLIP       1300
  5    block_bull_1100_1200                    SKIP_BULL_1100_1200         1318
  6    block_bull_morning_agg                  SKIP_BULL_MORNING_AGG       1338
  7    require_bearish_fill_bar (look-ahead)  SKIP_BULLISH_FILL_BAR_AT..  1358
  8    min_ribbon_momentum_cents              SKIP_RIBBON_MOMENTUM_GATE   1380
  9    max_ribbon_duration_bars               SKIP_RIBBON_DURATION_GATE   1400
  10   midday_trendline_gate                  SKIP_MIDDAY_TRENDLINE_GATE  1422
  11   block_conf_lvl_rej_midday_afternoon    SKIP_CONF_LVL_REJ_MIDDAY..  1443
  12   block_conf_lvl_rec_afternoon           SKIP_CONF_LVL_REC_AFTERN..  1463
  13   entry_bar_body_pct_min (bear)          SKIP_DOJI_ENTRY_BAR         1491
  14   entry_bar_body_pct_min_bull            SKIP_DOJI_ENTRY_BAR_BULL    1509
  15   vix_bear_hard_cap                      SKIP_VIX_BEAR_HIGH          1527
  ===  =====================================  ==========================  =====

WHAT THIS DELIBERATELY DOES NOT LIFT
------------------------------------
Two ``...; continue`` blocks in the same orchestrator region are NOT pure verdict
gates and stay in ``orchestrator.py`` (they are not part of Phase 2's "gate
evaluation" — they mutate or scan, they don't decide allow/skip from the bar's
own scoring/time/VIX/trigger state):

  * ``SKIP_QUALITY_LOCK`` (orch. ~1211) — depends on MUTABLE per-day state
    (``setup_quality_taken_today`` / ``setup_last_stopped_today`` / the 45-min
    leg-2 gap). It is the escalation lock, not a static gate.
  * ``SKIP_NO_PULLBACK`` (orch. ~1545, V_PULLBACK) — forward-SCANS bars and
    MUTATES ``actual_entry_idx``/``actual_entry_bar``; it changes WHERE you enter,
    not WHETHER the verdict allows it.

ORDER INVARIANT (why one call can replace the 15 inline blocks)
---------------------------------------------------------------
All 15 lifted gates are PURE over the bar's already-computed inputs (scoring
result, winning side/tier/triggers, time, VIX, the ribbon history, and — for the
two look-ahead/lookback gates — read-only slices of the SPY/ribbon frames). None
of them reads or writes ``setup_quality_taken_today``. The orchestrator mutates
that dict at line ~1376 (``setup_quality_taken_today[lock_key] = max(...)``)
*between* gate 7 and gate 8 — but since no lifted gate depends on it, the
mutation's position relative to the gates does not change any verdict. Therefore
``evaluate_gates`` can be called ONCE, right after the winning side/tier/triggers
are derived, and it returns the SAME first-firing SKIP as the inline cascade.

PURITY
------
Like ``risk_gate.check_order`` and ``engine.score``: no file reads, no MCP, no
mutation. ``GateBlock`` is a frozen dataclass; ``evaluate_gates`` reads its inputs
and returns a NEW object (or ``None`` when no gate fires). The two gates that need
historical context receive it as read-only objects on :class:`GateContext`
(``spy_df`` for the look-ahead fill bar; ``ribbon_df`` + the ``ribbon_at`` accessor
for the momentum/duration gates) — they are read, never written.

HOW THE ORCHESTRATOR USES IT (this phase: assert-agree oracle)
--------------------------------------------------------------
Exactly as Phase 1 wired ``engine.score_bar``: the orchestrator still runs its
inline gate cascade, and ALSO calls ``evaluate_gates`` on the same context as an
independent oracle, asserting the engine fires the SAME SKIP action (or none) the
inline blocks did. On by default; opt-out via ``GAMMA_ENGINE_GATES_ASSERT=0``.
This proves the extraction is faithful with ZERO behaviour change before any call
site depends on it. The byte-identical backtest diff is the second proof.

PHASES 3-4 FOLLOW (see the spec):
  * Phase 3 — ``engine/engine_cli.py`` stdin/stdout shim feeds a ``GateContext``
    built from the live heartbeat's chart read; the engine verdict is logged as a
    read-only shadow row alongside the prose action for N>=5 trading days.
  * Phase 4 — cutover: the heartbeat consults the verdict and obeys it; the ~450
    lines of scoring/gate prose collapse to a thin "compute inputs, call, obey"
    stub, and ``GATE_ORDER`` (+ params.json) is codegen'd into the prompt so the
    gate list CAN'T silently drift (kills the manual ``gamma-sync`` ritual).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

import pandas as pd

from ..filters import _bar_geometry
from ..ribbon import RibbonState, ribbon_at

__all__ = [
    "GATE_ORDER",
    "GateBlock",
    "GateContext",
    "evaluate_gates",
]


# --------------------------------------------------------------------------- #
# GATE_ORDER — the single declared source of the gate sequence.
#
# This list replaces both the orchestrator's IMPLICIT top-to-bottom order and the
# live heartbeat's "Apply Gates E-I in order" prose (Phase 4 codegens the prose
# from it). The order here is EXACTLY the orchestrator's inline order; a parity
# test asserts ``evaluate_gates`` fires the first matching gate in this order, and
# the structural ``test_heartbeat_gate_intent_parity`` (Phase 2c) will assert
# every key here is referenced by name in the heartbeat prompts.
#
# Each entry: (gate_id, params_key, skip_action). ``gate_id`` is the stable
# internal name; ``params_key`` is the run_backtest kwarg / params.json knob that
# arms it; ``skip_action`` is the decision-row "action" the gate emits.
# --------------------------------------------------------------------------- #
GATE_ORDER: list[tuple[str, str, str]] = [
    ("block_level_rejection", "block_level_rejection", "SKIP_LEVEL_REJECTION_GATE"),
    ("trendline_requires_ribbon_flip", "trendline_requires_ribbon_flip", "SKIP_TRENDLINE_NO_RIBBON_FLIP"),
    ("block_elite_bull", "block_elite_bull", "SKIP_ELITE_BULL_LEVEL_RECLAIM"),
    ("block_bull_ribbon_flip", "block_bull_ribbon_flip", "SKIP_BULL_RIBBON_FLIP"),
    ("block_bull_1100_1200", "block_bull_1100_1200", "SKIP_BULL_1100_1200"),
    ("block_bull_morning_agg", "block_bull_morning_agg", "SKIP_BULL_MORNING_AGG"),
    ("require_bearish_fill_bar", "require_bearish_fill_bar", "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY"),
    ("min_ribbon_momentum_cents", "min_ribbon_momentum_cents", "SKIP_RIBBON_MOMENTUM_GATE"),
    ("max_ribbon_duration_bars", "max_ribbon_duration_bars", "SKIP_RIBBON_DURATION_GATE"),
    ("midday_trendline_gate", "midday_trendline_gate", "SKIP_MIDDAY_TRENDLINE_GATE"),
    ("block_conf_lvl_rej_midday_afternoon", "block_conf_lvl_rej_midday_afternoon", "SKIP_CONF_LVL_REJ_MIDDAY_AFTERNOON"),
    ("block_conf_lvl_rec_afternoon", "block_conf_lvl_rec_afternoon", "SKIP_CONF_LVL_REC_AFTERNOON"),
    ("entry_bar_body_pct_min", "entry_bar_body_pct_min", "SKIP_DOJI_ENTRY_BAR"),
    ("entry_bar_body_pct_min_bull", "entry_bar_body_pct_min_bull", "SKIP_DOJI_ENTRY_BAR_BULL"),
    ("vix_bear_hard_cap", "vix_bear_hard_cap", "SKIP_VIX_BEAR_HIGH"),
]


@dataclass(frozen=True)
class GateBlock:
    """The FIRST entry gate that fired SKIP for one bar (or None means allow).

    Pure data. Carries everything the orchestrator's inline ``decisions.append``
    row needs so the call site can build a byte-identical skip row:

      * ``gate_id``   — the stable internal gate name (matches ``GATE_ORDER``).
      * ``action``    — the decision-row ``"action"`` (e.g. ``"SKIP_VIX_BEAR_HIGH"``).
      * ``blockers``  — the decision-row ``"blockers"`` list (e.g. ``["VIX_BEAR_HARD_CAP"]``).

    The orchestrator already owns the rest of the row (bar_idx, timestamp, prices,
    ribbon, triggers, level, setup) from its loop locals — this object supplies
    only the two fields that DIFFER per gate.
    """

    gate_id: str
    action: str
    blockers: list = field(default_factory=list)


@dataclass(frozen=True)
class GateContext:
    """The exact inputs the 15 entry gates read for ONE bar.

    A faithful capture of the orchestrator loop locals each lifted gate touches —
    nothing more (LEAN: this is the gates' narrow waist, not the whole BarContext).
    Built once per bar at the orchestrator's gate point; reused by the live shim in
    Phase 3.

    Scoring / routing (already derived upstream by score + the side/tier logic):
        winning_side:     "P" | "C" — the side that won routing (None never reaches gates).
        winning_triggers: the winning side's triggers_fired list.
        quality_tier:     "LEVEL"|"ELITE"|"TRENDLINE"|"SUPER"|... — the tier label.
        has_level:        whether the winning side's level-tied trigger is present
                          (level_rejection for P / level_reclaim for C). Mirrors the
                          orchestrator's ``has_level`` exactly.

    Bar state:
        bar:              the trigger bar (pd.Series; geometry gates read O/H/L/C).
        bar_idx:          integer index into ``spy_df`` (look-ahead fill gate).
        bar_time:         the bar timestamp (pandas Timestamp or datetime); ``.time()``
                          is used by the time-window gates.
        vix_now:          spot VIX at the bar (vix_bear_hard_cap + elite-bull band).
        ribbon_spread_cents: current ribbon spread (momentum gate baseline).
        ribbon_stack:     current ribbon stack string (duration gate walk).

    Historical context (READ-ONLY; only two gates need it):
        spy_df:           full SPY frame — ``require_bearish_fill_bar`` reads bar idx+1.
        ribbon_df:        full ribbon frame — momentum/duration gates walk it via
                          ``ribbon_at``.
    """

    # scoring / routing
    winning_side: str
    winning_triggers: Sequence[str]
    quality_tier: str
    has_level: bool
    # bar state
    bar: Any
    bar_idx: int
    bar_time: Any
    vix_now: float
    ribbon_spread_cents: float
    ribbon_stack: str
    # historical context (read-only)
    spy_df: Any = None
    ribbon_df: Any = None


def evaluate_gates(ctx: GateContext, params: Mapping[str, Any]) -> Optional[GateBlock]:
    """Evaluate the 15 entry gates in :data:`GATE_ORDER`; return the first SKIP.

    Faithful relocation of the orchestrator's inline gate cascade (orch.
    ~1239-1540). Each gate's predicate and SKIP action are copied verbatim; the
    order matches ``GATE_ORDER`` exactly. Returns a frozen :class:`GateBlock` for
    the FIRST gate whose condition fires, or ``None`` when every gate passes
    (allow). Pure: no I/O, no mutation.

    Args:
        ctx: the :class:`GateContext` for this bar (the orchestrator loop locals
            each gate reads).
        params: the armed gate knobs — a mapping keyed by the ``run_backtest``
            gate kwarg names (``block_level_rejection``, ``vix_bear_hard_cap``,
            ``entry_bar_body_pct_min``, the VIX-band bounds, the midday-gate start
            minutes, ...). Reads use ``params.get(key, default)`` with the SAME
            defaults the ``run_backtest`` signature declares, so an unsupplied knob
            behaves exactly as the orchestrator's default-valued kwarg (gate off).

    Returns:
        The first-firing :class:`GateBlock`, or ``None`` if no gate blocks the entry.
    """
    side = ctx.winning_side
    trigs = ctx.winning_triggers
    tier = ctx.quality_tier
    vix_now = ctx.vix_now
    bar = ctx.bar
    # ``bar_time`` may be a pandas Timestamp or a datetime; ``.time()`` works on both.
    bt = ctx.bar_time

    # ── 1. LEVEL_REJECTION_GATE (orch. 1244) ─────────────────────────────────
    # Block all BEAR-side LEVEL-tier level_rejection entries.
    if (
        params.get("block_level_rejection", False)
        and tier == "LEVEL"
        and ctx.has_level
        and side == "P"
    ):
        return GateBlock("block_level_rejection", "SKIP_LEVEL_REJECTION_GATE", ["LEVEL_REJECTION_GATE"])

    # ── 2. TRENDLINE_RIBBON_FLIP_REQUIRED (orch. 1261) ───────────────────────
    # Block TRENDLINE entries lacking ribbon_flip.
    if params.get("trendline_requires_ribbon_flip", False) and tier == "TRENDLINE":
        if "ribbon_flip" not in trigs:
            return GateBlock(
                "trendline_requires_ribbon_flip",
                "SKIP_TRENDLINE_NO_RIBBON_FLIP",
                ["TRENDLINE_RIBBON_FLIP_REQUIRED"],
            )

    # ── 3. BLOCK_ELITE_BULL (orch. 1281) ─────────────────────────────────────
    # Block ELITE entries where level_reclaim is present (BULL confluence),
    # restricted to the configured VIX band.
    if (
        params.get("block_elite_bull", False)
        and tier == "ELITE"
        and "level_reclaim" in trigs
        and params.get("block_elite_bull_vix_low", 0.0)
        <= vix_now
        < params.get("block_elite_bull_vix_high", 999.0)
    ):
        return GateBlock("block_elite_bull", "SKIP_ELITE_BULL_LEVEL_RECLAIM", ["BLOCK_ELITE_BULL"])

    # ── 4. BLOCK_BULL_RIBBON_FLIP (orch. 1300) ───────────────────────────────
    # Block BULLISH_RECLAIM when ribbon_flip fires.
    if params.get("block_bull_ribbon_flip", False) and side == "C" and "ribbon_flip" in trigs:
        return GateBlock("block_bull_ribbon_flip", "SKIP_BULL_RIBBON_FLIP", ["BLOCK_BULL_RIBBON_FLIP"])

    # ── 5. BLOCK_BULL_1100_1200 (orch. 1318) ─────────────────────────────────
    # Block ALL BULL entries in the 11:00-12:00 ET window.
    if (
        params.get("block_bull_1100_1200", False)
        and side == "C"
        and dt.time(11, 0) <= bt.time() < dt.time(12, 0)
    ):
        return GateBlock("block_bull_1100_1200", "SKIP_BULL_1100_1200", ["BLOCK_BULL_1100_1200"])

    # ── 6. BLOCK_BULL_MORNING_AGG (orch. 1338) ───────────────────────────────
    # Block ALL BULL (C) entries 10:00-11:30 ET AND >=14:00 ET. Aggressive only.
    if (
        params.get("block_bull_morning_agg", False)
        and side == "C"
        and (
            dt.time(10, 0) <= bt.time() < dt.time(11, 30)
            or bt.time() >= dt.time(14, 0)
        )
    ):
        return GateBlock("block_bull_morning_agg", "SKIP_BULL_MORNING_AGG", ["BLOCK_BULL_MORNING_AGG"])

    # ── 7. REQUIRE_BEARISH_FILL_BAR (orch. 1358) ─────────────────────────────
    # Look-ahead gate: skip BEAR when the fill bar (idx+1) is bullish/doji.
    # NOTE: look-ahead (idx+1 unknown at signal time); backtest upper-bound only.
    if params.get("require_bearish_fill_bar", False) and side == "P":
        spy_df = ctx.spy_df
        _fill_idx = min(ctx.bar_idx + 1, len(spy_df) - 1)
        _fill_bar = spy_df.iloc[_fill_idx]
        _fill_body = float(_fill_bar["close"]) - float(_fill_bar["open"])
        if _fill_body >= 0:  # bullish or doji fill bar — skip
            return GateBlock(
                "require_bearish_fill_bar",
                "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY",
                ["REQUIRE_BEARISH_FILL_BAR"],
            )

    # ── 8. RIBBON_MOMENTUM_GATE (orch. 1380) ─────────────────────────────────
    # Require ribbon spread widening >= threshold over the last 3 bars.
    _rmom_thresh = params.get("min_ribbon_momentum_cents", None)
    if _rmom_thresh is not None and ctx.bar_idx >= 3:
        _prev_st = ribbon_at(ctx.ribbon_df, ctx.bar_idx - 3)
        if _prev_st is not None:
            _rmom = ctx.ribbon_spread_cents - _prev_st.spread_cents
            if _rmom < _rmom_thresh:
                return GateBlock("min_ribbon_momentum_cents", "SKIP_RIBBON_MOMENTUM_GATE", ["RIBBON_MOMENTUM_GATE"])

    # ── 9. RIBBON_DURATION_GATE (orch. 1400) ─────────────────────────────────
    # Require the ribbon stack age <= max bars (fresh flip > stale trend).
    _rdur_max = params.get("max_ribbon_duration_bars", None)
    if _rdur_max is not None:
        _rdur = 0
        for _j in range(ctx.bar_idx, max(0, ctx.bar_idx - _rdur_max - 2), -1):
            _st2 = ribbon_at(ctx.ribbon_df, _j)
            if _st2 is None or _st2.stack != ctx.ribbon_stack:
                break
            _rdur += 1
        if _rdur > _rdur_max:
            return GateBlock("max_ribbon_duration_bars", "SKIP_RIBBON_DURATION_GATE", ["RIBBON_DURATION_GATE"])

    # ── 10. MIDDAY_TRENDLINE_GATE (orch. 1422) ───────────────────────────────
    # Block 1-trigger trendline_rejection in the midday window (start..14:00 ET).
    if params.get("midday_trendline_gate", False):
        _start_minutes = params.get("midday_trendline_gate_start_minutes", 690)
        _gate_h, _gate_m = divmod(_start_minutes, 60)
        _is_mid = dt.time(_gate_h, _gate_m) <= bt.time() < dt.time(14, 0)
        _is_tl_only = len(trigs) == 1 and "trendline_rejection" in trigs
        if _is_mid and _is_tl_only:
            return GateBlock("midday_trendline_gate", "SKIP_MIDDAY_TRENDLINE_GATE", ["MIDDAY_TRENDLINE_GATE"])

    # ── 11. BLOCK_CONF_LVL_REJ_MIDDAY_AFTERNOON (orch. 1443) ──────────────────
    # Block conf+level_rejection entries from 11:30 ET onward (midday+afternoon).
    if params.get("block_conf_lvl_rej_midday_afternoon", False):
        _is_midday_or_aft = bt.time() >= dt.time(11, 30)
        _is_conf_rej = "confluence" in trigs and "level_rejection" in trigs
        if _is_midday_or_aft and _is_conf_rej:
            return GateBlock(
                "block_conf_lvl_rej_midday_afternoon",
                "SKIP_CONF_LVL_REJ_MIDDAY_AFTERNOON",
                ["BLOCK_CONF_LVL_REJ_MIDDAY_AFTERNOON"],
            )

    # ── 12. BLOCK_CONF_LVL_REC_AFTERNOON (orch. 1463) ─────────────────────────
    # Block conf+level_reclaim entries from 14:00 ET onward.
    if params.get("block_conf_lvl_rec_afternoon", False):
        _is_afternoon = bt.time() >= dt.time(14, 0)
        _is_conf_rec = "confluence" in trigs and "level_reclaim" in trigs
        if _is_afternoon and _is_conf_rec:
            return GateBlock(
                "block_conf_lvl_rec_afternoon",
                "SKIP_CONF_LVL_REC_AFTERNOON",
                ["BLOCK_CONF_LVL_REC_AFTERNOON"],
            )

    # ── 13. ENTRY_BAR_BODY_PCT_MIN (orch. 1491) ──────────────────────────────
    # Block BEAR entries on doji/wick-dominant bars (body_pct < threshold).
    _body_min = params.get("entry_bar_body_pct_min", 0.0)
    if _body_min > 0.0 and side == "P":
        _entry_geo = _bar_geometry(bar)
        if _entry_geo["body_pct"] < _body_min:
            return GateBlock("entry_bar_body_pct_min", "SKIP_DOJI_ENTRY_BAR", ["ENTRY_BAR_BODY_PCT_GATE"])

    # ── 14. ENTRY_BAR_BODY_PCT_MIN_BULL (orch. 1509) ─────────────────────────
    # Same body gate for BULL (C) entries.
    _body_min_bull = params.get("entry_bar_body_pct_min_bull", 0.0)
    if _body_min_bull > 0.0 and side == "C":
        _entry_geo_c = _bar_geometry(bar)
        if _entry_geo_c["body_pct"] < _body_min_bull:
            return GateBlock(
                "entry_bar_body_pct_min_bull",
                "SKIP_DOJI_ENTRY_BAR_BULL",
                ["ENTRY_BAR_BODY_PCT_GATE_BULL"],
            )

    # ── 15. VIX_BEAR_HARD_CAP (orch. 1527) ───────────────────────────────────
    # Block BEAR entries when VIX is at or above the cap.
    _vix_cap = params.get("vix_bear_hard_cap", None)
    if _vix_cap is not None and side == "P" and vix_now >= _vix_cap:
        return GateBlock("vix_bear_hard_cap", "SKIP_VIX_BEAR_HIGH", ["VIX_BEAR_HARD_CAP"])

    # No gate fired — allow.
    return None
