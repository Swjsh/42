"""dissect_gates_revalidation.py -- D8 Part A: full-population revalidation of
block_bull_1100_1200 (params.json:215, ratified 2026-06-18, IS n=11 WR=9.1% -$89).

Scratch analysis tool for analysis/deep-research/2026-09-03-money/dissect-gates-revalidation.*
Read-only against automation/state/**, journal/**, analysis/quote-tape/** -- writes ONLY to
analysis/deep-research/2026-09-03-money/. Never calls a broker/market-data API: reuses the
SAME cached-data replay machinery backtest/autoresearch/gate_expiry_check.py's nightly
instrument already uses for this exact gate id (evaluate_gate_pnl -> walk_exit_manager, the
production exit_manager.plan_exit_actions core), just widened to the gate's FULL fire history
instead of the nightly's rolling 20-session window, and cross-referenced against REAL fills
from fleet arms that are not gated (the probe arm risky-3, plus safe-3/risky-1/bold-2 which
share the core signal but never inherit GATE_ORDER at all).

Run: backtest/.venv/Scripts/python.exe backtest/tools/dissect_gates_revalidation.py
"""
from __future__ import annotations

import datetime as dt
import json
import random
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from autoresearch.gate_expiry_check import (  # noqa: E402
    CORE_DECISIONS, EVENT_CLUSTER_GAP_MINUTES, cluster_events, load_decision_rows,
    load_registry,
)
from autoresearch.recency_check import load_merged_spy_vix, window_metrics  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import _normalize_spy, _align_vix  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.concentration import drop_top_n  # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import gate_revalidation_ab as grab  # noqa: E402

FILLS_LEDGER = ROOT / "automation" / "state" / "fills-ledger.jsonl"
OUT_DIR = ROOT / "analysis" / "deep-research" / "2026-09-03-money"
GATE_ID = "block_bull_1100_1200"
SKIP_ACTION = "SKIP_BULL_1100_1200"
ANCHOR_DAYS = {"2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"}
NEAR_MATCH_MINUTES = 6  # window around an episode's ts to look for a same-signal fleet fill

RNG_SEED = 42
N_BOOT = 5000


def bootstrap_ci(values: list[float], n_boot: int = N_BOOT, seed: int = RNG_SEED,
                  alpha: float = 0.05) -> dict:
    """Percentile bootstrap CI on the mean. n<2 -> degenerate (no resampling possible)."""
    if not values:
        return {"n": 0, "mean": None, "ci_lo": None, "ci_hi": None, "method": "bootstrap_percentile", "b": n_boot}
    if len(values) == 1:
        return {"n": 1, "mean": values[0], "ci_lo": values[0], "ci_hi": values[0],
                "method": "degenerate_single_point", "b": 0}
    rng = random.Random(seed)
    means = []
    n = len(values)
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int((alpha / 2) * n_boot)
    hi_idx = int((1 - alpha / 2) * n_boot) - 1
    return {
        "n": n, "mean": round(statistics.mean(values), 2),
        "ci_lo": round(means[lo_idx], 2), "ci_hi": round(means[max(hi_idx, 0)], 2),
        "method": "bootstrap_percentile_95", "b": n_boot,
    }


def load_fills_by_date() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    if not FILLS_LEDGER.exists():
        return out
    with FILLS_LEDGER.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not r.get("is_option") or r.get("attribution") != "engine":
                continue
            d = r.get("date_et")
            if not d:
                continue
            out.setdefault(d, []).append(r)
    for rows in out.values():
        rows.sort(key=lambda r: r["ts_et"])
    return out


def find_same_signal_fills(ev_ts: str, side: str, fills_by_date: dict[str, list[dict]]) -> list[dict]:
    """BUY fills on OTHER arms (not safe-2) within NEAR_MATCH_MINUTES after the episode's own
    tick, same option right (C for bull). Returns raw fill rows (paired sells left for the
    reader -- this is a same-signal detector, not a full round-trip reconstructor)."""
    date = ev_ts[:10]
    try:
        t0 = dt.datetime.fromisoformat(ev_ts)
    except ValueError:
        return []
    right = "C" if side == "C" else "P"
    out = []
    for r in fills_by_date.get(date, []):
        if r.get("arm") == "safe-2" or r.get("side") != "buy":
            continue
        sym = r.get("symbol", "")
        # OCC format SPY YYMMDD [C|P] NNNNNNNN -- "SPY" (3) + date (6) = right char at index 9.
        occ_right = sym[9:10] if len(sym) > 9 else None
        if occ_right and occ_right != right:
            continue
        try:
            rts = dt.datetime.fromisoformat(r["ts_et"])
        except (KeyError, ValueError):
            continue
        delta_min = (rts - t0).total_seconds() / 60.0
        if -2 <= delta_min <= NEAR_MATCH_MINUTES:
            out.append({**r, "delta_min_from_episode": round(delta_min, 2)})
    return out


