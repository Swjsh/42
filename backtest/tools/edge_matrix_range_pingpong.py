"""edge_matrix_range_pingpong.py — pre-registered RANGE PING-PONG entry family (edge-matrix 2026-07-23).

FAMILY (J: "things just ping-pong between levels"): fade the edge of a qualified two-level
range — when a bar tags the zone of one of two adjacent, prior-touched, role-consistent
LevelMemory levels bounding price and rejects back toward the other level, enter toward the
range interior (P at the upper level, C at the lower level). BOTH directions.

FROZEN PRE-REG: analysis/edge-matrix/prereg-range-pingpong-2026-07-23.json — written and
frozen BEFORE this file. 4 knobs x 16 cells, single pass, no iteration after results.

SOURCES (live, never invented):
  levels  : backtest/lib/watchers/level_memory.py LevelMemory (lookback_days=5, stock constants)
  ribbon  : backtest/lib/ribbon.py (fingerprinted 13/20/48, causal SMA-seeded EMA)
  exits   : automation/state/fleet/strategies.py RIBBON_RIDE.exit walked through
            backtest/lib/exit_manager_walk.walk_exit_manager (the REAL live decision core),
            structure_stop_enabled=True (live params.json truth), trigger_level = tagged level
  dollars : real OPRA 5m bars, backtest/data/options/ (option_pricing_real cache + symbology);
            NO BS-synthetic anywhere
  frame   : et-v2 (per-row offset -> UTC -> true ET) for BOTH SPY and OPRA (DST-artifact safe)

CAUSALITY (C6): bar i uses ONLY bars <= i. Enforced structurally (LevelMemory.levels_at(i))
plus runtime asserts on every level's indices, plus a hard truncation self-test on 3 fixed
dates that REFUSES to produce results if it fails.

Population: analysis/edge-matrix/day-inventory-2026-07-23.json (381 OPRA days; heldout = its
frozen last-25% list, used only for held_out_total / gate 4).

NO live wiring. NO git commits. NO broker imports.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
if str(BACKTEST) not in sys.path:
    sys.path.insert(0, str(BACKTEST))

from lib import exit_manager_walk as emw                    # noqa: E402
from lib.exit_manager_walk import walk_exit_manager         # noqa: E402
from lib.option_pricing_real import CACHE_DIR, option_symbol  # noqa: E402
from lib.ribbon import compute_ribbon, load_periods         # noqa: E402
from lib.watchers.level_memory import LevelMemory           # noqa: E402

import strategies  # noqa: E402  (fleet dir put on sys.path by exit_manager_walk)

INVENTORY_PATH = REPO / "analysis" / "edge-matrix" / "day-inventory-2026-07-23.json"
EPISODES_PATH = REPO / "analysis" / "edge-matrix" / "range-pingpong-episodes.json"
RESULTS_PATH = REPO / "analysis" / "edge-matrix" / "range-pingpong-results.json"
PREREG_PATH = REPO / "analysis" / "edge-matrix" / "prereg-range-pingpong-2026-07-23.json"

# ── frozen grid (mirrors the pre-reg EXACTLY) ────────────────────────────────
SPACING_MIN_GRID = (0.80, 1.20)
TOUCHES_MIN_GRID = (2, 3)
BAND_GRID = (0.10, 0.20)
CONFIRM_GRID = (0, 1)
SPACING_MAX = 3.50           # fixed structural, not tuned
LOOKBACK_DAYS = 5            # LevelMemory production default
CONTEXT_PRIOR_DAYS = 4       # + current day = 5-day lookback window
ENTRY_EARLIEST = dt.time(9, 35)   # decision-bar CLOSE instant window
ENTRY_LATEST = dt.time(15, 30)
QTY = 3                      # Safe minimum: 2 TP1 + 1 runner
PERM_ITERS = 10_000
PERM_SEED = 42
SELF_TEST_DATES = ("2025-03-19", "2025-11-14", "2026-01-13")

# The frozen exit shape must be the LIVE RIBBON_RIDE shape — assert-pinned against the pre-reg.
EXIT_SHAPE = strategies.RIBBON_RIDE.exit.to_dict()
_PREREG_SHAPE = {
    "premium_stop_pct": -0.20, "tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667,
    "profit_lock_mode": "trailing", "runner_target_pct": 99.0, "trail_pct": 0.15,
    "profit_lock_arm_pct": 0.05, "stop_mode": "structure", "catastrophe_stop_pct": -0.50,
    "profit_lock_arm_scope": "post_tp1",
}
assert EXIT_SHAPE == _PREREG_SHAPE, f"live RIBBON_RIDE shape drifted from pre-reg: {EXIT_SHAPE}"

RIBBON_PERIODS = load_periods()


def make_cells() -> list[dict]:
    cells = []
    for s in SPACING_MIN_GRID:
        for t in TOUCHES_MIN_GRID:
            for b in BAND_GRID:
                for c in CONFIRM_GRID:
                    cells.append({
                        "cell_id": f"rp-s{int(round(s*100)):03d}-t{t}-b{int(round(b*100)):03d}-c{c}",
                        "spacing_min": s, "touches_min": t, "band": b, "confirm": c,
                    })
    assert len(cells) == 16
    return cells


CELLS = make_cells()

# ── data loading (et-v2 frame everywhere) ────────────────────────────────────
_SPY_FILE_CACHE: dict[str, pd.DataFrame] = {}
_OPT_CACHE: dict[str, pd.DataFrame | None] = {}
_INV: dict | None = None


def load_inventory() -> dict:
    global _INV
    if _INV is None:
        _INV = json.loads(INVENTORY_PATH.read_text())
    return _INV


def _load_spy_source(source_file: str) -> pd.DataFrame:
    """Full source CSV parsed et-v2 to NAIVE TRUE ET, sorted, all rows."""
    if source_file in _SPY_FILE_CACHE:
        return _SPY_FILE_CACHE[source_file]
    df = pd.read_csv(BACKTEST / "data" / source_file)
    # format="mixed": some source files interleave "YYYY-MM-DD HH:MM:SS-04:00" and
    # "YYYY-MM-DDTHH:MM:SS-04:00" rows (two writer eras); single-format inference raised
    # on 26 held-out days (2026-04-08..2026-05-13). Per-element parse, same et-v2 frame.
    ts = pd.to_datetime(df["timestamp_et"], utc=True, format="mixed").dt.tz_convert("America/New_York")
    df["timestamp_et"] = ts.dt.tz_localize(None)
    df = df.sort_values("timestamp_et").reset_index(drop=True)
    _SPY_FILE_CACHE[source_file] = df
    return df


def day_rth_frame(source_file: str, date_str: str) -> pd.DataFrame:
    """RTH rows (09:30 <= t < 16:00 TRUE ET) of one day from its inventory-chosen source
    file, deduped by timestamp (inventory dedupe convention)."""
    src = _load_spy_source(source_file)
    d = dt.date.fromisoformat(date_str)
    mask = (src["timestamp_et"].dt.date == d)
    day = src.loc[mask]
    tod = day["timestamp_et"].dt.time
    day = day.loc[(tod >= dt.time(9, 30)) & (tod < dt.time(16, 0))]
    day = day.drop_duplicates(subset="timestamp_et").sort_values("timestamp_et")
    return day.reset_index(drop=True)


def load_option_frame(symbol: str) -> pd.DataFrame | None:
    """One contract's 5m bars, et-v2 -> naive true ET. None if uncached/empty."""
    if symbol in _OPT_CACHE:
        return _OPT_CACHE[symbol]
    path = CACHE_DIR / f"{symbol}.csv"
    out: pd.DataFrame | None = None
    if path.exists() and path.stat().st_size > 0:
        try:
            df = pd.read_csv(path)
            if len(df) > 0:
                ts = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
                df["timestamp_et"] = ts.dt.tz_localize(None)
                out = df.sort_values("timestamp_et").reset_index(drop=True)
        except Exception:
            out = None
    _OPT_CACHE[symbol] = out
    return out


