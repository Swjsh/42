"""participation_daily.py -- the GOAL-LAYER daily instrument (root-cause audit 2026-07-15 SS9).

WHY THIS EXISTS: the audit (markdown/audits/FIX-SHIP-REPEAT-ROOT-CAUSE-2026-07-15.md SS9,
Miner 3 / effort-allocation census) found ~36 of ~81 scheduled tasks are monitoring
instruments -- and ZERO of them measure GOAL ATTAINMENT (fills/day vs J's 2-4/day/account
target). Every existing instrument watches ALIVENESS (is it running) or CORRECTNESS (is this
veto right); none compute "did the engine actually participate enough today." The one tool
that could answer this -- backtest/tools/participation_cascade.py -- was built the day AFTER
J caught a $0 day from his own P&L ("6 arms and nothing took a trade from over 700 signals?
why didn't you see this yesterday?"), yet was never scheduled, had no installer, and was
imported by nothing. Both of 2026-07-15's goal-level failures ("Bold can't trade afternoons",
"0.82 fills/day") were computed ad hoc by a J-anger-triggered audit, not a standing instrument.
This script closes that gap with ONE daily fire (16:10 ET weekdays, after EOD-flatten +
BrokerFills so the day's ledger rows are settled):

  1. Calls participation_cascade.compute_cascade_day / write_state_file / write_report --
     REUSES its ledger-parsing + dedup + stage-classification, never reimplements it. This
     fire is also the first time participation_cascade.py's OWN artifacts
     (automation/state/participation-cascade.json + analysis/participation-cascade/{date}.md)
     get produced on a schedule at all.
  2. Derives PER-ACCOUNT (safe-2, bold-2 -- the two CORE production accounts in CLAUDE.md's
     account-context table; NOT the 4 extra fleet research arms) enter_verdicts / attempts /
     fills counts from the already-classified event list (see STAGE BUCKETS below).
  3. Compares fills to a per-account target (default 2-4/day; overridable per account via that
     account's OWN params.json keys participation_target_fills_min / _max -- not currently set
     anywhere, so both accounts run on the default today).
  4. Emits ONE glanceable verdict per account + an overall rollup (GREEN/YELLOW/RED/IDLE) to
     automation/state/participation-daily.json, and appends a goal-layer section to that
     session's analysis/participation-cascade/{date}.md report.
  5. On YELLOW/RED, appends one line to automation/state/discord-outbox.jsonl (schema mirrors
     self_check.py's {ts,channel,source,message} rows) so J sees a goal miss without asking --
     de-duped per (date, verdict) so a manual re-run for verification doesn't re-spam.

STAGE BUCKETS (derived from participation_cascade.py's own documented STAGE FUNNEL -- see that
module's docstring for the authoritative per-stage definitions):
  enter_verdicts = RISK_GATE_DENY + STALE_TRIGGER + PLACE_FAIL + PLACED + FILLED
                   ("the engine formed a directional ENTER_* verdict; this is what happened
                   after" -- for FLEET rows this is exact, since classify_fleet_row only reaches
                   these 4 non-STALE_TRIGGER stages when action.startswith("ENTER"); for CORE
                   rows STALE_TRIGGER is included too because heartbeat_core's staleness ladder
                   resolves BEFORE the verdict-prefix check, so a stale-trigger event is still a
                   real entry candidate the engine formed and then abandoned on data grounds).
  attempts       = PLACE_FAIL + PLACED + FILLED (an order actually reached the broker).
  fills          = FILLED only (broker-truth fill evidence).
  no-order sinks = every passed-scoring stage that is NOT PLACED/FILLED (the same universe
                   participation_cascade's own top_blockers leaderboard draws from), sliced to
                   one account instead of all 6 arms.

SCOPE NOTE (a real, verified finding -- not a bug in THIS script): this counts ENGINE-decided
fills only, same as the underlying module (core-decisions.jsonl). A J-called MANUAL fill that
bypasses the engine's decision path entirely is INVISIBLE here. Confirmed against 2026-07-15's
real data: journal/trades.csv shows 2 fills tagged account "safe" that day (1 engine ENTER_BULL
@ 13:56 ET + 1 manual j_called BEARISH_REJECTION @ 13:16 ET), but participation_cascade's safe-2
arm only classifies the engine one as FILLED -- the manual trade never enters core-decisions.jsonl
as an engine-scored row at all. This instrument measures "is the ENGINE hitting its goal," which
is deliberately narrower than "is the account hitting its goal" -- the two diverge whenever J
trades manually. Reconciling trades.csv into the fills count would mean re-implementing a SECOND
ledger parser on top of the one this script is explicitly told to reuse, not duplicate -- out of
scope for this fire; noted here so the gap is documented, not silently hidden (OP-33).

CLI:  backtest/.venv/Scripts/python.exe setup/scripts/participation_daily.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, mirrors context_bundle_producer.py /
# firm_brief.py / free_model_audit.py, 2026-07-14 popup-storm fix) =========================
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "participation-daily.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "participation-daily.stderr.log", "a", buffering=1, encoding="utf-8")
# ============================================================================================

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))    # et_clock (same dir)
sys.path.insert(0, str(REPO / "backtest" / "tools"))         # participation_cascade

from et_clock import et_now                     # noqa: E402
import participation_cascade as pc               # noqa: E402
from arm_display import display_name_for_arm_id  # noqa: E402  (2026-07-17 arm display names)

STATE = REPO / "automation" / "state"
ANALYSIS_DIR = REPO / "analysis" / "participation-cascade"
OUT_F = STATE / "participation-daily.json"
DISCORD_OUTBOX = STATE / "discord-outbox.jsonl"
LAST_ALERT_F = STATE / "participation-daily-last-alert.json"

SAFE_PARAMS = STATE / "params.json"
BOLD_PARAMS = STATE / "aggressive" / "params.json"

DEFAULT_TARGET_MIN = 2
DEFAULT_TARGET_MAX = 4
RED_ENTER_VERDICT_FLOOR = 5   # 0 fills + >= this many ENTER verdicts -> RED (a real hole, not a quiet day)

# See module docstring "STAGE BUCKETS" -- names are the literal `stage` strings
# participation_cascade.classify_core_row / classify_fleet_row already assign.
_ENTER_VERDICT_STAGES = frozenset({"RISK_GATE_DENY", "STALE_TRIGGER", "PLACE_FAIL", "PLACED", "FILLED"})
_ATTEMPT_STAGES = frozenset({"PLACE_FAIL", "PLACED", "FILLED"})
_NO_ORDER_BLOCKER_STAGES = frozenset({
    "STRUCTURE_VETO", "GATE_BLOCK", "WINDOW_BLOCK", "STALE_TRIGGER", "RISK_GATE_DENY",
    "PLACE_FAIL", "OTHER_BLOCK",
})

ACCOUNTS = pc.CORE_ARM_LABEL   # {"safe": "safe-2", "bold": "bold-2"} -- the 2 real J-facing accounts


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def account_target(account: str) -> tuple[int, int]:
    """(min, max) daily fill target for `account` ('safe'|'bold'). params-overridable via
    that account's OWN params.json keys participation_target_fills_min/_max; default 2/4
    when absent (true for both accounts as of this writing)."""
    params = _load_json(SAFE_PARAMS if account == "safe" else BOLD_PARAMS)
    lo = params.get("participation_target_fills_min", DEFAULT_TARGET_MIN)
    hi = params.get("participation_target_fills_max", DEFAULT_TARGET_MAX)
    try:
        return int(lo), int(hi)
    except (TypeError, ValueError):
        return DEFAULT_TARGET_MIN, DEFAULT_TARGET_MAX


def account_stats(cascade_day: dict, arm: str) -> dict:
    """Derive (enter_verdicts, attempts, fills, top-3 no-order sinks) for one arm from
    compute_cascade_day's already-parsed+classified `events` list. NO ledger re-parsing."""
    events = [e for e in cascade_day.get("events", []) if e.get("arm") == arm]
    enter_verdicts = sum(1 for e in events if e["stage"] in _ENTER_VERDICT_STAGES)
    attempts = sum(1 for e in events if e["stage"] in _ATTEMPT_STAGES)
    fills = sum(1 for e in events if e["stage"] == "FILLED")
    blocker_events = [e for e in events if e["stage"] in _NO_ORDER_BLOCKER_STAGES]
    leaderboard = Counter((e["category"], e["blocker"] or e["stage"]) for e in blocker_events)
    top3 = [{"blocker": name, "category": cat, "n_events": n}
            for (cat, name), n in leaderboard.most_common(3)]
    return {"enter_verdicts": enter_verdicts, "attempts": attempts, "fills": fills,
            "top_no_order_sinks": top3}


