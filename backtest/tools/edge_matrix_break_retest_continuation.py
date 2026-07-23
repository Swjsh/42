"""edge_matrix_break_retest_continuation.py -- pre-registered BREAK + RETEST CONTINUATION
edge-matrix runner (family: break-retest-continuation, 2026-07-23 fire).

PRE-REGISTRATION (frozen BEFORE any run -- the grid, gates, and every fixed rule):
    analysis/edge-matrix/prereg-break-retest-continuation-2026-07-23.json

WHAT THIS TESTS (J, dojo 2026-07-17: "13:50 is a nice break and then retest"):
  A closed-bar BREAK of a live-engine LevelMemory level, then a RETEST of that level's
  ZONE within a bounded number of bars, then continuation in the break direction.
  Both directions: up-break+retest -> CALL, down-break+retest -> PUT.

HARD CONTRACT (shared edge-matrix protocol):
  - Detector is CAUSAL (bar i uses only bars <= i; C6). Break detection reads the level
    set as of the bar BEFORE the break bar. Runtime truncation assert included.
  - Levels come from the LIVE engine's LevelMemory (backtest/lib/watchers/level_memory.py),
    engine constants untouched. Zones (retest_band), never penny-exact.
  - Exits are the LIVE RIBBON_RIDE shape walked through the REAL exit_manager decision
    core via backtest/lib/exit_manager_walk.py. ENTRY-side tuning only.
  - Dollars are real OPRA fills only (backtest/data/options/). No BS-synthetic anywhere;
    unfillable signals are excluded from gate math and disclosed as skips.
  - Held-out = inventory heldout_days (last 25% of OPRA days by date). Tune metrics never
    read them; the frozen grid is evaluated on them exactly once for held_out_total.
  - NO live wiring, NO commits, NO broker imports.

Run (backtest venv):
    backtest/.venv/Scripts/python.exe backtest/tools/edge_matrix_break_retest_continuation.py
Options: --limit-days N (timing probe), --rebuild-cache, --cache-dir PATH
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BACKTEST = ROOT / "backtest"
if str(BACKTEST) not in sys.path:
    sys.path.insert(0, str(BACKTEST))

from lib.watchers.level_memory import LevelMemory, CLUSTER_TOL  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib import exit_manager_walk as emw  # noqa: E402  (also puts fleet dir on sys.path)
from lib.option_pricing_real import option_symbol, CACHE_DIR as OPT_DIR  # noqa: E402

import exit_manager as em  # noqa: E402  (fleet dir, via exit_manager_walk's sys.path insert)
import strategies as fleet_strategies  # noqa: E402

ET_TZ = "America/New_York"
INVENTORY = ROOT / "analysis" / "edge-matrix" / "day-inventory-2026-07-23.json"
PREREG = ROOT / "analysis" / "edge-matrix" / "prereg-break-retest-continuation-2026-07-23.json"
EPISODES_OUT = ROOT / "analysis" / "edge-matrix" / "break-retest-continuation-episodes.json"
RESULTS_OUT = ROOT / "analysis" / "edge-matrix" / "break-retest-continuation-results.json"
PARAMS_JSON = ROOT / "automation" / "state" / "params.json"

DEFAULT_CACHE_DIR = Path(os.environ.get(
    "EDGE_MATRIX_CACHE",
    r"C:\Users\jackw\AppData\Local\Temp\claude\C--Users-jackw-Desktop-42"
    r"\21375492-0e59-4fe4-99b0-ba94a60caa33\scratchpad"))

QTY = 3                      # live minimum (2 TP + 1 runner under tp1_qty_fraction 0.667)
LOOKBACK_DAYS = 5            # LevelMemory module default -- live engine convention
SIGNAL_LAST_LABEL = dt.time(15, 25)   # entry fill bar starts <= 15:30 (prereg)
CONFIRM_WINDOW_BARS = 3      # fixed constant (prereg)
PERM_N = 10_000
PERM_SEED = 42

# The FROZEN 16-cell grid (must match the prereg file verbatim).
GRID = [
    {"break_margin_c": bm, "retest_band_c": rb, "max_gap_bars": g, "confirm": cf}
    for bm in (15, 30) for rb in (10, 25) for g in (6, 12) for cf in ("touch", "close_confirm")
]


def cell_id(c: dict) -> str:
    short = "touch" if c["confirm"] == "touch" else "close"
    return f"bm{c['break_margin_c']}_rb{c['retest_band_c']}_g{c['max_gap_bars']}_{short}"


# ---------------------------------------------------------------------------- data load
def load_source_days(inv: dict) -> dict[str, pd.DataFrame]:
    """Per covered day: its RTH 5m frame from the inventory-chosen source file (et-v2,
    tz-aware ET), deduped by timestamp, sorted. Honors the inventory's per-day source."""
    by_src: dict[str, dict] = {}
    for d in inv["days"]:
        by_src.setdefault(d["source_file"], {})[d["date"]] = None
    frames: dict[str, pd.DataFrame] = {}
    for src, wanted in by_src.items():
        path = BACKTEST / "data" / src
        df = pd.read_csv(path)
        raw = df["timestamp_et"].astype(str)
        # DST-frame discipline (et_frame.py): offset-stamped files carry the fixed -04:00
        # writer frame -- parse offset -> UTC -> true ET. NAIVE files (the merged master)
        # stripped that same -04:00 label but kept its WALL time, so recover the UTC
        # instant by localizing to the fixed -04:00 frame (Etc/GMT+4) first.
        if ("+" in raw.iloc[0][10:]) or ("-" in raw.iloc[0][10:]):
            ts = pd.to_datetime(raw, utc=True, format="ISO8601").dt.tz_convert(ET_TZ)
        else:
            ts = (pd.to_datetime(raw, format="ISO8601")
                    .dt.tz_localize("Etc/GMT+4").dt.tz_convert(ET_TZ))
        df = df.assign(timestamp_et=ts)
        df["_date"] = df["timestamp_et"].dt.strftime("%Y-%m-%d")
        tt = df["timestamp_et"].dt.time
        rth = df[(tt >= dt.time(9, 30)) & (tt < dt.time(16, 0))]
        for date_str, sub in rth.groupby("_date"):
            if date_str not in wanted:
                continue
            sub = (sub.drop_duplicates(subset="timestamp_et", keep="first")
                      .sort_values("timestamp_et").reset_index(drop=True)
                      .drop(columns=["_date"]))
            frames[date_str] = sub[["timestamp_et", "open", "high", "low", "close", "volume"]]
    missing = [d["date"] for d in inv["days"] if d["date"] not in frames]
    assert not missing, f"inventory days missing from source files: {missing[:5]}"
    return frames


