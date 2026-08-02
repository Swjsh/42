"""frequency_ceiling_cascade_2026_08_03.py -- THE FULL GATE CASCADE, not the gates.

Task (J, overnight into 2026-08-03): the engine takes 0.49 trades/day ($4,808.75 / 191
trades / 391 days). J's $100-200/day target needs ~4 trades/day at the current per-trade
quality. Twelve pre-registered attempts to improve SELECTION nulled this weekend
(analysis/deep-research/WEEKEND-TWELVE-2026-08-01.md) -- frequency, not quality, is the
binding term. This tool answers the one axis nobody has measured: **the JOINT marginal
cost of the full gate stack**, not each gate in isolation (CLAUDE.md lesson C15: "gates
interact multiplicatively -- trace session cascades").

===========================================================================================
WHY THIS IS GENUINELY NEW (not a re-run of REGIME-PARTICIPATION-2026-08-02.md)
===========================================================================================
Two architectural facts, verified by reading the source before writing a line of new code:

  1. `lib.filters.evaluate_bearish_setup` / `evaluate_bullish_setup` already collect the
     FULL per-side filter blocker set (every filter 1/5/6/7/8/9/10/11 is checked
     unconditionally and appended to `blockers` -- no short-circuit). This part of the
     cascade was NEVER the lossy step.
  2. `lib.engine.gates.evaluate_gates` -- the 15 NAMED gates (block_elite_bull,
     require_bearish_fill_bar, min_ribbon_momentum_cents, ...) -- returns
     `Optional[GateBlock]`: **the FIRST-firing gate only**, by explicit design ("Evaluate
     the 15 entry gates in GATE_ORDER; return the first SKIP"). The orchestrator's OWN
     inline cascade (orchestrator.py ~1239-1540) is a sequence of `if <gate>: ...;
     continue` blocks -- a bar that fails gate #3 is NEVER evaluated against gates #4-15.
     **This is the actual lossy step** the task describes: every gate study to date
     (filter_5, filter_8, block_elite_bull, the score ladder) measured its OWN isolated
     effect against a population where an earlier-in-order gate may have ALREADY removed
     the bar from consideration -- nobody has asked "of the bars gate X blocks, how many
     would gate Y ALSO have blocked, and how many would gate X have rescued alone."

  Additionally: every existing full-population replay (`day_report_card.py`,
  `regime_participation_replay.py`, `ladder_fullhist_replay.py`) is **explicit about being
  bear-side only** ("Bear-side candidates only... a bull-side oracle would need a different
  extraction -- out of scope for v1", `day_report_card.py` docstring). `is_ladder_candidate`
  hard-requires `bull_passed is False`. This tool extends candidate generation to BOTH
  sides, namespaced (bear filter_8 and bull filter_8 are different predicates that happen
  to share a number -- conflating them would be a real bug, not a shortcut).

===========================================================================================
METHOD -- zero duplication of gate/filter logic, only new INSTRUMENTATION
===========================================================================================
  Filter layer     `evaluate_bearish_setup`/`evaluate_bullish_setup` called UNCHANGED
                    (monkeypatch-captured, pass-through -- exact precedent:
                    `ladder_fullhist_replay.run_backtest_with_bull_capture`, itself already
                    verified not to disturb the orchestrator's own
                    GAMMA_ENGINE_SCORE_ASSERT/GAMMA_ENGINE_GATES_ASSERT cross-checks). This
                    tool captures the FULL SetupResult/BullishSetupResult (not just
                    `.passed`) for BOTH sides on every bar.
  Gate layer        `evaluate_gates_full()` below calls the REAL, unmodified
                    `lib.engine.gates.evaluate_gates` REPEATEDLY: get the first-firing
                    GateBlock, neutralize THAT gate's param to its documented "off" value,
                    call again, repeat until None. This is a peel-off, not a rewrite --
                    every predicate is still gates.py's own code, evaluated through the
                    same function the orchestrator's assert-agree oracle already trusts.
                    Zero risk of the two cascades drifting apart.
  Quality lock      STATEFUL (depends on what already fired earlier that day on the same
                    setup -- `setup_quality_taken_today` et al, orchestrator.py ~1158-1253).
                    Re-deriving this independently would mean reimplementing ~100 lines of
                    path-dependent state and risking a subtle divergence. Instead: read the
                    REAL verdict off the SAME run's own `r.decisions` log (bar_idx ->
                    `action == "SKIP_QUALITY_LOCK"`), which the actual sequential walk
                    already computed correctly. Reported as its own bucket (a lock, not a
                    veto -- different mechanism class, kept visibly distinct in every table).
  Counterfactual $  Sole-blocker cohorts are walked through the SAME real-OPRA + REAL
                    exit_manager pipeline every trusted study in this repo uses
                    (`lib.exit_manager_walk.walk_exit_manager`, structure-stop enabled,
                    RIBBON_RIDE exit shape, entry+1-at-OPEN convention) -- see
                    `day_report_card.py` / `ladder_fullhist_replay.py`. The bear entry
                    resolver (`ladder_fullhist_replay.resolve_ladder_entry`) is PUT-only;
                    `resolve_entry_any_side()` below is a side-parameterized copy (same
                    entry+1/OPRA/BS-synthetic-disclosure logic, `option_symbol`/
                    `black_scholes(is_call=...)` threaded by side) so calls can be
                    priced identically. Oracle, hindsight, NOT achievable, NOT
                    one-position-at-a-time -- same disclosed convention as every prior
                    oracle-bound table this repo has published.

===========================================================================================
AXIS 2 -- no-trade day vocabulary gap (a/b/c split)
===========================================================================================
(a) genuinely nothing tradeable, (b) a move the engine has a detector for but a gate
blocked, (c) a move with NO existing detector. (b) is exactly this tool's own
GATE_BLOCKED-day bucket (extended to both sides) -- no new mechanism needed. (a) vs (c)
needs a genuinely new oracle: `clean_move_candidates()` scans every ACTIVE level seen that
day (captured off `ctx.levels_active`/`ctx.multi_day_levels` at replay time -- the engine's
OWN level set, not re-derived) for a touch-then-clean-break (tolerance touch + decisive
next-bar break + does not give back >=50% of the run within 60 minutes), generalizing
`MULTIDAY-STRUCTURE-2026-07-31.md`'s hand-run touch-ledger (one level, one week) into a
reusable scan (every level, every no-trade day). The day's best such candidate (hindsight)
is walked through the SAME real exit-manager pipeline; classification is by that $ bound
crossing the FOCUS_DAILY_FLOOR (doctrine constant, `markdown/doctrine/FOCUS-DOCTRINE.md`)
AND whether ANY of the engine's own triggers (real + shadow-logged) fired within 2 bars of
the touch. Per task instruction, "defended shelf touch" is explicitly excluded as a NEW (c)
candidate -- `SHELF-HOLD-RECLAIM-STUDY` (WEEKEND-TWELVE WS5) already measured it NULL
(0/96 cells survive BH-FDR, dose-response INVERTED).

===========================================================================================
DISCLOSURES (same standard every study cited above uses)
===========================================================================================
- DESCRIPTIVE FIRST: this tool does not ship or arm anything. Sole-blocker cohorts that
  look profitable are flagged for a LATER pre-registered A/B, never shipped from this run.
- Window: `lib.orchestrator`'s FULL_START/FULL_END as re-exported by
  `ladder_fullhist_replay` (2025-01-02..2026-07-27), the SAME window + SAME two-file SPY/VIX
  merge as `day_report_card.py`/`ladder_fullhist_replay.py` -- chosen for direct
  anchor-comparability over maximum recency (this is a structural/architecture question,
  not a recency-sensitive edge question).
- The pre-existing $498 discrepancy between `engine-fullhist-replay-2026-07-23.json`
  ($4,808.75/191) and `LADDER-FULLHIST-2026-07-27.json` ($5,306.95/191) is INHERITED,
  UNRESOLVED, and NOT investigated further here (REGIME-PARTICIPATION-2026-08-02.md
  section 6 already chased it and found it non-blocking for count-based findings).
- BH-FDR (q=0.10) applied to every cohort-vs-complement significance claim below -- many
  slices, one correction, per task instruction.
- Real-OPRA fills only; BS-synthetic candidates counted + disclosed, excluded from every
  $ figure (C1: "Real-fills is the only WR authority").

Run: backtest/.venv/Scripts/python.exe backtest/tools/frequency_ceiling_cascade_2026_08_03.py
Outputs: analysis/deep-research/FREQUENCY-CEILING-2026-08-03.md
         analysis/deep-research/FREQUENCY-CEILING-2026-08-03.json
Guards: backtest/tests/test_frequency_ceiling_cascade_2026_08_03.py
"""
from __future__ import annotations

