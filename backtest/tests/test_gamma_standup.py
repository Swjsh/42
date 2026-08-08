"""Guard: setup/scripts/gamma_standup.py -- Gamma's self-initiated Discord standup.

Locks in: banned substrings (DEGRADED / MASKED EXIT / Traceback / exit=[ / jsonl) never
leak into a composed message even when a git commit subject carries one; no file-path
token longer than MAX_PATH_TOKEN_LEN survives; the 1200-char hard cap is enforced; wants
are surfaced top-3 by priority; Monday morning gets an extra WEEKEND RECAP section;
--dry-run performs zero disk writes; a real run appends exactly one outbox row in the
bridge's expected {content, source, queued_at} schema and writes gamma-standup-latest.json.

Every state-file read goes through a module-level Path constant (SHADOW_PROGRESS_PATH,
QUEUE_MD_PATH, TRADES_CSV_PATH, WANTS_PATH, ...) so tests monkeypatch those onto a tmp_path
fixture rather than touching the real repo state. git log is read through the single seam
_git_log_subjects, which every fixture-driven test monkeypatches directly -- no test here
ever depends on this repo's actual commit history (which changes every session).
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    p = str(REPO / _p) if _p else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

import gamma_standup as gs  # noqa: E402


# ============================================================================
# Test fixtures / helpers
# ============================================================================

def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _next_weekday(start: date, weekday: int) -> date:
    d = start
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


# Computed, not hand-recalled from a calendar -- guaranteed correct regardless of what
# weekday any particular hardcoded date actually falls on.
MONDAY = _next_weekday(date(2026, 8, 1), 0)
TUESDAY = MONDAY + timedelta(days=1)
SATURDAY = MONDAY - timedelta(days=2)


def _dt(d: date, hour: int, minute: int) -> datetime:
    return datetime.combine(d, datetime.min.time()).replace(hour=hour, minute=minute)


@pytest.fixture
def state_paths(tmp_path, monkeypatch):
    paths = {
        "shadow": tmp_path / "futures" / "shadow-progress.json",
        "ssr": tmp_path / "futures" / "ssr-shadow-progress.json",
        "cap_ledger": tmp_path / "catastrophe-cap-shadow-ledger.jsonl",
        "queue_md": tmp_path / "queue.md",
        "trades_csv": tmp_path / "trades.csv",
        "wants": tmp_path / "gamma-wants.json",
        "discord_cfg": tmp_path / ".discord-config.json",
        "outbox": tmp_path / "discord-outbox.jsonl",
        "latest": tmp_path / "gamma-standup-latest.json",
    }
    monkeypatch.setattr(gs, "SHADOW_PROGRESS_PATH", paths["shadow"])
    monkeypatch.setattr(gs, "SSR_SHADOW_PROGRESS_PATH", paths["ssr"])
    monkeypatch.setattr(gs, "CATASTROPHE_CAP_LEDGER_PATH", paths["cap_ledger"])
    monkeypatch.setattr(gs, "QUEUE_MD_PATH", paths["queue_md"])
    monkeypatch.setattr(gs, "TRADES_CSV_PATH", paths["trades_csv"])
    monkeypatch.setattr(gs, "WANTS_PATH", paths["wants"])
    monkeypatch.setattr(gs, "DISCORD_CFG_PATH", paths["discord_cfg"])
    monkeypatch.setattr(gs, "OUTBOX_PATH", paths["outbox"])
    monkeypatch.setattr(gs, "LATEST_PATH", paths["latest"])
    return paths


def _no_git(monkeypatch):
    """Most tests don't care about git content -- stub it to empty so nothing depends
    on this repo's real, ever-changing commit history."""
    monkeypatch.setattr(gs, "_git_log_subjects", lambda since, until=None: [])


# ============================================================================
# _humanize_commit_subject / _sanitize_bullet / _strip_long_paths / _redact_banned
# ============================================================================

def test_humanize_commit_subject_strips_prefix_and_sentence_cases():
    out = gs._humanize_commit_subject("619f41aa fix: mcp-daily-audit budget mis-sized at birth")
    assert out == "Mcp-daily-audit budget mis-sized at birth"


def test_humanize_commit_subject_strips_type_and_scope():
    out = gs._humanize_commit_subject("04bed7c8 feat(exits): exit-repair lane closed honestly")
    assert out == "Exit-repair lane closed honestly"