def load_opt_day(symbol: str, date_str: str, _cache: dict = {}) -> pd.DataFrame | None:
    """Real OPRA bars for one contract, et-v2 tz-aware ET, RTH-sliced. None if uncached."""
    if symbol in _cache:
        df = _cache[symbol]
    else:
        path = OPT_DIR / f"{symbol}.csv"
        if not path.exists() or path.stat().st_size == 0:
            _cache[symbol] = None
            return None
        try:
            df = pd.read_csv(path)
        except Exception:
            _cache[symbol] = None
            return None
        if df.empty:
            _cache[symbol] = None
            return None
        ts = pd.to_datetime(df["timestamp_et"], utc=True,
                            format="ISO8601").dt.tz_convert(ET_TZ)
        df = df.assign(timestamp_et=ts).sort_values("timestamp_et").reset_index(drop=True)
        _cache[symbol] = df
    if df is None:
        return None
    day = df[df["timestamp_et"].dt.strftime("%Y-%m-%d") == date_str]
    tt = day["timestamp_et"].dt.time
    day = day[(tt >= dt.time(9, 30)) & (tt < dt.time(16, 0))]
    return day.reset_index(drop=True) if len(day) else None


# ---------------------------------------------------------------------------- levels cache
def build_levels_cache(inv: dict, frames: dict[str, pd.DataFrame], run_dates: list[str],
                       cache_path: Path, rebuild: bool) -> dict:
    """Per OPRA run day: per-bar LevelMemory level lists [(price, role, mem)], plus the
    level set of the bar immediately BEFORE the day's first bar (for j=0 break checks).
    Shared across all 16 cells (levels do not depend on any grid knob)."""
    if cache_path.exists() and not rebuild:
        with open(cache_path, "rb") as f:
            cached = pickle.load(f)
        if set(run_dates).issubset(cached.keys()):
            return cached
    covered = [d["date"] for d in inv["days"]]
    out: dict = {}
    t0 = time.time()
    for k, date_str in enumerate(run_dates):
        pos = covered.index(date_str)
        window_dates = covered[max(0, pos - (LOOKBACK_DAYS - 1)): pos + 1]
        window_df = pd.concat([frames[d] for d in window_dates], ignore_index=True)
        offset = sum(len(frames[d]) for d in window_dates[:-1])
        n_bars = len(frames[date_str])
        lm = LevelMemory(window_df)
        prev = (_simplify(lm.levels_at(offset - 1, LOOKBACK_DAYS)) if offset > 0 else [])
        per_bar = [_simplify(lm.levels_at(offset + j, LOOKBACK_DAYS)) for j in range(n_bars)]
        out[date_str] = {"prev": prev, "per_bar": per_bar}
        if (k + 1) % 25 == 0:
            rate = (time.time() - t0) / (k + 1)
            print(f"  levels {k+1}/{len(run_dates)} ({rate:.2f}s/day, "
                  f"eta {rate*(len(run_dates)-k-1)/60:.1f}m)", flush=True)
    with open(cache_path, "wb") as f:
        pickle.dump(out, f)
    return out


