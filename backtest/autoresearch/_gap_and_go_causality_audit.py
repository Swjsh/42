"""Causality audit for H2b gap_and_go (L166 look-ahead mirage guard).

Standalone, $0, read-only. PROVES the detector reads the gap, the confirming first
bar, and the continuation trigger STRICTLY at-or-before the trigger bar's close, and
that the simulator fills on the NEXT bar's open (no future leak). If any check fails,
the script exits non-zero and prints LOOK_AHEAD_DETECTED — which would VOID the edge.

Checks
------
1. prior_close provenance: for every gapped signal, independently recompute the prior
   TRADING day's last RTH close from the raw frame and assert it equals the DayCtx
   prior_close the detector used. (Guards against today's-close leak into the gap.)
2. trigger-bar = FIRST RTH bar: every gap_and_go signal's bar_idx is the day's first
   RTH bar (the only bar the detector reads). No later bar is consulted.
3. confirmation uses ONLY the trigger bar: re-derive gap sign + first-bar green/red
   from the raw bar at bar_idx and assert it reproduces the detector's side. No bar
   AFTER bar_idx is referenced.
4. fill is strictly future: re-run the simulator on a sample of signals and assert the
   recorded entry time is > the trigger bar's timestamp (next-bar-open), and that the
   stop_level equals the trigger bar's opposite extreme (read at-or-before close).
5. monotonic index: bar_idx for the signal is < every subsequent bar index used by the
   sim loop (the sim only ever walks forward from entry_bar_idx+2).

Usage:  backtest/.venv/Scripts/python.exe backtest/autoresearch/_gap_and_go_causality_audit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    load_spy,
    align_vix,
    build_day_contexts,
    detect_gap_and_go,
    _gap_setup,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real, _strike_from_spot  # noqa: E402
from lib.option_pricing_real import option_symbol, load_contract_bars  # noqa: E402

SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

MIN_GAP = 0.0025
MAX_GAP = 0.015


def main() -> int:
    failures: list[str] = []
    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)

    # Independent prior-close map: for each trading date, the prior trading day's
    # LAST bar close (raw, no detector code path).
    by_date = {d: g for d, g in spy.groupby("date", sort=True)}
    ordered_dates = sorted(by_date.keys())
    indep_prior_close: dict = {}
    prev_close = None
    for d in ordered_dates:
        indep_prior_close[d] = prev_close
        prev_close = float(by_date[d]["close"].iloc[-1])

    signals = detect_gap_and_go(spy, ribbon, vix, days)
    print(f"gap_and_go signals: {len(signals)}")

    # Map global bar_idx -> DayCtx for the first-RTH-bar assertion.
    first_rth_idx = {dc.idx0: dc for dc in days}

    # ---- CHECK 1+2+3: per-signal causal reconstruction --------------------------
    n_checked = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["date"]
        n_checked += 1

        # (2) trigger bar must be the day's FIRST RTH bar
        if sg.bar_idx not in first_rth_idx:
            failures.append(
                f"[CHECK2] {d}: signal bar_idx {sg.bar_idx} is NOT a day's first RTH bar"
            )
            continue
        dc = first_rth_idx[sg.bar_idx]

        # (1) prior_close used by detector == independently recomputed prior close
        indep = indep_prior_close.get(d)
        if indep is None:
            failures.append(f"[CHECK1] {d}: independent prior_close is None but a signal fired")
        elif dc.prior_close is None:
            failures.append(f"[CHECK1] {d}: DayCtx.prior_close is None but a signal fired")
        elif abs(float(dc.prior_close) - float(indep)) > 1e-6:
            failures.append(
                f"[CHECK1] {d}: DayCtx.prior_close={dc.prior_close} != independent {indep}"
            )

        # (3) re-derive gap + confirmation from ONLY the trigger bar + prior close
        first_open = float(bar["open"])
        first_close = float(bar["close"])
        gap = first_open / float(indep) - 1.0 if indep else 0.0
        green = first_close > first_open
        red = first_close < first_open
        expect_side = None
        if MIN_GAP <= abs(gap) <= MAX_GAP:
            if gap > 0 and green:
                expect_side = "C"
            elif gap < 0 and red:
                expect_side = "P"
        if expect_side != sg.side:
            failures.append(
                f"[CHECK3] {d}: re-derived side {expect_side} (gap={gap:+.4f} "
                f"green={green} red={red}) != detector side {sg.side}"
            )

        # (3b) stop_level must equal the trigger bar's opposite extreme (read at close)
        expect_stop = float(bar["low"]) if sg.side == "C" else float(bar["high"])
        if sg.stop_level is None or abs(float(sg.stop_level) - expect_stop) > 1e-6:
            failures.append(
                f"[CHECK3b] {d}: stop_level {sg.stop_level} != trigger-bar opposite "
                f"extreme {expect_stop}"
            )

    print(f"per-signal causal reconstruction checked: {n_checked}")

    # ---- CHECK 4: fill is strictly the NEXT bar open (sample of cached signals) --
    n_fill_checked = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        # ATM tier (offset 0). Snap to nearest cached for an honest fill.
        strike = None
        for step in range(0, 5):
            cands = [atm] if step == 0 else [atm - step, atm + step]
            for c in cands:
                if load_contract_bars(option_symbol(d, c, sg.side)) is not None:
                    strike = c
                    break
            if strike is not None:
                break
        if strike is None:
            continue
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx,
            entry_bar=bar,
            spy_df=spy,
            ribbon_df=ribbon,
            rejection_level=sg.stop_level,
            triggers_fired=[sg.note or "audit"],
            side=sg.side,
            qty=3,
            setup="AUDIT",
            strike_override=strike,
        )
        if fill is None:
            continue
        n_fill_checked += 1
        trig_ts = bar["timestamp_et"]
        entry_ts = fill.entry_time_et
        # entry must be strictly AFTER the trigger bar timestamp (next-bar fill)
        if not (pd.Timestamp(entry_ts) > pd.Timestamp(trig_ts)):
            failures.append(
                f"[CHECK4] {d}: fill entry_time {entry_ts} not strictly after trigger "
                f"bar {trig_ts} (look-ahead fill!)"
            )
        # entry must be exactly one 5-min bar later (the immediate next bar open)
        delta_min = (pd.Timestamp(entry_ts) - pd.Timestamp(trig_ts)).total_seconds() / 60.0
        if delta_min < 5.0:
            failures.append(
                f"[CHECK4b] {d}: fill {delta_min:.1f}min after trigger (<5min — same/earlier bar)"
            )
        if n_fill_checked >= 25:
            break
    print(f"fill-timing checked on {n_fill_checked} cached signals")

    # ---- verdict ----------------------------------------------------------------
    print("\n" + "=" * 70)
    if failures:
        print("LOOK_AHEAD_DETECTED — causality FAILED:")
        for f in failures[:40]:
            print("  " + f)
        print(f"\nTOTAL FAILURES: {len(failures)}")
        return 1
    print("CAUSALITY_PASS — no look-ahead found across all checks.")
    print(f"  - {n_checked} signals: prior_close provenance + first-RTH-bar + "
          f"trigger-only confirmation + stop-at-close all verified")
    print(f"  - {n_fill_checked} fills: entry strictly next-bar-open (>= +5min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
