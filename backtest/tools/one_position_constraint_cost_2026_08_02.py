"""one_position_constraint_cost_2026_08_02.py -- MEASUREMENT ONLY. Quantifies what the
engine's one-position-at-a-time constraint (`fb.is_flat_spy_options(creds)` gate,
setup/scripts/heartbeat_core.py ~line 1895, "Any open SPY-option position still BLOCKS a
2nd (stacked) entry") costs in refused opportunity, and what relaxing it to 2 or 3
concurrent slots would cost in risk. SHIPS NOTHING, ARMS NOTHING -- concurrency is J's
call (Rule 6 per-trade cap + Rule 5 daily kill switch, both risk-POSTURE rules); this
tool produces the number and the risk analysis, never a recommendation to act.

Prereg (frozen BEFORE this runner executed):
    analysis/deep-research/PREREG-ONE-POSITION-CONSTRAINT-COST-2026-08-02.md

WHY THIS LANE EXISTS: the just-concluded three-iteration Bold sizing lane (min-contracts,
adaptive-sizing, selective-fallback -- all NULL) found that adaptive sizing gained
+$2,894.80 in aggregate but was killed because 2 of Bold's 32 runner-cohort trades were
pre-empted, and quality-based selectivity could NOT fix it because the two blocking trades
were themselves SUPER/ELITE tier AND level-anchored. The blocker is a slot being OCCUPIED,
not something unworthy occupying it. That points one level up the stack, at the constraint
those three iterations never questioned: the engine holds exactly ONE position at a time.
Nobody has ever measured what THAT constraint costs. This tool does.

METHOD (two-layer, matching this repo's established convention -- see
bold_fullhist_replay.py / engine_fullhist_replay.py's own "TWO-LAYER DESIGN" docstrings):
  1. BOLD candidate population: `bold_fullhist_replay.replay_population(qty_mode="fixed",
     min_contracts=5, block_elite_bull=True)` -- the CURRENT LIVE core-Bold shape, reused
     verbatim (import, zero modification to that already-shipped/anchored file). Already
     carries exit_time_et (added 2026-08-02 for the adaptive-sizing lane).
  2. SAFE candidate population: `_replay_safe_population()` below -- a hand-built loop that
     reuses engine_fullhist_replay.py's SAFE_BASE_LIVE / build_ribbon_lookup /
     ribbon_tick_df_for / naive_dt VERBATIM (import only, that file is NOT modified by this
     measurement-only lane) and adds the one field it discards today: exit_time_et
     (WalkResult already computes it). Parity-checked below against the already-shipped
     n=191/$4,808.75 headline (engine-fullhist-replay-2026-07-23.json) before being trusted.
  3. `_sequential_admit_concurrent(rows, K)`: generalizes bold_adaptive_sizing_2026_08_02.py's
     `_sequential_admit` (K=1 is byte-parity-checked against that already-shipped function's
     own output) to K simultaneous slots -- a signal is admitted iff fewer than K
     previously-admitted positions are still open at its arrival. PROVEN monotonic
     (admitted(K) is a strict superset of admitted(K-1)) via an independently-coded
     "cascading servers" cross-check on the REAL population, in the guard file -- not just a
     synthetic fixture, because this property is load-bearing for the entire "gained cohort
     per concurrency step" framing.
  4. Risk side, symmetric weight: peak simultaneous notional/count, day-level realized P&L,
     kill-switch breach counting (disclosed as a LOWER BOUND on true intraday risk -- see
     prereg), at each concurrency level.
  5. Slot-turnover: for the refused-at-K=1 cohort, how much earlier would the occupying
     trade have needed to exit -- cross-referenced descriptively (not row-joined) against
     analysis/pain-ledger/mae-mfe.json's real-fills MAE/MFE timing.

Run: backtest/.venv/Scripts/python.exe backtest/tools/one_position_constraint_cost_2026_08_02.py
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]           # backtest/
ROOT = REPO.parent                                     # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
CRYPTO_LIB = ROOT / "crypto" / "lib"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR), str(CRYPTO_LIB)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import bold_fullhist_replay as bfr  # noqa: E402
import engine_fullhist_replay as efr  # noqa: E402
import elite_bear_level_reject_gate_ab as eb  # noqa: E402
import strategies as fleet_strategies  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402

PREREG = ROOT / "analysis" / "deep-research" / "PREREG-ONE-POSITION-CONSTRAINT-COST-2026-08-02.md"
OUT_JSON = ROOT / "analysis" / "deep-research" / "ONE-POSITION-CONSTRAINT-COST-2026-08-02.json"

RECENT_N = 25
CONCURRENCY_LEVELS = (1, 2, 3)

# --- Anchors this study cross-checks against (already-shipped, real prior runs) -----------
BOLD_CONTROL_SEQUENTIAL_N_EXPECTED = 153
BOLD_CONTROL_SEQUENTIAL_PNL_EXPECTED = 7578.40   # bold-adaptive-sizing-2026-08-02.json .control_sequential.total_pnl
SAFE_SHIPPED_N_EXPECTED = 191
SAFE_SHIPPED_PNL_EXPECTED = 4808.75              # engine-fullhist-replay-2026-07-23.json .headline.total_pnl (UNSEQUENCED candidate population)

SAFE_EQUITY = 1746.75            # CLAUDE.md 2026-07-11 live-verified -- same figure engine_fullhist_replay.py uses (most current on record for Safe)
SAFE_PER_TRADE_RISK_CAP_PCT = 0.30   # automation/state/params.json
SAFE_KILL_SWITCH_PCT = 0.30          # automation/state/params.json#daily_loss_kill_switch_pct

BOLD_EQUITY = bfr.BOLD_LIVE_EQUITY               # 1197.52, live-verified 2026-08-01/02
BOLD_PER_TRADE_RISK_CAP_PCT = 0.50   # automation/state/aggressive/params.json
BOLD_KILL_SWITCH_PCT = 0.50          # automation/state/aggressive/params.json#daily_loss_kill_switch_pct


def log(msg: str) -> None:
    print(f"[one-position-constraint-cost] {msg}", flush=True)


# --- population: SAFE (hand-built exit_time_et-capturing loop, engine_fullhist_replay.py untouched) --
def _replay_safe_population(spy_df: pd.DataFrame, vix_df: pd.DataFrame, ribbon_lookup: pd.DataFrame) -> dict:
    """See module docstring point 2. Reuses efr.SAFE_BASE_LIVE / efr.build_ribbon_lookup /
    efr.ribbon_tick_df_for / efr.naive_dt / eb.entry_date / eb.classify_tier verbatim.
    DISCLOSED (prereg): inherits engine_fullhist_replay.py's own qty=int(t.qty) (always 3,
    the DEFAULT_QTY coincidence) with NO risk-cap-affordability exclusion -- unlike Bold's
    resolve_bold_qty. Not fixed here; out of this measurement-only lane's scope."""
    base = efr.SAFE_BASE_LIVE
    t0 = time.time()
    r = run_backtest(spy_df, vix_df, start_date=efr.FULL_START, end_date=efr.FULL_END, **base)
    entry_elapsed = time.time() - t0
    log(f"  [SAFE] run_backtest done in {entry_elapsed:.1f}s -- {len(r.trades)} raw entries")

    correct_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    rows: list[dict] = []
    n_no_opra = 0
    n_no_spy_day = 0
    t1 = time.time()
    for t in r.trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            n_no_opra += 1
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            n_no_spy_day += 1
            continue

        entry_time_et = efr.naive_dt(t.entry_time_et)
        entry_premium = float(t.entry_premium)
        qty = int(t.qty)
        trigger_level = float(t.rejection_level) if t.rejection_level else None
        tier = eb.classify_tier(t.triggers_fired)
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)

        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et, entry_premium=entry_premium,
            qty=qty, exit_shape=correct_shape, structure_stop_enabled=True,
            trigger_level=trigger_level, strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        rows.append({
            "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "setup": t.setup, "side": t.side, "tier": tier, "symbol": symbol,
            "qty": qty, "entry_premium": round(entry_premium, 4), "triggers": t.triggers_fired,
            "trigger_level": trigger_level,
            "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
            "resolved_stop_mode": res.stop_mode, "hold_minutes": res.hold_minutes,
            "n_ticks_walked": res.n_ticks_walked, "resolved": res.resolved,
            "exit_time_et": res.exit_time_et.isoformat() if res.exit_time_et else None,
        })
    exit_elapsed = time.time() - t1
    log(f"  [SAFE] exit re-derivation done in {exit_elapsed:.1f}s -- n_replayed={len(rows)} "
        f"n_no_opra_excluded={n_no_opra} n_no_spy_day_excluded={n_no_spy_day}")
    return {"rows": rows, "n_raw_entries": len(r.trades), "n_excluded_no_opra_cache": n_no_opra,
            "n_excluded_no_spy_day": n_no_spy_day, "entry_layer_seconds": round(entry_elapsed, 1),
            "exit_layer_seconds": round(exit_elapsed, 1)}


