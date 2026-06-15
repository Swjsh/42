"""
Diagnostic: test confluence carve-out over 3-month windows, narrowing crash location.
Redirects I/O to files for pythonw.exe compatibility.
"""
from __future__ import annotations

import sys
from pathlib import Path

_log_dir = Path(__file__).resolve().parent.parent.parent / "automation" / "state" / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)
sys.stderr = open(_log_dir / "sweep3-diag-err.txt", "w", encoding="utf-8", buffering=1)
sys.stdout = open(_log_dir / "sweep3-diag-out.txt", "w", encoding="utf-8", buffering=1)

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from lib.orchestrator import run_backtest  # noqa: E402
import datetime as dt
import pandas as pd
import traceback

DATA_DIR = REPO / "data"

PROD_KWARGS = dict(
    premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.75,
    tp1_qty_fraction=0.50,
    runner_target_premium_pct=2.5,
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.0,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.20,
    use_real_fills=True,
    min_triggers_bear=1,
    min_triggers_bull=2,
    strike_offset_bear=-3,
    strike_offset_bull=-3,
    f9_vol_mult=0.7,
    enable_bullish=True,
)

# Load full dataset once
print("Loading full 16-month dataset...")
spy_full, vix_full = None, None
for cs, ce in [("2025-01-01","2026-05-07"),("2025-01-01","2026-05-12"),
               ("2025-01-01","2026-05-15"),("2025-01-01","2026-05-19_merged")]:
    sp = DATA_DIR / f"spy_5m_{cs}_{ce}.csv"
    vp = DATA_DIR / f"vix_5m_{cs}_{ce}.csv"
    if not vp.exists():
        vp = DATA_DIR / f"vix_5m_{cs}_{ce.replace('_merged','')}.csv"
    if sp.exists() and vp.exists():
        spy_full = pd.read_csv(sp)
        vix_full = pd.read_csv(vp)
        print(f"  Loaded {sp.name}: {len(spy_full)} SPY bars")
        break
if spy_full is None:
    print("NO DATA FOUND", file=sys.stderr)
    sys.exit(1)

# Test monthly windows — first crash tells us which month has the issue
windows = [
    (dt.date(2025, 1, 1),  dt.date(2025, 3, 31),  "Q1-2025"),
    (dt.date(2025, 4, 1),  dt.date(2025, 6, 30),  "Q2-2025"),
    (dt.date(2025, 7, 1),  dt.date(2025, 9, 30),  "Q3-2025"),
    (dt.date(2025, 10, 1), dt.date(2025, 12, 31), "Q4-2025"),
    (dt.date(2026, 1, 1),  dt.date(2026, 3, 31),  "Q1-2026"),
    (dt.date(2026, 4, 1),  dt.date(2026, 5, 7),   "Q2-2026-partial"),
]

def slice_data(spy_full, vix_full, start, end):
    ss, es = start.isoformat(), f"{end.isoformat()}T23:59:59"
    s = spy_full[(spy_full["timestamp_et"] >= ss) & (spy_full["timestamp_et"] < es)].reset_index(drop=True)
    v = vix_full[(vix_full["timestamp_et"] >= ss) & (vix_full["timestamp_et"] < es)].reset_index(drop=True)
    return s, v

for start, end, label in windows:
    spy, vix = slice_data(spy_full, vix_full, start, end)
    print(f"\n[{label}] {start}..{end} ({len(spy)} bars)")

    # BASELINE
    try:
        r = run_backtest(spy, vix, start_date=start, end_date=end,
                         sweep_blocker_enabled=False, **PROD_KWARGS)
        print(f"  BASELINE OK: {len(r.trades)} trades")
    except Exception as e:
        print(f"  BASELINE CRASH: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    # WITH_GATE
    try:
        r2 = run_backtest(spy, vix, start_date=start, end_date=end,
                          sweep_blocker_enabled=True,
                          sweep_min_wick_pct=0.0003, sweep_min_close_back_pct=0.0005,
                          **PROD_KWARGS)
        print(f"  WITH_GATE OK: {len(r2.trades)} trades")
    except Exception as e:
        print(f"  WITH_GATE CRASH on [{label}]: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        print(f"WITH_GATE crashed on [{label}] — see sweep3-diag-err.txt", flush=True)
        sys.exit(1)

print("\nAll windows passed — no crash detected.")
sys.stdout.flush()
sys.stderr.flush()
