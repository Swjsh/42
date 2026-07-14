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
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state" / "trendline-draw-state.json"


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


def save(entries: list[dict]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"drawn": entries}, indent=2), encoding="utf-8")


def ids_to_clear() -> list[str]:
    """Entity IDs from the PRIOR draw pass -- call draw_remove_one on each of these (never
    draw_clear) before drawing the new set, so a refresh doesn't accumulate stale lines."""
    return [e["entity_id"] for e in load().get("drawn", []) if e.get("entity_id")]


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

    args = p.parse_args()
    if args.cmd == "list-ids":
        for entity_id in ids_to_clear():
            print(entity_id)
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
