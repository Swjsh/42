"""gamma_standup.py -- Gamma's self-initiated Discord standup (J directive, 2026-08-08).

THE GAP THIS CLOSES (J, verbatim): "Gamma isn't existing or wanting anything; I need a
coworker, not a chatbot." The Discord channel today is 100% log-spew (self_check DEGRADED
dumps, pipeline-promote JSON blobs) -- zero FIRST-PERSON, coworker-register presence. This
module is a standup, not a log line: two short daily messages, written as Gamma talking to J
the way a coworker would ("here's what I did, here's what I'm on, here's what I want"), sent
through the EXISTING Discord bridge outbox (setup/scripts/discord-bridge.py drains
automation/state/discord-outbox.jsonl -- this module only ever APPENDS one row per run, same
schema prospector.py/daily_brief.py already use: {"content", "source", "queued_at"}).

MODES (Gamma_StandupAM 08:15 ET / Gamma_StandupEOD 16:45 ET weekdays, see
install-gamma-standup.ps1):
  --mode morning  Line 1 "Morning J -- Gamma here." then OVERNIGHT/YESTERDAY (2-4 bullets of
                  what shipped, from git log), TODAY (1 bullet, queue.md backlog), I WANT
                  (0-3 bullets, priority-sorted from the wants registry), CLOCKS (one line:
                  SSR/MES shadow progress + catastrophe-cap accrual). On a Monday, an
                  additional WEEKEND RECAP section is inserted (wider git-log window).
  --mode eod      Line 1 "EOD from Gamma." then P&L (both accounts if today's journal has
                  rows), WHAT I LEARNED (1 bullet, today's most notable shipped commit),
                  TOMORROW (1 bullet, queue.md backlog), I WANT (delta-annotated: entries new
                  since the last standup's latest.json are prefixed "(new)").

DATA SOURCES (every reader is FAIL-OPEN -- a missing/garbled file degrades that ONE bullet or
clocks segment to omitted, never a crash, never an invented claim -- C7 + the honesty rule):
  automation/state/futures/shadow-progress.json      -- MES mirror n/needed + beats_null
  automation/state/futures/ssr-shadow-progress.json  -- SSR shadow n/needed
  analysis/recommendations/catastrophe-cap-shadow-ledger.jsonl -- line count -> n/20 cadence
  git log (subprocess, --oneline, feat/fix/docs only) -- OVERNIGHT / WEEKEND RECAP / LEARNED
  automation/overnight/queue.md  -- count of "- [ ] " unchecked items -> TODAY/TOMORROW
  journal/trades.csv             -- today's rows, grouped by account_id -> EOD P&L
  automation/state/gamma-wants.json -- durable wants registry -> I WANT (top 3 by priority)

VOICE RULES (hard requirements, test-enforced -- see backtest/tests/test_gamma_standup.py):
  - First person, plain English, coworker register. HARD CAP 1200 chars (CHAR_CAP) on the
    composed body (before the Discord @mention prefix).
  - BANNED_SUBSTRINGS never leak into the final text, even if a source (a git commit subject
    quoting a self-check alert, say) contains them -- git bullets are dropped outright if they
    match; the fully-composed text also gets a final redaction pass as a safety net.
  - No file-path token longer than MAX_PATH_TOKEN_LEN survives -- shortened to its basename,
    or "[path]" if even the basename is too long.
  - Numbers are rounded to whole dollars with thousands separators ($fmt via _fmt_money).
  - Never invents a claim: if a source file is missing, the bullet/segment it would have fed
    is simply omitted (fallback copy is used instead, always phrased as "no data", never as a
    guess).

NO LLM ANYWHERE ON THIS PATH -- pure deterministic string assembly, $0, matches
daily_brief.py's precedent and CLAUDE.md's "deterministic > LLM on hot paths" rule. "Rewritten
human" (per the build spec) is implemented as: strip the conventional-commit type/scope
prefix, sentence-case the first letter, cap length -- not narrative paraphrase (that would
need an LLM call this module deliberately does not make).

Run:
  backtest/.venv/Scripts/python.exe setup/scripts/gamma_standup.py --mode morning [--dry-run]
  backtest/.venv/Scripts/python.exe setup/scripts/gamma_standup.py --mode eod [--dry-run]

Also writes automation/state/gamma-standup-latest.json every REAL (non-dry-run) fire -- the
composed text + metadata (incl. which want ids were shown, so the NEXT run can flag deltas).
A sibling HUD reads this file. --dry-run performs NO disk writes at all (outbox untouched,
latest.json untouched) -- it only prints what would have been sent.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41, 2026-07-14 popup-storm fix) ====================
# When launched via pythonw.exe (no console -- see install-gamma-standup.ps1's wscript ->
# run_exe_hidden.vbs -> system-pythonw -> run_cmd_hidden.py -> backtest-venv-pythonw chain),
# Windows 11's default-terminal handler can allocate a visible window on the FIRST
# stdout/stderr write. Redirect to log files BEFORE any other import gets a chance to write.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "gamma_standup.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "gamma_standup.stderr.log", "a", buffering=1, encoding="utf-8")
# ==========================================================================================

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from et_clock import et_now, et_offset_hours  # noqa: E402

# Console UTF-8 hardening: the composed text carries em-dashes and a middle-dot (CLOCKS
# line), and Windows' python.exe defaults stdout to the ANSI codepage (cp1252) rather than
# UTF-8 when attached to a real console -- readable there (cp1252 does encode em-dash) but
# mis-decoded by a UTF-8-native terminal (Git Bash/mintty), showing "�". This affects
# ONLY the human-readable console print() in main() -- the two real persistence paths
# (the pythonw headless log redirect above, and append_outbox's explicit encoding="utf-8")
# already force UTF-8 and are unaffected either way. Best-effort + fail-open: never break
# a run over a display nicety.
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):  # noqa: PERF203 -- tiny, run-once
        pass

STATE = REPO / "automation" / "state"
FUTURES_DIR = STATE / "futures"

SHADOW_PROGRESS_PATH = FUTURES_DIR / "shadow-progress.json"
SSR_SHADOW_PROGRESS_PATH = FUTURES_DIR / "ssr-shadow-progress.json"
CATASTROPHE_CAP_LEDGER_PATH = REPO / "analysis" / "recommendations" / "catastrophe-cap-shadow-ledger.jsonl"
QUEUE_MD_PATH = REPO / "automation" / "overnight" / "queue.md"
TRADES_CSV_PATH = REPO / "journal" / "trades.csv"
WANTS_PATH = STATE / "gamma-wants.json"
DISCORD_CFG_PATH = STATE / ".discord-config.json"
OUTBOX_PATH = STATE / "discord-outbox.jsonl"
LATEST_PATH = STATE / "gamma-standup-latest.json"
AUTONOMY_REPORT_PATH = STATE / "autonomy-report.json"
# gate_recency_report.py's weekly artifact (2026-08-08 addition: a top-level "core_strategy"
# block -- see GATE-RECENCY-DOCTRINE.md's "Two verdict families"). Read-only, never
# recomputed here -- same discipline as every other source in this module.
GATE_RECENCY_LATEST_PATH = STATE / "gate-recency-latest.json"

CHAR_CAP = 1200
COMMIT_BULLET_MAX_CHARS = 150
MAX_PATH_TOKEN_LEN = 40
CATASTROPHE_CAP_CADENCE = 20
FOCUS_MAX_CHARS = 110
# "thin" caveat threshold for the CORE STRATEGY alert line -- mirrors
# setup/scripts/gate_recency_report.py's CORE_STRATEGY_THIN_N verbatim (gate_expiry_check.py's
# confirm_n_floor is 10; a sample only modestly above that bare actionability floor should
# read as thin, not confidently conclusive). Kept as an independent constant rather than a
# shared import -- both scripts are deliberately dependency-light / standalone.
CORE_STRATEGY_THIN_N = 20

# Fixed, test-enforced. Never let one of these leak into a real Discord message.
BANNED_SUBSTRINGS = ["DEGRADED", "MASKED EXIT", "Traceback", "exit=[", "jsonl"]

_MENTION_UID_CACHE: Optional[str] = None


# --------------------------------------------------------------------------- #
# Fail-open readers -- degrade to None/""/[] on any error, never raise (C7).
# --------------------------------------------------------------------------- #

def _read_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# --------------------------------------------------------------------------- #
# Safety net -- banned substrings + long file paths. Applied per-bullet (git
# commits, the highest-risk source) AND once more on the fully composed text.
# --------------------------------------------------------------------------- #

def _sanitize_bullet(text: str) -> Optional[str]:
    """None if text contains ANY banned substring -- caller drops it."""
    for bad in BANNED_SUBSTRINGS:
        if bad in text:
            return None
    return text


def _redact_banned(text: str) -> str:
    """Final defensive pass over the WHOLE composed message. Every bullet source
    should already be clean via _sanitize_bullet; this only fires if something
    slipped through construction logic itself."""
    for bad in BANNED_SUBSTRINGS:
        if bad in text:
            text = text.replace(bad, "[removed]")
    return text


_PATH_TOKEN_RE = re.compile(r"\S*[\\/]\S*")


def _shorten_path_token(token: str) -> str:
    lead = ""
    while token and token[0] in "([{":
        lead += token[0]
        token = token[1:]
    trail = ""
    while token and token[-1] in ").,;:]}":
        trail = token[-1] + trail
        token = token[:-1]
    if len(token) <= MAX_PATH_TOKEN_LEN:
        return lead + token + trail
    base = re.split(r"[\\/]", token)[-1]
    if base and len(base) <= MAX_PATH_TOKEN_LEN:
        return lead + base + trail
    return lead + "[path]" + trail


def _strip_long_paths(text: str) -> str:
    return _PATH_TOKEN_RE.sub(lambda m: _shorten_path_token(m.group(0)), text)


def _finalize(text: str) -> str:
    """Final safety net + hard cap, run on every composed message before it is
    ever printed or queued: banned-substring redaction, long-path shortening,
    then CHAR_CAP enforcement (never exceeds CHAR_CAP, ever)."""
    text = _redact_banned(text)
    text = _strip_long_paths(text)
    if len(text) > CHAR_CAP:
        suffix = "\n...[cut]"
        budget = max(0, CHAR_CAP - len(suffix))
        truncated = text[:budget]
        cut = truncated.rfind("\n")
        if cut > budget * 0.5:
            truncated = truncated[:cut]
        text = truncated.rstrip() + suffix
    return text


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #

def _fmt_money(x: float) -> str:
    return f"${abs(x):,.0f}"


def _fmt_signed_money(x: float) -> str:
    if abs(x) < 0.005:
        return "flat"
    return f"{'up' if x > 0 else 'down'} {_fmt_money(x)}"


# --------------------------------------------------------------------------- #
# git log -- OVERNIGHT / WEEKEND RECAP / WHAT I LEARNED bullets.
# _git_log_subjects is the ONE seam tests monkeypatch (never hits real git in
# a unit test -- keeps results independent of this repo's actual commit history).
# --------------------------------------------------------------------------- #

_COMMIT_TYPE_RE = re.compile(r"^[0-9a-f]+\s+(feat|fix|docs)(\([^)]*\))?:\s*(.+)$")


def _git_log_subjects(since: str, until: Optional[str] = None) -> list[str]:
    """Raw `git log --oneline` lines within the window, newest-first. [] on ANY
    failure (not a git repo, git missing, timeout, non-zero exit) -- fail-open."""
    cmd = ["git", "log", f"--since={since}", "--oneline"]
    if until:
        cmd.append(f"--until={until}")
    try:
        r = subprocess.run(
            cmd, cwd=str(REPO), capture_output=True, text=True, timeout=10,
            creationflags=(0x08000000 if sys.platform == "win32" else 0),
        )
    except Exception:  # noqa: BLE001 -- fail-open, never break the standup
        return []
    if r.returncode != 0:
        return []
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def _humanize_commit_subject(line: str) -> Optional[str]:
    """feat/fix/docs commit line -> a short sentence-cased bullet, or None if the
    line isn't one of the three tracked types, or sanitizes to nothing."""
    m = _COMMIT_TYPE_RE.match(line.strip())
    if not m:
        return None
    desc = m.group(3).strip()
    desc = _sanitize_bullet(desc)
    if not desc:
        return None
    if len(desc) > COMMIT_BULLET_MAX_CHARS:
        cut = desc[:COMMIT_BULLET_MAX_CHARS].rsplit(" ", 1)[0]
        desc = (cut or desc[:COMMIT_BULLET_MAX_CHARS]).rstrip(" ,.;:-") + "..."
    if desc:
        desc = desc[0].upper() + desc[1:]
    return desc or None


