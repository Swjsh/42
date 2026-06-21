"""Shared random-entry NULL baseline + the standard null candidate-gate (C3/L58).

WHY THIS EXISTS — the exit-structure-artifact trap
───────────────────────────────────────────────────
The v15 asymmetric exit bracket (tight premium stop + +30% TP1 + 2.5x runner) is
mildly POSITIVE on almost ANY 0DTE entry over a 16-month sample: the tight stop caps
the left tail while the runner leaves the right tail open. So a directional candidate
that "passes every structural gate" (OOS per-trade > 0, >=4/6 positive quarters,
n >= 20, drop-top5 per-trade > 0) can be a pure EXIT-STRUCTURE artifact with ZERO
directional alpha — the bracket is doing the work, not the read.

The decisive test is a coin-flip null: re-run the SAME number of entries, SAME call/put
mix, SAME stop + strike + invalidation rule, but at RANDOM RTH bars instead of the
signal bars (deterministic, fixed seeds). If the signal's per-trade does NOT clear the
null's MAX (the luckiest random seed), the "edge" is the bracket, not the signal.

First proven on the Connors RSI(2) mean-reversion new-hunt (2026-06-20): it cleared
every coded structural gate, yet its +$6.11/trade sat UNDER the random-null MAX of
+$8.10 (mean +$2.66) -> REJECTED as an exit-structure artifact. Artifact:
``analysis/recommendations/newhunt-rsi2-mean-reversion.json``. See LESSONS-LEARNED L171.

USAGE — every new-hunt / real-fills validator
──────────────────────────────────────────────
Compute the best cell's headline per-trade + its concentration-robust drop-top5
per-trade, then::

    from autoresearch.null_baseline import random_entry_null, null_gate

    null = random_entry_null(rth, n_signals=len(rows), n_call=n_c, n_put=n_p,
                             strike_offset=so, premium_stop_pct=ps)
    gate = null_gate(best_per_trade, drop_top5_per_trade, null)
    if not gate["null_pass"]:
        ...  # NOT a candidate — the edge is the exit structure, not the signal (C3/L58)

``null_gate`` is the home of the two STANDARD candidate-gate keys this module adds —
``beats_null_max`` and ``drop_top5_beats_null_mean`` — plus ``beats_null_mean`` /
``edge_over_null_per_trade`` for disclosure. The STANDARD bar is::

    null_pass = beats_null_max AND drop_top5_beats_null_mean

i.e. beat the MAX (the luckiest coin-flip), not merely be positive, AND the
day-concentration-robust drop-top5 per-trade must beat the null MEAN.

Pure Python, $0. Deterministic (fixed per-seed RNG; reproducible across runs).
"""
from __future__ import annotations

import datetime as dt
import random
import sys
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import numpy as np
import pandas as pd

# Self-sufficient import: ensure backtest/ is importable so `lib.simulator_real`
# resolves even when this module is imported directly (e.g. from a unit test).
_REPO = Path(__file__).resolve().parent.parent  # backtest/
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.simulator_real import simulate_trade_real  # noqa: E402

# Defaults match the production v15 conventions every new-hunt already uses: the 09:35
# entry gate (no first-bar) with room before the 15:50 time stop, a 12-bar swing-low/high
# invalidation, and qty 3 (2 TP + 1 runner).
DEFAULT_ENTRY_GATE: tuple[dt.time, dt.time] = (dt.time(9, 35), dt.time(15, 45))
DEFAULT_SWING_LOOKBACK = 12
DEFAULT_QTY = 3
DEFAULT_SEEDS = 10


def _swing_invalidation(rth: pd.DataFrame, idx: int, side: str, swing_lookback: int) -> float:
    """Generic chart-stop invalidation for a random entry so the null's stop geometry
    matches the signal's: trailing swing LOW (CALL -> support that must hold) / swing
    HIGH (PUT -> resistance). Causal — uses only bars in ``[idx-lookback+1, idx]``."""
    c = float(rth.iloc[idx]["close"])
    lo = max(0, idx - swing_lookback + 1)
    win = rth.iloc[lo: idx + 1]
    if side == "C":
        rej = float(win["low"].min())
        return rej if rej < c else c - 1.0
    rej = float(win["high"].max())
    return rej if rej > c else c + 1.0


