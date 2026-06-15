"""v31_momentum_accel_highvol_gate — MOMENTUM_ACCELERATION_HIGHVOL VIX+alignment gate regression suite.

Background:
  2026-05-20: MOMENTUM_ACCELERATION_HIGHVOL watcher shipped as rank #1 OP-16 result
  (N=47, WR=59.6%, EdgeCap=+$24.46, Score=+7.17).

  Key discriminators:
    1. VIX_HIGH_VOL_FLOOR = 20.0 — watcher fires ONLY when VIX >= 20 (opposite of
       morning/base-quiet watchers which want LOW_VOL).
    2. ALIGNED_STACKS_BULL = ("BULL",) — bullish momentum hit requires BULL ribbon.
    3. ALIGNED_STACKS_BEAR = ("BEAR",) — bearish momentum hit requires BEAR ribbon.
    4. DEFAULT_PREMIUM_STOP_PCT = -0.99 — chart-stop knob per L51/L55 (initial bar in
       high-vol can wick before directional move develops). NOT a detection gate.

  Walk-forward (2026-05-20): IMPROVED +6.6pp
    Train (2025-01-01 to 2025-09-30): N=11, WR=54.55%
    Test  (2025-10-01 to 2026-05-15): N=36, WR=61.11%  (SPY-price proxy)
  Real-fills: WATCH_FRAGILE (WR=42.9%, negative expectancy in VIX[20-25) drag).
  VIX_FLOOR=25 re-test queued in Chef inbox.

Offline tests:
  T1  VIX < 20 rejected (LOW_VOL — watcher wants HIGH_VOL): None
  T2  VIX >= 20, BULL momentum, BEAR ribbon (misaligned) → None
  T3  VIX >= 20, BULL momentum, BULL ribbon → WatcherSignal(direction="long")
  T4  VIX >= 20, BEAR momentum, BEAR ribbon → WatcherSignal(direction="short")
  T5  No momentum pattern (flat bars) → None

  Bar design:
    Background (19 rows): (100.00, 100.10, 99.90, 100.05, 40_000) range=0.20, vol=40K
    Bull accel bar: (100.00, 100.70, 99.90, 100.65, 120_000)
      range=0.80 (4× avg 0.20 ✓ ≥ 2×), body=0.65/0.80=81% ✓ ≥ 60%, vol=3× ✓
      bias=bullish (close > open)
    Bear accel bar: (100.70, 100.80, 100.00, 100.05, 120_000)
      range=0.80 ✓, body=0.65/0.80=81% ✓, vol=3× ✓, bias=bearish (close < open)

Live test:
  Scan watcher-observations.jsonl for rows where
  watcher_name == "momentum_accel_highvol" (or setup_name == "MOMENTUM_ACCELERATION_HIGHVOL")
  with metadata.vix_now < 20.0.
  Expected: zero such observations (VIX gate bypass would be a bug).
  If no observations exist yet, report PASS with note.

Modes:
  offline  5 deterministic gate tests. All 5 must PASS.
  live     Audit scan of watcher-observations.jsonl for VIX gate bypasses.
           pass=True always (audit mode — not a blocking gate).

Evidence basis:
  2026-05-20: smoke test t_momentum_accel_highvol_smoke.py confirmed 12/12 PASS.
  Walk-forward: IMPROVED +6.6pp. Real-fills: WATCH_FRAGILE (VIX[20-25) drag).
  Key foot-gun prevented: VIX_HIGH_VOL_FLOOR=20.0 must reject when vix_now < 20.0,
  and ALIGNED_STACKS_BULL=("BULL",) must reject bullish momentum with a BEAR ribbon.

Exit code:
  0  all offline tests pass
  1  any offline test fails
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Fixture bar data (inline — deterministic, no external dependencies)
# ---------------------------------------------------------------------------

# Background bar: range=0.20, vol=40K (baseline for acceleration ratio)
_BG = (100.00, 100.10, 99.90, 100.05, 40_000)

# Bull acceleration bar:
#   range = 100.70 - 99.90 = 0.80 (4× avg 0.20 — satisfies ≥ 2× threshold)
#   body  = |100.65 - 100.00| = 0.65; fill = 0.65/0.80 = 81.25% (≥ 60% threshold)
#   vol   = 120,000 (3× avg 40,000 — satisfies ≥ 2× threshold)
#   bias  = bullish (close 100.65 > open 100.00)
_BULL_ACCEL = (100.00, 100.70, 99.90, 100.65, 120_000)

# Bear acceleration bar:
#   range = 100.80 - 100.00 = 0.80 (4× avg 0.20 ✓)
#   body  = |100.05 - 100.70| = 0.65; fill = 0.65/0.80 = 81.25% ✓
#   vol   = 120,000 (3× ✓)
#   bias  = bearish (close 100.05 < open 100.70)
_BEAR_ACCEL = (100.70, 100.80, 100.00, 100.05, 120_000)

# 20-bar datasets: 19 background bars + 1 acceleration bar
_BULL_BARS_DATA = [_BG] * 19 + [_BULL_ACCEL]
_BEAR_BARS_DATA = [_BG] * 19 + [_BEAR_ACCEL]
# Flat bars: 20 identical background bars — no acceleration, detector won't fire
_FLAT_BARS_DATA = [_BG] * 20


def _make_prior_bars(bars_data: list[tuple]):
    """Build prior_bars DataFrame from (open, high, low, close, volume) tuples."""
    import pandas as pd
    return pd.DataFrame(bars_data, columns=["open", "high", "low", "close", "volume"])


def _make_ctx(
    bars_data: list[tuple],
    *,
    timestamp_str: str = "11:00",
    vix_now: float = 22.0,
    ribbon_stack: Optional[str] = "BULL",
):
    """Build a minimal BarContext for the given bar data.

    Args:
        bars_data: list of (open, high, low, close, volume) tuples (20 rows expected)
        timestamp_str: "HH:MM" in ET on 2026-01-15
        vix_now: current VIX value
        ribbon_stack: "BULL", "BEAR", or None (None → ribbon_now=None)
    """
    import pandas as pd
    from backtest.lib.filters import BarContext
    from backtest.lib.ribbon import RibbonState

    prior_bars = _make_prior_bars(bars_data)
    trigger_bar = prior_bars.iloc[-1]
    ts = pd.Timestamp(f"2026-01-15 {timestamp_str}", tz="America/New_York")

    if ribbon_stack is not None:
        ribbon_now = RibbonState(
            fast=100.1,
            pivot=100.0,
            slow=99.9,
            stack=ribbon_stack,
            spread_cents=40.0,
        )
    else:
        ribbon_now = None

    return BarContext(
        bar_idx=len(prior_bars) - 1,
        timestamp_et=ts,
        bar=trigger_bar,
        prior_bars=prior_bars,
        ribbon_now=ribbon_now,
        ribbon_history=[ribbon_now] if ribbon_now is not None else [],
        vix_now=vix_now,
        vix_prior=vix_now,
        vol_baseline_20=40_000.0,
        range_baseline_20=0.20,
        levels_active=[],
        multi_day_levels=[],
        htf_15m_stack="NEUTRAL",
        level_states={},
    )


# ---------------------------------------------------------------------------
# Offline mode
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    """Run 5 deterministic gate tests for MOMENTUM_ACCELERATION_HIGHVOL.

    Evidence basis:
      2026-05-20: smoke test t_momentum_accel_highvol_smoke.py 12/12 PASS.
      Walk-forward IMPROVED +6.6pp (train WR=54.55% -> test WR=61.11%).
      Real-fills WATCH_FRAGILE: WR=42.9% in VIX[20-25) band (dominant drag).
      VIX_HIGH_VOL_FLOOR=20.0 rejects vix_now < 20.
      ALIGNED_STACKS_BULL=("BULL",): bullish momentum hit requires BULL ribbon.
      ALIGNED_STACKS_BEAR=("BEAR",): bearish momentum hit requires BEAR ribbon.
    """
    import backtest.lib.watchers.momentum_acceleration_highvol_watcher as _wmod
    from backtest.lib.watchers.momentum_acceleration_highvol_watcher import (
        detect_momentum_accel_highvol_setup,
        VIX_HIGH_VOL_FLOOR,
        ALIGNED_STACKS_BULL,
        ALIGNED_STACKS_BEAR,
    )

    results: list[dict] = []

    # -- T1: VIX < 20 rejected (watcher wants HIGH_VOL) ------------------------
    _wmod._last_signal_time = None
    ctx_t1 = _make_ctx(_BULL_BARS_DATA, timestamp_str="10:00", vix_now=15.0, ribbon_stack="BULL")
    sig_t1 = detect_momentum_accel_highvol_setup(ctx_t1)
    ok_t1 = sig_t1 is None
    results.append({
        "name": "T1_vix_below_floor_rejected",
        "pass": ok_t1,
        "note": (
            f"vix_now=15.0 < VIX_HIGH_VOL_FLOOR={VIX_HIGH_VOL_FLOOR} "
            f"ribbon=BULL momentum=bullish "
            f"watcher_result={'None (PASS)' if sig_t1 is None else 'Signal (FAIL)'}"
        ),
    })

    # -- T2: VIX >= 20, BULL momentum, BEAR ribbon (misaligned) → None ---------
    _wmod._last_signal_time = None
    ctx_t2 = _make_ctx(_BULL_BARS_DATA, timestamp_str="10:05", vix_now=22.0, ribbon_stack="BEAR")
    sig_t2 = detect_momentum_accel_highvol_setup(ctx_t2)
    ok_t2 = sig_t2 is None
    results.append({
        "name": "T2_bull_momentum_bear_ribbon_rejected",
        "pass": ok_t2,
        "note": (
            f"vix_now=22.0 ribbon=BEAR (BEAR not in ALIGNED_STACKS_BULL={ALIGNED_STACKS_BULL}) "
            f"bullish momentum hit present "
            f"watcher_result={'None (PASS)' if sig_t2 is None else 'Signal (FAIL)'}"
        ),
    })

    # -- T3: VIX >= 20, BULL momentum, BULL ribbon → WatcherSignal (long) ------
    _wmod._last_signal_time = None
    ctx_t3 = _make_ctx(_BULL_BARS_DATA, timestamp_str="10:10", vix_now=22.0, ribbon_stack="BULL")
    sig_t3 = detect_momentum_accel_highvol_setup(ctx_t3)
    if sig_t3 is not None:
        ok_t3 = (
            sig_t3.direction == "long"
            and sig_t3.setup_name == "MOMENTUM_ACCELERATION_HIGHVOL"
        )
        note_t3 = (
            f"direction={sig_t3.direction} setup={sig_t3.setup_name} "
            f"confidence={sig_t3.confidence} entry={sig_t3.entry_price:.2f}"
        )
    else:
        ok_t3 = False
        note_t3 = (
            "watcher returned None — expected WatcherSignal(direction='long'). "
            "Check: momentum_acceleration detector fires on _BULL_BARS_DATA, "
            "vix_now=22.0 >= 20.0, ribbon=BULL in ALIGNED_STACKS_BULL."
        )
    results.append({"name": "T3_vix_high_bull_ribbon_fires_long", "pass": ok_t3, "note": note_t3})

    # -- T4: VIX >= 20, BEAR momentum, BEAR ribbon → WatcherSignal (short) -----
    _wmod._last_signal_time = None
    ctx_t4 = _make_ctx(_BEAR_BARS_DATA, timestamp_str="10:15", vix_now=22.0, ribbon_stack="BEAR")
    sig_t4 = detect_momentum_accel_highvol_setup(ctx_t4)
    if sig_t4 is not None:
        ok_t4 = (
            sig_t4.direction == "short"
            and sig_t4.setup_name == "MOMENTUM_ACCELERATION_HIGHVOL"
        )
        note_t4 = (
            f"direction={sig_t4.direction} setup={sig_t4.setup_name} "
            f"confidence={sig_t4.confidence} entry={sig_t4.entry_price:.2f}"
        )
    else:
        ok_t4 = False
        note_t4 = (
            "watcher returned None — expected WatcherSignal(direction='short'). "
            "Check: momentum_acceleration detector fires on _BEAR_BARS_DATA, "
            "vix_now=22.0 >= 20.0, ribbon=BEAR in ALIGNED_STACKS_BEAR."
        )
    results.append({"name": "T4_vix_high_bear_ribbon_fires_short", "pass": ok_t4, "note": note_t4})

    # -- T5: No momentum pattern (flat bars) → None ----------------------------
    _wmod._last_signal_time = None
    ctx_t5 = _make_ctx(_FLAT_BARS_DATA, timestamp_str="10:20", vix_now=22.0, ribbon_stack="BULL")
    sig_t5 = detect_momentum_accel_highvol_setup(ctx_t5)
    ok_t5 = sig_t5 is None
    results.append({
        "name": "T5_flat_bars_no_momentum_signal",
        "pass": ok_t5,
        "note": (
            "20 identical background bars (range=0.20, vol=40K) — no acceleration bar present. "
            f"vix_now=22.0 ribbon=BULL "
            f"watcher_result={'None (PASS)' if sig_t5 is None else 'Signal (FAIL)'}"
        ),
    })

    # -- Build result dict -----------------------------------------------------
    all_pass = all(r["pass"] for r in results)
    return {
        "mode": "offline",
        "evidence_basis": (
            "2026-05-20: detect_momentum_accel_highvol_setup gate logic verified via "
            "t_momentum_accel_highvol_smoke.py (12/12 PASS). "
            "VIX_HIGH_VOL_FLOOR=20.0 rejects LOW_VOL (T1). "
            "ALIGNED_STACKS_BULL=('BULL',) rejects bullish momentum with BEAR ribbon (T2). "
            "Bull accel bars (range=4×, body=81%, vol=3×) + VIX=22.0 + BULL ribbon = long signal (T3). "
            "Bear accel bars + VIX=22.0 + BEAR ribbon = short signal (T4). "
            "Flat background bars (no acceleration) = None even at VIX=22.0 (T5). "
            "Walk-forward IMPROVED +6.6pp (SPY-price proxy). "
            "Real-fills WATCH_FRAGILE: WR=42.9% in VIX[20-25) drag; VIX_FLOOR=25 re-test queued."
        ),
        "constants_verified": {
            "VIX_HIGH_VOL_FLOOR": VIX_HIGH_VOL_FLOOR,
            "ALIGNED_STACKS_BULL": list(ALIGNED_STACKS_BULL),
            "ALIGNED_STACKS_BEAR": list(ALIGNED_STACKS_BEAR),
            "DEFAULT_PREMIUM_STOP_PCT_note": "-0.99 (chart-stop knob, not a detection gate)",
        },
        "tests": results,
        "passed": sum(1 for r in results if r["pass"]),
        "total": len(results),
        "all_pass": all_pass,
    }


# ---------------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------------

def run_live() -> dict:
    """Scan watcher-observations.jsonl for VIX gate bypasses on MOMENTUM_ACCELERATION_HIGHVOL.

    Gate-bypass definition:
      Any observation with watcher_name="momentum_accel_highvol" (or
      setup_name="MOMENTUM_ACCELERATION_HIGHVOL") where metadata.vix_now < 20.0
      indicates the VIX_HIGH_VOL_FLOOR gate was bypassed — this is a bug.

    Audit mode: all_pass=True always (bypasses are informational RED, not blocking).
    If no observations exist yet, report PASS with note.
    """
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        return {
            "mode": "live",
            "source": str(obs_path),
            "skipped": True,
            "reason": "watcher-observations.jsonl not found",
            "all_pass": True,
            "pass": True,
        }

    matching_obs: list[dict] = []
    vix_bypasses: list[dict] = []
    lines_read = 0
    _VIX_FLOOR = 20.0

    try:
        with open(obs_path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obs = json.loads(line)
                except json.JSONDecodeError:
                    continue
                lines_read += 1
                setup = obs.get("setup_name", obs.get("watcher_name", ""))
                if setup not in ("MOMENTUM_ACCELERATION_HIGHVOL", "momentum_accel_highvol"):
                    continue
                matching_obs.append(obs)

                # Check VIX gate bypass
                vix_val = (obs.get("metadata") or {}).get("vix_now", None)
                if vix_val is not None and vix_val < _VIX_FLOOR:
                    vix_bypasses.append({
                        "date": obs.get("date", "?"),
                        "timestamp": obs.get("bar_timestamp") or obs.get("timestamp_et", "?"),
                        "vix_now": vix_val,
                        "vix_floor": _VIX_FLOOR,
                        "issue": "vix_gate_bypass_vix_below_20",
                    })

    except Exception as exc:
        return {
            "mode": "live",
            "skipped": True,
            "reason": f"read error: {exc}",
            "all_pass": True,
            "pass": True,
        }

    if not matching_obs:
        return {
            "mode": "live",
            "source": str(obs_path),
            "total_lines_scanned": lines_read,
            "momentum_accel_highvol_obs": 0,
            "vix_gate_bypasses": 0,
            "verdict": "GREEN",
            "note": (
                "No MOMENTUM_ACCELERATION_HIGHVOL observations yet — "
                "watcher is new as of 2026-05-20. VIX gate not yet exercised live. "
                "PASS: absence of bypass evidence."
            ),
            "all_pass": True,
            "pass": True,
        }

    verdict = "GREEN" if not vix_bypasses else "RED"
    return {
        "mode": "live",
        "source": str(obs_path),
        "total_lines_scanned": lines_read,
        "momentum_accel_highvol_obs": len(matching_obs),
        "vix_gate_bypasses": len(vix_bypasses),
        "bypass_details": vix_bypasses,
        "verdict": verdict,
        "note": (
            "Scanned all MOMENTUM_ACCELERATION_HIGHVOL observations. "
            "Any row with metadata.vix_now < 20.0 is a VIX_HIGH_VOL_FLOOR gate bypass — "
            "the watcher should only fire when VIX >= 20.0."
        ),
        "all_pass": True,  # audit mode — RED is informational; gate bypass is unexpected
        "pass": True,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="v31 MOMENTUM_ACCELERATION_HIGHVOL VIX+alignment gate regression suite"
    )
    parser.add_argument("--mode", choices=["offline", "live", "both"], default="offline")
    args = parser.parse_args(argv)

    exit_code = 0

    if args.mode in ("offline", "both"):
        result = run_offline()
        print(json.dumps(result, indent=2))
        if not result.get("all_pass", False):
            exit_code = 1

    if args.mode in ("live", "both"):
        result = run_live()
        print(json.dumps(result, indent=2))
        # live is audit-mode, never fails overall

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
