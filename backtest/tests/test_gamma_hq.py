"""Tests for setup/scripts/gamma_hq.py -- GAMMA HQ, the always-on VISIBLE terminal
window where Gamma narrates its state in first person (J: "Gamma works but is
invisible" -- feedback_gamma_presence_not_prompting_2026_07_22), rendered as a
resizable, professional-report-style screen (J, 2026-08-08: "make it look
better -- resizable, clearer, more intuitive, bullets/emojis/line breaks, a
professional report, like a regular PowerShell terminal").

render_frame(state, now_et, width) is a pure function; these tests exercise it
directly against hand-built fixtures, at multiple widths. They also exercise
gather_state() against both a synthetic empty directory, a synthetic
journal/trades.csv fixture, and the real repo state dir, but they NEVER call
main() -- the infinite render loop is never started under test (would hang
pytest).
"""
import csv
import datetime as dt
import importlib.util
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPO_ROOT, "setup", "scripts", "gamma_hq.py")


def _load():
    spec = importlib.util.spec_from_file_location("gamma_hq", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hq = _load()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


# The 8 layout blocks from the spec, in order. Every fixture below (full, empty,
# partial, banned-content, malformed) must produce all 8 -- only the DATA inside
# a block is allowed to degrade to a placeholder.
SECTION_MARKERS = [
    "⚡ GAMMA",             # 1. title band
    "\U0001f3af GOAL",           # 2.
    "\U0001f4b0 TODAY'S TAPE",   # 3.
    "⏱ RIGHT NOW",          # 4.
    "\U0001f4ca MY CLOCKS",      # 5.
    "\U0001f64f I WANT",         # 6.
    "\U0001f9fe RECENT SHIPS",   # 7.
    "talk to me",           # 8. footer
]


def _full_state_fixture() -> dict:
    """A fully populated state dict, shaped like gather_state()'s real output
    (field shapes lifted from the actual state files on disk as of 2026-08-07,
    plus a synthetic "tape" segment pair for the TODAY'S TAPE section)."""
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
            "feat(analysis): add SSR shadow tracker",
            "fix(engine): correct catastrophe cap math",
            "chore: prune stale candidates",
            "docs(readme): update install steps",
        ],
        "tape": {"segments": [("safe", 2, 182.0), ("risky-1", 1, -46.0)]},
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
    assert "● TRADING" in frame
    assert "Watching SPY off the 5m engine; last tick 12:31 ET" in frame
    assert "Today's focus: Flat both accounts, watching the 5350 level." in frame
    assert "3 trades · net +$136" in frame
    assert "safe: 2 trades, +$182" in frame
    assert "risky-1: 1 trade, -$46" in frame
    assert hq._clock_line("SSR shadow", 0, 20) in frame
    assert hq._clock_line("MES mirror", 48, 20, extra=" · needs beats-null") in frame
    assert hq._clock_line("Cap re-check", 13, 20) in frame
    assert "1. Ship the SSR shadow eval once armed" in frame
    assert "· Add SSR shadow tracker" in frame


# --------------------------------------------------------------------------------
# empty / partial / None / malformed state: never raises, still renders every
# marker + placeholders
# --------------------------------------------------------------------------------

def test_render_frame_empty_state_no_raise_and_placeholders():
    frame = hq.render_frame({}, dt.datetime(2026, 8, 9, 3, 0, 0))  # Sunday
    for marker in SECTION_MARKERS:
        assert marker in frame
    assert hq.PLACEHOLDER in frame
    assert "Market closed — research mode." in frame


def test_render_frame_none_state_no_raise():
    # Defensive: render_frame's contract says `state: dict`, but a stray None
    # must not blow up the always-visible window either.
    frame = hq.render_frame(None, dt.datetime(2026, 8, 7, 10, 0, 0))
    for marker in SECTION_MARKERS:
        assert marker in frame


def test_render_frame_partial_state_missing_keys_no_raise():
    partial = {
        "wants": None,
        "recent_commits": None,
        "clocks": {"ssr": "not-a-dict"},
        "tape": {"segments": "garbage"},
    }
    frame = hq.render_frame(partial, dt.datetime(2026, 8, 7, 10, 0, 0))
    for marker in SECTION_MARKERS:
        assert marker in frame


