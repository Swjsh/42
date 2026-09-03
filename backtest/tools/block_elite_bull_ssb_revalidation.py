"""block_elite_bull_ssb_revalidation.py -- RELAUNCH of the block_elite_bull SS-B revalidation
a PC reboot killed on 2026-07-09. Executes the FROZEN pre-registration at
analysis/recommendations/block-elite-bull-ssb-preregistration.json exactly (see that file for
the full cohort/method/pass-bar spec) -- no re-picks after seeing results.

WHAT THIS DOES
--------------
1. Re-runs bull_unblock_replay_probe.py's own A/B (block_elite_bull True vs False, real OPRA
   fills) over its ORIGINAL window (2026-05-21..2026-06-30) to (a) reproduce its recorded n=7 /
   -$241.26 finding as an old-exit PARITY CHECK, and (b) recover the 7 trades' entry_time_et /
   strike / entry_premium / rejection_level in-memory (the saved JSON only has date/strike/pnl).
2. Mines automation/state/core-decisions.jsonl (safe account) for every
   SKIP_ELITE_BULL_LEVEL_RECLAIM tick since 2026-07-01, dedupes consecutive ticks into signal
   EVENTS, excludes stale-prior-session echoes (cross-account SKIP_STALE_TRIGGER corroboration),
   and recovers each event's strike/premium/trigger-level.
3. Separately mines the SUPER-tier bull population (never touched by block_elite_bull, since the
   gate only checks tier=='ELITE') over the full window as a disclosure-only comparison cohort.
4. Replays every event under TWO exit shapes via structure_stop_study.py's own machinery
   (replay_structure_aware + structure_stop_signal_time, imported unmodified): OLD (the shipped
   -20/+150/sell80/fixed CONTROL shape) and SS-B (cat -50% + tp1 100%/sell66 + trail15%).
5. Grades the frozen 4-condition pass bar and writes the result. If it clears, stages (does NOT
   apply) an unblock proposal.

Rail-4 CLEAR: analysis only. Touches NO trading-path file. Reads core-decisions.jsonl (read-only)
and live Alpaca OPRA option-bar data (read-only market data, $0, explicitly cleared this session).

Run: backtest/.venv/Scripts/python.exe backtest/tools/block_elite_bull_ssb_revalidation.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time as _time_mod
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import pandas as pd  # noqa: E402

import t4_exit_matrix as t4                       # noqa: E402  (_shape, CONTROL)
import tw8_level_context as lc                     # noqa: E402  (load_spy_full, frozen_level_set_for_date)
import exit_shape_parity_study as esp              # noqa: E402  (fetch_option_bars)
from structure_stop_study import (                 # noqa: E402
    SS_B_SHAPE, replay_structure_aware, structure_stop_signal_time, norm_bars_from_esp,
)
from lib.orchestrator import run_backtest          # noqa: E402
from lib.filters import detect_level_reclaim       # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from autoresearch.bull_unblock_replay_probe import (  # noqa: E402
    _bull_cfg, START as ORIG_START, END as ORIG_END, SPY as ORIG_SPY_REL, VIX as ORIG_VIX_REL,
)

PREREG = REPO / "analysis" / "recommendations" / "block-elite-bull-ssb-preregistration.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "block-elite-bull-ssb-revalidation.json"
PROPOSAL_JSON = REPO / "analysis" / "recommendations" / "block-elite-bull-ssb-unblock-proposal.json"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"

EXTENSION_START = dt.date(2026, 7, 1)
EXTENSION_END = dt.date(2026, 7, 10)
COMPARISON_START = dt.date(2026, 5, 21)
COMPARISON_END = dt.date(2026, 7, 10)
LEVEL_HISTORY_START = dt.date(2026, 5, 19)   # earliest date covered by a cached CSV that also
                                              # reaches EXTENSION_END (2026-07-10); still gives
                                              # 6+ weeks of level-formation lookback before the
                                              # extension window opens (07-01) -- well past t5's
                                              # own >=10-day warmup convention. NOT a cohort-
                                              # definition change (see run-log disclosure).

DEDUPE_GAP_MINUTES = 5
STRIKE_OFFSET_BULL = -2
PARITY_TOLERANCE_DOLLARS = 1.00
N_EVENTS_FLOOR = 12
RECORDED_ORIGINAL_NET_PNL = -241.26
QTY_ELITE = 10
QTY_SUPER = 15
TIME_STOP_ET = dt.time(15, 50)   # exit_manager.TIME_STOP_ET convention (live-decision-log-sourced signals)

CONTROL_SHAPE = t4._shape(t4.CONTROL)   # -20/+150/sell80/fixed -- the shipped shape

# Bumped 2026-09-03: the prereg's `status` transitioned FROZEN_PENDING_RUN -> RUN_COMPLETE_KEEP
# and a `run_2026_09_03` disclosure note was appended (see that key's `content_hash_note`) --
# a disclosed status-lifecycle edit closing a bookkeeping gap (this module's own confirmatory
# run had ALREADY completed 2026-07-10T16:10:35 with verdict KEEP -- see
# analysis/recommendations/block-elite-bull-ssb-revalidation.json -- but main() never writes
# back to the prereg's status field, so it was stuck reading FROZEN_PENDING_RUN for 2 months).
# NOT a re-pick of cohort_definition/dedupe_rule/stale_echo_exclusion/strike_convention/
# entry_premium_recovery/trigger_level_recovery/exit_shapes/pass_bar, all of which are
# byte-identical to the 2026-07-10 freeze. Prior values, oldest first (still valid for any
# artifact/log referencing an earlier prereg state): "e9933be0e0ed453e" (freeze),
# "2a05d565370fbf6a" (intermediate 2026-09-03 edit, superseded same session).
EXPECTED_PREREG_SHA16 = "9182d6f9e43b62ab"
EXPECTED_PREREG_VERSION = 1


# =============================================================================
# PRE-FLIGHT -- prereg hash pin
# =============================================================================
def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def preflight() -> dict:
    """Recompute the frozen pre-registration's content hash and compare against both the
    hardcoded expectation in this file AND what is currently stored on disk. Any mismatch means
    the pre-registration was edited after freezing (or this runner drifted from it) -- FAIL LOUD,
    never silently proceed on a re-picked spec."""
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    stored = preg.get("content_sha256_16")
    preg_no_hash = {k: v for k, v in preg.items() if k != "content_sha256_16"}
    recomputed = _content_hash(preg_no_hash)
    return {
        "prereg_version": preg.get("version"),
        "prereg_version_ok": preg.get("version") == EXPECTED_PREREG_VERSION,
        "prereg_sha256_16_recomputed": recomputed,
        "prereg_sha256_16_stored": stored,
        "prereg_hash_ok": recomputed == EXPECTED_PREREG_SHA16 and recomputed == stored,
    }


# =============================================================================
# PURE FUNCTIONS -- dedupe, stale-echo filter, strike/parity/drop-top1 (unit-tested, no network)
# =============================================================================
def dedupe_into_events(rows: list[dict], gap_minutes: int = DEDUPE_GAP_MINUTES) -> list[dict]:
    """Group ts_et-sorted decision rows into signal EVENTS. RULE (preregistration.dedupe_rule):
    a row joins the current event if the gap since the previous row's ts_et is <= gap_minutes;
    a larger gap starts a new event. Each event's representative fields come from its FIRST row."""
    if not rows:
        return []
    ordered = sorted(rows, key=lambda r: r["ts_et"])
    groups: list[list[dict]] = [[ordered[0]]]
    for prev, row in zip(ordered, ordered[1:]):
        prev_ts = dt.datetime.fromisoformat(prev["ts_et"])
        this_ts = dt.datetime.fromisoformat(row["ts_et"])
        gap_min = (this_ts - prev_ts).total_seconds() / 60.0
        if gap_min <= gap_minutes:
            groups[-1].append(row)
        else:
            groups.append([row])
    return [
        {"entry_row": grp[0], "n_ticks": len(grp), "first_ts": grp[0]["ts_et"], "last_ts": grp[-1]["ts_et"]}
        for grp in groups
    ]