def _commit_bullets(since: str, until: Optional[str] = None, *, max_n: int = 4) -> list[str]:
    """Scans commits in the window (newest-first) and collects up to max_n GOOD
    (type-matching + sanitize-passing) bullets -- keeps scanning past a dropped
    commit instead of stopping short, so one banned-word commit doesn't starve
    the whole section."""
    out: list[str] = []
    for ln in _git_log_subjects(since, until):
        bullet = _humanize_commit_subject(ln)
        if bullet:
            out.append(bullet)
        if len(out) >= max_n:
            break
    return out


def _et_midnight_iso(day: str) -> str:
    """ET midnight of `day` as an offset-qualified ISO string git understands
    unambiguously (git's relative-date literals interpret naive strings in the
    SYSTEM'S local timezone -- Mountain on this box, 2h off from ET -- so this
    is spelled out with an explicit DST-aware offset instead)."""
    off = et_offset_hours(datetime.now(timezone.utc))
    return f"{day}T00:00:00{off:+03d}:00"


# --------------------------------------------------------------------------- #
# queue.md -- TODAY / TOMORROW backlog fallback bullet.
# --------------------------------------------------------------------------- #

_UNCHECKED_RE = re.compile(r"^- \[ \] ", re.M)


def _queue_unchecked_count(path: Path) -> Optional[int]:
    text = _read_text(path)
    if not text:
        return None
    return len(_UNCHECKED_RE.findall(text))