def test_today_focus_text_takes_first_line_only_of_real_standup_shape():
    # Regression pin for a real bug caught in the 2026-08-08 smoke test against
    # actual repo state: gamma_standup.py's real gamma-standup-latest.json has
    # NO one-line "summary" field -- its "text" field is the FULL multi-
    # paragraph composed standup. Rendering the whole thing flooded "Today's
    # focus:" with a mid-word-truncated wall of text. Must degrade to just the
    # first line.
    standup = {
        "text": (
            "Morning J — Gamma here.\n\n"
            "**OVERNIGHT/YESTERDAY**\n"
            "- Exit-repair lane CLOSED honestly -- catastrophe-cap DECIDED at n=13"
        )
    }
    assert hq._today_focus_text(standup) == "Morning J — Gamma here."
    frame = hq.render_frame({"standup": standup}, dt.datetime(2026, 8, 7, 12, 31, 0))
    assert "Today's focus: Morning J — Gamma here." in frame
    assert "OVERNIGHT/YESTERDAY" not in frame
    assert "**" not in frame


def test_today_focus_text_banned_word_on_first_line_still_scrubbed():
    standup = {"text": "Engine DEGRADED at open.\n\nEverything after is irrelevant here."}
    assert "DEGRADED" not in hq._today_focus_text(standup)


# --------------------------------------------------------------------------------
# CHANGES 2026-08-08 follow-up -- HQ prefers gamma_standup.py's new "focus"
# field over the first-line-of-text fallback.
# --------------------------------------------------------------------------------

def test_today_focus_text_prefers_focus_field_over_text():
    standup = {
        "focus": "3 open research items; today I'm on the top one.",
        "text": "Morning J — Gamma here.\n\n**OVERNIGHT/YESTERDAY**\n- something else entirely",
    }
    assert hq._today_focus_text(standup) == "3 open research items; today I'm on the top one."


def test_today_focus_text_falls_back_to_first_line_when_focus_absent():
    # EOD-mode standups never populate "focus" (no TODAY section) -- must
    # still degrade cleanly to the first-line-of-text logic.
    standup = {"text": "EOD from Gamma.\n\n**P&L**\nSafe up $150."}
    assert hq._today_focus_text(standup) == "EOD from Gamma."


def test_today_focus_text_falls_back_to_first_line_when_focus_is_none():
    standup = {"focus": None, "text": "Morning J — Gamma here.\n\nrest of message"}
    assert hq._today_focus_text(standup) == "Morning J — Gamma here."


def test_today_focus_text_falls_back_to_first_line_when_focus_blank():
    standup = {"focus": "   ", "text": "Morning J — Gamma here.\n\nrest of message"}
    assert hq._today_focus_text(standup) == "Morning J — Gamma here."


def test_today_focus_text_focus_field_wrong_type_falls_back():
    standup = {"focus": 12345, "text": "Morning J — Gamma here.\n\nrest of message"}
    assert hq._today_focus_text(standup) == "Morning J — Gamma here."


def test_today_focus_text_focus_field_is_sanitized():
    standup = {"focus": "Engine DEGRADED right now"}
    result = hq._today_focus_text(standup)
    assert "DEGRADED" not in result


def test_render_frame_goal_section_uses_focus_field():
    state = _full_state_fixture()
    state["standup"] = {
        "focus": "3 open research items; today I'm on the top one.",
        "text": "Morning J — Gamma here.\n\nlots more detail that must NOT show up",
    }
    frame = hq.render_frame(state, dt.datetime(2026, 8, 7, 12, 31, 0))
    assert "Today's focus: 3 open research items; today I'm on the top one." in frame
    assert "lots more detail" not in frame


