"""conductor_budget.py -- nightly spend governor for the conductor family.

WHY (measured census, 07-18..07-23 session transcripts, 2026-07-25):
The conductor family (Conductor + ConductorRTH + ConductorWeekend) was **93.3% of all automation
token burn** -- $149.57/day of a $160.26/day total. Two structural fixes landed alongside this
file (wake-watcher debounce 30->180min + a RED pattern that no longer matches cosmetic DEGRADED;
scheduled cadence cut to 3 overnight fires). This governor is the BACKSTOP: even if a future fire
launches a big multi-agent battery, the night stops when the budget is spent.

THE 2.2x CORRECTION (the load-bearing detail):
`conductor-outcomes.jsonl`'s self-reported `cost_usd` averages $3.44/fire, but the measured
per-session token cost is $7.69/fire -- the conductor UNDER-REPORTS its own spend by ~2.2x. A cap
built naively on the self-report would silently allow ~2x the intended budget, which is exactly
the class of error this whole pass exists to kill. Every read of `cost_usd` here is multiplied by
SELF_REPORT_CORRECTION before comparison. If a future fire learns to report true cost, set that
constant to 1.0 and re-measure -- do not delete the mechanism.

Pure Python, $0, no LLM, no broker, no network. Fails OPEN (exit 0 = proceed) on any internal
error: a broken governor must never be the reason the rig stops working (C7).

CLI:
  python setup/scripts/conductor_budget.py --check    # exit 0 proceed / 3 exhausted
  python setup/scripts/conductor_budget.py --status   # human/JSON summary, always exit 0
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
OUTCOMES = REPO / "automation" / "state" / "conductor-outcomes.jsonl"
CONFIG = REPO / "automation" / "state" / "conductor-budget.json"

# Measured 2026-07-25: real $7.69/fire vs $3.44 self-reported.
SELF_REPORT_CORRECTION = 2.2

DEFAULTS = {"daily_cap_usd": 30.0, "max_fires": 4, "enabled": True}

EXIT_PROCEED = 0
EXIT_EXHAUSTED = 3


def _et_today() -> str:
    try:
        sys.path.insert(0, str(REPO / "setup" / "scripts"))
        from et_clock import et_today_str  # noqa: PLC0415 -- optional dep, fail-open below
        return et_today_str()
    except Exception:  # noqa: BLE001
        return (dt.datetime.utcnow() - dt.timedelta(hours=4)).date().isoformat()


def load_config(path: Optional[Path] = None) -> dict:
    cfg = dict(DEFAULTS)
    try:
        raw = json.loads((path or CONFIG).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for k in DEFAULTS:
                if k in raw:
                    cfg[k] = raw[k]
    except (OSError, ValueError):
        pass  # defaults -- never block on a missing/garbled config
    return cfg


def spend_today(day: Optional[str] = None, path: Optional[Path] = None) -> dict:
    """Corrected spend + fire count for `day` (ET). Never raises."""
    day = day or _et_today()
    p = path or OUTCOMES
    raw_usd, fires = 0.0, 0
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if day not in line:
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(row, dict):
                    continue
                # fired_at is UTC ISO; the ET-day substring test above already filtered, but a UTC
                # evening maps to the same ET date only part of the time -- accept either stamp.
                stamp = str(row.get("fired_at") or row.get("ts_et") or "")
                if day not in stamp:
                    continue
                fires += 1
                try:
                    raw_usd += float(row.get("cost_usd") or 0.0)
                except (TypeError, ValueError):
                    pass
    except OSError:
        return {"day": day, "fires": 0, "raw_usd": 0.0, "corrected_usd": 0.0,
                "readable": False}
    return {"day": day, "fires": fires, "raw_usd": round(raw_usd, 2),
            "corrected_usd": round(raw_usd * SELF_REPORT_CORRECTION, 2), "readable": True}


def check(day: Optional[str] = None, cfg: Optional[dict] = None,
          path: Optional[Path] = None, cfg_path: Optional[Path] = None) -> dict:
    """Decide whether the conductor may do LLM work right now. Never raises."""
    cfg = cfg or load_config(cfg_path)
    s = spend_today(day, path)
    if not cfg.get("enabled", True):
        return {**s, "verdict": "PROCEED", "reason": "governor disabled in config", **_caps(cfg)}
    if s["corrected_usd"] >= float(cfg["daily_cap_usd"]):
        return {**s, "verdict": "EXHAUSTED",
                "reason": (f"corrected spend ${s['corrected_usd']:.2f} "
                           f">= cap ${float(cfg['daily_cap_usd']):.2f} "
                           f"(raw self-report ${s['raw_usd']:.2f} x{SELF_REPORT_CORRECTION})"),
                **_caps(cfg)}
    if s["fires"] >= int(cfg["max_fires"]):
        return {**s, "verdict": "EXHAUSTED",
                "reason": f"{s['fires']} fires today >= max_fires {cfg['max_fires']}",
                **_caps(cfg)}
    return {**s, "verdict": "PROCEED",
            "reason": (f"${s['corrected_usd']:.2f} of ${float(cfg['daily_cap_usd']):.2f} used, "
                       f"{s['fires']}/{cfg['max_fires']} fires"),
            **_caps(cfg)}


def _caps(cfg: dict) -> dict:
    return {"daily_cap_usd": float(cfg["daily_cap_usd"]), "max_fires": int(cfg["max_fires"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="exit 3 when the budget is spent")
    ap.add_argument("--status", action="store_true", help="print status, always exit 0")
    ap.add_argument("--date", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        res = check(a.date)
    except Exception as e:  # noqa: BLE001 -- fail OPEN, loudly
        print(f"conductor_budget: internal error, failing OPEN: {e}")
        return EXIT_PROCEED

    print(json.dumps(res, indent=2) if a.json
          else f"{res['day']}  {res['verdict']}  {res['reason']}")
    if a.check and res["verdict"] == "EXHAUSTED":
        return EXIT_EXHAUSTED
    return EXIT_PROCEED


if __name__ == "__main__":
    raise SystemExit(main())
