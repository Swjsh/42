"""trendline_watch.py -- WS8 (2026-08-01): the trendline VISIBILITY bridge.

THE GAP THIS CLOSES: the multi-day trendline engine (trendline_engine.py, 5-min
Gamma_Trendlines task) correctly logged Friday 07-31's 10:15 trend break in real
time -- and NOTHING consumed it. This module turns the engine's two existing
outputs (automation/state/trendlines-live.json overwrite-state + the append-only
analysis/trendlines/trendline-log.jsonl) into ONE consumer-ready surface:

    automation/state/trendline-watch.json
      - active (non-BROKEN) lines with flavor (wick|body), tier, status, value
      - nearest active line to last close (distance + side)
      - last BREAK event + last RETEST event (status TRANSITIONS mined from the
        log tail -- not just "latest row with status X")
      - a ready-made one-sentence premarket_line consumed verbatim by
        setup/scripts/daily_brief.py --mode morning (Gamma_MorningBrief 08:45 ET)

MERGE POINT (WS7 coordination, stated per the 2026-08-01 weekend-grind brief):
live-watch.json does not exist yet (WS7's setup/scripts/live_watch.py is
pending as of this build). When WS7 lands, live_watch.py should READ
automation/state/trendline-watch.json and embed its payload under an additive
"trendlines" key of live-watch.json. This module deliberately does NOT write
live-watch.json itself -- ONE WRITER PER STATE FILE (the 2026-07-31 fleet
build_shared_signal write/read race: two writers on one surface forfeited a
3-min cadence slot; never again by construction).

FAIL-OPEN EVERYWHERE (C7): a missing/garbled input degrades to an honest
"no data" payload -- never a crash. The engine hook in trendline_engine.main()
additionally wraps refresh() in try/except so visibility can NEVER break the
5-min production fire.

STATUS SEMANTICS (inherited from trendline_engine._fit, unchanged here):
INTACT = holding, TESTING = price at the line this bar, BROKEN = closed through.
ACTIVE = INTACT | TESTING. Events: prev!=BROKEN -> BROKEN is a "break";
INTACT -> TESTING is a "retest". Line identity for transition-tracking =
(kind, anchor_family, tier, a_et, b_et) -- the anchor pair IS the line.

Run standalone:  python backtest/autoresearch/trendline_watch.py [--print-line]
Production: called by trendline_engine.main() after write_live_state each fire.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
LIVE_STATE = REPO / "automation" / "state" / "trendlines-live.json"
LOG = REPO / "analysis" / "trendlines" / "trendline-log.jsonl"
WATCH = REPO / "automation" / "state" / "trendline-watch.json"

SETUP_SCRIPTS = REPO / "setup" / "scripts"
if str(SETUP_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SETUP_SCRIPTS))
from et_clock import et_now  # noqa: E402

SCHEMA_VERSION = 1
LOG_TAIL_LINES = 2000   # ~2 sessions of 5-min fires x <=8 lines/fire -- plenty for "last event"
MAX_EVENTS_KEPT = 5

ACTIVE_STATUSES = ("INTACT", "TESTING")


# --------------------------------------------------------------------------- io
def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _read_log_tail(path: Path, max_lines: int = LOG_TAIL_LINES) -> list[dict]:
    """Last max_lines parsed rows of the append-only trendline log. Garbled lines
    are skipped (counted nowhere -- the log is telemetry, not a ledger)."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    rows: list[dict] = []
    for ln in raw[-max_lines:]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue
        if isinstance(d, dict):
            rows.append(d)
    return rows


def _atomic_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ------------------------------------------------------------------ event mining
def _line_identity(row: dict) -> tuple:
    return (row.get("kind"), row.get("anchor_family"), row.get("tier", "primary"),
            row.get("a_et"), row.get("b_et"))


def detect_events(rows: list[dict]) -> list[dict]:
    """Mine status TRANSITIONS per line identity from chronological log rows.

    break  = prev status != BROKEN -> BROKEN   (the line just gave way)
    retest = prev status == INTACT -> TESTING  (price just came back to the line)

    A line first seen already-BROKEN / already-TESTING emits NO event (no prior
    state to transition from -- avoids re-announcing stale states every fire).
    Returns events chronologically (oldest first), each carrying ts_et, type,
    kind, flavor, tier, level (current_value at the transition row) and the
    row's human summary.
    """
    last_status: dict[tuple, str] = {}
    events: list[dict] = []
    for row in rows:
        ident = _line_identity(row)
        status = row.get("status")
        if status not in ("INTACT", "TESTING", "BROKEN"):
            continue
        prev = last_status.get(ident)
        if prev is not None and prev != status:
            ev_type = None
            if status == "BROKEN" and prev != "BROKEN":
                ev_type = "break"
            elif status == "TESTING" and prev == "INTACT":
                ev_type = "retest"
            if ev_type:
                events.append({
                    "type": ev_type,
                    "ts_et": row.get("ts_et"),
                    "date_et": row.get("date_et"),
                    "kind": row.get("kind"),
                    "flavor": row.get("anchor_family"),
                    "tier": row.get("tier", "primary"),
                    "level": row.get("current_value"),
                    "summary": row.get("summary") or "",
                })
        last_status[ident] = status
    return events


# ------------------------------------------------------------------ payload build
def _slim_line(ln: dict) -> dict:
    return {
        "kind": ln.get("kind"),
        "flavor": ln.get("anchor_family"),
        "tier": ln.get("tier", "primary"),
        "status": ln.get("status"),
        "current_value": ln.get("current_value"),
        "break_level": ln.get("break_level"),
        "respect_count": ln.get("respect_count"),
        "violations": ln.get("violations"),
        "slope_per_bar": ln.get("slope_per_bar"),
        "summary": ln.get("summary") or "",
    }


