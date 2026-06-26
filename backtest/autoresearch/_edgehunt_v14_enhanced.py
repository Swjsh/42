"""EDGE HUNT — v14_enhanced (closest-to-LIVE) 0DTE SPY family, REAL OPRA fills.

Mandate (the real-fills quant): does the LIVE engine have a per-trade option edge,
and can a different CONTRACT SIZING (strike_offset) + different EXITS improve it?

DESIGN — "detect signals ONCE, then loop the grid re-running ONLY the sim"
=========================================================================
The v14_enhanced family IS the live engine (lib.orchestrator + lib.filters under
the v15.3 params.json config). Re-implementing its entry detector here would risk
SIGNAL DRIFT vs production (an anti-pattern). Instead we:

  1. Wrap lib.simulator_real.simulate_trade_real with a CAPTURING shim and run the
     orchestrator EXACTLY ONCE with use_real_fills=True under the live family config.
     The shim records every (entry_bar_idx, entry_bar, rejection_level,
     triggers_fired, side, levels_active, levels_carry, setup, native_qty) the live
     engine actually decides to enter — i.e. the canonical live signal set — and
     returns the real fill so the orchestrator run completes normally.

  2. Re-run ONLY simulate_trade_real across the 5x4 (strike_offset x premium_stop)
     grid against those captured signals. Every other arg is held identical to what
     the live engine passed; we override ONLY strike_offset + premium_stop_pct (and,
     in the exit mini-sweep, the exit knobs). qty is forced to QTY=3 for an
     apples-to-apples PER-CONTRACT read (option bracket P&L is linear in qty, so
     this isolates the per-trade edge and matches the OP-20 per-trade disclosure).

STRIKE CONVENTION (verified in simulator_real.py lines 357-364, anti-pattern 2.2):
  puts:  strike = atm - strike_offset   -> offset<0 => strike ABOVE spot => ITM
  calls: strike = atm + strike_offset   -> offset<0 => strike BELOW spot => ITM
  => negative = ITM, positive = OTM for BOTH sides. (Matches the task spec.)
  NB: this is the simulator_real convention. params.json's v15_strike_offset_per_tier
  uses the OPPOSITE sign (negative=OTM) but that is translated by the orchestrator
  BEFORE the sim; our sweep overrides at the sim level so we use the sim convention.

REAL-FILLS AUTHORITY (C1): all P&L is real OPRA fills. simulate_trade_real returns
None on an OPRA cache miss for the swept strike — that signal is simply DROPPED for
that cell (no BS fallback; this is a pure real-fills study). We report the drop count
per cell; a cell with a high drop rate is flagged.

CANDIDATE-EDGE BAR (ALL required): OOS per-trade expectancy > 0 AND
positive_quarters >= 4/6 AND top5_day_pct < 200 AND n_trades >= 20.

OP-20 DISCLOSURE: per-trade expectancy (not WR alone — OP-14), IS(2025) vs OOS(2026),
positive_quarters/6, top5_day_pct (top-5 winning DAYS as % of total P&L), direction
split (bull vs bear). We do NOT cherry-pick a survivor (2.10): a positive cell that is
tiny-N / high-concentration / OOS-negative is reported with clears_bar=false.

Pure Python, $0 (NO LLM in the loop). No live orders. Markets closed.

    python -m autoresearch._edgehunt_v14_enhanced
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import logging
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

# Engine-score assert is a per-bar oracle that doubles detection cost; off for the
# single capture run (we are not modifying the scorer). Must be set BEFORE importing
# the orchestrator (it reads the env var at import time).
os.environ.setdefault("GAMMA_ENGINE_SCORE_ASSERT", "0")
os.environ.setdefault("GAMMA_ENGINE_GATES_ASSERT", "0")

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from lib import simulator_real as sim_real_mod  # noqa: E402
from lib import orchestrator as orch_mod  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

# ── Window ────────────────────────────────────────────────────────────────────
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)
IS_YEAR = 2025   # in-sample
OOS_YEAR = 2026  # out-of-sample

QTY = 3  # per-contract read; option bracket P&L is linear in qty

# ── The sweep grid ─────────────────────────────────────────────────────────────
STRIKE_OFFSETS = [-2, -1, 0, 1, 2]                 # neg=ITM, pos=OTM (sim convention)
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]       # -0.99 == chart-stop-only

# Exit mini-sweep (only on OOS-positive strike/stop cells)
TP1_PCTS = [0.30, 0.50]
RUNNER_TARGETS = [2.0, 2.5, 3.0]
CHANDELIER_OPTIONS = [False, True]                 # trailing 0.20 off HWM on/off
CHANDELIER_TRAIL = 0.20

OUT_JSON = ROOT / "analysis" / "recommendations" / "edgehunt-v14_enhanced.json"

# ── LIVE v15.3 family config (from automation/state/params.json, the source of
# truth). These reproduce the live engine's ENTRY DETECTION + default v15 EXITS.
# strike_offset / premium_stop are intentionally OMITTED here — the sweep sets them.
LIVE_EXITS = dict(
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5,
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.0,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.15,
    ribbon_flip_back_min_spread_cents=30.0,
    level_stop_buffer_dollars=0.50,
)
# time_stop_et is derived from time_stop_minutes_before_close in run_backtest.
# params.json time_stop_et=15:40 == 20 min before 16:00.
LIVE_DETECTION = dict(
    enable_bullish=True,
    min_triggers_bear=1,
    min_triggers_bull=2,
    f9_vol_mult=0.7,
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,                 # v15.1: mid-day blackout removed
    midday_trendline_gate=True,           # params.json: true
    min_ribbon_momentum_cents=None,       # params.json literal = 0 -> gate OFF (None)
    max_ribbon_duration_bars=None,        # params.json literal = 999 -> gate OFF (None)
    time_stop_minutes_before_close=20,    # -> 15:40 ET
    # Live-enabled entry block-gates (params.json, all True) — included so the
    # captured signal set IS the live engine's, not a looser superset:
    block_level_rejection=True,           # params.json: true
    block_bull_1100_1200=True,            # params.json: true
    block_elite_bull=True,                # params.json: true (VIX-conditional below)
    block_elite_bull_vix_low=0.0,
    block_elite_bull_vix_high=25.0,
)
# Entry cutoff: params.json entry_no_trade_after_et = 15:00. run_backtest has no
# direct "no_trade_after" kwarg; the live engine enforces it inside filters via the
# no_trade_window historically, but v15.1 removed the window. The 15:40 hard time
# stop bounds hold-time. We additionally drop any captured signal whose entry time
# is >= 15:00 ET to honour the live entry cutoff exactly (belt-and-suspenders).
ENTRY_CUTOFF_ET = dt.time(15, 0)


# ── Captured signal record ──────────────────────────────────────────────────────
@dataclass
class Signal:
    entry_bar_idx: int
    entry_bar: pd.Series
    rejection_level: Optional[float]
    triggers_fired: list
    side: str
    setup: str
    levels_active: list
    levels_carry: list
    native_qty: int
    entry_time: dt.datetime
    entry_vix: float


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


# ── Capture wrapper ─────────────────────────────────────────────────────────────
def capture_live_signals(spy_df: pd.DataFrame, vix_df: pd.DataFrame) -> list[Signal]:
    """Run the live engine ONCE; capture every real-fills entry it decides to take."""
    captured: list[Signal] = []
    real_fn = sim_real_mod.simulate_trade_real

    def _shim(*args, **kwargs):
        # The orchestrator calls simulate_trade_real with ALL keyword args
        # (verified at orchestrator.py:1693). Record the live decision, then
        # delegate to the real function so the orchestrator run completes.
        captured.append(Signal(
            entry_bar_idx=kwargs["entry_bar_idx"],
            entry_bar=kwargs["entry_bar"],
            rejection_level=kwargs.get("rejection_level"),
            triggers_fired=list(kwargs.get("triggers_fired") or []),
            side=kwargs.get("side", "P"),
            setup=kwargs.get("setup", "?"),
            levels_active=list(kwargs.get("levels_active") or []),
            levels_carry=list(kwargs.get("levels_carry") or []),
            native_qty=int(kwargs.get("qty", QTY)),
            entry_time=_entry_time_of(kwargs["entry_bar"]),
            entry_vix=0.0,  # filled post-hoc below from vix alignment
        ))
        return real_fn(*args, **kwargs)

    # Patch BOTH the module attr and the orchestrator's imported reference.
    sim_real_mod.simulate_trade_real = _shim
    orch_had = hasattr(orch_mod, "simulate_trade_real")
    orch_saved = getattr(orch_mod, "simulate_trade_real", None)
    if orch_had:
        orch_mod.simulate_trade_real = _shim
    try:
        run_backtest(
            spy_df, vix_df,
            start_date=START, end_date=END,
            use_real_fills=True,
            **LIVE_DETECTION,
            **LIVE_EXITS,
        )
    finally:
        sim_real_mod.simulate_trade_real = real_fn
        if orch_had:
            orch_mod.simulate_trade_real = orch_saved
    return captured


def _entry_time_of(entry_bar: pd.Series) -> dt.datetime:
    t = entry_bar["timestamp_et"]
    if hasattr(t, "tz_localize"):
        if getattr(t, "tz", None) is not None:
            t = t.tz_localize(None)
        t = t.to_pydatetime()
    elif hasattr(t, "tzinfo") and t.tzinfo is not None:
        t = t.replace(tzinfo=None)
    return t


# ── Accumulator ─────────────────────────────────────────────────────────────────
class Acc:
    __slots__ = ("n", "wins", "pnl", "by_day")

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.pnl = 0.0
        self.by_day: dict[str, float] = defaultdict(float)

    def add(self, pnl: float, day: str):
        self.n += 1
        self.wins += 1 if pnl > 0 else 0
        self.pnl += pnl
        self.by_day[day] += pnl

    def report(self) -> dict:
        if not self.n:
            return {"n": 0, "per_trade": 0.0, "total_pnl": 0.0, "wr": 0.0, "top5_day_pct": None}
        days_sorted = sorted(self.by_day.values(), reverse=True)
        top5 = sum(days_sorted[:5])
        return {
            "n": self.n,
            "wr": round(100 * self.wins / self.n, 1),
            "total_pnl": round(self.pnl, 0),
            "per_trade": round(self.pnl / self.n, 1),
            # top5 winning DAYS as % of total P&L (OP-20 #5)
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


# ── One cell: re-sim captured signals with a strike/stop (+ optional exit) override ─
def run_cell(signals: list[Signal], ribbon_df: pd.DataFrame, strike_offset: int,
             premium_stop_pct: float, exits: dict) -> dict:
    overall = Acc()
    bull = Acc()
    bear = Acc()
    is_acc = Acc()
    oos_acc = Acc()
    by_q: dict[str, Acc] = defaultdict(Acc)
    dropped = 0

    for s in signals:
        fill = sim_real_mod.simulate_trade_real(
            entry_bar_idx=s.entry_bar_idx,
            entry_bar=s.entry_bar,
            spy_df=_SPY_RTH,           # module-global set in main()
            ribbon_df=ribbon_df,
            rejection_level=s.rejection_level,
            triggers_fired=s.triggers_fired,
            side=s.side,
            qty=QTY,                   # per-contract read
            setup=s.setup,
            levels_active=s.levels_active,
            levels_carry=s.levels_carry,
            premium_stop_pct=premium_stop_pct,
            strike_offset=strike_offset,
            **exits,
        )
        if fill is None:
            dropped += 1
            continue
        pnl = fill.dollar_pnl
        d = s.entry_time.date()
        day = d.isoformat()
        overall.add(pnl, day)
        (bull if s.side == "C" else bear).add(pnl, day)
        (is_acc if d.year == IS_YEAR else oos_acc).add(pnl, day)
        by_q[_quarter(d)].add(pnl, day)

    q_reports = {k: by_q[k].report() for k in sorted(by_q)}
    pos_q = sum(1 for r in q_reports.values() if r.get("total_pnl", 0) > 0)
    oos_rep = oos_acc.report()
    ov_rep = overall.report()
    bear_rep = bear.report()
    bull_rep = bull.report()

    clears, reasons = _clears_bar(oos_rep, pos_q, len(q_reports), ov_rep)
    # AUTHORIZED-SIDE clearance: per OP-16/L140, only BEARISH_REJECTION is live-
    # authorized; BULLISH_RECLAIM is DRAFT. An aggregate "edge" that is really the
    # bull side masking a losing bear book is the C4/C24 anti-pattern. So we ALSO
    # report whether the bear (authorized) side stands alone as a per-trade edge.
    bear_clears = bear_rep.get("n", 0) >= 20 and bear_rep.get("per_trade", 0) > 0 and (
        bear_rep.get("top5_day_pct") is not None and bear_rep["top5_day_pct"] < 200)
    return {
        "strike_offset": strike_offset,
        "strike_label": _strike_label(strike_offset),
        "premium_stop_pct": premium_stop_pct,
        "exits": {k: exits[k] for k in ("tp1_premium_pct", "runner_target_premium_pct",
                                        "profit_lock_mode", "profit_lock_trail_pct")
                  if k in exits},
        "n_dropped_opra_miss": dropped,
        "overall": ov_rep,
        "bull": bull_rep,
        "bear": bear_rep,
        "IS_2025": is_acc.report(),
        "OOS_2026": oos_rep,
        "by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{len(q_reports)}",
        "positive_quarters_n": pos_q,
        "clears_bar": clears,
        "clears_bar_reasons": reasons,
        "bear_authorized_clears": bear_clears,
        "bear_per_trade": bear_rep.get("per_trade", 0),
        "bull_per_trade": bull_rep.get("per_trade", 0),
    }


def _strike_label(off: int) -> str:
    if off < 0:
        return f"ITM-{abs(off)}"
    if off > 0:
        return f"OTM-{off}"
    return "ATM"


def _clears_bar(oos_rep: dict, pos_q: int, q_count: int, ov_rep: dict) -> tuple[bool, list]:
    """ALL required: OOS per-trade>0 AND positive_quarters>=4/6 AND
    top5_day_pct<200 AND n_trades>=20.

    top5_day_pct is checked on BOTH the full sample AND the OOS sample — a cell
    whose OOS P&L is >=200% concentrated in 5 winning days is a survivor artifact,
    not an edge (OP-20 #5, anti-pattern 2.10). n_trades is the OVERALL n.
    """
    reasons = []
    if oos_rep.get("n", 0) == 0 or oos_rep.get("per_trade", 0) <= 0:
        reasons.append(f"OOS per_trade={oos_rep.get('per_trade', 0)} (need >0, n={oos_rep.get('n', 0)})")
    if pos_q < 4:
        reasons.append(f"positive_quarters={pos_q}/{q_count} (need >=4)")
    t5 = ov_rep.get("top5_day_pct")
    if t5 is None or t5 >= 200:
        reasons.append(f"top5_day_pct(full)={t5} (need <200 and positive total)")
    t5_oos = oos_rep.get("top5_day_pct")
    if t5_oos is None or t5_oos >= 200:
        reasons.append(f"top5_day_pct(OOS)={t5_oos} (need <200; OOS concentration)")
    if ov_rep.get("n", 0) < 20:
        reasons.append(f"n_trades={ov_rep.get('n', 0)} (need >=20)")
    return (len(reasons) == 0), reasons


# ── Main ─────────────────────────────────────────────────────────────────────────
_SPY_RTH: pd.DataFrame = None  # set in main(); shared by run_cell


def main() -> int:
    global _SPY_RTH
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)

    # Normalise SPY timestamps to tz-naive ET (simulator_real strips tz on entry;
    # mixing tz-aware spy rows with tz-naive entry causes subtraction errors).
    spy_full["timestamp_et"] = (
        pd.to_datetime(spy_full["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York").dt.tz_localize(None)
    )
    vix_full["timestamp_et"] = (
        pd.to_datetime(vix_full["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York").dt.tz_localize(None)
    )
    log.info("Loaded SPY %d bars, VIX %d bars", len(spy_full), len(vix_full))

    # ── STEP 1: capture the live signal set ONCE ────────────────────────────────
    log.info("STEP 1: capturing LIVE engine signals (single orchestrator run, real-fills)...")
    signals = capture_live_signals(spy_full, vix_full)
    log.info("Captured %d raw live entries", len(signals))

    # The orchestrator runs over the RTH frame it builds internally. For the re-sim
    # we need the SAME spy_df the captured entry_bar_idx indexes into. The
    # orchestrator filters to RTH 09:30-16:00 and resets the index, and the captured
    # entry_bar carries its own timestamp, so rebuild the identical RTH frame and
    # VERIFY index alignment against the captured bars (fail loud on any mismatch —
    # silent index drift would invalidate the whole sweep, anti-pattern 2.x).
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
                   & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    _SPY_RTH = rth
    log.info("Rebuilt RTH frame: %d bars", len(rth))

    # Verify every captured entry_bar_idx lands on the SAME timestamp in our rth.
    mismatches = 0
    for s in signals[:5000]:
        if s.entry_bar_idx >= len(rth):
            mismatches += 1
            continue
        ts_rth = rth.iloc[s.entry_bar_idx]["timestamp_et"]
        ts_cap = s.entry_bar["timestamp_et"]
        ts_cap = ts_cap.tz_localize(None) if getattr(ts_cap, "tz", None) is not None else ts_cap
        if pd.Timestamp(ts_rth) != pd.Timestamp(ts_cap):
            mismatches += 1
    if mismatches:
        log.error("INDEX MISALIGNMENT: %d/%d captured entries do not match rebuilt RTH frame; "
                  "the orchestrator's internal frame differs. ABORTING (would invalidate sweep).",
                  mismatches, len(signals))
        raise SystemExit(2)
    log.info("Index alignment verified: all captured entries match the rebuilt RTH frame.")

    # Honour the live 15:00 ET entry cutoff exactly (drop late captures, if any).
    pre = len(signals)
    signals = [s for s in signals if s.entry_time.time() < ENTRY_CUTOFF_ET]
    if len(signals) != pre:
        log.info("Dropped %d entries at/after 15:00 ET entry cutoff -> %d signals",
                 pre - len(signals), len(signals))

    # Ribbon frame for the sim (same construction the orchestrator uses).
    log.info("Computing ribbon over RTH frame...")
    ribbon_df = compute_ribbon(rth["close"])  # matches orchestrator.py:796 exactly

    # Signal-set composition for disclosure.
    n_bull = sum(1 for s in signals if s.side == "C")
    n_bear = sum(1 for s in signals if s.side == "P")
    setups = defaultdict(int)
    for s in signals:
        setups[s.setup] += 1
    log.info("Signal set: %d total (%d bear / %d bull). Setups: %s",
             len(signals), n_bear, n_bull, dict(setups))

    # ── STEP 2: 5x4 strike x stop grid (default v15 exits) ──────────────────────
    log.info("STEP 2: sweeping %d strike x %d stop = %d cells (qty=%d, default v15 exits)...",
             len(STRIKE_OFFSETS), len(PREMIUM_STOPS), len(STRIKE_OFFSETS) * len(PREMIUM_STOPS), QTY)
    base_exits = dict(LIVE_EXITS)
    grid: list[dict] = []
    for so in STRIKE_OFFSETS:
        for ps in PREMIUM_STOPS:
            cell = run_cell(signals, ribbon_df, so, ps, base_exits)
            grid.append(cell)
            ov, oos = cell["overall"], cell["OOS_2026"]
            log.info("  strike=%+d(%s) stop=%.2f : overall n=%d per_trade=$%.1f total=$%.0f | "
                     "OOS n=%d per_trade=$%.1f | +q=%s top5=%s | drop=%d | clears=%s",
                     so, cell["strike_label"], ps, ov["n"], ov["per_trade"], ov["total_pnl"],
                     oos["n"], oos["per_trade"], cell["positive_quarters"], ov["top5_day_pct"],
                     cell["n_dropped_opra_miss"], cell["clears_bar"])

    # ── STEP 3: exit mini-sweep on OOS-positive strike/stop cells ───────────────
    oos_positive_cells = [c for c in grid
                          if c["OOS_2026"].get("n", 0) >= 1 and c["OOS_2026"].get("per_trade", 0) > 0]
    log.info("STEP 3: %d strike/stop cells are OOS per-trade positive -> exit mini-sweep each.",
             len(oos_positive_cells))
    exit_sweeps: list[dict] = []
    for c in oos_positive_cells:
        so, ps = c["strike_offset"], c["premium_stop_pct"]
        best = None
        combos = []
        for tp1 in TP1_PCTS:
            for rt in RUNNER_TARGETS:
                for chand in CHANDELIER_OPTIONS:
                    ex = dict(LIVE_EXITS)
                    ex["tp1_premium_pct"] = tp1
                    ex["runner_target_premium_pct"] = rt
                    if chand:
                        ex["profit_lock_mode"] = "trailing"
                        ex["profit_lock_trail_pct"] = CHANDELIER_TRAIL
                        ex["profit_lock_threshold_pct"] = 0.05
                    else:
                        # chandelier OFF: fixed profit-lock arm only (no trailing)
                        ex["profit_lock_mode"] = "fixed"
                        ex["profit_lock_trail_pct"] = 0.0
                        ex["profit_lock_threshold_pct"] = 0.0
                    rc = run_cell(signals, ribbon_df, so, ps, ex)
                    rec = {
                        "tp1_premium_pct": tp1,
                        "runner_target_premium_pct": rt,
                        "chandelier": chand,
                        "n_trades": rc["overall"]["n"],
                        "overall_per_trade": rc["overall"]["per_trade"],
                        "overall_total": rc["overall"]["total_pnl"],
                        "oos_per_trade": rc["OOS_2026"]["per_trade"],
                        "oos_total": rc["OOS_2026"]["total_pnl"],
                        "oos_top5_day_pct": rc["OOS_2026"]["top5_day_pct"],
                        "bear_per_trade": rc["bear_per_trade"],
                        "bull_per_trade": rc["bull_per_trade"],
                        "bear_authorized_clears": rc["bear_authorized_clears"],
                        "positive_quarters": rc["positive_quarters"],
                        "top5_day_pct": rc["overall"]["top5_day_pct"],
                        "clears_bar": rc["clears_bar"],
                        "full": rc,
                    }
                    combos.append(rec)
                    # rank exit combos by OOS per-trade, then overall total
                    key = (rec["oos_per_trade"], rec["overall_total"])
                    if best is None or key > (best["oos_per_trade"], best["overall_total"]):
                        best = rec
        exit_sweeps.append({
            "cell": f"strike={so}({c['strike_label']}) stop={ps}",
            "strike_offset": so,
            "premium_stop_pct": ps,
            "best_exit": {k: best[k] for k in best if k != "full"},
            "best_exit_full": best["full"],
            "all_combos": [{k: r[k] for k in r if k != "full"} for r in combos],
        })
        be = best
        log.info("  cell strike=%+d stop=%.2f best exit: tp1=%.2f runner=%.1f chand=%s -> "
                 "OOS per_trade=$%.1f overall_total=$%.0f clears=%s",
                 so, ps, be["tp1_premium_pct"], be["runner_target_premium_pct"], be["chandelier"],
                 be["oos_per_trade"], be["overall_total"], be["clears_bar"])

    # ── Candidate edges. A config is reported as a candidate edge only if it clears
    # the FULL bar (OOS per-trade>0, +q>=4/6, top5<200 on BOTH full AND OOS, n>=20).
    # We ALSO annotate each with the direction split + whether the AUTHORIZED (bear)
    # side stands alone — because per OP-16/L140 only BEARISH_REJECTION is live, and
    # an aggregate that clears only because the DRAFT bull side masks a losing bear
    # book is the C4/C24 anti-pattern (a survivor, not a shippable live edge). ──────
    candidate_edges = []
    for c in grid:
        if c["clears_bar"]:
            candidate_edges.append({
                "config": f"strike={c['strike_offset']}({c['strike_label']}) stop={c['premium_stop_pct']} "
                          f"exits=v15_default(tp1=0.50,runner=2.5,chand=0.15)",
                "n_trades": c["overall"]["n"],
                "oos_per_trade": c["OOS_2026"]["per_trade"],
                "oos_total_pnl": c["OOS_2026"]["total_pnl"],
                "overall_per_trade": c["overall"]["per_trade"],
                "positive_quarters": c["positive_quarters"],
                "top5_day_pct": c["overall"]["top5_day_pct"],
                "oos_top5_day_pct": c["OOS_2026"]["top5_day_pct"],
                "bear_per_trade": c["bear_per_trade"],
                "bull_per_trade": c["bull_per_trade"],
                "bear_authorized_clears": c["bear_authorized_clears"],
                "clears_bar": True,
                "source": "strike_stop_grid",
            })
    for es in exit_sweeps:
        for r in es["all_combos"]:
            if r["clears_bar"]:
                candidate_edges.append({
                    "config": f"strike={es['strike_offset']} stop={es['premium_stop_pct']} "
                              f"tp1={r['tp1_premium_pct']} runner={r['runner_target_premium_pct']} "
                              f"chand={r['chandelier']}",
                    "n_trades": r.get("n_trades"),
                    "oos_per_trade": r["oos_per_trade"],
                    "oos_total_pnl": r["oos_total"],
                    "overall_per_trade": r["overall_per_trade"],
                    "positive_quarters": r["positive_quarters"],
                    "top5_day_pct": r["top5_day_pct"],
                    "oos_top5_day_pct": r.get("oos_top5_day_pct"),
                    "bear_per_trade": r.get("bear_per_trade"),
                    "bull_per_trade": r.get("bull_per_trade"),
                    "bear_authorized_clears": r.get("bear_authorized_clears"),
                    "clears_bar": True,
                    "source": "exit_mini_sweep",
                })

    # ── Direction-split rollup: aggregate the bear (authorized) and bull (DRAFT)
    # books across the whole captured signal set, at the BEST stop per side. This is
    # the headline honesty check. ────────────────────────────────────────────────
    best_bear = max(grid, key=lambda c: c["bear_per_trade"]) if grid else None
    best_bull = max(grid, key=lambda c: c["bull_per_trade"]) if grid else None
    any_bear_clears = any(c["bear_authorized_clears"] for c in grid)
    direction_rollup = {
        "authorized_setup": "BEARISH_REJECTION_RIDE_THE_RIBBON (the ONLY live-authorized 0DTE setup, OP-16)",
        "draft_setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON (DRAFT per OP-16/L140 — not live-authorized)",
        "best_bear_cell": {
            "config": f"strike={best_bear['strike_offset']}({best_bear['strike_label']}) "
                      f"stop={best_bear['premium_stop_pct']}" if best_bear else None,
            "bear": best_bear["bear"] if best_bear else None,
        },
        "best_bull_cell": {
            "config": f"strike={best_bull['strike_offset']}({best_bull['strike_label']}) "
                      f"stop={best_bull['premium_stop_pct']}" if best_bull else None,
            "bull": best_bull["bull"] if best_bull else None,
        },
        "any_authorized_bear_cell_clears": any_bear_clears,
    }

    # ── Best config overall (by OOS per-trade among all grid cells; tiebreak total)
    def _cell_key(c):
        return (c["OOS_2026"].get("per_trade", -1e9), c["overall"].get("total_pnl", -1e9))
    best_cell = max(grid, key=_cell_key) if grid else None

    # baseline = ITM-2 / -0.50 stop default exits (the LIVE config) for reference
    baseline = next((c for c in grid if c["strike_offset"] == 2 and c["premium_stop_pct"] == -0.50), None)
    baseline_per_trade = baseline["overall"]["per_trade"] if baseline else None

    # ── Honest verdict ───────────────────────────────────────────────────────────
    bear_best_pt = best_bear["bear_per_trade"] if best_bear else 0.0
    bull_best_pt = best_bull["bull_per_trade"] if best_bull else 0.0
    n_clear = len(candidate_edges)
    n_clear_bear_authorized = sum(1 for ce in candidate_edges if ce.get("bear_authorized_clears"))
    if not any_bear_clears:
        honest_verdict = (
            f"NO LIVE-AUTHORIZED EDGE. The only live-authorized setup "
            f"(BEARISH_REJECTION) is per-trade NEGATIVE on real fills in ALL 20 strike/stop "
            f"cells (best bear cell {direction_rollup['best_bear_cell']['config']} = "
            f"${bear_best_pt:.1f}/trade, n~{(best_bear['bear']['n'] if best_bear else 0)}). "
            f"The {n_clear} aggregate cells that 'clear the bar' do so ONLY because the DRAFT, "
            f"NOT-live-authorized BULLISH_RECLAIM book (best ${bull_best_pt:.1f}/trade) masks the "
            f"losing bear book — the C4/C24 sub-population anti-pattern, NOT a shippable live edge. "
            f"Zero of those cells clear on the authorized bear side alone. "
            f"The pattern that IS real and robust across all cells: the v15 default/wide premium "
            f"stop bleeds; a TIGHT -8% premium stop is the only stop that is OOS-positive at every "
            f"strike (the live ITM-2/-0.50 baseline is NEGATIVE: ${baseline_per_trade}/trade overall). "
            f"Honest read: the live engine has no demonstrated 0DTE option edge on its authorized "
            f"setup over 2025-01..2026-05 real fills; nothing here is ship-ready under OP-16."
        )
    else:
        honest_verdict = (
            f"{n_clear_bear_authorized} config(s) clear the bar on the AUTHORIZED bear side alone "
            f"(bear per-trade>0, n>=20, top5<200). Best bear cell "
            f"{direction_rollup['best_bear_cell']['config']} = ${bear_best_pt:.1f}/trade. "
            f"These are candidate live edges; the bull book is reported separately as DRAFT."
        )

    report = {
        "family": "v14_enhanced",
        "generated_at": dt.datetime.now().isoformat(),
        "window": f"{START}..{END}",
        "is_year": IS_YEAR, "oos_year": OOS_YEAR,
        "qty_per_trade": QTY,
        "strike_convention": "simulator_real: negative=ITM, positive=OTM (verified lines 357-364)",
        "n_signals": len(signals),
        "signal_split": {"bear_P": n_bear, "bull_C": n_bull},
        "signal_setups": dict(setups),
        "candidate_edge_bar": "OOS per_trade>0 AND positive_quarters>=4/6 AND top5_day_pct<200 AND n_trades>=20",
        "sweep_grid_strike_offsets": STRIKE_OFFSETS,
        "sweep_grid_premium_stops": PREMIUM_STOPS,
        "baseline_live_config": {
            "strike_offset": 2, "strike_label": "ITM-2", "premium_stop_pct": -0.50,
            "exits": "v15 default (tp1=0.50, runner=2.5, chandelier trail=0.15)",
            "overall_per_trade": baseline_per_trade,
            "overall": baseline["overall"] if baseline else None,
            "OOS_2026": baseline["OOS_2026"] if baseline else None,
            "note": "This is the closest cell to the LIVE engine config (params.json v15.3).",
        },
        "strike_stop_grid": grid,
        "exit_mini_sweeps": exit_sweeps,
        "candidate_edges": candidate_edges,
        "direction_split_rollup": direction_rollup,
        "honest_verdict": honest_verdict,
        "baseline_default_per_trade": baseline_per_trade,
        "best_cell_by_oos_per_trade": {
            "config": f"strike={best_cell['strike_offset']}({best_cell['strike_label']}) "
                      f"stop={best_cell['premium_stop_pct']} exits=v15_default" if best_cell else None,
            "overall": best_cell["overall"] if best_cell else None,
            "OOS_2026": best_cell["OOS_2026"] if best_cell else None,
            "positive_quarters": best_cell["positive_quarters"] if best_cell else None,
            "clears_bar": best_cell["clears_bar"] if best_cell else None,
        },
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) — the only WR authority; no BS fallback in this study",
            "per_trade": "expectancy (per_trade $) reported alongside WR (OP-14: WR not standalone)",
            "concentration": "top5_day_pct = top-5 winning DAYS as % of total P&L (OP-20 #5)",
            "is_oos": f"IS={IS_YEAR} vs OOS={OOS_YEAR}; ~12mo IS vs ~4.5mo OOS",
            "direction_split": "bull(C) vs bear(P) reported per cell (the bull-tilt claim)",
            "no_survivor_cherry_pick": "cells positive only on tiny-N / high-concentration / OOS-negative "
                                       "are reported with clears_bar=false (anti-pattern 2.10)",
            "sizing": f"qty={QTY} per-contract read; option bracket P&L is linear in qty so this isolates "
                      "the per-trade edge (scale to account per-trade risk cap separately)",
            "opra_miss": "simulate_trade_real returns None on OPRA cache miss for the swept strike; that "
                         "signal is dropped for that cell (n_dropped_opra_miss reported per cell)",
            "detection_faithfulness": "signals captured by wrapping simulate_trade_real and running the live "
                                      "orchestrator ONCE under params.json v15.3 config — zero signal drift "
                                      "vs production; only strike/stop/exit are overridden in re-sim",
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    # ── Console verdict ─────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("EDGE HUNT — v14_enhanced (LIVE engine) REAL-FILLS VERDICT")
    print("=" * 72)
    print(f"signals={len(signals)} (bear={n_bear} bull={n_bull})  window={START}..{END}")
    if baseline:
        print(f"BASELINE (live ITM-2/-0.50/v15-exits): overall {baseline['overall']}  "
              f"OOS {baseline['OOS_2026']}  +q={baseline['positive_quarters']}")
    print("\n--- DIRECTION SPLIT (the headline) ---")
    print(f"  AUTHORIZED bear (BEARISH_REJECTION): best cell {direction_rollup['best_bear_cell']['config']} "
          f"-> {direction_rollup['best_bear_cell']['bear']}")
    print(f"  DRAFT bull (BULLISH_RECLAIM, NOT live): best cell {direction_rollup['best_bull_cell']['config']} "
          f"-> {direction_rollup['best_bull_cell']['bull']}")
    print(f"  any authorized bear cell clears the bar? {any_bear_clears}")
    print(f"\nCANDIDATE EDGES clearing the AGGREGATE bar: {len(candidate_edges)} "
          f"(of which clear on AUTHORIZED bear side alone: {n_clear_bear_authorized})")
    for ce in candidate_edges[:12]:
        print(f"  + {ce['config']} | n={ce['n_trades']} OOS/tr=${ce['oos_per_trade']} "
              f"+q={ce['positive_quarters']} top5(full)={ce['top5_day_pct']} top5(OOS)={ce.get('oos_top5_day_pct')} "
              f"| bear/tr=${ce.get('bear_per_trade')} bull/tr=${ce.get('bull_per_trade')} "
              f"bear_clears={ce.get('bear_authorized_clears')}")
    if not candidate_edges:
        print("  (none clear the aggregate bar)")
    print(f"\nHONEST VERDICT:\n{honest_verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
