"""Guard for PRIOR-DAY-HLC-LEVELS (queue item filed 2026-08-03 from the LANE-4 violin
finding): `LEVEL_WEIGHT_PRIOR_DAY_HLC` (weight 3) existed in refresh_levels_intraday.py
since this file's early history but had ZERO producer — no code ever wrote
PRIOR_DAY_HIGH/LOW/CLOSE into key-levels.json (C14 dead-knob class). The violin metric
measured prior_day_close RESPECTED 15x on the 07-28/07-29 tape with 0% engine coverage;
the only file entry was a hand-inserted `PRIOR_CLOSE_2026-06-23`/`PRIOR_CLOSE_2026-06-26`
one-off, stale for weeks and never refreshed by any producer.

Fix: refresh() now computes PRIOR_DAY_HIGH/LOW/CLOSE from the previous trading day's RTH
subset in the same 7-day fetch window already used for everything else, gated by the SAME
degeneracy guard (_degeneracy_reason) and wired through the SAME idempotent strip-and-
recompute + dedup + hysteresis path as the INTRADAY_* family, at weight=3 (not the default
intraday weight=2) per this file's own weight-scale doctrine.

$0, pure-Python, no network (df is injected via the refresh(df=) seam) — same pattern as
test_refresh_levels_intraday.py.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "refresh_levels_intraday.py"

_spec = importlib.util.spec_from_file_location("refresh_levels_intraday", MOD_PATH)
rli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rli)


def _today() -> str:
    return rli.et_now().strftime("%Y-%m-%d")


def _yesterday() -> str:
    return (rli.et_now() - timedelta(days=1)).strftime("%Y-%m-%d")


def _rows(date: str, bars):
    return [{"date": date, "hm": hm, "high": hi, "low": lo, "close": cl, "volume": vol}
            for hm, hi, lo, cl, vol in bars]


# Realistic 5m SPY volumes (clears DEGENERACY_MIN_BARS=3 / DEGENERACY_MIN_VOLUME=10,000).
_PRIOR_RTH = [
    ("09:35", 733.0, 731.0, 732.5, 100_000),
    ("09:45", 734.5, 732.0, 733.0, 200_000),   # <- prior-day RTH high 734.5
    ("15:00", 732.5, 728.0, 730.0, 250_000),   # <- prior-day RTH low 728.0
    ("15:55", 731.0, 730.0, 730.75, 150_000),  # <- prior-day RTH close 730.75
]
_TODAY_RTH = [
    ("09:35", 738.0, 736.0, 737.5, 100_000),
    ("09:45", 739.9, 738.0, 738.5, 200_000),
    ("10:05", 737.5, 735.5, 736.0, 250_000),   # <- last close == spot 736.0
]
# Thin prior day: 1 bar, well under DEGENERACY_MIN_BARS -- must be REFUSED, not written.
_PRIOR_THIN = [("09:35", 733.0, 731.0, 732.5, 5_000)]


def _df_with_prior(prior_bars=_PRIOR_RTH, today_bars=_TODAY_RTH):
    rows = _rows(_yesterday(), prior_bars) + _rows(_today(), today_bars)
    return pd.DataFrame(rows)


@pytest.fixture
def _state(tmp_path, monkeypatch):
    kl = tmp_path / "key-levels.json"
    bias = tmp_path / "today-bias.json"
    bias.write_text(json.dumps({"key_levels": {}}), encoding="utf-8")
    monkeypatch.setattr(rli, "KEY_LEVELS", kl)
    monkeypatch.setattr(rli, "TODAY_BIAS", bias)
    # Same isolation fix as test_refresh_levels_intraday.py's _state fixture: a synthetic
    # fixture's PASS/FAIL must not depend on today's real live SPY shelf zones.
    monkeypatch.setattr(rli, "daily_context", None)
    return kl, bias


def _levels_by_family(kl_path, prefix):
    data = json.loads(kl_path.read_text(encoding="utf-8"))
    return [lv for lv in data["levels"] if str(lv.get("label", "")).startswith(prefix)]


# --- THE load-bearing regression guard ------------------------------------------------

def test_prior_day_hlc_written_with_correct_prices_and_roles(_state):
    """The fix: PRIOR_DAY_HIGH/LOW/CLOSE land in key-levels.json from the D-1 RTH subset,
    with structural (not price-relative) roles for high/low."""
    kl, _ = _state
    out = rli.refresh(df=_df_with_prior())
    assert out["ok"] is True
    data = json.loads(kl.read_text(encoding="utf-8"))
    by_label = {lv["label"].split("_2026")[0]: lv for lv in data["levels"]}
    assert "PRIOR_DAY_HIGH" in by_label and "PRIOR_DAY_LOW" in by_label and "PRIOR_DAY_CLOSE" in by_label
    assert by_label["PRIOR_DAY_HIGH"]["price"] == 734.5
    assert by_label["PRIOR_DAY_HIGH"]["role"] == "resistance"
    assert by_label["PRIOR_DAY_LOW"]["price"] == 728.0
    assert by_label["PRIOR_DAY_LOW"]["role"] == "support"
    assert by_label["PRIOR_DAY_CLOSE"]["price"] == 730.75


def test_prior_day_hlc_weight_is_3_not_default_intraday_2(_state):
    """The whole point of the fix: weight=LEVEL_WEIGHT_PRIOR_DAY_HLC (3), a stronger
    structural reference than same-day computed levels (weight=2) — never silently
    downgraded to the INTRADAY default."""
    kl, _ = _state
    rli.refresh(df=_df_with_prior())
    assert rli.LEVEL_WEIGHT_PRIOR_DAY_HLC == 3
    prior = _levels_by_family(kl, "PRIOR_DAY_")
    assert len(prior) == 3
    assert all(lv["weight"] == 3 for lv in prior)
    intraday = _levels_by_family(kl, "INTRADAY_RTH_")
    assert all(lv["weight"] == 2 for lv in intraday)   # unaffected, still the pre-fix default


def test_prior_day_close_is_non_directional_price_relative(_state):
    """prior_day_close carries no structural high/low semantics (docstring: 'non-directional
    refs ... keep what they had') -- role falls through to the price-vs-spot fallback, same
    as every other unclassified source, NOT hard-coded resistance/support."""
    kl, _ = _state
    # spot (last today close) = 736.0; prior close 730.75 < spot -> support via fallback.
    rli.refresh(df=_df_with_prior())
    data = json.loads(kl.read_text(encoding="utf-8"))
    close_lv = next(lv for lv in data["levels"] if lv["label"].startswith("PRIOR_DAY_CLOSE"))
    assert close_lv["role"] == "support"
    assert "prior_day_close" not in rli.SEMANTIC_SOURCE_ROLE   # deliberately absent (non-directional)


def test_prior_day_thin_subset_refused_not_written(_state):
    """Same degeneracy guard as every other family (2027-07-27 doctrine): a 1-bar, thin-volume
    prior day is REFUSED, not silently written as a garbage level."""
    kl, _ = _state
    out = rli.refresh(df=_df_with_prior(prior_bars=_PRIOR_THIN))
    assert out["ok"] is True
    prior = _levels_by_family(kl, "PRIOR_DAY_")
    assert prior == []
    reasons = " ".join(r["reason"] for r in out["refused"])
    assert "bar(s)" in reasons or "volume" in reasons   # the degeneracy guard's own wording


def test_no_prior_trading_day_in_window_fails_open(_state):
    """Edge case (e.g. very first run, or a 7-day fetch window with no prior session):
    no crash, an explicit visible refusal, zero PRIOR_DAY_* levels written."""
    kl, _ = _state
    today_only = pd.DataFrame(_rows(_today(), _TODAY_RTH))
    out = rli.refresh(df=today_only)
    assert out["ok"] is True
    prior = _levels_by_family(kl, "PRIOR_DAY_")
    assert prior == []
    assert any("prior trading day" in r["reason"] for r in out["refused"])


def test_idempotent_no_prior_day_duplication(_state):
    """Re-running twice must not pile up duplicate PRIOR_DAY_* entries -- same idempotent
    strip-and-recompute contract as INTRADAY_*."""
    kl, _ = _state
    rli.refresh(df=_df_with_prior())
    rli.refresh(df=_df_with_prior())
    prior = _levels_by_family(kl, "PRIOR_DAY_HIGH")
    assert len(prior) == 1


def test_prior_day_survives_alongside_intraday_family(_state):
    """Additive: PRIOR_DAY_* and INTRADAY_* coexist in the same run, neither displaces the
    other (both idempotently stripped-and-recomputed independently)."""
    kl, _ = _state
    rli.refresh(df=_df_with_prior())
    data = json.loads(kl.read_text(encoding="utf-8"))
    labels = {lv["label"].split("_2026")[0] for lv in data["levels"]}
    assert {"PRIOR_DAY_HIGH", "PRIOR_DAY_LOW", "PRIOR_DAY_CLOSE",
            "INTRADAY_RTH_HIGH", "INTRADAY_RTH_LOW"} <= labels


def test_prior_day_picks_the_most_recent_prior_session_not_oldest(_state):
    """With >1 prior date in the 7-day window, the MOST RECENT prior session wins (not the
    oldest) -- the correct 'yesterday', not some stale earlier day in the fetch window."""
    kl, _ = _state
    older_date = (rli.et_now() - timedelta(days=3)).strftime("%Y-%m-%d")
    rows = (_rows(older_date, [("09:35", 999.0, 990.0, 995.0, 500_000),
                                ("09:45", 998.0, 989.0, 994.0, 500_000),
                                ("09:55", 997.0, 988.0, 993.0, 500_000)])
            + _rows(_yesterday(), _PRIOR_RTH)
            + _rows(_today(), _TODAY_RTH))
    out = rli.refresh(df=pd.DataFrame(rows))
    assert out["ok"] is True
    data = json.loads(kl.read_text(encoding="utf-8"))
    high_lv = next(lv for lv in data["levels"] if lv["label"].startswith("PRIOR_DAY_HIGH"))
    assert high_lv["price"] == 734.5   # yesterday's high, NOT the older-day 999.0 poison value
