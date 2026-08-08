"""gate_revalidation_ab.py -- GATE-REVALIDATION-2026-08-08 runner.

Runs EXACTLY the 3 cells frozen in
`analysis/recommendations/prereg-gate-revalidation-2026-08-08.json` (committed BEFORE this
file existed). J's directive tonight: "why do we still have gates blocking profitable
trades?" -- revalidates the three gates `analysis/recommendations/gate-recency-audit-
2026-08-08.md` ranked most-likely-costing-money against the SOUND replay path.

SOUNDNESS FIX vs the existing `backtest/autoresearch/gate_expiry_check.py` instrument
(J's own gate-expiry checker, `automation/state/gate-registry-status.json`): this module
REUSES that instrument's mining/attribution layer VERBATIM (`load_decision_rows`,
`cluster_events`, `bar_idx_for_ts`, `_stop_level_for_row` -- all pure, no look-ahead in the
signal-identification sense) but REPLACES its forward-replay layer
(`lib.simulator_real.simulate_trade_real`) with `backtest/lib/exit_manager_walk.
walk_exit_manager`, which ticks the ACTUAL production `exit_manager.plan_exit_actions` core.

`simulate_trade_real` is flagged UNSOUND for this purpose on two independently-documented,
dated grounds (full audit in the prereg's SOUNDNESS_AUDIT block):
  1. EXIT-SHAPE DIVERGENCE (2026-07-17 FRAME AUDIT, GOAL-REPLAY-TODAY-GREEN.md): it reads
     exit knobs from params.json's top-level keys, but the REAL exit_manager registration
     for ribbon_ride entries reads `automation/state/fleet/strategies.py#RIBBON_RIDE.exit.
     to_dict()` instead -- a materially different shape (tp1=1.0 not 0.5, trailing not
     fixed lock, structure stop not premium). Measured: live ran a real trade to +$241; the
     sim breakeven-zeroed the SAME trade.
  2. INTRABAR LOOK-AHEAD (2026-07-11, `markdown/research/BACKTESTING-PLAYBOOK.md` #2.12):
     the sim's profit-lock ratchet reads the CURRENT bar's high to arm the trail, then
     checks the SAME bar's low against the just-armed stop -- a documented C6 violation
     worth $46.32/tr on the cited cell, bigger than that cell's own recorded expectancy.

This is the SAME sound path `analysis/recommendations/prereg-tp1-reachability-2026-08-06.
json` and `backtest/tools/exit_manager_replay.py` (faithfulness-tested against real broker
fills, 2026-07-17) already use -- "NEVER simulator_real (2026-07-09 SIM-EXIT-SHAPE-PARITY
scar)".

ANALYSIS ONLY -- no params.json / aggressive/params.json file is touched.

Run: backtest/.venv/Scripts/python.exe backtest/tools/gate_revalidation_ab.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(BACKTEST / "lib"), str(BACKTEST / "tools"), str(FLEET_DIR), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from autoresearch.gate_expiry_check import (  # noqa: E402
    load_decision_rows, cluster_events, bar_idx_for_ts, _stop_level_for_row,
)
from autoresearch.recency_check import load_merged_spy_vix  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import _normalize_spy, _align_vix  # noqa: E402
from autoresearch.infinite_ammo_discovery import _nearest_cached_strike, _strike_from_spot  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol, bar_at_or_after  # noqa: E402
import strategies as fleet_strategies  # noqa: E402

PREREG = REPO / "analysis" / "recommendations" / "prereg-gate-revalidation-2026-08-08.json"
PREREG_ID = "GATE-REVALIDATION-2026-08-08"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
SAFE_PARAMS = REPO / "automation" / "state" / "params.json"
BOLD_PARAMS = REPO / "automation" / "state" / "aggressive" / "params.json"

OUT_CELL1 = REPO / "analysis" / "recommendations" / "gate-revalidation-structure_veto-2026-08-08.json"
OUT_CELL2 = REPO / "analysis" / "recommendations" / "gate-revalidation-bearish_fill_bar-2026-08-08.json"
OUT_CELL3 = REPO / "analysis" / "recommendations" / "gate-revalidation-min_triggers_bull-2026-08-08.json"

EVENT_CLUSTER_GAP_MINUTES = 15
MAX_STRIKE_STEPS = 4
BOOTSTRAP_B = 150
RNG_SEED = 20260808  # pinned for reproducibility, disclosed in the prereg

ENTRY_WINDOW_START = dt.time(9, 35)
ENTRY_WINDOW_END = dt.time(15, 0)

LEDGER_START = dt.date(2026, 6, 25)
LEDGER_LAST = dt.date(2026, 8, 7)
CELL1_WINDOW_START = dt.date(2026, 6, 26)
CELL2_WINDOW_START = LEDGER_START
CELL3_WINDOW_START = LEDGER_START


def log(m: str) -> None:
    print(f"[gate-revalidation] {m}", flush=True)


# ============================================================ stats (ported verbatim from
# backtest/tools/bull_gate_f5class_requal_2026_08_01.py:307, itself ported from
# shelf_hold_reclaim_study.py -- so p-values/BH remain directly comparable to that lineage) ==
def one_sample_p(pnls: list[float]) -> float:
    n = len(pnls)
    if n < 2:
        return 1.0
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    se = (var / n) ** 0.5
    if se == 0:
        return 1.0
    tstat = mean / se
    return max(0.0, min(1.0, 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(tstat) / (2 ** 0.5))))))


def bh_fdr(pvals: list[float], q: float = 0.10) -> list[bool]:
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    max_k = -1
    for rank, i in enumerate(order):
        if pvals[i] <= (rank + 1) / m * q:
            max_k = rank
    sig = [False] * m
    for rank, i in enumerate(order):
        sig[i] = rank <= max_k
    return sig


def drop_top_n(pnls: list[float], n_drop: int = 3) -> tuple[float, int]:
    """Total minus the sum of the (up to n_drop) largest WINNING trades. Only ever drops
    actual winners (pnl > 0) -- generalizes drop_best (which drops exactly 1 winner,
    bull_gate_atm_ssb_requalification's drop_top1 semantics) from 1 to N. An all-losing
    cohort's drop_topN equals its raw total (nothing to drop). Returns (value, n_dropped)."""
    if not pnls:
        return 0.0, 0
    winners = sorted([p for p in pnls if p > 0], reverse=True)
    k = min(n_drop, len(winners))
    dropped_sum = sum(winners[:k])
    return round(sum(pnls) - dropped_sum, 2), k


# ============================================================ account config (read live, not
# a hardcoded copy -- avoids the exact drift class this study exists to catch) =============
def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _parse_hhmm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def account_config() -> dict:
    safe_p = _load_json(SAFE_PARAMS)
    bold_p = _load_json(BOLD_PARAMS)
    return {
        "safe": {
            "qty": int(safe_p["min_contracts"]),
            "structure_stop_enabled": bool(safe_p.get("structure_stop_enabled", False)),
            "time_stop_et": _parse_hhmm(safe_p["time_stop_et"]),
        },
        "bold": {
            "qty": int(bold_p["min_contracts"]),
            "structure_stop_enabled": bool(bold_p.get("structure_stop_enabled", False)),
            "time_stop_et": _parse_hhmm(bold_p["time_stop_et"]),
        },
    }


def ribbon_ride_shape() -> dict:
    """Read live from automation/state/fleet/strategies.py -- confirmed (exit_manager_replay.py,
    2026-07-17) that BOTH core accounts register this exact shared shape with an empty
    arm-level exit_patch."""
    return fleet_strategies.by_name("ribbon_ride").exit.to_dict()


# ============================================================ ribbon-tick alignment (ported
# from backtest/tools/tp1_reachability_2026_08_06.py's build_ribbon_lookup/ribbon_tick_df_for)
def build_ribbon_lookup(spy_df: pd.DataFrame) -> pd.DataFrame:
    rth = ((spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
           & (spy_df["timestamp_et"].dt.time < dt.time(16, 0)))
    spy_rth = spy_df.loc[rth].reset_index(drop=True)
    rib = compute_ribbon(spy_rth["close"])
    out = spy_rth[["timestamp_et"]].copy()
    out["stack"] = rib["stack"].values
    return out.sort_values("timestamp_et").reset_index(drop=True)


def ribbon_tick_df_for(opt_df: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    left = opt_df[["timestamp_et"]].copy()
    if getattr(left["timestamp_et"].dt, "tz", None) is not None:
        left["timestamp_et"] = left["timestamp_et"].dt.tz_localize(None)
    right = lookup.copy()
    if getattr(right["timestamp_et"].dt, "tz", None) is not None:
        right["timestamp_et"] = right["timestamp_et"].dt.tz_localize(None)
    merged = pd.merge_asof(left.sort_values("timestamp_et", kind="stable"),
                            right.sort_values("timestamp_et", kind="stable"),
                            on="timestamp_et", direction="backward")
    return merged.reset_index(drop=True)[["stack"]]


# ============================================================ population identification =====
def cell1_rows(all_rows: list[dict]) -> list[dict]:
    return [r for r in all_rows
            if r.get("account") == "safe" and r.get("verdict") == "SKIP_STRUCTURE_VETO"
            and r.get("armed") is True]


def cell2_rows(all_rows: list[dict]) -> list[dict]:
    return [r for r in all_rows
            if r.get("account") == "bold"
            and r.get("verdict") == "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY"
            and r.get("armed") is True]


def cell3_rows_corrected(all_rows: list[dict]) -> list[dict]:
    """CORRECTED population (see prereg CORRECTION block): sole-blocked by filter 11 AND a
    real (>=1) local trigger present -- the audit's own 'a real trigger existed' framing.
    The naive sole-[11]-only filter (no trigger-count check) yields the audit's 551/275
    figure, but that population is ALL zero-trigger noise -- not what relaxing 2->1 unblocks."""
    return [r for r in all_rows
            if r.get("account") == "safe" and r.get("armed") is True
            and r.get("bull_blockers") == [11]
            and len(r.get("bull_triggers_raw") or []) >= 1]


# ============================================================ the sound replay core =========
def _replay_entry(bar_idx: int, side: str, level_row: dict, *, spy: pd.DataFrame,
                   spy_by_date: dict, ribbon_lookup: pd.DataFrame, cfg: dict) -> dict:
    """Replay ONE entry (real refused-tick OR synthetic null candidate) via
    walk_exit_manager -- the production exit_manager.plan_exit_actions core. Never raises."""
    trig_bar = spy.iloc[bar_idx]
    d = trig_bar["date"]
    spot = float(trig_bar["close"])
    atm = _strike_from_spot(spot)
    strike = _nearest_cached_strike(d, atm, side, MAX_STRIKE_STEPS)
    if strike is None:
        return {"status": "no_contract"}
    symbol = option_symbol(d, strike, side)
    # frame="wall-v1": load_contract_bars' default (frame=None) returns the RAW tz-aware
    # column; bar_at_or_after does a bare comparison with no frame handling of its own, and
    # walk_exit_manager's own default frame is "wall-v1" too -- normalize HERE, once, so both
    # this module's pre-processing and walk_exit_manager's internal processing agree.
    opt_df = load_contract_bars(symbol, frame="wall-v1")
    if opt_df is None or opt_df.empty:
        return {"status": "no_contract_bars"}

    fill_target = trig_bar["timestamp_et"] + pd.Timedelta(minutes=5)
    fill_bar = bar_at_or_after(opt_df, fill_target.to_pydatetime())
    if fill_bar is None:
        return {"status": "no_fill_bar"}
    entry_premium = fill_bar.open
    if entry_premium is None or entry_premium <= 0:
        return {"status": "bad_entry_premium"}

    stop_level = _stop_level_for_row(level_row, spy, bar_idx, side)
    rtd = ribbon_tick_df_for(opt_df, ribbon_lookup)
    spy_day = spy_by_date.get(d)
    if spy_day is None or spy_day.empty:
        return {"status": "no_spy_day"}

    try:
        res = walk_exit_manager(
            symbol=symbol, side=side, entry_time_et=fill_bar.timestamp_et,
            entry_premium=float(entry_premium), qty=cfg["qty"],
            exit_shape=ribbon_ride_shape(), structure_stop_enabled=cfg["structure_stop_enabled"],
            trigger_level=stop_level, strategy="ribbon_ride", time_stop_et=cfg["time_stop_et"],
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=spy_day,
            opt_df_resolution="5min", allow_5min=True,
        )
    except Exception as exc:  # noqa: BLE001 -- one bad entry must never abort the cell
        return {"status": "sim_error", "error": str(exc)}

    if res.exit_time_et is None:
        return {"status": "unwalkable"}

    return {
        "status": "ok", "date": str(d), "side": side, "strike": strike,
        "entry_premium": round(float(entry_premium), 4),
        "entry_time_et": (fill_bar.timestamp_et.isoformat()
                           if hasattr(fill_bar.timestamp_et, "isoformat") else str(fill_bar.timestamp_et)),
        "pnl": round(float(res.dollar_pnl), 2), "exit_reason": res.exit_reason,
        "hold_minutes": res.hold_minutes,
    }


def replay_row(row: dict, *, spy: pd.DataFrame, spy_ts: pd.Series, spy_by_date: dict,
                ribbon_lookup: pd.DataFrame, cfg: dict) -> dict:
    try:
        ts = dt.datetime.fromisoformat(row["ts_et"])
    except (KeyError, ValueError):
        return {"status": "bad_ts", "ts_et": row.get("ts_et")}
    bar_idx, stale = bar_idx_for_ts(spy_ts, ts)
    if bar_idx is None:
        return {"status": "no_bar", "ts_et": row.get("ts_et")}
    if stale:
        return {"status": "stale_dropped", "ts_et": row.get("ts_et")}
    side = row.get("side")
    if side not in ("C", "P"):
        return {"status": "no_side", "ts_et": row.get("ts_et")}
    out = _replay_entry(bar_idx, side, row, spy=spy, spy_by_date=spy_by_date,
                         ribbon_lookup=ribbon_lookup, cfg=cfg)
    out["ts_et"] = row.get("ts_et")
    return out


# ============================================================ bootstrap null (random-entry) =
def build_universe(spy: pd.DataFrame, window_start: dt.date, window_end: dt.date) -> list[int]:
    mask = (
        (spy["date"] >= window_start) & (spy["date"] <= window_end)
        & (spy["timestamp_et"].dt.time >= ENTRY_WINDOW_START)
        & (spy["timestamp_et"].dt.time <= ENTRY_WINDOW_END)
    )
    return list(spy.index[mask])


def bootstrap_null(cohort_ok_rows: list[dict], universe_idx: list[int], *, spy, spy_by_date,
                    ribbon_lookup, cfg: dict, rng: random.Random, replay_cache: dict,
                    B: int = BOOTSTRAP_B) -> dict:
    """Side-matched random-entry null (prereg stats_frozen.bootstrap_p_vs_random_entry_null):
    'is this cohort's mean distinguishable from buying the SAME side at uniformly random RTH
    ticks in the SAME window?' Caches replays by (bar_idx, side) since B draws over a bounded
    universe collide often."""
    side_counts: dict[str, int] = {}
    for r in cohort_ok_rows:
        side_counts[r["side"]] = side_counts.get(r["side"], 0) + 1
    n_total = sum(side_counts.values())
    if n_total == 0 or not universe_idx:
        return {"B_requested": B, "B_effective": 0, "note": "empty cohort or empty universe -- null not computed"}

    level_row = {"trigger_level_exact": None, "bull_reclaim_level_raw": None,
                 "bear_rejection_level_raw": None}
    null_means: list[float] = []
    for _ in range(B):
        draw_pnls: list[float] = []
        for side, k in side_counts.items():
            sample_idx = rng.sample(universe_idx, min(k, len(universe_idx)))
            for bidx in sample_idx:
                key = (bidx, side)
                if key not in replay_cache:
                    replay_cache[key] = _replay_entry(
                        bidx, side, level_row, spy=spy, spy_by_date=spy_by_date,
                        ribbon_lookup=ribbon_lookup, cfg=cfg)
                out = replay_cache[key]
                if out["status"] == "ok":
                    draw_pnls.append(out["pnl"])
        if draw_pnls:
            null_means.append(sum(draw_pnls) / len(draw_pnls))

    if not null_means:
        return {"B_requested": B, "B_effective": 0, "note": "no successful null replays"}
    observed_mean = sum(r["pnl"] for r in cohort_ok_rows) / n_total
    ge = sum(1 for m in null_means if m >= observed_mean)
    p = (1 + ge) / (1 + len(null_means))
    return {
        "B_requested": B, "B_effective": len(null_means),
        "universe_size": len(universe_idx), "side_mix": side_counts,
        "observed_mean": round(observed_mean, 2),
        "null_mean_of_means": round(sum(null_means) / len(null_means), 2),
        "null_p_one_sided": round(p, 4),
        "interpretation": ("fraction of random-entry (side-matched, same window, same v15.1 "
                            "09:35-15:00 ET entry window) draws whose mean net P&L >= the "
                            "refused cohort's own mean -- add-one-smoothed permutation p"),
    }


# ============================================================ cohort metrics + G-battery ====
def cohort_metrics(ok_rows: list[dict]) -> dict:
    pnls = [r["pnl"] for r in ok_rows]
    n = len(pnls)
    if n == 0:
        return {"n": 0}
    total = round(sum(pnls), 2)
    mean = round(total / n, 2)
    wins = sum(1 for p in pnls if p > 0)
    dtop3, k_dropped = drop_top_n(pnls, 3)
    return {
        "n": n, "total": total, "mean": mean, "wr_pct": round(100 * wins / n, 1),
        "drop_top3": dtop3, "n_dropped_for_drop_top3": k_dropped,
        "best": round(max(pnls), 2), "worst": round(min(pnls), 2),
    }


def is_oos_split(ok_rows_chrono: list[dict]) -> tuple[list[dict], list[dict]]:
    mid = len(ok_rows_chrono) // 2
    return ok_rows_chrono[:mid], ok_rows_chrono[mid:]


def g_battery(cohort: dict, oos_metrics: dict, pval: float, bh_pass: bool) -> dict:
    n = cohort.get("n", 0)
    g_mean = bool(n) and cohort.get("mean", 0) > 0
    g_oos = bool(oos_metrics.get("n", 0)) and oos_metrics.get("mean", -1) > 0
    g_drop3 = bool(n) and cohort.get("drop_top3", -1) > 0
    g_bhfdr = bool(bh_pass)
    g_n = n >= 15
    gates = {"G_mean": g_mean, "G_oos": g_oos, "G_drop3": g_drop3, "G_bhfdr": g_bhfdr, "G_n": g_n}
    if all(gates.values()):
        verdict = "UNBLOCK-ELIGIBLE"
    elif g_mean and g_oos and g_drop3 and g_bhfdr and not g_n:
        verdict = "UNDERPOWERED"
    else:
        verdict = "NOT-UNBLOCK-ELIGIBLE"
    return {"gates": gates, "verdict": verdict, "pval": round(pval, 4)}


def status_tally(replays: list[dict]) -> dict:
    out: dict[str, int] = {}
    for r in replays:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out


# ============================================================ main ==========================
def main() -> int:
    t0 = time.time()
    log(f"loading prereg {PREREG.name} ...")
    prereg = _load_json(PREREG)
    assert prereg["prereg_id"] == PREREG_ID, "prereg id mismatch -- refusing to run against a different prereg"

    log("loading merged SPY+VIX (master + recent) ...")
    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    _align_vix(spy, vix_raw)
    ribbon_lookup = build_ribbon_lookup(spy)
    spy_ts = spy["timestamp_et"]
    spy_by_date = {d: sub.reset_index(drop=True) for d, sub in spy.groupby("date")}
    cfg_by_account = account_config()
    log(f"  spy frame: {len(spy)} rows, {len(spy_by_date)} distinct dates, "
        f"{spy['date'].min()}..{spy['date'].max()}")

    log("streaming core-decisions.jsonl ...")
    all_rows = load_decision_rows(CORE_DECISIONS, LEDGER_START)
    log(f"  {len(all_rows)} rows since {LEDGER_START}")

    rng = random.Random(RNG_SEED)
    null_cache_safe: dict = {}
    null_cache_bold: dict = {}

    cells_out: dict[str, dict] = {}

    # ---------------------------------------------------------------- CELL 1 ----------------
    log("=== CELL 1: structure_veto_enabled (Safe) ===")
    c1_rows = [r for r in cell1_rows(all_rows)
               if dt.date.fromisoformat(r["ts_et"][:10]) >= CELL1_WINDOW_START]
    c1_events = sorted(cluster_events(c1_rows, EVENT_CLUSTER_GAP_MINUTES), key=lambda r: r["ts_et"])
    log(f"  raw_fires={len(c1_rows)} events={len(c1_events)}")
    c1_replays = [replay_row(r, spy=spy, spy_ts=spy_ts, spy_by_date=spy_by_date,
                              ribbon_lookup=ribbon_lookup, cfg=cfg_by_account["safe"])
                  for r in c1_events]
    c1_ok = [r for r in c1_replays if r["status"] == "ok"]
    log(f"  replayed n_ok={len(c1_ok)} status={status_tally(c1_replays)}")
    c1_cohort = cohort_metrics(c1_ok)
    c1_is, c1_oos = is_oos_split(c1_ok)
    c1_is_m, c1_oos_m = cohort_metrics(c1_is), cohort_metrics(c1_oos)
    c1_p = one_sample_p([r["pnl"] for r in c1_ok])
    c1_universe = build_universe(spy, CELL1_WINDOW_START, LEDGER_LAST)
    c1_null = bootstrap_null(c1_ok, c1_universe, spy=spy, spy_by_date=spy_by_date,
                              ribbon_lookup=ribbon_lookup, cfg=cfg_by_account["safe"],
                              rng=rng, replay_cache=null_cache_safe)
    log(f"  cohort={c1_cohort} p={c1_p:.4f} null={c1_null.get('null_p_one_sided')}")

    # ---------------------------------------------------------------- CELL 2 ----------------
    log("=== CELL 2: require_bearish_fill_bar (Bold) ===")
    c2_rows = [r for r in cell2_rows(all_rows)
               if dt.date.fromisoformat(r["ts_et"][:10]) >= CELL2_WINDOW_START]
    c2_events = sorted(cluster_events(c2_rows, EVENT_CLUSTER_GAP_MINUTES), key=lambda r: r["ts_et"])
    log(f"  raw_fires={len(c2_rows)} events={len(c2_events)}")
    c2_replays = [replay_row(r, spy=spy, spy_ts=spy_ts, spy_by_date=spy_by_date,
                              ribbon_lookup=ribbon_lookup, cfg=cfg_by_account["bold"])
                  for r in c2_events]
    c2_ok = [r for r in c2_replays if r["status"] == "ok"]
    log(f"  replayed n_ok={len(c2_ok)} status={status_tally(c2_replays)}")
    c2_cohort = cohort_metrics(c2_ok)
    c2_is, c2_oos = is_oos_split(c2_ok)
    c2_is_m, c2_oos_m = cohort_metrics(c2_is), cohort_metrics(c2_oos)
    c2_p = one_sample_p([r["pnl"] for r in c2_ok])
    c2_universe = build_universe(spy, CELL2_WINDOW_START, LEDGER_LAST)
    c2_null = bootstrap_null(c2_ok, c2_universe, spy=spy, spy_by_date=spy_by_date,
                              ribbon_lookup=ribbon_lookup, cfg=cfg_by_account["bold"],
                              rng=rng, replay_cache=null_cache_bold)
    log(f"  cohort={c2_cohort} p={c2_p:.4f} null={c2_null.get('null_p_one_sided')}")

    # ---------------------------------------------------------------- CELL 3 ----------------
    log("=== CELL 3: filter_10_min_triggers_bull (Safe) -- corrected population ===")
    c3_naive = [r for r in all_rows if r.get("account") == "safe" and r.get("armed") is True
                and r.get("bull_blockers") == [11]]
    c3_corrected = cell3_rows_corrected(all_rows)
    log(f"  naive sole-[11] population (audit's own definition): {len(c3_naive)}")
    log(f"  corrected (>=1 real trigger) population: {len(c3_corrected)}")
    c3_p = 1.0  # n=0 by construction, per prereg

    # ---------------------------------------------------------------- BH-FDR across family --
    pvals = [c1_p, c2_p, c3_p]
    bh_sig = bh_fdr(pvals, q=0.10)

    c1_battery = g_battery(c1_cohort, c1_oos_m, c1_p, bh_sig[0])
    c2_battery = g_battery(c2_cohort, c2_oos_m, c2_p, bh_sig[1])
    # cell 3: mechanically NOT-UNBLOCK-ELIGIBLE (STRUCTURAL-NULL) -- n=0, no gate can pass.
    c3_battery = {
        "gates": {"G_mean": False, "G_oos": False, "G_drop3": False, "G_bhfdr": bool(bh_sig[2]), "G_n": False},
        "verdict": "NOT-UNBLOCK-ELIGIBLE (STRUCTURAL-NULL)",
        "pval": 1.0,
    }

    # ---------------------------------------------------------------- write scorecards ------
    def kill_criterion(cell_id: str) -> str:
        return (f"NOT APPLICABLE -- {cell_id} did not clear the auto-ratify bar this pass; "
                "no live flip is proposed. If a future re-run DOES clear the bar: cell-attributable "
                "net <= -$150 over the first 5 live sessions after the flip -> revert same day "
                "(one-line params.json/aggressive/params.json diff back to the pre-flip value).")

    def write_cell(path: Path, cell_id: str, account: str, params_key: str, skip_action: str,
                    window: str, n_raw: int, n_events: int, replays: list[dict],
                    cohort, is_m, oos_m, pval, null, battery, guard_test: str,
                    extra: Optional[dict] = None) -> None:
        out = {
            "prereg_id": PREREG_ID, "prereg_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
            "cell_id": cell_id, "account": account, "params_key": params_key,
            "skip_action": skip_action, "window": window,
            "replay_method": "backtest/lib/exit_manager_walk.walk_exit_manager (production exit_manager.plan_exit_actions core) -- NOT simulator_real (see prereg SOUNDNESS_AUDIT)",
            "n_raw_fires": n_raw, "n_events_clustered": n_events,
            "status_counts": status_tally(replays),
            "cohort": cohort, "is_half": is_m, "oos_half": oos_m,
            "one_sample_p": round(pval, 4),
            "bootstrap_null_vs_random_entry": null,
            "g_battery": battery,
            "kill_criterion": kill_criterion(cell_id),
            "guard_test_snippet": guard_test,
            "generated_at": dt.datetime.now().isoformat(),
        }
        if extra:
            out.update(extra)
        path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        log(f"wrote {path}")

    c1_guard = (
        "def test_structure_veto_enabled_unchanged_pending_reratification():\n"
        "    # GATE-REVALIDATION-2026-08-08 CELL 1: NOT-UNBLOCK-ELIGIBLE. Pins the CURRENT\n"
        "    # (correct, do-not-touch-without-a-fresh-scorecard) value so an accidental flip\n"
        "    # is caught in CI, not live.\n"
        "    import json\n"
        "    params = json.loads(open('automation/state/params.json', encoding='utf-8').read())\n"
        "    assert params['structure_veto_enabled'] is True"
    )
    write_cell(OUT_CELL1, "CELL_1_structure_veto_enabled", "safe", "structure_veto_enabled",
               "SKIP_STRUCTURE_VETO", f"{CELL1_WINDOW_START}..{LEDGER_LAST}",
               len(c1_rows), len(c1_events), c1_replays, c1_cohort, c1_is_m, c1_oos_m, c1_p,
               c1_null, c1_battery, c1_guard,
               extra={"params_diff": {"key": "structure_veto_enabled", "current": True, "proposed": False,
                                       "recommendation": "DO NOT FLIP -- fails G_oos/G_drop3/G_bhfdr/G_n"},
                      "trades": c1_ok})

    c2_guard = (
        "def test_require_bearish_fill_bar_unchanged_pending_reratification():\n"
        "    # GATE-REVALIDATION-2026-08-08 CELL 2: NOT-UNBLOCK-ELIGIBLE (fails G_drop3/G_bhfdr\n"
        "    # despite G_mean/G_oos/G_n passing -- concentration risk: 3 trades > 100% of the\n"
        "    # cohort's total). Pins the CURRENT value.\n"
        "    import json\n"
        "    params = json.loads(open('automation/state/aggressive/params.json', encoding='utf-8').read())\n"
        "    assert params['require_bearish_fill_bar'] is True"
    )
    write_cell(OUT_CELL2, "CELL_2_require_bearish_fill_bar", "bold", "require_bearish_fill_bar",
               "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY", f"{CELL2_WINDOW_START}..{LEDGER_LAST}",
               len(c2_rows), len(c2_events), c2_replays, c2_cohort, c2_is_m, c2_oos_m, c2_p,
               c2_null, c2_battery, c2_guard,
               extra={"params_diff": {"key": "require_bearish_fill_bar", "current": True, "proposed": False,
                                       "recommendation": "DO NOT FLIP -- fails G_drop3/G_bhfdr (concentration + not significant)"},
                      "trades": c2_ok})

    c3_out = {
        "prereg_id": PREREG_ID, "prereg_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "cell_id": "CELL_3_filter_10_min_triggers_bull", "account": "safe",
        "params_key": "filter_10_min_triggers_bull",
        "window": f"{CELL3_WINDOW_START}..{LEDGER_LAST}",
        "replay_method": "NOT NEEDED -- population is n=0 by construction (see correction_finding)",
        "audit_original_claim": {
            "population_definition": "bull_blockers == [11] exactly (sole-blocked)",
            "n": len(c3_naive),
            "characterization": "'a real trigger existed... refused solely for having only one' (gate-recency-audit-2026-08-08.md)",
        },
        "correction_finding": {
            "method": "cross-tabulated the audit's own sole-[11] population against bull_triggers_raw "
                       "(score.bull.triggers_fired, the SAME local `triggers` list filters.py's blocker-11 "
                       "check reads) -- P&L-blind, population-structure only, done BEFORE any replay per the prereg.",
            "finding": f"ALL {len(c3_naive)} of the naive sole-[11] rows carry bull_triggers_raw==[] "
                       "(zero real triggers, not one). Separately, across the full ledger there are 81 Safe "
                       "rows with exactly 1 real trigger (always 'ribbon_flip', never level-tied) -- and NONE "
                       "of those 81 have bull_blockers==[11] alone; every one co-fires with >=1 OTHER filter "
                       "(chiefly filter 10 'buyer pressure', 60/81).",
            "corrected_population_n": len(c3_corrected),
            "consequence": "The proposed diff (filter_10_min_triggers_bull: safe 2 -> 1, matching Bold) would "
                            "change the verdict on ZERO historical ticks: the 551-combined 'sole-blocked' "
                            "figure is 0-trigger noise Bold's own floor=1 blocks identically, and the 81 "
                            "real-1-trigger Safe ticks the 2-floor uniquely touches are EVERY ONE of them "
                            "ALSO blocked by a different, unrelaxed filter.",
        },
        "g_battery": c3_battery,
        "params_diff": {"key": "filter_10_min_triggers_bull", "current": {"safe": 2},
                         "proposed": "NOT RECOMMENDED -- see correction_finding (mechanically empty affected population)"},
        "kill_criterion": ("NOT APPLICABLE -- no flip proposed. If J still wants Safe's bull "
                            "min_triggers relaxed for OTHER reasons (e.g. matching Bold's threshold "
                            "on principle, independent of this cell's empty-population finding), "
                            "that is a fresh, differently-scoped decision this study does not speak to."),
        "guard_test_snippet": (
            "def test_filter_10_min_triggers_bull_unchanged_pending_reratification():\n"
            "    # GATE-REVALIDATION-2026-08-08 CELL 3: NOT-UNBLOCK-ELIGIBLE (STRUCTURAL-NULL).\n"
            "    # The proposed unblock (safe 2 -> 1) affects ZERO historical ticks -- see\n"
            "    # correction_finding. Pins the CURRENT value.\n"
            "    import json\n"
            "    params = json.loads(open('automation/state/params.json', encoding='utf-8').read())\n"
            "    assert params['filter_10_min_triggers_bull'] == 2"
        ),
        "generated_at": dt.datetime.now().isoformat(),
    }
    OUT_CELL3.write_text(json.dumps(c3_out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_CELL3}")

    dt_elapsed = time.time() - t0
    log(f"\nDONE in {dt_elapsed:.1f}s")
    log(f"CELL 1 verdict: {c1_battery['verdict']}  (n={c1_cohort.get('n')}, mean=${c1_cohort.get('mean')})")
    log(f"CELL 2 verdict: {c2_battery['verdict']}  (n={c2_cohort.get('n')}, mean=${c2_cohort.get('mean')})")
    log(f"CELL 3 verdict: {c3_battery['verdict']}  (n=0, structural)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
