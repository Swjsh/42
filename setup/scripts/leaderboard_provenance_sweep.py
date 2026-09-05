"""leaderboard_provenance_sweep.py -- I2 of GOAL-KITCHEN-INTEGRITY-2026-09-05.

Sweeps strategy/candidates/_LEADERBOARD.md: for every data row, resolves the linked
candidate file's provenance status (from analysis/kitchen-review/provenance-audit.json,
produced by kitchen_provenance_audit.py). If the row's ONLY evidence file is
PROVENANCE-MISSING or NO-ARTIFACT-CITED, the Status column is rewritten to
`UNSUPPORTED (provenance)`.

GUARDS (per goal OPERATING RULES + task prompt):
  * A row whose Status cell already contains KILLED / SHADOW-FILED / EXTEND /
    BLOCKED-ON-DATA is a row tonight's adjudication pass already rewrote -- NEVER
    touched, cell kept verbatim.
  * A row that doesn't parse into the expected 10-column shape (ranks 24/25 -- known
    malformed 8-column rows) is left alone, logged as skipped_malformed.
  * A row whose Candidate cell carries no `](....md)` link (no evidence file to check)
    is left alone, logged as skipped_no_link.
  * A row whose linked file isn't in the provenance corpus at all (never scored, e.g.
    NOT-A-VERDICT or simply absent from the scan) is left alone -- this sweep only acts
    on the two classes named in the goal, never guesses.
  * File is rewritten via targeted line substitution, preserving the original CRLF line
    endings and UTF-8 BOM -- every other byte in the file is untouched.

USAGE:
  python setup/scripts/leaderboard_provenance_sweep.py               # apply
  python setup/scripts/leaderboard_provenance_sweep.py --dry-run     # counts only, no write

OUTPUT:
  analysis/kitchen-review/leaderboard-provenance-sweep-2026-09-05.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEADERBOARD = REPO / "strategy" / "candidates" / "_LEADERBOARD.md"
PROVENANCE_JSON = REPO / "analysis" / "kitchen-review" / "provenance-audit.json"
SWEEP_JSON = REPO / "analysis" / "kitchen-review" / "leaderboard-provenance-sweep-2026-09-05.json"

_PROTECTED_TOKENS = ("KILLED", "SHADOW-FILED", "EXTEND", "BLOCKED-ON-DATA")
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+\.md)\)")
_UNSUPPORTED_CELL = "UNSUPPORTED (provenance)"


def _load_provenance_map() -> dict[str, str]:
    report = json.loads(PROVENANCE_JSON.read_text(encoding="utf-8"))
    return {row["path"]: row["status"] for row in report["rows"]}


def _split_row(line: str) -> list[str] | None:
    """Split a markdown table row on unescaped '|'. Returns the cell list (including the
    leading/trailing empty strings from a well-formed '| a | b |' row) or None if the line
    isn't a table row at all."""
    stripped = line.strip("\r\n")
    if not stripped.startswith("|"):
        return None
    if set(stripped.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
        return None  # separator row (all dashes/colons)
    return stripped.split("|")


def sweep(apply: bool = True) -> dict:
    prov_map = _load_provenance_map()
    raw = LEADERBOARD.read_text(encoding="utf-8-sig")
    lines = raw.splitlines(keepends=True)

    header_cols: int | None = None
    rows_report: list[dict] = []
    rewritten = 0

    for idx, line in enumerate(lines):
        cells = _split_row(line)
        if cells is None:
            continue
        if header_cols is None and "Rank" in line and "Candidate" in line:
            header_cols = len(cells)
            continue
        if header_cols is None:
            continue  # haven't seen the header yet -- not a data row we recognize
        # Skip the header separator / any subsequent header row repeated after a heading.
        if "Rank" in line and "Candidate" in line and "Status" in line:
            continue

        rank = cells[1].strip() if len(cells) > 1 else "?"

        if len(cells) != header_cols:
            rows_report.append({"line": idx, "rank": rank, "action": "skipped_malformed"})
            continue

        candidate_cell = cells[2]
        status_idx = header_cols - 3  # last real column is 'Filed', second-to-last is 'Status'
        status_cell = cells[status_idx]

        if any(tok in status_cell for tok in _PROTECTED_TOKENS):
            rows_report.append({"line": idx, "rank": rank, "action": "kept_protected"})
            continue

        m = _LINK_RE.search(candidate_cell)
        if not m:
            rows_report.append({"line": idx, "rank": rank, "action": "skipped_no_link"})
            continue

        cand_path = f"strategy/candidates/{m.group(1)}"
        prov_status = prov_map.get(cand_path)
        if prov_status is None:
            rows_report.append({
                "line": idx, "rank": rank, "candidate_file": cand_path,
                "action": "skipped_not_in_corpus",
            })
            continue

        if prov_status in ("PROVENANCE-MISSING", "NO-ARTIFACT-CITED"):
            if _UNSUPPORTED_CELL in status_cell:
                rows_report.append({
                    "line": idx, "rank": rank, "candidate_file": cand_path,
                    "provenance_status": prov_status, "action": "already_unsupported",
                })
                continue
            new_cells = list(cells)
            new_cells[status_idx] = f" {_UNSUPPORTED_CELL} -- was: {status_cell.strip()} "
            new_line_body = "|".join(new_cells)
            ending = line[len(line.rstrip("\r\n")):]
            if apply:
                lines[idx] = new_line_body + ending
            rewritten += 1
            rows_report.append({
                "line": idx, "rank": rank, "candidate_file": cand_path,
                "provenance_status": prov_status, "action": "rewritten_unsupported",
            })
        else:
            rows_report.append({
                "line": idx, "rank": rank, "candidate_file": cand_path,
                "provenance_status": prov_status, "action": "kept_ok_evidence",
            })

    if apply and rewritten:
        LEADERBOARD.write_text("".join(lines), encoding="utf-8-sig")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "apply" if apply else "dry-run",
        "rows_examined": len(rows_report),
        "rewritten_unsupported": rewritten,
        "action_counts": {},
        "rows": rows_report,
    }
    for r in rows_report:
        report["action_counts"][r["action"]] = report["action_counts"].get(r["action"], 0) + 1

    SWEEP_JSON.parent.mkdir(parents=True, exist_ok=True)
    SWEEP_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    report = sweep(apply=not args.dry_run)
    print(
        f"[leaderboard_provenance_sweep] mode={report['mode']} rows_examined={report['rows_examined']} "
        f"rewritten_unsupported={report['rewritten_unsupported']} action_counts={report['action_counts']} "
        f"-> {SWEEP_JSON.relative_to(REPO)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