def _nearest_active(lines: list[dict], last_close: Optional[float]) -> Optional[dict]:
    """Nearest ACTIVE (non-BROKEN) line to last_close, with signed side."""
    if last_close is None:
        return None
    best = None
    for ln in lines:
        if ln.get("status") not in ACTIVE_STATUSES:
            continue
        cv = ln.get("current_value")
        if not isinstance(cv, (int, float)):
            continue
        dist = abs(cv - last_close)
        if best is None or dist < best["distance_dollars"]:
            best = {
                "kind": ln.get("kind"),
                # NOTE: input dicts here are SLIMMED lines (anchor_family already
                # renamed to "flavor" by _slim_line) -- caught live on first run
                # ("nearest None support"): never read the pre-slim field name.
                "flavor": ln.get("flavor"),
                "tier": ln.get("tier", "primary"),
                "status": ln.get("status"),
                "current_value": cv,
                "distance_dollars": round(dist, 2),
                "side": "above" if cv > last_close else "below",
                "vs_close": last_close,
            }
    return best


def build_watch_payload(live_state: Optional[dict], log_rows: list[dict],
                        now_et_iso: str) -> dict:
    """Pure assembly -- no IO, fully unit-testable. Degrades honestly on None."""
    lines_raw = (live_state or {}).get("trendlines") or []
    lines = [_slim_line(ln) for ln in lines_raw if isinstance(ln, dict)]
    active = [ln for ln in lines if ln.get("status") in ACTIVE_STATUSES]
    last_close = None
    for ln in lines_raw:
        lc = ln.get("last_close")
        if isinstance(lc, (int, float)):
            last_close = lc
            break
    events = detect_events(log_rows)
    breaks = [e for e in events if e["type"] == "break"]
    retests = [e for e in events if e["type"] == "retest"]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ts_et": now_et_iso,
        "source": {
            "live_state": "automation/state/trendlines-live.json",
            "log": "analysis/trendlines/trendline-log.jsonl",
            "producer": "backtest/autoresearch/trendline_watch.py (fed by trendline_engine.main, 5-min Gamma_Trendlines RTH)",
        },
        "live_state_ts_et": (live_state or {}).get("ts_et"),
        "live_state_date_et": (live_state or {}).get("date_et"),
        "n_total": len(lines),
        "n_active": len(active),
        "last_close": last_close,
        "active_lines": active,
        "all_lines": lines,
        "nearest_active": _nearest_active(lines, last_close),
        "last_break": breaks[-1] if breaks else None,
        "last_retest": retests[-1] if retests else None,
        "recent_events": events[-MAX_EVENTS_KEPT:],
        "_merge_note": ("WS7 live-watch.json integration: READ this file and embed this payload "
                        "under an additive 'trendlines' key. One writer per state file -- this "
                        "producer never writes live-watch.json."),
    }
    payload["premarket_line"] = premarket_line(payload)
    return payload


def premarket_line(payload: dict) -> str:
    """ONE short spoken sentence for the morning brief (Gamma_MorningBrief is
    word-capped at 140 -- keep this lean). Always carries the as-of stamp:
    Gamma_Trendlines fires RTH-only, so at 08:45 the state is yesterday's close."""
    asof = payload.get("live_state_ts_et") or "unknown time"
    asof_short = asof[5:16].replace("T", " ") if isinstance(asof, str) and len(asof) >= 16 else str(asof)
    n_act = payload.get("n_active") or 0
    if not payload.get("n_total"):
        return "Trendlines: none on file yet."
    if not n_act:
        line = f"Trendlines: 0 active as of {asof_short}"
    else:
        near = payload.get("nearest_active") or {}
        if near:
            line = (f"Trendlines: {n_act} active as of {asof_short}, nearest "
                    f"{near.get('flavor', '?')} {near.get('kind', '?')} at "
                    f"{near.get('current_value'):.2f}, {near.get('distance_dollars'):.2f} "
                    f"{near.get('side', '?')} close")
        else:
            line = f"Trendlines: {n_act} active as of {asof_short}"
    lb = payload.get("last_break")
    if lb and lb.get("level") is not None:
        line += (f"; last break {lb.get('flavor', '?')} {lb.get('kind', '?')} "
                 f"{lb.get('level'):.2f} at {(lb.get('ts_et') or '?')[5:16].replace('T', ' ')}")
    return line + "."


# -------------------------------------------------------------------------- main
def refresh(now_et_iso: Optional[str] = None) -> dict:
    """Load inputs, build payload, atomically write WATCH. Returns the payload.
    Never raises on missing/garbled inputs (fail-open); may raise on an unwritable
    disk -- the engine hook wraps this call in try/except for that case."""
    now_et_iso = now_et_iso or et_now().strftime("%Y-%m-%dT%H:%M:%S")
    payload = build_watch_payload(_read_json(LIVE_STATE), _read_log_tail(LOG), now_et_iso)
    _atomic_write_json(WATCH, payload)
    return payload


def main(argv: Optional[list] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--print-line", action="store_true", help="print the premarket one-liner")
    args = ap.parse_args(argv)
    payload = refresh()
    print(f"trendline_watch: wrote {WATCH.relative_to(REPO)} "
          f"(n_active={payload['n_active']}, last_break={'yes' if payload['last_break'] else 'none'})")
    if args.print_line:
        print(payload["premarket_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