def test_humanize_commit_subject_rejects_non_tracked_type():
    assert gs._humanize_commit_subject("2d39414b chore: auto-commit 13 files") is None


def test_humanize_commit_subject_rejects_unstructured_line():
    assert gs._humanize_commit_subject("abc1234 Merge branch 'main' into feature") is None


def test_humanize_commit_subject_truncates_long_description():
    long_desc = "word " * 80
    out = gs._humanize_commit_subject(f"abc1234 fix: {long_desc}")
    assert out is not None
    assert len(out) <= gs.COMMIT_BULLET_MAX_CHARS + 3
    assert out.endswith("...")


@pytest.mark.parametrize("bad", gs.BANNED_SUBSTRINGS)
def test_humanize_commit_subject_drops_banned_substring(bad):
    assert gs._humanize_commit_subject(f"abc1234 fix: something with {bad} inside it") is None


def test_sanitize_bullet_passes_clean_text():
    assert gs._sanitize_bullet("a perfectly normal sentence") == "a perfectly normal sentence"


@pytest.mark.parametrize("bad", gs.BANNED_SUBSTRINGS)
def test_sanitize_bullet_drops_banned(bad):
    assert gs._sanitize_bullet(f"contains {bad} somewhere") is None


def test_redact_banned_replaces_all_occurrences():
    text = "alert: DEGRADED and another DEGRADED plus a Traceback here"
    out = gs._redact_banned(text)
    assert "DEGRADED" not in out
    assert "Traceback" not in out


def test_strip_long_paths_shortens_to_basename():
    text = "See markdown/research/SSR-PIVOT-LIQUIDITY-STRATEGY.md section 6 for detail."
    out = gs._strip_long_paths(text)
    assert "markdown/research/" not in out
    assert "SSR-PIVOT-LIQUIDITY-STRATEGY.md" in out


def test_strip_long_paths_leaves_short_paths_alone():
    text = "check a/b.py for detail"
    assert gs._strip_long_paths(text) == text


def test_strip_long_paths_falls_back_to_placeholder_when_basename_too_long():
    token = "some/very/deeply/nested/" + ("x" * 50) + ".py"
    out = gs._strip_long_paths(f"path: {token} end")
    assert "[path]" in out
    assert token not in out


def test_strip_long_paths_no_token_exceeds_cap(monkeypatch):
    text = "note automation/state/futures/shadow-progress.json and journal/trades.csv both."
    out = gs._strip_long_paths(text)
    for tok in out.split():
        assert len(tok) <= gs.MAX_PATH_TOKEN_LEN + 2  # +2 allows trailing punctuation


# ============================================================================
# _top_wants / _wants_bullets / _new_want_ids
# ============================================================================

def _wants_doc(items):
    return {"_doc": "test", "wants": items}


def test_top_wants_sorted_by_priority_max_three():
    doc = _wants_doc([
        {"priority": 3, "id": "c", "text": "third"},
        {"priority": 1, "id": "a", "text": "first"},
        {"priority": 2, "id": "b", "text": "second"},
        {"priority": 4, "id": "d", "text": "fourth"},
    ])
    top = gs._top_wants(doc, n=3)
    assert [w["id"] for w in top] == ["a", "b", "c"]


def test_top_wants_missing_doc_returns_empty():
    assert gs._top_wants(None) == []


def test_top_wants_malformed_wants_key_returns_empty():
    assert gs._top_wants({"_doc": "x", "wants": "not-a-list"}) == []


def test_top_wants_skips_entries_missing_required_fields():
    doc = _wants_doc([
        {"priority": 1, "id": "ok", "text": "fine"},
        {"priority": 2, "text": "missing id"},
        {"priority": 3, "id": "no-text"},
    ])
    top = gs._top_wants(doc, n=5)
    assert [w["id"] for w in top] == ["ok"]


def test_wants_bullets_plain():
    top = [{"id": "a", "text": "want a"}, {"id": "b", "text": "want b"}]
    assert gs._wants_bullets(top) == ["want a", "want b"]


def test_new_want_ids_none_previous_means_no_new_flags():
    assert gs._new_want_ids([{"id": "a", "text": "x"}], None) == set()


def test_new_want_ids_flags_ids_not_in_previous():
    top = [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}]
    assert gs._new_want_ids(top, ["a"]) == {"b"}


