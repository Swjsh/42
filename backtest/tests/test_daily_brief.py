"""Guard for daily_brief.py -- Gamma's twice-daily self-initiated presence brief.

Covers the load-bearing contracts:
  1. Morning + EOD compose correctly from fixture state (deterministic, no LLM).
  2. Missing/garbled state degrades to explicit "no data" phrasing, never crashes.
  3. The spoken-script word cap (140) is actually ENFORCED, not just usually true.
  4. NO broker import anywhere in the module's source (static scan -- this script must
     never touch Alpaca, it is a pure state-file reader per the daily_brief.py doctrine).
  5. File-based readers (_status_headers / _queue_backlog_titles / _dojo_brief_info /
     _setups_traded_today / _nearest_levels) are fail-open against a missing/garbled
     file (or None input) on disk.

Imports the script by path (not a package), matching this repo's open_bell_status.py /
engine_health.py test convention.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_DB_PATH = _REPO / "setup" / "scripts" / "daily_brief.py"
_spec = importlib.util.spec_from_file_location("daily_brief_under_test", _DB_PATH)
db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db)


# --------------------------------------------------------------------------- #
# 4. NO broker import anywhere in the source (static scan -- cheap, load-bearing).
# --------------------------------------------------------------------------- #

def test_no_broker_imports_in_source():
    src = _DB_PATH.read_text(encoding="utf-8").lower()
    for banned in ("import alpaca", "mcp__alpaca", "fleet_broker", "alpaca_mcp", "import requests"):
        assert banned not in src, f"daily_brief.py must never import/touch {banned!r}"


# --------------------------------------------------------------------------- #
# MORNING -- fixtures + composition.
# --------------------------------------------------------------------------- #

_BIAS = {"bias": "no-trade", "bias_note": "SPY chopping 740-748. Lean: wait for a confirmed break."}
_KEY_LEVELS = {
    "spot_at_compute": 748.6,
    "levels": [
        {"price": 745.76, "type": "support"},
        {"price": 746.11, "type": "resistance"},
        {"price": 748.30, "type": "resistance"},
        {"price": 900.00, "type": "resistance"},  # far away -- must NOT make the nearest-3
    ],
}
_SAFE_BREAKER = {"tripped": False, "last_reset": "2026-07-22T08:30:00-04:00"}
_BOLD_BREAKER = {"tripped": False, "session_id": "2026-07-22"}
_STATUS_HEADERS = [
    "[2026-07-22 ~19:12 ET] OK -- conductor: fixed X",
    "[2026-07-22 ~18:42 ET] OK -- conductor: shipped Y",
]


def test_morning_composes_from_fixtures():
    facts = db.gather_morning_facts(
        "2026-07-22", today_bias=_BIAS, key_levels=_KEY_LEVELS,
        safe_breaker=_SAFE_BREAKER, bold_breaker=_BOLD_BREAKER, status_headers=_STATUS_HEADERS,
    )
    text = db.compose_morning_text(facts)
    assert text.startswith("Gamma here.")
    assert "no-trade" in text
    assert "745.76" in text and "900.00" not in text  # nearest-3 only, not the far level
    assert "Safe armed" in text and "Bold armed" in text
    assert "fixed X" in text and "shipped Y" in text


def test_morning_caption_is_three_lines():
    facts = db.gather_morning_facts(
        "2026-07-22", today_bias=_BIAS, key_levels=_KEY_LEVELS,
        safe_breaker=_SAFE_BREAKER, bold_breaker=_BOLD_BREAKER, status_headers=_STATUS_HEADERS,
    )
    caption = db.build_caption("morning", "2026-07-22", facts)
    assert len(caption.splitlines()) == 3
    assert "GAMMA MORNING BRIEF" in caption


def test_morning_tripped_breaker_shows_in_text():
    tripped = {"tripped": True, "tripped_reason": "daily_loss_31%"}
    facts = db.gather_morning_facts(
        "2026-07-22", today_bias=_BIAS, key_levels=_KEY_LEVELS,
        safe_breaker=tripped, bold_breaker=_BOLD_BREAKER, status_headers=_STATUS_HEADERS,
    )
    text = db.compose_morning_text(facts)
    assert "TRIPPED" in text and "daily_loss_31%" in text


def test_morning_all_inputs_none_never_raises_and_says_no_data():
    """Every morning source may be totally missing -- must degrade to honest 'no data'
    phrasing, never crash, never fabricate a bias/level/status that isn't there."""
    facts = db.gather_morning_facts("2026-07-22")
    text = db.compose_morning_text(facts)
    assert text.startswith("Gamma here.")
    assert "unknown" in text
    assert facts["safe_breaker"] == "unknown" and facts["bold_breaker"] == "unknown"
    assert "No fresh key levels" in text
    assert "Quiet overnight" in text


