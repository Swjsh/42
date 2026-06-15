"""Detection module — Phase 3 (real orchestrator replay).

Replays today's RTH bars through the actual heartbeat orchestrator
(`lib.filters.evaluate_bearish_setup` + `evaluate_bullish_setup`) and emits
an EngineDecision per bar. This is the ground-truth measure of "what would the
engine have done at this bar?" — replacing the Phase 2 hand-rolled
ribbon+vol+body heuristic that produced lots of false-positive blocked
candidates.

Output (drop-in compatible with main.py):
  - CategoryScore with score 0..100
  - evidence['engine_decisions'] = list[dict] (one per RTH bar)
  - evidence['verdict']         = PERFECT | OVER_AGGRESSIVE | TOO_PASSIVE
                                  | INTRADAY_INCONSISTENT | NO_DATA
  - evidence['phase']           = "3.0" so downstream knows we're in real-replay

Verdict semantics:
  PERFECT       : engine ENTERED at the same bar J's actual entry happened, and
                  no spurious ENTERs elsewhere.
  OVER_AGGRESSIVE: engine produced ENTER decisions at bars where no trade
                  actually fired (would have churned the account).
  TOO_PASSIVE   : engine never produced an ENTER on a day where a real trade
                  fired and won (missed the setup).
  INTRADAY_INCONSISTENT: engine fired AT the actual entry bar AND also fired
                  spurious ENTERs at other bars (mixed).
  NO_DATA       : no today data found (CSV missing, etc).

Performance: must complete in <30s for 78 RTH bars. Uses the same
compute_ribbon_cached + vectorized_features_for_all_bars primitives as
forensics so the heavy ribbon/EMA pass is cached.
"""
from __future__ import annotations

import datetime as dt
import sys
import warnings
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from ..schema import CategoryScore
from ..ingest import IngestedData
from ._bar_features import (
    compute_ribbon_cached,
    compute_vol_baseline,
    vectorized_features_for_all_bars,
)

REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
# REPO = C:\Users\jackw\Desktop\42

DATA_DIR = REPO / "backtest" / "data"

# Add backtest dir to sys.path so `lib.*` imports resolve when this module is
# loaded by the EOD deep-dive runner (which doesn't otherwise put backtest on path).
sys.path.insert(0, str(REPO / "backtest"))

# Imports from lib.* — same engine the live heartbeat / production backtest uses.
try:
    from lib.filters import (  # noqa: E402
        BarContext,
        LevelState,
        evaluate_bearish_setup,
        evaluate_bullish_setup,
        vol_baseline_20bar,
        range_baseline_20bar,
    )
    from lib.ribbon import compute_ribbon, ribbon_at  # noqa: E402
    from lib.levels import _detect_from_history  # noqa: E402
    from lib.orchestrator import (  # noqa: E402
        _precompute_htf_15m_stacks,
        _update_level_states,
    )
    ENGINE_AVAILABLE = True
except Exception as _e_imp:  # pragma: no cover — defensive only
    ENGINE_AVAILABLE = False
    _IMPORT_ERROR = f"{type(_e_imp).__name__}: {_e_imp}"