def build_context(date_str: str):
    """(ctx_naive, day_idx_list) — ctx = prior <=4 covered days + day D, RTH only, reset index."""
    inv = load_inventory()
    covered = [r["date"] for r in inv["days"]]
    srcmap = {r["date"]: r["source_file"] for r in inv["days"]}
    pos = covered.index(date_str)
    ctx_days = covered[max(0, pos - CONTEXT_PRIOR_DAYS): pos + 1]
    frames = [day_rth_frame(srcmap[d], d) for d in ctx_days]
    ctx = pd.concat(frames, ignore_index=True)
    d = dt.date.fromisoformat(date_str)
    day_idx = ctx.index[ctx["timestamp_et"].dt.date == d].tolist()
    return ctx, day_idx


# ── detector (pure, causal) ──────────────────────────────────────────────────

def levels_for_day(ctx: pd.DataFrame, day_idx: list[int]) -> dict[int, list]:
    """LevelMemory levels at every day bar. CAUSALITY assert on every level's indices."""
    lm_frame = ctx.copy()
    lm_frame["timestamp_et"] = lm_frame["timestamp_et"].dt.tz_localize("America/New_York")
    lm = LevelMemory(lm_frame)
    out: dict[int, list] = {}
    for i in day_idx:
        lvls = lm.levels_at(i, LOOKBACK_DAYS)
        for lv in lvls:
            # C6 hard assert: nothing about a level may reference a bar AFTER the eval bar.
            assert lv.first_seen_idx <= i, f"look-ahead: first_seen {lv.first_seen_idx} > {i}"
            assert lv.last_touch_idx <= i, f"look-ahead: last_touch {lv.last_touch_idx} > {i}"
            assert lv.last_flip_idx <= i, f"look-ahead: last_flip {lv.last_flip_idx} > {i}"
        out[i] = lvls
    return out


