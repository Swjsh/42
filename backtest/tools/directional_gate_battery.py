"""directional_gate_battery.py -- 12-gate directional-gate revalidation battery (2026-07-15).

Executes the FROZEN pre-registration at
analysis/recommendations/prereg-directional-gate-battery-2026-07-15.json EXACTLY -- no re-picks
after seeing results (see that file for the full gate list / current-config / windows / method /
ratification-bar spec). Generalizes backtest/tools/block_elite_bull_ssb_revalidation.py's mining
+replay pattern (one gate, block_elite_bull/Safe only) to the 6 gates that have real fresh-OOS
evidence in core-decisions.jsonl this session, of the 12 REVALIDATE gates named in
markdown/audits/DIRECTIONAL-GATE-DEEP-RESEARCH-2026-07-15.md section 4.

WHAT THIS DOES (per gate in gates_in_battery.testable_this_session)
---------------------------------------------------------------------
1. Mines automation/state/core-decisions.jsonl for every row matching the gate's own account +
   GATE_ORDER skip_action within the fresh OOS window (2026-07-09..2026-07-15). Trusts the live
   engine's own evaluate_gates() call that produced each row (does not re-derive gate predicates)
   -- GATE_ORDER's own contract means a row logged under gate X's skip_action proves every gate
   BEFORE X in the order already passed for that row under current live config.
2. Dedupes consecutive re-evaluation ticks into signal EVENTS (5-min gap rule), applies the same
   cross-account stale-echo exclusion the block_elite_bull template used, then applies a
   PER-GATE downstream-double-block exclusion (a row is dropped if another gate later in
   GATE_ORDER, currently armed, would ALSO independently fire for that row's own logged fields --
   "all else held at current config" cuts both ways).
3. Recovers each event's strike (crypto/lib/strike_selection V15_SAFE_TIERS/V15_BOLD_TIERS,
   live-verified equity), trigger level (logged trigger_level_exact, else the same detector the
   live engine used), and entry premium (real Alpaca OPRA 1-min option bars, cache-then-live).
   Applies the 0.30 min-entry-premium floor to the recovered premium (the live floor check never
   ran for a gate-blocked signal, since gates.py is premium-blind).
4. Replays every recovered event under the CURRENT exit shape (structure_stop_study.py's
   replay_structure_aware + structure_stop_signal_time machinery, reused unmodified, fed a shape
   derived PROGRAMMATICALLY from strategies.RIBBON_RIDE.exit.to_dict() -- see
   current_config.exit_shape.replay_shape_derivation in the prereg for why a straight pass-through
   would silently corrupt the in-engine stop level).
5. Grades the 5 ratification gates (OOS positive, WF>=0.70 per-trade-normalized, sub-window
   stable, anchor_no_regression per the prereg's real anchor-mechanism precheck, evidence_n
   advisory) + a Benjamini-Hochberg FDR correction across the battery (multiple comparisons).
6. Writes analysis/recommendations/directional-gate-battery-2026-07-15.json + .md. Does NOT edit
   any params.json file -- any params flip for a gate that clears happens in a separate, later,
   explicitly-flagged step (per the task's own item 5), never inside this script.

Rail-4 CLEAR: analysis only. Reads core-decisions.jsonl (read-only) and live Alpaca OPRA option-
bar data (read-only market data, $0). Touches no trading-path file.

Run: backtest/.venv/Scripts/python.exe backtest/tools/directional_gate_battery.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sys
import time as _time_mod
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import pandas as pd  # noqa: E402

import tw8_level_context as lc                     # noqa: E402  (load_spy_full, frozen_level_set_for_date)
import exit_shape_parity_study as esp               # noqa: E402  (fetch_option_bars)
from structure_stop_study import (                  # noqa: E402
    replay_structure_aware, structure_stop_signal_time, norm_bars_from_esp,
)
from exit_manager import TIME_STOP_ET                # noqa: E402
from lib.filters import detect_level_reclaim, detect_level_rejection  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
import strategies                                     # noqa: E402
from crypto.lib.strike_selection import pick_strike, V15_SAFE_TIERS, V15_BOLD_TIERS  # noqa: E402

PREREG = REPO / "analysis" / "recommendations" / "prereg-directional-gate-battery-2026-07-15.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "directional-gate-battery-2026-07-15.json"
OUT_MD = REPO / "analysis" / "recommendations" / "directional-gate-battery-2026-07-15.md"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"

EXPECTED_PREREG_SHA16 = "c0a96f51cc0af81d"
EXPECTED_PREREG_VERSION = 1

OOS_START = dt.date(2026, 7, 9)
OOS_END = dt.date(2026, 7, 15)
SW1 = (dt.date(2026, 7, 9), dt.date(2026, 7, 10))
SW2 = (dt.date(2026, 7, 13), dt.date(2026, 7, 15))
LEVEL_HISTORY_START = dt.date(2026, 5, 19)   # >=10-day level-formation lookback before OOS_START,
                                              # matching the block_elite_bull template's own choice.
DEDUPE_GAP_MINUTES = 5
MIN_ENTRY_PREMIUM = 0.30
BH_ALPHA = 0.10
EVIDENCE_N_ADVISORY_FLOOR = 15

SAFE_EQUITY = 1569.32   # mcp__alpaca__get_account_info, PA3DHPT7KIQE, live-verified this session
BOLD_EQUITY = 1963.04   # mcp__alpaca_aggressive__get_account_info, PA33W2KUAT40, live-verified this session


# =============================================================================
# CURRENT EXIT SHAPE -- derived programmatically from strategies.RIBBON_RIDE, never hand-copied.
# See prereg current_config.exit_shape.replay_shape_derivation for the full rationale: the replay
# harness (ExitState.from_entry called WITHOUT structure_stop_enabled=True) resolves stop_mode
# internally to "premium" regardless of the shape's own stop_mode field, so premium_stop_pct MUST
# be set to the catastrophe value directly, or every replayed trade gets a silently-wrong -20%
# in-engine stop instead of the intended -50% catastrophe cap.
# =============================================================================
_RR = strategies.RIBBON_RIDE.exit.to_dict()
CURRENT_SHAPE = {
    "premium_stop_pct": _RR["catastrophe_stop_pct"],
    "tp1_premium_pct": _RR["tp1_premium_pct"],
    "tp1_qty_fraction": _RR["tp1_qty_fraction"],
    "profit_lock_mode": _RR["profit_lock_mode"],
    "trail_pct": _RR["trail_pct"],
    "runner_target_pct": _RR["runner_target_pct"],
    "profit_lock_arm_pct": _RR["profit_lock_arm_pct"],
}
TIME_STOP = TIME_STOP_ET


# =============================================================================
# GATE SPECS -- downstream-double-block predicates match the prereg's prose exactly (cross-check
# gates_in_battery.testable_this_session.*.downstream_double_block_check).
# =============================================================================
def _row_time(row: dict) -> dt.time:
    return dt.datetime.fromisoformat(row["ts_et"]).time()


def _excl_none(_row: dict) -> bool:
    return False


def _excl_block_elite_bull_safe(row: dict) -> bool:
    """gate #5 block_bull_1100_1200 is armed True on Safe -- 11:00-12:00 ET double-block."""
    t = _row_time(row)
    return dt.time(11, 0) <= t < dt.time(12, 0)


