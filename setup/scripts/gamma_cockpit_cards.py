"""gamma_cockpit_cards.py - Action Cards: the cockpit's ranked "what should I

fire next" surface, generated deterministically -- no LLM anywhere in this
file (WHY: this module decides what an escalated Claude gets TOLD to do, and
a card generator that itself calls an LLM to decide that is the fabrication
risk this whole cockpit exists to close).

RANKING IS NOT INVENTED HERE (spec: scratchpad/SPEC.md sec 4). It mirrors the
conductor's own STAGE 1 priority order verbatim -- reusing task_scorer.py's
ranker for source 3 rather than writing a second one:
  0. automation/state/active-goal.json     -- the goal's next '- [ ]' item.
                                               ALWAYS prepended as rank 1 when
                                               present+unexpired (2026-08-29
                                               goal-to-card linkage fix): the
                                               loop's own next step must never
                                               be outranked by anything below.
  1. automation/state/engine-health.json   -- any critical check not GREEN
  2. automation/overnight/STATUS.md        -- '## Known broken' / '### BROKEN:'
  3. task_scorer.rank()                    -- top 3 ready backlog items
  4. gamma_cockpit_army sessions[].context_pct -- any session > 85% of its
                                               autoCompactWindow (never when
                                               context_source == "unknown")
  5. automation/state/unattended-health.json -- RED/YELLOW units

QUIET-MODE IS READ FIRST (the #1 false-alarm source per the spec). When
quiet_active is true, a scheduled task that quiet-mode itself disabled reads
RED/YELLOW in unattended-health.json for a reason that has nothing to do with
it being broken. Any problem line attributable to a task named in
quiet-mode-restore.json's `restore_to_ready` list is filtered out before a
card is ever built from it -- never surfaced, never counted, never RED.

SAFETY (spec sec 4, "Security notes"): every card carries a `prompt` that an
approved fire hands straight to a headless Claude session (gamma-companion's
runEscalation -> Agent SDK). The only untrusted ingredients in that prompt are
substrings pulled from state files this module does not control (STATUS.md,
queue.md, unattended-health.json...) -- a compromised or buggy producer could
in principle write something like "set GAMMA_CORE_ARMED=1" into one of those
files. _looks_dangerous() scans exactly that untrusted material (never the
static safety footer this module authors itself) and the card is DROPPED,
not sanitised, on a hit. Belt-and-suspenders with guard.js's own DENY_WRITE/
DENY_TOOL at the SDK boundary (gamma-companion/lib/guard.js) -- this is the
generation-time gate, that is the execution-time gate.

Nothing here ever writes automation/state/action-cards.json with a card whose
prompt could arm live money, touch a secret, or take an irreversible external
action. Every failure degrades to fewer cards, never a crash -- this module
must never be the reason the cockpit page fails to build.

AUTOFIRE SAFETY (2026-08-29, the field the auto-fire runner depends on): every
card also carries `autofire_safe` (bool) + `autofire_reason` (str). Default is
FALSE -- a card the classifier cannot confidently place is not safe. TRUE is
reserved for cards whose objective is unambiguously READ-AND-REPORT
(investigate/measure/audit/check/summarise) with no action verb anywhere in
the card's own text. Unconditionally FALSE, regardless of verb, when the
card's untrusted text mentions live arming, a secret, or an irreversible
external action, or when it touches the frozen trading path during the
2026-08-31 -> 2026-09-29 config freeze (doctrine.freeze_active /
doctrine.FROZEN_TRADING_PATH). See _autofire_classification().
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))  # sibling imports below (setup/scripts)
sys.path.insert(0, str(_SCRIPTS_DIR.parent / "hooks"))  # setup/hooks -- doctrine.py

import et_clock  # noqa: E402  -- the ONE DST-aware ET source (never Bash TZ=...)
import task_scorer  # noqa: E402  -- the ONE backlog ranker (never re-derive ROI here)
import gamma_cockpit_army  # noqa: E402  -- source of sessions[].context_pct for the context-alarm cards
import doctrine  # noqa: E402  -- setup/hooks/doctrine.py: REUSED verbatim (not re-parsed) for
                  # goal_next_open_item/goal_expired (goal-to-card linkage) and
                  # freeze_active/FROZEN_TRADING_PATH (autofire classification)

ENGINE_HEALTH_JSON = STATE / "engine-health.json"
UNATTENDED_HEALTH_JSON = STATE / "unattended-health.json"
QUIET_MODE_JSON = STATE / "quiet-mode.json"
QUIET_MODE_RESTORE_JSON = STATE / "quiet-mode-restore.json"
ACTIVE_GOAL_JSON = STATE / "active-goal.json"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
ACTION_CARDS_JSON = STATE / "action-cards.json"

MODEL = "sonnet"  # Model routing (CLAUDE.md #1): grunt-work escalations are Sonnet's job.

# Per-source caps keep the view a short, skimmable list even on a bad night --
# an unbounded card feed just becomes a second STATUS.md nobody reads either.
MAX_STATUS_CARDS = 3
MAX_TASK_CARDS = 3
MAX_UNIT_CARDS = 4

_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)")


# --------------------------------------------------------------------- safety

# Patterns that must NEVER survive into a fired prompt's UNTRUSTED half (the
# state-derived title/why text -- see _looks_dangerous docstring). Deliberately
# broad: a false-positive here just costs one dropped card, a false-negative
# risks the exact class of harm OP-0's "four things route to J" exists to fence.
_DENY_PATTERNS = [
    (re.compile(r"GAMMA_CORE_ARMED", re.I), "live-arm env var"),
    (re.compile(r'"?live"?\s*[:=]\s*true', re.I), "fleet live:true flag"),
    (re.compile(r"\b(place|cancel|close|replace|exercise|do_not_exercise)[_ ]"
                r"(option|options|stock|crypto)?[_ ]?order", re.I), "live order verb"),
    (re.compile(r"exercise_options_position", re.I), "live order verb"),
    (re.compile(r"\brotate\b[^\n]{0,24}\b(key|secret|token)\b", re.I), "secret rotation"),
    (re.compile(r"\.vapid\.json|push-subscriptions\.json|\.approve-hmac\.key", re.I), "push secret file"),
    (re.compile(r"[\w./\\-]+\.key\b", re.I), "a *.key credential file"),
    (re.compile(r"git\s+push\s+(--force|-f)\b", re.I), "force-push"),
    (re.compile(r"\brm\s+-rf\b", re.I), "recursive delete"),
]


def _looks_dangerous(untrusted_text: str) -> str | None:
    """Return a human label for the FIRST denylist hit, else None.

    Scans only the interpolated state-derived text (title + why bullets), never
    the static safety footer this module writes itself -- that footer legitimately
    NAMES these same banned actions in order to prohibit them, which would
    otherwise self-trigger every single card.
    """
    for pat, label in _DENY_PATTERNS:
        if pat.search(untrusted_text):
            return label
    return None


# ----------------------------------------------------------- autofire safety
#
# _looks_dangerous() (above) is a narrow, syntax-specific denylist -- it drops
# a card outright on a hit. This classifier is broader on purpose: it also
# catches a card that merely TALKS ABOUT live arming / a secret / an
# irreversible action without matching one of the specific command shapes
# above, and it is the thing that decides whether the auto-fire runner may
# dispatch a SURVIVING card without a human looking at it first. Same scoping
# rule as _looks_dangerous: runs ONLY on the untrusted, state-derived text
# (title/why/objective/done_when + source_path), never the static safety
# footer -- the footer legitimately NAMES "live arming"/"secret"/
# "irreversible" in order to prohibit them, which would otherwise mark every
# card unsafe for the wrong reason.

_READ_ONLY_VERBS = ("investigate", "measure", "audit", "check", "summarise", "summarize")

# Any of these appearing ANYWHERE in the card's own text means the work is not
# purely read-and-report -- the objective's opening verb alone is not trusted,
# because a "check X" objective whose `why`/`done_when` also says "then update
# the file" is not actually a read-only card.
_ACTION_VERB_RE = re.compile(
    r"\b("
    r"edit|edits|editing|change|changes|changing|commit|commits|committing|"
    r"resolve|resolves|resolving|restore|restores|restoring|fix|fixes|fixing|"
    r"drain|drains|draining|complete|completes|completing|update|updates|updating|"
    r"modify|modifies|modifying|write|writes|writing|apply|applies|applying|"
    r"ship|ships|shipping|revert|reverts|reverting|delete|deletes|deleting|"
    r"create|creates|creating|arm|arms|arming|rotate|rotates|rotating|"
    r"place|places|placing|cancel|cancels|cancelling|canceling|close|closes|closing|"
    r"replace|replaces|replacing|exercise|exercises|exercising|push|pushes|pushing|"
    r"merge|merges|merging|deploy|deploys|deploying|kill|kills|killing|"
    r"restart|restarts|restarting|mark|marks|marking|set"
    r")\b", re.I,
)

_LIVE_ARM_MENTION_RE = re.compile(
    r"\blive\b[^\n.;]{0,30}\barm\w*|\barm\w*[^\n.;]{0,30}\blive\b|"
    r"GAMMA_CORE_ARMED|\blive\s*:\s*true\b|\blive[- ]money\b|\blive\s+order\b",
    re.I,
)
_SECRET_MENTION_RE = re.compile(
    r"\bsecret(s)?\b|\bcredential(s)?\b|\bapi[- ]?key(s)?\b|\.key\b|\btoken(s)?\b|"
    r"\bpassword(s)?\b|\.vapid\.json|push-subscriptions\.json",
    re.I,
)
_IRREVERSIBLE_MENTION_RE = re.compile(
    r"\birreversible\b|force[- ]push|\bgit\s+push\b|\brm\s+-rf\b|\bpermanently\s+delete\b",
    re.I,
)


def _autofire_classification(title: str, why: list[str], objective: str, done_when: str,
                              source_path: str, today: date | None = None) -> tuple[bool, str]:
    """(autofire_safe, autofire_reason) for one card. Default is FALSE.

    TRUE only when ALL of:
      - none of the three unconditional-false triggers below hit, AND
      - the (freeze-window, frozen-path) trigger below misses, AND
      - `objective` opens on a read-only verb (investigate/measure/audit/
        check/summarise), AND
      - no action verb (edit/change/commit/fix/arm/place/push/...) appears
        ANYWHERE in title/why/objective/done_when.

    `today` is injectable for tests; defaults to the real ET calendar date.
    """
    text = " ".join([title, " ".join(why), objective, done_when])

    if _LIVE_ARM_MENTION_RE.search(text):
        return False, "prompt mentions live arming -- unconditionally unsafe to auto-fire."
    if _SECRET_MENTION_RE.search(text):
        return False, "prompt mentions a secret/credential -- unconditionally unsafe to auto-fire."
    if _IRREVERSIBLE_MENTION_RE.search(text):
        return False, "prompt mentions an irreversible external action -- unconditionally unsafe to auto-fire."

    if today is None:
        today = date.fromisoformat(et_clock.et_today_str())
    if doctrine.freeze_active(today):
        frozen_hit = doctrine.frozen_path_hit(source_path)
        if not frozen_hit:
            text_l = text.lower()
            for entry in doctrine.FROZEN_TRADING_PATH:
                base = entry.rsplit("/", 1)[-1]
                if entry.lower() in text_l or base.lower() in text_l:
                    frozen_hit = entry
                    break
        if frozen_hit:
            return False, (
                "on the frozen trading path (%s) during the %s -> %s config freeze -- "
                "unconditionally unsafe to auto-fire." % (frozen_hit, doctrine.FREEZE_START, doctrine.FREEZE_END)
            )

    objective_l = _clean(objective).lower()
    if not any(objective_l.startswith(v) for v in _READ_ONLY_VERBS):
        return False, (
            "objective is not a read-and-report action (investigate/measure/audit/check/"
            "summarise) -- default is unsafe."
        )
    if _ACTION_VERB_RE.search(text):
        return False, (
            "objective opens read-only but an action verb (edit/change/commit/fix/...) "
            "still appears in the card text -- default is unsafe when the classifier "
            "cannot confidently place it."
        )
    return True, (
        "objective is read-and-report only (investigate/measure/audit/check/summarise) "
        "with no action verb anywhere in the card -- safe to auto-fire."
    )


# -------------------------------------------------------------------- helpers

def _clean(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _clip(s, cap: int = 200) -> str:
    s = _clean(s)
    if len(s) <= cap:
        return s
    cut = s[:cap].rsplit(" ", 1)[0].rstrip(",;:.-")
    return (cut or s[:cap]) + "…"


def _load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _age_h(p: Path):
    try:
        return (datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)).total_seconds() / 3600.0
    except OSError:
        return None


def _rel(p: Path) -> str:
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return str(p)


_SAFETY_FOOTER = (
    "\n\nBOUNDARIES (non-negotiable, not a suggestion):\n"
    "- CONFIG FREEZE 2026-08-31 -> ~2026-09-29 (automation/overnight/STATUS.md "
    "'## Known broken' banner, verbatim): \"no trading-path changes after Monday's "
    "open except pre-registered kill-type risk reductions -- the window exists to "
    "give the gate 20 clean days to score.\" Never touch automation/state/params*.json, "
    "backtest/lib/filters.py, backtest/lib/risk_gate.py, automation/state/fleet/*.py, "
    "or setup/scripts/heartbeat_core.py for the duration of that window.\n"
    "- NO LIVE ARMING: never set GAMMA_CORE_ARMED or a fleet live:true flag. Never "
    "place, cancel, close, replace, or exercise a live Alpaca order. Paper/shadow "
    "changes never need J; arming live money is one of the only four things that do "
    "(CLAUDE.md OP-0).\n"
    "- NO SECRETS: never rotate, print, or read a *.key / .vapid.json / "
    "push-subscriptions.json secret, and never hardcode or echo a credential.\n"
    "- NO PUSH DURING MARKET HOURS: never `git push` between 09:30-15:55 ET -- that "
    "window shares the Max subscription pool with the live heartbeat and a push can "
    "starve a tick. After-hours push is fine; committing locally is always fine.\n"
    "- NO OTHER IRREVERSIBLE ACTION: never `git push --force`, never recursively "
    "delete anything.\n\n"
    "MODEL ROUTING (2026-07-23 scar, cost-verified): if this fire spawns ANY "
    "sub-agent or Workflow agent() call, pass model=\"sonnet\" explicitly on every "
    "single call site. An in-prompt instruction telling a spawned session to run "
    "\"/model sonnet\" first is a NO-OP -- subagents cannot switch their own model. "
    "An 11-agent matrix workflow that relied on that in-prompt instruction instead of "
    "pinning the tier inherited the parent's top-tier model and burned 2.2M tokens on "
    "mechanical grid work. If you are reading this prompt as the orchestrator itself "
    "and your own model tier exceeds sonnet, that is a routing mismatch worth noting "
    "in your report, not a reason to stop.\n\n"
    "VERIFICATION: name the root cause in one sentence before fixing "
    "(setup/hooks/gamma_doctrine.py, CLAUDE.md OP-33). Apply the smallest correct "
    "change -- no drive-by refactors. Verify with a freshly-run command and quote its "
    "output; do not claim 'fixed', 'done', or 'works' on anything you did not verify "
    "this session.\n\n"
    "RECORD THE OUTCOME: when you stop (shipped, blocked, or determined no action "
    "needed), run `setup/scripts/conductor_outcome.py record --task-id %(card_id)s "
    "--note \"<one line: what happened>\"` (see that script's own --help for the full "
    "flag set) so this fire counts toward the conductor's net-improvement metric -- an "
    "outcome that is not recorded does not count as done."
)


def _prompt(card_id: str, objective: str, why: list[str], source_path: str,
            done_when: str) -> str:
    """Build a complete, self-contained brief. A fresh orchestrator session with
    NO other context must be able to act on this alone: what to accomplish, the
    exact evidence that surfaced it (quoted, with its source file), how to know
    the work is actually finished, and the hard boundaries it may never cross."""
    why_lines = "\n".join(
        '- "%s" (from %s)' % (w, source_path) for w in why
    )
    body = (
        "OBJECTIVE: %s\n\n"
        "WHY THIS CARD FIRED (evidence, quoted verbatim from the source file):\n"
        "%s\n\n"
        "DONE-WHEN (this work is finished ONLY when this is true, and you have "
        "quoted the fresh check that proves it):\n"
        "%s\n"
    ) % (objective, why_lines, done_when)
    footer = _SAFETY_FOOTER % {"card_id": card_id}
    return body + footer


def _card(card_id: str, title: str, why: list[str], source_path: str,
          source_age_h, objective: str | None = None, done_when: str | None = None,
          gated: bool = False) -> dict | None:
    """The one constructor every source below funnels through -- the single
    point where the denylist actually runs, so no source can bypass it.

    `objective` and `done_when` are optional so existing/ad-hoc callers (and
    the guard tests) keep working with a sane fallback derived from title/why;
    every real source below passes both explicitly."""
    objective = objective or ("Resolve the condition described in: %s" % title)
    done_when = done_when or (
        "The condition described in the title above no longer holds, verified by "
        "re-reading %s fresh and quoting the changed state." % source_path
    )
    # Scan EVERY untrusted, state-derived field -- title, why, AND the two new
    # fields, since objective/done_when are themselves built from title/why by
    # the call sites below and can carry the same injected substrings.
    untrusted = " ".join([title, " ".join(why), objective, done_when])
    hit = _looks_dangerous(untrusted)
    if hit:
        print("WARN: dropped card %s -- denylist hit (%s)" % (card_id, hit), file=sys.stderr)
        return None
    autofire_safe, autofire_reason = _autofire_classification(
        title, why, objective, done_when, source_path)
    return {
        "id": card_id,
        "rank": 0,  # assigned by build_cards() once every source has contributed
        "title": _clip(title, 140),
        "why": [_clip(w, 200) for w in why][:4],
        "source_path": source_path,
        "source_age_h": round(source_age_h, 2) if isinstance(source_age_h, (int, float)) else None,
        "model": MODEL,
        "gated": bool(gated),
        "autofire_safe": autofire_safe,
        "autofire_reason": _clip(autofire_reason, 220),
        "prompt": _prompt(card_id, _clip(objective, 400), why, source_path, _clip(done_when, 400)),
    }


# ------------------------------------------------------- source 1: engine health

def _cards_engine_health() -> list[dict]:
    data = _load_json(ENGINE_HEALTH_JSON)
    if not isinstance(data, dict):
        return []
    age = _age_h(ENGINE_HEALTH_JSON)
    checked_at = data.get("checked_at_et", "")
    out = []
    for chk in data.get("checks") or []:
        if not isinstance(chk, dict) or not chk.get("critical"):
            continue
        status = str(chk.get("status", "")).upper()
        if status == "GREEN":
            continue
        name = str(chk.get("name", "check"))
        c = _card(
            card_id="card-engine-%s" % re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
            title="%s is %s" % (name, status),
            why=[_clip(chk.get("detail", "")), "engine-health.json checked_at_et %s" % checked_at],
            source_path=_rel(ENGINE_HEALTH_JSON),
            source_age_h=age,
            objective="Restore the critical engine-health.json check '%s' to GREEN "
                      "(it currently reads %s)." % (name, status),
            done_when="Re-run `python setup/scripts/engine_health.py`, re-read the fresh "
                      "automation/state/engine-health.json, and quote the line for check "
                      "'%s' showing status GREEN." % name,
        )
        if c:
            out.append(c)
    return out


# ------------------------------------------------------------ source 2: STATUS.md

def _parse_ts(s: str):
    m = _TS_RE.search(s or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + " " + m.group(2)[:5], "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _status_md_entries(text: str) -> list[dict]:
    """Every '## Known broken' bracket bullet + every '### BROKEN:' block's
    bullets, each as {text, ts (datetime|None)}. DEGRADED headers are excluded
    on purpose -- conductor_wake_watch.py's own doctrine (same repo) treats
    DEGRADED as "reads unwell, not urgent"; only BROKEN and the bracket-style
    Known-broken lines are load-bearing enough for a fire-me card."""
    entries: list[dict] = []

    idx = text.find("## Known broken")
    if idx != -1:
        nxt = text.find("\n## ", idx + 1)
        section = text[idx: nxt if nxt != -1 else len(text)]
        for line in section.splitlines():
            s = line.strip()
            if s.startswith("- [") and not s.startswith("### "):
                entries.append({"text": s.lstrip("- ").strip(), "ts": _parse_ts(s)})

    for m in re.finditer(r"^### BROKEN:\s*(.*)$", text, re.MULTILINE):
        header_ts = _parse_ts(m.group(1))
        block_start = m.end()
        block_end = text.find("\n\n", block_start)
        block_end = block_end if block_end != -1 else min(len(text), block_start + 4000)
        block = text[block_start:block_end]
        for line in block.splitlines():
            s = line.strip()
            if s.startswith("- "):
                entries.append({"text": s[2:].strip(), "ts": header_ts})

    # De-dupe (the same bug is sometimes logged by two writers) and sort newest
    # first; entries with no parseable timestamp sort after every dated one.
    seen: set[str] = set()
    uniq = []
    for e in entries:
        if e["text"] in seen:
            continue
        seen.add(e["text"])
        uniq.append(e)
    uniq.sort(key=lambda e: e["ts"] or datetime.min, reverse=True)
    return uniq


def _cards_status_md() -> list[dict]:
    try:
        text = STATUS_MD.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    entries = _status_md_entries(text)[:MAX_STATUS_CARDS]
    file_age = _age_h(STATUS_MD)
    out = []
    for i, e in enumerate(entries):
        # STATUS.md timestamps are ET; this box's local clock is Mountain (ET-2h,
        # CLAUDE.md's own TZ-SYSTEMIC scar) -- subtracting a naive local now() from
        # a naive ET timestamp produced a NEGATIVE age (caught live 2026-08-29: a
        # 16:19:48 ET entry read as -0.08h "in the future" against a Mountain-time
        # now()). et_clock.et_now() is the one DST-aware ET source; never datetime.now() here.
        age = (et_clock.et_now() - e["ts"]).total_seconds() / 3600.0 if e["ts"] else file_age
        title = _clip(e["text"].split(" -- ", 1)[0].split(" :: ", 1)[0], 120)
        c = _card(
            card_id="card-broken-%d-%s" % (i, re.sub(r"[^a-z0-9]+", "-", title.lower())[:40].strip("-")),
            title=title,
            why=[_clip(e["text"], 260)],
            source_path=_rel(STATUS_MD),
            source_age_h=age,
            objective="Root-cause and resolve the STATUS.md entry '%s' so it no longer "
                      "reads as broken." % title,
            done_when="Re-read %s fresh: either the exact bullet quoted above is gone "
                      "from '## Known broken' / the '### BROKEN:' block, or it has been "
                      "edited in place to record the verified fix and the commit that "
                      "made it. Quote the updated section." % _rel(STATUS_MD),
        )
        if c:
            out.append(c)
    return out


# --------------------------------------------------------- source 3: task_scorer

def _task_description(text: str, task_id: str) -> str:
    for line in text.splitlines():
        m = task_scorer.ITEM_RE.match(line.strip())
        if m and m.group("id") == task_id:
            return m.group("rest")
    return ""


def _cards_task_scorer() -> list[dict]:
    text = task_scorer.load_queue_text()
    if text is None:
        return []
    ranked = task_scorer.rank(text, include_blocked=False)[:MAX_TASK_CARDS]
    if not ranked:
        return []
    advisory = task_scorer.staleness_advisory(ranked)
    age = _age_h(task_scorer.QUEUE)
    out = []
    for i, t in enumerate(ranked):
        desc = _clip(_task_description(text, t.id), 220)
        why = [desc] if desc else []
        why.append("task_scorer: priority %s, score %.1f -- %s" % (t.priority, t.score, t.reason))
        if i == 0 and advisory:
            why.append(_clip(advisory, 200))
        c = _card(
            card_id="card-task-%s" % re.sub(r"[^a-z0-9]+", "-", t.id.lower()).strip("-"),
            title=t.id.replace("-", " ").title(),
            why=why,
            source_path=_rel(task_scorer.QUEUE),
            source_age_h=age,
            objective="Drain backlog item '%s' (%s): %s" % (t.id, t.priority, desc or t.id),
            done_when="Per queue.md's own header convention, the '- [ ] %s (...)' line is "
                      "moved out of the active backlog into '## Completed' (or its "
                      "':: status:' field is updated to reflect the outcome) in a fresh "
                      "read of %s. Quote the updated line." % (t.id, _rel(task_scorer.QUEUE)),
        )
        if c:
            out.append(c)
    return out


# ------------------------------------------------------------- source 0: goal
#
# ALWAYS prepended as rank 1 by build_cards() when it fires -- see that
# function. Parsing is REUSED (imported), not re-derived: goal_next_open_item
# and goal_expired both come straight from setup/hooks/doctrine.py, the same
# functions the Stop-hook continuation logic runs on. Writing a second parser
# here would risk the two readers of active-goal.json/the goal .md silently
# disagreeing about what "the next open item" or "expired" means.

def _cards_active_goal() -> list[dict]:
    goal = _load_json(ACTIVE_GOAL_JSON)
    if not isinstance(goal, dict) or not goal.get("active"):
        return []
    if doctrine.goal_expired(goal.get("expires_at_et"), et_clock.et_now()):
        return []  # expired -- not this fire's job to resurrect it
    goal_file = REPO / str(goal.get("file", ""))
    try:
        text = goal_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    item = doctrine.goal_next_open_item(text)
    if not item:
        return []
    goal_id = str(goal.get("id", "?"))
    c = _card(
        card_id="card-goal-%s" % re.sub(r"[^a-z0-9]+", "-", goal_id.lower()).strip("-"),
        title="Goal %s: %s" % (goal_id, _clip(item, 90)),
        why=[_clip(item, 260),
             "next open '- [ ]' item in the goal's own QUEUE (doctrine.goal_next_open_item)"],
        source_path=_rel(goal_file),
        source_age_h=_age_h(goal_file),
        objective="Complete the next open step of goal %s: %s" % (goal_id, _clip(item, 300)),
        done_when="Re-read %s: the exact line '- [ ] %s' is changed to '- [x] %s' (or "
                  "otherwise recorded as done per the goal file's own convention). Quote "
                  "the updated line." % (_rel(goal_file), _clip(item, 150), _clip(item, 150)),
        gated=False,  # a literal '- [ ]' item is by construction not '[B]'/'[B-J]' blocked
    )
    return [c] if c else []


# ------------------------------------------------------ source 4: context alarm
#
# gamma_cockpit_army.build_army() already computes sessions[].context_pct
# (verified live 2026-08-29: two sessions at 88%/90% of the 800000
# autoCompactWindow). A session over CONTEXT_ALARM_PCT is a thing to ACT on --
# close it, or let it compact -- not a colour on a bar nobody reads.
#
# HONESTY (mirrors gamma_cockpit_army's own contract verbatim): NEVER emit a
# card when context_source == gamma_cockpit_army.CONTEXT_UNKNOWN. An alarm
# computed from a number that could not be computed is worse than no alarm.

CONTEXT_ALARM_PCT = 85.0
MAX_CONTEXT_CARDS = 3


def _cards_context_alarm(army_payload: dict | None = None) -> list[dict]:
    if army_payload is None:
        try:
            army_payload = gamma_cockpit_army.build_army()
        except Exception as e:  # noqa: BLE001 - this source must degrade, never crash the build
            print("WARN: context-alarm source skipped -- build_army() failed (%s)" % e, file=sys.stderr)
            return []
    sessions = (army_payload or {}).get("sessions") or []
    out: list[dict] = []
    for s in sessions:
        if not isinstance(s, dict):
            continue
        if s.get("context_source") == gamma_cockpit_army.CONTEXT_UNKNOWN:
            continue  # unknown source -- never alarm on a number that couldn't be computed
        pct = s.get("context_pct")
        if not isinstance(pct, (int, float)) or pct < CONTEXT_ALARM_PCT:
            continue
        sid = str(s.get("session_id") or "")
        name = _clip(s.get("title") or s.get("name") or sid or "session", 80)
        limit = s.get("context_limit")
        tokens = s.get("context_tokens")
        c = _card(
            card_id="card-context-%s" % (re.sub(r"[^a-z0-9]+", "-", sid.lower()).strip("-") or "unknown"),
            title="Session '%s' is at %.0f%% context" % (name, pct),
            why=[
                "context_pct %.1f%% of context_limit %s tokens (context_tokens %s), "
                "context_source=%s" % (pct, limit, tokens, s.get("context_source")),
                "gamma_cockpit_army sessions[] over the %.0f%% alarm threshold" % CONTEXT_ALARM_PCT,
            ],
            source_path="~/.claude/sessions/*.json (gamma_cockpit_army.build_army)",
            source_age_h=None,
            objective="Act on session '%s' (id %s), which is sitting at %.0f%% of its "
                      "%s-token autoCompactWindow: close it, or let it auto-compact -- "
                      "don't leave it to silently run out of room." % (name, sid or "?", pct, limit),
            done_when="Re-run gamma_cockpit_army.build_army() (or re-read the cockpit Army "
                      "view) and confirm session '%s' either no longer appears (closed) or "
                      "its context_pct now reads under %.0f%% (compacted)." % (name, CONTEXT_ALARM_PCT),
        )
        if c:
            out.append(c)
        if len(out) >= MAX_CONTEXT_CARDS:
            break
    return out


# --------------------------------------------------- source 5: unattended health

def _quiesced_task_names() -> set[str]:
    """Task Scheduler names quiet-mode itself disabled -- see this file's own
    docstring on why this MUST be read before any RED/YELLOW is trusted."""
    quiet = _load_json(QUIET_MODE_JSON)
    if not isinstance(quiet, dict) or not quiet.get("quiet_active"):
        return set()
    restore = _load_json(QUIET_MODE_RESTORE_JSON)
    names = (restore or {}).get("restore_to_ready") if isinstance(restore, dict) else None
    return set(names) if isinstance(names, list) else set()


_TASK_PREFIX_RE = re.compile(r"^([A-Za-z0-9_]+):")


def _filter_quiesced(problems: list, quiesced: set[str]) -> list[str]:
    out = []
    for p in problems or []:
        s = str(p)
        m = _TASK_PREFIX_RE.match(s)
        task = m.group(1) if m else None
        if task and task in quiesced:
            continue  # explained by quiet mode holding it down -- not broken
        out.append(s)
    return out


def _unit_has_quiesced_task(unit: dict, quiesced: set[str]) -> bool:
    for t in unit.get("tasks") or []:
        if isinstance(t, dict) and t.get("name") in quiesced:
            return True
    return False


def _cards_unattended(quiesced: set[str]) -> list[dict]:
    data = _load_json(UNATTENDED_HEALTH_JSON)
    if not isinstance(data, dict):
        return []
    age = _age_h(UNATTENDED_HEALTH_JSON)
    out = []
    for unit in data.get("units") or []:
        if not isinstance(unit, dict) or unit.get("status") not in ("RED", "YELLOW"):
            continue
        remaining = _filter_quiesced(unit.get("problems") or [], quiesced)
        # SECOND PASS: a unit whose own engine task IS one quiet-mode held down
        # can also show a "STALE BY AGE" artifact complaint from a SEPARATE
        # (still-running) sentinel task that simply has nothing fresh to report
        # while the engine is down -- crypto-twin/twin-health.json is exactly
        # this shape (verified live 2026-08-29: Gamma_TwinSentinel ran 2m ago,
        # GREEN, yet twin-health.json still reads 496m stale, because the thing
        # it watches -- Gamma_CryptoTwin -- is the disabled one). That staleness
        # is an EXPECTED downstream consequence of the held-down engine, not an
        # independent break, so it is quiesced too rather than left as a
        # half-filtered YELLOW that still misreads as a real problem.
        if remaining and _unit_has_quiesced_task(unit, quiesced):
            remaining = [p for p in remaining if "stale by age" not in str(p).lower()]
        if not remaining:
            continue  # fully explained by quiet mode -- quiesced, never a card
        unit_id = str(unit.get("id", "unit"))
        unit_name = str(unit.get("name", unit_id))
        c = _card(
            card_id="card-unit-%s" % re.sub(r"[^a-z0-9]+", "-", unit_id.lower()).strip("-"),
            title="%s is %s" % (unit_name, unit.get("status")),
            why=remaining[:3],
            source_path=_rel(UNATTENDED_HEALTH_JSON),
            source_age_h=age,
            objective="Restore unattended-health unit '%s' (%s) to GREEN -- resolve the "
                      "problem(s) quoted above, not just the symptom." % (unit_name, unit_id),
            done_when="Re-run `python setup/scripts/unattended_health.py`, re-read the "
                      "fresh automation/state/unattended-health.json, and quote the entry "
                      "for unit '%s' showing status GREEN (or every one of the problems "
                      "above independently resolved)." % unit_id,
        )
        if c:
            out.append(c)
        if len(out) >= MAX_UNIT_CARDS:
            break
    return out


# ---------------------------------------------------------------------- build

def build_cards(write: bool = True) -> dict:
    quiesced = _quiesced_task_names()

    # The goal's next open item is computed FIRST and prepended, not appended
    # in source order -- it must ALWAYS be rank 1 when it fires, outranking
    # every other source, never merely "wherever source 0 happens to sort".
    goal_cards = _cards_active_goal()

    try:
        army_payload = gamma_cockpit_army.build_army()
    except Exception as e:  # noqa: BLE001 - a presence-telemetry failure must not lose the cards page
        print("WARN: gamma_cockpit_army.build_army() failed -- context-alarm source "
              "skipped (%s)" % e, file=sys.stderr)
        army_payload = None

    cards: list[dict] = []
    cards += _cards_engine_health()
    cards += _cards_status_md()
    cards += _cards_task_scorer()
    cards += _cards_context_alarm(army_payload)
    cards += _cards_unattended(quiesced)
    cards = goal_cards + cards
    for i, c in enumerate(cards, start=1):
        c["rank"] = i

    quiet = _load_json(QUIET_MODE_JSON) or {}
    payload = {
        "cards": cards,
        "generated_et": et_clock.et_now().strftime("%Y-%m-%d %H:%M:%S"),
        "rth_now": et_clock.is_market_hours(),
        "quiet_active": bool(quiet.get("quiet_active")),
        "quiesced_task_count": len(quiesced),
        "legend": ("Deterministic, no LLM. The active goal's next open item, when present "
                   "and unexpired, is ALWAYS rank 1. Below that, ranking mirrors the "
                   "conductor's own STAGE 1 priority order. A producer quiet-mode itself "
                   "held down renders as quiesced, never as a card and never as RED."),
        "source": {
            "engine_health": {"path": _rel(ENGINE_HEALTH_JSON), "age_h": _age_h(ENGINE_HEALTH_JSON),
                               "ok": ENGINE_HEALTH_JSON.exists()},
            "status_md": {"path": _rel(STATUS_MD), "age_h": _age_h(STATUS_MD), "ok": STATUS_MD.exists()},
            "queue": {"path": _rel(task_scorer.QUEUE), "age_h": _age_h(task_scorer.QUEUE),
                      "ok": task_scorer.QUEUE.exists()},
            "active_goal": {"path": _rel(ACTIVE_GOAL_JSON), "age_h": _age_h(ACTIVE_GOAL_JSON),
                             "ok": ACTIVE_GOAL_JSON.exists()},
            "context_alarm": {"path": "~/.claude/sessions/*.json", "age_h": None,
                               "ok": army_payload is not None},
            "unattended_health": {"path": _rel(UNATTENDED_HEALTH_JSON), "age_h": _age_h(UNATTENDED_HEALTH_JSON),
                                   "ok": UNATTENDED_HEALTH_JSON.exists()},
        },
    }
    if write:
        try:
            ACTION_CARDS_JSON.parent.mkdir(parents=True, exist_ok=True)
            tmp = ACTION_CARDS_JSON.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(ACTION_CARDS_JSON)
        except OSError as e:
            print("WARN: could not write %s (%s)" % (ACTION_CARDS_JSON, e), file=sys.stderr)
    return payload


def main() -> int:
    payload = build_cards(write=True)
    print("wrote -> %s (%d cards, quiet_active=%s, rth_now=%s)" % (
        ACTION_CARDS_JSON.relative_to(REPO), len(payload["cards"]),
        payload["quiet_active"], payload["rth_now"]))
    for c in payload["cards"]:
        print("  #%d %s -- %s" % (c["rank"], c["id"], c["title"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
