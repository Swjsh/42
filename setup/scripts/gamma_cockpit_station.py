"""gamma_cockpit_station.py -- the Station panel payload builder (GOAL-GAMMA-STATION-
2026-09-13 item (5), "the TV face").

Reads the Station loop's own outputs (setup/scripts/station_loop.py is the writer; this
module is READ-ONLY and never imports its writer functions) and reshapes them for the
cockpit's Command view:
    automation/state/station/ideas-board.json   -> the ideas board (title/mechanism/
                                                     evidence/proposed_shadow_test/
                                                     cost_line/confidence/status/ts_et)
    automation/state/station/station-brief.md   -> the latest first-person brief
    automation/state/station/config.json        -> the planner model name
    automation/state/station/mode.json          -> J's gaming/work/off switch
    automation/state/station/loop-ledger.jsonl  -> last loop fire (planner status) +
                                                     the last 10 rows
    nvidia-smi (2s budget)                      -> current GPU utilization %

CONTRACT (mirrors gamma_cockpit_tiles.py's tile shape so the existing srcRow()/health()
JS helpers render it with no new client code): every sub-section is its own dict
carrying at least {ok, path, stamp_et, verdict, say, source}; verdict in
{green, amber, red, off}. A missing/garbled source degrades that ONE sub-section to
ok:False with a "NO DATA, looked for <path>" say -- it never raises and never
fabricates a card, a brief line, or a ledger row (OP-33 / C7).

No LLM call, no write anywhere (this module only ever reads), no subprocess beyond one
2s-budget nvidia-smi probe that fails open (None, never an exception) on any error.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

REPO = Path(__file__).resolve().parents[2]
STATION_DIR = REPO / "automation" / "state" / "station"
IDEAS_BOARD_PATH = STATION_DIR / "ideas-board.json"
BRIEF_PATH = STATION_DIR / "station-brief.md"
CONFIG_PATH = STATION_DIR / "config.json"
MODE_PATH = STATION_DIR / "mode.json"
LEDGER_PATH = STATION_DIR / "loop-ledger.jsonl"

LEDGER_TAIL_N = 10

sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import et_now  # noqa: E402 -- DST-aware ET, no subprocess needed
import station_board  # noqa: E402 -- reuse read_json_or_none, never re-implement it


def _rel(p: Path) -> str:
    """Posix repo-relative path; falls back to a posix-ified absolute string for a
    path outside REPO (a tmp_path fixture in tests)."""
    try:
        return p.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return str(p).replace("\\", "/")


def _source_meta(p: Path) -> dict:
    """{path, age_h, last_write} -- the exact shape gamma_cockpit_js.py's srcRow()
    already renders (prefers last_write for a live-updating age; age_h is the
    build-time fallback). A missing file still returns all three keys, age fields
    None -- callers never need a second shape for "not found"."""
    rel = _rel(p)
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return {"path": rel, "age_h": None, "last_write": None}
    age_h = (datetime.now(timezone.utc).timestamp() - mtime) / 3600.0
    last_write = et_now(now_utc=datetime.fromtimestamp(mtime, tz=timezone.utc)).replace(microsecond=0).isoformat()
    return {"path": rel, "age_h": round(age_h, 3), "last_write": last_write}


def _no_data(p: Path, extra: dict) -> dict:
    src = _source_meta(p)
    row = {"ok": False, "path": src["path"], "stamp_et": None, "verdict": "off",
           "say": f"NO DATA, looked for {src['path']}", "source": src}
    row.update(extra)
    return row


def _gpu_util_pct() -> float | None:
    """Best-effort GPU utilization within a 2s budget -- fails open (None), never
    blocks the page build. An independent copy of station_loop.py's own
    _gpu_util_pct (that function is underscore-private to that module; a sibling
    reader must never import another module's private API) -- same invocation
    shape, a tighter timeout because this runs inline in a page-generation pass
    rather than a 30-minute loop fire."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2, creationflags=_CREATE_NO_WINDOW,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        return float(out.stdout.strip().splitlines()[0].strip())
    except Exception:  # noqa: BLE001 -- a stalled/missing nvidia-smi is NO DATA, never a crash
        return None


def _tail_jsonl(p: Path, n: int) -> tuple[list, int]:
    """Returns (last-n-parsed-rows, skipped_line_count). Never raises: an unreadable
    file returns ([], 0); a malformed line is skipped and counted rather than
    aborting the read (same fail-open contract as gamma_cockpit_costpulse.py)."""
    try:
        text = p.read_text(encoding="utf-8-sig")
    except OSError:
        return [], 0
    rows, skipped = [], 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            skipped += 1
    return rows[-n:], skipped


def _ideas_section() -> dict:
    if not IDEAS_BOARD_PATH.exists():
        return _no_data(IDEAS_BOARD_PATH, {"cards": []})
    board = station_board.load_board(IDEAS_BOARD_PATH)
    src = _source_meta(IDEAS_BOARD_PATH)
    cards = [
        {
            "id": c.get("id", ""),
            "title": c.get("title", ""),
            "mechanism": c.get("mechanism", ""),
            "evidence": c.get("evidence", []) if isinstance(c.get("evidence"), list) else [],
            "proposed_shadow_test": c.get("proposed_shadow_test", ""),
            "cost_line": c.get("cost_line", ""),
            "confidence": c.get("confidence", ""),
            "status": c.get("status", "proposed"),
            "ts_et": c.get("ts_et", ""),
        }
        for c in board if isinstance(c, dict)
    ]
    return {
        "ok": True, "path": src["path"], "stamp_et": src["last_write"],
        "verdict": "green" if cards else "amber",
        "say": f"{len(cards)} card(s) on the board" if cards else "board is empty",
        "source": src, "cards": cards,
    }


def _brief_section() -> dict:
    if not BRIEF_PATH.exists():
        return _no_data(BRIEF_PATH, {"text": ""})
    try:
        text = BRIEF_PATH.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return _no_data(BRIEF_PATH, {"text": ""})
    src = _source_meta(BRIEF_PATH)
    return {
        "ok": bool(text), "path": src["path"], "stamp_et": src["last_write"],
        "verdict": "green" if text else "amber",
        "say": "latest brief" if text else "brief is empty",
        "source": src, "text": text,
    }


def _planner_section(ledger_rows: list) -> dict:
    cfg = station_board.read_json_or_none(CONFIG_PATH)
    model = (cfg or {}).get("model") if isinstance(cfg, dict) else None
    mode_data = station_board.read_json_or_none(MODE_PATH)
    mode = (mode_data or {}).get("mode", "work") if isinstance(mode_data, dict) else "work"
    gpu_util = _gpu_util_pct()
    last_row = ledger_rows[-1] if ledger_rows else None

    if model is None and last_row is None:
        return _no_data(CONFIG_PATH, {"model": None, "mode": mode, "gpu_util_pct": gpu_util, "last_row": None})

    if last_row is None:
        verdict, say = "amber", "no loop fire recorded yet"
    elif last_row.get("status") == "ok":
        verdict, say = "green", f"last fire ok, {last_row.get('cards_added', 0)} card(s) added"
    elif last_row.get("status") == "yielded":
        verdict, say = "amber", f"last fire yielded: {last_row.get('reason', '')}"[:160]
    else:
        verdict, say = "red", f"last fire {last_row.get('status', 'error')}: {last_row.get('reason', '')}"[:160]

    ledger_src = _source_meta(LEDGER_PATH)
    return {
        "ok": True, "path": ledger_src["path"], "stamp_et": ledger_src["last_write"],
        "verdict": verdict, "say": say, "source": ledger_src,
        "model": model, "mode": mode, "gpu_util_pct": gpu_util, "last_row": last_row,
        "config_source": _source_meta(CONFIG_PATH),
    }


def _ledger_section() -> dict:
    if not LEDGER_PATH.exists():
        return _no_data(LEDGER_PATH, {"rows": []})
    rows, skipped = _tail_jsonl(LEDGER_PATH, LEDGER_TAIL_N)
    src = _source_meta(LEDGER_PATH)
    return {
        "ok": bool(rows), "path": src["path"], "stamp_et": src["last_write"],
        "verdict": "green" if rows else "amber",
        "say": (f"last {len(rows)} fire(s)" + (f", {skipped} malformed line(s) skipped" if skipped else "")),
        "source": src, "rows": rows, "skipped_lines": skipped,
    }


def build() -> dict:
    stamp_et = et_now().replace(microsecond=0).isoformat()
    ledger = _ledger_section()
    ideas = _ideas_section()
    brief = _brief_section()
    planner = _planner_section(ledger.get("rows", []))
    ok = any(s["ok"] for s in (ideas, brief, planner, ledger))
    return {
        "ok": ok, "stamp_et": stamp_et,
        "ideas": ideas, "brief": brief, "planner": planner, "ledger": ledger,
        "say": "station loop state" if ok else "NO DATA, looked for automation/state/station/*",
    }


def _cli() -> None:
    print(json.dumps(build(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _cli()