def test_render_frame_malformed_types_no_raise():
    # Wrong types everywhere a real fixture would have dicts/lists/datetimes.
    garbage = {
        "right_now": "not-a-dict",
        "standup": ["not", "a", "dict"],
        "clocks": "not-a-dict",
        "wants": {"not": "a-list"},
        "recent_commits": {"not": "a-list"},
        "tape": 12345,
    }
    frame = hq.render_frame(garbage, dt.datetime(2026, 8, 7, 10, 0, 0))
    for marker in SECTION_MARKERS:
        assert marker in frame


def test_render_frame_malformed_width_falls_back_no_raise():
    for bad_width in (None, "not-a-number", -10, object()):
        frame = hq.render_frame(_full_state_fixture(), dt.datetime(2026, 8, 7, 12, 31, 0), width=bad_width)
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
    assert "● STANDING BY" in frame


# --------------------------------------------------------------------------------
# CHANGES #1 -- resizable/responsive: width param drives every rule/wrap/
# truncation decision, and no rendered line ever exceeds width (+2 slack,
# ignoring ANSI escapes -- render_frame itself never emits any, but the check is
# written defensively in case a future change folds styling into it).
# --------------------------------------------------------------------------------

@pytest.mark.parametrize("width", [60, 150])
def test_render_frame_width_adaptation_no_line_exceeds_width(width):
    frame = hq.render_frame(_full_state_fixture(), dt.datetime(2026, 8, 7, 12, 31, 0), width=width)
    for marker in SECTION_MARKERS:
        assert marker in frame
    for line in frame.split("\n"):
        visible = _strip_ansi(line)
        assert len(visible) <= width + 2, f"line exceeds width+2 at width={width}: {visible!r} ({len(visible)} chars)"


def test_render_frame_reflows_between_widths():
    # A deliberately long want item forces wrapping at width=60 but not at
    # width=150 -- confirms resizing actually changes the layout, not just the
    # rule length.
    state = _full_state_fixture()
    state["wants"] = ["This is a deliberately long I WANT item written to force line "
                       "wrapping at a narrow terminal width but not at a wide one"]
    now = dt.datetime(2026, 8, 7, 12, 31, 0)
    narrow = hq.render_frame(state, now, width=60)
    wide = hq.render_frame(state, now, width=150)
    assert narrow.count("\n") > wide.count("\n")


def test_render_frame_default_width_is_100():
    now = dt.datetime(2026, 8, 7, 12, 31, 0)
    default = hq.render_frame(_full_state_fixture(), now)
    explicit = hq.render_frame(_full_state_fixture(), now, width=100)
    assert default == explicit
    assert hq.DEFAULT_WIDTH == 100


@pytest.mark.parametrize("raw,expected", [
    (100, 100),
    (60, 60),
    (160, 160),
    (10, 60),      # below MIN_WIDTH -- clamps up
    (999, 160),    # above MAX_WIDTH -- clamps down
    (None, 100),
    ("garbage", 100),
    (150.7, 150),
])
def test_clamp_width(raw, expected):
    assert hq._clamp_width(raw) == expected


# --------------------------------------------------------------------------------
# CHANGES #2 -- progress-bar math (MY CLOCKS)
# --------------------------------------------------------------------------------

def test_progress_bar_zero_of_target_is_empty():
    assert hq._progress_bar(0, 20) == "▱" * 10


def test_progress_bar_partial_rounds_correctly():
    # 13/20 = 0.65 -> 6.5 cells -> round() = 6 (verified empirically, not
    # assumed -- float(13/20*10) lands at/under 6.5 in this runtime).
    assert hq._progress_bar(13, 20) == "▰" * 6 + "▱" * 4


def test_progress_bar_overfull_shows_full_bar():
    assert hq._progress_bar(48, 20) == "▰" * 10


def test_progress_bar_none_have_treated_as_zero():
    assert hq._progress_bar(None, 20) == "▱" * 10


def test_progress_bar_exact_target_is_full():
    assert hq._progress_bar(20, 20) == "▰" * 10


def test_clock_line_overfull_shows_raw_numbers_not_clamped():
    line = hq._clock_line("MES mirror", 48, 20)
    assert "48/20" in line
    assert hq._progress_bar(48, 20) in line


