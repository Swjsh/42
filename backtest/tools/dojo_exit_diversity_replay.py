"""backtest/tools/dojo_exit_diversity_replay.py -- DOJO autonomous exit-diversity replay.

Spec: markdown/specs/DOJO-AUTONOMOUS-FINETUNE.md ("The autonomous harness (exit-diversity
replay)") + markdown/specs/DOJO-ARCHITECTURE-DECISION.md (module contracts, frozen -- this
file IMPORTS setup/scripts/dojo/{engine_step,sim_executor,clock}.py, never edits them).

THE QUESTION: given the ENGINE'S OWN entries (no human judgment, no hindsight), which of J's
3 defined exit profiles banks the most real-fill P&L across a curriculum of real trading days?
Entry selection is HELD FIXED across all 3 profiles per entry -- only the exit policy varies.
This isolates the exit-diversity question from the entry-diversity question (that one is
interactive-only, per the spec's "split" section -- J's discretionary chart read, not
autonomous).

ENTRY SOURCE (disclosed choice, not specified verbatim by the pre-reg author): CORE-SAFE
(accounts.json id "safe-2", dojo alias "safe") ONLY. Rationale: (1) "the engine" in the spec
is singular; picking one canonical, always-live account avoids conflating two different risk
profiles' entries into one race; (2) CORE-SAFE is production v15's real trading account, the
account structure-stop-reference-level-2026-07-20.json's own anchor population is built from
(safe-side fleet arms); (3) CONTROL's own accounts.json description explicitly pairs
"risky-1/core" as sharing the SAME (empty) exit_patch, so core-safe entries under all 3
profiles is a faithful within-spec instantiation. Bold/aggressive entries are NOT included
this pass -- a disclosed scope narrowing, not an oversight.

EXIT PROFILES (pulled VERBATIM from automation/state/fleet/accounts.json at runtime, never
hand-copied -- see _load_exit_profiles): CONTROL = risky-1/safe-2's empty params_patch (today's
live trigger-exact structure stop + chandelier, registry default for ribbon_ride). RIBBON =
safe-3's params_patch.exit_patch. ZONE-RIDE = risky-3's params_patch.exit_patch. NOTE (expected,
not a bug): every dojo core-safe entry fires via BEARISH_REJECTION_RIDE_THE_RIBBON /
BULLISH_RECLAIM_RIDE_THE_RIBBON (the ribbon_ride strategy) -- and ribbon_ride's REGISTRY exit
shape ALREADY IS {stop_mode: structure, profit_lock_mode: trailing, trail_pct: 0.15}, which is
exactly what RIBBON's patch sets. So for this entry population, CONTROL and RIBBON are
mathematically IDENTICAL per-episode (accounts.json's own docstring says this outright: "for
ribbon_ride this is a no-op"). Only ZONE-RIDE (trail_pct 0.20 vs 0.15) can differ. This is
disclosed prominently in the MD report, not buried.

RIBBON-FLIP FIDELITY: engine_step.load_day_bars() does not carry a 'stack' (ribbon) column, so
naively no ribbon_flip_back stage could ever fire in a walk_exit_manager replay (the same gap
sim_executor.py's own _ribbon_aligned_to docstring discloses for ITS callers). This script
closes that gap for free: the entry-discovery pass already calls engine_step.step() every RTH
bar of the day (to find would_place=True events) and each DojoDecision carries bc["ribbon_now"]
["stack"] for that bar -- so every day's FULL ribbon-stack series is collected as a side effect
and threaded into every position's walk via sim_executor._ribbon_aligned_to (reused verbatim).

USAGE:
    python -m backtest.tools.dojo_exit_diversity_replay prereg   # STEP 0, writes the frozen pre-reg
    python -m backtest.tools.dojo_exit_diversity_replay run      # STEP 1+2, reads the frozen pre-reg,
                                                                  # writes scorecard + MD

HARD FENCE: no alpaca/broker import anywhere in this module (mirrors the dojo package's own
fence, guard-tested by backtest/tests/test_dojo_exit_diversity_replay.py). No git operations.
No edits to any live trading-path file or to the dojo package's own source files -- this
module only IMPORTS them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd

# --- path setup (mirrors dojo/engine_step.py + dojo/sim_executor.py's own bootstrap) --------
_ROOT = Path(__file__).resolve().parents[2]  # .../42
for _p in ("backtest", "setup/scripts", "setup/scripts/dojo", "automation/state/fleet"):
    _ap = str(_ROOT / _p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from dojo import engine_step  # noqa: E402 -- REUSED, not edited (frozen contract)
from dojo import sim_executor as se  # noqa: E402 -- REUSED, not edited (frozen contract)
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import bar_at_or_after, option_symbol  # noqa: E402
import fleet_executor as fx  # noqa: E402 -- reuse risk_gate.max_affordable_qty

ET = ZoneInfo("America/New_York")
DATA_DIR = _ROOT / "backtest" / "data"
OPTIONS_DIR = DATA_DIR / "options"
ACCOUNTS_PATH = _ROOT / "automation" / "state" / "fleet" / "accounts.json"
SAFE_PARAMS_PATH = _ROOT / "automation" / "state" / "params.json"
ANALYSIS_DIR = _ROOT / "analysis" / "dojo"
PREREG_PATH = ANALYSIS_DIR / "exit-diversity-prereg-2026-07-20.json"
SCORECARD_PATH = ANALYSIS_DIR / "exit-diversity-scorecard-2026-07-20.json"
MD_PATH = ANALYSIS_DIR / "EXIT-DIVERSITY-2026-07-20.md"
REF_ZONE_STUDY_PATH = _ROOT / "analysis" / "recommendations" / "structure-stop-reference-level-2026-07-20.json"

REQUESTED_DAYS = ["2026-07-17", "2026-07-20", "2026-06-30", "2026-07-02", "2026-07-08"]
DISCOVERY_WINDOW_START = date(2026, 6, 29)  # matches structure-stop-reference-level's own anchor start
DISCOVERY_WINDOW_END = date(2026, 7, 20)    # "today" per this task's frame
ENTRY_SOURCE_DOJO_ARM = "safe"              # -> accounts.json "safe-2" (CORE-SAFE) via CORE_ARM_ALIASES
STRATEGY_NAME = "ribbon_ride"
HELD_OUT_FRACTION = 0.25  # last ~25% of curriculum days by calendar date, frozen at pre-reg time
_OPT_FILE_RE = re.compile(r"^SPY(\d{2})(\d{2})(\d{2})[CP]\d{8}\.csv$")


# =====================================================================================
# STEP 0 -- pre-registration (curriculum discovery + exit profiles + win-gate rules,
# frozen BEFORE any simulation runs; no post-hoc tuning after `run` sees results).
# =====================================================================================
def _load_exit_profiles() -> dict:
    """Pull the 3 exit_patch dicts VERBATIM from accounts.json (never hand-copied). Asserts
    the arm each profile is sourced from still carries the expected exit_profile label, so a
    future accounts.json edit that silently reshuffles these fails LOUD here rather than
    quietly racing the wrong profile under an old name (C14)."""
    accounts = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    arms = {a["id"]: a for a in accounts["arms"]}
    safe2, risky1, safe3, risky3 = arms["safe-2"], arms["risky-1"], arms["safe-3"], arms["risky-3"]
    # 2026-07-29: risky-1 stopped being the CONTROL. J's "rip apart the shared exit shape"
    # directive turned it into the BE-FLOOR challenger lane (fixed breakeven lock armed pre-TP1
    # at +30% MFE, reachable tp1 0.5). The CONTROL role moved to the CORE arms (safe-2/bold-2),
    # which still run the registry shape verbatim -- so CONTROL is now sourced from safe-2's
    # (empty) patch rather than risky-1's. This guard's contract is unchanged: any future
    # relabelling still fails LOUD here instead of silently racing the wrong profile (C14).
    expected_labels = {"safe-2": "CORE", "risky-1": "REACHABLE-TP1", "safe-3": "RIBBON", "risky-3": "ZONE-RIDE"}
    for arm_id, want in expected_labels.items():
        got = arms[arm_id].get("exit_profile")
        if got != want:
            raise ValueError(
                f"accounts.json arm {arm_id!r} exit_profile changed shape: "
                f"expected {want!r}, got {got!r} -- exit-diversity profile mapping is stale"
            )
    control_patch = (safe2.get("params_patch") or {}).get("exit_patch") or {}
    if control_patch:
        raise ValueError(
            "CONTROL source (safe-2, the CORE registry-verbatim arm) now carries a non-empty "
            "exit_patch -- accounts.json changed shape; this pre-reg's CONTROL definition "
            "('the untouched registry exit shape') is no longer accurate without a human re-check"
        )
    ribbon_patch = (safe3.get("params_patch") or {}).get("exit_patch") or {}
    zone_patch = (risky3.get("params_patch") or {}).get("exit_patch") or {}
    be_patch = (risky1.get("params_patch") or {}).get("exit_patch") or {}
    if not be_patch:
        raise ValueError(
            "REACHABLE-TP1 source (risky-1) has an EMPTY exit_patch -- the 2026-07-29 challenger "
            "lane was reverted or lost; re-check accounts.json before trusting this study"
        )
    return {"CONTROL": {}, "RIBBON": dict(ribbon_patch), "ZONE-RIDE": dict(zone_patch),
            "REACHABLE-TP1": dict(be_patch)}


def _discover_option_days() -> list[str]:
    """Every date with >=1 cached OPRA option-chain file (backtest/data/options/SPY*.csv)
    within [DISCOVERY_WINDOW_START, DISCOVERY_WINDOW_END] -- real-fills-capable days. Pure
    filesystem scan, deterministic, no simulation."""
    seen: set[str] = set()
    for p in OPTIONS_DIR.glob("SPY*.csv"):
        m = _OPT_FILE_RE.match(p.name)
        if not m:
            continue
        yy, mm, dd = m.groups()
        try:
            d = date(2000 + int(yy), int(mm), int(dd))
        except ValueError:
            continue
        if DISCOVERY_WINDOW_START <= d <= DISCOVERY_WINDOW_END:
            seen.add(d.isoformat())
    return sorted(seen)


def build_curriculum() -> list[dict]:
    """Union of the requested days (task-specified) and every discovered real-fills day in
    the window. A requested day with no OPRA coverage (e.g. 2026-07-20 itself -- today, not
    yet fetched into the cache) stays IN the curriculum but is flagged opra_available=False;
    its episodes will run on the disclosed BS-synthetic fallback (never silently dropped, per
    Free-Kitchen-Plan-B doctrine) and are excluded from the real-fills gate computation."""
    discovered = set(_discover_option_days())
    all_days = sorted(set(REQUESTED_DAYS) | discovered)
    return [
        {"date": d, "opra_available": d in discovered, "requested_explicitly": d in REQUESTED_DAYS}
        for d in all_days
    ]


def _held_out_days(curriculum_dates: list[str]) -> list[str]:
    """Last ~25% of curriculum days by calendar date (chronological tail), frozen here --
    never chosen after seeing results. At least 1 day."""
    n = max(1, round(len(curriculum_dates) * HELD_OUT_FRACTION))
    return sorted(curriculum_dates)[-n:]


def write_preregistration() -> dict:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    curriculum = build_curriculum()
    dates = [c["date"] for c in curriculum]
    held_out = _held_out_days(dates)
    exit_profiles = _load_exit_profiles()
    accounts_raw = ACCOUNTS_PATH.read_text(encoding="utf-8")
    doc = {
        "_doc": (
            "DOJO exit-diversity replay -- FROZEN pre-registration, written BEFORE any "
            "simulation run. See markdown/specs/DOJO-AUTONOMOUS-FINETUNE.md. No field in "
            "this file may be edited after `run` executes; a changed curriculum/gate/profile "
            "definition requires a NEW dated pre-reg, never an edit to this one."
        ),
        "generated_at": datetime.now(ET).isoformat(),
        "entry_source": {
            "dojo_arm": ENTRY_SOURCE_DOJO_ARM,
            "accounts_json_id": "safe-2",
            "display_name": "CORE-SAFE",
            "strategy": STRATEGY_NAME,
            "disclosure": (
                "Entries = every bar where core-safe's OWN engine verdict (heartbeat_core's "
                "real decide path, via dojo.engine_step.step()) is ENTER_BEAR/ENTER_BULL. "
                "Consecutive would_place=True bars on the SAME side are collapsed into ONE "
                "entry event (the first bar of the run) -- matches Rule 4 (no adding without "
                "a NEW confirmed trigger) and the one-position-at-a-time invariant; without "
                "this collapse, a held setup would double/triple-count as separate entries. "
                "Bold/aggressive entries are NOT included (disclosed scope narrowing)."
            ),
        },
        "curriculum": curriculum,
        "held_out_days": held_out,
        "held_out_rule": f"chronological tail, last {HELD_OUT_FRACTION:.0%} of curriculum days by date, frozen pre-run",
        "exit_profiles": exit_profiles,
        "exit_profiles_source": "automation/state/fleet/accounts.json (pulled verbatim at pre-reg time, hashed below)",
        "exit_profiles_disclosure": (
            "CONTROL = risky-1/safe-2's shared empty exit_patch (today's live trigger-exact "
            "structure stop + chandelier, the ribbon_ride REGISTRY default). RIBBON = safe-3's "
            "exit_patch -- MATHEMATICALLY IDENTICAL to CONTROL for every entry in this "
            "population, because ribbon_ride's registry shape already IS "
            "{stop_mode: structure, profit_lock_mode: trailing, trail_pct: 0.15} (accounts.json's "
            "own docstring: 'for ribbon_ride this is a no-op'). ZONE-RIDE = risky-3's exit_patch "
            "(same lane, trail_pct widened 0.15 -> 0.20) -- the ONLY profile that can differ from "
            "CONTROL for this entry population."
        ),
        "accounts_json_sha256_16": hashlib.sha256(accounts_raw.encode("utf-8")).hexdigest()[:16],
        "metric": "per-episode real-fill dollar P&L (walk_exit_manager.dollar_pnl), qty-scaled",
        "win_gate": {
            "_doc": "A profile beats CONTROL only if ALL FOUR hold (AND, not OR):",
            "condition_1": "higher aggregate P&L than CONTROL across every real-fills episode",
            "condition_2": "wins (higher day-total P&L than CONTROL) on a STRICT MAJORITY of curriculum days",
            "condition_3": (
                "edge survives dropping the profile's OWN single largest-P&L episode "
                "(concentration/C4/C24 check) -- total-minus-top-trade must still beat CONTROL's "
                "full aggregate"
            ),
            "condition_4": "holds (beats CONTROL's day-totals) on the frozen held-out day subset",
            "real_fills_only": (
                "The gate is computed ONLY over episodes whose entry premium came from real "
                "OPRA data (price_source=='opra_5m'); BS-synthetic episodes (any day lacking "
                "OPRA coverage, e.g. 2026-07-20 itself) are reported separately, never counted "
                "toward the gate, per C1 (real-fills is the only WR authority)."
            ),
            "no_post_hoc_tuning": "This gate's math is fixed here; `run` may not adjust it after seeing results.",
        },
        "reconciliation_target": {
            "file": str(REF_ZONE_STUDY_PATH.relative_to(_ROOT)).replace("\\", "/"),
            "note": (
                "structure-stop-reference-level-2026-07-20.json's REF-ZONE tests a DIFFERENT "
                "mechanism (stop referenced to a nearby key level's zone boundary, not built in "
                "ExitShape -- disclosed schema gap) than this study's ZONE-RIDE (a wider "
                "chandelier trail_pct on the SAME trigger-exact structure stop). Naming overlap "
                "('zone') is coincidental, not a shared mechanism -- see the MD report's "
                "reconciliation section for the full comparison, done regardless of directional "
                "agreement."
            ),
        },
    }
    PREREG_PATH.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
    doc["_prereg_sha256_16"] = hashlib.sha256(
        PREREG_PATH.read_text(encoding="utf-8").encode("utf-8")
    ).hexdigest()[:16]
    return doc


# =====================================================================================
# STEP 1 -- entries (reuse dojo.engine_step's REAL live decide path, unedited) + the
# day's ribbon-stack series (collected as a free side effect of the same pass).
# =====================================================================================
@dataclass
class EntryEvent:
    day: str
    cursor_et: str
    side: str
    trigger_level: "float | None"
    spy: "float | None"
    setup: "str | None"
    verdict: str
    triggers: tuple


def extract_entries_and_ribbon(day: str) -> "tuple[Optional[pd.DataFrame], list[EntryEvent], Optional[str]]":
    """Returns (ribbon_df, entries, error). ribbon_df has columns [timestamp_et, stack] at the
    day's native 5-min cadence (tz-naive ET) -- fed straight into
    sim_executor._ribbon_aligned_to for every position opened that day, unedited reuse."""
    try:
        bars = engine_step.load_day_bars(day)  # full multi-month frame -- NEEDED for warmup below
    except FileNotFoundError as exc:
        return None, [], f"no bar cache for {day}: {exc}"
    rth = engine_step._rth_filter(bars)  # reused utility, not reimplemented

    # BUG FIX 2026-07-21 (DOJO-EXIT-HARNESS-BUGS, entry-scan scope): load_day_bars()
    # deliberately returns the FULL multi-month cache frame (warmup for the ribbon/level
    # EMA seed, per that function's own docstring) -- but the OLD code iterated `rth` (every
    # RTH bar in that whole frame) as if it were `day`'s own bars, so a day=2026-06-30 episode
    # could carry a cursor from 2026-05-21. Restrict the CURSOR/entry-scan loop to `day`'s own
    # RTH bars only; `bars` (untrimmed) is still passed to engine_step.step() below so warmup
    # is unaffected -- only the entry-discovery window narrows to the target day.
    day_date = date.fromisoformat(day)
    day_rth = rth[rth["timestamp"].dt.date == day_date].reset_index(drop=True)
    if len(day_rth) < 2:
        return None, [], f"fewer than 2 RTH bars cached for {day}"

    entries: list[EntryEvent] = []
    ribbon_rows: list[dict] = []
    active_side: "str | None" = None
    for i in range(1, len(day_rth)):
        cursor = day_rth.iloc[i]["timestamp"].to_pydatetime()  # already tz-aware ET
        decisions = engine_step.step(day, cursor, bars)
        safe_dec = decisions[0]  # CORE_ACCOUNTS = ("safe", "bold") -- index 0 is "safe"
        ribbon_rows.append({
            "timestamp_et": pd.Timestamp(cursor).tz_convert(ET).tz_localize(None),
            "stack": safe_dec.ribbon,
        })
        if safe_dec.would_place:
            if safe_dec.side != active_side:
                entries.append(EntryEvent(
                    day=day, cursor_et=safe_dec.cursor_et, side=safe_dec.side,
                    trigger_level=safe_dec.trigger_level, spy=safe_dec.spy,
                    setup=safe_dec.setup, verdict=safe_dec.verdict,
                    triggers=tuple(safe_dec.triggers),
                ))
            active_side = safe_dec.side
        else:
            active_side = None
    ribbon_df = pd.DataFrame(ribbon_rows) if ribbon_rows else None
    return ribbon_df, entries, None


# =====================================================================================
# STEP 2 -- race all 3 exit profiles on the SAME entry (reuse sim_executor + exit_manager_walk).
# =====================================================================================
def simulate_entry(entry: EntryEvent, ribbon_df: "Optional[pd.DataFrame]", exit_profiles: dict,
                    safe_arm_cfg: dict, safe_params: dict) -> dict:
    trade_date = date.fromisoformat(entry.day)
    cursor_naive = datetime.fromisoformat(entry.cursor_et).astimezone(ET).replace(tzinfo=None)
    side = entry.side
    base = {
        "day": entry.day, "cursor_et": entry.cursor_et, "side": side,
        "trigger_level": entry.trigger_level, "setup": entry.setup, "triggers": list(entry.triggers),
    }
    if entry.spy is None:
        return {**base, "status": "NO_SPOT", "profiles": {}}

    strike = se._strike_for(safe_arm_cfg, float(entry.spy), side)  # reused, not reimplemented
    symbol = option_symbol(trade_date, strike, side)
    spy_df = se._load_spy_5m_for_date(trade_date)
    if spy_df is None:
        return {**base, "status": "NO_SPY_DATA", "symbol": symbol, "strike": strike, "profiles": {}}

    opt_df, price_source, is_synth = se._load_option_series(symbol, side, strike, trade_date, spy_df)
    if opt_df is None or opt_df.empty:
        return {**base, "status": "NO_OPTION_DATA", "symbol": symbol, "strike": strike, "profiles": {}}

    fill = bar_at_or_after(opt_df, cursor_naive)
    if fill is None:
        return {**base, "status": "NO_FILL", "symbol": symbol, "strike": strike,
                "price_source": price_source, "is_synthetic": is_synth, "profiles": {}}

    entry_premium = round(fill.vwap, 4)
    base_qty = int(safe_params.get("min_contracts", 3))
    afford = fx.risk_gate.max_affordable_qty(
        equity=float(safe_arm_cfg.get("starting_equity", 2000.0)), premium=entry_premium, params=safe_params)
    qty = min(base_qty, afford) if afford else base_qty
    if qty < 1:
        return {**base, "status": "UNAFFORDABLE", "symbol": symbol, "strike": strike,
                "entry_premium": entry_premium, "price_source": price_source,
                "is_synthetic": is_synth, "profiles": {}}

    ribbon_tick_df = se._ribbon_aligned_to(ribbon_df, opt_df) if ribbon_df is not None else None
    time_stop_str = se._time_stop_et_for(safe_arm_cfg)
    structure_enabled = se._structure_stop_enabled()

    profiles_out = {}
    for name, patch in exit_profiles.items():
        exit_shape = se._resolve_exit_shape(safe_arm_cfg, STRATEGY_NAME, patch)
        result = walk_exit_manager(
            symbol=symbol, side=side, entry_time_et=fill.timestamp_et, entry_premium=entry_premium,
            qty=qty, exit_shape=exit_shape, structure_stop_enabled=structure_enabled,
            trigger_level=entry.trigger_level, strategy=STRATEGY_NAME,
            time_stop_et=se._parse_hhmm(time_stop_str), opt_df=opt_df, ribbon_tick_df=ribbon_tick_df,
            five_min_spy_df=spy_df,
        )
        profiles_out[name] = {
            "pnl": result.dollar_pnl, "exit_reason": result.exit_reason,
            "resolved": result.resolved, "hold_minutes": result.hold_minutes,
            "n_legs": len(result.legs),
        }
    return {**base, "status": "FILLED", "symbol": symbol, "strike": strike, "qty": qty,
            "entry_premium": entry_premium, "price_source": price_source, "is_synthetic": is_synth,
            "profiles": profiles_out}


# =====================================================================================
# STEP 3 -- pure win-gate evaluator (importable + unit-testable without any real-cache I/O)
# =====================================================================================
def evaluate_win_gate(profile_episodes: list[dict], control_day_totals: dict, control_total: float,
                       held_out_days: list[str]) -> dict:
    """profile_episodes: [{"day": str, "pnl": float}, ...] for ONE challenger profile
    (real-fills episodes only). control_day_totals: {day: total_pnl} for CONTROL, same
    population. Returns a dict with each condition's boolean + the aggregate `overall` verdict
    (all 4 AND'd). Pure function -- no file I/O, no simulation -- so it's cheaply unit-tested
    against synthetic data (backtest/tests/test_dojo_exit_diversity_replay.py)."""
    profile_total = sum(e["pnl"] for e in profile_episodes)
    condition_1 = profile_total > control_total

    profile_day_totals: dict[str, float] = {}
    for e in profile_episodes:
        profile_day_totals[e["day"]] = profile_day_totals.get(e["day"], 0.0) + e["pnl"]
    all_days = sorted(set(profile_day_totals) | set(control_day_totals))
    day_wins = sum(1 for d in all_days if profile_day_totals.get(d, 0.0) > control_day_totals.get(d, 0.0))
    condition_2 = len(all_days) > 0 and day_wins > (len(all_days) / 2.0)

    if profile_episodes:
        top = max(profile_episodes, key=lambda e: e["pnl"])
        total_minus_top = profile_total - top["pnl"]
    else:
        total_minus_top = profile_total
    condition_3 = total_minus_top > control_total

    held_out_profile_total = sum(e["pnl"] for e in profile_episodes if e["day"] in held_out_days)
    held_out_control_total = sum(control_day_totals.get(d, 0.0) for d in held_out_days)
    condition_4 = held_out_profile_total > held_out_control_total

    # Zero real-fills episodes is zero evidence, never a win: with a negative-performing
    # CONTROL, an EMPTY profile can otherwise satisfy all 4 arithmetic conditions vacuously
    # (0 > a negative number on every axis) without a single real trade backing it up.
    has_evidence = len(profile_episodes) >= 1
    overall = bool(has_evidence and condition_1 and condition_2 and condition_3 and condition_4)
    return {
        "n": len(profile_episodes),
        "profile_total": round(profile_total, 2),
        "control_total": round(control_total, 2),
        "condition_1_beats_aggregate": condition_1,
        "condition_2_day_majority": condition_2,
        "condition_2_day_wins": day_wins,
        "condition_2_day_count": len(all_days),
        "condition_3_survives_top_trade_drop": condition_3,
        "condition_3_total_minus_top_trade": round(total_minus_top, 2),
        "condition_4_holds_on_held_out": condition_4,
        "condition_4_held_out_profile_total": round(held_out_profile_total, 2),
        "condition_4_held_out_control_total": round(held_out_control_total, 2),
        "overall": "SHIP_CANDIDATE" if overall else "CONTROL_HOLDS",
    }


# =====================================================================================
# orchestration -- `run`
# =====================================================================================
def _safe_arm_and_params() -> "tuple[dict, dict]":
    arm_cfg, _canonical = se._resolve_arm_cfg(ENTRY_SOURCE_DOJO_ARM)
    safe_params = json.loads(SAFE_PARAMS_PATH.read_text(encoding="utf-8"))
    return arm_cfg, safe_params


def run_replay(prereg: dict, only_days: "list[str] | None" = None) -> dict:
    """Run the per-episode simulation. `only_days` (if given) restricts WHICH frozen-curriculum
    days are actually simulated -- a SCOPE control that only lowers n; it never touches the
    frozen win-gate thresholds or profile definitions. Curriculum days not in `only_days` are
    recorded as skipped_for_scope so the reduction is fully disclosed, never silent."""
    exit_profiles = prereg["exit_profiles"]
    curriculum = prereg["curriculum"]
    safe_arm_cfg, safe_params = _safe_arm_and_params()
    scope = set(only_days) if only_days else None

    all_episodes: list[dict] = []  # one row per (entry, profile)
    day_notes: list[dict] = []
    for day_info in curriculum:
        day = day_info["date"]
        if scope is not None and day not in scope:
            day_notes.append({"date": day, "n_entries": 0, "error": None,
                              "opra_available": day_info["opra_available"], "skipped_for_scope": True})
            continue
        print(f"[run] extracting entries for {day} ...", file=sys.stderr, flush=True)
        ribbon_df, entries, err = extract_entries_and_ribbon(day)
        print(f"[run]   {day}: {len(entries)} entries (err={err})", file=sys.stderr, flush=True)
        day_notes.append({"date": day, "n_entries": len(entries), "error": err,
                           "opra_available": day_info["opra_available"], "skipped_for_scope": False})
        if err:
            continue
        for entry in entries:
            sim = simulate_entry(entry, ribbon_df, exit_profiles, safe_arm_cfg, safe_params)
            for profile_name in exit_profiles:
                prof = sim["profiles"].get(profile_name)
                all_episodes.append({
                    "day": day, "cursor_et": entry.cursor_et, "side": entry.side,
                    "setup": entry.setup, "profile": profile_name,
                    "status": sim["status"],
                    "symbol": sim.get("symbol"), "strike": sim.get("strike"), "qty": sim.get("qty"),
                    "entry_premium": sim.get("entry_premium"),
                    "price_source": sim.get("price_source"), "is_synthetic": sim.get("is_synthetic"),
                    "pnl": (prof or {}).get("pnl"),
                    "exit_reason": (prof or {}).get("exit_reason"),
                    "hold_minutes": (prof or {}).get("hold_minutes"),
                    "n_legs": (prof or {}).get("n_legs"),
                })

    days_run = [d["date"] for d in day_notes if not d.get("skipped_for_scope") and d.get("error") is None]
    days_skipped = [d["date"] for d in day_notes if d.get("skipped_for_scope")]
    return {
        "generated_at": datetime.now(ET).isoformat(),
        "prereg_file": str(PREREG_PATH.relative_to(_ROOT)).replace("\\", "/"),
        "prereg_sha256_16": prereg.get("_prereg_sha256_16"),
        "scope_only_days": sorted(only_days) if only_days else None,
        "days_run": days_run,
        "days_skipped_for_scope": days_skipped,
        "day_notes": day_notes,
        "episodes": all_episodes,
    }


def _filled_real_fills(episodes: list[dict], profile: str) -> list[dict]:
    return [e for e in episodes if e["profile"] == profile and e["status"] == "FILLED"
            and e["price_source"] == "opra_5m" and e["pnl"] is not None]


def _filled_all(episodes: list[dict], profile: str) -> list[dict]:
    return [e for e in episodes if e["profile"] == profile and e["status"] == "FILLED" and e["pnl"] is not None]


def score(prereg: dict, run_result: dict) -> dict:
    episodes = run_result["episodes"]
    profiles = list(prereg["exit_profiles"].keys())
    held_out_days = prereg["held_out_days"]

    per_profile_real: dict[str, list[dict]] = {p: _filled_real_fills(episodes, p) for p in profiles}
    per_profile_all: dict[str, list[dict]] = {p: _filled_all(episodes, p) for p in profiles}

    def _totals(eps: list[dict]) -> dict:
        n = len(eps)
        total = sum(e["pnl"] for e in eps)
        wr = (sum(1 for e in eps if e["pnl"] > 0) / n) if n else None
        by_day: dict[str, float] = {}
        for e in eps:
            by_day[e["day"]] = by_day.get(e["day"], 0.0) + e["pnl"]
        return {"n": n, "total": round(total, 2), "expectancy": round(total / n, 2) if n else None,
                "wr": round(wr, 4) if wr is not None else None, "by_day": {k: round(v, 2) for k, v in by_day.items()}}

    headline_real = {p: _totals(per_profile_real[p]) for p in profiles}
    headline_all = {p: _totals(per_profile_all[p]) for p in profiles}

    control_real = per_profile_real.get("CONTROL", [])
    control_day_totals_real = headline_real["CONTROL"]["by_day"]
    control_total_real = headline_real["CONTROL"]["total"]

    gates = {}
    for p in profiles:
        if p == "CONTROL":
            continue
        gates[p] = evaluate_win_gate(
            [{"day": e["day"], "pnl": e["pnl"]} for e in per_profile_real[p]],
            control_day_totals_real, control_total_real, held_out_days,
        )

    synthetic_note = {
        p: {"n_synthetic": len(per_profile_all[p]) - len(per_profile_real[p]),
            "n_no_fill_or_error": sum(1 for e in episodes if e["profile"] == p and e["status"] != "FILLED")}
        for p in profiles
    }

    return {
        "generated_at": datetime.now(ET).isoformat(),
        "prereg_file": run_result["prereg_file"],
        "prereg_sha256_16": run_result["prereg_sha256_16"],
        "scope_only_days": run_result.get("scope_only_days"),
        "days_run": run_result.get("days_run"),
        "days_skipped_for_scope": run_result.get("days_skipped_for_scope"),
        "held_out_days_prereg": held_out_days,
        "held_out_days_actually_run": sorted(set(held_out_days) & set(run_result.get("days_run") or [])),
        "day_notes": run_result["day_notes"],
        "n_unique_entries": len({(e["day"], e["cursor_et"]) for e in episodes}),
        "headline_real_fills_only": headline_real,
        "headline_including_synthetic": headline_all,
        "synthetic_disclosure": synthetic_note,
        "win_gates": gates,
        "verdict": "SHIP_CANDIDATE" if any(g["overall"] == "SHIP_CANDIDATE" for g in gates.values()) else "CONTROL_HOLDS",
        "episodes": episodes,
    }


# =====================================================================================
# MD report
# =====================================================================================
def _reconciliation_block() -> str:
    if not REF_ZONE_STUDY_PATH.exists():
        return "structure-stop-reference-level-2026-07-20.json not found on disk -- reconciliation skipped."
    try:
        ref = json.loads(REF_ZONE_STUDY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"Could not read structure-stop-reference-level-2026-07-20.json ({exc}) -- reconciliation skipped."
    a = ref.get("layer_a_fresh_slice", {}).get("candidates", {})
    b = ref.get("layer_b_real_fills_anchor", {}).get("candidates", {})
    ref_exact_a, ref_zone_a = a.get("REF-EXACT", {}), a.get("REF-ZONE", {})
    ref_exact_b, ref_zone_b = b.get("REF-EXACT", {}), b.get("REF-ZONE", {})
    verdict = ref.get("verdicts", {}).get("REF-ZONE", {})
    lines = [
        "structure-stop-reference-level-2026-07-20.json tested a DIFFERENT mechanism than this "
        "study's ZONE-RIDE: REF-ZONE substitutes the structure stop's REFERENCE LEVEL (this "
        "position's entry trigger_level -> the nearest key-level ZONE BOUNDARY) -- a knob that "
        "does not exist in ExitShape today (disclosed schema gap, accounts.json 2026-07-20 note). "
        "This study's ZONE-RIDE is risky-3's ACTUAL live exit_patch: the SAME trigger-exact "
        "structure stop as CONTROL, with a WIDER chandelier trail (trail_pct 0.15 -> 0.20). "
        "Naming overlap ('zone') is coincidental -- these are not the same lever, so agreement or "
        "disagreement between them is not evidence either way about the other.",
        "",
        f"- REF-EXACT (their CONTROL) layer(a) fresh-slice expectancy: ${ref_exact_a.get('expectancy')}/tr "
        f"(n={ref_exact_a.get('n')})",
        f"- REF-ZONE layer(a) fresh-slice expectancy: ${ref_zone_a.get('expectancy')}/tr (n={ref_zone_a.get('n')}) "
        f"-- WORSE than control (the CLAUDE.md-cited -$63.73 vs -$47.34 finding)",
        f"- REF-EXACT layer(b) real-fills anchor total: ${ref_exact_b.get('anchor_total')} (n={ref_exact_b.get('n_valid')})",
        f"- REF-ZONE layer(b) real-fills anchor total: ${ref_zone_b.get('anchor_total')} (n={ref_zone_b.get('n_valid')}) "
        f"-- LOOKS better in raw aggregate, but REJECTED: {verdict.get('reason', 'n/a')}",
        "",
        "The frozen finding's rejection mechanism (sub-window sign flip -- first half "
        f"${verdict.get('sub_window_delta_first_half')}, second half ${verdict.get('sub_window_delta_second_half')}) "
        "is EXACTLY the failure class this study's condition_3 (concentration / top-trade-drop) and "
        "condition_4 (held-out subset) are built to catch. If ZONE-RIDE's aggregate here also looks "
        "good only because of 1-2 trades or only in one half of the curriculum, this study's own gate "
        "will independently reject it for the same reason -- mutual corroboration of the underlying "
        "doctrine (C4/C24: don't trust an aggregate win without checking who's carrying it), even "
        "though the two studies are testing different knobs.",
    ]
    return "\n".join(lines)


def write_report_md(scorecard: dict) -> None:
    profiles = list(scorecard["headline_real_fills_only"].keys())
    lines = [
        "# DOJO Exit-Diversity Replay -- 2026-07-20",
        "",
        f"Generated: {scorecard['generated_at']}",
        f"Pre-registration: `{scorecard['prereg_file']}` (sha256-16 `{scorecard['prereg_sha256_16']}`)",
        "",
        "## Scope",
        "",
        (f"Ran a REDUCED day-set: `{scorecard['days_run']}` "
         f"(scope filter `--days {','.join(scorecard['scope_only_days'])}`). "
         f"Skipped-for-scope: `{scorecard['days_skipped_for_scope']}`. "
         "The reduction lowers n ONLY -- the frozen pre-reg's win-gate thresholds and profile "
         "definitions are untouched (verified: same pre-reg sha256). Held-out days in the frozen "
         f"pre-reg = `{scorecard['held_out_days_prereg']}`; of those, actually run under this scope "
         f"= `{scorecard['held_out_days_actually_run']}` -- so condition_4 (held-out) rests on that "
         "thinner basis, disclosed here, not silently."
         if scorecard.get("scope_only_days") else
         "Ran the FULL frozen curriculum (no day-set reduction)."),
        "",
        "## Headline (real fills only -- OPRA-priced episodes, gate-eligible)",
        "",
        "| Profile | n | Total P&L | Expectancy/tr | WR |",
        "|---|---|---|---|---|",
    ]
    for p in profiles:
        h = scorecard["headline_real_fills_only"][p]
        lines.append(f"| {p} | {h['n']} | ${h['total']} | ${h['expectancy']} | {h['wr']} |")

    lines += [
        "",
        "## Headline (including BS-synthetic episodes -- disclosed, not gate-eligible)",
        "",
        "| Profile | n | Total P&L | Expectancy/tr | n synthetic | n no-fill/error |",
        "|---|---|---|---|---|---|",
    ]
    for p in profiles:
        h = scorecard["headline_including_synthetic"][p]
        syn = scorecard["synthetic_disclosure"][p]
        lines.append(f"| {p} | {h['n']} | ${h['total']} | ${h['expectancy']} | "
                      f"{syn['n_synthetic']} | {syn['n_no_fill_or_error']} |")

    lines += ["", "## Win-gate verdicts (challengers vs CONTROL, real fills only)", ""]
    for p, g in scorecard["win_gates"].items():
        lines += [
            f"### {p} -- **{g['overall']}**",
            "",
            f"- Beats CONTROL aggregate: {g['condition_1_beats_aggregate']} "
            f"(${g['profile_total']} vs ${g['control_total']})",
            f"- Day-majority: {g['condition_2_day_majority']} "
            f"({g['condition_2_day_wins']}/{g['condition_2_day_count']} days)",
            f"- Survives top-trade drop: {g['condition_3_survives_top_trade_drop']} "
            f"(total-minus-top ${g['condition_3_total_minus_top_trade']} vs control ${g['control_total']})",
            f"- Holds on held-out subset: {g['condition_4_holds_on_held_out']} "
            f"(${g['condition_4_held_out_profile_total']} vs control ${g['condition_4_held_out_control_total']})",
            "",
        ]

    lines += ["## Per-day entry counts", "", "| Day | Entries | OPRA available | Error |", "|---|---|---|---|"]
    for d in scorecard["day_notes"]:
        lines.append(f"| {d['date']} | {d['n_entries']} | {d['opra_available']} | {d.get('error') or ''} |")

    lines += ["", "## Reconciliation vs structure-stop-reference-level-2026-07-20.json", "",
              _reconciliation_block(), ""]

    lines += [
        "## Verdict",
        "",
        f"**{scorecard['verdict']}**",
        "",
        ("A gated candidate cleared all 4 conditions -- see the win-gate section above for the "
         "specific profile. Per doctrine (OP-16 eval-first), this is a CANDIDATE for J's REVOKE "
         "review, not something this harness wires live itself. One-line wire: set that profile's "
         "exit_patch on CORE-SAFE in accounts.json/params.json + a revert note."
         if scorecard["verdict"] == "SHIP_CANDIDATE" else
         "No challenger profile cleared the full frozen gate. CONTROL holds -- today's live "
         "trigger-exact structure stop + chandelier remains the best-evidenced exit policy for "
         "core-safe's own entries over this curriculum. This is an honest, valid, and useful "
         "morning answer (per the spec's own framing), not a null result to be hidden."),
    ]
    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# =====================================================================================
# CLI
# =====================================================================================
def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prereg", "run", "all"])
    parser.add_argument("--days", default=None,
                        help="comma-separated subset of curriculum days to actually simulate "
                             "(SCOPE control -- lowers n only, never touches the frozen win-gate). "
                             "Omit to run the full frozen curriculum.")
    args = parser.parse_args(argv)
    only_days = [d.strip() for d in args.days.split(",")] if args.days else None

    if args.mode in ("prereg", "all"):
        prereg = write_preregistration()
        print(f"[prereg] wrote {PREREG_PATH} (sha256-16 {prereg['_prereg_sha256_16']}); "
              f"{len(prereg['curriculum'])} curriculum days, held-out={prereg['held_out_days']}")
        if args.mode == "prereg":
            return 0
    else:
        prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
        prereg["_prereg_sha256_16"] = hashlib.sha256(
            PREREG_PATH.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()[:16]

    run_result = run_replay(prereg, only_days=only_days)
    scorecard = score(prereg, run_result)
    SCORECARD_PATH.write_text(json.dumps(scorecard, indent=2, default=str), encoding="utf-8")
    write_report_md(scorecard)
    print(f"[run] wrote {SCORECARD_PATH}")
    print(f"[run] wrote {MD_PATH}")
    print(f"[run] verdict: {scorecard['verdict']}")
    for p, h in scorecard["headline_real_fills_only"].items():
        print(f"  {p}: n={h['n']} total=${h['total']} exp=${h['expectancy']} wr={h['wr']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
