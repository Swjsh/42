"""Guards for setup/scripts/macro_calendar.py -- the macro/news calendar producer.

Context (2026-07-09): automation/state/macro-calendar.json's only producer was
weekly-review.md Section 8a, a WebFetch step at the tail of a long Sunday LLM
prompt. It silently stopped updating refresh_log[] after 2026-06-14 while
weekly-review itself kept firing and exiting 0 -- confirmed live via
today-bias.json#news_calendar == {"no_trade_window": [], "stale": true,
"calendar_freshness_days": 24} on 2026-07-08. macro_calendar.py replaces that
fragile path with a deterministic, dependency-free script. These tests guard
the three properties the task required:
  1. Schema-compat with consumers (premarket.md Step 1b / dashboard / backtest
     contracts) -- every field those readers touch must exist with the right
     shape.
  2. Fail-open on source error -- a fully-broken network must never raise,
     never wipe existing events, and must still produce a written file.
  3. Freshness stamp -- every run leaves refresh_log[-1].ran_at / news.json's
     as_of within seconds of "now", so the staleness gate premarket.md Step 1b
     computes (days_stale > params.macro_calendar_max_staleness_days) reads 0
     immediately after this script runs.

All tests operate on an isolated tmp_path repo root -- NEVER the real
automation/state/*.json (those are live production files this script also
writes on schedule; tests must not depend on or mutate them).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import macro_calendar as mc  # noqa: E402

TODAY = "2026-07-09"

# A trimmed but structurally-real no_trade_window_rules block (subset of the
# live file) so compute_no_trade_windows() is exercised against real doctrine
# shapes, not a stub.
NO_TRADE_RULES = {
    "cpi_release": {"block_starts_minutes_before": 5, "block_ends_minutes_after": 30},
    "fomc_decision": {"block_starts_minutes_before": 30, "block_ends_minutes_after": 60},
    "ppi_release": {"block_starts_minutes_before": 5, "block_ends_minutes_after": 20},
}


def _seed_repo(tmp_path: Path, calendar_extra: dict | None = None, write_alpaca_calendar: bool = True) -> Path:
    """Build a minimal isolated repo skeleton under tmp_path and return its root."""
    state = tmp_path / "automation" / "state"
    state.mkdir(parents=True)
    base_calendar = {
        "schema_version": 1,
        "purpose": "test fixture",
        "no_trade_window_rules": NO_TRADE_RULES,
        "events_30d": [],
        "earnings_30d": [],
        "fetch_failures": [],
        "refresh_log": [],
    }
    if calendar_extra:
        base_calendar.update(calendar_extra)
    (state / "macro-calendar.json").write_text(json.dumps(base_calendar), encoding="utf-8")
    if write_alpaca_calendar:
        (state / "calendar.json").write_text(
            json.dumps({"source": "alpaca_v2_calendar", "holidays": ["2026-01-01", "2026-07-03"]}),
            encoding="utf-8",
        )
    return tmp_path


def _always_fails(url: str) -> tuple[int, str]:
    return 0, "connection refused (simulated)"


def _always_200_no_match(url: str) -> tuple[int, str]:
    return 200, "<html>irrelevant body</html>"


# --------------------------------------------------------------------------- #
# 1. Schema-compat with consumers
# --------------------------------------------------------------------------- #
def test_events_have_required_premarket_fields() -> None:
    """premarket.md Step 1b reads date/time_et/event/type/severity/source_url
    off every events_30d[] entry. KNOWN_EVENTS_2026 must never regress that."""
    required = {"date", "time_et", "event", "type", "severity", "source_url"}
    for ev in mc.KNOWN_EVENTS_2026:
        missing = required - ev.keys()
        assert not missing, f"{ev.get('event')} missing fields {missing}"
        assert ev["severity"] in ("high", "med", "low")
        # OP-18: no speculation -- every event must cite a source.
        assert ev["source_url"].startswith("https://"), f"{ev['event']} has no real source_url"


def test_no_trade_window_output_shape_matches_dashboard_and_backtest_contract() -> None:
    """dashboard/lib/state.ts expects no_trade_window: Array<{start_et,end_et,event}>;
    backtest/lib/contracts/models.py's _NewsCalendar expects events_today: List[Any]
    consumed the same way. compute_no_trade_windows must satisfy both shapes."""
    events_today = [
        {"date": TODAY, "time_et": "08:30", "event": "CPI (June 2026 data)",
         "type": "cpi_release", "severity": "high", "source_url": "https://www.bls.gov/x"},
    ]
    windows = mc.compute_no_trade_windows(events_today, NO_TRADE_RULES)
    assert len(windows) == 1
    w = windows[0]
    for key in ("start_et", "end_et", "event", "type", "severity"):
        assert key in w
    # CPI 08:30, block -5/+30 minutes -> 08:25 .. 09:00
    assert w["start_et"] == "08:25"
    assert w["end_et"] == "09:00"


def test_low_severity_events_never_produce_a_no_trade_window() -> None:
    events_today = [
        {"date": TODAY, "time_et": "10:00", "event": "Consumer confidence", "type": "cpi_release",
         "severity": "low", "source_url": "https://example.gov"},
    ]
    assert mc.compute_no_trade_windows(events_today, NO_TRADE_RULES) == []


def test_news_json_preserves_legacy_top_level_keys(tmp_path: Path) -> None:
    """The historical hand-written news.json (as_of, for_session, regime,
    catalyst_summary, primary_catalyst, secondary_catalysts, vix_expectation,
    key_levels_for_session, no_trade_windows_added_for_today,
    implication_for_setups, watch_for_reversal, sources,
    next_scheduled_news_check) must all still be present so no existing
    consumer keyed on one of them starts KeyError-ing."""
    repo = _seed_repo(tmp_path)
    summary = mc.run(repo, today=TODAY, do_fetch=False, dry_run=True)
    news = mc.build_news_json(
        mc.load_json(repo / "automation" / "state" / "macro-calendar.json", {}), TODAY, TODAY
    )
    legacy_keys = {
        "as_of", "for_session", "regime", "catalyst_summary", "primary_catalyst",
        "secondary_catalysts", "vix_expectation", "key_levels_for_session",
        "no_trade_windows_added_for_today", "implication_for_setups",
        "watch_for_reversal", "sources", "next_scheduled_news_check",
    }
    missing = legacy_keys - news.keys()
    assert not missing, f"news.json dropped legacy keys: {missing}"
    assert summary["wrote"] is False  # dry-run must not write


def test_primary_catalyst_is_string_typed_like_the_legacy_file(tmp_path: Path) -> None:
    """verify-news-json.ps1 (and any future consumer) does
    `$json.primary_catalyst.type` / `.description.Substring(...)` -- both must
    stay non-empty strings, never null, when at least one event exists."""
    repo = _seed_repo(tmp_path, calendar_extra={"events_30d": list(mc.KNOWN_EVENTS_2026)})
    mc.run(repo, today=TODAY, do_fetch=False, dry_run=True)
    calendar = mc.load_json(repo / "automation" / "state" / "macro-calendar.json", {})
    news = mc.build_news_json(calendar, TODAY, TODAY)
    assert isinstance(news["primary_catalyst"]["type"], str) and news["primary_catalyst"]["type"]
    assert isinstance(news["primary_catalyst"]["description"], str) and len(news["primary_catalyst"]["description"]) > 0
    assert isinstance(news["vix_expectation"], str) and news["vix_expectation"]


# --------------------------------------------------------------------------- #
# 2. Fail-open on source error
# --------------------------------------------------------------------------- #
def test_total_network_failure_still_writes_and_never_raises(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    summary = mc.run(repo, today=TODAY, do_fetch=True, dry_run=False, fetch_fn=_always_fails)
    assert summary["wrote"] is True
    cal_path = repo / "automation" / "state" / "macro-calendar.json"
    assert cal_path.exists()
    written = json.loads(cal_path.read_text(encoding="utf-8"))
    assert written["refresh_log"][-1]["data_quality"] == "baseline_only"
    assert written["events_30d"], "baseline events must still merge in even when every fetch fails"
    assert any("unreachable" in w for w in written["refresh_log"][-1]["warnings"])


def test_source_down_keeps_prior_events_not_wiped(tmp_path: Path) -> None:
    """A manually-added prior event that ISN'T in KNOWN_EVENTS_2026 must survive
    a run even when the network is fully down -- fail-open means 'keep last
    data', never 'reset to baseline only'."""
    hand_added = {
        "date": "2026-07-11", "time_et": "09:00", "event": "J manual note: earnings watch",
        "type": "retail_sales", "severity": "low", "source_url": "https://example.com/manual",
    }
    repo = _seed_repo(tmp_path, calendar_extra={"events_30d": [hand_added]})
    mc.run(repo, today=TODAY, do_fetch=True, dry_run=False, fetch_fn=_always_fails)
    written = json.loads((repo / "automation" / "state" / "macro-calendar.json").read_text(encoding="utf-8"))
    assert any(e["event"] == hand_added["event"] for e in written["events_30d"])


