"""Guard for the P5 DIRECTION-CONTROLLED null gate in family_grind (L188 graduation).

L188: the PHASE-3 random-entry null shuffles the SIDE, so any DIRECTIONAL family beats it
just by being directionally correct -- it does NOT isolate selection alpha. The graduation
wires a direction-controlled null (random bars, side = the bar's OWN direction) into
family_grind as an automatic P5 gate for high-firing/directional families. This guard pins
that the gate (a) flags directional families by firing rate (C27), (b) uses momentum-aware
sides (NOT shuffled), (c) downgrades a direction-following artifact to PASS-P4-DIR-ARTIFACT
(so it is NOT an elite), (d) fails CLOSED on an uncomputable null, and (e) leaves
non-directional families byte-identical. Re-violated prose is a missing guardrail; this is
its code assertion (OP-25).

$0 / offline: synthetic frame + a deterministic fake simulate_trade_real (no real OPRA fills).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "backtest") not in sys.path:
    sys.path.insert(0, str(_REPO / "backtest"))

from autoresearch import family_grind as fg  # noqa: E402


class _Fill:
    """Minimal TradeFill stand-in (only the fields family_grind reads)."""

    def __init__(self, pnl: float, side: str = "C", ts: dt.datetime | None = None,
                 idx: int = 0):
        self.dollar_pnl = pnl
        self.side = side
        self.entry_time_et = ts or dt.datetime(2025, 6, 2, 10, 0)
        self.entry_bar_idx = idx


def _mk_rth(n_days: int = 10, bars_per_day: int = 20) -> pd.DataFrame:
    """Synthetic RTH frame with the columns family_grind/null_baseline read: open/high/low/
    close/timestamp_et/date/t on a reset RangeIndex. Bars alternate up/down so every bar's
    own direction is known."""
    rows = []
    d = dt.date(2025, 1, 2)
    made = 0
    while made < n_days:
        if d.weekday() < 5:
            for b in range(bars_per_day):
                ts = dt.datetime(d.year, d.month, d.day, 9, 30) + dt.timedelta(minutes=5 * b)
                o = 100.0 + b * 0.1
                c = o + (0.2 if b % 2 == 0 else -0.2)   # even bar = up (C), odd bar = down (P)
                rows.append({"open": o, "high": max(o, c) + 0.1, "low": min(o, c) - 0.1,
                             "close": c, "timestamp_et": ts})
            made += 1
        d += dt.timedelta(days=1)
    df = pd.DataFrame(rows)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    df["date"] = df["timestamp_et"].dt.date
    df["t"] = df["timestamp_et"].dt.time
    return df


_WINDOW = (dt.time(9, 30), dt.time(15, 55))


# ── (1) pure STRICT gate ───────────────────────────────────────────────────────
def test_dir_null_survives_strict_gate() -> None:
    # exp beats null MAX AND drop5 beats null MEAN -> survives
    assert fg.dir_null_survives(50.0, 30.0, {"null_max": 40.0, "null_mean": 20.0}) is True
    # exp does NOT beat null MAX -> artifact
    assert fg.dir_null_survives(35.0, 30.0, {"null_max": 40.0, "null_mean": 20.0}) is False
    # drop5 does NOT beat null MEAN -> artifact (concentration not robust)
    assert fg.dir_null_survives(50.0, 10.0, {"null_max": 40.0, "null_mean": 20.0}) is False


def test_dir_null_survives_fails_closed_on_uncomputable_null() -> None:
    assert fg.dir_null_survives(999.0, 999.0, {"null_max": None, "null_mean": 10.0}) is False
    assert fg.dir_null_survives(999.0, 999.0, {"null_max": 10.0, "null_mean": None}) is False
    assert fg.dir_null_survives(999.0, 999.0, {}) is False


# ── (2) pure verdict mapping ────────────────────────────────────────────────────
def test_p5_verdict_mapping() -> None:
    pass_null = {"dir_null_pass": True}
    fail_null = {"dir_null_pass": False}
    # directional family, survives both -> PASS-P5 (elite)
    assert fg.p5_verdict("PASS-P4", True, pass_null) == "PASS-P5"
    # directional family, collapses -> artifact (NOT elite)
    assert fg.p5_verdict("PASS-P4", True, fail_null) == "PASS-P4-DIR-ARTIFACT"
    # NON-directional family -> untouched even if a dir_null dict is present
    assert fg.p5_verdict("PASS-P4", False, fail_null) == "PASS-P4"
    # a cell that never reached PASS-P4 -> untouched
    assert fg.p5_verdict("PASS-P3", True, fail_null) == "PASS-P3"
    # directional but dir_null uncomputed (None) -> falls back to PASS-P4, never silently elites
    assert fg.p5_verdict("PASS-P4", True, None) == "PASS-P4"


# ── (3) firing-rate -> directional flag (C27) ───────────────────────────────────
def test_firing_rate_and_directional_flag() -> None:
    rth = _mk_rth(n_days=10, bars_per_day=20)
    # fire on 9 of 10 days (>80%) -> directional
    high = [{"bar_idx": day * 20 + 5} for day in range(9)]
    assert fg.firing_rate(rth, high) == pytest.approx(0.9)
    assert fg.is_directional_family(rth, high) is True
    # fire on 3 of 10 days (30%) -> NOT directional
    low = [{"bar_idx": day * 20 + 5} for day in range(3)]
    assert fg.firing_rate(rth, low) == pytest.approx(0.3)
    assert fg.is_directional_family(rth, low) is False
    # empty signals -> 0.0, not directional (no divide-by-zero)
    assert fg.firing_rate(rth, []) == 0.0
    assert fg.is_directional_family(rth, []) is False


# ── (4) dir-null uses MOMENTUM-AWARE sides (not shuffled) ────────────────────────
def test_dir_null_uses_momentum_aware_sides(monkeypatch) -> None:
    rth = _mk_rth(n_days=4, bars_per_day=20)
    seen: list[tuple[int, str]] = []

    def _fake_sim(entry_bar_idx, entry_bar, spy_df, ribbon_df, rejection_level,
                  triggers_fired, side, qty, setup, premium_stop_pct, strike_offset, **ek):
        seen.append((int(entry_bar_idx), side))
        return _Fill(1.0, side=side, idx=int(entry_bar_idx))

    monkeypatch.setattr(fg, "simulate_trade_real", _fake_sim)
    fills = [_Fill(5.0) for _ in range(6)]
    out = fg._dir_null(rth, fills, so=0, stop=-0.08, tp1=0.30, tq=0.667, trail=None,
                       window=_WINDOW, drop_top5=4.0, seeds=2)

    assert seen, "dir-null never called the simulator"
    o = rth["open"].to_numpy(); c = rth["close"].to_numpy()
    for idx, side in seen:
        expected = "C" if c[idx] >= o[idx] else "P"
        assert side == expected, f"bar {idx}: dir-null side {side} != momentum {expected}"
    # shape of the returned dict
    for k in ("dir_null_pass", "per_trade", "null_mean", "null_max", "edge_over_dir_null", "seeds"):
        assert k in out
    assert out["per_trade"] == pytest.approx(5.0)   # exp from the passed signal fills


# ── (5) gate BITES on a direction-following artifact (end-to-end decision) ───────
def test_gate_downgrades_artifact_and_keeps_real_edge(monkeypatch) -> None:
    rth = _mk_rth(n_days=4, bars_per_day=20)
    fills = [_Fill(20.0) for _ in range(8)]   # signal exp = 20

    # null returns +50/trade -> dir-null max == 50 > signal 20 -> ARTIFACT
    def _hot_sim(entry_bar_idx, entry_bar, spy_df, ribbon_df, rejection_level,
                 triggers_fired, side, qty, setup, premium_stop_pct, strike_offset, **ek):
        return _Fill(50.0, side=side, idx=int(entry_bar_idx))

    monkeypatch.setattr(fg, "simulate_trade_real", _hot_sim)
    art = fg._dir_null(rth, fills, 0, -0.08, 0.30, 0.667, None, _WINDOW, drop_top5=18.0, seeds=3)
    assert art["dir_null_pass"] is False
    assert fg.p5_verdict("PASS-P4", True, art) == "PASS-P4-DIR-ARTIFACT"

    # null returns +1/trade -> dir-null max == 1 < signal 20 -> REAL selection edge survives
    def _cold_sim(entry_bar_idx, entry_bar, spy_df, ribbon_df, rejection_level,
                  triggers_fired, side, qty, setup, premium_stop_pct, strike_offset, **ek):
        return _Fill(1.0, side=side, idx=int(entry_bar_idx))

    monkeypatch.setattr(fg, "simulate_trade_real", _cold_sim)
    real = fg._dir_null(rth, fills, 0, -0.08, 0.30, 0.667, None, _WINDOW, drop_top5=18.0, seeds=3)
    assert real["dir_null_pass"] is True
    assert fg.p5_verdict("PASS-P4", True, real) == "PASS-P5"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