def test_wants_bullets_delta_annotates_new():
    top = [{"id": "a", "text": "want a"}, {"id": "b", "text": "want b"}]
    assert gs._wants_bullets(top, new_ids={"b"}) == ["want a", "(new) want b"]


# ============================================================================
# _backlog_bullet / _queue_unchecked_count
# ============================================================================

def test_queue_unchecked_count_matches_checkbox_lines(tmp_path):
    p = tmp_path / "queue.md"
    _write_text(p, "- [ ] one\n- [x] done\n- [ ] two\n- [x] done2\n- [ ] three\n")
    assert gs._queue_unchecked_count(p) == 3


def test_queue_unchecked_count_ignores_mid_line_occurrences(tmp_path):
    p = tmp_path / "queue.md"
    _write_text(p, "some prose mentioning - [ ] not at line start\n- [ ] real one\n")
    assert gs._queue_unchecked_count(p) == 1


def test_queue_unchecked_count_missing_file_is_none(tmp_path):
    assert gs._queue_unchecked_count(tmp_path / "nope.md") is None


def test_backlog_bullet_none_when_count_none():
    assert gs._backlog_bullet(None, tense="today") is None


def test_backlog_bullet_zero_phrasing():
    out = gs._backlog_bullet(0, tense="today")
    assert "clear" in out.lower()


def test_backlog_bullet_singular_vs_plural():
    assert "1 open research item;" in gs._backlog_bullet(1, tense="today")
    assert "2 open research items;" in gs._backlog_bullet(2, tense="today")


def test_backlog_bullet_matches_spec_example_format():
    assert gs._backlog_bullet(5, tense="today") == "5 open research items; today I'm on the top one."


def test_backlog_bullet_tomorrow_tense():
    assert gs._backlog_bullet(3, tense="tomorrow") == "3 open research items; tomorrow I'm on the top one."


# ============================================================================
# "focus" field (2026-08-08 follow-up, gamma_hq.py flag #4):
# _strip_markdown / _truncate_at_word_boundary / _derive_focus
# ============================================================================

def test_strip_markdown_drops_list_prefix():
    assert gs._strip_markdown("- some bullet text") == "some bullet text"
    assert gs._strip_markdown("* some bullet text") == "some bullet text"


def test_strip_markdown_unwraps_bold():
    assert gs._strip_markdown("**bold** and __also bold__") == "bold and also bold"


def test_strip_markdown_unwraps_code():
    assert gs._strip_markdown("run `pytest -x` now") == "run pytest -x now"


def test_strip_markdown_collapses_whitespace():
    assert gs._strip_markdown("  a   b\nc  ") == "a b c"


def test_strip_markdown_plain_text_unchanged():
    assert gs._strip_markdown("nothing fancy here") == "nothing fancy here"


def test_truncate_at_word_boundary_short_text_unchanged():
    assert gs._truncate_at_word_boundary("short text", 20) == "short text"


def test_truncate_at_word_boundary_never_cuts_mid_word():
    text = "word " * 40
    result = gs._truncate_at_word_boundary(text.strip(), 30)
    assert len(result) <= 30
    assert result.endswith("...")
    for w in result[: -len("...")].split():
        assert w in text


def test_truncate_at_word_boundary_one_unbroken_token_hard_slices():
    result = gs._truncate_at_word_boundary("x" * 200, 20)
    assert len(result) <= 20
    assert result.endswith("...")


def test_derive_focus_uses_today_bullet_directly():
    bullet = "5 open research items; today I'm on the top one."
    assert gs._derive_focus(bullet) == bullet


def test_derive_focus_fallback_when_today_bullet_none():
    # Mirrors compose_morning_text's own TODAY-section fallback phrase
    # verbatim -- the focus field must never diverge from what the composed
    # message itself shows.
    assert gs._derive_focus(None) == "Nothing queued -- reading the tape as it comes."


def test_derive_focus_strips_markdown():
    assert gs._derive_focus("- **today**: ship the thing") == "today: ship the thing"


def test_derive_focus_caps_at_focus_max_chars():
    long_bullet = ("word " * 40).strip()
    result = gs._derive_focus(long_bullet)
    assert len(result) <= gs.FOCUS_MAX_CHARS
    assert result.endswith("...")


# ============================================================================
# _cap_clock_segment / _shadow_segment / _compose_clocks_line
# ============================================================================