def _eligible_indices(rth: pd.DataFrame, entry_gate: tuple[dt.time, dt.time]) -> np.ndarray:
    """Positional indices of RTH bars whose wall-clock time falls inside the entry gate.

    Returns ascending positional indices (``rth`` is expected to carry a reset RangeIndex,
    as every caller builds it via ``.reset_index(drop=True)``)."""
    start, end = entry_gate
    ts = pd.to_datetime(rth["timestamp_et"])
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    times = ts.dt.time.to_numpy()
    mask = np.array([start <= t <= end for t in times], dtype=bool)
    return np.flatnonzero(mask)


def random_entry_null(
    rth: pd.DataFrame,
    n_signals: int,
    n_call: int,
    n_put: int,
    strike_offset: int,
    premium_stop_pct: float,
    *,
    qty: int = DEFAULT_QTY,
    swing_lookback: int = DEFAULT_SWING_LOOKBACK,
    entry_gate: tuple[dt.time, dt.time] = DEFAULT_ENTRY_GATE,
    eligible_idx: Optional[Sequence[int]] = None,
    setup: str = "RANDOM_NULL",
    triggers: Optional[Sequence[str]] = None,
    rejection_fn: Optional[Callable[[pd.DataFrame, int, str], float]] = None,
    seeds: int = DEFAULT_SEEDS,
    sim_fn: Optional[Callable[..., Any]] = None,
) -> dict:
    """Coin-flip null: random RTH entries with the SAME count, SAME call/put mix, SAME
    stop + strike + invalidation rule as the cell under test, drawn at RANDOM bars inside
    the entry gate. Isolates the SIGNAL from the exit STRUCTURE (C3/L58).

    Deterministic: seed ``s`` uses a private ``random.Random(s)`` (no global RNG side
    effects), so results are reproducible across runs and processes.

    Args:
        rth: RTH-only frame with a reset RangeIndex and ``timestamp_et``/``close``/
            ``low``/``high`` columns. ``simulate_trade_real`` receives this as ``spy_df``.
        n_signals: number of entries to draw per seed (matched to the cell's trade count).
        n_call, n_put: the cell's realized call/put split (the side mix is preserved).
        strike_offset, premium_stop_pct: the cell's strike + stop (held identical).
        qty: contracts per simulated trade (default 3 = 2 TP + 1 runner).
        swing_lookback: bars for the default swing-low/high invalidation.
        entry_gate: (start, end) wall-clock ET window the random bars are drawn from.
        eligible_idx: explicit positional indices to draw from; overrides ``entry_gate``
            (use when the caller's eligible set is not a simple time window).
        setup, triggers: labels passed through to ``simulate_trade_real`` (audit only).
        rejection_fn: optional ``(rth, idx, side) -> level`` to override the default
            swing invalidation (e.g. a neckline-based stop) so the null mirrors the
            signal's stop geometry.
        seeds: number of deterministic seeds (0..seeds-1) averaged.
        sim_fn: optional simulator override (defaults to the module
            :func:`simulate_trade_real`). Lets a caller drive the null through the SAME
            injected simulator as its signal cell so the coin-flip benchmark is
            apples-to-apples (and lets unit tests stub OPRA out). Defaults preserve the
            existing module-global behavior byte-for-byte.

    Returns:
        dict with ``seeds``, ``n_eligible``, ``n_drawn``, ``per_trade_mean``,
        ``per_trade_min``, ``per_trade_max`` and ``per_trade_by_seed``.
    """
    trig = list(triggers) if triggers is not None else ["random_null"]
    sim = sim_fn if sim_fn is not None else simulate_trade_real

    if eligible_idx is not None:
        elig = np.asarray(list(eligible_idx), dtype=int)
    else:
        elig = _eligible_indices(rth, entry_gate)

    if len(elig) == 0:
        return {
            "seeds": seeds, "n_eligible": 0, "n_drawn": 0,
            "per_trade_mean": 0.0, "per_trade_min": 0.0, "per_trade_max": 0.0,
            "per_trade_by_seed": [], "note": "no eligible bars in entry gate",
        }

    n_draw = min(int(n_signals), len(elig))
    elig_list = [int(i) for i in elig]
    per_trades: list[float] = []

    for seed in range(seeds):
        rng = random.Random(seed)
        picks = rng.sample(elig_list, n_draw)
        sides = ["C"] * int(n_call) + ["P"] * int(n_put)
        # Guard a mismatched side-mix (n_call + n_put < n_draw): pad with the majority
        # side so indexing is always safe. In the normal case (n_call + n_put == n_signals)
        # no padding occurs and the RNG draw is bit-identical to the legacy inline version.
        if len(sides) < n_draw:
            sides += ["C" if n_call >= n_put else "P"] * (n_draw - len(sides))
        rng.shuffle(sides)

        pnl = 0.0
        nn = 0
        for k, idx in enumerate(picks):
            side = sides[k]
            rej = (rejection_fn(rth, idx, side) if rejection_fn is not None
                   else _swing_invalidation(rth, idx, side, swing_lookback))
            fill = sim(
                entry_bar_idx=idx, entry_bar=rth.iloc[idx], spy_df=rth, ribbon_df=None,
                rejection_level=round(float(rej), 2), triggers_fired=trig, side=side,
                qty=qty, setup=setup, premium_stop_pct=premium_stop_pct,
                strike_offset=strike_offset)
            if fill is None:
                continue
            pnl += float(fill.dollar_pnl)
            nn += 1
        per_trades.append(pnl / nn if nn else 0.0)

    return {
        "seeds": seeds,
        "n_eligible": int(len(elig)),
        "n_drawn": int(n_draw),
        "per_trade_mean": round(float(np.mean(per_trades)), 2),
        "per_trade_min": round(float(min(per_trades)), 2),
        "per_trade_max": round(float(max(per_trades)), 2),
        "per_trade_by_seed": [round(float(x), 2) for x in per_trades],
    }