def detect_candidates(ctx: pd.DataFrame, day_idx: list[int],
                      levels_by_idx: dict[int, list], cell: dict) -> list[dict]:
    """Raw signal candidates for one cell (NO position discipline, NO fills — pure detector).
    A candidate at tag bar i reads bars <= decision_idx only."""
    highs = ctx["high"].values
    lows = ctx["low"].values
    closes = ctx["close"].values
    ts = ctx["timestamp_et"]
    day_set = set(day_idx)
    band = cell["band"]
    out: list[dict] = []
    for i in day_idx:
        lvls = levels_by_idx.get(i)
        if not lvls:
            continue
        cl = closes[i]
        u_cands = [lv for lv in lvls if lv.price > cl and lv.role == "resistance"
                   and lv.touches >= cell["touches_min"]]
        l_cands = [lv for lv in lvls if lv.price < cl and lv.role == "support"
                   and lv.touches >= cell["touches_min"]]
        if not u_cands or not l_cands:
            continue
        u_lv = min(u_cands, key=lambda lv: lv.price)
        l_lv = max(l_cands, key=lambda lv: lv.price)
        U, L = u_lv.price, l_lv.price
        spacing = U - L
        if not (cell["spacing_min"] <= spacing <= SPACING_MAX):
            continue
        side = None
        if highs[i] >= U - band and lows[i] > L + band:
            side, level, other = "P", U, L        # tag+reject at range top (close < U by U selection)
        elif lows[i] <= L + band and highs[i] < U - band:
            side, level, other = "C", L, U        # tag+reject at range bottom (close > L)
        if side is None:
            continue
        decision_idx = i
        if cell["confirm"] == 1:
            j = i + 1
            if j not in day_set:
                continue
            cj = closes[j]
            if not (L < cj < U):
                continue
            decision_idx = j
        dts = ts.iloc[decision_idx] + pd.Timedelta(minutes=5)  # decision-bar CLOSE instant
        tod = dts.time()
        if tod < ENTRY_EARLIEST or tod > ENTRY_LATEST:
            continue
        out.append({
            "tag_idx": i, "decision_idx": decision_idx, "decision_close": dts,
            "side": side, "level": round(level, 2), "other_level": round(other, 2),
            "spacing": round(spacing, 2),
            "decision_close_spy": float(closes[decision_idx]),
            "u_touches": u_lv.touches, "l_touches": l_lv.touches,
        })
    return out


