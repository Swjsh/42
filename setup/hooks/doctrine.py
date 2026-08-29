"""Doctrine tables + pure predicates for the Gamma doctrine hooks.

WHY THIS EXISTS (2026-08-29, J: "I'm tired of it not working"):
CLAUDE.md is delivered as a user message after the system prompt -- Anthropic's own docs
state there is "no guarantee of strict compliance", and that adherence DROPS as the
instruction payload grows ("target under 200 lines per CLAUDE.md file"). The measured
always-on payload on this box is ~19.8K tokens across 15 files. Adding more prose to
CLAUDE.md therefore makes adherence WORSE, not better. Hooks are the enforcement layer:
"Use CLAUDE.md for 'we do it this way here.' Use permissions or hooks for ... anything
that must never happen, where you need a guarantee instead of guidance."

DESIGN CONTRACT (every function here):
  - PURE. No IO, no clock reads, no subprocess. Everything testable offline.
  - The caller (gamma_doctrine.py) owns all IO and owns FAIL-OPEN.
  - Narrow denylists ONLY. A guard that can block general work is an OP-32 lockout
    waiting to happen (the 2026-05-22 market-hours firewall scar). Everything not
    explicitly named is ALWAYS allowed.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Iterable

# --------------------------------------------------------------------------------------
# The prime card -- the ONLY doctrine injected unconditionally.
#
# Written as FACTUAL STATEMENTS, not imperative system commands. Anthropic's guidance:
# "Write the text as factual statements rather than imperative system instructions ...
# Text framed as out-of-band system commands can trigger Claude's prompt-injection
# defenses." J's CLAUDE.md is written in shouted-imperative register (BANNED / MUST /
# NEVER / MANDATORY), which is exactly the register that gets discounted. This card is
# the same doctrine restated as project facts.
# --------------------------------------------------------------------------------------
PRIME_CARD = """\
Project Gamma operating facts (5 that carry the most weight):
1. Sanctioned, reversible, paper-only work ships without asking. A turn that ends in a
   permission-question on sanctioned work is a failed turn; the report shape is "here is
   what I did, revert with `git revert`" (OP-0).
2. "Works / fixed / running / done" is only said alongside a check quoted from this
   session. Unverified findings stay labelled UNVERIFIED (OP-33).
3. Four things route to J and nothing else: arming live money, rotating/exposing a secret,
   an irreversible external action, a genuine fork with no doctrine default.
4. Repo-wide searches start at MAP.md's routing table. 6,777 md files exist; ~479 are
   human-written.
5. Generated surfaces (MAP.md, HOME.md, SHADOW.md, journal dailies, INDEX.md) are written
   by setup/scripts/obsidian_vault_sync.py. The generator is the edit point, not the file.
