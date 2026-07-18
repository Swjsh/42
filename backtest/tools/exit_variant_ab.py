"""exit_variant_ab.py -- exit-quality lever L2 A/B, driven by the REAL exit_manager
(GOAL-REPLAY-TODAY-GREEN iteration 6, step 3). Companion to exit_manager_replay.py (today's
faithfulness check); this is the HISTORICAL OOS half the task's step 3 asks for.

WHY THIS EXISTS RATHER THAN REUSING hold_posture_ab_study.py (EDGE-3): that study already
drives exit_manager.plan_exit_actions over historical bars, but its OWN disclosure list says
so explicitly -- "premium-only exit replay (structure_stop/ribbon-flip collapse to the -50%
catastrophe cap)" (never passes last_closed_5m_close). Structure-stop is the PRIMARY v15.3
invalidation and governed 5/6 of TODAY's real entries (exit_manager_replay.py,
analysis/recommendations/exit-manager-replay-2026-07-17.json) -- a control shape that
collapses it isn't testing "current SS-B", it's testing the pre-STOP-B premium-only shape.
This module fixes that gap: every entry is walked with a REAL per-day 5-min SPY series feeding
last_closed_5m_close, so structure_stop can actually fire, matching what today's harness proved
faithful.

POPULATION: `lib.orchestrator.run_backtest` (SAFE_BASE config, reused verbatim from
elite_bear_level_reject_gate_ab.py for entry-detection consistency with a prior, reviewed
study) over IS 2025 + OOS 2026-YTD -- but ONLY the entry fields (entry_time_et, entry_premium,
strike, qty, side, rejection_level) are trusted from it; each TradeFill's OWN exit fields are
DISCARDED and re-derived independently via exit_manager_walk under two shapes:
  CONTROL   = automation/state/fleet/strategies.py#RIBBON_RIDE.exit.to_dict() -- the REAL
              production shape (trail_pct=0.15, arm +5%, tp1 @ +100%/sell 66.7%, runner_target
              99x, stop_mode=structure, catastrophe -50%), structure_stop_enabled=True.
  CANDIDATE = WIDER_TRAIL_25 -- the SAME shape with trail_pct=0.25. Chosen because TODAY's own
              faithful replay showed BOTH real winners (13:01 746P, 13:51 bold 743P) exited via
              the "trail" stage (the chandelier floor), not runner_target or time_stop -- trail
              width is the empirically OBSERVED binding constraint on today's tape, and this is
              the TRAIL60-REOPEN-WATCH family's underlying mechanism (queue.md), tested here
              under the now-correct structure-stop-aware machinery rather than the premium-only
              approximation that produced the earlier inconclusive result.

DISCLOSED LIMITATIONS (bounded, stated up front, not discovered after the fact):
  1. ribbon_flip_back is OFF for this population (always False) -- never fired even once across
     today's real 6-trade primary population, and replicating a from-scratch ribbon series
     aligned to 18 months of entries was out of this iteration's time budget. Structure_stop /
     premium_stop / tp1 / runner_target / time_stop are ALL modeled; only the ribbon-flip
     secondary exit is omitted.
  2. TRENDLINE-tier entries (rejection_level=None -- no static level was the trigger) fall back
     to exit_shape's own premium_stop_pct=-0.20 "flag-off" fallback rather than live's heuristic
     nearest-key-level lookup (heartbeat_core.py's `_trigger_level_heuristic`) -- historical
     key-levels.json snapshots for arbitrary past dates aren't available. This is the SAME
     code path production falls back to when NO exact level exists, so it is not a fabricated
     branch, just a narrower fallback source than live's.
  3. qty is whatever SAFE_BASE's backtest sizing produced (not today's live position sizing) --
     irrelevant to the paired per-trade delta this study scores (both control and candidate see
     the identical qty for a given trade), but absolute $ magnitudes are not directly comparable
     to live dollar figures.

Run: backtest/.venv/Scripts/python.exe backtest/tools/exit_variant_ab.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from backtest.tools.regime_classifier import RegimeCalendar  # noqa: E402
from backtest.tools.regime_conditioned_validator import validate_candidate  # noqa: E402
import strategies as fleet_strategies  # noqa: E402
from elite_bear_level_reject_gate_ab import SAFE_BASE, SPY_FILE, VIX_FILE  # noqa: E402

from lib.orchestrator import run_backtest  # noqa: E402

WINDOW_START = dt.date(2025, 1, 2)
WINDOW_END = dt.date(2026, 7, 8)
RIBBON_SETUPS = ("BEARISH_REJECTION_RIDE_THE_RIBBON", "BULLISH_RECLAIM_RIDE_THE_RIBBON")

CANDIDATE_NAME = "exit_wider_trail_25"
CANDIDATE_TRAIL_PCT = 0.25

OUT_JSON = ROOT / "analysis" / "recommendations" / "exit-variant-ab-wider-trail25-2026-07-17.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "exit-variant-ab-wider-trail25-2026-07-17.md"


def log(msg: str) -> None:
    print(f"[exit-variant-ab] {msg}", flush=True)


def entry_date_of(t) -> dt.date:
    et = t.entry_time_et
    return et.date() if hasattr(et, "date") else dt.date.fromisoformat(str(et)[:10])


def naive_dt(ts) -> dt.datetime:
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts


def main() -> int:
    log("loading data + running SAFE_BASE population (entry-detection layer only)")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    res = run_backtest(spy_df, vix_df, start_date=WINDOW_START, end_date=WINDOW_END, **SAFE_BASE)
    ribbon_trades = [t for t in res.trades if str(t.setup) in RIBBON_SETUPS]
    log(f"n_total_trades={len(res.trades)} n_ribbon_ride={len(ribbon_trades)} "
        f"window={WINDOW_START}..{WINDOW_END}")

    control_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    candidate_shape = dict(control_shape)
    candidate_shape["trail_pct"] = CANDIDATE_TRAIL_PCT
    log(f"control_shape={control_shape}")
    log(f"candidate_shape={candidate_shape}")

    rows = []
    cache_misses = 0
    for t in ribbon_trades:
        edate = entry_date_of(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            cache_misses += 1
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            cache_misses += 1
            continue
        entry_time_et = naive_dt(t.entry_time_et)
        entry_premium = float(t.entry_premium)
        trigger_level = float(t.rejection_level) if t.rejection_level is not None else None
        qty = int(t.qty)

        res_control = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et, entry_premium=entry_premium,
            qty=qty, exit_shape=control_shape, structure_stop_enabled=True,
            trigger_level=trigger_level, strategy="ribbon_ride", time_stop_et=dt.time(15, 40),
            opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=day_spy)
        res_candidate = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et, entry_premium=entry_premium,
            qty=qty, exit_shape=candidate_shape, structure_stop_enabled=True,
            trigger_level=trigger_level, strategy="ribbon_ride", time_stop_et=dt.time(15, 40),
            opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=day_spy)

        delta = round(res_candidate.dollar_pnl - res_control.dollar_pnl, 2)
        rows.append({
            "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "symbol": symbol, "side": t.side, "qty": qty,
            "trigger_level": trigger_level, "resolved_stop_mode": res_control.stop_mode,
            "control_pnl": res_control.dollar_pnl, "control_exit_reason": res_control.exit_reason,
            "candidate_pnl": res_candidate.dollar_pnl, "candidate_exit_reason": res_candidate.exit_reason,
            "pnl": delta,
        })

    log(f"n_replayed={len(rows)} cache_misses={cache_misses}")
    if not rows:
        log("FATAL: no trades replayed -- aborting")
        return 1

    control_total = round(sum(r["control_pnl"] for r in rows), 2)
    candidate_total = round(sum(r["candidate_pnl"] for r in rows), 2)
    total_delta = round(candidate_total - control_total, 2)
    log(f"control_total=${control_total:+.2f} candidate_total=${candidate_total:+.2f} "
        f"total_delta=${total_delta:+.2f} n={len(rows)}")

    # ---- calendar A/B-delta WF (WF-GATE-METHODOLOGY-2026-07-16.md form), disclosure/cross-check ----
    is_rows = [r for r in rows if r["date"] <= "2025-12-31"]
    oos_rows = [r for r in rows if r["date"] >= "2026-01-02"]
    is_delta = round(sum(r["pnl"] for r in is_rows), 2)
    oos_delta = round(sum(r["pnl"] for r in oos_rows), 2)
    wf_calendar = None
    if is_delta != 0 and is_rows and oos_rows:
        wf_calendar = round((oos_delta / len(oos_rows)) / (is_delta / len(is_rows)), 3)

    # ---- regime-conditioned validation (the earned methodology, iteration 5) ----
    cal = RegimeCalendar()
    regime_result = validate_candidate(
        [{"date": r["date"], "pnl": r["pnl"]} for r in rows],
        candidate_name=CANDIDATE_NAME, calendar=cal,
        full_window_start=WINDOW_START, full_window_end=WINDOW_END)

    # ---- fable-too-good: concentration + anchor cross-check ----
    rows_sorted = sorted(rows, key=lambda r: -abs(r["pnl"]))
    drop_top3 = rows_sorted[3:]
    delta_ex_top3 = round(sum(r["pnl"] for r in drop_top3), 2)

    try:
        from autoresearch.j_edge_tracker import J_WINNERS, J_LOSERS  # noqa: E402
        anchor_win_dates = {t["date"] for t in J_WINNERS}
        anchor_lose_dates = {t["date"] for t in J_LOSERS}
    except Exception:
        anchor_win_dates, anchor_lose_dates = set(), set()
    anchor_win_delta = round(sum(r["pnl"] for r in rows if r["date"] in anchor_win_dates), 2)
    anchor_lose_delta = round(sum(r["pnl"] for r in rows if r["date"] in anchor_lose_dates), 2)

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "candidate_name": CANDIDATE_NAME,
        "control_shape": control_shape,
        "candidate_shape": candidate_shape,
        "window": [str(WINDOW_START), str(WINDOW_END)],
        "n_ribbon_ride_trades": len(ribbon_trades),
        "n_replayed": len(rows),
        "cache_misses": cache_misses,
        "control_total_pnl": control_total,
        "candidate_total_pnl": candidate_total,
        "total_delta": total_delta,
        "calendar_wf_disclosure": {
            "is_2025_delta": is_delta, "n_is": len(is_rows),
            "oos_2026_delta": oos_delta, "n_oos": len(oos_rows),
            "wf_gate_cohort_normalized": wf_calendar,
            "note": "cross-check only, calendar-year split -- the ladder decision uses the "
                     "regime-conditioned result below (iteration 5's earned methodology)",
        },
        "regime_conditioned_validation": regime_result,
        "concentration_check": {
            "top3_dropped": [{"date": r["date"], "pnl": r["pnl"]} for r in rows_sorted[:3]],
            "delta_ex_top3": delta_ex_top3, "survives_ex_top3": delta_ex_top3 > 0,
        },
        "anchor_cross_check_op16": {
            "j_winners_delta": anchor_win_delta, "j_losers_delta": anchor_lose_delta,
            "note": "delta = candidate-minus-control on ribbon_ride trades landing on J's OP-16 "
                     "anchor dates -- disclosure only, not a formal gate here (regime validator "
                     "already ran its own gates)",
        },
        "trades": rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"REGIME-CONDITIONED VERDICT: {regime_result.get('verdict')}")
    print(json.dumps(regime_result, indent=2, default=str))
    return 0


def write_markdown(out: dict) -> None:
    r = out["regime_conditioned_validation"]
    L = [
        f"# Exit-quality A/B -- {out['candidate_name']} (GOAL-REPLAY-TODAY-GREEN iteration 6, step 3)",
        "",
        f"Generated {out['generated_at']}. Runner: `backtest/tools/exit_variant_ab.py`.",
        "",
        f"**Control shape:** `{out['control_shape']}`",
        "",
        f"**Candidate shape:** `{out['candidate_shape']}`",
        "",
        f"Window {out['window']}, n_ribbon_ride_trades={out['n_ribbon_ride_trades']}, "
        f"n_replayed={out['n_replayed']}, cache_misses={out['cache_misses']}.",
        "",
        "## Full-population result",
        "",
        f"| control total | candidate total | delta |",
        f"|--:|--:|--:|",
        f"| ${out['control_total_pnl']:,.2f} | ${out['candidate_total_pnl']:,.2f} | ${out['total_delta']:+,.2f} |",
        "",
        "## Calendar WF disclosure (cross-check only)",
        "",
        f"{out['calendar_wf_disclosure']}",
        "",
        "## Regime-conditioned validation (the earned methodology, iteration 5)",
        "",
        f"Target bucket: **{r.get('target_regime_bucket')}** "
        f"(n_bucket={r.get('n_bucket')}, concentration={r.get('target_regime_bucket_meta', {}).get('concentration_pct')}%)",
        "",
        f"regime-IS delta_mean=${r.get('regime_is_delta_mean')}/tr (n={r.get('n_regime_is')}) -> "
        f"regime-OOS delta_mean=${r.get('regime_oos_delta_mean')}/tr (n={r.get('n_regime_oos')}), "
        f"WF={r.get('wf_delta')}",
        "",
        "| gate | result |",
        "|---|:--:|",
    ]
    for k, v in (r.get("gates") or {}).items():
        L.append(f"| {k} | {v} |")
    L += [
        "",
        f"**Ladder verdict: {r.get('ladder_verdict')}. Overall: {r.get('verdict')}.**",
        "",
        "## Concentration check (fable-too-good hunt)",
        "",
        f"{out['concentration_check']}",
        "",
        "## OP-16 anchor cross-check (disclosure only)",
        "",
        f"{out['anchor_cross_check_op16']}",
        "",
        "## Disclosed limitations",
        "",
        "See module docstring: ribbon_flip_back OFF for this population, TRENDLINE-tier entries "
        "fall back to the shape's premium floor rather than a historical key-level lookup, qty "
        "is backtest-sizing not live-sizing.",
        "",
        "---",
        f"_Source: `backtest/tools/exit_variant_ab.py`. SHIP DECISION lives in "
        f"`automation/overnight/GOAL-REPLAY-TODAY-GREEN.md` ITERATION 6, not this file._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
