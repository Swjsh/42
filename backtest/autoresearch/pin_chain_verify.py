"""Pin chain verify — verify rule_version pin matches across params.json + heartbeat.md + premarket.md.

Per CLAUDE.md OP-4 (no code drift) + rule 9 (no mid-session rule changes), the
canonical rule_version in `automation/state/params.json` MUST match the embedded
constants in `automation/prompts/heartbeat.md` (RULE_VERSION) and
`automation/prompts/premarket.md` (RULE_VERSION_EXPECTED).

If they drift:
  - Premarket Step 1a kill-switches the day (correct behavior)
  - Heartbeat may run on stale doctrine
  - Backtest engine may diverge from live engine

This skill checks all three. AUDIT, DIAGNOSE, REPORT proposed-fix-diff. NO auto-edit
(rule 9 — production prompt edits require J authorization).

USAGE:
    python -m autoresearch.pin_chain_verify
    python -m autoresearch.pin_chain_verify --quiet

OUTPUTS:
    stdout: per-source rule_version + verdict
    automation/state/pin-chain-verify-latest.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PARAMS_PATH      = ROOT / "automation" / "state" / "params.json"
HEARTBEAT_PATH   = ROOT / "automation" / "prompts" / "heartbeat.md"
PREMARKET_PATH   = ROOT / "automation" / "prompts" / "premarket.md"
HB_AGGRESSIVE    = ROOT / "automation" / "prompts" / "aggressive" / "heartbeat.md"
HB_V14_BACKUP    = ROOT / "automation" / "prompts" / "heartbeat-v14-prod-backup.md"
HB_V15_DRAFT     = ROOT / "automation" / "prompts" / "heartbeat-v15-draft.md"
PREMARKET_DRAFT  = ROOT / "automation" / "prompts" / "premarket-v15-draft.md"
OUTPUT_DIR       = ROOT / "automation" / "state"

RULE_VERSION_RX = re.compile(r"""RULE_VERSION(?:_EXPECTED)?\s*=\s*["']([^"']+)["']""")


def extract_rule_version(path: Path) -> tuple[str | None, int | None]:
    """Return (version, line_number) of first matching RULE_VERSION assignment."""
    if not path.exists():
        return (None, None)
    try:
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            m = RULE_VERSION_RX.search(line)
            if m:
                return (m.group(1), i)
    except Exception:
        return (None, None)
    return (None, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    # ---- AUDIT ----
    if not PARAMS_PATH.exists():
        result = _emit("RED", "params.json missing", {}, args.quiet)
        return 1
    try:
        params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
        params_version = params.get("rule_version")
    except Exception as e:
        result = _emit("RED", f"params.json parse failed: {e}", {}, args.quiet)
        return 1

    hb_version,        hb_line        = extract_rule_version(HEARTBEAT_PATH)
    pm_version,        pm_line        = extract_rule_version(PREMARKET_PATH)
    hb_agg_version,    hb_agg_line    = extract_rule_version(HB_AGGRESSIVE)
    hb_v14_version,    hb_v14_line    = extract_rule_version(HB_V14_BACKUP)
    hb_v15_version,    hb_v15_line    = extract_rule_version(HB_V15_DRAFT)
    pm_draft_version,  pm_draft_line  = extract_rule_version(PREMARKET_DRAFT)

    sources = {
        "params.json": {"version": params_version, "path": str(PARAMS_PATH), "line": None},
        "heartbeat.md": {"version": hb_version, "path": str(HEARTBEAT_PATH), "line": hb_line},
        "premarket.md": {"version": pm_version, "path": str(PREMARKET_PATH), "line": pm_line},
        "aggressive/heartbeat.md": {"version": hb_agg_version, "path": str(HB_AGGRESSIVE), "line": hb_agg_line},
    }
    drafts = {
        "heartbeat-v14-prod-backup.md": {"version": hb_v14_version, "path": str(HB_V14_BACKUP), "line": hb_v14_line},
        "heartbeat-v15-draft.md": {"version": hb_v15_version, "path": str(HB_V15_DRAFT), "line": hb_v15_line},
        "premarket-v15-draft.md": {"version": pm_draft_version, "path": str(PREMARKET_DRAFT), "line": pm_draft_line},
    }

    # ---- DIAGNOSE ----
    # Production pin chain = params.json + heartbeat.md + premarket.md
    # Drafts/backups are advisory (NOT in pin chain — they're version-pinned
    # by their filename and content)
    canonical = params_version
    mismatches = []

    if hb_version != canonical:
        mismatches.append({
            "file": str(HEARTBEAT_PATH),
            "line": hb_line,
            "found": hb_version,
            "expected": canonical,
        })
    if pm_version != canonical:
        mismatches.append({
            "file": str(PREMARKET_PATH),
            "line": pm_line,
            "found": pm_version,
            "expected": canonical,
        })
    if hb_agg_version is not None and hb_agg_version != canonical:
        # aggressive variant — only report if it diverges (it may legitimately differ
        # if J runs aggressive on a different rule_version)
        mismatches.append({
            "file": str(HB_AGGRESSIVE),
            "line": hb_agg_line,
            "found": hb_agg_version,
            "expected": canonical,
            "note": "aggressive-variant-may-be-intentionally-divergent-confirm-with-J"
        })

    if not mismatches:
        verdict = "GREEN"
        reason = f"all-pins-match-canonical-{canonical}"
    else:
        verdict = "RED"
        reason = f"{len(mismatches)}-pin-mismatch(es)-vs-canonical-{canonical}"

    # ---- HEAL (read-only proposal — NEVER auto-edit per rule 9) ----
    proposed_fix = []
    for m in mismatches:
        proposed_fix.append({
            "file": m["file"],
            "line": m["line"],
            "current_value": m["found"],
            "proposed_value": canonical,
            "manual_command": (
                f'python -c "import re,pathlib; '
                f'p=pathlib.Path(r\"{m["file"]}\"); '
                f'src=p.read_text(encoding=\"utf-8\"); '
                f'p.write_text(re.sub(r\"RULE_VERSION(_EXPECTED)?\\s*=\\s*[\\\'\\\"][^\\\'\\\"]+[\\\'\\\"]\", '
                f'lambda mm: f\"RULE_VERSION{{mm.group(1) or \\\"\\\" }} = \\\"{canonical}\\\"\", src), encoding=\"utf-8\")"'
            ),
            "warning": "DO-NOT-RUN-AUTOMATICALLY-needs-J-authorization-per-rule-9",
        })

    # ---- REPORT ----
    result = {
        "skill": "pin-chain-verify",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "verdict": verdict,
        "reason": reason,
        "canonical_rule_version": canonical,
        "rule_version_ratified_at": params.get("rule_version_ratified_at"),
        "production_pin_chain": sources,
        "draft_versions": drafts,
        "mismatches": mismatches,
        "proposed_fix_diff": proposed_fix,
        "heal_action": "NO-AUTO-HEAL-rule-9-production-prompts-need-J-authorization" if mismatches else "no-op",
    }
    return _emit(verdict, reason, result, args.quiet)


def _emit(verdict: str, reason: str, result: dict, quiet: bool) -> int:
    out = OUTPUT_DIR / "pin-chain-verify-latest.json"
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    if not quiet:
        print(f"=== pin-chain-verify ===")
        print(f"VERDICT: {verdict}")
        print(f"  reason: {reason}")
        if result:
            print(f"  canonical: {result.get('canonical_rule_version')}")
            for name, info in (result.get("production_pin_chain") or {}).items():
                ver = info.get("version") or "<NONE>"
                print(f"    {name}: {ver}" + (f" (line {info.get('line')})" if info.get("line") else ""))
            if result.get("mismatches"):
                print(f"  mismatches:")
                for m in result["mismatches"]:
                    print(f"    {m['file']}: found '{m['found']}' expected '{m['expected']}'")
                print(f"  heal: {result.get('heal_action')}")
            print(f"  wrote: {out}")
    return 1 if verdict == "RED" else 0


if __name__ == "__main__":
    sys.exit(main())
