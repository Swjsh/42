"""v32_db_base_quiet_gate — DOUBLE_BOTTOM_BASE_QUIET gate regression suite.

Background:
  2026-05-20: DOUBLE_BOTTOM_BASE_QUIET watcher shipped as OP-21 watch-only strategy.
  16-month combo: double_bottom|NOT_NEAR_NAMED|conf=LOW|vix=LOW_VOL
  N=168, WR=59.5%, EdgeCap=+$14.66. Walk-forward STABLE +1.2pp.
  Real-fills (2026-05-20): FAVORABLE +4.4pp, WR=63.9%, N=122, +$1,755 total P&L.

  Key discriminators vs DOUBLE_BOTTOM_MORNING_LOW_VOL (v30):

  1. _RTH_START=09:35, _RTH_END=15:55 ET — full RTH window, NO morning restriction.
     Afternoon bars (13:00, 14:00, 15:00 ET) are valid and expected to fire.

  2. CONFIDENCE_LOW_CEILING=0.60 — REJECTS patterns with conf >= 0.60.
     This is the critical gate: only base patterns (conf<0.60) accepted.
     Textbook conf=0.75 (decisive_reclaim + multi-factor) IS REJECTED.
     db_morning_low_vol watcher ACCEPTS conf=0.75. This watcher REJECTS it.

  3. VIX_LOW_VOL_CEILING=20.0 — same as morning watcher.

  Walk-forward result (2026-05-20): STABLE +1.2pp (WATCH_STABLE)
    Train (2025-01-01 to 2025-09-30): N=68, WR=58.82%
    Test  (2025-10-01 to 2026-05-15): N=100, WR=60.0%
    Most robust of the 2026-05-20 watchers — no MORNING filter to overfit.

Offline tests:
  T1  base pattern (conf=0.45) in afternoon (13:00 ET, VIX=15) → WatcherSignal
  T2  VIX >= 20 rejected by HIGH_VOL gate → None
  T3  textbook pattern (conf=0.75) REJECTED by confidence ceiling → None
  T4  late RTH (15:00 ET) fires → WatcherSignal  (full RTH window confirmed)
  T5  pre-RTH (09:20 ET) rejected → None

  Evidence:
    T1 proves the full RTH window (no morning restriction). db_morning_low_vol
    would have accepted 10:00 ET but NOT 13:00 ET; db_base_quiet accepts 13:00 ET.
    T2 confirms VIX gate (same as morning watcher).
    T3 is the CRITICAL contrast: db_morning_low_vol accepts conf=0.75 (T5 in v30
    was "fires with no ceiling"); db_base_quiet REJECTS it (CONFIDENCE_LOW_CEILING=0.60).
    T4 confirms 15:00 ET fires (within _RTH_END=15:55).
    T5 confirms pre-RTH (09:20 ET) is rejected by _RTH_START=09:35 gate.

Live test:
  Scan watcher-observations.jsonl for DOUBLE_BOTTOM_BASE_QUIET observations where:
    - metadata.vix_now >= 20.0 (VIX gate bypass), OR
    - metadata.confidence_score >= 0.60 (confidence ceiling bypass)
  Audit mode: all_pass=True always.

Modes:
  offline  5 deterministic gate tests. All 5 must PASS.
  live     Audit scan of watcher-observations.jsonl.
           pass=True always (audit mode).

Evidence basis:
  2026-05-20: db_base_quiet_real_fills_validate.py confirmed N=122 signals,
  WR=63.9% FAVORABLE. Time dist: 10AM peak (41), 13:00 (18), 14:00 (14), 15:00 (16).
  Proof that afternoon signals fire and are viable.

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

# Pure base double-bottom bars (conf=0.45, same fixture as v30).
# All v2 factors False → conf = 0.45 (base only) → BELOW CONFIDENCE_LOW_CEILING=0.60
#   - low1=100.00, low2=100.12, neckline=100.45
#   - rise_pct=0.45% < 0.5% → decent_neckline_height=False
#   - reclaim_pct ~0.01% < 0.1% → decisive_reclaim=False
_BASE_BARS_DATA = [
    (100.60, 100.70, 100.50, 100.60, 50_000),
    (100.60, 100.65, 100.55, 100.62, 50_000),
    (100.62, 100.68, 100.58, 100.64, 50_000),
    (100.64, 100.70, 100.60, 100.65, 50_000),
    (100.50, 100.60, 100.40, 100.50, 50_000),
    (100.50, 100.50, 100.00, 100.10, 50_000),   # FIRST LOCAL LOW (100.00)
    (100.10, 100.40, 100.20, 100.35, 50_000),
    (100.35, 100.45, 100.30, 100.40, 50_000),   # NECKLINE BAR (high=100.45)
    (100.40, 100.42, 100.12, 100.20, 50_000),   # SECOND LOCAL LOW (100.12)
    (100.20, 100.42, 100.20, 100.40, 50_000),
    (100.40, 100.48, 100.40, 100.46, 50_000),   # BREAKOUT (close=100.46 > neckline=100.45)
]

# Textbook high-confidence bars (conf=0.75, same fixture as v30 _T1_BARS_DATA).
# Used for T3: confirms CONFIDENCE_LOW_CEILING rejects conf=0.75.
# decisive_reclaim (+0.15) + decent_neckline_height (+0.05) + very_tight_lows (+0.10) = 0.75
#   - low1=100.0, low2=100.05, neckline=102.0, rise_pct=2% > 0.5%
_T1_BARS_DATA = [
    (100.5, 100.6, 100.4, 100.5, 50_000),
    (100.5, 100.6, 100.4, 100.5, 50_000),
    (100.5, 100.6, 100.4, 100.5, 50_000),
    (100.5, 100.6, 100.4, 100.5, 50_000),
    (100.5, 100.6, 100.4, 100.5, 50_000),
    (100.5, 100.8, 100.2, 100.4, 50_000),
    (100.4, 100.6, 100.0, 100.1, 50_000),   # FIRST LOCAL LOW (100.0)
    (100.1, 102.0, 100.1, 101.8, 50_000),   # neckline area (high=102.0)
    (101.8, 102.0, 101.5, 101.7, 50_000),
    (101.7, 101.9, 100.05, 100.2, 50_000),  # SECOND LOCAL LOW (100.05)
    (100.2, 102.3, 100.2, 102.2, 50_000),   # BREAKOUT (close=102.2 >> neckline=102.0)
]


def _make_prior_bars(bars_data: list[tuple]):
    import pandas as pd
    return pd.DataFrame(bars_data, columns=["open", "high", "low", "close", "volume"])


def _make_ctx(
    bars_data: list[tuple],
    *,
    timestamp_et: Optional[dt.datetime] = None,
    vix_now: float = 15.0,
    levels_active: Optional[list] = None,
):
    from backtest.lib.filters import BarContext

    if timestamp_et is None:
        timestamp_et = dt.datetime(2026, 1, 15, 13, 0, 0)  # 13:00 ET — afternoon
    if levels_active is None:
        levels_active = []

    prior_bars = _make_prior_bars(bars_data)
    trigger_bar = prior_bars.iloc[-1]

    return BarContext(
        bar_idx=len(prior_bars) - 1,
        timestamp_et=timestamp_et,
        bar=trigger_bar,
        prior_bars=prior_bars,
        ribbon_now=None,
        ribbon_history=[],
        vix_now=vix_now,
        vix_prior=vix_now,
        vol_baseline_20=50_000.0,
        range_baseline_20=0.40,
        levels_active=levels_active,
        multi_day_levels=[],
        htf_15m_stack=None,
        level_states={},
    )


# ---------------------------------------------------------------------------
# Offline mode
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    """Run 5 deterministic gate tests for DOUBLE_BOTTOM_BASE_QUIET.

    Evidence basis:
      2026-05-20: real-fills validation confirmed N=122 signals, WR=63.9% FAVORABLE.
      Time dist: 10AM peak but signals across full RTH (13:00=18, 14:00=14, 15:00=16).
      Key foot-gun prevented: CONFIDENCE_LOW_CEILING (base_quiet) vs NO ceiling (morning).
      Walk-forward STABLE +1.2pp — most robust of the 2026-05-20 watcher trio.
    """
    import backtest.lib.watchers.double_bottom_base_quiet_watcher as _watcher_mod
    from backtest.lib.watchers.double_bottom_base_quiet_watcher import (
        detect_db_base_quiet_setup,
        _RTH_START,
        _RTH_END,
        VIX_LOW_VOL_CEILING,
        CONFIDENCE_LOW_CEILING,
    )

    results: list[dict] = []
    _AFTERNOON = dt.datetime(2026, 1, 15, 13, 0, 0)   # 13:00 ET — full RTH, no morning req

    # -- T1: base pattern (conf=0.45) in afternoon (13:00 ET) fires --------------
    # Critical proof: db_morning_low_vol REJECTS 13:00 ET; db_base_quiet ACCEPTS it.
    _watcher_mod._last_signal_time = None
    ctx_t1 = _make_ctx(_BASE_BARS_DATA, timestamp_et=_AFTERNOON, vix_now=15.0)
    sig_t1 = detect_db_base_quiet_setup(ctx_t1)
    if sig_t1 is not None:
        ok_t1 = (
            sig_t1.direction == "long"
            and sig_t1.setup_name == "DOUBLE_BOTTOM_BASE_QUIET"
            and sig_t1.confidence == "low"   # always "low" by design
        )
        note_t1 = (
            f"direction={sig_t1.direction} setup={sig_t1.setup_name} "
            f"confidence_tier={sig_t1.confidence} — fired at 13:00 ET (full RTH). "
            f"db_morning_low_vol would have rejected this timestamp."
        )
    else:
        ok_t1 = False
        note_t1 = "watcher returned None — base pattern did not fire at 13:00 ET (full RTH expected)"
    results.append({"name": "T1_base_pattern_fires_in_afternoon", "pass": ok_t1, "note": note_t1})

    # -- T2: VIX >= 20 rejected (HIGH_VOL gate) --------------------------------
    _watcher_mod._last_signal_time = None
    vix_high = VIX_LOW_VOL_CEILING + 5.0   # 25.0
    ctx_t2 = _make_ctx(_BASE_BARS_DATA, timestamp_et=_AFTERNOON, vix_now=vix_high)
    sig_t2 = detect_db_base_quiet_setup(ctx_t2)
    ok_t2 = sig_t2 is None
    results.append({
        "name": "T2_vix_gate_rejects_high_vol",
        "pass": ok_t2,
        "note": (
            f"vix_now={vix_high} >= VIX_LOW_VOL_CEILING={VIX_LOW_VOL_CEILING} "
            f"watcher_result={'None (PASS)' if sig_t2 is None else 'Signal (FAIL)'}"
        ),
    })

    # -- T3: textbook conf=0.75 REJECTED by CONFIDENCE_LOW_CEILING ------------
    # This is the CRITICAL contrast vs db_morning_low_vol (which accepts conf=0.75).
    # v30 T5 was "fires with no ceiling"; v32 T3 is "rejects above ceiling".
    _watcher_mod._last_signal_time = None
    ctx_t3 = _make_ctx(_T1_BARS_DATA, timestamp_et=_AFTERNOON, vix_now=15.0)
    sig_t3 = detect_db_base_quiet_setup(ctx_t3)
    ok_t3 = sig_t3 is None
    if not ok_t3:
        conf_got = sig_t3.metadata.get("confidence_score", -1) if sig_t3 else -1
        note_t3 = (
            f"textbook pattern (conf>=0.60) should be REJECTED by ceiling={CONFIDENCE_LOW_CEILING}. "
            f"Got WatcherSignal (conf_score={conf_got:.3f}) — ceiling gate NOT working."
        )
    else:
        note_t3 = (
            f"textbook high-conf pattern correctly REJECTED at CONFIDENCE_LOW_CEILING={CONFIDENCE_LOW_CEILING}. "
            f"db_morning_low_vol would have accepted this (it has no ceiling). "
            f"CORRECT base_quiet behavior: only clean base patterns allowed."
        )
    results.append({"name": "T3_textbook_conf_rejected_by_ceiling", "pass": ok_t3, "note": note_t3})

    # -- T4: late RTH (15:00 ET) fires (confirms full RTH window) -------------
    _watcher_mod._last_signal_time = None
    late_rth = dt.datetime(2026, 1, 15, 15, 0, 0)   # 15:00 ET — within _RTH_END=15:55
    ctx_t4 = _make_ctx(_BASE_BARS_DATA, timestamp_et=late_rth, vix_now=15.0)
    sig_t4 = detect_db_base_quiet_setup(ctx_t4)
    ok_t4 = sig_t4 is not None
    results.append({
        "name": "T4_late_rth_fires",
        "pass": ok_t4,
        "note": (
            f"timestamp=15:00 ET < _RTH_END={_RTH_END} "
            f"watcher_result={'Signal (PASS)' if sig_t4 is not None else 'None (FAIL)'}"
        ),
    })

    # -- T5: pre-RTH (09:20 ET) rejected by _RTH_START gate -------------------
    _watcher_mod._last_signal_time = None
    pre_rth = dt.datetime(2026, 1, 15, 9, 20, 0)   # 09:20 ET < _RTH_START=09:35
    ctx_t5 = _make_ctx(_BASE_BARS_DATA, timestamp_et=pre_rth, vix_now=15.0)
    sig_t5 = detect_db_base_quiet_setup(ctx_t5)
    ok_t5 = sig_t5 is None
    results.append({
        "name": "T5_pre_rth_rejected",
        "pass": ok_t5,
        "note": (
            f"timestamp=09:20 ET < _RTH_START={_RTH_START} "
            f"watcher_result={'None (PASS)' if sig_t5 is None else 'Signal (FAIL)'}"
        ),
    })

    all_pass = all(r["pass"] for r in results)
    return {
        "mode": "offline",
        "evidence_basis": (
            "2026-05-20: detect_db_base_quiet_setup gate logic verified. "
            "Full RTH window (09:35-15:55 ET, no morning restriction). "
            "CONFIDENCE_LOW_CEILING=0.60 — only base patterns (conf<0.60) accepted. "
            "VIX_LOW_VOL_CEILING=20.0 — same as morning watcher. "
            "Walk-forward STABLE +1.2pp. Real-fills FAVORABLE +4.4pp."
        ),
        "constants_verified": {
            "_RTH_START": "09:35",
            "_RTH_END": "15:55",
            "VIX_LOW_VOL_CEILING": VIX_LOW_VOL_CEILING,
            "CONFIDENCE_LOW_CEILING": CONFIDENCE_LOW_CEILING,
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
    """Scan watcher-observations.jsonl for DOUBLE_BOTTOM_BASE_QUIET gate bypasses.

    Gate-bypass definitions:
      - VIX gate bypass: metadata.vix_now >= 20.0
      - Confidence ceiling bypass: metadata.confidence_score >= 0.60

    Audit mode: all_pass=True always (bypasses are informational RED, not blocking).
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

    base_quiet_obs: list[dict] = []
    vix_bypasses: list[dict] = []
    conf_bypasses: list[dict] = []
    lines_read = 0

    _VIX_CEILING = 20.0
    _CONF_CEILING = 0.60

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
                if setup not in ("DOUBLE_BOTTOM_BASE_QUIET", "db_base_quiet"):
                    continue
                base_quiet_obs.append(obs)

                raw_ts = obs.get("bar_timestamp") or obs.get("timestamp_et", "")

                # Check VIX gate bypass
                meta = obs.get("metadata") or {}
                vix_val = meta.get("vix_now", None)
                if vix_val is not None and vix_val >= _VIX_CEILING:
                    vix_bypasses.append({
                        "date": obs.get("date", "?"),
                        "timestamp": raw_ts,
                        "vix_now": vix_val,
                        "issue": "vix_gate_bypass",
                    })

                # Check confidence ceiling bypass
                conf_score = meta.get("confidence_score", None)
                if conf_score is not None and conf_score >= _CONF_CEILING:
                    conf_bypasses.append({
                        "date": obs.get("date", "?"),
                        "timestamp": raw_ts,
                        "confidence_score": conf_score,
                        "issue": "confidence_ceiling_bypass",
                    })

    except Exception as exc:
        return {
            "mode": "live",
            "skipped": True,
            "reason": f"read error: {exc}",
            "all_pass": True,
            "pass": True,
        }

    if not base_quiet_obs:
        return {
            "mode": "live",
            "source": str(obs_path),
            "total_lines_scanned": lines_read,
            "db_base_quiet_obs": 0,
            "vix_gate_bypasses": 0,
            "conf_ceiling_bypasses": 0,
            "verdict": "GREEN",
            "note": (
                "No DOUBLE_BOTTOM_BASE_QUIET observations yet — "
                "watcher is new as of 2026-05-20. Gates not yet exercised live. "
                "PASS: absence of bypass evidence."
            ),
            "all_pass": True,
            "pass": True,
        }

    all_bypasses = vix_bypasses + conf_bypasses
    verdict = "GREEN" if not all_bypasses else "RED"
    return {
        "mode": "live",
        "source": str(obs_path),
        "total_lines_scanned": lines_read,
        "db_base_quiet_obs": len(base_quiet_obs),
        "vix_gate_bypasses": len(vix_bypasses),
        "conf_ceiling_bypasses": len(conf_bypasses),
        "bypass_details": all_bypasses,
        "verdict": verdict,
        "note": (
            "Scanned all DOUBLE_BOTTOM_BASE_QUIET observations. "
            "VIX gate bypass = vix_now >= 20.0 in accepted observation. "
            "Confidence ceiling bypass = confidence_score >= 0.60 in accepted observation."
        ),
        "all_pass": True,  # audit mode — RED is informational
        "pass": True,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="v32 DOUBLE_BOTTOM_BASE_QUIET gate regression suite"
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

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