def test_clock_line_missing_have_shows_placeholder_not_zero():
    line = hq._clock_line("SSR shadow", None, 20)
    assert f"{hq.PLACEHOLDER}/20" in line


def test_clock_line_label_column_alignment():
    # All 3 real labels should left-align to the same column so the bars start
    # in the same place -- confirms the ljust width matches the longest label.
    ssr = hq._clock_line("SSR shadow", 5, 20)
    mes = hq._clock_line("MES mirror", 5, 20)
    cap = hq._clock_line("Cap re-check", 5, 20)
    bar_start = hq._CLOCK_LABEL_WIDTH  # ljust column width, one past "Cap re-check"'s 12 chars
    assert ssr[bar_start] == "▰" or ssr[bar_start] == "▱"
    assert mes[bar_start] == "▰" or mes[bar_start] == "▱"
    assert cap[bar_start] == "▰" or cap[bar_start] == "▱"


# --------------------------------------------------------------------------------
# CHANGES #2 -- RECENT SHIPS: conventional-commit prefix stripping
# --------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("feat(analysis): add SSR shadow tracker", "Add SSR shadow tracker"),
    ("fix: correct catastrophe cap math", "Correct catastrophe cap math"),
    ("chore: prune stale candidates", "Prune stale candidates"),
    ("Merge branch 'main' into feature", "Merge branch 'main' into feature"),
])
def test_humanize_commit_subject_strips_conventional_prefix(raw, expected):
    assert hq._humanize_commit_subject(raw, 200) == expected


def test_humanize_commit_subject_truncates_to_max_len():
    long_subject = "feat: " + ("x" * 100)
    result = hq._humanize_commit_subject(long_subject, 20)
    assert len(result) <= 20


def test_humanize_commit_subject_redacts_banned_content():
    result = hq._humanize_commit_subject("fix: DEGRADED sensor path", 200)
    assert "DEGRADED" not in result
    assert "degraded" not in result.lower()


# --------------------------------------------------------------------------------
# _wrap_block -- hanging-indent wrap primitive
# --------------------------------------------------------------------------------

def test_wrap_block_short_text_single_line():
    assert hq._wrap_block("short", 100) == ["  short"]


def test_wrap_block_hanging_indent_numbered():
    text = ("word " * 30).strip()
    lines = hq._wrap_block(text, 40, indent="  ", first_prefix="1. ")
    assert len(lines) > 1
    assert lines[0].startswith("  1. ")
    for cont in lines[1:]:
        assert cont.startswith("     ")  # 2 indent + len("1. ") == 5
        assert not cont.lstrip().startswith("1.")


def test_wrap_block_never_exceeds_width_even_for_one_giant_word():
    text = "x" * 500
    for width in (60, 100, 150):
        for ln in hq._wrap_block(text, width, indent="  "):
            assert len(ln) <= width


# --------------------------------------------------------------------------------
# _truncate
# --------------------------------------------------------------------------------

def test_truncate_short_text_unchanged():
    assert hq._truncate("short text", 20) == "short text"


def test_truncate_long_text_adds_ellipsis_and_respects_max_len():
    text = "this is a long sentence that needs cutting for sure"
    result = hq._truncate(text, 20)
    assert len(result) <= 20
    assert result.endswith("…")


def test_truncate_never_cuts_mid_word():
    # Regression pin for the real 2026-08-08 I WANT bug (caught in the smoke
    # test against actual gamma-wants.json content): the OLD blind
    # text[:max_len] slice cut this exact want item to "...futures edge
    # that'" -- a mid-word cut leaving a dangling apostrophe. Word-boundary
    # truncation must never do that: every "word" left in the result must
    # appear intact in the source text.
    text = (
        "Rotate the Tastytrade PROD tokens (owed since 06-22) — it unlocks "
        "mes-mnq-div, a validated +$71/trade futures edge that's been parked for 6 weeks"
    )
    result = hq._truncate(text, 120)
    assert len(result) <= 120
    assert result.endswith("…")
    body = result[: -len("…")]
    assert not body.endswith("'")
    for word in body.split():
        assert word in text, f"word {word!r} does not appear intact in the source text -- mid-word cut"


