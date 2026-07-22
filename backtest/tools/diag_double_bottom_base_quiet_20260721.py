"""Diagnostic (read-only, no trading-path edits) for LANE-A CAPABILITY GAP #2:
double_bottom_base_quiet fired ZERO times since arming 2026-06-01 (20+ days), including on
2026-07-21's textbook 08:15/10:15 double bottom (markdown/doctrine/DOJO-HARVEST-2026-07-21.md).

Traces the EXACT live-shape pipeline:
  1. What raw bars actually exist at 08:15 and 10:15 ET on 2026-07-21 (spy_5m cache).
  2. Whether ctx.prior_bars (as heartbeat_core._build_payload constructs it LIVE, RTH-only
     >=09:30 <16:00 -- setup/scripts/heartbeat_core.py:551-556) still contains the 08:15 bar
     by the time the 10:15 bar is the trigger.
  3. Whether backtest.lib.watchers.double_bottom_base_quiet_watcher.detect_db_base_quiet_setup
     fires at 10:15 given the REAL ctx built the way the live/backtest path builds it, with a
     per-gate trace (RTH window / VIX / cooldown / pattern-detected / confidence / proximity).
  4. crypto.lib.chart_patterns.double_bottom_detector run directly on the RTH-only tail(30)
     window at 10:15, with the underlying local-low search shown explicitly.
  5. A zero-fire scan across every cached trading day covering 2026-06-01 (arm date) through
     2026-07-21, importing the REAL watcher function (no re-implementation), to check
     dead-by-design vs dead-by-bug (project lesson class C14 vary-and-assert).

NO trading-path files are modified. NO orders. NO git ops. Pure read + report.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for p in ("backtest", "setup/scripts", "."):
    ap = str(ROOT / p) if p != "." else str(ROOT)
    if ap not in sys.path:
        sys.path.insert(0, ap)

ET = ZoneInfo("America/New_York")
DATA_DIR = ROOT / "backtest" / "data"

from lib.filters import BarContext  # noqa: E402
from lib.watchers.double_bottom_base_quiet_watcher import (  # noqa: E402
    detect_db_base_quiet_setup,
    _WINDOW_BARS,
)
from crypto.lib.chart_patterns import double_bottom_detector, Bar  # noqa: E402


def _tz_aware(series: pd.Series) -> pd.Series:
    as_str = series.astype("string").str.strip()
    has_offset = bool(as_str.str.contains(r"(?:[+-]\d{2}:?\d{2}|Z)$", regex=True, na=False).any())
    if has_offset:
        return pd.to_datetime(series, utc=True).dt.tz_convert(ET)
    parsed = pd.to_datetime(series)
    if parsed.dt.tz is None:
        return parsed.dt.tz_localize(ET)
    return parsed.dt.tz_convert(ET)


def load_cache(prefix: str, day: dt.date) -> pd.DataFrame:
    pattern = re.compile(rf"^{prefix}_(\d{{4}}-\d{{2}}-\d{{2}})_(\d{{4}}-\d{{2}}-\d{{2}})\.csv$")
    candidates = []
    for f in DATA_DIR.glob(f"{prefix}_*.csv"):
        m = pattern.match(f.name)
        if not m:
            continue
        start = dt.date.fromisoformat(m.group(1))
        end = dt.date.fromisoformat(m.group(2))
        if start <= day <= end:
            candidates.append((end, f))
    if not candidates:
        raise FileNotFoundError(f"no {prefix} cache covers {day}")
    candidates.sort(key=lambda t: t[0])
    df = pd.read_csv(candidates[0][1])
    df["timestamp_et"] = _tz_aware(df["timestamp_et"])
    return df


def section(title: str) -> None:
    print("\n" + "=" * 88)
    print(title)
    print("=" * 88)


# --------------------------------------------------------------------------- STEP 1: raw bars
section("STEP 1 -- raw spy_5m bars around 08:15 and 10:15 ET on 2026-07-21")
day = dt.date(2026, 7, 21)
full = load_cache("spy_5m", day)
today = full[full["timestamp_et"].dt.date == day].reset_index(drop=True)
print(f"Total bars cached for {day}: {len(today)}")
print(f"First bar: {today.iloc[0]['timestamp_et']}  Last bar: {today.iloc[-1]['timestamp_et']}")

window = today[(today["timestamp_et"].dt.time >= dt.time(8, 0)) & (today["timestamp_et"].dt.time <= dt.time(11, 20))]
print("\nRelevant bars (08:00-11:20 ET):")
for _, r in window.iterrows():
    t = r["timestamp_et"].strftime("%H:%M")
    flag = ""
    if t == "08:15":
        flag = "  <-- J's low #1 (PREMARKET)"
    if t == "10:15":
        flag = "  <-- J's low #2 (RTH)"
    if t == "11:05":
        flag = "  <-- J's bullish engulfing entry"
    print(f"  {t}  O={r['open']:.2f} H={r['high']:.2f} L={r['low']:.2f} C={r['close']:.2f} V={r['volume']:.0f}{flag}")

bar_0815 = today[today["timestamp_et"].dt.strftime("%H:%M") == "08:15"]
bar_1015 = today[today["timestamp_et"].dt.strftime("%H:%M") == "10:15"]
print(f"\n08:15 bar low = {bar_0815.iloc[0]['low']:.3f} (ET session bucket = PREMARKET, before 09:30 RTH open)")
print(f"10:15 bar low = {bar_1015.iloc[0]['low']:.3f}")
gap_bars = int((bar_1015.iloc[0]["timestamp_et"] - bar_0815.iloc[0]["timestamp_et"]).total_seconds() / 300)
print(f"Raw 5m-bar gap between the two lows (calendar, ALL bars incl. premarket): {gap_bars} bars ({gap_bars*5} min)")


# --------------------------------------------------------------------------- STEP 2: what the LIVE payload builder actually keeps
section("STEP 2 -- heartbeat_core._build_payload's RTH-only filter (setup/scripts/heartbeat_core.py:556)")
rth_today = today[(today["timestamp_et"].dt.time >= dt.time(9, 30)) & (today["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
has_0815 = (rth_today["timestamp_et"].dt.strftime("%H:%M") == "08:15").any()
print(f"Does the RTH-filtered frame (the ONLY frame the live engine ever builds prior_bars/ctx.prior_bars from) contain the 08:15 bar? {has_0815}")
print("heartbeat_core.py:551-556 quoted verbatim:")
print('  "RTH-ONLY (>=09:30, <16:00 ET) BEFORE anything -- the backtest computes its ribbon +')
print('  baselines on RTH-only bars (orchestrator.py:786-798, \\"matches the live indicator\\")."')
print("orchestrator.py:798-803 (the backtest/scan path double_bottom_base_quiet_watcher is scored under) is IDENTICAL:")
print('  "Split: RTH-only (>= 09:30, < 16:00) for ribbon + baselines + evaluation."')
print("\n==> The 08:15 premarket low is NEVER present in ctx.prior_bars at ANY point in the session,")
print("    in EITHER the live engine or the backtest/watcher scan path. This is upstream of the")
print("    watcher's own logic entirely -- the watcher is never even handed the data.")


# --------------------------------------------------------------------------- STEP 3: watcher gate trace at 08:15 and 10:15
section("STEP 3 -- detect_db_base_quiet_setup(ctx) gate-by-gate trace")

def make_ctx(trigger_time_str: str, prior_bars: pd.DataFrame, vix_now: float = 15.0, levels_active=None) -> BarContext:
    row = today[today["timestamp_et"].dt.strftime("%H:%M") == trigger_time_str].iloc[0]
    ts = row["timestamp_et"].to_pydatetime()
    return BarContext(
        bar_idx=len(prior_bars) - 1,
        timestamp_et=ts,
        bar=row,
        prior_bars=prior_bars,
        ribbon_now=None,
        ribbon_history=[],
        vix_now=vix_now,
        vix_prior=vix_now,
        vol_baseline_20=0.0,
        range_baseline_20=0.0,
        levels_active=levels_active or [],
        multi_day_levels=[],
        htf_15m_stack=None,
    )

# 08:15 attempt: prior_bars = ALL bars up to and incl 08:15 (as if the engine even offered it a look)
prior_at_0815 = today[today["timestamp_et"] <= bar_0815.iloc[0]["timestamp_et"]].reset_index(drop=True)
ctx_0815 = make_ctx("08:15", prior_at_0815)
sig_0815 = detect_db_base_quiet_setup(ctx_0815)
print(f"08:15 attempt -- bar_time={ctx_0815.timestamp_et.time()}  RTH_START gate (9:35) -- would fire: {sig_0815 is not None}")
print(f"  Gate 1 (RTH window >=9:35): 08:15 < 09:35 -> BLOCKS UNCONDITIONALLY (watcher line 175 'return None')")
print("  This means even feeding the watcher its ideal premarket data, gate 1 alone kills it 80 minutes before RTH open.")

# reset module cooldown state between the two probes (they share a module-level global)
import lib.watchers.double_bottom_base_quiet_watcher as dbq_mod
dbq_mod._last_signal_time = None

# 10:15 attempt: prior_bars = the RTH-only frame (matches live), tail(_WINDOW_BARS=30) as the watcher builds it
prior_at_1015_RTH = rth_today[rth_today["timestamp_et"] <= bar_1015.iloc[0]["timestamp_et"]].reset_index(drop=True)
ctx_1015 = make_ctx("10:15", prior_at_1015_RTH)
sig_1015 = detect_db_base_quiet_setup(ctx_1015)
print(f"\n10:15 attempt (RTH-only prior_bars, matches live/backtest exactly) -- would fire: {sig_1015 is not None}")
print(f"  Gate 1 (RTH window): {ctx_1015.timestamp_et.time()} within [09:35,15:55] -> PASS")
print(f"  Gate 2 (VIX<20): probe vix_now={ctx_1015.vix_now} -> PASS")
print(f"  Gate 3 (cooldown): module state reset for this probe -> PASS")
tail30 = ctx_1015.prior_bars.tail(_WINDOW_BARS)
print(f"  Gate 4 input: ctx.prior_bars.tail({_WINDOW_BARS}) spans {tail30.iloc[0]['timestamp_et'].strftime('%H:%M')} -> {tail30.iloc[-1]['timestamp_et'].strftime('%H:%M')} ET")
print(f"    (08:15 is {'PRESENT' if (tail30['timestamp_et'].dt.strftime('%H:%M') == '08:15').any() else 'ABSENT'} in this window -- confirms Step 2)")


# --------------------------------------------------------------------------- STEP 4: raw detector trace
section("STEP 4 -- crypto.lib.chart_patterns.double_bottom_detector direct trace on the RTH-only tail(30) at 10:15")

def to_bars(df: pd.DataFrame) -> list[Bar]:
    out = []
    for _, row in df.iterrows():
        out.append(Bar(
            open_time=row["timestamp_et"].astimezone(dt.timezone.utc),
            open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
            close=float(row["close"]), volume=float(row.get("volume", 50_000)),
            granularity_seconds=300, source="spy_5m",
        ))
    return out

bars_30 = to_bars(tail30)
# default lookback inside double_bottom_detector is 20 (the watcher calls it with NO lookback override)
hit_default = double_bottom_detector(bars_30)
print(f"double_bottom_detector(bars_30) with DEFAULT lookback=20 (watcher's actual call signature, watcher.py:193): hit={'FIRED: ' + str(hit_default.notes) if hit_default else None}")

window20 = bars_30[-20:]
print(f"\nThe internal lookback=20 window (what the detector ACTUALLY scans) spans:")
print(f"  {window20[0].open_time.astimezone(ET).strftime('%H:%M')} ET -> {window20[-1].open_time.astimezone(ET).strftime('%H:%M')} ET  ({len(window20)} bars)")
print(f"  08:15 present in this 20-bar scan window: {any(b.open_time.astimezone(ET).strftime('%H:%M') == '08:15' for b in window20)}")

# What local lows DOES the 20-bar window actually contain, and what pair does the algorithm pick?
def local_lows(bars):
    idxs = []
    for i in range(1, len(bars) - 1):
        if bars[i].low < bars[i - 1].low and bars[i].low < bars[i + 1].low:
            idxs.append(i)
    return idxs

lows_idx = local_lows(window20)
print(f"\nLocal lows found in the 20-bar window (index, ET time, low price):")
for i in lows_idx:
    b = window20[i]
    print(f"  idx={i}  {b.open_time.astimezone(ET).strftime('%H:%M')} ET  low={b.low:.3f}")

if len(lows_idx) >= 2:
    low1_idx, low2_idx = lows_idx[-2], lows_idx[-1]
    low1, low2 = window20[low1_idx].low, window20[low2_idx].low
    sep_pct = abs(low1 - low2) / max(low1, low2)
    bars_between = low2_idx - low1_idx - 1
    print(f"\nAlgorithm picks the LAST TWO local lows as the double-bottom candidate:")
    print(f"  low1 idx={low1_idx} ({window20[low1_idx].open_time.astimezone(ET).strftime('%H:%M')}) = {low1:.3f}")
    print(f"  low2 idx={low2_idx} ({window20[low2_idx].open_time.astimezone(ET).strftime('%H:%M')}) = {low2:.3f}")
    print(f"  separation_pct = {sep_pct:.5f}  vs tolerance_pct required < 0.0015 -> {'PASS' if sep_pct <= 0.0015 else 'FAIL'}")
    print(f"  bars_between = {bars_between}, min_separation_bars required >= 2 -> {'PASS' if bars_between + 1 >= 2 else 'FAIL'}")
else:
    print("\nFewer than 2 local lows in the 20-bar window -- pattern search aborts at Gate 4 'len(local_lows_idx) < 2' (line 154-155).")
    print("This is DOWNSTREAM of Step 2/4's window truncation: the true low1 (08:15, premarket) never enters ANY window this")
    print("detector is ever run against, at any lookback size <= the number of RTH bars between 09:30 and the current trigger.")

# Also show: even if we HYPOTHETICALLY ignored the RTH-filter and premarket-exclusion entirely and fed the raw
# ALL-bars-incl-premarket tail(30)/lookback(20), would it still fail on pure bar-count grounds?
section("STEP 4b -- counterfactual: bar-count math IF premarket bars were included (they are not, live)")
raw_gap_bars = gap_bars  # computed in Step 1
print(f"08:15 -> 10:15 raw calendar gap = {raw_gap_bars} bars ({raw_gap_bars*5} minutes)")
print(f"double_bottom_detector's default lookback=20 bars = 100 minutes of history from the trigger bar")
print(f"Even with premarket bars hypothetically included, {raw_gap_bars} bars > 20-bar lookback by {raw_gap_bars-20} bars")
print(f"({raw_gap_bars-20})*5 = {(raw_gap_bars-20)*5} minutes -- low1 (08:15) would ALREADY have scrolled out of the")
print("lookback window by the time low2 (10:15) is the trigger bar, independent of the RTH-filter issue.")
print("These are TWO INDEPENDENT binding constraints, either one alone is sufficient to kill this exact signal:")
print("  (a) RTH-only prior_bars construction (heartbeat_core.py:556 / orchestrator.py:803) strips 08:15 entirely.")
print("  (b) double_bottom_detector's default lookback=20 bars (100 min) < the 120-min real gap between the lows.")


# --------------------------------------------------------------------------- STEP 5: zero-fire scan across history
section("STEP 5 -- zero-fire scan: does detect_db_base_quiet_setup fire on ANY cached RTH day 2026-06-01..2026-07-21?")

dbq_mod._last_signal_time = None

all_days = sorted(today["timestamp_et"].dt.date.unique())  # placeholder, replaced below
full_cache = full  # the widest-window cache file already loaded covers back to 2026-05-19
cache_days = sorted(full_cache["timestamp_et"].dt.date.unique())
scan_days = [d for d in cache_days if dt.date(2026, 6, 1) <= d <= dt.date(2026, 7, 21)]
print(f"Cached trading days in [2026-06-01 (arm date), 2026-07-21]: {len(scan_days)}")

total_fires = 0
fire_log = []
for d in scan_days:
    dbq_mod._last_signal_time = None  # reset cooldown state per day (each day is an independent session)
    day_all = full_cache[full_cache["timestamp_et"].dt.date == d].reset_index(drop=True)
    day_rth = day_all[(day_all["timestamp_et"].dt.time >= dt.time(9, 30)) & (day_all["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    if len(day_rth) < 15:
        continue
    for i in range(len(day_rth)):
        prior = day_rth.iloc[: i + 1].reset_index(drop=True)
        ctx = make_ctx_row = BarContext(
            bar_idx=i,
            timestamp_et=day_rth.iloc[i]["timestamp_et"].to_pydatetime(),
            bar=day_rth.iloc[i],
            prior_bars=prior,
            ribbon_now=None,
            ribbon_history=[],
            vix_now=15.0,  # neutral LOW_VOL probe -- isolates the pattern/confidence/proximity gates
            vix_prior=15.0,
            vol_baseline_20=0.0,
            range_baseline_20=0.0,
            levels_active=[],  # no named levels -- isolates gate 4/5 from gate 6 (proximity)
            multi_day_levels=[],
            htf_15m_stack=None,
        )
        sig = detect_db_base_quiet_setup(ctx)
        if sig is not None:
            total_fires += 1
            fire_log.append((d, ctx.timestamp_et.strftime("%H:%M"), sig.metadata.get("confidence_score")))

print(f"\nTotal fires across {len(scan_days)} days, VIX pinned to 15.0 (always LOW_VOL) and levels_active=[] (never near-named): {total_fires}")
if fire_log:
    print("Fire log (date, time, confidence):")
    for d, t, c in fire_log[:30]:
        print(f"  {d} {t}  conf={c}")
else:
    print("ZERO fires even with the VIX and proximity gates forced maximally permissive.")
    print("This isolates the failure to Gate 4/5 (double_bottom_detector pattern + confidence<0.60) alone --")
    print("the pattern-detection step itself is the dead knob, not VIX regime or named-level proximity.")

# --------------------------------------------------------------------------- STEP 6: real-VIX scan
section("STEP 6 -- same scan with REAL VIX (not pinned to 15.0), levels_active still [] (isolates VIX's real effect)")
vix_full = load_cache("vix_5m", dt.date(2026, 7, 21))
dbq_mod._last_signal_time = None
total_fires_realvix = 0
fire_log_realvix = []
vix_missing_days = []
for d in scan_days:
    dbq_mod._last_signal_time = None
    day_all = full_cache[full_cache["timestamp_et"].dt.date == d].reset_index(drop=True)
    day_rth = day_all[(day_all["timestamp_et"].dt.time >= dt.time(9, 30)) & (day_all["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    day_vix = vix_full[vix_full["timestamp_et"].dt.date == d].reset_index(drop=True)
    if len(day_rth) < 15 or day_vix.empty:
        vix_missing_days.append(d)
        continue
    for i in range(len(day_rth)):
        ts = day_rth.iloc[i]["timestamp_et"]
        vix_upto = day_vix[day_vix["timestamp_et"] <= ts]
        if vix_upto.empty:
            continue
        vix_now_real = float(vix_upto.iloc[-1]["close"])
        prior = day_rth.iloc[: i + 1].reset_index(drop=True)
        ctx = BarContext(
            bar_idx=i,
            timestamp_et=ts.to_pydatetime(),
            bar=day_rth.iloc[i],
            prior_bars=prior,
            ribbon_now=None,
            ribbon_history=[],
            vix_now=vix_now_real,
            vix_prior=vix_now_real,
            vol_baseline_20=0.0,
            range_baseline_20=0.0,
            levels_active=[],
            multi_day_levels=[],
            htf_15m_stack=None,
        )
        sig = detect_db_base_quiet_setup(ctx)
        if sig is not None:
            total_fires_realvix += 1
            fire_log_realvix.append((d, ts.strftime("%H:%M"), round(vix_now_real, 2), sig.metadata.get("confidence_score")))

print(f"Days with no VIX cache coverage (skipped): {len(vix_missing_days)}")
print(f"Total fires across {len(scan_days) - len(vix_missing_days)} days, REAL VIX, levels_active=[] (proximity gate still neutralized): {total_fires_realvix}")
if fire_log_realvix:
    print("Fire log (date, time, vix_now, confidence):")
    for d, t, v, c in fire_log_realvix:
        print(f"  {d} {t}  vix={v}  conf={c}")
print(f"\n(Compare Step 5's {total_fires} fires with VIX pinned permissive-LOW_VOL(15.0) vs this step's {total_fires_realvix} with REAL VIX.")
print(" Difference isolates how much the VIX<20 gate itself contributes to the production near-silence,")
print(" independent of the still-neutralized proximity gate and of 2026-07-21's specific RTH-truncation issue.)")

print("\nDone.")
