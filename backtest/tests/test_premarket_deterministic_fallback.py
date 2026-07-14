"""Guards for setup/scripts/premarket_deterministic_fallback.py -- the A5 premarket
LLM-step safety net (analysis/deep-research/2026-07-14-premarket-reliability.md).

These tests operate ENTIRELY on injected fake data / tmp_path-redirected module
globals -- NEVER the real automation/state/*.json (those are live production files
this script also writes on schedule; a bad test must not be able to touch them, and
none of the network paths (Alpaca REST, yfinance) are exercised here -- fully offline
and deterministic, per this repo's own $0/no-network testing convention).

Three properties this file guards (mirrors test_macro_calendar_producer.py's
structure):
  1. STALE-DATE DETECTION: the fallback's `date` field is ALWAYS derived from the
     live ET clock (now_et), never from stale input data -- the exact class of bug
     (06-30 hand-rebuild carrying a stale date past the gate) the whole A5 spec
     exists to never repeat.
  2. DEGRADED MARKER discipline: every successful build() carries
     degraded=true/source="deterministic_fallback"/updated_by that does NOT match
     the OP-33 gate's banned-hand-rebuild-author list, and falsifiable_predictions
     is ALWAYS empty (the fallback never fabricates a qualitative call).
  3. FAIL-SAFE: with no primary input (SPY bars) available from any source, the
     fallback refuses to write a fabricated bias at all (ok=False, file untouched).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import premarket_deterministic_fallback as pf  # noqa: E402

TODAY = "2026-07-14"
PRIOR = "2026-07-13"


def _bar(date: str, time_et: str, o: float, h: float, l: float, c: float) -> dict:
    return {"date": date, "time_et": time_et, "open": o, "high": h, "low": l, "close": c}


def _bars_for(*, prior_close: float, premarket_close: float, overnight_high: float,
              overnight_low: float, today_str: str = TODAY, prior_date: str = PRIOR) -> list[dict]:
    """A minimal-but-structurally-real bar series: one prior-session RTH bar (its close
    IS prior_close) plus a couple of today premarket bars spanning the given range,
    ending at premarket_close."""
    return [
        _bar(prior_date, "15:55", prior_close - 0.10, prior_close + 0.05, prior_close - 0.15, prior_close),
        _bar(today_str, "08:00", prior_close, overnight_high, overnight_low, overnight_low),
        _bar(today_str, "09:15", overnight_low, overnight_high, overnight_low, premarket_close),
    ]


def _fake_bars_fn(bars: list[dict], source: str = "test_bars"):
    return lambda: (bars, source)


def _fake_vix_fn(vix_now, vix_prior=None):
    return lambda: (vix_now, vix_prior if vix_prior is not None else vix_now, "test_vix")


def _fake_equity_fn(value):
    return lambda account: value


# --------------------------------------------------------------------------------- #
# 1. Bias formula
# --------------------------------------------------------------------------------- #
class TestBiasFormula:
    def test_bullish_when_both_signals_agree_up(self):
        bars = _bars_for(prior_close=100.0, premarket_close=101.0, overnight_high=101.5, overnight_low=99.5)
        r = pf.compute_bias(bars, TODAY)
        assert r["bias"] == "bullish"
        assert r["pct_change"] > 0
        assert r["overnight_position"] > 0.5

    def test_bearish_when_both_signals_agree_down(self):
        bars = _bars_for(prior_close=100.0, premarket_close=99.0, overnight_high=100.5, overnight_low=98.5)
        r = pf.compute_bias(bars, TODAY)
        assert r["bias"] == "bearish"
        assert r["pct_change"] < 0
        assert r["overnight_position"] < 0.5

    def test_neutral_on_signal_disagreement(self):
        # price UP vs prior close, but sitting in the LOWER half of the overnight range
        bars = _bars_for(prior_close=100.0, premarket_close=100.5, overnight_high=103.0, overnight_low=100.0)
        r = pf.compute_bias(bars, TODAY)
        assert r["bias"] == "neutral"

    def test_neutral_inside_deadband(self):
        # 1 cent move on a $100 base is far inside the 5bps deadband
        bars = _bars_for(prior_close=100.0, premarket_close=100.01, overnight_high=100.5, overnight_low=99.5)
        r = pf.compute_bias(bars, TODAY)
        assert r["bias"] == "neutral"

    def test_no_prior_session_bars_yields_neutral_no_data(self):
        bars = [_bar(TODAY, "08:00", 100.0, 100.5, 99.5, 100.2)]  # today-only, no prior session at all
        r = pf.compute_bias(bars, TODAY)
        assert r["bias"] == "neutral_no_data"
        assert r["reason"] == "no_prior_session_bars_available"
        assert r["pct_change"] is None


# --------------------------------------------------------------------------------- #
# 2. VIX context (against injected params, never the real live params.json)
# --------------------------------------------------------------------------------- #
class TestVixContext:
    PARAMS = {
        "vix_iv_regime_bands": {"low": {"max_exclusive": 15}, "mid": {"min_inclusive": 15, "max_inclusive": 22},
                                 "high": {"min_exclusive": 22}},
        "vix_entry_thresholds": {"bull_max_exclusive_or_falling": 17.2, "bear_min_exclusive_and_rising": 17.3,
                                  "bull_hard_cap": 22.0},
    }

    def test_low_regime(self):
        r = pf.compute_vix_context(12.0, self.PARAMS)
        assert r["iv_regime"] == "LOW"

    def test_high_regime(self):
        r = pf.compute_vix_context(25.0, self.PARAMS)
        assert r["iv_regime"] == "HIGH"

    def test_mid_below_bear_threshold(self):
        r = pf.compute_vix_context(16.8, self.PARAMS)
        assert r["iv_regime"] == "MID"
        assert "below_bear_threshold" in r["vix_bias"]

    def test_mid_above_bull_threshold(self):
        r = pf.compute_vix_context(18.0, self.PARAMS)
        assert "above_bull_threshold" in r["vix_bias"]

    def test_vix_fetch_failure_is_explicit_unknown_not_a_guess(self):
        r = pf.compute_vix_context(None, self.PARAMS)
        assert r["vix_bias"] == "UNKNOWN_vix_fetch_failed"
        assert r["vix_at_open"] is None


# --------------------------------------------------------------------------------- #
# 3. rule_version_pin (reads premarket.md's constant -- single source, never hardcoded)
# --------------------------------------------------------------------------------- #
class TestRuleVersionPin:
    def test_match(self, tmp_path, monkeypatch):
        prompt = tmp_path / "premarket.md"
        prompt.write_text('Some text\nRULE_VERSION_EXPECTED = "v99.9"\nmore text\n', encoding="utf-8")
        monkeypatch.setattr(pf, "PREMARKET_PROMPT", prompt)
        r = pf.compute_rule_version_pin({"rule_version": "v99.9"})
        assert r == {"expected": "v99.9", "actual": "v99.9", "match": True}

    def test_mismatch(self, tmp_path, monkeypatch):
        prompt = tmp_path / "premarket.md"
        prompt.write_text('RULE_VERSION_EXPECTED = "v99.9"\n', encoding="utf-8")
        monkeypatch.setattr(pf, "PREMARKET_PROMPT", prompt)
        r = pf.compute_rule_version_pin({"rule_version": "v14.0"})
        assert r["match"] is False

    def test_missing_prompt_file_fails_open(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pf, "PREMARKET_PROMPT", tmp_path / "does_not_exist.md")
        r = pf.compute_rule_version_pin({"rule_version": "v14.0"})
        assert r["expected"] is None
        assert r["match"] is False


# --------------------------------------------------------------------------------- #
# 4. key_levels: prefer fresh key-levels.json, fall back to prior-day H/L from bars
# --------------------------------------------------------------------------------- #
class TestKeyLevels:
    def test_prefers_fresh_key_levels_json(self, tmp_path, monkeypatch):
        kl = tmp_path / "key-levels.json"
        kl.write_text(json.dumps({
            "as_of": f"{TODAY}T09:00:00-04:00",
            "levels": [
                {"price": 101.0, "role": "resistance", "expires_at": f"{TODAY}T16:00:00-04:00"},
                {"price": 99.0, "role": "support", "expires_at": f"{TODAY}T16:00:00-04:00"},
                {"price": 50.0, "role": "support", "expires_at": f"{TODAY}T16:00:00-04:00"},  # too far from spot
                {"price": 100.5, "role": "resistance", "expires_at": "2026-06-01T16:00:00-04:00"},  # expired
            ],
        }), encoding="utf-8")
        monkeypatch.setattr(pf, "KEY_LEVELS", kl)
        bars = _bars_for(prior_close=100.0, premarket_close=100.2, overnight_high=100.5, overnight_low=99.5)
        levels, source = pf.compute_key_levels(bars, TODAY)
        assert source == "key_levels_json_fresh_today"
        assert 101.0 in levels["resistance"]
        assert 99.0 in levels["support"]
        assert 50.0 not in levels["support"]  # out-of-band excluded
        assert levels["ema_read_failed"] is True

    def test_falls_back_to_prior_day_hl_when_stale(self, tmp_path, monkeypatch):
        kl = tmp_path / "key-levels.json"
        kl.write_text(json.dumps({"as_of": "2026-06-01T09:00:00-04:00", "levels": []}), encoding="utf-8")
        monkeypatch.setattr(pf, "KEY_LEVELS", kl)
        bars = _bars_for(prior_close=100.0, premarket_close=100.2, overnight_high=100.5, overnight_low=99.5)
        levels, source = pf.compute_key_levels(bars, TODAY)
        assert source == "prior_day_hl_from_bars"
        assert levels["resistance"] and levels["support"]

    def test_no_data_at_all_never_crashes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pf, "KEY_LEVELS", tmp_path / "missing.json")
        levels, source = pf.compute_key_levels([], TODAY)
        assert source == "no_data"
        assert levels["resistance"] == [] and levels["support"] == []


# --------------------------------------------------------------------------------- #
# 5. build()/run() -- the full assembly, degraded markers, stale-date detection, fail-safe
# --------------------------------------------------------------------------------- #
class TestBuildAndRun:
    def _valid_bars(self):
        return _bars_for(prior_close=749.13, premarket_close=751.9, overnight_high=752.5, overnight_low=748.5)

    def test_date_is_always_from_the_live_clock_not_input_data(self):
        """STALE-DATE DETECTION guard: the output `date` must equal the injected
        now_et's date, REGARDLESS of what dates appear in the bars or any stale
        carried-forward state -- this is the exact 06-30 class of bug (a write that
        LOOKS fresh-dated without actually being produced this run) the deliverable
        gate exists to catch, and the fallback must never reproduce it."""
        import datetime as dt
        as_of = dt.datetime(2026, 8, 3, 8, 45, 0)  # deliberately far from any bar date below
        bars = _bars_for(prior_close=100.0, premarket_close=100.5, overnight_high=101.0, overnight_low=99.5,
                          today_str="2019-01-01", prior_date="2018-12-31")  # ancient bar dates
        result = pf.build(now_et=as_of, fetch_bars=_fake_bars_fn(bars), fetch_vix_fn=_fake_vix_fn(16.0),
                          fetch_equity_fn=_fake_equity_fn(1000.0))
        assert result["ok"] is True
        assert result["date"] == "2026-08-03"  # from now_et, NOT from the 2019 bar dates

    def test_degraded_markers_and_non_hand_rebuild_author(self):
        result = pf.build(fetch_bars=_fake_bars_fn(self._valid_bars()), fetch_vix_fn=_fake_vix_fn(16.8),
                          fetch_equity_fn=_fake_equity_fn(1746.63))
        assert result["ok"] is True
        assert result["degraded"] is True
        assert result["source"] == "deterministic_fallback"
        updated_by_lc = str(result["updated_by"]).lower()
        for banned in ("interactive", "rebuilt", "by hand", "by_hand"):
            assert banned not in updated_by_lc, f"updated_by must never match the OP-33 banned-author list ({banned})"

    def test_falsifiable_predictions_always_empty(self):
        result = pf.build(fetch_bars=_fake_bars_fn(self._valid_bars()), fetch_vix_fn=_fake_vix_fn(16.8),
                          fetch_equity_fn=_fake_equity_fn(1746.63))
        assert result["falsifiable_predictions"] == []
        assert result["falsifiable_hypothesis"] is None

    def test_no_bars_from_any_source_refuses_to_fabricate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pf, "TODAY_BIAS", tmp_path / "today-bias.json")
        result = pf.run(fetch_bars=_fake_bars_fn([], "test_all_sources_failed"),
                        fetch_vix_fn=_fake_vix_fn(16.0), fetch_equity_fn=_fake_equity_fn(1000.0))
        assert result["ok"] is False
        assert not (tmp_path / "today-bias.json").exists(), "must NOT write a file when it has no primary input"

    def test_writes_atomic_file_with_full_schema_on_success(self, tmp_path, monkeypatch):
        target = tmp_path / "today-bias.json"
        monkeypatch.setattr(pf, "TODAY_BIAS", target)
        result = pf.run(fetch_bars=_fake_bars_fn(self._valid_bars()), fetch_vix_fn=_fake_vix_fn(16.8),
                        fetch_equity_fn=_fake_equity_fn(1746.63))
        assert result["ok"] is True
        assert target.exists()
        written = json.loads(target.read_text(encoding="utf-8"))
        assert "ok" not in written  # internal-only flag, never persisted
        for field in ("date", "bias", "bias_note", "key_levels", "falsifiable_predictions",
                      "vix_at_open", "vix_bias", "session_window", "news_calendar",
                      "readiness_flags", "updated_at", "degraded", "source"):
            assert field in written, f"missing field {field} in written today-bias.json"

    def test_dry_run_never_writes(self, tmp_path, monkeypatch):
        target = tmp_path / "today-bias.json"
        monkeypatch.setattr(pf, "TODAY_BIAS", target)
        pf.run(dry_run=True, fetch_bars=_fake_bars_fn(self._valid_bars()), fetch_vix_fn=_fake_vix_fn(16.8),
              fetch_equity_fn=_fake_equity_fn(1746.63))
        assert not target.exists()

    def test_vix_failure_does_not_block_the_whole_write(self):
        """A secondary input (VIX) failing must degrade gracefully, not veto the
        entire fallback -- only the PRIMARY input (bars) is a hard blocker."""
        result = pf.build(fetch_bars=_fake_bars_fn(self._valid_bars()), fetch_vix_fn=_fake_vix_fn(None),
                          fetch_equity_fn=_fake_equity_fn(1746.63))
        assert result["ok"] is True
        assert result["vix_bias"] == "UNKNOWN_vix_fetch_failed"
        assert any("VIX read failed" in f for f in result["readiness_flags"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
