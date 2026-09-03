"""dissect_f10_bull_relax.py -- D8 Part B: first live run of the FROZEN prereg
analysis/recommendations/bull-f10-buyer-pressure-prereg-2026-08-04.json against the
sole-[10] bull cohort in automation/state/core-decisions.jsonl.

Cohort: HOLD rows (safe + bold, cross-account deduped -- GATE-EXPIRY-SOLE-BLOCKER-DOUBLE-
COUNT convention) whose bull_blockers list is EXACTLY [10], since the earliest ledger date
that field exists (2026-07-27). For each distinct episode:
  - the gate_expiry sole-blocker proxy (NOT_REPLAYED, directional: day's own next real P1
    fill, same side, WIN/LOSS/NONE) -- reused byte-for-bit from gate_expiry_check.py.
  - real fills where another (non-gated) fleet arm took the SAME tick.
  - the actual bar (via trigger_bar_et, the 5m bar filters.py evaluated) replayed against
    buyer_pressure_bar_v11 at the prereg's 4 frozen cells (0.7 baseline / 0.5 / 0.35 / 0.0)
    to see whether relaxing the threshold would ADMIT the episode, and if so, that episode's
    own sound (walk_exit_manager) forward-replay $ outcome.

SCOPE NOTE: the prereg's own `population` field calls for a full 391-day real-OPRA rebuild via
the fullhist/orchestrator battery (bull-gate-f5class-requal-2026-08-01.json template) -- out of
scope for a <5min scratch script. This runner scores the prereg's frozen gates against the
LIVE-ledger sole-[10] cohort only (since 2026-07-27) -- disclosed as a narrower population than
the prereg's own frozen population field asks for; every number is honestly n-labeled.

Run: backtest/.venv/Scripts/python.exe backtest/tools/dissect_f10_bull_relax.py
"""
from __future__ import annotations

import datetime as dt
import json
import random
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from autoresearch.gate_expiry_check import (  # noqa: E402
    CORE_DECISIONS, EVENT_CLUSTER_GAP_MINUTES, cluster_events, load_decision_rows,
    load_p1_outcomes_by_day, p1_outcome_for_event, sole_blocker_events,
    sole_blocker_rows_all_accounts, bar_idx_for_ts,
)
from autoresearch.recency_check import load_merged_spy_vix, window_metrics  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import _normalize_spy, _align_vix  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.filters import vol_baseline_20bar, buyer_pressure_bar_v11  # noqa: E402
from lib.concentration import drop_top_n  # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import gate_revalidation_ab as grab  # noqa: E402

FILLS_LEDGER = ROOT / "automation" / "state" / "fills-ledger.jsonl"
OUT_DIR = ROOT / "analysis" / "deep-research" / "2026-09-03-money"
PREREG = ROOT / "analysis" / "recommendations" / "bull-f10-buyer-pressure-prereg-2026-08-04.json"
ANCHOR_DAYS = {"2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"}
NEAR_MATCH_MINUTES = 6
RNG_SEED = 42
N_BOOT = 5000
DOOR = "bull"
FILT = 10


def bootstrap_ci(values: list[float], n_boot: int = N_BOOT, seed: int = RNG_SEED, alpha: float = 0.05) -> dict:
    if not values:
        return {"n": 0, "mean": None, "ci_lo": None, "ci_hi": None}
    if len(values) == 1:
        return {"n": 1, "mean": values[0], "ci_lo": values[0], "ci_hi": values[0], "method": "degenerate_single_point"}
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_boot):
        means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo = int((alpha / 2) * n_boot)
    hi = int((1 - alpha / 2) * n_boot) - 1
    return {"n": n, "mean": round(statistics.mean(values), 2), "ci_lo": round(means[lo], 2),
            "ci_hi": round(means[max(hi, 0)], 2), "method": "bootstrap_percentile_95", "b": n_boot}


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


