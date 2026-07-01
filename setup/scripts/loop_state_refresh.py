"""loop_state_refresh.py -- derive loop-state.json tick truth from core-decisions.jsonl.

THE LIE THIS FIXES (2026-07-01): loop-state.json is a legacy LLM-heartbeat artifact;
the deterministic engine (heartbeat_core) never increments it, so it read
ticks_today=0 while core-decisions.jsonl carried 766 real decision rows. Readers
(dashboard lib/state.ts, gamma-companion lib/state.js, the EOD prompt inlines)
then repeated "0 ticks" as truth.

Fix (smallest safe change): a standalone refresher that re-derives the tick fields
from the ledger and patches ONLY those keys in place -- everything else in the file
(ribbon, vix_cache, spy, mode) is left untouched for its existing writers. Invoked
from self_check.run() every ~30 min (fail-open) + available as a CLI.

  ticks_today            = engine cycles today: distinct minute-level ts_et
                           (a cycle writes one row per account in the same minute)
  ticks_today_source     = "core-decisions.jsonl" (marks the field as derived)
  ticks_refreshed_at_et  = when this refresher last ran
  last_decision_ts_et    = max ts_et seen today

Run:  backtest/.venv/Scripts/python.exe setup/scripts/loop_state_refresh.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
sys.path.insert(0, str(REPO / "setup" / "scripts"))

try:
    from et_clock import et_now
except Exception:  # noqa: BLE001
    def et_now() -> dt.datetime:  # fail-open (rig is on Mountain; never Bash TZ)
        return dt.datetime.utcnow() - dt.timedelta(hours=4)


def derive_ticks(day: str, core_path: Path) -> tuple[int, str | None]:
    """(engine cycles today, max ts_et). A cycle writes one row per account within
    the same minute at slightly different seconds, so cycles = distinct minute-level
    timestamps (ts_et[:16]), not distinct raw timestamps. Fail-open -> (0, None)."""
    minutes: set[str] = set()
    last_ts: str | None = None
    try:
        for ln in core_path.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if not ln or day not in ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            ts = str(o.get("ts_et", ""))
            if ts.startswith(day):
                minutes.add(ts[:16])  # YYYY-MM-DDTHH:MM
                if last_ts is None or ts > last_ts:
                    last_ts = ts
    except OSError:
        pass
    return len(minutes), last_ts


def refresh(now: dt.datetime | None = None, *, state_dir: Path | None = None,
            core_path: Path | None = None) -> dict:
    """Patch loop-state.json tick fields from the ledger. Returns a summary dict.
    Never raises (fail-open into self_check / the scheduler)."""
    now = now or et_now()
    state_dir = state_dir or STATE
    core_path = core_path or (state_dir / "core-decisions.jsonl")
    ls_path = state_dir / "loop-state.json"
    day = now.strftime("%Y-%m-%d")
    summary = {"day": day, "changed": False, "ticks_today": None, "note": ""}
    try:
        try:
            ls = json.loads(ls_path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            summary["note"] = "loop-state.json missing -- nothing to refresh"
            return summary
        except Exception as exc:  # noqa: BLE001
            summary["note"] = f"loop-state.json unreadable ({type(exc).__name__}) -- left alone"
            return summary
        if not isinstance(ls, dict):
            summary["note"] = "loop-state.json not a dict -- left alone"
            return summary
        ticks, last_ts = derive_ticks(day, core_path)
        summary["ticks_today"] = ticks
        if ls.get("ticks_today") == ticks and ls.get("ticks_today_source") == "core-decisions.jsonl":
            summary["note"] = "already current"
            return summary
        ls["ticks_today"] = ticks
        ls["ticks_today_source"] = "core-decisions.jsonl"
        ls["ticks_refreshed_at_et"] = now.strftime("%Y-%m-%dT%H:%M:%S")
        if last_ts:
            ls["last_decision_ts_et"] = last_ts
        ls_path.write_text(json.dumps(ls, indent=2), encoding="utf-8")
        summary["changed"] = True
        summary["note"] = f"ticks_today -> {ticks} (from {core_path.name})"
        return summary
    except Exception as exc:  # noqa: BLE001 -- fail-open, never break the caller
        summary["note"] = f"refresh failed: {type(exc).__name__}: {exc}"
        return summary


if __name__ == "__main__":
    s = refresh()
    print(f"[loop-state-refresh] {s['day']} ticks_today={s['ticks_today']} "
          f"changed={s['changed']} -- {s['note']}")
    raise SystemExit(0)
