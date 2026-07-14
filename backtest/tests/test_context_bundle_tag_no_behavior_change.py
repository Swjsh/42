"""Guard: THE zero-behavior-change proof for the Phase 0 context-bundle TAG
(context-enrichment plan, 2026-07-14).

WHAT THIS PINS: setup/scripts/heartbeat_core.py stamps automation/state/context-bundle.json
onto bar_ctx (`_build_payload`, via `_read_context_bundle`) and onto the decision-row ledger
(`run_account`'s `rec["context_bundle"]`) -- LOGGED ONLY. Nothing on the decision path
(score_bar / evaluate_gates / _derive_tier, all in backtest/lib/engine) may read it this
phase. This file proves that end to end:

  1. REAL WIRING (`_build_payload` + `_engine_verdict`, no mocks): the same core-decisions
     VERDICT is produced whether context-bundle.json is present, absent, or stale on disk --
     using the REAL `_read_context_bundle` staleness/read logic, not a stub.
  2. LEDGER TAG (`run_account`, mocked engine per the test_trigger_level_exact_provenance.py
     `_wire_run_account` pattern): `rec["verdict"]/["action"]/["side"]/["setup"]/scores` are
     byte-identical whether `bar_ctx["context_bundle"]` is present or None, while
     `rec["context_bundle"]` itself correctly differs -- proving the test isn't vacuous (a
     wired-in dependency would show up here first).
  3. RED-PROOF (documented, not left as an assertion in this file): during authorship, the
     tag was temporarily wired to ALSO perturb the verdict (a one-line hack that added the
     bundle's alignment_score into bear_score before returning), test #1 above was re-run and
     it FAILED (verdict/bear_score diverged across present vs absent), then the hack was
     reverted and this file was confirmed green again. That proves the guard actually
     exercises the wiring it claims to -- see PROJECT-GAMMA session notes / STATUS.md dated
     2026-07-14 for the exact revert diff quoted at the time.

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_context_bundle_tag_no_behavior_change.py -q
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
_SCRIPTS = ROOT / "setup" / "scripts"
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(ROOT), str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# heartbeat_core lives in setup/scripts (not a package) -- load it by path, same convention
# every other heartbeat_core test in this directory uses (test_g6_vix_intraday_feed.py,
# test_heartbeat_core_no_trade_window.py).
_MOD = ROOT / "setup" / "scripts" / "heartbeat_core.py"
_spec = importlib.util.spec_from_file_location("heartbeat_core", _MOD)
hc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hc)

SAFE_PARAMS = json.loads((ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8"))

_BUNDLE = {
    "schema_version": 1, "computed_at_et": "PLACEHOLDER",
    "per_tf": {"daily": {"trend": "uptrend", "confidence": 0.8, "available": True},
              "hourly": {"trend": "uptrend", "confidence": 0.8, "available": True},
              "m15": {"trend": "uptrend", "confidence": 0.8, "available": True}},
    "trend_alignment": {"bull": {"aligned": True, "agree_count": 3},
                        "bear": {"aligned": False, "agree_count": 0}},
    "alignment_score": 3, "degraded": False, "degraded_reason": None,
}


# --------------------------------------------------------------------------- #
# Fixture: ~4 days of gentle-uptrend RTH 5m bars (test_g6_vix_intraday_feed.py's
# _synth_rth_bars, reused verbatim -- enough to seed the ribbon + yield a real payload).
# --------------------------------------------------------------------------- #
def _synth_rth_bars() -> pd.DataFrame:
    rows = []
    price = 600.0
    prev = price - 0.06
    for d in range(4):
        day = pd.Timestamp(f"2026-06-0{d + 1} 00:00", tz="America/New_York")
        t = day + pd.Timedelta(hours=9, minutes=30)
        end = day + pd.Timedelta(hours=16)
        while t < end:
            price = round(price + 0.06, 2)
            rows.append({"timestamp": t, "open": prev, "high": max(prev, price) + 0.05,
                         "low": min(prev, price) - 0.05, "close": price, "volume": 1_000_000})
            prev = price
            t = t + pd.Timedelta(minutes=5)
    return pd.DataFrame(rows)


# =============================================================================
# PART 1 -- REAL WIRING: _build_payload + _engine_verdict, no mocks. The three
# on-disk states of context-bundle.json (absent / fresh / stale) must produce
# byte-identical engine verdicts.
# =============================================================================
def test_build_payload_tags_context_bundle_present_absent_stale(monkeypatch, tmp_path):
    monkeypatch.setattr(hc, "STATE", tmp_path)
    df = _synth_rth_bars()

    # -- ABSENT: no context-bundle.json on disk at all --------------------------
    payload_absent = hc._build_payload(df, SAFE_PARAMS, vix=(18.0, 17.9),
                                       levels=([], []), vix_ma=(17.0, 16.5))
    assert payload_absent is not None, "fixture must yield a valid payload"
    assert payload_absent["bar_ctx"]["context_bundle"] is None

    # -- PRESENT: a FRESH bundle (computed_at_et = right now per hc._et_now()) --
    now = hc._et_now()
    fresh = dict(_BUNDLE, computed_at_et=now.strftime("%Y-%m-%dT%H:%M:%S"))
    (tmp_path / "context-bundle.json").write_text(json.dumps(fresh), encoding="utf-8")
    payload_present = hc._build_payload(df, SAFE_PARAMS, vix=(18.0, 17.9),
                                        levels=([], []), vix_ma=(17.0, 16.5))
    assert payload_present["bar_ctx"]["context_bundle"] == fresh, (
        "a present, fresh bundle must be tagged onto bar_ctx verbatim -- proves this test "
        "isn't vacuously comparing None to None")

    # -- STALE: computed_at_et older than CONTEXT_BUNDLE_STALE_MIN -> resolves to None ---
    stale_ts = now - dt.timedelta(minutes=hc.CONTEXT_BUNDLE_STALE_MIN + 5)
    stale = dict(_BUNDLE, computed_at_et=stale_ts.strftime("%Y-%m-%dT%H:%M:%S"))
    (tmp_path / "context-bundle.json").write_text(json.dumps(stale), encoding="utf-8")
    payload_stale = hc._build_payload(df, SAFE_PARAMS, vix=(18.0, 17.9),
                                      levels=([], []), vix_ma=(17.0, 16.5))
    assert payload_stale["bar_ctx"]["context_bundle"] is None, (
        "a bundle older than CONTEXT_BUNDLE_STALE_MIN must be treated as absent")

    # -- THE ZERO-BEHAVIOR-CHANGE PROOF: the REAL engine verdict is unaffected -----------
    verdict_absent = hc._engine_verdict(payload_absent)
    verdict_present = hc._engine_verdict(payload_present)
    verdict_stale = hc._engine_verdict(payload_stale)
    assert verdict_absent == verdict_present == verdict_stale, (
        "context_bundle presence/absence/staleness must NEVER change the engine verdict "
        f"(purity rule -- decide_payload never reads this key):\n"
        f"absent={verdict_absent}\npresent={verdict_present}\nstale={verdict_stale}")


def test_stale_bundle_uses_the_documented_threshold_boundary(monkeypatch, tmp_path):
    """CONTEXT_BUNDLE_STALE_MIN is the exact boundary -- just inside is present, just
    outside is absent (pins the constant against silent drift)."""
    monkeypatch.setattr(hc, "STATE", tmp_path)
    now = hc._et_now()

    just_fresh = now - dt.timedelta(minutes=hc.CONTEXT_BUNDLE_STALE_MIN - 1)
    (tmp_path / "context-bundle.json").write_text(
        json.dumps(dict(_BUNDLE, computed_at_et=just_fresh.strftime("%Y-%m-%dT%H:%M:%S"))),
        encoding="utf-8")
    assert hc._read_context_bundle() is not None

    just_stale = now - dt.timedelta(minutes=hc.CONTEXT_BUNDLE_STALE_MIN + 1)
    (tmp_path / "context-bundle.json").write_text(
        json.dumps(dict(_BUNDLE, computed_at_et=just_stale.strftime("%Y-%m-%dT%H:%M:%S"))),
        encoding="utf-8")
    assert hc._read_context_bundle() is None


def test_read_context_bundle_fail_open_on_missing_and_malformed(monkeypatch, tmp_path):
    monkeypatch.setattr(hc, "STATE", tmp_path)
    assert hc._read_context_bundle() is None  # missing file

    (tmp_path / "context-bundle.json").write_text("{not valid json", encoding="utf-8")
    assert hc._read_context_bundle() is None  # malformed JSON

    (tmp_path / "context-bundle.json").write_text(json.dumps({"no_computed_at": True}), encoding="utf-8")
    assert hc._read_context_bundle() is None  # missing computed_at_et

    (tmp_path / "context-bundle.json").write_text(
        json.dumps({"computed_at_et": "not-a-timestamp"}), encoding="utf-8")
    assert hc._read_context_bundle() is None  # unparseable timestamp


# =============================================================================
# PART 2 -- LEDGER TAG: run_account's rec["context_bundle"], engine mocked
# (mirrors test_trigger_level_exact_provenance.py::_wire_run_account exactly).
# =============================================================================
def _wire_run_account(monkeypatch, now, verdict, *, context_bundle=None):
    payload = {"bar_ctx": {
        "timestamp_et": now.strftime("%Y-%m-%d %H:%M:%S"),
        "bar": {"close": 620.0},
        "ribbon_now": {"stack": "BEAR", "spread_cents": 45.0},
        "vix_now": 17.2, "vix_prior": 17.3, "htf_15m_stack": "BEAR",
        "levels_active": [],
        "context_bundle": context_bundle,
    }}
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "_fetch_spy_5m", lambda: None)
    monkeypatch.setattr(hc, "_build_payload", lambda df, p, **k: payload)
    monkeypatch.setattr(hc, "_engine_verdict", lambda p: dict(verdict))
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", False)
    monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
    monkeypatch.setattr(hc, "_execute", lambda *a, **k: {"status": "WOULD_PLACE"})
    monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
    logged: list = []
    monkeypatch.setattr(hc, "_log", lambda rec: logged.append(rec))
    monkeypatch.setitem(sys.modules, "setup_dispatch",
                        types.SimpleNamespace(dispatch_extra_setups=lambda *a, **k: []))
    return logged


_ENTER_VERDICT = {"verdict": "ENTER_BEAR", "side": "P", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                  "bear_score": 9, "bull_score": 2, "triggers_fired": ["level_rejection"],
                  "reason": "test", "rejection_level": 622.5}
_HOLD_VERDICT = {"verdict": "HOLD", "side": None, "setup_name": None,
                 "bear_score": 3, "bull_score": 1, "triggers_fired": [], "reason": "no setup"}

_BEHAVIOR_KEYS = ("verdict", "side", "setup", "bear_score", "bull_score", "triggers",
                  "reason", "trigger_level_exact", "action", "spy", "ribbon", "vix")


@pytest.mark.parametrize("verdict", [_ENTER_VERDICT, _HOLD_VERDICT], ids=["ENTER_BEAR", "HOLD"])
def test_run_account_rec_identical_with_and_without_context_bundle(monkeypatch, verdict):
    now = dt.datetime(2026, 7, 14, 11, 0)

    _wire_run_account(monkeypatch, now, verdict, context_bundle=None)
    rec_absent = hc.run_account("safe")

    fresh_bundle = dict(_BUNDLE, computed_at_et="2026-07-14T10:55:00")
    _wire_run_account(monkeypatch, now, verdict, context_bundle=fresh_bundle)
    rec_present = hc.run_account("safe")

    for key in _BEHAVIOR_KEYS:
        assert rec_absent[key] == rec_present[key], (
            f"{key!r} must be byte-identical regardless of context_bundle presence: "
            f"{rec_absent[key]!r} vs {rec_present[key]!r}")

    # the tag ITSELF must differ -- proves the comparison above is non-vacuous.
    assert rec_absent["context_bundle"] is None
    assert rec_present["context_bundle"] == fresh_bundle


def test_run_account_logs_the_same_context_bundle_it_stamps(monkeypatch):
    """The LOGGED row (core-decisions.jsonl) must carry the identical bundle the returned
    rec carries -- no drift between what's returned and what's persisted."""
    now = dt.datetime(2026, 7, 14, 11, 0)
    bundle = dict(_BUNDLE, computed_at_et="2026-07-14T10:55:00")
    logged = _wire_run_account(monkeypatch, now, _ENTER_VERDICT, context_bundle=bundle)
    rec = hc.run_account("safe")
    assert rec["context_bundle"] == bundle
    assert logged and logged[-1]["context_bundle"] == bundle


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