# ── v15 default thresholds (matches automation/state/params.json contract) ─────
# Caller (main.py) doesn't pass overrides today; these match the live-engine defaults.
# 2026-05-14 evening fix: V15_NO_TRADE_BEFORE was hardcoded to dt.time(10, 0)
# which was the v14 value. v15 (LIVE since 5/13 evening per heartbeat.md L307+329)
# moved entry gate to 09:35 ET. The stale 10:00 value caused detection.py to
# falsely classify today's 09:58 ENTER_BULL as TOO_PASSIVE (verdict score 40)
# when in fact v15 ALLOWS entries from 09:35 onward. Fix: read v15's actual
# value from heartbeat.md or hardcode the correct value here. Future: read from
# automation/state/params.json#v15_entry_gate_et if/when that field exists.
V15_NO_TRADE_BEFORE = dt.time(9, 35)               # filter 1 (v15.1 09:35 ET, was 10:00 in v14)
V15_NO_TRADE_AFTER = dt.time(15, 0)                # NEW v15.1 (was 15:50): theta protection. Existing positions still flatten by 15:50 ET hard time stop.
V15_NO_TRADE_WINDOW = None                          # v15.1 REMOVED (was (14:00, 15:00) v11-v15 mid-day blackout — J 2026-05-14 evening: "any time between 9:35 - and 3pm is fair game for ENTRIES")
V15_F9_VOL_MULT = 0.7
V15_BEAR_MIN_TRIGGERS = 1                          # asymmetric
V15_BULL_MIN_TRIGGERS = 2
RTH_END = dt.time(16, 0)


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_master_spy_today(date_str: str) -> Optional[pd.DataFrame]:
    """Load SPY master CSV with today's bars merged in.

    Mirrors forensics._load_master_with_features behaviour: master CSV ends
    2026-05-12; daily-window CSVs (spy_5m_2026-*.csv) carry newer days.
    """
    # Master CSV (16-month window through 2026-05-12).
    master_path = DATA_DIR / "spy_5m_2025-01-01_2026-05-12.csv"
    dfs = []
    if master_path.exists():
        try:
            df = pd.read_csv(master_path)
            df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True)
            df["timestamp_et"] = df["timestamp_et"].dt.tz_convert("America/New_York")
            df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)
            dfs.append(df)
        except Exception:
            pass

    # Newer daily-window CSVs that contain target_date
    for csv_path in sorted(DATA_DIR.glob("spy_5m_2026-*.csv"), reverse=True):
        try:
            df = pd.read_csv(csv_path)
            df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True)
            df["timestamp_et"] = df["timestamp_et"].dt.tz_convert("America/New_York")
            df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)
            if date_str in df["timestamp_et"].dt.date.astype(str).values:
                dfs.append(df)
                break
        except Exception:
            continue

    if not dfs:
        return None

    spy = pd.concat(dfs, ignore_index=True)
    spy = spy.drop_duplicates(subset=["timestamp_et"], keep="last")
    spy = spy.sort_values("timestamp_et").reset_index(drop=True)
    spy["date"] = spy["timestamp_et"].dt.date
    return spy


def _load_vix_aligned(spy_df: pd.DataFrame) -> pd.Series:
    """Load VIX 5m bars and align them onto SPY's bar index (forward-fill).

    Returns a Series the same length as spy_df with VIX close per SPY bar.
    """
    # Find any VIX CSV in data dir; pick the one that covers spy_df's date range
    vix_candidates = sorted(DATA_DIR.glob("vix_5m_*.csv"), reverse=True)
    if not vix_candidates:
        return pd.Series([18.0] * len(spy_df), index=range(len(spy_df)))

    vix_dfs = []
    for vix_path in vix_candidates:
        try:
            v = pd.read_csv(vix_path)
            v["timestamp_et"] = pd.to_datetime(v["timestamp_et"], utc=True)
            vix_dfs.append(v)
        except Exception:
            continue
    if not vix_dfs:
        return pd.Series([18.0] * len(spy_df), index=range(len(spy_df)))
    vix = pd.concat(vix_dfs, ignore_index=True)
    vix = vix.drop_duplicates(subset=["timestamp_et"], keep="last")
    vix = vix.sort_values("timestamp_et").reset_index(drop=True)

    # Reindex VIX onto SPY's timestamp index (forward-fill).
    # CRITICAL: both indexes must be the same tz-awareness (both naive OR both
    # tz-aware in the same tz). spy_df["timestamp_et"] was tz-stripped to naive ET
    # in _load_master_spy_today; do the same to VIX before reindex.
    spy_ts = pd.to_datetime(spy_df["timestamp_et"])
    if spy_ts.dt.tz is not None:
        spy_ts = spy_ts.dt.tz_convert("America/New_York").dt.tz_localize(None)

    vix_ts = vix["timestamp_et"]
    if vix_ts.dt.tz is not None:
        vix_ts = vix_ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    else:
        vix_ts = pd.to_datetime(vix_ts)

    vix_indexed = pd.Series(vix["close"].values, index=vix_ts)
    if not vix_indexed.index.is_unique:
        vix_indexed = vix_indexed[~vix_indexed.index.duplicated(keep="first")]
    vix_indexed = vix_indexed.sort_index()

    aligned_values = vix_indexed.reindex(spy_ts.values, method="ffill").values
    aligned = pd.Series(aligned_values, index=range(len(spy_df))).fillna(18.0)
    return aligned


