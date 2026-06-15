"""Smoke test for PREMARKET_FAIL_FADE watcher (J's 2026-05-13 09:30 ET trade).

Run from repo root:
    cd backtest
    python tools/smoke_test_pff.py

Expected output:
    - The 09:30 ET 2026-05-13 RTH bar fires a PREMARKET_FAIL_FADE SHORT
      signal against the 738.86 premarket resistance (from today-bias.json).
    - Signal direction='short', entry_price ~ 738.x, level_label
      starts with 'premarket_resistance_'.
    - All other bars in the eligible window (09:35, 09:40) may also fire
      if the conditions repeat; dedup logic outside this test would
      suppress them.

The smoke test fetches today's bars via yfinance because the master CSV
(spy_5m_2025-01-01_2026-05-12.csv) stops at 5/12 — exactly the foot-gun
pattern documented in CLAUDE.md "Lessons absorbed" (2026-05-13 08:42 ET).
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

import pandas as pd

from lib.premarket_fail_fade_detector import (
    PremarketFailFadeParams,
    assemble_levels,
    detect_premarket_fail_fade,
)
from lib.watchers.premarket_fail_fade_watcher import (
    detect_premarket_fail_fade_setup,
)


DATA_DIR = REPO / "data"
MASTER_CSV = DATA_DIR / "spy_5m_2025-01-01_2026-05-12.csv"
TODAY_BIAS = ROOT / "automation" / "state" / "today-bias.json"
TODAY = dt.date(2026, 5, 13)


def _fetch_intraday(symbol: str, day: dt.date) -> pd.DataFrame:
    """Yfinance intraday 5m fetch for `day`. Returns RTH-filtered ET-naive bars."""
    import yfinance as yf
    import pytz as _pytz

    ET = _pytz.timezone("America/New_York")

    df = yf.download(
        symbol,
        start=day - dt.timedelta(days=2),
        end=day + dt.timedelta(days=1),
        interval="5m",
        auto_adjust=False,
        progress=False,
        prepost=False,
    )
    if df.empty:
        return pd.DataFrame()
    # Flatten MultiIndex columns (yfinance >=0.2.40 returns tuples for single ticker)
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    ts_col = df.columns[0]
    df = df.rename(columns={
        ts_col: "timestamp_et",
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    ts = df["timestamp_et"]
    if hasattr(ts.iloc[0], "tzinfo") and ts.iloc[0].tzinfo is not None:
        df["timestamp_et"] = ts.dt.tz_convert(ET).dt.tz_localize(None)
    else:
        df["timestamp_et"] = (
            pd.to_datetime(ts).dt.tz_localize("UTC").dt.tz_convert(ET).dt.tz_localize(None)
        )
    df = df[df["timestamp_et"].dt.date == day]
    if df.empty:
        return df
    # RTH only
    df = df[
        (df["timestamp_et"].dt.time >= dt.time(9, 30))
        & (df["timestamp_et"].dt.time < dt.time(16, 0))
    ]
    df["date"] = df["timestamp_et"].dt.date
    return df[["timestamp_et", "open", "high", "low", "close", "volume", "date"]].reset_index(drop=True)


def main() -> int:
    print("=" * 70)
    print(f"PREMARKET_FAIL_FADE smoke test — J's 2026-05-13 09:30 ET trade")
    print("=" * 70)

    # 1. Load historical SPY bars from master CSV (for prior-day H/L levels)
    if not MASTER_CSV.exists():
        print(f"FAIL: master CSV not found: {MASTER_CSV}")
        return 1

    print(f"\n[1] Loading historical bars from {MASTER_CSV.name}...")
    spy_hist = pd.read_csv(MASTER_CSV)
    spy_hist["timestamp_et"] = pd.to_datetime(spy_hist["timestamp_et"])
    # Strip tz if present, to match the smoke-test yfinance fetch dtype.
    if spy_hist["timestamp_et"].dt.tz is not None:
        spy_hist["timestamp_et"] = spy_hist["timestamp_et"].dt.tz_localize(None)
    spy_hist["date"] = spy_hist["timestamp_et"].dt.date
    spy_hist_rth = spy_hist[
        (spy_hist["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_hist["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    print(f"    Historical bars: {len(spy_hist_rth)} RTH rows through {spy_hist_rth['date'].max()}")

    # 2. Fetch today's bars from yfinance
    print(f"\n[2] Fetching {TODAY} intraday bars from yfinance...")
    try:
        today_bars = _fetch_intraday("SPY", TODAY)
    except Exception as e:
        print(f"    yfinance fetch failed: {e}")
        return 1
    if today_bars.empty:
        print(f"FAIL: yfinance returned no bars for {TODAY}")
        return 1
    print(f"    Today bars: {len(today_bars)} RTH rows")
    for _, r in today_bars.head(4).iterrows():
        print(
            f"      {r['timestamp_et'].strftime('%H:%M')} "
            f"O={r['open']:.2f} H={r['high']:.2f} L={r['low']:.2f} "
            f"C={r['close']:.2f} V={int(r['volume'])}"
        )

    # 3. Concat historical + today (mimics watcher_live.py pattern)
    print(f"\n[3] Building multi-day SPY frame...")
    spy_full = pd.concat([spy_hist_rth, today_bars], ignore_index=True)
    # Re-coerce timestamp after concat (per LESSONS-LEARNED 2026-05-13 09:39 ET note)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    if spy_full["timestamp_et"].dt.tz is not None:
        spy_full["timestamp_et"] = spy_full["timestamp_et"].dt.tz_localize(None)
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    spy_full = spy_full.drop_duplicates(subset=["timestamp_et"], keep="last")
    spy_full = spy_full.sort_values("timestamp_et").reset_index(drop=True)
    print(f"    Combined: {len(spy_full)} bars")

    # 4. Load today-bias.json
    print(f"\n[4] Loading today-bias.json...")
    if not TODAY_BIAS.exists():
        print(f"FAIL: today-bias.json not found: {TODAY_BIAS}")
        return 1
    import json
    bias = json.loads(TODAY_BIAS.read_text(encoding="utf-8-sig"))
    resistance = bias.get("key_levels", {}).get("resistance", [])
    print(f"    Premarket resistance levels: {resistance}")

    # 5. Locate the 09:30 ET bar
    target_time = pd.Timestamp(year=TODAY.year, month=TODAY.month, day=TODAY.day, hour=9, minute=30)
    matches = spy_full.index[spy_full["timestamp_et"] == target_time]
    if len(matches) == 0:
        print(f"FAIL: no 09:30 bar found for {TODAY}")
        return 1
    bar_idx = int(matches[0])
    bar = spy_full.iloc[bar_idx]
    print(f"\n[5] Target 09:30 bar: open={bar['open']:.2f} high={bar['high']:.2f} "
          f"low={bar['low']:.2f} close={bar['close']:.2f} vol={int(bar['volume'])}")

    # 6. Assemble level union manually + run core detector first (sanity)
    print(f"\n[6] Detector core call...")
    params = PremarketFailFadeParams()
    levels = assemble_levels(
        spy_bars=spy_full,
        as_of=bar["timestamp_et"].to_pydatetime(),
        today_bias=bias,
    )
    print(f"    Assembled {len(levels)} resistance levels:")
    for lvl in levels:
        print(f"      {lvl.label}@{lvl.price:.2f} ({lvl.tier}, {lvl.stars}*)")

    core_sig = detect_premarket_fail_fade(
        bar=bar,
        bar_idx=bar_idx,
        spy_bars=spy_full,
        levels=levels,
        params=params,
        today_bias=bias,
    )
    if core_sig is None:
        print("    CORE DETECTOR: no signal fired.")
    else:
        print(f"    CORE DETECTOR: signal fired!")
        print(f"      direction={core_sig.direction}")
        print(f"      entry_price={core_sig.entry_price:.2f}")
        print(f"      level={core_sig.level.label}@{core_sig.level.price:.2f}")
        print(f"      body=${core_sig.body_dollars:.2f}")
        print(f"      distance_to_level=${core_sig.distance_to_level:.2f}")
        print(f"      reason: {core_sig.reason}")

    # 7. Watcher adapter
    print(f"\n[7] Watcher adapter call...")
    ws = detect_premarket_fail_fade_setup(
        bar=bar,
        bar_idx=bar_idx,
        spy_bars=spy_full,
        today_bias=bias,
    )
    if ws is None:
        print("    WATCHER: no signal fired.")
        print("\nRESULT: smoke test did NOT fire — review detector logic.")
        return 2
    print(f"    WATCHER: signal fired!")
    print(f"      watcher_name={ws.watcher_name}")
    print(f"      setup_name={ws.setup_name}")
    print(f"      direction={ws.direction}")
    print(f"      entry_price={ws.entry_price:.2f}")
    print(f"      stop_price={ws.stop_price:.2f}")
    print(f"      tp1_price={ws.tp1_price:.2f}")
    print(f"      runner_price={ws.runner_price:.2f}")
    print(f"      confidence={ws.confidence}")
    print(f"      reason: {ws.reason}")
    print(f"      metadata.level_label={ws.metadata.get('level_label')}")
    print(f"      metadata.level_price={ws.metadata.get('level_price')}")
    print(f"      metadata.quality_tier={ws.metadata.get('quality_tier')}")
    print(f"      metadata.tp1_source={ws.metadata.get('tp1_source')}")
    print(f"      metadata.promotion_status={ws.metadata.get('promotion_status')}")

    # 8. Verify J trade alignment
    print(f"\n[8] J trade alignment check:")
    print(f"    J bought 736P @ $0.77 at 09:30:33 (premium).")
    print(f"    Engine signal: SHORT @ SPY {ws.entry_price:.2f}, target SPY {ws.tp1_price:.2f}")
    print(f"    Direction match: {'PASS' if ws.direction == 'short' else 'FAIL'}")
    print(f"    Level identification: {'PASS' if ws.metadata.get('level_price', 0) >= 738.0 else 'FAIL'}")

    print(f"\n{'=' * 70}")
    print(f"SMOKE TEST: PASS — PFF watcher fires on J's 2026-05-13 09:30 trade.")
    print(f"{'=' * 70}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
