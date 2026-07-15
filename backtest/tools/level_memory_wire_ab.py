"""level_memory_wire_ab.py -- G11-LEVEL-MEMORY-AB-REPLAY (queue.md 2026-07-09).

Pre-registered spec: analysis/recommendations/prereg-level-memory-wire-2026-07-15.json
(read that FIRST -- this module implements it verbatim, no re-picks).

WHAT THIS ANSWERS: the G11 level-memory wire (setup/scripts/refresh_levels_intraday.py
#_merge_memory_levels, LIVE since 2026-07-09, gated by params.json's
level_memory_live_merge) unions the shadow multi-day memory map into the live
key-levels.json feed -- but shipped with no A/B scorecard. This script builds one.

MECHANISM: the backtest engine's own level detection (backtest/lib/levels.py) has
ZERO notion of level_memory -- it derives levels purely from OHLC price structure.
CONTROL (vanilla run_backtest) is therefore the correct proxy for "wire OFF" /
current backtest-modeled behavior. TREATMENT unions the SAME memory-merge formula
(nearest-6 within 1.5% of spot, score>=60/tier==Active) via the new additive
`memory_levels_by_day` kwarg on backtest/lib/levels.py#_detect_from_history --
real production trigger logic (filters.py), not a reimplementation.

Usage:
    cd backtest
    .venv/Scripts/python.exe tools/level_memory_wire_ab.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from lib.orchestrator import run_backtest  # noqa: E402
import level_memory_producer as LMP  # noqa: E402

DATA = BACKTEST / "data"
PARAMS_PATH = REPO / "automation" / "state" / "params.json"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"

MASTER = "2026-05-19_2026-07-14"
SPY_CSV = DATA / f"spy_5m_{MASTER}.csv"
VIX_CSV = DATA / f"vix_5m_{MASTER}.csv"

LOOKBACK_START = dt.date(2026, 5, 19)   # buffer for the 10-trading-day memory lookback
SCORE_START = dt.date(2026, 6, 5)
SCORE_END = dt.date(2026, 7, 14)

WIRE_LIVE_SINCE = dt.date(2026, 7, 9)   # params.json flag flipped true 2026-07-09 07:02 MT
LIVE_SESSIONS = (dt.date(2026, 7, 9), dt.date(2026, 7, 10), dt.date(2026, 7, 14))

MEMORY_SPOT_PCT = 0.015
MEMORY_CAP = 6
MEMORY_MIN_SCORE = 60.0
INITIAL_EQUITY = 1746.75   # current live Gamma-Safe-2 equity (CLAUDE.md, 2026-07-11)
ATM_STRIKE_OFFSET = 0      # live-truth override (CLAUDE.md strike-tier reconciliation
                            # 2026-07-11): core Safe trades ATM via
                            # crypto/lib/strike_selection.py#V15_SAFE_TIERS; params.json's
                            # v15_strike_offset_per_tier ladder is VESTIGIAL on the live
                            # path (would pick OTM-3 for this equity) -- sim accuracy gate
                            # (CLAUDE.md OP-16) requires the sim match production, so this
                            # study overrides strike_offset explicitly rather than trusting
                            # the stale ladder.


def log(msg: str) -> None:
    print(f"[level_memory_wire_ab] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #

def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    spy = pd.read_csv(SPY_CSV)
    vix = pd.read_csv(VIX_CSV)
    return spy, vix


def trading_days(spy: pd.DataFrame, start: dt.date, end: dt.date) -> list[dt.date]:
    d = pd.to_datetime(spy["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.date
    days = sorted(set(x for x in d if start <= x <= end))
    return days


# --------------------------------------------------------------------------- #
# Causal per-day memory candidate precompute (LOOKBACK_DAYS=10 trading days,
# using ONLY bars strictly before the scored day's first bar -- no look-ahead).
# --------------------------------------------------------------------------- #

def build_memory_candidates_by_day(spy: pd.DataFrame, days: list[dt.date]) -> dict[str, list[dict]]:
    """{date.isoformat(): [{"price":..., "role":...}, ...]} -- tier=='Active' only
    (memory_score>=60, the SAME floor _merge_memory_levels' MEMORY_MERGE_MIN_SCORE uses).
    """
    ts = pd.to_datetime(spy["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    dates = ts.dt.date
    out: dict[str, list[dict]] = {}
    for d in days:
        history = spy[dates < d]
        if len(history) < 50:
            out[d.isoformat()] = []
            continue
        try:
            levels = LMP.build_levels(history)
        except Exception as exc:  # noqa: BLE001 -- fail-open, matches the live producer
            log(f"WARN build_levels failed for {d}: {exc}")
            levels = []
        active = [lv for lv in levels if str(lv.get("tier", "")).lower() == "active"
                  and float(lv.get("memory_score") or 0) >= MEMORY_MIN_SCORE]
        out[d.isoformat()] = [{"price": lv["price"], "role": lv["role"],
                               "memory_score": lv.get("memory_score")} for lv in active]
    return out


# --------------------------------------------------------------------------- #
# Trade diffing
# --------------------------------------------------------------------------- #

def _trade_key(t) -> tuple:
    return (t.entry_time_et.isoformat(), t.side)


def diff_trades(control_trades: list, treatment_trades: list) -> dict:
    c_by_key = {_trade_key(t): t for t in control_trades}
    t_by_key = {_trade_key(t): t for t in treatment_trades}
    c_keys, t_keys = set(c_by_key), set(t_by_key)

    treatment_only = sorted(t_keys - c_keys)
    control_only = sorted(c_keys - t_keys)
    shared_keys = sorted(c_keys & t_keys)

    changed_shared = []
    for k in shared_keys:
        c, t = c_by_key[k], t_by_key[k]
        if (round(c.rejection_level or 0, 2) != round(t.rejection_level or 0, 2)
                or sorted(c.triggers_fired) != sorted(t.triggers_fired)
                or round(c.dollar_pnl, 2) != round(t.dollar_pnl, 2)):
            changed_shared.append({
                "entry_time_et": k[0], "side": k[1],
                "control": {"rejection_level": c.rejection_level, "triggers": c.triggers_fired,
                            "dollar_pnl": round(c.dollar_pnl, 2)},
                "treatment": {"rejection_level": t.rejection_level, "triggers": t.triggers_fired,
                              "dollar_pnl": round(t.dollar_pnl, 2)},
            })

    def _row(t):
        return {"entry_time_et": t.entry_time_et.isoformat(), "side": t.side,
                "setup": t.setup, "strike": t.strike, "qty": t.qty,
                "rejection_level": t.rejection_level, "triggers_fired": t.triggers_fired,
                "dollar_pnl": round(t.dollar_pnl, 2), "exit_reason": str(t.exit_reason)}

    added_rows = [_row(t_by_key[k]) for k in treatment_only]
    removed_rows = [_row(c_by_key[k]) for k in control_only]

    pnl_added = sum(r["dollar_pnl"] for r in added_rows)
    pnl_removed = sum(r["dollar_pnl"] for r in removed_rows)  # signed loss-of-access to treatment
    pnl_shared_delta = sum(round(cs["treatment"]["dollar_pnl"] - cs["control"]["dollar_pnl"], 2)
                            for cs in changed_shared)

    return {
        "n_control_trades": len(control_trades),
        "n_treatment_trades": len(treatment_trades),
        "n_treatment_only_participation": len(added_rows),
        "n_control_only_removed": len(removed_rows),
        "n_shared_behavior_changed": len(changed_shared),
        "n_shared_unchanged": len(shared_keys) - len(changed_shared),
        "pnl_participation_added": round(pnl_added, 2),
        "pnl_removed_trades": round(pnl_removed, 2),
        "pnl_shared_behavior_delta": round(pnl_shared_delta, 2),
        "pnl_combined_a_plus_c": round(pnl_added + pnl_shared_delta, 2),
        "treatment_only_trades": added_rows,
        "control_only_trades": removed_rows,
        "shared_behavior_changed_trades": changed_shared,
    }


def concentration(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, "top1_pct": None, "top3_pct": None}
    total = sum(abs(r["dollar_pnl"]) for r in rows)
    if total == 0:
        return {"n": len(rows), "top1_pct": 0.0, "top3_pct": 0.0}
    ordered = sorted(rows, key=lambda r: -abs(r["dollar_pnl"]))
    top1 = abs(ordered[0]["dollar_pnl"]) / total * 100
    top3 = sum(abs(r["dollar_pnl"]) for r in ordered[:3]) / total * 100
    return {"n": len(rows), "top1_pct": round(top1, 1), "top3_pct": round(top3, 1)}


# --------------------------------------------------------------------------- #
# Real-live cross-check (sub_cohort_A): 3 sessions the wire has actually been
# live for. Cross-references core-decisions.jsonl ENTER rows against the SAME
# causal memory candidate set + spot-band selection used in the counterfactual.
# --------------------------------------------------------------------------- #

def live_cross_check(memory_by_day: dict[str, list[dict]]) -> dict:
    if not CORE_DECISIONS.exists():
        return {"available": False, "reason": "core-decisions.jsonl not found"}
    rows = []
    with CORE_DECISIONS.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    live_days = {d.isoformat() for d in LIVE_SESSIONS}
    hits = []
    n_enter_safe = 0
    for r in rows:
        ts = str(r.get("ts_et") or "")
        day = ts[:10]
        if day not in live_days or str(r.get("account") or "") != "safe":
            continue
        verdict = str(r.get("verdict") or "")
        if not verdict.startswith("ENTER"):
            continue
        n_enter_safe += 1
        lvl = r.get("trigger_level_exact")
        spy_px = r.get("spy")
        if lvl is None or spy_px is None:
            continue
        cands = memory_by_day.get(day) or []
        band = float(spy_px) * MEMORY_SPOT_PCT
        picks = sorted(
            (abs(round(float(c["price"]), 2) - float(spy_px)), round(float(c["price"]), 2))
            for c in cands if abs(round(float(c["price"]), 2) - float(spy_px)) <= band
        )[:MEMORY_CAP]
        for dist, price in picks:
            if abs(price - float(lvl)) <= 0.10:
                hits.append({"date": day, "ts_et": ts, "trigger_level_exact": lvl,
                             "matched_memory_price": price, "verdict": verdict,
                             "setup": r.get("setup")})
                break

    return {"available": True, "sessions": sorted(live_days),
            "n_enter_verdicts_safe": n_enter_safe,
            "n_matched_memory_sourced": len(hits), "matches": hits}


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    log(f"loading {SPY_CSV.name} / {VIX_CSV.name}")
    spy, vix = load_data()

    base_params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    from lib.orchestrator import _params_to_kwargs  # noqa: PLC0415
    kwargs = _params_to_kwargs(base_params, account_equity=INITIAL_EQUITY)
    kwargs["strike_offset"] = ATM_STRIKE_OFFSET  # live-truth override, see module docstring

    score_days = trading_days(spy, SCORE_START, SCORE_END)
    log(f"scoring window {SCORE_START}..{SCORE_END}: {len(score_days)} trading days")

    log("precomputing causal per-day memory candidates (LOOKBACK_DAYS=10 trading days)...")
    memory_by_day = build_memory_candidates_by_day(spy, score_days)
    n_days_with_candidates = sum(1 for v in memory_by_day.values() if v)
    log(f"{n_days_with_candidates}/{len(score_days)} scored days have >=1 tier=Active memory candidate")

    log("running CONTROL backtest (real fills, live Safe params, no memory merge)...")
    control = run_backtest(
        spy, vix, start_date=SCORE_START, end_date=SCORE_END,
        use_real_fills=True, params_overrides=base_params, initial_equity=INITIAL_EQUITY,
        **{k: v for k, v in kwargs.items()},
    )
    log(f"CONTROL: {len(control.trades)} trades")

    log("running TREATMENT backtest (same + memory_levels_by_day injection)...")
    treatment = run_backtest(
        spy, vix, start_date=SCORE_START, end_date=SCORE_END,
        use_real_fills=True, params_overrides=base_params, initial_equity=INITIAL_EQUITY,
        level_flags={"memory_levels_by_day": memory_by_day,
                     "memory_spot_pct": MEMORY_SPOT_PCT, "memory_cap": MEMORY_CAP},
        **{k: v for k, v in kwargs.items()},
    )
    log(f"TREATMENT: {len(treatment.trades)} trades")

    diff = diff_trades(control.trades, treatment.trades)
    conc_added = concentration(diff["treatment_only_trades"])
    conc_changed = concentration([
        {"dollar_pnl": cs["treatment"]["dollar_pnl"] - cs["control"]["dollar_pnl"]}
        for cs in diff["shared_behavior_changed_trades"]
    ])

    log("cross-checking the 3 real wire-live sessions against core-decisions.jsonl...")
    live_check = live_cross_check(memory_by_day)

    # ---- Verdict per the pre-registered kill criteria ----
    n_effect = diff["n_treatment_only_participation"] + diff["n_shared_behavior_changed"]
    combined_pnl = diff["pnl_combined_a_plus_c"]
    if n_effect == 0:
        verdict = "NO_EFFECT"
    elif n_effect < 15:
        verdict = "NEGATIVE_INSUFFICIENT_N" if combined_pnl < 0 else "INSUFFICIENT_N"
    elif combined_pnl < 0:
        verdict = "NEGATIVE"
    else:
        verdict = "POSITIVE"

    out = {
        "_doc": "G11-LEVEL-MEMORY-AB-REPLAY scorecard. Pre-reg: analysis/recommendations/"
                "prereg-level-memory-wire-2026-07-15.json (frozen before this run).",
        "generated_at_et": dt.datetime.now().isoformat(timespec="seconds"),
        "window": {"lookback_buffer": [LOOKBACK_START.isoformat(), SCORE_START.isoformat()],
                   "scored": [SCORE_START.isoformat(), SCORE_END.isoformat()],
                   "n_scored_trading_days": len(score_days),
                   "n_days_with_memory_candidates": n_days_with_candidates,
                   "wire_live_since": WIRE_LIVE_SINCE.isoformat(),
                   "real_wire_live_sessions_in_window": [d.isoformat() for d in LIVE_SESSIONS]},
        "config": {"use_real_fills": True, "initial_equity": INITIAL_EQUITY,
                   "strike_offset_atm_override": ATM_STRIKE_OFFSET,
                   "memory_spot_pct": MEMORY_SPOT_PCT, "memory_cap": MEMORY_CAP,
                   "memory_min_score": MEMORY_MIN_SCORE},
        "trade_diff": diff,
        "concentration": {"participation_added": conc_added, "shared_behavior_changed": conc_changed},
        "live_cross_check_sub_cohort_A": live_check,
        "verdict": verdict,
        "verdict_basis": (
            f"n_effect (participation + shared-behavior-change) = {n_effect}, "
            f"combined P&L delta = ${combined_pnl:.2f}, evidence floor = 15 (OP-16 advisory)."
        ),
        "flag_recommendation": (
            "flip level_memory_live_merge to FALSE (queue item's own pre-authorized revert)"
            if verdict == "NEGATIVE" else
            "leave level_memory_live_merge ON -- inert in the modeled window, not harmful"
            if verdict == "NO_EFFECT" else
            "leave level_memory_live_merge ON -- insufficient n for a kill verdict"
            if "INSUFFICIENT_N" in verdict else
            "leave level_memory_live_merge ON -- positive/neutral in the modeled window"
        ),
    }

    out_path = REPO / "analysis" / "recommendations" / "level-memory-wire.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {out_path}")

    log("=" * 70)
    log(f"VERDICT: {verdict}")
    log(f"  participation (treatment-only): n={diff['n_treatment_only_participation']} "
        f"pnl=${diff['pnl_participation_added']:.2f}")
    log(f"  removed (control-only):         n={diff['n_control_only_removed']} "
        f"pnl=${diff['pnl_removed_trades']:.2f}")
    log(f"  shared behavior-changed:        n={diff['n_shared_behavior_changed']} "
        f"pnl_delta=${diff['pnl_shared_behavior_delta']:.2f}")
    log(f"  combined (a+c): ${combined_pnl:.2f}")
    log(f"  live cross-check: {live_check.get('n_matched_memory_sourced', 'n/a')} / "
        f"{live_check.get('n_enter_verdicts_safe', 'n/a')} real ENTER rows on the 3 "
        f"wire-live sessions matched a memory-sourced level")
    log(f"  recommendation: {out['flag_recommendation']}")
    log("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
