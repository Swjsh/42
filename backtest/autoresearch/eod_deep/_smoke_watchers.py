"""SMOKE TEST: directly invoke each watcher on today's bars to verify they fire
when the setup is present.

Bypasses watcher_live's dedup logic (which skips when bar already processed).
Tests each watcher in isolation against today's BULLISH_RECLAIM bar (09:55).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO / "backtest"))

from autoresearch.eod_deep.modules._bar_features import compute_ribbon_cached, compute_vol_baseline


def run_smoke():
    # Load today's bars
    today_csv = REPO / "backtest" / "data" / "spy_5m_2026-05-08_2026-05-14.csv"
    df = pd.read_csv(today_csv)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    if df["timestamp_et"].dt.tz is not None:
        df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)

    # Filter to today RTH
    today_rth = df[
        (df["timestamp_et"].dt.date == pd.Timestamp("2026-05-14").date()) &
        (df["timestamp_et"].dt.time >= pd.Timestamp("09:30").time()) &
        (df["timestamp_et"].dt.time < pd.Timestamp("16:00").time())
    ].reset_index(drop=True)
    print(f"Today RTH bars: {len(today_rth)}")

    # Compute ribbon
    ribbon_df = compute_ribbon_cached(today_rth)
    vol_baseline = compute_vol_baseline(today_rth["volume"])

    # Pick the 09:55 trigger bar (BULLISH_RECLAIM entry)
    bar_955_idx = today_rth[today_rth["timestamp_et"].dt.strftime("%H:%M") == "09:55"].index
    if len(bar_955_idx) == 0:
        print("No 09:55 bar found")
        return
    bar_idx = int(bar_955_idx[0])
    bar = today_rth.iloc[bar_idx]
    print(f"\nTest bar: {bar['timestamp_et']} O={bar['open']:.2f} H={bar['high']:.2f} L={bar['low']:.2f} C={bar['close']:.2f} V={int(bar['volume']):,}")
    print(f"Ribbon at this bar: fast={ribbon_df.iloc[bar_idx]['fast']:.2f} pivot={ribbon_df.iloc[bar_idx]['pivot']:.2f} slow={ribbon_df.iloc[bar_idx]['slow']:.2f} stack={ribbon_df.iloc[bar_idx]['stack']} spread={ribbon_df.iloc[bar_idx]['ribbon_spread_cents']:.1f}c")
    print(f"Vol baseline: {vol_baseline.iloc[bar_idx]:,.0f}, ratio: {bar['volume']/vol_baseline.iloc[bar_idx]:.2f}x")

    # Test each watcher
    print("\n" + "="*60)
    print("WATCHER FIRE TESTS on 09:55 bar (today's BULLISH_RECLAIM)")
    print("="*60)

    watchers_to_test = [
        ("sniper_watcher", "lib.watchers.sniper_watcher", "detect_sniper_setup"),
        ("vwap_watcher", "lib.watchers.vwap_watcher", "detect_vwap_setup"),
        ("opening_drive_fade_watcher", "lib.watchers.opening_drive_fade_watcher", "detect_opening_drive_fade_setup"),
        ("premarket_fail_fade_watcher", "lib.watchers.premarket_fail_fade_watcher", "detect_premarket_fail_fade_setup"),
    ]

    for name, mod_path, fn_name in watchers_to_test:
        try:
            mod = __import__(mod_path, fromlist=[fn_name])
            fn = getattr(mod, fn_name)
            try:
                # Try simplest invocation pattern: (bar, bar_idx, spy_bars)
                signal = fn(bar, bar_idx, today_rth)
            except TypeError:
                # Try with extra args (vwap requires ribbon_state_dict)
                try:
                    signal = fn(bar, bar_idx, today_rth, None)
                except Exception as e:
                    signal = f"call_error: {e}"
            if signal is None:
                print(f"  {name}: None (no signal)")
            elif isinstance(signal, str):
                print(f"  {name}: {signal}")
            else:
                print(f"  {name}: SIGNAL FIRED — {signal.setup_name} {signal.direction} entry={signal.entry_price:.2f}")
        except Exception as e:
            print(f"  {name}: ERROR {type(e).__name__}: {e}")
            traceback.print_exc()

    print("\nWatchers that DON'T need multi_day_rth (today_only path):")
    other_watchers = [
        ("orb_watcher", "lib.watchers.orb_watcher", "detect_orb_break"),
        ("bullish_watcher", "lib.watchers.bullish_watcher", "detect_bullish_setup"),
    ]
    # These have different signatures; just check importability
    for name, mod_path, fn_name in other_watchers:
        try:
            mod = __import__(mod_path, fromlist=[fn_name])
            fn = getattr(mod, fn_name)
            print(f"  {name}: importable (function {fn_name} exists)")
        except Exception as e:
            print(f"  {name}: ERROR {type(e).__name__}: {e}")


def run_full_day_scan():
    """Test EVERY bar today against each silent watcher to find ANY fire."""
    today_csv = REPO / "backtest" / "data" / "spy_5m_2026-05-08_2026-05-14.csv"
    df = pd.read_csv(today_csv)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    if df["timestamp_et"].dt.tz is not None:
        df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)

    today_rth = df[
        (df["timestamp_et"].dt.date == pd.Timestamp("2026-05-14").date()) &
        (df["timestamp_et"].dt.time >= pd.Timestamp("09:30").time()) &
        (df["timestamp_et"].dt.time < pd.Timestamp("16:00").time())
    ].reset_index(drop=True)

    # Need full multi_day_rth for sniper levels
    full_master_csv = REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-12.csv"
    master = pd.read_csv(full_master_csv)
    master["timestamp_et"] = pd.to_datetime(master["timestamp_et"])
    if master["timestamp_et"].dt.tz is not None:
        master["timestamp_et"] = master["timestamp_et"].dt.tz_localize(None)
    multi_day = pd.concat([master, today_rth], ignore_index=True).drop_duplicates(subset=["timestamp_et"], keep="last").sort_values("timestamp_et").reset_index(drop=True)

    print(f"\n{'='*70}")
    print(f"FULL-DAY SCAN: testing each silent watcher on every today RTH bar")
    print(f"  multi_day_rth: {len(multi_day)} rows")
    print(f"{'='*70}")

    # Pre-compute ribbon over multi_day so we can build per-bar ribbon_state_dict
    multi_ribbon = compute_ribbon_cached(multi_day)

    fires_per_watcher = {}
    skip_per_watcher = {}
    error_per_watcher = {}
    watchers = [
        ("sniper_watcher", "lib.watchers.sniper_watcher", "detect_sniper_setup", False),
        ("vwap_watcher", "lib.watchers.vwap_watcher", "detect_vwap_setup", True),
        ("opening_drive_fade_watcher", "lib.watchers.opening_drive_fade_watcher", "detect_opening_drive_fade_setup", False),
        ("premarket_fail_fade_watcher", "lib.watchers.premarket_fail_fade_watcher", "detect_premarket_fail_fade_setup", False),
    ]

    for name, mod_path, fn_name, needs_extra in watchers:
        try:
            mod = __import__(mod_path, fromlist=[fn_name])
            fn = getattr(mod, fn_name)
            fires_per_watcher[name] = []
            skip_per_watcher[name] = 0
            error_per_watcher[name] = []
            for _, bar in today_rth.iterrows():
                # Find this bar's idx within multi_day
                ix = multi_day.index[multi_day["timestamp_et"] == bar["timestamp_et"]]
                if len(ix) == 0:
                    continue
                multi_idx = int(ix[0])
                try:
                    if needs_extra:
                        # Build ribbon_state_dict like watcher_live.py does (lines 300-307)
                        rb = multi_ribbon.iloc[multi_idx]
                        ribbon_state_dict = {
                            "fast": float(rb["fast"]),
                            "pivot": float(rb["pivot"]),
                            "slow": float(rb["slow"]),
                            "stack": str(rb["ribbon_stack"]),
                            "spread_cents": float(rb["ribbon_spread_cents"]),
                        }
                        signal = fn(bar, multi_idx, multi_day, ribbon_state_dict)
                    else:
                        signal = fn(bar, multi_idx, multi_day)
                    if signal is None:
                        skip_per_watcher[name] += 1
                    else:
                        fires_per_watcher[name].append({
                            "time": str(bar["timestamp_et"])[11:16],
                            "setup": signal.setup_name,
                            "direction": signal.direction,
                            "entry": signal.entry_price,
                            "confidence": getattr(signal, "confidence", "?"),
                        })
                except Exception as e:
                    error_per_watcher[name].append(f"{str(bar['timestamp_et'])[11:16]}: {type(e).__name__}: {e}")
        except Exception as e:
            fires_per_watcher[name] = f"import_error: {e}"

    print()
    for name, fires in fires_per_watcher.items():
        if isinstance(fires, str):
            print(f"  {name}: {fires}")
            continue
        n_skip = skip_per_watcher.get(name, 0)
        n_err = len(error_per_watcher.get(name, []))
        if not fires:
            print(f"  {name}: 0 fires (skipped={n_skip} errors={n_err})")
            if n_err:
                for e in error_per_watcher[name][:3]:
                    print(f"    err: {e}")
        else:
            print(f"  {name}: {len(fires)} fires (skipped={n_skip} errors={n_err})")
            for f in fires[:8]:
                print(f"    {f['time']}: {f['setup']} {f['direction']} entry=${f['entry']:.2f} conf={f['confidence']}")


if __name__ == "__main__":
    run_smoke()
    run_full_day_scan()