# --- concurrency admission (frozen mechanism) ----------------------------------------------
def _key(row: dict) -> tuple:
    return (row["symbol"], row["entry_time_et"])


def _sequential_admit_concurrent(rows: list[dict], max_concurrent: int) -> list[dict]:
    """Generalizes bold_adaptive_sizing_2026_08_02.py's _sequential_admit (max_concurrent=1
    is byte-parity-checked against that function's own output, guard file) to N simultaneous
    slots: a signal is admitted iff fewer than max_concurrent previously-admitted positions
    are still open (exit_time_et > this signal's entry_time_et) at its arrival. Same
    UNRESOLVED-TRADE CONVENTION as the parent function: a missing exit_time_et occupies its
    slot through 16:00 ET of its own entry day, never freed early, never carried to a later
    day (the conservative direction -- see _sequential_admit's own docstring).

    PROVEN MONOTONIC (guard file, cross-checked against an independently-coded 'cascading
    servers' formulation on the REAL population): admitted(K) is a strict superset of
    admitted(K-1) for the same chronologically-ordered input. This is what makes 'refused
    cohort' and 'gained cohort per concurrency step' well-defined and non-overlapping."""
    if max_concurrent < 1:
        raise ValueError(f"max_concurrent must be >= 1, got {max_concurrent}")
    kept: list[dict] = []
    open_exits: list[dt.datetime] = []
    for r in sorted(rows, key=lambda x: x["entry_time_et"]):
        entry = dt.datetime.fromisoformat(r["entry_time_et"])
        open_exits = [e for e in open_exits if e > entry]
        if len(open_exits) < max_concurrent:
            kept.append(r)
            exit_s = r.get("exit_time_et")
            if exit_s:
                exit_dt = dt.datetime.fromisoformat(exit_s)
            else:
                exit_dt = dt.datetime.combine(entry.date(), dt.time(16, 0))
            open_exits.append(exit_dt)
    return kept