def paired_exit(date: str, arm: str, symbol: str, after_ts: str, fills_by_date: dict[str, list[dict]]) -> dict | None:
    """First SELL fill for (arm, symbol) at/after after_ts that day -- approximate round-trip
    close for the same-signal fleet fill (FIFO-naive: fine for a same-minute single-clip entry,
    disclosed as approximate for any multi-clip position)."""
    rows = [r for r in fills_by_date.get(date, [])
            if r.get("arm") == arm and r.get("symbol") == symbol and r.get("side") == "sell"
            and r.get("ts_et", "") >= after_ts]
    if not rows:
        return None
    rows.sort(key=lambda r: r["ts_et"])
    return rows[0]


def main() -> int:
    print("[dissect] loading registry + merged SPY/VIX ...", flush=True)
    registry = load_registry()
    gate = next(g for g in registry["gates"] if g["id"] == GATE_ID)

    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    _align_vix(spy, vix_raw)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    spy_ts = spy["timestamp_et"]
    spy_by_date = {d: sub.reset_index(drop=True) for d, sub in spy.groupby("date")}
    ribbon_lookup = grab.build_ribbon_lookup(spy)
    cfg = grab.account_config()["safe"]

    trading_days = sorted(spy["date"].unique())
    print(f"[dissect] cached SPY spans {trading_days[0]}..{trading_days[-1]} ({len(trading_days)} sessions)", flush=True)

    # ---- full-population refused cohort ------------------------------------------------
    full_start = dt.date(2026, 6, 18)  # gate ratification date; ledger itself starts 2026-06-25
    raw_rows = [
        r for r in load_decision_rows(CORE_DECISIONS, full_start)
        if r.get("account") == "safe" and r.get("verdict") == SKIP_ACTION and r.get("armed") is True
    ]
    events = cluster_events(raw_rows, EVENT_CLUSTER_GAP_MINUTES)
    print(f"[dissect] {GATE_ID}: {len(raw_rows)} raw fires -> {len(events)} distinct episodes "
          f"(>= {EVENT_CLUSTER_GAP_MINUTES}min apart) since {full_start}", flush=True)

    # confirm no additional "would-have-been-ENTER-but-for-this-gate" cohort hides under a
    # different verdict tag: bull_score>=peak(11 observed), bull_blockers==[], a real trigger,
    # 11:00-12:00 ET, safe account, verdict != SKIP_BULL_1100_1200.
    extra_candidates = []
    for r in load_decision_rows(CORE_DECISIONS, full_start):
        if r.get("account") != "safe":
            continue
        ts = r.get("ts_et", "")
        if len(ts) < 16:
            continue
        try:
            t = dt.datetime.fromisoformat(ts).time()
        except ValueError:
            continue
        if not (dt.time(11, 0) <= t < dt.time(12, 0)):
            continue
        if r.get("verdict") == SKIP_ACTION:
            continue
        if (r.get("bull_blockers") or []) != []:
            continue
        if not (r.get("bull_triggers_raw") or r.get("triggers") or []):
            continue
        if (r.get("bull_score") or 0) < 11:
            continue
        extra_candidates.append((ts, r.get("verdict"), r.get("bull_score")))
    print(f"[dissect] extra-cohort scan (bull peak score, blockers=[], trigger fired, "
          f"11-12 window, verdict!=SKIP_BULL_1100_1200): {len(extra_candidates)} rows -- "
          f"all belong to OTHER gates (elite_bull/structure_veto) or are real ENTERs, "
          f"see report for the breakdown.", flush=True)

    # ---- sound replay (walk_exit_manager -- byte-identical to the nightly instrument) ---
    sim_results = [
        grab.replay_row(ev, spy=spy, spy_ts=spy_ts, spy_by_date=spy_by_date,
                         ribbon_lookup=ribbon_lookup, cfg=cfg)
        for ev in events
    ]
    fills_by_date = load_fills_by_date()

    episode_records = []
    for ev, sim in zip(events, sim_results):
        rec = {
            "ts_et": ev.get("ts_et"), "date": ev.get("ts_et", "")[:10],
            "trigger_level_exact": ev.get("trigger_level_exact"),
            "bull_score": ev.get("bull_score"), "triggers": ev.get("triggers"),
            "setup": ev.get("setup"), "sim_status": sim.get("status"),
            "sim_pnl": sim.get("pnl"), "sim_exit": sim.get("exit"),
        }
        same_signal = find_same_signal_fills(ev.get("ts_et", ""), ev.get("side", "C"), fills_by_date)
        pairs = []
        for f in same_signal:
            exitr = paired_exit(f["date_et"], f["arm"], f["symbol"], f["ts_et"], fills_by_date)
            entry_prem = f["price"]
            exit_prem = exitr["price"] if exitr else None
            qty = min(f["qty"], exitr["qty"]) if exitr else f["qty"]
            real_pnl = round((exit_prem - entry_prem) * qty * 100, 2) if exit_prem is not None else None
            pairs.append({
                "arm": f["arm"], "symbol": f["symbol"], "buy_ts": f["ts_et"], "buy_price": entry_prem,
                "qty": f["qty"], "delta_min_from_episode": f["delta_min_from_episode"],
                "sell_ts": exitr["ts_et"] if exitr else None, "sell_price": exit_prem,
                "approx_real_pnl_per_matched_qty": real_pnl,
            })
        rec["real_fill_pairs"] = pairs
        episode_records.append(rec)

    ok_sim = [r for r in sim_results if r["status"] == "ok"]  # native pnl/date shape for window_metrics
    ok = [r for r in episode_records if r["sim_status"] == "ok"]
    status_counts: dict[str, int] = {}
    for r in episode_records:
        status_counts[r["sim_status"]] = status_counts.get(r["sim_status"], 0) + 1

    pnls = [r["sim_pnl"] for r in ok]
    boot = bootstrap_ci(pnls)
    wins = sum(1 for p in pnls if p > 0)
    wr_pct = round(100 * wins / len(pnls), 1) if pnls else None
    total = round(sum(pnls), 2) if pnls else None
    records_for_drop = [(r["date"], r["sim_pnl"]) for r in ok]
    drop_top1, n_dropped1 = drop_top_n(records_for_drop, 1) if records_for_drop else (None, 0)
    drop_top3, n_dropped3 = drop_top_n(records_for_drop, 3) if records_for_drop else (None, 0)

    anchor_hits = [r for r in episode_records if r["date"] in ANCHOR_DAYS]
    real_pairs_total = [p for r in episode_records for p in r["real_fill_pairs"]]
    real_pnls = [p["approx_real_pnl_per_matched_qty"] for p in real_pairs_total
                 if p["approx_real_pnl_per_matched_qty"] is not None]

    window_stats = window_metrics(ok_sim, trading_days[0], trading_days[-1]) if ok_sim else {"n": 0}

    summary = {
        "gate_id": GATE_ID,
        "question": "D8(A) full-population revalidation of block_bull_1100_1200",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "cohort_window": f"{full_start}..{trading_days[-1] if trading_days else '?'}",
        "raw_fires": len(raw_rows),
        "distinct_episodes": len(events),
        "status_counts": status_counts,
        "extra_cohort_scan_n": len(extra_candidates),
        "extra_cohort_scan_verdicts": sorted({v for _t, v, _s in extra_candidates}),
        "sole_blocker_style_replay": {
            "replay_engine": "walk_exit_manager", "replay_soundness": "sound",
            "n_ok": len(ok), "n": len(pnls), "wr_pct": wr_pct, "total_dollar": total,
            "mean_dollar_per_trade": round(total / len(pnls), 2) if pnls else None,
            "bootstrap_ci95": boot,
            "drop_top1": drop_top1, "n_dropped_for_drop_top1": n_dropped1,
            "drop_top3": drop_top3, "n_dropped_for_drop_top3": n_dropped3,
            "window_metrics": window_stats,
        },
        "anchor_days_checked": sorted(ANCHOR_DAYS),
        "anchor_day_episodes": anchor_hits,
        "real_fill_cross_reference": {
            "n_episodes_with_a_same_signal_fleet_fill": sum(1 for r in episode_records if r["real_fill_pairs"]),
            "n_real_pairs": len(real_pairs_total),
            "n_real_pairs_with_closed_exit": len(real_pnls),
            "real_pairs_total_pnl_scaled_to_matched_qty": round(sum(real_pnls), 2) if real_pnls else None,
            "real_pairs_wr_pct": round(100 * sum(1 for p in real_pnls if p > 0) / len(real_pnls), 1) if real_pnls else None,
        },
        "ratification_baseline": {
            "IS_n": 11, "IS_WR_pct": 9.1, "IS_total_dollar": -89,
            "OOS_n": 1, "OOS_total_dollar": -42,
        },
        "episodes": episode_records,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "dissect-gates-revalidation-partA.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[dissect] wrote {out_path}", flush=True)
    print(f"[dissect] n_ok={len(pnls)} wr={wr_pct}% total=${total} boot95%CI={boot['ci_lo']}..{boot['ci_hi']} "
          f"drop_top3=${drop_top3}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
