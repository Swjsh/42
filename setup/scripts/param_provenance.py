"""param_provenance.py -- glanceable provenance surface for params.json.

Retires the recurring J question "why are we running arbitrary/stale hardcoded params?"
(OP-33(e): a repeated question is a missing INSTRUMENT). For every LIVE param it answers:
is this value VALIDATED (has a scorecard), DOCUMENTED (has a rationale but no scorecard),
or BARE (no provenance at all -> the actual stale-hardcode risk)?

$0, read-only. Emits automation/state/param-provenance.json + a stdout table.
Run: python setup/scripts/param_provenance.py [--bare]  (--bare lists only unaccounted params)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PARAMS = ROOT / "automation" / "state" / "params.json"
OUT = ROOT / "automation" / "state" / "param-provenance.json"
SCORE_RE = re.compile(r"analysis/recommendations/[\w./-]+|scorecard", re.I)


def main() -> int:
    d = json.loads(PARAMS.read_text(encoding="utf-8"))
    docs = {k: str(v) for k, v in d.items() if k.startswith("_")}
    doc_blob = "\n".join(docs.values())
    real = [k for k in d if not k.startswith("_")]

    rows = []
    for k in sorted(real):
        v = d[k]
        # docs that name this key (e.g. _premium_stop_pct_doc, or any _doc mentioning it)
        naming = [dk for dk in docs if k in dk or re.search(rf"\b{re.escape(k)}\b", docs[dk])]
        has_scorecard = any(SCORE_RE.search(docs[dk]) for dk in naming)
        if has_scorecard:
            status = "VALIDATED"
        elif naming:
            status = "DOCUMENTED"
        else:
            status = "BARE"
        scorecard = ""
        for dk in naming:
            m = re.search(r"analysis/recommendations/[\w./-]+", docs[dk])
            if m:
                scorecard = m.group(0)
                break
        rows.append({"param": k, "value": v if not isinstance(v, (dict, list)) else "(complex)",
                     "status": status, "scorecard": scorecard})

    counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("VALIDATED", "DOCUMENTED", "BARE")}
    bare = [r for r in rows if r["status"] == "BARE"]
    OUT.write_text(json.dumps({"n_params": len(real), "counts": counts, "rows": rows}, indent=1), encoding="utf-8")

    only_bare = "--bare" in sys.argv
    print(f"=== params.json provenance ({len(real)} live params) ===")
    print(f"  VALIDATED (has scorecard): {counts['VALIDATED']}")
    print(f"  DOCUMENTED (rationale, no scorecard): {counts['DOCUMENTED']}")
    print(f"  BARE (no provenance -> review): {counts['BARE']}")
    print()
    print(f"  {'BARE / unaccounted params (the real stale-hardcode risk):':}")
    for r in bare:
        print(f"    {r['param']:42s} = {r['value']}")
    if not only_bare:
        print(f"\n  -> full table: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
