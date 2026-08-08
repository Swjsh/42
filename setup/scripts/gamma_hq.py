"""gamma_hq.py -- GAMMA HQ: the always-on VISIBLE terminal window where Gamma lives.

THE GAP THIS CLOSES (J, repeated ask -- see MEMORY.md
feedback_gamma_presence_not_prompting_2026_07_22.md): "Gamma works but is invisible."
J wants one place to glance at where Gamma narrates, in first person, what it is
doing and wanting RIGHT NOW -- not another metrics dashboard, a PRESENCE.

INTENTIONAL WINDOW -- THE SANCTIONED INVERSE OF THE WINDOW-LEAK DOCTRINE.
Every other script in this repo works hard to stay INVISIBLE: pythonw.exe +
CREATE_NO_WINDOW + the wscript/vbs hidden-launch chain exist because a flashing
console on every scheduled-task tick was a real, repeatedly-fixed foot-gun (OP-27
L41; see audit_window_leak_compliance.py's whole reason for existing). GAMMA HQ is
the deliberate, single exception to that doctrine: ONE window, launched ONCE (at
logon via install-gamma-hq.ps1's Startup shortcut, or by hand via
gamma-hq-launch.ps1), that is SUPPOSED to stay visible on J's desktop. Do not "fix"
this by hiding it -- that would undo the entire point of this file.

WHAT IT DOES: an infinite render loop. Every 30s it re-gathers state from disk
(never guesses, never invents a number -- OP-33/C7 discipline), renders one frame
of first-person narration as a professional, PowerShell-report-style screen (title
band, GOAL/TAPE/RIGHT NOW/CLOCKS/I WANT/RECENT SHIPS sections, footer), clears the
screen, and redraws. It is intentionally NOT a wall of numbers -- every section is
short, blank-line-separated, and reads like something a colleague would say.

RESIZABLE: render_frame(..., width=N) drives every rule/wrap/truncation decision.
main() re-queries the live terminal width (shutil.get_terminal_size(), clamped to
MIN_WIDTH..MAX_WIDTH) every single frame, so dragging the window wider/narrower
reflows the NEXT redraw -- no restart needed.

ARCHITECTURE FOR TESTABILITY: gather_state() does ALL the I/O (file reads, mtimes,
git log, today's journal/trades.csv rows) and fails open per-field -- one missing/
corrupt file never blanks the rest of the window. render_frame(state, now_et,
width) is a PURE function: given a state dict, an already-resolved ET datetime,
and a column width, it deterministically returns the frame text, with no disk/
clock access of its own. main() is the thin, impure shell that wires
gather_state -> render_frame -> screen. Tests import render_frame (and
derive_state_word, gather_state, and the small pure math helpers) directly; they
never call main() and never touch a live console -- see backtest/tests/test_gamma_hq.py.

RICH IS OPTIONAL: backtest/.venv currently has `rich`, but this must keep working
even if a future venv rebuild drops it (or any other optional-dep drift) --
import-guarded, never a hard dependency. render_frame() itself never imports rich
at all (plain text only, so its output is exactly testable); rich is used ONLY as
a presentation wrapper around the finished frame string inside _print_frame_rich()
(styled Text lines, no Panel -- see _segment_line()), and any rich failure there
falls back to the raw-ANSI path within the SAME cycle rather than ever crashing
the window. The raw-ANSI path itself has one further fallback: if the terminal
can't even encode the UTF-8 glyphs (emoji, box-drawing bar cells, middle dots),
_asciify() swaps every known glyph for a plain-ASCII substitute (emoji -> bracket
tags like "[GOAL]") so the window still renders cleanly instead of crashing or
spewing "?" replacement characters.

Run:  backtest/.venv/Scripts/python.exe setup/scripts/gamma_hq.py
Launched by: setup/scripts/gamma-hq-launch.ps1 (idempotent; opens the visible
window). Installed to auto-start at logon by: setup/scripts/install-gamma-hq.ps1
(Startup-folder + Desktop shortcuts; never auto-launches itself).
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

from et_clock import et_now  # noqa: E402 -- canonical ET clock; NEVER hand-roll a TZ offset (TZ-systemic lesson)

# OP-27 L41 window-leak discipline: even inside our OWN intentionally-visible window,
# any subprocess WE spawn (git.exe for the RECENT SHIPS section) must not flash a
# second console of its own.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# rich is a nice-to-have presentation layer only -- see module docstring. Never a
# hard dependency; render_frame() never touches it. Panel is deliberately NOT
# imported -- the frame's own rule lines already frame the content, so a rich
# Panel border would just double it; styled Text lines are enough (J's spec).
try:
    from rich.console import Console
    from rich.text import Text
    _HAS_RICH = True
except Exception:  # noqa: BLE001 -- any import/runtime issue just means "no rich today"
    _HAS_RICH = False

STATE = REPO / "automation" / "state"
ANALYSIS = REPO / "analysis"

# Source-of-truth state files (module-level so tests can monkeypatch individual
# paths, e.g. to point gather_state() at an empty directory).
WATCHER_LIVE_STATE = STATE / ".watcher-live-state.json"
FUTURES_MIRROR = STATE / "futures" / "mirror-would-be.jsonl"
AGGRESSIVE_LOOP_STATE = STATE / "aggressive" / "loop-state.json"
STANDUP_LATEST = STATE / "gamma-standup-latest.json"
SSR_SHADOW_PROGRESS = STATE / "futures" / "ssr-shadow-progress.json"
MES_SHADOW_PROGRESS = STATE / "futures" / "shadow-progress.json"
CATASTROPHE_LEDGER = ANALYSIS / "recommendations" / "catastrophe-cap-shadow-ledger.jsonl"
GAMMA_WANTS = STATE / "gamma-wants.json"
TRADES_CSV = REPO / "journal" / "trades.csv"

REFRESH_SECS = 30
PLACEHOLDER = "—"  # em dash "--" -- the one universal "nothing here yet" glyph

# Resizable-terminal bounds (CHANGES #1): main() re-probes the live terminal width
# every frame and clamps into this range before handing it to render_frame(). The
# clamp also runs INSIDE render_frame() itself so the function stays safe (never
# raises) no matter what a caller/test passes.
MIN_WIDTH = 60
MAX_WIDTH = 160
DEFAULT_WIDTH = 100

_CLOCK_LABEL_WIDTH = 13  # "Cap re-check" (12) + 1 -- the longest of the 3 clock labels
_BAR_CELLS = 10
_CATASTROPHE_CAP_CADENCE = 20

_GOAL_LINE = "$100–200/day — one clean level trade pays the day (FOCUS-DOCTRINE)"
_FOOTER_TEXT = "\U0001f4ac talk to me → claw chat · #gamma · standups 08:15 & 16:45 ET weekdays"

# Text that must NEVER leak verbatim into the narration window, even if some
# upstream producer wrote a raw traceback or dashboard-speak status word into a
# state file. GAMMA HQ narrates in first person -- it does not dump internals.
_BANNED_SUBSTRINGS = ("traceback (most recent call last)", "degraded")


# --------------------------------------------------------------------------------
# Pure helpers (no I/O) -- safe to unit test in isolation
# --------------------------------------------------------------------------------

def derive_state_word(now_et: datetime) -> str:
    """TRADING / RESEARCHING / STANDING BY from an already-resolved ET datetime.

    Mirrors et_clock.is_market_hours' Mon-Fri 09:30<=ET<15:55 threshold literally
    (930/1555, same boundary semantics) rather than calling it, because
    is_market_hours only accepts a UTC instant and re-derives "now" internally --
    calling it here would make render_frame's output depend on the real wall
    clock even under test, breaking the "render_frame is a pure function of its
    arguments" contract this module is built around. et_clock.py remains the
    single source of truth for the THRESHOLD VALUES; this just can't call through
    to it without losing purity. If that window ever changes, update both.
    """
    if now_et.weekday() >= 5:  # Saturday / Sunday
        return "STANDING BY"
    hhmm = now_et.hour * 100 + now_et.minute
    if 930 <= hhmm < 1555:
        return "TRADING"
    return "RESEARCHING"


def _clamp_width(width: object) -> int:
    """Coerce anything into a sane column width. Never raises: a non-numeric or
    missing width just falls back to DEFAULT_WIDTH rather than blowing up the one
    window on this rig that's supposed to always be up."""
    try:
        w = int(width)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_WIDTH
    return max(MIN_WIDTH, min(MAX_WIDTH, w))


