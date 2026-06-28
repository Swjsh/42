"""setup_dispatch.py — dispatch layer for 4 validated-but-dormant setup detectors.

Bridges heartbeat_core.py's per-tick payload to the watcher-layer detectors
(vwap_continuation, vwap_reclaim_failed_break, vix_regime_dayside, gap_and_go).
Each detector is individually flag-gated via params.json. When ALL flags are OFF
(the current default), this module is a pure no-op — it produces an empty list
and has zero effect on the ribbon verdict or execution path.

HOW IT WORKS
  SetupDispatcher(params, payload).run()
    -> list[DispatchResult]  (empty when all flags OFF)

  Each DispatchResult carries:
    - setup_name    : str  (e.g. "vwap_continuation")
    - fired         : bool (True when the detector found a valid signal this tick)
    - signal        : WatcherSignal | None  (only when fired=True)
    - skip_reason   : str | None  (SKIP_DISABLED, SKIP_NO_FEED, SKIP_DETECTOR_ERROR,
                                   SKIP_NO_SIGNAL — the most informative non-fire outcome)

SAFETY GUARANTEES
  - All flags default FALSE in params.json → dispatch returns [] immediately.
  - No detector import happens when its flag is False (lazy import).
  - Every detector call is wrapped in try/except; exceptions return DispatchResult
    with skip_reason="SKIP_DETECTOR_ERROR:<message>" and fired=False.
  - Never raises. Never alters the ribbon verdict. Fails open on any error.

WIRING NOTE (heartbeat_core.py integration)
  The payload dict produced by heartbeat_core._build_payload already contains
  'sameday_5m_bars' (list of {open,high,low,close,volume,timestamp_iso}) and
  the full 'bar_ctx' dict. This module reconstructs a BarContext with
  timestamps from 'sameday_5m_bars' so the VWAP watchers can compute session
  VWAP. The gap_and_go watcher needs the prior-day RTH close, which it derives
  from the multi-day prior_bars frame (also reconstructed with timestamps).

  Called from run_account() AFTER _engine_verdict() and BEFORE _execute(), so
  extra signals are evaluated on the same tick state.

PER-DETECTOR STATUS (as of 2026-06-28):
  vwap_continuation        : j_vwap_cont_enabled=true  → ALREADY LIVE in params
  gap_and_go               : gap_and_go_enabled=true    → ALREADY LIVE in params
  vwap_reclaim_failed_break: j_vwap_reclaim_fb_enabled=false → DORMANT (recency RED)
  vix_regime_dayside       : j_vix_dayside_enabled=false  → DORMANT (no vix_intraday feed)
  double_bottom_base_quiet : db_base_quiet_enabled=false → WIRED DISARMED (exec gated on
                             extra_setup_exec_armed["double_bottom_base_quiet"]=True; NOT present
                             in params.json → default-off byte-identical no-op; 2026-06-28)
                             EVIDENCE: edgehunt-double_bottom_base_quiet.json (2026-06-20)
                             4 cells clear full bar (OOS>0, posQ>=4, top5<200, N>=20):
                             strike+0_stop-0.99: N=122, WR=63.9%, OOS_avg=+$26.3/trade
                             strike-1_stop-0.99: N=121, WR=62.0%, OOS_avg=+$13.2/trade
                             strike-2_stop-0.2:  N=115, WR=41.7%, OOS_avg=+$1.3/trade
                             strike-1_stop-0.5:  N=121, WR=61.2%, OOS_avg=+$5.9/trade
  head_and_shoulders_bear  : DOES NOT CLEAR — N=19 completed (7 missing OPRA), all cells
                             fail n_trades<20; anchor-no-regression pending; NOT wired.
                             Source: edgehunt-hs_bear.json (2026-06-20).
  double_top               : DOES NOT CLEAR — new observe-only stream, no edge hunt;
                             explicitly PENDING all OP-21 gates. NOT wired.
                             Source: backtest/lib/watchers/double_top_watcher.py.
  trendline_break (v52)    : DOES NOT CLEAR — standalone pure trendline entries IS avg
                             -$8.92/trade (n=64); only ribbon_flip sub has edge (n=6, IS
                             only). OOS gate fails (WF=-1.371). NOT wired.
                             Source: trendline-subclassification.json + trendline-ribbon-flip-01.json.

DO NOT change any enabled flags to True here. The dispatcher reads them from params.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Add backtest/lib to sys.path so we can import the watchers.
# heartbeat_core.py already does this, but this module may be imported standalone.
_REPO = Path(__file__).resolve().parents[2]
_BACKTEST_LIB = str(_REPO / "backtest" / "lib")
if _BACKTEST_LIB not in sys.path:
    sys.path.insert(0, _BACKTEST_LIB)
# Also expose the repo root so `backtest.lib.*` PACKAGE imports resolve — filters.py uses a
# relative `from .ribbon import RibbonState`, which fails when filters is loaded as a bare
# top-level module (the latent _build_ctx ImportError that silently no-op'd every extra setup).
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Lazy import of watcher types — only performed when a flag is ON.
# We define the type hints as strings to avoid import at module load time.


@dataclass
class DispatchResult:
    """Output of one detector's dispatch evaluation for a single tick."""
    setup_name: str
    fired: bool = False
    signal: Optional[Any] = None   # WatcherSignal when fired=True
    skip_reason: Optional[str] = None


