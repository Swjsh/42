"""WP-3: nightly blocker histogram -- "why didn't the lane trade today?" in one read.

Yesterday's 178 HOLDs were opaque: scores were logged, blockers were not, and diagnosing them
took manual probing. That is how a dead lane stays dead. This turns the shadow ledger into a
ranked answer.

Reads only. Writes analysis/multi-lane/blocker-histogram-{date}.json.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "automation" / "state" / "multi" / "shadow-ledger.jsonl"
OUT_DIR = REPO / "analysis" / "multi-lane"
ET = ZoneInfo("America/New_York")


def build(date_str: str) -> dict:
    if not LEDGER.exists():
        raise SystemExit(f"no ledger at {LEDGER}")
    rows = []
    for line in LEDGER.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(r.get("ts_et", "")).startswith(date_str):
            rows.append(r)

    scored = [r for r in rows if r.get("bear_blockers") is not None]
    bear, bull, gates = collections.Counter(), collections.Counter(), collections.Counter()
    for r in rows:
        if r.get("gate"):
            gates[r["gate"]] += 1
    for r in scored:
        for b in r.get("bear_blockers") or []:
            bear[b] += 1
        for b in r.get("bull_blockers") or []:
            bull[b] += 1

    n = len(scored)
    def pct(c):
        return [{"blocker": k, "count": v, "pct_of_scored": round(100.0 * v / n, 1) if n else 0.0}
                for k, v in c.most_common()]

    # TOP BLOCKER is reported PER SIDE. A combined count over a one-side denominator can
    # exceed 100% (it did: F10 appeared on both sides and rendered "160% of scored"), and a
    # percentage above 100 is the kind of nonsense number that quietly destroys trust in a
    # surface. Each side has its own denominator of `n` scored rows.
    top = None
    top_bear = ({"blocker": bear.most_common(1)[0][0], "count": bear.most_common(1)[0][1],
                 "pct_of_scored": round(100.0 * bear.most_common(1)[0][1] / n, 1)}
                if bear and n else None)
    top_bull = ({"blocker": bull.most_common(1)[0][0], "count": bull.most_common(1)[0][1],
                 "pct_of_scored": round(100.0 * bull.most_common(1)[0][1] / n, 1)}
                if bull and n else None)
    # The binding constraint overall = whichever side's top blocker binds harder.
    for cand in (top_bear, top_bull):
        if cand and (top is None or cand["pct_of_scored"] > top["pct_of_scored"]):
            top = dict(cand)
    if top is not None:
        top["side"] = "bear" if top_bear and top["blocker"] == top_bear["blocker"] and             top["count"] == top_bear["count"] else "bull"

    return {
        "date": date_str,
        "rows_total": len(rows),
        "rows_scored": n,
        "would_place": sum(1 for r in rows if r.get("decision") == "WOULD_PLACE"),
        "top_blocker": top,
        "top_blocker_bear": top_bear,
        "top_blocker_bull": top_bull,
        "bear_blockers": pct(bear),
        "bull_blockers": pct(bull),
        "gate_counts": dict(gates.most_common()),
        "_reading": (
            "A blocker at ~100% of scored rows is the binding constraint. F5:ribbon_stack at "
            "100% on ONE side is usually correct (the ribbon can only stack one way). "
            "F10:level_tied_trigger at 100% with EMPTY triggers means no level interaction "
            "occurred -- on a closed market that is a flat-bar artifact, during RTH it is a "
            "real signal-design finding."
        ),
    }


def main(argv=None) -> int:
    import datetime as dt
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.datetime.now(ET).date().isoformat())
    a = ap.parse_args(argv)
    h = build(a.date)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"blocker-histogram-{a.date}.json").write_text(
        json.dumps(h, indent=2), encoding="utf-8")

    print(f"=== MULTI-LANE BLOCKERS {a.date} ===")
    print(f"  rows {h['rows_total']} | scored {h['rows_scored']} | WOULD_PLACE {h['would_place']}")
    if h["top_blocker"]:
        t = h["top_blocker"]
        print(f"  TOP BLOCKER: {t['blocker']} [{t.get('side')}]  "
              f"{t['count']} ({t['pct_of_scored']}% of scored)")
    for side in ("bear_blockers", "bull_blockers"):
        if h[side]:
            print(f"  {side}:")
            for b in h[side]:
                print(f"     {b['blocker']:<30} {b['count']:>4}  {b['pct_of_scored']}%")
    if h["rows_scored"] == 0:
        print("  NOTE: zero scored rows -- the funnel or bar fetch stopped everything before "
              "scoring; read gate_counts.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