def account_verdict(fills: int, enter_verdicts: int, target_min: int) -> str:
    """IDLE: nothing scored at all today (holiday / feed down -- never false-alarm on silence).
    RED: a real participation hole -- zero fills on a day the engine formed >=5 ENTER verdicts.
    YELLOW: fills short of the account's own daily-min target.
    GREEN: target met or beaten."""
    if enter_verdicts == 0:
        return "IDLE"
    if fills == 0 and enter_verdicts >= RED_ENTER_VERDICT_FLOOR:
        return "RED"
    if fills < target_min:
        return "YELLOW"
    return "GREEN"


_SEVERITY = {"GREEN": 0, "IDLE": 1, "YELLOW": 2, "RED": 3}


def rollup_verdict(account_verdicts: list[str]) -> str:
    """Worst-account-wins, same traffic-light rollup pattern as gym-session. Ordering is
    GREEN < IDLE < YELLOW < RED -- GREEN is the only state better than "no data": a same-day
    split where one account traded normally (GREEN) while the other scored ZERO signals all
    day (IDLE) is itself worth a glance (real precedent in this repo: Bold's afternoon
    strike-floor collision, queue.md EOD-2026-07-15 item 1), so IDLE must not silently read as
    fine just because it isn't a confirmed miss. YELLOW/RED (confirmed shortfalls) still
    outrank IDLE (merely ambiguous/no-data, e.g. a real market holiday)."""
    if not account_verdicts:
        return "IDLE"
    return max(account_verdicts, key=lambda v: _SEVERITY[v])