def test_cap_clock_segment_counts_lines_under_cadence(tmp_path):
    p = tmp_path / "ledger.jsonl"
    _write_text(p, '{"a":1}\n{"a":2}\n{"a":3}\n')
    assert gs._cap_clock_segment(p) == "Cap shadow 3/20"


def test_cap_clock_segment_wraps_modulo_at_cadence(tmp_path):
    p = tmp_path / "ledger.jsonl"
    _write_text(p, "\n".join('{"a":%d}' % i for i in range(23)) + "\n")
    assert gs._cap_clock_segment(p) == "Cap shadow 3/20"


def test_cap_clock_segment_missing_file_is_none(tmp_path):
    assert gs._cap_clock_segment(tmp_path / "nope.jsonl") is None


def test_shadow_segment_missing_data_is_none():
    assert gs._shadow_segment("SSR shadow", None) is None


def test_shadow_segment_basic():
    data = {"n_round_trips": 0, "arming_bar": {"round_trips_needed": 20, "armable": False, "beats_null": None}}
    assert gs._shadow_segment("SSR shadow", data) == "SSR shadow 0/20"


def test_shadow_segment_needs_beats_null_annotation():
    data = {"n_round_trips": 48, "arming_bar": {"round_trips_needed": 20, "armable": False, "beats_null": False}}
    assert gs._shadow_segment("MES mirror", data) == "MES mirror 48/20 (needs beats-null)"


def test_shadow_segment_armable_true_no_annotation():
    data = {"n_round_trips": 25, "arming_bar": {"round_trips_needed": 20, "armable": True, "beats_null": True}}
    assert gs._shadow_segment("MES mirror", data) == "MES mirror 25/20"


def test_compose_clocks_line_joins_available_segments():
    out = gs._compose_clocks_line(["SSR shadow 0/20", None, "Cap shadow 13/20"])
    assert out == "Clocks: SSR shadow 0/20 · Cap shadow 13/20"


def test_compose_clocks_line_all_missing_is_none():
    assert gs._compose_clocks_line([None, None, None]) is None


# ============================================================================
# _pnl_segments / _trades_rows_for_day / money formatting
# ============================================================================

def test_fmt_money_rounds_and_adds_commas():
    assert gs._fmt_money(6068.4) == "$6,068"
    assert gs._fmt_money(-342) == "$342"


def test_fmt_signed_money_flat_near_zero():
    assert gs._fmt_signed_money(0.001) == "flat"


def test_fmt_signed_money_up_down():
    assert gs._fmt_signed_money(100) == "up $100"
    assert gs._fmt_signed_money(-100) == "down $100"


def test_pnl_segments_groups_by_account_and_sums():
    rows = [
        {"account_id": "safe", "dollar_pnl": "100"},
        {"account_id": "safe", "dollar_pnl": "-40"},
        {"account_id": "bold", "dollar_pnl": "-305"},
    ]
    assert gs._pnl_segments(rows) == [("bold", 1, -305.0), ("safe", 2, 60.0)]


def test_pnl_segments_skips_non_numeric_rows():
    rows = [{"account_id": "safe", "dollar_pnl": "not-a-number"}, {"account_id": "safe", "dollar_pnl": "10"}]
    assert gs._pnl_segments(rows) == [("safe", 1, 10.0)]


def test_pnl_segments_empty_rows_is_empty():
    assert gs._pnl_segments([]) == []


def test_trades_rows_for_day_filters_by_date(tmp_path):
    p = tmp_path / "trades.csv"
    _write_text(p, "date,account_id,dollar_pnl\n2026-08-08,safe,100\n2026-08-07,safe,50\n")
    rows = gs._trades_rows_for_day(p, "2026-08-08")
    assert len(rows) == 1
    assert rows[0]["dollar_pnl"] == "100"


def test_trades_rows_for_day_robust_to_trailing_new_column(tmp_path):
    """L(BXM-PROBE) precedent: journal/trades.csv gained theta_at_entry AFTER account_id.
    DictReader keys by column NAME, never a fixed index, so this must stay robust to any
    future trailing column the journal schema grows."""
    p = tmp_path / "trades.csv"
    _write_text(
        p,
        "date,account_id,dollar_pnl,theta_at_entry\n2026-08-08,safe,100,-0.05\n",
    )
    rows = gs._trades_rows_for_day(p, "2026-08-08")
    assert len(rows) == 1
    segs = gs._pnl_segments(rows)
    assert segs == [("safe", 1, 100.0)]


