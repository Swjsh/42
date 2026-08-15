#!/usr/bin/env python
"""conviction_shadow_report.py -- the WEEKLY would_block distribution for conviction.

MEASUREMENT ONLY. Conviction is DISARMED: there is no SKIP_LOW_CONVICTION branch in the
engine, and this reporter has no write surface outside analysis/entry-quality/. Reading it
changes nothing; it exists so the ratchet's block rate is a standing artifact instead of
something a human re-derives (and re-derives differently) each week.

WHAT IT REPORTS
    would_block distribution, score histogram, per-component hit rate, degraded-component
    census, and the ESCALATING-FLOOR view (block rate by k, the entry index of the day) --
    because the gate is `floor + step*k`, so a block rate quoted without k is an average
    over a moving bar and means very little on its own.

WHY IT PARTITIONS ON A FIX BOUNDARY (the load-bearing design choice)
    `974ca235` (2026-08-14 19:15 ET, after Friday's close) fixed a TRANSPOSED KEY that had
    degraded C4 range_extreme on 102/102 rows since birth, and threaded C5 structure for the
    first time. Every conviction row written BEFORE that commit therefore scored on a
    strictly smaller component set and blocked 102/102 by construction.

    Pooling those with post-fix rows would report something like "conviction blocks ~95% of
    entries" -- a number that is an artifact of two dead components, not a property of the
    ratchet. That is the L248 class ("quote the refinement cell, not |BASELINE") and it would
    most likely get the component killed on false evidence. So PRE-FIX rows are counted,
    labelled, and reported SEPARATELY -- never merged, never silently dropped.

    The boundary is a TIMESTAMP, not a row count, so it stays correct as rows accumulate.

STATUS AT BIRTH (2026-08-15, verified not assumed): 102 rows on disk, ALL pre-fix
(08-13 x56, 08-14 x46), last row 2026-08-14T13:35 -- 5h41m before the fix landed. The
post-fix population is EMPTY until the next session with an ENTER verdict (Monday
2026-08-17 at the earliest). The report says so in those words rather than rendering an
empty table as if it were a finding.

Run:
    python setup/scripts/conviction_shadow_report.py            # human table + JSON
    python setup/scripts/conviction_shadow_report.py --json     # JSON only

Writes: analysis/entry-quality/conviction-shadow-report.json
Guard:  backtest/tests/test_conviction_shadow_report.py
Cost:   $0 -- pure local JSONL reads, no network, no LLM, no broker.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
OUT_DIR = REPO / "analysis" / "entry-quality"
OUT_PATH = OUT_DIR / "conviction-shadow-report.json"

# `974ca235 fix(conviction): C4 read a TRANSPOSED key and degraded 102/102 -- range_extreme
# + C5 structure now actually score`, committed 2026-08-14 17:15:22 -0600 = 19:15:22 ET.
# Rows at or after this instant scored C4/C5 for real; rows before it could not.
FIX_BOUNDARY_ET = "2026-08-14T19:15:22"
FIX_COMMIT = "974ca235"

COMPONENT_KEYS = (
    "named_level", "multi_day_memory", "fresh_test", "range_extreme",
    "structure_agreement", "elite_trigger", "zone_stack",
)


def ledger_paths() -> list[Path]:
    """Every decision ledger that can carry a conviction row."""
    paths = [STATE / "core-decisions.jsonl"]
    paths += [Path(p) for p in sorted(glob.glob(str(STATE / "fleet" / "*" / "decisions.jsonl")))]
    return [p for p in paths if p.exists()]


def load_rows() -> list[dict]:
    """All conviction shadow rows on disk, newest-last. Never raises."""
    out: list[dict] = []
    for path in ledger_paths():
        arm = ("core" if path.name == "core-decisions.jsonl"
               else path.parent.name)
        try:
            handle = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with handle:
            for line in handle:
                if "conviction" not in line:
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                cv = row.get("conviction")
                if not isinstance(cv, dict):
                    continue
                ts = row.get("ts_et")
                if not isinstance(ts, str) or len(ts) < 10:
                    continue
                out.append({
                    "arm": arm, "ts_et": ts, "date": ts[:10],
                    "account": row.get("account"), "side": row.get("side"),
                    "conviction": cv,
                })
    out.sort(key=lambda r: r["ts_et"])
    return out


def is_post_fix(row: dict) -> bool:
    """Lexicographic ISO compare -- both sides are naive ET strings from the same producer."""
    return row["ts_et"] >= FIX_BOUNDARY_ET


def summarise(rows: list[dict]) -> dict:
    """would_block distribution + the shape behind it, for ONE population."""
    total = len(rows)
    if not total:
        return {"n": 0}
    blocked = sum(1 for r in rows if r["conviction"].get("would_block"))
    errored = sum(1 for r in rows if r["conviction"].get("error"))
    scores = Counter()
    comp_hits = Counter()
    degraded = Counter()
    by_k = defaultdict(lambda: {"n": 0, "blocked": 0})
    by_date = defaultdict(lambda: {"n": 0, "blocked": 0})
    floors = Counter()
    for r in rows:
        cv = r["conviction"]
        if cv.get("error"):
            continue
        score = cv.get("total")
        if score is None:
            score = cv.get("score")
        scores[score] += 1
        floors[cv.get("floor_effective")] += 1
        for key, val in (cv.get("components") or {}).items():
            if val:
                comp_hits[key] += 1
        for name in (cv.get("degraded_components") or []):
            degraded[name] += 1
        k_bucket = by_k[cv.get("k")]
        k_bucket["n"] += 1
        k_bucket["blocked"] += 1 if cv.get("would_block") else 0
        d_bucket = by_date[r["date"]]
        d_bucket["n"] += 1
        d_bucket["blocked"] += 1 if cv.get("would_block") else 0
    scored = total - errored
    return {
        "n": total,
        "n_scored": scored,
        "n_errored": errored,
        "would_block": blocked,
        "would_allow": total - blocked,
        "block_rate_pct": round(100.0 * blocked / total, 1) if total else None,
        "dates": sorted({r["date"] for r in rows}),
        "arms": sorted({r["arm"] for r in rows}),
        "score_histogram": {str(k): v for k, v in sorted(scores.items(),
                                                         key=lambda kv: (kv[0] is None, kv[0]))},
        "floor_effective_histogram": {str(k): v for k, v in sorted(
            floors.items(), key=lambda kv: (kv[0] is None, kv[0]))},
        "component_hit_rate_pct": {
            key: round(100.0 * comp_hits.get(key, 0) / scored, 1) if scored else None
            for key in COMPONENT_KEYS
        },
        "degraded_components": dict(degraded.most_common()),
        "by_k": {str(k): dict(v, block_rate_pct=round(100.0 * v["blocked"] / v["n"], 1))
                 for k, v in sorted(by_k.items(), key=lambda kv: (kv[0] is None, kv[0]))},
        "by_date": {k: dict(v, block_rate_pct=round(100.0 * v["blocked"] / v["n"], 1))
                    for k, v in sorted(by_date.items())},
    }


def _recent_sessions(rows: list[dict], n_sessions: int = 5) -> list[dict]:
    """Rows from the most recent `n_sessions` SESSIONS present in the data.

    Session-scoped, not calendar-scoped, deliberately: a calendar 7-day window silently
    shrinks over a holiday week and would report a smaller population as if the block rate
    had moved. The weekly read must be a fixed number of sessions.
    """
    dates = sorted({r["date"] for r in rows})[-n_sessions:]
    return [r for r in rows if r["date"] in dates]


def build_report(rows: list[dict], generated_at_et: str) -> dict:
    pre = [r for r in rows if not is_post_fix(r)]
    post = [r for r in rows if is_post_fix(r)]
    report = {
        "_meta": {
            "generated_at_et": generated_at_et,
            "builder": "setup/scripts/conviction_shadow_report.py",
            "armed": False,
            # ASCII deliberately: this string is printed to a cp1252 console AND written to
            # JSON. A non-ASCII marker here crashes the console render on Windows.
            "shadow_only": ("[DISARMED] MEASUREMENT ONLY -- no SKIP_LOW_CONVICTION branch "
                            "exists; no row here refused an entry."),
            "fix_boundary_et": FIX_BOUNDARY_ET,
            "fix_commit": FIX_COMMIT,
            "partition_rationale": (
                "Rows before the boundary scored with C4 range_extreme and C5 structure "
                "DEGRADED (transposed key), so they blocked by construction. Pooling them "
                "with post-fix rows would report the artifact, not the ratchet (L248)."),
            "ledgers_read": [str(p.relative_to(REPO)).replace("\\", "/")
                             for p in ledger_paths()],
        },
        "post_fix": summarise(post),
        "weekly_last_5_sessions": summarise(_recent_sessions(post)),
        "pre_fix_DO_NOT_POOL": summarise(pre),
    }
    if not post:
        report["_meta"]["status"] = (
            "POST-FIX POPULATION IS EMPTY. The C4/C5 fix landed after the last session's "
            "final tick, so no conviction row has yet been scored with those components "
            "live. This is not a finding about the ratchet -- there is no evidence yet. "
            "First rows arrive on the next session with an ENTER verdict.")
    else:
        report["_meta"]["status"] = (
            f"{len(post)} post-fix row(s) across {len(report['post_fix']['dates'])} "
            f"session(s). Block rate {report['post_fix']['block_rate_pct']}%.")
    return report


def render(report: dict) -> str:
    meta = report["_meta"]
    lines = [
        "=" * 78,
        "CONVICTION SHADOW -- would_block distribution   [DISARMED / MEASUREMENT ONLY]",
        "=" * 78,
        meta["shadow_only"],
        f"generated {meta['generated_at_et']} ET",
        f"fix boundary: {meta['fix_boundary_et']}  ({meta['fix_commit']})",
        "",
        "STATUS: " + meta["status"],
        "",
    ]
    for label, key in (("POST-FIX (the live population, all sessions)", "post_fix"),
                       ("WEEKLY (last 5 sessions, post-fix only)", "weekly_last_5_sessions"),
                       ("PRE-FIX (artifact -- DO NOT POOL)", "pre_fix_DO_NOT_POOL")):
        sec = report[key]
        lines.append("-" * 78)
        lines.append(label)
        if not sec.get("n"):
            lines.append("  (no rows)")
            lines.append("")
            continue
        lines.append(f"  n={sec['n']}  would_block={sec['would_block']} "
                     f"({sec['block_rate_pct']}%)  allow={sec['would_allow']}"
                     + (f"  errored={sec['n_errored']}" if sec.get("n_errored") else ""))
        lines.append(f"  sessions: {', '.join(sec['dates'])}")
        lines.append(f"  score histogram: {sec['score_histogram']}")
        hits = {k: v for k, v in sec["component_hit_rate_pct"].items() if v}
        lines.append(f"  components scoring >0: {hits or 'NONE'}")
        if sec["degraded_components"]:
            lines.append(f"  DEGRADED: {sec['degraded_components']}")
        if sec["by_k"]:
            lines.append(f"  block rate by k (escalating floor): "
                         + ", ".join(f"k={k}:{v['block_rate_pct']}%({v['n']})"
                                     for k, v in sec["by_k"].items()))
        lines.append("")
    lines.append("=" * 78)
    return "\n".join(lines)


def _et_now_str() -> str:
    try:
        sys.path.insert(0, str(REPO / "setup" / "scripts"))
        from et_clock import et_now  # noqa: PLC0415
        return et_now().strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:  # noqa: BLE001 -- a reporter must not die on a clock import
        return "unknown"


def run(write: bool = True) -> dict:
    rows = load_rows()
    report = build_report(rows, _et_now_str())
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        tmp = OUT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(report, indent=1), encoding="utf-8")
        os.replace(tmp, OUT_PATH)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true", help="print JSON instead of the table")
    ap.add_argument("--no-write", action="store_true", help="compute, write nothing")
    args = ap.parse_args()
    report = run(write=not args.no_write)
    print(json.dumps(report, indent=1) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