def _truncate(text: str, max_len: int, ellipsis: str = "…") -> str:
    """Truncate to at most max_len characters, cutting at the last whitespace
    boundary within budget rather than mid-word, then appending `ellipsis`.
    Never leaves a dangling partial word/punctuation -- the real bug this
    fixes (2026-08-08, J's own smoke-test catch): the OLD blind text[:max_len]
    slice cut a want item to "...futures edge that'", a mid-word cut leaving a
    stray apostrophe. Falls back to a hard slice only when there's no
    whitespace anywhere in budget (one giant unbroken token) or max_len is too
    small to fit the ellipsis at all. Always len(result) <= max_len. The
    ellipsis is a real unicode "…" (not ASCII "...") -- covered in
    _ASCII_SUBSTITUTES for the no-UTF8 fallback path like every other glyph
    this module renders.
    """
    if len(text) <= max_len:
        return text
    budget = max_len - len(ellipsis)
    if budget <= 0:
        return text[:max_len]
    cut = text[:budget]
    boundary = cut.rfind(" ")
    if boundary > 0:
        cut = cut[:boundary]
    cut = cut.rstrip(" \t,.;:-")
    if not cut:
        # no whitespace anywhere in budget (one giant unbroken token) -- fall
        # back to a hard slice rather than return a bare ellipsis
        cut = text[:budget]
    return cut + ellipsis


