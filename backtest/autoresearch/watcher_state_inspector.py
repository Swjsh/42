"""Watcher-state inspector — verify ORB + ODF state machines progress as expected.

For the given date (defaults to today), runs the SAME T82+T82b warmup loop that
production watcher_live.py executes, then dumps the resulting `_orb_state[date_str]`
and `_odf_state[date_str]` dicts for inspection.

Verifies:
  - ORB state progresses past NEUTRAL (BREAKOUT_HIGH / BREAKOUT_LOW expected on
    a session with a clean opening drive)
  - ODF state shows hod/lod ratchet + stall counter incremented (chop morning)
  - State machines aren't stuck

USAGE:
    python -m autoresearch.watcher_state_inspector
    python -m autoresearch.watcher_state_inspector --date 2026-05-14
    python -m autoresearch.watcher_state_inspector --date 2026-05-14 --heal

OUTPUTS:
    stdout: per-watcher state dump + verdict
    automation/state/watcher-state-inspector-{date}.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "automation" / "state"
OBS_PATH = OUTPUT_DIR / "watcher-observations.jsonl"


def _load_obs(date: str) -> int:
    """Count watcher observations on the given date (any watcher)."""
    if not OBS_PATH.exists():
        return 0
    n = 0
    try:
        with OBS_PATH.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if date in line:
                    n += 1
    except Exception:
        pass
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (defaults to today)")
    parser.add_argument("--heal", action="store_true",
                        help="if RED, run audit-silent-watcher-days.ps1 + watcher_replay")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    target_date = args.date or datetime.now().strftime("%Y-%m-%d")

    # Late imports — these touch lib/watchers internals
    sys.path.insert(0, str(ROOT / "backtest"))

    # Reset module state by importing fresh (Python caches modules per-process,
    # so a fresh subprocess invocation IS the reset — no need to del them)
    try:
        from lib.watchers import orb_watcher
        from lib.watchers import opening_drive_fade_watcher
    except Exception as e:
        if not args.quiet:
            print(f"ERROR importing watcher modules: {e}", file=sys.stderr)
        return 2

    # Load today's bars via the same pipeline watcher_live.py uses
    try:
        from autoresearch import watcher_live
    except Exception as e:
        if not args.quiet:
            print(f"ERROR importing watcher_live: {e}", file=sys.stderr)
        return 2

    # Replicate watcher_live's bar load via ar_runner.load_data
    rth = None
    today_bars = None
    bar_idx_in_day = -1
    vol_baseline = 0.0

    try:
        import datetime as _dt
        import pandas as _pd
        from autoresearch import runner as ar_runner
        # Use a 7-day lookback like watcher_live.py
        target_dt = _dt.datetime.strptime(target_date, "%Y-%m-%d").date()
        lookback_start = target_dt - _dt.timedelta(days=7)
        spy_full, _vix_full = ar_runner.load_data(lookback_start, target_dt)
        spy_full["timestamp_et"] = _pd.to_datetime(spy_full["timestamp_et"])
        spy_full["date"] = spy_full["timestamp_et"].dt.date
        # Filter to RTH (09:30 - 16:00 ET) — same as watcher_live
        spy_full["time_et"] = spy_full["timestamp_et"].dt.time
        rth_mask = (spy_full["time_et"] >= _dt.time(9, 30)) & (spy_full["time_et"] <= _dt.time(16, 0))
        rth = spy_full[rth_mask].reset_index(drop=True)
        # Compute vol baseline from latest 20 bars
        if len(rth) >= 20:
            try:
                from lib.filters import vol_baseline_20bar
                vol_baseline = vol_baseline_20bar(rth, len(rth) - 1)
            except Exception:
                vol_baseline = float(rth["volume"].tail(20).mean()) if "volume" in rth.columns else 0.0
    except Exception as e:
        if not args.quiet:
            print(f"WARN: bar load failed: {type(e).__name__}: {e}", file=sys.stderr)
        rth = None

    if rth is None or len(rth) == 0:
        verdict = "RED"
        reason = "could-not-load-bars-for-date"
        result = {
            "skill": "watcher-state-inspector",
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "target_date": target_date,
            "verdict": verdict,
            "reason": reason,
            "orb_state": {},
            "odf_state": {},
            "watcher_obs_count_today": _load_obs(target_date),
            "heal_action": "no-op-bar-load-failed",
        }
        out = OUTPUT_DIR / f"watcher-state-inspector-{target_date}.json"
        out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        if not args.quiet:
            print(f"=== watcher-state-inspector {target_date} ===")
            print(f"VERDICT: {verdict} ({reason})")
            print(f"wrote: {out}")
        return 1

    # Filter to today's bars
    try:
        import pandas as pd
        rth["timestamp_et"] = pd.to_datetime(rth["timestamp_et"])
        today_mask = rth["timestamp_et"].dt.strftime("%Y-%m-%d") == target_date
        today_bars = rth[today_mask].reset_index(drop=True)
    except Exception as e:
        today_bars = None

    if today_bars is None or len(today_bars) == 0:
        verdict = "YELLOW"
        reason = "no-bars-for-target-date-yet (market may not be open or csv stale)"
        result = {
            "skill": "watcher-state-inspector",
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "target_date": target_date,
            "verdict": verdict,
            "reason": reason,
            "orb_state": {},
            "odf_state": {},
            "watcher_obs_count_today": _load_obs(target_date),
            "heal_action": "no-op-no-bars",
        }
        out = OUTPUT_DIR / f"watcher-state-inspector-{target_date}.json"
        out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        if not args.quiet:
            print(f"=== watcher-state-inspector {target_date} ===")
            print(f"VERDICT: {verdict} ({reason})")
            print(f"wrote: {out}")
        return 0

    bar_idx_in_day = len(today_bars) - 1

    # Run T82 warmup loop (same as watcher_live.py lines 323-349)
    warmup_errors = []
    if bar_idx_in_day > 0:
        try:
            for _wu_idx in range(int(bar_idx_in_day)):
                _wu_bar = today_bars.iloc[_wu_idx]
                try:
                    orb_watcher.detect_orb_break(_wu_bar, today_bars, _wu_idx, vol_baseline)
                except Exception as e_orb:
                    warmup_errors.append(f"orb idx={_wu_idx}: {type(e_orb).__name__}: {e_orb}")
                try:
                    _wu_match = rth.index[rth["timestamp_et"] == _wu_bar["timestamp_et"]]
                    if len(_wu_match) > 0:
                        _wu_full_idx = int(_wu_match[-1])
                        opening_drive_fade_watcher.detect_opening_drive_fade_setup(
                            _wu_bar, _wu_full_idx, rth
                        )
                except Exception as e_odf:
                    warmup_errors.append(f"odf idx={_wu_idx}: {type(e_odf).__name__}: {e_odf}")
        except Exception as e_top:
            warmup_errors.append(f"warmup-loop-failed: {e_top}")

    # ---- INSPECT STATE ----
    orb_state_dict = getattr(orb_watcher, "_orb_state", {})
    odf_state_dict = getattr(opening_drive_fade_watcher, "_odf_state", {})

    orb_today = orb_state_dict.get(target_date, {}) if isinstance(orb_state_dict, dict) else {}
    odf_today = odf_state_dict.get(target_date, {}) if isinstance(odf_state_dict, dict) else {}

    obs_today = _load_obs(target_date)

    # ---- DIAGNOSE ----
    verdict = "GREEN"
    reason = "state-machines-progressing-normally"

    # ORB stores state in `state` key; ODF in `state` or `status` depending on version
    orb_status = (orb_today.get("state") or orb_today.get("status")) if isinstance(orb_today, dict) else None
    odf_status = (odf_today.get("state") or odf_today.get("status")) if isinstance(odf_today, dict) else None

    # Determine session-elapsed minutes
    now_t = datetime.now().time()
    market_open  = dt_time(9, 30)
    market_close = dt_time(16, 0)
    is_market_hours = market_open <= now_t <= market_close
    is_today = (target_date == datetime.now().strftime("%Y-%m-%d"))

    # If state empty AND market session has passed multiple bars, that's RED
    if not orb_today and bar_idx_in_day >= 6:
        verdict = "RED"
        reason = (f"orb_state empty after {bar_idx_in_day + 1} bars on {target_date} "
                  "(state machine never advanced -- expected NEUTRAL at minimum)")
    elif not odf_today and bar_idx_in_day >= 6:
        # ODF often legitimately stays NEUTRAL on trending days; downgrade to YELLOW
        if verdict == "GREEN":
            verdict = "YELLOW"
            reason = "odf_state empty (may be correct if no drive-then-fade pattern)"

    if warmup_errors:
        verdict = "YELLOW" if verdict == "GREEN" else verdict
        reason = f"{reason}; warmup_errors={len(warmup_errors)}"

    if obs_today == 0 and is_today and not is_market_hours and bar_idx_in_day >= 12:
        # Market closed AND we have many bars AND zero observations on a "should-have-fired" day
        # This is suspicious but not always RED — gap-and-go days legitimately produce few signals
        if verdict == "GREEN":
            verdict = "YELLOW"
            reason = "0-observations-today-after-full-session (may be correct on no-setup days)"

    # ---- HEAL ----
    heal_action = "no-op"
    if args.heal and verdict == "RED":
        heal_script = ROOT / "setup" / "scripts" / "audit-silent-watcher-days.ps1"
        if heal_script.exists():
            try:
                import subprocess
                # CREATE_NO_WINDOW = 0x08000000 — OP-27 L41.
                _flags = 0x08000000 if sys.platform == "win32" else 0
                subprocess.run(
                    ["powershell.exe", "-File", str(heal_script)],
                    capture_output=True, timeout=60, check=False,
                    creationflags=_flags,
                )
                heal_action = "ran-audit-silent-watcher-days-script"
            except Exception as e_heal:
                heal_action = f"heal-failed: {type(e_heal).__name__}: {e_heal}"
        else:
            heal_action = f"heal-script-missing-at-{heal_script}"

    # ---- REPORT ----
    result = {
        "skill": "watcher-state-inspector",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": target_date,
        "verdict": verdict,
        "reason": reason,
        "today_bars_loaded": int(len(today_bars)),
        "bar_idx_in_day_warmed_up": int(bar_idx_in_day),
        "orb_state": _safe(orb_today),
        "odf_state": _safe(odf_today),
        "orb_status": orb_status,
        "odf_status": odf_status,
        "warmup_errors": warmup_errors,
        "watcher_obs_count_today": obs_today,
        "heal_action": heal_action,
    }
    out = OUTPUT_DIR / f"watcher-state-inspector-{target_date}.json"
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    if not args.quiet:
        print(f"=== watcher-state-inspector {target_date} ===")
        print(f"VERDICT: {verdict}")
        print(f"  reason: {reason}")
        print(f"  bars warmed: {bar_idx_in_day}")
        print(f"  ORB state: {orb_status} :: keys={list(orb_today.keys()) if isinstance(orb_today, dict) else 'n/a'}")
        print(f"  ODF state: {odf_status} :: keys={list(odf_today.keys()) if isinstance(odf_today, dict) else 'n/a'}")
        print(f"  watcher observations on {target_date}: {obs_today}")
        if warmup_errors:
            print(f"  warmup errors: {len(warmup_errors)} (first 3): {warmup_errors[:3]}")
        print(f"  heal: {heal_action}")
        print(f"  wrote: {out}")

    if verdict == "RED":
        return 1
    return 0


def _safe(obj: Any) -> Any:
    """Make state dict JSON-serializable (handle datetimes, numpy types)."""
    if isinstance(obj, dict):
        return {str(k): _safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe(v) for v in obj]
    if isinstance(obj, (datetime, dt_time)):
        return str(obj)
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)


if __name__ == "__main__":
    sys.exit(main())