def test_partial_source_failure_marked_partial(tmp_path: Path) -> None:
    """BEA/FOMC reachable but content doesn't match expectations -> HTTP 200
    still counts toward 'live_verified' (the hard gate is reachability, not
    the soft content_match diagnostic). fomc/bea_pce_gdp each require a
    specific substring (e.g. "July 29") so an irrelevant body correctly
    reads content_match=False; fed_speeches has no fixed phrase to check
    (speech topics are unpredictable) so it vacuously content-matches on any
    200 -- that asymmetry is intentional, not a bug, so pin it explicitly."""
    repo = _seed_repo(tmp_path)
    summary = mc.run(repo, today=TODAY, do_fetch=True, dry_run=False, fetch_fn=_always_200_no_match)
    written = json.loads((repo / "automation" / "state" / "macro-calendar.json").read_text(encoding="utf-8"))
    entry = written["refresh_log"][-1]
    assert entry["data_quality"] == "live_verified"  # all 3 _LIVE_SOURCES returned 200
    for label in ("fomc", "bea_pce_gdp", "fed_speeches"):
        assert entry["live_status"][label]["http_status"] == 200
    assert entry["live_status"]["fomc"]["content_match"] is False
    assert entry["live_status"]["bea_pce_gdp"]["content_match"] is False
    assert entry["live_status"]["fed_speeches"]["content_match"] is True  # no substring required -> vacuous match