def _sanitize_line(raw: object, max_len: int = 120, fallback: str = "(unavailable)") -> str:
    """Collapse arbitrary source-file text into one narration-safe line.

    Three jobs: (1) never let a multi-line blob (e.g. an accidental traceback
    written by some other producer) reach the screen as anything but a single
    flattened line, (2) refuse known-banned substrings outright rather than
    display them, (3) bound the length so one bad field can't blow out the
    layout -- via _truncate's word-boundary cut, never a blind mid-word slice.
    Used on every piece of free text this window displays that ultimately
    originates from a semi-trusted upstream file (standup summary/focus, I
    WANT items, RECENT SHIPS commit subjects, trade account ids) -- numbers/
    timestamps/booleans never go through here because fixed narration templates
    render those directly.
    """
    if raw is None:
        return fallback
    text = str(raw).strip()
    if not text:
        return fallback
    text = " ".join(text.split())  # collapse embedded newlines/whitespace to one line
    lowered = text.lower()
    for banned in _BANNED_SUBSTRINGS:
        if banned in lowered:
            return fallback
    return _truncate(text, max_len)


def _wrap_block(text: str, width: int, *, indent: str = "  ", first_prefix: str = "") -> list[str]:
    """Wrap `text` so every returned line (already including `indent`/
    `first_prefix`) fits within `width` columns -- the shared width-adaptation
    primitive every free-text section line goes through. Continuation lines
    hang-indent to align under where the first line's text began (indent +
    len(first_prefix) spaces), never under the bare indent alone -- this is what
    makes numbered "I WANT" items (first_prefix="1. ") align cleanly under their
    own text on wrap. break_long_words=True guarantees no single pathological
    unbroken "word" can ever push a line past width, even adversarially. Always
    returns at least one line, even for an empty string.
    """
    hang = indent + (" " * len(first_prefix))
    avail = max(10, width - len(indent) - len(first_prefix))
    pieces = textwrap.wrap(text, width=avail, break_long_words=True, break_on_hyphens=False) or [""]
    lines = [f"{indent}{first_prefix}{pieces[0]}"]
    lines.extend(f"{hang}{p}" for p in pieces[1:])
    return lines


def _progress_bar(have: Optional[int], need: int) -> str:
    """Render a 10-cell filled/empty bar: bar = min(have,need)/need scaled to
    _BAR_CELLS. Overfull (have > need) clamps to a FULL bar -- the raw numbers
    (not this bar) are what show the true have/need in _clock_line."""
    need_safe = need if isinstance(need, int) and need > 0 else 1
    have_val = have if isinstance(have, int) and have >= 0 else 0
    filled_raw = min(have_val, need_safe)
    cells = round(filled_raw / need_safe * _BAR_CELLS)
    cells = max(0, min(_BAR_CELLS, cells))
    return ("▰" * cells) + ("▱" * (_BAR_CELLS - cells))


def _clock_line(label: str, have: Optional[int], need: int, extra: str = "") -> str:
    bar = _progress_bar(have, need)
    have_str = str(have) if isinstance(have, int) else PLACEHOLDER
    return f"{label.ljust(_CLOCK_LABEL_WIDTH)}{bar} {have_str}/{need}{extra}"


def _extract_progress(payload: Optional[dict], default_need: int = 20) -> tuple[Optional[int], int]:
    """Read (have, need) off a *-shadow-progress.json-shaped dict, fail-open.

    Reads the target ('need') from the file's own arming_bar.round_trips_needed
    when present (so a future change to the arming bar upstream is reflected here
    automatically) and falls back to default_need only when the field is absent --
    today that's always 20 for both SSR and MES shadows, matching the spec.
    """
    if not isinstance(payload, dict):
        return None, default_need
    have = payload.get("n_round_trips")
    arming = payload.get("arming_bar") or {}
    need = arming.get("round_trips_needed", default_need) if isinstance(arming, dict) else default_need
    have_val = int(have) if isinstance(have, (int, float)) else None
    need_val = int(need) if isinstance(need, (int, float)) else default_need
    return have_val, need_val


def _needs_beats_null_suffix(beats_null: Optional[object]) -> str:
    """" · needs beats-null" only while the shadow is genuinely short of that
    bar (beats_null is False). True (already beats null) or None/missing
    (not yet evaluated) both render with no caveat -- there's nothing actionable
    to flag."""
    if beats_null is False:
        return " · needs beats-null"
    return ""


def _extract_want_text(item: object) -> object:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("title", "text", "want", "summary", "label"):
            v = item.get(key)
            if isinstance(v, str) and v.strip():
                return v
    return item  # _sanitize_line's str() will make a best effort on anything else