import datetime as dt
import itertools
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                      # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# =========================================================================================
# PURE SECTION -- no I/O, no pandas/data dependency beyond gates.py's own dataclasses.
# Guarded by backtest/tests/test_frequency_ceiling_cascade_2026_08_03.py. Kept import-light
# per day_report_card.py's own convention ("lazy imports so the guard test imports stay
# light/pure") -- heavy imports (pandas, orchestrator, exit_manager_walk, ...) are deferred
# into main() and the counterfactual-pricing helpers below the PURE SECTION marker.
# =========================================================================================

from lib.engine.gates import GATE_ORDER, GateBlock, GateContext, evaluate_gates  # noqa: E402

QUALIFYING_SCORE_FLOOR = 8          # matches day_report_card.py / ladder_fullhist_replay.py
FOCUS_DAILY_FLOOR = 100.0           # markdown/doctrine/FOCUS-DOCTRINE.md
MFE_WINNER_PCT = 0.30               # the same doctrine's "one clean +30% trade" bar

# Bear filter id -> name (backtest/lib/filters.py evaluate_bearish_setup, verified this build)
BEAR_FILTER_NAMES = {
    1: "entry_time_window", 5: "ribbon_not_BEAR_5m", 6: "ribbon_spread_lt_30c",
    7: "volume_divergence", 8: "vix_regime_bear", 9: "breakdown_bar_vol_confirm",
    10: "min_triggers_bear", 11: "bullish_sweep_blocker",
}
# Bull filter id -> name (evaluate_bullish_setup) -- NUMBERS OVERLAP bear's but mean
# DIFFERENT predicates (bull's 8/9 are VIX-low/VIX-hard-cap, not bear's VIX-regime; bull's
# 10 is buyer-pressure, not bear's min_triggers) -- MUST stay namespaced, never merged.
BULL_FILTER_NAMES = {
    1: "entry_time_window", 5: "ribbon_not_BULL_5m", 6: "ribbon_spread_lt_30c",
    7: "volume_divergence_bull", 8: "vix_not_low_or_falling", 9: "vix_hard_cap_bull",
    10: "buyer_pressure_bar", 11: "min_triggers_bull_or_no_level_tied", 12: "bearish_sweep_blocker",
}

# The bear/bull level-tied trigger sets that gate "qualifying candidate" status (score>=8 +
# >=1 of these present + a numeric level). Bear set is production's own
# (automation/state/fleet/build_shared_signal.LADDER_LEVEL_TIED, re-declared here to keep
# this module's guard tests free of the fleet dir's own import chain -- identical value,
# cross-checked against the import in main()). Bull set is filters.py's own inline
# `level_tied = {"level_reclaim", "confluence", "sequence_reclaim"}` (evaluate_bullish_setup,
# filter 11 defensive check) -- bull has no FHH-reclaim trigger, so no fhh entry here.
BEAR_LEVEL_TIED = frozenset({"level_rejection", "fhh_level_rejection", "confluence", "sequence_rejection"})
BULL_LEVEL_TIED = frozenset({"level_reclaim", "confluence", "sequence_reclaim"})

QUALITY_LOCK_ID = "quality_lock"   # kept namespace-distinct from GATE_ORDER's 15 ids -- a
                                    # STATEFUL escalation lock, not a static per-bar veto.


def neutral_gate_params() -> dict[str, Any]:
    """The documented 'off' value for every GATE_ORDER param key -- sourced from gates.py's
    own inline comments (MIN-RIBBON-SEMI-ARMED-FIX / MAX-RIBBON-DURATION-ZERO-FIX: "0 and
    None BOTH mean off"; every other gate is a plain boolean flag). Used by
    `evaluate_gates_full` to peel off one firing gate at a time without touching any other
    gate's armed state."""
    return {
        "block_level_rejection": False,
        "trendline_requires_ribbon_flip": False,
        "block_elite_bull": False,
        "block_bull_ribbon_flip": False,
        "block_bull_1100_1200": False,
        "block_bull_morning_agg": False,
        "require_bearish_fill_bar": False,
        "min_ribbon_momentum_cents": None,
        "max_ribbon_duration_bars": None,
        "midday_trendline_gate": False,
        "block_conf_lvl_rej_midday_afternoon": False,
        "block_conf_lvl_rec_afternoon": False,
        "entry_bar_body_pct_min": 0.0,
        "entry_bar_body_pct_min_bull": 0.0,
        "vix_bear_hard_cap": None,
    }


def evaluate_gates_full(ctx: GateContext, params: dict[str, Any]) -> list[GateBlock]:
    """Non-short-circuiting `evaluate_gates`: peel off the first-firing gate by neutralizing
    ONLY that gate's own param, re-call, repeat until none fire. Returns every gate in
    GATE_ORDER that would fire against the ORIGINAL params, in GATE_ORDER order (== the
    real cascade's firing order, so element [0] is provably what production actually fires
    first -- cross-checked in main() against the real run's own logged SKIP action).

    Calls the REAL `lib.engine.gates.evaluate_gates` -- zero duplicated predicate logic, zero
    drift risk. Bounded to len(GATE_ORDER)+1 iterations with a seen-set guard so a bug in a
    neutral value (one that doesn't actually turn its gate off) fails LOUD (RuntimeError)
    rather than looping forever or silently under-counting.
    """
    fired: list[GateBlock] = []
    local = dict(params)
    neutral = neutral_gate_params()
    seen: set[str] = set()
    for _ in range(len(GATE_ORDER) + 1):
        blk = evaluate_gates(ctx, local)
        if blk is None:
            break
        if blk.gate_id in seen:
            raise RuntimeError(
                f"evaluate_gates_full: gate {blk.gate_id!r} fired twice -- neutral value "
                "did not actually disarm it (neutral_gate_params bug)."
            )
        seen.add(blk.gate_id)
        fired.append(blk)
        if blk.gate_id not in neutral:
            raise RuntimeError(
                f"evaluate_gates_full: gate {blk.gate_id!r} has no neutral value registered "
                "-- GATE_ORDER has drifted ahead of neutral_gate_params()."
            )
        local[blk.gate_id] = neutral[blk.gate_id]
    return fired


def namespaced_filter_blockers(side: str, blockers: list[int]) -> frozenset[str]:
    """bear:filter_8 / bull:filter_8 -- namespaced because the SAME integer means a
    DIFFERENT predicate depending on side (see BEAR_FILTER_NAMES vs BULL_FILTER_NAMES).
    `side` is the engine's own "P"/"C" convention (bear=PUT, bull=CALL)."""
    if side not in ("P", "C"):
        raise ValueError(f"side must be 'P' or 'C', got {side!r}")
    prefix = "bear" if side == "P" else "bull"
    return frozenset(f"{prefix}:filter_{n}" for n in blockers)