"""

# --------------------------------------------------------------------------------------
# September config freeze (analysis/deep-research/FABLE-FULL-REVIEW-2026-08-29.md).
# The window exists to give go_live_gate.py 20 clean scoring days. A trading-path edit
# inside it silently invalidates the window -- the single most expensive mistake available
# to any session between these dates.
# --------------------------------------------------------------------------------------
FREEZE_START = dt.date(2026, 8, 31)
FREEZE_END = dt.date(2026, 9, 29)
FREEZE_OVERRIDE_TOKEN = "GAMMA_FREEZE_OVERRIDE"

# The decision+execution path scored by the gate. Suffix-matched against a normalised path.
FROZEN_TRADING_PATH = (
    "automation/state/params.json",
    "automation/state/aggressive/params.json",
    "automation/state/fleet/accounts.json",
    "automation/state/fleet/strategies.py",
    "automation/state/fleet/exit_manager.py",
    "automation/state/fleet/fleet_executor.py",
    "automation/state/fleet/build_shared_signal.py",
    "backtest/lib/filters.py",
    "backtest/lib/risk_gate.py",
    "setup/scripts/heartbeat_core.py",
)

# Written only by obsidian_vault_sync.py. Hand-edits are overwritten on the next sync,
# so an edit here reads as "done" but silently reverts (the OP-22 / Obsidian-brain rule).
GENERATED_SURFACES = ("map.md", "home.md", "shadow.md")
GENERATED_SUFFIXES = ("/index.md",)
GENERATED_GENERATOR = "setup/scripts/obsidian_vault_sync.py"

# --------------------------------------------------------------------------------------
# Bash guards. Each is a scar with a lesson number behind it.
# --------------------------------------------------------------------------------------
BASH_GUARDS = (
    (
        re.compile(r"\bTZ=(?:America/New_York|US/Eastern)\b"),
        "Bash TZ returns UTC on this box (it runs Mountain time), so this reads ~2h wrong. "
        "ET comes from setup/scripts/et_clock.py. Guard: test_et_clock.",
    ),
    (
        re.compile(r"\bgit\s+(?:checkout|restore)\s+\.(?:\s|$)|\bgit\s+reset\s+--hard\b"),
        "Tree-wide git restore in the shared checkout reverts LIVE decision-gating state "
        "backward (L214 / lesson cluster C34). Name the specific paths instead.",
    ),
    (
        re.compile(r"\bgit\s+push\b.*(?:--force|-f)(?:\s|$)"),
        "Force-push to the public Swjsh/42 remote is irreversible and routes to J (OP-0 #3).",
    ),
)

# Turn-ending framings that OP-0 names as the failed-turn shape.
_ASK_PATTERNS = re.compile(
    r"(?:"
    r"(?:do|would)\s+you\s+want\s+me\s+to"
    r"|want\s+me\s+to\b[^?\n]{0,60}\?"
    r"|shall\s+i\b"
    r"|should\s+i\s+(?:go\s+ahead|proceed|start|build|ship|run)"
    r"|let\s+me\s+know\s+if\s+you(?:'|’)?d\s+like"
    r"|your\s+call\b"
    r"|say\s+the\s+word\b"
    r")",
    re.IGNORECASE,
)

# If the turn is a genuine OP-0 escalation, the ask is CORRECT and must not be blocked.
_ESCALATION_MARKERS = re.compile(
    r"(?:live\s+money|arm(?:ing)?\s+(?:the\s+)?live|GAMMA_CORE_ARMED|live:\s*true"
    # A secret mentioned anywhere in the turn makes the ask legitimate (OP-0 #2); do not
    # require it to sit adjacent to the verb ("rotate the OpenRouter secret" must count).
    r"|\bsecrets?\b|\bcredential|\bapi\s+key\b|\btoken\b"
    r"|force[-\s]?push|irreversible"
    r"|OP-0\s*#|NEEDS-J|delete\s+J(?:'|’)?s)",
    re.IGNORECASE,
)

# Claims that require a quoted check in the same turn (OP-33).
_CLAIM_PATTERNS = re.compile(
    r"(?:\bit\s+works\b|\bnow\s+working\b|\bis\s+(?:now\s+)?running\b|\bverified\b"
    r"|\bconfirmed\s+working\b|\ball\s+(?:tests\s+)?pass(?:ing|ed)?\b|\bfixed\s+it\b)",
    re.IGNORECASE,
)

# Prompt keyword -> the ONE rule worth injecting for that turn. Situational beats always-on:
# a rule that arrives when it is relevant is read; a rule that arrives every turn is wallpaper.
PROMPT_ROUTES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        # Boundaries are hand-rolled: \b fails on snake_case (tp1_premium_pct) because "_"
        # is a word char, and \b...\b would miss the plural forms the repo actually uses.
        re.compile(
            r"(?<![a-z0-9])(?:params?|tp1|stop[-_ ]?mode|exits?|filters?|gates?|strikes?|sizing)"
            r"(?![a-z])",
            re.I,
        ),
        "Freeze note: the September scoring window bars trading-path changes except "
        "pre-registered kill-type risk reductions. Shadow/prereg work is unaffected.",
    ),
    (
        re.compile(r"\b(?:push|commit|pr\b|pull request)\b", re.I),
        "Push note: Swjsh/42 is a PUBLIC repo and pushes share the heartbeat's Max pool. "
        "Pushes go outside 09:30-15:55 ET; secrets live only in gitignored .mcp.json.",
    ),
    (
        re.compile(r"\b(?:live|real money|arm|go[- ]live)\b", re.I),
        "Arming note: live-money arming is the one decision that routes to J (OP-0 #1), "
        "measured only by setup/scripts/go_live_gate.py. Paper validation never needs J.",
    ),
    (
        re.compile(r"\b(?:backtest|expectancy|edge|win[- ]?rate|sharpe|PF\b)\b", re.I),
        "Result note: suspicion scales with how good a result looks. The /fable-too-good "
        "artifact hunt runs before an extraordinary number is reported.",
    ),
    (
        re.compile(r"\b(?:why|broke|broken|failing|failed|stuck|debug|root[- ]cause)\b", re.I),
        "Diagnosis note: a fix is a root cause stated in one sentence plus why the change "
        "addresses that mechanism. Re-running a failing action is a loop, not progress.",
    ),
)


def normalise_path(raw: str) -> str:
    """Lowercase, forward-slashed path for suffix matching."""
    return (raw or "").replace("\\", "/").lower()


def freeze_active(today: dt.date) -> bool:
    return FREEZE_START <= today <= FREEZE_END


def frozen_path_hit(file_path: str) -> str | None:
    """Return the matched frozen trading-path entry, or None."""
    norm = normalise_path(file_path)
    if not norm:
        return None
    for entry in FROZEN_TRADING_PATH:
        if norm.endswith(entry):
            return entry
    if re.search(r"automation/state/(?:aggressive/)?params[^/]*\.json$", norm):
        return "automation/state/params*.json"
    return None


def generated_surface_hit(file_path: str) -> str | None:
    """Return the matched generated-surface name, or None."""
    norm = normalise_path(file_path)
    if not norm:
        return None
    base = norm.rsplit("/", 1)[-1]
    if base in GENERATED_SURFACES:
        return base
    for suffix in GENERATED_SUFFIXES:
        if norm.endswith(suffix):
            return base
    if re.search(r"(?:^|/)journal/\d{4}-\d{2}-\d{2}\.md$", norm):
        return base
    return None


_HEREDOC_START = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_heredocs(command: str) -> str:
    """Drop heredoc BODIES, keeping the command lines that open them.

    Caught in the wild 2026-08-29, first live use: this guard denied its own commit
    because the commit message -- passed via `git commit -F - <<'EOF'` -- quoted the
    string `TZ=America/New_York date` while documenting the guard. Heredoc bodies are
    data (commit messages, file content, docs), never commands, so scanning them
    produces false positives on any text that merely *describes* a banned command.
    A guard that blocks writing about itself is a guard that gets torn out.
    """
    lines = command.split("\n")
    kept: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        match = _HEREDOC_START.search(line)
        if match:
            delimiter = match.group(2)
            i += 1
            while i < len(lines) and lines[i].strip() != delimiter:
                i += 1  # body is data -- drop it
        i += 1
    return "\n".join(kept)


def bash_guard_hit(command: str) -> str | None:
    """Return the guard message for a denied shell command, or None."""
    if not command:
        return None
    scanned = strip_heredocs(command)
    for pattern, message in BASH_GUARDS:
        if pattern.search(scanned):
            return message
    return None


def is_permission_question(message: str, tail_chars: int = 400) -> bool:
    """True when the turn ENDS on an OP-0 permission question and is not an escalation."""
    if not message:
        return False
    tail = message[-tail_chars:]
    if not _ASK_PATTERNS.search(tail):
        return False
    return not _ESCALATION_MARKERS.search(message)


# A turn that was ASKED to summarise cannot be expected to re-run its tools. Caught on the
# guard's first day (2026-08-29): it blocked a "tldr" that restated checks already quoted
# earlier in the same session. OP-33 governs NEW claims, not recaps of verified ones.
_RECAP_REQUEST = re.compile(
    r"^\W*(?:tl;?dr|recap|summar(?:y|ise|ize)|shorter|condense|in\s+short|eli5"
    r"|what\s+did\s+you\s+(?:do|change|ship)|explain|why\b|how\s+come)",
    re.IGNORECASE,
)


def is_recap_request(user_prompt: str) -> bool:
    """True when this turn was asked to restate, not to act."""
    text = (user_prompt or "").strip()
    if not text:
        return False
    return bool(_RECAP_REQUEST.match(text)) or len(text) <= 12 and "tldr" in text.lower()


def is_unverified_claim(
    message: str, tool_calls_this_turn: int, user_prompt: str = ""
) -> bool:
    """True when the turn makes a NEW success claim but ran no tool at all (OP-33)."""
    if tool_calls_this_turn > 0:
        return False
    if is_recap_request(user_prompt):
        return False
    return bool(_CLAIM_PATTERNS.search(message or ""))


def route_prompt(prompt: str) -> list[str]:
    """Situational rules for this prompt. Empty list is the common and correct case."""
    if not prompt:
        return []
    return [note for pattern, note in PROMPT_ROUTES if pattern.search(prompt)]


def freeze_banner(today: dt.date, days_left: int | None = None) -> str:
    """One line of freeze state, phrased as a fact."""
    if today < FREEZE_START:
        gap = (FREEZE_START - today).days
        return (
            f"Config freeze opens in {gap}d ({FREEZE_START}). Trading-path changes intended "
            f"for this window land before it opens or wait it out."
        )
    if freeze_active(today):
        left = (FREEZE_END - today).days if days_left is None else days_left
        return (
            f"Config freeze ACTIVE ({FREEZE_START} -> {FREEZE_END}, {left}d left). "
            f"Trading-path edits are blocked; pre-registered kill-type risk reductions are not."
        )
    return f"Config freeze closed {FREEZE_END}. go_live_gate.py scores the window."


def join_notes(notes: Iterable[str]) -> str:
    return "\n".join(f"- {n}" for n in notes)