# ─────────────────────────────────────────────────────────────────────────────
# Trade timeline extraction
# ─────────────────────────────────────────────────────────────────────────────

def _trade_windows_from_trades(trades) -> list[dict]:
    """Build active-position windows from trade fills (entry → last exit)."""
    windows = []
    for t in trades:
        buy_fills = [f for f in t.fills if f.side == "buy"]
        sell_fills = [f for f in t.fills if f.side == "sell"]
        if not buy_fills:
            continue
        try:
            entry_min = _hhmm_to_min_from_open(buy_fills[0].time_et)
        except (ValueError, AttributeError):
            continue
        if sell_fills:
            try:
                exit_min = _hhmm_to_min_from_open(sell_fills[-1].time_et)
            except (ValueError, AttributeError):
                exit_min = 380  # 15:50 hard close
        else:
            exit_min = 380
        windows.append({
            "trade_id": t.id,
            "direction": getattr(t, "direction", "long"),
            "setup_name": getattr(t, "setup_name", "UNKNOWN"),
            "entry_min": entry_min,
            "exit_min": exit_min,
        })
    return windows


def _hhmm_to_min_from_open(time_str: str) -> int:
    """Convert "HH:MM:SS" → minutes from 09:30 ET (negative if before)."""
    parts = time_str.split(":")
    hh = int(parts[0])
    mm = int(parts[1])
    return (hh - 9) * 60 + mm - 30


def _bar_min_from_open(ts: pd.Timestamp) -> int:
    """Bar timestamp → minutes from 09:30 ET."""
    return (int(ts.hour) - 9) * 60 + int(ts.minute) - 30


# ─────────────────────────────────────────────────────────────────────────────
# Engine replay — main loop
# ─────────────────────────────────────────────────────────────────────────────

