"""G6 guard — the intraday VIX feed for the vix_regime_dayside (edge #4) setup.

Pins the PRODUCER/CONSUMER CONTRACT of the G6 wiring (thread an intraday ^VIX 5m series
from heartbeat_core into the vix_regime_dayside watcher, which otherwise hard-returns
``SKIP_NO_FEED:vix_intraday_not_wired`` every tick):

  1. DORMANT no-op (the safety crux): while ``j_vix_dayside_enabled`` is false/absent,
     ``_build_payload`` adds NO ``vix_intraday`` to bar_ctx AND never calls the fetch — so
     the wiring is a byte-identical no-op with zero extra hot-path download. The producer is
     gated on the SAME flag the dispatch consumer is gated on, so they arm together.
  2. ENABLED — INJECTED: an injected ``vix_intraday`` (the replay-determinism seam, parallel
     to vix/levels/vix_ma) threads straight into bar_ctx, no fetch.
  3. ENABLED — LIVE FETCH: with no injection, ``_build_payload`` calls ``_fetch_vix_intraday``
     CAUSALLY CAPPED at the trigger bar timestamp (no look-ahead, C6) and attaches the result.
  4. FAIL-OPEN: a fetch returning None leaves vix_intraday ABSENT (no empty/garbage key) ->
     the watcher SKIPs, never guesses the regime.
  5. HELPER: ``_fetch_vix_intraday`` filters to RTH, applies the causal cap, returns newest-
     last closes, and yields None on an empty/failed download — all WITHOUT network (yfinance
     monkeypatched).
  6. CONSUMER thread: ``SetupDispatcher._build_ctx`` copies bar_ctx['vix_intraday'] onto the
     (frozen) BarContext so the watcher's ``getattr(ctx, 'vix_intraday', None)`` sees it;
     absent -> attribute never set (DORMANT-safe).
  7. END-TO-END contract: with the feed present + the flag on, the dispatch no longer returns
     ``SKIP_NO_FEED:vix_intraday_not_wired`` — the producer and consumer halves are both wired.

These are graduated guards (OP-25): dropping EITHER half of the producer/consumer contract,
or making the producer fetch unconditionally (hot-path cost while dormant), REDs here. Kills
the silent producer/consumer-drift + dead-knob classes (C7/C14) for this feed.

Run:
  cd C:\\Users\\jackw\\Desktop\\42
  backtest\\.venv\\Scripts\\python.exe -m pytest backtest/tests/test_g6_vix_intraday_feed.py -q
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
for _p in (str(BACKTEST), str(BACKTEST / "lib"), str(ROOT / "setup" / "scripts"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# heartbeat_core lives in setup/scripts (not a package) — load it by path.
_MOD = ROOT / "setup" / "scripts" / "heartbeat_core.py"
_spec = importlib.util.spec_from_file_location("heartbeat_core", _MOD)
hc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hc)

from setup_dispatch import SetupDispatcher  # noqa: E402

SAFE_PARAMS = json.loads((ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8"))


def _synth_rth_bars() -> pd.DataFrame:
    """~300 RTH 5m bars on a gentle uptrend (deterministic, no network) — enough to seed the
    48-EMA ribbon and yield a non-UNKNOWN stack so _build_payload returns a payload."""
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


class _Recorder:
    """Records calls to a monkeypatched _fetch_vix_intraday + returns a canned value."""

    def __init__(self, ret):
        self.ret = ret
        self.calls = []

    def __call__(self, cap_ts_et=None):
        self.calls.append(cap_ts_et)
        return self.ret


def _enabled_params() -> dict:
    return dict(SAFE_PARAMS, j_vix_dayside_enabled=True)


# --------------------------------------------------------------------------- #
# 1. DORMANT no-op — flag off => no key, no fetch (the safety crux)
# --------------------------------------------------------------------------- #
def test_dormant_adds_no_key_and_never_fetches(monkeypatch):
    rec = _Recorder(["should", "not", "appear"])
    monkeypatch.setattr(hc, "_fetch_vix_intraday", rec)
    df = _synth_rth_bars()
    # SAFE_PARAMS has j_vix_dayside_enabled=false on disk.
    assert SAFE_PARAMS.get("j_vix_dayside_enabled", False) is False, \
        "premise: params.json must keep vix_dayside dormant (recency-RED) — update this guard"
    payload = hc._build_payload(df, SAFE_PARAMS, vix=(18.0, 17.9),
                                levels=([], []), vix_ma=(17.0, 16.5))
    assert payload is not None
    assert "vix_intraday" not in payload["bar_ctx"], "dormant must not add the key"
    assert rec.calls == [], "dormant must NOT call the fetch (zero hot-path download)"


# --------------------------------------------------------------------------- #
# 2. ENABLED — injected series threads straight in (replay-determinism seam)
# --------------------------------------------------------------------------- #
def test_enabled_injected_series_threads_into_bar_ctx(monkeypatch):
    # If injection works, the live fetch must NOT be reached.
    monkeypatch.setattr(hc, "_fetch_vix_intraday",
                        lambda cap=None: pytest.fail("must not fetch when injected"))
    df = _synth_rth_bars()
    series = [17.0 + i * 0.01 for i in range(120)]
    payload = hc._build_payload(df, _enabled_params(), vix=(18.0, 17.9),
                                levels=([], []), vix_ma=(17.0, 16.5),
                                vix_intraday=series)
    assert payload["bar_ctx"]["vix_intraday"] == series


# --------------------------------------------------------------------------- #
# 3. ENABLED — live fetch, causally capped at the trigger bar
# --------------------------------------------------------------------------- #
def test_enabled_live_fetch_is_capped_at_trigger(monkeypatch):
    rec = _Recorder([16.0, 16.1, 16.2])
    monkeypatch.setattr(hc, "_fetch_vix_intraday", rec)
    df = _synth_rth_bars()
    payload = hc._build_payload(df, _enabled_params(), vix=(18.0, 17.9),
                                levels=([], []), vix_ma=(17.0, 16.5))
    assert payload["bar_ctx"]["vix_intraday"] == [16.0, 16.1, 16.2]
    assert len(rec.calls) == 1, "enabled + no injection => exactly one fetch"
    cap = rec.calls[0]
    assert cap is not None, "the fetch must be causally capped (no look-ahead)"
    # the cap is the trigger bar timestamp == bar_ctx.timestamp_et
    assert str(pd.Timestamp(cap)) == str(pd.Timestamp(payload["bar_ctx"]["timestamp_et"]))


# --------------------------------------------------------------------------- #
# 4. FAIL-OPEN — fetch None => absent key (no empty/garbage), watcher SKIPs
# --------------------------------------------------------------------------- #
def test_enabled_fetch_none_leaves_key_absent(monkeypatch):
    monkeypatch.setattr(hc, "_fetch_vix_intraday", lambda cap=None: None)
    df = _synth_rth_bars()
    payload = hc._build_payload(df, _enabled_params(), vix=(18.0, 17.9),
                                levels=([], []), vix_ma=(17.0, 16.5))
    assert "vix_intraday" not in payload["bar_ctx"]


# --------------------------------------------------------------------------- #
# 5. HELPER — RTH filter + causal cap + newest-last, no network
# --------------------------------------------------------------------------- #
class _FakeYF:
    def __init__(self, df):
        self._df = df

    def download(self, *a, **k):
        return self._df


def _vix_frame(empty=False):
    if empty:
        return pd.DataFrame()
    idx = pd.DatetimeIndex([
        "2026-06-04 08:00", "2026-06-04 09:30", "2026-06-04 09:35",
        "2026-06-04 09:40", "2026-06-04 16:05",
    ], tz="America/New_York")
    return pd.DataFrame({"Close": [99.0, 10.0, 11.0, 12.0, 99.0]}, index=idx)


def test_fetch_vix_intraday_rth_filter_and_causal_cap(monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", _FakeYF(_vix_frame()))
    cap = pd.Timestamp("2026-06-04 09:40", tz="America/New_York")
    out = hc._fetch_vix_intraday(cap)
    # 08:00 (pre) + 16:05 (post) dropped by RTH; 09:40 is the cap; newest LAST.
    assert out == [10.0, 11.0, 12.0]


def test_fetch_vix_intraday_empty_returns_none(monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", _FakeYF(_vix_frame(empty=True)))
    assert hc._fetch_vix_intraday() is None


def test_fetch_vix_intraday_download_raises_returns_none(monkeypatch):
    class _Boom:
        def download(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setitem(sys.modules, "yfinance", _Boom())
    assert hc._fetch_vix_intraday() is None  # fail-open, never raises


# --------------------------------------------------------------------------- #
# 6/7. CONSUMER thread + end-to-end producer/consumer contract (dispatch side)
# --------------------------------------------------------------------------- #
def _ts(h, m, date="2026-01-07"):
    return f"{date}T{h:02d}:{m:02d}:00-04:00"


def _dispatch_payload(with_vix_intraday):
    bars = [
        {"timestamp_iso": _ts(9, 30), "open": 600.0, "high": 600.6, "low": 599.9, "close": 599.5, "volume": 5000},
        {"timestamp_iso": _ts(9, 35), "open": 599.5, "high": 599.6, "low": 598.8, "close": 598.9, "volume": 5000},
        {"timestamp_iso": _ts(9, 40), "open": 598.9, "high": 599.0, "low": 598.2, "close": 598.3, "volume": 5000},
    ]
    bar_ctx = {
        "bar_idx": len(bars) - 1,
        "timestamp_et": bars[-1]["timestamp_iso"],
        "bar": {"open": 598.9, "high": 599.0, "low": 598.2, "close": 598.3, "volume": 5000},
        "prior_bars": [{k: b[k] for k in ("open", "high", "low", "close", "volume")} for b in bars],
        "ribbon_now": {"fast": 598.0, "pivot": 598.5, "slow": 599.0, "spread_cents": 200.0, "stack": "BEAR"},
        "ribbon_history": [], "vix_now": 17.0, "vix_prior": 17.5,
        "vol_baseline_20": 5000.0, "range_baseline_20": 0.5,
        "levels_active": [], "multi_day_levels": [], "htf_15m_stack": "BEAR",
        "level_states": {}, "fhh_level": None, "vix_5d_ma": 0.0, "vix_20d_ma": 0.0,
    }
    if with_vix_intraday is not None:
        bar_ctx["vix_intraday"] = with_vix_intraday
    return {"bar_ctx": bar_ctx, "sameday_5m_bars": bars,
            "spy_df": [{k: b[k] for k in ("open", "high", "low", "close", "volume")} for b in bars],
            "ribbon_df": [], "gate_params": {}, "score_params": {}}


def test_build_ctx_threads_vix_intraday_onto_ctx():
    series = [16.0 + i * 0.01 for i in range(12)]
    disp = SetupDispatcher({"j_vix_dayside_enabled": True}, _dispatch_payload(series))
    ctx = disp._build_ctx()
    assert ctx is not None
    assert list(getattr(ctx, "vix_intraday")) == series


def test_build_ctx_absent_feed_leaves_attr_unset():
    disp = SetupDispatcher({"j_vix_dayside_enabled": True}, _dispatch_payload(None))
    ctx = disp._build_ctx()
    assert ctx is not None
    assert getattr(ctx, "vix_intraday", None) is None  # DORMANT-safe


def test_feed_present_clears_skip_no_feed_vix_not_wired():
    """The regression that G6 closes: with the feed wired (+ flag on) the dispatch no longer
    returns SKIP_NO_FEED:vix_intraday_not_wired (it may SKIP_NO_SIGNAL — that's fine)."""
    params = {"j_vwap_cont_enabled": False, "gap_and_go_enabled": False,
              "j_vwap_reclaim_fb_enabled": False, "j_vix_dayside_enabled": True}
    series = [16.0 + i * 0.01 for i in range(120)]
    results = SetupDispatcher(params, _dispatch_payload(series)).run()
    assert len(results) == 1
    r = results[0]
    assert r.setup_name == "vix_regime_dayside"
    assert r.skip_reason != "SKIP_NO_FEED:vix_intraday_not_wired", (
        f"feed is wired now — must not report it unwired; got {r.skip_reason}"
    )


def test_absent_feed_still_skips_no_feed_when_flag_on():
    """The OTHER half of the contract: with the flag on but NO feed, the dispatch still
    correctly reports SKIP_NO_FEED:vix_intraday_not_wired (the guard's premise stays honest)."""
    params = {"j_vwap_cont_enabled": False, "gap_and_go_enabled": False,
              "j_vwap_reclaim_fb_enabled": False, "j_vix_dayside_enabled": True}
    results = SetupDispatcher(params, _dispatch_payload(None)).run()
    assert len(results) == 1
    assert results[0].skip_reason == "SKIP_NO_FEED:vix_intraday_not_wired"
