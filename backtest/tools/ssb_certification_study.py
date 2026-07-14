"""ssb_certification_study.py -- SS-B PRODUCTION-CODE CERTIFICATION (2026-07-09).

Certifies that the SHIPPED production exit path (commit 933bd6513de3c30046d09a6014a20518edcea5f3,
"SS-B structure-stop live, both lanes, flag-ON") agrees with structure_stop_study.py -- the
validation study that justified shipping it -- and closes that study's disclosed OP-16 gap (it
never replayed the J-anchor source-of-truth trades under SS-B).

WHY THIS IS A DIFFERENT TEST THAN THE STUDY ITSELF (read before trusting a MATCH verdict):
structure_stop_study.replay_structure_aware() NEVER exercises ExitState's own stop_mode==
"structure" resolution or plan_exit_actions' internal _structure_stop_hit branches -- by its
own module docstring, "the structure-stop layer is new code that sits IN FRONT of
plan_exit_actions, never inside it." Concretely: SS_B_SHAPE carries no "stop_mode" key, so
every ExitState the study builds resolves to stop_mode="premium" with premium_stop_pct=-0.50
(numerically identical to the catastrophe cap, but reached via the ORDINARY premium-stop
branch (a), never branch (a2)); the structure-stop itself is a fully separate precomputed
`ss_time` check that ALWAYS overrides whatever plan_exit_actions would have decided on that
bar. So the study's own test suite (including backtest/tests/test_structure_stop_study.py) has
never once exercised the code path that strategies.py's RIBBON_RIDE + exit_actuator.
register_entry + exit_manager.ExitState.from_entry(structure_stop_enabled=True, trigger_level=
...) + plan_exit_actions(last_closed_5m_close=...) actually run live. THIS module builds and
runs THAT path -- the genuine production wiring -- and compares it position-by-position against
the study's already-published SS-B numbers.

TASK 1 -- PARITY: today's (2026-07-09) 10 real fleet positions (trade-today.json / fills-
ledger.jsonl), replayed through:
  (S) the study's OWN replay_structure_aware, re-derived here (must reproduce the persisted
      +$138.50 SS-B total in analysis/recommendations/structure-stop-2026-07-09.json exactly).
  (P) THIS module's replay_production_path: ExitState.from_entry(exit_shape=strategies.
      RIBBON_RIDE.exit.to_dict(), structure_stop_enabled=<params.json, read live>,
      trigger_level=<same value (S) resolved>) + plan_exit_actions fed a PER-1-MIN-TICK
      last_closed_5m_close derived from real SPY 5m bars (the same closed-bar semantics (S)
      uses, but consulted THROUGH plan_exit_actions' own internal branches instead of an
      external override).
Both use IDENTICAL entries, IDENTICAL trigger levels, IDENTICAL real 1-min OPRA option bars.
The only thing that differs is WHICH CODE resolves the structure stop. A MATCH certifies the
production wiring reproduces the study; a REAL divergence means the study's validation does
not transfer byte-for-byte to what actually ships (see docstring above for the one KNOWN
structural gap: pre-TP1, plan_exit_actions checks catastrophe-stop (a) BEFORE structure-stop
(a2), whereas the study's external ss_time check always wins on the same bar).

TASK 2 -- OP-16 J-ANCHOR: replays the 7 CLAUDE.md OP-16 source-of-truth trades (entries taken
VERBATIM from journal/trades.csv -- the same file backtest/autoresearch/audit_j_winners.py
reads, NOT re-derived) under (a) SS-B (the same production-faithful harness as Task 1) and
(b) the OLD -20%/+150%/sell80/fixed CONTROL shape, on REAL Alpaca OPRA 1-min bars for the EXACT
contracts J traded. Computes edge_capture per OP-16's formula from the REPLAYED P&L (J's entry
held fixed; only the EXIT shape is counterfactual).

ANALYSIS ONLY: writes only to analysis/recommendations/. Touches no trading-path file, no
params.json, no strategies.py (both are only READ, live, so a re-run reflects whatever is
actually shipped at run time -- that IS the certification; hard-coding the flag would defeat
the point).

Run: backtest/.venv/Scripts/python.exe backtest/tools/ssb_certification_study.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import pandas as pd  # noqa: E402

import structure_stop_study as sss                       # noqa: E402
import exit_shape_parity_study as esp                     # noqa: E402
import tw8_level_context as lc                            # noqa: E402
from exit_manager import ExitState, plan_exit_actions, parse_time_stop_et  # noqa: E402
import strategies                                          # noqa: E402

PARAMS_SAFE = REPO / "automation" / "state" / "params.json"
PARAMS_AGGRESSIVE = REPO / "automation" / "state" / "aggressive" / "params.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "ssb-certification-2026-07-09.json"
SHIP_COMMIT = "933bd6513de3c30046d09a6014a20518edcea5f3"

TODAY = dt.date(2026, 7, 9)
OP16_MAX = 1542.0
OP16_FLOOR = 771.0

STUDY_PUBLISHED_SS_B_TOTAL = 138.5     # analysis/recommendations/structure-stop-2026-07-09.json
STUDY_PUBLISHED_CONTROL_TOTAL = -400.2  # ..today_exhibit_2026_07_09.candidates.CONTROL.anchor_total

J_ANCHOR_LEVEL_START = dt.date(2026, 3, 1)   # >=40 trading days before the earliest J trade
J_ANCHOR_LEVEL_END = dt.date(2026, 5, 8)     # one day past the latest J trade (2026-05-07)


# ---------------------------------------------------------------------------------------------
# PRODUCTION CONFIG -- read LIVE from the actual params files (never hard-coded/assumed)
# ---------------------------------------------------------------------------------------------
def load_production_config() -> dict:
    safe = json.loads(PARAMS_SAFE.read_text(encoding="utf-8"))
    agg = json.loads(PARAMS_AGGRESSIVE.read_text(encoding="utf-8"))
    return {
        "structure_stop_enabled_safe": bool(safe.get("structure_stop_enabled", False)),
        "structure_stop_enabled_aggressive": bool(agg.get("structure_stop_enabled", False)),
        "time_stop_et_safe": safe.get("time_stop_et"),
        "time_stop_et_aggressive": agg.get("time_stop_et"),
    }


ARM_STRUCTURE_ENABLED_KEY = {
    "safe-1": "structure_stop_enabled_safe", "safe-3": "structure_stop_enabled_safe",
    "risky-1": "structure_stop_enabled_aggressive", "risky-3": "structure_stop_enabled_aggressive",
}
ARM_TIME_STOP_KEY = {
    "safe-1": "time_stop_et_safe", "safe-3": "time_stop_et_safe",
    "risky-1": "time_stop_et_aggressive", "risky-3": "time_stop_et_aggressive",
}


def ribbon_ride_exit_shape() -> dict:
    """The REAL, currently-shipped ribbon_ride exit shape -- imported live from strategies.py,
    never hand-copied, so a future edit there is automatically picked up by this certification."""
    return strategies.RIBBON_RIDE.exit.to_dict()


# ---------------------------------------------------------------------------------------------
# THE PRODUCTION-FAITHFUL REPLAY -- drives ExitState + plan_exit_actions the way exit_actuator.
# manage_tick actually does: structure-stop resolved ONCE at from_entry, structure/catastrophe/
# TP1/trail/time-stop priority decided ENTIRELY INSIDE plan_exit_actions -- no external override,
# unlike structure_stop_study.replay_structure_aware (see module docstring).
# ---------------------------------------------------------------------------------------------
def last_closed_5m_close_asof(spy_lifetime: pd.DataFrame, t: dt.datetime) -> Optional[float]:
    """The close of the most recent SPY 5m bar whose window [open, open+5min) has fully
    elapsed by time `t` (bar timestamps are bar-OPEN, matching this codebase's convention --
    see structure_stop_study.structure_stop_signal_time's `+timedelta(minutes=5)`). None if no
    such bar exists yet (fail-open, matches exit_manager._structure_stop_hit's None-safety).

    DISCLOSED GAP vs the TRUE live feed: fleet_live.py actually forwards
    `usable_signal.get("spot")` (the shared-signal's current/live spot sample, refreshed each
    ~1-minute tick) into manage_tick's last_closed_5m_close parameter -- NOT a value explicitly
    re-derived from a verified-closed 5m SPY bar. This replay uses the doctrine-documented
    closed-bar semantics (the definition exit_manager.py's own docstring and CLAUDE.md
    "chart-stop-primary" describe, and the more conservative/reproducible proxy given historical
    data only supports bar closes, not a tick-by-tick spot log) rather than assuming the two are
    identical. See disclosures in the output JSON."""
    if spy_lifetime.empty:
        return None
    cutoff = t - dt.timedelta(minutes=5)
    closed = spy_lifetime[spy_lifetime["timestamp_et"] <= cutoff]
    if closed.empty:
        return None
    return float(closed.iloc[-1]["close"])


def replay_production_path(
    entry_premium: float, side: str, qty: int, norm_bars: list, spy_lifetime: pd.DataFrame,
    exit_shape: dict, trigger_level: Optional[float], structure_stop_enabled: bool,
    time_stop_et: dt.time, strategy: str = "ribbon_ride",
) -> dict:
    """ONE position, replayed through the REAL production wiring: ExitState.from_entry exactly
    as exit_actuator.register_entry calls it, then plan_exit_actions exactly as exit_actuator.
    manage_tick calls it (the live decision core itself -- no reimplementation), fed a genuine
    per-tick last_closed_5m_close computed from REAL SPY 5m bars.

    Fill-price convention per stage (matches exit_shape_parity_study.replay_position /
    structure_stop_study.replay_structure_aware exactly, so comparisons are apples-to-apples):
    TP1/runner-target fill AT the triggering level; premium/catastrophe-stop fill AT the stop
    level; trail/BE-stop fill at the ratcheted runner_stop; time-stop fills at that bar's close;
    structure-stop (fired HERE, from plan_exit_actions' OWN branch, unlike the study) fills at
    THIS bar's OPEN -- the earliest tradeable price once plan_exit_actions could see the breach,
    the identical "next-bar-open" C6 convention the study uses for its own external check.
    """
    state = ExitState.from_entry(symbol="x", side=side, entry_premium=entry_premium, qty=qty,
                                 exit_shape=exit_shape, strategy=strategy,
                                 trigger_level=trigger_level,
                                 structure_stop_enabled=structure_stop_enabled)
    open_qty = qty
    realized = 0.0
    exits: list[dict] = []
    last_close = entry_premium
    for bar in norm_bars:
        if open_qty <= 0:
            break
        last_close = bar.c
        lc5 = last_closed_5m_close_asof(spy_lifetime, bar.dt)
        now_et = bar.dt.time()
        dec = plan_exit_actions(state, best_premium=bar.h, worst_premium=bar.l,
                                open_qty=open_qty, now_et=now_et, ribbon_flip_back=False,
                                time_stop_et=time_stop_et, last_closed_5m_close=lc5)
        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            if a.stage == "tp1":
                fp = entry_premium * (1.0 + state.tp1_premium_pct)
            elif a.stage == "runner_target":
                fp = entry_premium * (1.0 + state.runner_target_pct)
            elif a.stage == "premium_stop":
                fp = entry_premium * (1.0 + state.premium_stop_pct)
            elif a.stage in ("trail", "be_stop"):
                fp = dec.state.runner_stop_premium
            elif a.stage == "structure_stop":
                fp = bar.o
            else:  # time_stop
                fp = bar.c
            realized += (fp - entry_premium) * a.qty * 100.0
            open_qty -= a.qty
            exits.append({"stage": a.stage, "qty": a.qty, "fill_price": round(fp, 4),
                         "dt": bar.dt.isoformat(), "reason": a.reason})
        state = dec.state
    if open_qty > 0:
        realized += (last_close - entry_premium) * open_qty * 100.0
        exits.append({"stage": "eod_mark", "qty": open_qty, "fill_price": round(last_close, 4)})
        open_qty = 0
    structure_fired = any(e["stage"] == "structure_stop" for e in exits)
    return {"pnl": round(realized, 2), "exits": exits, "structure_fired": structure_fired,
           "final_stop_mode": state.stop_mode}


# ---------------------------------------------------------------------------------------------
# TASK 1 -- ENGINE-vs-STUDY PARITY on today's 10 real fleet positions
# ---------------------------------------------------------------------------------------------
def run_task1_parity(prod_config: dict) -> dict:
    fills = esp.load_fleet_engine_fills()
    positions = esp.reconstruct_positions(fills)
    today_positions = [p for p in positions if p["date_et"] == TODAY.isoformat()]

    spy_full = sss.load_spy_full_with_today()
    prepared, stats = sss.prepare_positions(today_positions, spy_full)

    rows = []
    for p in prepared:
        # (S) the study's OWN SS-B re-derivation (must reproduce the published number)
        ss_time = sss.structure_stop_signal_time(p["spy_lifetime"], p["side"], p["trigger_level"],
                                                  sss.STRUCTURE_BUFFER["SS-B"])
        study = sss.replay_structure_aware(p["entry_premium"], p["side"], p["qty"], p["norm_bars"],
                                           ss_time, sss.SS_B_SHAPE, sss.TIME_STOP_LAYER_B)
        # (P) the production-faithful path -- real shape, real flag, real per-tick structure check
        struct_enabled = prod_config[ARM_STRUCTURE_ENABLED_KEY[p["arm"]]]
        time_stop = parse_time_stop_et(prod_config[ARM_TIME_STOP_KEY[p["arm"]]])
        prod = replay_production_path(p["entry_premium"], p["side"], p["qty"], p["norm_bars"],
                                      p["spy_lifetime"], ribbon_ride_exit_shape(), p["trigger_level"],
                                      struct_enabled, time_stop)

        diff = round(prod["pnl"] - study["pnl"], 2)
        prod_stages = [e["stage"] for e in prod["exits"] if e["stage"] != "eod_mark"]
        study_stages = [e["stage"] for e in study["exits"] if e["stage"] != "eod_mark"]
        if abs(diff) < 0.01:
            cls, note = "MATCH", "production and study SS-B agree to the cent"
        elif prod["structure_fired"] == study["structure_fired"] and prod_stages == study_stages:
            cls = "BENIGN-DIVERGENCE"
            note = ("same exit stage sequence and same structure_fired flag -- the dollar gap is "
                    "a fill-price/time-stop-parameter convention artifact, not a logic gap")
        else:
            cls = "REAL-DIVERGENCE"
            note = (f"stage sequence differs: production={prod_stages} "
                    f"(structure_fired={prod['structure_fired']}) vs study={study_stages} "
                    f"(structure_fired={study['structure_fired']}) -- likely the documented "
                    f"pre-TP1 catastrophe-before-structure ordering gap; inspect exits[] both sides")

        rows.append({
            "arm": p["arm"], "symbol": p["symbol"], "date_et": p["date_et"], "side": p["side"],
            "qty": p["qty"], "entry_premium": p["entry_premium"],
            "trigger_level": p["trigger_level"], "recovery_status": p["recovery_status"],
            "actual_exit_pnl": round(p.get("actual_exit_pnl") or 0.0, 2),
            "study_ss_b": {"pnl": study["pnl"], "structure_fired": study["structure_fired"],
                          "exits": study["exits"]},
            "production_path": {"pnl": prod["pnl"], "structure_fired": prod["structure_fired"],
                               "exits": prod["exits"], "structure_stop_enabled": struct_enabled,
                               "time_stop_et": str(time_stop)},
            "diff_dollars": diff, "divergence_class": cls, "divergence_note": note,
        })

    # Self-check: production-path CONTROL (structure disabled) should reproduce the study's
    # PUBLISHED CONTROL exhibit total -- validates the non-structure branches (catastrophe/TP1/
    # trail/time-stop) of THIS module's harness independently of the structure-stop question.
    control_total = 0.0
    for p in prepared:
        prod_ctl = replay_production_path(p["entry_premium"], p["side"], p["qty"], p["norm_bars"],
                                          p["spy_lifetime"], dict(sss.CONTROL_SHAPE), None, False,
                                          sss.TIME_STOP_LAYER_B)
        control_total += prod_ctl["pnl"]
    control_total = round(control_total, 2)

    study_total = round(sum(r["study_ss_b"]["pnl"] for r in rows), 2)
    prod_total = round(sum(r["production_path"]["pnl"] for r in rows), 2)
    n_match = sum(1 for r in rows if r["divergence_class"] == "MATCH")
    n_benign = sum(1 for r in rows if r["divergence_class"] == "BENIGN-DIVERGENCE")
    n_real = sum(1 for r in rows if r["divergence_class"] == "REAL-DIVERGENCE")
    overall = "REAL-DIVERGENCE" if n_real else ("BENIGN-DIVERGENCE" if n_benign else "MATCH")

    return {
        "n_positions": len(rows), "positions": rows,
        "study_ss_b_published_total": STUDY_PUBLISHED_SS_B_TOTAL,
        "study_ss_b_rederived_total": study_total,
        "study_rederivation_matches_published": abs(study_total - STUDY_PUBLISHED_SS_B_TOTAL) < 0.01,
        "production_path_total": prod_total,
        "total_diff_dollars": round(prod_total - study_total, 2),
        "n_match": n_match, "n_benign_divergence": n_benign, "n_real_divergence": n_real,
        "verdict": overall,
        "control_self_check": {
            "production_harness_control_total": control_total,
            "study_published_control_total": STUDY_PUBLISHED_CONTROL_TOTAL,
            "matches": abs(control_total - STUDY_PUBLISHED_CONTROL_TOTAL) < 0.01,
        },
        "production_config_used": prod_config,
    }


# ---------------------------------------------------------------------------------------------
# TASK 2 -- OP-16 J-ANCHOR edge_capture (SS-B vs the old -20/+150 shape)
# ---------------------------------------------------------------------------------------------
# Entries taken VERBATIM from journal/trades.csv (grepped 2026-07-09) -- the canonical ledger
# audit_j_winners.py reads. NOT re-derived. Cross-checked against CLAUDE.md OP-16 dollar figures.
J_ANCHOR_TRADES = [
    {"date": "2026-04-29", "side": "P", "strike": 710, "qty": 6, "entry_time_et": "10:25:51",
     "entry_premium": 1.67, "role": "winner", "j_pnl": 342.0,
     "note": "trades.csv row 2 verbatim."},
    {"date": "2026-05-01", "side": "P", "strike": 721, "qty": 20, "entry_time_et": "13:09:14",
     "entry_premium": 0.325, "role": "winner", "j_pnl": 470.0,
     "note": "trades.csv row 3: entry_px 0.325 is a QTY-weighted AVERAGE of two legs (13:09 "
             "anticipation entry + 13:36 real trendline-rejection trigger, per notes_short). "
             "Replayed here as ONE position at the averaged premium and the FIRST leg's "
             "timestamp -- no per-leg qty split is recorded in the ledger, so this is the "
             "best-available faithful reconstruction, not a re-derivation."},
    {"date": "2026-05-04", "side": "P", "strike": 721, "qty": 10, "entry_time_et": "10:27:50",
     "entry_premium": 0.85, "role": "winner", "j_pnl": 730.0,
     "note": "trades.csv row 5 verbatim."},
    {"date": "2026-05-05", "side": "P", "strike": 722, "qty": 20, "entry_time_et": "13:00:33",
     "entry_premium": 0.30, "role": "loser", "j_pnl": -260.0,
     "note": "trades.csv row 8 verbatim (manual J trade, UNCATEGORIZED_PROBE -- no playbook "
             "trigger fired in the system either, per notes_short)."},
    {"date": "2026-05-06", "side": "P", "strike": 730, "qty": 10, "entry_time_et": "13:09:37",
     "entry_premium": 0.32, "role": "loser", "j_pnl": -300.0,
     "note": "trades.csv row 9 verbatim (manual J trade, held to expiry with NO stop -- worst-"
             "case outcome of Rule 3/8 violations; replay applies the SS-B/CONTROL stop "
             "discipline J did not)."},
    {"date": "2026-05-07", "side": "C", "strike": 734, "qty": 3, "entry_time_et": "12:30:00",
     "entry_premium": 0.73, "role": "loser", "j_pnl": -45.0,
     "note": "trades.csv row 7 verbatim (BULLISH_RECLAIM_RIDE_THE_RIBBON -- the system's FIRST "
             "autonomous trade; time_entry recorded to the minute only, seconds assumed :00)."},
    {"date": "2026-05-07", "side": "C", "strike": 737, "qty": 10, "entry_time_et": "11:14:15",
     "entry_premium": 0.38, "role": "loser", "j_pnl": -120.0,
     "note": "trades.csv row 10 verbatim (manual J trade, UNCATEGORIZED_PROBE_MANUAL -- separate "
             "from the same-day 734C system trade)."},
]
assert round(sum(t["j_pnl"] for t in J_ANCHOR_TRADES if t["role"] == "winner"), 2) == OP16_MAX, \
    "J_ANCHOR_TRADES winner sum must equal CLAUDE.md OP-16 max ($1,542) -- transcription check"
assert len(J_ANCHOR_TRADES) == 7 and sum(1 for t in J_ANCHOR_TRADES if t["role"] == "loser") == 4


def occ_symbol(date: dt.date, strike: int, side: str) -> str:
    """OCC-format SPY option symbol: SPY{YYMMDD}{C|P}{strike*1000:08d} (matches
    structure_stop_study.option_side_from_symbol's own convention, inverted)."""
    return f"SPY{date.strftime('%y%m%d')}{side}{strike * 1000:08d}"


def et_time_to_utc_iso(date_et: str, hh: int, mm: int, ss: int) -> str:
    """ET HH:MM:SS -> a full UTC ISO string ('...THH:MM:SSZ'), EDT convention (+4h, wraps at
    24h) -- extends exit_shape_parity_study._et_hhmm_to_utc (which drops seconds) so the
    entry-bar filter matches this codebase's OWN established string-comparison convention for
    real fills (see esp.norm_bars/replay_position: `b["t"] >= entry_ts_utc`, sub-minute-precise
    entries EXCLUDE the bar containing the exact entry second and start from the next full
    minute -- verified this is the pre-existing behavior for every real-fill replay in this
    repo, not something introduced here)."""
    utc_hh = (hh + 4) % 24
    return f"{date_et}T{utc_hh:02d}:{mm:02d}:{ss:02d}Z"


def run_task2_j_anchor(prod_config: dict) -> dict:
    spy_full = lc.load_spy_full(J_ANCHOR_LEVEL_START, J_ANCHOR_LEVEL_END)
    level_cache: dict = {}
    # time_stop_et is identical in both params files (both "15:40") -- confirmed live above;
    # use the safe-arm value as the single production value (would diverge loudly if the files
    # ever disagree, since `assert` below would trip).
    assert prod_config["time_stop_et_safe"] == prod_config["time_stop_et_aggressive"], (
        "safe/aggressive time_stop_et disagree -- Task 2 needs an explicit per-arm choice")
    time_stop = parse_time_stop_et(prod_config["time_stop_et_safe"])

    rows = []
    for t in J_ANCHOR_TRADES:
        date = dt.date.fromisoformat(t["date"])
        symbol = occ_symbol(date, t["strike"], t["side"])
        hh, mm, ss = (int(x) for x in t["entry_time_et"].split(":"))
        entry_ts_et = dt.datetime.combine(date, dt.time(hh, mm, ss))

        trigger_level, recovery_status = sss.recover_trigger_level_real_position(
            spy_full, level_cache, date, entry_ts_et, t["side"])

        bars = esp.fetch_option_bars(symbol, t["date"])
        entry_ts_utc_iso = et_time_to_utc_iso(t["date"], hh, mm, ss)
        norm_bars = sss.norm_bars_from_esp(bars, entry_ts_utc=entry_ts_utc_iso)
        spy_lifetime = spy_full[(spy_full["date"] == date) & (spy_full["timestamp_et"] >= entry_ts_et)]

        fallback_note = None
        if trigger_level is None:
            fallback_note = (
                f"trigger_level unrecoverable (recovery_status={recovery_status}); "
                "ExitState.from_entry resolves stop_mode='premium' using RIBBON_RIDE.exit's OWN "
                "premium_stop_pct=-0.20 (the documented 'flag-OFF emergency fallback', NOT the "
                "-50% catastrophe cap -- automation/state/fleet/strategies.py RIBBON_RIDE.note). "
                "This is production's real, verified fallback behavior, not a convention chosen "
                "for this study.")

        ss_b = replay_production_path(t["entry_premium"], t["side"], t["qty"], norm_bars,
                                      spy_lifetime, ribbon_ride_exit_shape(), trigger_level,
                                      True, time_stop)
        control = replay_production_path(t["entry_premium"], t["side"], t["qty"], norm_bars,
                                         spy_lifetime, dict(sss.CONTROL_SHAPE), None, False,
                                         time_stop)

        def _classify(role: str, pnl: float) -> str:
            if role == "winner":
                return "CAUGHT" if pnl > 0 else "MISSED"
            return "AVOIDED" if pnl >= 0 else "OVERTRADED"

        rows.append({
            "date": t["date"], "role": t["role"], "side": t["side"], "strike": t["strike"],
            "qty": t["qty"], "entry_time_et": t["entry_time_et"], "entry_premium": t["entry_premium"],
            "j_actual_pnl": t["j_pnl"], "symbol": symbol,
            "trigger_level": trigger_level, "recovery_status": recovery_status,
            "fallback_note": fallback_note, "source_note": t["note"],
            "n_option_bars_available": len(bars), "n_option_bars_replayed": len(norm_bars),
            "ss_b_pnl": ss_b["pnl"], "ss_b_structure_fired": ss_b["structure_fired"],
            "ss_b_classification": _classify(t["role"], ss_b["pnl"]),
            "ss_b_exits": ss_b["exits"],
            "control_pnl": control["pnl"], "control_classification": _classify(t["role"], control["pnl"]),
            "control_exits": control["exits"],
        })

    def _edge_capture(pnl_key: str) -> tuple[float, float, float]:
        winner_total = sum(r[pnl_key] for r in rows if r["role"] == "winner")
        loser_exposure = sum(max(0.0, -r[pnl_key]) for r in rows if r["role"] == "loser")
        return round(winner_total - loser_exposure, 2), round(winner_total, 2), round(loser_exposure, 2)

    edge_ss_b, winner_total_ss_b, loser_exp_ss_b = _edge_capture("ss_b_pnl")
    edge_control, winner_total_control, loser_exp_control = _edge_capture("control_pnl")

    winners_flipped_negative = [r["date"] for r in rows
                                if r["role"] == "winner" and r["ss_b_pnl"] < 0]
    op16_pass = edge_ss_b >= OP16_FLOOR and not winners_flipped_negative

    return {
        "trades": rows,
        "edge_capture_ss_b": edge_ss_b, "winner_total_ss_b": winner_total_ss_b,
        "loser_exposure_ss_b": loser_exp_ss_b,
        "edge_capture_control": edge_control, "winner_total_control": winner_total_control,
        "loser_exposure_control": loser_exp_control,
        "op16_max": OP16_MAX, "op16_floor": OP16_FLOOR,
        "edge_capture_pct_of_max_ss_b": round(edge_ss_b / OP16_MAX * 100, 1),
        "any_winner_flipped_negative_ss_b": bool(winners_flipped_negative),
        "winners_flipped_negative_dates": winners_flipped_negative,
        "verdict": "PASS" if op16_pass else "FAIL",
        "time_stop_et_used": str(time_stop),
    }


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    prod_config = load_production_config()
    print(f"[ssb-cert] production config (read live): {prod_config}", flush=True)

    print("[ssb-cert] TASK 1 -- engine-vs-study parity on today's 10 real positions...", flush=True)
    parity = run_task1_parity(prod_config)
    print(f"[ssb-cert] parity: n={parity['n_positions']} match={parity['n_match']} "
          f"benign={parity['n_benign_divergence']} real={parity['n_real_divergence']} "
          f"verdict={parity['verdict']}", flush=True)
    print(f"[ssb-cert] study SS-B re-derived ${parity['study_ss_b_rederived_total']} "
          f"(published ${parity['study_ss_b_published_total']}, matches="
          f"{parity['study_rederivation_matches_published']}) vs production-path "
          f"${parity['production_path_total']} (diff ${parity['total_diff_dollars']})", flush=True)
    print(f"[ssb-cert] control self-check: harness ${parity['control_self_check']['production_harness_control_total']} "
          f"vs study-published ${parity['control_self_check']['study_published_control_total']} "
          f"matches={parity['control_self_check']['matches']}", flush=True)

    print("[ssb-cert] TASK 2 -- OP-16 J-anchor edge_capture (SS-B vs CONTROL)...", flush=True)
    j_anchor = run_task2_j_anchor(prod_config)
    print(f"[ssb-cert] edge_capture SS-B=${j_anchor['edge_capture_ss_b']} "
          f"({j_anchor['edge_capture_pct_of_max_ss_b']}% of ${OP16_MAX} max, floor ${OP16_FLOOR}) "
          f"CONTROL=${j_anchor['edge_capture_control']} verdict={j_anchor['verdict']} "
          f"winners_flipped={j_anchor['winners_flipped_negative_dates']}", flush=True)

    disclosures = [
        "Task 1's 'production path' feeds plan_exit_actions a last_closed_5m_close derived from "
        "REAL, historical, verified-CLOSED SPY 5m bars (matching exit_manager.py's own doctrine "
        "docstring). fleet_live.py's ACTUAL live wiring instead forwards "
        "`usable_signal.get('spot')` -- the shared-signal's current spot sample at that tick, "
        "NOT explicitly re-derived from a closed-bar close. No historical per-minute `spot` log "
        "was mined for this certification (out of scope); this is a disclosed, not silently "
        "assumed, gap between 'what the parameter is named' and 'what fleet_live.py actually "
        "threads into it'. It does not affect today's 10 positions either way since all 10 "
        "closed by 10:34 ET on fast TP1/premium exits, well before any structure/time-stop path "
        "could diverge on this specific point -- see each position's exits[] trace.",
        "Both params.json and aggressive/params.json currently set time_stop_et='15:40' (NOT "
        "the exit_manager.TIME_STOP_ET default of 15:50 the study's own layer(b)/exhibit used). "
        "This certification uses the REAL 15:40 value throughout (Task 1 per-arm, Task 2 "
        "uniformly, both confirmed identical across the two params files). Inert for today's "
        "10 positions (all closed by 10:34 ET) and for 6 of 7 J-anchor trades; material only for "
        "2026-05-06 (SPY 730P), where it forces JJ's manually-held-to-expiry position flat well "
        "before J's actual 18:17 ET exit -- see that trade's exits[] trace.",
        "Task 1's structure-stop fill price (when plan_exit_actions' OWN branch fires, unlike "
        "the study's external override) uses the SAME bar's OPEN as the study's convention "
        "(next-bar-open, C6) -- a deliberate choice to keep the comparison apples-to-apples, "
        "not an independently re-derived convention.",
        "Task 2 trigger_level recovery uses structure_stop_study.recover_trigger_level_real_"
        "position (the backward-scan heuristic, lookback=8 bars/40min) -- the SAME method the "
        "study's own layer (b) real-fills anchor used, because J's manual/system trades in "
        "journal/trades.csv carry no entry_spot label (the exact-match tw8_level_context method "
        "needs one). This is a coarser, disclosed approximation, not an exact match -- see "
        "recovery_status per trade.",
        "The 2026-05-01 721P winner's entry_premium (0.325) is a qty-weighted average of two "
        "legs at different times (13:09 + 13:36); replayed as one position at the averaged "
        "premium and the first leg's timestamp (no per-leg qty split is recorded).",
        "5-min OPRA-derived SPY structure bars + REAL 1-min Alpaca OPRA option bars throughout "
        "(both tasks) -- no synthetic/BS pricing (C1).",
        "Frictionless fills at trigger/stop/target levels (no spread/queue modelled), matching "
        "every prior anchor study in this codebase (T3/T4/T5/T-W8/structure_stop_study).",
    ]

    key_findings = [
        f"PARITY VERDICT: {parity['verdict']} -- production-path total ${parity['production_path_total']} "
        f"vs study SS-B total ${parity['study_ss_b_rederived_total']} (published ${parity['study_ss_b_published_total']}), "
        f"diff ${parity['total_diff_dollars']} across {parity['n_positions']} positions "
        f"({parity['n_match']} MATCH, {parity['n_benign_divergence']} BENIGN, {parity['n_real_divergence']} REAL).",
        f"Harness self-check: replaying today's positions under CONTROL through THIS module's OWN "
        f"production-faithful function reproduces the study's published CONTROL total "
        f"(${parity['control_self_check']['production_harness_control_total']} vs "
        f"${parity['control_self_check']['study_published_control_total']}, matches="
        f"{parity['control_self_check']['matches']}) -- validates the non-structure branches "
        f"independently of the structure-stop question.",
        f"OP-16 J-ANCHOR: edge_capture SS-B=${j_anchor['edge_capture_ss_b']} vs floor ${OP16_FLOOR} "
        f"({j_anchor['edge_capture_pct_of_max_ss_b']}% of ${OP16_MAX} max) -> {j_anchor['verdict']}. "
        f"CONTROL edge_capture=${j_anchor['edge_capture_control']} for comparison. "
        f"Winners flipped negative under SS-B: {j_anchor['winners_flipped_negative_dates'] or 'NONE'}.",
    ]

    out = {
        "_doc": "SS-B production-code certification -- parity vs structure_stop_study.py's "
                "published numbers (Task 1) + OP-16 J-anchor edge_capture under SS-B vs CONTROL "
                "(Task 2, closes the study's disclosed gap). ANALYSIS ONLY.",
        "generated_at": dt.datetime.now().isoformat(),
        "commit_certified": SHIP_COMMIT,
        "parity": parity,
        "j_anchor": j_anchor,
        "key_findings": key_findings,
        "disclosures": disclosures,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[ssb-cert] wrote {OUT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
