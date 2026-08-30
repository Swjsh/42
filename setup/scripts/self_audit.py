"""self_audit.py -- the proactive GAP-FINDER organ Gamma was missing.

Why (2026-06-26, J: "WHY IS GAMMA NOT SMART YET? WHY DID GAMMA NOT KNOW THIS"): all day the
operator had to point out gaps Gamma should have caught itself (validation-not-direction,
draw-your-own-trendlines, dormant-setups-are-theater, test-in-the-24/7-gym). Root cause the
swarm itself named: the "brainstorm second-order effects" directive (OP / feedback_proactive_
engine_brainstorm) was NEVER run autonomously -- Gamma reacts instead of interrogating its own
work. This script turns the existing free swarm-decision-engine into a SCHEDULED self-audit:
every run it asks the free swarm "what is Gamma obviously missing right now?", logs the ranked
gaps, and FLAGS the ones it hasn't seen before -- so Gamma surfaces its own gaps before J does.

$0 (free OpenRouter models via swarm_consult.py). Pure stdlib + subprocess. Flash-free when
scheduled via the wscript->pythonw chain (NEVER a bare powershell/cmd action -- see the popup
lesson). Idempotent: appends to a gap-log, dedupes by normalized gap text.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "self-audit.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "self-audit.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import hashlib
import json
import re
import subprocess
import sys

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # no conhost flash on win32 (OP-27 L41)
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
from et_clock import et_now as _et_clock_now  # DST-aware ET (TZ-SYSTEMIC fix)
SWARM = REPO / "setup" / "scripts" / "swarm_consult.py"
PY = REPO / "backtest" / ".venv" / "Scripts" / "python.exe"

# SELF-AUDIT-GAP-LOG-REVERSION (2026-08-11): swarm_consult.py's OWN internal budget is
# PERSPECTIVE_TIMEOUT_S(240, parallel across models) + SYNTHESIS_TIMEOUT_S(300, sequential
# after perspectives) = 540s worst case -- this outer subprocess timeout MUST exceed that
# sum or every run whose synthesis phase takes anywhere near its own allotted budget gets
# silently killed here and swallowed by the bare `except Exception: return 0` below (exit-0
# "success" with zero audit performed). Measured live: 300s (< 540s) caused 2 consecutive
# full-audit failures, 2026-08-09 + 2026-08-10, invisible until this fire's investigation --
# gap-log.jsonl (the dedup ledger) hadn't advanced in a month for a COMPOUNDING reason (see
# .gitignore), but these 2 fires never even reached the write step at all.
# See backtest/tests/test_self_audit_swarm_timeout.py for the cross-file drift guard.
SWARM_SUBPROCESS_TIMEOUT_S = 600
LOG = REPO / "analysis" / "self-audit" / "gap-log.jsonl"
FLAGS = REPO / "analysis" / "self-audit" / "new-gaps-flagged.md"
CONSULT_DIR = REPO / "analysis" / "swarm-consult"

STANDING_QUESTION = (
    "Audit Project Gamma (autonomous 0DTE SPY options trader + self-improvement engine) for "
    "what it is OBVIOUSLY missing or should already be doing AUTONOMOUSLY. List the top 6-8 "
    "concrete, ranked, actionable gaps Gamma should self-identify RIGHT NOW: better tools it "
    "isn't using, existing infrastructure not connected, next-order implications, and what the "
    "operator will point at NEXT. Be specific; avoid generic advice."
)


def _et_now() -> datetime:
    """ET from UTC via DST-aware et_clock (replaces hardcoded -4)."""
    return _et_clock_now()


def _recent_context() -> str:
    """Feed the swarm what changed lately so the audit is grounded, not generic."""
    bits = []
    try:
        status = (REPO / "automation" / "overnight" / "STATUS.md").read_text(encoding="utf-8")
        bits.append("RECENT STATUS (top):\n" + "\n".join(status.splitlines()[:40]))
    except Exception:
        pass
    try:
        log = subprocess.run(["git", "-C", str(REPO), "log", "--oneline", "-12"],
                             capture_output=True, text=True, timeout=20,
                             creationflags=_CREATE_NO_WINDOW)
        bits.append("RECENT COMMITS:\n" + log.stdout)
    except Exception:
        pass
    return "\n\n".join(bits)[:180_000]


def _norm(s: str) -> str:
    # 2026-08-18: collapse ALL unicode whitespace (e.g. U+202F narrow no-break
    # space, seen verbatim in real consult text as "Rule 10") to a plain
    # ' ' BEFORE stripping non-alnum chars. Without this, the alnum-strip
    # regex below (which only preserves literal ASCII ' ') silently GLUES
    # adjacent words together ("Rule 10" -> "rule10"), defeating every
    # space-anchored scaffold-prefix match (e.g. the "rule 9"/"rule 10"
    # entries in _SCAFFOLD_PREFIXES) -- a latent bug newly exposed once
    # _extract_gaps started joining full bullet lines (see _join_bold_bullet)
    # instead of short bold-only headlines, which had accidentally masked it
    # via the separate <3-word length check.
    s = re.sub(r"\s", " ", s)
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()[:90]


# 2026-08-02: the synthesis-bullet harvest (unlike the perspective bold-lead-in harvest)
# grabbed the WHOLE bullet line verbatim, including markdown bold LABEL prefixes like
# "**Most rigorous view:** Perspective 2 provides ..." (the label, not the gap itself),
# then hard-truncated at 120 chars with a raw slice -- cutting mid-word/mid-sentence
# ("...they provide a concrete, testable failure mode, "). Two batches (2026-07-31,
# 2026-08-01) landed in new-gaps-flagged.md as unreadable, unactionable fragments --
# a self-audit organ producing noise instead of signal is exactly the C7 class this
# organ exists to prevent. Fixed here: strip a leading bold LABEL (text before the
# colon inside **...**), and soft-truncate at a word boundary instead of a raw slice.
_BOLD_LABEL_PREFIX_RE = re.compile(r"^\*\*([^*]+?)\*\*:?\s*(.+)$")
_SYNTH_BULLET_LIMIT = 240


def _strip_bold_label(line: str) -> str:
    """Drop a leading '**Label:**' markdown lead-in, keeping only what follows.

    'Most rigorous view:** Perspective 2 provides ...' -> 'Perspective 2 provides ...'
    A bullet with NO bold label (the common case) passes through unchanged.
    """
    m = _BOLD_LABEL_PREFIX_RE.match(line.strip())
    return m.group(2).strip() if m else line.strip()


def _soft_truncate(s: str, limit: int = _SYNTH_BULLET_LIMIT) -> str:
    """Truncate at the last word boundary <= limit, never mid-word. Adds an
    ellipsis marker so a still-truncated gap is visibly incomplete, not silently
    chopped mid-sentence (readers can tell to go re-read the source consult)."""
    s = s.strip()
    if len(s) <= limit:
        return s
    cut = s[:limit]
    sp = cut.rfind(" ")
    if sp > limit * 0.5:
        cut = cut[:sp]
    return cut.rstrip() + " [...]"


def _known_gap_keys() -> set[str]:
    if not LOG.exists():
        return set()
    keys = set()
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            keys.add(json.loads(line)["key"])
        except Exception:
            continue
    return keys


# --- Noise filter (2026-06-29) ----------------------------------------------
# The bold/numbered-bullet harvest also catches the MODEL'S OWN reasoning scaffold
# and the pre-ship-check / prompt-skeleton SECTION HEADERS (the model echoes the
# template back as bold lead-ins). On 2026-06-29 a whole batch of 12 "gaps" was
# pure scaffold ("Analyze the Request:", "Role:", "Task:", "Risk score",
# "Failure mode", ...) which crowded the REAL gaps (in a later perspective) out of
# the [:12] budget -> the self-audit organ flagged 100% noise. Reject scaffold so
# genuine gaps survive. Conservative by design: reject only CLEAR noise; when in
# doubt KEEP (the downstream conductor applies its own judgment, and flooding out
# every real gap is far costlier than one stray header surviving).
_SCAFFOLD_PREFIXES = (
    "rule 9", "rule 10", "failure mode", "most likely failure mode",
    "impact on j", "impact on pilot", "worstcase impact", "worst case impact",
    "secondorder effects", "second order effects", "hidden secondorder effects",
    "hidden second order effects", "risk score", "key question",
    "single mostimportant question", "single most important question",
    "op 32", "op32", "op violations", "trade missed", "wrong direction", "overfit",
    "analyze the", "identify gaps", "refine and rank", "drafting the response",
    "specific output format", "final polish", "impact on pilotheartbeat",
    "first a ranked", "then for the", "produce the seven",
    # 2026-07-01: the synthesis echoes a "Question for reviewer" template section
    # and cross-references each perspective ("Perspective 2 flags ...") as bold
    # lead-ins -> pure scaffold that crowded 5 of 9 real-gap slots this batch.
    "question for reviewer", "question for the reviewer",
)
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,8}(?:/[0-9a-f]{6,8})*$")
# "Perspective 2 flags ...", "Perspective 3 zeroes in ...", "Perspectives 1, 2, 5
# view ..." -- the synthesis describing WHAT a perspective (or several) said, not
# stating a gap. Reject the cross-ref lead-in (normalized to 'perspective(s) 2
# flags ...'). `s?` handles the plural form seen in the 2026-07-18 batch
# ("Perspectives 1, 2, 5 view the guard issue as a symptom ..."), which the
# singular-only regex let through. Word-boundary + digit so a genuine gap that
# merely contains the word 'perspective' mid-sentence survives.
_PERSPECTIVE_REF_RE = re.compile(r"^perspectives?\s*\d")
# 2026-07-19: "All perspectives agree that ...", "All agree that ...", "All
# concur that ...", "There is broad agreement that ...", "A majority (4/5) agree
# that ...", "Finally, all concur that ..." -- the SAME synthesis
# cross-reference-noise class the 2026-07-01 fix targeted for the singular
# "Perspective N flags ..." lead-in, just a different lexical family: consensus
# COMMENTARY describing what the perspectives collectively said, not a gap
# statement itself. Recurred untouched across the 07-09/07-10/07-11/07-13/07-18
# batches (7+ leaked "gaps" that are pure meta-commentary, e.g. "All agree that
# missing real-time risk guards ... can lead to Rule 9/10 vi[olations]" -- a
# description of consensus, not an actionable finding on its own). Conservative:
# anchored to the LEAD-IN only, so a real gap that happens to mention "most
# perspectives" or "a majority" mid-sentence still survives.
_CONSENSUS_LEADIN_RE = re.compile(
    r"^(all (perspectives )?(agree|concur)\b"
    r"|there is (broad )?agreement\b"
    r"|a majority\b"
    r"|most (perspectives|agree)\b"
    r"|finally all (concur|agree)\b"
    r"|several (perspectives )?agree\b"
    # 2026-08-18: "The most rigorous view is Perspective 5 because ..." -- the
    # SAME synthesis cross-reference-noise class as _PERSPECTIVE_REF_RE (rating
    # one perspective against the others), just a lead-in shape neither that
    # regex (requires the LINE to start with 'perspective(s) N') nor this one
    # (required an explicit agree/concur/majority verb) caught. Leaked verbatim
    # into the 2026-08-18 batch under "Key disagreements". Anchored to the
    # rating lead-in only, so a real gap that happens to discuss which
    # perspective is "most rigorous" mid-sentence still survives.
    r"|the most (rigorous|compelling|persuasive|convincing) view is perspectives?\s*\d"
    r"|the strongest perspective is\s*\d)"
)
# 2026-08-19: a THIRD lexical family of the exact same synthesis cross-reference-noise
# class, using abbreviated "P1/P2/P3" shorthand instead of the spelled-out "Perspective
# N" that _PERSPECTIVE_REF_RE requires, or an "all agree/concur" verb that
# _CONSENSUS_LEADIN_RE requires. Leaked 4 of 8 flagged "gaps" in the 2026-08-19 batch
# (en-dash synthesis bullets: "P1, P2, and P3 all flag ...", "P1 and P2 explicitly note
# ...", "P1 shows ... P2 calls ...", "P1's <claim> and P3's <claim> both demand ...") and
# sat un-triaged in new-gaps-flagged.md for 5 more days before anyone re-read the batch.
# Two shapes:
#   (a) "P<n>[, P<n>]* (all )?<verb> ..." -- one or more P<n> tokens then a reporting verb
#   (b) "P<n>'s ... and P<m>'s ... <verb>" -- possessive P<n> tokens joined by "and"
#       (the "verb" here typically lands past the 90-char _norm truncation, e.g. "both
#       demand", so this shape is anchored on the "P<n>'s ... and P<m>'s" join alone,
#       which always survives truncation since it appears early in the sentence).
# Conservative: both require a LITERAL "p<digit>" token, which does not occur in genuine
# gap prose (0DTE/SPY/options text never abbreviates a perspective this way), so
# over-rejection risk is effectively nil.
_ABBREV_PERSPECTIVE_LEADIN_RE = re.compile(
    r"^p\d+(?:s)?"
    r"(?:\s*,?\s*(?:and\s+)?p\d+(?:s)?)*"
    r"\s+(?:all\s+|and\s+)?(?:explicitly\s+|clearly\s+|specifically\s+)?"
    r"(?:flag|flags|note|notes|show|shows|call|calls|demand|demands|warn|warns"
    r"|argue|argues|converge|convergess|rank|ranks|view|views|agree|agrees)\b"
)
_ABBREV_PERSPECTIVE_BOTH_RE = re.compile(r"^p\d+s\b.*\band\s+p\d+s\b")


def _is_real_gap(text: str) -> bool:
    """True if `text` reads like an actionable gap, not model scaffold / a header.

    Rejects (clear noise only): markdown section headers (trailing ':'),
    commit-hash dashbolds, one/two-word headers, and known prompt/template
    section-names echoed back as bold lead-ins. Everything substantive is kept.
    """
    t = (text or "").strip()
    if not t or t.endswith(":"):            # markdown section header
        return False
    if _COMMIT_RE.match(t.replace(" ", "")):  # commit-hash dashbold
        return False
    n = _norm(t)
    if len(n.split()) < 3:                   # 'Overfit' / 'Risk score' / 'Trade missed'
        return False
    if _PERSPECTIVE_REF_RE.match(n):         # 'Perspective(s) 2 flags ...' cross-ref lead-in
        return False
    if _CONSENSUS_LEADIN_RE.match(n):        # 'All perspectives agree that ...' consensus commentary
        return False
    if _ABBREV_PERSPECTIVE_LEADIN_RE.match(n) or _ABBREV_PERSPECTIVE_BOTH_RE.match(n):
        return False                          # 'P1, P2 all flag ...' / "P1's X and P3's Y ..."
    for p in _SCAFFOLD_PREFIXES:
        # multi-word scaffold prefixes match as a true prefix (handles tokens the
        # normalizer fuses, e.g. "pilot/heartbeat" -> "pilotheartbeat"); single-word
        # prefixes require an exact/word-boundary match to avoid over-rejecting.
        if n == p or n.startswith(p + " ") or (" " in p and n.startswith(p)):
            return False
    return True


_NUM_BOLD_LINE_RE = re.compile(r"(?m)^\s*\d+\.\s+\*\*(.+?)\*\*(.*)$")
_DASH_BOLD_LINE_RE = re.compile(r"(?m)^\s*[-*]\s+\*\*(.+?)\*\*(.*)$")
_LEADING_SEP_RE = re.compile(r"^[:\-–—]+\s*")
# Known prompt-template SECTION-NAME labels ("**Role:**", "**Task:**", ...) --
# when the ENTIRE bold span is exactly one of these (colon included), the
# bullet is the model echoing its own prompt skeleton, not a gap, regardless
# of what mundane instruction-restatement text follows on the same line
# ("Formatting: List format as requested. Top 6-8."). Joining full lines
# (2026-08-18 fix below) would otherwise let these survive the trailing-':'
# scaffold check, which only fired when the label was captured bare.
_KNOWN_TEMPLATE_LABELS = {
    "role", "task", "context", "constraints", "formatting", "final polish",
    "specific output format", "drafting the response",
}


def _join_bold_bullet(label: str, rest: str) -> str:
    """Recombine a perspective bold-lead-in bullet with the explanation that
    follows it on the SAME line, instead of keeping only the bold headline.

    2026-08-18 (real observed regression, 4th day running of the SAME
    scaffold-crowding triage class): the old code captured ONLY the text
    inside `**...**` and threw away everything after -- so
    '1. **Implement the watcher scripts** (`order-quality-watcher.py`, ...) as
    lightweight services that publish events to `automation/state/`' flagged
    as the unreadable, contextless fragment 'Implement the watcher scripts'.
    Synthesis bullets got a full-line-capture fix for this exact class back
    on 2026-08-02 (`_strip_bold_label`); perspective numbered/dash bold
    bullets never did, and kept leaking headline-only fragments across the
    2026-08-15/16/17/18 batches (each individually triaged as noise instead
    of the root cause being fixed). NOTE this is intentionally NOT the same
    transform as `_strip_bold_label`: that one DROPS the bold segment because
    it is a meta-label ('Key risk:', 'Most rigorous view:'); here the bold
    segment is usually the finding/action ITSELF, so it is KEPT and the
    trailing explanation is appended, not substituted.
    """
    label = label.strip()
    if label.endswith(":") and label[:-1].strip().lower() in _KNOWN_TEMPLATE_LABELS:
        return ""  # pure template-skeleton label; nothing salvageable
    rest = _LEADING_SEP_RE.sub("", rest.strip())
    return f"{label} {rest}".strip() if rest else label


def _extract_gaps(consult_json: dict) -> list[str]:
    """Pull the ranked gap bullets out of the swarm synthesis + perspectives."""
    # The synthesis + perspective markdown carries numbered/bulleted gaps; grab bold lead-ins
    # and numbered items from the raw perspective text, WITH whatever explanation follows
    # them on the same line (see _join_bold_bullet).
    out = []
    for persp in consult_json.get("perspectives", []):
        body = persp.get("content") or persp.get("text") or ""
        for m in _NUM_BOLD_LINE_RE.finditer(body):
            out.append(_soft_truncate(_join_bold_bullet(m.group(1), m.group(2))))
        for m in _DASH_BOLD_LINE_RE.finditer(body):
            out.append(_soft_truncate(_join_bold_bullet(m.group(1), m.group(2))))
    synth = consult_json.get("synthesis", {})
    sbody = synth.get("content") if isinstance(synth, dict) else str(synth)
    for m in re.findall(r"(?m)^\s*[-*]\s+(.+)$", sbody or ""):
        out.append(_soft_truncate(_strip_bold_label(m)))
    # filter scaffold/headers, then dedupe preserving order (filter BEFORE the [:12]
    # cap so real gaps in later perspectives aren't crowded out by early scaffold)
    seen, ded = set(), []
    for g in out:
        if not _is_real_gap(g):
            continue
        k = _norm(g)
        if k and k not in seen:
            seen.add(k); ded.append(g)
    return ded[:12]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    LOG.parent.mkdir(parents=True, exist_ok=True)
    exe = str(PY) if PY.exists() else sys.executable
    before = {p.name for p in CONSULT_DIR.glob("*.json")} if CONSULT_DIR.exists() else set()
    try:
        subprocess.run([exe, str(SWARM), "audit", "--quiet", "--question", STANDING_QUESTION,
                        "--context", _recent_context()],
                       cwd=str(REPO), timeout=SWARM_SUBPROCESS_TIMEOUT_S, capture_output=True,
                       text=True, creationflags=_CREATE_NO_WINDOW)
    except Exception as e:  # noqa: BLE001
        print(f"self_audit: swarm run failed ({type(e).__name__}: {e})")
        return 0
    new_files = sorted((CONSULT_DIR.glob("*.json")), key=lambda p: p.stat().st_mtime)
    new_files = [p for p in new_files if p.name not in before]
    if not new_files:
        print("self_audit: no swarm output produced (roster may be fully stale)")
        return 0
    consult = json.loads(new_files[-1].read_text(encoding="utf-8"))
    gaps = _extract_gaps(consult)
    known = _known_gap_keys()
    ts = _et_now().strftime("%Y-%m-%dT%H:%M:%S")
    fresh = []
    with LOG.open("a", encoding="utf-8") as f:
        for g in gaps:
            key = hashlib.sha1(_norm(g).encode()).hexdigest()[:12]
            is_new = _norm(g) not in {_norm(x) for x in []} and key not in known
            f.write(json.dumps({"ts_et": ts, "key": key, "gap": g, "new": is_new}) + "\n")
            if is_new:
                fresh.append(g)
    print(f"self_audit {ts}: {len(gaps)} gaps audited, {len(fresh)} NEW")
    for g in gaps:
        print(("  NEW  " if g in fresh else "  seen ") + g[:100])
    if fresh:
        with FLAGS.open("a", encoding="utf-8") as f:
            f.write(f"\n## {ts} -- {len(fresh)} new gap(s) Gamma self-identified\n")
            for g in fresh:
                f.write(f"- {g}\n")
        print(f"  -> flagged {len(fresh)} new to {FLAGS.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
