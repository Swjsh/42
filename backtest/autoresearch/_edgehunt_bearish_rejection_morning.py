"""EDGE HUNT — bearish_rejection_morning family: strike x stop x exit real-fills sweep.

FAMILY (J's anchor entries 4/29 + 5/04): 09:35-10:55 ET, EMA ribbon just-flipped BEAR,
named-level rejection >= 15c, vol >= 1.5x 20-bar avg -> PUTS. This is the
bearish_rejection_morning_watcher signal (the v40_bearish_rejection_morning_gate logic),
which is BEARISH_REJECTION_RIDE_THE_RIBBON entered WITH the morning flip.

WHAT THIS ADDS over prior work (stratify_bearish_rejection_quality.py): that script ran
ONLY ATM + ITM2 at chart-stop-only (premium_stop=-0.99) and concluded the book is NEGATIVE
(baseline ATM exp -$32.8). This sweep keeps the SAME proven signal-detection harness
(compute_ribbon + _detect_from_history levels + full BarContext + detect_bearish_rejection_morning)
but explores the dimension that was NOT swept: contract sizing (strike_offset) x stop
(premium_stop_pct), then a second exits mini-sweep on any OOS-positive cell.

STRIKE CONVENTION (verified in simulator_real.py L357-364 BEFORE writing — anti-pattern 2.2):
  For PUTS (side='P'):  strike = atm - strike_offset
    strike_offset = -2  -> strike = atm+2  = ITM-2 (production default, deep-ITM put)
    strike_offset = -1  -> strike = atm+1  = ITM-1
    strike_offset =  0  -> strike = atm    = ATM
    strike_offset = +1  -> strike = atm-1  = OTM-1
    strike_offset = +2  -> strike = atm-2  = OTM-2
  So negative=ITM, positive=OTM for puts. Confirmed: matches the task brief + L259 comment.

REAL-FILLS AUTHORITY (C1): simulate_trade_real over OPRA bars. OPRA cache ends ~2026-05-29
(latest contract SPY260529 in backtest/data/options), so the real-fills window is
~2025-01-02..2026-05-29 — fires after that return no data (counted no_fill). OOS(2026)
real fills therefore cover Jan-May 2026.

DISCLOSURE (OP-20 / OP-14): per-trade EXPECTANCY (not WR alone), IS(2025) vs OOS(2026)
split, positive_quarters out of 6, top5_day_pct (top-5 winning DAYS as % of total P&L).
A cell is a CANDIDATE EDGE only if ALL: OOS exp > 0 AND positive_quarters >= 4/6 AND
top5_day_pct < 200 AND n_trades >= 20. Survivors that are tiny-N / high-concentration /
OOS-negative are reported with clears_bar=false (anti-pattern 2.10 — no cherry-picking).

Pure Python, $0, no LLM, no live orders. Markets closed (weekend) — heavy compute OK.

Usage:
  backtest/.venv/Scripts/python.exe -m autoresearch._edgehunt_bearish_rejection_morning
Output:
  analysis/recommendations/edgehunt-bearish_rejection_morning.json
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from autoresearch import validate_breakout_family as vbf  # noqa: E402
from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext  # noqa: E402
from lib.ribbon import compute_ribbon, RibbonState  # noqa: E402
from lib.levels import _detect_from_history  # noqa: E402
from lib.orchestrator import (  # noqa: E402
    _align_vix_to_spy,
    _precompute_htf_15m_stacks,
    _update_level_states,
)
from lib.watchers import bearish_rejection_morning_watcher as _brm  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stdout)
log = logging.getLogger("edgehunt")

# ── Window + grid ─────────────────────────────────────────────────────────────
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)          # matches confluence template; real fills cap ~05-29 anyway
QTY = 3
SIDE = "P"                          # family is bearish -> puts only

STRIKE_OFFSETS = [-2, -1, 0, 1, 2]          # neg=ITM, pos=OTM (for puts; verified above)
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]  # -0.99 == chart-stop-only

# Production-default cell (v15): ITM-2 + bear stop -0.08. Reported as the baseline.
DEFAULT_OFFSET = -2
DEFAULT_STOP = -0.08

# Exit mini-sweep (only on OOS-positive cells)
TP1_PCTS = [0.30, 0.50]
RUNNER_TARGETS = [2.0, 2.5, 3.0]
TRAIL_MODES = [("fixed", 0.0), ("trailing", 0.20)]  # chandelier off / 20%-off-HWM on

# Candidate-edge bar (ALL must hold)
BAR_OOS_EXP = 0.0          # OOS per-trade expectancy > 0
BAR_POS_QUARTERS = 4       # >= 4 of 6
BAR_TOP5_PCT = 200.0       # top5_day_pct < 200
BAR_MIN_TRADES = 20        # n_trades >= 20


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _offset_label(off: int) -> str:
    if off < 0:
        return f"ITM{-off}"
    if off > 0:
        return f"OTM{off}"
    return "ATM"


def _stop_label(stop: float) -> str:
    return "chart_only" if stop <= -0.99 else f"{int(round(stop * 100))}pct"


def _cell_name(off: int, stop: float) -> str:
    return f"{_offset_label(off)}|stop_{_stop_label(stop)}"


# ──────────────────────────────────────────────────────────────────────────────
# STEP 1: detect every family signal ONCE (proven harness from
# stratify_bearish_rejection_quality._collect — full BarContext pipeline with real
# ribbon + historically-rebuilt levels + the actual detect_bearish_rejection_morning).
# We keep the (idx, bar, rejection_level, triggers, vix, date) carriers for the sweep.
# ──────────────────────────────────────────────────────────────────────────────
def detect_signals(start: dt.date, end: dt.date) -> tuple[list[dict], pd.DataFrame, pd.DataFrame]:
    spy_full, vix_full = vbf._load_data(start, end)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
                   (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    log.info("RTH bars: %d", len(rth))

    ribbon_df = compute_ribbon(rth["close"])
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    htf_stacks = _precompute_htf_15m_stacks(rth)

    signals: list[dict] = []
    level_states: dict = {}
    ribbon_history: list = []
    last_date = None
    _lvl_cache = [None]
    _lvl_date = [None]

    for idx in range(len(rth)):
        bar = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        bar_date = bar_time.date()
        if bar_date < start or bar_date > end:
            continue
        if last_date is not None and bar_date != last_date:
            ribbon_history = []
            level_states = {}
        last_date = bar_date
        if idx < 60:
            continue
        try:
            r = ribbon_df.iloc[idx]
            ribbon_state = RibbonState(fast=float(r["fast"]), pivot=float(r["pivot"]),
                                       slow=float(r["slow"]), stack=str(r["stack"]),
                                       spread_cents=float(r["spread_cents"]))
        except Exception:
            continue
        ribbon_history.append(ribbon_state)
        ribbon_history = ribbon_history[-10:]
        vol_baseline = vol_baseline_20bar(rth, idx)
        range_baseline = range_baseline_20bar(rth, idx)
        vix_now = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 17.0
        vix_prior = float(vix_aligned.iloc[max(0, idx - 3)]) if max(0, idx - 3) < len(vix_aligned) else vix_now

        if bar_date != _lvl_date[0]:
            full_history = spy_full[spy_full["timestamp_et"] <= bar_time]
            _lvl_cache[0] = _detect_from_history(full_history, bar_date)
            _lvl_date[0] = bar_date
        level_set = _lvl_cache[0]
        _update_level_states(level_states, level_set.active, bar, idx)
        htf = htf_stacks[idx] if idx < len(htf_stacks) else None

        ctx = BarContext(
            bar_idx=idx, timestamp_et=bar_time.to_pydatetime(), bar=bar,
            prior_bars=rth.iloc[:idx + 1], ribbon_now=ribbon_state, ribbon_history=ribbon_history,
            vix_now=vix_now, vix_prior=vix_prior, vol_baseline_20=vol_baseline,
            range_baseline_20=range_baseline, levels_active=level_set.active,
            multi_day_levels=level_set.multi_day, htf_15m_stack=htf, level_states=level_states,
        )

        try:
            sig = _brm.detect_bearish_rejection_morning(ctx)
        except Exception as _e:
            sys.stderr.write(f"brm bar={bar_time}: {type(_e).__name__}: {_e}\n")
            sig = None
        if sig is None:
            continue

        rej_level = float(sig.metadata.get("rejection_level") or sig.stop_price)
        signals.append({
            "idx": idx,
            "date": bar_date,
            "time": bar_time.strftime("%H:%M"),
            "is_anchor": bar_date in vbf.ANCHORS,
            "anchor_label": vbf.ANCHORS.get(bar_date),
            "conf": sig.confidence,
            "vix_now": round(vix_now, 2),
            "rejection_level": rej_level,
            "triggers_fired": list(sig.triggers_fired),
            "setup_name": sig.setup_name,
            "_bar": bar,
        })

    log.info("Family signals detected: %d", len(signals))
    return signals, rth, ribbon_df


# ──────────────────────────────────────────────────────────────────────────────
# P&L accumulator with the full OP-20 disclosure surface.
# ──────────────────────────────────────────────────────────────────────────────
class Acc:
    __slots__ = ("pnls", "by_day", "by_q_total", "is_pnls", "oos_pnls",
                 "anchor_win", "anchor_loss", "n_anchor")

    def __init__(self):
        self.pnls: list[float] = []
        self.by_day: dict[str, float] = defaultdict(float)
        self.by_q_total: dict[str, float] = defaultdict(float)
        self.is_pnls: list[float] = []
        self.oos_pnls: list[float] = []
        self.anchor_win = 0.0
        self.anchor_loss = 0.0
        self.n_anchor = 0

    def add(self, pnl: float, d: dt.date, anchor_label):
        self.pnls.append(pnl)
        self.by_day[d.isoformat()] += pnl
        self.by_q_total[_quarter(d)] += pnl
        if d.year == 2025:
            self.is_pnls.append(pnl)
        else:
            self.oos_pnls.append(pnl)
        if anchor_label == "WIN":
            self.anchor_win += pnl
            self.n_anchor += 1
        elif anchor_label == "LOSS":
            self.anchor_loss += max(0.0, -pnl)
            self.n_anchor += 1

    @staticmethod
    def _exp(pnls: list[float]):
        return round(sum(pnls) / len(pnls), 2) if pnls else None

    @staticmethod
    def _wr(pnls: list[float]):
        return round(100 * sum(1 for p in pnls if p > 0) / len(pnls), 1) if pnls else None

    def top5_day_pct(self):
        tot = sum(self.pnls)
        if tot <= 0:
            return None  # undefined when net book is not positive
        winning = sorted([v for v in self.by_day.values() if v > 0], reverse=True)
        return round(100 * sum(winning[:5]) / tot, 0)

    def positive_quarters(self) -> tuple[int, int]:
        qs = [v for v in self.by_q_total.values()]
        return sum(1 for v in qs if v > 0), len(qs)

    def report(self) -> dict:
        n = len(self.pnls)
        pos_q, tot_q = self.positive_quarters()
        return {
            "n_trades": n,
            "overall_per_trade": self._exp(self.pnls),
            "overall_total_pnl": round(sum(self.pnls), 0) if n else 0.0,
            "overall_wr": self._wr(self.pnls),
            "is_2025_n": len(self.is_pnls),
            "is_2025_per_trade": self._exp(self.is_pnls),
            "oos_2026_n": len(self.oos_pnls),
            "oos_per_trade": self._exp(self.oos_pnls),
            "oos_total_pnl": round(sum(self.oos_pnls), 0) if self.oos_pnls else 0.0,
            "positive_quarters": f"{pos_q}/{tot_q}",
            "by_quarter": {k: round(self.by_q_total[k], 0) for k in sorted(self.by_q_total)},
            "top5_day_pct": self.top5_day_pct(),
            "edge_capture": round(self.anchor_win - self.anchor_loss, 1),
            "n_anchor_fills": self.n_anchor,
        }


def _run_cell(signals, rth, ribbon_df, offset, stop, exit_cfg=None) -> tuple[Acc, int]:
    """Run the full signal set through simulate_trade_real for one (offset, stop[, exits])
    cell. Returns (accumulator, n_no_fill)."""
    acc = Acc()
    no_fill = 0
    cfg = dict(exit_cfg or {})
    for s in signals:
        try:
            fill = simulate_trade_real(
                entry_bar_idx=s["idx"], entry_bar=s["_bar"], spy_df=rth, ribbon_df=ribbon_df,
                rejection_level=float(s["rejection_level"]), triggers_fired=s["triggers_fired"],
                side=SIDE, qty=QTY, setup=s["setup_name"],
                strike_offset=offset, premium_stop_pct=stop,
                entry_vix=float(s.get("vix_now") or 0.0), **cfg)
        except Exception as _e:
            sys.stderr.write(f"sim {_cell_name(offset, stop)} {s['date']} {s['time']}: "
                             f"{type(_e).__name__}: {_e}\n")
            fill = None
        if fill is None or getattr(fill, "dollar_pnl", None) is None:
            no_fill += 1
            continue
        acc.add(float(fill.dollar_pnl), s["date"], s["anchor_label"])
    return acc, no_fill


def _clears_bar(rep: dict) -> bool:
    oos = rep.get("oos_per_trade")
    if oos is None or oos <= BAR_OOS_EXP:
        return False
    pos_q = int(rep["positive_quarters"].split("/")[0])
    if pos_q < BAR_POS_QUARTERS:
        return False
    t5 = rep.get("top5_day_pct")
    if t5 is None or t5 >= BAR_TOP5_PCT:
        return False
    if rep.get("n_trades", 0) < BAR_MIN_TRADES:
        return False
    return True


def main() -> int:
    log.info("Loading %s..%s and detecting family signals ONCE...", START, END)
    signals, rth, ribbon_df = detect_signals(START, END)
    if not signals:
        log.error("No signals detected — aborting.")
        return 1

    # ── STEP 2: 5x4 strike x stop grid (re-run sim only — fast) ──
    grid: dict[str, dict] = {}
    default_report = None
    log.info("Running 5x4 = 20 strike x stop cells...")
    for off in STRIKE_OFFSETS:
        for stop in PREMIUM_STOPS:
            acc, no_fill = _run_cell(signals, rth, ribbon_df, off, stop)
            rep = acc.report()
            rep["n_no_fill"] = no_fill
            rep["clears_bar"] = _clears_bar(rep)
            name = _cell_name(off, stop)
            grid[name] = rep
            if off == DEFAULT_OFFSET and stop == DEFAULT_STOP:
                default_report = rep
            log.info("  %-22s n=%-3d exp=%-8s OOSexp=%-8s posQ=%-4s top5=%-5s clears=%s",
                     name, rep["n_trades"], rep["overall_per_trade"], rep["oos_per_trade"],
                     rep["positive_quarters"], rep["top5_day_pct"], rep["clears_bar"])

    # ── STEP 3: exit mini-sweep on every OOS-positive cell ──
    oos_positive = [(name, rep) for name, rep in grid.items()
                    if rep.get("oos_per_trade") is not None and rep["oos_per_trade"] > 0
                    and rep["n_trades"] >= BAR_MIN_TRADES]
    log.info("OOS-positive cells (n>=%d) for exit mini-sweep: %d -> %s",
             BAR_MIN_TRADES, len(oos_positive), [n for n, _ in oos_positive])

    exit_sweeps: dict[str, dict] = {}
    for name, _rep in oos_positive:
        # recover offset+stop from the name
        off = next(o for o in STRIKE_OFFSETS for st in PREMIUM_STOPS if _cell_name(o, st) == name)
        stop = next(st for o in STRIKE_OFFSETS for st in PREMIUM_STOPS if _cell_name(o, st) == name)
        best = None
        combos = []
        for tp1 in TP1_PCTS:
            for rt in RUNNER_TARGETS:
                for mode, trail in TRAIL_MODES:
                    cfg = {
                        "tp1_premium_pct": tp1,
                        "runner_target_premium_pct": rt,
                        "profit_lock_mode": mode,
                    }
                    if mode == "trailing":
                        cfg["profit_lock_trail_pct"] = trail
                        cfg["profit_lock_threshold_pct"] = 0.05  # arm at +5% favor (v15 chandelier)
                    acc, nf = _run_cell(signals, rth, ribbon_df, off, stop, exit_cfg=cfg)
                    r = acc.report()
                    r["clears_bar"] = _clears_bar(r)
                    combo_name = f"tp1_{int(tp1*100)}|rt_{rt}|{mode}{('_'+str(trail)) if mode=='trailing' else ''}"
                    combos.append({"combo": combo_name, **{k: r[k] for k in (
                        "n_trades", "overall_per_trade", "oos_per_trade", "oos_total_pnl",
                        "positive_quarters", "top5_day_pct", "clears_bar")}})
                    score = r["oos_per_trade"] if r["oos_per_trade"] is not None else -1e9
                    if best is None or score > best["_score"]:
                        best = {"_score": score, "combo": combo_name, "report": r}
        if best is not None:
            best.pop("_score", None)
        exit_sweeps[name] = {"best_exit": best, "all_combos": combos}

    # ── Direction split context (OP: bull loses less than bear on options) ──
    # This family is bearish-only by construction (it requires ribbon=BEAR + resistance
    # rejection). We cannot run the SAME signals as calls (no bullish trigger), so the
    # direction split is reported as a DOCUMENTED STRUCTURAL NOTE referencing the existing
    # cross-family evidence rather than a fabricated call-side run on bear signals.
    direction_note = (
        "This family is structurally BEARISH-ONLY (gate requires ribbon=BEAR + a resistance "
        "rejection). There is no call-side variant of the SAME signal to run, so a within-family "
        "C-vs-P split is undefined. The documented cross-family bull-tilt (lessons C4/C5 + "
        "confluence_real_fills_validate.py by_bias) — bull books lose less than bear books on "
        "0DTE options because puts fight positive drift + faster theta on down-moves — is the "
        "REASON this bear-only family starts at a structural disadvantage, consistent with the "
        "negative baseline reported here."
    )

    # ── Rank + pick best overall cell (by OOS per-trade, then total) ──
    rankable = [(n, r) for n, r in grid.items() if r.get("oos_per_trade") is not None]
    rankable.sort(key=lambda kv: (kv[1]["oos_per_trade"], kv[1]["oos_total_pnl"]), reverse=True)
    best_overall = rankable[0][0] if rankable else None

    candidate_edges = []
    for name, rep in grid.items():
        candidate_edges.append({
            "config": name,
            "n_trades": rep["n_trades"],
            "overall_per_trade": rep["overall_per_trade"],
            "oos_per_trade": rep["oos_per_trade"],
            "oos_total_pnl": rep["oos_total_pnl"],
            "positive_quarters": rep["positive_quarters"],
            "top5_day_pct": rep["top5_day_pct"],
            "clears_bar": rep["clears_bar"],
        })
    candidate_edges.sort(key=lambda c: (c["oos_per_trade"] if c["oos_per_trade"] is not None else -1e9),
                         reverse=True)

    n_clear = sum(1 for c in candidate_edges if c["clears_bar"])
    if n_clear == 0:
        honest = (
            f"NO CANDIDATE EDGE. Across all 20 strike x stop cells of the "
            f"bearish_rejection_morning family ({len(signals)} signals, real fills "
            f"~2025-01..2026-05), ZERO cells clear the bar (OOS exp>0 AND posQ>=4/6 AND "
            f"top5<200 AND n>=20). The production-default cell "
            f"({_offset_label(DEFAULT_OFFSET)}|stop_{_stop_label(DEFAULT_STOP)}) is "
            f"{(str(default_report.get('overall_per_trade')) + '/trade') if default_report else 'n/a'} "
            f"overall. This CONFIRMS the prior real-fills verdict (stratify_bearish_rejection_"
            f"quality.py: book is NEGATIVE, no conditioning makes it cleanly positive). The "
            f"bull-tilt is structural, not capturable here — this bear-only family is a "
            f"do-not-ship. Keep WATCH_ONLY."
        )
    else:
        clears = [c for c in candidate_edges if c["clears_bar"]]
        honest = (
            f"{n_clear} cell(s) clear the bar: {[c['config'] for c in clears]}. "
            f"Best by OOS per-trade: {best_overall}. Each must still pass anchor-no-regression "
            f"(edge_capture sign) + DSR before any ship. See candidate_edges + exit_sweeps."
        )

    out = {
        "generated_at": dt.datetime.now().isoformat(),
        "family": "bearish_rejection_morning",
        "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON (bearish_rejection_morning_watcher / v40 gate)",
        "window_requested": f"{START}..{END}",
        "side": SIDE,
        "qty": QTY,
        "n_signals": len(signals),
        "strike_convention_verified": ("puts: strike=atm-strike_offset; neg=ITM pos=OTM "
                                       "(simulator_real.py L357-364). default v15 = ITM-2 (offset -2)."),
        "grid_axes": {"strike_offset": STRIKE_OFFSETS, "premium_stop_pct": PREMIUM_STOPS},
        "candidate_edge_bar": {
            "oos_per_trade": f"> {BAR_OOS_EXP}", "positive_quarters": f">= {BAR_POS_QUARTERS}/6",
            "top5_day_pct": f"< {BAR_TOP5_PCT}", "n_trades": f">= {BAR_MIN_TRADES}",
        },
        "baseline_default_cell": {
            "config": _cell_name(DEFAULT_OFFSET, DEFAULT_STOP),
            "report": default_report,
        },
        "grid": grid,
        "candidate_edges_sorted": candidate_edges,
        "n_clears_bar": n_clear,
        "best_overall_by_oos_per_trade": best_overall,
        "exit_mini_sweeps_on_oos_positive_cells": exit_sweeps,
        "direction_split": direction_note,
        "honest_verdict": honest,
        "op20_disclosures": {
            "authority": "real OPRA fills (C1) via simulate_trade_real — the only WR/expectancy authority",
            "realfills_window": ("OPRA cache ends ~2026-05-29 (SPY260529); real fills "
                                 "~2025-01-02..2026-05-29. Fires after that = no_fill. OOS(2026) "
                                 "real fills cover Jan-May 2026."),
            "per_trade": "expectancy (overall_per_trade / oos_per_trade) reported, not WR alone (OP-14)",
            "is_oos_split": "IS=2025, OOS=2026 (calendar). per-trade reported each side.",
            "concentration": "top5_day_pct = top-5 winning DAYS as % of net total (None when net<=0).",
            "positive_quarters": "count of calendar quarters with positive net P&L, out of quarters seen.",
            "levels": ("historically-rebuilt level proxies (_detect_from_history), NOT production "
                       "star/Carry named set — disclosed; placement edge is real, reaction edge unproven (L142-144)."),
            "no_survivor_cherry_pick": ("anti-pattern 2.10: any positive cell that is tiny-N / "
                                        "high-concentration / OOS-negative is marked clears_bar=false."),
            "prior_result": ("stratify_bearish_rejection_quality.py (ATM+ITM2 chart-stop-only) found "
                             "this book NEGATIVE (baseline ATM exp -$32.8, PSR(>0)=0.04). This sweep "
                             "adds the strike x stop x exit dimension it did not explore."),
        },
    }

    out_path = ROOT / "analysis" / "recommendations" / "edgehunt-bearish_rejection_morning.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", out_path)

    print("\n=== EDGE HUNT: bearish_rejection_morning ===")
    print(f"signals={len(signals)}  cells=20  clears_bar={n_clear}")
    print(f"baseline default {_cell_name(DEFAULT_OFFSET, DEFAULT_STOP)}: "
          f"{default_report.get('overall_per_trade') if default_report else 'n/a'}/trade "
          f"(OOS {default_report.get('oos_per_trade') if default_report else 'n/a'})")
    print("TOP 5 cells by OOS per-trade:")
    for c in candidate_edges[:5]:
        print(f"  {c['config']:22s} n={c['n_trades']:<3} OOSexp={c['oos_per_trade']} "
              f"posQ={c['positive_quarters']} top5={c['top5_day_pct']} clears={c['clears_bar']}")
    print(f"\nVERDICT: {honest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
