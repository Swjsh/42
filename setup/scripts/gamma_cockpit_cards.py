"""gamma_cockpit_cards.py - Action Cards: the cockpit's ranked "what should I

fire next" surface, generated deterministically -- no LLM anywhere in this
file (WHY: this module decides what an escalated Claude gets TOLD to do, and
a card generator that itself calls an LLM to decide that is the fabrication
risk this whole cockpit exists to close).

RANKING IS NOT INVENTED HERE (spec: scratchpad/SPEC.md sec 4). It mirrors the
conductor's own STAGE 1 priority order verbatim -- reusing task_scorer.py's
ranker for source 3 rather than writing a second one:
  1. automation/state/engine-health.json   -- any critical check not GREEN
  2. automation/overnight/STATUS.md        -- '## Known broken' / '### BROKEN:'
  3. task_scorer.rank()                    -- top 3 ready backlog items
  4. automation/state/active-goal.json     -- the goal's next '- [ ]' item
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
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling imports below

import et_clock  # noqa: E402  -- the ONE DST-aware ET source (never Bash TZ=...)
import task_scorer  # noqa: E402  -- the ONE backlog ranker (never re-derive ROI here)

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
    "\n\nHard rules for this fire (non-negotiable, not a suggestion):\n"
    "- Never touch automation/state/params*.json, backtest/lib/filters.py, "
    "backtest/lib/risk_gate.py, automation/state/fleet/*.py, or "
    "setup/scripts/heartbeat_core.py -- CONFIG FREEZE 2026-08-31 -> 2026-09-29 "
    "(automation/overnight/STATUS.md).\n"
    "- Never set GAMMA_CORE_ARMED or a fleet live:true flag. Never place, cancel, "
    "close, replace, or exercise a live Alpaca order.\n"
    "- Never rotate, print, or read a *.key / .vapid.json / push-subscriptions.json "
    "secret.\n"
    "- Never git push --force, never recursively delete anything.\n"
    "- Name the root cause in one sentence before fixing (setup/hooks/gamma_doctrine.py, "
    "CLAUDE.md OP-33). Apply the smallest correct change. Verify with a freshly-run "
    "command and quote its output -- do not claim 'fixed' on anything else."
)


def _prompt(card_id: str, title: str, why: list[str], source_path: str) -> str:
    body = "Task: %s\nSource: %s\nWhy this card fired:\n%s\n" % (
        card_id, source_path, "\n".join("- %s" % w for w in why),
    )
    return body + _SAFETY_FOOTER


def _card(card_id: str, title: str, why: list[str], source_path: str,
          source_age_h, gated: bool = False) -> dict | None:
    """The one constructor every source below funnels through -- the single
    point where the denylist actually runs, so no source can bypass it."""
    untrusted = title + " " + " ".join(why)
    hit = _looks_dangerous(untrusted)
    if hit:
        print("WARN: dropped card %s -- denylist hit (%s)" % (card_id, hit), file=sys.stderr)
        return None
    return {
        "id": card_id,
        "rank": 0,  # assigned by build_cards() once every source has contributed
        "title": _clip(title, 140),
        "why": [_clip(w, 200) for w in why][:4],
        "source_path": source_path,
        "source_age_h": round(source_age_h, 2) if isinstance(source_age_h, (int, float)) else None,
        "model": MODEL,
        "gated": bool(gated),
        "prompt": _prompt(card_id, title, why, source_path),
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
        )
        if c:
            out.append(c)
    return out


# ------------------------------------------------------------- source 4: goal

def _cards_active_goal() -> list[dict]:
    goal = _load_json(ACTIVE_GOAL_JSON)
    if not isinstance(goal, dict) or not goal.get("active"):
        return []
    expires = str(goal.get("expires_at_et", ""))[:10]
    if expires and expires < et_clock.et_today_str():
        return []  # expired -- not this fire's job to resurrect it
    goal_file = REPO / str(goal.get("file", ""))
    try:
        text = goal_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    m = re.search(r"^## QUEUE\s*$", text, re.MULTILINE)
    if not m:
        return []
    tail = text[m.end():]
    stop = re.search(r"^## ", tail, re.MULTILINE)
    section = tail[: stop.start() if stop else len(tail)]
    item = None
    for line in section.splitlines():
        s = line.strip()
        if s.startswith("- [ ]"):
            item = s[len("- [ ]"):].strip()
            break
    if not item:
        return []
    c = _card(
        card_id="card-goal-%s" % re.sub(r"[^a-z0-9]+", "-", str(goal.get("id", "goal")).lower()).strip("-"),
        title="Goal %s: %s" % (goal.get("id", "?"), _clip(item, 90)),
        why=[_clip(item, 260), "next open '- [ ]' item in the goal's own QUEUE"],
        source_path=_rel(goal_file),
        source_age_h=_age_h(goal_file),
        gated=False,  # a literal '- [ ]' item is by construction not '[B]'/'[B-J]' blocked
    )
    return [c] if c else []


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
        c = _card(
            card_id="card-unit-%s" % re.sub(r"[^a-z0-9]+", "-", str(unit.get("id", "unit")).lower()).strip("-"),
            title="%s is %s" % (unit.get("name", unit.get("id", "unit")), unit.get("status")),
            why=remaining[:3],
            source_path=_rel(UNATTENDED_HEALTH_JSON),
            source_age_h=age,
        )
        if c:
            out.append(c)
        if len(out) >= MAX_UNIT_CARDS:
            break
    return out


# ---------------------------------------------------------------------- build

def build_cards(write: bool = True) -> dict:
    quiesced = _quiesced_task_names()
    cards: list[dict] = []
    cards += _cards_engine_health()
    cards += _cards_status_md()
    cards += _cards_task_scorer()
    cards += _cards_active_goal()
    cards += _cards_unattended(quiesced)
    for i, c in enumerate(cards, start=1):
        c["rank"] = i

    quiet = _load_json(QUIET_MODE_JSON) or {}
    payload = {
        "cards": cards,
        "generated_et": et_clock.et_now().strftime("%Y-%m-%d %H:%M:%S"),
        "rth_now": et_clock.is_market_hours(),
        "quiet_active": bool(quiet.get("quiet_active")),
        "quiesced_task_count": len(quiesced),
        "legend": ("Deterministic, no LLM. Ranking mirrors the conductor's own STAGE 1 "
                   "priority order. A producer quiet-mode itself held down renders as "
                   "quiesced, never as a card and never as RED."),
        "source": {
            "engine_health": {"path": _rel(ENGINE_HEALTH_JSON), "age_h": _age_h(ENGINE_HEALTH_JSON),
                               "ok": ENGINE_HEALTH_JSON.exists()},
            "status_md": {"path": _rel(STATUS_MD), "age_h": _age_h(STATUS_MD), "ok": STATUS_MD.exists()},
            "queue": {"path": _rel(task_scorer.QUEUE), "age_h": _age_h(task_scorer.QUEUE),
                      "ok": task_scorer.QUEUE.exists()},
            "active_goal": {"path": _rel(ACTIVE_GOAL_JSON), "age_h": _age_h(ACTIVE_GOAL_JSON),
                             "ok": ACTIVE_GOAL_JSON.exists()},
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