def _backlog_bullet(n: Optional[int], *, tense: str) -> Optional[str]:
    if n is None:
        return None
    if n == 0:
        return f"Backlog's clear -- nothing queued, {tense} is whatever the tape gives me."
    plural = "s" if n != 1 else ""
    return f"{n} open research item{plural}; {tense} I'm on the top one."


# --------------------------------------------------------------------------- #
# "focus" field (2026-08-08, gamma_hq.py flag #4; corrected 2026-08-08 same
# day -- see BUG note below) -- a one-line, GAMMA-HQ-ready summary written
# into gamma-standup-latest.json alongside the existing keys (schema ADDITION,
# still backward compatible -- any older reader that doesn't know "focus"
# just ignores it). BOTH modes populate it now: morning derives it from the
# TODAY bullet, eod from the TOMORROW bullet -- whichever backlog bullet that
# mode's own composed message already shows, via the SAME fallback phrase
# (TODAY_FALLBACK / TOMORROW_FALLBACK below), so this field can never diverge
# from what J actually sees in the full message.
#
# BUG this replaced (J-flagged, live on the Gamma App page 2026-08-08): the
# first cut of this field only fired in morning mode; gather_facts left
# facts["focus"] = None for eod, and gamma_hq.py's _today_focus_text fell
# back to the first line of standup["text"] -- which for a real standup is
# the fixed greeting sentence ("EOD from Gamma."). The header rendered
# "Today's focus: EOD from Gamma." -- a coworker's hello line dressed up as
# the day's actual focus. Root cause was the missing eod-mode write, not the
# consumer's fallback logic; the fallback just made the gap invisible instead
# of surfacing it. Fixed at the source (both modes always write a real
# "focus") AND at gamma_hq.py's consumer (_today_focus_text no longer falls
# back to any greeting-bearing text at all -- see that module).
# --------------------------------------------------------------------------- #

