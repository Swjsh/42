"""Guards for the trendline shadow ledger (J-directed 2026-08-20).

WHAT IT IS
  J hand-drew an ascending support line through the 2026-08-20 lows and asked why
  the engine never saw it. It structurally cannot: `filters.py::detect_trendline_
  rejection_bearish` reads pivot HIGHS and hard-rejects any non-decreasing slope, so
  ascending support, its break and its retest are invisible by construction.

  `backtest/lib/trendlines.py::detect_trendlines` already fits ascending lines from
  swing lows and had ZERO consumers. trendline_shadow.py wraps it into an observation
  ledger, and — per J — takes THEORETICAL trades with the line acting as an extra
  gate, so there is something to A/B rather than an argument from a chart.

WHAT THESE GUARDS PROTECT
  1. NO LOOK-AHEAD on the decision side. The fit at bar i must use bars[0:i] only.
     Forward MFE/MAE deliberately DO look ahead — that is the measurement — and must
     never be reachable by anything that decides.
  2. IT STAYS SHADOW. No order placement, no params writes, no entry-path import.
  3. IT CANNOT GO SILENTLY BLIND. A date with no bars exits non-zero; a skipped
     session says so. A silently-empty ledger reads downstream as "no trendlines
     today", which is the exact confusion the ledger exists to remove (C7).
  4. THE EDGE CLAIM STAYS HONEST. Measured 2026-08-20: +0.041 SPY pts/trade over
     n=1332 — ABOVE a random-entry null, but the session-clustered 95% CI is
     [-0.039, +0.124] and the top 3 sessions supply >100% of total profit. Any
     surface that publishes a trailing window must publish its concentration too.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import trendline_shadow as T  # noqa: E402

SRC = Path(T.__file__).read_text(encoding="utf-8")


# ---------------------------------------------------------------- shadow-ness
def test_it_can_never_place_an_order():
    for bad in ("place_option_order", "place_stock_order", "submit_order", "alpaca"):
        assert bad not in SRC.lower().replace("alpaca-mcp", ""), f"{bad} reachable from the shadow"


# The module docstring cites filters.py by name to explain WHY the engine cannot see
# ascending support. That is documentation, not a dependency, so code-level guards scan
# the body with the docstring stripped -- otherwise the guard fails on its own rationale.
CODE = SRC.split('"""', 2)[-1]


def test_it_never_writes_params_or_the_entry_path():
    for bad in ("params.json", "heartbeat_core", "exit-state.json", "filters.py"):
        assert bad not in CODE, f"shadow reaches a live decision surface in code: {bad}"


def test_the_only_file_it_writes_is_its_own_ledger():
    writes = [ln for ln in SRC.splitlines()
              if (".write_text(" in ln or '.open("a"' in ln or ".to_csv(" in ln)]
    assert writes, "no write found — did the ledger stop persisting?"
    for ln in writes:
        assert "out" in ln or "OUT" in ln, f"writes somewhere other than the ledger: {ln.strip()}"


# ---------------------------------------------------------------- no look-ahead
def test_the_fit_uses_only_prior_bars():
    assert "detect_trendlines(day.iloc[:i])" in SRC, (
        "the fit must slice bars[0:i] — including bar i leaks the bar being judged (C6)"
    )
    assert "day.iloc[:i + 1]" not in SRC and "day.iloc[:i+1]" not in SRC


def test_forward_measurement_is_strictly_after_the_event_bar():
    assert "day.iloc[i + 1: i + 1 + w]" in SRC, (
        "forward MFE/MAE must start at i+1; starting at i would include the event bar"
    )


def test_theoretical_trade_walks_forward_from_the_next_bar():
    """Entry is bar i's close, so the walk must start at i+1 — never re-read bar i."""
    day = pd.DataFrame({
        "close": [100.0, 100.0, 100.0, 100.0],
        "high":  [999.0,  100.2, 100.2, 100.2],   # bar 0 has a huge high
        "low":   [1.0,     99.9,  99.9,  99.9],   # and a huge low
    })
    tr = T._theoretical_trade(day, 0, bearish=True)
    assert tr["outcome"] == "time_stop", (
        f"bar 0's own extremes leaked into its trade ({tr}) — the walk must begin at i+1"
    )


def test_stop_is_checked_before_target_within_a_bar():
    """Intrabar order is unknowable, so the pessimistic branch must win. A sim that
    resolves ties in its own favour manufactures edge out of nothing."""
    day = pd.DataFrame({          # one bar that spans BOTH the stop and the target
        "close": [100.0, 100.0],
        "high":  [100.0, 100.0 + T.THEO_STOP_POINTS + 0.1],
        "low":   [100.0, 100.0 - T.THEO_TP_POINTS - 0.1],
    })
    tr = T._theoretical_trade(day, 0, bearish=True)
    assert tr["outcome"] == "stop" and tr["points"] < 0, (
        f"a bar that hits both resolved as {tr['outcome']} — must resolve as the stop"
    )


