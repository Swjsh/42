"""Drive run_native_backtest.py to completion in a single long process.

This replaces the multi-call while-loop pattern. Runs the full backtest for
both MNQ and MES by calling run() directly with a very large budget, printing
progress every N days.
"""
from __future__ import annotations
import datetime as dt, json, sys, time
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "backtest"))

# Import the run function directly
from futures.run_native_backtest import run, load_futures, load_vix
from futures.instruments import MNQ, MES
from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext
from lib.ribbon import compute_ribbon, RibbonState
from lib.levels import _detect_from_history
from lib.orchestrator import _align_vix_to_spy, _precompute_htf_15m_stacks, _update_level_states
from lib.watchers.runner import run_all_watchers
from futures.futures_sim import simulate_futures
from lib.watchers.orb_watcher import set_futures_range_scale

_SPY_REFERENCE = 700.0

DATA_DIR = REPO / "backtest" / "data" / "futures"
EOD = dt.time(15, 55)


def run_full(inst, start="2025-01-01", end="2026-06-12"):
    """Run the full backtest for one instrument, progress every 30 days."""
    sym = inst.symbol
    rows_path = str(DATA_DIR / f"{sym}_native_rows.jsonl")
    state_path = str(DATA_DIR / f"{sym}_native_state.json")

    # Clear any previous partial run
    for p in [rows_path, state_path]:
        if Path(p).exists():
            Path(p).unlink()
            print(f"Cleared {p}")

    t0 = time.time()
    rth = load_futures(sym)
    # load_futures already RTH-filtered to 5m; but filter again in case 1m was saved with ETH
    rth = rth[(rth["timestamp_et"].dt.time >= dt.time(9, 30)) &
               (rth["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)

    # Scale ORB thresholds for futures prices (was calibrated on SPY ~$700)
    approx_price = float(rth["close"].median())
    set_futures_range_scale(approx_price / _SPY_REFERENCE)

    vix_full = load_vix()
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    htf_stacks = _precompute_htf_15m_stacks(rth)
    ribbon_df = compute_ribbon(rth["close"])
    bars_full = load_futures(sym)

    day_groups = {d: g.reset_index(drop=True)
                  for d, g in rth.groupby(rth["timestamp_et"].dt.date)}
    all_dates = sorted(day_groups.keys())

    start_d = dt.date.fromisoformat(start)
    end_d   = dt.date.fromisoformat(end)

    rows = []
    level_states: dict = {}
    ribbon_history: list = []
    last_date = None
    lvl_cache = [None]; lvl_date = [None]
    days_done = 0

    print(f"\n=== {sym} native backtest ({start} to {end}) ===")
    print(f"  {len(rth):,} RTH bars, {len(all_dates)} trading days")

    for idx in range(len(rth)):
        bar = rth.iloc[idx]
        bt  = bar["timestamp_et"]
        bd  = bt.date()

        if bd < start_d or bd > end_d:
            continue

        if bd != last_date:
            if last_date is not None:
                days_done += 1
                if days_done % 30 == 0:
                    elapsed = time.time() - t0
                    pct = days_done / len([d for d in all_dates if start_d <= d <= end_d]) * 100
                    print(f"  {days_done} days done ({pct:.0f}%), {elapsed:.0f}s elapsed, {len(rows)} signals so far")
            ribbon_history = []
            level_states = {}
            last_date = bd

        if idx < 60:
            continue

        try:
            r = ribbon_df.iloc[idx]
            rib = RibbonState(
                fast=float(r["fast"]), pivot=float(r["pivot"]), slow=float(r["slow"]),
                stack=str(r["stack"]), spread_cents=float(r["spread_cents"]),
            )
        except Exception:
            continue

        ribbon_history.append(rib)
        ribbon_history = ribbon_history[-10:]

        volb  = vol_baseline_20bar(rth, idx)
        rngb  = range_baseline_20bar(rth, idx)
        vix_now   = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 17.0
        vix_prior = float(vix_aligned.iloc[max(0, idx-3)]) if max(0, idx-3) < len(vix_aligned) else vix_now

        if bd != lvl_date[0]:
            bars_to_now = bars_full[bars_full["timestamp_et"] <= bt]
            lvl_cache[0] = _detect_from_history(bars_to_now, bd)
            lvl_date[0] = bd
        lset = lvl_cache[0]

        _update_level_states(level_states, lset.active, bar, idx)
        htf = htf_stacks[idx] if idx < len(htf_stacks) else None

        ctx = BarContext(
            bar_idx=idx, timestamp_et=bt.to_pydatetime(), bar=bar,
            prior_bars=rth.iloc[:idx+1], ribbon_now=rib, ribbon_history=ribbon_history,
            vix_now=vix_now, vix_prior=vix_prior, vol_baseline_20=volb, range_baseline_20=rngb,
            levels_active=lset.active, multi_day_levels=lset.multi_day,
            htf_15m_stack=htf, level_states=level_states,
        )

        dbars = day_groups[bd]
        bidx  = int((dbars["timestamp_et"] == bt).values.argmax())

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
            rows.append({
                "date": str(bd), "watcher": s.watcher_name, "setup": s.setup_name,
                "dir": s.direction, "conf": s.confidence,
                "net": res["net"], "outcome": res["outcome"],
                "entry": s.entry_price, "stop": s.stop_price,
                "tp1": s.tp1_price, "runner": s.runner_price,
                "vix": round(vix_now, 2),
            })

    elapsed = time.time() - t0
    set_futures_range_scale(None)  # restore SPY mode

    orb_count = sum(1 for r in rows if r.get("watcher") == "orb_watcher")
    has_vix = sum(1 for r in rows if "vix" in r)
    print(f"  DONE: {days_done} days, {len(rows)} signals, {elapsed:.1f}s")
    print(f"  ORB signals: {orb_count}  |  rows with vix: {has_vix}")

    with open(rows_path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    Path(state_path).write_text(json.dumps({"last_done": str(last_date), "reached_end": True}))
    print(f"  Saved to {rows_path}")
    return rows


def summarize(rows: list, label: str):
    if not rows:
        print(f"\n{label}: No signals found!")
        return
    df = pd.DataFrame(rows)
    total_net = df["net"].sum()
    total_n   = len(df)
    wr        = (df["net"] > 0).mean() * 100
    per_trade = total_net / total_n if total_n else 0
    print(f"\n=== {label} SUMMARY ===")
    print(f"  Total signals : {total_n}")
    print(f"  Win rate      : {wr:.1f}%")
    print(f"  Total net P&L : ${total_net:,.2f}")
    print(f"  Per trade     : ${per_trade:.2f}")

    print(f"\n  By watcher (top 10 by net):")
    g = df.groupby(["watcher", "dir", "conf"]).agg(
        n=("net", "count"), net=("net", "sum"), wr=("net", lambda x: (x>0).mean()*100)
    ).sort_values("net", ascending=False).head(10)
    print(g.to_string())

    print(f"\n  By quarter:")
    df["q"] = pd.to_datetime(df["date"]).dt.to_period("Q")
    gq = df.groupby("q").agg(n=("net","count"), net=("net","sum"), wr=("net",lambda x:(x>0).mean()*100))
    print(gq.to_string())


if __name__ == "__main__":
    print("Running MNQ native backtest...")
    mnq_rows = run_full(MNQ)
    summarize(mnq_rows, "MNQ")

    print("\n\nRunning MES native backtest...")
    mes_rows = run_full(MES)
    summarize(mes_rows, "MES")
