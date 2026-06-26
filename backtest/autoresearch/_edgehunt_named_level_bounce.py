"""EDGE-HUNT: counter-ribbon NAMED-LEVEL bounce/rejection (LONG-side validation).

Fork of ``_edgehunt_vwap_continuation`` — same REAL-OPRA fill path
(``simulate_trade_real``), same metric bundle, but a DIFFERENT detector:

    Fire on the rejection/reclaim CANDLE at a named Active/Carry-tier level
    (level tag + rejection wick + close back THROUGH the level) WITHOUT requiring
    the EMA ribbon to confirm direction (counter-ribbon ALLOWED). ITM + tight
    target (anti-theta), outer-band only (~$0.30 of the level), confirmed candle
    not a bare tag, hard cap 2 entries/session, no re-entry on a broken level.

────────────────────────────────────────────────────────────────────────────────
WHY STRUCTURAL (PDH/PDL/PMH/PML/PDC) AND NOT key-levels.json
────────────────────────────────────────────────────────────────────────────────
J-curated named levels live ONLY in TODAY's ``automation/state/key-levels.json``
(level_source.load_named_levels reads parents[3]/automation/state/key-levels.json,
per-calendar-day cache). They are NOT archived historically — there is no
per-date snapshot. A named-level backtest over history therefore CANNOT use the
J-curated levels (the BLOCKER in agent-memory project_named_level_trigger_scope).

The honest surrogate: reconstruct the level TYPES that BECOME Active/Carry tier in
the live protocol, causally, from the bar data itself:
    PDH  = prior RTH session high       (resistance)
    PDL  = prior RTH session low         (support)
    PDC  = prior RTH session close       (pivot)
    PMH  = today's pre-market high (04:00-09:30 ET)  (resistance)
    PML  = today's pre-market low  (04:00-09:30 ET)  (support)
    ONH/ONL = overnight (prior 16:00 → today 09:30) high/low
All are known at-or-before the RTH open → reading them intraday is causal.

The anchor cases the setup MUST capture are exactly these types:
  (1) 2026-06-26 ~09:41-09:51 — reclaim of PML support ~728.50 (LONG, counter-BEAR)
  (2) 2026-06-24 ~09:40       — rejection at PMH 737.11 (SHORT, counter-BULL)
So PDH/PDL/PMH/PML/PDC are the RIGHT surrogate for the anchors by construction.

CAVEAT (disclosed, OP-20): this is a PROXY level set. PDL real-fills historically
UNDERSTATE J's ★★★ key-levels by up to ~20pp (NLWB lesson L58). A FAIL on this
proxy is decisive (proxy is the EASIER, more-frequent set); a marginal PASS would
need re-validation on live ★★★ levels before any promotion.

────────────────────────────────────────────────────────────────────────────────
THE CRITICAL GATE — beat a random-entry NULL at the same levels/times (C3/L183)
────────────────────────────────────────────────────────────────────────────────
A level edge that a random-entry null at the SAME bars reproduces is an EXIT-
STRUCTURE artifact (ITM+tight target mechanics), NOT signal alpha. We build a
matched null: for every real signal day, pick a RANDOM eligible bar in the same
[09:35,14:30] window, same side, same structural stop = nearest level — and run
the SAME fill path. If real does not clearly beat the null MAX over N seeds, HOLD.

PROPOSE-ONLY (Rule 9). Real OPRA fills only (C1). Pure Python, $0. No live orders.
Run:
    backtest/.venv/Scripts/python.exe -m autoresearch._edgehunt_named_level_bounce
    backtest/.venv/Scripts/python.exe -m autoresearch._edgehunt_named_level_bounce --smoke
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    _nearest_cached_strike,
    _strike_from_spot,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _align_vix,
    _normalize_spy,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "edgehunt-named-level-bounce.json"

# ── Session windows (ET) ───────────────────────────────────────────────────────
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
PM_START = dt.time(4, 0)          # pre-market open
ENTRY_START = dt.time(9, 35)
ENTRY_END = dt.time(14, 30)

# ── Detector knobs (the setup design) ──────────────────────────────────────────
OUTER_BAND = 0.30        # bar must approach within $0.30 of the level (outer-band only)
WICK_MIN_CENTS = 8.0     # rejection/reclaim wick must pierce >= 8c through the level
BODY_MIN_CENTS = 5.0     # close must be >= 5c back on the correct side (confirmed candle)
MAX_ENTRIES_PER_SESSION = 2
QTY = 3
MAX_STRIKE_STEPS = 4

# ── Sweep space (anti-theta: ITM + tight target is the hypothesis) ─────────────
STRIKE_OFFSETS = [-2, -1, 0]        # NEGATIVE = ITM (verified simulator_real L357-364)
PREMIUM_STOPS = [-0.99, -0.50]      # chart-stop-primary (-0.99) and -50% cap
TP1_LEVELS = [0.30, 0.50]           # TIGHT targets (the vwap winning profile)
TP1_QTY = 0.667
RUNNER_TGT = 2.5
NULL_SEEDS = 40                     # random-entry null draws (per cell)

OOS_YEAR = 2026                     # IS=2025 / OOS=2026 calendar split


# ── Structural level reconstruction (causal) ──────────────────────────────────
@dataclass(frozen=True)
class DayLevels:
    date: dt.date
    supports: tuple                 # (label, price) below/at open — long-bounce candidates
    resistances: tuple              # (label, price) — short-rejection candidates
    idx0: int                       # first RTH global idx
    idx_last: int                   # last RTH global idx


def build_day_levels(spy: pd.DataFrame) -> list[DayLevels]:
    """Per-day PDH/PDL/PDC/PMH/PML/ONH/ONL — all known at the RTH open (causal)."""
    out: list[DayLevels] = []
    prev_rth_hi = prev_rth_lo = prev_rth_close = None
    for d, day in spy.groupby("date", sort=True):
        rth = day[(day["t"] >= RTH_OPEN) & (day["t"] < RTH_CLOSE)]
        pm = day[(day["t"] >= PM_START) & (day["t"] < RTH_OPEN)]
        if len(rth) >= 12:
            sup, res = [], []
            if prev_rth_lo is not None:
                sup.append(("PDL", prev_rth_lo))
                res.append(("PDH", prev_rth_hi))
                # PDC acts as both pivot — list on the side the open is relative to.
            if len(pm) > 0:
                pmh = float(pm["high"].max())
                pml = float(pm["low"].min())
                res.append(("PMH", pmh))
                sup.append(("PML", pml))
            if prev_rth_close is not None:
                # classify PDC by where the RTH open sits
                op = float(rth["open"].iloc[0])
                (sup if op >= prev_rth_close else res).append(("PDC", prev_rth_close))
            out.append(DayLevels(
                date=d, supports=tuple(sup), resistances=tuple(res),
                idx0=int(rth.index[0]), idx_last=int(rth.index[-1])))
        # roll prior-day facts
        if len(rth) >= 12:
            prev_rth_hi = float(rth["high"].max())
            prev_rth_lo = float(rth["low"].min())
            prev_rth_close = float(rth["close"].iloc[-1])
    return out


@dataclass(frozen=True)
class Signal:
    bar_idx: int
    side: str           # 'C' long / 'P' short
    stop_level: float
    level_label: str
    level_price: float
    note: str


def detect_signals(spy: pd.DataFrame, day_levels: list[DayLevels], *,
                   long_only: bool = False, short_only: bool = False) -> list[Signal]:
    """Counter-ribbon-ALLOWED bounce(long)/rejection(short) at a structural level.

    LONG  (reclaim of support): bar LOW pierces >= WICK_MIN_CENTS below a support
          level AND CLOSE is >= BODY_MIN_CENTS back ABOVE it (failed breakdown).
    SHORT (rejection at resistance): bar HIGH pierces >= WICK_MIN_CENTS above a
          resistance AND CLOSE is >= BODY_MIN_CENTS back BELOW it.
    NO ribbon gate (the whole point). Outer-band: the pierce wick must be within
    OUTER_BAND of the level (it is, by the wick definition). Hard cap 2/session.
    No re-entry on a level already used (broken-level guard).
    """
    out: list[Signal] = []
    for dl in day_levels:
        rth = spy.loc[dl.idx0:dl.idx_last]
        rth = rth[(rth["t"] >= ENTRY_START) & (rth["t"] <= ENTRY_END)]
        fired = 0
        used_levels: set = set()
        for gidx, bar in rth.iterrows():
            if fired >= MAX_ENTRIES_PER_SESSION:
                break
            lo = float(bar["low"]); hi = float(bar["high"]); cl = float(bar["close"])
            best = None  # (deepest_wick, side, label, price, stop)
            if not short_only:
                for lab, lvl in dl.supports:
                    if lab in used_levels:
                        continue
                    wick = round((lvl - lo) * 100.0, 2)          # how far below the level
                    if wick < WICK_MIN_CENTS:
                        continue
                    if (cl - lvl) * 100.0 < BODY_MIN_CENTS:       # must close back above
                        continue
                    if best is None or wick > best[0]:
                        best = (wick, "C", lab, lvl, lo - 0.10)   # chart stop just under wick
            if not long_only and (best is None):
                for lab, lvl in dl.resistances:
                    if lab in used_levels:
                        continue
                    wick = round((hi - lvl) * 100.0, 2)
                    if wick < WICK_MIN_CENTS:
                        continue
                    if (lvl - cl) * 100.0 < BODY_MIN_CENTS:       # must close back below
                        continue
                    if best is None or wick > best[0]:
                        best = (wick, "P", lab, lvl, hi + 0.10)
            if best is None:
                continue
            _w, side, lab, lvl, stop = best
            out.append(Signal(bar_idx=int(gidx), side=side, stop_level=float(stop),
                              level_label=lab, level_price=float(lvl),
                              note=f"nlb_{lab}_{side}"))
            used_levels.add(lab)
            fired += 1
    return out


# ── Real-fills sim for one signal list at one (strike,stop,tp1) cell ───────────
@dataclass
class TR:
    date: str
    time_et: str
    side: str
    level: str
    entry_premium: float
    pnl: float
    exit_reason: str


def _fill_signal(sg, spy, ribbon, vix, *, strike_offset, premium_stop_pct, tp1):
    bar = spy.iloc[sg.bar_idx]
    d = bar["timestamp_et"].date()
    spot = float(bar["close"])
    atm = _strike_from_spot(spot)
    target = atm - strike_offset if sg.side == "P" else atm + strike_offset
    strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
    if strike is None:
        return None
    entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
    setup = "NLB_BULLISH" if sg.side == "C" else "NLB_BEARISH"
    fill = simulate_trade_real(
        entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
        rejection_level=sg.stop_level, triggers_fired=[sg.note], side=sg.side,
        qty=QTY, setup=setup, strike_override=strike, entry_vix=entry_vix,
        premium_stop_pct=premium_stop_pct, tp1_premium_pct=tp1,
        tp1_qty_fraction=TP1_QTY, runner_target_premium_pct=RUNNER_TGT,
        profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.0,
        profit_lock_mode="trailing", profit_lock_trail_pct=0.125,
    )
    if fill is None or fill.dollar_pnl is None:
        return None
    return TR(date=str(d), time_et=str(bar["timestamp_et"].time()), side=sg.side,
              level=sg.level_label, entry_premium=round(float(fill.entry_premium), 4),
              pnl=round(float(fill.dollar_pnl), 2),
              exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE")


def simulate_cell(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct, tp1):
    rows = []
    for sg in signals:
        tr = _fill_signal(sg, spy, ribbon, vix, strike_offset=strike_offset,
                          premium_stop_pct=premium_stop_pct, tp1=tp1)
        if tr is not None:
            rows.append(tr)
    return rows


# ── Random-entry NULL: same days/sides/window, random eligible bar, level stop ─
def build_null_signals(signals, spy, day_levels, rng) -> list:
    """For each real signal, draw a RANDOM eligible bar on the SAME day, SAME side,
    stop = the nearest level on that side. Matches days/sides/times (C3/L183)."""
    dl_by_date = {dl.date: dl for dl in day_levels}
    null = []
    for sg in signals:
        d = spy.iloc[sg.bar_idx]["timestamp_et"].date()
        dl = dl_by_date.get(d)
        if dl is None:
            continue
        rth = spy.loc[dl.idx0:dl.idx_last]
        rth = rth[(rth["t"] >= ENTRY_START) & (rth["t"] <= ENTRY_END)]
        if len(rth) == 0:
            continue
        pick = rth.iloc[rng.randrange(len(rth))]
        gidx = int(pick.name)
        cl = float(pick["close"])
        if sg.side == "C":
            cands = [p for _l, p in dl.supports if p < cl]
            stop = (max(cands) if cands else cl - 0.5) - 0.10
        else:
            cands = [p for _l, p in dl.resistances if p > cl]
            stop = (min(cands) if cands else cl + 0.5) + 0.10
        null.append(Signal(bar_idx=gidx, side=sg.side, stop_level=float(stop),
                           level_label="NULL", level_price=cl, note="null"))
    return null


# ── Metrics (OP-20 disclosure) ─────────────────────────────────────────────────
def _q(date_str):
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def metrics(rows: list, regime_by_date: Optional[dict] = None) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]
    by_q = defaultdict(list)
    for r in rows:
        by_q[_q(r.date)].append(r.pnl)
    quarters = {q: round(float(np.mean(v)), 2) for q, v in sorted(by_q.items())}
    q_pos = sum(1 for e in quarters.values() if e > 0)
    by_day = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    tot = sum(by_day.values())
    top5 = (round(100 * sum(sorted(by_day.values(), reverse=True)[:5]) / tot, 1)
            if tot > 0 else None)
    by_side = {}
    for sd in ("C", "P"):
        s = [r.pnl for r in rows if r.side == sd]
        if s:
            by_side[sd] = {"n": len(s), "exp": round(float(np.mean(s)), 2),
                           "wr": round(100 * float((np.array(s) > 0).mean()), 1),
                           "total": round(float(np.sum(s)), 2)}
    out = {
        "n": n, "wr": round(100 * float((pnl > 0).mean()), 1),
        "exp": round(float(pnl.mean()), 2), "total": round(float(pnl.sum()), 2),
        "is_n": len(is_rows), "is_exp": round(float(np.mean([r.pnl for r in is_rows])), 2) if is_rows else None,
        "oos_n": len(oos_rows), "oos_exp": round(float(np.mean([r.pnl for r in oos_rows])), 2) if oos_rows else None,
        "quarters": quarters, "positive_quarters": f"{q_pos}/{len(quarters)}",
        "top5_day_pct": top5, "by_side": by_side,
        "exit_hist": {k: sum(1 for r in rows if r.exit_reason == k)
                      for k in sorted({r.exit_reason for r in rows})},
    }
    if regime_by_date is not None:
        for reg in ("range", "trend"):
            s = [r.pnl for r in rows if regime_by_date.get(r.date) == reg]
            out[f"regime_{reg}"] = ({"n": len(s), "exp": round(float(np.mean(s)), 2),
                                     "wr": round(100 * float((np.array(s) > 0).mean()), 1),
                                     "total": round(float(np.sum(s)), 2)} if s else {"n": 0})
    return out


def walk_forward(rows: list) -> Optional[float]:
    """Chronological 70/30: fraction of OOS that retains IS sign (simple WF proxy).
    Returns OOS_exp / IS_exp clipped to [0,1.5] when both positive, else 0/None."""
    if len(rows) < 10:
        return None
    rs = sorted(rows, key=lambda r: r.date)
    cut = int(len(rs) * 0.70)
    is_e = float(np.mean([r.pnl for r in rs[:cut]]))
    oos_e = float(np.mean([r.pnl for r in rs[cut:]]))
    if is_e <= 0:
        return None
    return round(max(0.0, oos_e) / is_e, 3)


# ── Regime classification: range vs trend day (causal label per date) ──────────
def classify_regime(spy: pd.DataFrame) -> dict:
    """range vs trend by RTH close-to-close net move vs total path (efficiency ratio).
    ER = |last_close - first_close| / sum(|bar-to-bar close move|). High ER = trend."""
    reg = {}
    for d, day in spy.groupby("date", sort=True):
        rth = day[(day["t"] >= RTH_OPEN) & (day["t"] < RTH_CLOSE)]
        if len(rth) < 12:
            continue
        c = rth["close"].values
        net = abs(c[-1] - c[0])
        path = float(np.sum(np.abs(np.diff(c))))
        er = net / path if path > 0 else 0.0
        reg[str(d)] = "trend" if er >= 0.35 else "range"
    return reg


# ── Anchor capture check ───────────────────────────────────────────────────────
def anchor_capture(signals, spy) -> dict:
    """Did the detector fire the two anchor cases (date+approx-time+side)?"""
    hits = {"2026-06-26_long_PML": False, "2026-06-24_short_PMH": False}
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = str(bar["timestamp_et"].date())
        t = bar["timestamp_et"].time()
        if d == "2026-06-26" and sg.side == "C" and dt.time(9, 35) <= t <= dt.time(10, 5):
            hits["2026-06-26_long_PML"] = True
        if d == "2026-06-24" and sg.side == "P" and dt.time(9, 35) <= t <= dt.time(10, 5):
            hits["2026-06-24_short_PMH"] = True
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    print("[nlb] loading SPY+VIX ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 6, 18))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    day_levels = build_day_levels(spy)
    print(f"[nlb] SPY bars={len(spy)} days_with_levels={len(day_levels)} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    regime = classify_regime(spy)

    sig_all = detect_signals(spy, day_levels)
    sig_long = [s for s in sig_all if s.side == "C"]
    sig_short = [s for s in sig_all if s.side == "P"]
    anchors = anchor_capture(sig_all, spy)
    print(f"[nlb] signals: total={len(sig_all)} long={len(sig_long)} short={len(sig_short)}",
          flush=True)
    print(f"[nlb] anchors: {anchors}", flush=True)

    if args.smoke:
        base = dict(strike_offset=-2, premium_stop_pct=-0.99, tp1=0.30)
        rl = simulate_cell(sig_long, spy, ribbon, vix, **base)
        m = metrics(rl, regime)
        print(f"[smoke] LONG ITM-2/chart/tp+30: n={m['n']} exp=${m.get('exp')} "
              f"wr={m.get('wr')} oos_exp={m.get('oos_exp')}", flush=True)
        if m["n"] == 0:
            print("[smoke] FAIL: zero long fills", flush=True)
            return 1
        print("[smoke] PASS", flush=True)
        return 0

    results = {"family": "named_level_bounce", "run_date": dt.date.today().isoformat(),
               "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
               "level_source": "STRUCTURAL PROXY (PDH/PDL/PDC/PMH/PML) — key-levels.json not archived",
               "anchors": anchors, "n_signals": {"total": len(sig_all), "long": len(sig_long),
                                                  "short": len(sig_short)},
               "sweep": {"strike_offsets": STRIKE_OFFSETS, "premium_stops": PREMIUM_STOPS,
                         "tp1_levels": TP1_LEVELS}, "cells": [], "null_seeds": NULL_SEEDS}

    # Pre-build null seed signal lists for the LONG set (the side under test).
    rngs = [random.Random(1000 + i) for i in range(NULL_SEEDS)]
    null_lists_long = [build_null_signals(sig_long, spy, day_levels, r) for r in rngs]

    for so in STRIKE_OFFSETS:
        for ps in PREMIUM_STOPS:
            for tp1 in TP1_LEVELS:
                rl = simulate_cell(sig_long, spy, ribbon, vix,
                                   strike_offset=so, premium_stop_pct=ps, tp1=tp1)
                m = metrics(rl, regime)
                wf = walk_forward(rl)
                # NULL distribution at the SAME cell
                null_exps = []
                for nl in null_lists_long:
                    rn = simulate_cell(nl, spy, ribbon, vix,
                                       strike_offset=so, premium_stop_pct=ps, tp1=tp1)
                    if rn:
                        null_exps.append(float(np.mean([r.pnl for r in rn])))
                null_max = round(max(null_exps), 2) if null_exps else None
                null_mean = round(float(np.mean(null_exps)), 2) if null_exps else None
                null_p95 = round(float(np.percentile(null_exps, 95)), 2) if null_exps else None
                real_exp = m.get("exp")
                beats_null = bool(real_exp is not None and null_max is not None
                                  and real_exp > null_max)
                tier = (f"ITM{abs(so)}" if so < 0 else ("ATM" if so == 0 else f"OTM{so}"))
                cell = {"side": "LONG", "strike_offset": so, "tier": tier,
                        "premium_stop_pct": ps, "tp1": tp1, "metrics": m, "wf": wf,
                        "null_max": null_max, "null_mean": null_mean, "null_p95": null_p95,
                        "beats_null_max": beats_null}
                results["cells"].append(cell)
                print(f"  LONG {tier}/stop{ps}/tp+{int(tp1*100)}: n={m['n']} "
                      f"exp=${real_exp} oos=${m.get('oos_exp')} wr={m.get('wr')} "
                      f"wf={wf} | null_max=${null_max} mean=${null_mean} "
                      f"-> beats_null={beats_null}", flush=True)

    # SHORT side reference (anchor-coverage only; not the side under validation)
    rs = simulate_cell(sig_short, spy, ribbon, vix, strike_offset=-2,
                       premium_stop_pct=-0.99, tp1=0.30)
    results["short_reference_ITM2_chart_tp30"] = metrics(rs, regime)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n[nlb] wrote {OUT}", flush=True)

    # Verdict
    longs = [c for c in results["cells"] if c["side"] == "LONG"]
    beating = [c for c in longs if c["beats_null_max"] and (c["metrics"].get("oos_exp") or -1) > 0]
    print("\n=== NAMED-LEVEL BOUNCE LONG VERDICT ===", flush=True)
    print(f"cells that beat null-MAX AND OOS-positive: {len(beating)}/{len(longs)}", flush=True)
    for c in beating:
        print(f"  {c['tier']}/stop{c['premium_stop_pct']}/tp+{int(c['tp1']*100)}: "
              f"exp=${c['metrics']['exp']} null_max=${c['null_max']} "
              f"oos=${c['metrics']['oos_exp']} wf={c['wf']}", flush=True)
    if not beating:
        print("  NONE beat the random-entry null — exit-structure artifact, not alpha. HOLD.",
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