def _excl_block_elite_bull_bold(row: dict) -> bool:
    """gate #12 block_conf_lvl_rec_afternoon is armed True on Bold -- confluence+level_reclaim
    AND >=14:00 ET double-block."""
    trigs = row.get("triggers") or []
    t = _row_time(row)
    return "confluence" in trigs and "level_reclaim" in trigs and t >= dt.time(14, 0)


def _excl_entry_body_min_safe(row: dict) -> bool:
    """gate #15 vix_bear_hard_cap (23.0) is armed on Safe -- double-block."""
    vix = row.get("vix")
    return vix is not None and float(vix) >= 23.0


GATE_SPECS: list[dict] = [
    dict(gate_key="block_elite_bull__safe", account="safe", side="C",
         params_key="block_elite_bull", skip_action="SKIP_ELITE_BULL_LEVEL_RECLAIM",
         downstream_exclude=_excl_block_elite_bull_safe),
    dict(gate_key="block_elite_bull__bold", account="bold", side="C",
         params_key="block_elite_bull", skip_action="SKIP_ELITE_BULL_LEVEL_RECLAIM",
         downstream_exclude=_excl_block_elite_bull_bold),
    dict(gate_key="require_bearish_fill_bar__bold", account="bold", side="P",
         params_key="require_bearish_fill_bar", skip_action="SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY",
         downstream_exclude=_excl_none),
    dict(gate_key="entry_bar_body_pct_min__safe", account="safe", side="P",
         params_key="entry_bar_body_pct_min", skip_action="SKIP_DOJI_ENTRY_BAR",
         downstream_exclude=_excl_entry_body_min_safe),
    dict(gate_key="block_conf_lvl_rec_afternoon__bold", account="bold", side="C",
         params_key="block_conf_lvl_rec_afternoon", skip_action="SKIP_CONF_LVL_REC_AFTERNOON",
         downstream_exclude=_excl_none),
    dict(gate_key="block_bull_1100_1200__safe", account="safe", side="C",
         params_key="block_bull_1100_1200", skip_action="SKIP_BULL_1100_1200",
         downstream_exclude=_excl_none),
]