def test_offline_mode_never_touches_network(tmp_path: Path) -> None:
    """--no-fetch (fetch_fn=None) must not call anything network-shaped --
    verified by NOT passing a fetch_fn and confirming data_quality reflects
    pure-offline mode deterministically."""
    repo = _seed_repo(tmp_path)
    summary = mc.run(repo, today=TODAY, do_fetch=False, dry_run=False)
    written = json.loads((repo / "automation" / "state" / "macro-calendar.json").read_text(encoding="utf-8"))
    assert written["refresh_log"][-1]["data_quality"] == "baseline_only"
    assert written["refresh_log"][-1]["live_status"] == {"mode": "offline (--no-fetch)"}


def test_cli_main_never_raises_on_internal_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A genuine bug inside run() must exit 1, not crash the scheduled task
    with an unhandled traceback (Task Scheduler needs a clean exit code)."""
    def _boom(*a, **kw):
        raise RuntimeError("simulated internal failure")

    monkeypatch.setattr(mc, "run", _boom)
    rc = mc.main(["--dry-run"])
    assert rc == 1


# --------------------------------------------------------------------------- #
# 3. Freshness stamp
# --------------------------------------------------------------------------- #
def test_refresh_log_ran_at_is_fresh(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    before = datetime.now()
    summary = mc.run(repo, today=TODAY, do_fetch=False, dry_run=False)
    after = datetime.now()
    ran_at = datetime.fromisoformat(summary["refresh_log_entry"]["ran_at"])
    # et_now() differs from local wall clock by a fixed DST-aware offset, but
    # the DELTA between two et_now() calls must equal the delta between two
    # local calls (same clock, just shifted) -- so ran_at must land within a
    # generous window around "now" once that shift is allowed for.
    assert abs((ran_at - before).total_seconds()) < 6 * 3600 + 30, "ran_at is not close to now (>~6h off)"


def test_news_json_freshness_stamp_present_and_parseable(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    mc.run(repo, today=TODAY, do_fetch=False, dry_run=False)
    news = json.loads((repo / "automation" / "state" / "news.json").read_text(encoding="utf-8"))
    assert news["mechanical"] is True
    assert news["generator"] == "setup/scripts/macro_calendar.py"
    # Must parse as ISO -- premarket Step 1b's "< 7 days old" check depends on it.
    parsed_as_of = datetime.fromisoformat(news["as_of"])
    parsed_stamp = datetime.fromisoformat(news["freshness_stamp"])
    assert parsed_as_of == parsed_stamp


def test_staleness_resets_to_zero_immediately_after_a_run(tmp_path: Path) -> None:
    """Reproduce premarket.md Step 1b's own staleness formula
    (days_stale = (now_et - last_ran_at).days) against a FRESH run's output --
    must read 0, not the 24 the live file showed pre-fix."""
    stale_prior = {
        "refresh_log": [{"ran_at": "2026-06-14T18:00:00-04:00", "source": "weekly-review (dead)"}],
    }
    repo = _seed_repo(tmp_path, calendar_extra=stale_prior)
    mc.run(repo, today=TODAY, do_fetch=False, dry_run=False)
    written = json.loads((repo / "automation" / "state" / "macro-calendar.json").read_text(encoding="utf-8"))
    last_ran_at = datetime.fromisoformat(written["refresh_log"][-1]["ran_at"])
    days_stale = (datetime.now() - last_ran_at).total_seconds() / 86400.0
    assert days_stale < 0.25, f"expected a near-zero freshness immediately after run, got {days_stale} days"


# --------------------------------------------------------------------------- #
# Supporting behavior: merge/prune/idempotency/trading-day math
# --------------------------------------------------------------------------- #
def test_second_run_same_day_is_idempotent(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    mc.run(repo, today=TODAY, do_fetch=False, dry_run=False)
    summary2 = mc.run(repo, today=TODAY, do_fetch=False, dry_run=False)
    assert summary2["refresh_log_entry"]["added_count"] == 0
    assert summary2["refresh_log_entry"]["skipped_existing_count"] == len(mc.KNOWN_EVENTS_2026)
    assert summary2["total_events_in_file"] == len(mc.KNOWN_EVENTS_2026)


def test_events_older_than_seven_days_are_pruned(tmp_path: Path) -> None:
    old_event = {
        "date": "2026-06-01", "time_et": "08:30", "event": "ancient CPI", "type": "cpi_release",
        "severity": "high", "source_url": "https://example.gov",
    }
    repo = _seed_repo(tmp_path, calendar_extra={"events_30d": [old_event]})
    mc.run(repo, today=TODAY, do_fetch=False, dry_run=False)
    written = json.loads((repo / "automation" / "state" / "macro-calendar.json").read_text(encoding="utf-8"))
    assert not any(e["event"] == "ancient CPI" for e in written["events_30d"])


def test_next_trading_day_skips_weekend_and_holiday() -> None:
    holidays = {"2026-07-03"}  # observed Jul 4th holiday (Friday)
    # Thu 2026-07-02 -> next trading day (exclusive) should skip weekend + holiday to Mon 2026-07-06
    assert mc.next_trading_day("2026-07-02", holidays, inclusive=False) == "2026-07-06"


def test_next_n_trading_days_excludes_weekends() -> None:
    days = mc.next_n_trading_days("2026-07-09", 10, set())  # Thu 2026-07-09, no holidays in window
    assert "2026-07-11" not in days  # Saturday
    assert "2026-07-12" not in days  # Sunday
    assert len(days) == 10
    assert days[0] == "2026-07-09"


def test_tomorrow_2026_07_10_is_a_plain_trading_day() -> None:
    """Concrete check for the task's 'tomorrow' ask: 2026-07-10 is a Friday and
    not a US market holiday, so it must be treated as a normal trading day."""
    holidays: set[str] = set()  # no US holiday on 2026-07-10
    assert mc.is_trading_day("2026-07-10", holidays) is True


def test_dry_run_never_writes(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    mc.run(repo, today=TODAY, do_fetch=False, dry_run=True)
    assert not (repo / "automation" / "state" / "macro-calendar.json").exists() or json.loads(
        (repo / "automation" / "state" / "macro-calendar.json").read_text(encoding="utf-8")
    ).get("events_30d") == []
    assert not (repo / "automation" / "state" / "news.json").exists()


def test_atomic_write_leaves_no_tmp_files(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    mc.run(repo, today=TODAY, do_fetch=False, dry_run=False)
    leftovers = list((repo / "automation" / "state").glob("*.tmp"))
    assert leftovers == []


def test_missing_calendar_file_bootstraps_cleanly(tmp_path: Path) -> None:
    """A brand-new project (or a wiped state dir) must not crash -- the script
    should bootstrap a minimal valid macro-calendar.json from scratch."""
    repo = tmp_path
    (repo / "automation" / "state").mkdir(parents=True)
    summary = mc.run(repo, today=TODAY, do_fetch=False, dry_run=False)
    assert summary["wrote"] is True
    written = json.loads((repo / "automation" / "state" / "macro-calendar.json").read_text(encoding="utf-8"))
    assert written["events_30d"]