def _sequential_admit_cascading_servers(rows: list[dict], max_concurrent: int) -> list[dict]:
    """INDEPENDENT re-derivation of the SAME admission rule -- used only by the guard test to
    cross-check _sequential_admit_concurrent on the REAL population, not the study itself.
    Simulates max_concurrent independent single-slot servers; each signal cascades to the
    lowest-indexed FREE server (server 1 gets first refusal on every signal, in chronological
    order -- exactly reproducing the plain max_concurrent=1 rule run alone; servers 2..K only
    ever see what 1..(their index-1) already refused)."""
    servers: list[Optional[dt.datetime]] = [None] * max_concurrent
    kept: list[dict] = []
    for r in sorted(rows, key=lambda x: x["entry_time_et"]):
        entry = dt.datetime.fromisoformat(r["entry_time_et"])
        for i in range(max_concurrent):
            if servers[i] is None or servers[i] <= entry:
                kept.append(r)
                exit_s = r.get("exit_time_et")
                servers[i] = (dt.datetime.fromisoformat(exit_s) if exit_s
                              else dt.datetime.combine(entry.date(), dt.time(16, 0)))
                break
    return kept


# --- stats (mirrors bold_adaptive_sizing_2026_08_02.py's _stats shape) ---------------------
def _stats(rows: list[dict], label: str) -> dict:
    n = len(rows)
    pnls = [r["dollar_pnl"] for r in rows]
    total = round(sum(pnls), 2)
    wins = [p for p in pnls if p > 0]
    wr = round(len(wins) / n, 4) if n else None
    avg = round(total / n, 2) if n else None
    if pnls:
        best = max(pnls)
        remainder = round(total - best, 2)
    else:
        best, remainder = 0.0, 0.0
    ordered = sorted(rows, key=lambda r: r["entry_time_et"])
    recent = ordered[-RECENT_N:] if ordered else []
    recent_pnls = [r["dollar_pnl"] for r in recent]
    recent_total = round(sum(recent_pnls), 2)
    recent_wr = round(sum(1 for p in recent_pnls if p > 0) / len(recent_pnls), 4) if recent_pnls else None
    return {
        "label": label, "n": n, "total_pnl": total, "win_rate": wr, "avg_pnl_per_trade": avg,
        "drop_best": {"best_trade_pnl": round(best, 2), "remainder": remainder,
                      "still_positive": remainder > 0},
        "recent_25": {"n": len(recent), "total_pnl": recent_total, "win_rate": recent_wr,
                      "start_date": recent[0]["date"] if recent else None,
                      "end_date": recent[-1]["date"] if recent else None},
    }