def is_possible_stale_echo(entry_row: dict, other_account_rows: list[dict]) -> tuple[bool, str]:
    """Cross-account corroboration (preregistration.stale_echo_exclusion): if the OTHER account
    shows SKIP_STALE_TRIGGER within +/-90s of this event's first tick, the underlying bar was a
    prior-session echo carried into today's open ticks, not a live signal."""
    ts = dt.datetime.fromisoformat(entry_row["ts_et"])
    for other in other_account_rows:
        other_ts_str = other.get("ts_et")
        if not other_ts_str:
            continue
        other_ts = dt.datetime.fromisoformat(other_ts_str)
        if abs((other_ts - ts).total_seconds()) <= 90 and other.get("action") == "SKIP_STALE_TRIGGER":
            return True, f"cross-account SKIP_STALE_TRIGGER at {other_ts_str}"
    return False, ""


def is_open_adjacent(entry_row: dict) -> bool:
    """09:35:00-09:41:00 ET: the documented at-open stale-bar-carryover risk window
    (_stale_trigger_bar's own docstring: 'at the open ticks the 2nd-to-last fetched bar is
    still the PRIOR day's bar')."""
    ts = dt.datetime.fromisoformat(entry_row["ts_et"])
    t = ts.time()
    return dt.time(9, 35) <= t < dt.time(9, 41)