# ── ribbon alignment for the walk ────────────────────────────────────────────

def ribbon_for_ctx(ctx: pd.DataFrame) -> pd.DataFrame:
    return compute_ribbon(ctx["close"], periods=RIBBON_PERIODS)


def ribbon_tick_rows(opt_df: pd.DataFrame, ctx: pd.DataFrame, ribbon_df: pd.DataFrame) -> pd.DataFrame:
    """Row-aligned 'stack' for each opt bar = ribbon stack of the last CLOSED SPY 5m bar at
    that opt bar's fire instant (opt bar label t -> last SPY label <= t-5min)."""
    spy_labels = ctx["timestamp_et"].values
    stacks = ribbon_df["stack"].values
    out = []
    for t in opt_df["timestamp_et"].values:
        cutoff = t - np.timedelta64(5, "m")
        k = int(np.searchsorted(spy_labels, cutoff, side="right")) - 1
        out.append(stacks[k] if k >= 0 else "WARMUP")
    return pd.DataFrame({"stack": out})


# ── per-day engine ───────────────────────────────────────────────────────────

def process_day(date_str: str) -> list[dict]:
    """All 16 cells over one OPRA day. Returns episode/signal records."""
    ctx, day_idx = build_context(date_str)
    if len(day_idx) < 30:
        return []
    levels_by_idx = levels_for_day(ctx, day_idx)
    ribbon_df = ribbon_for_ctx(ctx)
    day_spy = ctx.iloc[day_idx][["timestamp_et", "open", "high", "low", "close"]].reset_index(drop=True)
    d = dt.date.fromisoformat(date_str)
    records: list[dict] = []

    for cell in CELLS:
        cands = detect_candidates(ctx, day_idx, levels_by_idx, cell)
        busy_until: dt.datetime | None = None
        for cand in cands:
            dts: pd.Timestamp = cand["decision_close"]
            if busy_until is not None and dts.to_pydatetime() <= busy_until:
                continue  # one position at a time (not counted as a signal)
            rec = {
                "cell_id": cell["cell_id"], "date": date_str,
                "tag_ts": str(ctx["timestamp_et"].iloc[cand["tag_idx"]]),
                "decision_close": str(dts), "side": cand["side"],
                "level": cand["level"], "other_level": cand["other_level"],
                "spacing": cand["spacing"], "filled": False,
            }
            strike = int(round(cand["decision_close_spy"]))
            symbol = option_symbol(d, strike, cand["side"])
            rec["strike"] = strike
            rec["symbol"] = symbol
            odf = load_option_frame(symbol)
            if odf is None:
                rec["no_fill_reason"] = "contract_not_cached"
                records.append(rec)
                continue
            entry_rows = odf.loc[(odf["timestamp_et"] >= dts)
                                 & (odf["timestamp_et"] <= dts + pd.Timedelta(minutes=5))]
            if entry_rows.empty:
                rec["no_fill_reason"] = "no_entry_bar_within_5min"
                records.append(rec)
                continue
            entry_bar = entry_rows.iloc[0]
            entry_premium = float(entry_bar["vwap"])
            if not (entry_premium > 0):
                rec["no_fill_reason"] = "zero_vwap"
                records.append(rec)
                continue
            trigger_level = cand["level"]
            opt_walk = odf[["timestamp_et", "open", "high", "low", "close"]].reset_index(drop=True)
            rib_rows = ribbon_tick_rows(opt_walk, ctx, ribbon_df)
            res = walk_exit_manager(
                symbol=symbol, side=cand["side"],
                entry_time_et=entry_bar["timestamp_et"].to_pydatetime(),
                entry_premium=entry_premium, qty=QTY,
                exit_shape=EXIT_SHAPE, structure_stop_enabled=True,
                trigger_level=trigger_level, strategy="ribbon_ride",
                time_stop_et=emw.em.TIME_STOP_ET,
                opt_df=opt_walk, ribbon_tick_df=rib_rows, five_min_spy_df=day_spy,
            )
            if res.exit_reason == "no_bars_after_entry":
                rec["no_fill_reason"] = "no_bars_after_entry"
                records.append(rec)
                continue
            rec.update({
                "filled": True,
                "entry_ts": str(entry_bar["timestamp_et"]),
                "entry_premium": round(entry_premium, 4), "qty": QTY,
                "exit_ts": str(res.exit_time_et), "exit_reason": res.exit_reason,
                "hold_minutes": res.hold_minutes, "pnl": res.dollar_pnl,
                "legs": [{"stage": lg.stage, "qty": lg.qty, "px": lg.fill_price,
                          "pnl": lg.leg_pnl} for lg in res.legs],
            })
            records.append(rec)
            busy_until = res.exit_time_et
    return records