def derive_winning_side(
    *, bear_passed: bool, bear_triggers: list[str], bull_passed: bool, bull_triggers: list[str],
) -> Optional[str]:
    """Byte-faithful port of orchestrator.py:1126-1149's routing tie-break (both PASSED ->
    higher trigger count wins, exact tie -> neither enters ("skip -- conflict", comment
    verbatim); else whichever side passed). Pure over the two sides' own passed/triggers --
    no ctx/state needed, so this is provably NOT the escalation lock (which needs day state)."""
    if bear_passed and bull_passed:
        if len(bear_triggers) > len(bull_triggers):
            return "P"
        if len(bull_triggers) > len(bear_triggers):
            return "C"
        return None  # exact tie: orchestrator's own "skip -- conflict" branch
    if bear_passed:
        return "P"
    if bull_passed:
        return "C"
    return None


def build_overlap_matrix(blocker_sets: list[frozenset[str]]) -> dict[str, Any]:
    """Given one non-empty joint-blocker-set per blocked candidate, return:
      - size_histogram: Counter{1: n_sole_blocked, 2: n_double_blocked, ...}
      - sole_blocker_counts: Counter{blocker_id: n_times_it_was_the_ONLY_reason}
      - pair_counts: Counter{frozenset({a,b}): n_times_a_and_b_co-fired} (size>=2 sets only)
      - member_counts: Counter{blocker_id: n_times_it_appeared_at_all} (any set size)
    Pure aggregation, no I/O. Empty sets are a caller bug (a candidate with zero blockers is
    an ENTRY, not a blocked row) -- raises rather than silently skipping, so a mis-wired
    caller cannot understate the blocking rate."""
    size_histogram: Counter = Counter()
    sole_blocker_counts: Counter = Counter()
    pair_counts: Counter = Counter()
    member_counts: Counter = Counter()
    for i, s in enumerate(blocker_sets):
        if not s:
            raise ValueError(f"build_overlap_matrix: row {i} has an EMPTY blocker set "
                              "(that's an entry, not a blocked candidate) -- caller bug.")
        size_histogram[len(s)] += 1
        for b in s:
            member_counts[b] += 1
        if len(s) == 1:
            sole_blocker_counts[next(iter(s))] += 1
        else:
            for a, b in itertools.combinations(sorted(s), 2):
                pair_counts[frozenset((a, b))] += 1
    return {
        "n_blocked": len(blocker_sets),
        "size_histogram": dict(size_histogram),
        "sole_blocker_counts": dict(sole_blocker_counts),
        "pair_counts": {"|".join(sorted(k)): v for k, v in pair_counts.items()},
        "member_counts": dict(member_counts),
    }


def one_sample_p(pnls: list[float]) -> float:
    """Two-sided normal-approximation p that mean(pnls) != 0. Same estimator convention as
    `bull_gate_f5class_requal_2026_08_01.py`/`WEEKEND-TWELVE`'s own studies (disclosed as
    optimistic at small n -- flagged in the report, not hidden)."""
    n = len(pnls)
    if n < 2:
        return 1.0
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    se = math.sqrt(var / n) if var > 0 else 0.0
    if se == 0.0:
        return 0.0 if mean != 0 else 1.0
    z = abs(mean) / se
    # two-sided normal tail via erfc (no scipy dependency in this venv-light module)
    return math.erfc(z / math.sqrt(2))


def bh_fdr(pvals: list[float], q: float = 0.10) -> list[bool]:
    """Standard Benjamini-Hochberg step-up. Returns a same-length bool list, True = survives
    at FDR q. Ties in p broken by original index (stable) -- matches the conventional
    step-up procedure (find largest k with p_(k) <= (k/m)*q; reject all <= that rank)."""
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    survive = [False] * m
    largest_k = 0
    for rank, idx in enumerate(order, start=1):
        if pvals[idx] <= (rank / m) * q:
            largest_k = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= largest_k:
            survive[idx] = True
    return survive


def classify_a_vs_c(
    *, oracle_bound_dollars: Optional[float], detector_fired_near_move: bool,
    floor: float = FOCUS_DAILY_FLOOR,
) -> str:
    """AXIS 2's (a)-vs-(c) decision tree -- called ONLY on days with zero qualifying
    candidates on either side (GATE_BLOCKED-day handles (b) upstream, unambiguously, before
    this function is ever reached). Pure, total, three-way closed enum:
      NOTHING_TRADEABLE      -- no clean-break candidate cleared the $ floor even with
                                 hindsight (or none existed at all)
      DETECTOR_FIRED_WEAK    -- a clean move cleared the floor AND some real/shadow trigger
                                 fired within 2 bars of its origin (weak-vocabulary, not a
                                 true vocabulary gap)
      NO_DETECTOR_GENUINE_GAP-- a clean move cleared the floor AND NOTHING fired near it --
                                 the genuine (c) case task asked for.
    """
    if oracle_bound_dollars is None or oracle_bound_dollars < floor:
        return "NOTHING_TRADEABLE"
    if detector_fired_near_move:
        return "DETECTOR_FIRED_WEAK"
    return "NO_DETECTOR_GENUINE_GAP"


def clean_move_candidates(
    levels: list[float], bars: list[dict], *, tolerance: float = 0.30,
    forward_bars: int = 12, retrace_max_pct: float = 0.50,
) -> list[dict]:
    """Oracle (hindsight) scan generalizing MULTIDAY-STRUCTURE-2026-07-31.md's hand-run
    touch-ledger (one level, one week, by hand) into a reusable function (every level, any
    day, in code). `bars` is a list of dicts (already-extracted, no pandas dependency here
    so this stays guard-testable with plain fixtures) with keys
    {idx, open, high, low, close}, chronological, same-day.

    For every level and every bar whose [low,high] comes within `tolerance` of it: determine
    approach direction (price was above -> support test -> bullish break is "away"; price
    was below -> resistance test -> bearish break is "away"), require the NEXT bar to close
    beyond the level by >= tolerance in the "away" direction (a decisive break/rejection,
    not a graze), then walk up to `forward_bars` bars measuring the peak favorable move and
    whether more than `retrace_max_pct` of that peak was given back before the window ends
    (chop, not a clean impulse). Returns one dict per surviving candidate:
      {level, touch_idx, break_idx, direction ("up"/"down"), peak_move_dollars, clean: bool}
    Directional convention: direction="up" -> a BULL/call candidate; "down" -> BEAR/put.
    """
    out: list[dict] = []
    if not bars:
        return out
    by_idx = {b["idx"]: b for b in bars}
    idx_sorted = sorted(by_idx)
    for level in levels:
        for pos, idx in enumerate(idx_sorted):
            b = by_idx[idx]
            if not (b["low"] - tolerance <= level <= b["high"] + tolerance):
                continue
            # approach direction: compare bar's own open to the level
            approached_from_above = b["open"] >= level
            nxt_pos = pos + 1
            if nxt_pos >= len(idx_sorted):
                continue
            nxt_idx = idx_sorted[nxt_pos]
            nxt = by_idx[nxt_idx]
            if approached_from_above:
                # support test -> "away" is UP; decisive break is a clean reject-and-bounce
                if nxt["close"] < level - tolerance:
                    continue  # broke DOWN through -- not a bounce, skip (would be caught
                              # as its own down-break candidate from a different touch bar)
                direction = "up"
                decisive = nxt["close"] >= level + tolerance
            else:
                if nxt["close"] > level + tolerance:
                    continue
                direction = "down"
                decisive = nxt["close"] <= level - tolerance
            if not decisive:
                continue
            window = [by_idx[i] for i in idx_sorted[nxt_pos: nxt_pos + forward_bars] if i in by_idx]
            if not window:
                continue
            entry_ref = nxt["open"]
            if direction == "up":
                peak = max(w["high"] for w in window)
                peak_move = peak - entry_ref
                trough_after_peak = min(
                    (w["low"] for w in window if w["high"] <= peak), default=peak
                )
                # retrace = give-back measured from the running peak to the window's final low
                final_low = window[-1]["low"]
                retrace = (peak - final_low) / peak_move if peak_move > 0 else 1.0
            else:
                trough = min(w["low"] for w in window)
                peak_move = entry_ref - trough
                final_high = window[-1]["high"]
                retrace = (final_high - trough) / peak_move if peak_move > 0 else 1.0
            if peak_move <= 0:
                continue
            clean = retrace <= retrace_max_pct
            out.append({
                "level": level, "touch_idx": idx, "break_idx": nxt_idx,
                "direction": direction, "peak_move_dollars": round(peak_move, 4),
                "retrace_pct": round(retrace, 4), "clean": clean,
            })
    return out


