"""gamma_cockpit_costpulse.py -- 14-day cost-pulse series for the Cost pulse KPI
panel (WS-D, 2026-09-04, COCKPIT-DESIGN-SPEC-V2-GLOW-2026-09-04.md section 4/8b).

Reads automation/state/conductor-outcomes.jsonl (one JSON object per conductor
fire: fired_at ISO timestamp, cost_usd, items_drained, regressions, ...) and
buckets cost_usd by the ET CALENDAR DAY of fired_at, for the trailing `days`
ET days ending today, zero-filled for any day with no fires.

Why ET, not local time or naive-UTC-as-if-ET: this box runs Mountain time and
every other cockpit surface reports on the ET trading calendar (CLAUDE.md
"TIME = et_clock, NEVER Bash TZ"). fired_at in the ledger carries an explicit
UTC offset (+00:00) -- converted via et_clock.ET_TZ, never assumed to already
be ET.

READ-ONLY. Fail-open: a missing file, an empty file, or a file that cannot be
read at all returns ok:False with a NO-DATA `say` naming the path it looked
for -- never raises, never fabricates a data point. Any single malformed line
(bad JSON, unparseable fired_at, unusable cost_usd) is skipped and counted in
skipped_lines rather than dropping the whole build.

CONTRACT (fixed -- gamma_cockpit_costpulse_js.py renders directly off this):
    build(path=None, days=14) -> {
        ok, path, stamp_et,
        days: [{day, cost_usd, fires, drained, regressions}, ...],  # oldest -> newest
        total_usd, last: {day, cost_usd, fires} | None,
        source: {path, age_h, last_write},
        say, skipped_lines,
    }
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_PATH = REPO / "automation" / "state" / "conductor-outcomes.jsonl"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import et_now, ET_TZ  # noqa: E402 -- pure-stdlib DST-aware ET


def _rel(p: Path) -> str:
    """Posix repo-relative path; falls back to a posix-ified absolute string
    for a path outside REPO (a tmp_path in tests)."""
    try:
        return p.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return str(p).replace("\\", "/")


def _et_day_of(fired_at) -> str | None:
    """ET calendar-day 'YYYY-MM-DD' of an ISO fired_at timestamp. A naive
    timestamp (no offset) is treated as UTC -- the convention every sampled
    row in this ledger already uses; never guessed as local/ET."""
    if not fired_at:
        return None
    s = str(fired_at).strip()
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    try:
        return d.astimezone(ET_TZ).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return None


def _no_data(rel: str, stamp_et: str, skipped: int = 0) -> dict:
    return {
        "ok": False,
        "path": rel,
        "stamp_et": stamp_et,
        "days": [],
        "total_usd": 0.0,
        "last": None,
        "source": {"path": rel, "age_h": None, "last_write": None},
        "say": f"NO DATA, looked for {rel}",
        "skipped_lines": skipped,
    }


def build(path=None, days: int = 14) -> dict:
    p = Path(path) if path is not None else DEFAULT_PATH
    rel = _rel(p)
    stamp_et = et_now().replace(microsecond=0).isoformat()

    if not p.exists():
        return _no_data(rel, stamp_et)

    try:
        raw_text = p.read_text(encoding="utf-8", errors="strict")
    except OSError:
        return _no_data(rel, stamp_et)

    today_et = et_now().strftime("%Y-%m-%d")
    today_dt = datetime.strptime(today_et, "%Y-%m-%d")
    window = [(today_dt - timedelta(days=i)).strftime("%Y-%m-%d")
              for i in range(days - 1, -1, -1)]
    window_set = set(window)
    buckets = {d: {"day": d, "cost_usd": 0.0, "fires": 0, "drained": 0,
                   "regressions": 0} for d in window}

    skipped = 0
    saw_any_line = False
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        saw_any_line = True
        try:
            row = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        if not isinstance(row, dict):
            skipped += 1
            continue
        day = _et_day_of(row.get("fired_at"))
        if day is None:
            skipped += 1
            continue
        cost_raw = row.get("cost_usd")
        try:
            cost = float(cost_raw) if cost_raw is not None else 0.0
        except (TypeError, ValueError):
            skipped += 1
            continue
        if day not in window_set:
            continue  # outside the requested window -- older data, not corrupt
        b = buckets[day]
        b["cost_usd"] = round(b["cost_usd"] + cost, 6)
        b["fires"] += 1
        drained = row.get("items_drained")
        if isinstance(drained, (int, float)) and not isinstance(drained, bool):
            b["drained"] += int(drained)
        regressions = row.get("regressions")
        if isinstance(regressions, (int, float)) and not isinstance(regressions, bool):
            b["regressions"] += int(regressions)

    if not saw_any_line:
        return _no_data(rel, stamp_et, skipped)

    days_list = [buckets[d] for d in window]
    for b in days_list:
        b["cost_usd"] = round(b["cost_usd"], 2)
    total_usd = round(sum(b["cost_usd"] for b in days_list), 2)

    last = days_list[-1] if days_list else None
    last_summary = ({"day": last["day"], "cost_usd": last["cost_usd"],
                      "fires": last["fires"]} if last else None)

    try:
        mtime = p.stat().st_mtime
        age_h = (datetime.now(timezone.utc).timestamp() - mtime) / 3600.0
        last_write = et_now(
            now_utc=datetime.fromtimestamp(mtime, tz=timezone.utc)
        ).replace(microsecond=0).isoformat()
    except OSError:
        age_h = None
        last_write = None

    return {
        "ok": True,
        "path": rel,
        "stamp_et": stamp_et,
        "days": days_list,
        "total_usd": total_usd,
        "last": last_summary,
        "source": {
            "path": rel,
            "age_h": round(age_h, 3) if age_h is not None else None,
            "last_write": last_write,
        },
        "say": (f"{len(days_list)}d window, ${total_usd:.2f} total"
                + (f", last fire {last_summary['day']}" if last_summary else "")),
        "skipped_lines": skipped,
    }


def _cli() -> None:
    print(json.dumps(build(), indent=2))


if __name__ == "__main__":
    _cli()
