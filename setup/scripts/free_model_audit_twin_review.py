"""free_model_audit_twin_review.py -- the "twin_review" AUDIT_SUBJECTS adapter (AUDIT-HARNESS-B2).

Grades twin_review.py's nightly FREE-LLM health assessment of the CRYPTO TWIN (a mechanism-
validation training ground, never a P&L/edge claim -- see markdown/planning/TWIN-PROGRAM.md).
Each night (after 23:30 UTC, via twin_sentinel.run_sentinel()'s subroutine call) one free-tier
model reads a digest of the day's ticks/incidents/coverage and writes a structured verdict:
{"date", "model_used", "assessment": HEALTHY|DEGRADED|CONCERNING, "confidence": 0-1,
"flags_raised": [...], "summary": "..."} to automation/state/crypto-twin/reviews/YYYY-MM-DD.json.

GROUND TRUTH -- DIFFERENT SHAPE FROM heartbeat_veto's COUNTERFACTUAL REPLAY (see this repo's
free_model_audit_heartbeat_veto.py for that adapter): there is no "would it have made money"
question here (the twin's P&L is never evidence of anything, per TWIN-PROGRAM.md doctrine).
Instead this adapter cross-checks the free-LLM's qualitative HEALTHY/DEGRADED/CONCERNING read
against twin_sentinel.py's DETERMINISTIC RED/YELLOW/GREEN verdict for the SAME UTC day --
"deterministic_cross_check", a new grading_method (alongside counterfactual/llm_judgment/
ungraded_insufficient_data) since agreement-with-a-second-deterministic-source is a genuinely
different evidence class from "did the trade win" or "does Sonnet independently agree blind".

  RED    <-> CONCERNING   YELLOW <-> DEGRADED   GREEN <-> HEALTHY

Source of the deterministic verdict, in priority order (see _sentinel_verdict_for_date):
  1. A REAL twin-sentinel.json snapshot dated the SAME UTC day (most trustworthy -- an actual
     point-in-time judgement already computed by the sentinel's 15-min cadence, not a
     reconstruction). twin-sentinel.json holds only the LATEST snapshot (no append-only
     history file exists yet, confirmed by reading the real file this adapter was built
     against, 2026-07-11) -- this path only fires when the review's date IS "today" from the
     sentinel's perspective.
  2. Reconstruction via twin_sentinel.evaluate() itself, called directly with now_utc pinned to
     23:59:59 UTC on the target date (per the task spec: "reconstruct from twin_sentinel's own
     evaluate() logic if no history file exists yet"). decisions.jsonl/incidents.jsonl are
     genuinely date-filterable append-only logs, so TICK_GAP/LOW_UPTIME/INCIDENT_SPIKE
     reconstruct faithfully for a past day. twin-health.json and path-coverage.json do NOT
     carry per-day history (twin-health.json has no date field at all; path-coverage.json's own
     date_utc simply won't match an older target day, so evaluate() correctly treats coverage
     as "not available" rather than misattributing it -- see twin_sentinel.parse_path_coverage).
     CONSEQUENCE, DISCLOSED NOT HIDDEN (surfaced per-item in evidence_summary/detail's "caveat"
     key): BREAKER_TRIPPED/ACCOUNT_REGRESSION reflect CURRENT twin-health.json state when this
     path is used, not the historical target date's state. This only matters for a date other
     than "today" (path 1 above always wins for today, which is the only date this harness has
     real data for as of authorship -- there is exactly one review on disk, 2026-07-11.json).
  3. `ungraded_insufficient_data` if twin_sentinel.py can't be imported, the date string doesn't
     parse, or evaluate() raises -- never guessed.

READ-ONLY / NEVER-PARTICIPATES: this module never edits twin_review.py, twin_sentinel.py,
crypto_twin_core.py, crypto_twin_health.py, or crypto_twin_scenarios.py -- it only imports
twin_sentinel's evaluate()/_read_json (already the established reuse pattern: twin_review.py
itself imports twin_sentinel's "private" readers rather than re-implementing them) and reads
twin_review's REVIEWS_DIR/VALID_ASSESSMENTS constants. Never places an order, never touches
params*.json, never writes decisions.jsonl of any kind. Writes only through free_model_audit.py's
existing history/scorecard/bar-state plumbing (this adapter itself writes nothing directly).

KNOWN, DISCLOSED APPROXIMATIONS (also logged per-item, never hidden):
  - Sidecar filenames/`date` fields are UTC calendar days (twin_review.py's own explicit
    anchoring -- "matches the twin's own UTC-day session/breaker anchoring", per
    twin_sentinel.py's module docstring), while the free_model_audit.py framework's collect()
    window bounds (`since`/`until`) are ET calendar dates (its own stated contract). At most a
    1-calendar-day slop is possible right at a UTC/ET midnight boundary -- never a content loss
    (a boundary item merely shifts into the adjacent run's window; item_id-based dedupe makes a
    late pickup harmless) and never a double-count. Same disclosed-approximation category as
    heartbeat_veto's own documented list, not a silent bug.
  - The sidecar JSON carries only a UTC calendar date, no exact run timestamp -- `timestamp_et`
    is a midnight-ET placeholder for that date, used for logging/history display only, never for
    TZ-sensitive comparisons.
  - This adapter grades ONLY the `assessment` field (HEALTHY/DEGRADED/CONCERNING vs the mapped
    sentinel verdict) -- `confidence` calibration and `flags_raised` precision are surfaced in
    `detail` for future analysis but are NOT part of `correct` in this first cut (out of the
    task's stated scope; would need much more evidence to grade meaningfully anyway).
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("crypto/lib", "automation/state/fleet", "setup/scripts", "backtest/lib", "backtest/tools"):
    if str(REPO / _p) not in sys.path:
        sys.path.insert(0, str(REPO / _p))

from et_clock import et_now  # noqa: E402

import twin_review as tr  # noqa: E402 -- sibling module (B2's own build); read-only consumption
                          # of its REVIEWS_DIR/VALID_ASSESSMENTS constants, never edited.
import twin_sentinel as ts  # noqa: E402 -- read-only consumption of its evaluate()/_read_json;
                            # this is the SAME reuse pattern twin_review.py itself already uses
                            # ("reuse its fail-open readers/paths rather than a third copy").

STATE = REPO / "automation" / "state"
REVIEWS_DIR = tr.REVIEWS_DIR
SENTINEL_PATH = ts.SENTINEL_PATH

# Deterministic-verdict -> qualitative-assessment mapping. Exact match required for `correct`;
# no partial credit for an adjacent tier (e.g. YELLOW read as HEALTHY is still wrong) -- the
# task asks "does the free-LLM's read agree with what the deterministic sentinel showed", which
# is a direct three-way agreement question, not a tolerance band.
_VERDICT_TO_ASSESSMENT = {"GREEN": "HEALTHY", "YELLOW": "DEGRADED", "RED": "CONCERNING"}


# --------------------------------------------------------------------------------------------
# collect_items -- pure log reader over the reviews/ directory. Returns every dated sidecar in
# [since, until]; the framework (free_model_audit.py) skips already-graded item_ids, so this
# stays a dumb, stateless, re-runnable reader (mirrors free_model_audit_heartbeat_veto.py).
# --------------------------------------------------------------------------------------------

def collect_items(since: Optional[date], until: date, *, reviews_dir: Optional[Path] = None) -> list:
    from free_model_audit import AuditItem  # local import: avoids a circular import at module load
    reviews_dir = reviews_dir or REVIEWS_DIR
    if not reviews_dir.exists():
        return []
    items: list = []
    for path in sorted(reviews_dir.glob("*.json")):
        stem = path.stem  # expected "YYYY-MM-DD" (twin_review.run_review's own naming)
        try:
            d = date.fromisoformat(stem)
        except ValueError:
            continue  # not a dated sidecar (defensive; only shape twin_review.py ever writes)
        # UTC-vs-ET date-window caveat -- see module docstring's "Known, disclosed
        # approximations". Compared at face value against the (ET-labeled) since/until bounds.
        if d > until or (since is not None and d < since):
            continue
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(row, dict):
            continue
        items.append(AuditItem(
            subject="twin_review",
            item_id=f"review:{stem}",
            timestamp_et=f"{stem}T00:00:00",  # midnight-ET placeholder; see module docstring
            account="crypto-twin",
            context={"date": stem, "sidecar_path": str(path)},
            free_model_output=row,
        ))
    return items


# --------------------------------------------------------------------------------------------
# Ground truth: twin_sentinel.py's deterministic verdict for the target UTC day (recorded
# snapshot preferred, evaluate()-reconstruction fallback). See module docstring for full detail.
# --------------------------------------------------------------------------------------------

def _snapshot_date_utc(snap: dict) -> Optional[str]:
    ts_val = snap.get("checked_at_utc") or snap.get("checked_at_et")
    if not ts_val:
        return None
    s = str(ts_val)
    return s[:10] if len(s) >= 10 else None


def _sentinel_verdict_for_date(target_date_str: str, *, sentinel_path: Optional[Path] = None) -> Optional[dict]:
    """Returns {"verdict", "reasons", "incidents_today", "source", "checked_at_utc", ["caveat"]}
    or None only when genuinely nothing is available (bad date string, or twin_sentinel.evaluate
    itself raised) -- caller must grade `ungraded_insufficient_data` in that case, never guess.
    """
    sentinel_path = sentinel_path or SENTINEL_PATH
    snap = ts._read_json(sentinel_path)
    if isinstance(snap, dict):
        if _snapshot_date_utc(snap) == target_date_str:
            facts = snap.get("facts") or {}
            return {
                "verdict": snap.get("verdict"),
                "reasons": list(snap.get("reasons") or []),
                "incidents_today": facts.get("incidents_today"),
                "source": "recorded_snapshot",
                "checked_at_utc": snap.get("checked_at_utc"),
            }

    try:
        target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc)
    except ValueError:
        return None
    try:
        result = ts.evaluate(now_utc=target_dt, now_et=et_now(now_utc=target_dt), prior_sentinel=None)
    except Exception:  # noqa: BLE001 -- a reconstruction failure must never crash the audit run
        return None
    facts = result.get("facts") or {}
    return {
        "verdict": result.get("verdict"),
        "reasons": list(result.get("reasons") or []),
        "incidents_today": facts.get("incidents_today"),
        "source": "reconstructed_evaluate_call",
        "caveat": ("BREAKER_TRIPPED/ACCOUNT_REGRESSION reflect CURRENT twin-health.json state "
                  "(that file carries no per-day history) rather than the historical target "
                  "date; COVERAGE_LAG similarly only applies if path-coverage.json's own "
                  "date_utc still happens to match the target date. Reliable for 'today'; a "
                  "disclosed approximation for any earlier date."),
        "checked_at_utc": target_dt.isoformat(),
    }


# --------------------------------------------------------------------------------------------
# grade_item -- the SubjectAdapter.grade entry point
# --------------------------------------------------------------------------------------------

def grade_item(item, opts: dict) -> dict:  # noqa: ARG001 -- opts accepted for contract parity;
                                           # this grader has no LLM-fallback branch to gate.
    review = item.free_model_output or {}
    llm_assessment = review.get("assessment")
    base = {"decision": llm_assessment or "unknown"}

    if llm_assessment not in tr.VALID_ASSESSMENTS:
        return {**base, "grading_method": "ungraded_insufficient_data", "correct": None,
               "evidence_summary": f"sidecar assessment field missing/invalid: {llm_assessment!r}"}

    target_date = item.context.get("date")
    truth = _sentinel_verdict_for_date(target_date) if target_date else None
    if truth is None or truth.get("verdict") not in _VERDICT_TO_ASSESSMENT:
        return {**base, "grading_method": "ungraded_insufficient_data", "correct": None,
               "evidence_summary": ("no twin-sentinel ground truth available for "
                                    f"{target_date!r} (no same-day recorded snapshot, and "
                                    "evaluate()-reconstruction failed or returned an "
                                    "unrecognized verdict)")}

    expected = _VERDICT_TO_ASSESSMENT[truth["verdict"]]
    correct = (expected == llm_assessment)
    reasons_str = "; ".join(truth.get("reasons") or []) or "(none)"
    caveat = f" CAVEAT: {truth['caveat']}" if truth.get("caveat") else ""
    return {
        **base,
        "grading_method": "deterministic_cross_check",
        "correct": correct,
        "evidence_summary": (f"sentinel_verdict={truth['verdict']} "
                             f"(maps to expected_llm_assessment={expected}) "
                             f"source={truth['source']} "
                             f"incidents_today={truth.get('incidents_today')} "
                             f"reasons=[{reasons_str}]{caveat}"),
        "detail": {**truth, "llm_assessment": llm_assessment,
                  "llm_confidence": review.get("confidence"),
                  "llm_flags_raised": review.get("flags_raised"),
                  "llm_model_used": review.get("model_used")},
    }
