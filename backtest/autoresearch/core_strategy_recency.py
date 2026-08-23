"""core_strategy_recency.py -- WS11: CORE-STRATEGY RECENCY WIRING (2026-08-01).

THE GAP THIS CLOSES: recency_check.py runs the rolling 25-trading-day CONFIRM gate but
covers only the 3 secondary edges (vwap_continuation / vwap_reclaim_failed_break /
vix_regime_dayside) -- NOT the core RIDE_THE_RIBBON strategy (either direction) that
actually trades every day. J's standing rule (2026-07-31, verbatim: "the same thing that
worked on day three hundred and seventy two ago is not gonna work on day one hundred and
sixty two ago") applies to the CORE strategy MORE than to any gate: it is the largest
armed thing in the system with no revalidation clock. This module is that clock.

WHAT IT REUSES (never reinvented):
  - autoresearch.recency_check: RECENCY_LOOKBACK_TRADING_DAYS (25), CONFIRM_N_FLOOR (10),
    _latest_rolling (auto-resolving newest rolling SPY/VIX daily-append file) -- imported.
  - tools.engine_fullhist_replay (efr): SAFE_BASE_LIVE (the field-cited params.json
    translation), TIME_STOP_ET, build_ribbon_lookup, ribbon_tick_df_for -- the SAME
    two-layer production-parity replay (orchestrator entry layer + walk_exit_manager /
    plan_exit_actions exit layer) g2_trendline_bypass_ab_2026_08_01.py used tonight.
  - lib.orchestrator.run_backtest + lib.exit_manager_walk.walk_exit_manager +
    fleet strategies.by_name("ribbon_ride").exit.to_dict() -- byte-same machinery.

THREE STRATA, NEVER SILENTLY BLENDED (the WS11 rule: "broker fills first; where n<floor,
supplement with the fullhist replay's recent window, disclosed separately"):
  1. broker_core   -- REAL broker fills (journal/trades.csv, backfilled from
                      pnl-statement.json broker truth by fleet_journal_bridge) for the
                      CORE lanes only (account_id 'safe' = core Safe, 'bold' = core Bold),
                      setup in the RIDE_THE_RIBBON family, per direction (P=bear, C=bull).
                      Exit LEGS of one entry (tp1 leg + runner leg share account/date/
                      time_entry/contract) are grouped into ONE trade event so n counts
                      ENTRIES, not legs. THE VERDICT AUTHORITY (C1: real fills only).
  2. broker_fleet_context -- the same family's real fills on the fleet arms (roster-driven
                      id list from automation/state/fleet/accounts.json, L234: never a
                      hardcoded lineup). Same signal family, different risk shells --
                      DISCLOSED CONTEXT only, never in the core verdict.
  3. replay_supplement_safe_shape -- the fullhist two-layer replay (Safe shape; there is
                      NO production-parity Bold replay harness in this codebase, per
                      engine_fullhist_replay.py's own scope disclosure -- stated, not
                      papered over), full frame 2025-01-02..latest, sliced to the same
                      recent window. Real cached OPRA contracts only; missing contracts
                      are EXCLUDED AND COUNTED, never BS-synthesized. Engine-sim evidence,
                      quoted next to (never added into) the broker n.

VERDICT PER DIRECTION (rules inherited from recency_check's documented floor semantics,
frozen here BEFORE the first run; the floor is CONFIRM_N_FLOOR, imported not copied):
  GREEN        broker-core expectancy/trade > 0 AND n >= floor AND the sign SURVIVES
               concentration (see below)
  RED          broker-core expectancy/trade <= 0 AND n >= floor AND the sign SURVIVES
               concentration (a losing core strategy on real recent fills is the loudest
               possible signal -- but only when it is a genuinely BROAD signal)
  GREEN_CONCENTRATED / RED_CONCENTRATED  (added 2026-08-23, J directive, OP-25 self-
               correction -- 3rd confirmed instance of the naive-mean-only defect this same
               weekend, after gate_expiry_check.py's costing_verdict, commit 71c39545): this
               used to be a NAIVE MEAN ONLY check -- n>=floor AND sign(mean) => a bare
               actionable GREEN or RED, no drop-topN, no day-level term, no robustness check
               at all. Measured 2026-07-20..08-21 (core safe+bold, n=31/side): BULL read a
               clean GREEN at +$2.45/tr when its ENTIRE +$76 net was TWO DAYS (2026-08-04
               +$1,141 and 2026-08-13 +$962 = +$2,103, i.e. 2,767% of net -- the label dies on
               dropping ONE of those days), while BEAR read a clean RED at -$16.71/tr for an
               evenly-spread bleed whose win rate is actually HIGHER (35.5% vs 25.8%). At
               drop-top3 the two were statistically indistinguishable (-$55.36 vs -$51.96,
               gap $3.40; day-block bootstrap B=20,000 gives P(gap<=0)=0.410) yet read as
               opposite, confident labels -- an OP-25 violation this fix closes. A sign no
               longer earns a bare GREEN/RED unless it SURVIVES concentration on BOTH axes:
               drop_top3/drop_bottom3 (per-trade, via backtest/lib/concentration.py, the SAME
               shared helper gate_expiry_check.py's costing_verdict uses) AND
               drop_best2_days/drop_worst2_days (per-DAY -- the term that matters MOST here,
               since instance 3's artifact was 2 DAYS, not 3 trades: a single outsized session
               can spread across several entries that no per-trade drop would catch alone).
               Missing/unknown concentration data is treated as UNPROVEN, never an automatic
               pass -- fails CLOSED, exactly like costing_verdict's drop_top3 rule. A
               concentration-carried GREEN downgrades to GREEN_CONCENTRATED ("not actionable
               on its own"); a concentration-carried RED downgrades to RED_CONCENTRATED ("not
               a broad systemic signal, read in context") -- neither can ever again be
               misread as a finished finding, and NEITHER trips gate_expiry_check.py's
               STATUS.md "## Known broken" alarm (that field checks the literal string "RED"
               only -- see check_gate's overall-mapping).
  UNDERPOWERED 0 < n < floor -- no verdict manufactured; supplement quoted alongside
  NO_FILLS     n == 0
NOTE the semantics differ from gate_expiry_check's per-GATE verdicts (there RED = the
gate is costing money by refusing winners; here RED = the strategy itself is losing).
Both mean "needs attention now" on the shared surface; reason strings carry the meaning.

INTEGRATION (same surface as the gate-expiry instrument, additive):
  - automation/state/gate-registry.json carries two category="core_strategy" rows
    (core_strategy_bear / core_strategy_bull); gate_expiry_check.check_gate routes that
    category here (evaluate_for_registry) so the nightly Gamma_GateExpiryCheck fire
    computes + reports core-strategy recency on the same gate-registry-status.json
    surface and the same newly-RED STATUS.md flag path. No second report invented.
  - evaluate() persists automation/state/core-strategy-recency.json; firm_brief.py's
    "Core strategy recency" section renders its headline (fail-open).

DISCLOSURE: per-trade EXPECTANCY not WR alone; window n is SMALL by design and printed
with every number; the recent window includes the level-feed-outage week (2026-07-25..
07-30, feed repaired ~07-31) -- fills from that stretch are real fills and are NOT
excluded, but the outage is named so a RED is read in context. RESEARCH/REPORT ONLY:
no order, no arming, no param edit, fail-open throughout (OP-25).

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/core_strategy_recency.py
     [--lookback N] [--floor N] [--no-replay]
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, copied verbatim from
# setup/guard_runner_slow.py -- convention for anything a pythonw scheduled chain can
# import/run; see gate_expiry_check.py's identical header for the 2026-07-14 root cause).
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "core-strategy-recency.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "core-strategy-recency.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import csv
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
TOOLS = REPO / "tools"
# Same order g2_trendline_bypass_ab_2026_08_01.py uses -- FLEET_DIR must win the
# `strategies` name (automation/state/fleet/strategies.py, not any tools sibling).
for _p in (str(ROOT), str(REPO), str(TOOLS), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch.recency_check import (  # noqa: E402
    RECENCY_LOOKBACK_TRADING_DAYS,
    CONFIRM_N_FLOOR,
    _latest_rolling,
)
from lib.concentration import (  # noqa: E402
    drop_top_n,
    drop_bottom_n,
    drop_best_days,
    drop_worst_days,
    top_day_share,
)

# concentration terms (2026-08-23, see module docstring's GREEN_CONCENTRATED / RED_CONCENTRATED
# paragraph): trade-level drop-N and day-level drop-N-days, shared with gate_expiry_check.py's
# CONCENTRATION_DROP_TOP_N via backtest/lib/concentration.py.
CONCENTRATION_DROP_TOP_N = 3
CONCENTRATION_DROP_BEST_DAYS = 2

TRADES_CSV = ROOT / "journal" / "trades.csv"
FLEET_ACCOUNTS = FLEET_DIR / "accounts.json"
OUT_JSON = ROOT / "automation" / "state" / "core-strategy-recency.json"
DATA = REPO / "data"
OLD_SPY = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
OLD_VIX = DATA / "vix_5m_2025-01-01_2026-07-22.csv"
OLD_WINDOW_END = dt.date(2026, 7, 22)
FULL_START = dt.date(2025, 1, 2)

FAMILY_SETUPS = {"BEARISH_REJECTION_RIDE_THE_RIBBON", "BULLISH_RECLAIM_RIDE_THE_RIBBON"}
CORE_ACCOUNTS = {"safe": "core Safe", "bold": "core Bold"}
SIDE_NAME = {"P": "bear", "C": "bull"}
_FLEET_ARM_RE = re.compile(r"^(safe|risky|bold)-\d+$")

# The level-feed-outage stretch named in every honest read of this window (established
# 2026-08-01 evidence base; see module docstring DISCLOSURE paragraph).
OUTAGE_NOTE = ("recent window includes the level-feed-outage stretch (~2026-07-25..07-30, "
               "repaired ~07-31); those fills are real and included, read RED in context")


def log(msg: str) -> None:
    print(f"[core-recency] {msg}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# broker-fills layer (pure helpers, unit-tested)
# ─────────────────────────────────────────────────────────────────────────────

def fleet_arm_ids() -> set[str]:
    """Roster-driven fleet arm ids (L234: a hardcoded lineup goes synthetic-by-omission
    when arms change). SPY-shape arms only (`{safe,risky,bold}-N`); futures arms and the
    core aliases are excluded. Fail-open to the regex alone on a missing/odd roster."""
    ids: set[str] = set()
    try:
        d = json.loads(FLEET_ACCOUNTS.read_text(encoding="utf-8"))
        for a in d.get("arms", []):
            aid = a.get("id")
            if isinstance(aid, str) and _FLEET_ARM_RE.match(aid):
                ids.add(aid)
    except Exception as exc:  # noqa: BLE001 -- roster unreadable must not kill the report
        log(f"WARN fleet roster unreadable ({exc}); fleet context matches by pattern only")
    return ids


def load_broker_rows(csv_path: Path = TRADES_CSV) -> list[dict]:
    """Read journal/trades.csv fail-open per row (the file has known malformed legacy
    rows whose notes bled across columns -- they are excluded downstream by the
    account/setup/side/pnl validators, and counted)."""
    try:
        with csv_path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except OSError as exc:
        log(f"WARN trades.csv unreadable: {exc}")
        return []


def group_fills(rows: list[dict], window_start: dt.date, window_end: dt.date,
                fleet_ids: set[str]) -> tuple[list[dict], dict]:
    """Fold per-LEG journal rows into per-ENTRY trade events within the window.

    A tp1 leg and its runner leg share (account_id, date, time_entry, contract) -- one
    entry fill, several exit legs (e.g. the 2026-07-31 12:19 746C entry is two rows:
    qty3 tp1 +$96 and qty2 trail +$30 = ONE +$126 trade). n must count ENTRIES.

    Returns (events, exclusions) where each event carries account/lane/side/date/pnl and
    exclusions counts every dropped row by reason (C7: audited outputs, not exit codes)."""
    groups: dict[tuple, dict] = {}
    excl = {"bad_date": 0, "outside_window": 0, "non_family": 0, "bad_side": 0,
            "bad_pnl": 0, "unattributed_account": 0, "side_setup_mismatch": 0}
    for r in rows:
        try:
            d = dt.date.fromisoformat((r.get("date") or "")[:10])
        except ValueError:
            excl["bad_date"] += 1
            continue
        if not (window_start <= d <= window_end):
            excl["outside_window"] += 1
            continue
        setup = r.get("setup") or ""
        if setup not in FAMILY_SETUPS:
            excl["non_family"] += 1
            continue
        acct = (r.get("account_id") or "").strip()
        if acct in CORE_ACCOUNTS:
            lane = "core"
        elif acct in fleet_ids or _FLEET_ARM_RE.match(acct):
            lane = "fleet"
        else:
            excl["unattributed_account"] += 1
            continue
        side = r.get("c_or_p")
        if side not in ("P", "C"):
            excl["bad_side"] += 1
            continue
        # cross-check: setup family vs contract right must agree (a P fill journaled as a
        # BULLISH_RECLAIM row is a data defect, not a trade to score)
        if (side == "P") != setup.startswith("BEARISH"):
            excl["side_setup_mismatch"] += 1
            continue
        try:
            pnl = float(r.get("dollar_pnl"))
        except (TypeError, ValueError):
            excl["bad_pnl"] += 1
            continue
        key = (acct, str(r.get("date")), str(r.get("time_entry")), str(r.get("contract")))
        g = groups.setdefault(key, {"account": acct, "lane": lane, "side": side,
                                    "date": str(r.get("date")), "pnl": 0.0, "n_legs": 0})
        g["pnl"] += pnl
        g["n_legs"] += 1
    events = sorted(groups.values(), key=lambda g: (g["date"], g["account"]))
    for g in events:
        g["pnl"] = round(g["pnl"], 2)
    return events, excl


def cell_metrics(events: list[dict]) -> dict:
    """n / total / expectancy / WR / day-count for one cohort cell, PLUS concentration
    diagnostics (2026-08-23, see module docstring): drop_top3/drop_bottom3 (per-trade) and
    drop_best2_days/drop_worst2_days (per-day, via backtest/lib/concentration.py -- the SAME
    shared helper gate_expiry_check.py's costing_verdict uses) and top_day_share (disclosure).
    Computed here, once, so every caller (broker_core, broker_fleet_context, the replay
    supplement, by_account sub-cells) carries the same fields -- direction_verdict reads them
    straight off the cell it's handed, exactly like costing_verdict reads drop_top3 off `m`.
    Pure."""
    if not events:
        return {"n": 0}
    pnls = [e["pnl"] for e in events]
    total = round(sum(pnls), 2)
    records = [(e["date"], e["pnl"]) for e in events]
    drop_top3, n_dropped_top3 = drop_top_n(records, CONCENTRATION_DROP_TOP_N)
    drop_bottom3, n_dropped_bottom3 = drop_bottom_n(records, CONCENTRATION_DROP_TOP_N)
    drop_best2_days, n_days_dropped_best, dropped_best_dates = drop_best_days(
        records, CONCENTRATION_DROP_BEST_DAYS)
    drop_worst2_days, n_days_dropped_worst, dropped_worst_dates = drop_worst_days(
        records, CONCENTRATION_DROP_BEST_DAYS)
    return {
        "n": len(events),
        "total_dollar": total,
        "exp_per_trade": round(total / len(events), 2),
        "wr_pct": round(100.0 * sum(1 for p in pnls if p > 0) / len(pnls), 1),
        "n_days": len({e["date"] for e in events}),
        "first_fill": min(e["date"] for e in events),
        "last_fill": max(e["date"] for e in events),
        "drop_top3": drop_top3, "n_dropped_for_drop_top3": n_dropped_top3,
        "drop_bottom3": drop_bottom3, "n_dropped_for_drop_bottom3": n_dropped_bottom3,
        "drop_best2_days": drop_best2_days, "n_days_dropped_for_drop_best2_days": n_days_dropped_best,
        "dropped_best_days": dropped_best_dates,
        "drop_worst2_days": drop_worst2_days, "n_days_dropped_for_drop_worst2_days": n_days_dropped_worst,
        "dropped_worst_days": dropped_worst_dates,
        "top_day_share": top_day_share(records),
    }


def _concentration_survives(cell: dict, positive: bool) -> tuple[bool, str]:
    """(survives, note) -- CONCENTRATION TERM (2026-08-23, see module docstring's
    GREEN_CONCENTRATED / RED_CONCENTRATED paragraph). For a positive-mean cell, 'survives'
    means the total stays POSITIVE after dropping BOTH its top-3 winning trades AND its best
    2 days. For a negative-mean cell, 'survives' (as a genuinely broad RED, not a couple of
    blowup days) means the total stays NEGATIVE after dropping its bottom-3 losing trades AND
    its worst 2 days. Missing concentration data (cell has no drop_top3/drop_best2_days key,
    e.g. drop_bottom3/drop_worst2_days) is UNPROVEN, never an automatic pass -- fails CLOSED,
    mirroring gate_expiry_check.costing_verdict's identical drop_top3 rule."""
    if positive:
        t3, d2 = cell.get("drop_top3"), cell.get("drop_best2_days")
        if t3 is None or d2 is None:
            return False, "concentration UNKNOWN (drop-top3/drop-best2-days not supplied)"
        if t3 <= 0 or d2 <= 0:
            return False, (f"drop-top3=${t3}, drop-best2-days=${d2} -- does NOT survive "
                           f"(sign flips or zeroes out)")
        return True, f"drop-top3=${t3}, drop-best2-days=${d2} -- survives, broad signal"
    b3, w2 = cell.get("drop_bottom3"), cell.get("drop_worst2_days")
    if b3 is None or w2 is None:
        return False, "concentration UNKNOWN (drop-bottom3/drop-worst2-days not supplied)"
    if b3 > 0 or w2 > 0:
        return False, (f"drop-bottom3=${b3}, drop-worst2-days=${w2} -- sign flips positive "
                       f"once concentration is removed")
    return True, f"drop-bottom3=${b3}, drop-worst2-days=${w2} -- still negative, broad signal"


def direction_verdict(cell: dict, floor: int) -> tuple[str, str]:
    """The frozen verdict rules (module docstring). Applied to the BROKER-CORE cell ONLY --
    the replay supplement never lifts n over the floor (the never-blend rail).

    CONCENTRATION TERM (added 2026-08-23, J directive, OP-25 self-correction, 3rd confirmed
    instance of the naive-mean-only defect -- see module docstring for the full incident: bull
    read a clean GREEN carried by 2 days out of 31 trades while bear read a clean RED for an
    evenly-spread, higher-win-rate bleed indistinguishable from bull at drop-top3). n>=floor
    plus sign(mean) alone can no longer earn a bare GREEN or RED -- the sign must SURVIVE
    _concentration_survives (both the per-trade and the per-day term) or it downgrades to
    GREEN_CONCENTRATED / RED_CONCENTRATED, explicitly NOT actionable/broad on its own."""
    n = cell.get("n", 0)
    exp = cell.get("exp_per_trade")
    if n == 0:
        return "NO_FILLS", "no core-lane real fills in the recent window"
    if n < floor:
        sign = "positive" if (exp or 0) > 0 else "negative"
        return "UNDERPOWERED", (f"n={n} < floor {floor} on real fills ({sign} "
                                f"${exp}/tr) -- no verdict manufactured; see replay supplement")
    if exp is not None and exp > 0:
        survives, note = _concentration_survives(cell, positive=True)
        if not survives:
            return "GREEN_CONCENTRATED", (
                f"NOT ACTIONABLE (concentration-carried): real-fills exp +${exp}/tr, n={n} "
                f">= floor {floor}, but {note} -- this positive mean is NOT a broad edge; "
                f"treat as unproven until a fuller sample supports it.")
        return "GREEN", f"real-fills exp +${exp}/tr, n={n} >= floor {floor} -- {note}"
    survives, note = _concentration_survives(cell, positive=False)
    if not survives:
        return "RED_CONCENTRATED", (
            f"NOT A BROAD SIGNAL (concentration-carried): real-fills exp ${exp}/tr, n={n} "
            f">= floor {floor}, but {note} -- read this in context, not as a clean systemic "
            f"RED; a handful of days/trades are carrying the whole loss.")
    return "RED", (f"real-fills exp ${exp}/tr NEGATIVE-or-flat, n={n} >= floor {floor} "
                   f"-- the core strategy itself is losing on the freshest window, and this "
                   f"read is broad ({note})")


# ─────────────────────────────────────────────────────────────────────────────
# replay-supplement layer (heavy; production-parity two-layer replay, Safe shape)
# ─────────────────────────────────────────────────────────────────────────────

def _load_extended_frame():
    """OLD master (..2026-07-22) + strictly-after tail of the NEWEST rolling daily-append
    file (auto-resolved via recency_check._latest_rolling, so the frame extends nightly
    without a hardcoded filename -- the C14 dead-literal trap _latest_rolling exists for)."""
    import pandas as pd
    spy_old = pd.read_csv(OLD_SPY)
    spy_old["timestamp_et"] = pd.to_datetime(spy_old["timestamp_et"])
    spy_new = pd.read_csv(_latest_rolling("spy"))
    spy_new["timestamp_et"] = pd.to_datetime(spy_new["timestamp_et"])
    spy_tail = spy_new[spy_new["timestamp_et"].dt.date > OLD_WINDOW_END]
    spy_df = (pd.concat([spy_old, spy_tail], ignore_index=True)
              .sort_values("timestamp_et").reset_index(drop=True))
    vix_old = pd.read_csv(OLD_VIX)
    vix_new = pd.read_csv(_latest_rolling("vix"))
    _vix_new_dates = pd.to_datetime(vix_new["timestamp_et"]).dt.date
    vix_tail = vix_new[_vix_new_dates > OLD_WINDOW_END].reset_index(drop=True)
    vix_df = pd.concat([vix_old, vix_tail], ignore_index=True)
    return spy_df, vix_df


def run_replay_supplement(lookback: int) -> dict:
    """Full-frame two-layer replay of the CURRENT LIVE core-Safe engine (both directions),
    then slice the newest `lookback` trading days. Machinery identical to
    g2_trendline_bypass_ab_2026_08_01.py (which is itself efr's) -- entry layer
    run_backtest(**SAFE_BASE_LIVE), exit layer walk_exit_manager under the RIBBON_RIDE
    registry shape, real cached OPRA only (missing contracts excluded AND counted)."""
    import time as _time
    import engine_fullhist_replay as efr  # noqa: E402  (tools/ on path)
    from lib.orchestrator import run_backtest  # noqa: E402
    from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
    from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
    import elite_bear_level_reject_gate_ab as eb  # noqa: E402
    from strategies import by_name as fleet_strategy_by_name  # noqa: E402

    t0 = _time.time()
    spy_df, vix_df = _load_extended_frame()
    all_days = sorted({d for d in spy_df["timestamp_et"].dt.date})
    frame_end = all_days[-1]
    window_days = all_days[-lookback:]
    log(f"replay frame {all_days[0]}..{frame_end} ({len(all_days)} trading days); "
        f"recent window {window_days[0]}..{window_days[-1]}")

    r = run_backtest(spy_df, vix_df, start_date=FULL_START, end_date=frame_end,
                     **efr.SAFE_BASE_LIVE)
    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    exit_shape = fleet_strategy_by_name("ribbon_ride").exit.to_dict()

    rows: list[dict] = []
    skipped = {"no_opra": 0, "no_spy_day": 0}
    for t in r.trades:
        if t.setup not in FAMILY_SETUPS:
            continue  # scope guard; run_backtest models only this family today
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            skipped["no_opra"] += 1
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            skipped["no_spy_day"] += 1
            continue
        entry_time_et = t.entry_time_et
        if hasattr(entry_time_et, "to_pydatetime"):
            entry_time_et = entry_time_et.to_pydatetime()
        if getattr(entry_time_et, "tzinfo", None) is not None:
            entry_time_et = entry_time_et.replace(tzinfo=None)
        trigger_level = float(t.rejection_level) if t.rejection_level else None
        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et,
            entry_premium=float(t.entry_premium), qty=int(t.qty), exit_shape=exit_shape,
            structure_stop_enabled=True, trigger_level=trigger_level, strategy="ribbon_ride",
            time_stop_et=efr.TIME_STOP_ET, opt_df=opt_df,
            ribbon_tick_df=efr.ribbon_tick_df_for(opt_df, ribbon_lookup),
            five_min_spy_df=day_spy,
        )
        rows.append({"date": edate.isoformat(), "side": t.side,
                     "pnl": round(float(res.dollar_pnl), 2)})

    def _slice_metrics(rs: list[dict]) -> dict:
        return cell_metrics([{"pnl": x["pnl"], "date": x["date"]} for x in rs])

    win_set = {d.isoformat() for d in window_days}
    out = {"frame": f"{all_days[0]}..{frame_end}",
           "recent_window": f"{window_days[0]}..{window_days[-1]}",
           "n_frame_trading_days": len(all_days),
           "excluded": skipped,
           "shape": "core Safe (SAFE_BASE_LIVE) -- no production-parity Bold replay "
                    "harness exists (engine_fullhist_replay.py scope disclosure)",
           "basis": "engine-sim (orchestrator entry + walk_exit_manager exit, real OPRA "
                    "only) -- NEVER blended into broker-fills n",
           "runtime_seconds": None,
           "recent": {}, "full": {}}
    for side in ("P", "C"):
        side_rows = [x for x in rows if x["side"] == side]
        out["full"][SIDE_NAME[side]] = _slice_metrics(side_rows)
        out["recent"][SIDE_NAME[side]] = _slice_metrics(
            [x for x in side_rows if x["date"] in win_set])
    out["runtime_seconds"] = round(_time.time() - t0, 1)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# top-level evaluation (memoized so the two registry rows share one computation)