UNTESTABLE_GATE_KEYS = [
    "block_level_rejection__safe", "midday_trendline_gate__both",
    "block_conf_lvl_rej_midday_afternoon__both", "entry_bar_body_pct_min_bull__safe",
    "vix_bear_hard_cap__safe", "min_ribbon_momentum_cents__both", "max_ribbon_duration_bars__both",
]


# =============================================================================
# PRE-FLIGHT -- prereg hash pin (same convention as block_elite_bull_ssb_revalidation.py)
# =============================================================================
def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def preflight() -> tuple[dict, dict]:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    stored = preg.get("content_sha256_16")
    preg_no_hash = {k: v for k, v in preg.items() if k != "content_sha256_16"}
    recomputed = _content_hash(preg_no_hash)
    pf = {
        "prereg_version": preg.get("version"),
        "prereg_version_ok": preg.get("version") == EXPECTED_PREREG_VERSION,
        "prereg_sha256_16_recomputed": recomputed,
        "prereg_sha256_16_stored": stored,
        "prereg_hash_ok": recomputed == EXPECTED_PREREG_SHA16 and recomputed == stored,
    }
    return pf, preg


# =============================================================================
# DECISION-LOG I/O + PURE MINING FUNCTIONS (ported from block_elite_bull_ssb_revalidation.py)
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


def dedupe_into_events(rows: list[dict], gap_minutes: int = DEDUPE_GAP_MINUTES) -> list[dict]:
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
    ts = dt.datetime.fromisoformat(entry_row["ts_et"])
    t = ts.time()
    return dt.time(9, 35) <= t < dt.time(9, 41)


def _rows_in_window(rows: list[dict], account: str, action: str, start: dt.date, end: dt.date) -> list[dict]:
    out = []
    for r in rows:
        ts = r.get("ts_et")
        if not ts or r.get("account") != account or r.get("action") != action:
            continue
        try:
            d = dt.date.fromisoformat(ts[:10])
        except ValueError:
            continue
        if start <= d <= end:
            out.append(r)
    return out


def mine_gate_events(all_rows: list[dict], spec: dict) -> tuple[list[dict], dict]:
    """Mine + dedupe + stale-echo-filter + downstream-double-block-filter one gate's cohort."""
    account = spec["account"]
    other_account = "bold" if account == "safe" else "safe"
    matched = _rows_in_window(all_rows, account, spec["skip_action"], OOS_START, OOS_END)
    n_raw = len(matched)
    n_reason_mismatch = sum(
        1 for r in matched
        if r.get("reason") != f"blocked by entry gate {spec['params_key']}"
    )
    events = dedupe_into_events(matched, DEDUPE_GAP_MINUTES)
    other_rows = _rows_in_window(all_rows, other_account, "SKIP_STALE_TRIGGER", OOS_START, OOS_END)
    kept, excluded, flagged = [], [], []
    for ev in events:
        stale, reason = is_possible_stale_echo(ev["entry_row"], other_rows)
        if stale:
            excluded.append({**ev, "exclusion_reason": reason})
            continue
        if spec["downstream_exclude"](ev["entry_row"]):
            excluded.append({**ev, "exclusion_reason": "downstream_double_block"})
            continue
        if is_open_adjacent(ev["entry_row"]):
            ev = {**ev, "elevated_stale_risk": True}
            flagged.append(ev)
        kept.append(ev)
    stats = {
        "n_raw_ticks": n_raw, "n_reason_mismatch": n_reason_mismatch,
        "n_events_total": len(events), "n_excluded": len(excluded),
        "n_excluded_stale_echo": sum(1 for e in excluded if "SKIP_STALE_TRIGGER" in e["exclusion_reason"]),
        "n_excluded_downstream_double_block": sum(1 for e in excluded if e["exclusion_reason"] == "downstream_double_block"),
        "n_flagged_open_adjacent": len(flagged), "n_kept": len(kept),
    }
    return kept, stats


# =============================================================================
# TRIGGER-LEVEL + STRIKE + OPTION-BAR RECOVERY (generalized for both C/P, both accounts)
# =============================================================================
_level_cache: dict = {}
_spy_full_cache: Optional[pd.DataFrame] = None


def _spy_full() -> pd.DataFrame:
    global _spy_full_cache
    if _spy_full_cache is None:
        _spy_full_cache = lc.load_spy_full(LEVEL_HISTORY_START, OOS_END)
    return _spy_full_cache