TODAY_FALLBACK = "Nothing queued -- reading the tape as it comes."
TOMORROW_FALLBACK = "Reading the tape fresh, nothing queued yet."

_MARKDOWN_LIST_PREFIX_RE = re.compile(r"^[-*]\s+")
_MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MARKDOWN_BOLD_ALT_RE = re.compile(r"__(.+?)__")
_MARKDOWN_CODE_RE = re.compile(r"`([^`]+)`")


def _strip_markdown(text: str) -> str:
    """Best-effort plain-text extraction from a markdown-ish source line: drop
    a leading list-item marker ("- "/"* "), unwrap **bold**/__bold__/`code`
    runs (keep the inner text), collapse whitespace. Not a full markdown
    parser -- just enough that a stray "-"/"**" never reaches the one-line
    focus field. today_bullet's own text never actually contains markdown
    today (it's a plain composed sentence -- see _backlog_bullet), but the
    spec calls for stripping it and a future TODAY-section source could add
    some, so this runs unconditionally rather than being skipped as "not
    needed yet"."""
    t = _MARKDOWN_LIST_PREFIX_RE.sub("", text.strip())
    t = _MARKDOWN_BOLD_RE.sub(r"\1", t)
    t = _MARKDOWN_BOLD_ALT_RE.sub(r"\1", t)
    t = _MARKDOWN_CODE_RE.sub(r"\1", t)
    return " ".join(t.split())


def _truncate_at_word_boundary(text: str, max_len: int, ellipsis: str = "...") -> str:
    """Truncate to at most max_len characters, cutting at the last whitespace
    boundary within budget rather than mid-word, then appending `ellipsis`.
    Standalone sibling of the word-boundary discipline _humanize_commit_subject
    already applies inline to commit bullets (.rsplit(" ", 1)[0] + "...") --
    same style (ASCII "...", not a unicode ellipsis) for consistency within
    this file, kept as its own small helper rather than touching that
    established, separately-tested function."""
    if len(text) <= max_len:
        return text
    budget = max_len - len(ellipsis)
    if budget <= 0:
        return text[:max_len]
    cut = text[:budget].rsplit(" ", 1)[0]
    cut = (cut or text[:budget]).rstrip(" ,.;:-")
    return cut + ellipsis


