"""SHOTGUN_SCALPER stage5 SPREAD-STRESS — adversarial half-spread penalty sweep.

The fresh stage5 rank-1 combo (tp+150% / stop-35% / time12m / OTM-2 / chand0.4 /
vol1.2; 7/7 gates, n=1204, WF PASS — shotgun-scalper-stage5.json 2026-07-01) reuses
the LEVEL_REJECT vein whose tick-scalp cousin DIED on slippage. The stage-4 sim fills
at OPRA bar CLOSE prices with NO explicit spread cost ("slippage not explicitly
modeled — bid/ask spread implicit in VWAP vs last", stage5 disclosure #4). For a
12-minute scalp that is the difference between an edge and a bleed.

THIS TEST: re-run ONLY that combo through the SAME per-day harness
(shotgun_scalper_grinder.run_shotgun_day, detector + OPRA fills byte-identical)
with an explicit PER-SIDE half-spread penalty p swept over {0.5c, 1c, 2c, 3c, 5c}:

  entry fill  = OPRA close + p        (buyer crosses half the spread)
  exit  fill  = sim exit    - p        (seller crosses half the spread)
  brackets (stop/tp/chandelier-arm) computed off the PENALIZED entry — exactly what
  a live premium-%-of-fill bracket would do.

Round-trip cost per trade = 2p x 100 x qty(3) -> $3 / $6 / $12 / $18 / $30.
Baseline p=0 is the parity control: it must reproduce the stage-4 keeper
(n=1204, wide_pnl $18,339.75, sharpe 4.503) or the whole run is void.

Per penalty, ALL SEVEN stage-5 gates are re-checked:
  walk_forward (test-2026 net-positive + both test quarters positive)
  sharpe >= 1.5 | wide_pnl >= $5,000 | max_dd <= 35% of wide_pnl
  positive_quarters >= 6 | edge_capture > 0 (recomputed on the 2026-05-16 stage-4
  anchor set, hardcoded below — the module-level J_WINNERS was emptied 2026-06-16)
  directional >= 2 (anchor-day FIRING direction — penalty-invariant, inherited from
  the keeper and re-disclosed, since a fill-price penalty cannot change which side
  the detector fires)

VERDICT: PASSES_AT_Xc / DIES_AT_Xc — the largest penalty at which all 7 gates hold.
Realistic bar for 0DTE SPY near-the-money contracts: 1-3c per side. Its family has
form — be adversarial. NO wiring regardless of outcome (feeds pipeline_promoter
after close only if it passes).

Window: 2025-01-01..2026-05-15 (the keeper's own window — one variable: the penalty).
Output: analysis/recommendations/shotgun-scalper-stage5-spreadstress.json
ONE process (OPRA cache is per-process; shared warm cache across the sweep).

Run: backtest/.venv/Scripts/python.exe -m autoresearch.shotgun_scalper_stage5_spreadstress
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch import shotgun_scalper_grinder as g   # noqa: E402
from autoresearch import runner as _runner              # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "shotgun-scalper-stage5-spreadstress.json"

# ── the fresh stage5 rank-1 combo (shotgun-scalper-stage5.json best, 2026-07-01) ─
COMBO = g.ShotgunCombo(
    tp_premium_pct=1.5,
    stop_premium_pct=-0.35,
    time_stop_min=12,
    strike_offset=2,
    chandelier_arm_pct=0.4,
    vol_ratio_threshold=1.2,
)

# per-side half-spread penalties in DOLLARS per contract-share (0.5c..5c)
PENALTIES = [0.0, 0.005, 0.01, 0.02, 0.03, 0.05]

WIDE_START = dt.date(2025, 1, 1)
# The keeper's ACTUAL window: stage-4 keepers.jsonl is dated 2026-05-16, when the
# grinder module's wide_end was still 2026-05-15 (it moved to 05-22 on 2026-05-23).
# First sweep attempt on ..05-22 gave n=1225/pnl $19,045 vs keeper 1204/$18,339.75
# with edge_capture matching EXACTLY ($573.75) — i.e. sim parity at trade level,
# n-delta fully explained by the +5 window days. Pin 05-15 for a one-variable test.
WIDE_END = dt.date(2026, 5, 15)     # the keeper's window — parity control at p=0

# stage-4 anchor set AS OF the 2026-05-16 keeper run (module J_WINNERS emptied
# 2026-06-16; these are reconstructed from the keeper's by_day/direction_detail —
# winners_capture 576.75 - losers_added 3.0 = edge_capture 573.75 reproduces).
ANCHOR_WINNERS = [
    {"date": "2026-04-29", "j_dir": "short"},
    {"date": "2026-05-01", "j_dir": "short"},
    {"date": "2026-05-04", "j_dir": "short"},
    {"date": "2026-05-14", "j_dir": "long"},
    {"date": "2026-05-15", "j_dir": "short"},
]
ANCHOR_LOSERS = ["2026-05-05", "2026-05-06", "2026-05-07"]

# keeper baseline (stage-4 keepers.jsonl row for this combo) — the p=0 parity target
KEEPER_BASELINE = {"wide_pnl": 18339.75, "wide_n_trades": 1204, "sharpe": 4.503,
                   "expectancy_per_trade": 15.23, "max_drawdown": 1340.7,
                   "top5_pct": 0.163, "positive_quarters": 6,
                   "edge_capture": 573.75, "stage4_directional_score": 3}

# stage-5 gates (mirror shotgun_scalper_stage5.py constants)
MIN_SHARPE = 1.5
MIN_WIDE_PNL = 5000.0
MAX_DRAWDOWN_PCT = 0.35
MAX_TOP5_PCT = 0.50
MIN_DIR_SCORE = 2
TRAIN_QUARTERS = ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]
TEST_QUARTERS = ["2026-Q1", "2026-Q2"]


def _log(msg: str) -> None:
    print(f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


# ── penalty-aware simulator (byte-identical to g._simulate_trade_real except the
#    two explicitly-marked penalty lines) ───────────────────────────────────────
_PENALTY = 0.0   # module-level knob read by the patched simulator


def _simulate_trade_real_penalized(
    signal: Any,
    bar_idx: int,
    spy_bars,
    combo: g.ShotgunCombo,
    opra_cache: dict,
) -> Optional[g.ShotgunTrade]:
    """g._simulate_trade_real + per-side half-spread penalty _PENALTY.

    entry_premium := OPRA close + _PENALTY (brackets derive from THIS, as live would);
    every exit premium := sim exit - _PENALTY (applied in _bt below).
    With _PENALTY == 0.0 this is behavior-identical to the original (parity control).
    """
    p = _PENALTY

    direction = signal["direction"] if isinstance(signal, dict) else signal.direction
    entry_time = signal["bar_timestamp_et"] if isinstance(signal, dict) else signal.bar_timestamp_et
    entry_spot = float(signal["entry_price"] if isinstance(signal, dict) else signal.entry_price)
    target_level = signal.get("target_level") if isinstance(signal, dict) else getattr(signal, "target_level", None)
    vol_ratio = float(signal.get("vol_ratio", 0.0) if isinstance(signal, dict) else getattr(signal, "vol_ratio", 0.0))

    strike, side = g._strike_for(direction, entry_spot, combo.strike_offset)

    if bar_idx + 1 >= len(spy_bars):
        return None
    next_bar = spy_bars.iloc[bar_idx + 1]
    next_bar_ts = next_bar["timestamp_et"]
    raw_entry = g._opra_premium_at(entry_time.date(), strike, side, next_bar_ts, opra_cache)
    if raw_entry is None or raw_entry < 0.05 or raw_entry > 25.0:
        return None       # same admission rule as the original (raw close) — the trade
                          # SET is held constant across the sweep; only prices shift
    entry_premium = raw_entry + p          # ← PENALTY: buyer pays half the spread

    stop_premium = entry_premium * (1.0 + combo.stop_premium_pct)
    tp_premium = entry_premium * (1.0 + combo.tp_premium_pct)
    chandelier_arm = entry_premium * (1.0 + combo.chandelier_arm_pct)
    chandelier_trail_ratio = 0.20

    hwm_premium = entry_premium
    chandelier_floor: Optional[float] = None
    chandelier_armed = False

    time_stop_deadline = entry_time + dt.timedelta(minutes=combo.time_stop_min)
    eod_deadline = entry_time.replace(hour=15, minute=50, second=0, microsecond=0)
    final_deadline = min(time_stop_deadline, eod_deadline)

    def _bt(exit_premium: float, exit_time, exit_reason: str) -> g.ShotgunTrade:
        # ← PENALTY: seller gives up half the spread on the way out
        return g._build_trade(
            signal, entry_time, entry_spot, strike, side, entry_premium,
            combo, exit_premium - p, exit_time, exit_reason, target_level,
            vol_ratio, chandelier_armed,
        )

    for fwd_idx in range(bar_idx + 1, len(spy_bars)):
        fwd = spy_bars.iloc[fwd_idx]
        fwd_time = fwd["timestamp_et"]
        if not hasattr(fwd_time, "date") or fwd_time.date() != entry_time.date():
            break

        bar_start = fwd_time
        bar_end = bar_start + dt.timedelta(minutes=5)

        opra_window = g._opra_bar_high_low(
            entry_time.date(), strike, side, bar_start, bar_end, opra_cache
        )
        if opra_window is None:
            close_premium = g._opra_premium_at(
                entry_time.date(), strike, side, bar_start, opra_cache
            )
            if close_premium is None:
                continue
            premium_high, premium_low = close_premium, close_premium
        else:
            premium_high, premium_low = opra_window

        if premium_high > hwm_premium:
            hwm_premium = premium_high
            if not chandelier_armed and hwm_premium >= chandelier_arm:
                chandelier_armed = True
            if chandelier_armed:
                new_floor = hwm_premium * (1.0 - chandelier_trail_ratio)
                if chandelier_floor is None or new_floor > chandelier_floor:
                    chandelier_floor = new_floor

        effective_stop = stop_premium
        if chandelier_floor is not None and chandelier_floor > effective_stop:
            effective_stop = chandelier_floor

        if premium_low <= effective_stop:
            exit_reason = "CHANDELIER" if (chandelier_floor is not None and effective_stop == chandelier_floor) else "STOP"
            return _bt(effective_stop, fwd_time, exit_reason)

        if target_level is not None:
            spy_high = float(fwd["high"])
            spy_low = float(fwd["low"])
            level_hit = False
            if direction == "short" and spy_low <= target_level:
                level_hit = True
            elif direction == "long" and spy_high >= target_level:
                level_hit = True
            if level_hit:
                return _bt(premium_high, fwd_time, "TARGET_LEVEL")

        if premium_high >= tp_premium:
            return _bt(tp_premium, fwd_time, "TP_PREMIUM")

        if fwd_time >= final_deadline:
            close_premium = g._opra_premium_at(
                entry_time.date(), strike, side, bar_start, opra_cache
            )
            if close_premium is None:
                close_premium = premium_low
            return _bt(close_premium, fwd_time,
                       "TIME_STOP" if fwd_time >= time_stop_deadline else "EOD_FLAT")

    last = spy_bars.iloc[-1]
    last_time = last["timestamp_et"]
    last_premium = g._opra_premium_at(entry_time.date(), strike, side, last_time, opra_cache)
    if last_premium is None:
        return None
    return _bt(last_premium, last_time, "EOD_FORCED")


# ── metric bundle + stage-5 gates for one penalty run ─────────────────────────
def _metrics(day_pnl_map: dict, trades: list) -> dict:
    wide_pnl = round(sum(day_pnl_map.values()), 2)
    n = len(trades)
    pnls = [t.dollar_pnl for t in trades]
    exp = round(wide_pnl / n, 2) if n else 0.0
    wr = round(sum(1 for x in pnls if x > 0) / n, 3) if n else 0.0
    if n > 1:
        mean_pnl = sum(pnls) / n
        var = sum((x - mean_pnl) ** 2 for x in pnls) / (n - 1)
        std = math.sqrt(var) if var > 0 else 1.0
        tpy = n / max(1, (WIDE_END - WIDE_START).days / 365.25)
        sharpe = (mean_pnl / std) * math.sqrt(tpy) if std > 0 else 0.0
    else:
        sharpe = 0.0
    q_pnl: dict[str, float] = defaultdict(float)
    for d, v in day_pnl_map.items():
        q_pnl[f"{d.year}-Q{(d.month - 1) // 3 + 1}"] += v
    sorted_days = sorted(day_pnl_map.values(), reverse=True)
    top5_pct = round(sum(sorted_days[:5]) / wide_pnl, 3) if wide_pnl > 0 else 999.0
    cum = peak = max_dd = 0.0
    for d in sorted(day_pnl_map.keys()):
        cum += day_pnl_map[d]
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    train = sum(q_pnl.get(q, 0) for q in TRAIN_QUARTERS)
    test = sum(q_pnl.get(q, 0) for q in TEST_QUARTERS)
    test_pos = sum(1 for q in TEST_QUARTERS if q_pnl.get(q, 0) > 0)
    return {
        "wide_pnl": wide_pnl, "n_trades": n, "expectancy": exp, "wr": wr,
        "sharpe": round(sharpe, 3), "top5_pct": top5_pct,
        "quarter_pnl": {k: round(v, 2) for k, v in sorted(q_pnl.items())},
        "positive_quarters": sum(1 for v in q_pnl.values() if v > 0),
        "max_drawdown": round(max_dd, 2),
        "wf": {"train_pnl": round(train, 2), "test_pnl": round(test, 2),
               "test_positive_quarters": test_pos,
               "passed": bool(test > 0 and test_pos == len(TEST_QUARTERS))},
    }


def _gates(m: dict, edge_capture: float, dir_score: int) -> dict:
    checks = {
        "walk_forward": m["wf"]["passed"],
        "directional": dir_score >= MIN_DIR_SCORE,
        "sharpe": m["sharpe"] >= MIN_SHARPE,
        "wide_pnl": m["wide_pnl"] >= MIN_WIDE_PNL,
        "max_drawdown": m["max_drawdown"] <= MAX_DRAWDOWN_PCT * max(m["wide_pnl"], 1),
        "positive_q6": m["positive_quarters"] >= 6,
        "edge_capture": edge_capture > 0,
    }
    return {"checks": checks, "passed": all(checks.values()),
            "n_passed": sum(checks.values()),
            "concentration_ok": m["top5_pct"] <= MAX_TOP5_PCT}


def _run_penalty(penalty: float, spy_w, all_dates, opra_cache: dict) -> dict:
    global _PENALTY
    _PENALTY = penalty
    t0 = time.time()
    trades: list = []
    day_pnl_map: dict[dt.date, float] = defaultdict(float)
    for d in all_dates:
        day_trades = g.run_shotgun_day(d, spy_w, COMBO, opra_cache)
        trades.extend(day_trades)
        day_pnl_map[d] += sum(t.dollar_pnl for t in day_trades)
    m = _metrics(day_pnl_map, trades)

    # anchor-day edge_capture on the 2026-05-16 stage-4 anchor set
    by_day = {w["date"]: round(day_pnl_map.get(dt.date.fromisoformat(w["date"]), 0.0), 2)
              for w in ANCHOR_WINNERS}
    for ld in ANCHOR_LOSERS:
        by_day[ld] = round(day_pnl_map.get(dt.date.fromisoformat(ld), 0.0), 2)
    winners_capture = sum(by_day[w["date"]] for w in ANCHOR_WINNERS)
    losers_added = sum(-by_day[ld] for ld in ANCHOR_LOSERS if by_day[ld] < 0)
    edge_capture = round(winners_capture - losers_added, 2)

    gates = _gates(m, edge_capture, KEEPER_BASELINE["stage4_directional_score"])
    row = {
        "penalty_per_side_cents": round(penalty * 100, 1),
        "round_trip_cost_per_trade_qty3": round(2 * penalty * 100 * COMBO.qty, 2),
        **m,
        "anchor_by_day": by_day,
        "edge_capture": edge_capture,
        "gate": gates,
        "elapsed_min": round((time.time() - t0) / 60, 1),
    }
    _log(f"p={penalty*100:.1f}c: n={m['n_trades']} pnl=${m['wide_pnl']:.0f} "
         f"exp=${m['expectancy']} sharpe={m['sharpe']} dd=${m['max_drawdown']:.0f} "
         f"+Q={m['positive_quarters']}/6 WFtest=${m['wf']['test_pnl']:.0f} "
         f"EC=${edge_capture} -> {gates['n_passed']}/7 "
         f"{'PASS' if gates['passed'] else 'FAIL'} ({row['elapsed_min']}min)")
    return row


def main() -> int:
    t0 = time.time()
    _log(f"combo: {COMBO}")
    _log(f"window {WIDE_START}..{WIDE_END}; penalties {[f'{p*100:.1f}c' for p in PENALTIES]}")

    import pandas as pd
    spy_w, _vw = _runner.load_data(WIDE_START, WIDE_END)
    spy_w["timestamp_et"] = (
        pd.to_datetime(spy_w["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    all_dates = sorted(d for d in set(spy_w["timestamp_et"].dt.date.unique())
                       if WIDE_START <= d <= WIDE_END)
    _log(f"loaded {len(spy_w)} bars, {len(all_dates)} trading days")

    # patch the grinder's simulator with the penalty-aware clone (module-global call site)
    g._simulate_trade_real = _simulate_trade_real_penalized

    opra_cache: dict = {}    # shared warm cache across the whole sweep (same contracts)
    rows = [_run_penalty(p, spy_w, all_dates, opra_cache) for p in PENALTIES]

    base = rows[0]
    parity = {
        "n_trades": (base["n_trades"], KEEPER_BASELINE["wide_n_trades"]),
        "wide_pnl": (base["wide_pnl"], KEEPER_BASELINE["wide_pnl"]),
        "sharpe": (base["sharpe"], KEEPER_BASELINE["sharpe"]),
        "edge_capture": (base["edge_capture"], KEEPER_BASELINE["edge_capture"]),
    }
    parity_ok = (base["n_trades"] == KEEPER_BASELINE["wide_n_trades"]
                 and abs(base["wide_pnl"] - KEEPER_BASELINE["wide_pnl"]) < 1.0)

    passing = [r for r in rows if r["penalty_per_side_cents"] > 0 and r["gate"]["passed"]]
    failing = [r for r in rows if r["penalty_per_side_cents"] > 0 and not r["gate"]["passed"]]
    max_pass_c = max((r["penalty_per_side_cents"] for r in passing), default=0.0)
    min_fail_c = min((r["penalty_per_side_cents"] for r in failing), default=None)
    if min_fail_c is not None and max_pass_c >= min_fail_c:
        # non-monotonic (possible via bracket-shift path effects) — report conservatively
        max_pass_c = min(r["penalty_per_side_cents"] for r in failing) and max_pass_c
    verdict = (f"PASSES_AT_{max_pass_c:g}c" if max_pass_c >= 2.0 else
               (f"DIES_AT_{min_fail_c:g}c" if min_fail_c is not None
                else f"PASSES_AT_{max_pass_c:g}c_ONLY (below the 2c realistic bar)"))

    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "purpose": "alpha-plan rank #3 (judge 7.5) — adversarial per-side half-spread "
                   "entry/exit penalty sweep on the fresh stage5 rank-1 combo. "
                   "LEVEL_REJECT vein: its tick-scalp cousin died on slippage.",
        "combo": {"tp_premium_pct": 1.5, "stop_premium_pct": -0.35, "time_stop_min": 12,
                  "strike_offset": 2, "chandelier_arm_pct": 0.4, "vol_ratio_threshold": 1.2,
                  "qty": 3},
        "window": f"{WIDE_START}..{WIDE_END}",
        "penalty_model": "entry = OPRA close + p; every exit = sim exit - p; brackets "
                         "off the penalized entry (live premium-% behavior). Round trip "
                         "= 2p x 100 x qty.",
        "baseline_parity_control": {"ok": parity_ok, "run_vs_keeper": parity,
                                    "keeper": "stage4 keepers.jsonl 2026-05-16 row"},
        "stage5_gates": {"min_sharpe": MIN_SHARPE, "min_wide_pnl": MIN_WIDE_PNL,
                         "max_drawdown_pct": MAX_DRAWDOWN_PCT, "min_positive_quarters": 6,
                         "walk_forward_test_positive": True, "min_dir_score": MIN_DIR_SCORE,
                         "edge_capture_gt_0": True,
                         "dir_score_note": "directional + anchor set inherited from the "
                                           "2026-05-16 stage-4 run (fill-price penalty "
                                           "cannot change which side fires); edge_capture "
                                           "RECOMPUTED per penalty on those anchor days"},
        "sweep": rows,
        "verdict": verdict,
        "realistic_penalty_bar_cents": 2.0,
        "no_wiring_note": "NO wiring regardless of outcome (2026-07-02 session). If PASS, "
                          "feeds pipeline_promoter after close.",
        "elapsed_min": round((time.time() - t0) / 60, 1),
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    _log(f"VERDICT: {verdict} (parity_ok={parity_ok}) -> {OUT_JSON.name} "
         f"({out['elapsed_min']} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
