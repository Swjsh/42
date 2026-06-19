"""Watcher orchestrator — runs all watchers per-bar, logs observations.

Called by:
  - heartbeat (live, market hours): per-tick watcher pass alongside main engine
  - backtest replay: post-hoc on historical bars to populate observation history
  - scheduled task (Sunday): batch-replay over recent days for source-of-truth list

Observation log: automation/state/watcher-observations.jsonl  (append-only)
Per-day summary:  automation/state/watcher-summary.json       (overwritten daily)

Observation row schema:
  {
    "observed_at": "ISO timestamp",
    "bar_timestamp_et": "ISO timestamp",
    "watcher_name": "orb_watcher" | "bullish_watcher" | "v14_enhanced_watcher" | ...,
    "setup_name": "ORB_BREAK_LONG" | ...,
    "direction": "long" | "short" | "neutral",
    "entry_price": float,
    "stop_price": float,
    "tp1_price": float,
    "runner_price": float | null,
    "confidence": "low" | "medium" | "high",
    "reason": str,
    "triggers_fired": [str],
    "metadata": {...},
    "would_be_outcome": null,    # filled in by replay scorer once bars after entry exist
    "would_be_pnl_dollars": null
  }
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from . import WatcherSignal
from .orb_watcher import detect_orb_break
from .bullish_watcher import detect_bullish_setup
from .vwap_watcher import detect_vwap_setup
from .opening_drive_fade_watcher import detect_opening_drive_fade_setup
from .v14_enhanced_watcher import detect_v14_enhanced_setup
from .premarket_fail_fade_watcher import detect_premarket_fail_fade_setup
from .shotgun_scalper_watcher import detect_shotgun_scalper_setup
from .tbr_high_vol_watcher import detect_tbr_high_vol_setup
from .bearish_reversal_at_level_watcher import detect_bearish_reversal_at_level
from .level_break_first_strike_watcher import detect_lbfs_setup
from .named_level_wick_bounce_watcher import detect_nlwb_setup
from .double_bottom_morning_low_vol_watcher import detect_db_morning_low_vol_setup
from .momentum_acceleration_highvol_watcher import detect_momentum_accel_highvol_setup
from .double_bottom_base_quiet_watcher import detect_db_base_quiet_setup
from .hs_near_named_level_watcher import detect_hs_near_named_setup
from .hs_watcher import detect_hs_setup
from .fbw_morning_mid_watcher import detect_fbw_morning_mid_setup
from .close_ceiling_fade_watcher import detect_close_ceiling_fade_setup
from .floor_hold_bounce_watcher import detect_floor_hold_bounce_setup
from .rsi_divergence_watcher import detect_rsi_divergence_bull
from .bearish_rejection_morning_watcher import detect_bearish_rejection_morning
from .orb15_watcher import detect_orb15_break  # Reddit ORB-15 adoption 2026-06-14
from .erl_irl_watcher import detect_erl_irl_setup  # Reddit ERL->IRL adoption 2026-06-14
from .named_level_second_test_watcher import detect_named_level_second_test_setup  # 2026-06-18
from .stairstep_continuation_watcher import detect_stairstep_continuation_setup  # 2026-06-18
from .vwap_trend_pullback_watcher import detect_vwap_trend_pullback_setup  # 2026-06-19 H4
from .gap_and_go_watcher import detect_gap_and_go_setup  # 2026-06-19 H2b (open-bar; needs prior_close)
from ..filters import BarContext

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO.parent
STATE_DIR = ROOT / "automation" / "state"
OBS_LOG = STATE_DIR / "watcher-observations.jsonl"
SUMMARY = STATE_DIR / "watcher-summary.json"
STATE_DIR.mkdir(parents=True, exist_ok=True)


# Per-day dedup state (resets each new day)
_dedup_state: dict[tuple[str, str, str], str] = {}  # (date, watcher, setup_direction) -> best_confidence
_dedup_date: Optional[str] = None

CONF_RANK = {"low": 0, "medium": 1, "high": 2}


# ─────────────────────────────────────────────────────────────────────────────
# Watcher registry — the single source of truth for the fleet.
#
# Being defined == being registered == being run. Every active watcher appears
# here exactly once; `run_all_watchers` iterates THIS list (no hand-maintained
# call chain). A reconciliation test (backtest/tests/test_watcher_registry.py)
# asserts set(detector files) == set(registry) so a watcher can never be added
# to the tree without being wired in (the "engine couldn't see it" orphan bug)
# nor registered without existing.
#
# Each WatcherSpec wraps ONE detector with an `invoke(deps)` adapter that
# normalizes its (heterogeneous) call signature and applies any per-watcher
# post-filter (e.g. ORB/bullish keep medium-conf only). The adapter calls the
# detector by its BARE GLOBAL NAME on purpose: that resolves the function from
# this module's namespace at call time, so a monkeypatch of
# `runner.detect_*` (v24 runner-invariants T4/T5) is honored. Capturing the
# function object instead would silently bypass the patch.
#
# Each invoke is wrapped in try/except → stderr by the loop, preserving the
# T63 silent-failure guard (one broken watcher never kills the live loop, but
# every caught exception is surfaced).
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _WatcherDeps:
    """Everything any watcher needs for a single bar (built once per call)."""
    bar: "pd.Series"
    day_bars: "pd.DataFrame"
    bar_idx_in_day: int
    vol_baseline_20: float
    ctx: BarContext
    vix_now: float
    ribbon_state_dict: Optional[dict]
    ribbon_stack: Optional[str]
    multi_day_rth: Optional["pd.DataFrame"]
    bar_idx_full: int  # index of `bar` within multi_day_rth, or -1 if absent/unmatched


@dataclass(frozen=True)
class WatcherSpec:
    """One registry entry: a watcher's stable name + its bar-level adapter.

    name:   the watcher_name emitted on WatcherSignal (stable identifier).
    attr:   the detector's attribute name in THIS module's namespace. Used for
            reconciliation against the detector files and to document which
            global the adapter resolves (the monkeypatch surface for v24).
    invoke: adapter (deps) -> Optional[WatcherSignal]. Returns None to skip.
    """
    name: str
    attr: str
    invoke: Callable[["_WatcherDeps"], Optional[WatcherSignal]]


def _orb_invoke(d: "_WatcherDeps") -> Optional[WatcherSignal]:
    # 16-month finding (2026-05-10): ORB MEDIUM-conf is the sweet spot.
    # Low=$+96/68 fires (noise). Medium=$+589/86 fires. High=$-198/9 fires (consensus trap).
    orb = detect_orb_break(d.bar, d.day_bars, d.bar_idx_in_day, d.vol_baseline_20)
    return orb if (orb is not None and orb.confidence == "medium") else None


def _orb15_invoke(d: "_WatcherDeps") -> Optional[WatcherSignal]:
    # ORB-15 (WATCH-ONLY, Reddit r/FuturesTradingNQ adoption 2026-06-14). 15-min
    # opening range vs the deployed 30-min ORB; own state, long-only retest.
    # VALIDATION 2026-06-14: net-negative SPY-space; DO NOT promote (OP-21 + Rule 9).
    return detect_orb15_break(d.bar, d.day_bars, d.bar_idx_in_day, d.vol_baseline_20)


def _bullish_invoke(d: "_WatcherDeps") -> Optional[WatcherSignal]:
    # Bullish: medium-conf is break-even, low+high are net negative. Keep
    # medium-only for observation/learning until 3+ live wins (OP-21).
    bull = detect_bullish_setup(d.ctx)
    return bull if (bull is not None and bull.confidence == "medium") else None


def _shotgun_invoke(d: "_WatcherDeps") -> Optional[WatcherSignal]:
    # SHOTGUN_SCALPER (WATCH-ONLY 2026-05-15). T1 open-bar reject / T2 named-level
    # reject / T3 trendline break+retest. Single-exit doctrine, no runner.
    return detect_shotgun_scalper_setup(
        bar=d.bar, day_bars=d.day_bars, bar_idx_in_day=d.bar_idx_in_day,
        ribbon_state_dict=d.ribbon_state_dict, vix_now=d.vix_now,
    )


def _tbr_invoke(d: "_WatcherDeps") -> Optional[WatcherSignal]:
    # TBR_HIGH_VOL (2026-05-24): dedicated high-volume TBR stream. Single-exit.
    return detect_tbr_high_vol_setup(
        bar=d.bar, day_bars=d.day_bars, bar_idx_in_day=d.bar_idx_in_day,
        ribbon_state_dict=d.ribbon_state_dict, vix_now=d.vix_now,
    )


def _odf_invoke(d: "_WatcherDeps") -> Optional[WatcherSignal]:
    # Needs multi_day_rth (HOD/LOD ratchet over the full RTH frame). Replay
    # callers pass multi_day_rth=None on purpose → bar_idx_full<0 → skip.
    if d.bar_idx_full < 0:
        return None
    return detect_opening_drive_fade_setup(d.bar, d.bar_idx_full, d.multi_day_rth)


def _vwap_invoke(d: "_WatcherDeps") -> Optional[WatcherSignal]:
    if d.bar_idx_full < 0:
        return None
    return detect_vwap_setup(d.bar, d.bar_idx_full, d.multi_day_rth, d.ribbon_state_dict)


def _pff_invoke(d: "_WatcherDeps") -> Optional[WatcherSignal]:
    # PREMARKET_FAIL_FADE — first 3 RTH bars; needs multi-day history for the
    # prior-day-high fallback level when the bias file lacks premarket resistance.
    if d.bar_idx_full < 0:
        return None
    return detect_premarket_fail_fade_setup(d.bar, d.bar_idx_full, d.multi_day_rth)


def _gap_and_go_invoke(d: "_WatcherDeps") -> Optional[WatcherSignal]:
    # GAP_AND_GO (H2b) — once-per-day OPEN-bar setup. The wrapper fires only on the
    # 09:30 ET first RTH bar and needs the PRIOR trading day's RTH close. It derives
    # that from ctx.prior_bars when the frame spans >1 day; in single-day replay it
    # no-ops (returns None) — like odf/vwap/pff when multi_day_rth is absent. The live
    # Gamma_WatcherLive feed + the proposed heartbeat open-block pass the prior close.
    # Resolve the global at call time so a monkeypatch of runner.detect_gap_and_go_setup
    # is honored (registry convention).
    return globals()["detect_gap_and_go_setup"](d.ctx)


def _ctx_spec(name: str, attr: str, fn: Callable[[BarContext], Optional[WatcherSignal]]) -> WatcherSpec:
    """Build a spec for a plain ctx-only watcher: detect_fn(ctx).

    `fn` is the import-time default; the adapter resolves the CURRENT module
    global named `attr` at call time so monkeypatching runner.<attr> is honored.
    """
    def _invoke(d: "_WatcherDeps", _attr: str = attr) -> Optional[WatcherSignal]:
        return globals()[_attr](d.ctx)
    return WatcherSpec(name=name, attr=attr, invoke=_invoke)


# The fleet. Order is preserved from the historical hand-wired chain so the
# observation/dedup stream is byte-identical to before the registry refactor.
WATCHERS: list[WatcherSpec] = [
    WatcherSpec("orb_watcher", "detect_orb_break", _orb_invoke),
    WatcherSpec("orb15_watcher", "detect_orb15_break", _orb15_invoke),
    WatcherSpec("bullish_watcher", "detect_bullish_setup", _bullish_invoke),
    _ctx_spec("v14_enhanced_watcher", "detect_v14_enhanced_setup", detect_v14_enhanced_setup),
    _ctx_spec("bearish_reversal_at_level_watcher", "detect_bearish_reversal_at_level", detect_bearish_reversal_at_level),
    _ctx_spec("level_break_first_strike_watcher", "detect_lbfs_setup", detect_lbfs_setup),
    _ctx_spec("named_level_wick_bounce_watcher", "detect_nlwb_setup", detect_nlwb_setup),
    _ctx_spec("double_bottom_morning_low_vol_watcher", "detect_db_morning_low_vol_setup", detect_db_morning_low_vol_setup),
    _ctx_spec("momentum_acceleration_highvol_watcher", "detect_momentum_accel_highvol_setup", detect_momentum_accel_highvol_setup),
    _ctx_spec("double_bottom_base_quiet_watcher", "detect_db_base_quiet_setup", detect_db_base_quiet_setup),
    _ctx_spec("hs_near_named_level_watcher", "detect_hs_near_named_setup", detect_hs_near_named_setup),
    _ctx_spec("hs_watcher", "detect_hs_setup", detect_hs_setup),
    _ctx_spec("close_ceiling_fade_watcher", "detect_close_ceiling_fade_setup", detect_close_ceiling_fade_setup),
    _ctx_spec("floor_hold_bounce_watcher", "detect_floor_hold_bounce_setup", detect_floor_hold_bounce_setup),
    _ctx_spec("named_level_second_test_watcher", "detect_named_level_second_test_setup", detect_named_level_second_test_setup),
    _ctx_spec("stairstep_continuation_watcher", "detect_stairstep_continuation_setup", detect_stairstep_continuation_setup),
    _ctx_spec("rsi_divergence_watcher", "detect_rsi_divergence_bull", detect_rsi_divergence_bull),
    _ctx_spec("bearish_rejection_morning_watcher", "detect_bearish_rejection_morning", detect_bearish_rejection_morning),
    _ctx_spec("erl_irl_watcher", "detect_erl_irl_setup", detect_erl_irl_setup),
    _ctx_spec("fbw_morning_mid_watcher", "detect_fbw_morning_mid_setup", detect_fbw_morning_mid_setup),
    # H4 data-discovered survivor (2026-06-19). Ratified: analysis/recommendations/
    # vwap-trend-pullback-LIVE.json (OOS+, WF median 1.679, causality PASS, DSR PASS).
    # WATCH_ONLY per OP-21 until 3 live J wins; ctx-only (needs full session history
    # in prior_bars for the as-of session-VWAP + 6-bar trend window).
    _ctx_spec("vwap_trend_pullback_watcher", "detect_vwap_trend_pullback_setup", detect_vwap_trend_pullback_setup),
    # H2b data-discovered survivor (2026-06-19). Ratified: analysis/recommendations/
    # gap-and-go-LIVE.json (chart-stop-only: exp +$41.6/WR 72.6%, DSR PASS, WF_PASS
    # all cuts, causality 96/96 PASS, both dirs +). Once-per-day OPEN-bar setup: fires
    # ONLY on the 09:30 ET first RTH bar and needs the PRIOR day's RTH close. In
    # single-day replay (prior_bars = today only) it no-ops by design — like odf/vwap/
    # pff when multi_day_rth is absent. Live (Gamma_WatcherLive) + the proposed
    # heartbeat open-block supply the prior close. WATCH_ONLY per OP-21 until 3 live J wins.
    WatcherSpec("gap_and_go_watcher", "detect_gap_and_go_setup", _gap_and_go_invoke),
    WatcherSpec("shotgun_scalper_watcher", "detect_shotgun_scalper_setup", _shotgun_invoke),
    WatcherSpec("tbr_high_vol_watcher", "detect_tbr_high_vol_setup", _tbr_invoke),
    WatcherSpec("opening_drive_fade_watcher", "detect_opening_drive_fade_setup", _odf_invoke),
    WatcherSpec("vwap_watcher", "detect_vwap_setup", _vwap_invoke),
    WatcherSpec("premarket_fail_fade_watcher", "detect_premarket_fail_fade_setup", _pff_invoke),
]

# Derived count — the ONE place the watcher-fleet size is sourced from. Consumers
# (docs, audits, the eod_deep watcher_fleet module) should reference this rather
# than hardcoding a number that drifts every time the fleet changes.
WATCHER_COUNT: int = len(WATCHERS)


def registered_watcher_names() -> list[str]:
    """The stable watcher_name of every registered watcher, in fire order.

    The single public source of truth for "which watchers does the engine run".
    Audits / docs / dashboards should call this instead of hardcoding a list or a
    count that silently drifts when the fleet changes.
    """
    return [spec.name for spec in WATCHERS]


def run_all_watchers(
    bar: pd.Series,
    day_bars: pd.DataFrame,
    bar_idx_in_day: int,
    vol_baseline_20: float,
    ctx: BarContext,
    vix_now: float,
    multi_day_rth: Optional[pd.DataFrame] = None,
    ribbon_state_dict: Optional[dict] = None,
) -> list[WatcherSignal]:
    """Run every watcher on the current bar; return all triggered signals.

    Deduplicates same-watcher+setup+direction signals within a day, keeping
    only the FIRST occurrence at each confidence tier. So if ORB_BREAK_LONG
    fires at 10:20 medium then again at 10:25 medium, only 10:20 logs.
    But if 10:20 medium then 10:25 HIGH (upgraded confidence), the 10:25
    upgrade DOES log.
    """
    global _dedup_state, _dedup_date

    bar_date_str = bar["timestamp_et"].date().isoformat() if hasattr(bar["timestamp_et"], "date") else "?"
    if _dedup_date != bar_date_str:
        _dedup_state = {}
        _dedup_date = bar_date_str

    ribbon_stack = ctx.ribbon_now.stack if ctx.ribbon_now else None

    # Some watchers (ODF, VWAP, PFF) need the bar's index within the FULL multi-day
    # RTH frame. T62 (fire #22): surface the two silent-skip modes so they're never
    # invisible — (a) timestamp NOT MATCHED inside a provided multi_day_rth, and
    # (b) an apparent live call with no multi_day_rth at all. Replay callers pass
    # multi_day_rth=None on purpose; their multi-day-only watchers simply no-op
    # (bar_idx_full = -1 → those invokes return None).
    bar_idx_full = -1
    if multi_day_rth is not None and not multi_day_rth.empty:
        try:
            matching = multi_day_rth.index[multi_day_rth["timestamp_et"] == bar["timestamp_et"]]
            bar_idx_full = int(matching[-1]) if len(matching) > 0 else -1
        except Exception as _e_match:
            sys.stderr.write(f"multi_day_rth timestamp lookup failed: {type(_e_match).__name__}: {_e_match}\n")
            bar_idx_full = -1
        if bar_idx_full < 0:
            # T62: rare in live mode. Diagnose tz-aware vs tz-naive / dtype=object
            # after concat (CLAUDE.md L31). v24 runner-invariants T3 asserts this fires.
            sys.stderr.write(
                f"multi_day_rth timestamp NOT MATCHED for bar {bar.get('timestamp_et')!r} "
                f"(multi_day_rth tz={getattr(multi_day_rth['timestamp_et'].dtype, 'tz', None)}, "
                f"bar tz={getattr(bar.get('timestamp_et'), 'tz', None)}). "
                f"Silent-skip of odf/vwap/pff this bar.\n"
            )
    else:
        # T62 best-effort invariant: an apparent LIVE call (fresh bar, populated ctx)
        # with no multi_day_rth means the wiring broke — surface it. Replay callers
        # can ignore. Never break the loop on this check.
        try:
            _bts = bar.get("timestamp_et") if isinstance(bar, pd.Series) else None
            _now = dt.datetime.now(dt.timezone(dt.timedelta(hours=-4)))  # ET
            if _bts is not None and hasattr(_bts, "to_pydatetime"):
                _bts_py = _bts.to_pydatetime()
                if _bts_py.tzinfo is None:
                    _bts_py = _bts_py.replace(tzinfo=dt.timezone(dt.timedelta(hours=-4)))
                _age_sec = (_now - _bts_py).total_seconds()
                if 0 <= _age_sec <= 3600 and ctx is not None:
                    sys.stderr.write(
                        f"WARNING T62: multi_day_rth None/empty in apparent live call "
                        f"(bar age {_age_sec:.0f}s). Skipping odf/vwap/pff. "
                        f"Replay callers can ignore this.\n"
                    )
        except Exception:
            pass  # best-effort; never break the loop

    deps = _WatcherDeps(
        bar=bar,
        day_bars=day_bars,
        bar_idx_in_day=bar_idx_in_day,
        vol_baseline_20=vol_baseline_20,
        ctx=ctx,
        vix_now=vix_now,
        ribbon_state_dict=ribbon_state_dict,
        ribbon_stack=ribbon_stack,
        multi_day_rth=multi_day_rth,
        bar_idx_full=bar_idx_full,
    )

    # Iterate the registry — being registered == being run. Each invoke is wrapped
    # in try/except → stderr (T63 silent-failure guard, OP-25): one broken watcher
    # never kills the live loop, but EVERY caught exception is surfaced (visible in
    # Gamma_WatcherLive task output). Per-watcher post-filters (e.g. ORB/bullish
    # medium-only) and multi-day gating live inside each spec's invoke adapter.
    raw_signals: list[WatcherSignal] = []
    for spec in WATCHERS:
        try:
            sig = spec.invoke(deps)
        except Exception as _e_w:
            sys.stderr.write(f"{spec.name} exception: {type(_e_w).__name__}: {_e_w}\n")
            continue
        if sig is not None:
            raw_signals.append(sig)

    # Dedup per-day: emit only NEW (watcher, setup, direction) combos OR confidence upgrades
    emitted = []
    for s in raw_signals:
        key = (bar_date_str, s.watcher_name, f"{s.setup_name}_{s.direction}")
        prior_conf = _dedup_state.get(key)
        if prior_conf is None:
            _dedup_state[key] = s.confidence
            emitted.append(s)
        elif CONF_RANK[s.confidence] > CONF_RANK[prior_conf]:
            _dedup_state[key] = s.confidence
            emitted.append(s)
        # else: same or lower confidence, suppress
    return emitted


def log_observation(signal: WatcherSignal, bar_timestamp_et) -> None:
    """Append a single observation to the JSONL log."""
    row = {
        "observed_at": dt.datetime.now().isoformat(),
        "bar_timestamp_et": bar_timestamp_et.isoformat() if hasattr(bar_timestamp_et, "isoformat") else str(bar_timestamp_et),
        "watcher_name": signal.watcher_name,
        "setup_name": signal.setup_name,
        "direction": signal.direction,
        "entry_price": signal.entry_price,
        "stop_price": signal.stop_price,
        "tp1_price": signal.tp1_price,
        "runner_price": signal.runner_price,
        "confidence": signal.confidence,
        "reason": signal.reason,
        "triggers_fired": signal.triggers_fired,
        "metadata": signal.metadata,
        "would_be_outcome": None,        # filled by replay scorer
        "would_be_pnl_dollars": None,
    }
    with OBS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def grade_observation(obs: dict, future_bars: pd.DataFrame) -> dict:
    """Score a watcher observation with proper TP1+runner partial accounting.

    Mimics the orchestrator's TP1+RUNNER doctrine:
      - 50% qty exits at TP1 (locked profit)
      - 50% qty rides as runner with stop moved to BE
      - If runner hits target = full target capture
      - If runner BE-stops = TP1 partial profit only
      - If full stop hits before TP1 = full loss
    """
    if obs.get("would_be_outcome") is not None:
        return obs

    direction = obs["direction"]
    entry = obs["entry_price"]
    stop = obs["stop_price"]
    tp1 = obs["tp1_price"]
    runner = obs["runner_price"]

    if future_bars.empty:
        return obs

    outcome = "open"
    tp1_filled = False
    pnl_dollars = 0.0   # in $ for 1 SPY contract (SPY price * 100)

    for _, b in future_bars.iterrows():
        bar_high = float(b["high"])
        bar_low = float(b["low"])

        if direction == "long":
            # Stop check (BE if tp1 already filled, else original)
            if not tp1_filled and bar_low <= stop:
                outcome = "stopped"
                pnl_dollars = (stop - entry) * 100   # full size loss
                break
            if tp1_filled and bar_low <= entry:
                outcome = "tp1_then_be_stop"
                # TP1 50% locked at tp1 price; runner 50% exited at BE (entry)
                pnl_dollars = ((tp1 - entry) * 0.5 + 0.0) * 100   # only TP1 partial wins
                break
            # Runner check
            if runner is not None and bar_high >= runner:
                outcome = "runner_hit"
                if tp1_filled:
                    pnl_dollars = ((tp1 - entry) * 0.5 + (runner - entry) * 0.5) * 100
                else:
                    pnl_dollars = (runner - entry) * 100   # full size at runner
                break
            # TP1 check (lock partial, move stop to BE, keep runner alive)
            if not tp1_filled and bar_high >= tp1:
                tp1_filled = True
                stop = entry  # BE
        elif direction == "short":
            if not tp1_filled and bar_high >= stop:
                outcome = "stopped"
                pnl_dollars = (entry - stop) * 100
                break
            if tp1_filled and bar_high >= entry:
                outcome = "tp1_then_be_stop"
                pnl_dollars = ((entry - tp1) * 0.5 + 0.0) * 100
                break
            if runner is not None and bar_low <= runner:
                outcome = "runner_hit"
                if tp1_filled:
                    pnl_dollars = ((entry - tp1) * 0.5 + (entry - runner) * 0.5) * 100
                else:
                    pnl_dollars = (entry - runner) * 100
                break
            if not tp1_filled and bar_low <= tp1:
                tp1_filled = True
                stop = entry
        elif direction == "neutral":
            # PIN-FADE: profit if SPY stays within range, loss if breaks
            # FIX 2026-05-10: original grader had no "pinned" win path → 0 wins in 53 fires.
            # Iron condor sells premium; profit = full premium collected if expiring in range.
            # Approximate: nominal premium = $50 collected per condor.
            # If SPY stays in range until end of grading window OR through next 12 bars (1h)
            # whichever first, treat as "pinned" win = +$50.
            # If breaks either side = lose net premium minus collected = -$150 (conservative).
            if bar_high >= stop:
                outcome = "broken_high"
                pnl_dollars = -150.0
                break
            other_boundary = tp1 - (stop - tp1)
            if bar_low <= other_boundary:
                outcome = "broken_low"
                pnl_dollars = -150.0
                break

    if outcome == "open" and tp1_filled:
        # End of window with TP1 filled but runner still open — treat as TP1-only
        outcome = "tp1_partial_open"
        pnl_dollars = ((tp1 - entry) if direction == "long" else (entry - tp1)) * 0.5 * 100
    elif outcome == "open" and direction == "neutral":
        # PIN-FADE that didn't break — won via theta decay (premium collected)
        outcome = "pinned"
        pnl_dollars = 50.0   # nominal premium collected on iron condor

    obs["would_be_outcome"] = outcome
    obs["would_be_pnl_dollars"] = round(pnl_dollars, 2)
    obs["tp1_filled"] = tp1_filled
    return obs
