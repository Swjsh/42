"""Run ALL engine watchers on REAL MNQ/MES 5m bars (native index-point prices).

This is the Step 2+3 harness: loads real Databento-pulled continuous futures bars,
runs the watcher fleet, grades each signal with futures P&L (px_to_points=1.0),
streams rows to JSONL, checkpoints for resumable multi-call completion.

Usage (resume loop until reached_end: true):
    python backtest/futures/run_native_backtest.py --inst MNQ --budget 35
    python backtest/futures/run_native_backtest.py --inst MES --budget 35

Key difference vs run_futures_backtest.py (SPY proxy):
- Bar prices are in native index points (MNQ ~21000, MES ~5500)
- px_to_points=1.0 in simulate_futures (no spy_to_index scaling)
- Level detection uses futures bars -> levels in index-point space
- VIX aligned by timestamp from the same SPY vix CSV (VIX is instrument-agnostic)
"""
from __future__ import annotations
import argparse, datetime as dt, json, sys, time
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "backtest"))

from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext
from lib.ribbon import compute_ribbon, RibbonState
from lib.levels import _detect_from_history
from lib.orchestrator import _align_vix_to_spy, _precompute_htf_15m_stacks, _update_level_states
from lib.watchers.runner import run_all_watchers
from futures.instruments import MES, MNQ
from futures.futures_sim import simulate_futures
from lib.watchers.orb_watcher import set_futures_range_scale

_SPY_REFERENCE = 700.0  # nominal SPY price used for ORB calibration

DATA = REPO / "backtest" / "data"
FUTURES_DATA = DATA / "futures"
EOD = dt.time(15, 55)


def load_futures(inst_symbol: str) -> pd.DataFrame:
    path = FUTURES_DATA / f"{inst_symbol}_5m_continuous.csv"
    if not path.exists():
        sys.exit(f"ERROR: {path} not found. Run fetch_data.py first.")
    df = pd.read_csv(path)
    # Parse with utc=True to handle mixed EDT/EST offsets, then convert to ET
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df = df.dropna(subset=["open","high","low","close"]).reset_index(drop=True)
    return df


