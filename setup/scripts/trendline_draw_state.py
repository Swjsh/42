"""trendline_draw_state.py -- persistence helper for the trendline-draw VISIBILITY BRIDGE
(T14, 2026-07-14: J's audit -- "why have we not drawn one yet i can see it from pre market").

WHY THIS EXISTS: trendline_engine.py (the live Gamma_Trendlines fire, every 5 min RTH) detects
and LOGS respected trendlines but never drew them on J's chart -- draw_shape/draw_clear/
draw_list are TradingView MCP tools, only callable from a live Claude+CDP session, never from
the headless pythonw scheduled-task chain (verified: draw_shape only appears in automation/
prompts/*.md persona instructions, never in a standalone .py script). So the DRAW step is
necessarily an on-demand (or premarket-session-embedded) skill invocation, not a new pythonw
daemon -- this module is the small piece of it that CAN run standalone: tracking which
TradingView entity_ids belong to the ENGINE's own drawings (never J's manual ones) so a refresh
can scope-clear via draw_remove_one instead of draw_clear.

draw_clear has NO tag/scope parameter (verified against the TV MCP tool schema: it takes zero
arguments and removes EVERY drawing on the chart) -- calling it would wipe J's own manually
drawn lines too. The only scoped-removal primitive the TV MCP exposes is draw_remove_one(entity_
id), so scoped clearing has to be built here, application-side, by remembering the IDs we drew.

No MCP calls happen in this module -- it is pure state I/O. The actual draw loop (call
draw_shape, capture entity_id, call this script to record it) lives in the trendline-draw skill
(.claude/skills/trendline-draw/SKILL.md), which runs inside a live Claude+MCP session.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state" / "trendline-draw-state.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from et_clock import et_now
except Exception:  # noqa: BLE001
    import datetime as _dt
    from zoneinfo import ZoneInfo

    def et_now():  # pragma: no cover -- fallback mirrors self_check.py's own fallback
        return _dt.datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)


def load() -> dict:
    if not STATE.exists():
        return {"drawn": []}
    try:
        payload = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"drawn": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("drawn"), list):
        return {"drawn": []}
    return payload


def save(entries: list[dict], *, last_run: dict | None = None) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {"drawn": entries}
    if last_run is not None:
        payload["last_run"] = last_run
    else:
        # record()/clear_record() don't know about last_run -- preserve whatever mark_run()
        # last wrote so a bookkeeping-only save never silently erases the freshness stamp.
        prior = load().get("last_run")
        if prior is not None:
            payload["last_run"] = prior
    STATE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def ids_to_clear() -> list[str]:
    """Entity IDs from the PRIOR draw pass -- call draw_remove_one on each of these (never
    draw_clear) before drawing the new set, so a refresh doesn't accumulate stale lines."""
    return [e["entity_id"] for e in load().get("drawn", []) if e.get("entity_id")]


def mark_run(status: str, reason: str = "") -> dict:
    """Stamp the outcome of a Step 5c (or on-demand skill) invocation -- TRENDLINE-FIXES-2026-07-17
    item 1: 'PREMARKET DRAW CANNOT SILENTLY SKIP'. Two budget-skips in two days (2026-07-16/17)
    went to journal '## Setups skipped' only -- nothing self_check/engine-health reads, so J never
    saw it. This is independent of the entity-id bookkeeping above (a 'skipped' run has no
    entities). NOTE (2026-09-03): self_check.check_trendline_draw_freshness() was RE-POINTED at
    the new headless producer's stamp (`trendline-headless-draw.json`, written by
    `setup/scripts/trendline_headless_draw.py`) and no longer reads this file's `last_run` --
    kept here only for anyone still invoking the LLM skill by hand; see that function's
    docstring for the full re-point rationale (TRENDLINE-DRAW-HEADLESS)."""
    now = et_now()
    last_run = {
        "status": status,
        "reason": reason,
        "date_et": now.strftime("%Y-%m-%d"),
        "ts_et": now.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    entries = load().get("drawn", [])
    save(entries, last_run=last_run)
    return last_run


def record(entity_id: str, kind: str, family: str, label: str = "") -> list[dict]:
    entries = load().get("drawn", [])
    entries.append({"entity_id": entity_id, "kind": kind, "family": family, "label": label})
    save(entries)
    return entries


def clear_record() -> None:
    """Wipe OUR OWN bookkeeping only (call this AFTER draw_remove_one has actually removed each
    ID from the chart -- clearing the record without removing the chart lines first would leak
    orphaned drawings that nothing can find again)."""
    save([])


def _cli() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-ids", help="Print prior entity_ids, one per line (for draw_remove_one).")

    rec = sub.add_parser("record", help="Persist one newly-drawn entity_id.")
    rec.add_argument("--entity-id", required=True)
    rec.add_argument("--kind", required=True, choices=["support", "resistance"])
    rec.add_argument("--family", required=True, choices=["wick", "body"])
    rec.add_argument("--label", default="")

    sub.add_parser("clear-record", help="Wipe the bookkeeping after chart-side removal.")
    sub.add_parser("show", help="Print the current record as JSON.")

    mr = sub.add_parser("mark-run", help="Stamp today's Step 5c outcome for self_check staleness detection.")
    mr.add_argument("--status", required=True, choices=["success", "skipped"])
    mr.add_argument("--reason", default="")

    args = p.parse_args()
    if args.cmd == "list-ids":
        for entity_id in ids_to_clear():
            print(entity_id)
        return 0
    if args.cmd == "mark-run":
        last_run = mark_run(args.status, args.reason)
        suffix = f" -- {last_run['reason']}" if last_run["reason"] else ""
        print(f"marked {last_run['status']} at {last_run['ts_et']} ET{suffix}")
        return 0
    if args.cmd == "record":
        entries = record(args.entity_id, args.kind, args.family, args.label)
        print(f"recorded {args.entity_id} ({args.kind}/{args.family}) -- {len(entries)} total tracked")
        return 0
    if args.cmd == "clear-record":
        clear_record()
        print("cleared trendline-draw-state.json bookkeeping (0 entries tracked)")
        return 0
    if args.cmd == "show":
        print(json.dumps(load(), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