# ── causality truncation self-test (refuses results on failure) ──────────────

def _cand_key(c: dict) -> tuple:
    return (c["tag_idx"], c["decision_idx"], c["side"], c["level"], c["other_level"])


def causality_self_test() -> None:
    inv = load_inventory()
    covered = {r["date"] for r in inv["days"]}
    for date_str in SELF_TEST_DATES:
        assert date_str in covered, f"self-test date {date_str} not covered"
        ctx, day_idx = build_context(date_str)
        levels_full = levels_for_day(ctx, day_idx)
        # truncate at ~12:30 bar of day D
        k = None
        for i in day_idx:
            if ctx["timestamp_et"].iloc[i].time() >= dt.time(12, 30):
                k = i
                break
        assert k is not None
        ctx_trunc = ctx.iloc[: k + 1].reset_index(drop=True)
        day_idx_trunc = [i for i in day_idx if i <= k]
        levels_trunc = levels_for_day(ctx_trunc, day_idx_trunc)
        for cell in CELLS:
            full = [c for c in detect_candidates(ctx, day_idx, levels_full, cell)
                    if c["decision_idx"] <= k]
            trunc = detect_candidates(ctx_trunc, day_idx_trunc, levels_trunc, cell)
            fk = sorted(_cand_key(c) for c in full)
            tk = sorted(_cand_key(c) for c in trunc)
            assert fk == tk, (
                f"CAUSALITY VIOLATION {date_str} cell {cell['cell_id']}: "
                f"future bars changed past signals.\nfull<=k: {fk}\ntrunc:  {tk}")
    print(f"causality self-test PASS on {SELF_TEST_DATES}")


# ── aggregation ──────────────────────────────────────────────────────────────

def perm_p(pnls: list[float]) -> float | None:
    """One-sided sign-flip permutation p vs zero (pre-registered: 10000 iters, seed 42)."""
    if len(pnls) < 2:
        return None
    # sorted -> order-invariant under imap_unordered day scheduling (deterministic artifact;
    # sign-flip permutation is exchangeable so sorting does not change the test itself)
    arr = np.sort(np.asarray(pnls, dtype=float))
    obs = arr.mean()
    rng = np.random.default_rng(PERM_SEED)
    signs = rng.choice([-1.0, 1.0], size=(PERM_ITERS, len(arr)))
    perm_means = (signs * arr).mean(axis=1)
    return float((1 + int((perm_means >= obs).sum())) / (PERM_ITERS + 1))