def test_trades_rows_for_day_missing_file_is_empty(tmp_path):
    assert gs._trades_rows_for_day(tmp_path / "nope.csv", "2026-08-08") == []


def test_et_midnight_iso_format():
    out = gs._et_midnight_iso("2026-08-08")
    assert out.startswith("2026-08-08T00:00:00")
    assert out[-6] in "+-"
    assert out.endswith(":00")


# ============================================================================
# gather_facts + compose_*_text -- full-fixture integration tests
# ============================================================================

def test_compose_morning_full_fixture(state_paths, monkeypatch):
    _write_json(state_paths["shadow"], {
        "n_round_trips": 48,
        "arming_bar": {"round_trips_needed": 20, "armable": False, "beats_null": False},
    })
    _write_json(state_paths["ssr"], {
        "n_round_trips": 0,
        "arming_bar": {"round_trips_needed": 20, "armable": False, "beats_null": None},
    })
    _write_text(state_paths["cap_ledger"], "\n".join('{"a":%d}' % i for i in range(13)) + "\n")
    _write_text(state_paths["queue_md"], "\n".join(f"- [ ] item{i}" for i in range(5)) + "\n")
    _write_json(state_paths["wants"], _wants_doc([
        {"priority": 1, "id": "a", "text": "Rotate the tokens"},
        {"priority": 2, "id": "b", "text": "Unmute the channel"},
        {"priority": 3, "id": "c", "text": "Do the reps"},
    ]))
    monkeypatch.setattr(gs, "_git_log_subjects", lambda since, until=None: [
        "abc1234 feat(exits): shipped the new exit lane",
        "def5678 fix: corrected a budget sizing bug",
        "c0ffee1 chore: auto-commit candidates",
        "fed9012 docs: flagged a regressing trend",
    ])

    now = _dt(TUESDAY, 8, 15)
    facts = gs.gather_facts("morning", now.strftime("%Y-%m-%d"), now)
    text = gs.compose_morning_text(facts)

    assert text.startswith("Morning J — Gamma here.")
    assert "**OVERNIGHT/YESTERDAY**" in text
    assert "Shipped the new exit lane" in text
    assert "Corrected a budget sizing bug" in text
    assert "Flagged a regressing trend" in text
    assert "auto-commit candidates" not in text  # chore: excluded by type filter
    assert "**TODAY**" in text
    assert "5 open research items; today I'm on the top one." in text
    assert "**I WANT**" in text
    assert "Rotate the tokens" in text
    assert "Unmute the channel" in text
    assert "Do the reps" in text
    assert "Clocks: SSR shadow 0/20 · MES mirror 48/20 (needs beats-null) · Cap shadow 13/20" in text
    assert "WEEKEND RECAP" not in text
    assert len(text) <= gs.CHAR_CAP
    # "focus" field (2026-08-08 follow-up) -- must match the TODAY bullet
    # verbatim, since gamma_hq.py's GAMMA HQ window renders it directly.
    assert facts["focus"] == "5 open research items; today I'm on the top one."
    assert facts["focus"] == facts["today_bullet"]


def test_compose_eod_full_fixture(state_paths, monkeypatch):
    now = _dt(TUESDAY, 16, 45)
    day = now.strftime("%Y-%m-%d")
    monkeypatch.setattr(gs, "_git_log_subjects", lambda since, until=None: [
        "abc1234 fix: closed the exit-repair question for good",
    ])
    _write_text(state_paths["trades_csv"],
                "date,account_id,dollar_pnl\n" + f"{day},safe,150\n" + f"{day},bold,75\n")
    _write_text(state_paths["queue_md"], "\n".join(f"- [ ] item{i}" for i in range(7)) + "\n")
    _write_json(state_paths["wants"], _wants_doc([{"priority": 1, "id": "a", "text": "want a"}]))

    facts = gs.gather_facts("eod", day, now)
    text = gs.compose_eod_text(facts)

    assert text.startswith("EOD from Gamma.")
    assert "Safe up $150 on 1 trade" in text
    assert "Bold up $75 on 1 trade" in text
    assert "Overall up $225." in text
    assert "**WHAT I LEARNED**" in text
    assert "Closed the exit-repair question for good" in text
    assert "**TOMORROW**" in text
    assert "7 open research items; tomorrow I'm on the top one." in text
    assert "**I WANT**" in text
    assert "want a" in text
    assert len(text) <= gs.CHAR_CAP
    # EOD has no TODAY section -- "focus" must stay None (gamma_hq.py falls
    # back to first-line-of-"text" for EOD-mode standups).
    assert facts["focus"] is None


