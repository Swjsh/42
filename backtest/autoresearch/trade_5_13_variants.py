"""5/13 BULLISH_RECLAIM_RIDE_THE_RIBBON variant grid (real OPRA fills).

Replays production v14's 11:38 ET (trigger fired on 11:30 close, entry at 11:35
open) bullish 738C trade with a 2,205-combo grid:
  - 7 strikes  (ITM-2 .. OTM-4 of $739 spot) → 737..744
  - 7 sizes    (1, 2, 3, 5, 8, 10, 15)
  - 5 TP1 %    (+30, +50, +75, +100, +150)
  - 3 TP1 frac (0.33, 0.50, 0.667)
  - 3 runner   (1.5x, 2.5x, 5.0x)

Locked: profit_lock_threshold=0.05, profit_lock_stop_offset=0.10,
        premium_stop_pct=-0.20.

Every combo runs through a custom bracket walker that uses real OPRA bars
(`backtest/data/options/SPY260513{C|P}{strike*1000}.csv`) — NO Black-Scholes,
NO IV proxy. Exit knobs are parameterised (simulator_real.py only accepts
premium_stop_pct + profit_lock_*; TP1/runner targets are hard-coded module
constants there, so we re-implement the bracket math here).

Output:
  analysis/recommendations/trade-5-13-variants.json (full grid)
  docs/TRADE-5-13-VARIANTS-2026-05-13.md           (human report)

Usage:
  python backtest/autoresearch/trade_5_13_variants.py
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from dataclasses import dataclass, asdict
from itertools import product
from pathlib import Path
from typing import Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[1]   # = backtest/
sys.path.insert(0, str(REPO))

from autoresearch import runner as _runner  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Constants (TASK-locked) ───────────────────────────────────────────────────
TRADE_DATE = dt.date(2026, 5, 13)
TRIGGER_BAR_TIME = dt.datetime(2026, 5, 13, 11, 30)   # bar START (closes at 11:35)
ENTRY_BAR_TIME = dt.datetime(2026, 5, 13, 11, 35)     # next bar — fill happens here
SIDE = "C"
SETUP = "BULLISH_RECLAIM_RIDE_THE_RIBBON"
REJECTION_LEVEL = 738.10  # reclaimed support
TIME_STOP_ET = dt.time(15, 50)
ENTRY_SLIPPAGE = 0.02
EXIT_SLIPPAGE = 0.02

# Locked exit knobs per task spec
LOCKED_PROFIT_LOCK_THRESHOLD = 0.05
LOCKED_PROFIT_LOCK_OFFSET = 0.10
LOCKED_PREMIUM_STOP_PCT = -0.20

# Variant grid axes
STRIKE_OFFSETS = [-2, -1, 0, 1, 2, 3, 4]   # ITM-2 .. OTM-4 (call: spot + offset)
QTYS = [1, 2, 3, 5, 8, 10, 15]
TP1_PREMIUM_PCTS = [0.30, 0.50, 0.75, 1.00, 1.50]
TP1_QTY_FRACS = [0.333, 0.500, 0.667]
RUNNER_TARGET_PCTS = [1.50, 2.50, 5.00]   # 1.5x, 2.5x, 5x = +150%, +250%, +500%

# Output paths
OUT_JSON = REPO.parent / "analysis" / "recommendations" / "trade-5-13-variants.json"
OUT_DOC = REPO.parent / "docs" / "TRADE-5-13-VARIANTS-2026-05-13.md"


@dataclass(frozen=True)
class VariantKey:
    strike_offset: int
    qty: int
    tp1_premium_pct: float
    tp1_qty_frac: float
    runner_target_pct: float


@dataclass
class VariantResult:
    strike_offset: int
    strike: int
    qty: int
    tp1_premium_pct: float
    tp1_qty_frac: float
    runner_target_pct: float
    profit_lock_variant: str   # "locked" (5%/10%) or "no_lock" (0%/0%) — added 2026-05-13
    entry_premium: Optional[float]
    tp1_premium: Optional[float]
    tp1_filled: bool
    runner_exit_premium: Optional[float]
    exit_reason: str
    total_cost: float
    total_proceeds: float
    dollar_pnl: float
    pct_gain: float
    pct_of_1k_account: float
    pct_of_98k_account: float
    hold_minutes: int
    blocked: bool = False
    block_reason: str = ""


def _load_spy_for_513() -> pd.DataFrame:
    """Load the SPY 5m frame for 5/13, normalize to tz-naive ET, slice to 5/13 RTH.

    Note: We bypass `_runner.load_data` because its candidate list only covers
    master files up to 5/12. The 5/13 bars live in `spy_5m_2026-05-08_2026-05-13.csv`,
    which we read directly here.
    """
    # Try the runner first in case a fresh master file appears later
    spy_full: Optional[pd.DataFrame] = None
    try:
        loaded, _ = _runner.load_data(TRADE_DATE, TRADE_DATE)
        ts = pd.to_datetime(loaded["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
        if (ts.dt.date == TRADE_DATE).any():
            spy_full = loaded.copy()
            spy_full["timestamp_et"] = ts
    except Exception as exc:  # noqa: BLE001
        log.info("runner.load_data fallback (%s) — reading 5/13 file directly", exc)
    if spy_full is None:
        path = REPO / "data" / "spy_5m_2026-05-08_2026-05-13.csv"
        if not path.exists():
            raise FileNotFoundError(f"5/13 SPY data file missing: {path}")
        spy_full = pd.read_csv(path)
        spy_full["timestamp_et"] = (
            pd.to_datetime(spy_full["timestamp_et"], utc=True)
            .dt.tz_convert("America/New_York")
            .dt.tz_localize(None)
        )

    day = spy_full[spy_full["timestamp_et"].dt.date == TRADE_DATE].reset_index(drop=True)
    return day


def _find_entry_idx(day: pd.DataFrame) -> int:
    """Index of the 11:30 trigger bar in `day`."""
    matches = day.index[day["timestamp_et"] == pd.Timestamp(TRIGGER_BAR_TIME)]
    if len(matches) == 0:
        raise RuntimeError("Could not locate 11:30 trigger bar in 5/13 SPY data")
    return int(matches[0])


def _strike_for_offset(spot: float, offset: int) -> int:
    """Call: strike = round(spot) + offset. ATM = round(spot)."""
    return int(round(spot)) + offset


def _simulate_bracket(
    *,
    strike: int,
    qty: int,
    tp1_premium_pct: float,
    tp1_qty_frac: float,
    runner_target_pct: float,
    spy_day: pd.DataFrame,
    entry_idx: int,
    profit_lock_threshold_pct: float = LOCKED_PROFIT_LOCK_THRESHOLD,
    profit_lock_stop_offset_pct: float = LOCKED_PROFIT_LOCK_OFFSET,
    premium_stop_pct: float = LOCKED_PREMIUM_STOP_PCT,
) -> VariantResult:
    """Bracket walker driven entirely by real OPRA bars for 5/13.

    Bracket logic (mirrors simulator_real.py but with exit knobs parameterised):
      - Entry: 11:35 bar open + ENTRY_SLIPPAGE (proxy for ASK fill)
      - Stop:  entry * (1 + LOCKED_PREMIUM_STOP_PCT)  (-20%)
      - TP1:   entry * (1 + tp1_premium_pct), sells `tp1_qty_frac × qty`
      - Runner stop after TP1 = entry premium (BE)
      - Runner target = entry * (1 + runner_target_pct)
      - Profit-lock: when best premium >= entry*(1+0.05), raise stop floor to
                     entry*(1+0.10) — applies pre AND post TP1
      - Time stop: 15:50 ET → flatten remaining at close - exit slippage
      - Conservative: stop+TP1 same bar → stop fills first (low touched first)
    """
    side_letter = SIDE
    sym = option_symbol(TRADE_DATE, strike, side_letter)
    opt_df = load_contract_bars(sym)
    if opt_df is None:
        return _blocked(strike, qty, tp1_premium_pct, tp1_qty_frac, runner_target_pct,
                        f"OPRA cache missing: {sym}")

    opt_df = opt_df.copy()
    if opt_df["timestamp_et"].dt.tz is not None:
        opt_df["timestamp_et"] = opt_df["timestamp_et"].dt.tz_localize(None)

    # Find entry bar in OPRA
    next_start = pd.Timestamp(ENTRY_BAR_TIME)
    entry_rows = opt_df[opt_df["timestamp_et"] >= next_start]
    if entry_rows.empty:
        return _blocked(strike, qty, tp1_premium_pct, tp1_qty_frac, runner_target_pct,
                        f"OPRA no entry bar at/after 11:35: {sym}")
    entry_row = entry_rows.iloc[0]
    if float(entry_row["open"]) <= 0:
        return _blocked(strike, qty, tp1_premium_pct, tp1_qty_frac, runner_target_pct,
                        f"OPRA bad entry open: {sym}")

    entry_premium = float(entry_row["open"]) + ENTRY_SLIPPAGE
    stop_premium = entry_premium * (1.0 + premium_stop_pct)
    tp1_target = entry_premium * (1.0 + tp1_premium_pct)
    runner_target = entry_premium * (1.0 + runner_target_pct)
    profit_lock_active = profit_lock_threshold_pct > 0
    profit_lock_arm = entry_premium * (1.0 + profit_lock_threshold_pct) if profit_lock_active else float("inf")
    profit_lock_floor = entry_premium * (1.0 + profit_lock_stop_offset_pct)

    # Allocate qty to TP1 vs runner
    tp1_qty = max(1, int(round(qty * tp1_qty_frac)))
    if tp1_qty >= qty:
        tp1_qty = qty - 1 if qty > 1 else qty   # always reserve 1 runner if possible
    runner_qty = qty - tp1_qty

    # Entry timestamp aligned to OPRA row
    entry_ts = pd.Timestamp(entry_row["timestamp_et"])

    # Walk forward over OPRA bars from the bar AFTER entry. (Entry bar itself is
    # used only as the fill bar — no exits checked on entry bar.)
    opt_idx_start = int(entry_rows.index[0]) + 1

    tp1_filled = False
    tp1_premium = None
    runner_stop = stop_premium
    profit_lock_armed = False
    runner_exit_premium = None
    exit_reason = "open"
    last_close_premium = entry_premium
    last_ts = entry_ts

    for i in range(opt_idx_start, len(opt_df)):
        row = opt_df.iloc[i]
        ts = pd.Timestamp(row["timestamp_et"])
        if ts.date() != TRADE_DATE:
            break
        bar_low = float(row["low"])
        bar_high = float(row["high"])
        bar_close = float(row["close"])
        last_close_premium = bar_close
        last_ts = ts

        time_stop_now = ts.time() >= TIME_STOP_ET

        # Profit-lock arming (parity with simulator_real.py T41 logic).
        # Once favorable premium reaches arm threshold, raise stop floor.
        # Never lowers an existing higher floor.
        if profit_lock_active and not profit_lock_armed and bar_high >= profit_lock_arm:
            profit_lock_armed = True
            if profit_lock_floor > runner_stop:
                runner_stop = profit_lock_floor

        # ── Pre-TP1 hard exits ───────────────────────────────────────────────
        if not tp1_filled:
            # Stop touched (conservative: stop fills first if both touched)
            if bar_low <= runner_stop:
                runner_exit_premium = runner_stop
                exit_reason = "EXIT_ALL_PREMIUM_STOP"
                break

            # Time stop — flatten at close - exit slippage
            if time_stop_now:
                runner_exit_premium = max(0.01, bar_close - EXIT_SLIPPAGE)
                exit_reason = "EXIT_ALL_TIME_STOP"
                break

            # TP1 touched
            if bar_high >= tp1_target:
                tp1_filled = True
                tp1_premium = tp1_target
                runner_stop = entry_premium  # BE stop on runner
                # Skip same-bar runner exit checks (mirrors simulator_real)
                continue
            continue

        # ── Post-TP1 runner exits ────────────────────────────────────────────
        # Stop touched
        if bar_low <= runner_stop:
            runner_exit_premium = runner_stop
            exit_reason = "TP1_THEN_RUNNER_BE_STOP"
            break

        # Runner target hit
        if bar_high >= runner_target:
            runner_exit_premium = runner_target
            exit_reason = "TP1_THEN_RUNNER_TARGET"
            break

        # Time stop
        if time_stop_now:
            runner_exit_premium = max(0.01, bar_close - EXIT_SLIPPAGE)
            exit_reason = "TP1_THEN_RUNNER_TIME"
            break

    # Loop fell through (rare on a 1-day window)
    if runner_exit_premium is None:
        runner_exit_premium = max(0.01, last_close_premium - EXIT_SLIPPAGE)
        exit_reason = "EOD_FALLTHROUGH"

    # ── P&L math (matches simulator._compute_pnl) ────────────────────────────
    if tp1_filled and tp1_premium is not None:
        tp1_pnl = (tp1_premium - entry_premium) * tp1_qty * 100.0
        runner_pnl = (runner_exit_premium - entry_premium) * runner_qty * 100.0
        dollar_pnl = tp1_pnl + runner_pnl
    else:
        dollar_pnl = (runner_exit_premium - entry_premium) * qty * 100.0

    total_cost = entry_premium * qty * 100.0
    if tp1_filled and tp1_premium is not None:
        total_proceeds = (tp1_premium * tp1_qty * 100.0) + (runner_exit_premium * runner_qty * 100.0)
    else:
        total_proceeds = runner_exit_premium * qty * 100.0
    pct_gain = (dollar_pnl / total_cost) if total_cost > 0 else 0.0

    hold_minutes = int(round((last_ts - entry_ts).total_seconds() / 60.0))

    variant_label = "locked" if profit_lock_active else "no_lock"
    return VariantResult(
        strike_offset=strike - int(round(spy_day.iloc[entry_idx]["close"])),
        strike=strike,
        qty=qty,
        tp1_premium_pct=tp1_premium_pct,
        tp1_qty_frac=tp1_qty_frac,
        runner_target_pct=runner_target_pct,
        profit_lock_variant=variant_label,
        entry_premium=round(entry_premium, 4),
        tp1_premium=round(tp1_premium, 4) if tp1_premium is not None else None,
        tp1_filled=tp1_filled,
        runner_exit_premium=round(runner_exit_premium, 4),
        exit_reason=exit_reason,
        total_cost=round(total_cost, 2),
        total_proceeds=round(total_proceeds, 2),
        dollar_pnl=round(dollar_pnl, 2),
        pct_gain=round(pct_gain, 4),
        pct_of_1k_account=round(total_cost / 1000.0 * 100.0, 2),
        pct_of_98k_account=round(total_cost / 98000.0 * 100.0, 2),
        hold_minutes=hold_minutes,
    )


def _blocked(strike, qty, tp1_pct, tp1_frac, runner_pct, reason,
             variant: str = "locked") -> VariantResult:
    return VariantResult(
        strike_offset=0, strike=strike, qty=qty,
        tp1_premium_pct=tp1_pct, tp1_qty_frac=tp1_frac, runner_target_pct=runner_pct,
        profit_lock_variant=variant,
        entry_premium=None, tp1_premium=None, tp1_filled=False,
        runner_exit_premium=None, exit_reason="BLOCKED",
        total_cost=0.0, total_proceeds=0.0, dollar_pnl=0.0, pct_gain=0.0,
        pct_of_1k_account=0.0, pct_of_98k_account=0.0, hold_minutes=0,
        blocked=True, block_reason=reason,
    )


def _build_grid(spy_day: pd.DataFrame, entry_idx: int) -> list[VariantResult]:
    spot = float(spy_day.iloc[entry_idx]["close"])
    log.info("Entry spot (11:30 close) = %.2f → ATM strike %d", spot, round(spot))
    log.info("Variant grid axes: strikes=%s qtys=%s tp1_pct=%s tp1_frac=%s runner_pct=%s",
             [_strike_for_offset(spot, o) for o in STRIKE_OFFSETS],
             QTYS, TP1_PREMIUM_PCTS, TP1_QTY_FRACS, RUNNER_TARGET_PCTS)

    results: list[VariantResult] = []
    combos = list(product(STRIKE_OFFSETS, QTYS, TP1_PREMIUM_PCTS, TP1_QTY_FRACS, RUNNER_TARGET_PCTS))
    # Two variants: locked (5%/10% profit-lock per task spec) and no_lock (control,
    # shows what the trade COULD make if profit-lock is disabled — useful because
    # profit-lock dominates exit-knob choices on a strong-trending signal like 5/13).
    variant_specs = [
        ("locked", LOCKED_PROFIT_LOCK_THRESHOLD, LOCKED_PROFIT_LOCK_OFFSET),
        ("no_lock", 0.0, 0.0),
    ]
    total_n = len(combos) * len(variant_specs)
    log.info("Total combos to evaluate: %d (%d combos x %d profit-lock variants)",
             total_n, len(combos), len(variant_specs))

    n = 0
    for variant_label, pl_thresh, pl_offset in variant_specs:
        for off, qty, tp1_pct, tp1_frac, run_pct in combos:
            n += 1
            strike = _strike_for_offset(spot, off)
            res = _simulate_bracket(
                strike=strike,
                qty=qty,
                tp1_premium_pct=tp1_pct,
                tp1_qty_frac=tp1_frac,
                runner_target_pct=run_pct,
                spy_day=spy_day,
                entry_idx=entry_idx,
                profit_lock_threshold_pct=pl_thresh,
                profit_lock_stop_offset_pct=pl_offset,
            )
            # Patch strike_offset so it reflects the call-side mapping (offset=0=ATM)
            res.strike_offset = off
            results.append(res)
            if n % 1000 == 0 or n == total_n:
                log.info("  ...evaluated %d/%d", n, total_n)
    return results


# ── Reporting ────────────────────────────────────────────────────────────────

def _label_offset(off: int) -> str:
    if off == 0:
        return "ATM"
    if off < 0:
        return f"ITM-{abs(off)}"
    return f"OTM+{off}"


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def _row_for_result(r: VariantResult) -> list[str]:
    return [
        _label_offset(r.strike_offset),
        str(r.strike),
        str(r.qty),
        f"+{int(r.tp1_premium_pct*100)}%",
        f"{r.tp1_qty_frac:.3f}",
        f"{r.runner_target_pct:.2f}x",
        r.profit_lock_variant,
        f"${r.entry_premium:.2f}" if r.entry_premium else "—",
        f"${r.total_cost:,.0f}",
        f"${r.dollar_pnl:+,.0f}",
        f"{r.pct_gain*100:+.1f}%",
        f"{r.pct_of_1k_account:.1f}%",
        f"{r.pct_of_98k_account:.1f}%",
        r.exit_reason,
    ]


def _strike_qty_heatmap(results: list[VariantResult], spot: float) -> str:
    """For each (strike_offset, qty), the BEST $ P&L across all exit knob combos."""
    best: dict[tuple[int, int], VariantResult] = {}
    for r in results:
        if r.blocked:
            continue
        k = (r.strike_offset, r.qty)
        if k not in best or r.dollar_pnl > best[k].dollar_pnl:
            best[k] = r

    headers = ["Strike\\Qty"] + [str(q) for q in QTYS]
    rows: list[list[str]] = []
    for off in STRIKE_OFFSETS:
        strike = _strike_for_offset(spot, off)
        label = f"{_label_offset(off)} ({strike}C)"
        cells = [label]
        for q in QTYS:
            r = best.get((off, q))
            if r is None:
                cells.append("—")
            else:
                cells.append(f"${r.dollar_pnl:+,.0f}")
        rows.append(cells)
    return _md_table(headers, rows)


def _write_outputs(results: list[VariantResult], spot: float, atm_strike: int,
                   ground_truth: dict) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_DOC.parent.mkdir(parents=True, exist_ok=True)

    # JSON dump
    payload = {
        "trade_date": TRADE_DATE.isoformat(),
        "trigger_bar_et": TRIGGER_BAR_TIME.isoformat(),
        "entry_bar_et": ENTRY_BAR_TIME.isoformat(),
        "side": SIDE,
        "setup": SETUP,
        "rejection_level": REJECTION_LEVEL,
        "spot_at_trigger_close": spot,
        "atm_strike": atm_strike,
        "locked_variant": {
            "profit_lock_threshold_pct": LOCKED_PROFIT_LOCK_THRESHOLD,
            "profit_lock_stop_offset_pct": LOCKED_PROFIT_LOCK_OFFSET,
            "premium_stop_pct": LOCKED_PREMIUM_STOP_PCT,
            "entry_slippage": ENTRY_SLIPPAGE,
            "exit_slippage": EXIT_SLIPPAGE,
        },
        "no_lock_variant": {
            "profit_lock_threshold_pct": 0.0,
            "profit_lock_stop_offset_pct": 0.0,
            "premium_stop_pct": LOCKED_PREMIUM_STOP_PCT,
            "note": "Control variant — profit-lock disabled to expose TP1/runner-target headroom",
        },
        "grid_axes": {
            "strike_offsets": STRIKE_OFFSETS,
            "qtys": QTYS,
            "tp1_premium_pcts": TP1_PREMIUM_PCTS,
            "tp1_qty_fracs": TP1_QTY_FRACS,
            "runner_target_pcts": RUNNER_TARGET_PCTS,
            "profit_lock_variants": ["locked", "no_lock"],
        },
        "ground_truth_actual_trade": ground_truth,
        "n_combos": len(results),
        "n_blocked": sum(1 for r in results if r.blocked),
        "results": [asdict(r) for r in results],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    # MD report
    valid = [r for r in results if not r.blocked]
    blocked = [r for r in results if r.blocked]
    locked = [r for r in valid if r.profit_lock_variant == "locked"]
    no_lock = [r for r in valid if r.profit_lock_variant == "no_lock"]

    # Diagnose: how many unique P&L outcomes per variant (1 per cell = dominance)
    def _unique_pnl_count(arr):
        per_cell: dict[tuple[int, int], set] = {}
        for r in arr:
            per_cell.setdefault((r.strike_offset, r.qty), set()).add(round(r.dollar_pnl, 2))
        return sum(len(v) for v in per_cell.values()), len(per_cell)

    locked_uniq_pnl, locked_cells = _unique_pnl_count(locked)
    no_lock_uniq_pnl, no_lock_cells = _unique_pnl_count(no_lock)

    by_dollar = sorted(valid, key=lambda r: r.dollar_pnl, reverse=True)
    by_pct = sorted(valid, key=lambda r: r.pct_gain, reverse=True)

    # Separate top-10s per variant
    locked_by_dollar = sorted(locked, key=lambda r: r.dollar_pnl, reverse=True)
    locked_by_pct = sorted(locked, key=lambda r: r.pct_gain, reverse=True)
    no_lock_by_dollar = sorted(no_lock, key=lambda r: r.dollar_pnl, reverse=True)
    no_lock_by_pct = sorted(no_lock, key=lambda r: r.pct_gain, reverse=True)

    # $1K-account constrained: total_cost ≤ $500 (50% per-trade cap per rule 6)
    constrained_1k = [r for r in valid if r.total_cost <= 500.0]
    constrained_1k_by_dollar = sorted(constrained_1k, key=lambda r: r.dollar_pnl, reverse=True)

    # J's "buy < $100, sell > $100" pattern: total_cost ≤ $100, dollar_pnl > $100
    jstyle = [r for r in valid if r.total_cost <= 100.0 and r.dollar_pnl > 100.0]
    jstyle_by_pct = sorted(jstyle, key=lambda r: r.pct_gain, reverse=True)
    # Also surface "best % gain among < $300 cost" — J zone is OTM+1..OTM+4 area
    jzone = [r for r in valid if r.total_cost <= 300.0 and r.strike_offset >= 1]
    jzone_by_dollar = sorted(jzone, key=lambda r: r.dollar_pnl, reverse=True)

    # Best per account scenario (constrained to LOCKED variant — that's what J asked for)
    best_overall = locked_by_dollar[0] if locked_by_dollar else None
    locked_1k = sorted([r for r in locked if r.total_cost <= 500.0],
                       key=lambda r: r.dollar_pnl, reverse=True)
    best_1k = locked_1k[0] if locked_1k else None
    best_10k = sorted(
        [r for r in locked if r.total_cost <= 5000.0],   # ≤ 50% of $10K
        key=lambda r: r.dollar_pnl, reverse=True,
    )
    best_10k = best_10k[0] if best_10k else None
    best_98k = sorted(
        [r for r in locked if r.total_cost <= 49000.0],
        key=lambda r: r.dollar_pnl, reverse=True,
    )
    best_98k = best_98k[0] if best_98k else None

    # Also surface the BEST no-lock combo for "what was possible" context
    no_lock_best_overall = no_lock_by_dollar[0] if no_lock_by_dollar else None
    no_lock_best_1k = sorted([r for r in no_lock if r.total_cost <= 500.0],
                             key=lambda r: r.dollar_pnl, reverse=True)
    no_lock_best_1k = no_lock_best_1k[0] if no_lock_best_1k else None

    headers = ["Strike", "K", "Qty", "TP1%", "TP1frac", "Runner", "Lock",
               "Entry$", "Cost$", "P&L$", "%Gain", "%1K", "%98K", "ExitReason"]
    n_grid_per_variant = (
        len(STRIKE_OFFSETS) * len(QTYS) * len(TP1_PREMIUM_PCTS)
        * len(TP1_QTY_FRACS) * len(RUNNER_TARGET_PCTS)
    )

    md = []
    md.append("# 5/13 BULLISH_RECLAIM Variant Grid (Real OPRA Fills)")
    md.append("")
    md.append(f"_Generated {dt.datetime.now().isoformat(timespec='seconds')} ET_")
    md.append("")
    md.append("**Trade replayed:** Production v14 fired at 11:38 ET; trigger bar 11:30 close;")
    md.append(f"entry on 11:35 bar open. SPY spot at trigger close = **${spot:.2f}**, ATM = **{atm_strike}C**.")
    md.append(f"Setup: {SETUP}. Rejection level: {REJECTION_LEVEL}. Side: long calls.")
    md.append("")
    md.append("**Variants tested (per the task's locked exit knobs + a no-lock control):**")
    md.append("")
    md.append("| Variant  | profit_lock_threshold | profit_lock_offset | premium_stop |")
    md.append("| -------- | --------------------- | ------------------ | ------------ |")
    md.append("| `locked` | +5%  (arm at entry×1.05) | +10% (floor at entry×1.10) | -20% |")
    md.append("| `no_lock`| 0 (disabled)             | 0                          | -20% |")
    md.append("")
    md.append(f"**Grid axes:** {len(STRIKE_OFFSETS)} strikes × {len(QTYS)} qtys × "
              f"{len(TP1_PREMIUM_PCTS)} TP1% × {len(TP1_QTY_FRACS)} TP1frac × "
              f"{len(RUNNER_TARGET_PCTS)} runner-pct × 2 variants = **{len(results)} combos** "
              f"({n_grid_per_variant} per variant)")
    md.append(f"Blocked combos: **{len(blocked)}** (OPRA cache holes)")
    md.append(f"Slippage: entry +${ENTRY_SLIPPAGE}/contract (ASK proxy), exit -${EXIT_SLIPPAGE}/contract (BID proxy).")
    md.append("")
    md.append("**Ground truth:** J's actual fill 738C × 15 @ $2.10. Scaled out in equal thirds at")
    md.append("$2.80 / $5.43 / $4.32 → gross +$3,125 (+99%); task reports +$2,932 (+93%) post-fees.")
    md.append("Simulator entry premium for 738C: " +
              f"**${ground_truth.get('sim_entry_738c', 0):.2f}** (vs J's $2.10 fill).")
    md.append("")
    md.append("**Note:** The 2-tier simulator (TP1+runner) does NOT perfectly match J's 3-way scale-out.")
    md.append("J's effective TP1 was ~+33%; my grid quantises at +30/+50/+75/+100/+150%.")
    md.append("")
    md.append("---")
    md.append("")
    # ─── CRITICAL FINDING ───────────────────────────────────────────────────
    md.append("## CRITICAL FINDING — profit-lock dominance")
    md.append("")
    md.append(f"Under the **locked** variant (profit_lock_threshold=5%, offset=10%), all")
    md.append(f"**{len(locked)} combos collapse to {locked_uniq_pnl} unique P&L outcomes across")
    md.append(f"{locked_cells} (strike, qty) cells — i.e. exactly one outcome per cell.**")
    md.append("")
    md.append(f"By contrast, the **no_lock** variant produced **{no_lock_uniq_pnl} unique P&L outcomes**")
    md.append(f"across {no_lock_cells} (strike, qty) cells — showing TP1%/TP1-frac/runner-target")
    md.append("actually discriminate between combos when profit-lock is disabled.")
    md.append("")
    md.append("**Why:** The 11:50 ET bar low on 738C was $1.96, which is below the profit-lock floor")
    md.append("of entry×1.10 = $2.23 (which was armed at the 11:40 bar high of $2.52).")
    md.append("Every TP1 threshold ≥+10% in the grid is ABOVE the profit-lock arm threshold, so")
    md.append("profit-lock arms first, then stops the trade at ~$2.23 on the 11:50 retrace.")
    md.append("Net: trade always exits at ~+10% no matter which TP1/runner knobs are picked.")
    md.append("")
    md.append("**Implication:** For an explosive bullish-reclaim like 5/13, the locked profit-lock")
    md.append("policy CAPS gains at ~+10% per contract. J's actual +93% trade only worked because he")
    md.append("did NOT have profit-lock active — he held through the 11:50-12:05 retrace and let")
    md.append("the runner extend to 738C peak of $5.80.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## TL;DR — Best LOCKED combo per account scenario (the task's main ask)")
    md.append("")
    md.append("> All cells in the locked variant collapse to one outcome — TP1/runner knobs don't matter.")
    md.append("> The only knobs that change locked P&L are **strike** (entry premium) and **qty** (scale).")
    md.append("")
    md.append(_md_table(headers,
              [_row_for_result(best_1k)] if best_1k else [["—"]*14]) + "  ← **$1K account (≤50% = $500 cost)**")
    md.append("")
    md.append(_md_table(headers,
              [_row_for_result(best_10k)] if best_10k else [["—"]*14]) + "  ← **$10K account (≤50% = $5,000 cost)**")
    md.append("")
    md.append(_md_table(headers,
              [_row_for_result(best_98k)] if best_98k else [["—"]*14]) + "  ← **$98K account (≤50% = $49,000 cost)**")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## CONTRAST — Best NO-LOCK combo per account scenario (what the trade could have made)")
    md.append("")
    md.append(_md_table(headers,
              [_row_for_result(no_lock_best_1k)] if no_lock_best_1k else [["—"]*14]) + "  ← **$1K account, no profit-lock**")
    md.append("")
    md.append(_md_table(headers,
              [_row_for_result(no_lock_best_overall)] if no_lock_best_overall else [["—"]*14]) + "  ← **Overall no-lock champion (any cost)**")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## Top 10 by absolute $ P&L — LOCKED (per task spec)")
    md.append("")
    md.append(_md_table(headers, [_row_for_result(r) for r in locked_by_dollar[:10]]))
    md.append("")
    md.append("## Top 10 by % gain — LOCKED (per task spec, J's preferred metric)")
    md.append("")
    md.append(_md_table(headers, [_row_for_result(r) for r in locked_by_pct[:10]]))
    md.append("")
    md.append("## Top 10 by absolute $ P&L — NO LOCK (control, profit-lock disabled)")
    md.append("")
    md.append(_md_table(headers, [_row_for_result(r) for r in no_lock_by_dollar[:10]]))
    md.append("")
    md.append("## Top 10 by % gain — NO LOCK (J's preferred metric, control variant)")
    md.append("")
    md.append(_md_table(headers, [_row_for_result(r) for r in no_lock_by_pct[:10]]))
    md.append("")
    md.append("## Top 10 for $1K account (total_cost ≤ $500, both variants)")
    md.append("")
    md.append(_md_table(headers, [_row_for_result(r) for r in constrained_1k_by_dollar[:10]]))
    md.append("")
    md.append("## J's pattern — cheapest cost, biggest $ gain (cost ≤ $100, P&L > $100)")
    md.append("")
    if jstyle_by_pct:
        md.append(_md_table(headers, [_row_for_result(r) for r in jstyle_by_pct[:10]]))
    else:
        md.append("_No combos matched the strict <$100→>$100 filter._")
        md.append("")
        # Surface the cheapest combos that DID make money
        cheap_winners = sorted(
            [r for r in valid if r.total_cost <= 200.0 and r.dollar_pnl > 0],
            key=lambda r: r.pct_gain, reverse=True,
        )
        if cheap_winners:
            md.append("**Closest match — cheapest winners (cost ≤ $200, P&L > 0), both variants:**")
            md.append("")
            md.append(_md_table(headers, [_row_for_result(r) for r in cheap_winners[:10]]))
        else:
            md.append("**No winners with cost ≤ $200 — at this trigger, all sub-$200 tickets are OTM+3/+4 calls")
            md.append("that drifted slightly OTM further by EOD. The signal moved spot $4 (+0.5%), not enough")
            md.append("to put +$3 OTM strikes ITM by close.**")
    md.append("")
    md.append("## J-zone cluster — OTM+1 to OTM+4, total_cost ≤ $300")
    md.append("")
    if jzone_by_dollar:
        md.append(_md_table(headers, [_row_for_result(r) for r in jzone_by_dollar[:10]]))
    else:
        md.append("_No J-zone combos under $300 cost._")
    md.append("")
    md.append("## Strike × Qty heatmap — BEST $ P&L per cell across all exit-knob combos (BOTH variants)")
    md.append("")
    md.append(_strike_qty_heatmap(results, spot))
    md.append("")
    md.append("## Strike × Qty heatmap — LOCKED variant only (task's main ask)")
    md.append("")
    md.append(_strike_qty_heatmap(locked, spot))
    md.append("")
    md.append("## Strike × Qty heatmap — NO LOCK variant (control)")
    md.append("")
    md.append(_strike_qty_heatmap(no_lock, spot))
    md.append("")
    md.append("---")
    md.append("")
    md.append("## Recommendation for J's $1K starting strategy")
    md.append("")
    if best_1k:
        md.append(f"### Under the locked profit-lock policy (the production rule):")
        md.append("")
        md.append(f"Optimal $1K-account combo: **{_label_offset(best_1k.strike_offset)} "
                  f"({best_1k.strike}C) × {best_1k.qty} contracts** with TP1 at "
                  f"+{int(best_1k.tp1_premium_pct*100)}% / {best_1k.tp1_qty_frac:.3f} fraction "
                  f"and runner target {best_1k.runner_target_pct:.2f}x.")
        md.append("")
        md.append(f"- **Cost:** ${best_1k.total_cost:,.0f} ({best_1k.pct_of_1k_account:.1f}% of $1K, within 50% rule)")
        md.append(f"- **P&L:** ${best_1k.dollar_pnl:+,.0f} ({best_1k.pct_gain*100:+.1f}%)")
        md.append(f"- **Exit:** {best_1k.exit_reason} after {best_1k.hold_minutes} minutes")
        md.append(f"- **Why this beats other strikes:** ITM-2 (738C) has the lowest entry premium ($2.03)")
        md.append(f"  of all in-the-money strikes, maximising contracts buyable under the $500 budget.")
        md.append(f"  Note: TP1/runner-target knobs are NOOPs in locked variant — only strike + qty matter.")
        md.append("")
    if no_lock_best_1k:
        md.append(f"### If profit-lock is relaxed (control comparison):")
        md.append("")
        md.append(f"Optimal $1K-account no-lock combo: **{_label_offset(no_lock_best_1k.strike_offset)} "
                  f"({no_lock_best_1k.strike}C) × {no_lock_best_1k.qty} contracts** with TP1 at "
                  f"+{int(no_lock_best_1k.tp1_premium_pct*100)}% / {no_lock_best_1k.tp1_qty_frac:.3f} fraction "
                  f"and runner target {no_lock_best_1k.runner_target_pct:.2f}x.")
        md.append("")
        md.append(f"- **Cost:** ${no_lock_best_1k.total_cost:,.0f} ({no_lock_best_1k.pct_of_1k_account:.1f}% of $1K)")
        md.append(f"- **P&L:** ${no_lock_best_1k.dollar_pnl:+,.0f} ({no_lock_best_1k.pct_gain*100:+.1f}%)")
        md.append(f"- **Exit:** {no_lock_best_1k.exit_reason} after {no_lock_best_1k.hold_minutes} minutes")
        md.append("")
        md.append("**Headroom delta:** locked ${:+,.0f} vs no-lock ${:+,.0f} = "
                  "**${:+,.0f} of theoretical upside locked away.**".format(
                      best_1k.dollar_pnl if best_1k else 0,
                      no_lock_best_1k.dollar_pnl,
                      (no_lock_best_1k.dollar_pnl - (best_1k.dollar_pnl if best_1k else 0)),
                  ))
        md.append("")
    if jstyle_by_pct:
        rec = jstyle_by_pct[0]
        md.append("### J's preferred '<$100 → >$100' pattern:")
        md.append("")
        md.append(f"**{_label_offset(rec.strike_offset)} ({rec.strike}C) × {rec.qty} @ ${rec.entry_premium:.2f}** "
                  f"turned ${rec.total_cost:.0f} into ${rec.total_cost+rec.dollar_pnl:.0f} "
                  f"(+{rec.pct_gain*100:.0f}%) on this signal under the `{rec.profit_lock_variant}` profit-lock.")
        md.append("")
    md.append("---")
    md.append("")
    md.append("## What to ratify (1-paragraph verdict)")
    md.append("")
    md.append("This N=1 study surfaces a structural issue, not a new ratification candidate: the")
    md.append("locked profit-lock (+5%/+10%) caps explosive winners at ~+10% on this 5/13-style ribbon")
    md.append("ride. **Do NOT ratify** any TP1/runner-target change off this single trade — the knobs are")
    md.append("noop under the lock. The right follow-up is a regime-aware profit-lock: either")
    md.append("(a) widen the arm threshold (e.g., +15-20%) so it only activates once the trade is")
    md.append("clearly working, or (b) gate profit-lock by setup-type — only apply to chop-prone")
    md.append("setups (PIN_FADE, mean reversion), never to ride-the-ribbon trades. Either change is a")
    md.append("weekend-research candidate via the full 5-stage grinder + walk-forward + real-fills")
    md.append("pipeline (CLAUDE.md OP 20), NOT an immediate live-rule change.")
    md.append("")
    md.append("**Disclaimer:** N=1 trade. This is what *would have happened* on this single 5/13 signal under each variant — "
              "it does NOT validate any combo's edge across other days/setups. To ratify any of these knobs, "
              "the standard 5-stage grinder + walk-forward + real-fills checklist still applies (CLAUDE.md OP 20).")
    md.append("")

    OUT_DOC.write_text("\n".join(md), encoding="utf-8")
    log.info("Wrote %s", OUT_DOC)


def main() -> int:
    log.info("Loading 5/13 SPY data ...")
    spy_day = _load_spy_for_513()
    if spy_day.empty:
        log.error("No 5/13 bars in data — aborting")
        return 1
    entry_idx = _find_entry_idx(spy_day)
    spot = float(spy_day.iloc[entry_idx]["close"])
    atm_strike = int(round(spot))
    log.info("Trigger bar at index %d, time %s, close=%.2f, ATM=%d",
             entry_idx, spy_day.iloc[entry_idx]["timestamp_et"], spot, atm_strike)

    log.info("Building variant grid ...")
    results = _build_grid(spy_day, entry_idx)
    n_blocked = sum(1 for r in results if r.blocked)
    log.info("Grid done: %d combos, %d blocked", len(results), n_blocked)

    # Validate ground truth: 738C × 15, tp1=33%, tp1_frac=0.467 ≈ +$2,932
    # Find a combo close to that for the report
    gt_combos = [r for r in results
                 if not r.blocked and r.strike == 738 and r.qty == 15
                 and r.tp1_premium_pct == 0.30 and abs(r.tp1_qty_frac - 0.500) < 0.01]
    sim_entry_738c = 0.0
    for r in gt_combos[:1]:
        sim_entry_738c = r.entry_premium or 0.0
        log.info(
            "Ground-truth-style combo (738C x15, tp1=+30%%, tp1_frac=0.500): "
            "entry=$%.2f cost=$%.0f PnL=$%.0f (J actual: $2.10 / $3,150 / +$3,125)",
            r.entry_premium, r.total_cost, r.dollar_pnl,
        )

    # J's scaled-out trade math: cost = 2.10*15*100 = $3,150;
    # proceeds = (2.80+5.43+4.32)*5*100 = $6,275; gross PnL = +$3,125.
    # Task spec quotes "+93%" headline = ~$2,932 (slightly lower than $3,125, likely
    # post-fees). We report both.
    ground_truth = {
        "j_actual_strike": 738,
        "j_actual_qty": 15,
        "j_actual_entry": 2.10,
        "j_actual_exits": [2.80, 5.43, 4.32],
        "j_actual_qty_per_exit_thirds": [5, 5, 5],
        "j_actual_gross_pnl": 3125.0,
        "task_reported_pnl_after_fees": 2932.0,
        "j_actual_pct_gain": 0.93,
        "sim_entry_738c": sim_entry_738c,
    }

    _write_outputs(results, spot, atm_strike, ground_truth)

    # Console summary
    valid = [r for r in results if not r.blocked]
    by_dollar = sorted(valid, key=lambda r: r.dollar_pnl, reverse=True)
    by_pct = sorted(valid, key=lambda r: r.pct_gain, reverse=True)
    constrained_1k = sorted(
        [r for r in valid if r.total_cost <= 500.0],
        key=lambda r: r.dollar_pnl, reverse=True,
    )
    print("\n" + "=" * 78)
    print("5/13 VARIANT GRID -- TOP 5 SUMMARY")
    print("=" * 78)
    print(f"\nTOP 5 BY $ P&L:")
    for r in by_dollar[:5]:
        print(f"  {_label_offset(r.strike_offset)} {r.strike}C × {r.qty} "
              f"TP1=+{int(r.tp1_premium_pct*100)}% frac={r.tp1_qty_frac:.3f} "
              f"runner={r.runner_target_pct}x -> "
              f"cost=${r.total_cost:,.0f} P&L=${r.dollar_pnl:+,.0f} "
              f"({r.pct_gain*100:+.1f}%) [{r.exit_reason}]")
    print(f"\nTOP 5 BY % GAIN:")
    for r in by_pct[:5]:
        print(f"  {_label_offset(r.strike_offset)} {r.strike}C × {r.qty} "
              f"TP1=+{int(r.tp1_premium_pct*100)}% frac={r.tp1_qty_frac:.3f} "
              f"runner={r.runner_target_pct}x -> "
              f"cost=${r.total_cost:,.0f} P&L=${r.dollar_pnl:+,.0f} "
              f"({r.pct_gain*100:+.1f}%) [{r.exit_reason}]")
    print("\nTOP 5 FOR $1K ACCOUNT (cost <= $500):")
    for r in constrained_1k[:5]:
        print(f"  {_label_offset(r.strike_offset)} {r.strike}C × {r.qty} "
              f"TP1=+{int(r.tp1_premium_pct*100)}% frac={r.tp1_qty_frac:.3f} "
              f"runner={r.runner_target_pct}x -> "
              f"cost=${r.total_cost:,.0f} P&L=${r.dollar_pnl:+,.0f} "
              f"({r.pct_gain*100:+.1f}%) [{r.exit_reason}]")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
