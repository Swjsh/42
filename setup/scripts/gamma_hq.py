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
of first-person narration, clears the screen, and redraws. It is intentionally NOT
a metrics dashboard -- no tables of numbers for their own sake; every line reads
like something a colleague would actually say.

ARCHITECTURE FOR TESTABILITY: gather_state() does ALL the I/O (file reads, mtimes,
git log) and fails open per-field -- one missing/corrupt file never blanks the rest
of the window. render_frame(state, now_et) is a PURE function: given a state dict
and an already-resolved ET datetime, it deterministically returns the frame text,
with no disk/clock access of its own. main() is the thin, impure shell that wires
gather_state -> render_frame -> screen. Tests import render_frame (and
derive_state_word, gather_state) directly; they never call main() and never touch
a live console -- see backtest/tests/test_gamma_hq.py.

RICH IS OPTIONAL: backtest/.venv currently has `rich`, but this must keep working
even if a future venv rebuild drops it (or any other optional-dep drift) --
import-guarded, never a hard dependency. render_frame() itself never imports rich
at all (plain text only, so its output is exactly testable); rich is used ONLY as
a presentation wrapper around the finished frame string inside _print_frame(), and
any rich failure there falls back to the plain ANSI path within the SAME cycle
rather than ever crashing the window.

Run:  backtest/.venv/Scripts/python.exe setup/scripts/gamma_hq.py
Launched by: setup/scripts/gamma-hq-launch.ps1 (idempotent; opens the visible
window). Installed to auto-start at logon by: setup/scripts/install-gamma-hq.ps1
(Startup-folder + Desktop shortcuts; never auto-launches itself).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

from et_clock import et_now  # noqa: E402 -- canonical ET clock; NEVER hand-roll a TZ offset (TZ-systemic lesson)

# OP-27 L41 window-leak discipline: even inside our OWN intentionally-visible window,
# any subprocess WE spawn (git.exe for the RECENT section) must not flash a second
# console of its own.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# rich is a nice-to-have presentation layer only -- see module docstring. Never a
# hard dependency; render_frame() never touches it.
try:
    from rich.console import Console
    from rich.panel import Panel
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

REFRESH_SECS = 30
PLACEHOLDER = "—"  # em dash "-" -- the one universal "nothing here yet" glyph
_WIDTH = 64

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