# ---------------------------------------------------------------- quality bar
def test_only_real_lines_and_tradeable_shapes_qualify():
    assert T.THEO_MIN_TOUCHES >= 3, "a 2-touch 'line' is two points and any two points fit"
    assert 0 < T.THEO_MIN_R2 <= 1
    assert ("descending", "BREAK") not in T.THEO_EVENTS, (
        "a descending line breaking UP is a bullish read the engine already covers; "
        "including it here silently doubles the sample with a different setup"
    )


def test_events_are_stamped_with_anchor_flavor():
    """J 2026-07-14: anchors are ALL-body or ALL-wick, never mixed. detect_trendlines
    fits swing extremes, so every row must say 'wick' or a future body-anchored
    variant gets silently conflated with this one."""
    assert '"flavor": "wick"' in SRC


# ---------------------------------------------------------------- fail loud
def test_a_date_with_no_bars_exits_non_zero(tmp_path):
    r = subprocess.run([sys.executable, str(REPO / "setup" / "scripts" / "trendline_shadow.py"),
                        "--date", "1999-01-04"],
                       capture_output=True, text=True, errors="replace", cwd=str(REPO))
    assert r.returncode != 0, (
        "a session with no bars exited 0. Downstream that is indistinguishable from "
        "'no trendlines today' — the ledger must fail LOUD instead (C7)."
    )
    assert "SKIPPED, not empty" in (r.stdout + r.stderr)


def test_the_ledger_is_idempotent_per_date(tmp_path):
    """Re-running a date must not double-log it — the ladder-ledger scar (2026-08-20),
    where 08-07 landed eight times and inflated the naive sum 6x."""
    out = tmp_path / "l.jsonl"
    T.run(["2026-08-20"], out=out)
    first = out.read_text(encoding="utf-8").count("\n")
    T.run(["2026-08-20"], out=out)
    assert out.read_text(encoding="utf-8").count("\n") == first, "re-run duplicated rows"
    assert first > 0


# ---------------------------------------------------------------- honest reporting
def test_rollup_says_why_when_it_has_nothing():
    r = T.daily_rollup("1999-01-04")
    assert r["logged"] is False and r.get("reason"), (
        "an empty rollup must carry a reason — a blank EOD section reads as 'no lines'"
    )


def test_baseline_publishes_concentration_not_just_the_total():
    """The trap this closes: the trailing 5 sessions read +17.14 pts / WR 64% on
    2026-08-20 — the BEST of 61 comparable windows, with one session supplying 48%.
    A trailing window with no baseline re-cherry-picks itself every single day."""
    if not T.OUT.exists():
        pytest.skip("ledger not seeded")
    b = T.baseline("2026-08-20")
    if not b.get("ok"):
        pytest.skip(b.get("reason", "no baseline"))
    for k in ("window_percentile", "top3_share_of_total", "windows_negative",
              "all_points_per_trade", "sessions_positive"):
        assert k in b, f"baseline drops {k} — concentration must ship WITH the number"


def test_the_eod_report_asks_the_question_every_day():
    """J 2026-08-20: 'we need to check EVERY SINGLE DAY. Do we see any trend lines?
    How do we act on them?' — wired into the full audit, not left to a human to run."""
    eod = (REPO / "setup" / "scripts" / "eod_full_audit.py").read_text(encoding="utf-8")
    assert "TRENDLINES" in eod and "trendline_shadow" in eod
    assert "NO TRENDLINE DATA" in eod, "the blind case must be loud, not blank"
    assert "whole-sample number is the honest one" in eod, (
        "the EOD section must publish the whole-sample baseline next to the trailing "
        "window, or a hot streak reads as a discovery"
    )


def test_the_standing_verdict_is_recorded_as_not_a_green_light():
    assert "NOT a green light" in (REPO / "setup" / "scripts" / "eod_full_audit.py").read_text(
        encoding="utf-8")


def test_ledger_rows_carry_what_an_ab_would_need():
    if not T.OUT.exists():
        pytest.skip("ledger not seeded")
    with T.OUT.open(encoding="utf-8") as fh:
        row = json.loads(fh.readline())
    for k in ("date", "ts_et", "event", "direction", "flavor", "line_price",
              "touch_count", "r_squared", "bias", "theo_qualifies"):
        assert k in row, f"ledger row missing {k}"