def _derive_focus(bullet: Optional[str], fallback: str) -> str:
    """One-line 'focus' field for gamma-standup-latest.json, shared by BOTH
    modes: morning passes the TODAY bullet + TODAY_FALLBACK, eod passes the
    TOMORROW bullet + TOMORROW_FALLBACK. `fallback` mirrors that mode's own
    compose_*_text no-backlog phrase EXACTLY (same module constant used in
    both places -- see TODAY_FALLBACK/TOMORROW_FALLBACK above), so this can
    never diverge from what the composed message itself actually shows --
    markdown-stripped, capped at FOCUS_MAX_CHARS."""
    raw = bullet if bullet else fallback
    return _truncate_at_word_boundary(_strip_markdown(raw), FOCUS_MAX_CHARS)


# --------------------------------------------------------------------------- #
# Wants registry -- I WANT section (morning: plain top-3; eod: delta-annotated).
# --------------------------------------------------------------------------- #

def _top_wants(doc: Optional[dict], n: int = 3) -> list[dict]:
    if not doc:
        return []
    wants = doc.get("wants")
    if not isinstance(wants, list):
        return []
    valid = [
        w for w in wants
        if isinstance(w, dict) and isinstance(w.get("text"), str) and w.get("text").strip()
        and isinstance(w.get("id"), str) and w.get("id").strip()
    ]

    def _pri(w: dict):
        p = w.get("priority")
        return p if isinstance(p, (int, float)) else 999

    valid.sort(key=lambda w: (_pri(w), w["id"]))
    return valid[:n]


def _new_want_ids(current_top: list[dict], previous_shown_ids: Optional[list]) -> set:
    if previous_shown_ids is None:
        return set()
    prev = set(previous_shown_ids)
    return {w["id"] for w in current_top if w.get("id") not in prev}


def _wants_bullets(top: list[dict], *, new_ids: Optional[set] = None) -> list[str]:
    new_ids = new_ids or set()
    out = []
    for w in top:
        text = w["text"].strip()
        prefix = "(new) " if w.get("id") in new_ids else ""
        out.append(prefix + text)
    return out


# --------------------------------------------------------------------------- #
# CLOCKS line (morning only) -- shadow-progress + ssr-shadow-progress + the
# catastrophe-cap accrual ledger's line count.
# --------------------------------------------------------------------------- #

def _shadow_segment(label: str, data: Optional[dict]) -> Optional[str]:
    if not data:
        return None
    ab = data.get("arming_bar") or {}
    have = data.get("n_round_trips")
    need = ab.get("round_trips_needed")
    if have is None or need is None:
        return None
    seg = f"{label} {have}/{need}"
    if ab.get("armable") is False and ab.get("beats_null") is False:
        seg += " (needs beats-null)"
    return seg