def _simplify(levels) -> list[tuple[float, str, float]]:
    return [(lv.price, "R" if lv.role == "resistance" else "S", lv.memory_score)
            for lv in levels]


def assert_causality(inv: dict, frames: dict[str, pd.DataFrame], cache: dict,
                     sample_date: str) -> None:
    """CAUSALITY GUARD (prereg): the cached full-frame levels_at(i) must equal a fresh
    LevelMemory built over the frame TRUNCATED at bar i. A planted-future level would
    differ. Also re-asserts the level-set-before-break convention structurally."""
    covered = [d["date"] for d in inv["days"]]
    pos = covered.index(sample_date)
    window_dates = covered[max(0, pos - (LOOKBACK_DAYS - 1)): pos + 1]
    window_df = pd.concat([frames[d] for d in window_dates], ignore_index=True)
    offset = sum(len(frames[d]) for d in window_dates[:-1])
    n_bars = len(frames[sample_date])
    for j in (0, n_bars // 2, n_bars - 1):
        i = offset + j
        trunc = LevelMemory(window_df.iloc[: i + 1])
        got = set((p, r) for p, r, _ in _simplify(trunc.levels_at(i, LOOKBACK_DAYS)))
        want = set((p, r) for p, r, _ in cache[sample_date]["per_bar"][j])
        assert got == want, (
            f"CAUSALITY VIOLATION {sample_date} bar {j}: truncated-frame levels != "
            f"cached full-frame levels (diff={got ^ want})")
    print(f"  causality guard PASS (truncation assert, {sample_date} bars 0/"
          f"{n_bars//2}/{n_bars-1})", flush=True)


# ---------------------------------------------------------------------------- detector
def detect_day_signals(day_df: pd.DataFrame, prev_levels, per_bar_levels, cell: dict):
    """Causal break+retest detection for ONE day under ONE cell's knobs.

    Returns signal dicts (sig_idx, level, direction, mem, break_idx, touch_idx), already
    same-bar-deduped by memory score and sorted by time. Pure; no I/O."""
    margin = cell["break_margin_c"] / 100.0
    band = cell["retest_band_c"] / 100.0
    max_gap = cell["max_gap_bars"]
    confirm = cell["confirm"]

    closes = day_df["close"].to_numpy(float)
    lows = day_df["low"].to_numpy(float)
    highs = day_df["high"].to_numpy(float)
    labels = day_df["timestamp_et"]
    n = len(day_df)

    active: list[dict] = []
    signals: list[dict] = []

    def _signal(ep, j):
        # runtime ordering assert (prereg causality guard #3)
        assert ep["break_idx"] < j and (ep["touch_idx"] is None or
                                        ep["break_idx"] < ep["touch_idx"] <= j), \
            f"episode ordering violation: break={ep['break_idx']} touch={ep['touch_idx']} sig={j}"
        if labels.iloc[j].time() <= SIGNAL_LAST_LABEL:
            signals.append({"sig_idx": j, "level": ep["level"], "dir": ep["dir"],
                            "mem": ep["mem"], "break_idx": ep["break_idx"],
                            "touch_idx": ep["touch_idx"]})
        ep["resolved"] = "signaled"

    for j in range(n):
        close, low, high = closes[j], lows[j], highs[j]

        # 1) advance existing episodes with bar j (touch window starts at break_idx+1)
        for ep in active:
            if ep["resolved"]:
                continue
            P, d = ep["level"], ep["dir"]
            if (d > 0 and close <= P - margin) or (d < 0 and close >= P + margin):
                ep["resolved"] = "failed_break"
                continue
            if ep["touch_idx"] is None:
                if j > ep["break_idx"] + max_gap:
                    ep["resolved"] = "retest_window_expired"
                    continue
                if low <= P + band and high >= P - band:      # bar range enters the zone
                    ep["touch_idx"] = j
                    if confirm == "touch":
                        _signal(ep, j)
                    elif (d > 0 and close > P) or (d < 0 and close < P):
                        _signal(ep, j)                        # touch bar confirms itself
                continue
            # touched, waiting for close-confirm (close_confirm mode only)
            if j > ep["touch_idx"] + CONFIRM_WINDOW_BARS:
                ep["resolved"] = "confirm_window_expired"
                continue
            if (d > 0 and close > P) or (d < 0 and close < P):
                _signal(ep, j)

        # 2) new breaks at bar j against the level set as of the PREVIOUS bar (causal)
        prior = per_bar_levels[j - 1] if j > 0 else prev_levels
        for (P, role, mem) in prior:
            if role == "R" and close >= P + margin:
                d = +1
            elif role == "S" and close <= P - margin:
                d = -1
            else:
                continue
            if any((not e["resolved"]) and abs(e["level"] - P) <= CLUSTER_TOL
                   for e in active):
                continue                                       # same-level re-arm rule
            active.append({"level": P, "dir": d, "mem": mem, "break_idx": j,
                           "touch_idx": None, "resolved": None})

    # same-bar dedupe: keep highest-memory level per signal bar
    best: dict[int, dict] = {}
    for s in signals:
        if s["sig_idx"] not in best or s["mem"] > best[s["sig_idx"]]["mem"]:
            best[s["sig_idx"]] = s
    return [best[k] for k in sorted(best)]


# ---------------------------------------------------------------------------- fills+walk
def run_cell_day(date_str: str, day_df: pd.DataFrame, signals: list[dict],
                 stack_by_label: dict, exit_shape: dict, time_stop: dt.time):
    """Serialize a day's signals into real-OPRA walked trades (one position at a time)."""
    trades, skips = [], []
    labels = day_df["timestamp_et"]
    closes = day_df["close"].to_numpy(float)
    trade_date = dt.date.fromisoformat(date_str)
    open_until = None  # naive ET exit ts of the currently-walked position

    for s in signals:
        j = s["sig_idx"]
        sig_label = labels.iloc[j]
        sig_close_time = sig_label + pd.Timedelta(minutes=5)   # bar close = entry search start
        naive_entry_search = sig_close_time.tz_localize(None)
        side = "C" if s["dir"] > 0 else "P"
        spot = float(closes[j])
        strike = int(round(spot))
        base = {"date": date_str, "signal_ts": str(sig_label), "level": s["level"],
                "dir": "up" if s["dir"] > 0 else "down", "mem": round(s["mem"], 1),
                "break_ts": str(labels.iloc[s["break_idx"]]),
                "touch_ts": str(labels.iloc[s["touch_idx"]]) if s["touch_idx"] is not None else None,
                "side": side, "strike": strike, "spot": round(spot, 2)}

        if open_until is not None and naive_entry_search < open_until:
            skips.append({**base, "skip_reason": "overlap"})
            continue
        sym = option_symbol(trade_date, strike, side)
        odf = load_opt_day(sym, date_str)
        if odf is None or odf.empty:
            skips.append({**base, "skip_reason": "no_opra", "symbol": sym})
            continue
        entry_rows = odf[odf["timestamp_et"] >= sig_close_time]
        if entry_rows.empty:
            skips.append({**base, "skip_reason": "no_entry_bar", "symbol": sym})
            continue
        entry_row = entry_rows.iloc[0]
        entry_premium = float(entry_row["vwap"])
        if not np.isfinite(entry_premium) or entry_premium <= 0.0:
            skips.append({**base, "skip_reason": "bad_premium", "symbol": sym})
            continue
        entry_ts = entry_row["timestamp_et"].tz_localize(None)
        assert entry_ts >= naive_entry_search, "entry bar precedes signal close (causality)"

        # ribbon ticks aligned row-for-row with the option bars we hand the walk
        opt_walk = odf.copy()
        stacks = [_stack_for(ts, stack_by_label) for ts in opt_walk["timestamp_et"]]
        ribbon_tick_df = pd.DataFrame({"stack": stacks})

        res = emw.walk_exit_manager(
            symbol=sym, side=side, entry_time_et=entry_ts.to_pydatetime(),
            entry_premium=entry_premium, qty=QTY,
            exit_shape=exit_shape, structure_stop_enabled=True,
            trigger_level=float(s["level"]), strategy="ribbon_ride",
            time_stop_et=time_stop,
            opt_df=opt_walk[["timestamp_et", "open", "high", "low", "close"]],
            ribbon_tick_df=ribbon_tick_df,
            five_min_spy_df=day_df[["timestamp_et", "close"]])

        exit_ts = res.exit_time_et
        open_until = (pd.Timestamp(exit_ts) if exit_ts is not None
                      else pd.Timestamp(f"{date_str} 16:00:00"))
        trades.append({**base, "symbol": sym, "entry_ts": str(entry_ts),
                       "entry_premium": round(entry_premium, 4), "qty": QTY,
                       "exit_ts": str(exit_ts) if exit_ts is not None else None,
                       "exit_reason": res.exit_reason, "hold_min": res.hold_minutes,
                       "n_legs": len(res.legs), "pnl": round(res.dollar_pnl, 2)})
    return trades, skips


def _stack_for(ts, stack_by_label):
    key = ts.value
    st = stack_by_label.get(key)
    if st is not None:
        return st
    keys = stack_by_label["_sorted_keys"]
    i = np.searchsorted(keys, key, side="right") - 1
    return stack_by_label[keys[i]] if i >= 0 else "WARMUP"


# ---------------------------------------------------------------------------- metrics
def perm_p(pnls: list[float]) -> float:
    if not pnls:
        return 1.0
    arr = np.asarray(pnls, float)
    obs = arr.sum()
    rng = np.random.default_rng(PERM_SEED)
    flips = rng.choice([-1.0, 1.0], size=(PERM_N, len(arr)))
    totals = flips @ arr
    return float((np.sum(totals >= obs) + 1) / (PERM_N + 1))


def segment_metrics(trades: list[dict]) -> dict:
    pnls = [t["pnl"] for t in trades]
    n = len(pnls)
    total = float(np.sum(pnls)) if n else 0.0
    by_day: dict[str, float] = {}
    for t in trades:
        by_day[t["date"]] = by_day.get(t["date"], 0.0) + t["pnl"]
    n_days = len(by_day)
    day_wr = (sum(1 for v in by_day.values() if v > 0) / n_days) if n_days else 0.0
    top = sorted(pnls, reverse=True)
    ex_top3 = total - sum(top[:3])
    ex_top1 = total - (top[0] if top else 0.0)
    return {"n": n, "total": round(total, 2),
            "expectancy": round(total / n, 2) if n else 0.0,
            "n_days_covered": n_days, "day_wr": round(day_wr, 4),
            "ex_top3_total": round(ex_top3, 2), "ex_top1_total": round(ex_top1, 2),
            "pnls": pnls}


# ---------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-days", type=int, default=0,
                    help="probe mode: run only the first N tune days (no heldout, no writes)")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    args = ap.parse_args()
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    prereg = json.loads(PREREG.read_text())
    assert prereg["frozen"] and prereg["grid"]["n_cells"] == len(GRID) == 16
    assert [cell_id(c) for c in GRID] == prereg["grid"]["cells"], "grid drifted from prereg"

    inv = json.loads(INVENTORY.read_text())
    heldout = list(inv["heldout_days"])
    heldout_set = set(heldout)
    tune = [d for d in inv["opra_days"] if d not in heldout_set]
    probe = bool(args.limit_days)
    if probe:
        tune = tune[: args.limit_days]
        heldout = []
    run_dates = tune + heldout

    print(f"[1/5] loading SPY frames ({len(inv['days'])} covered days)...", flush=True)
    frames = load_source_days(inv)

    print("[2/5] ribbon (Saty 13/20/48, continuous RTH closes)...", flush=True)
    master = pd.concat([frames[d["date"]] for d in inv["days"]], ignore_index=True)
    rib = compute_ribbon(master["close"])
    stack_by_label: dict = {ts.value: st for ts, st in
                            zip(master["timestamp_et"], rib["stack"])}
    stack_by_label["_sorted_keys"] = np.asarray(
        sorted(k for k in stack_by_label if k != "_sorted_keys"), dtype=np.int64)

    print(f"[3/5] LevelMemory levels cache ({len(run_dates)} run days)...", flush=True)
    cache_path = cache_dir / "brc_levels_cache.pkl"
    levels = build_levels_cache(inv, frames, run_dates, cache_path, args.rebuild_cache)
    assert_causality(inv, frames, levels, tune[min(len(tune) - 1, len(tune) // 2)])

    exit_shape = fleet_strategies.RIBBON_RIDE.exit.to_dict()
    try:
        time_stop = em.parse_time_stop_et(
            json.loads(PARAMS_JSON.read_text()).get("time_stop_et"))
    except Exception:
        time_stop = dt.time(15, 40)
    print(f"    exit shape = RIBBON_RIDE {exit_shape}")
    print(f"    time_stop_et = {time_stop}  structure_stop_enabled = True  qty = {QTY}")

    print(f"[4/5] grid run: {len(GRID)} cells x {len(run_dates)} days...", flush=True)
    episodes: dict = {}
    results: list[dict] = []
    t0 = time.time()
    for ci, cell in enumerate(GRID):
        cid = cell_id(cell)
        cell_trades: list[dict] = []
        cell_skips: list[dict] = []
        n_signals_tune = 0
        n_signals_held = 0
        knob_diag = {"touch_gap_gt6": 0, "confirm_lag_gt0": 0, "n_sigs": 0}
        for date_str in run_dates:
            seg = "heldout" if date_str in heldout_set else "tune"
            day_df = frames[date_str]
            sigs = detect_day_signals(day_df, levels[date_str]["prev"],
                                      levels[date_str]["per_bar"], cell)
            if seg == "tune":
                n_signals_tune += len(sigs)
            else:
                n_signals_held += len(sigs)
            for s in sigs:   # knob-bind diagnostic (C14 vary-and-assert)
                knob_diag["n_sigs"] += 1
                if s["touch_idx"] is not None and s["touch_idx"] - s["break_idx"] > 6:
                    knob_diag["touch_gap_gt6"] += 1
                if s["touch_idx"] is not None and s["sig_idx"] > s["touch_idx"]:
                    knob_diag["confirm_lag_gt0"] += 1
            trades, skips = run_cell_day(date_str, day_df, sigs, stack_by_label,
                                         exit_shape, time_stop)
            for t in trades:
                t["seg"] = seg
            for s in skips:
                s["seg"] = seg
            cell_trades.extend(trades)
            cell_skips.extend(skips)

        tune_trades = [t for t in cell_trades if t["seg"] == "tune"]
        held_trades = [t for t in cell_trades if t["seg"] == "heldout"]
        m = segment_metrics(tune_trades)
        hm = segment_metrics(held_trades)
        p = perm_p(m.pop("pnls"))
        hm.pop("pnls")
        gates = int(m["total"] > 0) + int(m["day_wr"] > 0.5) + \
            int(m["ex_top1_total"] > 0) + int(hm["total"] > 0)
        row = {"cell_id": cid, "params": cell,
               "n_signals": n_signals_tune, "n_real_fills": m["n"],
               "expectancy": m["expectancy"], "total_pnl": m["total"],
               "day_wr": m["day_wr"], "n_days_covered": m["n_days_covered"],
               "ex_top3_total": m["ex_top3_total"], "ex_top1_total": m["ex_top1_total"],
               "held_out_total": hm["total"], "heldout_n_fills": hm["n"],
               "heldout_n_signals": n_signals_held, "heldout_day_wr": hm["day_wr"],
               "p_raw": round(p, 5), "gates_passed": gates,
               "n_skips": len([s for s in cell_skips if s["seg"] == "tune"]),
               "knob_diag": knob_diag}
        results.append(row)
        episodes[cid] = {"trades": cell_trades, "skips": cell_skips}
        el = time.time() - t0
        print(f"  [{ci+1:2d}/16] {cid:22s} n={m['n']:4d} exp={m['expectancy']:8.2f} "
              f"tot={m['total']:10.2f} dwr={m['day_wr']:.2f} held={hm['total']:9.2f} "
              f"p={p:.4f} gates={gates}  ({el:.0f}s)", flush=True)

    print("[5/5] writing outputs...", flush=True)
    if not probe:
        EPISODES_OUT.write_text(json.dumps({
            "family": "break-retest-continuation",
            "prereg": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "inventory": str(INVENTORY.relative_to(ROOT)).replace("\\", "/"),
            "qty": QTY, "exit_shape": exit_shape, "time_stop_et": str(time_stop),
            "tune_days": len(tune), "heldout_days": len(heldout),
            "cells": episodes}, indent=1))
        RESULTS_OUT.write_text(json.dumps({
            "family": "break-retest-continuation",
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "cells": results}, indent=1))
        print(f"  episodes -> {EPISODES_OUT}")
        print(f"  results  -> {RESULTS_OUT}")
    else:
        print("  probe mode: no files written")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