def test_gather_facts_morning_focus_fallback_when_queue_unreadable(state_paths, monkeypatch):
    # queue.md is never written in this fixture -- _queue_unchecked_count
    # returns None, so today_bullet is None too; focus must fall back to the
    # SAME phrase compose_morning_text's own TODAY section would show.
    _no_git(monkeypatch)
    now = _dt(TUESDAY, 8, 15)
    facts = gs.gather_facts("morning", now.strftime("%Y-%m-%d"), now)
    assert facts["today_bullet"] is None
    assert facts["focus"] == "Nothing queued -- reading the tape as it comes."


def test_missing_everything_produces_valid_short_message(state_paths, monkeypatch):
    _no_git(monkeypatch)
    now = _dt(TUESDAY, 8, 15)
    day = now.strftime("%Y-%m-%d")

    text_m = gs.compose_morning_text(gs.gather_facts("morning", day, now))
    assert text_m.startswith("Morning J — Gamma here.")
    assert len(text_m) <= gs.CHAR_CAP
    assert len(text_m) < 500
    for bad in gs.BANNED_SUBSTRINGS:
        assert bad not in text_m

    now_eod = _dt(TUESDAY, 16, 45)
    text_e = gs.compose_eod_text(gs.gather_facts("eod", day, now_eod))
    assert text_e.startswith("EOD from Gamma.")
    assert len(text_e) <= gs.CHAR_CAP
    assert len(text_e) < 500
    for bad in gs.BANNED_SUBSTRINGS:
        assert bad not in text_e


def test_eod_pnl_fallback_when_no_trades_weekday(state_paths, monkeypatch):
    _no_git(monkeypatch)
    now = _dt(TUESDAY, 16, 45)
    facts = gs.gather_facts("eod", now.strftime("%Y-%m-%d"), now)
    text = gs.compose_eod_text(facts)
    assert "No trades today." in text
    assert "market closed" not in text


def test_eod_pnl_fallback_on_weekend(state_paths, monkeypatch):
    _no_git(monkeypatch)
    now = _dt(SATURDAY, 16, 45)
    facts = gs.gather_facts("eod", now.strftime("%Y-%m-%d"), now)
    text = gs.compose_eod_text(facts)
    assert "No trades today (market closed)." in text


# ============================================================================
# Hard cap + banned-substring leak tests (git-source injection, realistic path)
# ============================================================================

def test_finalize_enforces_hard_cap_directly():
    long_text = "line\n" * 500
    out = gs._finalize(long_text)
    assert len(out) <= gs.CHAR_CAP


def test_char_cap_enforced_end_to_end(state_paths, monkeypatch):
    monkeypatch.setattr(gs, "_git_log_subjects", lambda since, until=None: [
        f"abc{i} fix: {'padding text ' * 20}" for i in range(10)
    ])
    _write_json(state_paths["wants"], _wants_doc([
        {"priority": 1, "id": "a", "text": "want text " * 40},
        {"priority": 2, "id": "b", "text": "want text " * 40},
        {"priority": 3, "id": "c", "text": "want text " * 40},
    ]))
    now = _dt(TUESDAY, 8, 15)
    facts = gs.gather_facts("morning", now.strftime("%Y-%m-%d"), now)
    text = gs.compose_morning_text(facts)
    assert len(text) <= gs.CHAR_CAP


def test_banned_substrings_never_leak_from_git_source(state_paths, monkeypatch):
    """Fixture a STATUS.md-style DEGRADED/MASKED EXIT line as a fake commit subject and
    prove it never survives into the composed message -- the exact scenario named in the
    build spec ("fixture a STATUS-style DEGRADED line and prove it never leaks")."""
    monkeypatch.setattr(gs, "_git_log_subjects", lambda since, until=None: [
        "abc1234 fix: resolve SELF-CHECK DEGRADED alert for run-cmd-hidden MASKED EXIT",
        "def5678 fix: a perfectly clean commit message",
    ])
    now = _dt(TUESDAY, 8, 15)
    facts = gs.gather_facts("morning", now.strftime("%Y-%m-%d"), now)
    text = gs.compose_morning_text(facts)
    for bad in gs.BANNED_SUBSTRINGS:
        assert bad not in text
    assert "A perfectly clean commit message" in text


