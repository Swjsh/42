"""free_model_audit_swarm_consult.py -- the "swarm_consult" AUDIT_SUBJECTS adapter
(AUDIT-HARNESS-B3).

Grades swarm_consult.py's free-tier-model synthesized answers (analysis/swarm-consult/*.json --
{question, context, mode, perspectives:[...], synthesis:{model, ok, content, ...}}) via BLIND
RE-JUDGMENT (grading method #2 in free_model_audit.py's module docstring -- the same method
heartbeat_veto uses as its fallback, promoted here to the PRIMARY method since swarm_consult's
open-ended brainstorm/decide/critique/audit questions have no $ counterfactual and no second
deterministic source to cross-check against):

  1. Sonnet answers the SAME question + context, BLIND -- it is NEVER shown the free-tier
     swarm's synthesized answer first (anti-anchoring, same principle as heartbeat_veto's
     `_llm_judgment`).
  2. A SEPARATE Sonnet call is then shown BOTH the blind re-answer and the swarm's synthesis and
     asked one question: do these two INDEPENDENTLY-arrived-at answers reach the same
     substantive conclusion, or a different one? Its {"agree": true|false} becomes `correct`.

Two Sonnet calls per graded item (not one) -- the blind answer must be committed BEFORE the
swarm's answer is revealed, or the "independent" re-judgment is contaminated by anchoring.
grading_method="llm_judgment" (the framework's existing tag for this method; no new tag needed).

COST BOUND (J: "cap the per-run sample (<=5 consults) to bound cost"): collect_items caps at
MAX_SAMPLE_PER_RUN=5 consults, most-recent-first, REGARDLESS of window size -- a large backlog on
first run never balloons into dozens of Sonnet calls. At most 5 items x 2 calls = 10 Sonnet
calls per run, riding the Max subscription pool (not metered API spend), same cost model as
heartbeat_veto's own LLM fallback and manager_overseer.py/gamma-drive.

READ-ONLY / NEVER-PARTICIPATES: this module never edits analysis/swarm-consult/*.json, never
calls swarm_consult.consult()/brainstorm(), never writes anywhere except through
free_model_audit.py's existing history/scorecard/bar-state plumbing (this adapter itself writes
nothing directly, aside from a scratch prompt tmpfile it always overwrites in place).

KNOWN, DISCLOSED APPROXIMATIONS (logged per-item in `evidence_summary`/`detail`, never hidden):
  - "Agreement" on an open-ended, multi-paragraph recommendation is inherently a judgment call,
    not a bit-exact comparison -- this is why the method is `llm_judgment`, not
    `deterministic_cross_check`. Sonnet grading Sonnet-authored text (the blind re-answer) next
    to free-tier-authored text (the swarm synthesis) could in principle carry a stylistic bias
    toward whichever answer "sounds like itself"; not something this first cut corrects for
    (would need a genuinely blind third judge to rule out, out of scope here).
  - The swarm's `context` blob is truncated to CONTEXT_TRUNCATE_CHARS before the blind re-answer
    call, mirroring swarm_consult._build_synthesis_prompt's own truncation (same 5000-char
    constant) -- so the blind re-answer sees exactly as much engine-state context as the
    original swarm synthesis pass did, not more or less.
  - A consult whose `synthesis.ok` is False (all perspectives failed, no synthesis produced) is
    `ungraded_insufficient_data` -- there is nothing to grade.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Optional

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

REPO = Path(__file__).resolve().parents[2]
for _p in ("crypto/lib", "automation/state/fleet", "setup/scripts", "backtest/lib", "backtest/tools"):
    if str(REPO / _p) not in sys.path:
        sys.path.insert(0, str(REPO / _p))

from free_model_audit_heartbeat_veto import _claude_exe  # noqa: E402 -- reused claude-exe
                          # resolution cascade (repo convention: sibling adapters reuse each
                          # other's "private" helpers rather than a third copy -- see
                          # free_model_audit_twin_review.py's own docstring for the same pattern
                          # with twin_sentinel's _read_json).

SWARM_CONSULT_DIR = REPO / "analysis" / "swarm-consult"
PROMPT_TMP = REPO / "automation" / "state" / ".free-model-audit-swarm-prompt.tmp"

SONNET = "claude-sonnet-4-6"  # matches free_model_audit_heartbeat_veto.py's constant exactly
MAX_SAMPLE_PER_RUN = 5  # bound cost: at most 5 consults re-judged (2 Sonnet calls each) per run
CONTEXT_TRUNCATE_CHARS = 5000  # mirrors swarm_consult._build_synthesis_prompt's own truncation

def _rel(path: Path) -> str:
    """repo-relative path for readable logging; falls back to the absolute path when `path`
    is outside REPO (e.g. a tmp_path fixture in tests) -- never raises."""
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


_BLIND_PROMPT_TEMPLATE = """You are being asked to give an INDEPENDENT, BLIND answer for an
audit -- you have NOT been shown any other model's analysis or recommendation. Answer the
question below SOLELY on the context given, in your own honest, independent read.