def find_same_signal_fills(ev_ts: str, right: str, fills_by_date: dict[str, list[dict]],
                            exclude_arms: tuple[str, ...] = ()) -> list[dict]:
    date = ev_ts[:10]
    try:
        t0 = dt.datetime.fromisoformat(ev_ts)
    except ValueError:
        return []
    out = []
    for r in fills_by_date.get(date, []):
        if r.get("arm") in exclude_arms or r.get("side") != "buy":
            continue
        sym = r.get("symbol", "")
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
    rows = [r for r in fills_by_date.get(date, [])
            if r.get("arm") == arm and r.get("symbol") == symbol and r.get("side") == "sell"
            and r.get("ts_et", "") >= after_ts]
    if not rows:
        return None
    rows.sort(key=lambda r: r["ts_et"])
    return rows[0]


def main() -> int:
    print("[dissect-f10] loading prereg + merged SPY/VIX ...", flush=True)
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    cells_frozen = prereg["cells_frozen"]
    gates_frozen = prereg["gates_frozen_before_any_runner"]

    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    _align_vix(spy, vix_raw)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    spy_ts = spy["timestamp_et"]
    spy_by_date = {d: sub.reset_index(drop=True) for d, sub in spy.groupby("date")}
    ribbon_lookup = grab.build_ribbon_lookup(spy)
    account_cfg = grab.account_config()
    trading_days = sorted(spy["date"].unique())

    full_start = dt.date(2026, 7, 27)  # earliest ledger row carrying bull_blockers
    rows = [r for r in load_decision_rows(CORE_DECISIONS, full_start) if r.get("armed") is True]
    holds_by_account = {
        account: [r for r in rows if r.get("account") == account and r.get("verdict") == "HOLD"]
        for account in ("safe", "bold")
    }
    per_account_events = {
        account: sole_blocker_events(holds_by_account[account], DOOR, FILT) for account in ("safe", "bold")
    }
    distinct_raw = sole_blocker_rows_all_accounts(holds_by_account, DOOR, FILT)
    distinct_events = cluster_events(distinct_raw, EVENT_CLUSTER_GAP_MINUTES)
    print(f"[dissect-f10] raw sole-[10] HOLD rows: safe={len(holds_by_account['safe'])} holds "
          f"({sum(1 for r in holds_by_account['safe'] if (r.get('bull_blockers') or [])==[10])} sole-[10]), "
          f"bold={len(holds_by_account['bold'])} holds "
          f"({sum(1 for r in holds_by_account['bold'] if (r.get('bull_blockers') or [])==[10])} sole-[10])", flush=True)
    print(f"[dissect-f10] per-account clustered episodes: safe={len(per_account_events['safe'])}, "
          f"bold={len(per_account_events['bold'])}; cross-account DISTINCT episodes={len(distinct_events)}", flush=True)

    p1_by_day = load_p1_outcomes_by_day()
    fills_by_date = load_fills_by_date()

    episode_records = []
    for ev in distinct_events:
        ts = ev.get("ts_et", "")
        trigger_bar_et = ev.get("trigger_bar_et") or ts
        # F10 (buyer_pressure_bar_v11) evaluates ctx.bar = spy_df.iloc[idx], and the ledger's
        # own trigger_bar_et field IS bar_ctx.timestamp_et == ctx.timestamp_et (heartbeat_core.py
        # ~1752/1846/2587: "trigger_bar_et": str(bc.get("timestamp_et"))) -- i.e. it is, by
        # construction, the exact bar the live engine evaluated F10 against. Using it here.
        # DISCLOSED CAVEAT (found live, see report): re-evaluating buyer_pressure_bar_v11 on
        # THIS SAME bar timestamp against the CACHED backtest SPY/volume series (not the live
        # intraday feed the engine actually gated on) does not byte-reproduce the live verdict
        # -- baseline (0.70, identical to the live default) "admits" ~1/3 of episodes that were
        # live sole-[10]-blocked, which is definitionally impossible on matched data. This is a
        # DATA-PROVENANCE mismatch between the cached OPRA-adjacent SPY cache and the engine's
        # live volume feed (same class as L-doctrine C4/data-provenance-strata), not a logic
        # bug -- quantified and reported, and the ADDED-vs-baseline delta (computed on the SAME
        # recomputed series at every cell) is used as the primary relax-lift read since the
        # provenance noise is common-mode across cells.
        try:
            tbar = dt.datetime.fromisoformat(trigger_bar_et).replace(tzinfo=None)
        except ValueError:
            tbar = None
        bar_idx = None
        bar_row = None
        vol_ratio = None
        is_green = None
        if tbar is not None:
            bar_idx, stale = bar_idx_for_ts(spy_ts, tbar)
            if bar_idx is not None and not stale:
                bar_row = spy.iloc[bar_idx]
                vbase = vol_baseline_20bar(spy, bar_idx)
                vol_ratio = (float(bar_row["volume"]) / vbase) if vbase else None
                is_green = bool(bar_row["close"] > bar_row["open"])
            else:
                bar_idx = None  # stale/no-bar -- can't evaluate relax cells for this episode

        cell_results = {}
        for cell in cells_frozen:
            mult = cell["f10_vol_mult"]
            if bar_row is None:
                cell_results[cell["cell"]] = {"admitted": None, "reason": "no_bar_or_stale"}
                continue
            admitted = bool(buyer_pressure_bar_v11(bar_row, vol_baseline_20bar(spy, bar_idx), vol_mult=mult))
            cell_results[cell["cell"]] = {"admitted": admitted, "f10_vol_mult": mult}

        p1_read, p1_pnl = p1_outcome_for_event(ev, p1_by_day, "C")
        same_signal = find_same_signal_fills(ts, "C", fills_by_date)
        pairs = []
        for f in same_signal:
            exitr = paired_exit(f["date_et"], f["arm"], f["symbol"], f["ts_et"], fills_by_date)
            entry_prem = f["price"]
            exit_prem = exitr["price"] if exitr else None
            qty = min(f["qty"], exitr["qty"]) if exitr else f["qty"]
            real_pnl = round((exit_prem - entry_prem) * qty * 100, 2) if exit_prem is not None else None
            pairs.append({"arm": f["arm"], "symbol": f["symbol"], "buy_ts": f["ts_et"], "buy_price": entry_prem,
                           "qty": f["qty"], "sell_ts": exitr["ts_et"] if exitr else None,
                           "sell_price": exit_prem, "approx_real_pnl_per_matched_qty": real_pnl})

        episode_records.append({
            "ts_et": ts, "date": ts[:10], "account_source": ev.get("account"),
            "bull_score": ev.get("bull_score"), "bull_triggers_raw": ev.get("bull_triggers_raw"),
            "trigger_bar_et": trigger_bar_et, "bar_idx": bar_idx,
            "bar_close": float(bar_row["close"]) if bar_row is not None else None,
            "bar_open": float(bar_row["open"]) if bar_row is not None else None,
            "bar_is_green": is_green, "vol_ratio_to_20bar_avg": round(vol_ratio, 3) if vol_ratio is not None else None,
            "cells": cell_results,
            "gate_expiry_sole_blocker_proxy": {"read": p1_read, "pnl": p1_pnl, "costing": "NOT_REPLAYED"},
            "real_fill_pairs": pairs,
        })

    # ---- per-cell ADDED-COHORT sound replay (walk_exit_manager) -------------------------
    cell_summaries = {}
    for cell in cells_frozen:
        cname = cell["cell"]
        admitted_events = [e for e, rec in zip(distinct_events, episode_records)
                            if rec["cells"].get(cname, {}).get("admitted") is True]
        # replay each admitted episode using its ORIGINATING account's config/side
        sims = []
        for ev in admitted_events:
            acct = ev.get("account") if ev.get("account") in ("safe", "bold") else "safe"
            cfg = account_cfg[acct]
            side_ev = dict(ev)
            side_ev["side"] = "C"
            sim = grab.replay_row(side_ev, spy=spy, spy_ts=spy_ts, spy_by_date=spy_by_date,
                                   ribbon_lookup=ribbon_lookup, cfg=cfg)
            sims.append(sim)
        sims_detail = [{"ts_et": ev.get("ts_et"), "account_source": ev.get("account"),
                         "status": s["status"], "pnl": s.get("pnl")}
                        for ev, s in zip(admitted_events, sims)]
        ok = [s for s in sims if s["status"] == "ok"]
        pnls = [s["pnl"] for s in ok]
        boot = bootstrap_ci(pnls)
        records_for_drop = [(s["date"], s["pnl"]) for s in ok]
        drop_top1, nd1 = drop_top_n(records_for_drop, 1) if records_for_drop else (None, 0)
        drop_top3, nd3 = drop_top_n(records_for_drop, 3) if records_for_drop else (None, 0)
        wm = window_metrics(ok, trading_days[0], trading_days[-1]) if ok else {"n": 0}
        status_counts: dict[str, int] = {}
        for s in sims:
            status_counts[s["status"]] = status_counts.get(s["status"], 0) + 1
        cell_summaries[cname] = {
            "f10_vol_mult": cell["f10_vol_mult"],
            "n_admitted_episodes": len(admitted_events),
            "status_counts": status_counts,
            "n_ok": len(ok), "wr_pct": wm.get("wr_pct"), "total_dollar": wm.get("total_dollar"),
            "mean_dollar_per_trade": round(sum(pnls) / len(pnls), 2) if pnls else None,
            "bootstrap_ci95": boot, "drop_top1": drop_top1, "drop_top3": drop_top3,
            "window_metrics": wm, "sims_detail": sims_detail,
        }
        print(f"[dissect-f10] cell={cname:10s} mult={cell['f10_vol_mult']:.2f} admitted={len(admitted_events):3d} "
              f"n_ok={len(ok):3d} wr={wm.get('wr_pct')} total=${wm.get('total_dollar')} drop_top3=${drop_top3}", flush=True)

    # ---- ADDED cohort relative to baseline (0.7): episodes admitted at a relaxed threshold
    # but NOT at baseline -- the actual "would this relax add money" question. -------------
    added_vs_baseline = {}
    baseline_admitted_ts = {rec["ts_et"] for rec in episode_records if rec["cells"].get("baseline", {}).get("admitted") is True}
    for cell in cells_frozen:
        cname = cell["cell"]
        if cname == "baseline":
            continue
        added_ts = {rec["ts_et"] for rec in episode_records
                    if rec["cells"].get(cname, {}).get("admitted") is True} - baseline_admitted_ts
        added_sims = [d for d in cell_summaries[cname]["sims_detail"]
                       if d["ts_et"] in added_ts and d["status"] == "ok"]
        added_pnls = [d["pnl"] for d in added_sims]
        added_vs_baseline[cname] = {
            "episode_ts": sorted(added_ts),
            "n_added": len(added_ts),
            "n_ok": len(added_pnls),
            "wr_pct": round(100 * sum(1 for p in added_pnls if p > 0) / len(added_pnls), 1) if added_pnls else None,
            "total_dollar": round(sum(added_pnls), 2) if added_pnls else None,
            "bootstrap_ci95": bootstrap_ci(added_pnls),
            "drop_top3": drop_top_n([(d["ts_et"][:10], d["pnl"]) for d in added_sims], 3)[0] if added_sims else None,
        }

    # ---- prereg gate scoring (against the LIVE-ledger cohort only, disclosed) ------------
    prereg_gate_reads = {}
    for cname in ("relax_50", "relax_35", "off"):
        avb = added_vs_baseline[cname]
        n = avb["n_ok"]
        prereg_gate_reads[cname] = {
            # prereg text: "added cohort (trades admitted by the relax that baseline refuses)"
            # -- scored against the ADDED-vs-baseline subset, not the cell's full admitted set.
            "decision_floor_n_ge_20": {"required": 20, "actual_added_n": n, "pass": n >= 20},
            "added_cohort_total_dollar": avb["total_dollar"],
            "added_cohort_wr_pct": avb["wr_pct"],
            "added_cohort_bootstrap_ci95": avb["bootstrap_ci95"],
            "added_cohort_drop_top3": avb["drop_top3"],
            "oos_positive": "NOT EVALUATED -- no IS/OOS split exists for a single-ledger-era cohort this size; see caveats",
            "wf_or_disclosed_null": "NOT EVALUATED -- same reason",
            "sub_window_stable": "NOT EVALUATED -- n too small to split by month meaningfully",
            "anchor_no_regression": "see anchor_days section below",
            "drop_best": {"drop_top1_full_cell": cell_summaries[cname]["drop_top1"]},
        }

    anchor_hits = {d: [rec for rec in episode_records if rec["date"] == d] for d in sorted(ANCHOR_DAYS)}

    real_pairs_all = [p for rec in episode_records for p in rec["real_fill_pairs"]]
    real_pnls = [p["approx_real_pnl_per_matched_qty"] for p in real_pairs_all if p["approx_real_pnl_per_matched_qty"] is not None]
    p1_reads = [rec["gate_expiry_sole_blocker_proxy"]["read"] for rec in episode_records]
    p1_win = sum(1 for r in p1_reads if r == "WIN")
    p1_loss = sum(1 for r in p1_reads if r == "LOSS")
    p1_none = sum(1 for r in p1_reads if r == "NONE")

    summary = {
        "question": "D8(B) first live run of bull-f10-buyer-pressure-prereg-2026-08-04.json",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "prereg_file": str(PREREG.relative_to(ROOT)),
        "prereg_cells_frozen": cells_frozen,
        "prereg_gates_frozen": gates_frozen,
        "scope_note": prereg.get("population") ,
        "cohort_window": f"{full_start}..{trading_days[-1]}",
        "raw_holds": {"safe": len(holds_by_account["safe"]), "bold": len(holds_by_account["bold"])},
        "per_account_clustered_episodes": {a: len(v) for a, v in per_account_events.items()},
        "distinct_episodes_cross_account": len(distinct_events),
        "sole_blocker_proxy_directional_read": {
            "costing": "NOT_REPLAYED", "n_episodes": len(episode_records),
            "n_cost_money_WIN": p1_win, "n_saved_money_LOSS": p1_loss, "n_unknown_NONE": p1_none,
        },
        "real_fill_cross_reference": {
            "n_episodes_with_a_same_signal_fleet_fill": sum(1 for rec in episode_records if rec["real_fill_pairs"]),
            "n_real_pairs": len(real_pairs_all),
            "n_real_pairs_with_closed_exit": len(real_pnls),
            "real_pairs_total_pnl_scaled_to_matched_qty": round(sum(real_pnls), 2) if real_pnls else None,
            "real_pairs_wr_pct": round(100 * sum(1 for p in real_pnls if p > 0) / len(real_pnls), 1) if real_pnls else None,
        },
        "cells": cell_summaries,
        "added_vs_baseline_episode_ts": added_vs_baseline,
        "prereg_gate_scoring_on_live_cohort": prereg_gate_reads,
        "anchor_days_checked": sorted(ANCHOR_DAYS),
        "anchor_day_episodes": {d: len(v) for d, v in anchor_hits.items()},
        "anchor_day_detail": anchor_hits,
        "episodes": episode_records,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "dissect-gates-revalidation-partB.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[dissect-f10] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