class SetupDispatcher:
    """Evaluates each of the 4 extra detectors against the current tick.

    Parameters
    ----------
    params : dict
        The account's params.json contents (read by heartbeat_core.run_account).
    payload : dict
        The full payload dict from heartbeat_core._build_payload, containing:
          - 'bar_ctx'         : dict with bar fields + prior_bars list (no timestamps)
          - 'sameday_5m_bars' : list of {open,high,low,close,volume,timestamp_iso}
          - 'spy_df'          : full multi-day OHLCV list (oldest→newest)
          - 'ribbon_df'       : list of ribbon dicts (same length as spy_df window)
    """

    def __init__(self, params: dict, payload: dict) -> None:
        self._params = params
        self._payload = payload
        self._ctx_cache: Optional[Any] = None   # cached BarContext (built once, lazily)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> list[DispatchResult]:
        """Evaluate all detectors. Returns [] when every flag is OFF.

        Execution for each detector requires BOTH:
          1. its enable flag = True (WATCH mode)
          2. extra_setup_exec_armed[setup_name] = True (ORDER mode)
        Flags absent in params.json default to False — heartbeat_core._extra_exec_armed
        enforces this contract; this dispatcher only signals intent.
        """
        results: list[DispatchResult] = []

        # Each entry: (setup_name, enabled_flag_key, _dispatch_method)
        dispatchers = [
            ("vwap_continuation",         "j_vwap_cont_enabled",       self._dispatch_vwap_continuation),
            ("gap_and_go",                "gap_and_go_enabled",         self._dispatch_gap_and_go),
            ("vwap_reclaim_failed_break", "j_vwap_reclaim_fb_enabled",  self._dispatch_vwap_reclaim_fb),
            ("vix_regime_dayside",        "j_vix_dayside_enabled",      self._dispatch_vix_dayside),
            # 2026-06-28: double_bottom_base_quiet wired DISARMED — enable flag present, exec-arm
            # key absent in params.json → WATCH_NOT_ARMED on every tick (byte-identical no-op).
            # Evidence: edgehunt-double_bottom_base_quiet.json, 4 cells clear full bar, OOS>0.
            # ARM requires: extra_setup_exec_armed["double_bottom_base_quiet"]=True in params.json.
            ("double_bottom_base_quiet",  "db_base_quiet_enabled",      self._dispatch_db_base_quiet),
        ]

        for setup_name, flag_key, method in dispatchers:
            if not self._params.get(flag_key, False):
                # Flag is OFF — produce a minimal DISABLED result only when debug logging
                # is requested (avoids noise in the ledger on every tick).
                logger.debug("[DISPATCH] %s: SKIP_DISABLED (%s=false)", setup_name, flag_key)
                continue   # NOT appended to results — truly a no-op

            try:
                result = method()
            except Exception as e:  # noqa: BLE001 — never crash the caller
                result = DispatchResult(
                    setup_name=setup_name,
                    fired=False,
                    skip_reason=f"SKIP_DETECTOR_ERROR:{type(e).__name__}: {e}",
                )
            results.append(result)

        return results

    # ------------------------------------------------------------------
    # BarContext builder (shared by VWAP-family detectors)
    # ------------------------------------------------------------------

    def _build_ctx(self) -> Optional[Any]:
        """Build a BarContext from the payload, with timestamps in prior_bars.

        The watcher's _session_rth_vwap() needs a 'timestamp_et' column in
        prior_bars. heartbeat_core._build_payload provides 'sameday_5m_bars'
        (with timestamp_iso) which we use as the session-scoped prior_bars.
        For gap_and_go (which needs multi-day prior_bars to derive the prior
        RTH close), we attach 'spy_df_with_ts' from the multi-day window.

        Returns None if the required data is absent or construction fails.
        """
        if self._ctx_cache is not None:
            return self._ctx_cache

        try:
            import datetime as dt
            import pandas as pd

            # Package-first: filters.py does `from .ribbon import RibbonState`, which only
            # resolves when filters is loaded as `backtest.lib.filters` (a package member).
            # Loading it as a bare top-level `filters` raises "attempted relative import with
            # no known parent package" -> _build_ctx returned None -> EVERY extra setup silently
            # SKIP'd. Prefer the package import (REPO is on sys.path above); keep the bare form
            # as a legacy fallback so nothing regresses if the layout changes.
            try:
                from backtest.lib.filters import BarContext  # type: ignore[import]
                from backtest.lib.ribbon import RibbonState   # type: ignore[import]
            except ImportError:
                from filters import BarContext  # type: ignore[import]
                from ribbon import RibbonState   # type: ignore[import]

            bar_ctx_d = self._payload.get("bar_ctx", {})
            sameday = self._payload.get("sameday_5m_bars", [])
            spy_df_rows = self._payload.get("spy_df", [])

            if not sameday:
                return None

            # Build sameday DataFrame with timestamps.
            sd_rows = []
            for r in sameday:
                ts_raw = r.get("timestamp_iso") or r.get("timestamp_et") or ""
                try:
                    ts = dt.datetime.fromisoformat(str(ts_raw))
                    # Ensure it's timezone-aware ET
                    if ts.tzinfo is None:
                        import pytz
                        ts = pytz.timezone("America/New_York").localize(ts)
                except (ValueError, TypeError):
                    ts = None
                sd_rows.append({
                    "timestamp_et": ts,
                    "open": float(r.get("open", 0)),
                    "high": float(r.get("high", 0)),
                    "low": float(r.get("low", 0)),
                    "close": float(r.get("close", 0)),
                    "volume": float(r.get("volume", 0)),
                })
            sameday_df = pd.DataFrame(sd_rows)

            # Build multi-day prior_bars with timestamps for gap_and_go.
            # We use spy_df (the full bounded window from heartbeat_core) and
            # attach synthetic timestamps spaced 5-min apart if the real ones
            # aren't available (the gap_and_go only needs the date boundary to
            # find the prior-day close, so approximate is fine).
            # NOTE: spy_df in the payload is a list of dicts {open,high,low,close,volume}
            # WITHOUT timestamps. We skip multi-day prior_bars — the gap_and_go wrapper
            # will fall back to prior_rth_close=None and return SKIP_NO_FEED.
            # A future enhancement can supply prior_close from today-bias.json.
            multiday_df = None  # see gap_and_go dispatch for the SKIP_NO_FEED path

            # The trigger bar is the last row of sameday.
            if sameday_df.empty:
                return None
            trigger_row = sameday_df.iloc[-1]

            # Reconstruct ribbon_now from bar_ctx.
            ribbon_raw = bar_ctx_d.get("ribbon_now")
            ribbon_now = None
            if ribbon_raw and isinstance(ribbon_raw, dict):
                try:
                    ribbon_now = RibbonState(
                        fast=float(ribbon_raw.get("fast") or 0),
                        pivot=float(ribbon_raw.get("pivot") or 0),
                        slow=float(ribbon_raw.get("slow") or 0),
                        spread_cents=float(ribbon_raw.get("spread_cents") or 0),
                        stack=str(ribbon_raw.get("stack", "UNKNOWN")),
                    )
                except Exception:
                    pass

            ts = trigger_row["timestamp_et"]
            if ts is None:
                return None
            if not isinstance(ts, dt.datetime):
                ts = pd.Timestamp(ts).to_pydatetime()

            ctx = BarContext(
                bar_idx=len(sameday_df) - 1,
                timestamp_et=ts,
                bar=trigger_row,
                prior_bars=sameday_df,   # WITH timestamps — watcher needs this
                ribbon_now=ribbon_now,
                ribbon_history=[],
                vix_now=float(bar_ctx_d.get("vix_now", 0.0) or 0.0),
                vix_prior=float(bar_ctx_d.get("vix_prior", 0.0) or 0.0),
                vol_baseline_20=float(bar_ctx_d.get("vol_baseline_20", 0.0) or 0.0),
                range_baseline_20=float(bar_ctx_d.get("range_baseline_20", 0.0) or 0.0),
                levels_active=list(bar_ctx_d.get("levels_active", [])),
                multi_day_levels=list(bar_ctx_d.get("multi_day_levels", [])),
                htf_15m_stack=bar_ctx_d.get("htf_15m_stack"),
            )
            # G6: thread the OPTIONAL intraday VIX series (heartbeat_core supplies it on
            # bar_ctx ONLY when j_vix_dayside_enabled). BarContext is frozen, so set it via
            # object.__setattr__ — the vix_regime_dayside watcher reads getattr(ctx,
            # "vix_intraday", None). Absent -> attribute never set -> watcher SKIPs (DORMANT-safe).
            _vi = bar_ctx_d.get("vix_intraday")
            if _vi is not None:
                try:
                    object.__setattr__(ctx, "vix_intraday", list(_vi))
                except Exception:  # noqa: BLE001 — never break the tick over an optional feed
                    pass
            self._ctx_cache = ctx
            return ctx

        except Exception as e:  # noqa: BLE001
            logger.warning("[DISPATCH] _build_ctx failed: %s: %s", type(e).__name__, e)
            return None

    # ------------------------------------------------------------------
    # Per-detector dispatch methods
    # ------------------------------------------------------------------

    def _dispatch_vwap_continuation(self) -> DispatchResult:
        """Dispatch the vwap_continuation detector.

        Feed: needs session VWAP from sameday_5m_bars → WIRED_CLEAN.
        """
        ctx = self._build_ctx()
        if ctx is None:
            return DispatchResult("vwap_continuation", fired=False,
                                  skip_reason="SKIP_NO_FEED:sameday_5m_bars_missing")

        try:
            from watchers.vwap_continuation_watcher import detect_vwap_continuation_setup  # type: ignore[import]
        except ImportError as e:
            return DispatchResult("vwap_continuation", fired=False,
                                  skip_reason=f"SKIP_IMPORT_ERROR:{e}")

        # Read per-setup params
        put_vix_gate = bool(self._params.get("j_vwap_cont_put_vix_gate", True))

        sig = detect_vwap_continuation_setup(ctx, put_needs_rising_vix=put_vix_gate)
        if sig is None:
            return DispatchResult("vwap_continuation", fired=False,
                                  skip_reason="SKIP_NO_SIGNAL")
        return DispatchResult("vwap_continuation", fired=True, signal=sig)

    def _dispatch_gap_and_go(self) -> DispatchResult:
        """Dispatch the gap_and_go detector.

        Feed: needs prior-day RTH close. The multi-day spy_df from heartbeat_core
        does NOT carry timestamps, so we cannot reconstruct the prior close from it.
        We attempt to read today-bias.json for prior_close (the cleanest source),
        and fall back to SKIP_NO_FEED if absent.
        """
        ctx = self._build_ctx()
        if ctx is None:
            return DispatchResult("gap_and_go", fired=False,
                                  skip_reason="SKIP_NO_FEED:sameday_5m_bars_missing")

        try:
            from watchers.gap_and_go_watcher import detect_gap_and_go_setup  # type: ignore[import]
        except ImportError as e:
            return DispatchResult("gap_and_go", fired=False,
                                  skip_reason=f"SKIP_IMPORT_ERROR:{e}")

        # Attempt to source the prior RTH close from today-bias.json.
        prior_close = self._get_prior_rth_close()

        # If prior_close is None, the watcher will try to derive from prior_bars.
        # Our prior_bars is sameday-only (no prior day), so the watcher will also
        # return None → SKIP_NO_FEED. That is the correct behavior.
        sig = detect_gap_and_go_setup(ctx, prior_rth_close=prior_close)
        if sig is None:
            skip = ("SKIP_NO_FEED:prior_rth_close_unavailable"
                    if prior_close is None else "SKIP_NO_SIGNAL")
            return DispatchResult("gap_and_go", fired=False, skip_reason=skip)
        return DispatchResult("gap_and_go", fired=True, signal=sig)

    def _dispatch_vwap_reclaim_fb(self) -> DispatchResult:
        """Dispatch the vwap_reclaim_failed_break detector.

        Feed: needs session VWAP from sameday_5m_bars → WIRED_CLEAN (same as vwap_cont).
        Currently DORMANT (j_vwap_reclaim_fb_enabled=false, recency RED).
        """
        ctx = self._build_ctx()
        if ctx is None:
            return DispatchResult("vwap_reclaim_failed_break", fired=False,
                                  skip_reason="SKIP_NO_FEED:sameday_5m_bars_missing")

        try:
            from watchers.vwap_reclaim_failed_break_watcher import detect_vwap_reclaim_failed_break_setup  # type: ignore[import]
        except ImportError as e:
            return DispatchResult("vwap_reclaim_failed_break", fired=False,
                                  skip_reason=f"SKIP_IMPORT_ERROR:{e}")

        sig = detect_vwap_reclaim_failed_break_setup(ctx)
        if sig is None:
            return DispatchResult("vwap_reclaim_failed_break", fired=False,
                                  skip_reason="SKIP_NO_SIGNAL")
        return DispatchResult("vwap_reclaim_failed_break", fired=True, signal=sig)

    def _dispatch_vix_dayside(self) -> DispatchResult:
        """Dispatch the vix_regime_dayside detector.

        Feed: needs ctx.vix_intraday (78-bar intraday VIX history + slope).
        heartbeat_core does NOT supply vix_intraday — only vix_now/vix_prior.
        Result: SKIP_NO_FEED until the feed is wired in heartbeat_core.py.

        The detector itself handles a missing vix_intraday gracefully (returns None),
        but we surface an explicit SKIP_NO_FEED reason here for clarity.
        """
        ctx = self._build_ctx()
        if ctx is None:
            return DispatchResult("vix_regime_dayside", fired=False,
                                  skip_reason="SKIP_NO_FEED:sameday_5m_bars_missing")

        # Check if vix_intraday is available on ctx (heartbeat_core does not supply it).
        has_vix_intraday = hasattr(ctx, "vix_intraday") and getattr(ctx, "vix_intraday", None) is not None

        if not has_vix_intraday:
            return DispatchResult("vix_regime_dayside", fired=False,
                                  skip_reason="SKIP_NO_FEED:vix_intraday_not_wired")

        try:
            from watchers.vix_regime_dayside_watcher import detect_vix_regime_dayside_setup  # type: ignore[import]
        except ImportError as e:
            return DispatchResult("vix_regime_dayside", fired=False,
                                  skip_reason=f"SKIP_IMPORT_ERROR:{e}")

        sig = detect_vix_regime_dayside_setup(ctx)
        if sig is None:
            return DispatchResult("vix_regime_dayside", fired=False,
                                  skip_reason="SKIP_NO_SIGNAL")
        return DispatchResult("vix_regime_dayside", fired=True, signal=sig)

    def _dispatch_db_base_quiet(self) -> DispatchResult:
        """Dispatch the double_bottom_base_quiet detector (WIRED DISARMED, 2026-06-28).

        Evidence (edgehunt-double_bottom_base_quiet.json, run 2026-06-20):
          4/20 strike/stop cells clear the full candidate-edge bar:
            best cell: strike+0_stop-0.99 — N=122, WR=63.9%, OOS avg=+$26.3/trade
          Bars required: OOS_avg>0, posQ>=4/6, top5_day_pct<200, N>=20. All real OPRA fills (C1).

        DISARMED by default: this method dispatches the signal (fired=True when detector fires),
        but heartbeat_core._extra_exec_armed gates live order placement on:
            params["extra_setup_exec_armed"]["double_bottom_base_quiet"] = True
        That key is ABSENT from params.json — so every tick routes to WATCH_NOT_ARMED (no order).

        Feed: needs session sameday_5m_bars with timestamps + vix_now — same as vwap_continuation.
        """
        ctx = self._build_ctx()
        if ctx is None:
            return DispatchResult("double_bottom_base_quiet", fired=False,
                                  skip_reason="SKIP_NO_FEED:sameday_5m_bars_missing")

        try:
            from watchers.double_bottom_base_quiet_watcher import detect_db_base_quiet_setup  # type: ignore[import]
        except ImportError as e:
            return DispatchResult("double_bottom_base_quiet", fired=False,
                                  skip_reason=f"SKIP_IMPORT_ERROR:{e}")

        sig = detect_db_base_quiet_setup(ctx)
        if sig is None:
            return DispatchResult("double_bottom_base_quiet", fired=False,
                                  skip_reason="SKIP_NO_SIGNAL")
        return DispatchResult("double_bottom_base_quiet", fired=True, signal=sig)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_prior_rth_close(self) -> Optional[float]:
        """Try to read the prior RTH close from today-bias.json (the pre-market file).

        today-bias.json is written by the premarket session and contains the previous
        day's close under keys like 'prior_close' or 'key_levels.prev_close'. Falls
        back to None (and the gap_and_go watcher will emit SKIP_NO_FEED) when absent.
        """
        try:
            import json
            state = _REPO / "automation" / "state"
            bias_path = state / "today-bias.json"
            if not bias_path.exists():
                return None
            bias = json.loads(bias_path.read_text(encoding="utf-8"))
            # Try common keys written by premarket
            for key in ("prior_close", "prev_close", "prev_rth_close", "prior_rth_close"):
                v = bias.get(key)
                if v is not None:
                    return float(v)
            # Also try nested key_levels
            kl = bias.get("key_levels") or {}
            for key in ("prev_close", "prior_close"):
                v = kl.get(key)
                if v is not None:
                    return float(v)
            return None
        except Exception:  # noqa: BLE001
            return None


