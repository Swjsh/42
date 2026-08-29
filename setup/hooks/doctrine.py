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
import posixpath
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
    (
        re.compile(r"\bGAMMA_CORE_ARMED\s*=\s*['\"]?1\b"),
        "Setting GAMMA_CORE_ARMED=1 arms LIVE money -- OP-0 #1, the one thing that always "
        "routes to J. A Bash/PowerShell export cannot do this on J's behalf; name the "
        "escalation and stop instead of exporting it.",
    ),
    (
        re.compile(
            r"\brm\s+(?:-[a-zA-Z]*[rR][a-zA-Z]*[fF][a-zA-Z]*\b"
            r"|-[a-zA-Z]*[fF][a-zA-Z]*[rR][a-zA-Z]*\b"
            r"|--recursive\b(?:[^\n;&|]*)--force\b"
            r"|--force\b(?:[^\n;&|]*)--recursive\b)"
            r"[^\n;&|]{0,80}\bautomation[\\/]state\b"
        ),
        "rm -rf against automation/state deletes live decision-gating state (params, "
        "pulse log, active-goal, kill-switches) -- the same class of harm as a tree-wide "
        "git reset (lesson cluster C34). Delete the specific stale file by name instead.",
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
    """Lowercase, forward-slashed, dot/slash-collapsed path for suffix matching.

    Two aliasing primitives get folded into the same string the OS will actually
    touch, otherwise a frozen/generated path can be spelled a second way that a raw
    suffix comparison misses while the write still lands on the real file:
      * "." / ".." segments and doubled separators resolve away on any real
        filesystem access (`a/b/../c` and `a/c` are the same file) -- collapsed
        with posixpath.normpath before comparison.
      * a trailing run of "." and/or " " is silently stripped by the Win32 path
        layer this box's tools ultimately call (verified empirically 2026-08-29:
        writing through "x.txt." or "x.txt " mutates "x.txt" itself) -- stripped
        after normpath so only the Windows-quirk trailing run is affected, never a
        meaningful ".."/"." segment earlier in the path.
    """
    norm = (raw or "").replace("\\", "/").lower()
    if not norm:
        return ""
    norm = posixpath.normpath(norm)
    stripped = norm.rstrip(". ")
    return stripped if stripped else norm


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


def strip_quoted_strings(command: str) -> str:
    """Blank the CONTENTS of quoted string literals, keeping quotes and structure.

    Regression (2026-08-29, caught live testing this very hook): the guard blocked
    `echo '{"command":"git push --force origin main"}'` -- a fixture being built for
    a test, never executed -- because the banned phrase sat verbatim inside a quoted
    string. Same principle as strip_heredocs above: a git commit message (`-m "..."`),
    an echoed/printf'd sentence, or a JSON string literal is DATA, not a command run
    by the shell, and must not trip a guard meant for commands actually executed.

    Bash-only quoting rules: single quotes are fully literal (no escapes possible
    inside them); double quotes honour a backslash escape. An unterminated quote
    blanks to the end of the string rather than raising -- a malformed shell
    fragment fails toward "not a command", the same fail-open direction as every
    other guard in this module.

    Known, accepted trade-off: a command deliberately smuggled entirely inside
    quotes (e.g. `bash -c 'git push --force origin main'`) is no longer caught by
    this narrow footgun guard. That is intentional under this module's own
    contract -- "Denylists are NARROW... a guard that can block general work is
    an OP-32 lockout scar waiting to happen" -- and the false-positive block this
    fixes was actively happening, not hypothetical, while the quote-wrapped-evasion
    case is not the failure mode this guard exists to catch (see OP-0 for the real
    backstop on irreversible actions).
    """
    out: list[str] = []
    i = 0
    n = len(command)
    while i < n:
        ch = command[i]
        if ch == "'":
            out.append(ch)
            i += 1
            while i < n and command[i] != "'":
                out.append(" ")
                i += 1
            if i < n:
                out.append(command[i])
                i += 1
        elif ch == '"':
            out.append(ch)
            i += 1
            while i < n and command[i] != '"':
                if command[i] == "\\" and i + 1 < n:
                    out.append(" ")
                    i += 1
                out.append(" ")
                i += 1
            if i < n:
                out.append(command[i])
                i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def bash_guard_hit(command: str) -> str | None:
    """Return the guard message for a denied shell command, or None."""
    if not command:
        return None
    scanned = strip_quoted_strings(strip_heredocs(command))
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


# --------------------------------------------------------------------------------------
# Goal continuation (Stop hook, third clause) -- automation/state/active-goal.json.
#
# Three independent brakes are the WHOLE safety argument here (SPEC.md section 6):
#   1. payload["stop_hook_active"] -- handled entirely by the caller, before any of
#      this runs. Never chains within a single continuation.
#   2. a hard per-session counter (goal_should_continue's continuations_so_far/max).
#   3. a convergence stop -- an item identical to the one named at the LAST block
#      means that continuation did not move the goal, so continuing again would
#      loop rather than help. Same no-op logic as run-gamma-drive.ps1's
#      Test-OutcomeNoop, restated for a single field instead of a metrics row.
# All three are pure here; the caller owns the clock, the files, and FAIL OPEN.
# --------------------------------------------------------------------------------------
DEFAULT_MAX_CONTINUATIONS = 3

_QUEUE_OPEN_ITEM = re.compile(r"^-\s*\[ \]\s*(.+?)\s*$")
# Any ATX heading level (# through ######), not just "##" -- a goal file's
# `## QUEUE` heading typo'd to a different level (H1 `# QUEUE`, H3 `### QUEUE`)
# previously matched NO heading at all, so `in_queue` never turned on and
# goal_next_open_item silently returned None even with real open items below
# it -- the same silent-scope-boundary failure class as task_scorer.py's
# _active_lines heading bug (C7 / L245-L246). Matching any level here is safe:
# the goal schema (SKILL.md) never nests a "###" sub-heading inside QUEUE, so
# widening the level can only ever RECOGNIZE a heading that this narrower
# pattern used to miss, never mis-fire on QUEUE body content.
_HEADING_LINE = re.compile(r"^\s*#{1,6}\s+(.*)$")


def goal_next_open_item(goal_md: str | None) -> str | None:
    """First unchecked `- [ ]` line under the `## QUEUE` heading, or None.

    Only the bare `[ ]` marker counts as open -- `[~]` (wip), `[x]` (done), and
    `[B]`/`[B-J]` (blocked) are deliberately excluded, matching the goal schema
    (SPEC.md section 5). A blocked item must never keep re-triggering a
    continuation; that is what the B/B-J markers exist to prevent.
    """
    in_queue = False
    for line in (goal_md or "").splitlines():
        heading = _HEADING_LINE.match(line)
        if heading:
            in_queue = heading.group(1).strip().upper().startswith("QUEUE")
            continue
        if not in_queue:
            continue
        m = _QUEUE_OPEN_ITEM.match(line)
        if m:
            return m.group(1).strip()
    return None


def goal_expired(expires_at_et: str | None, now_et: dt.datetime) -> bool:
    """True when the goal's expiry has passed, or its expiry can't be read.

    A malformed or unparseable expiry fails toward "treat as expired" (i.e. allow
    the stop) rather than "block forever" -- same fail-open direction as every
    other guard in this module. An EMPTY expiry means "no expiry was set" and is
    the one case that does NOT count as expired.
    """
    raw = (expires_at_et or "").strip()
    if not raw:
        return False
    try:
        if len(raw) == 10:  # "YYYY-MM-DD" -- expires at end of that day
            exp = dt.datetime.strptime(raw, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        else:
            exp = dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        return now_et > exp
    except Exception:
        return True


def goal_max_continuations(goal: dict) -> int:
    """The per-session continuation budget from active-goal.json, or the default.

    Any non-positive or non-int value (missing key, 0, negative, a string) falls
    back to DEFAULT_MAX_CONTINUATIONS -- a malformed budget must never mean
    "unlimited continuations".
    """
    raw = goal.get("max_continuations_per_session")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        return DEFAULT_MAX_CONTINUATIONS
    return raw


def goal_should_continue(
    item: str | None,
    last_next_item: str | None,
    continuations_so_far: int,
    max_continuations: int,
) -> bool:
    """Brakes 2 and 3 together. True only when there is an open item, the
    session hasn't spent its continuation budget, and that item is not a
    repeat of the one the last block already named."""
    if not item:
        return False
    if continuations_so_far >= max_continuations:
        return False
    if last_next_item and item == last_next_item:
        return False
    return True


def goal_continuation_reason(goal_id: str, item: str, goal_file: str, n: int, max_n: int) -> str:
    """The Stop-block message: names the item, tells the session what to do next."""
    return (
        f"Goal {goal_id} still has open work. Next item: {item}. Do it, then append one "
        f"PROGRESS LOG line to {goal_file}, record the outcome via "
        f"`python setup/scripts/conductor_outcome.py record ...`, then stop. "
        f"Continuation {n}/{max_n}."
    )