# ─────────────────────────────────────────────────────────────────────────────

_MEMO: dict = {}


def evaluate(lookback: int = RECENCY_LOOKBACK_TRADING_DAYS,
             floor: int = CONFIRM_N_FLOOR,
             include_replay: bool = True,
             write_json: bool = True) -> dict:
    """Compute the full core-strategy recency block (all three strata + per-direction
    verdicts), persist OUT_JSON (the firm_brief source), and memoize per process."""
    memo_key = (lookback, floor, include_replay, dt.date.today().isoformat())
    if memo_key in _MEMO:
        return _MEMO[memo_key]

    # window = newest N trading days of the SPY frame calendar (broker fills need no OPRA
    # cache, so the window ends at the last cached RTH day, not the OPRA-cache last-date
    # recency_check's simulated edges are bound to -- basis disclosed in the JSON).
    import pandas as pd
    spy_new = pd.read_csv(_latest_rolling("spy"))
    tail_days = sorted({d for d in pd.to_datetime(spy_new["timestamp_et"]).dt.date})
    spy_old_days_needed = lookback - len(tail_days)
    if spy_old_days_needed > 0:
        spy_old = pd.read_csv(OLD_SPY)
        old_days = sorted({d for d in pd.to_datetime(spy_old["timestamp_et"]).dt.date})
        all_days = sorted(set(old_days) | set(tail_days))
    else:
        all_days = tail_days
    window_days = all_days[-lookback:]
    w_start, w_end = window_days[0], window_days[-1]

    fleet_ids = fleet_arm_ids()
    events, excl = group_fills(load_broker_rows(), w_start, w_end, fleet_ids)

    def cells_for(lane: str) -> dict:
        out = {}
        for side in ("P", "C"):
            out[SIDE_NAME[side]] = cell_metrics(
                [e for e in events if e["lane"] == lane and e["side"] == side])
        return out

    broker_core = cells_for("core")
    broker_core["by_account"] = {}
    for acct, label in CORE_ACCOUNTS.items():
        for side in ("P", "C"):
            cell = cell_metrics([e for e in events
                                 if e["account"] == acct and e["side"] == side])
            broker_core["by_account"][f"{label}/{SIDE_NAME[side]}"] = cell
    broker_fleet = cells_for("fleet")

    replay = None
    if include_replay:
        try:
            replay = run_replay_supplement(lookback)
        except Exception as exc:  # noqa: BLE001 -- supplement failure never kills the verdict
            log(f"WARN replay supplement failed: {exc}")
            replay = {"error": str(exc)}

    verdicts = {}
    for side in ("P", "C"):
        name = SIDE_NAME[side]
        cell = broker_core[name]
        verdict, reason = direction_verdict(cell, floor)
        supp = ""
        if replay and not replay.get("error"):
            rc = replay["recent"].get(name, {})
            if rc.get("n"):
                supp = (f"; replay supplement (Safe shape, engine-sim, DISCLOSED not "
                        f"blended): n={rc['n']} exp=${rc.get('exp_per_trade')}/tr recent")
            else:
                supp = "; replay supplement: no engine-sim entries in window"
        verdicts[name] = {
            "verdict": verdict,
            "n": cell.get("n", 0),
            "exp_per_trade": cell.get("exp_per_trade"),
            "reason": reason + supp,
            "headline": f"{name} {verdict} n={cell.get('n', 0)}",
            # CONCENTRATION DISCLOSURE (2026-08-23, additive fields only -- existing consumers
            # (monday_verify.py, firm_brief.py, gate_recency_report.py) read verdict/n/
            # exp_per_trade/reason/headline unchanged; these are new, so this cohort's
            # concentration numbers are visible on the same surface every reader already uses,
            # never buried in a field nobody reads):
            "drop_top3": cell.get("drop_top3"), "drop_bottom3": cell.get("drop_bottom3"),
            "drop_best2_days": cell.get("drop_best2_days"),
            "drop_worst2_days": cell.get("drop_worst2_days"),
            "top_day_share": cell.get("top_day_share"),
        }

    headline = ("core strategy recency: "
                + ", ".join(verdicts[s]["headline"] for s in ("bear", "bull"))
                + f" (floor {floor}, {lookback}d to {w_end})")

    block = {
        "instrument": "CORE-STRATEGY RECENCY (WS11 2026-08-01) -- the revalidation clock "
                      "for the strategy itself, per J's 2026-07-31 recency rule",
        "run_date": dt.date.today().isoformat(),
        "window": {"start": str(w_start), "end": str(w_end),
                   "n_trading_days": len(window_days),
                   "basis": "SPY 5m frame calendar (master + newest rolling); broker fills "
                            "need no OPRA cache so the window ends at the last cached RTH "
                            "day (differs from recency_check's OPRA-cache-last bound for "
                            "its SIMULATED edges -- disclosed, deliberate)"},
        "lookback_trading_days": lookback,
        "confirm_n_floor": floor,
        "strategy_family": sorted(FAMILY_SETUPS),
        "verdict_rules": {
            "GREEN": "broker-core exp/tr > 0 AND n >= floor",
            "RED": "broker-core exp/tr <= 0 AND n >= floor",
            "UNDERPOWERED": "0 < n < floor (no verdict manufactured; supplement quoted)",
            "NO_FILLS": "n == 0",
            "authority": "broker_core stratum ONLY -- fleet context and replay supplement "
                         "are disclosed alongside, never blended into n",
        },
        "verdicts": verdicts,
        "headline": headline,
        "strata": {
            "broker_core": broker_core,
            "broker_fleet_context": {
                **broker_fleet,
                "note": "same RIDE_THE_RIBBON family on the fleet arms (roster-driven ids) "
                        "-- real fills, different risk shells; CONTEXT only, not verdict",
            },
            "replay_supplement_safe_shape": replay,
        },
        "exclusions": excl,
        "DISCLOSURE": {
            "authority": "real broker fills (C1); per-trade expectancy, legs grouped per entry",
            "outage_context": OUTAGE_NOTE,
            "small_n": "window n is small by design; UNDERPOWERED is reported as such, "
                       "never dressed as a verdict",
            "no_bold_replay": "replay supplement is Safe-shape only (no Bold harness exists)",
            "report_only": "no order, no arming, no param edit",
        },
    }
    if write_json:
        try:
            OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
            OUT_JSON.write_text(json.dumps(block, indent=2, default=str), encoding="utf-8")
            log(f"wrote {OUT_JSON}")
        except OSError as exc:
            log(f"WARN could not write {OUT_JSON}: {exc}")
    _MEMO[memo_key] = block
    return block