def strike_for_call(spy_spot: float, strike_offset: int = STRIKE_OFFSET_BULL) -> int:
    """simulator_real.py:372-376 production convention (NOT t4_exit_matrix's OTM-2 convention --
    see the preregistration's strike_convention.sim_accuracy_check_OP16): atm = round(spot);
    strike = atm + strike_offset for calls."""
    atm = int(round(spy_spot))
    return atm + strike_offset


def parity_within_tolerance(actual: float, expected: float = RECORDED_ORIGINAL_NET_PNL,
                             tolerance_dollars: float = PARITY_TOLERANCE_DOLLARS) -> bool:
    return abs(actual - expected) <= tolerance_dollars


def drop_top1(trade_pnls: list[float]) -> tuple[float, bool]:
    """Remove ONE largest-magnitude WINNING trade; return (remainder_total, remainder_positive).
    No winners -> nothing to drop, remainder = the unchanged total."""
    if not trade_pnls:
        return 0.0, False
    winners = [p for p in trade_pnls if p > 0]
    if not winners:
        total = sum(trade_pnls)
        return round(total, 2), total > 0
    remainder = sum(trade_pnls) - max(winners)
    return round(remainder, 2), remainder > 0


def _is_super_tier(row: dict) -> bool:
    """engine_cli.py:481-484 _derive_tier, mirrored: (confluence AND ribbon_flip) OR
    len(triggers)>=3 => SUPER. block_elite_bull (gates.py:271) checks tier=='ELITE' only, so
    SUPER is structurally never touched by the gate under test."""
    trigs = row.get("triggers") or []
    return ("confluence" in trigs and "ribbon_flip" in trigs) or len(trigs) >= 3


# =============================================================================
# DECISION-LOG I/O
# =============================================================================
def load_core_decisions() -> list[dict]:
    rows = []
    with CORE_DECISIONS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def _rows_in_window(rows: list[dict], account: str, start: dt.date, end: dt.date) -> list[dict]:
    out = []
    for r in rows:
        ts = r.get("ts_et")
        if not ts or r.get("account") != account:
            continue
        try:
            d = dt.date.fromisoformat(ts[:10])
        except ValueError:
            continue
        if start <= d <= end:
            out.append(r)
    return out


def _apply_stale_filter(events: list[dict], other_account_rows: list[dict]) -> tuple[list[dict], dict]:
    kept, excluded, flagged = [], [], []
    for ev in events:
        stale, reason = is_possible_stale_echo(ev["entry_row"], other_account_rows)
        if stale:
            excluded.append({**ev, "exclusion_reason": reason})
            continue
        if is_open_adjacent(ev["entry_row"]):
            ev = {**ev, "elevated_stale_risk": True}
            flagged.append(ev)
        kept.append(ev)
    stats = {
        "n_events_total": len(events), "n_excluded_stale_echo": len(excluded),
        "n_flagged_open_adjacent": len(flagged), "n_kept": len(kept),
        "excluded_detail": [{"first_ts": e["first_ts"], "reason": e["exclusion_reason"]} for e in excluded],
        "flagged_detail": [e["first_ts"] for e in flagged],
    }
    return kept, stats


