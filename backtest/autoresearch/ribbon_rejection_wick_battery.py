"""RIBBON_REJECTION_WICK — full canonical battery on OPRA REAL FILLS.

Window: 2025-01-02 .. 2026-07-01 (OPRA cache coverage ends 2026-07-01).
P&L authority: real OPRA contract bars (backtest/data/options/) via the
battle-tested fill walker in autoresearch.shotgun_scalper_grinder
(_simulate_trade_real) — NO Black-Scholes anywhere.

Design (efficiency without integrity loss):
  1. SUPERSET SCAN — run the detector once per bar with the loosest grid
     corner, recording every event WITH its features (wick_frac,
     bars_since_break, vol_break_ratio, stack_flipped).
  2. SIMULATE each unique event ONCE (fixed exits — exits are NOT gridded).
  3. COMBOS = post-hoc feature filters over the event list (24 combos,
     <= 36 per spec), with per-combo chronological non-overlap + max 3/day.
  4. BATTERY per combo: N, WR, expectancy, OOS split (IS 2025 / OOS 2026),
     drop-top3, both-halves, slippage breakeven, per-direction split,
     random-entry null bootstrap p-value; BH-FDR across combos (alpha=0.10).

Fixed exits (disclosed, sensible for J's 30-60 min rejection->dump thesis):
  ATM strike (offset 0), qty=3, TP +50% premium, catastrophe stop -30%,
  chandelier arms at +25% and trails 20% off HWM, time stop 60 min,
  EOD flat 15:50. Entry = next 5m bar (OPRA close of first bar at/after).

CLI:
    backtest/.venv/Scripts/python.exe backtest/autoresearch/ribbon_rejection_wick_battery.py
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent      # backtest/
PROJECT_ROOT = REPO.parent                          # 42/
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(PROJECT_ROOT))

from lib.ribbon import compute_ribbon  # noqa: E402
from lib.watchers.ribbon_rejection_wick_detector import (  # noqa: E402
    SUPERSET_PARAMS,
    detect_both,
)
from autoresearch import shotgun_scalper_grinder as g  # noqa: E402  (real-fills walker)

DATA = REPO / "data"
OUT_SCORECARD = PROJECT_ROOT / "analysis" / "recommendations" / "ribbon-rejection-wick.json"
OUT_EVENTS = REPO / "autoresearch" / "_state" / "ribbon_rejection_wick_events.jsonl"

WINDOW_START = dt.date(2025, 1, 2)
WINDOW_END = dt.date(2026, 7, 1)          # OPRA cache coverage ends here
OOS_CUT = dt.date(2026, 1, 1)             # IS: 2025 (12mo) | OOS: 2026-01..2026-07 (6mo)

ENTRY_START = dt.time(9, 45)
ENTRY_END = dt.time(15, 0)
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)

MAX_TRADES_PER_DAY = 3
NULL_ENTRIES_PER_DAY = 2
NULL_BOOTSTRAP_ITERS = 2000
RNG_SEED = 42
FDR_ALPHA = 0.10

# Fixed exit knobs → grinder combo (exits NOT gridded; strike ATM).
FIXED_EXITS = dict(
    tp_premium_pct=0.50,
    stop_premium_pct=-0.30,
    time_stop_min=60,
    strike_offset=0,
    chandelier_arm_pct=0.25,
    vol_ratio_threshold=0.0,  # unused here — filtering happens combo-side
    qty=3,
)

# ── Grid: 2 x 2 x 3 x 2 = 24 combos (<= 36 per spec) ────────────────────────
WICK_FRACS = [0.35, 0.50]
BREAK_LOOKBACKS = [6, 12]
VOL_MULTS = [0.0, 1.5, 2.5]   # 1.5 keeps today's anchor (IEX volx=1.8); 2.5 stricter
STACK_FILTERS = ["not_flipped", "any"]


def load_master() -> pd.DataFrame:
    """Concat the two masters covering 2025-01..2026-07, tz-normalize, RTH-only."""
    paths = [
        DATA / "spy_5m_2025-01-01_2026-06-18.csv",
        DATA / "spy_5m_2026-05-19_2026-07-01.csv",
    ]
    frames = []
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(p)
        frames.append(pd.read_csv(p))
    df = pd.concat(frames, ignore_index=True)
    df["timestamp_et"] = (
        pd.to_datetime(df["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    df = df.drop_duplicates(subset="timestamp_et").sort_values("timestamp_et")
    t = df["timestamp_et"].dt.time
    df = df[(t >= RTH_OPEN) & (t < RTH_CLOSE)]
    return df.reset_index(drop=True)


def load_vix() -> pd.DataFrame | None:
    frames = []
    for name in ("vix_5m_2025-01-01_2026-06-18.csv", "vix_5m_2026-05-19_2026-07-01.csv"):
        p = DATA / name
        if p.exists():
            frames.append(pd.read_csv(p))
    if not frames:
        return None
    v = pd.concat(frames, ignore_index=True)
    v["timestamp_et"] = (
        pd.to_datetime(v["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    v = v.drop_duplicates(subset="timestamp_et").sort_values("timestamp_et")
    return v.reset_index(drop=True)


def vix_at(vix: pd.DataFrame | None, ts) -> float | None:
    if vix is None:
        return None
    prior = vix[vix["timestamp_et"] <= ts]
    if prior.empty:
        return None
    return float(prior.iloc[-1]["close"])


# ── Stage 1: superset event scan ─────────────────────────────────────────────

def superset_scan(spy: pd.DataFrame, vix: pd.DataFrame | None) -> list[dict]:
    ribbon = compute_ribbon(spy["close"])
    times = spy["timestamp_et"]
    events: list[dict] = []
    in_window = (times.dt.time >= ENTRY_START) & (times.dt.time <= ENTRY_END) & \
                (times.dt.date >= WINDOW_START) & (times.dt.date <= WINDOW_END)
    idxs = spy.index[in_window].tolist()
    t0 = time.time()
    for n, i in enumerate(idxs):
        if n % 5000 == 0:
            print(f"  scan {n}/{len(idxs)} bars  events={len(events)}  "
                  f"{time.time()-t0:.0f}s", flush=True)
        for sig in detect_both(spy, i, SUPERSET_PARAMS, ribbon_df=ribbon):
            ts = times.iloc[i]
            events.append({
                "bar_idx": int(i),
                "date": ts.date().isoformat(),
                "ts": ts.isoformat(),
                "direction": "short" if sig["direction"] == "bearish" else "long",
                "entry_price": float(spy.iloc[i]["close"]),
                "wick_frac": sig["wick_frac"],
                "bars_since_break": sig["bars_since_break"],
                "vol_break_ratio": sig["vol_break_ratio"],
                "vol_is_day_max": sig["vol_is_day_max"],
                "stack_flipped": sig["stack_flipped"],
                "stack": sig["stack_at_signal"],
                "vix": vix_at(vix, ts),
            })
    print(f"  scan done: {len(idxs)} bars -> {len(events)} superset events "
          f"({time.time()-t0:.0f}s)", flush=True)
    return events


# ── Stage 2: simulate each unique event once (fixed exits, OPRA real fills) ──

def simulate_events(events: list[dict], spy: pd.DataFrame) -> dict[tuple, dict | None]:
    combo = g.ShotgunCombo(**FIXED_EXITS)
    opra_cache: dict = {}
    sims: dict[tuple, dict | None] = {}
    t0 = time.time()
    for n, ev in enumerate(events):
        key = (ev["date"], ev["ts"], ev["direction"])
        if key in sims:
            continue
        if n % 200 == 0:
            print(f"  sim {n}/{len(events)}  {time.time()-t0:.0f}s", flush=True)
        signal = {
            "direction": ev["direction"],
            "bar_timestamp_et": pd.Timestamp(ev["ts"]),
            "entry_price": ev["entry_price"],
            "target_level": None,
            "vol_ratio": ev["vol_break_ratio"],
        }
        try:
            tr = g._simulate_trade_real(signal, ev["bar_idx"], spy, combo, opra_cache)
        except Exception as exc:  # noqa: BLE001 — one bad contract must not kill the battery
            print(f"  sim error {key}: {exc!r}", flush=True)
            tr = None
        if tr is None:
            sims[key] = None
        else:
            sims[key] = {
                "pnl": tr.dollar_pnl,
                "entry_premium": tr.entry_premium,
                "exit_premium": tr.exit_premium,
                "exit_reason": tr.exit_reason,
                "exit_time": tr.exit_time_et.isoformat(),
                "strike": tr.strike,
                "side": tr.side,
            }
    print(f"  sims done: {len(sims)} unique ({time.time()-t0:.0f}s)", flush=True)
    return sims


def build_null_pool(events: list[dict], spy: pd.DataFrame) -> dict[str, list[float]]:
    """Random-entry null: same days as events, random bars, same fixed exits."""
    rng = random.Random(RNG_SEED)
    combo = g.ShotgunCombo(**FIXED_EXITS)
    opra_cache: dict = {}
    times = spy["timestamp_et"]
    by_day_dir: set[tuple[str, str]] = {(e["date"], e["direction"]) for e in events}
    pool: dict[str, list[float]] = {"short": [], "long": []}
    t0 = time.time()
    for n, (day, direction) in enumerate(sorted(by_day_dir)):
        if n % 100 == 0:
            print(f"  null {n}/{len(by_day_dir)}  {time.time()-t0:.0f}s", flush=True)
        d = dt.date.fromisoformat(day)
        day_mask = (times.dt.date == d) & (times.dt.time >= ENTRY_START) & (times.dt.time <= ENTRY_END)
        day_idxs = spy.index[day_mask].tolist()
        if len(day_idxs) < 4:
            continue
        for _ in range(NULL_ENTRIES_PER_DAY):
            i = rng.choice(day_idxs)
            signal = {
                "direction": direction,
                "bar_timestamp_et": times.iloc[i],
                "entry_price": float(spy.iloc[i]["close"]),
                "target_level": None,
                "vol_ratio": 0.0,
            }
            try:
                tr = g._simulate_trade_real(signal, i, spy, combo, opra_cache)
            except Exception:  # noqa: BLE001
                tr = None
            if tr is not None:
                pool[direction].append(tr.dollar_pnl)
    print(f"  null pool: short n={len(pool['short'])} long n={len(pool['long'])} "
          f"({time.time()-t0:.0f}s)", flush=True)
    return pool


# ── Stage 3: combos + battery stats ──────────────────────────────────────────

def combo_filter(ev: dict, wick: float, lookback: int, vol: float, stack: str) -> bool:
    if ev["wick_frac"] < wick:
        return False
    if ev["bars_since_break"] > lookback:
        return False
    if vol > 0 and ev["vol_break_ratio"] < vol:
        return False
    if stack == "not_flipped" and ev["stack_flipped"]:
        return False
    return True


def select_trades(events: list[dict], sims: dict, wick, lookback, vol, stack) -> list[dict]:
    """Chronological non-overlap + max/day; returns trades with pnl attached."""
    picked: list[dict] = []
    last_exit: pd.Timestamp | None = None
    per_day: dict[str, int] = defaultdict(int)
    for ev in sorted(events, key=lambda e: e["ts"]):
        if not combo_filter(ev, wick, lookback, vol, stack):
            continue
        if per_day[ev["date"]] >= MAX_TRADES_PER_DAY:
            continue
        ts = pd.Timestamp(ev["ts"])
        if last_exit is not None and ts < last_exit:
            continue
        sim = sims.get((ev["date"], ev["ts"], ev["direction"]))
        if sim is None:
            continue  # no OPRA fill — disclosed via opra_miss count
        picked.append({**ev, **sim})
        per_day[ev["date"]] += 1
        last_exit = pd.Timestamp(sim["exit_time"])
    return picked


def _stats(pnls: list[float]) -> dict:
    n = len(pnls)
    if n == 0:
        return {"n": 0, "pnl": 0.0, "wr": 0.0, "expectancy": 0.0}
    total = sum(pnls)
    return {
        "n": n,
        "pnl": round(total, 2),
        "wr": round(sum(1 for p in pnls if p > 0) / n, 3),
        "expectancy": round(total / n, 2),
    }


def bootstrap_p(trade_pnls: list[float], n_short: int, n_long: int,
                null_pool: dict[str, list[float]], rng: random.Random) -> float:
    """One-sided p: how often does a direction-matched random-entry sample
    beat the combo's mean P&L?"""
    if not trade_pnls:
        return 1.0
    mean_obs = sum(trade_pnls) / len(trade_pnls)
    ps, pl = null_pool["short"], null_pool["long"]
    if (n_short > 0 and not ps) or (n_long > 0 and not pl):
        return 1.0
    hits = 0
    for _ in range(NULL_BOOTSTRAP_ITERS):
        s = [rng.choice(ps) for _ in range(n_short)] + [rng.choice(pl) for _ in range(n_long)]
        if sum(s) / len(s) >= mean_obs:
            hits += 1
    return hits / NULL_BOOTSTRAP_ITERS


