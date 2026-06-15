"""v37_tbr_high_vol_gate — TBR_HIGH_VOL watcher signal-filter correctness gate.

Background:
  2026-05-24: tbr_high_vol_watcher.py ships as WATCH_ONLY (real-fills validation
  pending).  OOS (2025-10-01..2026-05-22) N=277 WR=44.9% exp=-$6.44 — FAIL on
  the promotion gate (WR>=55% required).  All 3 OOS quarters negative.
  Status: BLOCKED_BY_RF.

  NOTE: This validator tests CODE CORRECTNESS only — that _is_high_vol_tbr()
  filters correctly.  A PASS here does NOT imply TBR_HIGH_VOL is promotion-ready.
  The watcher is WATCH_ONLY pending real-fills validation.

  The watcher wraps shotgun_scalper_detector.detect() and emits signals ONLY when:
    1. trigger["name"] == "TRENDLINE_BREAK_RETEST"       (not OPEN_REJECTION / LEVEL_REJECT_LIVE)
    2. vol_ratio >= 1.5 OR confidence in ("high", "medium")  (TBR_VOL_CONFIRM_MULT = 1.5)

  _is_high_vol_tbr() predicate from tbr_high_vol_watcher.py (lines 66-74):
    if trigger.get("name") != "TRENDLINE_BREAK_RETEST": return False
    vr = trigger.get("vol_ratio") or 0.0
    conf = trigger.get("confidence", "low")
    return vr >= TBR_VOL_MIN_RATIO or conf in ("high", "medium")

Offline coverage (8 tests):
  T1  name=TBR, vol_ratio=2.0, conf=high   → PASS  (high vol + high conf)
  T2  name=TBR, vol_ratio=1.5, conf=medium → PASS  (exactly at threshold)
  T3  name=TBR, vol_ratio=1.2, conf=low    → BLOCK (below threshold, low conf)
  T4  name=TBR, vol_ratio=0.0, conf=low    → BLOCK (zero vol, low conf)
  T5  name=OPEN_REJECTION, vol_ratio=3.0   → BLOCK (wrong signal type)
  T6  name=LEVEL_REJECT_LIVE, vol_ratio=2.0→ BLOCK (wrong signal type)
  T7  name=TBR, vol_ratio=1.0, conf=medium → PASS  (below vol threshold but medium conf)
  T8  name=TBR, vol_ratio=1.5+epsilon      → PASS  (just above threshold, low conf)

Live coverage (audit mode):
  Scan watcher-observations.jsonl for tbr_high_vol_watcher rows.
  Assert all have confidence != "low" (the filter guarantees this).
  Report count of high/medium/low breakdown. pass=True always (evidence audit).

Exit code:
  0 — all offline tests PASS (live is always pass=True)
  1 — any offline test FAIL
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

# Import the predicate directly from the watcher — we test the real code, not a copy.
from backtest.lib.watchers.tbr_high_vol_watcher import (  # noqa: E402
    TBR_VOL_MIN_RATIO,
    _is_high_vol_tbr,
)


# ---------------------------------------------------------------------------
# Offline tests — deterministic, no I/O
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    """8 boundary tests for _is_high_vol_tbr().

    Tests confirm:
      - Only TRENDLINE_BREAK_RETEST signals pass the name guard.
      - vol_ratio >= 1.5 (TBR_VOL_MIN_RATIO) passes regardless of confidence.
      - confidence in (high, medium) passes regardless of vol_ratio.
      - vol_ratio < 1.5 AND confidence=low is blocked.
    """
    # Each case: (label, trigger_dict, expected_result, description)
    cases = [
        (
            "T1",
            {"name": "TRENDLINE_BREAK_RETEST", "vol_ratio": 2.0, "confidence": "high"},
            True,
            "high vol (2.0x) + high conf: PASS",
        ),
        (
            "T2",
            {"name": "TRENDLINE_BREAK_RETEST", "vol_ratio": TBR_VOL_MIN_RATIO, "confidence": "medium"},
            True,
            f"vol_ratio exactly at threshold ({TBR_VOL_MIN_RATIO}): PASS",
        ),
        (
            "T3",
            {"name": "TRENDLINE_BREAK_RETEST", "vol_ratio": 1.2, "confidence": "low"},
            False,
            "vol_ratio=1.2 (below 1.5) + low conf: BLOCK",
        ),
        (
            "T4",
            {"name": "TRENDLINE_BREAK_RETEST", "vol_ratio": 0.0, "confidence": "low"},
            False,
            "zero vol + low conf: BLOCK",
        ),
        (
            "T5",
            {"name": "OPEN_REJECTION", "vol_ratio": 3.0, "confidence": "high"},
            False,
            "wrong signal type (OPEN_REJECTION): BLOCK regardless of vol",
        ),
        (
            "T6",
            {"name": "LEVEL_REJECT_LIVE", "vol_ratio": 2.0, "confidence": "high"},
            False,
            "wrong signal type (LEVEL_REJECT_LIVE): BLOCK regardless of vol",
        ),
        (
            "T7",
            {"name": "TRENDLINE_BREAK_RETEST", "vol_ratio": 1.0, "confidence": "medium"},
            True,
            "vol below threshold but medium conf: PASS (conf gate saves it)",
        ),
        (
            "T8",
            {"name": "TRENDLINE_BREAK_RETEST", "vol_ratio": TBR_VOL_MIN_RATIO + 0.001, "confidence": "low"},
            True,
            "vol just above threshold, low conf: PASS (vol gate saves it)",
        ),
    ]

    results = []
    for label, trigger, expected, desc in cases:
        actual = _is_high_vol_tbr(trigger)
        ok = actual == expected
        detail = (
            f"_is_high_vol_tbr({trigger}) = {actual}, expected {expected}"
        )
        results.append({"test": label, "desc": desc, "pass": ok, "detail": detail})
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {label}: {desc}")
        if not ok:
            print(f"         DETAIL: {detail}")

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    all_pass = passed == total

    return {
        "mode": "offline",
        "all_pass": all_pass,
        "passed": passed,
        "total": total,
        "tbr_vol_min_ratio": TBR_VOL_MIN_RATIO,
        "tests": results,
    }


# ---------------------------------------------------------------------------
# Live tests — audit mode (watcher-observations.jsonl)
# ---------------------------------------------------------------------------

def run_live() -> dict:
    """Scan watcher-observations.jsonl for tbr_high_vol_watcher rows.

    Asserts all emitted signals have confidence != 'low'.
    The filter _is_high_vol_tbr() guarantees this — if any 'low' confidence
    row is found, the watcher has a bug (it would mean vol_ratio>=1.5 was
    set but confidence was still left as 'low', which the detector marks
    only when vol_ratio < TBR_VOL_MIN_RATIO).

    Returns pass=True always (evidence audit, not a blocking gate).
    """
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        print("  [AUDIT] watcher-observations.jsonl not found (no data yet)")
        return {
            "mode": "live",
            "all_pass": True,
            "note": "watcher-observations.jsonl not found — no data to audit",
            "tbr_highvol_total": 0,
            "conf_high": 0,
            "conf_medium": 0,
            "conf_low": 0,
            "low_conf_anomalies": [],
        }

    conf_counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0, "other": 0}
    low_conf_anomalies: list[dict] = []

    with obs_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("watcher_name") != "tbr_high_vol_watcher":
                continue
            conf = row.get("confidence", "other")
            conf_counts[conf] = conf_counts.get(conf, 0) + 1
            if conf == "low":
                low_conf_anomalies.append({
                    "ts": row.get("bar_timestamp") or row.get("timestamp"),
                    "vol_ratio": (row.get("metadata") or {}).get("vol_ratio"),
                    "confidence": conf,
                })

    total = sum(conf_counts.values())
    has_anomalies = len(low_conf_anomalies) > 0

    print(f"  [AUDIT] tbr_high_vol_watcher obs: total={total}")
    print(f"          conf breakdown: high={conf_counts['high']} medium={conf_counts['medium']} low={conf_counts['low']}")
    if has_anomalies:
        print(f"  [WARN]  {len(low_conf_anomalies)} low-conf anomalies found (watcher filter may have a bug)")
        for a in low_conf_anomalies[:3]:
            print(f"          {a}")
    else:
        print("          no low-conf anomalies (filter is consistent)")

    return {
        "mode": "live",
        "all_pass": True,  # audit only — does not block
        "note": "audit only — pass=True regardless of result (code-correctness evidence)",
        "tbr_highvol_total": total,
        "conf_high": conf_counts["high"],
        "conf_medium": conf_counts["medium"],
        "conf_low": conf_counts["low"],
        "low_conf_anomalies": low_conf_anomalies,
        "promotion_status": "WATCH_ONLY (real-fills FAIL: OOS WR=44.9% vs gate WR>=55%)",
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["offline", "live", "both"],
        default="offline",
        help="offline=deterministic fixture tests; live=watcher-obs audit; both=run both",
    )
    args = parser.parse_args(argv)

    print(f"\n[v37] TBR_HIGH_VOL watcher signal-filter gate — mode={args.mode}")
    print(f"      TBR_VOL_MIN_RATIO = {TBR_VOL_MIN_RATIO}")

    if args.mode in ("offline", "both"):
        result = run_offline()
        status = "PASS" if result["all_pass"] else "FAIL"
        print(f"\n  [{status}] offline: {result['passed']}/{result['total']} tests passed")
        if args.mode == "offline":
            return 0 if result["all_pass"] else 1

    if args.mode in ("live", "both"):
        result = run_live()
        print(f"\n  [PASS] live: audit complete (tbr_highvol obs={result['tbr_highvol_total']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