def test_truncate_falls_back_to_hard_slice_for_one_unbroken_token():
    # No whitespace anywhere within budget -- nothing to back off to, so this
    # degrades to a hard slice + ellipsis rather than returning empty/garbage.
    text = "x" * 500
    result = hq._truncate(text, 20)
    assert len(result) <= 20
    assert result.endswith("…")


def test_truncate_budget_too_small_for_ellipsis_hard_slices():
    assert hq._truncate("hello world", 0) == ""
    assert hq._truncate("hello world", 1) == "h"


def test_truncate_budget_of_one_char_plus_ellipsis():
    assert hq._truncate("hello", 2) == "h…"


def test_render_frame_i_want_long_item_no_mid_word_truncation():
    # End-to-end regression pin, real content: this is the ACTUAL want item
    # from automation/state/gamma-wants.json that produced the visible
    # "...futures edge that'" bug in the 2026-08-08 real-repo smoke frame at
    # both width=80 and width=130.
    state = _full_state_fixture()
    state["wants"] = [
        "Rotate the Tastytrade PROD tokens (owed since 06-22) — it unlocks "
        "mes-mnq-div, a validated +$71/trade futures edge that's been parked for 6 weeks"
    ]
    for width in (80, 100, 130):
        frame = hq.render_frame(state, dt.datetime(2026, 8, 7, 12, 31, 0), width=width)
        assert "that'" not in frame  # the exact dangling-apostrophe artifact
        for line in frame.split("\n"):
            assert not line.rstrip().endswith("'")


# --------------------------------------------------------------------------------
# CHANGES #3 -- ASCII-safe fallback: every glyph has a substitute, output is
# always pure ASCII, "emoji -> bracketed tags" per spec's own [GOAL] example.
# --------------------------------------------------------------------------------

def test_asciify_replaces_all_known_glyphs_and_is_pure_ascii():
    sample = (
        "⚡ GAMMA ● TRADING\n"
        "\U0001f3af GOAL\n"
        "\U0001f4b0 TODAY'S TAPE\n"
        "⏱ RIGHT NOW\n"
        "\U0001f4ca MY CLOCKS ▰▰▱▱ 2/4\n"
        "\U0001f64f I WANT\n"
        "\U0001f9fe RECENT SHIPS\n"
        "\U0001f4ac talk to me → claw chat · #gamma\n"
        "a truncated want item…"
    )
    out = hq._asciify(sample)
    for glyph in "⚡●\U0001f3af\U0001f4b0⏱\U0001f4ca\U0001f64f\U0001f9fe\U0001f4ac▰▱·→…":
        assert glyph not in out, f"glyph {glyph!r} survived asciify"
    out.encode("ascii")  # raises if anything non-ASCII slipped through
    assert "[GOAL]" in out
    assert "[GAMMA]" in out
    assert "[TAPE]" in out
    assert "[CLOCKS]" in out
    assert "[WANT]" in out
    assert "[SHIPS]" in out
    assert "[CHAT]" in out
    assert "a truncated want item..." in out


def test_asciify_is_noop_on_plain_ascii_text():
    assert hq._asciify("plain ascii text 123") == "plain ascii text 123"


def test_asciify_preserves_ansi_escape_codes():
    styled = f"{hq._ANSI_STYLE_CODES['bold']}\U0001f3af GOAL{hq._ANSI_RESET}"
    out = hq._asciify(styled)
    assert hq._ANSI_STYLE_CODES["bold"] in out
    assert hq._ANSI_RESET in out
    assert "[GOAL]" in out


def test_render_frame_ascii_safe_via_asciify_full_fixture():
    frame = hq.render_frame(_full_state_fixture(), dt.datetime(2026, 8, 7, 12, 31, 0))
    ascii_frame = hq._asciify(frame)
    ascii_frame.encode("ascii")  # must never raise
    assert "[GOAL]" in ascii_frame
    assert "[TAPE]" in ascii_frame
    assert "[CLOCKS]" in ascii_frame
    assert "[NOW]" in ascii_frame
    assert "[WANT]" in ascii_frame
    assert "[SHIPS]" in ascii_frame