def evaluate_combo(events, sims, null_pool, wick, lookback, vol, stack, rng) -> dict:
    trades = select_trades(events, sims, wick, lookback, vol, stack)
    pnls = [t["pnl"] for t in trades]
    full = _stats(pnls)

    shorts = [t for t in trades if t["direction"] == "short"]
    longs = [t for t in trades if t["direction"] == "long"]

    is_trades = [t for t in trades if dt.date.fromisoformat(t["date"]) < OOS_CUT]
    oos_trades = [t for t in trades if dt.date.fromisoformat(t["date"]) >= OOS_CUT]

    # drop-top3: remove the 3 largest winners; does the edge survive?
    drop3 = sorted(pnls, reverse=True)[3:] if len(pnls) > 3 else []
    # both-halves: split at median trade date
    if trades:
        dates = sorted(t["date"] for t in trades)
        mid = dates[len(dates) // 2]
        h1 = [t["pnl"] for t in trades if t["date"] < mid]
        h2 = [t["pnl"] for t in trades if t["date"] >= mid]
    else:
        h1, h2 = [], []

    # Slippage breakeven: cents of per-side premium slippage that zero the edge.
    qty = FIXED_EXITS["qty"]
    slip_be_cents = (full["expectancy"] / (qty * 100 * 2)) * 100 if full["n"] else 0.0

    p_null = bootstrap_p(pnls, len(shorts), len(longs), null_pool, rng)

    # exit-reason mix (dead-knob visibility per C14/C30)
    reasons: dict[str, int] = defaultdict(int)
    for t in trades:
        reasons[t["exit_reason"]] += 1

    # VIX buckets (info)
    vix_b: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        v = t.get("vix")
        b = ("na" if v is None else "<17" if v < 17 else "17-20" if v < 20
             else "20-25" if v < 25 else ">=25")
        vix_b[b].append(t["pnl"])

    return {
        "combo": {"wick_frac_min": wick, "break_lookback_bars": lookback,
                  "vol_mult_min": vol, "stack_filter": stack},
        "full": full,
        "short": _stats([t["pnl"] for t in shorts]),
        "long": _stats([t["pnl"] for t in longs]),
        "is": _stats([t["pnl"] for t in is_trades]),
        "oos": _stats([t["pnl"] for t in oos_trades]),
        "drop_top3_pnl": round(sum(drop3), 2) if drop3 else 0.0,
        "half1": _stats(h1),
        "half2": _stats(h2),
        "slippage_breakeven_cents_per_side": round(slip_be_cents, 2),
        "p_null": round(p_null, 4),
        "exit_reasons": dict(reasons),
        "vix_buckets": {k: _stats(v) for k, v in sorted(vix_b.items())},
        "n_days_traded": len({t["date"] for t in trades}),
    }


def bh_fdr(results: list[dict], alpha: float = FDR_ALPHA) -> None:
    """Benjamini-Hochberg across combos; annotates results in place."""
    m = len(results)
    order = sorted(range(m), key=lambda i: results[i]["p_null"])
    thresh_rank = 0
    for rank, i in enumerate(order, start=1):
        if results[i]["p_null"] <= rank / m * alpha:
            thresh_rank = rank
    for rank, i in enumerate(order, start=1):
        results[i]["bh_fdr_survivor"] = rank <= thresh_rank
        results[i]["bh_rank"] = rank


def combo_clears(r: dict) -> tuple[bool, list[str]]:
    fails = []
    if r["full"]["n"] < 30:
        fails.append(f"n {r['full']['n']} < 30")
    if r["full"]["expectancy"] <= 0:
        fails.append(f"expectancy {r['full']['expectancy']} <= 0")
    if r["oos"]["n"] < 10:
        fails.append(f"oos_n {r['oos']['n']} < 10")
    if r["oos"]["expectancy"] <= 0:
        fails.append(f"oos_expectancy {r['oos']['expectancy']} <= 0")
    if r["drop_top3_pnl"] <= 0:
        fails.append(f"drop_top3 {r['drop_top3_pnl']} <= 0")
    if r["half1"]["pnl"] <= 0 or r["half2"]["pnl"] <= 0:
        fails.append(f"halves {r['half1']['pnl']}/{r['half2']['pnl']} not both > 0")
    if r["p_null"] > 0.05:
        fails.append(f"p_null {r['p_null']} > 0.05")
    if not r.get("bh_fdr_survivor"):
        fails.append("BH-FDR non-survivor")
    if r["slippage_breakeven_cents_per_side"] < 2.0:
        fails.append(f"slip_breakeven {r['slippage_breakeven_cents_per_side']}c < 2c")
    if r["short"]["n"] > 0 and r["short"]["expectancy"] <= 0:
        fails.append(f"bear-side expectancy {r['short']['expectancy']} <= 0")
    return (len(fails) == 0, fails)


def main() -> int:
    print("=== RIBBON_REJECTION_WICK battery ===", flush=True)
    spy = load_master()
    vix = load_vix()
    print(f"master: {len(spy)} RTH bars {spy['timestamp_et'].iloc[0]} .. "
          f"{spy['timestamp_et'].iloc[-1]}  vix={'ok' if vix is not None else 'MISSING'}",
          flush=True)

    print("[1/4] superset scan", flush=True)
    events = superset_scan(spy, vix)
    OUT_EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with OUT_EVENTS.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")

    print("[2/4] OPRA real-fills sims", flush=True)
    sims = simulate_events(events, spy)
    opra_miss = sum(1 for v in sims.values() if v is None)
    print(f"  OPRA coverage: {len(sims) - opra_miss}/{len(sims)} events fillable "
          f"({opra_miss} missing)", flush=True)

    print("[3/4] random-entry null pool", flush=True)
    null_pool = build_null_pool(events, spy)
    null_exp = {k: (round(sum(v) / len(v), 2) if v else None) for k, v in null_pool.items()}

    print("[4/4] combo battery", flush=True)
    rng = random.Random(RNG_SEED + 1)
    results = []
    for wick, lb, vol, stack in itertools.product(
        WICK_FRACS, BREAK_LOOKBACKS, VOL_MULTS, STACK_FILTERS
    ):
        results.append(evaluate_combo(events, sims, null_pool, wick, lb, vol, stack, rng))
    bh_fdr(results)
    for r in results:
        ok, fails = combo_clears(r)
        r["clears"] = ok
        r["fails"] = fails

    results.sort(key=lambda r: (r["clears"], r["full"]["expectancy"] * math.log(max(2, r["full"]["n"]))),
                 reverse=True)

    survivors = [r for r in results if r["clears"]]
    verdict = "CLEARS" if survivors else "FAIL"

    scorecard = {
        "rule_id": "ribbon-rejection-wick",
        "setup_name": "RIBBON_REJECTION_WICK",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "spec_origin": "J live read 2026-07-02 ~11:00 ET — 10:30/10:35 ribbon wick rejections, "
                       "30 min before the 11:00 confirmatory ribbon flip",
        "window": {"start": WINDOW_START.isoformat(), "end": WINDOW_END.isoformat(),
                   "oos_cut": OOS_CUT.isoformat()},
        "pnl_authority": "OPRA real fills (backtest/data/options), entry next-5m-bar, "
                         "shotgun_scalper_grinder._simulate_trade_real walker",
        "fixed_exits": FIXED_EXITS,
        "grid": {"wick_frac_min": WICK_FRACS, "break_lookback_bars": BREAK_LOOKBACKS,
                 "vol_mult_min": VOL_MULTS, "stack_filter": STACK_FILTERS,
                 "n_combos": len(results)},
        "superset_events": len(events),
        "opra_missing_events": opra_miss,
        "null_expectancy_per_direction": null_exp,
        "null_pool_n": {k: len(v) for k, v in null_pool.items()},
        "fdr": {"method": "benjamini-hochberg", "alpha": FDR_ALPHA,
                "survivors": sum(1 for r in results if r.get("bh_fdr_survivor"))},
        "anchor_case_2026_07_02": {
            "requirement": "bearish fire at 10:30 and/or 10:35 ET on today's live bars",
            "result": "HIT — bearish fires 10:25 / 10:30 / 10:40 ET (10:35 closed back "
                      "inside band on IEX feed); 3 fires total (<=5 gate PASS); "
                      "stack=BULL at all fires (not yet flipped — J's anticipatory case)",
            "fixture": "backtest/tests/fixtures/spy_5m_2026-07-02_anchor.csv",
            "checker": "backtest/autoresearch/ribbon_rejection_wick_anchor_today.py",
        },
        "verdict": verdict,
        "combos": results,
    }
    OUT_SCORECARD.parent.mkdir(parents=True, exist_ok=True)
    OUT_SCORECARD.write_text(json.dumps(scorecard, indent=1), encoding="utf-8")
    print(f"\nscorecard -> {OUT_SCORECARD}", flush=True)

    print(f"\nVERDICT: {verdict}  (survivors: {len(survivors)}/{len(results)})")
    for r in results[:8]:
        c = r["combo"]
        print(f"  wick>={c['wick_frac_min']} lb<={c['break_lookback_bars']} "
              f"vol>={c['vol_mult_min']} {c['stack_filter']:11s} | "
              f"N={r['full']['n']:4d} WR={r['full']['wr']:.2f} "
              f"exp=${r['full']['expectancy']:7.2f} pnl=${r['full']['pnl']:9.2f} | "
              f"OOS N={r['oos']['n']:3d} exp=${r['oos']['expectancy']:7.2f} | "
              f"p={r['p_null']:.3f} fdr={'Y' if r.get('bh_fdr_survivor') else 'N'} "
              f"{'CLEARS' if r['clears'] else 'fail: ' + '; '.join(r['fails'][:2])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
