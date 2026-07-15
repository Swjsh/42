"""free_model_audit_prospector.py -- the "prospector" AUDIT_SUBJECTS adapter (AUDIT-HARNESS-B3).

Grades prospector.py's (Gamma_Prospector) idea-promotion judgment: for every idea it promoted
into strategy/candidates/_chef-inbox/ (its own promote_top1() -- the single oldest not-yet-
promoted "battery-ready" idea each fire), did that idea go on to survive its downstream battery,
get killed, or is it still pending? A promotion is prospector's (and, upstream, the free-tier
swarm model that proposed the idea -- see idea row's "source" field) implicit bet that the idea
was worth Chef's time; this adapter checks whether that bet paid off.

GROUND TRUTH -- DETERMINISTIC CROSS-CHECK, TWO SOURCES, CHECKED IN ORDER (never an LLM
judgment call -- there is no "would it have made money" question for an idea proposal, and no
open-ended text to blindly re-judge either; this is a pure record-linkage problem):
  1. `kind:"kill"` rows in the SAME analysis/prospector/ideas-ledger.jsonl file, keyed by the
     EXACT dedupe_key (prospector.kill_idea()'s own mechanism -- see prospector.py module
     docstring: "a dedupe_key that was EVER recorded as killed... can never re-enter"). This is
     the most authoritative signal available: prospector's own organ recording its own idea's
     death, not an inference.
  2. A literal dedupe_key match inside analysis/recommendations/ (any .json or .md file), with a
     KILL/CLEAR verdict word found in the SAME file (see _KILL_WORDS/_CLEAR_WORDS below). If the
     dedupe_key is found but no unambiguous verdict word is present, this is logged as
     `ungraded_insufficient_data` (AMBIGUOUS) rather than guessed -- a bare substring match is
     not proof of disposition.
  3. Neither found -> `ungraded_insufficient_data` ("still pending") -- the overwhelmingly
     common case as of this adapter's authorship (2026-07-14/15): every currently-promoted
     dedupe_key was grepped against analysis/recommendations/ and ideas-ledger.jsonl's own kill
     rows and NONE matched yet (Chef's pipeline has not yet cycled any prospector-sourced idea
     through a full battery to a scorecard). This is disclosed, not hidden: the first real run
     of this adapter is expected to report INSUFFICIENT EVIDENCE for every item.

KNOWN, DISCLOSED APPROXIMATIONS (logged per-item in `evidence_summary`/`detail`, never hidden):
  - "Promoted" is read from the strategy/candidates/_chef-inbox/*-prospector-*.md filesystem
    listing (parsed for the promotion date in the filename + the exact dedupe_key from the
    file's own "## Files for Reference" line -- both written verbatim by
    prospector.render_chef_inbox_item()), NOT from automation/state/prospector-last.json's
    promoted_total counter or state.json's promoted_dedupe_keys list. Those two ARE stale
    relative to the filesystem (state.json shows promoted_total=4 as of 2026-07-14 while 29
    *-prospector-*.md files exist in _chef-inbox/ -- confirmed by direct listing before writing
    this adapter) -- a pre-existing prospector.py bookkeeping drift, NOT something this
    read-only audit module fixes or hides. The filesystem listing is the more complete and
    verifiable source of "what was actually promoted."
  - A dedupe_key promoted MORE THAN ONCE (observed for both `vix1d_gate` and
    `volume_shelf_tv_vp`, promoted 2026-07-09/07-10 AND again 2026-07-14 -- the same
    pre-existing drift noted above) yields ONE AuditItem PER PROMOTION EVENT (item_id includes
    the promotion date), each graded independently against the SAME downstream disposition.
    This is a deliberate, disclosed choice, not a bug: each promotion event is prospector's own
    distinct "I still think this is worth Chef's time" decision.
  - The KILL/CLEAR verdict-word scan over analysis/recommendations/ is a coarse keyword match
    (see _KILL_WORDS/_CLEAR_WORDS), not a schema-aware parse -- recommendation files use
    genuinely heterogeneous shapes across ~130+ files (confirmed by sampling several before
    writing this module: some carry a "verdict" key, some don't, field names vary). A file that
    contains BOTH a kill-word and a clear-word is treated as AMBIGUOUS (ungraded) rather than
    guessed either way.

READ-ONLY / NEVER-PARTICIPATES: this module never edits prospector.py's ledger/state/inbox, never
calls kill_idea() or promote_top1(), never writes to analysis/recommendations/. It reads
prospector.py's own CHEF_INBOX/LEDGER_FILE constants and load_ledger() (same reuse pattern
free_model_audit_twin_review.py already established -- import the sibling module read-only
rather than re-implementing its I/O). Writes only through free_model_audit.py's existing
history/scorecard/bar-state plumbing (this adapter itself writes nothing directly).
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("crypto/lib", "automation/state/fleet", "setup/scripts", "backtest/lib", "backtest/tools"):
    if str(REPO / _p) not in sys.path:
        sys.path.insert(0, str(REPO / _p))

import prospector as pr  # noqa: E402 -- sibling module (this subject's own build); read-only
                         # consumption of its CHEF_INBOX/LEDGER_FILE constants + load_ledger(),
                         # never edited (mirrors free_model_audit_twin_review.py's own pattern).

CHEF_INBOX = pr.CHEF_INBOX
LEDGER_FILE = pr.LEDGER_FILE
RECOMMENDATIONS_DIR = REPO / "analysis" / "recommendations"

_INBOX_FNAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-prospector-")
_DEDUPE_KEY_RE = re.compile(r"\(dedupe_key:\s*([^)]+)\)")

# Coarse keyword scan -- see module docstring's "Known, disclosed approximations". Word-boundary
# matched, case-insensitive. A file matching BOTH sets is treated as ambiguous (grade_item),
# never guessed.
_KILL_WORDS = re.compile(r"\b(KILL(?:ED)?|REJECT(?:ED)?|FAIL(?:ED)?|DEAD|NO-?GO)\b", re.I)
_CLEAR_WORDS = re.compile(r"\b(SHIP(?:PED|S)?|RATIF(?:Y|IED)|CLEAR(?:ED)?|PROMOTE(?:D)?|"
                          r"PASS(?:ED)?|LIVE|CONFIRMED?)\b", re.I)


def _rel(path: Path) -> str:
    """repo-relative path for readable logging; falls back to the absolute path when `path`
    is outside REPO (e.g. a tmp_path fixture in tests) -- never raises."""
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------------------------
# collect_items -- reads the REAL promotion record (_chef-inbox filesystem listing), cross-
# referenced against ideas-ledger.jsonl for the idea's own fields. Pure log reader; the
# framework (free_model_audit.py) skips already-graded item_ids, so this stays a dumb,
# stateless, re-runnable reader (mirrors both existing adapters).
# --------------------------------------------------------------------------------------------

def collect_items(since: Optional[date], until: date, *,
                  inbox_dir: Optional[Path] = None, ledger_path: Optional[Path] = None) -> list:
    from free_model_audit import AuditItem  # local import: avoids a circular import at module load
    inbox_dir = inbox_dir or CHEF_INBOX
    ledger_path = ledger_path or LEDGER_FILE
    if not inbox_dir.exists():
        return []
    ledger_rows = pr.load_ledger(ledger_path)
    idea_by_key = {r["dedupe_key"]: r for r in ledger_rows
                  if r.get("kind") == "idea" and r.get("dedupe_key")}

    items: list = []
    for path in sorted(inbox_dir.glob("*-prospector-*.md")):
        m = _INBOX_FNAME_RE.match(path.name)
        if not m:
            continue  # not prospector's own naming shape (defensive; see promote_top1's fname)
        try:
            promo_date = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if promo_date > until or (since is not None and promo_date < since):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        dk_m = _DEDUPE_KEY_RE.search(text)
        if not dk_m:
            continue  # no parseable dedupe_key -- can't grade what we can't identify
        dedupe_key = dk_m.group(1).strip()
        idea_row = idea_by_key.get(dedupe_key, {})
        items.append(AuditItem(
            subject="prospector",
            item_id=f"promoted:{dedupe_key}:{promo_date.isoformat()}",
            timestamp_et=f"{promo_date.isoformat()}T00:00:00",
            account="prospector",
            context={"dedupe_key": dedupe_key, "promoted_date": promo_date.isoformat(),
                    "chef_inbox_file": _rel(path),
                    "beat": idea_row.get("beat"), "idea": idea_row.get("idea"),
                    "testability": idea_row.get("testability")},
            free_model_output={"idea": idea_row.get("idea"),
                               "mechanism_1line": idea_row.get("mechanism_1line"),
                               "testability": idea_row.get("testability"),
                               "source": idea_row.get("source"), "promoted": True},
        ))
    return items


# --------------------------------------------------------------------------------------------
# Ground truth: prospector's own kill ledger (authoritative) + analysis/recommendations/ scan
# --------------------------------------------------------------------------------------------

def _kill_reason_for(dedupe_key: str, ledger_rows: list[dict]) -> Optional[str]:
    for r in ledger_rows:
        if r.get("kind") == "kill" and r.get("dedupe_key") == dedupe_key:
            return str(r.get("reason") or "(no reason logged)")
    return None


def _recommendation_verdict_for(dedupe_key: str, *,
                                recs_dir: Path = RECOMMENDATIONS_DIR) -> Optional[dict]:
    """Returns {"disposition": KILLED|CLEARED|AMBIGUOUS, "file", ["evidence"|"n_hits"]} or None
    if the dedupe_key is not found anywhere under analysis/recommendations/ at all."""
    if not recs_dir.exists():
        return None
    hits: list[tuple[Path, str]] = []
    for path in sorted(recs_dir.rglob("*")):
        if not path.is_file() or path.suffix not in (".json", ".md"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if dedupe_key not in text:
            continue
        hits.append((path, text))
    if not hits:
        return None
    for path, text in hits:
        kill_m = _KILL_WORDS.search(text)
        clear_m = _CLEAR_WORDS.search(text)
        if kill_m and not clear_m:
            return {"disposition": "KILLED", "file": _rel(path),
                    "evidence": kill_m.group(0)}
        if clear_m and not kill_m:
            return {"disposition": "CLEARED", "file": _rel(path),
                    "evidence": clear_m.group(0)}
    return {"disposition": "AMBIGUOUS", "file": _rel(hits[0][0]),
           "n_hits": len(hits)}


# --------------------------------------------------------------------------------------------
# grade_item -- the SubjectAdapter.grade entry point
# --------------------------------------------------------------------------------------------

def grade_item(item, opts: dict) -> dict:  # noqa: ARG001 -- opts accepted for contract parity;
                                           # this grader has no LLM-fallback branch to gate (pure
                                           # deterministic record-linkage, no open-ended text).
    dedupe_key = item.context.get("dedupe_key")
    base = {"decision": "promoted", "dedupe_key": dedupe_key}
    if not dedupe_key:
        return {**base, "grading_method": "ungraded_insufficient_data", "correct": None,
               "evidence_summary": "chef-inbox item missing a parseable dedupe_key"}

    ledger_rows = pr.load_ledger(LEDGER_FILE)
    killed_reason = _kill_reason_for(dedupe_key, ledger_rows)
    if killed_reason is not None:
        return {**base, "grading_method": "deterministic_cross_check", "correct": False,
               "evidence_summary": f"idea KILLED in ideas-ledger.jsonl: {killed_reason}",
               "detail": {"source": "ideas_ledger_kill_row", "reason": killed_reason}}

    rec = _recommendation_verdict_for(dedupe_key)
    if rec is None:
        return {**base, "grading_method": "ungraded_insufficient_data", "correct": None,
               "evidence_summary": (f"no downstream kill row or recommendations artifact yet "
                                    f"for dedupe_key={dedupe_key!r} -- still pending")}
    if rec["disposition"] == "KILLED":
        return {**base, "grading_method": "deterministic_cross_check", "correct": False,
               "evidence_summary": (f"downstream recommendation artifact shows KILL "
                                    f"({rec['file']}, matched {rec['evidence']!r})"),
               "detail": rec}
    if rec["disposition"] == "CLEARED":
        return {**base, "grading_method": "deterministic_cross_check", "correct": True,
               "evidence_summary": (f"downstream recommendation artifact shows battery-cleared "
                                    f"({rec['file']}, matched {rec['evidence']!r})"),
               "detail": rec}
    return {**base, "grading_method": "ungraded_insufficient_data", "correct": None,
           "evidence_summary": (f"dedupe_key found in {rec['file']} but no unambiguous "
                                f"KILL/CLEAR verdict signal -- not guessed ({rec['n_hits']} "
                                f"file(s) matched)"),
           "detail": rec}