# =========================================================================================
# HEAVY PIPELINE -- lazy imports below this marker, matching day_report_card.py's own
# convention ("lazy imports so the guard test imports stay light/pure").
# =========================================================================================

GATE_PARAM_KEYS = [k for _gid, k, _act in GATE_ORDER] + [
    "block_elite_bull_vix_low", "block_elite_bull_vix_high", "midday_trendline_gate_start_minutes",
]


def build_gate_params(safe_base_live: dict, run_backtest_fn) -> dict:
    """The exact gate-param dict `evaluate_gates`/`evaluate_gates_full` need for THIS run:
    SAFE_BASE_LIVE's explicit value where present, else `run_backtest`'s OWN declared
    default -- introspected via `inspect.signature`, never hand-copied, zero drift risk.
    Gate params are FIXED for the whole walk (SAFE_BASE_LIVE doesn't vary bar-to-bar), so
    this is computed ONCE, not per candidate."""
    import inspect
    sig = inspect.signature(run_backtest_fn)
    out = {}
    for key in GATE_PARAM_KEYS:
        out[key] = safe_base_live[key] if key in safe_base_live else sig.parameters[key].default
    return out


def run_backtest_with_full_capture(spy_df, vix_df, start_date, end_date, **kwargs):
    """Extends `ladder_fullhist_replay.run_backtest_with_bull_capture`'s established
    monkeypatch pattern (which captures ONLY a bull `.passed` boolean) to capture the FULL
    SetupResult/BullishSetupResult for BOTH sides on every bar, plus the bar-level ctx
    fields (levels_active, multi_day_levels, vix_now, OHLC, ribbon) the gate layer and the
    AXIS-2 oracle scan both need. Pure pass-through wrapper (same args in, same object out,
    zero behavior change) -- restores both originals in `finally` regardless of outcome,
    same safety guarantee the precedent already carries (verified there against
    GAMMA_ENGINE_SCORE_ASSERT/GAMMA_ENGINE_GATES_ASSERT; unchanged here since neither
    assert's OWN internal calls route through the orchestrator-module names we rebind)."""
    import lib.orchestrator as orch_mod
    from lib.orchestrator import run_backtest

    bear_capture: dict[int, dict] = {}
    bull_capture: dict[int, dict] = {}
    orig_bear = orch_mod.evaluate_bearish_setup
    orig_bull = orch_mod.evaluate_bullish_setup

    def _capture_bear(ctx, **kw):
        res = orig_bear(ctx, **kw)
        bear_capture[ctx.bar_idx] = {
            "bar_idx": ctx.bar_idx, "passed": bool(res.passed), "score": res.bear_score,
            "blockers": list(res.blockers), "triggers_fired": list(res.triggers_fired),
            "level": res.rejection_level,
            "levels_active": [float(x) for x in (ctx.levels_active or [])],
            "multi_day_levels": [float(x) for x in (ctx.multi_day_levels or [])],
            "vix_now": float(ctx.vix_now), "bar_time": ctx.timestamp_et,
            "bar_open": float(ctx.bar["open"]), "bar_high": float(ctx.bar["high"]),
            "bar_low": float(ctx.bar["low"]), "bar_close": float(ctx.bar["close"]),
            "ribbon_spread_cents": (float(ctx.ribbon_now.spread_cents) if ctx.ribbon_now else None),
            "ribbon_stack": (ctx.ribbon_now.stack if ctx.ribbon_now else None),
        }
        return res

    def _capture_bull(ctx, **kw):
        res = orig_bull(ctx, **kw)
        bull_capture[ctx.bar_idx] = {
            "bar_idx": ctx.bar_idx, "passed": bool(res.passed), "score": res.bull_score,
            "blockers": list(res.blockers), "triggers_fired": list(res.triggers_fired),
            "level": res.reclaim_level,
        }
        return res

    orch_mod.evaluate_bearish_setup = _capture_bear
    orch_mod.evaluate_bullish_setup = _capture_bull
    try:
        r = run_backtest(spy_df, vix_df, start_date=start_date, end_date=end_date, **kwargs)
    finally:
        orch_mod.evaluate_bearish_setup = orig_bear
        orch_mod.evaluate_bullish_setup = orig_bull
    return r, bear_capture, bull_capture


def build_qualifying_candidates(bear_capture: dict, bull_capture: dict) -> list[dict]:
    """Extends `day_report_card.py`/`ladder_fullhist_replay.py`'s bear-only, score>=8 +
    level-tied-trigger + valid-level candidate definition to BOTH sides -- same
    QUALIFYING_SCORE_FLOOR, applied symmetrically via BEAR_LEVEL_TIED/BULL_LEVEL_TIED.

    ALSO covers the bear TRENDLINE-ONLY shape (`trendline_rejection` present, NONE of
    level_rejection/confluence/sequence_rejection present -- the exact `_trendline_only_shape`
    predicate `evaluate_bearish_setup` itself uses for its own filters-5/8/9 relaxation,
    filters.py ~1625). THIS MATTERS: per CLAUDE.md's own live doctrine citation
    ("Measured 2026-07-27..08-01: 89% of all bear ENTER verdicts over 33 sessions came
    through this bypass alone" -- the G2-TRENDLINE-BYPASS thread, resolved 2026-08-01,
    "neither arm ships"), excluding this shape would mean the gate-cascade study covers a
    MINORITY of real bear entries. `SetupResult` does not expose the trendline's own price
    (it's a local inside `evaluate_bearish_setup`, only `rejection_level` -- populated from
    level_rejection/wick/FHH -- is returned), so TRENDLINE_ONLY rows are emitted with
    `level=None` here; `main()` backfills it via a DIRECT, READ-ONLY re-call to the same
    `detect_trendline_rejection_bearish` pure function production itself calls (zero drift
    risk -- identical function, identical bar/prior_bars/bar_idx inputs) before any
    downstream layer-resolution or pricing touches these rows. Bull has NO trendline
    trigger in production (`trendline_reclaim` is SHADOW-only, never merged into
    `triggers_fired` -- confirmed by reading `evaluate_bullish_setup`), so there is no bull
    mirror of this branch."""
    out = []
    for b in bear_capture.values():
        if b["score"] < QUALIFYING_SCORE_FLOOR:
            continue
        trig = b["triggers_fired"]
        if isinstance(b["level"], (int, float)) and any(t in BEAR_LEVEL_TIED for t in trig):
            out.append({**b, "side": "P", "candidate_class": "LEVEL_TIED"})
        elif ("trendline_rejection" in trig and "level_rejection" not in trig
              and "confluence" not in trig and "sequence_rejection" not in trig):
            out.append({**b, "side": "P", "candidate_class": "TRENDLINE_ONLY", "level": None})
    for u in bull_capture.values():
        if u["score"] >= QUALIFYING_SCORE_FLOOR and isinstance(u["level"], (int, float)):
            if any(t in BULL_LEVEL_TIED for t in u["triggers_fired"]):
                out.append({**u, "side": "C", "candidate_class": "LEVEL_TIED"})
    return out