# --- risk side --------------------------------------------------------------------------
def _day_pnl(rows: list[dict]) -> dict:
    by_day: dict[str, float] = {}
    for r in rows:
        by_day[r["date"]] = round(by_day.get(r["date"], 0.0) + r["dollar_pnl"], 2)
    return by_day


def _kill_switch_breaches(day_pnl: dict, equity: float, kill_switch_pct: float) -> dict:
    threshold = -round(equity * kill_switch_pct, 2)
    breaches = sorted(((d, p) for d, p in day_pnl.items() if p <= threshold), key=lambda x: x[1])
    worst = min(day_pnl.items(), key=lambda x: x[1]) if day_pnl else None
    return {
        "threshold_dollars": threshold, "n_breach_days": len(breaches),
        "breach_days": [{"date": d, "day_pnl": p} for d, p in breaches],
        "worst_day": {"date": worst[0], "day_pnl": worst[1]} if worst else None,
    }


def _max_concurrent_notional(admitted_rows: list[dict]) -> dict:
    """Walks the ADMITTED set chronologically, tracking notional = entry_premium * qty * 100
    (the SAME definition resolve_bold_qty / risk_gate's RISK_CAP check itself uses for Rule 6
    -- reused for consistency, not invented fresh). Records the peak simultaneous sum and
    peak simultaneous COUNT (self-consistency check: peak count must never exceed the
    concurrency level that produced this admitted set). Closes are processed before opens at
    a tied timestamp, matching the admission rule's own strict '>' still-open test."""
    events = []  # (time, sign, notional) sign: -1 close, +1 open
    for r in admitted_rows:
        entry = dt.datetime.fromisoformat(r["entry_time_et"])
        exit_s = r.get("exit_time_et")
        exit_dt = (dt.datetime.fromisoformat(exit_s) if exit_s
                   else dt.datetime.combine(entry.date(), dt.time(16, 0)))
        notional = r["entry_premium"] * r["qty"] * 100.0
        events.append((entry, 1, notional))
        events.append((exit_dt, -1, notional))
    events.sort(key=lambda e: (e[0], e[1]))  # close (-1) before open (+1) at a tie
    running = 0.0
    running_n = 0
    peak = 0.0
    peak_n = 0
    peak_at = None
    for ts, sign, notional in events:
        running += sign * notional
        running_n += sign
        if running > peak:
            peak = running
            peak_n = running_n
            peak_at = ts.isoformat()
    return {"peak_notional_dollars": round(peak, 2), "peak_concurrent_count": peak_n, "peak_at": peak_at}