def resolve_sessions(date_arg: Optional[str], n: int = 10) -> list[dict]:
    """Mirrors participation_cascade.py's own main() --date resolution EXACTLY (reused logic,
    not reimplemented parsing) so this wrapper's --date behaves identically to the underlying
    CLI's. Returns the trailing `n` cascade-day dicts, most-recent last."""
    if date_arg:
        all_days = pc.discover_sessions(0)   # 0 = no truncation, search full ledger history
        days = [d for d in all_days if d <= date_arg]
        if not days or days[-1] != date_arg:
            days.append(date_arg)             # target date has no ledger rows yet -- still analyze (-> IDLE)
        days = days[-n:]
        return [pc.compute_cascade_day(d) for d in days]
    return pc.compute_cascade_sessions(n)


def compute_daily(cascade_day: dict) -> dict:
    """The goal-layer view for one already-computed cascade day."""
    accounts = {}
    for account, arm in ACCOUNTS.items():
        lo, hi = account_target(account)
        stats = account_stats(cascade_day, arm)
        verdict = account_verdict(stats["fills"], stats["enter_verdicts"], lo)
        accounts[account] = {"arm": arm, "target_min": lo, "target_max": hi, "verdict": verdict, **stats}
    overall = rollup_verdict([a["verdict"] for a in accounts.values()])
    return {
        "date": cascade_day["date"],
        "generated_at_et": et_now().strftime("%Y-%m-%dT%H:%M:%S"),
        "verdict": overall,
        "accounts": accounts,
        "cascade": {
            "n_passed_scoring_events": cascade_day["n_passed_scoring_events"],
            "n_orders": cascade_day["n_orders"],
            "joint_participation_pct": cascade_day["joint_participation_pct"],
            "spy_range_pct": cascade_day["spy_range_pct"],
            "cascade_verdict": cascade_day["verdict"],
        },
        "scope_note": (
            "ENGINE-decided fills only (core-decisions.jsonl via participation_cascade.py). "
            "A J-called MANUAL fill that bypasses the engine's decision path is invisible to "
            "this instrument -- see participation_daily.py module docstring SCOPE NOTE."
        ),
    }


def render_line(daily: dict) -> str:
    parts = [f"{acc}={a['fills']}/{a['target_min']}-{a['target_max']} [{a['verdict']}]"
             for acc, a in daily["accounts"].items()]
    return (f"PARTICIPATION {daily['date']} [{daily['verdict']}]  " + " ".join(parts) +
            f"  (cascade: passed_scoring={daily['cascade']['n_passed_scoring_events']} "
            f"orders={daily['cascade']['n_orders']} cascade_verdict={daily['cascade']['cascade_verdict']})")