def backfill_trendline_levels(candidates: list[dict], spy_rth) -> list[dict]:
    """For every TRENDLINE_ONLY candidate, re-derive the trendline price via a DIRECT call
    to `filters.detect_trendline_rejection_bearish` (the SAME pure function production
    calls, same args -- read-only reuse, zero duplication of its pivot-finding logic).
    `ctx.prior_bars` in production is literally the whole reindexed `spy_df` object, not a
    per-bar slice (confirmed: orchestrator.py's BarContext construction passes
    `prior_bars=spy_df` unconditionally) -- so `spy_rth` (this tool's own byte-identical
    reconstruction of that same frame) is the correct, drift-free substitute. Rows where the
    detector no longer fires (should not happen if `triggers_fired` was recorded correctly,
    but defensive) are DROPPED with a count, never silently kept with `level=None` (which
    would crash the pricing layer downstream)."""
    from lib.filters import detect_trendline_rejection_bearish, TRENDLINE_LOOKBACK_BARS, TRENDLINE_MIN_SWINGS
    out = []
    n_dropped = 0
    for c in candidates:
        if c.get("candidate_class") != "TRENDLINE_ONLY":
            out.append(c)
            continue
        bar_idx = c["bar_idx"]
        level = detect_trendline_rejection_bearish(
            spy_rth.iloc[bar_idx], spy_rth, bar_idx,
            lookback_bars=TRENDLINE_LOOKBACK_BARS, min_swings=TRENDLINE_MIN_SWINGS,
        )
        if level is None:
            n_dropped += 1
            continue
        out.append({**c, "level": float(level)})
    return out, n_dropped


def resolve_candidate_layer(
    cand: dict, *, other_side_capture: dict, bear_capture: dict,
    decisions_by_bar_idx: dict, gate_params: dict, ribbon_df, spy_rth,
) -> dict:
    """For ONE qualifying candidate, walk the REAL cascade order and return its outcome:
      FILTER_BLOCKED  cand['blockers'] non-empty -> joint_set = namespaced filter blockers
                       (already the FULL set -- evaluate_*_setup never short-circuits).
      ROUTING_LOSS    filters clean, but the OTHER side won routing (orchestrator's own
                       tie-break, see derive_winning_side) -- NOT a gate, reported
                       separately, never folded into gate/overlap stats.
      GATE_BLOCKED    this side won routing; quality_lock and/or >=1 named gate fires
                       (peel-off, see evaluate_gates_full) -> joint_set = their union.
      ENTERED         this side won routing; nothing in the gate layer fires.
    `bear_capture` supplies bar-level fields (OHLC/vix/ribbon/time) regardless of the
    candidate's own side, since ctx is the SAME object orchestrator built once per bar and
    handed to BOTH evaluate_bearish_setup and evaluate_bullish_setup -- bear_capture has
    complete per-bar coverage (bear is evaluated unconditionally every bar); bull_capture
    does not carry these fields (see run_backtest_with_full_capture)."""
    side = cand["side"]
    bar_idx = cand["bar_idx"]
    if cand["blockers"]:
        return {
            "side": side, "bar_idx": bar_idx, "status": "FILTER_BLOCKED",
            "joint_set": namespaced_filter_blockers(side, cand["blockers"]),
            "triggers_fired": cand["triggers_fired"], "level": cand["level"],
        }

    other = other_side_capture.get(bar_idx)
    other_passed = bool(other["passed"]) if other else False
    other_triggers = other["triggers_fired"] if other else []
    if side == "P":
        winner = derive_winning_side(bear_passed=True, bear_triggers=cand["triggers_fired"],
                                      bull_passed=other_passed, bull_triggers=other_triggers)
    else:
        winner = derive_winning_side(bear_passed=other_passed, bear_triggers=other_triggers,
                                      bull_passed=True, bull_triggers=cand["triggers_fired"])
    if winner != side:
        return {"side": side, "bar_idx": bar_idx, "status": "ROUTING_LOSS",
                "joint_set": frozenset(), "triggers_fired": cand["triggers_fired"], "level": cand["level"]}

    import elite_bear_level_reject_gate_ab as eb  # classify_tier -- the codebase-wide standard
    tier = eb.classify_tier(cand["triggers_fired"])
    has_level_trig = ("level_rejection" if side == "P" else "level_reclaim") in cand["triggers_fired"]
    quality_lock_fired = any(
        row.get("action") == "SKIP_QUALITY_LOCK" for row in decisions_by_bar_idx.get(bar_idx, [])
    )
    bar_fields = bear_capture[bar_idx]
    gctx = GateContext(
        winning_side=side, winning_triggers=cand["triggers_fired"], quality_tier=tier,
        has_level=has_level_trig,
        bar={"open": bar_fields["bar_open"], "high": bar_fields["bar_high"],
             "low": bar_fields["bar_low"], "close": bar_fields["bar_close"]},
        bar_idx=bar_idx, bar_time=bar_fields["bar_time"], vix_now=bar_fields["vix_now"],
        ribbon_spread_cents=bar_fields["ribbon_spread_cents"], ribbon_stack=bar_fields["ribbon_stack"],
        spy_df=spy_rth, ribbon_df=ribbon_df,
    )
    fired_gates = evaluate_gates_full(gctx, gate_params)
    joint = {g.gate_id for g in fired_gates}
    if quality_lock_fired:
        joint.add(QUALITY_LOCK_ID)
    status = "GATE_BLOCKED" if joint else "ENTERED"
    return {"side": side, "bar_idx": bar_idx, "status": status, "joint_set": frozenset(joint),
            "triggers_fired": cand["triggers_fired"], "level": cand["level"],
            "first_real_action": (
                next((row.get("action") for row in decisions_by_bar_idx.get(bar_idx, [])
                      if row.get("action") not in (None,)), None)
            )}


def resolve_entry_any_side(spy_df, trigger_idx: int, strike: int, trade_date, vix_now: float,
                            spot: float, side: str, opt_loader=None) -> dict:
    """Side-parameterized clone of `ladder_fullhist_replay.resolve_ladder_entry` (which
    hardcodes side='P'/put). IDENTICAL entry+1 / real-OPRA / BS-synthetic-disclosure logic
    -- `option_symbol(..., side)` and `black_scholes(..., is_call=(side=='C'))` threaded by
    side instead of hardcoded. Returns either {"ok": True, symbol, opt_df, entry_time_et
    (naive), entry_premium} from the REAL OPRA cache, or {"ok": False, reason,
    synthetic_entry_premium} -- a BS-synthetic premium for DISCLOSURE only, never fed
    through a synthetic exit walk (same rule every oracle table in this repo follows)."""
    from lib.option_pricing_real import bar_at_or_after, load_contract_bars, option_symbol
    from lib.pricing import black_scholes, time_to_expiry_years, vix_to_iv
    import engine_fullhist_replay as efr
    if opt_loader is None:
        opt_loader = load_contract_bars

    next_idx = trigger_idx + 1
    if next_idx >= len(spy_df):
        return {"ok": False, "reason": "no_next_bar_same_day", "synthetic_entry_premium": None}
    trig_date = spy_df.iloc[trigger_idx]["timestamp_et"].date()
    if spy_df.iloc[next_idx]["timestamp_et"].date() != trig_date:
        return {"ok": False, "reason": "no_next_bar_same_day", "synthetic_entry_premium": None}
    next_ts = spy_df.iloc[next_idx]["timestamp_et"]
    symbol = option_symbol(trade_date, int(strike), side)
    opt_df = opt_loader(symbol)
    reason = "no_opra_cache"
    if opt_df is not None:
        ob = bar_at_or_after(opt_df, next_ts)
        if ob is not None:
            return {"ok": True, "symbol": symbol, "opt_df": opt_df,
                    "entry_time_et": efr.naive_dt(ob.timestamp_et), "entry_premium": float(ob.open)}
        reason = "opra_cached_but_no_bar_at_or_after_next"
    iv = vix_to_iv(vix_now)
    tte = time_to_expiry_years(next_ts.to_pydatetime())
    price, _delta = black_scholes(spot, strike, iv, tte, is_call=(side == "C"))
    return {"ok": False, "reason": reason, "synthetic_entry_premium": round(max(price, 0.01), 4)}