# --------------------------------------------------------------------------------
# CHANGES #3 -- color classification (presentation layer, but _segment_line
# itself is a pure function shared by both rich and raw-ANSI paths)
# --------------------------------------------------------------------------------

def test_segment_line_classifies_rule_as_dim():
    segs = hq._segment_line("=" * 80)
    assert segs == [("=" * 80, "dim")]


def test_segment_line_classifies_chip_and_bolds_title_prefix():
    line = "⚡ GAMMA" + " " * 10 + "● TRADING"
    segs = hq._segment_line(line)
    styles = [s for _, s in segs]
    assert "green" in styles  # the chip itself
    assert "bold" in styles   # the "⚡ GAMMA" prefix sharing the line


def test_segment_line_classifies_section_header_as_bold():
    segs = hq._segment_line("\U0001f3af GOAL")
    assert segs == [("\U0001f3af GOAL", "bold")]


def test_segment_line_colors_money_tokens():
    segs = hq._segment_line("safe: 2 trades, +$182")
    styles = dict((t, s) for t, s in segs)
    assert styles.get("+$182") == "green"


def test_segment_line_colors_negative_money_red():
    segs = hq._segment_line("risky-1: 1 trade, -$46")
    styles = dict((t, s) for t, s in segs)
    assert styles.get("-$46") == "red"


def test_ansi_style_line_wraps_recognized_segments():
    out = hq._ansi_style_line("=" * 20)
    assert out.startswith(hq._ANSI_STYLE_CODES["dim"])
    assert out.endswith(hq._ANSI_RESET)


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
    monkeypatch.setattr(hq, "TRADES_CSV", empty / "trades.csv")

    state = hq.gather_state(now_et=dt.datetime(2026, 8, 7, 12, 0, 0))
    assert isinstance(state, dict)
    assert state["right_now"]["watcher_mtime_et"] is None
    assert state["standup"] is None
    assert state["clocks"]["ssr"] is None
    assert state["wants"] is None
    assert state["tape"]["segments"] == []

    frame = hq.render_frame(state, dt.datetime(2026, 8, 7, 12, 31, 0))
    for marker in SECTION_MARKERS:
        assert marker in frame
    assert hq.PLACEHOLDER in frame
    assert "Grinding research queue" not in frame  # no timestamp at all -> plain placeholder, not a guess
    assert "Market closed — research mode." in frame


def test_gather_state_missing_wants_file_is_none_not_error(tmp_path, monkeypatch):
    monkeypatch.setattr(hq, "GAMMA_WANTS", tmp_path / "does-not-exist.json")
    state = hq.gather_state()
    assert state["wants"] is None


def test_gather_state_defaults_now_et_when_omitted():
    # No now_et passed -> must use the real clock internally rather than raise.
    state = hq.gather_state()
    assert isinstance(state, dict)
    assert "tape" in state


# --------------------------------------------------------------------------------
# CHANGES #2 -- TODAY'S TAPE: renders from a fixture CSV, and an absent file
# renders the placeholder.
# --------------------------------------------------------------------------------