def mine_elite_extension_events(all_rows: list[dict]) -> tuple[list[dict], dict]:
    safe_rows = _rows_in_window(all_rows, "safe", EXTENSION_START, EXTENSION_END)
    elite_rows = [r for r in safe_rows if r.get("action") == "SKIP_ELITE_BULL_LEVEL_RECLAIM"]
    events = dedupe_into_events(elite_rows, DEDUPE_GAP_MINUTES)
    bold_rows = _rows_in_window(all_rows, "bold", EXTENSION_START, EXTENSION_END)
    kept, stats = _apply_stale_filter(events, bold_rows)
    stats["n_raw_ticks"] = len(elite_rows)
    # sensitivity disclosure (preregistration.dedupe_rule.sensitivity_disclosure)
    stats["n_events_at_2min"] = len(dedupe_into_events(elite_rows, 2))
    stats["n_events_at_15min"] = len(dedupe_into_events(elite_rows, 15))
    return kept, stats


def mine_super_comparison_events(all_rows: list[dict]) -> tuple[list[dict], dict]:
    safe_rows = _rows_in_window(all_rows, "safe", COMPARISON_START, COMPARISON_END)
    super_rows = [r for r in safe_rows if r.get("side") == "C" and _is_super_tier(r)]
    events = dedupe_into_events(super_rows, DEDUPE_GAP_MINUTES)
    bold_rows = _rows_in_window(all_rows, "bold", COMPARISON_START, COMPARISON_END)
    kept, stats = _apply_stale_filter(events, bold_rows)
    # additional exclusion: signals that could never have been live trades regardless of
    # block_elite_bull (mechanically un-tradeable), and same-account stale echoes.
    further_kept, further_excluded = [], []
    for ev in kept:
        act = ev["entry_row"].get("action")
        if act == "SKIP_STALE_TRIGGER":
            further_excluded.append({**ev, "exclusion_reason": "own-account SKIP_STALE_TRIGGER"})
        elif act == "SKIP_LATE_ENTRY":
            further_excluded.append({**ev, "exclusion_reason": "past 15:00 entry ceiling -- untradeable regardless of block_elite_bull"})
        else:
            further_kept.append(ev)
    stats["n_raw_ticks"] = len(super_rows)
    stats["n_further_excluded_mechanical"] = len(further_excluded)
    stats["further_excluded_detail"] = [{"first_ts": e["first_ts"], "reason": e["exclusion_reason"]} for e in further_excluded]
    stats["n_kept"] = len(further_kept)
    return further_kept, stats


# =============================================================================
# TRIGGER-LEVEL RECOVERY (tw8_level_context convention)
# =============================================================================
_level_cache: dict = {}
_spy_full_cache: Optional[pd.DataFrame] = None


def _spy_full() -> pd.DataFrame:
    global _spy_full_cache
    if _spy_full_cache is None:
        _spy_full_cache = lc.load_spy_full(LEVEL_HISTORY_START, EXTENSION_END)
    return _spy_full_cache


def recover_trigger_level(entry_row: dict) -> tuple[Optional[float], str]:
    """Use the logged trigger_level_exact when present (only populated from ~2026-07-10 11:51 ET
    onward); otherwise recover it via the SAME detector the live engine used to fire the signal
    (lib.filters.detect_level_reclaim against tw8_level_context's frozen per-day level set) --
    the exact-match method, since the decision log gives an exact entry spot/time (unlike real
    fills, which carry no entry_spot label and need structure_stop_study's backward-scan
    heuristic instead)."""
    logged = entry_row.get("trigger_level_exact")
    if logged is not None:
        return float(logged), "logged"
    ts_et = dt.datetime.fromisoformat(entry_row["ts_et"])
    date = ts_et.date()
    spy_full = _spy_full()
    level_set = lc.frozen_level_set_for_date(spy_full, date, _level_cache)
    if level_set is None:
        return None, "no_level_set"
    day_bars = spy_full[(spy_full["date"] == date) & (spy_full["timestamp_et"] <= ts_et)].tail(3)
    for idx in list(day_bars.index)[::-1]:
        bar = spy_full.loc[idx]
        lvl = detect_level_reclaim(bar, level_set.active)
        if lvl is not None:
            return lvl, "recovered_exact_match"
    return None, "no_trigger_bar_found"