def price_sole_blocker_cohort(
    rows: list[dict], *, spy_rth, ribbon_lookup, exit_shape: dict, time_stop_et: dt.time,
    min_contracts: int, ref_equity: float,
) -> dict:
    """Walk EVERY row in a sole-blocker cohort through the SAME real-OPRA + REAL
    exit_manager pipeline day_report_card.py's oracle walks use (structure-stop enabled,
    RIBBON_RIDE exit shape, entry+1-at-OPEN). ORACLE, hindsight, NOT achievable, NOT
    one-position-at-a-time -- identical disclosed convention to every prior oracle table in
    this repo. Returns {n_priced, n_synthetic_excluded, total_dollars, per_trade, wr,
    trades: [...]}."""
    from crypto.lib.strike_selection import pick_strike
    import fleet_executor as fx
    import engine_fullhist_replay as efr
    from lib.exit_manager_walk import walk_exit_manager

    trades = []
    n_synth = 0
    for row in rows:
        bar_idx = row["bar_idx"]
        side = row["side"]
        spot = float(spy_rth.iloc[bar_idx]["close"])
        vix_now = row.get("vix_now")
        if vix_now is None:
            vix_now = float(spy_rth.iloc[bar_idx].get("vix", 16.0))
        strike = pick_strike(spot, ref_equity, side, fx.PROBE_STRIKE_TIERS)
        res = resolve_entry_any_side(spy_rth, bar_idx, strike, spy_rth.iloc[bar_idx]["timestamp_et"].date(),
                                      vix_now, spot, side)
        if not res["ok"]:
            n_synth += 1
            continue
        rtd = efr.ribbon_tick_df_for(res["opt_df"], ribbon_lookup)
        day_spy = spy_rth.loc[spy_rth["timestamp_et"].dt.date == spy_rth.iloc[bar_idx]["timestamp_et"].date()]
        walk = walk_exit_manager(
            symbol=res["symbol"], side=side, entry_time_et=res["entry_time_et"],
            entry_premium=res["entry_premium"], qty=min_contracts, exit_shape=exit_shape,
            structure_stop_enabled=True, trigger_level=float(row["level"]),
            strategy="ribbon_ride", time_stop_et=time_stop_et,
            opt_df=res["opt_df"], ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        trades.append({
            "bar_idx": bar_idx, "side": side, "date": spy_rth.iloc[bar_idx]["timestamp_et"].date().isoformat(),
            "entry_time_et": res["entry_time_et"].isoformat(), "entry_premium": round(res["entry_premium"], 4),
            "dollar_pnl": walk.dollar_pnl, "exit_reason": walk.exit_reason,
            "triggers_fired": row["triggers_fired"],
        })
    total = round(sum(t["dollar_pnl"] for t in trades), 2)
    n = len(trades)
    wr = round(sum(1 for t in trades if t["dollar_pnl"] > 0) / n, 4) if n else None
    return {"n_priced": n, "n_synthetic_excluded": n_synth, "total_dollars": total,
            "per_trade_dollars": (round(total / n, 2) if n else None), "win_rate": wr, "trades": trades}


# =========================================================================================
# AXIS 2 -- day-level participation taxonomy + the (a)/(c) oracle clean-move scan.
# =========================================================================================

def aggregate_day_participation(*, bear_capture: dict, bull_capture: dict,
                                  resolved_by_bar_side: dict, spy_rth) -> dict[str, dict]:
    """Per calendar day, BOTH sides: ENTERED / GATE_BLOCKED_DAY / CORRECTLY_FLAT /
    NO_VOCABULARY. Extends day_report_card.py's bear-only taxonomy (GATE_BLOCKED_DAY here
    folds FILTER_BLOCKED and GATE_BLOCKED candidate-level statuses together -- both are
    task's (b), "detector fired + something blocked it"; the filter-vs-gate distinction is
    preserved candidate-by-candidate in `resolved_by_bar_side`, just not needed at the
    day-taxonomy level). `resolved_by_bar_side` is {(bar_idx, side): resolved_row} from
    resolve_candidate_layer, for every qualifying candidate."""
    dates = spy_rth["timestamp_et"].dt.date
    date_by_idx = {i: dates.iloc[i] for i in range(len(spy_rth))}

    any_trigger_by_day: dict = {}
    for cap in (bear_capture, bull_capture):
        for bar_idx, row in cap.items():
            d = date_by_idx.get(bar_idx)
            if d is not None and row["triggers_fired"]:
                any_trigger_by_day[d] = True

    status_by_day: dict = {}
    for (bar_idx, _side), row in resolved_by_bar_side.items():
        d = date_by_idx.get(bar_idx)
        if d is not None:
            status_by_day.setdefault(d, set()).add(row["status"])

    out = {}
    for d in sorted(set(date_by_idx.values())):
        statuses = status_by_day.get(d, set())
        if "ENTERED" in statuses:
            cause = "ENTERED"
        elif "GATE_BLOCKED" in statuses or "FILTER_BLOCKED" in statuses:
            cause = "GATE_BLOCKED_DAY"
        elif any_trigger_by_day.get(d, False):
            cause = "CORRECTLY_FLAT"
        else:
            cause = "NO_VOCABULARY"
        out[d.isoformat()] = {"cause": cause, "statuses_seen": sorted(statuses)}
    return out


def levels_seen_for_day(bear_capture: dict, day_bar_idxs: list[int]) -> list[float]:
    """Union of every levels_active/multi_day_levels value seen on any bar that day
    (bear_capture has complete per-bar coverage -- see run_backtest_with_full_capture),
    rounded to the cent and deduped -- the engine's OWN level set for that day, not
    re-derived from scratch."""
    seen: set[float] = set()
    for idx in day_bar_idxs:
        row = bear_capture.get(idx)
        if not row:
            continue
        for lv in row["levels_active"]:
            seen.add(round(float(lv), 2))
        for lv in row["multi_day_levels"]:
            seen.add(round(float(lv), 2))
    return sorted(seen)


def detector_fired_near(bear_capture: dict, bull_capture: dict, touch_idx: int, window: int = 2) -> bool:
    """Did ANY real trigger (either side) fire within `window` bars of touch_idx? Shadow
    triggers (bull's trendline_reclaim/wick_reclaim/pullback_hold) are DELIBERATELY
    EXCLUDED here -- INERT-SIGNALS-2026-07-31.md already measured trendline_reclaim
    significant-NEGATIVE and wick_reclaim negative-not-significant as entry triggers; a day
    those shadow signals fired near a big move is NOT evidence of a vocabulary gap, it is
    evidence of an already-quarantined-for-cause signal being present. Counting them here
    would misclassify a DETECTOR_FIRED_WEAK day as NO_DETECTOR_GENUINE_GAP."""
    for offset in range(-window, window + 1):
        idx = touch_idx + offset
        for cap in (bear_capture, bull_capture):
            row = cap.get(idx)
            if row and row["triggers_fired"]:
                return True
    return False


def oracle_scan_no_trade_day(
    *, day_bar_idxs: list[int], bear_capture: dict, bull_capture: dict, spy_rth,
    top_k_to_price: int = 2,
) -> dict:
    """AXIS 2's (a)-vs-(c) oracle for ONE no-qualifying-candidate day. Builds the day's bar
    list + active level set from the engine's OWN captured state, runs
    `clean_move_candidates`, prices the top-K by raw SPY-point size (bounds runtime -- see
    module docstring), and returns the day's best oracle bound + whether a real trigger
    fired near it. Pricing is deferred to the caller (needs the heavier
    ribbon_lookup/exit_shape plumbing) -- this function returns the CANDIDATE list to price,
    not $ figures, keeping it testable without OPRA I/O.
    """
    if not day_bar_idxs:
        return {"candidates_to_price": [], "levels": []}
    levels = levels_seen_for_day(bear_capture, day_bar_idxs)
    bars = []
    for idx in day_bar_idxs:
        row = bear_capture.get(idx)
        if not row:
            continue
        bars.append({"idx": idx, "open": row["bar_open"], "high": row["bar_high"],
                      "low": row["bar_low"], "close": row["bar_close"]})
    cands = clean_move_candidates(levels, bars)
    clean = [c for c in cands if c["clean"]]
    clean.sort(key=lambda c: -c["peak_move_dollars"])
    top = clean[: top_k_to_price]
    for c in top:
        c["detector_fired_near_move"] = detector_fired_near(bear_capture, bull_capture, c["touch_idx"])
        c["side"] = "P" if c["direction"] == "down" else "C"
    return {"candidates_to_price": top, "levels": levels}


# =========================================================================================
# main() -- orchestration.
# =========================================================================================

def log(msg: str) -> None:
    print(f"[freq-ceiling] {msg}", flush=True)


OUT_JSON = ROOT / "analysis" / "deep-research" / "FREQUENCY-CEILING-2026-08-03.json"
OUT_MD = ROOT / "analysis" / "deep-research" / "FREQUENCY-CEILING-2026-08-03.md"
REF_EQUITY_FOR_STRIKE = 2000.0
MIN_CONTRACTS = 3
TIME_STOP_ET = dt.time(15, 40)

# Top-N sole-blocker cohorts (by n) to price with real OPRA -- bounds runtime; every cohort's
# COUNT still appears in the overlap matrix regardless of whether it gets priced.
MAX_SOLE_BLOCKER_COHORTS_TO_PRICE = 12
MAX_NO_TRADE_DAYS_TO_ORACLE_SCAN = 0   # 0 == no cap (scan every no-qualifying-candidate day)


def main(smoke: bool = False, smoke_days: int = 15) -> int:
    import time
    t_start = time.time()
    import pandas as pd  # noqa: F401
    import elite_bear_level_reject_gate_ab as eb
    import engine_fullhist_replay as efr
    import fleet_executor as fx
    import ladder_fullhist_replay as lfr
    import strategies as fleet_strategies
    from lib.orchestrator import run_backtest
    from lib.ribbon import compute_ribbon

    log("loading extended SPY/VIX data (identical merge to ladder_fullhist_replay/day_report_card)")
    spy_df_raw, vix_df = lfr.load_extended_data()
    spy_rth = lfr.build_rth_frame(spy_df_raw)
    all_dates = sorted(spy_rth["timestamp_et"].dt.date.unique())
    log(f"  window: {all_dates[0]}..{all_dates[-1]} ({len(all_dates)} RTH days)")

    run_kwargs = dict(efr.SAFE_BASE_LIVE)
    start_date, end_date = lfr.FULL_START, lfr.FULL_END
    report_dates = all_dates
    if smoke:
        # Fast correctness pass over the most recent 15 RTH days only -- NOT a reported
        # result, a pre-flight check before committing to the ~2-5min full-population run.
        # `report_dates` (NOT `all_dates`) gates which calendar days axis-2/day-participation
        # iterate -- without this, days outside the smoke window have NO captured data and
        # fall through to a spurious NO_VOCABULARY (bear_capture.get() misses, not a real
        # zero-trigger day) -- a smoke-mode-only artifact, disclosed here rather than shipped
        # silently. The full (non-smoke) run is unaffected: report_dates == all_dates.
        start_date = all_dates[-smoke_days]
        report_dates = [d for d in all_dates if d >= start_date]
        log(f"  SMOKE MODE: restricting to {start_date}..{end_date} "
            f"({len(report_dates)} reportable days)")

    gate_params = build_gate_params(run_kwargs, run_backtest)
    log(f"gate params resolved for {len(gate_params)} keys (SAFE_BASE_LIVE + introspected defaults)")

    log("running run_backtest with FULL bear+bull capture (both SetupResult objects, every bar)")
    t0 = time.time()
    r, bear_capture, bull_capture = run_backtest_with_full_capture(
        spy_df_raw, vix_df, start_date=start_date, end_date=end_date, **run_kwargs)
    log(f"  done in {time.time()-t0:.1f}s -- {len(r.trades)} raw entries, "
        f"{len(r.decisions)} decision rows, {len(bear_capture)} bear-captured bars, "
        f"{len(bull_capture)} bull-captured bars")

    decisions_by_bar_idx: dict = {}
    for row in r.decisions:
        decisions_by_bar_idx.setdefault(row["bar_idx"], []).append(row)

    ribbon_df = compute_ribbon(spy_rth["close"])
    ribbon_lookup = efr.build_ribbon_lookup(spy_df_raw)
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    log("building qualifying candidates (score>=8, level-tied OR bear-trendline-only), BOTH sides")
    candidates = build_qualifying_candidates(bear_capture, bull_capture)
    n_trendline_raw = sum(1 for c in candidates if c.get("candidate_class") == "TRENDLINE_ONLY")
    candidates, n_trendline_dropped = backfill_trendline_levels(candidates, spy_rth)
    n_bear_cand = sum(1 for c in candidates if c["side"] == "P")
    n_bull_cand = sum(1 for c in candidates if c["side"] == "C")
    n_trendline_cand = sum(1 for c in candidates if c.get("candidate_class") == "TRENDLINE_ONLY")
    log(f"  {len(candidates)} qualifying candidates (bear={n_bear_cand} incl. "
        f"{n_trendline_cand} trendline-only [{n_trendline_dropped} of {n_trendline_raw} dropped, "
        f"detector didn't re-fire], bull={n_bull_cand}; anchor: bear-only level-tied floor-8 "
        f"count in the published ladder replay is 2308)")

    log("resolving each candidate's cascade outcome (filter layer -> routing -> gate layer)")
    resolved_by_bar_side: dict = {}
    gate_agreement_checked = 0
    gate_agreement_matched = 0
    for cand in candidates:
        side = cand["side"]
        other_cap = bull_capture if side == "P" else bear_capture
        out = resolve_candidate_layer(
            cand, other_side_capture=other_cap, bear_capture=bear_capture,
            decisions_by_bar_idx=decisions_by_bar_idx, gate_params=gate_params,
            ribbon_df=ribbon_df, spy_rth=spy_rth,
        )
        resolved_by_bar_side[(cand["bar_idx"], side)] = out
        # Cross-validation: where the REAL sequential run also logged a named-gate SKIP_*
        # action for this exact bar, the FIRST element of our peel-off must match it (proves
        # evaluate_gates_full's ordering agrees with the actual production cascade, not just
        # with evaluate_gates() in isolation).
        real_action = out.get("first_real_action")
        if real_action and real_action.startswith("SKIP_") and real_action != "SKIP_QUALITY_LOCK":
            gate_agreement_checked += 1
            first_gate_action = None
            for gid, _pk, act in GATE_ORDER:
                if gid in out["joint_set"]:
                    first_gate_action = act
                    break
            if first_gate_action == real_action:
                gate_agreement_matched += 1

    status_counts = Counter(v["status"] for v in resolved_by_bar_side.values())
    log(f"  status counts: {dict(status_counts)}")
    if gate_agreement_checked:
        log(f"  gate-order cross-check: {gate_agreement_matched}/{gate_agreement_checked} "
            "real-run first-SKIP actions matched our peel-off's first element")

    log("building overlap matrix (all blocked candidates) + gate-layer-only sub-matrix")
    all_blocked_sets = [v["joint_set"] for v in resolved_by_bar_side.values()
                         if v["status"] in ("FILTER_BLOCKED", "GATE_BLOCKED")]
    overlap_all = build_overlap_matrix(all_blocked_sets)
    gate_layer_sets = [v["joint_set"] for v in resolved_by_bar_side.values() if v["status"] == "GATE_BLOCKED"]
    overlap_gate_layer = build_overlap_matrix(gate_layer_sets) if gate_layer_sets else {
        "n_blocked": 0, "size_histogram": {}, "sole_blocker_counts": {}, "pair_counts": {}, "member_counts": {}}
    routing_loss_n = sum(1 for v in resolved_by_bar_side.values() if v["status"] == "ROUTING_LOSS")
    log(f"  overlap_all: n_blocked={overlap_all['n_blocked']} size_hist={overlap_all['size_histogram']}")
    log(f"  overlap_gate_layer (post-filter, post-routing only): n_blocked={overlap_gate_layer['n_blocked']} "
        f"size_hist={overlap_gate_layer['size_histogram']}")
    log(f"  routing_loss (rare tie/conflict bucket, excluded from gate stats): {routing_loss_n}")

    log(f"pricing top {MAX_SOLE_BLOCKER_COHORTS_TO_PRICE} sole-blocker cohorts (real OPRA + real exit walk)")
    sole_ranked = sorted(overlap_all["sole_blocker_counts"].items(), key=lambda kv: -kv[1])
    priced_cohorts = {}
    pvals_for_bh: list[float] = []
    cohort_names_for_bh: list[str] = []
    for blocker_id, n in sole_ranked[:MAX_SOLE_BLOCKER_COHORTS_TO_PRICE]:
        rows = [v for v in resolved_by_bar_side.values()
                if v["status"] in ("FILTER_BLOCKED", "GATE_BLOCKED") and v["joint_set"] == frozenset({blocker_id})]
        priced = price_sole_blocker_cohort(
            rows, spy_rth=spy_rth, ribbon_lookup=ribbon_lookup, exit_shape=exit_shape,
            time_stop_et=TIME_STOP_ET, min_contracts=MIN_CONTRACTS, ref_equity=REF_EQUITY_FOR_STRIKE,
        )
        priced_cohorts[blocker_id] = priced
        log(f"  {blocker_id}: n_blocked={n} n_priced={priced['n_priced']} "
            f"total=${priced['total_dollars']:+.2f}" if priced['total_dollars'] is not None
            else f"  {blocker_id}: n_blocked={n} n_priced=0")
        if priced["n_priced"] >= 2:
            pvals_for_bh.append(one_sample_p([t["dollar_pnl"] for t in priced["trades"]]))
            cohort_names_for_bh.append(blocker_id)
    bh_survive = bh_fdr(pvals_for_bh, q=0.10)
    bh_by_cohort = dict(zip(cohort_names_for_bh, bh_survive))

    log("AXIS 2 -- day-level participation classification")
    day_participation_raw = aggregate_day_participation(
        bear_capture=bear_capture, bull_capture=bull_capture,
        resolved_by_bar_side=resolved_by_bar_side, spy_rth=spy_rth)
    report_date_isos = {d.isoformat() for d in report_dates}
    day_participation = {k: v for k, v in day_participation_raw.items() if k in report_date_isos}
    day_cause_counts = Counter(v["cause"] for v in day_participation.values())
    log(f"  day causes ({len(day_participation)} reportable days): {dict(day_cause_counts)}")

    log("AXIS 2 -- oracle clean-move scan on every no-qualifying-candidate day")
    idxs_by_date: dict = {}
    dates_series = spy_rth["timestamp_et"].dt.date
    for i, d in enumerate(dates_series):
        idxs_by_date.setdefault(d, []).append(i)

    no_trade_days = [d for d, v in day_participation.items()
                      if v["cause"] in ("NO_VOCABULARY", "CORRECTLY_FLAT")]
    if MAX_NO_TRADE_DAYS_TO_ORACLE_SCAN:
        no_trade_days = no_trade_days[:MAX_NO_TRADE_DAYS_TO_ORACLE_SCAN]
    log(f"  {len(no_trade_days)} no-qualifying-candidate days to scan")

    axis2_rows = []
    for date_iso in no_trade_days:
        d = dt.date.fromisoformat(date_iso)
        scan = oracle_scan_no_trade_day(
            day_bar_idxs=idxs_by_date.get(d, []), bear_capture=bear_capture,
            bull_capture=bull_capture, spy_rth=spy_rth)
        best_dollars = None
        best_cand = None
        for c in scan["candidates_to_price"]:
            priced = price_sole_blocker_cohort(
                [{"bar_idx": c["touch_idx"], "side": c["side"], "level": c["level"],
                  "triggers_fired": [], "vix_now": bear_capture.get(c["touch_idx"], {}).get("vix_now")}],
                spy_rth=spy_rth, ribbon_lookup=ribbon_lookup, exit_shape=exit_shape,
                time_stop_et=TIME_STOP_ET, min_contracts=MIN_CONTRACTS, ref_equity=REF_EQUITY_FOR_STRIKE,
            )
            if priced["n_priced"] and (best_dollars is None or priced["total_dollars"] > best_dollars):
                best_dollars = priced["total_dollars"]
                best_cand = c
        classification = classify_a_vs_c(
            oracle_bound_dollars=best_dollars,
            detector_fired_near_move=(best_cand["detector_fired_near_move"] if best_cand else False),
        )
        axis2_rows.append({
            "date": date_iso, "day_cause": day_participation[date_iso]["cause"],
            "n_clean_candidates": len(scan["candidates_to_price"]),
            "oracle_bound_dollars": best_dollars,
            "best_candidate": best_cand, "classification": classification,
        })
    axis2_counts = Counter(row["classification"] for row in axis2_rows)
    log(f"  AXIS 2 classification: {dict(axis2_counts)}")

    out = {
        "generated_at": dt.datetime.now().isoformat(),
        "tool": "backtest/tools/frequency_ceiling_cascade_2026_08_03.py",
        "smoke_mode": smoke,
        "window": {"start": str(all_dates[0]), "end": str(all_dates[-1]), "n_days": len(all_dates)},
        "run_window": {"start": str(start_date), "end": str(end_date)},
        "anchors": {
            "n_raw_entries": len(r.trades),
            "n_qualifying_candidates": len(candidates),
            "n_bear_candidates": n_bear_cand, "n_bull_candidates": n_bull_cand,
            "n_trendline_only_candidates": n_trendline_cand,
            "n_trendline_only_dropped_by_backfill": n_trendline_dropped,
            "status_counts": dict(status_counts),
            "known_scope_limit": "TRENDLINE-only bear candidates ARE covered (backfilled via "
                                  "a direct re-call to detect_trendline_rejection_bearish -- "
                                  "see build_qualifying_candidates/backfill_trendline_levels "
                                  "docstrings; this closes the 89%-of-bear-entries gap the "
                                  "existing LADDER_LEVEL_TIED convention leaves open). Residual "
                                  "gap: any entry via a setup OTHER than RIDE_THE_RIBBON "
                                  "bear/bull (e.g. dormant flag-gated detectors, all default "
                                  "OFF in SAFE_BASE_LIVE) is still out of scope -- disclosed, "
                                  "not silently absorbed.",
            "gate_order_cross_check": {"checked": gate_agreement_checked, "matched": gate_agreement_matched},
        },
        "overlap_matrix_all_layers": overlap_all,
        "overlap_matrix_gate_layer_only": overlap_gate_layer,
        "routing_loss_n": routing_loss_n,
        "sole_blocker_cohorts_priced": priced_cohorts,
        "sole_blocker_bh_fdr_q010": bh_by_cohort,
        "day_participation_counts": dict(day_cause_counts),
        "day_participation": day_participation,
        "axis2_no_trade_day_scan": axis2_rows,
        "axis2_classification_counts": dict(axis2_counts),
        "runtime_seconds": round(time.time() - t_start, 1),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    import json
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    _smoke = "--smoke" in sys.argv
    _smoke_days = 15
    for _arg in sys.argv:
        if _arg.startswith("--smoke-days="):
            _smoke_days = int(_arg.split("=", 1)[1])
    sys.exit(main(smoke=_smoke, smoke_days=_smoke_days))