def _cap_clock_segment(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    text = _read_text(path)
    n = sum(1 for ln in text.splitlines() if ln.strip())
    display = n % CATASTROPHE_CAP_CADENCE if n >= CATASTROPHE_CAP_CADENCE else n
    return f"Cap shadow {display}/{CATASTROPHE_CAP_CADENCE}"


def _compose_clocks_line(segments: list) -> Optional[str]:
    parts = [s for s in segments if s]
    if not parts:
        return None
    return "Clocks: " + " · ".join(parts)


# --------------------------------------------------------------------------- #
# AUTONOMY line (morning only, 2026-08-08 -- LANE C) -- sourced ONLY from
# automation/state/autonomy-report.json (setup/scripts/autonomy_report.py),
# never recomputed here. Answers "did Gamma actually drive yesterday" in one
# honest line -- never flattering, never vague, never blank on a fully-starved
# day (that report's own build_verdict already guarantees a non-empty verdict
# string; this just reshapes it into first-person coworker voice using the
# SAME numbers, per the same never-invents-a-claim discipline as every other
# section in this module -- see gather_facts's "focus" field for precedent).
# --------------------------------------------------------------------------- #

def _autonomy_line(report: Optional[dict]) -> Optional[str]:
    if not isinstance(report, dict):
        return None
    today = report.get("today")
    if not isinstance(today, dict):
        return None
    total = today.get("total_fires")
    ship = today.get("ship_fires")
    if not isinstance(total, int) or not isinstance(ship, int):
        return None
    date = today.get("date") if isinstance(today.get("date"), str) else None
    if total == 0:
        suffix = f" ({date})" if date else ""
        return f"Autonomy: no conductor fires logged yesterday{suffix}."
    starved = (today.get("noop_reasons") or {}).get("budget_exhausted")
    slot = "slot" if total == 1 else "slots"
    line = f"Autonomy: yesterday I drove {ship} of {total} fire {slot}"
    if isinstance(starved, int) and starved > 0:
        line += f" -- {starved} starved on budget"
    return line + "."


# --------------------------------------------------------------------------- #
# CORE STRATEGY alert line (morning only, 2026-08-08) -- sourced ONLY from
# automation/state/gate-recency-latest.json's top-level "core_strategy" block (written by
# setup/scripts/gate_recency_report.py). THE GAP THIS CLOSES: gate-registry-status.json
# already computes core_strategy_bear/core_strategy_bull nightly (real-broker-fills recency
# verdicts on the strategy ITSELF, inverted semantics vs a gate -- see
# GATE-RECENCY-DOCTRINE.md's "Two verdict families") but nothing put them in front of J in
# his daily flow. A RED here outranks any individual gate/finding elsewhere in this standup,
# so it is surfaced right after the greeting line, ahead of OVERNIGHT/YESTERDAY -- the
# earliest position in the message, which also means _finalize's end-of-message truncation
# (the CHAR_CAP trade-off) drops lower-priority content FIRST, never this line.
#
# POISON-RESISTANT BY CONSTRUCTION: every interpolated value is read through an isinstance
# numeric check (falls back to a safe placeholder phrase otherwise) and the direction word is
# always one of the two fixed literals below -- never a raw string read off disk. No free-text
# field from the source JSON (e.g. a "reason"/"headline" string) is ever interpolated, so
# there is no path for a poisoned/corrupted artifact to inject banned substrings through this
# line's own construction. _sanitize_bullet still runs as defense-in-depth, matching every
# other free-form source in this module (git bullets).
# --------------------------------------------------------------------------- #

def _fmt_core_strategy_money(x) -> str:
    if not isinstance(x, (int, float)):
        return "an unknown $/trade figure"
    sign = "-" if x < 0 else "+"
    return f"{sign}${abs(x):,.2f}/trade"


def _core_strategy_alert_line(doc: Optional[dict]) -> Optional[str]:
    if not isinstance(doc, dict):
        return None
    cs = doc.get("core_strategy")
    if not isinstance(cs, dict):
        return None
    for direction in ("bear", "bull"):  # stable tie-break if somehow both are RED at once
        entry = cs.get(direction)
        if not isinstance(entry, dict) or entry.get("verdict") != "RED":
            continue
        exp = entry.get("exp_per_trade")
        n = entry.get("n")
        window = entry.get("window") if isinstance(entry.get("window"), dict) else {}
        n_days = window.get("n_trading_days")
        n_str = str(n) if isinstance(n, (int, float)) else "an unstated number of"
        window_str = f"{n_days}-day window" if isinstance(n_days, (int, float)) else "an unstated window"
        line = (
            f"CORE STRATEGY {direction.upper()} is RED: {_fmt_core_strategy_money(exp)} on "
            f"{n_str} real fill{'s' if n != 1 else ''} ({window_str}) -- the {direction} side "
            f"itself is losing money, not a gate blocking it."
        )
        if isinstance(n, (int, float)) and n < CORE_STRATEGY_THIN_N:
            line += f" n={n} is thin; this is a WATCH, not yet a mandate to disarm."
        return _sanitize_bullet(line)
    return None


# --------------------------------------------------------------------------- #
# trades.csv -- EOD P&L, grouped by account_id (whatever labels appear that
# day -- fleet arms use safe-1/safe-3/risky-1/risky-3/aggressive as well as the
# core safe/bold, so this never hardcodes just two accounts).
# --------------------------------------------------------------------------- #

def _trades_rows_for_day(path: Path, day: str) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            return [row for row in reader if (row.get("date") or "").strip() == day]
    except OSError:
        return []


def _pnl_segments(rows: list[dict]) -> list[tuple]:
    """[(account_id, n_trades, net_pnl), ...] sorted by account_id. Rows with a
    non-numeric/blank dollar_pnl are skipped (never crash on a dirty row)."""
    agg: dict = defaultdict(lambda: [0, 0.0])
    for r in rows:
        acct = (r.get("account_id") or "").strip()
        if not acct:
            continue
        try:
            pnl = float(r.get("dollar_pnl"))
        except (TypeError, ValueError):
            continue
        agg[acct][0] += 1
        agg[acct][1] += pnl
    return sorted((acct, n, pnl) for acct, (n, pnl) in agg.items())


# --------------------------------------------------------------------------- #
# Discord mention -- same pattern as daily_brief.py._load_user_mention.
# --------------------------------------------------------------------------- #

def _load_user_mention() -> str:
    try:
        cfg = json.loads(DISCORD_CFG_PATH.read_text(encoding="utf-8-sig"))
        uid = cfg.get("user_id")
        return f"<@{uid}> " if uid else ""
    except Exception:  # noqa: BLE001
        return ""


# --------------------------------------------------------------------------- #
# gather -- reads every source (via the module-level path constants above, so
# tests can monkeypatch them onto tmp_path fixtures) into one facts dict.
# --------------------------------------------------------------------------- #

def gather_facts(mode: str, day: str, now_et: datetime) -> dict:
    facts: dict = {
        "mode": mode,
        "day": day,
        "is_weekend": now_et.weekday() >= 5,
        "is_monday": now_et.weekday() == 0,
    }

    if mode == "morning":
        facts["overnight_bullets"] = _commit_bullets("18 hours ago", max_n=4)
        facts["weekend_bullets"] = (
            _commit_bullets("4 days ago", "18 hours ago", max_n=4) if facts["is_monday"] else []
        )
        facts["today_bullet"] = _backlog_bullet(_queue_unchecked_count(QUEUE_MD_PATH), tense="today")
        facts["focus"] = _derive_focus(facts["today_bullet"], TODAY_FALLBACK)

        wants_top = _top_wants(_read_json(WANTS_PATH), n=3)
        facts["wants_top"] = wants_top
        facts["wants_bullets"] = _wants_bullets(wants_top)

        facts["clocks_line"] = _compose_clocks_line([
            _shadow_segment("SSR shadow", _read_json(SSR_SHADOW_PROGRESS_PATH)),
            _shadow_segment("MES mirror", _read_json(SHADOW_PROGRESS_PATH)),
            _cap_clock_segment(CATASTROPHE_CAP_LEDGER_PATH),
        ])
        facts["autonomy_line"] = _autonomy_line(_read_json(AUTONOMY_REPORT_PATH))
        facts["core_strategy_line"] = _core_strategy_alert_line(_read_json(GATE_RECENCY_LATEST_PATH))
    else:  # eod
        learned = _commit_bullets(_et_midnight_iso(day), max_n=1)
        facts["learned_bullet"] = learned[0] if learned else None
        facts["tomorrow_bullet"] = _backlog_bullet(_queue_unchecked_count(QUEUE_MD_PATH), tense="tomorrow")
        # EOD has no TODAY section, but it DOES have a TOMORROW bullet -- use
        # that as the focus (same shared-constant discipline as morning; see
        # the BUG note above the "focus" field section for why this changed
        # from the old facts["focus"] = None).
        facts["focus"] = _derive_focus(facts["tomorrow_bullet"], TOMORROW_FALLBACK)

        wants_top = _top_wants(_read_json(WANTS_PATH), n=3)
        prev_latest = _read_json(LATEST_PATH)
        prev_ids = prev_latest.get("wants_shown") if isinstance(prev_latest, dict) else None
        new_ids = _new_want_ids(wants_top, prev_ids)
        facts["wants_top"] = wants_top
        facts["wants_bullets"] = _wants_bullets(wants_top, new_ids=new_ids)

        rows = _trades_rows_for_day(TRADES_CSV_PATH, day)
        facts["pnl_segments"] = _pnl_segments(rows)

    return facts


# --------------------------------------------------------------------------- #
# compose -- pure string assembly from an already-gathered facts dict.
# --------------------------------------------------------------------------- #

def compose_morning_text(facts: dict) -> str:
    lines = ["Morning J — Gamma here.", ""]

    # CORE STRATEGY RED outranks everything else in this message -- placed first (right
    # after the greeting) so _finalize's end-of-message truncation drops lower-priority
    # content before this line, never the reverse. See the section above _core_strategy_
    # alert_line for the full rationale.
    core_strategy_line = facts.get("core_strategy_line")
    if core_strategy_line:
        lines.append(core_strategy_line)
        lines.append("")

    lines.append("**OVERNIGHT/YESTERDAY**")
    overnight = facts.get("overnight_bullets") or []
    if overnight:
        lines.extend(f"- {b}" for b in overnight)
    else:
        lines.append("- Quiet stretch, nothing shipped.")
    lines.append("")

    if facts.get("is_monday"):
        lines.append("**WEEKEND RECAP**")
        weekend = facts.get("weekend_bullets") or []
        if weekend:
            lines.extend(f"- {b}" for b in weekend)
        else:
            lines.append("- Quiet weekend, nothing shipped.")
        lines.append("")

    lines.append("**TODAY**")
    today_bullet = facts.get("today_bullet")
    lines.append(f"- {today_bullet}" if today_bullet else f"- {TODAY_FALLBACK}")
    lines.append("")

    wants_bullets = facts.get("wants_bullets") or []
    if wants_bullets:
        lines.append("**I WANT**")
        lines.extend(f"- {b}" for b in wants_bullets)
        lines.append("")

    clocks = facts.get("clocks_line")
    if clocks:
        lines.append(clocks)

    autonomy_line = facts.get("autonomy_line")
    if autonomy_line:
        lines.append(autonomy_line)

    text = "\n".join(lines).strip()
    return _finalize(text)


def compose_eod_text(facts: dict) -> str:
    lines = ["EOD from Gamma.", ""]

    lines.append("**P&L**")
    segments = facts.get("pnl_segments") or []
    if segments:
        parts = [
            f"{acct.capitalize()} {_fmt_signed_money(pnl)} on {n} trade{'s' if n != 1 else ''}"
            for acct, n, pnl in segments
        ]
        line = "; ".join(parts) + "."
        if len(segments) > 1:
            total = sum(p for _, _, p in segments)
            line += f" Overall {_fmt_signed_money(total)}."
        lines.append(line)
    else:
        lines.append("No trades today (market closed)." if facts.get("is_weekend") else "No trades today.")
    lines.append("")

    lines.append("**WHAT I LEARNED**")
    learned = facts.get("learned_bullet")
    lines.append(f"- {learned}" if learned else "- Quiet session -- nothing new to log.")
    lines.append("")

    lines.append("**TOMORROW**")
    tomorrow = facts.get("tomorrow_bullet")
    lines.append(f"- {tomorrow}" if tomorrow else f"- {TOMORROW_FALLBACK}")

    wants_bullets = facts.get("wants_bullets") or []
    if wants_bullets:
        lines.append("")
        lines.append("**I WANT**")
        lines.extend(f"- {b}" for b in wants_bullets)

    text = "\n".join(lines).strip()
    return _finalize(text)


# --------------------------------------------------------------------------- #
# Delivery -- outbox append (bridge schema) + gamma-standup-latest.json.
# --------------------------------------------------------------------------- #

def build_outbox_row(content: str, source: str, queued_at: str) -> dict:
    return {"content": content, "source": source, "queued_at": queued_at}


def append_outbox(row: dict) -> None:
    OUTBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTBOX_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_latest(payload: dict) -> None:
    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LATEST_PATH.with_suffix(LATEST_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(LATEST_PATH)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Gamma's self-initiated Discord standup (morning/EOD).")
    ap.add_argument("--mode", choices=["morning", "eod"], required=True)
    ap.add_argument("--dry-run", action="store_true",
                     help="print only -- no outbox append, no latest.json write")
    args = ap.parse_args(argv)

    now = et_now()
    day = now.strftime("%Y-%m-%d")
    facts = gather_facts(args.mode, day, now)
    text = compose_morning_text(facts) if args.mode == "morning" else compose_eod_text(facts)

    mention = _load_user_mention()
    content = (mention + text).strip()
    if len(content) > 1900:  # Discord hard cap -- same guard every other producer uses
        content = content[:1900] + "...[truncated]"

    queued_at = now.isoformat(timespec="seconds")
    row = build_outbox_row(content, source=f"gamma_standup_{args.mode}", queued_at=queued_at)
    wants_shown = [w["id"] for w in facts.get("wants_top", []) if isinstance(w, dict) and w.get("id")]
    latest_payload = {
        "mode": args.mode,
        "day": day,
        "generated_et": queued_at,
        "text": text,
        "char_len": len(text),
        "wants_shown": wants_shown,
        "focus": facts.get("focus"),  # schema addition 2026-08-08 -- always a real one-line str now
    }

    print(f"[gamma_standup:{args.mode}] {day} ({len(text)} chars)")
    print(text)

    if args.dry_run:
        print("\n[gamma_standup] --dry-run: outbox NOT appended, latest.json NOT written")
        return 0

    try:
        append_outbox(row)
    except OSError as exc:
        print(f"[gamma_standup] OUTBOX APPEND FAILED: {exc}", file=sys.stderr)
        return 1

    try:
        write_latest(latest_payload)
    except OSError as exc:
        print(f"[gamma_standup] latest.json write failed (non-fatal): {exc}", file=sys.stderr)

    print(f"\n[gamma_standup:{args.mode}] queued to Discord outbox ({len(content)} chars incl. mention)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