# --- opportunity cost + slot turnover -------------------------------------------------------
def _refused_cohort(candidate_rows: list[dict], admitted_rows: list[dict]) -> list[dict]:
    admitted_keys = {_key(r) for r in admitted_rows}
    return [r for r in candidate_rows if _key(r) not in admitted_keys]


def _slot_turnover_analysis(admitted_1: list[dict], refused_1: list[dict]) -> list[dict]:
    """For each refused-at-K=1 signal, find the SINGLE admitted-1 trade whose open interval
    contains its arrival (by construction under K=1 exactly one exists -- asserted below, not
    assumed) and compute gap_minutes_needed = occupant.exit_time_et - refused.entry_time_et:
    how much EARLIER the occupant would need to exit for this signal to have been admitted,
    concurrency held at 1."""
    admitted_sorted = sorted(admitted_1, key=lambda r: r["entry_time_et"])
    out = []
    n_unexplained = 0
    for r in refused_1:
        entry = dt.datetime.fromisoformat(r["entry_time_et"])
        occupant = None
        for a in admitted_sorted:
            a_entry = dt.datetime.fromisoformat(a["entry_time_et"])
            a_exit_s = a.get("exit_time_et")
            a_exit = (dt.datetime.fromisoformat(a_exit_s) if a_exit_s
                      else dt.datetime.combine(a_entry.date(), dt.time(16, 0)))
            if a_entry <= entry < a_exit:
                occupant = a
                break
        if occupant is None:
            n_unexplained += 1
            continue
        occ_entry = dt.datetime.fromisoformat(occupant["entry_time_et"])
        occ_exit_s = occupant.get("exit_time_et")
        occ_exit = (dt.datetime.fromisoformat(occ_exit_s) if occ_exit_s
                    else dt.datetime.combine(occ_entry.date(), dt.time(16, 0)))
        gap_minutes = (occ_exit - entry).total_seconds() / 60.0
        occ_hold = occupant.get("hold_minutes")
        out.append({
            "refused_symbol": r["symbol"], "refused_entry": r["entry_time_et"],
            "occupant_symbol": occupant["symbol"], "occupant_entry": occupant["entry_time_et"],
            "occupant_exit_reason": occupant.get("exit_reason"),
            "gap_minutes_needed": round(gap_minutes, 1),
            "occupant_hold_minutes": occ_hold,
            "gap_as_pct_of_occupant_hold": (round(100.0 * gap_minutes / occ_hold, 1)
                                              if occ_hold else None),
        })
    if n_unexplained:
        log(f"  WARNING: {n_unexplained} refused-at-K1 signals had no single K=1 occupant "
            f"found -- should be 0 by construction, investigate")
    return out, n_unexplained


def _quantile(vals: list[float], frac: float) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, round(frac * (len(s) - 1))))
    return round(s[idx], 1)


def _summarize_turnover(gaps: list[dict], n_unexplained: int) -> dict:
    gap_vals = [g["gap_minutes_needed"] for g in gaps]
    pct_vals = [g["gap_as_pct_of_occupant_hold"] for g in gaps if g["gap_as_pct_of_occupant_hold"] is not None]
    return {
        "n_refused_explained": len(gaps), "n_unexplained": n_unexplained,
        "gap_minutes_needed": {
            "median": _quantile(gap_vals, 0.5), "p25": _quantile(gap_vals, 0.25),
            "p75": _quantile(gap_vals, 0.75),
            "mean": round(sum(gap_vals) / len(gap_vals), 1) if gap_vals else None,
        },
        "gap_as_pct_of_occupant_hold": {
            "median": _quantile(pct_vals, 0.5), "p25": _quantile(pct_vals, 0.25),
            "p75": _quantile(pct_vals, 0.75),
            "mean": round(sum(pct_vals) / len(pct_vals), 1) if pct_vals else None,
        },
        "detail_rows": gaps,
    }