def _extract_standup_text(standup: Optional[dict]) -> Optional[str]:
    # gamma-standup-latest.json's schema is owned by gamma_standup.py (a sibling
    # tool). Defensive multi-key lookup so whichever field name that tool uses
    # has a reasonable chance of being picked up without a code change here;
    # always falls open to None (caller renders a generic placeholder) either way.
    if not isinstance(standup, dict):
        return None
    for key in ("summary", "text", "narrative", "headline", "today"):
        v = standup.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return None


def _today_focus_text(standup: Optional[dict]) -> str:
    """The GOAL section's second line -- what used to be the standalone TODAY:
    section, now folded in per spec. Three-tier fail-open priority:

    1. standup["focus"] (added 2026-08-08 in gamma_standup.py per this exact
       flag): a purpose-built one-line summary -- the TODAY section's own
       bullet, markdown-stripped, <=110 chars -- written ONLY for morning-mode
       standups (EOD has no TODAY section, so gamma_standup.py leaves this
       None there). This is the semantically-correct "today's focus" content;
       prefer it whenever present.
    2. First-line-of-"text" (2026-08-08 smoke-test fix, kept as the fallback):
       gamma_standup.py's real gamma-standup-latest.json schema stores the
       FULL multi-paragraph composed standup body under "text" (no one-line
       "summary" field despite _extract_standup_text's defensive multi-key
       lookup hoping for one) -- rendering that whole blob produced exactly
       the mid-word-truncated wall of text this whole redesign exists to
       eliminate. gamma_standup's compose_morning_text/compose_eod_text always
       open with a short, fixed, variable-free greeting line ("Morning J --
       Gamma here." / "EOD from Gamma.") followed by a blank line then the
       detail sections, so taking just the first line yields a clean one-liner
       -- this is what covers EOD-mode standups (no "focus" field) and any
       morning standup whose "focus" derivation is somehow absent.
    3. The Monday/"(standup on file...)" placeholders when standup itself has
       neither field usably populated.

    Banned-content scrubbing (_sanitize_line) runs on whichever tier wins, and
    since only ONE line is ever displayed, content further down a multi-line
    "text" blob (which could theoretically contain a banned word) is never at
    risk of leaking -- it's simply never shown.
    """
    if isinstance(standup, dict):
        focus = standup.get("focus")
        if isinstance(focus, str) and focus.strip():
            return _sanitize_line(focus)
    text = _extract_standup_text(standup)
    if text is None:
        if isinstance(standup, dict) and standup:
            # file exists and parsed, just no field we recognize -- say so plainly
            # rather than silently falling back to the "no standup yet" message,
            # which would misreport that the sibling tool hasn't run.
            return "(standup on file, no readable summary field)"
        return "First standup lands Monday 08:15 ET"
    first_line = text.strip().split("\n", 1)[0].strip()
    return _sanitize_line(first_line or text)


_CONVENTIONAL_PREFIX_RE = re.compile(r"^[a-z]+(\([^)]*\))?:\s*(.+)$")


def _humanize_commit_subject(subject: object, max_len: int) -> str:
    """RECENT SHIPS bullet text: sanitize (banned-word + collapse, same as every
    other free-text field), strip a leading conventional-commit "type(scope):"
    or "type:" prefix if present (lowercase type only, e.g. feat/fix/docs/chore
    -- matches this repo's actual commit convention, see `git log --oneline`),
    sentence-case the remainder, then truncate to width. A non-conventional
    subject (e.g. a merge commit) passes through unstripped, just sanitized +
    truncated."""
    text = _sanitize_line(subject, max_len=500)
    m = _CONVENTIONAL_PREFIX_RE.match(text)
    if m:
        text = m.group(2).strip()
    if text:
        text = text[0].upper() + text[1:]
    return _truncate(text, max_len)


def _pnl_segments(rows: list[dict]) -> list[tuple[str, int, float]]:
    """[(account_id, n_trades, net_pnl), ...] sorted by account_id, aggregated
    from journal/trades.csv rows already filtered to one day. Pattern reused
    from setup/scripts/gamma_standup.py's _pnl_segments (same fail-open shape:
    blank account_id or non-numeric dollar_pnl rows are skipped, never crash on
    a dirty row -- trades.csv accumulates hand-edited/backfilled rows over
    time, so this can't assume clean data)."""
    agg: dict = defaultdict(lambda: [0, 0.0])
    for r in rows:
        if not isinstance(r, dict):
            continue
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


def _fmt_signed_money(x: float) -> str:
    if abs(x) < 0.005:
        return "flat $0"
    sign = "+" if x > 0 else "-"
    return f"{sign}${abs(x):,.0f}"


def _rule(width: int, ch: str = "=") -> str:
    return ch * width


def _state_chip(state_word: str) -> str:
    return f"● {state_word}"


def _section_title(state_word: str, now_et: datetime, width: int) -> str:
    left = "⚡ GAMMA"
    chip = _state_chip(state_word)
    gap = max(1, width - len(left) - len(chip))
    line1 = f"{left}{' ' * gap}{chip}"
    stamp = now_et.strftime("%A %Y-%m-%d") + " · " + now_et.strftime("%H:%M ET")
    return "\n".join([_rule(width), line1, stamp, _rule(width)])