# --------------------------------------------------------------------------- #
# EOD -- fixtures + composition.
# --------------------------------------------------------------------------- #

_PNL_LOSS = {
    "by_arm": [{"arm": "safe-2", "n_round_trips": 3, "realized_pnl": -108.0,
                "engine_pnl": -108.0, "manual_pnl": 0.0}],
    "total_pnl": -108.0, "source": "pnl-statement.json (T1, broker-truth)",
}
_PNL_WIN = {
    "by_arm": [{"arm": "safe-2", "n_round_trips": 5, "realized_pnl": 240.0,
                "engine_pnl": 151.0, "manual_pnl": 89.0}],
    "total_pnl": 240.0, "source": "pnl-statement.json (T1, broker-truth)",
}
_TRADE_TODAY = {"spy_fills_today": 3, "placed_not_filled_today": 1}
_SETUPS = ["BULLISH_RECLAIM_RIDE_THE_RIBBON"]
_QUEUE_TITLES = ["GAMMA-STUDY-CURRICULUM", "PULLBACK-HOLD-BULL-TRIGGER"]
_DOJO_YES = {"exists": True, "n_exhibits": 6}
_DOJO_NO = {"exists": False, "n_exhibits": 0}


def test_eod_composes_losing_day_honestly():
    facts = db.gather_eod_facts(
        "2026-07-22", pnl=_PNL_LOSS, trade_today=_TRADE_TODAY, setups=_SETUPS,
        queue_titles=_QUEUE_TITLES, dojo_info=_DOJO_YES,
    )
    text = db.compose_eod_text(facts)
    assert "down $108" in text
    assert "safe-2" in text
    assert "3 fill" in text
    assert "BULLISH_RECLAIM_RIDE_THE_RIBBON" in text
    assert "Film room is ready" in text and "6 exhibits" in text
    # Honesty rail (no sugar-coating a loss): the TOTAL sentence must never say "up".
    overall_sentence = text.split("Overall")[1].split(".")[0]
    assert "up $" not in overall_sentence


def test_eod_composes_winning_day():
    facts = db.gather_eod_facts(
        "2026-07-22", pnl=_PNL_WIN, trade_today=_TRADE_TODAY, setups=_SETUPS,
        queue_titles=_QUEUE_TITLES, dojo_info=_DOJO_NO,
    )
    text = db.compose_eod_text(facts)
    assert "up $240" in text
    assert "Film room" not in text  # no dojo session today -- must not fabricate one


def test_eod_flat_day_says_flat_not_a_fabricated_sign():
    pnl_flat = {"by_arm": [], "total_pnl": 0.0, "source": "pnl-statement.json (T1, broker-truth)"}
    facts = db.gather_eod_facts("2026-07-22", pnl=pnl_flat, trade_today=None, setups=[],
                                 queue_titles=[], dojo_info=None)
    text = db.compose_eod_text(facts)
    assert "flat" in text
    assert "No account traded today" in text


def test_eod_missing_pnl_source_says_unknown_not_zero():
    """No pnl-statement.json entry for the day -> must say P&L is UNKNOWN, never silently
    report $0 (a fabricated flat day would be worse than an honest 'no data')."""
    facts = db.gather_eod_facts("2026-07-22", pnl={}, trade_today=None, setups=[],
                                 queue_titles=[], dojo_info=None)
    text = db.compose_eod_text(facts)
    assert "P&L unknown" in text


def test_eod_caption_is_three_lines():
    facts = db.gather_eod_facts(
        "2026-07-22", pnl=_PNL_LOSS, trade_today=_TRADE_TODAY, setups=_SETUPS,
        queue_titles=_QUEUE_TITLES, dojo_info=_DOJO_YES,
    )
    caption = db.build_caption("eod", "2026-07-22", facts)
    assert len(caption.splitlines()) == 3
    assert "GAMMA EOD BRIEF" in caption


