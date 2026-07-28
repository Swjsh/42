"""crypto_twin_ladder_sim.py -- the LADDER-VARIANT SIM LANE: a fast falsifier for the
"ribbon lags at extremes" mechanism, run against BTC's 288 5-min prints/day instead of
waiting on SPY's ~78/day RTH cadence.

MECHANISM UNDER TEST (instrument-agnostic EMA math, NOT SPY microstructure, NOT an edge
claim -- same standing doctrine as every other twin module): "at extremes, the EMA ribbon
lags; a level-reaction entry should not have to wait for the SAME-timeframe ribbon to
finish stacking if a HIGHER timeframe already agrees." On SPY 2026-07-27 this cost $571 --
bear_score 9 was blocked by the 5m ribbon filter (still MIXED/lagging) while the 15m HTF
read was already right, and the engine chased the bottom after the ribbon caught up. The
SAME shape exists here: crypto_twin_signal.evaluate() requires the 5m ribbon BULL/BEAR-
stacked >=2 bars before a reclaim/rejection entry (crypto_twin_signal.MIN_STACK_BARS) --
the ribbon-aligned BASELINE this module runs alongside.

TWO LANES, BOTH FULLY SIMULATED (never a real order, never touching the twin's LIVE
ledgers) so the comparison is apples-to-apples sim-vs-sim, exercised on the EXACT SAME
ticks/bars/quotes:

  baseline -- tags crypto_twin_signal.evaluate()'s own verdict (the ribbon-stack-gated
              signal that already runs LIVE) and walks any resulting entry through a SIM
              round trip. This is NOT a duplicate of the LIVE lane's real position -- it
              is an independent, always-on SIM trace of "what would the ribbon-aligned
              signal have done on this exact bar", so it can be directly compared to the
              variant lane on ticks where the LIVE lane never entered).
  variant  -- evaluate_variant() below: the SAME level-reaction trigger (crypto_twin_
              levels.nearest_directional_level + classify_reactions -- REUSED, never
              forked), but the 5m ribbon-stack gate is REPLACED by a 15m HIGHER-TIMEFRAME
              alignment gate (compute_htf_15m_stack: the SAME 5m bars aggregated 3:1, EMA
              13/20/48 -- crypto_twin_signal.RIBBON_FAST/PIVOT/SLOW, reused verbatim, just
              evaluated on triple-width bars). BULL needs the 15m ribbon BULL-stacked,
              BEAR needs it BEAR-stacked; the 5m ribbon is read for logging/comparison
              only and never gates this verdict.

REUSE, never fork (HARD RAILS, same discipline as crypto_twin_core.py / crypto_twin_
scenarios.py):
  * crypto_twin_signal.evaluate / RIBBON_FAST,PIVOT,SLOW -- the baseline lane's verdict
    AND the variant lane's EMA periods, byte-identical.
  * crypto_twin_levels.build_level_set / nearest_directional_level / classify_reactions --
    the SAME level set + reaction classification both lanes trigger against.
  * exit_manager.ExitState / plan_exit_actions -- the IDENTICAL decision core every other
    twin lane runs, seeded from cfg.exit_shape (the twin's OWN live exit shape -- task
    requirement: "exits walked with the SAME exit shape the twin uses").
  * crypto_twin_scenarios.mirror_premium / mirror_price_from_premium / _bear_hilo_premiums
    -- the synthetic put-mirror economics for a bear (side="P") SIM leg (Alpaca crypto is
    long-only; see that module's docstring for why this transform is the ONE genuinely new
    piece of arithmetic in the whole twin). A bull (side="C") SIM leg needs no mirroring --
    premium tracks raw BTC price 1:1, exactly like crypto_twin_core's real bull entries.
  * backtest/futures/fill_sim_broker.gap_aware_stop_fill -- imported verbatim (never
    reimplemented) for gap-aware SIMULATED stop fills, generalized here to BOTH directions
    ("long" for a bull leg, "short" for a bear leg) where crypto_twin_scenarios' own SIM
    bear lane only ever needed "short".
  * crypto_twin_core.fetch_closed_bars / crypto_twin_broker.get_crypto_quote_hilo -- the
    SAME closed-bar SEE stage + the SAME live bid/ask read every other lane uses. Both
    read-only; this module NEVER imports crypto_twin_broker.place_crypto_order /
    market_sell_crypto / close_all_crypto (guard: backtest/tests/test_crypto_twin_ladder_
    sim.py's no-broker-order AST scan).

NEVER BLENDED WITH LIVE (same contract as the SIM bear lane): ladder positions are NEVER
written to exit-state.json / journal.jsonl / decisions.jsonl. They get their own private
namespace-scoped files -- automation/state/crypto-twin/ladder-sim-positions.json (open
positions, keyed by lane) and automation/state/crypto-twin/ladder-sim.jsonl (append-only
event journal, every row tagged "lane": "variant"|"baseline").

FENCES (task requirement, restated so a future reader never has to reconstruct intent from
code alone):
  1. No real orders from this lane, EVER -- SIM fills only, both directions, both lanes.
  2. State stays under automation/state/crypto-twin/ (namespace-isolated, like every other
     twin file -- see crypto_twin_core.py's own _assert_twin_namespace discipline).
  3. FAIL-OPEN: run_ladder_tick() catches per-lane AND catches whole-function exceptions,
     so a bug in this module can never propagate into the real twin tick that calls it
     (see the "TWIN-B1.5-WIRE"-style wiring block in crypto_twin_scenarios.py, wrapped in
     its OWN try/except at the call site too -- belt-and-suspenders, matching how
     seriously that file already treats "a hiccup here must never mask a successful tick").
  4. MECHANISM EVIDENCE ONLY. This lane's P&L (either side, either lane) answers "does the
     15m-HTF-instead-of-5m-ribbon gate reach more/better level reactions on live noise" --
     it is NEVER SPY edge evidence and NEVER enters any edge scorecard, per every other
     twin module's own standing doctrine (crypto_twin_core.py's module docstring).

P&L DISCIPLINE (same standard as crypto_twin_pnl.py -- wired realized fields, never
silent): every SELL_PARTIAL/SELL_ALL leg is journaled with its own realized leg_pct
(premium-space, side-aware), and every position close additionally reports a qty-weighted
round_trip_pct across all legs of that lifecycle (tp1 leg + runner leg, or a single leg if
the position never reached TP1) -- see _weighted_round_trip_pct.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
for _p in ("automation/state/fleet", "backtest/lib", "backtest"):
    _full = REPO / _p
    if str(_full) not in sys.path:
        sys.path.insert(0, str(_full))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.levels import LevelEvent  # noqa: E402
from crypto.lib.ribbon import compute_ribbon  # noqa: E402
from et_clock import et_now  # noqa: E402
from futures.fill_sim_broker import gap_aware_stop_fill  # noqa: E402

import crypto_twin_broker as broker  # noqa: E402  -- READ-ONLY: get_crypto_quote_hilo only, see module docstring
import crypto_twin_core as ctc  # noqa: E402
import crypto_twin_levels as tl  # noqa: E402
import crypto_twin_signal as sig  # noqa: E402
import exit_manager as em  # noqa: E402
from crypto_twin_scenarios import (  # noqa: E402  -- REUSE, never fork: the synthetic put-mirror math
    mirror_premium, mirror_price_from_premium, _bear_hilo_premiums,
)

LADDER_JOURNAL_FILENAME = "ladder-sim.jsonl"
LADDER_POSITIONS_FILENAME = "ladder-sim-positions.json"

LANES: tuple[str, ...] = ("variant", "baseline")

# 15m HTF ribbon -- SAME periods as the 5m ribbon (crypto_twin_signal.RIBBON_FAST/PIVOT/
# SLOW), reused verbatim, just evaluated on 3:1-aggregated bars (task requirement: "EMA
# 13/20/48"). A local alias, not a re-declaration, so the two can never silently drift.
RIBBON_FAST_15M, RIBBON_PIVOT_15M, RIBBON_SLOW_15M = (
    sig.RIBBON_FAST, sig.RIBBON_PIVOT, sig.RIBBON_SLOW)
AGG_FACTOR = 3  # 5m -> 15m


# ============================================================================
# 15m HTF aggregation (mechanism, not a candidate edge -- see module docstring)
# ============================================================================
def aggregate_bars(bars: Sequence[Bar], factor: int = AGG_FACTOR) -> list[Bar]:
    """Aggregate `factor` consecutive CLOSED bars into one higher-timeframe bar. Trims any
    leftover from the FRONT (oldest) so every emitted group is fully complete -- the newest
    emitted bar is always built from `factor` genuinely closed input bars (C6 sibling: never
    synthesizes an HTF bar from a partial/in-progress trailing group). `bars` must already
    be closed-bars-only (caller's responsibility, same contract as every other function in
    this twin that takes a bar sequence)."""
    n = len(bars) - (len(bars) % factor)
    if n <= 0:
        return []
    trimmed = bars[-n:]
    out: list[Bar] = []
    for i in range(0, n, factor):
        group = trimmed[i:i + factor]
        out.append(Bar(open_time=group[0].open_time, open=group[0].open,
                       high=max(b.high for b in group), low=min(b.low for b in group),
                       close=group[-1].close, volume=sum(b.volume for b in group),
                       granularity_seconds=group[0].granularity_seconds * factor,
                       source=group[0].source))
    return out


def compute_htf_15m_stack(bars_5m: Sequence[Bar]) -> Optional[str]:
    """The 15m ribbon status ("BULL"/"BEAR"/"MIXED") off the SAME 5m bars the twin's own
    SEE stage already fetched, aggregated 3:1. None when there is not enough history for
    the slow EMA's warmup on the AGGREGATED series (mirrors crypto_twin_signal.evaluate's
    own `len(bars) < max(RIBBON_SLOW, min_stack_bars) + 1` warmup guard, applied to the
    aggregated 15m series instead)."""
    agg = aggregate_bars(bars_5m, AGG_FACTOR)
    if len(agg) < RIBBON_SLOW_15M + 1:
        return None
    ribbons = compute_ribbon(agg, fast_len=RIBBON_FAST_15M, pivot_len=RIBBON_PIVOT_15M,
                             slow_len=RIBBON_SLOW_15M)
    last = ribbons[-1]
    if last.fast != last.fast:  # NaN check -- warmup guard above should prevent this, defensive
        return None
    return last.status


# ============================================================================
# The variant verdict + evaluator (crypto_twin_signal.TwinVerdict's shape, plus htf_15m)
# ============================================================================
@dataclass(frozen=True, slots=True)
class VariantVerdict:
    verdict: str                 # "ENTER_BULL" | "ENTER_BEAR" | "HOLD"
    side: Optional[str]          # "bull" | "bear" | None
    setup: Optional[str]
    triggers: list[str] = field(default_factory=list)
    reason: str = ""
    trigger_level_exact: Optional[float] = None
    ribbon_stack: str = "MIXED"     # the 5m ribbon -- INFORMATIONAL ONLY, never gates this verdict
    htf_15m: Optional[str] = None   # the 15m ribbon -- THE gate


def evaluate_variant(bars: Sequence[Bar], levels: tl.TwinLevelSet) -> VariantVerdict:
    """The variant lane's SEE->DECIDE verdict. Identical level-reaction trigger to
    crypto_twin_signal.evaluate (same nearest_directional_level + classify_reactions call),
    but the 5m ribbon-stack requirement is REPLACED by 15m HTF alignment (see module
    docstring's "MECHANISM UNDER TEST"). Deliberately reachable when the 5m ribbon is
    MIXED (or even opposed) -- that is the exact shape a lagging same-timeframe ribbon
    produces at a genuine extreme, which is what this lane exists to test."""
    if len(bars) < max(RIBBON_SLOW_15M, 1) + 1:
        return VariantVerdict("HOLD", None, None, reason="insufficient bar history for warmup")

    trig_bar = bars[-1]
    spot = trig_bar.close
    ribbons_5m = compute_ribbon(bars, fast_len=sig.RIBBON_FAST, pivot_len=sig.RIBBON_PIVOT,
                                slow_len=sig.RIBBON_SLOW)
    rib_5m = ribbons_5m[-1]
    ribbon_stack_5m = rib_5m.status if rib_5m.fast == rib_5m.fast else "MIXED"  # NaN -> MIXED, informational
    htf_15m = compute_htf_15m_stack(bars)

    if htf_15m is None:
        return VariantVerdict("HOLD", None, None, ribbon_stack=ribbon_stack_5m, htf_15m=None,
                              reason="insufficient 15m bar history for HTF warmup")

    triggers: list[str] = []
    if htf_15m == "BULL":
        lvl = tl.nearest_directional_level(levels.all_levels, spot, side="bull")
        if lvl is not None:
            reaction = tl.classify_reactions(trig_bar, [lvl])[lvl.price]
            if reaction in (LevelEvent.RECLAIM, LevelEvent.HOLD):
                triggers.append("htf_15m_bull")
                triggers.append(f"level_{reaction.value}_{lvl.label}")
                return VariantVerdict(
                    "ENTER_BULL", "bull", "LADDER_HTF_LEVEL_RECLAIM", triggers,
                    reason=(f"15m HTF BULL + {reaction.value} of {lvl.label} @ {lvl.price} "
                           f"(5m ribbon={ribbon_stack_5m})"),
                    trigger_level_exact=lvl.price, ribbon_stack=ribbon_stack_5m, htf_15m=htf_15m)
    elif htf_15m == "BEAR":
        lvl = tl.nearest_directional_level(levels.all_levels, spot, side="bear")
        if lvl is not None:
            reaction = tl.classify_reactions(trig_bar, [lvl])[lvl.price]
            if reaction in (LevelEvent.REJECT, LevelEvent.HOLD):
                triggers.append("htf_15m_bear")
                triggers.append(f"level_{reaction.value}_{lvl.label}")
                return VariantVerdict(
                    "ENTER_BEAR", "bear", "LADDER_HTF_LEVEL_REJECT", triggers,
                    reason=(f"15m HTF BEAR + {reaction.value} of {lvl.label} @ {lvl.price} "
                           f"(5m ribbon={ribbon_stack_5m})"),
                    trigger_level_exact=lvl.price, ribbon_stack=ribbon_stack_5m, htf_15m=htf_15m)

    return VariantVerdict(
        "HOLD", None, None, ribbon_stack=ribbon_stack_5m, htf_15m=htf_15m,
        reason=("no level in range for the current 15m HTF direction" if htf_15m != "MIXED"
               else "15m HTF MIXED"))


# ============================================================================
# SIM fill pricing -- side-aware generalization of crypto_twin_scenarios'
# _bear_sim_fill_raw_price (that function only ever needed "short"; a bull leg needs
# "long" via the exact same gap_aware_stop_fill primitive, never a second implementation).
# ============================================================================
def _raw_from_premium(side_code: str, entry_premium: float, premium: float) -> float:
    """premium -> raw BTC price. Bull (side_code=='C'): identity (premium IS raw price,
    exactly like crypto_twin_core's real bull entries). Bear (side_code=='P'): the
    synthetic put-mirror inverse (crypto_twin_scenarios.mirror_price_from_premium)."""
    return mirror_price_from_premium(entry_premium, premium) if side_code == "P" else premium


def _premium_from_raw(side_code: str, entry_premium: float, raw_price: float) -> float:
    """Inverse of _raw_from_premium -- raw BTC price -> premium space."""
    return mirror_premium(entry_premium, raw_price) if side_code == "P" else raw_price


def _sim_fill_raw_price(side_code: str, action: em.ExitAction, *, entry_premium: float,
                        pre_state: em.ExitState, post_state: em.ExitState,
                        price: float, bar_open: Optional[float]) -> float:
    """Simulated fill price, in RAW BTC terms, for one exit_manager action -- side-aware
    generalization of crypto_twin_scenarios._bear_sim_fill_raw_price (informational/
    journal-only, mirrors that function's own contract verbatim; see its docstring)."""
    direction = "short" if side_code == "P" else "long"
    stage = action.stage
    try:
        if stage == "structure_stop":
            stop_raw = pre_state.trigger_level if pre_state.trigger_level is not None else price
            return round(gap_aware_stop_fill(direction, stop_raw, price, bar_open), 2)
        if stage in ("premium_stop", "profit_lock_floor"):
            stop_premium = (post_state.runner_stop_premium if post_state.runner_stop_premium is not None
                            else pre_state.runner_stop_premium)
            stop_raw = (_raw_from_premium(side_code, entry_premium, stop_premium)
                       if stop_premium is not None else price)
            return round(gap_aware_stop_fill(direction, stop_raw, price, bar_open), 2)
        if stage == "tp1":
            level_premium = entry_premium * (1.0 + pre_state.tp1_premium_pct)
            return round(_raw_from_premium(side_code, entry_premium, level_premium), 2)
        if stage == "runner_target":
            level_premium = entry_premium * (1.0 + pre_state.runner_target_pct)
            return round(_raw_from_premium(side_code, entry_premium, level_premium), 2)
        if stage in ("trail", "be_stop"):
            stop_premium = (post_state.runner_stop_premium if post_state.runner_stop_premium is not None
                            else pre_state.runner_stop_premium)
            stop_raw = (_raw_from_premium(side_code, entry_premium, stop_premium)
                       if stop_premium is not None else price)
            return round(gap_aware_stop_fill(direction, stop_raw, price, bar_open), 2)
    except (TypeError, ValueError):
        pass
    return round(price, 2)  # ribbon_flip / time_stop / any unmodeled stage -- market exit


def _leg_pct(entry_premium: float, exit_premium: float) -> Optional[float]:
    if not entry_premium:
        return None
    return round((exit_premium - entry_premium) / entry_premium * 100.0, 6)


def _weighted_round_trip_pct(legs: list[dict], total_qty: int) -> Optional[float]:
    """Qty-weighted realized pct across every leg of one position's lifecycle (tp1 partial
    + runner, or a single leg if the position never reached TP1) -- the honest "per round
    trip" number the task asks for, not just the final leg's pct in isolation."""
    if not legs or not total_qty:
        return None
    weighted = sum(float(leg["qty"]) * float(leg["pct"]) for leg in legs if leg.get("pct") is not None)
    return round(weighted / total_qty, 6)


# ============================================================================
# ladder-sim-positions.json (private -- NEVER exit-state.json)
# ============================================================================
def _load_positions(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_positions(path: Path, positions: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(positions, indent=2), encoding="utf-8")


# ============================================================================
# ladder-sim.jsonl (private -- NEVER journal.jsonl)
# ============================================================================
def _journal_ladder(path: Path, event: str, **fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts_utc": datetime.now(timezone.utc).isoformat(), "event": event, "twin": True,
          "mechanism_only": True, **fields}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


# ============================================================================
# entry + management (mirrors crypto_twin_scenarios' SIM bear lane shape, generalized to
# both lanes x both sides -- NEVER calls crypto_twin_broker.place_crypto_order /
# market_sell_crypto / close_all_crypto; get_crypto_quote_hilo is the only broker call,
# read-only -- see module docstring + the no-broker-order guard test)
# ============================================================================
def _place_ladder_entry(cfg: ctc.TwinConfig, *, lane: str, verdict, now: datetime,
                        price: float, journal_path: Path) -> dict:
    side_code = "C" if verdict.side == "bull" else "P"
    shape = dict(cfg.exit_shape)  # the twin's OWN live exit shape -- task requirement
    trigger_level = verdict.trigger_level_exact
    st = em.ExitState.from_entry(symbol=cfg.symbol, side=side_code, entry_premium=price,
                                 qty=cfg.units_per_entry, exit_shape=shape,
                                 strategy=f"ladder_sim_{lane}", trigger_level=trigger_level,
                                 structure_stop_enabled=True)
    position = {"exit_state": st.to_dict(), "entered_at_utc": now.isoformat(), "lane": lane,
               "side": verdict.side, "setup": verdict.setup, "entry_price_raw": price,
               "trigger_level": trigger_level, "ribbon_stack": verdict.ribbon_stack,
               "htf_15m": getattr(verdict, "htf_15m", None), "legs": []}
    _journal_ladder(journal_path, "LADDER_ENTERED", lane=lane, side=verdict.side,
                    setup=verdict.setup, entry_price_raw=price, entry_premium=price,
                    level=trigger_level, ribbon_stack=verdict.ribbon_stack,
                    htf_15m=getattr(verdict, "htf_15m", None), triggers=verdict.triggers,
                    reason=verdict.reason, units=cfg.units_per_entry)
    return position


def _manage_ladder_position(cfg: ctc.TwinConfig, *, lane: str, position: dict, now: datetime,
                            price: float, bar_open: Optional[float], ribbon_stack: Optional[str],
                            journal_path: Path) -> tuple[list, str, Optional[dict]]:
    """Returns (exit_pass, action, new_position_or_None)."""
    st = em.ExitState.from_dict(position["exit_state"])
    side = position["side"]  # "bull" | "bear"
    side_code = "P" if side == "bear" else "C"
    entered_at = datetime.fromisoformat(position["entered_at_utc"])
    elapsed_h = (now - entered_at).total_seconds() / 3600.0

    hilo = broker.get_crypto_quote_hilo(cfg.symbol)
    if hilo is None:
        return [{"lane": lane, "action": "HOLD", "reason": "no_quote"}], "LADDER_HOLD_NO_QUOTE", position

    ask, bid = hilo
    if side == "bear":
        best, worst = _bear_hilo_premiums(st.entry_premium, ask, bid)
    else:
        best, worst = ask, bid

    if elapsed_h >= cfg.max_hold_hours:
        remaining_qty = st.runner_qty if st.tp1_filled else st.total_qty
        exit_premium = worst  # forced flatten -- conservative market-sell-at-worst convention
        leg_pct = _leg_pct(st.entry_premium, exit_premium)
        legs = list(position.get("legs", [])) + [{"qty": remaining_qty, "pct": leg_pct, "stage": "max_hold"}]
        round_trip_pct = _weighted_round_trip_pct(legs, st.total_qty)
        _journal_ladder(journal_path, "LADDER_CLOSED", lane=lane, side=side,
                        reason="max_hold_flatten", elapsed_hours=round(elapsed_h, 2),
                        sim_fill_premium=exit_premium, leg_pct=leg_pct,
                        round_trip_pct=round_trip_pct)
        return ([{"lane": lane, "action": "MAX_HOLD_FLATTEN", "elapsed_hours": round(elapsed_h, 2)}],
               "LADDER_MAX_HOLD_FLATTEN", None)

    now_et_time = et_now(now_utc=now).time()
    # side="P" flips on BULL ribbon -- mirrors crypto_twin_core._make_ribbon_flip_fn /
    # crypto_twin_scenarios._manage_sim_bear_position's own identical rule.
    flip = bool(ribbon_stack) and (ribbon_stack == ("BULL" if side == "bear" else "BEAR"))
    dec = em.plan_exit_actions(st, best_premium=best, worst_premium=worst,
                               open_qty=cfg.units_per_entry, now_et=now_et_time,
                               ribbon_flip_back=flip, last_closed_5m_close=price)

    executed = []
    new_legs = list(position.get("legs", []))
    for a in dec.actions:
        if a.kind in ("SELL_PARTIAL", "SELL_ALL"):
            fill_raw = _sim_fill_raw_price(side_code, a, entry_premium=st.entry_premium,
                                           pre_state=st, post_state=dec.state, price=price,
                                           bar_open=bar_open)
            fill_premium = _premium_from_raw(side_code, st.entry_premium, fill_raw)
            leg_pct = _leg_pct(st.entry_premium, fill_premium)
            new_legs.append({"qty": a.qty, "pct": leg_pct, "stage": a.stage})
            executed.append({"kind": a.kind, "units": a.qty, "stage": a.stage, "reason": a.reason,
                             "sim_fill_raw_price": fill_raw, "sim_fill_premium": fill_premium,
                             "leg_pct": leg_pct})
            event = "LADDER_MANAGED" if a.kind == "SELL_PARTIAL" else "LADDER_CLOSED"
            extra = {}
            if a.kind == "SELL_ALL":
                extra["round_trip_pct"] = _weighted_round_trip_pct(new_legs, st.total_qty)
            _journal_ladder(journal_path, event, lane=lane, side=side, kind=a.kind, units=a.qty,
                            stage=a.stage, reason=a.reason, sim_fill_raw_price=fill_raw,
                            sim_fill_premium=fill_premium, leg_pct=leg_pct, **extra)
        elif a.kind == "RATCHET_STOP":
            executed.append({"kind": "RATCHET_STOP", "stage": a.stage,
                             "new_stop_premium": a.new_stop_premium, "reason": a.reason})

    if dec.closes_position:
        return [{"lane": lane, "actions": executed}], "LADDER_CLOSED", None

    new_position = {**position, "exit_state": dec.state.to_dict(), "legs": new_legs}
    return [{"lane": lane, "actions": executed}], "LADDER_MANAGED", new_position


# ============================================================================
# the dual-lane tick (this module's own public entrypoint)
# ============================================================================
def run_ladder_tick(cfg: ctc.TwinConfig = ctc.TwinConfig(), *, now_utc: Optional[datetime] = None,
                    raw_bars: Optional[list[dict]] = None,
                    journal_path: Optional[Path] = None,
                    positions_path: Optional[Path] = None) -> dict:
    """ONE tick of the ladder-variant sim: fetch the SAME closed bars the twin's own SEE
    stage would, evaluate BOTH lanes (baseline = crypto_twin_signal.evaluate, byte-
    identical to the LIVE signal; variant = evaluate_variant above), and independently
    manage/place a SIM position per lane. NEVER touches a real broker order.

    FAIL-OPEN at two layers (task requirement): each lane's own processing is wrapped so
    one lane's bug can never affect the other, AND the whole function is wrapped so a bug
    anywhere in this module (bad state file, malformed position record, etc.) can never
    propagate to the caller -- see crypto_twin_scenarios.py's wiring, which wraps this
    call in its OWN try/except too (defense in depth, matching how seriously that file
    already treats "a hiccup here must never mask a successful [LIVE] tick").
    """
    now = now_utc or datetime.now(timezone.utc)
    journal_path = journal_path or (cfg.state_dir / LADDER_JOURNAL_FILENAME)
    positions_path = positions_path or (cfg.state_dir / LADDER_POSITIONS_FILENAME)

    lane_results: dict[str, dict] = {}
    try:
        bars, bar_meta = ctc.fetch_closed_bars(cfg, now_utc=now, raw_bars=raw_bars)
        if not bars or bar_meta["verdict"] != "ok":
            return {"action": "HOLD_BAD_BARS", "bar_meta": bar_meta, "price": None,
                   "lanes": {}, "error": None}

        levels = tl.build_level_set(bars, now)
        price = bars[-1].close
        bar_open = bars[-1].open

        # baseline is computed HERE (not inside the per-lane try below) because it is
        # BOTH lanes' shared ribbon_flip input -- it is also the exact call the LIVE
        # signal itself makes (sig.evaluate, no ladder-sim logic of its own), so this is
        # not "the variant lane's own risk surface" the fail-open contract targets.
        # evaluate_variant (the ladder-sim module's own new gating logic) is deliberately
        # called INSIDE the variant lane's try block below, so a bug there can never
        # affect the baseline lane or propagate to the caller (see module docstring).
        baseline_verdict = sig.evaluate(bars, levels)   # byte-identical to the LIVE signal

        positions = _load_positions(positions_path)
        for lane in LANES:
            try:
                verdict = baseline_verdict if lane == "baseline" else evaluate_variant(bars, levels)
                pos = positions.get(lane)
                if pos is not None:
                    exit_pass, action, new_pos = _manage_ladder_position(
                        cfg, lane=lane, position=pos, now=now, price=price, bar_open=bar_open,
                        ribbon_stack=baseline_verdict.ribbon_stack, journal_path=journal_path)
                    if new_pos is None:
                        positions.pop(lane, None)
                    else:
                        positions[lane] = new_pos
                elif verdict.verdict.startswith("ENTER") and verdict.side is not None:
                    new_pos = _place_ladder_entry(cfg, lane=lane, verdict=verdict, now=now,
                                                  price=price, journal_path=journal_path)
                    positions[lane] = new_pos
                    action, exit_pass = "LADDER_ENTERED", []
                else:
                    action, exit_pass = "HOLD", []
                lane_results[lane] = {"action": action, "exit_pass": exit_pass,
                                      "verdict": verdict.verdict, "side": verdict.side,
                                      "reason": verdict.reason}
            except Exception as e:  # noqa: BLE001 -- one lane's bug must never affect the other/the caller
                lane_results[lane] = {"action": "LANE_ERROR", "error": f"{type(e).__name__}: {e}"}

        _save_positions(positions_path, positions)
        return {"action": "OK", "price": price, "lanes": lane_results, "error": None}
    except Exception as e:  # noqa: BLE001 -- fail-open: this whole module must never break the caller's tick
        return {"action": "TICK_ERROR", "lanes": lane_results, "error": f"{type(e).__name__}: {e}"}


# ============================================================================
# health -- summarize() + report() (crypto_twin_pnl.py's own shape, reused deliberately)
# ============================================================================
def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


def summarize_lane(closed_rows: list[dict]) -> dict:
    pcts = [r["round_trip_pct"] for r in closed_rows if r.get("round_trip_pct") is not None]
    if not pcts:
        return {"n": 0, "wins": 0, "win_rate": None, "total_pct": 0.0, "avg_pct": None}
    wins = sum(1 for p in pcts if p > 0)
    return {"n": len(pcts), "wins": wins, "win_rate": round(100.0 * wins / len(pcts), 1),
           "total_pct": round(sum(pcts), 4), "avg_pct": round(sum(pcts) / len(pcts), 5)}


def summarize(journal_path: Optional[Path] = None) -> dict:
    rows = _read_jsonl(journal_path or (ctc.TWIN_DIR / LADDER_JOURNAL_FILENAME))
    closed = [r for r in rows if r.get("event") == "LADDER_CLOSED"]
    return {lane: summarize_lane([r for r in closed if r.get("lane") == lane]) for lane in LANES}


def _line(lane: str, s: dict) -> str:
    if s["n"] == 0:
        return f"- **{lane}**: 0 round trips yet"
    return (f"- **{lane}**: {s['n']} round trips | {s['win_rate']}% WR | "
           f"total {s['total_pct']:+.3f}% | avg {s['avg_pct']:+.4f}%/trip")


def report(journal_path: Optional[Path] = None) -> str:
    s = summarize(journal_path)
    lines = ["# Crypto twin -- LADDER-VARIANT sim (15m-HTF-gate vs ribbon-stack-gate)", "",
            "MECHANISM EVIDENCE ONLY -- BTC ribbon-lag validation, never SPY edge (see "
            "crypto_twin_ladder_sim.py's module docstring). Both lanes are fully SIMULATED, "
            "never a real order.", ""]
    for lane in LANES:
        lines.append(_line(lane, s[lane]))
    if s["variant"]["n"] and s["baseline"]["n"]:
        lines.append("")
        lines.append(f"- delta (variant - baseline) avg%/trip: "
                     f"{s['variant']['avg_pct'] - s['baseline']['avg_pct']:+.5f}")
    return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================
def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Crypto Twin ladder-variant SIM lane -- 15m-HTF-gate vs ribbon-stack-gate, "
                   "both lanes fully simulated, never a real order")
    parser.add_argument("--tick", action="store_true",
                        help="run one manual ladder-sim tick against live BTC data (SIM only)")
    parser.add_argument("--json", action="store_true", help="machine-readable summary")
    parser.add_argument("--report", action="store_true", help="print the per-lane summary report")
    args = parser.parse_args(argv)

    if args.tick:
        result = run_ladder_tick()
        print(json.dumps(result, indent=2, default=str))
        return 0
    if args.json:
        print(json.dumps(summarize(), indent=2))
        return 0
    print(report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