def _replay_today_bars(
    spy_full_df: pd.DataFrame,
    date_str: str,
    trade_windows: list[dict],
) -> tuple[list[dict], dict]:
    """Replay the engine over today's RTH bars; return (decisions, summary).

    decisions: list of EngineDecision-shaped dicts, one per RTH bar.
    summary: counts of each decision type + setup-fire bars + comparison metrics.
    """
    if not ENGINE_AVAILABLE:
        return [], {"error": f"engine import failed: {_IMPORT_ERROR}"}

    decisions: list[dict] = []
    summary = {
        "total_bars": 0,
        "n_enter_decisions": 0,
        "n_skip_decisions": 0,
        "n_hold_decisions": 0,
        "n_in_position_decisions": 0,
        "engine_entry_bars": [],   # list of "HH:MM" where engine would have ENTERed
        "actual_entry_bars": [w["entry_min"] for w in trade_windows],
    }

    # Compute ribbon + VIX once over the full SPY df (warmup matters)
    target_date = pd.to_datetime(date_str).date()
    spy_full_df = spy_full_df.copy()
    spy_full_df["timestamp_et"] = pd.to_datetime(spy_full_df["timestamp_et"])
    if spy_full_df["timestamp_et"].dt.tz is not None:
        spy_full_df["timestamp_et"] = spy_full_df["timestamp_et"].dt.tz_localize(None)
    spy_full_df["date"] = spy_full_df["timestamp_et"].dt.date

    # RTH-only df for ribbon + filter eval (matches orchestrator semantics)
    rth_mask = (
        (spy_full_df["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_full_df["timestamp_et"].dt.time < dt.time(16, 0))
    )
    spy_rth = spy_full_df.loc[rth_mask].reset_index(drop=True)
    if spy_rth.empty:
        return [], {"error": "no RTH bars"}

    # Ribbon over RTH-only bars (matches live indicator)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        warnings.simplefilter("ignore", category=DeprecationWarning)
        ribbon_df = compute_ribbon(spy_rth["close"])
        vix_aligned = _load_vix_aligned(spy_rth)
        htf_stacks = _precompute_htf_15m_stacks(spy_rth)

    # Identify today's RTH bar indices in the RTH df
    today_mask = spy_rth["timestamp_et"].dt.date == target_date
    today_idxs = spy_rth.index[today_mask].tolist()
    if not today_idxs:
        return [], {"error": f"no RTH bars for {date_str}"}

    # Per-level state across today's bars (shared mutable dict — same as orchestrator)
    level_states: dict = {}
    in_position_until_min: dict[str, int] = {}  # direction → exit_min if active

    for idx in today_idxs:
        try:
            bar = spy_rth.iloc[idx]
            bar_time = bar["timestamp_et"]
            bar_min = _bar_min_from_open(bar_time)
            time_label = bar_time.strftime("%H:%M:%S")
            summary["total_bars"] += 1

            # Position-active check (engine wouldn't re-enter)
            active_directions: list[str] = []
            for tw in trade_windows:
                if tw["entry_min"] <= bar_min <= tw["exit_min"]:
                    active_directions.append(tw["direction"])
            in_position = len(active_directions) > 0

            # Build BarContext (engine's eval input)
            ribbon_state = ribbon_at(ribbon_df, idx)
            if ribbon_state is None:
                decisions.append({
                    "time_et": time_label,
                    "tick_or_fire_id": idx,
                    "decision": "SKIP_RIBBON_WARMUP",
                    "reasoning": "ribbon EMAs not yet warmed up at this bar",
                    "raw_state": {
                        "in_position": in_position,
                        "bar_min_from_open": bar_min,
                    },
                })
                summary["n_skip_decisions"] += 1
                continue

            ribbon_history = []
            for j in range(max(0, idx - 4), idx + 1):
                rs = ribbon_at(ribbon_df, j)
                ribbon_history.append(rs)

            try:
                # 2026-05-14 v15.1 fix (PHASE3-VIX-THREADING): vix_prior was reading
                # bar(N-1) which is 5 min apart. Today's CSV showed deltas of ±0.00-0.04
                # = below the 0.05 deadband in vix_direction() → always "flat" → BULL
                # filter L8 always failed → engine never produced ENTER even though
                # production heartbeat at 09:58 saw vix=17.9(falling) and entered.
                # Production uses TV quote_get with up-to-10min cache, so its delta
                # window is 5-10 min. Match that with a 3-bar (15min) lookback here
                # so vix_direction has enough delta to register rising/falling.
                vix_now = float(vix_aligned.iloc[idx])
                vix_prior_idx = max(0, idx - 3)  # 15min lookback (was 5min) — see comment above
                vix_prior = float(vix_aligned.iloc[vix_prior_idx])
            except (IndexError, KeyError):
                vix_now = vix_prior = 18.0

            # Baselines (vectorised on RTH-only df)
            vol_baseline = vol_baseline_20bar(spy_rth, idx)
            range_baseline = range_baseline_20bar(spy_rth, idx)

            # Levels — use FULL spy data (incl. premarket) so PMH/PML detected
            full_history = spy_full_df[spy_full_df["timestamp_et"] <= bar_time]
            level_set = _detect_from_history(full_history, target_date)

            # Update per-level state for sequence_rejection trigger
            _update_level_states(level_states, level_set.active, bar, idx)

            htf_stack = htf_stacks[idx] if idx < len(htf_stacks) else None

            ctx = BarContext(
                bar_idx=idx,
                timestamp_et=bar_time.to_pydatetime(),
                bar=bar,
                prior_bars=spy_rth,
                ribbon_now=ribbon_state,
                ribbon_history=ribbon_history,
                vix_now=vix_now,
                vix_prior=vix_prior,
                vol_baseline_20=vol_baseline,
                range_baseline_20=range_baseline,
                levels_active=level_set.active,
                multi_day_levels=level_set.multi_day,
                htf_15m_stack=htf_stack,
                level_states=level_states,
            )

            # Run BOTH bear + bull evaluations (mirrors orchestrator)
            bear_result = evaluate_bearish_setup(
                ctx,
                min_triggers=V15_BEAR_MIN_TRIGGERS,
                no_trade_before=V15_NO_TRADE_BEFORE,
                no_trade_window=V15_NO_TRADE_WINDOW,
                f9_vol_mult=V15_F9_VOL_MULT,
            )
            bull_result = evaluate_bullish_setup(
                ctx,
                min_triggers=V15_BULL_MIN_TRIGGERS,
                no_trade_before=V15_NO_TRADE_BEFORE,
                no_trade_window=V15_NO_TRADE_WINDOW,
                f10_vol_mult=V15_F9_VOL_MULT,
            )

            # Decide what the engine would have done at this bar
            decision, reasoning = _classify_decision(
                bear_result=bear_result,
                bull_result=bull_result,
                in_position=in_position,
                active_directions=active_directions,
                bar_min=bar_min,
            )

            decisions.append({
                "time_et": time_label,
                "tick_or_fire_id": idx,
                "decision": decision,
                "reasoning": reasoning,
                "raw_state": {
                    "spy_close": float(bar["close"]),
                    "vix": vix_now,
                    "ribbon_stack": ribbon_state.stack,
                    "ribbon_spread_cents": ribbon_state.spread_cents,
                    "htf_15m_stack": htf_stack,
                    "bear_score": bear_result.bear_score,
                    "bull_score": bull_result.bull_score,
                    "bear_blockers": list(bear_result.blockers),
                    "bull_blockers": list(bull_result.blockers),
                    "bear_triggers": list(bear_result.triggers_fired),
                    "bull_triggers": list(bull_result.triggers_fired),
                    "rejection_level": bear_result.rejection_level,
                    "reclaim_level": bull_result.reclaim_level,
                    "in_position": in_position,
                    "active_directions": active_directions,
                    "bar_min_from_open": bar_min,
                },
            })

            if decision.startswith("ENTER"):
                summary["n_enter_decisions"] += 1
                summary["engine_entry_bars"].append(bar_min)
            elif decision.startswith("SKIP"):
                summary["n_skip_decisions"] += 1
                if "FIRST_ENTRY_LOCK" in decision or "POSITION" in decision:
                    summary["n_in_position_decisions"] += 1
            else:
                summary["n_hold_decisions"] += 1

        except Exception as e:
            # Per-bar errors must not crash the whole replay — emit a HOLD_ERROR
            # decision so the bar count stays consistent and main.py still has
            # a complete trace.
            decisions.append({
                "time_et": str(bar["timestamp_et"])[11:19] if "bar" in dir() else "??:??:??",
                "tick_or_fire_id": idx,
                "decision": "HOLD_ERROR",
                "reasoning": f"per-bar replay raised: {type(e).__name__}: {e}",
                "raw_state": {},
            })
            summary["n_hold_decisions"] += 1

    return decisions, summary


def _classify_decision(
    bear_result,
    bull_result,
    in_position: bool,
    active_directions: list[str],
    bar_min: int,
) -> tuple[str, str]:
    """Map a bear/bull eval pair + position state to (decision, reasoning).

    Returns one of:
      ENTER_BULL / ENTER_BEAR
      SKIP_FIRST_ENTRY_LOCK
      SKIP_TIME_GATE   (filter 1 blocked by no_trade_before / no_trade_window)
      SKIP_RIBBON      (filter 5 blocked — wrong stack)
      SKIP_VIX         (filter 8 blocked)
      SKIP_TRIGGERS    (filter 10/11 — not enough triggers)
      SKIP_FILTER_<n>  (any other filter blocked)
      SKIP_TIE         (both bull + bear passed with same trigger count — ambiguous)
      HOLD             (no setup fired, no clear blocker reason)
    """
    bear_passed = bear_result.passed
    bull_passed = bull_result.passed

    # Engaged in trade → first_entry_lock semantics (orchestrator skips re-entry)
    if in_position and (bear_passed or bull_passed):
        return (
            "SKIP_FIRST_ENTRY_LOCK",
            f"engine is in active position (directions={active_directions}); first_entry_lock blocks re-entry"
        )
    if in_position:
        return (
            "HOLD_IN_POSITION",
            f"engine in active position (directions={active_directions}); no new setup either"
        )

    # Both passed → pick higher-trigger side, else SKIP_TIE
    if bear_passed and bull_passed:
        if len(bear_result.triggers_fired) > len(bull_result.triggers_fired):
            return (
                "ENTER_BEAR",
                f"both setups passed; bear wins on trigger count "
                f"({len(bear_result.triggers_fired)} > {len(bull_result.triggers_fired)}). "
                f"triggers={bear_result.triggers_fired}, level={bear_result.rejection_level}"
            )
        elif len(bull_result.triggers_fired) > len(bear_result.triggers_fired):
            return (
                "ENTER_BULL",
                f"both setups passed; bull wins on trigger count. "
                f"triggers={bull_result.triggers_fired}, level={bull_result.reclaim_level}"
            )
        else:
            return (
                "SKIP_TIE",
                f"both bear+bull passed with equal trigger count {len(bear_result.triggers_fired)} — ambiguous"
            )

    if bear_passed:
        return (
            "ENTER_BEAR",
            f"bearish setup passed, score {bear_result.bear_score}/10. "
            f"triggers={bear_result.triggers_fired}, level={bear_result.rejection_level}"
        )
    if bull_passed:
        return (
            "ENTER_BULL",
            f"bullish setup passed, score {bull_result.bull_score}/11. "
            f"triggers={bull_result.triggers_fired}, level={bull_result.reclaim_level}"
        )

    # Neither passed → diagnose the dominant blocker reason
    # Use bear blockers as primary (bear-default for the CLAUDE.md scope-locked
    # BEARISH_REJECTION_RIDE_THE_RIBBON setup).
    bear_blockers = set(bear_result.blockers)
    bull_blockers = set(bull_result.blockers)
    common = bear_blockers & bull_blockers

    # Filter 1 = time gate (no_trade_before / no_trade_after / no_trade_window)
    # v15.1 (2026-05-14): no_trade_window REMOVED. Continuous entry [09:35, 15:00) ET.
    if 1 in common:
        bar_t = _bar_min_to_time(bar_min)
        if V15_NO_TRADE_WINDOW is not None and V15_NO_TRADE_WINDOW[0] <= bar_t < V15_NO_TRADE_WINDOW[1]:
            return (
                "SKIP_NO_TRADE_WINDOW",
                f"filter 1 blocked: bar in {V15_NO_TRADE_WINDOW[0]}-{V15_NO_TRADE_WINDOW[1]} ET no-trade-window"
            )
        if bar_t >= V15_NO_TRADE_AFTER:
            return (
                "SKIP_TIME_GATE_AFTER",
                f"filter 1 blocked: bar at/after no_trade_after={V15_NO_TRADE_AFTER} ET (v15.1 entry cutoff — theta protection)"
            )
        return (
            "SKIP_TIME_GATE",
            f"filter 1 blocked: bar before no_trade_before={V15_NO_TRADE_BEFORE} ET (v15.1 entry gate)"
        )
    # Filter 5 = ribbon stack
    if 5 in common:
        return (
            "SKIP_RIBBON",
            f"filter 5 blocked: ribbon not stacked. bear_blockers={sorted(bear_blockers)}, bull_blockers={sorted(bull_blockers)}"
        )
    # Filter 6 = ribbon spread < 30c
    if 6 in common:
        return (
            "SKIP_RIBBON_SPREAD",
            f"filter 6 blocked: ribbon spread <30c (chop)"
        )
    # Filter 8/9 = VIX
    if 8 in common or 9 in common:
        return (
            "SKIP_VIX",
            f"filter 8/9 blocked: VIX gate failed. bear_blockers={sorted(bear_blockers)}, bull_blockers={sorted(bull_blockers)}"
        )
    # Filter 10 (bear) / Filter 11 (bull) = not enough triggers
    if 10 in bear_blockers and 11 in bull_blockers:
        return (
            "SKIP_TRIGGERS",
            f"filter 10/11 blocked: insufficient triggers. "
            f"bear_triggers={bear_result.triggers_fired}, bull_triggers={bull_result.triggers_fired}"
        )
    # General fallback
    if bear_blockers or bull_blockers:
        return (
            f"SKIP_FILTER",
            f"blocked. bear_blockers={sorted(bear_blockers)}, bull_blockers={sorted(bull_blockers)}, "
            f"bear_score={bear_result.bear_score}/10, bull_score={bull_result.bull_score}/11"
        )
    return (
        "HOLD",
        f"no setup fired (bear_score={bear_result.bear_score}/10, bull_score={bull_result.bull_score}/11)"
    )


def _bar_min_to_time(bar_min: int) -> dt.time:
    """Convert minutes-from-09:30 to a dt.time for window comparisons."""
    total = 9 * 60 + 30 + bar_min
    hh = total // 60
    mm = total % 60
    if hh < 0 or hh > 23:
        return dt.time(0, 0)
    return dt.time(hh, mm)


# ─────────────────────────────────────────────────────────────────────────────
# Verdict
# ─────────────────────────────────────────────────────────────────────────────

def _verdict(decisions: list[dict], summary: dict, trade_windows: list[dict]) -> tuple[str, str]:
    """Compute verdict + narrative.

    PERFECT       : engine ENTER aligned ±5 min with each actual entry, no spurious ENTERs.
    OVER_AGGRESSIVE: more engine ENTERs than actual entries → would have churned.
    TOO_PASSIVE   : actual trade fired but engine never produced an ENTER.
    INTRADAY_INCONSISTENT: engine ENTERed AT actual entry AND elsewhere (mixed).
    NO_DATA       : no decisions emitted (no today data).
    """
    if not decisions:
        return "NO_DATA", "no engine decisions emitted (likely no today data)"

    n_actual = len(trade_windows)
    n_engine_enter = summary.get("n_enter_decisions", 0)
    engine_entry_bars = summary.get("engine_entry_bars", [])
    actual_entry_bars = summary.get("actual_entry_bars", [])

    # Match actual entries to engine entries within ±5 min (1 bar = 5 min)
    matched_actuals = 0
    matched_engine_idx = set()
    for ab in actual_entry_bars:
        for i, eb in enumerate(engine_entry_bars):
            if i in matched_engine_idx:
                continue
            if abs(eb - ab) <= 5:
                matched_actuals += 1
                matched_engine_idx.add(i)
                break
    spurious_engine = n_engine_enter - len(matched_engine_idx)
    missed_actuals = n_actual - matched_actuals

    if n_actual == 0 and n_engine_enter == 0:
        return (
            "PERFECT",
            f"no actual trades + no engine ENTERs → engine correctly stayed flat ({len(decisions)} bars)"
        )
    if matched_actuals == n_actual and spurious_engine == 0 and n_actual > 0:
        return (
            "PERFECT",
            f"engine ENTERed at all {n_actual} actual entry bar(s) within ±5min, no spurious ENTERs"
        )
    if matched_actuals > 0 and spurious_engine > 0:
        return (
            "INTRADAY_INCONSISTENT",
            f"engine fired AT actual entry ({matched_actuals}/{n_actual}) but ALSO produced "
            f"{spurious_engine} spurious ENTER(s) — mixed signal"
        )
    if missed_actuals > 0 and spurious_engine == 0:
        return (
            "TOO_PASSIVE",
            f"engine missed {missed_actuals}/{n_actual} actual entry(s); no spurious ENTERs. "
            f"Engine never identified the setup at the right bar."
        )
    if spurious_engine > 0 and matched_actuals == 0:
        return (
            "OVER_AGGRESSIVE",
            f"engine produced {spurious_engine} spurious ENTER(s) where no real trade fired. "
            f"Would have churned the account."
        )
    return (
        "INTRADAY_INCONSISTENT",
        f"engine ENTER count={n_engine_enter}, actual={n_actual}, matched={matched_actuals}, "
        f"spurious={spurious_engine}, missed={missed_actuals}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main module entry — drop-in replacement for Phase 2
# ─────────────────────────────────────────────────────────────────────────────

def analyze_detection(data: IngestedData, trades) -> CategoryScore:
    """Phase 3: replay heartbeat orchestrator over today's bars + emit decisions."""
    if not ENGINE_AVAILABLE:
        return CategoryScore(
            score=50.0,
            evidence={
                "phase": "3.0",
                "verdict": "NO_DATA",
                "error": f"engine import failed: {_IMPORT_ERROR}",
            },
            narrative=(
                "Detection N/A — could not import lib.filters / lib.orchestrator. "
                "Verify backtest dir is on sys.path."
            ),
            actions=[],
        )

    spy_full = _load_master_spy_today(data.date)
    if spy_full is None or spy_full.empty:
        return CategoryScore(
            score=50.0,
            evidence={
                "phase": "3.0",
                "verdict": "NO_DATA",
                "engine_decisions": [],
                "error": f"no_today_5m_data for {data.date}",
            },
            narrative=f"No 5m bars found for {data.date} — Phase 3 detection N/A.",
            actions=[],
        )

    # Build trade windows (entry/exit per actual trade)
    trade_windows = _trade_windows_from_trades(trades or [])

    # Run the replay
    decisions, summary = _replay_today_bars(spy_full, data.date, trade_windows)

    # If replay failed entirely, surface the error
    if not decisions:
        return CategoryScore(
            score=50.0,
            evidence={
                "phase": "3.0",
                "verdict": "NO_DATA",
                "engine_decisions": [],
                "error": summary.get("error", "no decisions emitted"),
            },
            narrative=f"Phase 3 replay produced no decisions: {summary.get('error', 'unknown')}",
            actions=[],
        )

    verdict, verdict_narr = _verdict(decisions, summary, trade_windows)

    # Score map (process_score adjustment in main.py reads this directly)
    score_map = {
        "PERFECT":               95,
        "INTRADAY_INCONSISTENT": 70,
        "OVER_AGGRESSIVE":       55,
        "TOO_PASSIVE":           40,
        "NO_DATA":               50,
    }
    score = score_map.get(verdict, 60)

    # Build action(s) — surface gap as a queue_for_grinder candidate when
    # engine missed or over-fired.
    actions = []
    if verdict == "TOO_PASSIVE":
        missed_setups = [w["setup_name"] for w in trade_windows]
        actions.append({
            "type": "queue_for_grinder",
            "priority": "HIGH",
            "details": {
                "setup_name": "DETECTION_PHASE3_TOO_PASSIVE",
                "rationale": (
                    f"Engine replay missed {len(trade_windows)} actual entry(s). "
                    f"Setups: {missed_setups}. Filter combo prevented engine from "
                    f"identifying the trigger bar that actually fired the trade."
                ),
                "actual_entries": summary.get("actual_entry_bars", []),
                "engine_entries": summary.get("engine_entry_bars", []),
            }
        })
    elif verdict == "OVER_AGGRESSIVE":
        spurious_bars = [
            d["time_et"] for d in decisions
            if d["decision"].startswith("ENTER")
        ]
        actions.append({
            "type": "queue_for_grinder",
            "priority": "MED",
            "details": {
                "setup_name": "DETECTION_PHASE3_OVER_AGGRESSIVE",
                "rationale": (
                    f"Engine replay would have ENTERed {summary.get('n_enter_decisions', 0)} "
                    f"times today; actual trades = {len(trade_windows)}. Excess fires "
                    f"would churn the account."
                ),
                "engine_entry_times": spurious_bars[:10],
            }
        })
    elif verdict == "INTRADAY_INCONSISTENT":
        actions.append({
            "type": "queue_for_grinder",
            "priority": "LOW",
            "details": {
                "setup_name": "DETECTION_PHASE3_INTRADAY_INCONSISTENT",
                "rationale": (
                    "Engine fired at actual entry AND also fired spurious ENTERs. "
                    "Filter tuning could tighten the setup-detection precision."
                ),
                "actual_entries": summary.get("actual_entry_bars", []),
                "engine_entries": summary.get("engine_entry_bars", []),
            }
        })

    narrative = (
        f"Phase 3 orchestrator-replay: {summary['total_bars']} bars evaluated. "
        f"Engine ENTERs: {summary['n_enter_decisions']} | Actual trades: {len(trade_windows)} | "
        f"SKIPs: {summary['n_skip_decisions']} | HOLDs: {summary['n_hold_decisions']} | "
        f"Verdict: {verdict}. {verdict_narr}. Score {score}/100."
    )

    return CategoryScore(
        score=float(score),
        evidence={
            "phase": "3.0",
            "verdict": verdict,
            "engine_decisions": decisions,
            "summary": summary,
            "trade_windows": trade_windows,
            "method": (
                "Replays lib.filters.evaluate_bearish_setup + evaluate_bullish_setup "
                "(same engine as live heartbeat) over today's RTH bars. Each bar produces "
                "one EngineDecision with full filter scores + blockers + triggers."
            ),
            "thresholds": {
                "no_trade_before": str(V15_NO_TRADE_BEFORE),
                "no_trade_after": str(V15_NO_TRADE_AFTER),
                "no_trade_window": (
                    [str(V15_NO_TRADE_WINDOW[0]), str(V15_NO_TRADE_WINDOW[1])]
                    if V15_NO_TRADE_WINDOW is not None else None
                ),
                "min_triggers_bear": V15_BEAR_MIN_TRIGGERS,
                "min_triggers_bull": V15_BULL_MIN_TRIGGERS,
                "f9_vol_mult": V15_F9_VOL_MULT,
            },
        },
        narrative=narrative,
        actions=actions,
    )
