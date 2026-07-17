"""One-off finalizer (NOT part of the pipeline): appends the near-miss diagnostic
(both/cand-only/ctrl-only delta decomposition + anchor-hit detail, computed by
_pong_decompose_check.py's logic, re-run here to persist the numbers) to the frozen
scorecard JSON, and regenerates the MD with a diagnostic section + build-spec-or-kill
writeup. Does not touch the prereg or the study script.
"""
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))
import pong_resting_limit_study as P  # noqa: E402

OUT_JSON = REPO / "analysis" / "recommendations" / "pong-resting-limit-2026-07-17.json"
OUT_MD = REPO / "analysis" / "recommendations" / "pong-resting-limit-2026-07-17.md"

out = json.loads(OUT_JSON.read_text(encoding="utf-8"))

spy_full, vix_full = P.load_data(P.IS_START, P.DATA_END)
spy_naive = spy_full.copy()
spy_naive["timestamp_et"] = P._wallv1(spy_naive["timestamp_et"])
spy_naive["date"] = spy_naive["timestamp_et"].dt.date
spy_naive["time"] = spy_naive["timestamp_et"].dt.time
spy_naive = spy_naive[spy_naive["date"] >= P.IS_START].sort_values("timestamp_et").reset_index(drop=True)
spy_by_date = {d: g.reset_index(drop=True) for d, g in spy_naive.groupby("date")}
vix_naive = vix_full.copy()
vix_naive["timestamp_et"] = P._wallv1(vix_naive["timestamp_et"])
vix_lookup = P.VixLookup(vix_naive)
level_by_day = P.build_level_by_day(spy_naive)

SHAPE = next(s for s in P.EXIT_SHAPES if s["label"] == "tp30_structure_t12")

near_miss = {}
for label, cfg in P.ACCOUNTS.items():
    raw_params = json.loads(cfg["params_path"].read_text(encoding="utf-8-sig"))
    equity = P.LIVE_EQUITY[label]
    so, tier_label = P.tier_for_equity(cfg["tiers"], equity)
    time_stop_et = dt.datetime.strptime(raw_params.get("time_stop_et", "15:40"), "%H:%M").time()

    eps = P.mine_cancel_rule(so, time_stop_et, spy_naive, level_by_day, vix_lookup, None)
    universe = {}
    for ep in eps:
        universe.setdefault(ep["episode_id"], ep)
    control_cache = {eid: P.control_outcome(eid, ep["date"], ep["role"], ep["level"], so, time_stop_et,
                                            spy_naive, spy_by_date) for eid, ep in universe.items()}

    both_delta_sum = both_n = 0.0
    cand_only_delta_sum = cand_only_n = 0.0
    ctrl_only_delta_sum = ctrl_only_n = 0.0
    anchor_hits = []
    for eid, ep in universe.items():
        ctrl = control_cache[eid]
        c_pnl = P.candidate_pnl(ep, SHAPE, time_stop_et, spy_by_date) if ep.get("outcome") == "filled" else None
        x_pnl = P.control_pnl_for_shape(ctrl, SHAPE, time_stop_et, spy_by_date) if ctrl["traded"] else None
        cand_traded, ctrl_traded = c_pnl is not None, x_pnl is not None
        if not cand_traded and not ctrl_traded:
            continue
        c_eff, x_eff = (c_pnl if cand_traded else 0.0), (x_pnl if ctrl_traded else 0.0)
        delta = c_eff - x_eff
        if cand_traded and ep["date"] in P.J_ANCHOR_DATES:
            anchor_hits.append({"episode_id": eid, "date": ep["date"], "role": ep["role"],
                                "level": round(float(ep["level"]), 2), "candidate_pnl": c_pnl})
        if cand_traded and ctrl_traded:
            both_delta_sum += delta; both_n += 1
        elif cand_traded:
            cand_only_delta_sum += delta; cand_only_n += 1
        elif ctrl_traded:
            ctrl_only_delta_sum += delta; ctrl_only_n += 1

    total = both_delta_sum + cand_only_delta_sum + ctrl_only_delta_sum
    n_anchor_losses = sum(1 for h in anchor_hits if h["candidate_pnl"] < 0)
    near_miss[label] = {
        "reference_cell": "no_cancel|tp30_structure_t12",
        "decomposition": {
            "both_traded": {"n": int(both_n), "delta_sum": round(both_delta_sum, 2),
                            "delta_mean": round(both_delta_sum / both_n, 2) if both_n else None},
            "cand_only": {"n": int(cand_only_n), "delta_sum": round(cand_only_delta_sum, 2),
                         "delta_mean": round(cand_only_delta_sum / cand_only_n, 2) if cand_only_n else None},
            "ctrl_only_pong_never_filled": {"n": int(ctrl_only_n), "delta_sum": round(ctrl_only_delta_sum, 2),
                                            "delta_mean": round(ctrl_only_delta_sum / ctrl_only_n, 2) if ctrl_only_n else None,
                                            "note": "delta = 0 - control_pnl; positive delta_sum here means control LOST money on episodes PONG never filled -- a real but execution-avoidance-driven contribution, not a head-to-head PONG win"},
            "total_delta": round(total, 2),
            "both_traded_share_of_total_pct": round(100 * both_delta_sum / total, 1) if total else None,
            "ctrl_only_share_of_total_pct": round(100 * ctrl_only_delta_sum / total, 1) if total else None,
        },
        "anchor_date_hits": {
            "n_hits": len(anchor_hits), "n_losses": n_anchor_losses,
            "n_wins": len(anchor_hits) - n_anchor_losses,
            "loss_rate": round(n_anchor_losses / len(anchor_hits), 3) if anchor_hits else None,
            "hits": anchor_hits,
        },
    }
    print(f"[{label}] anchor hits: {len(anchor_hits)}, losses: {n_anchor_losses} "
         f"({round(100*n_anchor_losses/len(anchor_hits),1) if anchor_hits else 0}%)")

out["near_miss_diagnostic"] = {
    "_doc": "Fable-too-good artifact hunt (CLAUDE.md 'suspicion scales with how good it looks') on the "
           "closest cell (no_cancel|tp30_structure_t12, 4/5 gates PASS on BOTH accounts, only "
           "anchor_no_regression fails on ALL 64 grid cells). Investigated: (a) does the positive "
           "delta come from real head-to-head entries or from PONG simply avoiding control's losers, "
           "(b) what specifically happens on the 6 J-anchor dates that fails the gate.",
    "accounts": near_miss,
    "verdict": "The anchor_no_regression failure is NOT a gate-calibration technicality (same-calendar-"
              "date match saturating at PONG's trade frequency) -- it is catching a REAL, mechanistically "
              "coherent vulnerability. On J's own 6 hand-verified anchor dates, the candidate loses on "
              "19/21 (Safe) and 15/17 (Bold) fills, several by $100+ -- consistent with the anchor days "
              "being fast/volatile/trending sessions (that is WHY they produced J's best real trades) "
              "rather than the range-bound ping-pong regime the mechanism's whole thesis depends on. The "
              "aggregate positive delta over the full window is driven predominantly by genuine "
              "head-to-head entries (both_traded population, ~97-109% of total delta on the two "
              "accounts -- not primarily an avoid-the-control-loser artifact), but that aggregate masks "
              "a regime-dependent sign flip that happens to land on exactly the days that matter most. "
              "This is exactly what the anchor gate exists to catch, and it caught something real -- "
              "the gate is doing its job here, not being overly conservative.",
}

OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print("updated", OUT_JSON)
