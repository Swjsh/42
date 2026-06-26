"""Graduated FRAUD-DETECTOR gates for EVERY real-fills candidate (C3/L58, L171/L172).

WHY THIS MODULE EXISTS
──────────────────────
Three "edges" — Connors RSI(2) mean-reversion, IBS mean-reversion, and an ema/adx
gate — each PASSED the naive 5-gate real-fills bar (OOS per-trade > 0, >=4/6 positive
quarters, top5-day < 200%, n >= 20, drop-top-5-days > 0) yet were NOT real per-trade
option edges. The lesson
``strategy/candidates/_lesson-inbox/2026-06-20-option-edge-vs-spy-tilt-discriminator.md``
names the two discriminators that caught all three, and demands they GRADUATE into the
real-fills verify harness so every future candidate is auto-checked:

  GATE 1 — RANDOM-ENTRY-NULL.   Re-run the SAME exit/stop/strike/side-mix on RANDOM RTH
           entry bars (~20 seeds). If a coin-flip entry reproduces the per-trade, the
           "edge" is the v15 EXIT BRACKET, not the signal. Caught RSI(2): null +$8.10/tr
           >= strategy +$6.11/tr.  -> backtest/autoresearch/null_baseline.py + L172.

  GATE 2 — NO-TRUNCATION-ARTIFACT.   The SIGN of per-trade must NOT invert between the
           chosen (tight) premium stop and chart-stop-only (-0.99). If it is only
           positive because the tight stop TRUNCATES losers, it is a stop artifact.
           Caught ema_adx: +$3.4/tr at -8% -> -$41.6/tr at chart-stop-only.
           -> backtest/lib/truncation_guard.py + L171.

Both gates need PER-TRADE RE-SIMULATION, so this module re-runs a candidate's exact
config through ``lib.simulator_real.simulate_trade_real`` (the only WR authority, C1):

  * the chosen cell  (strike_offset, premium_stop_pct) — the candidate's headline, and
  * the SAME strike at chart-stop-only (-0.99)         — the truncation reference, and
  * a random-entry null at the chosen cell             — the coin-flip benchmark.

THE KILLER COMBINATION (the lesson's operational C3/L58 form):
    PASS null  +  FAIL truncation  =  a SPY-DIRECTION tilt that profits only via
    stop-truncation, NOT an option edge.

``verify_candidate`` returns a :class:`FraudVerdict`; ``.passes`` is True only when BOTH
gates clear. It is wired as a STANDARD auto-check into
``backtest/autoresearch/verify_edgehunt_candidates.py`` so it runs on every candidate,
and is exercised by ``backtest/tests/test_fraud_gates.py`` (known-fake REJECTED /
known-real PASSES).

Pure Python, $0 in the sim loop. No live orders. Deterministic.
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

# Self-sufficient imports: make backtest/ importable so lib.* / autoresearch.*
# resolve whether this is imported from the verify harness or a unit test.
_REPO = Path(__file__).resolve().parent.parent  # backtest/
_ROOT = _REPO.parent                            # repo root (42/)
for _p in (str(_REPO), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch.null_baseline import (  # noqa: E402
    DEFAULT_SEEDS,
    null_gate,
    random_entry_null,
)
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.truncation_guard import (  # noqa: E402
    CHART_STOP_ONLY_PCT,
    is_truncation_artifact,
)

# Default seed count for the null. 20 seeds per the lesson ("~20 seeds"); the shared
# null_baseline default is 10, but the fraud gate uses the stronger 20-seed bar.
NULL_SEEDS = 20

# OOS-ALONE drop-top5 (L173). To drop the 5 best OOS observations and still have a
# non-empty remainder you need STRICTLY MORE than 5 OOS observations. Mirrors the
# per-harness convention in autoresearch/_b10_exit_audit.py::oos_drop_top5 (which
# trims arr[:-5] and reports drop-top5-positive only when len(trimmed) > 0). Below
# this floor the gate is UNEVALUABLE (skip/None), never a crash.
MIN_OOS_TO_DROP_TOP5 = 5


def oos_drop_top5_gate(
    *,
    oos_drop_top5_per_trade: Optional[float],
    oos_n: Optional[int] = None,
) -> dict:
    """L173 OOS-ALONE drop-top5 gate (the THIRD graduated concentration check).

    Full-sample drop-top5 > 0 (the existing GATE_FRAUD null check and the family
    grids' own ``top5_day_pct`` < 200% gate) is NECESSARY-BUT-NOT-SUFFICIENT: a
    candidate can pass full-sample concentration while its edge lives in a handful
    of OOS days, so that removing the 5 best OOS observations turns the OOS-only
    per-trade NEGATIVE. This caught edge #3 (a 2026-bull-regime artifact): it passed
    the full-sample drop-top5 at B5 but failed OOS-alone at B6 (OOS-alone drop-top5
    -$16 -> -$23; top5-day-OOS 120-228%). C4/L173.

    The gate PASSES iff the OOS-window-only per-trade AFTER dropping the 5 best OOS
    observations is strictly > 0. It is ADDITIVE — it never relaxes the full-sample
    drop-top5 / null / truncation gates; it only adds a stricter OOS-alone cut.

    Small-n handling (matches autoresearch/_b10_exit_audit.py::oos_drop_top5): when
    there are not strictly more than ``MIN_OOS_TO_DROP_TOP5`` (5) OOS observations,
    the 5-best cannot be dropped leaving a non-empty remainder, so the gate is
    UNEVALUABLE (``evaluable=False``) and reported as a caveat by the harness rather
    than failing or crashing. Fails OPEN on a missing per-trade value (cannot
    disprove != bless), exactly like the truncation/null gates.

    Args:
        oos_drop_top5_per_trade: OOS-only per-trade expectancy after removing the 5
            best OOS observations (None when the family did not record it).
        oos_n: OOS observation count, used only to flag the too-small-to-drop-5 case
            (advisory; the gate is still evaluated on the per-trade value when present).

    Returns:
        dict with ``oos_drop_top5_per_trade`` (echoed), ``evaluable`` (bool — False
        when the value is missing or OOS n <= 5), and ``oos_drop_top5_pass`` (bool —
        True only when evaluable AND per-trade > 0).
    """
    too_small = oos_n is not None and oos_n <= MIN_OOS_TO_DROP_TOP5
    evaluable = oos_drop_top5_per_trade is not None and not too_small
    return {
        "oos_drop_top5_per_trade": (round(float(oos_drop_top5_per_trade), 2)
                                    if oos_drop_top5_per_trade is not None else None),
        "oos_n": oos_n,
        "evaluable": bool(evaluable),
        # PASS only when we can evaluate AND the OOS-alone drop-top5 stays positive.
        "oos_drop_top5_pass": bool(evaluable and oos_drop_top5_per_trade > 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# A re-simulated signal: just the inputs simulate_trade_real needs.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CandidateSignal:
    """One causal entry to re-simulate. Immutable (coding-style: no in-place mutation).

    bar_idx must index into ``rth`` (a reset-RangeIndex RTH frame). rejection_level is
    the chart-stop invalidation level for that entry; side is 'C'/'P'.
    """

    bar_idx: int
    side: str
    rejection_level: float
    note: str = "candidate"


def _per_trade_and_drop_top5(
    pnls_by_day: dict[str, list[float]],
) -> tuple[Optional[float], Optional[float], int]:
    """Return (per_trade, drop_top5_per_trade, n) from a {day: [pnl,...]} map.

    ``drop_top5_per_trade`` removes the 5 best P&L *days* (concentration robustness,
    matching the lesson's drop-top-5-days gate and null_gate's drop_top5 input)."""
    all_pnls = [p for v in pnls_by_day.values() for p in v]
    n = len(all_pnls)
    if n == 0:
        return None, None, 0
    per_trade = sum(all_pnls) / n
    day_totals = {d: sum(v) for d, v in pnls_by_day.items()}
    top5_days = set(
        d for d, _ in sorted(day_totals.items(), key=lambda kv: kv[1], reverse=True)[:5]
    )
    kept = [p for d, v in pnls_by_day.items() if d not in top5_days for p in v]
    drop_top5 = (sum(kept) / len(kept)) if kept else None
    return per_trade, drop_top5, n


def _simulate_signals(
    signals: Sequence[CandidateSignal],
    rth,
    *,
    strike_offset: int,
    premium_stop_pct: float,
    qty: int,
    setup: str,
    sim_fn: Callable = simulate_trade_real,
) -> dict[str, list[float]]:
    """Re-run every signal at one (strike_offset, premium_stop_pct) cell; return a
    {day(YYYY-MM-DD): [dollar_pnl, ...]} map. Skips signals with no cached OPRA bars
    (fill is None) — exactly as the source validators do."""
    by_day: dict[str, list[float]] = defaultdict(list)
    for sg in signals:
        entry_bar = rth.iloc[sg.bar_idx]
        ts = entry_bar["timestamp_et"]
        day = (ts.date() if hasattr(ts, "date") else dt.date.today()).isoformat()
        fill = sim_fn(
            entry_bar_idx=sg.bar_idx,
            entry_bar=entry_bar,
            spy_df=rth,
            ribbon_df=None,
            rejection_level=round(float(sg.rejection_level), 2),
            triggers_fired=[sg.note],
            side=sg.side,
            qty=qty,
            setup=setup,
            premium_stop_pct=premium_stop_pct,
            strike_offset=strike_offset,
        )
        if fill is None or getattr(fill, "dollar_pnl", None) is None:
            continue
        by_day[day].append(float(fill.dollar_pnl))
    return by_day


@dataclass(frozen=True)
class FraudVerdict:
    """Immutable result of the two graduated fraud gates for one candidate cell."""

    # GATE 2 — no-truncation
    chosen_per_trade: Optional[float]
    chart_stop_only_per_trade: Optional[float]
    chosen_premium_stop_pct: float
    is_truncation_artifact: bool
    no_truncation_pass: bool

    # GATE 1 — random-entry null
    null: dict
    null_gate: dict
    null_pass: bool

    # disclosure
    n_chosen: int
    n_chart_stop_only: int
    reason: str = ""
    error: Optional[str] = None

    @property
    def passes(self) -> bool:
        """True only when BOTH graduated fraud gates clear (the lesson's 'must pass BOTH')."""
        return bool(self.no_truncation_pass and self.null_pass) and self.error is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "passes": self.passes,
            "no_truncation_pass": self.no_truncation_pass,
            "null_pass": self.null_pass,
            "is_truncation_artifact": self.is_truncation_artifact,
            "chosen_per_trade": (round(self.chosen_per_trade, 2)
                                 if self.chosen_per_trade is not None else None),
            "chart_stop_only_per_trade": (round(self.chart_stop_only_per_trade, 2)
                                          if self.chart_stop_only_per_trade is not None else None),
            "chosen_premium_stop_pct": self.chosen_premium_stop_pct,
            "n_chosen": self.n_chosen,
            "n_chart_stop_only": self.n_chart_stop_only,
            "null": self.null,
            "null_gate": self.null_gate,
            "reason": self.reason,
            "error": self.error,
        }


def fraud_gate_from_per_trade(
    *,
    chosen_per_trade: Optional[float],
    chart_stop_only_per_trade: Optional[float],
    chosen_premium_stop_pct: float,
    drop_top5_per_trade: Optional[float],
    null: dict,
    n_chosen: int = 0,
    n_chart_stop_only: int = 0,
    chart_stop_pct: float = CHART_STOP_ONLY_PCT,
) -> FraudVerdict:
    """Build a :class:`FraudVerdict` from already-computed per-trade numbers + a null dict.

    Pure (no simulation) — this is the testable core, and the path the verify harness
    uses when a candidate JSON already carries the per-trade + chart-stop-only numbers.

    No-truncation gate: artifact iff the chosen positive cell inverts to negative at
    chart-stop-only with a tight stop (delegates to ``truncation_guard``). Random-null
    gate: ``null_gate`` (beat the null MAX AND drop-top5 beats null MEAN).
    """
    artifact = is_truncation_artifact(
        best_per_trade=chosen_per_trade,
        chart_stop_only_per_trade=chart_stop_only_per_trade,
        best_premium_stop_pct=chosen_premium_stop_pct,
    )
    no_trunc_pass = not artifact

    ng = null_gate(chosen_per_trade, drop_top5_per_trade, null)
    null_pass = bool(ng.get("null_pass"))

    bits = []
    if artifact:
        bits.append(
            f"TRUNCATION ARTIFACT: +${chosen_per_trade}/tr at stop={chosen_premium_stop_pct} "
            f"inverts to ${chart_stop_only_per_trade}/tr at chart-stop-only ({chart_stop_pct}) "
            f"-> the tight stop, not the signal, is the edge (L171)"
        )
    else:
        bits.append(
            f"no-truncation PASS: chart-stop-only ({chart_stop_pct})/tr="
            f"${chart_stop_only_per_trade} holds vs chosen ${chosen_per_trade}/tr"
        )
    if not null_pass:
        bits.append(
            f"RANDOM-NULL FAIL: ${chosen_per_trade}/tr vs null max ${null.get('per_trade_max')} "
            f"mean ${null.get('per_trade_mean')} (drop-top5 ${drop_top5_per_trade}) "
            f"-> a coin-flip entry reproduces it; the edge is the exit bracket (L172)"
        )
    else:
        bits.append(
            f"random-null PASS: ${chosen_per_trade}/tr beats null max ${null.get('per_trade_max')} "
            f"AND drop-top5 ${drop_top5_per_trade} beats null mean ${null.get('per_trade_mean')}"
        )

    return FraudVerdict(
        chosen_per_trade=chosen_per_trade,
        chart_stop_only_per_trade=chart_stop_only_per_trade,
        chosen_premium_stop_pct=chosen_premium_stop_pct,
        is_truncation_artifact=artifact,
        no_truncation_pass=no_trunc_pass,
        null=null,
        null_gate=ng,
        null_pass=null_pass,
        n_chosen=n_chosen,
        n_chart_stop_only=n_chart_stop_only,
        reason=" | ".join(bits),
    )


def verify_candidate(
    signals: Sequence[CandidateSignal],
    rth,
    *,
    strike_offset: int,
    premium_stop_pct: float,
    qty: int = 3,
    setup: str = "FRAUD_GATE",
    seeds: int = NULL_SEEDS,
    chart_stop_pct: float = CHART_STOP_ONLY_PCT,
    sim_fn: Callable = simulate_trade_real,
) -> FraudVerdict:
    """Re-simulate a candidate's signals and run BOTH graduated fraud gates.

    Re-runs ``signals`` at (a) the chosen cell, (b) the SAME strike at chart-stop-only,
    and (c) a random-entry null at the chosen cell (count + call/put mix matched to the
    chosen cell's REALIZED fills). Returns a :class:`FraudVerdict`; ``.passes`` is True
    only when neither fraud gate trips.

    Args:
        signals: the candidate's causal entries (one per CandidateSignal).
        rth: RTH-only frame with a reset RangeIndex + timestamp_et/close/low/high.
        strike_offset, premium_stop_pct: the chosen cell.
        qty: contracts (default 3 = 2 TP + 1 runner).
        seeds: random-null seeds (default 20 per the lesson).
        sim_fn: injectable simulate_trade_real (tests stub it; never stubbed in prod).
    """
    try:
        # (a) chosen cell
        chosen_by_day = _simulate_signals(
            signals, rth, strike_offset=strike_offset, premium_stop_pct=premium_stop_pct,
            qty=qty, setup=setup, sim_fn=sim_fn)
        chosen_pt, drop_top5_pt, n_chosen = _per_trade_and_drop_top5(chosen_by_day)

        # (b) SAME strike at chart-stop-only (the truncation reference)
        loose_by_day = _simulate_signals(
            signals, rth, strike_offset=strike_offset, premium_stop_pct=chart_stop_pct,
            qty=qty, setup=setup, sim_fn=sim_fn)
        loose_pt, _, n_loose = _per_trade_and_drop_top5(loose_by_day)

        # (c) random-entry null at the chosen cell, matched count + realized side mix
        n_call = sum(1 for s in signals if s.side == "C")
        n_put = sum(1 for s in signals if s.side == "P")
        # Match the null's count to FILLED trades (n_chosen), not raw signal count, so
        # the coin-flip benchmark is apples-to-apples with what actually traded.
        n_draw = n_chosen if n_chosen else (n_call + n_put)
        null = random_entry_null(
            rth, n_signals=n_draw, n_call=n_call, n_put=n_put,
            strike_offset=strike_offset, premium_stop_pct=premium_stop_pct,
            qty=qty, setup=f"{setup}_NULL", seeds=seeds, sim_fn=sim_fn)
    except Exception as e:  # fail LOUD into the verdict; never silently bless (C7)
        return FraudVerdict(
            chosen_per_trade=None, chart_stop_only_per_trade=None,
            chosen_premium_stop_pct=premium_stop_pct,
            is_truncation_artifact=False, no_truncation_pass=False,
            null={}, null_gate={}, null_pass=False,
            n_chosen=0, n_chart_stop_only=0,
            reason=f"fraud-gate re-sim error: {e}", error=str(e))

    v = fraud_gate_from_per_trade(
        chosen_per_trade=chosen_pt,
        chart_stop_only_per_trade=loose_pt,
        chosen_premium_stop_pct=premium_stop_pct,
        drop_top5_per_trade=drop_top5_pt,
        null=null,
        n_chosen=n_chosen,
        n_chart_stop_only=n_loose,
        chart_stop_pct=chart_stop_pct,
    )
    return v