def _section_goal(standup: Optional[dict], width: int) -> str:
    focus = _today_focus_text(standup)
    lines = ["\U0001f3af GOAL"]
    lines.extend(_wrap_block(_GOAL_LINE, width))
    lines.extend(_wrap_block(f"Today's focus: {focus}", width))
    return "\n".join(lines)


def _section_tape(tape: Optional[dict], width: int) -> str:
    lines = ["\U0001f4b0 TODAY'S TAPE"]
    segments: list[tuple[str, int, float]] = []
    if isinstance(tape, dict) and isinstance(tape.get("segments"), list):
        for item in tape["segments"]:
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                continue
            acct, n, pnl = item
            try:
                segments.append((_sanitize_line(acct, max_len=30), int(n), float(pnl)))
            except (TypeError, ValueError):
                continue
    if not segments:
        lines.extend(_wrap_block("Market closed — research mode.", width))
        return "\n".join(lines)
    n_total = sum(n for _, n, _ in segments)
    net_total = sum(p for _, _, p in segments)
    headline = f"{n_total} trade{'s' if n_total != 1 else ''} · net {_fmt_signed_money(net_total)}"
    lines.extend(_wrap_block(headline, width))
    for acct, n, pnl in segments:
        line = f"{acct}: {n} trade{'s' if n != 1 else ''}, {_fmt_signed_money(pnl)}"
        lines.extend(_wrap_block(line, width, indent="    "))
    return "\n".join(lines)


def _section_right_now(right_now: dict, state_word: str, width: int) -> str:
    watcher = right_now.get("watcher_mtime_et") if isinstance(right_now, dict) else None
    futures = right_now.get("futures_tail_et") if isinstance(right_now, dict) else None
    aggressive = right_now.get("aggressive_mtime_et") if isinstance(right_now, dict) else None
    candidates = [t for t in (watcher, futures, aggressive) if isinstance(t, datetime)]
    lines = ["⏱ RIGHT NOW"]
    if not candidates:
        lines.append(f"  {PLACEHOLDER}")
        return "\n".join(lines)
    freshest = max(candidates)
    stamp = freshest.strftime("%H:%M ET")
    if state_word == "TRADING":
        sentence = f"Watching SPY off the 5m engine; last tick {stamp}"
    else:
        sentence = f"Grinding research queue; last fire {stamp}"
    lines.extend(_wrap_block(sentence, width))
    return "\n".join(lines)


def _section_clocks(clocks: dict, width: int) -> str:
    clocks = clocks if isinstance(clocks, dict) else {}
    ssr = clocks.get("ssr")
    mes = clocks.get("mes")
    cat_n = clocks.get("catastrophe_n")

    ssr_have, ssr_need = _extract_progress(ssr)
    mes_have, mes_need = _extract_progress(mes)
    beats_null = (mes.get("arming_bar") or {}).get("beats_null") if isinstance(mes, dict) else None
    cat_have = int(cat_n) if isinstance(cat_n, (int, float)) else None

    lines = [
        "\U0001f4ca MY CLOCKS",
        f"  {_clock_line('SSR shadow', ssr_have, ssr_need)}",
        f"  {_clock_line('MES mirror', mes_have, mes_need, extra=_needs_beats_null_suffix(beats_null))}",
        f"  {_clock_line('Cap re-check', cat_have, _CATASTROPHE_CAP_CADENCE)}",
    ]
    return "\n".join(lines)


def _section_wants(wants: Optional[list], width: int) -> str:
    items = wants if isinstance(wants, list) else []
    lines = ["\U0001f64f I WANT"]
    picked = items[:3]
    if not picked:
        lines.append(f"  {PLACEHOLDER}")
        return "\n".join(lines)
    for i, item in enumerate(picked, start=1):
        text = _sanitize_line(_extract_want_text(item))
        lines.extend(_wrap_block(text, width, indent="  ", first_prefix=f"{i}. "))
    return "\n".join(lines)


def _section_recent(commits: Optional[list], width: int) -> str:
    items = commits if isinstance(commits, list) else []
    lines = ["\U0001f9fe RECENT SHIPS"]
    if not items:
        lines.append(f"  {PLACEHOLDER}")
        return "\n".join(lines)
    avail = max(20, width - 4)  # 2-space indent + "· " bullet
    for subj in items[:4]:
        lines.append(f"  · {_humanize_commit_subject(subj, avail)}")
    return "\n".join(lines)


def _section_footer(width: int) -> str:
    lines = [_rule(width, "-")]
    lines.extend(_wrap_block(_FOOTER_TEXT, width, indent=""))
    return "\n".join(lines)