# ─────────────────────────────────────────────────────────────────────────────
# gate-registry integration (called by gate_expiry_check.check_gate, category
# "core_strategy") -- returns a pnl_check-shaped dict in the checker's vocabulary
# ─────────────────────────────────────────────────────────────────────────────

_REGISTRY_DIRECTION = {"core_strategy_bear": "bear", "core_strategy_bull": "bull"}
# checker-surface vocabulary: RED flows to the newly-RED STATUS flag; UNDERPOWERED maps
# to YELLOW (watch, not actionable); NO_FILLS to INSUFFICIENT_DATA (so an evidence-stale
# no-data row surfaces as STALE_UNVERIFIED exactly like any other gate). GREEN_CONCENTRATED/
# RED_CONCENTRATED (2026-08-23) pass straight through the checker vocabulary unchanged --
# check_gate's overall-mapping (gate_expiry_check.py) already gives both their own `overall`
# branch, distinct from the literal string "RED" compute_newly_red/flag_status_md key off, so
# neither can ever trip the STATUS.md "## Known broken" alarm.
_VERDICT_TO_CHECKER = {"GREEN": "GREEN", "RED": "RED",
                       "UNDERPOWERED": "YELLOW", "NO_FILLS": "INSUFFICIENT_DATA",
                       "GREEN_CONCENTRATED": "GREEN_CONCENTRATED",
                       "RED_CONCENTRATED": "RED_CONCENTRATED"}