# --------------------------------------------------------------------------- #
# 3. Word-cap enforcement -- prove truncate_to_word_cap ACTS, not just usually true.
# --------------------------------------------------------------------------- #

def test_word_cap_is_enforced_on_oversized_input():
    huge = " ".join(f"word{i}" for i in range(500))
    capped = db.truncate_to_word_cap(huge, cap=140)
    assert len(capped.split()) <= 140


def test_morning_text_never_exceeds_word_cap_even_with_many_headers():
    many_headers = [
        f"[2026-07-22 ~{h:02d}:00 ET] OK -- conductor did a whole lot of work item number {h}"
        for h in range(20)
    ]
    facts = db.gather_morning_facts(
        "2026-07-22", today_bias=_BIAS, key_levels=_KEY_LEVELS,
        safe_breaker=_SAFE_BREAKER, bold_breaker=_BOLD_BREAKER, status_headers=many_headers,
    )
    text = db.compose_morning_text(facts)
    assert len(text.split()) <= db.WORD_CAP


def test_eod_text_never_exceeds_word_cap_even_with_many_arms():
    many_arms = [{"arm": f"arm-{i}", "n_round_trips": i + 1, "realized_pnl": -i * 3.0,
                  "engine_pnl": -i * 3.0, "manual_pnl": 0.0} for i in range(20)]
    pnl = {"by_arm": many_arms, "total_pnl": -300.0, "source": "pnl-statement.json (T1, broker-truth)"}
    facts = db.gather_eod_facts(
        "2026-07-22", pnl=pnl, trade_today=_TRADE_TODAY, setups=_SETUPS * 10,
        queue_titles=_QUEUE_TITLES, dojo_info=_DOJO_YES,
    )
    text = db.compose_eod_text(facts)
    assert len(text.split()) <= db.WORD_CAP


# --------------------------------------------------------------------------- #
# 5. File-based readers -- fail-open against missing/garbled files (or None) on disk.
# --------------------------------------------------------------------------- #

def test_status_headers_missing_file_returns_empty():
    assert db._status_headers(Path("Z:/does/not/exist-daily-brief-test.md")) == []


def test_status_headers_parses_newest_first(tmp_path):
    p = tmp_path / "STATUS.md"
    p.write_text("## [2026-07-22 a] OK -- first\nbody\n\n## [2026-07-21 b] OK -- second\n", encoding="utf-8")
    headers = db._status_headers(p, n=3)
    assert headers[0].startswith("[2026-07-22 a]")
    assert "first" in headers[0]


def test_queue_backlog_titles_missing_file_returns_empty():
    assert db._queue_backlog_titles(Path("Z:/does/not/exist-daily-brief-test.md")) == []


def test_queue_backlog_titles_stops_at_completed_section(tmp_path):
    p = tmp_path / "queue.md"
    p.write_text(
        "## Active backlog\n\n### REAL-ITEM (HIGH, filed today)\n\n"
        "## Completed\n\n### OLD-DONE-ITEM (LOW)\n",
        encoding="utf-8",
    )
    titles = db._queue_backlog_titles(p, n=5)
    assert titles == ["REAL-ITEM"]


def test_dojo_brief_info_missing_file_returns_not_exists():
    assert db._dojo_brief_info("1999-01-01") == {"exists": False, "n_exhibits": 0}


def test_setups_traded_today_missing_files_returns_empty():
    assert db._setups_traded_today("1999-01-01") == []


def test_nearest_levels_handles_missing_or_malformed_input():
    assert db._nearest_levels(None) == []
    assert db._nearest_levels({"levels": []}) == []
    assert db._nearest_levels({"spot_at_compute": 700, "levels": "not-a-list"}) == []


def test_breaker_armed_str_unknown_on_none():
    assert db._breaker_armed_str(None, "last_reset", "2026-07-22") == "unknown"


def test_breaker_armed_str_stale_rearm_is_distinguishable():
    stale = {"tripped": False, "last_reset": "2026-07-20T08:30:00-04:00"}
    assert db._breaker_armed_str(stale, "last_reset", "2026-07-22") == "armed (stale re-arm)"