## Context
{context}

## Question
{question}

Give a concise, direct answer/recommendation (a few sentences to a short paragraph). No
preamble, no meta-commentary about being an auditor.
"""

_AGREEMENT_PROMPT_TEMPLATE = """You are auditing a free-tier LLM swarm's synthesized answer to a
question, by comparing it against an INDEPENDENT blind re-answer from a separate, trusted model
that was given the SAME question and context but never saw the swarm's answer.

## Question
{question}

## Independent blind re-answer (never saw the swarm's answer)
{blind_answer}

## Swarm's synthesized answer (free-tier models, being graded)
{swarm_answer}

Do these two answers reach the SAME substantive conclusion/recommendation (even if worded
differently, even if one is more detailed), or a DIFFERENT one? Output ONLY a JSON object:
{{"agree": true|false, "reason": "<one short sentence>"}}. No preamble, no code fences, no other
text.
"""


# --------------------------------------------------------------------------------------------
# collect_items -- pure log reader over analysis/swarm-consult/*.json, capped at
# MAX_SAMPLE_PER_RUN most-recent-in-window. The framework (free_model_audit.py) is responsible
# for skipping already-graded item_ids, so this stays a dumb, stateless, re-runnable reader --
# EXCEPT for the cost cap, which this adapter must own itself (an unbounded adapter would blow
# the "<=5 consults" budget the moment a large backlog exists on first run).
# --------------------------------------------------------------------------------------------

def collect_items(since: Optional[date], until: date, *, consult_dir: Optional[Path] = None) -> list:
    from free_model_audit import AuditItem  # local import: avoids a circular import at module load
    consult_dir = consult_dir or SWARM_CONSULT_DIR
    if not consult_dir.exists():
        return []

    candidates: list[tuple[str, Path, dict]] = []
    for path in sorted(consult_dir.glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        if not isinstance(row, dict):
            continue
        ts_et = row.get("ts_et")
        if not ts_et:
            continue
        try:
            row_date = date.fromisoformat(str(ts_et)[:10])
        except ValueError:
            continue
        if row_date > until or (since is not None and row_date < since):
            continue
        candidates.append((str(ts_et), path, row))

    # Cost bound -- most-recent-first, cap regardless of window size (see module docstring).
    candidates.sort(key=lambda t: t[0], reverse=True)
    candidates = candidates[:MAX_SAMPLE_PER_RUN]

    items: list = []
    for ts_et, path, row in candidates:
        synthesis = row.get("synthesis") or {}
        items.append(AuditItem(
            subject="swarm_consult",
            item_id=f"consult:{path.stem}",
            timestamp_et=str(ts_et),
            account="swarm_consult",
            context={"mode": row.get("mode"), "question": row.get("question"),
                    "context_blob": row.get("context"), "slug": row.get("slug"),
                    "path": _rel(path)},
            free_model_output=synthesis,
        ))
    return items


# --------------------------------------------------------------------------------------------
# Sonnet call plumbing -- SAME subprocess/tmpfile/creationflags pattern as
# free_model_audit_heartbeat_veto._llm_judgment (reused via _claude_exe, reimplemented here only
# because this adapter needs TWO distinct calls with different prompts/parsing, not one).
# --------------------------------------------------------------------------------------------

def _call_sonnet(prompt: str, *, timeout: int = 180) -> Optional[str]:
    exe = _claude_exe()
    try:
        PROMPT_TMP.parent.mkdir(parents=True, exist_ok=True)
        PROMPT_TMP.write_text(prompt, encoding="utf-8")
    except OSError:
        return None
    try:
        proc = subprocess.run(f'"{exe}" --print --model {SONNET} < "{PROMPT_TMP}"',
                              shell=True, capture_output=True, text=True, timeout=timeout,
                              cwd=str(REPO), encoding="utf-8", errors="replace",
                              creationflags=_CREATE_NO_WINDOW)
    except Exception:  # noqa: BLE001 -- a subprocess failure must degrade to "no answer", never crash
        return None
    out = (proc.stdout or "").strip()
    return out or None


def _blind_reanswer(question: str, context_blob: str, *, timeout: int = 180) -> Optional[str]:
    ctx = context_blob or ""
    if len(ctx) > CONTEXT_TRUNCATE_CHARS:
        ctx = ctx[:CONTEXT_TRUNCATE_CHARS] + "\n[truncated for audit]"
    prompt = _BLIND_PROMPT_TEMPLATE.format(context=ctx or "(no context given)", question=question)
    return _call_sonnet(prompt, timeout=timeout)


def _agreement_judgment(question: str, blind_answer: str, swarm_answer: str,
                        *, timeout: int = 180) -> Optional[dict]:
    try:
        from swarm_client import extract_json  # noqa: PLC0415
    except Exception:
        extract_json = lambda s: json.loads(s)  # noqa: E731 -- last-ditch, rarely needed
    prompt = _AGREEMENT_PROMPT_TEMPLATE.format(question=question, blind_answer=blind_answer,
                                               swarm_answer=swarm_answer)
    raw = _call_sonnet(prompt, timeout=timeout)
    if raw is None:
        return None
    out = extract_json(raw)
    if not isinstance(out, dict) or "agree" not in out:
        return None
    return {"agree": bool(out.get("agree")), "reason": str(out.get("reason", ""))[:300]}


# --------------------------------------------------------------------------------------------
# grade_item -- the SubjectAdapter.grade entry point
# --------------------------------------------------------------------------------------------

def grade_item(item, opts: dict) -> dict:
    ctx = item.context
    mode = ctx.get("mode") or "?"
    base = {"decision": mode, "slug": ctx.get("slug")}

    synthesis = item.free_model_output or {}
    swarm_answer = synthesis.get("content")
    swarm_ok = synthesis.get("ok", True)
    if not swarm_answer or not swarm_ok:
        return {**base, "grading_method": "ungraded_insufficient_data", "correct": None,
               "evidence_summary": "consult has no successful synthesis to grade"}

    question = str(ctx.get("question") or "").strip()
    if not question:
        return {**base, "grading_method": "ungraded_insufficient_data", "correct": None,
               "evidence_summary": "consult row missing a question to re-ask blind"}

    if not opts.get("allow_llm_fallback", True):
        return {**base, "grading_method": "ungraded_insufficient_data", "correct": None,
               "evidence_summary": ("llm fallback disabled (--no-llm-fallback) -- this subject "
                                    "has no non-LLM grading path (blind re-judgment IS the "
                                    "method, not a fallback)")}

    blind = _blind_reanswer(question, ctx.get("context_blob") or "")
    if blind is None:
        return {**base, "grading_method": "ungraded_insufficient_data", "correct": None,
               "evidence_summary": "blind re-answer Sonnet call failed/timed out"}

    agreement = _agreement_judgment(question, blind, swarm_answer)
    if agreement is None:
        return {**base, "grading_method": "ungraded_insufficient_data", "correct": None,
               "evidence_summary": "agreement-judgment Sonnet call failed/unparseable"}

    return {**base, "grading_method": "llm_judgment", "correct": agreement["agree"],
           "evidence_summary": (f"blind-reanswer agreement={agreement['agree']} "
                                f"reason={agreement['reason'][:140]}"),
           "detail": {"blind_answer": blind[:1000], "swarm_answer": str(swarm_answer)[:1000],
                      "agreement_reason": agreement["reason"]}}