def render_frame(state: dict, now_et: datetime, width: int = DEFAULT_WIDTH) -> str:
    """Pure: (state dict, ET datetime, column width) -> the full frame text. No
    I/O, no clock access, deterministic. Every section header renders
    unconditionally (so all 8 layout blocks -- title band, GOAL, TODAY'S TAPE,
    RIGHT NOW, MY CLOCKS, I WANT, RECENT SHIPS, footer -- are always present);
    only the DATA inside a section degrades to a placeholder when the
    corresponding state is missing/malformed. Never raises -- every lookup below
    is defensive against a missing key, a wrong type, or an empty/partial
    fixture, and width is clamped defensively so a bad caller can't break the
    "never raises" contract either.
    """
    state = state if isinstance(state, dict) else {}
    width = _clamp_width(width)
    state_word = derive_state_word(now_et)

    blocks = [
        _section_title(state_word, now_et, width),
        _section_goal(state.get("standup"), width),
        _section_tape(state.get("tape"), width),
        _section_right_now(state.get("right_now") or {}, state_word, width),
        _section_clocks(state.get("clocks") or {}, width),
        _section_wants(state.get("wants"), width),
        _section_recent(state.get("recent_commits"), width),
        _section_footer(width),
    ]
    return "\n\n".join(blocks)


# ASCII-safe fallback (CHANGES #3): every glyph this module ever renders, mapped
# to a plain-ASCII substitute. Applied ONLY on the last-resort path in
# _print_frame() when the terminal can't even encode UTF-8 -- the normal path
# (rich, or raw-ANSI on a UTF-8-capable console) renders the real glyphs.
# Section-anchor emoji become bracket tags (J's own example: "\U0001f3af" -> "[GOAL]");
# the structural glyphs (bar cells, bullet, separators) become plain punctuation.
_ASCII_SUBSTITUTES = {
    "⚡": "[GAMMA]",     # title bolt
    "\U0001f3af": "[GOAL]",  # GOAL section
    "\U0001f4b0": "[TAPE]",  # TODAY'S TAPE section
    "⏱": "[NOW]",       # RIGHT NOW section
    "\U0001f4ca": "[CLOCKS]",  # MY CLOCKS section
    "\U0001f64f": "[WANT]",  # I WANT section
    "\U0001f9fe": "[SHIPS]",  # RECENT SHIPS section
    "\U0001f4ac": "[CHAT]",  # footer chat bubble
    "●": "*",            # state chip bullet
    "▰": "#",             # progress bar filled cell
    "▱": "-",             # progress bar empty cell
    "·": "-",             # middle-dot separator/bullet
    "→": "->",            # footer arrow
    "–": "-",             # en dash (GOAL line)
    "—": "-",             # em dash (PLACEHOLDER + stray narration dashes)
    "…": "...",           # _truncate's word-boundary ellipsis (I WANT / RECENT SHIPS / focus)
}


def _asciify(text: str) -> str:
    """Pure string transform: every known glyph -> its ASCII substitute, then a
    last-resort blanket safety net for anything unmapped that might have slipped
    in from untrusted upstream content (e.g. a stray unicode char pasted into a
    want/commit-subject) -- guarantees the result is ALWAYS pure ASCII, never
    raises downstream, and never renders as blind "?" mojibake for a glyph we
    actually know about."""
    for glyph, sub in _ASCII_SUBSTITUTES.items():
        if glyph in text:
            text = text.replace(glyph, sub)
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        text = text.encode("ascii", errors="replace").decode("ascii")
    return text


# --------------------------------------------------------------------------------
# Impure helpers -- all disk/process I/O lives here, each individually fail-open
# --------------------------------------------------------------------------------

def _read_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 -- missing file, bad JSON, permission error: all "no data"
        return None
    return data if isinstance(data, (dict, list)) else None


def _mtime_et(path: Path) -> Optional[datetime]:
    try:
        ts = path.stat().st_mtime
    except OSError:
        return None
    try:
        return et_now(now_utc=datetime.fromtimestamp(ts, tz=timezone.utc))
    except Exception:  # noqa: BLE001
        return None