# =============================================================================
# ENTRY PREMIUM + OPTION-BAR RECOVERY
# =============================================================================
def _cached_bars_as_esp_shape(symbol: str) -> Optional[list[dict]]:
    """Adapt a locally-cached 5-min CSV (timestamp_et,open,high,low,close,...) into the
    {"t": iso_utc, "o","h","l","c"} shape esp/norm_bars_from_esp expect, avoiding a redundant
    live fetch when the contract is already on disk."""
    df = load_contract_bars(symbol)
    if df is None or df.empty:
        return None
    out = []
    for _, r in df.iterrows():
        ts = r["timestamp_et"]
        if getattr(ts, "tzinfo", None) is None:
            ts = ts.tz_localize("America/New_York")
        t_utc = ts.tz_convert("UTC")
        out.append({"t": t_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "o": float(r["open"]), "h": float(r["high"]),
                    "l": float(r["low"]), "c": float(r["close"])})
    return out or None


def fetch_bars_cache_then_live(symbol: str, date_et: str) -> tuple[list[dict], str]:
    cached = _cached_bars_as_esp_shape(symbol)
    if cached:
        return cached, "cache"
    live = esp.fetch_option_bars(symbol, date_et)
    _time_mod.sleep(0.12)
    return live, "live" if live else "none"


def prepare_event(entry_row: dict, qty: int) -> Optional[dict]:
    """Recover strike/trigger-level/option-bars for ONE mined event. Returns None (dropped,
    counted by the caller) if option bars cannot be recovered -- never imputed (C7)."""
    ts_et = dt.datetime.fromisoformat(entry_row["ts_et"])
    date = ts_et.date()
    spy_spot = entry_row.get("spy")
    if spy_spot is None:
        return None
    strike = strike_for_call(float(spy_spot))
    trigger_level, level_status = recover_trigger_level(entry_row)
    symbol = option_symbol(date, strike, "C")
    bars, bar_source = fetch_bars_cache_then_live(symbol, date.isoformat())
    if not bars:
        return None
    norm_bars = norm_bars_from_esp(bars, entry_ts_utc=None)
    norm_bars = [b for b in norm_bars if b.dt >= ts_et]
    if not norm_bars:
        return None
    entry_premium = norm_bars[0].o
    if entry_premium <= 0:
        return None
    spy_full = _spy_full()
    spy_lifetime = spy_full[(spy_full["date"] == date) & (spy_full["timestamp_et"] >= ts_et)]
    return {
        "date": date.isoformat(), "entry_ts_et": entry_row["ts_et"], "symbol": symbol,
        "strike": strike, "side": "C", "qty": qty, "entry_premium": round(entry_premium, 4),
        "trigger_level": trigger_level, "trigger_level_status": level_status,
        "bar_source": bar_source, "norm_bars": norm_bars, "spy_lifetime": spy_lifetime,
        "elevated_stale_risk": bool(entry_row.get("_elevated_stale_risk", False)),
    }


# =============================================================================
# REPLAY (structure_stop_study machinery, reused unmodified)
# =============================================================================
def replay_prepared_event(prepared: dict, shape: dict, use_structure: bool) -> dict:
    ss_time = None
    if use_structure:
        ss_time = structure_stop_signal_time(prepared["spy_lifetime"], prepared["side"],
                                              prepared["trigger_level"], buffer=0.0)
    r = replay_structure_aware(prepared["entry_premium"], prepared["side"], prepared["qty"],
                               prepared["norm_bars"], ss_time, shape, TIME_STOP_ET)
    return {**r, "date": prepared["date"], "entry_ts_et": prepared["entry_ts_et"],
            "strike": prepared["strike"], "entry_premium": prepared["entry_premium"],
            "trigger_level": prepared["trigger_level"], "bar_source": prepared["bar_source"]}


# =============================================================================
# PART A -- re-run the original probe's A/B for parity + in-memory trade recovery
# =============================================================================
def _et_naive(ts) -> dt.datetime:
    p = pd.Timestamp(ts)
    if p.tzinfo is not None:
        p = p.tz_localize(None)
    return p.to_pydatetime()


