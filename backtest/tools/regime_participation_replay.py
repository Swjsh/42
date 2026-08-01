"""regime_participation_replay.py -- FULL-POPULATION decision-trace x archetype cross-ref
(2026-08-02, REGIME-PARTICIPATION task).

WHY: engine-fullhist-replay-2026-07-23 showed gap-go = 60.5% of all P&L on ~22% of days,
while trend-up/trend-down/V-reversal/inverted-V are all underpowered (n<15 trades). The
open question is PARTICIPATION: on trend-up/trend-down days, is the engine SEEING setups
and refusing them (a gate problem) or never generating a candidate at all (a detector
problem)? Answering that needs a decision trace over every day, not just entered trades.

day_report_card.py already builds EXACTLY this decision trace (GREEN / GATE_BLOCKED[filter_N]
/ CORRECTLY_FLAT / NO_VOCABULARY / EXIT_LEFT_MONEY / EXIT_TOO_LATE / SHOULD_NOT_HAVE_TRADED
per day) -- but only renders the last 90 trading days. Its own heavy pipeline ALREADY scores
the FULL population every run (`run_backtest_with_bull_capture(start_date=lfr.FULL_START,
end_date=lfr.FULL_END, ...)` is unconditional; only the per-day CARD-BUILDING loop is sliced
to the last N_WINDOW_DAYS). This script reuses that exact pipeline byte-for-byte (same
imports, same classify_day/aggregate_cards/modal_blocker_of/trade_excursions functions --
NOT reimplemented, so no semantic drift) and removes only the final slice, producing cards
for every day 2025-01-02..2026-07-27 (the same FULL_START/FULL_END ladder_fullhist_replay.py
already uses -- the identical, already-anchored data window; NOT re-derived here).

Each card is then tagged with its WS6 regime-library archetype (backtest/lib/regime_slice.py)
and the cards are aggregated PER ARCHETYPE using the SAME aggregate_cards() bucketing logic
day_report_card uses for the whole population -- so "per-archetype cause histogram" and
"whole-population cause histogram" are computed by the identical, already-guarded function.

SCOPE DISCLOSURE (inherited from day_report_card.py, unchanged here):
  - Bear-side candidates only (RIDE_THE_RIBBON bear entry-gate trace). Bull-side candidate
    capture exists as a side-channel (bull_passed_by_idx) but is NOT run through the same
    named-filter attribution -- a bull day that is truly NO_VOCABULARY on this bear-only
    lens may have had a live bull candidate. Disclosed, not fixed here (day_report_card.py's
    own documented v1 scope limit).
  - Replay-vs-live divergence is known (trade-level anchors 1/4 on 2026-07-17).
  - Population window is 2025-01-02..2026-07-27 (ladder_fullhist_replay.FULL_END) -- FOUR
    days short of the regime library's 2026-07-31 endpoint (2026-07-28..07-31 have archetype
    tags but no decision-trace coverage from this lens; visible in the output as
    n_days_in_archetype_but_outside_replay_window).
  - GATE_BLOCKED here means a NAMED ENTRY-SELECTIVITY filter (filters.py blockers 1-11,
    see FILTER_NAMES) blocked an otherwise level-tied, score>=8 candidate. It does NOT cover
    the downstream risk_gate (PDT / NOT_FLAT / min_premium_floor / quality-lock) -- that
    layer only fires on candidates that already passed entry gates, and this replay does not
    walk the risk_gate at all (mirrors day_report_card.py). The live core-decisions.jsonl
    cross-reference (regime_participation_study.py) is the only source with risk-gate
    ("SIZING_REFUSED") visibility, over its own much shorter live window.

ANCHOR: this script's full-population run must reproduce the SAME baseline_n_trades=191 /
baseline_total_pnl=$5306.95 / candidates_at_floor8=2308 anchors day_report_card.py's own
90-day run reproduces (analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json) -- since the
underlying heavy pipeline call is byte-identical, only the reporting window differs. A
mismatch here means this script accidentally changed pipeline behavior, not just window size.

OUTPUT: analysis/regime-library/participation-replay-fullhist-2026-08-02.json
Run: backtest/.venv/Scripts/python.exe backtest/tools/regime_participation_replay.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]              # backtest/
ROOT = REPO.parent                                        # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import day_report_card as drc  # noqa: E402 -- classify_day/aggregate_cards/modal_blocker_of/
                                #              trade_excursions/FILTER_NAMES, REUSED not copied
from lib.regime_slice import archetype_of  # noqa: E402

OUT_JSON = ROOT / "analysis" / "regime-library" / "participation-replay-fullhist-2026-08-02.json"

_ENTERED_CAUSES = ("GREEN", "EXIT_LEFT_MONEY", "EXIT_TOO_LATE", "SHOULD_NOT_HAVE_TRADED")


def aggregate_by_archetype(cards: list[dict]) -> dict[str, dict]:
    """PURE -- no I/O. cards: [{"archetype": str|None, "cause": ..., "cause_detail": ...,
    "cause_dollars": ...}, ...] (day_report_card.classify_day's output shape, one dict per
    day, plus an 'archetype' key). Groups by archetype (None -> 'UNTAGGED'), reuses
    day_report_card.aggregate_cards() per group (same taxonomy-validation + $ bucketing
    every other consumer of that function gets -- not reimplemented), and derives the
    participation summary: n_days_entered (any traded-tree cause) / n_days_gate_blocked /
    n_days_correctly_flat (sub-qualifying trigger) / n_days_no_vocabulary (zero triggers).
    Guarded: test_regime_participation_replay.py."""
    by_archetype: dict[str, dict] = {}
    for arch in sorted({c["archetype"] or "UNTAGGED" for c in cards}):
        arch_cards = [c for c in cards if (c["archetype"] or "UNTAGGED") == arch]
        arch_agg = drc.aggregate_cards(arch_cards)
        n_entered = sum(b["n_days"] for b in arch_agg["ranked"] if b["cause"] in _ENTERED_CAUSES)
        n_gate_blocked = sum(b["n_days"] for b in arch_agg["ranked"] if b["cause"] == "GATE_BLOCKED")
        n_correctly_flat = sum(b["n_days"] for b in arch_agg["ranked"] if b["cause"] == "CORRECTLY_FLAT")
        n_no_vocab = sum(b["n_days"] for b in arch_agg["ranked"] if b["cause"] == "NO_VOCABULARY")
        by_archetype[arch] = {
            "n_days": len(arch_cards),
            "n_days_entered": n_entered,
            "participation_rate": round(n_entered / len(arch_cards), 4) if arch_cards else None,
            "n_days_gate_blocked": n_gate_blocked,
            "n_days_correctly_flat_subqualifying_trigger": n_correctly_flat,
            "n_days_no_vocabulary_zero_triggers": n_no_vocab,
            "cause_histogram": arch_agg["ranked"],
        }
    return by_archetype


def log(msg: str) -> None:
    print(f"[regime-participation-replay] {msg}", flush=True)


def main() -> int:
    t_start = time.time()
    import pandas as pd  # noqa: F401

    import elite_bear_level_reject_gate_ab as eb
    import engine_fullhist_replay as efr
    import fleet_executor as fx
    import ladder_fullhist_replay as lfr
    import strategies as fleet_strategies
    from crypto.lib.strike_selection import pick_strike
    from lib.exit_manager_walk import walk_exit_manager
    from lib.option_pricing_real import load_contract_bars, option_symbol

    log("loading extended SPY/VIX data (identical merge to ladder_fullhist_replay)")
    spy_df_raw, vix_df = lfr.load_extended_data()
    spy_rth = lfr.build_rth_frame(spy_df_raw)
    all_rth_dates = sorted(spy_rth["timestamp_et"].dt.date.unique())
    window_dates = all_rth_dates  # <-- THE ONLY SEMANTIC CHANGE FROM day_report_card.py: full pop, not [-90:]
    window_set = set(window_dates)
    log(f"  window: {window_dates[0]}..{window_dates[-1]} ({len(window_dates)} RTH days, FULL population)")

    log("running run_backtest(**SAFE_BASE_LIVE) with bull-passed capture (identical call to day_report_card.py)")
    t0 = time.time()
    r, bull_passed_by_idx = lfr.run_backtest_with_bull_capture(
        spy_df_raw, vix_df, start_date=lfr.FULL_START, end_date=lfr.FULL_END,
        **efr.SAFE_BASE_LIVE)
    log(f"  done in {time.time()-t0:.1f}s -- {len(r.trades)} raw entries, {len(r.decisions)} decision rows")

    ribbon_lookup = efr.build_ribbon_lookup(spy_df_raw)
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    log("walking baseline exits (all raw entries)")
    baseline_rows: list[dict] = []
    unpriceable_by_date: Counter = Counter()
    for t in r.trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            unpriceable_by_date[edate] += 1
            continue
        day_spy = spy_df_raw.loc[spy_df_raw["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            unpriceable_by_date[edate] += 1
            continue
        entry_time_et = efr.naive_dt(t.entry_time_et)
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
        walk = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et,
            entry_premium=float(t.entry_premium), qty=int(t.qty), exit_shape=exit_shape,
            structure_stop_enabled=True,
            trigger_level=(float(t.rejection_level) if t.rejection_level else None),
            strategy="ribbon_ride", time_stop_et=drc.TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        row = {
            "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "setup": t.setup, "side": t.side, "symbol": symbol, "qty": int(t.qty),
            "entry_premium": round(float(t.entry_premium), 4),
            "triggers": t.triggers_fired, "tier": eb.classify_tier(t.triggers_fired),
            "dollar_pnl": walk.dollar_pnl, "exit_reason": walk.exit_reason,
            "exit_time_et": (walk.exit_time_et.isoformat() if walk.exit_time_et else None),
            "hold_minutes": walk.hold_minutes,
        }
        if edate in window_set:
            row.update(drc.trade_excursions(opt_df, edate, entry_time_et, walk.exit_time_et,
                                              float(t.entry_premium), int(t.qty), walk.dollar_pnl))
        baseline_rows.append(row)

    full_total = round(sum(x["dollar_pnl"] for x in baseline_rows), 2)
    full_n = len(baseline_rows)
    full_wr = round(sum(1 for x in baseline_rows if x["dollar_pnl"] > 0) / full_n, 4) if full_n else None
    log(f"  full-window baseline: n={full_n} total=${full_total:+.2f} WR={full_wr}")

    log("extracting qualifying candidates (ladder extraction, floor>=8)")
    candidates = [c for c in lfr.build_candidates(r.decisions, bull_passed_by_idx)
                  if c["bear_score"] >= drc.QUALIFYING_SCORE_FLOOR]
    n_cand_full = len(candidates)
    log(f"  {n_cand_full} full-window qualifying candidates (anchor expects {drc.ANCHOR_CANDIDATES_AT_8})")

    cand_by_date: dict[dt.date, list[dict]] = {}
    for c in candidates:
        d = spy_rth.iloc[c["bar_idx"]]["timestamp_et"].date()
        cand_by_date.setdefault(d, []).append(c)

    triggers_by_date: dict[dt.date, bool] = {}
    scored_bars_by_date: Counter = Counter()
    for row in r.decisions:
        if "action" in row:
            continue
        d = row["timestamp_et"].date()
        scored_bars_by_date[d] += 1
        if row.get("triggers_fired"):
            triggers_by_date[d] = True

    log(f"building day cards for ALL {len(window_dates)} days (oracle walks on flat days) -- this is the slow part")
    trades_by_date: dict[str, list[dict]] = {}
    for row in baseline_rows:
        trades_by_date.setdefault(row["date"], []).append(row)

    cards: list[dict] = []
    n_oracle_walks = 0
    t_cards = time.time()
    for i, d in enumerate(window_dates):
        if i and i % 50 == 0:
            log(f"  ...{i}/{len(window_dates)} days ({time.time()-t_cards:.0f}s elapsed)")
        iso = d.isoformat()
        day_trades = trades_by_date.get(iso, [])
        day_cands = sorted(cand_by_date.get(d, []), key=lambda c: c["bar_idx"])
        day_spy_rth = spy_rth.loc[spy_rth["timestamp_et"].dt.date == d]
        day_open = float(day_spy_rth.iloc[0]["open"]) if len(day_spy_rth) else None
        day_range_pct = (round((float(day_spy_rth["high"].max()) - float(day_spy_rth["low"].min()))
                                / day_open * 100.0, 3) if day_open else None)

        day_pnl = round(sum(t["dollar_pnl"] for t in day_trades), 2) if day_trades else None
        best_mfe = max((t.get("mfe_pct", 0.0) for t in day_trades), default=0.0)
        best_peak = max((t.get("peak_dollars", 0.0) for t in day_trades), default=0.0)
        best_left = max((t.get("left_dollars", 0.0) for t in day_trades), default=0.0)

        oracle_walks: list[dict] = []
        n_synth = 0
        oracle_bound = None
        if not day_trades and day_cands:
            day_spy_full = spy_df_raw.loc[spy_df_raw["timestamp_et"].dt.date == d].reset_index(drop=True)
            for c in day_cands:
                spot = float(c["spy_close"])
                strike = pick_strike(spot, drc.REF_EQUITY_FOR_STRIKE, "P", fx.PROBE_STRIKE_TIERS)
                res = lfr.resolve_ladder_entry(spy_rth, c["bar_idx"], strike, d,
                                                 float(c["vix"]), spot)
                if not res["ok"]:
                    n_synth += 1
                    oracle_walks.append({
                        "trigger_time_et": drc._naive(spy_rth.iloc[c["bar_idx"]]["timestamp_et"]).isoformat(),
                        "bear_score": c["bear_score"], "blockers": c["blockers"],
                        "triggers": c["triggers_fired"], "rejection_level": c["rejection_level"],
                        "strike": strike, "excluded": res["reason"],
                        "synthetic_entry_premium": res.get("synthetic_entry_premium"),
                        "dollar_pnl": None,
                    })
                    continue
                rtd = efr.ribbon_tick_df_for(res["opt_df"], ribbon_lookup)
                walk = walk_exit_manager(
                    symbol=res["symbol"], side="P", entry_time_et=res["entry_time_et"],
                    entry_premium=res["entry_premium"], qty=drc.MIN_CONTRACTS,
                    exit_shape=exit_shape, structure_stop_enabled=True,
                    trigger_level=float(c["rejection_level"]), strategy="ribbon_ride",
                    time_stop_et=drc.TIME_STOP_ET, opt_df=res["opt_df"], ribbon_tick_df=rtd,
                    five_min_spy_df=day_spy_full,
                )
                n_oracle_walks += 1
                oracle_walks.append({
                    "trigger_time_et": drc._naive(spy_rth.iloc[c["bar_idx"]]["timestamp_et"]).isoformat(),
                    "bear_score": c["bear_score"], "blockers": c["blockers"],
                    "triggers": c["triggers_fired"], "rejection_level": c["rejection_level"],
                    "strike": strike, "symbol": res["symbol"],
                    "entry_premium": round(res["entry_premium"], 4),
                    "dollar_pnl": walk.dollar_pnl, "exit_reason": walk.exit_reason,
                })
                if oracle_bound is None or walk.dollar_pnl > oracle_bound:
                    oracle_bound = walk.dollar_pnl

        cls = drc.classify_day(
            n_walked_trades=len(day_trades), day_pnl=day_pnl,
            best_left_dollars=best_left, best_mfe_pct=best_mfe, best_peak_dollars=best_peak,
            n_qualifying_blocked=len(day_cands) if not day_trades else 0,
            modal_blocker=drc.modal_blocker_of([c["blockers"] for c in day_cands]) if (
                day_cands and not day_trades) else None,
            oracle_bound_dollars=oracle_bound,
            any_trigger_fired=triggers_by_date.get(d, False),
        )
        cards.append({
            "date": iso,
            "archetype": archetype_of(d),
            "cause": cls["cause"], "cause_detail": cls["cause_detail"],
            "cause_dollars": cls["cause_dollars"],
            "n_walked_trades": len(day_trades), "day_pnl": day_pnl,
            "n_qualifying_candidates": len(day_cands),
            "n_synthetic_excluded": n_synth,
            "spy_range_pct": day_range_pct,
            "any_trigger_fired": triggers_by_date.get(d, False),
            "n_scored_bars": int(scored_bars_by_date.get(d, 0)),
        })

    log(f"  {len(cards)} cards, {n_oracle_walks} oracle walks, cards loop took {time.time()-t_cards:.0f}s")

    agg = drc.aggregate_cards(cards)
    by_archetype = aggregate_by_archetype(cards)

    anchor = {
        "baseline_n_trades": {"got": full_n, "expected": drc.ANCHOR_BASELINE_N,
                               "pass": full_n == drc.ANCHOR_BASELINE_N},
        "baseline_total_pnl": {"got": full_total, "expected": drc.ANCHOR_BASELINE_PNL,
                                "pass": abs(full_total - drc.ANCHOR_BASELINE_PNL) < 1.0},
        "candidates_at_floor8": {"got": n_cand_full, "expected": drc.ANCHOR_CANDIDATES_AT_8,
                                  "pass": n_cand_full == drc.ANCHOR_CANDIDATES_AT_8},
        "source": "analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json (same anchors day_report_card.py checks)",
    }
    all_pass = all(v["pass"] for k, v in anchor.items() if isinstance(v, dict))
    log(f"anchor cross-check (must match day_report_card.py's own anchors): ALL PASS = {all_pass}")

    out = {
        "generated_at": dt.datetime.now().isoformat(),
        "tool": "backtest/tools/regime_participation_replay.py",
        "note": ("FULL-POPULATION variant of day_report_card.py -- identical pipeline, "
                 "window slice removed. Bear-side (RIDE_THE_RIBBON) candidate/gate trace only; "
                 "see module docstring SCOPE DISCLOSURE."),
        "window": {"start": window_dates[0].isoformat(), "end": window_dates[-1].isoformat(),
                    "n_days": len(window_dates)},
        "taxonomy": sorted(drc.VALID_CAUSES),
        "filter_names": drc.FILTER_NAMES,
        "thresholds": {"FOCUS_DAILY_FLOOR": drc.FOCUS_DAILY_FLOOR,
                        "MFE_WINNER_PCT": drc.MFE_WINNER_PCT,
                        "QUALIFYING_SCORE_FLOOR": drc.QUALIFYING_SCORE_FLOOR},
        "anchor_crosscheck": {"all_pass": all_pass, **anchor},
        "full_population_aggregate": agg,
        "by_archetype": by_archetype,
        "cards": cards,
        "runtime_seconds": round(time.time() - t_start, 1),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON} ({OUT_JSON.stat().st_size} bytes) in {time.time()-t_start:.1f}s total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