def _sanitize_line(raw: object, max_len: int = 120, fallback: str = "(unavailable)") -> str:
    """Collapse arbitrary source-file text into one narration-safe line.

    Three jobs: (1) never let a multi-line blob (e.g. an accidental traceback
    written by some other producer) reach the screen as anything but a single
    flattened line, (2) refuse known-banned substrings outright rather than
    display them, (3) bound the length so one bad field can't blow out the
    ~64-col layout. Used on every piece of free text this window displays that
    ultimately originates from a semi-trusted upstream file (standup summary,
    I WANT items, RECENT commit subjects) -- numbers/timestamps/booleans never
    go through here because fixed narration templates render those directly.
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
    return text[:max_len]


def _progress_tick(label: str, have: Optional[int], need: int, extra: str = "") -> str:
    have_str = str(have) if have is not None else PLACEHOLDER
    return f"{label} ▸ {have_str}/{need}{extra}"


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


def _beats_null_suffix(beats_null: Optional[object]) -> str:
    if not isinstance(beats_null, bool):
        return ""
    return f" (beats_null: {'yes' if beats_null else 'no'})"


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
    # gamma-standup-latest.json's schema isn't finalized as of this build (no
    # sibling standup tool exists yet -- the file is confirmed absent today).
    # Defensive multi-key lookup so whichever field name that tool ships with
    # has a reasonable chance of being picked up without a code change; always
    # falls open to None (caller renders a generic placeholder) either way.
    if not isinstance(standup, dict):
        return None
    for key in ("summary", "text", "narrative", "headline", "today"):
        v = standup.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return None


def _rule(ch: str = "=") -> str:
    return ch * _WIDTH


def _section_header(state_word: str, now_et: datetime) -> str:
    title = "GAMMA HQ"
    tag = f"[{state_word}]"
    pad = max(1, _WIDTH - len(title) - len(tag))
    stamp = now_et.strftime("%A %Y-%m-%d · %H:%M:%S ET")
    return "\n".join([_rule(), f"{title}{' ' * pad}{tag}", f"  {stamp}", _rule()])


def _section_right_now(right_now: dict, state_word: str) -> str:
    watcher = right_now.get("watcher_mtime_et") if isinstance(right_now, dict) else None
    futures = right_now.get("futures_tail_et") if isinstance(right_now, dict) else None
    aggressive = right_now.get("aggressive_mtime_et") if isinstance(right_now, dict) else None
    candidates = [t for t in (watcher, futures, aggressive) if isinstance(t, datetime)]
    if not candidates:
        return f"RIGHT NOW:\n  {PLACEHOLDER}"
    freshest = max(candidates)
    stamp = freshest.strftime("%H:%M ET")
    if state_word == "TRADING":
        line = f"Watching SPY off the 5m engine; last tick {stamp}"
    else:
        line = f"Grinding research queue; last fire {stamp}"
    return f"RIGHT NOW:\n  {line}"


def _section_today(standup: Optional[dict]) -> str:
    text = _extract_standup_text(standup)
    if text is None:
        if isinstance(standup, dict) and standup:
            # file exists and parsed, just no field we recognize -- say so plainly
            # rather than silently falling back to the "no standup yet" message,
            # which would misreport that the sibling tool hasn't run.
            line = "(standup on file, no readable summary field)"
        else:
            line = "First standup lands Monday 08:15 ET"
    else:
        line = _sanitize_line(text)
    return f"TODAY:\n  {line}"


def _section_clocks(clocks: dict) -> str:
    clocks = clocks if isinstance(clocks, dict) else {}
    ssr = clocks.get("ssr")
    mes = clocks.get("mes")
    cat_n = clocks.get("catastrophe_n")

    ssr_have, ssr_need = _extract_progress(ssr)
    mes_have, mes_need = _extract_progress(mes)
    beats_null = (mes.get("arming_bar") or {}).get("beats_null") if isinstance(mes, dict) else None
    cat_have = int(cat_n) if isinstance(cat_n, (int, float)) else None

    lines = [
        "MY CLOCKS:",
        f"  {_progress_tick('SSR shadow', ssr_have, ssr_need)}",
        f"  {_progress_tick('MES mirror', mes_have, mes_need, extra=_beats_null_suffix(beats_null))}",
        f"  {_progress_tick('Catastrophe cap', cat_have, 20)}",
    ]
    return "\n".join(lines)


def _section_wants(wants: Optional[list]) -> str:
    items = wants if isinstance(wants, list) else []
    lines = ["I WANT:"]
    picked = items[:3]
    if not picked:
        lines.append(f"  {PLACEHOLDER}")
        return "\n".join(lines)
    for i, item in enumerate(picked, start=1):
        lines.append(f"  {i}. {_sanitize_line(_extract_want_text(item))}")
    return "\n".join(lines)


def _section_recent(commits: Optional[list]) -> str:
    items = commits if isinstance(commits, list) else []
    lines = ["RECENT:"]
    if not items:
        lines.append(f"  {PLACEHOLDER}")
        return "\n".join(lines)
    for subj in items[:4]:
        lines.append(f"  · {_sanitize_line(subj, max_len=70)}")
    return "\n".join(lines)


def _section_footer() -> str:
    return "talk to me → claw chat · #gamma on Discord"


def render_frame(state: dict, now_et: datetime) -> str:
    """Pure: (state dict, ET datetime) -> the full frame text. No I/O, no clock
    access, deterministic. Every section header renders unconditionally (so all 7
    section markers are always present); only the DATA inside a section degrades
    to a placeholder when the corresponding state is missing/malformed. Never
    raises -- every lookup below is defensive against a missing key, a wrong
    type, or an empty/partial fixture.
    """
    state = state if isinstance(state, dict) else {}
    state_word = derive_state_word(now_et)

    blocks = [
        _section_header(state_word, now_et),
        _section_right_now(state.get("right_now") or {}, state_word),
        _section_today(state.get("standup")),
        _section_clocks(state.get("clocks") or {}),
        _section_wants(state.get("wants")),
        _section_recent(state.get("recent_commits")),
        _section_footer(),
    ]
    return "\n\n".join(blocks)


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


def gather_state() -> dict:
    """All the impure I/O for one frame. Returns the plain dict render_frame()
    consumes. Every field is individually try/except-guarded upstream (in the
    small helpers above) so one bad file degrades only its own section, never the
    whole window. Shape:

        {
          "right_now": {"watcher_mtime_et": dt|None, "futures_tail_et": dt|None,
                         "aggressive_mtime_et": dt|None},
          "standup": dict|None,
          "clocks": {"ssr": dict|None, "mes": dict|None, "catastrophe_n": int|None},
          "wants": list|None,
          "recent_commits": list[str],
        }
    """
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
    }


# --------------------------------------------------------------------------------
# Presentation + loop -- the thin, impure shell. Never unit-tested directly.
# --------------------------------------------------------------------------------

def _print_frame(frame: str, state_word: str) -> None:
    """Draw one frame. Tries rich (colored panel) first; ANY failure there falls
    through to the plain-ANSI path in the SAME cycle -- this function must never
    raise, or the window dies.
    """
    if _HAS_RICH:
        try:
            color = {"TRADING": "green", "RESEARCHING": "yellow", "STANDING BY": "bright_black"}.get(
                state_word, "white"
            )
            console = Console()
            console.clear()
            console.print(Panel(frame, title="GAMMA", border_style=color, expand=True))
            return
        except Exception:  # noqa: BLE001 -- rich misbehaved; fall back below, don't crash
            pass
    output = "\x1b[2J\x1b[H" + frame + "\n"  # full clear + cursor home, then the frame
    try:
        sys.stdout.write(output)
    except UnicodeEncodeError:
        # stdout is stuck on a non-UTF8 codepage (main()'s reconfigure() didn't
        # take, or this is some redirected/legacy pipe) -- degrade to ASCII
        # rather than crash the one window on this rig that's supposed to
        # always be up. Confirmed reachable: an early smoke test of this exact
        # module via a plain `python -c` invocation (stdout never reconfigured)
        # hit this precise UnicodeEncodeError on the ▸ glyph.
        sys.stdout.write(output.encode("ascii", errors="replace").decode("ascii"))
    sys.stdout.flush()


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
            state = gather_state()
            state_word = derive_state_word(now_et)
            frame = render_frame(state, now_et)
            _print_frame(frame, state_word)
        except Exception as exc:  # noqa: BLE001 -- the window must survive indefinitely
            try:
                sys.stdout.write(f"\n[render hiccup, retrying] {type(exc).__name__}: {exc}\n")
                sys.stdout.flush()
            except Exception:  # noqa: BLE001
                pass
        time.sleep(REFRESH_SECS)


if __name__ == "__main__":
    main()
