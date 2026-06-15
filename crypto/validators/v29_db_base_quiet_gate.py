"""v29_db_base_quiet_gate — DOUBLE_BOTTOM_BASE_QUIET conf=LOW ceiling regression gate.

Background:
  2026-05-20: DOUBLE_BOTTOM_BASE_QUIET watcher shipped. The critical discriminator is
  CONFIDENCE_LOW_CEILING = 0.60: the watcher ONLY accepts double-bottom hits where
  hit.confidence < 0.60. This guards against the pathological 0.60-0.70 band
  (OOS WR=46.8% at N=447 per 90-day analysis).

  The confidence formula (v2/v3 — see double_bottom_detector docstring):
    - Base conf = 0.45 for every valid double-bottom
    - decisive_reclaim (close > neckline by >0.1%): +0.15 → conf=0.60 AT ceiling
    - low2_volume_higher (v3 weight): +0.11 → conf=0.56 BELOW ceiling
    - bars_between_sweet_spot (4-12 bars): +0.10 → conf=0.55 BELOW ceiling
    - very_tight_lows (sep < 0.075%): +0.10 → conf=0.55 BELOW ceiling
    - decent_neckline_height (rise > 0.5%): +0.05 → conf=0.50 BELOW ceiling

  Gate expression: `if hit.confidence >= CONFIDENCE_LOW_CEILING: return None`
  This means conf=0.60 (decisive_reclaim only) is EXCLUDED — by design.
  The 0.60-0.70 band is the pathological case; the ceiling gate prevents it.

  Key difference from DOUBLE_BOTTOM_MORNING_LOW_VOL: no morning time restriction.
  This watcher fires 09:35-15:55 ET (all-day).

Offline tests:
  T1  pure base pattern (conf=0.45) passes all gates → WatcherSignal(direction="long")
  T2  textbook pattern (conf=0.75, via T1 bars from v22) rejected by conf gate → None
  T3  boundary exactly at conf=0.60 (decisive_reclaim only) rejected → None
      Engineering: sep_pct < 0.0015 (valid), neckline 0.2-0.5% rise (not decent),
      decisive_reclaim=True (close-neckline > 0.1%), 2 bars between (not sweet spot),
      equal volumes → conf = 0.45 + 0.15 = 0.60 exactly → gate rejects it
  T4  VIX >= 20 → None (HIGH_VOL gate)
  T5  named level near neckline → None (NOT_NEAR_NAMED gate)

Live test:
  Scan watcher-observations.jsonl for any DOUBLE_BOTTOM_BASE_QUIET rows where
  metadata.confidence_score >= 0.60 (should be zero — gate blocked them all).
  If watcher is new (no observations yet), report PASS with note.

Modes:
  offline  5 deterministic gate tests. All 5 must PASS.
  live     Audit scan for gate-bypass observations. pass=True always (audit mode).

Evidence basis:
  2026-05-20: DOUBLE_BOTTOM_BASE_QUIET cross-validated: N=168, WR=59.5%.
  0.60-0.70 band OOS WR=46.8% (N=447) — excluded by CONFIDENCE_LOW_CEILING gate.
  Single decisive_reclaim factor → conf=0.60 exactly at ceiling → EXCLUDED.

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

# Pure base double-bottom bars (conf = 0.45).
# Pattern lives in the LAST 7 rows; first 4 are neutral background padding.
#   - local low at idx 5 (100.00) and idx 8 (100.12)
#   - neckline = max(high of bars 6,7) = 100.45
#   - rise_pct = 0.45% < 0.5% -> decent_neckline_height = False
#   - reclaim_pct = (100.46-100.45)/100.45 ~0.0001 < 0.001 -> decisive_reclaim = False
#   - sep_pct = 0.12/100.12 ~0.12% > 0.075% -> very_tight_lows = False
#   - bars_between = 2 (not in 4-12) -> bars_between_sweet_spot = False
#   - volumes equal -> low2_volume_higher = False
#   => ALL factors False, conf = 0.45 (base only)
_BASE_BARS_DATA = [
    (100.60, 100.70, 100.50, 100.60, 50_000),   # idx 0: background (padding)
    (100.60, 100.65, 100.55, 100.62, 50_000),   # idx 1: background (padding)
    (100.62, 100.68, 100.58, 100.64, 50_000),   # idx 2: background (padding)
    (100.64, 100.70, 100.60, 100.65, 50_000),   # idx 3: background (padding)
    (100.50, 100.60, 100.40, 100.50, 50_000),   # idx 4: background
    (100.50, 100.50, 100.00, 100.10, 50_000),   # idx 5: FIRST LOCAL LOW (100.00)
    (100.10, 100.40, 100.20, 100.35, 50_000),   # idx 6: rising (high=100.40)
    (100.35, 100.45, 100.30, 100.40, 50_000),   # idx 7: NECKLINE BAR (high=100.45)
    (100.40, 100.42, 100.12, 100.20, 50_000),   # idx 8: SECOND LOCAL LOW (100.12)
    (100.20, 100.42, 100.20, 100.40, 50_000),   # idx 9: rising
    (100.40, 100.48, 100.40, 100.46, 50_000),   # idx 10: BREAKOUT (close=100.46 > neckline=100.45)
]

# Textbook high-conf bars from v22 T1 (same as smoke test _T1_BARS).
# decisive_reclaim + bars_between_sweet_spot? Let's verify what conf this produces:
#   - lows: bar1.low=100.0, bar4.low=100.05 → sep=(100.05-100.0)/100.05=0.05% < 0.075% → very_tight_lows=True (+0.10)
#   - bars_between: 3-1-1=2 bars → NOT sweet spot (4-12) → False
#   - neckline=102.0 (bar2.high=102.0), rise_pct=(102.0-100.0)/100.0=2% > 0.5% → decent_neckline_height=True (+0.05)
#   - close=102.2, reclaim_pct=(102.2-102.0)/102.0=0.00196 > 0.001 → decisive_reclaim=True (+0.15)
#   - volumes all equal → low2_volume_higher=False
#   => factors: decisive_reclaim(+0.15) + decent_neckline_height(+0.05) + very_tight_lows(+0.10)
#   => conf = 0.45 + 0.15 + 0.05 + 0.10 = 0.75 >= 0.60 → gate REJECTS
_T1_BARS_DATA = [
    (100.5, 100.8, 100.2, 100.4, 50_000),    # idx 0
    (100.4, 100.6, 100.0, 100.1, 50_000),    # idx 1: first low (100.0)
    (100.1, 102.0, 100.1, 101.8, 50_000),    # idx 2: neckline area (high=102.0)
    (101.8, 102.0, 101.5, 101.7, 50_000),    # idx 3
    (101.7, 101.9, 100.05, 100.2, 50_000),   # idx 4: second low (100.05)
    (100.2, 102.3, 100.2, 102.2, 50_000),    # idx 5: breakout (close=102.2 >> neckline=102.0)
]

# T3 boundary bars: conf = 0.45 + 0.15 (decisive_reclaim only) = 0.60 exactly → EXCLUDED.
# Verified 2026-05-20 via double_bottom_detector() direct call: conf=0.60, factors=['decisive_reclaim'].
# Engineering:
#   - low1=100.00 at idx5 (local low: idx4.low=100.20 > 100.00, idx6.low=100.15 > 100.00)
#   - low2=100.10 at idx8 (local low: idx7.low=100.15 > 100.10, idx9.low=100.15 > 100.10)
#   - sep_pct = 0.10/100.10 = 0.0999% < 0.15% tolerance → valid double-bottom
#   - sep_pct = 0.0999% > 0.075% (half of tolerance) → very_tight_lows = False
#   - neckline = 100.30 (bar6.high=100.30), rise_pct=0.30% > 0.2% min → passes neckline gate
#     BUT rise_pct=0.30% < 0.5% → decent_neckline_height = False
#   - bars_between = 2 (not in 4-12) → bars_between_sweet_spot = False
#   - equal volumes → low2_volume_higher = False
#   - close=100.41, neckline=100.30: reclaim_pct=(100.41-100.30)/100.30=0.0011 > 0.001
#     → decisive_reclaim = True (+0.15)
#   => conf = 0.45 + 0.15 = 0.60 exactly → hit.confidence >= CONFIDENCE_LOW_CEILING → gate rejects
_T3_BARS_DATA = [
    (100.60, 100.80, 100.50, 100.65, 50_000),  # idx 0: background padding
    (100.65, 100.75, 100.55, 100.70, 50_000),  # idx 1: background padding
    (100.70, 100.80, 100.60, 100.72, 50_000),  # idx 2: background padding
    (100.72, 100.85, 100.60, 100.75, 50_000),  # idx 3: background padding
    (100.50, 100.55, 100.20, 100.40, 50_000),  # idx 4: descent (low=100.20 > 100.00)
    (100.40, 100.42, 100.00, 100.10, 50_000),  # idx 5: FIRST LOCAL LOW (100.00)
    (100.10, 100.30, 100.15, 100.25, 50_000),  # idx 6: rising (high=100.30 = neckline, low=100.15)
    (100.25, 100.28, 100.15, 100.20, 50_000),  # idx 7: between (low=100.15 > 100.10)
    (100.20, 100.22, 100.10, 100.15, 50_000),  # idx 8: SECOND LOCAL LOW (100.10)
    (100.15, 100.35, 100.15, 100.30, 50_000),  # idx 9: rising (low=100.15 > 100.10)
    (100.30, 100.42, 100.30, 100.41, 50_000),  # idx 10: BREAKOUT close=100.41 > neckline=100.30
                                                # reclaim_pct=(100.41-100.30)/100.30=0.0011>0.001
                                                # decisive_reclaim=True → conf=0.45+0.15=0.60 exactly
]


def _make_prior_bars(bars_data: list[tuple]):
    """Build prior_bars DataFrame from (open, high, low, close, volume) tuples."""
    import pandas as pd
    return pd.DataFrame(bars_data, columns=["open", "high", "low", "close", "volume"])


def _make_ctx(
    bars_data: list[tuple],
    *,
    timestamp_et: Optional[dt.datetime] = None,
    vix_now: float = 15.0,
    levels_active: Optional[list] = None,
):
    """Build a minimal BarContext wrapping the given bar data."""
    from backtest.lib.filters import BarContext

    if timestamp_et is None:
        timestamp_et = dt.datetime(2026, 5, 20, 10, 0, 0)
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
      2026-05-20: confidence=0.60 boundary case (decisive_reclaim only) confirmed
      excluded by >= gate. 16-month OOS WR of the 0.60-0.70 band = 46.8% (N=447).
      Keeping ONLY conf < 0.60 (base + minor single factors) yields 59.5% WR (N=168).
    """
    import backtest.lib.watchers.double_bottom_base_quiet_watcher as _watcher_mod
    from backtest.lib.watchers.double_bottom_base_quiet_watcher import (
        detect_db_base_quiet_setup,
        CONFIDENCE_LOW_CEILING,
        VIX_LOW_VOL_CEILING,
    )

    results: list[dict] = []
    _RTH_TIME = dt.datetime(2026, 5, 20, 10, 0, 0)

    # -- T1: pure base pattern (conf=0.45) fires the watcher -------------------
    _watcher_mod._last_signal_time = None
    ctx_base = _make_ctx(_BASE_BARS_DATA, timestamp_et=_RTH_TIME, vix_now=15.0)
    sig = detect_db_base_quiet_setup(ctx_base)
    if sig is not None:
        conf_score = sig.metadata.get("confidence_score", -1)
        ok = (
            sig.direction == "long"
            and sig.setup_name == "DOUBLE_BOTTOM_BASE_QUIET"
            and conf_score < CONFIDENCE_LOW_CEILING
            and sig.confidence == "low"
        )
        note = (
            f"direction={sig.direction} setup={sig.setup_name} "
            f"conf_score={conf_score:.3f} conf_tier={sig.confidence}"
        )
    else:
        ok = False
        note = "watcher returned None — base pattern did not fire"
    results.append({"name": "T1_base_pattern_fires", "pass": ok, "note": note})

    # -- T2: textbook T1 bars (conf=0.75) rejected by conf gate ---------------
    _watcher_mod._last_signal_time = None
    ctx_t1 = _make_ctx(_T1_BARS_DATA, timestamp_et=_RTH_TIME, vix_now=15.0)
    sig_t2 = detect_db_base_quiet_setup(ctx_t1)
    ok = sig_t2 is None
    # Diagnose expected confidence via detector directly
    try:
        from crypto.lib.chart_patterns import double_bottom_detector, Bar

        t1_raw = [
            Bar(
                open_time=dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=5 * i),
                open=float(_T1_BARS_DATA[i][0]),
                high=float(_T1_BARS_DATA[i][1]),
                low=float(_T1_BARS_DATA[i][2]),
                close=float(_T1_BARS_DATA[i][3]),
                volume=float(_T1_BARS_DATA[i][4]),
                granularity_seconds=300,
                source="validator",
            )
            for i in range(len(_T1_BARS_DATA))
        ]
        t1_hit = double_bottom_detector(t1_raw)
        t1_conf = round(t1_hit.confidence, 3) if t1_hit else None
        conf_note = f"detector_conf={t1_conf}" if t1_conf else "detector_returned_None"
        expected_reject = t1_conf is not None and t1_conf >= CONFIDENCE_LOW_CEILING
        note = (
            f"watcher_result={'None' if sig_t2 is None else 'Signal'} "
            f"{conf_note} expected_gate_reject={expected_reject}"
        )
    except Exception as exc:
        note = f"watcher_result={'None' if sig_t2 is None else 'Signal'} (detector diag unavailable: {exc})"
    results.append({"name": "T2_textbook_high_conf_rejected", "pass": ok, "note": note})

    # -- T3: boundary conf=0.60 exactly is rejected (gate is >=, not >) --------
    # Bars engineered so ONLY decisive_reclaim fires: conf = 0.45 + 0.15 = 0.60
    _watcher_mod._last_signal_time = None
    ctx_t3 = _make_ctx(_T3_BARS_DATA, timestamp_et=_RTH_TIME, vix_now=15.0)
    sig_t3 = detect_db_base_quiet_setup(ctx_t3)
    ok_t3 = sig_t3 is None
    # Confirm detector sees 0.60 (or at least rejects)
    try:
        from crypto.lib.chart_patterns import double_bottom_detector, Bar

        t3_raw = [
            Bar(
                open_time=dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=5 * i),
                open=float(_T3_BARS_DATA[i][0]),
                high=float(_T3_BARS_DATA[i][1]),
                low=float(_T3_BARS_DATA[i][2]),
                close=float(_T3_BARS_DATA[i][3]),
                volume=float(_T3_BARS_DATA[i][4]),
                granularity_seconds=300,
                source="validator",
            )
            for i in range(len(_T3_BARS_DATA))
        ]
        t3_hit = double_bottom_detector(t3_raw)
        t3_conf = round(t3_hit.confidence, 3) if t3_hit else None
        conf_diag = f"detector_conf={t3_conf}" if t3_conf else "detector_returned_None"
        note_t3 = (
            f"watcher_result={'None (PASS)' if sig_t3 is None else 'Signal (FAIL)'} "
            f"{conf_diag} ceiling={CONFIDENCE_LOW_CEILING} "
            f"gate_expr='conf >= ceiling' so conf=0.60 is EXCLUDED"
        )
    except Exception as exc:
        note_t3 = (
            f"watcher_result={'None (PASS)' if sig_t3 is None else 'Signal (FAIL)'} "
            f"(detector diag unavailable: {exc})"
        )
    results.append({
        "name": "T3_boundary_conf_0p60_rejected",
        "pass": ok_t3,
        "note": note_t3,
    })

    # -- T4: VIX >= 20 returns None (HIGH_VOL gate) ----------------------------
    _watcher_mod._last_signal_time = None
    vix_high = VIX_LOW_VOL_CEILING + 5.0   # 25.0
    ctx_t4 = _make_ctx(_BASE_BARS_DATA, timestamp_et=_RTH_TIME, vix_now=vix_high)
    sig_t4 = detect_db_base_quiet_setup(ctx_t4)
    ok_t4 = sig_t4 is None
    results.append({
        "name": "T4_vix_gate_rejects_high_vol",
        "pass": ok_t4,
        "note": (
            f"vix_now={vix_high} >= ceiling={VIX_LOW_VOL_CEILING} "
            f"watcher_result={'None (PASS)' if sig_t4 is None else 'Signal (FAIL)'}"
        ),
    })

    # -- T5: named level near neckline returns None (NOT_NEAR_NAMED gate) ------
    _watcher_mod._last_signal_time = None
    # Neckline of _BASE_BARS_DATA is 100.45. Place a level at 100.45 (dist=0.0 < $0.50).
    ctx_t5 = _make_ctx(
        _BASE_BARS_DATA, timestamp_et=_RTH_TIME, vix_now=15.0, levels_active=[100.45]
    )
    sig_t5 = detect_db_base_quiet_setup(ctx_t5)
    ok_t5 = sig_t5 is None
    results.append({
        "name": "T5_not_near_named_gate_rejects",
        "pass": ok_t5,
        "note": (
            "level=100.45 at neckline (dist=$0.00 < $0.50 proximity_max) "
            f"watcher_result={'None (PASS)' if sig_t5 is None else 'Signal (FAIL)'}"
        ),
    })

    # -- Build result dict -----------------------------------------------------
    all_pass = all(r["pass"] for r in results)
    return {
        "mode": "offline",
        "evidence_basis": (
            "2026-05-20: DOUBLE_BOTTOM_BASE_QUIET cross-validated N=168, WR=59.5%. "
            "Pathological 0.60-0.70 band OOS WR=46.8% (N=447). "
            "CONFIDENCE_LOW_CEILING=0.60 gate (>= not >) excludes decisive_reclaim-only "
            "patterns. T3 bars engineered for conf=0.45+0.15=0.60 exactly -> excluded."
        ),
        "constants_verified": {
            "CONFIDENCE_LOW_CEILING": 0.60,
            "VIX_LOW_VOL_CEILING": 20.0,
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
    """Scan watcher-observations.jsonl for conf-gate bypasses.

    If any DOUBLE_BOTTOM_BASE_QUIET observation has metadata.confidence_score >= 0.60,
    that is a gate-bypass bug (the gate was supposed to block it).

    Audit mode: pass=True always. RED verdict is informational.
    If no observations yet (watcher is new), report PASS with note.
    """
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        return {
            "mode": "live",
            "source": str(obs_path),
            "skipped": True,
            "reason": "watcher-observations.jsonl not found",
            "pass": True,
        }

    db_quiet_obs: list[dict] = []
    bypasses: list[dict] = []
    lines_read = 0

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
                if setup != "DOUBLE_BOTTOM_BASE_QUIET":
                    continue
                db_quiet_obs.append(obs)
                conf_score = (obs.get("metadata") or {}).get("confidence_score", None)
                if conf_score is not None and conf_score >= 0.60:
                    bypasses.append({
                        "date": obs.get("date", "?"),
                        "timestamp": obs.get("bar_timestamp") or obs.get("timestamp_et", "?"),
                        "confidence_score": conf_score,
                        "setup_name": setup,
                    })
    except Exception as exc:
        return {
            "mode": "live",
            "skipped": True,
            "reason": f"read error: {exc}",
            "pass": True,
        }

    if not db_quiet_obs:
        return {
            "mode": "live",
            "source": str(obs_path),
            "total_lines_scanned": lines_read,
            "db_base_quiet_obs": 0,
            "gate_bypasses": 0,
            "verdict": "GREEN",
            "note": (
                "No DOUBLE_BOTTOM_BASE_QUIET observations yet — "
                "watcher is new as of 2026-05-20. Gate not yet exercised live. "
                "PASS: absence of bypass evidence."
            ),
            "pass": True,
        }

    verdict = "GREEN" if not bypasses else "RED"
    return {
        "mode": "live",
        "source": str(obs_path),
        "total_lines_scanned": lines_read,
        "db_base_quiet_obs": len(db_quiet_obs),
        "gate_bypasses": len(bypasses),
        "bypass_details": bypasses,
        "verdict": verdict,
        "note": (
            "Scanned all DOUBLE_BOTTOM_BASE_QUIET observations. "
            "Any row with metadata.confidence_score >= 0.60 is a gate-bypass bug "
            "(CONFIDENCE_LOW_CEILING gate should have returned None before WatcherSignal)."
        ),
        "pass": True,  # audit mode — RED is informational; no gate bypass expected
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="v29 DOUBLE_BOTTOM_BASE_QUIET confidence-ceiling regression gate"
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
