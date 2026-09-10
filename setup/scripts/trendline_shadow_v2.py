"""trendline_shadow_v2.py -- SHADOW ledger for trendline_fit_v2 (WS-C). Zero entry
effect, zero interaction with v1's shadow ledger or `filters.py`.

STATUS (2026-09-09): built and manually verified to run end-to-end (see the
CLI usage below). NOT yet registered in Windows Task Scheduler and NOT yet
called from `run-trendline-shadow.ps1` -- see "SCHEDULED WIRING (TODO)" below
for the exact one-line change, left undone deliberately: the acceptance test
this same work order requires (`analysis/trendline-v2/validate_j_lines.py`)
came back 0/24 (0%) against the >=80% reproduction bar, well short of "obviously
safe to wire in cleanly." Building the module + this shadow script + the
validation harness is NOW; flipping the scheduled task is an Opus call per the
work order's own WS-F(2) ("read WS-C's ledger ... and decide whether v2
replaces v1 ... prereg it now").

WHAT THIS DOES
  For "today" (ET), loads 04:00-16:00 ET 5m bars (SIP cache first, CSV fallback
  -- same loader `trendline_fit_v2.load_bars_multi_source` the validation
  harness uses), runs `detect_trendlines_v2` (CONFIRMED-only, both anchor
  families, both kinds), and appends one row per detected line to
  analysis/trendlines/shadow-ledger-v2.jsonl. Never touches
  analysis/trendlines/shadow-ledger.jsonl (v1's file, owned by
  setup/scripts/trendline_shadow.py) or any v1 state.

FAIL-OPEN (C7): any exception is caught, logged to stderr, and this exits 0 --
a bug here must never be able to affect the v1 fire it would run beside.

SCHEDULED WIRING (TODO -- NOT done in this pass):
  Add ONE line to setup/scripts/run-trendline-shadow.ps1, immediately after the
  existing `$out = & $exe (Join-Path $repoRoot "setup\\scripts\\trendline_shadow.py") ...`
  call, before its `$rc = $LASTEXITCODE` line:
      & $exe (Join-Path $repoRoot "setup\\scripts\\trendline_shadow_v2.py") --date $etDate 2>&1 | Out-Null
  This call is deliberately NOT chained into $rc / the STATUS.md escalation
  path above it -- v2 is shadow-only and must never be able to turn a v1
  success into a reported failure (or vice versa). A separate, v2-owned
  Known-broken line would be a follow-up, not this one.

USAGE
  backtest/.venv/Scripts/python.exe setup/scripts/trendline_shadow_v2.py --date 2026-09-08
  backtest/.venv/Scripts/python.exe setup/scripts/trendline_shadow_v2.py   # defaults to today (ET)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "lib"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

OUT = REPO / "analysis" / "trendlines" / "shadow-ledger-v2.jsonl"


def _dates_for(date_et: str, lookback_days: int = 5) -> list[str]:
    y, m, d = (int(x) for x in date_et.split("-"))
    end = datetime(y, m, d)
    start = end - timedelta(days=lookback_days)
    out, cur = [], start
    while cur <= end:
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out


def run(date_et: str) -> int:
    import trendline_fit_v2 as v2  # imported inside run() so argparse/CLI errors never mask this

    bars = v2.load_bars_multi_source(_dates_for(date_et))
    if not bars:
        print(f"[trendline-shadow-v2] no bars for {date_et} -- nothing to log (exit 0, not a failure)")
        return 0

    lines = v2.detect_trendlines_v2(bars)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fire_ts_et = v2._et_str(bars[-1].ts_unix)
    with OUT.open("a", encoding="utf-8") as f:
        for ln in lines:
            row = {"date_et": date_et, "fire_ts_et": fire_ts_et, "detector_version": v2.DETECTOR_VERSION,
                   **ln.to_dict()}
            f.write(json.dumps(row) + "\n")
    print(f"[trendline-shadow-v2] {date_et}: {len(lines)} CONFIRMED line(s) logged -> "
          f"{OUT.relative_to(REPO)}")
    return 0


def _cli() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="ET date YYYY-MM-DD (default: today ET via et_clock)")
    args = ap.parse_args()
    try:
        if args.date:
            date_et = args.date
        else:
            from et_clock import et_today_str
            date_et = et_today_str()
        return run(date_et)
    except Exception as exc:  # noqa: BLE001 -- deliberate fail-open (C7): never break the v1 fire
        print(f"[trendline-shadow-v2] FAILED (non-fatal, logged not raised): {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