def _tail_line_json(path: Path) -> Optional[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for ln in reversed(text.splitlines()):
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except Exception:  # noqa: BLE001 -- a corrupt trailing line just means "no tail"
            continue
        return obj if isinstance(obj, dict) else None
    return None


def _count_nonblank_lines(path: Path) -> Optional[int]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return sum(1 for ln in text.splitlines() if ln.strip())


def _recent_commit_subjects(n: int = 4) -> list:
    try:
        r = subprocess.run(
            ["git", "log", "--oneline", f"-{n}"],
            cwd=str(REPO), capture_output=True, encoding="utf-8", errors="replace",
            timeout=10, creationflags=_CREATE_NO_WINDOW,
        )
    except Exception:  # noqa: BLE001 -- git missing, not a repo, timeout: all "no recent"
        return []
    subjects = []
    for ln in (r.stdout or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        parts = ln.split(" ", 1)  # drop the abbreviated hash, keep the subject
        subjects.append(parts[1] if len(parts) == 2 else ln)
    return subjects[:n]


def _trades_rows_for_day(path: Path, day: str) -> list[dict]:
    """journal/trades.csv rows whose `date` column matches `day` (YYYY-MM-DD,
    ET). Column-handling pattern reused from setup/scripts/gamma_standup.py's
    _trades_rows_for_day (csv.DictReader, newline="" so quoted multi-line notes
    fields parse correctly). Fail-open: missing file or any read/parse error
    both mean "no rows today", never a crash."""
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            return [row for row in reader if (row.get("date") or "").strip() == day]
    except Exception:  # noqa: BLE001 -- malformed CSV, permission error: all "no rows today"
        return []


def gather_state(now_et: Optional[datetime] = None) -> dict:
    """All the impure I/O for one frame. Returns the plain dict render_frame()
    consumes. Every field is individually try/except-guarded upstream (in the
    small helpers above) so one bad file degrades only its own section, never the
    whole window. `now_et` is injectable for deterministic tests (it decides
    which journal/trades.csv rows count as "today's tape"); defaults to the real
    current ET instant in production. Shape:

        {
          "right_now": {"watcher_mtime_et": dt|None, "futures_tail_et": dt|None,
                         "aggressive_mtime_et": dt|None},
          "standup": dict|None,
          "clocks": {"ssr": dict|None, "mes": dict|None, "catastrophe_n": int|None},
          "wants": list|None,
          "recent_commits": list[str],
          "tape": {"segments": [(account_id, n_trades, net_pnl), ...]},
        }
    """
    if now_et is None:
        now_et = et_now()

    futures_tail = _tail_line_json(FUTURES_MIRROR)
    futures_tail_et: Optional[datetime] = None
    if futures_tail:
        raw_ts = futures_tail.get("ts_et")
        if raw_ts:
            try:
                futures_tail_et = datetime.fromisoformat(str(raw_ts))
            except Exception:  # noqa: BLE001
                futures_tail_et = None

    wants_raw = _read_json(GAMMA_WANTS)
    if isinstance(wants_raw, list):
        wants = wants_raw
    elif isinstance(wants_raw, dict):
        inner = wants_raw.get("wants")  # tolerate a {"wants": [...]} wrapper shape
        wants = inner if isinstance(inner, list) else None
    else:
        wants = None

    standup_raw = _read_json(STANDUP_LATEST)
    standup = standup_raw if isinstance(standup_raw, dict) else None

    day = now_et.strftime("%Y-%m-%d")
    tape_rows = _trades_rows_for_day(TRADES_CSV, day)

    return {
        "right_now": {
            "watcher_mtime_et": _mtime_et(WATCHER_LIVE_STATE),
            "futures_tail_et": futures_tail_et,
            "aggressive_mtime_et": _mtime_et(AGGRESSIVE_LOOP_STATE),
        },
        "standup": standup,
        "clocks": {
            "ssr": _read_json(SSR_SHADOW_PROGRESS),
            "mes": _read_json(MES_SHADOW_PROGRESS),
            "catastrophe_n": _count_nonblank_lines(CATASTROPHE_LEDGER),
        },
        "wants": wants,
        "recent_commits": _recent_commit_subjects(4),
        "tape": {"segments": _pnl_segments(tape_rows)},
    }


# --------------------------------------------------------------------------------
# Presentation + loop -- the thin, impure shell. Never unit-tested directly.
# --------------------------------------------------------------------------------

# Per-line style classification shared by BOTH presentation paths (rich Text and
# raw ANSI) so they can never visually disagree about what gets colored: rules
# dim, section/title headers bold, the state chip green/cyan/grey, and any
# "+$N"/"-$N" money token green/red wherever it appears (TODAY'S TAPE, and
# incidentally any I WANT item that happens to mention a dollar figure -- that's
# fine, money reads the same color everywhere in this window on purpose).
_SECTION_HEADER_PREFIXES = (
    "\U0001f3af ", "\U0001f4b0 ", "⏱ ", "\U0001f4ca ", "\U0001f64f ", "\U0001f9fe ", "⚡ ",
)
_MONEY_RE = re.compile(r"[+\-]\$[\d,]+")
_CHIP_STYLES = (
    ("● TRADING", "green"),
    ("● RESEARCHING", "cyan"),
    ("● STANDING BY", "grey"),
)


def _segment_line(line: str) -> list[tuple[str, Optional[str]]]:
    """One rendered line -> [(text, style_key), ...] segments. style_key is one
    of "dim"/"bold"/"green"/"cyan"/"grey"/"red"/None. Pure and side-effect-free
    so both _print_frame_rich and _ansi_style_line can consume it identically."""
    stripped = line.strip()
    if stripped and len(set(stripped)) == 1 and stripped[0] in "=-":
        return [(line, "dim")]
    for chip, style in _CHIP_STYLES:
        idx = line.find(chip)
        if idx == -1:
            continue
        segs: list[tuple[str, Optional[str]]] = []
        prefix = line[:idx]
        if prefix:
            segs.append((prefix, "bold" if prefix.strip() else None))
        segs.append((chip, style))
        suffix = line[idx + len(chip):]
        if suffix:
            segs.append((suffix, None))
        return segs
    if any(line.startswith(p) for p in _SECTION_HEADER_PREFIXES):
        return [(line, "bold")]
    segs = []
    pos = 0
    for m in _MONEY_RE.finditer(line):
        if m.start() > pos:
            segs.append((line[pos:m.start()], None))
        segs.append((m.group(0), "green" if m.group(0).startswith("+") else "red"))
        pos = m.end()
    if pos < len(line):
        segs.append((line[pos:], None))
    return segs or [(line, None)]


_ANSI_STYLE_CODES = {
    "dim": "\x1b[2m",
    "bold": "\x1b[1m",
    "green": "\x1b[32m",
    "cyan": "\x1b[36m",
    "grey": "\x1b[90m",
    "red": "\x1b[31m",
}
_ANSI_RESET = "\x1b[0m"

_RICH_STYLE_NAMES = {
    "dim": "dim",
    "bold": "bold",
    "green": "green",
    "cyan": "cyan",
    "grey": "bright_black",
    "red": "red",
}


def _ansi_style_line(line: str) -> str:
    out = []
    for text, style in _segment_line(line):
        if style:
            out.append(f"{_ANSI_STYLE_CODES[style]}{text}{_ANSI_RESET}")
        else:
            out.append(text)
    return "".join(out)


def _print_frame_rich(frame: str) -> None:
    """Draw one frame via rich: styled Text lines, no Panel (border-free by
    design -- see module docstring). Any failure here is caught by the caller
    and falls through to the raw-ANSI path within the SAME cycle."""
    console = Console()
    console.clear()
    text = Text()
    for i, line in enumerate(frame.split("\n")):
        if i:
            text.append("\n")
        for seg, style in _segment_line(line):
            if style:
                text.append(seg, style=_RICH_STYLE_NAMES[style])
            else:
                text.append(seg)
    console.print(text)


def _print_frame(frame: str) -> None:
    """Draw one frame. Tries rich first; ANY failure there falls through to the
    raw-ANSI path in the SAME cycle. The raw-ANSI path itself has one further
    fallback (UnicodeEncodeError -> _asciify) -- this function must never raise,
    or the window dies."""
    if _HAS_RICH:
        try:
            _print_frame_rich(frame)
            return
        except Exception:  # noqa: BLE001 -- rich misbehaved; fall back below, don't crash
            pass
    styled = "\n".join(_ansi_style_line(ln) for ln in frame.split("\n"))
    output = "\x1b[2J\x1b[H" + styled + "\n"  # full clear + cursor home, then the frame
    try:
        sys.stdout.write(output)
    except UnicodeEncodeError:
        # stdout is stuck on a non-UTF8 codepage (main()'s reconfigure() didn't
        # take, or this is some redirected/legacy pipe) -- degrade to the known
        # ASCII substitutes rather than crash the one window on this rig that's
        # supposed to always be up. _asciify runs on the ALREADY-ANSI-styled
        # string: the escape codes are pure ASCII bytes themselves, so they pass
        # through untouched while the glyph characters get swapped.
        sys.stdout.write("\x1b[2J\x1b[H" + _asciify(styled) + "\n")
    sys.stdout.flush()


def _terminal_width() -> int:
    """Live terminal column count, clamped to MIN_WIDTH..MAX_WIDTH. Re-queried
    every frame in main() so a mid-run window resize reflows on the NEXT redraw
    -- never raises (shutil.get_terminal_size itself already falls back to
    `fallback` internally when no real terminal is attached; the try/except here
    is a second, cheap layer of the same fail-open discipline every other I/O
    call in this module follows)."""
    try:
        cols = shutil.get_terminal_size(fallback=(DEFAULT_WIDTH, 24)).columns
    except Exception:  # noqa: BLE001
        cols = DEFAULT_WIDTH
    return _clamp_width(cols)


def main() -> None:
    if sys.platform == "win32":
        try:
            os.system("")  # flips modern Windows consoles into VT100/ANSI-escape mode
        except Exception:  # noqa: BLE001
            pass
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:  # noqa: BLE001
            pass

    while True:
        try:
            now_et = et_now()
            state = gather_state(now_et)
            width = _terminal_width()
            frame = render_frame(state, now_et, width=width)
            _print_frame(frame)
        except Exception as exc:  # noqa: BLE001 -- the window must survive indefinitely
            try:
                sys.stdout.write(f"\n[render hiccup, retrying] {type(exc).__name__}: {exc}\n")
                sys.stdout.flush()
            except Exception:  # noqa: BLE001
                pass
        time.sleep(REFRESH_SECS)


if __name__ == "__main__":
    main()