# ---------------------------------------------------------------------------
# Convenience: integration helper for heartbeat_core.run_account
# ---------------------------------------------------------------------------

def dispatch_extra_setups(
    account: str,
    params: dict,
    payload: dict,
    verdict: dict,
    *,
    armed: bool = False,
) -> list[dict]:
    """Run the extra-setup dispatch and return a list of ledger-serializable dicts.

    Designed to be called from heartbeat_core.run_account() AFTER the engine_cli
    verdict and BEFORE (or alongside) _execute(). The returned list is appended
    to the ledger row under 'extra_signals'.

    When ALL flags are OFF (current default), returns [] with zero side effects.

    The function does NOT place orders itself — that remains the caller's
    responsibility (heartbeat_core._execute). It signals intent via 'fired' and
    attaches the WatcherSignal to allow the caller to route through the same
    risk_gate -> fleet_broker path.
    """
    try:
        results = SetupDispatcher(params, payload).run()
    except Exception as e:  # noqa: BLE001 — never crash the caller
        logger.error("[DISPATCH] dispatch_extra_setups failed: %s: %s", type(e).__name__, e)
        return [{"error": f"dispatch_crashed: {e}"}]

    out = []
    for r in results:
        row: dict = {
            "setup_name": r.setup_name,
            "fired": r.fired,
            "skip_reason": r.skip_reason,
        }
        if r.fired and r.signal is not None:
            sig = r.signal
            row["direction"] = sig.direction
            row["entry_price"] = sig.entry_price
            row["stop_price"] = sig.stop_price
            row["confidence"] = sig.confidence
            row["triggers"] = sig.triggers_fired
            row["watcher"] = sig.watcher_name
        out.append(row)
        if r.fired:
            logger.info("[DISPATCH] %s FIRED dir=%s entry=%.2f stop=%.2f",
                        r.setup_name,
                        r.signal.direction if r.signal else "?",
                        r.signal.entry_price if r.signal else 0.0,
                        r.signal.stop_price if r.signal else 0.0)
        elif r.skip_reason:
            logger.info("[DISPATCH] %s: %s", r.setup_name, r.skip_reason)
    return out