def rerun_original_probe() -> dict:
    """Re-runs bull_unblock_replay_probe.py's EXACT A/B methodology (same _bull_cfg, same
    window/data files) so the 7 added-bull Trade objects are available in-memory (the saved JSON
    only persists date/strike/pnl, not entry_time_et/entry_premium/rejection_level)."""
    spy = pd.read_csv(REPO / "backtest" / ORIG_SPY_REL)
    vix = pd.read_csv(REPO / "backtest" / ORIG_VIX_REL)
    r_base = run_backtest(spy, vix, start_date=ORIG_START, end_date=ORIG_END, **_bull_cfg(True))
    r_unbl = run_backtest(spy, vix, start_date=ORIG_START, end_date=ORIG_END, **_bull_cfg(False))

    def key(t):
        ts = _et_naive(t.entry_time_et)
        return (ts, t.side, round(float(t.strike), 2))

    base_keys = {key(t) for t in r_base.trades}
    added_bulls = [t for t in r_unbl.trades if key(t) not in base_keys and t.side == "C"]
    net_pnl = round(sum(t.dollar_pnl for t in added_bulls), 2)

    prepared = []
    for t in added_bulls:
        ts_et = _et_naive(t.entry_time_et)
        date = ts_et.date()
        symbol = option_symbol(date, int(round(t.strike)), "C")
        bars, bar_source = fetch_bars_cache_then_live(symbol, date.isoformat())
        if not bars:
            continue
        norm_bars = [b for b in norm_bars_from_esp(bars, entry_ts_utc=None) if b.dt >= ts_et]
        if not norm_bars:
            continue
        spy_full = _spy_full()
        spy_lifetime = spy_full[(spy_full["date"] == date) & (spy_full["timestamp_et"] >= ts_et)]
        prepared.append({
            "date": date.isoformat(), "entry_ts_et": ts_et.isoformat(), "symbol": symbol,
            "strike": int(round(t.strike)), "side": "C", "qty": QTY_ELITE,
            "entry_premium": round(float(t.entry_premium), 4),
            "trigger_level": float(t.rejection_level) if t.rejection_level is not None else None,
            "trigger_level_status": "from_original_trade_object",
            "bar_source": bar_source, "norm_bars": norm_bars, "spy_lifetime": spy_lifetime,
            "elevated_stale_risk": False, "original_dollar_pnl_old_engine": round(t.dollar_pnl, 2),
        })

    return {
        "n_added_bulls": len(added_bulls), "n_prepared_for_ssb": len(prepared),
        "n_missing_bars": len(added_bulls) - len(prepared),
        "reproduced_net_pnl_old_exit": net_pnl,
        "parity_ok": parity_within_tolerance(net_pnl),
        "prepared_events": prepared,
    }


# =============================================================================
# STATS
# =============================================================================
def cohort_stats(replays: list[dict]) -> dict:
    pnls = [r["pnl"] for r in replays]
    n = len(pnls)
    total = round(sum(pnls), 2)
    wins = sum(1 for p in pnls if p > 0)
    remainder, remainder_positive = drop_top1(pnls)
    n_structure_fired = sum(1 for r in replays if r.get("structure_fired"))
    by_day: dict = {}
    for r in replays:
        by_day[r["date"]] = by_day.get(r["date"], 0.0) + r["pnl"]
    return {
        "n": n, "wr": round(wins / n, 4) if n else 0.0, "total_pnl": total,
        "expectancy_per_trade": round(total / n, 2) if n else 0.0,
        "n_structure_fired": n_structure_fired,
        "drop_top1_remainder": remainder, "drop_top1_positive": remainder_positive,
        "by_day_pnl": {k: round(v, 2) for k, v in sorted(by_day.items())},
        "trades": [{"date": r["date"], "entry_ts_et": r["entry_ts_et"], "strike": r["strike"],
                    "pnl": r["pnl"], "structure_fired": r.get("structure_fired", False)}
                   for r in sorted(replays, key=lambda x: x["entry_ts_et"])],
    }