@pytest.mark.parametrize("bad", gs.BANNED_SUBSTRINGS)
def test_banned_substring_dropped_from_overnight_bullets_parametrized(state_paths, monkeypatch, bad):
    monkeypatch.setattr(gs, "_git_log_subjects", lambda since, until=None: [
        f"abc1234 fix: something referencing {bad} in the message",
        "def5678 docs: an unrelated clean entry",
    ])
    now = _dt(TUESDAY, 8, 15)
    facts = gs.gather_facts("morning", now.strftime("%Y-%m-%d"), now)
    text = gs.compose_morning_text(facts)
    assert bad not in text


# ============================================================================
# Monday / WEEKEND RECAP detection
# ============================================================================

def test_monday_includes_weekend_recap_section(state_paths, monkeypatch):
    _no_git(monkeypatch)
    now = _dt(MONDAY, 8, 15)
    facts = gs.gather_facts("morning", now.strftime("%Y-%m-%d"), now)
    text = gs.compose_morning_text(facts)
    assert "WEEKEND RECAP" in text


def test_non_monday_omits_weekend_recap_section(state_paths, monkeypatch):
    _no_git(monkeypatch)
    now = _dt(TUESDAY, 8, 15)
    facts = gs.gather_facts("morning", now.strftime("%Y-%m-%d"), now)
    text = gs.compose_morning_text(facts)
    assert "WEEKEND RECAP" not in text


def test_monday_weekend_recap_uses_wider_git_window(state_paths, monkeypatch):
    calls = []

    def fake_git(since, until=None):
        calls.append((since, until))
        return []

    monkeypatch.setattr(gs, "_git_log_subjects", fake_git)
    now = _dt(MONDAY, 8, 15)
    gs.gather_facts("morning", now.strftime("%Y-%m-%d"), now)
    assert ("18 hours ago", None) in calls
    assert any(since != "18 hours ago" for since, _until in calls)


# ============================================================================
# Line-1 exact text (test-enforced literal strings)
# ============================================================================

def test_line1_exact_text_morning(state_paths, monkeypatch):
    _no_git(monkeypatch)
    now = _dt(TUESDAY, 8, 15)
    facts = gs.gather_facts("morning", now.strftime("%Y-%m-%d"), now)
    text = gs.compose_morning_text(facts)
    assert text.split("\n")[0] == "Morning J — Gamma here."


def test_line1_exact_text_eod(state_paths, monkeypatch):
    _no_git(monkeypatch)
    now = _dt(TUESDAY, 16, 45)
    facts = gs.gather_facts("eod", now.strftime("%Y-%m-%d"), now)
    text = gs.compose_eod_text(facts)
    assert text.split("\n")[0] == "EOD from Gamma."


# ============================================================================
# I WANT delta (eod) across runs, via gamma-standup-latest.json
# ============================================================================

def test_eod_wants_delta_flags_new_since_last_latest_json(state_paths, monkeypatch):
    _write_json(state_paths["wants"], _wants_doc([
        {"priority": 1, "id": "a", "text": "want a"},
        {"priority": 2, "id": "b", "text": "want b"},
    ]))
    _write_json(state_paths["latest"], {"wants_shown": ["a"]})  # simulates this morning's run
    _no_git(monkeypatch)
    now = _dt(TUESDAY, 16, 45)
    facts = gs.gather_facts("eod", now.strftime("%Y-%m-%d"), now)
    text = gs.compose_eod_text(facts)
    assert "(new) want b" in text
    assert "want a" in text
    assert "(new) want a" not in text


def test_eod_wants_no_delta_annotation_without_prior_latest_json(state_paths, monkeypatch):
    _write_json(state_paths["wants"], _wants_doc([{"priority": 1, "id": "a", "text": "want a"}]))
    _no_git(monkeypatch)
    now = _dt(TUESDAY, 16, 45)
    facts = gs.gather_facts("eod", now.strftime("%Y-%m-%d"), now)
    text = gs.compose_eod_text(facts)
    assert "(new)" not in text
    assert "want a" in text


# ============================================================================
# Discord mention loader
# ============================================================================

def test_load_user_mention_reads_config(state_paths):
    _write_json(state_paths["discord_cfg"], {"user_id": "12345"})
    assert gs._load_user_mention() == "<@12345> "