def aggregate(records: list[dict], heldout: set[str]) -> list[dict]:
    out = []
    for cell in CELLS:
        rows = [r for r in records if r["cell_id"] == cell["cell_id"]]
        tune = [r for r in rows if r["date"] not in heldout]
        held = [r for r in rows if r["date"] in heldout]
        tune_fills = [r for r in tune if r["filled"]]
        held_fills = [r for r in held if r["filled"]]
        pnls = [r["pnl"] for r in tune_fills]
        total = float(sum(pnls))
        n = len(pnls)
        exp = float(total / n) if n else 0.0
        by_day: dict[str, float] = {}
        for r in tune_fills:
            by_day[r["date"]] = by_day.get(r["date"], 0.0) + r["pnl"]
        n_days = len(by_day)
        day_wr = float(sum(1 for v in by_day.values() if v > 0) / n_days) if n_days else 0.0
        top = sorted(pnls, reverse=True)
        ex_top1 = total - (top[0] if top else 0.0)
        ex_top3 = total - sum(top[:3])
        held_total = float(sum(r["pnl"] for r in held_fills))
        p = perm_p(pnls)
        gates = [total > 0, day_wr > 0.5, ex_top1 > 0, held_total > 0]
        out.append({
            "cell_id": cell["cell_id"],
            "params": {k: cell[k] for k in ("spacing_min", "touches_min", "band", "confirm")},
            "n_signals": len(tune),
            "n_real_fills": n,
            "expectancy": round(exp, 2),
            "total_pnl": round(total, 2),
            "day_wr": round(day_wr, 4),
            "n_covered_days": n_days,
            "ex_top1_total": round(ex_top1, 2),
            "ex_top3_total": round(ex_top3, 2),
            "held_out_total": round(held_total, 2),
            "held_out_n_fills": len(held_fills),
            "p_raw": (round(p, 5) if p is not None else None),
            "gates_passed": int(sum(gates)),
            "gates": {"g1_positive_aggregate": gates[0], "g2_day_majority": gates[1],
                      "g3_survives_ex_top1": gates[2], "g4_heldout_positive": gates[3]},
        })
    return out


# ── main ─────────────────────────────────────────────────────────────────────

def _worker(date_str: str) -> list[dict]:
    try:
        return process_day(date_str)
    except AssertionError:
        raise
    except Exception as e:  # disclosed, never silently dropped (OP-33)
        return [{"cell_id": "__ERROR__", "date": date_str, "error": repr(e), "filled": False}]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test-only", action="store_true")
    ap.add_argument("--smoke-days", type=int, default=0, help="run first N OPRA days serially")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    causality_self_test()          # hard gate: no results without a passing causality check
    if args.self_test_only:
        return

    inv = load_inventory()
    opra_days = list(inv["opra_days"])
    heldout = set(inv["heldout_days"])
    run_days = opra_days[: args.smoke_days] if args.smoke_days else opra_days

    records: list[dict] = []
    if args.smoke_days or args.workers <= 1:
        for i, d in enumerate(run_days):
            records.extend(_worker(d))
            if (i + 1) % 10 == 0:
                print(f"  {i+1}/{len(run_days)} days", flush=True)
    else:
        import multiprocessing as mp
        with mp.Pool(processes=args.workers) as pool:
            for i, recs in enumerate(pool.imap_unordered(_worker, run_days, chunksize=4)):
                records.extend(recs)
                if (i + 1) % 25 == 0:
                    print(f"  {i+1}/{len(run_days)} days", flush=True)

    errors = [r for r in records if r["cell_id"] == "__ERROR__"]
    records = [r for r in records if r["cell_id"] != "__ERROR__"]

    cells = aggregate(records, heldout)
    results = {
        "family": "range-pingpong",
        "prereg": str(PREREG_PATH.relative_to(REPO)),
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "population": {"opra_days_run": len(run_days),
                       "tuning_days": len([d for d in run_days if d not in heldout]),
                       "heldout_days": len([d for d in run_days if d in heldout])},
        "exit_shape": EXIT_SHAPE,
        "qty": QTY,
        "day_errors": errors,
        "cells": cells,
    }
    EPISODES_PATH.write_text(json.dumps({
        "family": "range-pingpong", "prereg": str(PREREG_PATH.relative_to(REPO)),
        "heldout_days_flagged_inline": True,
        "episodes": [dict(r, heldout=(r["date"] in heldout)) for r in records],
    }, indent=1))
    RESULTS_PATH.write_text(json.dumps(results, indent=1))
    print(f"wrote {EPISODES_PATH}")
    print(f"wrote {RESULTS_PATH}")
    print(json.dumps(cells, indent=1))


if __name__ == "__main__":
    main()