def render_markdown_section(daily: dict) -> str:
    lines = [f"## Goal-layer daily check (participation_daily.py) -- {daily['date']}", "",
             f"**Verdict: {daily['verdict']}** -- generated {daily['generated_at_et']} ET.", "",
             daily["scope_note"], "",
             "| account | fills | target | enter_verdicts | attempts | verdict |",
             "|---|---|---|---|---|---|"]
    for acc, a in daily["accounts"].items():
        # DISPLAY NAME (2026-07-17): a['arm'] stays the raw accounts.json id (unchanged --
        # nothing downstream keys off this markdown table), display_name is appended so
        # "safe-2" reads as "safe-2 CORE-SAFE (KIQE)" instead of a bare, ambiguous number.
        arm_label = display_name_for_arm_id(a['arm'])
        arm_s = a['arm'] if arm_label == a['arm'] else f"{a['arm']} {arm_label}"
        lines.append(f"| {acc} ({arm_s}) | {a['fills']} | {a['target_min']}-{a['target_max']} | "
                      f"{a['enter_verdicts']} | {a['attempts']} | {a['verdict']} |")
    lines.append("")
    for acc, a in daily["accounts"].items():
        if not a["top_no_order_sinks"]:
            continue
        lines.append(f"**{acc} top no-order sinks:**")
        for b in a["top_no_order_sinks"]:
            lines.append(f"- {b['n_events']}x [{b['category']}] {b['blocker']}")
        lines.append("")
    return "\n".join(lines)


def write_daily_state(daily: dict) -> Path:
    OUT_F.write_text(json.dumps(daily, indent=1), encoding="utf-8")
    return OUT_F


def append_markdown(daily: dict) -> Optional[Path]:
    """Append the goal-layer section to that day's analysis/participation-cascade/{date}.md.
    Safe to call after pc.write_report() (which OVERWRITES the base cascade content fresh each
    run) -- the overwrite-then-append sequence within one process always yields exactly one
    goal-layer section, so no separate dedup bookkeeping is needed here."""
    report_path = ANALYSIS_DIR / f"{daily['date']}.md"
    section = render_markdown_section(daily)
    try:
        ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
        existing = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
        with report_path.open("a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n\n"):
                f.write("\n")
            f.write(section + "\n")
        return report_path
    except OSError:
        return None


def _already_alerted_today(day: str, verdict: str) -> bool:
    last = _load_json(LAST_ALERT_F)
    return last.get("date") == day and last.get("verdict") == verdict


def maybe_alert_discord(daily: dict) -> bool:
    """Append ONE discord-outbox line on YELLOW/RED, de-duped per (date, verdict) so a manual
    re-run (e.g. for verification) never re-spams. Schema mirrors self_check.py's existing
    {ts,channel,source,message} outbox rows (both accepted schemas -- see discord-bridge.py's
    G5 note -- but this one matches the sibling DEGRADED-alert producer most closely)."""
    if daily["verdict"] not in ("YELLOW", "RED"):
        return False
    if _already_alerted_today(daily["date"], daily["verdict"]):
        return False
    try:
        with DISCORD_OUTBOX.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": daily["generated_at_et"], "channel": "gamma-ops",
                "source": "participation_daily",
                "message": f"PARTICIPATION {daily['verdict']}: " + render_line(daily),
            }) + "\n")
        LAST_ALERT_F.write_text(json.dumps({"date": daily["date"], "verdict": daily["verdict"]}),
                                 encoding="utf-8")
        return True
    except OSError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Daily GOAL-LAYER check: fills/day vs J's 2-4/day/account target (root-cause audit 2026-07-15 SS9)")
    ap.add_argument("--date", default=None, help="ET date YYYY-MM-DD (default: latest session)")
    args = ap.parse_args()

    sessions = resolve_sessions(args.date, 10)
    if not sessions:
        print("[participation-daily] no sessions found in core-decisions.jsonl / fleet ledgers.")
        return 0
    cascade_day = sessions[-1]
    day = cascade_day["date"]

    # (Re-)write participation_cascade.py's OWN artifacts -- it has never run on a schedule
    # before this task, so these have never been produced on a cadence until now.
    p_state = pc.write_state_file(sessions)
    p_report = pc.write_report(sessions, spotlight=(day,))

    daily = compute_daily(cascade_day)
    write_daily_state(daily)
    append_markdown(daily)
    alerted = maybe_alert_discord(daily)

    print(render_line(daily))
    print(f"[participation-daily] wrote {OUT_F}")
    print(f"[participation-daily] wrote {p_state}" if p_state else "[participation-daily] WARN cascade state write failed")
    print(f"[participation-daily] appended goal-layer section to {p_report}" if p_report else
          "[participation-daily] WARN cascade report write failed")
    if alerted:
        print("[participation-daily] YELLOW/RED -> appended automation/state/discord-outbox.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