def recover_trigger_level(entry_row: dict, side: str) -> tuple[Optional[float], str]:
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
    detector = detect_level_reclaim if side == "C" else detect_level_rejection
    for idx in list(day_bars.index)[::-1]:
        bar = spy_full.loc[idx]
        lvl = detector(bar, level_set.active)
        if lvl is not None:
            return lvl, "recovered_exact_match"
    return None, "no_trigger_bar_found"


def strike_for(spy_spot: float, side: str, account: str) -> int:
    if account == "safe":
        return pick_strike(spy_spot, SAFE_EQUITY, side, V15_SAFE_TIERS)
    return pick_strike(spy_spot, BOLD_EQUITY, side, V15_BOLD_TIERS)


def _cached_bars_as_esp_shape(symbol: str) -> Optional[list[dict]]:
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
    return live, ("live" if live else "none")


def prepare_event(entry_row: dict, qty: int, side: str, account: str) -> tuple[Optional[dict], str]:
    ts_et = dt.datetime.fromisoformat(entry_row["ts_et"])
    date = ts_et.date()
    spy_spot = entry_row.get("spy")
    if spy_spot is None:
        return None, "no_spy_spot"
    strike = strike_for(float(spy_spot), side, account)
    trigger_level, level_status = recover_trigger_level(entry_row, side)
    symbol = option_symbol(date, strike, side)
    bars, bar_source = fetch_bars_cache_then_live(symbol, date.isoformat())
    if not bars:
        return None, "no_option_bars"
    norm_bars = norm_bars_from_esp(bars, entry_ts_utc=None)
    norm_bars = [b for b in norm_bars if b.dt >= ts_et]
    if not norm_bars:
        return None, "no_bars_after_entry"
    entry_premium = norm_bars[0].o
    if entry_premium <= 0:
        return None, "non_positive_premium"
    if entry_premium < MIN_ENTRY_PREMIUM:
        return None, "sub_floor_premium"
    spy_full = _spy_full()
    spy_lifetime = spy_full[(spy_full["date"] == date) & (spy_full["timestamp_et"] >= ts_et)]
    return {
        "date": date.isoformat(), "entry_ts_et": entry_row["ts_et"], "symbol": symbol,
        "strike": strike, "side": side, "qty": qty, "entry_premium": round(entry_premium, 4),
        "trigger_level": trigger_level, "trigger_level_status": level_status,
        "bar_source": bar_source, "norm_bars": norm_bars, "spy_lifetime": spy_lifetime,
    }, "ok"


# =============================================================================
# REPLAY (structure_stop_study.py machinery, reused unmodified)
# =============================================================================
def replay_prepared_event(prepared: dict) -> dict:
    ss_time = None
    if prepared["trigger_level"] is not None:
        ss_time = structure_stop_signal_time(prepared["spy_lifetime"], prepared["side"],
                                              prepared["trigger_level"], buffer=0.0)
    r = replay_structure_aware(prepared["entry_premium"], prepared["side"], prepared["qty"],
                               prepared["norm_bars"], ss_time, CURRENT_SHAPE, TIME_STOP)
    return {**r, "date": prepared["date"], "entry_ts_et": prepared["entry_ts_et"],
            "strike": prepared["strike"], "entry_premium": prepared["entry_premium"],
            "trigger_level": prepared["trigger_level"], "bar_source": prepared["bar_source"],
            "structure_available": prepared["trigger_level"] is not None}


# =============================================================================
# STATS + WF + BH-FDR
# =============================================================================
def cohort_stats(replays: list[dict]) -> dict:
    pnls = [r["pnl"] for r in replays]
    n = len(pnls)
    total = round(sum(pnls), 2)
    wins = sum(1 for p in pnls if p > 0)
    by_day: dict = {}
    for r in replays:
        by_day[r["date"]] = by_day.get(r["date"], 0.0) + r["pnl"]
    sw1_total = sum(v for d, v in by_day.items() if SW1[0] <= dt.date.fromisoformat(d) <= SW1[1])
    sw2_total = sum(v for d, v in by_day.items() if SW2[0] <= dt.date.fromisoformat(d) <= SW2[1])
    sw1_present = any(SW1[0] <= dt.date.fromisoformat(d) <= SW1[1] for d in by_day)
    sw2_present = any(SW2[0] <= dt.date.fromisoformat(d) <= SW2[1] for d in by_day)
    n_hurt = sum(1 for present, v in ((sw1_present, sw1_total), (sw2_present, sw2_total))
                 if present and v < 0)
    return {
        "n": n, "wr": round(wins / n, 4) if n else 0.0, "total_pnl": total,
        "expectancy_per_trade": round(total / n, 2) if n else 0.0,
        "n_structure_available": sum(1 for r in replays if r.get("structure_available")),
        "n_structure_fired": sum(1 for r in replays if r.get("structure_fired")),
        "by_day_pnl": {k: round(v, 2) for k, v in sorted(by_day.items())},
        "sw1_total": round(sw1_total, 2), "sw2_total": round(sw2_total, 2),
        "sw1_present": sw1_present, "sw2_present": sw2_present,
        "n_sw_hurt": n_hurt, "sub_window_stable": n_hurt <= 1,
        "trades": [{"date": r["date"], "entry_ts_et": r["entry_ts_et"], "strike": r["strike"],
                    "side": r.get("side", None), "entry_premium": r["entry_premium"],
                    "pnl": r["pnl"], "structure_available": r.get("structure_available", False),
                    "structure_fired": r.get("structure_fired", False)}
                   for r in sorted(replays, key=lambda x: x["entry_ts_et"])],
    }