def evaluate_for_registry(gate: dict, floor: int = CONFIRM_N_FLOOR,
                          lookback: int = RECENCY_LOOKBACK_TRADING_DAYS) -> dict:
    """One registry row (core_strategy_bear / core_strategy_bull) -> the pnl_check block
    gate_expiry_check.check_gate embeds. Shares one evaluate() computation across both
    rows via the module memo. Fail-open is the CALLER's job (check_gate already wraps)."""
    direction = _REGISTRY_DIRECTION.get(gate.get("id", ""))
    if direction is None:
        return {"verdict": "NOT_MEASURED",
                "reason": f"unknown core_strategy registry id {gate.get('id')!r}"}
    block = evaluate(lookback=lookback, floor=floor)
    v = block["verdicts"][direction]
    checker_verdict = _VERDICT_TO_CHECKER.get(v["verdict"], "YELLOW")
    reason = (f"CORE STRATEGY {direction.upper()} recency {v['verdict']}: {v['reason']} "
              f"[semantics: RED here = the strategy ITSELF is losing on recent real fills, "
              f"not a gate costing money]")
    return {
        "verdict": checker_verdict,
        "core_strategy_verdict": v["verdict"],
        "reason": reason,
        "headline": v["headline"],
        "window": block["window"],
        "broker_core": block["strata"]["broker_core"].get(direction),
        "replay_supplement": (block["strata"]["replay_supplement_safe_shape"] or {}).get(
            "recent", {}).get(direction),
        "detail": str(OUT_JSON.relative_to(ROOT)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Core-strategy recency (WS11 revalidation clock)")
    ap.add_argument("--lookback", type=int, default=RECENCY_LOOKBACK_TRADING_DAYS)
    ap.add_argument("--floor", type=int, default=CONFIRM_N_FLOOR)
    ap.add_argument("--no-replay", action="store_true",
                    help="skip the ~2min engine replay supplement (broker fills only)")
    args = ap.parse_args()
    block = evaluate(lookback=args.lookback, floor=args.floor,
                     include_replay=not args.no_replay)
    print("\n=== CORE-STRATEGY RECENCY ===")
    print(block["headline"])
    for name in ("bear", "bull"):
        v = block["verdicts"][name]
        print(f"  {name:5s} -> {v['verdict']:12s} {v['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
