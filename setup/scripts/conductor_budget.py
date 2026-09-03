"""conductor_budget.py -- nightly spend governor for the conductor family.

WHY (measured census, 07-18..07-23 session transcripts, 2026-07-25):
The conductor family (Conductor + ConductorRTH + ConductorWeekend) was **93.3% of all automation
token burn** -- $149.57/day of a $160.26/day total. Two structural fixes landed alongside this
file (wake-watcher debounce 30->180min + a RED pattern that no longer matches cosmetic DEGRADED;
scheduled cadence cut to 3 overnight fires). This governor is the BACKSTOP: even if a future fire
launches a big multi-agent battery, the night stops when the budget is spent.

THE 2.2x CORRECTION (the load-bearing detail, ORIGINAL 2026-07-25 framing -- see the
RE-MEASUREMENT note right below for what changed 2026-08-08):
`conductor-outcomes.jsonl`'s self-reported `cost_usd` averages $3.44/fire, but the measured
per-session token cost is $7.69/fire -- the conductor UNDER-REPORTS its own spend by ~2.2x. A cap
built naively on the self-report would silently allow ~2x the intended budget, which is exactly
the class of error this whole pass exists to kill. Every read of `cost_usd` here is multiplied by
SELF_REPORT_CORRECTION before comparison. If a future fire learns to report true cost, set that
constant to 1.0 and re-measure -- do not delete the mechanism.

RE-MEASUREMENT (2026-08-08, CONDUCTOR-BUDGET-ARITHMETIC queue item): the 07-25 numbers above
were never independently re-checked (they lived in prose only -- no surviving census script/
artifact) and autonomy-metric.json's total_cost_usd turned out to be the SAME self-reported
figure the constant is meant to correct, not an independent check -- exactly circular. A fresh
independent measurement (backtest/tools/measure_conductor_cost.py, matching real Claude Code
session transcripts to conductor fires and pricing actual tokens against Anthropic's published
rates) found a dollar-weighted aggregate ratio of 2.155 (n=16 real-work fires, ALL individually
>1.0x) -- close enough to 2.2 that a REPLAY of all 32 real ET-days in conductor-outcomes.jsonl
shows 2.20 vs 2.16 admits the IDENTICAL number of fire slots on every single day (112 either
way). The constant was updated to the more precisely-measured 2.16 anyway (see the constant's
own comment for the full citation), but this is an ACCURACY fix, not a fix for conductor
slot-starvation -- that turned out to be driven by max_fires=4 (a hard per-fire-count ceiling
that binds on 23/32 days regardless of dollar arithmetic) and by genuine real spend on cap-bound
days, not by the correction factor being miscalibrated. Full writeup:
analysis/recommendations/conductor-cost-correction-measurement-2026-08-08.md

Pure Python, $0, no LLM, no broker, no network. Fails OPEN (exit 0 = proceed) on any internal
error: a broken governor must never be the reason the rig stops working (C7).

PACING (added 2026-08-08, LANE-A-UNSTARVE-CONDUCTOR):
Real incident, quoted: on 2026-08-08, 3 fires landed inside the first ~2h of the ET day
(00:08/01:32/02:07 ET -- a `Gamma_ConductorWake`-triggered escalation cluster, debounced only
30 min apart, each doing real work) costing raw $3.90 + $9.35 + $2.80 = $16.05 (corrected
$35.31) -- OVER the $30 cap after just 3 fires. Every conductor-family fire for the rest of
that ET day (10+ rows through 20:00 UTC, including the important 20:30 ET evening slot) found
EXHAUSTED and did zero model work. The OLD gate was pure first-come-first-served against one
flat cumulative cap: whichever fires happen to land first get the whole day's budget, with
NO reservation for fires later in the day. `_pacing()` below adds a reservation: before
admitting fire (k+1) of the day, it reserves `min_allowance_usd` for each of the
`expected_fires_per_day - k` remaining nominal slots (including this one) and only proceeds if
what's left over clears that reservation. This intentionally does NOT (cannot) cap how much an
ADMITTED fire spends -- that decision is conductor.md's, outside this module's reach -- it only
gates ADMISSION of the *next* fire. One reservation formula produces both a floor (blocks once
the leftover-per-remaining-slot dips below `min_allowance_usd`) and a "carry-over" for
whichever fire happens first in the day (when nothing has been reserved against it yet, it
gets nearly the whole cap minus a token reserve for the others) -- no separate carry-over
constant needed, see `_pacing()`. THE HARD DAILY CAP IS UNCHANGED -- pacing only decides
*when within the day* admission stops, never *how much total* is allowed (OP-3: raising the
cap was not authorized for this fix).

KNOWN LIMIT (state plainly, don't oversell): pacing cannot protect the 20:30 ET slot on a day
where 2 early fires alone already cost ~97% of the whole day's corrected budget ($29.15 of $30
in the incident above) -- no admission-control scheme can create money that doesn't exist. The
deeper fix for THAT would be a per-fire $ cap enforced *inside* `conductor.md` itself (its
siblings `Gamma_ConductorRTH`/`Gamma_ConductorWeekend` already carry one -- $0.50 / $10 per
SCHEDULED-TASKS.md -- `Gamma_Conductor` itself does not) -- out of this fix's allowed surface
(conductor.md), flagged as a follow-up, not built here.

CORRECTION (2026-08-08, audit re-derivation -- min_allowance_usd default reverted to 0.0):
The "KNOWN LIMIT" above undersold the actual defect. `_pacing()` can only gate ADMISSION of a
fire before it spends -- it can never cap what an ALREADY-ADMITTED fire spends -- so a rescue
(pacing admitting a fire the old flat-cap-only gate would have blocked) can only ever happen if
denying an earlier fire leaves enough spare budget for the later fire pacing intends to protect.
A full chronological replay of all 32 real ET-days in `conductor-outcomes.jsonl` (279 rows) swept
across `min_allowance_usd` in {0, 1, 2, 3, 3.25, 5, 6.89, 7.15, 7.69, 8, 10, 15} -- 6.89/7.15 are
the measured corrected mean/median real-fire cost -- found **zero rescues at every single floor
value tested**, while `extra_blocks` (pacing blocking admission the old gate would have allowed)
strictly increases with the floor (2 extra_blocks at floor=2.0, the shipped default, rising to
101 at floor=15.0). In other words: given the real cost distribution, pacing at ANY calibration
only ever blocks fires the old gate would have admitted -- it never protects a later slot, because
the fire it lets through first can already outspend the whole reservation before its own next
check runs. Recalibrating the floor cannot fix this -- it is a structural limit of admission-only
gating, not a tuning problem. `min_allowance_usd` therefore now DEFAULTS to 0.0 (pacing disabled,
per this module's own documented escape hatch), restoring pure flat-cap + max_fires behavior
until a genuine per-fire $ cap lands inside `conductor.md` (the only mechanism that can actually
work, since it caps spend DURING a fire rather than gating admission before one). The `_pacing()`
mechanism and its config keys are kept intact and unit-tested -- set `min_allowance_usd` > 0 in
`automation/state/conductor-budget.json` to opt back in once that per-fire cap exists, or to
re-run the replay against fresh evidence.

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
from zoneinfo import ZoneInfo
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
OUTCOMES = REPO / "automation" / "state" / "conductor-outcomes.jsonl"
CONFIG = REPO / "automation" / "state" / "conductor-budget.json"
# Spend-shape visibility record (step 3, LANE-A-UNSTARVE-CONDUCTOR) -- written best-effort by
# main() on every --check/--status invocation so slots_used/slots_remaining/allowance_next are
# visible without re-deriving them. Never read by check() itself (side-effect-free, so tests
# calling check() directly stay hermetic); a module-level constant (not a main() local) so
# tests can monkeypatch it to a tmp path the same way OUTCOMES/CONFIG already are.
STATUS_OUT = REPO / "automation" / "state" / "conductor-budget-status.json"

# RE-MEASURED 2026-08-08 (CONDUCTOR-BUDGET-ARITHMETIC, queue item): the prior value (2.2,
# 2026-07-25) traced to prose only -- no census script/artifact survived in the repo, and
# automation/state/autonomy-metric.json's total_cost_usd was confirmed to be the SAME
# self-reported figure this constant corrects, not an independent check (exactly the OP-33
# staleness flag this comment used to carry). backtest/tools/measure_conductor_cost.py closes
# that gap: it matches each conductor-family conductor-outcomes.jsonl row to its own Claude
# Code session transcript (~/.claude/projects/.../*.jsonl) by a literal conductor.md marker
# string + nearest-timestamp, then computes REAL token-based cost via Anthropic's published
# per-token pricing (independent of the LLM's own self-report) -- same methodology as
# spend_summary.py / token_forensics.py, applied per-fire. Result, n=16 real-work fires
# (self-report >= $0.25) matched 2026-07-26..2026-08-08: dollar-weighted aggregate ratio
# (sum(real)/sum(self)) = 2.155 -> 2.16, ALL 16 individual ratios > 1.0 (self-report
# under-counts every single time), median 1.81 / mean 4.35 (right-skewed by a handful of
# investigation-heavy fires up to 14.2x). Full distribution + matched-fire list + a SEPARATE
# structural finding (near-zero-self-report no-op fires still cost ~$1.25 real each, which NO
# multiplicative constant can fix) + a subscription-vs-real-money verdict + a slot-admission
# replay (2.20 vs 2.16 changes ZERO of 32 real historical ET-days -- this is an accuracy fix,
# not a starvation fix):
# analysis/recommendations/conductor-cost-correction-measurement-2026-08-08.json
# Pinned by backtest/tests/test_conductor_budget.py::
# test_self_report_correction_matches_2026_08_08_remeasurement.
SELF_REPORT_CORRECTION = 2.16

DEFAULTS = {
    "daily_cap_usd": 30.0,
    "max_fires": 4,
    "enabled": True,
    # PACING (2026-08-08): the nominal number of fires the day's cap is meant to be spread
    # across. Mirrors max_fires by default -- independently tunable (this is the PACING
    # denominator, max_fires stays the absolute hard ceiling; see module docstring).
    "expected_fires_per_day": 4,
    # PACING floor: minimum $ (corrected) reserved per remaining nominal slot. DEFAULTS TO 0.0
    # (PACING DISABLED) as of 2026-08-08 -- see module docstring "CORRECTION": a full replay of
    # all 32 real ET-days showed 0 rescues at every floor value tested (0..15) while extra_blocks
    # only grows with the floor, because admission-only gating structurally cannot protect a
    # later slot once an earlier admitted fire overspends it. Set > 0 only once a genuine
    # per-fire $ cap exists inside conductor.md to actually bound an admitted fire's spend, or to
    # re-run the replay (setup/scripts/conductor_budget.py sweep logic is documented, not
    # shipped as a CLI -- see the audit script referenced in the CORRECTION note) against fresh
    # evidence and confirm a nonzero floor helps before re-enabling.
    "min_allowance_usd": 0.0,
}

EXIT_PROCEED = 0
EXIT_EXHAUSTED = 3


def _et_today() -> str:
    try:
        sys.path.insert(0, str(REPO / "setup" / "scripts"))
        from et_clock import et_today_str  # noqa: PLC0415 -- optional dep, fail-open below
        return et_today_str()
    except Exception:  # noqa: BLE001
        return dt.datetime.now(ZoneInfo("America/New_York")).date().isoformat()


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


def _stamp_to_et_date(stamp: str) -> Optional[str]:
    """Convert a row's timestamp to its true ET calendar date 'YYYY-MM-DD'.

    BUG THIS FIXES (found 2026-07-29, self-audit flagged "far more than max_fires" 3 nights
    running -- 07-27/07-28/07-29): `fired_at` is UTC ISO. ET is UTC-4 (EDT) / UTC-5 (EST), so
    any fire between ~20:00-23:59 ET has a `fired_at` whose UTC CALENDAR DATE is already
    tomorrow (e.g. the scheduled 20:30 ET fire on day D writes `fired_at` with a UTC date of
    D+1). The old code matched rows to a day via plain substring search on the raw `fired_at`
    string -- so that evening fire's own EXHAUSTED-check (which correctly asked "how many
    fires happened on ET day D so far") would ALSO be picked up by the NEXT calendar day's
    first budget check (which asks about ET day D+1) as if it were one of D+1's fires. Every
    day silently started already "1 fire spent" before its own first legitimate tick -- exactly
    the drift the self-audit kept re-flagging. Returns None (fail-open: caller falls back to
    the old substring behavior) on any parse failure -- a malformed timestamp must never crash
    the governor (C7)."""
    if not stamp:
        return None
    s = stamp.strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        parsed = dt.datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
    try:
        if parsed.tzinfo is not None:
            utc = parsed.astimezone(dt.timezone.utc)
            sys.path.insert(0, str(REPO / "setup" / "scripts"))
            from et_clock import et_now  # noqa: PLC0415 -- optional dep, fail-open below
            return et_now(now_utc=utc).strftime("%Y-%m-%d")
        # Naive stamp (the ts_et convention) is already ET-local -- no conversion needed.
        return parsed.strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001 -- fail-open: caller falls back to substring matching
        return None


def spend_today(day: Optional[str] = None, path: Optional[Path] = None) -> dict:
    """Corrected spend + fire count for `day` (ET). Never raises."""
    day = day or _et_today()
    p = path or OUTCOMES
    raw_usd, fires = 0.0, 0
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(row, dict):
                    continue
                stamp = str(row.get("fired_at") or row.get("ts_et") or "")
                et_date = _stamp_to_et_date(stamp)
                if et_date is not None:
                    if et_date != day:
                        continue
                elif day not in stamp:
                    # Fail-open fallback for an unparseable stamp: old substring behavior.
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


def _pacing(s: dict, cfg: dict) -> dict:
    """Per-fire pacing reservation. See module docstring 'PACING' section for the WHY.

    Reserves `min_allowance_usd` for each of the `expected_fires_per_day - fires_so_far`
    nominal slots still ahead today (floored at 1 -- always at least this fire's own slot),
    and checks whether what's left over after that reservation still clears the floor. Never
    raises; every input is defensively `.get()`'d with a DEFAULTS fallback so callers (incl.
    the existing test suite's partial `_cfg()` dicts) that predate these two config keys keep
    working unchanged.
    """
    expected = max(int(cfg.get("expected_fires_per_day", DEFAULTS["expected_fires_per_day"])), 1)
    floor = max(float(cfg.get("min_allowance_usd", DEFAULTS["min_allowance_usd"])), 0.0)
    cap = float(cfg.get("daily_cap_usd", DEFAULTS["daily_cap_usd"]))
    fires_so_far = int(s.get("fires", 0))
    remaining_slots = max(expected - fires_so_far, 1)
    remaining_budget = max(cap - float(s.get("corrected_usd", 0.0)), 0.0)
    reserve = max(remaining_slots - 1, 0) * floor
    allowance = round(max(remaining_budget - reserve, 0.0), 2)
    blocked = allowance < floor
    reason = None
    if blocked:
        reason = (f"pacing reserve exhausted: this fire's allowance ${allowance:.2f} < floor "
                  f"${floor:.2f} ({remaining_slots} nominal slot(s) left today incl. this one, "
                  f"${round(reserve, 2):.2f} reserved for the rest, expected {expected} "
                  f"fires/day)")
    return {"pacing_blocked": blocked, "pacing_reason": reason,
            "remaining_slots": remaining_slots, "reserve_for_future_usd": round(reserve, 2),
            "allowance_usd": allowance}


def check(day: Optional[str] = None, cfg: Optional[dict] = None,
          path: Optional[Path] = None, cfg_path: Optional[Path] = None) -> dict:
    """Decide whether the conductor may do LLM work right now. Never raises."""
    cfg = cfg or load_config(cfg_path)
    s = spend_today(day, path)
    pacing_info = _pacing(s, cfg)
    extra = {**_caps(cfg), **pacing_info}
    if not cfg.get("enabled", True):
        return {**s, "verdict": "PROCEED", "reason": "governor disabled in config", **extra}
    if s["corrected_usd"] >= float(cfg["daily_cap_usd"]):
        return {**s, "verdict": "EXHAUSTED",
                "reason": (f"corrected spend ${s['corrected_usd']:.2f} "
                           f">= cap ${float(cfg['daily_cap_usd']):.2f} "
                           f"(raw self-report ${s['raw_usd']:.2f} x{SELF_REPORT_CORRECTION})"),
                **extra}
    if s["fires"] >= int(cfg["max_fires"]):
        return {**s, "verdict": "EXHAUSTED",
                "reason": f"{s['fires']} fires today >= max_fires {cfg['max_fires']}",
                **extra}
    if pacing_info["pacing_blocked"]:
        return {**s, "verdict": "EXHAUSTED", "reason": pacing_info["pacing_reason"], **extra}
    return {**s, "verdict": "PROCEED",
            "reason": (f"${s['corrected_usd']:.2f} of ${float(cfg['daily_cap_usd']):.2f} used, "
                       f"{s['fires']}/{cfg['max_fires']} fires, ${pacing_info['allowance_usd']:.2f} "
                       f"paced allowance this fire ({pacing_info['remaining_slots']} slots left)"),
            **extra}


def _caps(cfg: dict) -> dict:
    return {"daily_cap_usd": float(cfg["daily_cap_usd"]), "max_fires": int(cfg["max_fires"]),
            "expected_fires_per_day": int(cfg.get("expected_fires_per_day",
                                                    DEFAULTS["expected_fires_per_day"])),
            "min_allowance_usd": float(cfg.get("min_allowance_usd",
                                                DEFAULTS["min_allowance_usd"]))}


def _write_status(res: dict, day: Optional[str]) -> None:
    """Best-effort spend-shape record: slots_used / slots_remaining / allowance_next. Never
    raises, never blocks the gate (C7) -- a write failure here must not affect the verdict
    already decided by check()."""
    try:
        payload = {
            "day": res.get("day") or day,
            "verdict": res.get("verdict"),
            "reason": res.get("reason"),
            "raw_usd": res.get("raw_usd"),
            "corrected_usd": res.get("corrected_usd"),
            "daily_cap_usd": res.get("daily_cap_usd"),
            "max_fires": res.get("max_fires"),
            "expected_fires_per_day": res.get("expected_fires_per_day"),
            "min_allowance_usd": res.get("min_allowance_usd"),
            "slots_used": res.get("fires"),
            "slots_remaining": res.get("remaining_slots"),
            "reserve_for_future_usd": res.get("reserve_for_future_usd"),
            "allowance_next_usd": res.get("allowance_usd"),
            "checked_at_utc": dt.datetime.utcnow().isoformat() + "Z",
        }
        STATUS_OUT.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATUS_OUT.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(STATUS_OUT)
    except Exception:  # noqa: BLE001 -- visibility record must never break the gate (C7)
        pass


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

    _write_status(res, a.date)
    print(json.dumps(res, indent=2) if a.json
          else f"{res['day']}  {res['verdict']}  {res['reason']}")
    if a.check and res["verdict"] == "EXHAUSTED":
        return EXIT_EXHAUSTED
    return EXIT_PROCEED


if __name__ == "__main__":
    raise SystemExit(main())
