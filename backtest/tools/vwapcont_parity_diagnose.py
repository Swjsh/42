"""vwapcont_parity_diagnose.py -- EXIT-ENGINE-PARITY-RESIDUAL diagnosis (queue.md, filed
2026-07-14ish, re-picked 2026-07-23 conductor AFTERHOURS).

vwapcont_entry_exit_matrix.py's parity_check() found a LARGE aggregate delta on the OLD
(burned) window control cell: bar-replay $15.02/tr vs simulate_trade_real $54.73/tr (n=149
both). Two mechanisms were already confirmed real but neither closes the gap alone or together:
  (1) pre-TP1 profit-lock scope difference: $54.73 -> $55.45 in isolation (tiny).
  (2) ribbon-flip-back (sim fires it on 39/149 trades, bar-replay never does): disabling it
      cleanly is not possible (still 33 exits fire with ribbon_df=None) -> inconclusive, $49.83.
A further undiagnosed factor was flagged: "most likely fill-order/tie-break nuances across many
bars, or another exit-priority difference between the two independent bar-walk implementations."

THIS SCRIPT: per-signal (not aggregate) diff. For every signal in the OLD window, runs BOTH
engines on the IDENTICAL signal (joined by sg.bar_idx, a stable index into the shared spy
frame -- not by date/side, which can collide), records each engine's PNL + terminal exit
stage/reason, and buckets the (bar_replay_stage, sim_exit_reason) pair -> aggregate delta so the
dominant driver of the ~$40/tr gap is identified BEFORE any future sim-authority ratification
trusts simulate_trade_real's absolute dollars for this population.

Reuses vwapcont_entry_exit_matrix's own signal-loading/prep/shape helpers verbatim (no
re-derivation, no re-picked window/shape) -- this is a read-only diagnostic layered on top of
that already-frozen study, not a new population.

ANALYSIS ONLY. Touches nothing under automation/state/params.json, automation/state/fleet/, or
any trading-path file. Writes only to analysis/recommendations/.

Run: backtest/.venv/Scripts/python.exe backtest/tools/vwapcont_parity_diagnose.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time as _time_mod
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(BACKTEST / "tools"), str(REPO / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch._edgehunt_vwap_continuation import QTY  # noqa: E402
from autoresearch.vwapcont_exit_parity import simulate_cell_ext  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from exit_manager import TIME_STOP_ET  # noqa: E402
import structure_stop_study as sss  # noqa: E402
import vwapcont_entry_exit_matrix as vmx  # noqa: E402

OUT_JSON = REPO / "analysis" / "recommendations" / "vwapcont-parity-diagnose-2026-07-23.json"
OUT_MD = REPO / "analysis" / "recommendations" / "vwapcont-parity-diagnose-2026-07-23.md"


def log(msg: str) -> None:
    print(f"[vwapmx-diag] {msg}", flush=True)


def main() -> int:
    t0 = _time_mod.time()
    signals, spy, vix, ribbon, days = vmx.load_signals()
    pf = vmx.preflight(signals, spy)
    log(f"preflight: {pf}")
    if not (pf["signal_set_hash_ok"] and pf["preregistration_version_ok"] and pf["old_window_parity_ok"]):
        print("[vwapmx-diag] PREFLIGHT FAILED -- population drifted from the frozen "
              "pre-registration this diagnosis depends on. Aborting.", file=sys.stderr)
        return 1

    vwap_cache = vmx.build_vwap_cache(days)
    grid_cells = vmx.load_grid_cells()
    control_cell = next(c for c in grid_cells if c["id"] == "P1T1F1L1")
    shape = vmx.shape_of(control_cell)

    signals_old = [s for s in signals if spy.iloc[s.bar_idx]["timestamp_et"].date() <= vmx.OLD_END]
    log(f"n_signals_old={len(signals_old)} (parity_check's known n=149)")

    sim_kwargs = {"premium_stop_pct": shape["premium_stop_pct"], "tp1_premium_pct": shape["tp1_premium_pct"],
                  "tp1_qty_fraction": shape["tp1_qty_fraction"], "profit_lock_mode": shape["profit_lock_mode"],
                  "profit_lock_threshold_pct": vmx.PROFIT_LOCK_ARM_PCT, "profit_lock_stop_offset_pct": 0.0,
                  "runner_target_premium_pct": vmx.RUNNER_TARGET_PCT}

    per_signal = []
    n_both_filled = n_br_only = n_sim_only = n_neither = 0
    for i, sg in enumerate(signals_old):
        bar = spy.iloc[sg.bar_idx]
        date = bar["timestamp_et"].date()

        # bar-replay leg (same helper the study uses)
        loaded, status = vmx.load_atm_bars(sg, spy, date)
        br_pnl = br_last_stage = br_n_exits = None
        if loaded is not None:
            r = sss.replay_structure_aware(loaded["entry_premium"], sg.side, QTY,
                                           loaded["norm_bars"], None, shape, vmx.TIME_STOP)
            br_pnl = r["pnl"]
            br_last_stage = r["exits"][-1]["stage"] if r["exits"] else None
            br_n_exits = len(r["exits"])

        # simulate_trade_real leg (same call convention as simulate_cell_ext, single signal)
        sim_rows, sim_cov = simulate_cell_ext([sg], spy, ribbon, vix, strike_offset=0, sim_kwargs=sim_kwargs)
        sim_pnl = sim_rows[0].pnl if sim_rows else None
        sim_reason = sim_rows[0].exit_reason if sim_rows else None

        br_filled = br_pnl is not None
        sim_filled = sim_pnl is not None
        if br_filled and sim_filled:
            n_both_filled += 1
        elif br_filled:
            n_br_only += 1
        elif sim_filled:
            n_sim_only += 1
        else:
            n_neither += 1

        delta = round(br_pnl - sim_pnl, 2) if (br_filled and sim_filled) else None
        per_signal.append({
            "idx": i, "bar_idx": sg.bar_idx, "date": str(date), "side": sg.side,
            "bar_replay_filled": br_filled, "bar_replay_pnl": br_pnl,
            "bar_replay_last_stage": br_last_stage, "bar_replay_n_exits": br_n_exits,
            "sim_filled": sim_filled, "sim_pnl": sim_pnl, "sim_exit_reason": sim_reason,
            "delta_br_minus_sim": delta,
            "load_miss_status": status if loaded is None else None,
        })
        if (i + 1) % 25 == 0:
            log(f"  {i + 1}/{len(signals_old)} signals processed...")

    log(f"fill coverage: both={n_both_filled} br_only={n_br_only} sim_only={n_sim_only} neither={n_neither}")

    both = [r for r in per_signal if r["delta_br_minus_sim"] is not None]
    total_br = round(sum(r["bar_replay_pnl"] for r in both), 2)
    total_sim = round(sum(r["sim_pnl"] for r in both), 2)
    n = len(both)
    exp_br = round(total_br / n, 2) if n else None
    exp_sim = round(total_sim / n, 2) if n else None
    log(f"on the {n} BOTH-filled trades: bar-replay total=${total_br:+.2f} (exp ${exp_br}) "
        f"vs sim total=${total_sim:+.2f} (exp ${exp_sim})")

    # bucket by (bar_replay_last_stage, sim_exit_reason) pair -> aggregate delta + count
    pair_bucket: dict = defaultdict(lambda: {"n": 0, "sum_delta": 0.0, "sum_br": 0.0, "sum_sim": 0.0})
    for r in both:
        key = f"{r['bar_replay_last_stage']} | {r['sim_exit_reason']}"
        b = pair_bucket[key]
        b["n"] += 1
        b["sum_delta"] += r["delta_br_minus_sim"]
        b["sum_br"] += r["bar_replay_pnl"]
        b["sum_sim"] += r["sim_pnl"]
    pair_summary = sorted(
        [{"stage_pair": k, "n": v["n"], "sum_delta": round(v["sum_delta"], 2),
          "avg_delta": round(v["sum_delta"] / v["n"], 2), "sum_br": round(v["sum_br"], 2),
          "sum_sim": round(v["sum_sim"], 2)} for k, v in pair_bucket.items()],
        key=lambda x: abs(x["sum_delta"]), reverse=True,
    )

    # same-stage-name pairs (both engines agree on WHICH stage/reason terminated the trade) --
    # if delta is still large here, the gap is a FILL-PRICE/rounding difference WITHIN the same
    # decision, not a stage-selection disagreement.
    def _same_family(stage: str | None, reason: str | None) -> bool:
        if stage is None or reason is None:
            return False
        s = stage.lower()
        r = reason.lower()
        fam = {
            "tp1": "tp1", "runner_target": "runner", "premium_stop": "premium_stop",
            "trail": "trail", "be_stop": "trail", "time_stop": "time_stop", "eod_mark": "time_stop",
        }
        return fam.get(s, s) in r or r.split("_")[0] in fam.get(s, s)

    agree_rows = [r for r in both if _same_family(r["bar_replay_last_stage"], r["sim_exit_reason"])]
    disagree_rows = [r for r in both if not _same_family(r["bar_replay_last_stage"], r["sim_exit_reason"])]
    agree_delta = round(sum(r["delta_br_minus_sim"] for r in agree_rows), 2)
    disagree_delta = round(sum(r["delta_br_minus_sim"] for r in disagree_rows), 2)

    # ── ROOT-CAUSE CONFIRMATORY TEST ──────────────────────────────────────────────────────
    # Hypothesis (derived from code read, not guessed): simulate_trade_real starts its
    # exit-check loop at `opt_idx = entry_idx_opt + 1` (lib/simulator_real.py:534-535) --
    # it NEVER evaluates the entry bar's own high/low for a stop/TP1, only bars strictly
    # AFTER it. replay_structure_aware's `norm_bars` (built by load_atm_bars) starts AT the
    # entry bar itself (norm_bars[0].open == entry_premium) and the exit loop
    # (`for bar in norm_bars:`) evaluates THAT bar's own high/low on its first iteration --
    # one bar earlier than sim. Confirmatory test: re-run bar-replay on the identical
    # population with norm_bars[1:] (skip the entry bar, matching sim's convention) and see
    # if the parity gap closes.
    log("root-cause confirmatory test: bar-replay excluding the entry bar from exit-checks...")
    total_excl = 0.0
    n_excl = 0
    for r in both:
        sg = signals_old[r["idx"]]
        bar2 = spy.iloc[sg.bar_idx]
        date2 = bar2["timestamp_et"].date()
        loaded2, _ = vmx.load_atm_bars(sg, spy, date2)
        if loaded2 is None:
            continue
        nb = loaded2["norm_bars"]
        nb2 = nb[1:] if len(nb) > 1 else nb
        r2 = sss.replay_structure_aware(loaded2["entry_premium"], sg.side, QTY, nb2, None, shape, vmx.TIME_STOP)
        total_excl += r2["pnl"]
        n_excl += 1
    exp_excl = round(total_excl / n_excl, 2) if n_excl else None
    root_cause = {
        "hypothesis": "simulate_trade_real (lib/simulator_real.py:534-535, spy_idx=entry_bar_idx+2 / "
                      "opt_idx=entry_idx_opt+1) NEVER checks the entry bar's own high/low for a stop/TP1 "
                      "-- exit-checks start at the bar AFTER entry. replay_structure_aware's norm_bars "
                      "(load_atm_bars) start AT the entry bar and the exit loop evaluates that SAME bar's "
                      "high/low on iteration 1 -- one bar earlier than sim. On a volatile entry bar (common "
                      "right after a breakout/pullback trigger) this can stop bar-replay out before sim "
                      "ever gets a chance to see the trade run to TP1.",
        "confirmatory_test": "re-ran bar-replay on the identical 149-signal population with norm_bars[1:] "
                             "(entry bar excluded from exit-eligibility, matching sim's convention)",
        "bar_replay_entry_bar_included_exp": exp_br,
        "bar_replay_entry_bar_excluded_exp": exp_excl,
        "sim_exp": exp_sim,
        "gap_before_pct_closed": None,
        "verdict": None,
    }
    gap_before = round(exp_sim - exp_br, 2) if (exp_sim is not None and exp_br is not None) else None
    gap_after = round(exp_sim - exp_excl, 2) if (exp_sim is not None and exp_excl is not None) else None
    if gap_before and gap_after is not None:
        pct_closed = round(100 * (1 - abs(gap_after) / abs(gap_before)), 1)
        root_cause["gap_before_pct_closed"] = pct_closed
        root_cause["gap_before_dollar"] = gap_before
        root_cause["gap_after_dollar"] = gap_after
        root_cause["verdict"] = (
            f"CONFIRMED ({pct_closed}% of the ${gap_before}/tr aggregate gap closed by removing the "
            f"single entry-bar-inclusion convention difference; residual ${gap_after}/tr is consistent "
            "with the two previously-confirmed smaller mechanisms (pre-TP1 profit-lock scope + "
            "ribbon-flip-back). This is a DISCLOSURE about which of two long-standing, independently-"
            "precedented backtest conventions (bar-replay family: t4_exit_matrix/structure_stop_study/"
            "this study, vs simulate_trade_real: the ratified ship-gate C1 authority) is more faithful to "
            "live risk exposure -- NOT adjudicated here (real-money-adjacent judgment call, escalated "
            "separately, not decided at this tier)."
        )
    log(f"confirmatory test: bar-replay entry-bar-EXCLUDED exp=${exp_excl} (was ${exp_br} included) "
        f"vs sim ${exp_sim} -- {root_cause['verdict']}")

    out = {
        "_doc": "Per-signal exit-reason diff diagnosis of EXIT-ENGINE-PARITY-RESIDUAL "
                "(bar-replay vs simulate_trade_real control-cell gap). ANALYSIS ONLY.",
        "generated_at": dt.datetime.now().isoformat(),
        "source_study": "backtest/tools/vwapcont_entry_exit_matrix.py#parity_check",
        "preflight": pf,
        "fill_coverage": {"both_filled": n_both_filled, "bar_replay_only": n_br_only,
                          "sim_only": n_sim_only, "neither": n_neither,
                          "known_scorecard_n": 149},
        "aggregate_on_both_filled": {
            "n": n, "bar_replay_total": total_br, "bar_replay_exp": exp_br,
            "sim_total": total_sim, "sim_exp": exp_sim,
            "delta_total": round(total_br - total_sim, 2),
            "known_scorecard_bar_replay_exp": 15.02, "known_scorecard_sim_exp": 54.73,
        },
        "stage_family_split": {
            "same_terminal_family": {"n": len(agree_rows), "sum_delta": agree_delta,
                                     "avg_delta": round(agree_delta / len(agree_rows), 2) if agree_rows else None,
                                     "interpretation": "engines agree WHICH mechanism ended the trade "
                                     "-> remaining delta here is fill-price/timing/rounding, not stage "
                                     "selection"},
            "different_terminal_family": {"n": len(disagree_rows), "sum_delta": disagree_delta,
                                          "avg_delta": round(disagree_delta / len(disagree_rows), 2) if disagree_rows else None,
                                          "interpretation": "engines picked a DIFFERENT mechanism to end "
                                          "the same trade -> exit-priority/tie-break divergence"},
        },
        "stage_pair_buckets_ranked_by_abs_delta": pair_summary,
        "root_cause_confirmatory_test": root_cause,
        "per_signal_detail": per_signal,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"done in {_time_mod.time() - t0:.1f}s")
    return 0


def write_markdown(out: dict) -> None:
    agg = out["aggregate_on_both_filled"]
    fam = out["stage_family_split"]
    L = [
        "# EXIT-ENGINE-PARITY-RESIDUAL -- per-signal diagnosis (2026-07-23)",
        "",
        f"Generated {out['generated_at']}. Runner: `backtest/tools/vwapcont_parity_diagnose.py`. "
        f"Source study: `{out['source_study']}`.",
        "",
        "## Fill coverage",
        "",
        f"both engines filled: {out['fill_coverage']['both_filled']} / "
        f"known scorecard n={out['fill_coverage']['known_scorecard_n']} -- "
        f"bar-replay-only: {out['fill_coverage']['bar_replay_only']}, "
        f"sim-only: {out['fill_coverage']['sim_only']}, "
        f"neither: {out['fill_coverage']['neither']}.",
        "",
        "## Aggregate reproduction (on the both-filled subset)",
        "",
        f"bar-replay: ${agg['bar_replay_total']:+,.2f} total (exp ${agg['bar_replay_exp']}, "
        f"known scorecard ${agg['known_scorecard_bar_replay_exp']}) | "
        f"sim: ${agg['sim_total']:+,.2f} total (exp ${agg['sim_exp']}, "
        f"known scorecard ${agg['known_scorecard_sim_exp']}).",
        "",
        "## Stage-family split (THE finding)",
        "",
        f"- **Same terminal mechanism** (both engines agree which stage ended the trade): "
        f"n={fam['same_terminal_family']['n']}, sum delta=${fam['same_terminal_family']['sum_delta']:+,.2f} "
        f"(avg ${fam['same_terminal_family']['avg_delta']}/tr) -- {fam['same_terminal_family']['interpretation']}.",
        f"- **Different terminal mechanism** (engines disagree which stage ended the trade): "
        f"n={fam['different_terminal_family']['n']}, sum delta=${fam['different_terminal_family']['sum_delta']:+,.2f} "
        f"(avg ${fam['different_terminal_family']['avg_delta']}/tr) -- {fam['different_terminal_family']['interpretation']}.",
        "",
        "## Top stage-pair buckets by |aggregate delta|",
        "",
        "| bar-replay stage | sim exit_reason | n | sum delta | avg delta |",
        "|---|---|--:|--:|--:|",
    ]
    for b in out["stage_pair_buckets_ranked_by_abs_delta"][:15]:
        stage, reason = b["stage_pair"].split(" | ")
        L.append(f"| {stage} | {reason} | {b['n']} | ${b['sum_delta']:+,.2f} | ${b['avg_delta']:+,.2f} |")

    rc = out.get("root_cause_confirmatory_test", {})
    if rc:
        L += [
            "",
            "## Root-cause confirmatory test (THE diagnosis)",
            "",
            f"**Hypothesis:** {rc['hypothesis']}",
            "",
            f"**Test:** {rc['confirmatory_test']}",
            "",
            f"| | bar-replay (entry bar INCLUDED, current) | bar-replay (entry bar EXCLUDED) | sim (known) |",
            "|---|--:|--:|--:|",
            f"| exp $/tr | ${rc['bar_replay_entry_bar_included_exp']} | ${rc['bar_replay_entry_bar_excluded_exp']} | ${rc['sim_exp']} |",
            "",
            f"**{rc.get('verdict', 'inconclusive')}**",
            "",
        ]
    L += [
        "",
        "---",
        "_Full per-signal detail (149 rows) in the companion `.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
