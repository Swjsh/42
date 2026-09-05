"""launch_rate.py -- launches-per-hour instrument (GOAL-SILENT-RIG-2026-09-05 L3).

Reads the two hidden-launcher logs (run_ps1_hidden.py and run_cmd_hidden.py write
one "launching: ..." line per process spawn) for a given date, buckets launches by
local hour, extracts a per-script tally, and writes
automation/state/launch-rate.json:

    {
      "date": "YYYY-MM-DD",
      "per_hour": {"00": 41, "01": 37, ...},
      "top_scripts": [["run-engine-health.ps1", 96], ...],
      "market_closed_hours_over_60": ["00", "01", ...]
    }

"Market-closed" hour = any local hour NOT in 07-14 local (box runs Mountain time;
ET = local+2h, so 07-14 local covers the 09:00-16:00 ET session with slack). This
mirrors the box's own clock, not a re-derivation of the ET session -- see
CLAUDE.md "TIME = et_clock, NEVER Bash TZ" for why we do not try to convert here;
the log timestamps are already local (box) time, matching Task Scheduler's own
frame, so no conversion is needed or attempted.

When any market-closed hour exceeds LAUNCHES_PER_HOUR_ALERT (60), upserts ONE
Known-broken line through the shared status_known_broken.upsert() helper
(marker "LAUNCH-RATE:") -- never appends a duplicate, never edits STATUS.md by
hand. A green (all-clear) run clears the marker.

CLI:
    python setup/scripts/launch_rate.py [--date YYYY-MM-DD] [--repo-root PATH]

Prints one summary line to stdout, e.g.:
    launch_rate: date=2026-09-05 total=3812 peak_hour=11(512) market_closed_over_60=[...]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]

LAUNCHES_PER_HOUR_ALERT = 60
# Local (box) hours treated as "market open, launches are expected to be heavy".
# Box is Mountain time; ET session 09:20-16:10 ET == 07:20-14:10 local. Round out
# to whole hours so a launch at 07:0x or 14:5x local isn't misflagged.
MARKET_OPEN_LOCAL_HOURS = set(range(7, 15))  # 07..14 inclusive

TS_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}) (\d{2}):\d{2}:\d{2}\]\s+launching:\s+(.*)$")

# Pull a script identifier out of the free-text tail of a "launching:" line.
# run_ps1_hidden.py lines look like: "run-engine-health.ps1 args=[]"
# run_cmd_hidden.py lines look like:
#   "C:\...\pythonw.exe C:\...\setup\scripts\auto_commit_candidates.py  [pid=1234]"
PS1_NAME_RE = re.compile(r"^([\w.\-]+\.ps1)\b")
PY_NAME_RE = re.compile(r"([\w.\-]+\.py)\b")


def _extract_script(tail: str) -> str:
    m = PS1_NAME_RE.search(tail)
    if m:
        return m.group(1)
    # cmd log: take the LAST .py token (the target script, not run_cmd_hidden.py
    # itself if present as an interpreter wrapper arg).
    py_matches = PY_NAME_RE.findall(tail)
    if py_matches:
        # Prefer the last non-wrapper match; run_cmd_hidden.py / run_ps1_hidden.py
        # are wrapper scripts, skip them if a later real target exists.
        wrappers = {"run_cmd_hidden.py", "run_ps1_hidden.py"}
        real = [p for p in py_matches if p not in wrappers]
        return real[-1] if real else py_matches[-1]
    # Fallback: first whitespace-delimited token.
    return tail.split()[0] if tail.split() else "UNKNOWN"


def parse_log(path: Path, date: str, per_hour: Counter, script_counts: Counter) -> int:
    """Parse one hidden-launcher log, accumulate counts for `date`. Returns lines matched."""
    if not path.exists():
        return 0
    matched = 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            m = TS_RE.match(raw_line.rstrip("\n"))
            if not m:
                continue
            line_date, hour, tail = m.group(1), m.group(2), m.group(3)
            if line_date != date:
                continue
            matched += 1
            per_hour[hour] += 1
            script_counts[_extract_script(tail)] += 1
    return matched


def compute(date: str, repo_root: Path = REPO_ROOT) -> dict:
    log_dir = repo_root / "automation" / "state" / "logs"
    ps1_log = log_dir / f"run-ps1-hidden-{date}.log"
    cmd_log = log_dir / f"run-cmd-hidden-{date}.log"

    per_hour: Counter = Counter()
    script_counts: Counter = Counter()
    matched = 0
    matched += parse_log(ps1_log, date, per_hour, script_counts)
    matched += parse_log(cmd_log, date, per_hour, script_counts)

    per_hour_dict = {f"{h:02d}": per_hour.get(f"{h:02d}", 0) for h in range(24)}
    market_closed_over_60 = [
        h for h in sorted(per_hour_dict)
        if int(h) not in MARKET_OPEN_LOCAL_HOURS and per_hour_dict[h] > LAUNCHES_PER_HOUR_ALERT
    ]

    return {
        "date": date,
        "per_hour": per_hour_dict,
        "top_scripts": [[name, n] for name, n in script_counts.most_common(25)],
        "market_closed_hours_over_60": market_closed_over_60,
        "total_launches": matched,
    }


def write_output(result: dict, repo_root: Path = REPO_ROOT) -> Path:
    out_path = repo_root / "automation" / "state" / "launch-rate.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return out_path


def maybe_flag_known_broken(
    result: dict, repo_root: Path = REPO_ROOT, status_path: Optional[Path] = None
) -> Optional[bool]:
    """Upsert (or clear) the LAUNCH-RATE: Known-broken marker via the shared helper.

    `status_path` lets callers (tests) redirect the write away from the live
    STATUS.md -- upsert()'s own `status_path` keyword argument is resolved at
    call time here rather than relying on the module-level default, which is
    bound once at status_known_broken import time and would NOT pick up a
    monkeypatched STATUS_PATH.

    Fail-open: if status_known_broken can't be imported (e.g. run outside the
    repo), returns None and does not raise.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import status_known_broken as skb  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"[launch_rate] status_known_broken unavailable: {exc}", file=sys.stderr)
        return None

    kwargs = {} if status_path is None else {"status_path": status_path}

    bad_hours = result["market_closed_hours_over_60"]
    if not bad_hours:
        return skb.upsert("LAUNCH-RATE:", None, **kwargs)

    worst = max(bad_hours, key=lambda h: result["per_hour"][h])
    line = (
        f"- [{result['date']} local] LAUNCH-RATE: {len(bad_hours)} market-closed hour(s) "
        f"exceeded {LAUNCHES_PER_HOUR_ALERT}/hr on {result['date']} (worst={worst}:00 "
        f"{result['per_hour'][worst]} launches); top scripts: "
        + ", ".join(f"{name}x{n}" for name, n in result["top_scripts"][:5])
    )
    return skb.upsert("LAUNCH-RATE:", line, **kwargs)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today per et_clock's date)")
    ap.add_argument("--repo-root", default=str(REPO_ROOT))
    ap.add_argument("--no-flag", action="store_true", help="skip the Known-broken upsert (for tests)")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root)
    date = args.date
    if date is None:
        # Local calendar date matching the log filenames' convention (box-local).
        import datetime
        date = datetime.datetime.now().strftime("%Y-%m-%d")

    result = compute(date, repo_root=repo_root)
    out_path = write_output(result, repo_root=repo_root)

    if not args.no_flag:
        maybe_flag_known_broken(result, repo_root=repo_root)  # writes live STATUS.md by default

    per_hour = result["per_hour"]
    peak_hour = max(per_hour, key=lambda h: per_hour[h]) if per_hour else "--"
    print(
        f"launch_rate: date={date} total={result['total_launches']} "
        f"peak_hour={peak_hour}({per_hour.get(peak_hour, 0)}) "
        f"market_closed_over_60={result['market_closed_hours_over_60']} "
        f"wrote={out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