# =============================================================================
# MAIN
# =============================================================================
def main() -> int:
    pf = preflight()
    print(f"[ssb-revalidation] preflight: {pf}", flush=True)
    if not pf["prereg_hash_ok"] or not pf["prereg_version_ok"]:
        print("[ssb-revalidation] PREFLIGHT FAILED -- prereg hash/version mismatch, aborting "
              "(no re-picks, no stale-hash runs)", file=sys.stderr)
        return 1

    print("[ssb-revalidation] part A: re-running the original probe A/B "
          f"({ORIG_START}..{ORIG_END}) for parity + trade recovery...", flush=True)
    part_a = rerun_original_probe()
    print(f"[ssb-revalidation] part A: n_added_bulls={part_a['n_added_bulls']} "
          f"reproduced_net_pnl={part_a['reproduced_net_pnl_old_exit']} "
          f"(recorded {RECORDED_ORIGINAL_NET_PNL}) parity_ok={part_a['parity_ok']}", flush=True)

    print("[ssb-revalidation] loading core-decisions.jsonl + mining extension/comparison events...",
          flush=True)
    all_rows = load_core_decisions()
    elite_ext_events, elite_ext_stats = mine_elite_extension_events(all_rows)
    super_events, super_stats = mine_super_comparison_events(all_rows)
    print(f"[ssb-revalidation] elite extension: {elite_ext_stats}", flush=True)
    print(f"[ssb-revalidation] super comparison: {super_stats}", flush=True)

    print("[ssb-revalidation] recovering strike/premium/bars for extension events "
          "(network reads, real OPRA)...", flush=True)
    elite_ext_prepared, elite_ext_missing = [], 0
    for ev in elite_ext_events:
        row = dict(ev["entry_row"])
        row["_elevated_stale_risk"] = ev.get("elevated_stale_risk", False)
        p = prepare_event(row, QTY_ELITE)
        if p is None:
            elite_ext_missing += 1
        else:
            elite_ext_prepared.append(p)

    super_prepared, super_missing = [], 0
    for ev in super_events:
        row = dict(ev["entry_row"])
        p = prepare_event(row, QTY_SUPER)
        if p is None:
            super_missing += 1
        else:
            super_prepared.append(p)

    print(f"[ssb-revalidation] extension prepared={len(elite_ext_prepared)} "
          f"missing_bars={elite_ext_missing}; super prepared={len(super_prepared)} "
          f"missing_bars={super_missing}", flush=True)

    # -- replay everything under both shapes --------------------------------------------------
    elite_all_prepared = part_a["prepared_events"] + elite_ext_prepared
    elite_old = [replay_prepared_event(p, CONTROL_SHAPE, use_structure=False) for p in elite_all_prepared]
    elite_ssb = [replay_prepared_event(p, SS_B_SHAPE, use_structure=True) for p in elite_all_prepared]
    super_old = [replay_prepared_event(p, CONTROL_SHAPE, use_structure=False) for p in super_prepared]
    super_ssb = [replay_prepared_event(p, SS_B_SHAPE, use_structure=True) for p in super_prepared]

    elite_old_stats = cohort_stats(elite_old)
    elite_ssb_stats = cohort_stats(elite_ssb)
    super_old_stats = cohort_stats(super_old)
    super_ssb_stats = cohort_stats(super_ssb)

    # flagged-excluded sensitivity: recompute with open-adjacent-flagged events also dropped
    elite_ssb_no_flagged = [r for r, p in zip(elite_ssb, elite_all_prepared)
                            if not p.get("elevated_stale_risk")]
    elite_ssb_stats_conservative = cohort_stats(elite_ssb_no_flagged)

    n_events_total = len(elite_all_prepared)

    # -- PASS BAR -------------------------------------------------------------------------------
    cond1 = elite_ssb_stats["total_pnl"] > 0
    cond2 = elite_ssb_stats["drop_top1_positive"]
    cond3 = part_a["parity_ok"]
    cond4 = n_events_total >= N_EVENTS_FLOOR
    all_pass = cond1 and cond2 and cond3 and cond4
    verdict = "UNBLOCK_PROPOSE" if all_pass else "KEEP"

    too_good_hunt = None
    if all_pass:
        delta_vs_old = elite_ssb_stats["total_pnl"] - elite_old_stats["total_pnl"]
        top3_days = sorted(elite_ssb_stats["by_day_pnl"].values(), reverse=True)[:3]
        top3_pct = (sum(top3_days) / elite_ssb_stats["total_pnl"] * 100.0) if elite_ssb_stats["total_pnl"] else None
        too_good_hunt = {
            "triggered": True,
            "delta_ssb_vs_old_same_cohort": round(delta_vs_old, 2),
            "top3_day_pct_of_net": round(top3_pct, 1) if top3_pct is not None else None,
            "conservative_no_flagged_total": elite_ssb_stats_conservative["total_pnl"],
            "conservative_still_positive": elite_ssb_stats_conservative["total_pnl"] > 0,
            "n_structure_fired_of_n": f"{elite_ssb_stats['n_structure_fired']}/{elite_ssb_stats['n']}",
            "note": "Reported per the preregistration's fable_too_good_discipline clause -- "
                    "a PROPOSE verdict on a gate previously ratified KEEP needs this disclosure "
                    "read before acting on it, not after.",
        }

    out = {
        "_doc": "block_elite_bull SS-B revalidation -- RELAUNCH of the 2026-07-09 PC-reboot-killed "
                "study, executed against the frozen block-elite-bull-ssb-preregistration.json. "
                "ANALYSIS ONLY.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "preflight": pf,
        "part_a_original_rerun": {k: v for k, v in part_a.items() if k != "prepared_events"},
        "elite_extension_mining": elite_ext_stats,
        "super_comparison_mining": super_stats,
        "elite_cohort": {
            "n_events_total": n_events_total,
            "OLD": elite_old_stats, "SS_B": elite_ssb_stats,
            "SS_B_excluding_open_adjacent_flagged": elite_ssb_stats_conservative,
        },
        "super_comparison_cohort_DISCLOSURE_ONLY": {
            "n_events_total": len(super_prepared),
            "OLD": super_old_stats, "SS_B": super_ssb_stats,
            "note": "NOT gated by its own pass bar (preregistration.cohort_definition."
                    "super_comparison_cohort.role). Known-thin by design.",
        },
        "pass_bar": {
            "condition_1_ssb_total_positive": cond1,
            "condition_2_ssb_drop_top1_positive": cond2,
            "condition_3_old_exit_parity": cond3,
            "condition_4_n_events_floor_12": cond4,
            "all_pass": all_pass,
            "verdict": verdict,
        },
        "too_good_discipline": too_good_hunt,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[ssb-revalidation] wrote {OUT_JSON}", flush=True)
    print(f"[ssb-revalidation] VERDICT: {verdict} "
          f"(cond1={cond1} cond2={cond2} cond3={cond3} cond4={cond4}, n={n_events_total})", flush=True)

    if all_pass:
        proposal = {
            "_doc": "STAGED unblock proposal for block_elite_bull -- NOT applied. Requires J "
                    "review + a live guard test before any params.json edit (OP-0 fork: a "
                    "reversal of a previously-ratified KEEP is exactly the kind of genuine-fork "
                    "call that gets flagged, not auto-shipped).",
            "generated_at": dt.datetime.now().isoformat(),
            "source_study": str(OUT_JSON.relative_to(REPO)).replace("\\", "/"),
            "proposed_change": {
                "file": "automation/state/params.json",
                "key": "block_elite_bull",
                "current_value": True,
                "proposed_value": False,
                "scope": "Safe (Gamma-Safe-2) ONLY -- this study never touched Bold's VIX band [15,18)",
            },
            "prerequisite": "SS-B exit shape (structure stop + cat-50 + tp1 100%/sell66 + trail15) "
                            "must itself be shipped to production BEFORE this unblock is safe to "
                            "apply -- unblocking under the OLD exit shape re-exposes the original "
                            "-$241.26 loser cohort this gate was built to remove.",
            "guard_test_to_write_before_applying": "backtest/tests/test_block_elite_bull_ssb_revalidation.py::test_committed_revalidation_verdict",
            "revert": "set block_elite_bull back to true in automation/state/params.json",
        }
        PROPOSAL_JSON.write_text(json.dumps(proposal, indent=2), encoding="utf-8")
        print(f"[ssb-revalidation] STAGED proposal written to {PROPOSAL_JSON} (NOT applied)", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