def null_gate(
    per_trade: Optional[float],
    drop_top5_per_trade: Optional[float],
    null: dict,
) -> dict:
    """The STANDARD null candidate-gate (C3/L58). Folds the random-entry null into the
    two standard gate keys plus disclosure.

    A 0DTE directional candidate that passes the structural gates but whose per-trade a
    random-entry null reproduces is an exit-structure artifact, not signal alpha. The bar
    is therefore: beat the null MAX (the luckiest coin-flip), not merely be positive, AND
    the concentration-robust drop-top5 per-trade must beat the null MEAN.

    Args:
        per_trade: the cell's headline per-trade expectancy.
        drop_top5_per_trade: per-trade after removing the 5 best P&L days (concentration
            robustness).
        null: the dict returned by :func:`random_entry_null` (needs ``per_trade_mean`` /
            ``per_trade_max``).

    Returns:
        dict with ``beats_null_mean``, ``beats_null_max``, ``drop_top5_beats_null_mean``,
        ``edge_over_null_per_trade`` and the combined ``null_pass``.
    """
    nmean = null.get("per_trade_mean")
    nmax = null.get("per_trade_max")
    beats_mean = per_trade is not None and nmean is not None and per_trade > nmean
    beats_max = per_trade is not None and nmax is not None and per_trade > nmax
    drop_beats_mean = (
        drop_top5_per_trade is not None and nmean is not None
        and drop_top5_per_trade > nmean
    )
    edge = (round(per_trade - nmean, 2)
            if (per_trade is not None and nmean is not None) else None)
    return {
        "beats_null_mean": bool(beats_mean),
        "beats_null_max": bool(beats_max),
        "drop_top5_beats_null_mean": bool(drop_beats_mean),
        "edge_over_null_per_trade": edge,
        # STANDARD BAR (C3/L58): beat the null MAX, not just be positive, AND the
        # day-concentration-robust drop-top5 per-trade must beat the null MEAN.
        "null_pass": bool(beats_max and drop_beats_mean),
    }