def test_load_user_mention_missing_config_is_empty(state_paths):
    assert gs._load_user_mention() == ""


# ============================================================================
# Outbox row schema + append/write helpers
# ============================================================================

def test_outbox_row_schema_matches_bridge_expected_keys():
    row = gs.build_outbox_row("hello", "gamma_standup_morning", "2026-08-08T08:15:00")
    assert set(row.keys()) == {"content", "source", "queued_at"}
    assert row["content"] == "hello"
    assert row["source"] == "gamma_standup_morning"
    assert row["queued_at"] == "2026-08-08T08:15:00"


def test_append_outbox_writes_jsonl_line(state_paths):
    gs.append_outbox({"content": "hi", "source": "test", "queued_at": "2026-08-08T00:00:00"})
    lines = state_paths["outbox"].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["content"] == "hi"


def test_write_latest_writes_json(state_paths):
    gs.write_latest({"mode": "morning", "text": "hi"})
    data = json.loads(state_paths["latest"].read_text(encoding="utf-8"))
    assert data["mode"] == "morning"


# ============================================================================
# main() -- CLI, dry-run, real-run
# ============================================================================

def test_dry_run_appends_nothing(state_paths, monkeypatch):
    _no_git(monkeypatch)
    rc = gs.main(["--mode", "morning", "--dry-run"])
    assert rc == 0
    assert not state_paths["outbox"].exists()
    assert not state_paths["latest"].exists()


def test_dry_run_eod_appends_nothing(state_paths, monkeypatch):
    _no_git(monkeypatch)
    rc = gs.main(["--mode", "eod", "--dry-run"])
    assert rc == 0
    assert not state_paths["outbox"].exists()
    assert not state_paths["latest"].exists()


def test_real_run_appends_one_row_and_writes_latest_json(state_paths, monkeypatch):
    _no_git(monkeypatch)
    _write_json(state_paths["discord_cfg"], {"user_id": "207983230618435584"})
    rc = gs.main(["--mode", "eod"])
    assert rc == 0

    assert state_paths["outbox"].exists()
    lines = state_paths["outbox"].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert set(row.keys()) == {"content", "source", "queued_at"}
    assert row["content"].startswith("<@207983230618435584> EOD from Gamma.")
    assert row["source"] == "gamma_standup_eod"

    assert state_paths["latest"].exists()
    latest = json.loads(state_paths["latest"].read_text(encoding="utf-8"))
    assert latest["mode"] == "eod"
    assert "text" in latest and latest["text"].startswith("EOD from Gamma.")
    assert "wants_shown" in latest
    # "focus" schema addition (2026-08-08 follow-up) -- present but null for
    # EOD (no TODAY section to derive it from).
    assert "focus" in latest
    assert latest["focus"] is None


def test_real_morning_run_writes_focus_field_to_latest_json_round_trip(state_paths, monkeypatch):
    # Full round-trip: real (non-dry-run) morning main() call -> compose ->
    # write_latest() -> read the json back off disk -> "focus" is present,
    # correct, and every pre-existing key is still there too (schema ADDITION,
    # backward compatible -- nothing was removed or renamed).
    _no_git(monkeypatch)
    _write_text(state_paths["queue_md"], "\n".join(f"- [ ] item{i}" for i in range(3)) + "\n")
    rc = gs.main(["--mode", "morning"])
    assert rc == 0

    assert state_paths["latest"].exists()
    latest = json.loads(state_paths["latest"].read_text(encoding="utf-8"))
    assert latest["focus"] == "3 open research items; today I'm on the top one."
    assert {"mode", "day", "generated_et", "text", "char_len", "wants_shown", "focus"} <= set(latest.keys())
    assert latest["mode"] == "morning"
    assert f"- {latest['focus']}" in latest["text"]  # matches the TODAY bullet actually shown


def test_real_run_twice_appends_two_rows(state_paths, monkeypatch):
    _no_git(monkeypatch)
    gs.main(["--mode", "morning"])
    gs.main(["--mode", "morning"])
    lines = state_paths["outbox"].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_main_requires_mode_argument(state_paths, monkeypatch):
    _no_git(monkeypatch)
    with pytest.raises(SystemExit):
        gs.main([])


def test_main_rejects_invalid_mode(state_paths, monkeypatch):
    _no_git(monkeypatch)
    with pytest.raises(SystemExit):
        gs.main(["--mode", "bogus"])