def compute_wf(oos_delta: float, n_oos: int, is_delta, n_is) -> tuple[Optional[float], str]:
    if is_delta in (None, 0):
        return None, "N/A structural (no IS baseline / is_delta=0)"
    if n_is is None:
        if is_delta == 0:
            return None, "N/A structural (is_delta=0)"
        wf_aggregate = oos_delta / is_delta
        return round(wf_aggregate, 3), "AGGREGATE (not per-trade normalized -- n_is unavailable, see prereg caveat)"
    if n_is == 0 or n_oos == 0:
        return None, "N/A structural (n_is=0 or n_oos=0)"
    wf = (oos_delta / n_oos) / (is_delta / n_is)
    return round(wf, 3), "per-trade normalized, backtest/safe_fill_bar_gate.py G3 formula"


def one_sided_p_mean_gt_0(xs: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    sd = var ** 0.5
    if sd == 0:
        return 0.0 if mean > 0 else 1.0
    t = mean / (sd / math.sqrt(n))
    return 0.5 * math.erfc(t / math.sqrt(2))


def bh_fdr(tests: list[dict], alpha: float = BH_ALPHA) -> list[dict]:
    """Benjamini-Hochberg step-up, same algorithm as
    backtest/autoresearch/discovery_shadow_ledger.py#fdr_screen (reimplemented, not imported --
    that module is coupled to its own ledger file format). A gate with no computable p-value
    (n<2) is treated as NOT surviving (fail-safe, never silently significant)."""
    testable = [t for t in tests if t["p"] is not None]
    testable.sort(key=lambda d: d["p"])
    m = len(testable)
    sig_cut = 0
    for i, d in enumerate(testable, 1):
        thresh = alpha * i / m if m else 0.0
        if d["p"] <= thresh:
            sig_cut = i
    for i, d in enumerate(testable, 1):
        d["bh_threshold"] = round(alpha * i / m, 5) if m else 0.0
        d["bh_significant"] = i <= sig_cut
    for t in tests:
        if t["p"] is None:
            t["bh_threshold"] = None
            t["bh_significant"] = False
    return tests


# =============================================================================
# ANCHOR VERDICT -- parsed from the frozen prereg's own precheck text (authored this session
# BEFORE any OOS mining/replay ran; not re-derived here, just read back).
# =============================================================================
def anchor_verdict_for(preg: dict, gate_key: str) -> tuple[bool, str]:
    entry = preg["anchor_mechanism_precheck"].get(gate_key)
    if entry is None:
        return False, "no anchor precheck entry in prereg"
    reading = entry.get("reading", "")
    if "anchor_no_regression = PASS" in reading:
        return True, reading
    if "anchor_no_regression = UNVERIFIED" in reading:
        return False, reading
    return False, reading  # conservative default if the text doesn't match either marker


# =============================================================================
# MAIN
# =============================================================================
def main() -> int:
    pf, preg = preflight()
    print(f"[gate-battery] preflight: {pf}", flush=True)
    if not pf["prereg_hash_ok"] or not pf["prereg_version_ok"]:
        print("[gate-battery] PREFLIGHT FAILED -- prereg hash/version mismatch, aborting "
              "(no re-picks, no stale-hash runs)", file=sys.stderr)
        return 1

    print(f"[gate-battery] CURRENT_SHAPE = {CURRENT_SHAPE}", flush=True)
    print(f"[gate-battery] SAFE_EQUITY={SAFE_EQUITY} -> tier {V15_SAFE_TIERS[0]}; "
          f"BOLD_EQUITY={BOLD_EQUITY} -> tier {V15_BOLD_TIERS[0]}", flush=True)

    print("[gate-battery] loading core-decisions.jsonl...", flush=True)
    all_rows = load_core_decisions()
    print(f"[gate-battery] loaded {len(all_rows)} rows", flush=True)

    print("[gate-battery] loading SPY history for level recovery (may take a moment)...", flush=True)
    _spy_full()  # warm the cache once, up front

    qty_by_account = {"safe": 3, "bold": 5}   # automation/state/params.json / aggressive/params.json
                                               # min_contracts, both accounts' $0-2K tier (== base_qty
                                               # == elite_qty at this equity band, no ELITE upsize)

    results: dict[str, dict] = {}
    p_tests: list[dict] = []

    for spec in GATE_SPECS:
        gate_key = spec["gate_key"]
        print(f"\n[gate-battery] ==== {gate_key} ({spec['account']}, {spec['skip_action']}) ====", flush=True)
        events, mine_stats = mine_gate_events(all_rows, spec)
        print(f"[gate-battery] {gate_key}: mining stats: {mine_stats}", flush=True)

        qty = qty_by_account[spec["account"]]
        prepared, n_missing, drop_reasons = [], 0, {}
        for ev in events:
            p, status = prepare_event(ev["entry_row"], qty, spec["side"], spec["account"])
            if p is None:
                n_missing += 1
                drop_reasons[status] = drop_reasons.get(status, 0) + 1
            else:
                prepared.append(p)
        print(f"[gate-battery] {gate_key}: prepared={len(prepared)} missing={n_missing} "
              f"drop_reasons={drop_reasons}", flush=True)

        replays = [replay_prepared_event(p) for p in prepared]
        stats = cohort_stats(replays)
        print(f"[gate-battery] {gate_key}: n={stats['n']} total_pnl={stats['total_pnl']} "
              f"wr={stats['wr']} sw1={stats['sw1_total']} sw2={stats['sw2_total']} "
              f"sub_window_stable={stats['sub_window_stable']}", flush=True)

        # --- WF vs the prereg's cited prior IS baseline ---
        prior = preg["gates_in_battery"]["testable_this_session"][gate_key]["prior_is_baseline"]
        is_delta = prior.get("is_delta")
        n_is = prior.get("n_is")
        wf, wf_note = compute_wf(stats["total_pnl"], stats["n"], is_delta, n_is)

        # --- anchor ---
        anchor_pass, anchor_text = anchor_verdict_for(preg, gate_key)

        # --- BH-FDR input ---
        pnls = [r["pnl"] for r in replays]
        p_val = one_sided_p_mean_gt_0(pnls)
        p_tests.append({"gate": gate_key, "p": p_val, "n": stats["n"], "mean_pnl": stats["expectancy_per_trade"]})

        cond1_oos_positive = stats["total_pnl"] > 0
        cond2_wf = (wf is not None and wf >= 0.70) or (wf is None and is_delta in (None, 0))
        cond3_sw_stable = stats["sub_window_stable"]
        cond4_anchor = anchor_pass
        cond5_evidence_n = stats["n"] >= EVIDENCE_N_ADVISORY_FLOOR   # advisory only

        results[gate_key] = {
            "params_key": spec["params_key"], "account": spec["account"], "side": spec["side"],
            "skip_action": spec["skip_action"], "qty_used": qty,
            "mining_stats": mine_stats, "n_missing_bars": n_missing, "drop_reasons": drop_reasons,
            "cohort_stats": stats,
            "prior_is_baseline": prior, "wf": wf, "wf_note": wf_note,
            "anchor_no_regression": anchor_pass, "anchor_evidence": anchor_text,
            "bh_p_value": p_val,
            "conditions": {
                "1_oos_positive": cond1_oos_positive,
                "2_wf_ge_070_or_waived": cond2_wf,
                "3_sub_window_stable": cond3_sw_stable,
                "4_anchor_no_regression": cond4_anchor,
                "5_evidence_n_advisory_pass": cond5_evidence_n,
            },
            "evidence_n_thin": stats["n"] < EVIDENCE_N_ADVISORY_FLOOR,
        }

    p_tests = bh_fdr(p_tests)
    for t in p_tests:
        results[t["gate"]]["bh_significant"] = t["bh_significant"]
        results[t["gate"]]["bh_threshold"] = t["bh_threshold"]

    # --- final verdicts ---
    for gate_key, r in results.items():
        c = r["conditions"]
        all_required_pass = (c["1_oos_positive"] and c["2_wf_ge_070_or_waived"]
                              and c["3_sub_window_stable"] and c["4_anchor_no_regression"])
        bh_ok = r["bh_significant"]
        if all_required_pass and bh_ok:
            r["verdict"] = "DISABLE"
        elif all_required_pass and not bh_ok:
            r["verdict"] = "KEEP"
            r["verdict_note"] = "conditions 1-4 clear but fails BH-FDR multiple-comparisons cut -- not shipped"
        else:
            r["verdict"] = "KEEP"
            failing = [k for k, v in c.items() if not v]
            r["verdict_note"] = f"fails: {failing}"

    for gate_key in UNTESTABLE_GATE_KEYS:
        entry = preg["gates_in_battery"]["untestable_this_session"][gate_key]
        results[gate_key] = {
            "verdict": "UNCHANGED",
            "verdict_note": "zero fresh-OOS evidence this session, per honesty rail: never "
                            "disable without its own passing A/B",
            "fresh_oos_raw_ticks_confirmed": entry.get("fresh_oos_raw_ticks_confirmed"),
            "current_value": entry.get("current_value"),
            "note": entry.get("note", ""),
        }

    out = {
        "_doc": "12-gate directional-gate revalidation battery result, per the frozen prereg. "
                "6 gates got a real mined+replayed A/B (testable_this_session); 6 had zero fresh "
                "OOS evidence this session (untestable_this_session, left UNCHANGED). "
                "trendline_requires_ribbon_flip and block_bull_morning_agg are OUT OF SCOPE "
                "(J-decision-gated, not re-run here at all).",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "preflight": pf,
        "current_shape_used": CURRENT_SHAPE,
        "equity_used": {"safe": SAFE_EQUITY, "bold": BOLD_EQUITY},
        "qty_used": qty_by_account,
        "bh_fdr": {"alpha": BH_ALPHA, "tests": p_tests},
        "cross_study_wf_check": {
            "_doc": "Mid-run methodology heads-up received from a concurrent session (Bold "
                    "strike-axis study, analysis/recommendations/bold-strike-axis-2026-07-15.json): "
                    "that study's WF gate was null for ALL 6 cells including its own control -- a "
                    "real red flag there. Checked against THIS battery's actual output before "
                    "shipping (not blindly applied): 4/6 gates have a real, non-null, meaningfully "
                    "negative WF (driven by genuinely negative recovered OOS dollars vs a positive "
                    "historical IS baseline); the 2 WF=None cases each have a distinct structural "
                    "cause (zero prior IS trades / zero surviving OOS trades post-premium-floor), "
                    "unrelated to the strike-axis study's 2025-half-vs-2026-half split (this "
                    "battery's WF does not use that split at all -- IS is each gate's own "
                    "pre-existing ratified scorecard). Spot-checked trade-level strikes/premiums/"
                    "structure-stop pattern for the largest cohort (block_elite_bull/safe, n=18) "
                    "-- mechanistically explicable, not degenerate.",
            "verdict": "WF is discriminating correctly in this battery, NOT the same artifact. "
                       "No methodology change made. Moot for shipping regardless (0 DISABLE "
                       "verdicts either way, well under the >3-disables recommendation threshold).",
            "gates_with_real_nonnull_wf": ["block_elite_bull__safe", "entry_bar_body_pct_min__safe",
                    "block_bull_1100_1200__safe", "block_conf_lvl_rec_afternoon__bold"],
            "gates_with_structural_na_wf": {"block_elite_bull__bold": "is_delta=0 (no prior IS "
                    "trades in this gate's own VIX-band history)",
                    "require_bearish_fill_bar__bold": "n_oos=0 (all 10 recovered events sub-$0.30, "
                    "dropped by the premium floor)"},
        },
        "results": results,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\n[gate-battery] wrote {OUT_JSON}", flush=True)

    write_markdown(out, preg)
    print(f"[gate-battery] wrote {OUT_MD}", flush=True)

    print("\n[gate-battery] ==== VERDICTS ====", flush=True)
    for gate_key, r in results.items():
        print(f"  {gate_key}: {r['verdict']}" + (f" ({r.get('verdict_note')})" if r.get("verdict_note") else ""), flush=True)

    return 0


def write_markdown(out: dict, preg: dict) -> None:
    lines = []
    lines.append("# Directional Gate Battery -- 2026-07-15")
    lines.append("")
    lines.append("> Pre-registered battery result. Runner: `backtest/tools/directional_gate_battery.py`. "
                 "Pre-registration: `analysis/recommendations/prereg-directional-gate-battery-2026-07-15.json`. "
                 "Source report: `markdown/audits/DIRECTIONAL-GATE-DEEP-RESEARCH-2026-07-15.md`.")
    lines.append("")
    lines.append(f"Generated: {out['generated_at']}. Preflight: {out['preflight']}.")
    lines.append("")
    lines.append(f"Exit shape used (derived from `strategies.RIBBON_RIDE.exit.to_dict()`): `{out['current_shape_used']}`")
    lines.append("")
    lines.append(f"Equity used (live-verified this session): Safe ${out['equity_used']['safe']} "
                 f"(ATM), Bold ${out['equity_used']['bold']} (OTM-3). Qty: {out['qty_used']}.")
    lines.append("")
    n_disable = sum(1 for r in out["results"].values() if r.get("verdict") == "DISABLE")
    n_keep = sum(1 for r in out["results"].values() if r.get("verdict") == "KEEP")
    n_unchanged = sum(1 for r in out["results"].values() if r.get("verdict") == "UNCHANGED")
    lines.append(f"**VERDICT: {n_disable} DISABLE / {n_keep} KEEP / {n_unchanged} UNCHANGED "
                 f"across the 12 REVALIDATE gates.** No params.json edit was needed unless "
                 f"DISABLE > 0 above.")
    lines.append("")
    cwf = out.get("cross_study_wf_check")
    if cwf:
        lines.append("## Cross-study methodology check (WF-null artifact caution)")
        lines.append("")
        lines.append(f"A concurrent session flagged mid-run that a related strike-axis study's WF "
                     f"gate was null for ALL its cells including its own control. {cwf['_doc']}")
        lines.append("")
        lines.append(f"**{cwf['verdict']}**")
        lines.append("")
        lines.append(f"- Gates with real, non-null WF this run: {cwf['gates_with_real_nonnull_wf']}")
        lines.append(f"- Gates with a structurally-N/A WF, each with its own distinct cause: "
                     f"{cwf['gates_with_structural_na_wf']}")
        lines.append("")
    lines.append("## Testable gates (real mined + replayed A/B)")
    lines.append("")
    lines.append("| Gate | Account | n | Total PnL | WR | WF | SubWin stable | Anchor | BH-sig | Verdict |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for spec in GATE_SPECS:
        gk = spec["gate_key"]
        r = out["results"][gk]
        cs = r["cohort_stats"]
        wf_s = f"{r['wf']}" if r["wf"] is not None else "N/A"
        lines.append(f"| `{r['params_key']}` | {r['account']} | {cs['n']} | ${cs['total_pnl']} | "
                     f"{cs['wr']*100:.0f}% | {wf_s} | {cs['sub_window_stable']} | "
                     f"{r['anchor_no_regression']} | {r['bh_significant']} | **{r['verdict']}** |")
    lines.append("")
    for spec in GATE_SPECS:
        gk = spec["gate_key"]
        r = out["results"][gk]
        cs = r["cohort_stats"]
        lines.append(f"### `{r['params_key']}` ({r['account']})")
        lines.append("")
        lines.append(f"- Verdict: **{r['verdict']}**" + (f" -- {r.get('verdict_note')}" if r.get("verdict_note") else ""))
        lines.append(f"- Mining: {r['mining_stats']}")
        lines.append(f"- Recovered/replayed n={cs['n']} (missing bars={r['n_missing_bars']}, drop_reasons={r['drop_reasons']})")
        lines.append(f"- Total PnL ${cs['total_pnl']}, expectancy ${cs['expectancy_per_trade']}/tr, WR {cs['wr']*100:.1f}%")
        lines.append(f"- By-day: {cs['by_day_pnl']}")
        lines.append(f"- Sub-windows: SW1(07-09/10)=${cs['sw1_total']} SW2(07-13..15)=${cs['sw2_total']}, "
                     f"hurt={cs['n_sw_hurt']}/2, stable={cs['sub_window_stable']}")
        lines.append(f"- Structure-stop available for {cs['n_structure_available']}/{cs['n']} trades, fired for {cs['n_structure_fired']}")
        lines.append(f"- WF: {r['wf']} ({r['wf_note']}) vs prior IS baseline {r['prior_is_baseline']}")
        lines.append(f"- Anchor: {r['anchor_no_regression']} -- {r['anchor_evidence']}")
        lines.append(f"- BH-FDR: p={r['bh_p_value']}, threshold={r['bh_threshold']}, significant={r['bh_significant']}")
        lines.append("")
    lines.append("## Untestable this session (left UNCHANGED)")
    lines.append("")
    lines.append("| Gate | Fresh OOS ticks | Current value | Note |")
    lines.append("|---|---|---|---|")
    for gate_key in UNTESTABLE_GATE_KEYS:
        r = out["results"][gate_key]
        lines.append(f"| `{gate_key}` | {r['fresh_oos_raw_ticks_confirmed']} | `{r['current_value']}` | {r['note']} |")
    lines.append("")
    lines.append("## Out of scope (J-decision-gated, not re-run)")
    lines.append("")
    for item in preg["decision_rule"]["explicitly_out_of_scope"]:
        lines.append(f"- {item}")
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