def _write_trades_csv(path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["date", "account_id", "dollar_pnl"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_gather_state_tape_from_fixture_csv_aggregates_by_account(tmp_path, monkeypatch):
    csv_path = tmp_path / "trades.csv"
    _write_trades_csv(csv_path, [
        {"date": "2026-08-07", "account_id": "safe", "dollar_pnl": "120"},
        {"date": "2026-08-07", "account_id": "safe", "dollar_pnl": "-40"},
        {"date": "2026-08-07", "account_id": "risky-1", "dollar_pnl": "300"},
        {"date": "2026-08-06", "account_id": "safe", "dollar_pnl": "9999"},  # different day -- excluded
        {"date": "2026-08-07", "account_id": "", "dollar_pnl": "50"},        # blank acct -- excluded
        {"date": "2026-08-07", "account_id": "risky-1", "dollar_pnl": "n/a"},  # bad pnl -- excluded
    ])
    monkeypatch.setattr(hq, "TRADES_CSV", csv_path)
    now = dt.datetime(2026, 8, 7, 12, 0, 0)
    state = hq.gather_state(now_et=now)
    assert state["tape"]["segments"] == [("risky-1", 1, 300.0), ("safe", 2, 80.0)]

    frame = hq.render_frame(state, now)
    assert "3 trades · net +$380" in frame
    assert "risky-1: 1 trade, +$300" in frame
    assert "safe: 2 trades, +$80" in frame


def test_gather_state_tape_absent_csv_renders_placeholder(tmp_path, monkeypatch):
    monkeypatch.setattr(hq, "TRADES_CSV", tmp_path / "does-not-exist.csv")
    now = dt.datetime(2026, 8, 8, 12, 0, 0)  # Saturday
    state = hq.gather_state(now_et=now)
    assert state["tape"]["segments"] == []
    frame = hq.render_frame(state, now)
    assert "Market closed — research mode." in frame


def test_gather_state_tape_no_rows_for_today_renders_placeholder(tmp_path, monkeypatch):
    csv_path = tmp_path / "trades.csv"
    _write_trades_csv(csv_path, [
        {"date": "2026-08-06", "account_id": "safe", "dollar_pnl": "500"},
    ])
    monkeypatch.setattr(hq, "TRADES_CSV", csv_path)
    now = dt.datetime(2026, 8, 7, 12, 0, 0)
    state = hq.gather_state(now_et=now)
    assert state["tape"]["segments"] == []
    frame = hq.render_frame(state, now)
    assert "Market closed — research mode." in frame


def test_pnl_segments_aggregates_and_sorts_by_account():
    rows = [
        {"account_id": "safe", "dollar_pnl": "100"},
        {"account_id": "safe", "dollar_pnl": "50"},
        {"account_id": "risky-1", "dollar_pnl": "-20"},
        {"account_id": "", "dollar_pnl": "999"},              # blank account -- skipped
        {"account_id": "risky-1", "dollar_pnl": "not-a-number"},  # bad pnl -- skipped
        "not-a-dict",                                          # garbage row -- skipped
    ]
    assert hq._pnl_segments(rows) == [("risky-1", 1, -20.0), ("safe", 2, 150.0)]


def test_trades_rows_for_day_filters_by_date_and_missing_file(tmp_path):
    assert hq._trades_rows_for_day(tmp_path / "missing.csv", "2026-08-07") == []


def test_fmt_signed_money():
    assert hq._fmt_signed_money(182.0) == "+$182"
    assert hq._fmt_signed_money(-46.0) == "-$46"
    assert hq._fmt_signed_money(0.0) == "flat $0"


# --------------------------------------------------------------------------------
# gather_state / render_frame smoke against the REAL repo state dir
# --------------------------------------------------------------------------------

def test_gather_state_and_render_against_real_repo_never_raises():
    state = hq.gather_state()
    assert isinstance(state, dict)
    for key in ("right_now", "standup", "clocks", "wants", "recent_commits", "tape"):
        assert key in state
    assert isinstance(state["tape"], dict)
    assert "segments" in state["tape"]

    frame = hq.render_frame(state, hq.et_now())
    assert isinstance(frame, str)
    for marker in SECTION_MARKERS:
        assert marker in frame
    # This repo always has commits; recent_commits should never be forced empty.
    assert isinstance(state["recent_commits"], list)


@pytest.mark.parametrize("width", [80, 130])
def test_gather_state_and_render_against_real_repo_at_widths_never_raises(width):
    state = hq.gather_state()
    frame = hq.render_frame(state, hq.et_now(), width=width)
    for marker in SECTION_MARKERS:
        assert marker in frame
    for line in frame.split("\n"):
        assert len(_strip_ansi(line)) <= width + 2


def test_module_never_starts_the_loop_on_import():
    # Sanity guard on the test harness itself: importing/loading the module must
    # not have started main()'s infinite loop (it would hang every test run).
    assert hasattr(hq, "main")
    assert hasattr(hq, "render_frame")