def _pain_ledger_turnover_context() -> dict:
    """Descriptive cross-reference (prereg: NOT row-joined -- a separate, smaller, real-fills
    dataset). % of a winner's hold time that elapses AFTER its own MFE peak -- directional
    evidence for whether trades linger past their peak (supports slot-turnover) or exit close
    to it (would not)."""
    path = ROOT / "analysis" / "pain-ledger" / "mae-mfe.json"
    if not path.exists():
        return {"available": False}
    d = json.loads(path.read_text(encoding="utf-8"))
    trades = d.get("trades", [])
    winners = [t for t in trades if t.get("outcome") == "winner" and t.get("time_to_mfe_min") is not None]
    ratios = []
    for t in winners:
        hold = t.get("hold_minutes")
        ttm = t.get("time_to_mfe_min")
        if hold and hold > 0 and ttm is not None:
            ratios.append(100.0 * (hold - ttm) / hold)
    return {
        "available": True, "n_winners_with_mfe_timing": len(winners),
        "n_total_trades_in_ledger": len(trades),
        "pct_of_hold_after_mfe_peak": {
            "median": round(statistics.median(ratios), 1) if ratios else None,
            "mean": round(statistics.mean(ratios), 1) if ratios else None,
            "p25": _quantile(ratios, 0.25), "p75": _quantile(ratios, 0.75),
        },
        "source": "analysis/pain-ledger/mae-mfe.json (REAL fills, 22 distinct dates "
                  "2026-06-26..2026-07-31, ALL arms combined -- descriptive corroboration "
                  "only, NOT row-joined against this study's 386-day synthetic population)",
    }