def load_vix() -> pd.DataFrame:
    # Use the merged VIX CSV (same one the SPY engine uses)
    candidates = sorted(DATA.glob("vix_5m_2025-01-01_*.csv"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        sys.exit("ERROR: No VIX CSV found in backtest/data/")
    vix = pd.read_csv(candidates[0])
    vix["timestamp_et"] = pd.to_datetime(vix["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    return vix


def run(
    start: dt.date,
    end: dt.date,
    inst,
    resume_after=None,
    budget_s: float = 38.0,
    rows_path: str | None = None,
):
    t0 = time.time()
    sym = inst.symbol
    rth = load_futures(sym)
    rth = rth[(rth["timestamp_et"].dt.time >= dt.time(9, 30)) &
               (rth["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)

    # Scale ORB dollar-based thresholds for futures index-point prices.
    # ORB was calibrated on SPY (~$700). MNQ (~21000) needs ~30x scale; MES (~5500) ~8x.
    approx_price = float(rth["close"].median())
    set_futures_range_scale(approx_price / _SPY_REFERENCE)

    # VIX alignment: use timestamp merge against vix CSV
    vix_full = load_vix()
    vix_aligned = _align_vix_to_spy(rth, vix_full)

    # HTF stacks on futures bars
    htf_stacks = _precompute_htf_15m_stacks(rth)

    # Ribbon on futures close (watchers expect a ribbon computed on whatever bars they get)
    ribbon_df = compute_ribbon(rth["close"])

    # Full bar history for level detection (all sessions not just RTH so we see pre-market levels)
    bars_full = load_futures(sym)

    day_groups = {d: g.reset_index(drop=True)
                  for d, g in rth.groupby(rth["timestamp_et"].dt.date)}

    rows_f = open(rows_path, "a") if rows_path else None
    level_states: dict = {}
    ribbon_history: list = []
    last_date = None
    lvl_cache = [None]; lvl_date = [None]

    for idx in range(len(rth)):
        bar = rth.iloc[idx]
        bt = bar["timestamp_et"]
        bd = bt.date()

        if start and bd < start:
            continue
        if end and bd > end:
            continue
        if resume_after is not None and bd <= resume_after:
            continue

        if bd != last_date:
            if last_date is not None and (time.time() - t0) > budget_s:
                if rows_f:
                    rows_f.flush(); rows_f.close()
                return {"last_done": str(last_date), "reached_end": False}
            ribbon_history = []
            level_states = {}
            last_date = bd

        if idx < 60:
            continue

        try:
            r = ribbon_df.iloc[idx]
            rib = RibbonState(
                fast=float(r["fast"]), pivot=float(r["pivot"]), slow=float(r["slow"]),
                stack=str(r["stack"]), spread_cents=float(r["spread_cents"])
            )
        except Exception:
            continue

        ribbon_history.append(rib)
        ribbon_history = ribbon_history[-10:]

        volb  = vol_baseline_20bar(rth, idx)
        rngb  = range_baseline_20bar(rth, idx)
        vix_now   = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 17.0
        vix_prior = float(vix_aligned.iloc[max(0, idx-3)]) if max(0, idx-3) < len(vix_aligned) else vix_now

        # Level detection on futures bar history (levels in index-point space)
        if bd != lvl_date[0]:
            bars_to_now = bars_full[bars_full["timestamp_et"] <= bt]
            lvl_cache[0] = _detect_from_history(bars_to_now, bd)
            lvl_date[0] = bd
        lset = lvl_cache[0]

        _update_level_states(level_states, lset.active, bar, idx)

        htf = htf_stacks[idx] if idx < len(htf_stacks) else None
        ctx = BarContext(
            bar_idx=idx,
            timestamp_et=bt.to_pydatetime(),
            bar=bar,
            prior_bars=rth.iloc[:idx+1],
            ribbon_now=rib,
            ribbon_history=ribbon_history,
            vix_now=vix_now,
            vix_prior=vix_prior,
            vol_baseline_20=volb,
            range_baseline_20=rngb,
            levels_active=lset.active,
            multi_day_levels=lset.multi_day,
            htf_15m_stack=htf,
            level_states=level_states,
        )

        dbars = day_groups[bd]
        bidx = int((dbars["timestamp_et"] == bt).values.argmax())

        try:
            sigs = run_all_watchers(bar, dbars, bidx, volb, ctx, vix_now, multi_day_rth=None)
        except Exception:
            sigs = []

        if not sigs:
            continue

        fut = dbars[(dbars["timestamp_et"] > bt) & (dbars["timestamp_et"].dt.time <= EOD)]
        if fut.empty:
            continue

        for s in sigs:
            if s.direction not in ("long", "short"):
                continue
            res = simulate_futures(
                s.direction,
                s.entry_price, s.stop_price, s.tp1_price, s.runner_price,
                fut, inst, qty=3, px_to_points=1.0,
            )
            if rows_f:
                rows_f.write(json.dumps({
                    "date": str(bd),
                    "watcher": s.watcher_name,
                    "setup": s.setup_name,
                    "dir": s.direction,
                    "conf": s.confidence,
                    "net": res["net"],
                    "outcome": res["outcome"],
                    "entry": s.entry_price,
                    "stop": s.stop_price,
                    "tp1": s.tp1_price,
                    "runner": s.runner_price,
                    "vix": round(vix_now, 2),
                }) + "\n")

    if rows_f:
        rows_f.flush(); rows_f.close()
    set_futures_range_scale(None)  # restore SPY mode after futures backtest completes
    return {"last_done": str(last_date), "reached_end": True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start",  default="2025-01-01")
    ap.add_argument("--end",    default="2026-06-12")
    ap.add_argument("--inst",   default="MNQ", choices=["MNQ", "MES"])
    ap.add_argument("--budget", type=float, default=38.0, help="seconds per call")
    ap.add_argument("--rows",   default=None)
    ap.add_argument("--state",  default=None)
    a = ap.parse_args()

    inst = {"MNQ": MNQ, "MES": MES}[a.inst]
    rows_p = a.rows or f"backtest/data/futures/{a.inst}_native_rows.jsonl"
    state_p = a.state or f"backtest/data/futures/{a.inst}_native_state.json"

    st = json.load(open(state_p)) if Path(state_p).exists() else {}
    resume_after = dt.date.fromisoformat(st["last_done"]) if st.get("last_done") else None
    if resume_after:
        print(f"Resuming from {resume_after}")

    r = run(
        dt.date.fromisoformat(a.start),
        dt.date.fromisoformat(a.end),
        inst,
        resume_after=resume_after,
        budget_s=a.budget,
        rows_path=rows_p,
    )

    ld = r.get("last_done") or st.get("last_done")
    Path(state_p).write_text(json.dumps({"last_done": ld, "reached_end": r["reached_end"]}))
    print(json.dumps({"last_done": ld, "reached_end": r["reached_end"]}))


if __name__ == "__main__":
    main()
