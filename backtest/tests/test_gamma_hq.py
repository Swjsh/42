"""Tests for setup/scripts/gamma_hq.py -- GAMMA HQ, the always-on VISIBLE terminal
window where Gamma narrates its state in first person (J: "Gamma works but is
invisible" -- feedback_gamma_presence_not_prompting_2026_07_22).

render_frame(state, now_et) is a pure function; these tests exercise it directly
against hand-built fixtures. They also exercise gather_state() against both a
synthetic empty directory and the real repo state dir, but they NEVER call main()
-- the infinite render loop is never started under test (would hang pytest).
"""
import datetime as dt
import importlib.util
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPO_ROOT, "setup", "scripts", "gamma_hq.py")


def _load():
    spec = importlib.util.spec_from_file_location("gamma_hq", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hq = _load()

# The 7 layout sections from the spec, in order. Every fixture below (full,
# empty, partial, banned-content) must produce all 7 -- only the DATA inside a
# section is allowed to degrade to a placeholder.
SECTION_MARKERS = [
    "GAMMA HQ",       # 1. header banner
    "RIGHT NOW:",     # 2.
    "TODAY:",         # 3.
    "MY CLOCKS:",     # 4.
    "I WANT:",        # 5.
    "RECENT:",        # 6.
    "talk to me",     # 7. footer
]


def _full_state_fixture() -> dict:
    """A fully populated state dict, shaped like gather_state()'s real output
    (field shapes lifted from the actual state files on disk as of 2026-08-07)."""
    now = dt.datetime(2026, 8, 7, 12, 31, 0)
    return {
        "right_now": {
            "watcher_mtime_et": now,
            "futures_tail_et": now - dt.timedelta(minutes=3),
            "aggressive_mtime_et": now - dt.timedelta(minutes=10),
        },
        "standup": {"summary": "Flat both accounts, watching the 5350 level."},
        "clocks": {
            "ssr": {"n_round_trips": 0, "arming_bar": {"round_trips_needed": 20, "beats_null": None}},
            "mes": {"n_round_trips": 48, "arming_bar": {"round_trips_needed": 20, "beats_null": False}},
            "catastrophe_n": 13,
        },
        "wants": [
            "Ship the SSR shadow eval once armed",
            "Re-check bull tier at n>=20",
            "Prune stale candidates",
        ],
        "recent_commits": [
            "chore: auto-commit 13 strategy/candidates/ changes",
            "docs(close-package): ladder addendum SYNTHESIS",
            "docs(research): FRIDAY-2026-08-07-FULL synthesis",
            "feat(analysis): SCORE-LADDER-V2 demerit replay",
        ],
    }


# --------------------------------------------------------------------------------
# render_frame: full fixture contains every section marker
# --------------------------------------------------------------------------------

def test_render_frame_full_fixture_has_all_section_markers():
    frame = hq.render_frame(_full_state_fixture(), dt.datetime(2026, 8, 7, 12, 31, 0))
    assert isinstance(frame, str)
    for marker in SECTION_MARKERS:
        assert marker in frame, f"missing section marker: {marker!r}"


def test_render_frame_full_fixture_renders_expected_data():
    frame = hq.render_frame(_full_state_fixture(), dt.datetime(2026, 8, 7, 12, 31, 0))
    assert "[TRADING]" in frame
    assert "Watching SPY off the 5m engine; last tick 12:31 ET" in frame
    assert "Flat both accounts, watching the 5350 level." in frame
    assert "SSR shadow ▸ 0/20" in frame
    assert "MES mirror ▸ 48/20 (beats_null: no)" in frame
    assert "Catastrophe cap ▸ 13/20" in frame
    assert "1. Ship the SSR shadow eval once armed" in frame
    assert "· chore: auto-commit 13 strategy/candidates/ changes" in frame


# --------------------------------------------------------------------------------
# empty / partial state: never raises, still renders every marker + placeholders
# --------------------------------------------------------------------------------

def test_render_frame_empty_state_no_raise_and_placeholders():
    frame = hq.render_frame({}, dt.datetime(2026, 8, 9, 3, 0, 0))  # Sunday
    for marker in SECTION_MARKERS:
        assert marker in frame
    assert hq.PLACEHOLDER in frame


def test_render_frame_none_state_no_raise():
    # Defensive: render_frame's contract says `state: dict`, but a stray None
    # must not blow up the always-visible window either.
    frame = hq.render_frame(None, dt.datetime(2026, 8, 7, 10, 0, 0))
    for marker in SECTION_MARKERS:
        assert marker in frame


def test_render_frame_partial_state_missing_keys_no_raise():
    partial = {"wants": None, "recent_commits": None, "clocks": {"ssr": "not-a-dict"}}
    frame = hq.render_frame(partial, dt.datetime(2026, 8, 7, 10, 0, 0))
    for marker in SECTION_MARKERS:
        assert marker in frame


def test_render_frame_malformed_types_no_raise():
    # Wrong types everywhere a real fixture would have dicts/lists/datetimes.
    garbage = {
        "right_now": "not-a-dict",
        "standup": ["not", "a", "dict"],
        "clocks": "not-a-dict",
        "wants": {"not": "a-list"},
        "recent_commits": {"not": "a-list"},
    }
    frame = hq.render_frame(garbage, dt.datetime(2026, 8, 7, 10, 0, 0))
    for marker in SECTION_MARKERS:
        assert marker in frame


# --------------------------------------------------------------------------------
# banned content never leaks through, even when a source fixture contains it
# --------------------------------------------------------------------------------

def test_render_frame_never_leaks_traceback_from_wants():
    state = _full_state_fixture()
    state["wants"] = ['Traceback (most recent call last):\n  File "x.py", line 1\nValueError: boom']
    frame = hq.render_frame(state, dt.datetime(2026, 8, 7, 12, 31, 0))
    assert "Traceback (most recent call last)" not in frame
    assert 'File "' not in frame


def test_render_frame_never_leaks_traceback_from_standup():
    state = _full_state_fixture()
    state["standup"] = {"summary": 'Traceback (most recent call last):\n  File "y.py", line 9\nKeyError'}
    frame = hq.render_frame(state, dt.datetime(2026, 8, 7, 12, 31, 0))
    assert "Traceback (most recent call last)" not in frame


def test_render_frame_never_leaks_degraded_word():
    state = _full_state_fixture()
    state["standup"] = {"summary": "Engine DEGRADED, halted at 10:03"}
    state["recent_commits"] = ["fix: DEGRADED sensor path", *state["recent_commits"]]
    state["wants"] = ["Investigate DEGRADED watcher state", *state["wants"]]
    frame = hq.render_frame(state, dt.datetime(2026, 8, 7, 12, 31, 0))
    assert "DEGRADED" not in frame
    assert "degraded" not in frame.lower()


# --------------------------------------------------------------------------------
# state-word derivation
# --------------------------------------------------------------------------------

@pytest.mark.parametrize("when,expected", [
    (dt.datetime(2026, 8, 7, 9, 30, 0), "TRADING"),        # Friday 09:30 ET -- inclusive lower bound
    (dt.datetime(2026, 8, 7, 12, 0, 0), "TRADING"),        # Friday midday
    (dt.datetime(2026, 8, 7, 15, 54, 59), "TRADING"),      # Friday just before the close gate
    (dt.datetime(2026, 8, 7, 15, 55, 0), "RESEARCHING"),   # Friday at the 15:55 cutoff -- exclusive
    (dt.datetime(2026, 8, 7, 9, 29, 59), "RESEARCHING"),   # Friday just before the open gate
    (dt.datetime(2026, 8, 7, 7, 0, 0), "RESEARCHING"),     # Friday premarket
    (dt.datetime(2026, 8, 7, 20, 0, 0), "RESEARCHING"),    # Friday evening
    (dt.datetime(2026, 8, 8, 12, 0, 0), "STANDING BY"),    # Saturday
    (dt.datetime(2026, 8, 9, 12, 0, 0), "STANDING BY"),    # Sunday
    (dt.datetime(2026, 8, 9, 10, 0, 0), "STANDING BY"),    # Sunday, inside what would be RTH on a weekday
    (dt.datetime(2026, 8, 10, 9, 30, 0), "TRADING"),       # Monday 09:30 ET
])
def test_derive_state_word(when, expected):
    assert hq.derive_state_word(when) == expected


def test_derive_state_word_used_inside_render_frame_header():
    frame = hq.render_frame({}, dt.datetime(2026, 8, 8, 9, 0, 0))  # Saturday
    assert "[STANDING BY]" in frame


# --------------------------------------------------------------------------------
# gather_state: empty state dir fails open end-to-end (real I/O, synthetic paths)
# --------------------------------------------------------------------------------

def test_gather_state_empty_dir_fails_open_and_renders_placeholders(tmp_path, monkeypatch):
    empty = tmp_path / "nothing_here"
    monkeypatch.setattr(hq, "WATCHER_LIVE_STATE", empty / ".watcher-live-state.json")
    monkeypatch.setattr(hq, "FUTURES_MIRROR", empty / "futures" / "mirror-would-be.jsonl")
    monkeypatch.setattr(hq, "AGGRESSIVE_LOOP_STATE", empty / "aggressive" / "loop-state.json")
    monkeypatch.setattr(hq, "STANDUP_LATEST", empty / "gamma-standup-latest.json")
    monkeypatch.setattr(hq, "SSR_SHADOW_PROGRESS", empty / "futures" / "ssr-shadow-progress.json")
    monkeypatch.setattr(hq, "MES_SHADOW_PROGRESS", empty / "futures" / "shadow-progress.json")
    monkeypatch.setattr(hq, "CATASTROPHE_LEDGER", empty / "catastrophe-cap-shadow-ledger.jsonl")
    monkeypatch.setattr(hq, "GAMMA_WANTS", empty / "gamma-wants.json")

    state = hq.gather_state()
    assert isinstance(state, dict)
    assert state["right_now"]["watcher_mtime_et"] is None
    assert state["standup"] is None
    assert state["clocks"]["ssr"] is None
    assert state["wants"] is None

    frame = hq.render_frame(state, dt.datetime(2026, 8, 7, 12, 31, 0))
    for marker in SECTION_MARKERS:
        assert marker in frame
    assert hq.PLACEHOLDER in frame
    assert "Grinding research queue" not in frame  # no timestamp at all -> plain placeholder, not a guess


def test_gather_state_missing_wants_file_is_none_not_error(tmp_path, monkeypatch):
    monkeypatch.setattr(hq, "GAMMA_WANTS", tmp_path / "does-not-exist.json")
    state = hq.gather_state()
    assert state["wants"] is None


# --------------------------------------------------------------------------------
# gather_state / render_frame smoke against the REAL repo state dir
# --------------------------------------------------------------------------------

def test_gather_state_and_render_against_real_repo_never_raises():
    state = hq.gather_state()
    assert isinstance(state, dict)
    for key in ("right_now", "standup", "clocks", "wants", "recent_commits"):
        assert key in state

    frame = hq.render_frame(state, hq.et_now())
    assert isinstance(frame, str)
    for marker in SECTION_MARKERS:
        assert marker in frame
    # This repo always has commits; recent_commits should never be forced empty.
    assert isinstance(state["recent_commits"], list)


def test_module_never_starts_the_loop_on_import():
    # Sanity guard on the test harness itself: importing/loading the module must
    # not have started main()'s infinite loop (it would hang every test run).
    assert hasattr(hq, "main")
    assert hasattr(hq, "render_frame")