# --- main ------------------------------------------------------------------------------------
def main() -> int:
    if not PREREG.exists():
        print(f"FAIL: prereg {PREREG} not found -- refusing to run an un-pre-registered study.",
              file=sys.stderr)
        return 2

    t_start = time.time()
    log(f"loaded prereg {PREREG.name}")
    log("loading merged full-history SPY/VIX data")
    spy_df, vix_df = bfr._load_spy_vix()
    ribbon_lookup = bfr.efr.build_ribbon_lookup(spy_df)

    log("=== BOLD candidate population (current live shape, qty_mode=fixed, min_contracts=5) ===")
    bold_pop = bfr.replay_population(spy_df, vix_df, ribbon_lookup, block_elite_bull=True,
                                      qty_mode="fixed", min_contracts=bfr.BOLD_MIN_CONTRACTS)
    bold_rows = bold_pop["rows"]

    log("=== SAFE candidate population (current live shape, hand-built exit_time_et capture) ===")
    safe_pop = _replay_safe_population(spy_df, vix_df, ribbon_lookup)
    safe_rows = safe_pop["rows"]

    # --- parity checks (task discipline: reproduce before trusting) ------------------------
    bold_seq1 = _sequential_admit_concurrent(bold_rows, 1)
    bold_seq1_stats = _stats(bold_seq1, "BOLD K=1")
    bold_parity_ok = (bold_seq1_stats["n"] == BOLD_CONTROL_SEQUENTIAL_N_EXPECTED
                       and abs(bold_seq1_stats["total_pnl"] - BOLD_CONTROL_SEQUENTIAL_PNL_EXPECTED) < 0.02)
    log(f"PARITY [BOLD K=1 vs bold-adaptive-sizing-2026-08-02.json.control_sequential]: "
        f"n={bold_seq1_stats['n']} (expected {BOLD_CONTROL_SEQUENTIAL_N_EXPECTED}) "
        f"total=${bold_seq1_stats['total_pnl']:+.2f} (expected "
        f"${BOLD_CONTROL_SEQUENTIAL_PNL_EXPECTED:+.2f}) PARITY_OK={bold_parity_ok}")

    safe_unsequenced_stats = _stats(safe_rows, "SAFE unsequenced (raw candidate)")
    safe_parity_ok = (safe_unsequenced_stats["n"] == SAFE_SHIPPED_N_EXPECTED
                       and abs(safe_unsequenced_stats["total_pnl"] - SAFE_SHIPPED_PNL_EXPECTED) < 0.02)
    log(f"PARITY [SAFE unsequenced vs engine-fullhist-replay-2026-07-23.json.headline]: "
        f"n={safe_unsequenced_stats['n']} (expected {SAFE_SHIPPED_N_EXPECTED}) "
        f"total=${safe_unsequenced_stats['total_pnl']:+.2f} (expected "
        f"${SAFE_SHIPPED_PNL_EXPECTED:+.2f}) PARITY_OK={safe_parity_ok}")

    safe_seq1 = _sequential_admit_concurrent(safe_rows, 1)
    safe_seq1_stats = _stats(safe_seq1, "SAFE K=1")
    n_preempted_in_shipped_headline = len(safe_rows) - len(safe_seq1)
    log(f"SIDE FINDING: Safe's already-shipped headline (n={len(safe_rows)}, "
        f"${safe_unsequenced_stats['total_pnl']:+.2f}) was NEVER sequentially admitted before "
        f"this study -- true K=1 walk: n={safe_seq1_stats['n']} total="
        f"${safe_seq1_stats['total_pnl']:+.2f} (self-pre-emption: {n_preempted_in_shipped_headline})")

    # --- cross-check: cascading-servers vs count-based, on the REAL population -------------
    crosscheck = {}
    for arm_name, rows in (("bold", bold_rows), ("safe", safe_rows)):
        for K in CONCURRENCY_LEVELS:
            a = {_key(r) for r in _sequential_admit_concurrent(rows, K)}
            b = {_key(r) for r in _sequential_admit_cascading_servers(rows, K)}
            crosscheck[f"{arm_name}_K{K}"] = (a == b)
    log(f"CROSSCHECK (count-based vs cascading-servers, real population): {crosscheck}")

    # --- per-arm concurrency sweep -----------------------------------------------------------
    results: dict = {}
    for arm_name, rows, equity, cap_pct, kill_pct in (
        ("bold", bold_rows, BOLD_EQUITY, BOLD_PER_TRADE_RISK_CAP_PCT, BOLD_KILL_SWITCH_PCT),
        ("safe", safe_rows, SAFE_EQUITY, SAFE_PER_TRADE_RISK_CAP_PCT, SAFE_KILL_SWITCH_PCT),
    ):
        arm_out: dict = {"equity": equity, "per_trade_risk_cap_pct": cap_pct,
                         "daily_loss_kill_switch_pct": kill_pct, "levels": {}}
        prev_admitted_keys: set = set()
        for K in CONCURRENCY_LEVELS:
            admitted = _sequential_admit_concurrent(rows, K)
            admitted_keys = {_key(r) for r in admitted}
            monotonic_ok = prev_admitted_keys <= admitted_keys
            gained = [r for r in admitted if _key(r) not in prev_admitted_keys]
            stats = _stats(admitted, f"{arm_name}_K{K}")
            gained_stats = _stats(gained, f"{arm_name}_gained_at_K{K}")
            day_pnl = _day_pnl(admitted)
            ks = _kill_switch_breaches(day_pnl, equity, kill_pct)
            notional = _max_concurrent_notional(admitted)
            log(f"[{arm_name} K={K}] n={stats['n']} total=${stats['total_pnl']:+.2f} "
                f"gained_n={gained_stats['n']} gained_pnl=${gained_stats['total_pnl']:+.2f} "
                f"peak_notional=${notional['peak_notional_dollars']:,.2f} "
                f"({100*notional['peak_notional_dollars']/equity:.1f}% of equity) "
                f"peak_concurrent_count={notional['peak_concurrent_count']} "
                f"kill_breach_days={ks['n_breach_days']} monotonic_ok={monotonic_ok}")
            arm_out["levels"][str(K)] = {
                "admitted": stats, "gained_vs_prior_level": gained_stats,
                "day_pnl_n_days_traded": len(day_pnl), "kill_switch": ks, "notional": notional,
                "monotonic_superset_ok": monotonic_ok,
            }
            prev_admitted_keys = admitted_keys

        admitted_1 = _sequential_admit_concurrent(rows, 1)
        refused_1 = _refused_cohort(rows, admitted_1)
        refused_1_stats = _stats(refused_1, f"{arm_name}_refused_at_K1")
        turnover_gaps, n_unexplained = _slot_turnover_analysis(admitted_1, refused_1)
        turnover_summary = _summarize_turnover(turnover_gaps, n_unexplained)
        arm_out["refused_at_concurrency_1"] = refused_1_stats
        arm_out["slot_turnover"] = turnover_summary
        log(f"[{arm_name}] REFUSED@K1: n={refused_1_stats['n']} total=${refused_1_stats['total_pnl']:+.2f} "
            f"recent25=${refused_1_stats['recent_25']['total_pnl']:+.2f} "
            f"gap_minutes_needed_median={turnover_summary['gap_minutes_needed']['median']} "
            f"gap_pct_of_occupant_hold_median={turnover_summary['gap_as_pct_of_occupant_hold']['median']}")
        results[arm_name] = arm_out

    pain_ledger_ctx = _pain_ledger_turnover_context()
    log(f"PAIN-LEDGER CONTEXT: {pain_ledger_ctx.get('pct_of_hold_after_mfe_peak')}")

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": str(PREREG.relative_to(ROOT)),
        "window": {"start": bfr.FULL_START.isoformat(), "end": bfr.FULL_END.isoformat()},
        "parity": {
            "bold_k1_vs_shipped_control_sequential": {
                "n": bold_seq1_stats["n"], "total_pnl": bold_seq1_stats["total_pnl"],
                "expected_n": BOLD_CONTROL_SEQUENTIAL_N_EXPECTED,
                "expected_pnl": BOLD_CONTROL_SEQUENTIAL_PNL_EXPECTED, "ok": bold_parity_ok,
            },
            "safe_unsequenced_vs_shipped_headline": {
                "n": safe_unsequenced_stats["n"], "total_pnl": safe_unsequenced_stats["total_pnl"],
                "expected_n": SAFE_SHIPPED_N_EXPECTED, "expected_pnl": SAFE_SHIPPED_PNL_EXPECTED,
                "ok": safe_parity_ok,
            },
            "cascading_servers_crosscheck_real_population": crosscheck,
            "all_crosschecks_pass": all(crosscheck.values()),
        },
        "safe_side_finding_never_sequenced_before": {
            "shipped_headline_n": len(safe_rows), "shipped_headline_pnl": safe_unsequenced_stats["total_pnl"],
            "true_k1_sequential_n": safe_seq1_stats["n"], "true_k1_sequential_pnl": safe_seq1_stats["total_pnl"],
            "n_self_preempted": n_preempted_in_shipped_headline,
            "note": "Safe's already-shipped headline (engine-fullhist-replay-2026-07-23.json) "
                    "was never checked for position-sequencing validity before this study. "
                    "Flagged here per OP-33 visibility discipline -- NOT re-shipped or "
                    "corrected (out of scope for this measurement-only lane).",
        },
        "population": {
            "bold": {"n_raw_entries": bold_pop["n_raw_entries"],
                     "n_excluded_no_opra_cache": bold_pop["n_excluded_no_opra_cache"],
                     "n_excluded_no_spy_day": bold_pop["n_excluded_no_spy_day"],
                     "n_excluded_risk_cap_deadlock": bold_pop["n_excluded_risk_cap_deadlock"],
                     "n_candidate": len(bold_rows)},
            "safe": {"n_raw_entries": safe_pop["n_raw_entries"],
                     "n_excluded_no_opra_cache": safe_pop["n_excluded_no_opra_cache"],
                     "n_excluded_no_spy_day": safe_pop["n_excluded_no_spy_day"],
                     "n_excluded_risk_cap_deadlock": "NOT_MODELED (disclosed, inherited gap)",
                     "n_candidate": len(safe_rows)},
        },
        "results": results,
        "pain_ledger_context": pain_ledger_ctx,
        "runtime_seconds": round(time.time() - t_start, 1),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    log(f"total runtime {out['runtime_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
