"""live_watch_trendlines_brief.py -- WS8->WS7 READ-SIDE MERGE, compact text renderer
(2026-08-01, WEEKEND-TWELVE Next-Twelve #11).

WHAT THIS IS
------------
Two separate producers, two separate state files: `trendline-watch.json` (WS8, written
by `backtest/autoresearch/trendline_watch.py` every 5-min RTH fire) and `live-watch.json`
(WS7, written every minute during RTH by `setup/scripts/live_watch.py`). WS8's own file
already carries the intended contract in its `_merge_note` field: "READ this file and
embed this payload under an additive 'trendlines' key. One writer per state file -- this
producer never writes live-watch.json."

`live_watch.py` is owned by another lane tonight, so this module does the merge on the
READ side ONLY: it reads both files independently, embeds the trendline payload under an
additive `trendlines` key on an in-memory COPY of the live-watch snapshot (never written
back to disk, never mutates the input), and renders one compact text block combining
both -- the position/arm summary `live_watch.render_brief` already produces, plus one
new line of trendline context. It imports `live_watch.render_brief` (a pure function,
read-only reference) rather than reimplementing it, so the two renderers can never drift
out of sync -- but it makes ZERO edits to live_watch.py itself: not the writer, not
render_brief, not one byte.

Sibling to the dashboard-side merge in `dashboard/app/api/live-watch/route.ts` (same
additive-key contract, same "never touch the writer" boundary, TypeScript instead of
Python because that's the dashboard panel's language).

CLI: no args -> print the merged compact brief once, reading both files fresh. This
module has no write mode -- live-watch.json is live_watch.py's file to write.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
STATE = REPO / "automation" / "state"
LIVE_WATCH_PATH = STATE / "live-watch.json"
TRENDLINE_WATCH_PATH = STATE / "trendline-watch.json"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _read_json(path: Path) -> Optional[dict]:
    """Fail-open: missing/garbled file -> None. Matches live_watch.py's own _read_json
    contract (never raises, the caller's renderer already handles a None snapshot)."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001 -- read-side visibility helper, never crashes
        return None


def merge_trendlines(snap: Optional[dict], trendlines: Optional[dict]) -> Optional[dict]:
    """Pure, non-mutating merge: returns a NEW dict with `trendlines` embedded under the
    additive key trendline-watch.json's own _merge_note names -- never mutates `snap`.
    snap=None passes through unchanged (the base renderer already handles a missing
    snapshot; nothing to merge onto)."""
    if snap is None:
        return None
    merged = dict(snap)
    merged["trendlines"] = trendlines
    return merged


def render_trendline_summary(trendlines: Optional[dict]) -> Optional[str]:
    """One compact line of trendline context, or None when there is nothing worth
    printing (no file, garbled file, or zero active lines) -- the compact renderer stays
    exactly as terse as before when trendlines add nothing."""
    if not isinstance(trendlines, dict):
        return None
    n_active = trendlines.get("n_active")
    if not n_active:
        return None
    bits = [f"trendlines: {n_active}/{trendlines.get('n_total', '?')} active"]
    near = trendlines.get("nearest_active")
    if isinstance(near, dict):
        dist = near.get("distance_dollars")
        dist_s = f"{dist:.2f}" if isinstance(dist, (int, float)) else "?"
        bits.append(
            f"nearest {near.get('kind', '?')}[{near.get('flavor', '?')}] "
            f"{near.get('current_value', '?')} ({dist_s} {near.get('side', '?')}) "
            f"{near.get('status', '')}".rstrip()
        )
    last_break = trendlines.get("last_break")
    if isinstance(last_break, dict) and last_break.get("level") is not None:
        ts = str(last_break.get("ts_et") or "")[11:16]
        bits.append(
            f"last break {last_break.get('kind', '?')}[{last_break.get('flavor', '?')}] "
            f"{last_break.get('level')}" + (f" @ {ts}" if ts else "")
        )
    return " | ".join(bits)


def render_brief_with_trendlines(snap: Optional[dict], trendlines: Optional[dict]) -> str:
    """The compact text renderer: WS7's own `render_brief` output, byte-identical, plus
    one additional trendline-context line when trendline data is present. Imports
    live_watch for its pure render_brief function only -- never its write path, never
    edited."""
    import live_watch  # local import (matches this repo's bare-import convention, e.g.
                        # `import exit_manager as em`); sys.path insert happens at module
                        # load time above, before this function can be called.

    merged = merge_trendlines(snap, trendlines)
    base = live_watch.render_brief(merged)
    tl_line = render_trendline_summary(trendlines)
    return base if tl_line is None else f"{base}\n{tl_line}"


def main(argv: Optional[list[str]] = None) -> int:  # noqa: ARG001 -- no flags today
    snap = _read_json(LIVE_WATCH_PATH)
    trendlines = _read_json(TRENDLINE_WATCH_PATH)
    print(render_brief_with_trendlines(snap, trendlines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
