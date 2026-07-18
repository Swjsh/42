"""regime_conditioned_readjudication.py -- re-score the 5 PARKED candidates under
regime-conditioned validation, GATED on regime_conditioned_self_validation.py having
returned self_validation_verdict == "EARNS_RIGHTS" (checked at the top of main(), aborts
loud otherwise -- per prereg's own on_fail clause: re-scoring after a failed
self-validation would itself be the methodology-shopping this whole exercise exists to
prevent).

Reuses each parked study's OWN existing, already-validated simulation internals (import +
call, never re-derived) to extract a per-episode DATED delta cohort, then runs
backtest/tools/regime_conditioned_validator.py#validate_candidate on it -- the SAME
procedure just self-validated, unchanged.

Candidates (per analysis/recommendations/REGIME-REFERENCE-CLASS-ADJUDICATION-2026-07-17.md
+ this task's explicit list):
  1. elite-bear-level-reject-gate (GOAL L1) -- block cohort, reuses
     backtest/tools/elite_bear_level_reject_gate_ab.py's SAFE_BASE/run_backtest/is_target.
  2. bold-strike-axis ATM vs OTM-3 control -- reuses
     backtest/tools/bold_strike_axis_deltawf.py's build_episode_outcomes.
  3. fleet strike tier (risky-3) -- NO separate cohort exists (WF-GATE-METHODOLOGY-2026-07-16.md's
     own disposition: risky-3 resolves via the SAME V15_BOLD_TIERS table as core Bold) ->
     inherits the bold-strike-axis ATM verdict by proxy, disclosed not computed separately.
  4. zone-rejection-band -- BOLD account, cell fixed_0.75 (n=15, the cell showing the clearest
     negative-IS/positive-OOS signature per the existing scorecard), reuses
     backtest/tools/zone_rejection_band_study.py's mine_account/build_delta_population/cell_membership.
  5. pong-resting-limit -- SAFE account, cell no_cancel|tp30_structure_t12 (the identified
     4/5-gates-pass near-miss cell), reuses
     backtest/tools/pong_resting_limit_study.py's mine_cancel_rule/control_outcome/candidate_pnl/compute_delta_wf.

Run: backtest/.venv/Scripts/python.exe backtest/tools/regime_conditioned_readjudication.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for p in (str(ROOT), str(REPO), str(REPO / "tools"),
          str(ROOT / "automation" / "state" / "fleet")):
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd  # noqa: E402

from backtest.tools.regime_classifier import RegimeCalendar  # noqa: E402
from backtest.tools.regime_conditioned_validator import validate_candidate  # noqa: E402

SELF_VAL_FILE = ROOT / "analysis" / "recommendations" / "regime-conditioned-validation-2026-07-17.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "regime-conditioned-readjudication-2026-07-17.json"

FULL_WINDOW_START = dt.date(2025, 1, 2)
FULL_WINDOW_END = dt.date(2026, 7, 8)


def log(msg: str) -> None:
    print(f"[regime-readjudicate] {msg}", flush=True)


def check_gate() -> str:
    if not SELF_VAL_FILE.exists():
        raise SystemExit("regime-conditioned-validation-2026-07-17.json missing -- run "
                          "regime_conditioned_self_validation.py first.")
    d = json.loads(SELF_VAL_FILE.read_text(encoding="utf-8"))
    verdict = d.get("self_validation_verdict")
    log(f"self_validation_verdict={verdict}")
    if verdict != "EARNS_RIGHTS":
        raise SystemExit(f"ABORT: self-validation verdict is '{verdict}', not EARNS_RIGHTS. "
                          "Re-adjudicating parked candidates now would be exactly the "
                          "methodology-shopping the prereg forbids. Not proceeding.")
    return verdict


# ===============================================================================================
# 1. ELITE-BEAR-LEVEL-REJECT-GATE (GOAL L1)
# ===============================================================================================
def cohort_elite_bear() -> list[dict]:
    import elite_bear_level_reject_gate_ab as eb

    log("elite-bear: loading SPY/VIX + running full-window backtest...")
    spy_df = pd.read_csv(eb.SPY_FILE)
    vix_df = pd.read_csv(eb.VIX_FILE)
    r = eb.run_backtest(spy_df, vix_df, start_date=FULL_WINDOW_START, end_date=FULL_WINDOW_END, **eb.SAFE_BASE)
    removed, _kept = eb.split_control_candidate(r.trades)
    log(f"elite-bear: n_total={len(r.trades)} n_removed(ELITE-bear)={len(removed)}")
    # elite_bear's OWN sign convention: delta = -pnl(removed) (blocking a losing trade = positive).
    return [{"date": eb.entry_date(t).isoformat(), "pnl": -float(t.dollar_pnl)} for t in removed]


# ===============================================================================================
# 2. BOLD-STRIKE-AXIS ATM vs OTM-3
# ===============================================================================================
def cohort_bold_strike_atm() -> list[dict]:
    import ribbon_ride_strike_exit_ab as rrse
    import bold_strike_axis_ab as bsa
    import bold_strike_axis_deltawf as bswf

    log("bold-strike ATM: loading shared signal cohort (rrse.load_cohort(), same n=250 "
        "cohort every strike-AB study in this lineage consumes)...")
    prepped, _spy_full, _spy_by_date = rrse.load_cohort()
    cells = dict(bsa.STRIKE_CELLS)
    atm_offset = cells["ATM"]
    otm3_offset = cells["OTM-3"]
    log(f"bold-strike: ATM offset={atm_offset} OTM-3 offset={otm3_offset} n_signals={len(prepped)}")

    atm_outcomes, atm_stats = bswf.build_episode_outcomes(prepped, atm_offset)
    otm3_outcomes, otm3_stats = bswf.build_episode_outcomes(prepped, otm3_offset)
    log(f"bold-strike: ATM n_traded={atm_stats['n_traded']} OTM-3 n_traded={otm3_stats['n_traded']}")

    shared_ids = sorted(i for i in atm_outcomes if atm_outcomes[i]["traded"] or otm3_outcomes[i]["traded"])
    out = []
    for i in shared_ids:
        c_pnl = atm_outcomes[i]["pnl"] if atm_outcomes[i]["traded"] else 0.0
        x_pnl = otm3_outcomes[i]["pnl"] if otm3_outcomes[i]["traded"] else 0.0
        date = atm_outcomes[i]["date"]
        date_str = date.isoformat() if hasattr(date, "isoformat") else str(date)
        out.append({"date": date_str, "pnl": round(c_pnl - x_pnl, 2)})
    return out


# ===============================================================================================
# 3. ZONE-REJECTION-BAND -- bold account, cell fixed_0.75
# ===============================================================================================
def cohort_zone_band_bold() -> list[dict]:
    import zone_rejection_band_study as zrb

    log("zone-band: loading SPY/VIX + computing ATR + mining bold account...")
    spy_full, vix_full = zrb.load_data(zrb.IS_START, zrb.DATA_END)
    spy_naive = spy_full.copy()
    spy_naive["timestamp_et"] = pd.to_datetime(spy_naive["timestamp_et"])
    if spy_naive["timestamp_et"].dt.tz is not None:
        spy_naive["timestamp_et"] = spy_naive["timestamp_et"].dt.tz_localize(None)
    spy_naive["date"] = spy_naive["timestamp_et"].dt.date
    spy_by_date = {d: g.reset_index(drop=True) for d, g in spy_naive.groupby("date")}
    atr_by_ts = zrb.compute_atr14_5m(spy_naive)

    mined = zrb.mine_account("bold", zrb.ACCOUNTS["bold"], spy_full, vix_full, atr_by_ts,
                              zrb.IS_START, zrb.DATA_END)
    pop, unchanged_n, control_only_excess, n_dropped = zrb.build_delta_population(
        mined, mined["fire_log"], spy_by_date)
    members = zrb.cell_membership(pop, "fixed_0.75", 0.75, False)
    log(f"zone-band bold fixed_0.75: n_pop={len(pop)} n_members={len(members)}")
    return [{"date": e["date"], "pnl": e["delta"]} for e in members]


# ===============================================================================================
# 4. PONG-RESTING-LIMIT -- safe account, cell no_cancel|tp30_structure_t12
# ===============================================================================================
def cohort_pong_safe() -> list[dict]:
    import pong_resting_limit_study as prl

    log("pong: loading SPY/VIX + building level set (safe account)...")
    spy_full, vix_full = prl.load_data(prl.IS_START, prl.DATA_END)
    spy_naive = spy_full.copy()
    spy_naive["timestamp_et"] = prl._wallv1(spy_naive["timestamp_et"])
    spy_naive["date"] = spy_naive["timestamp_et"].dt.date
    spy_naive["time"] = spy_naive["timestamp_et"].dt.time
    spy_naive = spy_naive[spy_naive["date"] >= prl.IS_START].sort_values("timestamp_et").reset_index(drop=True)
    spy_by_date = {d: g.reset_index(drop=True) for d, g in spy_naive.groupby("date")}

    vix_naive = vix_full.copy()
    vix_naive["timestamp_et"] = prl._wallv1(vix_naive["timestamp_et"])
    vix_lookup = prl.VixLookup(vix_naive)

    level_by_day = prl.build_level_by_day(spy_naive)

    cfg = prl.ACCOUNTS["safe"]
    raw_params = json.loads(cfg["params_path"].read_text(encoding="utf-8-sig"))
    equity = prl.LIVE_EQUITY["safe"]
    so, tier_label = prl.tier_for_equity(cfg["tiers"], equity)
    time_stop_et = dt.datetime.strptime(raw_params.get("time_stop_et", "15:40"), "%H:%M").time()
    log(f"pong safe: tier={tier_label} so={so}")

    eps = prl.mine_cancel_rule(so, time_stop_et, spy_naive, level_by_day, vix_lookup, None)  # "no_cancel"
    log(f"pong safe no_cancel: {len(eps)} arm events")
    eps_by_id = {e["episode_id"]: e for e in eps}

    control_cache = {}
    for eid, ep in eps_by_id.items():
        control_cache[eid] = prl.control_outcome(eid, ep["date"], ep["role"], ep["level"], so,
                                                  time_stop_et, spy_naive, spy_by_date)
    eid_date = {eid: dt.date.fromisoformat(eps_by_id[eid]["date"]) for eid in eps_by_id}

    shape_cell = next(s for s in prl.EXIT_SHAPES if s["label"] == "tp30_structure_t12")
    ctrl_outcomes = {}
    for eid in eps_by_id:
        ctrl = control_cache[eid]
        pnl = prl.control_pnl_for_shape(ctrl, shape_cell, time_stop_et, spy_by_date) if ctrl["traded"] else 0.0
        ctrl_outcomes[eid] = {"pnl": pnl, "date": eid_date[eid], "traded": ctrl["traded"]}

    cand_outcomes = {}
    for eid, ep in eps_by_id.items():
        if ep.get("outcome") == "filled":
            c_pnl = prl.candidate_pnl(ep, shape_cell, time_stop_et, spy_by_date)
            if c_pnl is not None:
                cand_outcomes[eid] = {"pnl": c_pnl, "date": dt.date.fromisoformat(ep["date"]), "traded": True}
                continue
        cand_outcomes[eid] = {"pnl": 0.0, "date": ctrl_outcomes[eid]["date"], "traded": False}

    dwf = prl.compute_delta_wf(cand_outcomes, ctrl_outcomes)
    log(f"pong safe no_cancel|tp30_structure_t12: n_shared={dwf['n_shared']} "
        f"is_delta_mean={dwf['is_delta_mean']} oos_delta_mean={dwf['oos_delta_mean']} wf={dwf['wf_delta']}")
    return [{"date": str(d["date"]), "pnl": d["delta"]} for d in dwf["deltas"]]


# ===============================================================================================
# MAIN
# ===============================================================================================
def main() -> int:
    check_gate()
    calendar = RegimeCalendar()

    results = {}
    errors = {}

    for name, fn in (
        ("elite_bear_level_reject_gate_L1", cohort_elite_bear),
        ("bold_strike_axis_ATM", cohort_bold_strike_atm),
        ("zone_rejection_band_bold_fixed_0.75", cohort_zone_band_bold),
        ("pong_resting_limit_safe_no_cancel_tp30_structure_t12", cohort_pong_safe),
    ):
        log(f"=== {name} ===")
        try:
            cohort = fn()
            log(f"{name}: cohort n={len(cohort)}")
            res = validate_candidate(cohort, candidate_name=name, calendar=calendar,
                                      full_window_start=FULL_WINDOW_START, full_window_end=FULL_WINDOW_END)
            results[name] = res
            log(f"{name}: verdict={res['verdict']} bucket={res.get('target_regime_bucket')} "
                f"n_bucket={res.get('n_bucket')}")
        except Exception as e:  # noqa: BLE001 -- one candidate's failure must not kill the others
            import traceback
            tb = traceback.format_exc()
            log(f"{name}: ERROR {type(e).__name__}: {e}")
            errors[name] = {"error": str(e), "type": type(e).__name__, "traceback": tb}

    # fleet strike / risky-3: no separate cohort (documented disposition in
    # WF-GATE-METHODOLOGY-2026-07-16.md -- resolves via the SAME V15_BOLD_TIERS table as core Bold).
    fleet_note = ("risky-3 resolves its strike via the SAME shared V15_BOLD_TIERS table as core "
                  "Bold (fleet_executor.py#_tiers_for_arm, confirmed by "
                  "test_bold_core_strike_tier_2026_07_15.py). No separate cohort exists "
                  "(WF-GATE-METHODOLOGY-2026-07-16.md's own risky-3 disposition: 'Action taken: "
                  "NONE... there is no ship-ready cell to recommend risky-3 move to'). It "
                  "therefore INHERITS the bold_strike_axis_ATM verdict above by proxy, not a "
                  "separately-computed one.")

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "gate_check": "self_validation_verdict == EARNS_RIGHTS (verified at top of main())",
        "results": results,
        "errors": errors,
        "fleet_strike_risky3_note": fleet_note,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
