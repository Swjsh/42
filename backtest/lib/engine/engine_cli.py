#!/usr/bin/env python3
"""engine_cli — the stdin/stdout BOUNDARY over the shared decision core (Phase 3).

Spec: ``markdown/specs/SHARED-DECISION-LIBRARY-MIGRATION.md`` §3 "Phase 3 — Shadow-mode the
engine verdict alongside the live prose for N days". This is the thin shell-out
shim the live heartbeat will call (Phase 4, J-gated), modelled EXACTLY on
``automation/scripts/pre_order_gate.py`` — which already does this for the RISK
layer (one pure function, the backtest delegates, the live path shells out).

WHAT THIS IS (and is NOT)
-------------------------
PURE MARSHALLING. The shim does ZERO decision logic of its own. It:

  1. reads ONE JSON payload on stdin (the market state the heartbeat computes each
     tick — the SPY trigger bar, ribbon, VIX, levels, the triggers it recognized);
  2. constructs the engine input objects (``filters.BarContext`` + the two
     historical frames the gates read);
  3. calls ``engine.score.score_bar`` and ``engine.gates.evaluate_gates``;
  4. mirrors the orchestrator's side/tier/has_level derivation VERBATIM (the only
     glue — it bridges ``score_bar``'s two-sided result into the single
     ``GateContext`` the gates consume, and is proven byte-identical to the
     orchestrator by ``backtest/tests/test_engine_cli_parity.py``);
  5. writes ONE compact JSON verdict on stdout.

It adds NO new gates, NO new scoring, NO mutation, NO I/O beyond stdin/stdout, and
is deterministic: the same payload always yields the same verdict. The verdict is
identical to what calling ``score_bar`` + ``evaluate_gates`` directly produces —
that equality is the whole point (the parity test is the proof).

This is a MACHINE BOUNDARY: malformed input is answered with a clean JSON error
object on stdout + a nonzero exit code, never a Python traceback. Like
``risk_gate.check_order``'s discipline, an unreadable payload fails CLOSED — the
verdict is ``SKIP_BAD_INPUT`` (never a speculative ENTER).

================================ INPUT CONTRACT ================================

stdin: a single JSON object. Top-level keys:

  bar_ctx   (object, REQUIRED) — the BarContext for the trigger bar. Fields:
      bar_idx            int      integer index of the trigger bar into spy_df
      timestamp_et       str      ISO-8601 bar timestamp, e.g. "2026-05-20T10:00:00-04:00"
      bar                object   {open, high, low, close, volume} of the trigger bar
      prior_bars         array    list of {open,high,low,close,volume}, oldest→newest,
                                  INCLUDING the trigger bar (the filters' history window)
      ribbon_now         object|null  {fast, pivot, slow, spread_cents, stack}
                                       stack ∈ {"BULL","BEAR","MIXED"}
      ribbon_history     array    list of (ribbon-object | null) — recent stacks
      vix_now            number   spot VIX at the bar
      vix_prior          number   VIX at the prior bar (direction)
      vol_baseline_20    number   20-bar volume SMA preceding the bar
      range_baseline_20  number   20-bar (high-low) SMA preceding the bar
      levels_active      array    [float] active support/resistance levels
      multi_day_levels   array    [float] subset that is multi-day (>=1 day old)
      htf_15m_stack      str|null "BULL"|"BEAR"|"MIXED"|null
      level_states       object   optional {price_str: LevelState-like}; default {}
      fhh_level          number|null  optional first-hour-high supplement; default null
      vix_5d_ma          number   optional; default 0.0
      vix_20d_ma         number   optional; default 0.0

  gate_params  (object, optional) — the armed gate knobs, keyed by the
      run_backtest gate-kwarg names (block_level_rejection, vix_bear_hard_cap,
      entry_bar_body_pct_min, block_elite_bull_vix_low/high,
      midday_trendline_gate_start_minutes, ...). Default {} = all gates disarmed,
      exactly as the orchestrator's default-valued kwargs (gate off). Reads use
      ``params.get(key, <orchestrator default>)``.

  score_params (object, optional) — forwarded to the scorers:
      enable_bullish  bool   default true — when false the bull side is not scored
      bear_kwargs     object default {} — kwargs for evaluate_bearish_setup
                             (min_triggers, vix_soft_mode, allow_one_blocker,
                             no_trade_before "HH:MM", no_trade_window ["HH:MM","HH:MM"],
                             f9_vol_mult, the sweep-blocker knobs, ...)
      bull_kwargs     object default {} — kwargs for evaluate_bullish_setup

  spy_df       (array, optional) — list of {open,high,low,close,volume} rows, the
      full SPY frame, ONLY needed when ``require_bearish_fill_bar`` is armed (the
      look-ahead fill-bar gate reads row bar_idx+1). Indexed 0..N-1 to match bar_idx.

  ribbon_df    (array, optional) — list of {fast,pivot,slow,spread_cents,stack}
      rows, the full ribbon frame, ONLY needed when ``min_ribbon_momentum_cents`` or
      ``max_ribbon_duration_bars`` is armed (those gates walk it via ribbon_at).
      Indexed 0..N-1 to match bar_idx. ``stack`` may be "WARMUP" for unwarmed bars.

A handful of bear_kwargs/bull_kwargs take time values: ``no_trade_before`` is an
"HH:MM" string, ``no_trade_window`` is a ["HH:MM","HH:MM"] pair, ``disable_filters``
is a list[int]. They are parsed here and forwarded; everything else passes through
verbatim.

================================ OUTPUT SHAPE =================================

stdout: a single compact JSON object.

  On success:
    {
      "verdict": "ENTER_BEAR" | "ENTER_BULL" | "HOLD" | "SKIP_<GATE>",
      "side": "P" | "C" | null,            # winning side, null if no side won
      "setup_name": str | null,            # the named setup, null if no side won
      "bear_score": int,
      "bull_score": int | null,            # null when enable_bullish=false
      "bear_blockers": [int, ...],
      "bull_blockers": [int, ...] | null,
      "triggers_fired": [str, ...],        # the WINNING side's triggers ([] if none)
      "rejection_level": float | null,     # winning level (reject for P / reclaim for C)
      "quality_tier": str | null,          # "SUPER"|"ELITE"|"LEVEL"|"TRENDLINE"|... or null
      "gate": {"gate_id": str, "action": str, "blockers": [str,...]} | null,
      "reason": str                        # one human clause
    }

  verdict resolution (mirrors the orchestrator's per-bar flow exactly):
    * neither side passed scoring          -> "HOLD"  (gate=null, side=null)
    * a side passed, but a gate fired SKIP -> "SKIP_<GATE>"  (gate=<the GateBlock>)
    * a side passed and no gate fired      -> "ENTER_BEAR" / "ENTER_BULL"

  Note: this boundary covers SCORING + the 15 entry GATES (score.py + gates.py).
  It deliberately does NOT evaluate the two MUTABLE/forward-scanning blocks that
  stay in the orchestrator (SKIP_QUALITY_LOCK — needs per-day state; SKIP_NO_PULLBACK
  — mutates the entry index) nor the SIZING gate (that is pre_order_gate.py's job).
  Those remain the caller's responsibility, exactly as the spec scopes Phase 2/3.

  On malformed input (fail-closed):
    {"verdict": "SKIP_BAD_INPUT", "error": "<clear message>", "side": null,
     "gate": null}
  printed to stdout with exit code 1. No traceback ever reaches stdout.

Usage:
  echo '{"bar_ctx": {...}}' | python -m backtest.lib.engine.engine_cli
  python -m backtest.lib.engine.engine_cli < payload.json
  python -m backtest.lib.engine.engine_cli --help

Exit codes: 0 = verdict produced; 1 = malformed/unreadable input (SKIP_BAD_INPUT).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

# Resolve the shared library the same way pre_order_gate.py does: put backtest/ and
# the repo root on sys.path so ``lib.engine`` / ``lib.filters`` resolve to the SAME
# modules the orchestrator and the parity tests import.
_REPO = Path(__file__).resolve().parents[3]
for _p in (str(_REPO / "backtest"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from lib.engine.gates import GateBlock, GateContext, evaluate_gates  # noqa: E402
from lib.engine.score import ScoreResult, score_bar  # noqa: E402
from lib.filters import BarContext  # noqa: E402
from lib.ribbon import RibbonState  # noqa: E402


class BadPayload(Exception):
    """Raised for any malformed / unreadable input at the boundary.

    Caught at the top level and rendered as a clean JSON ``SKIP_BAD_INPUT`` object,
    never a traceback — this is a machine boundary (fail-closed, like
    ``risk_gate``'s UNREADABLE_INPUT discipline).
    """


# --------------------------------------------------------------------------- #
# Input marshalling — JSON -> engine objects. All validation lives here so the
# rest of the file can assume well-formed inputs (parse, don't validate).
# --------------------------------------------------------------------------- #


def _require(obj: Mapping[str, Any], key: str, ctx: str) -> Any:
    if not isinstance(obj, Mapping) or key not in obj:
        raise BadPayload(f"{ctx}: missing required field {key!r}")
    return obj[key]


def _as_float(v: Any, ctx: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        raise BadPayload(f"{ctx}: expected a number, got {v!r}")


def _as_int(v: Any, ctx: str) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        raise BadPayload(f"{ctx}: expected an integer, got {v!r}")


def _bar_series(obj: Any, ctx: str) -> pd.Series:
    """Build an OHLCV pd.Series from a {open,high,low,close,volume} object."""
    if not isinstance(obj, Mapping):
        raise BadPayload(f"{ctx}: expected an OHLCV object, got {type(obj).__name__}")
    out = {}
    for k in ("open", "high", "low", "close"):
        out[k] = _as_float(_require(obj, k, ctx), f"{ctx}.{k}")
    # volume optional (gates/filters tolerate it; default 0)
    out["volume"] = _as_float(obj.get("volume", 0.0), f"{ctx}.volume")
    return pd.Series(out)


def _bars_frame(rows: Any, ctx: str) -> pd.DataFrame:
    """Build an OHLCV DataFrame from a list of {open,high,low,close,volume} rows."""
    if not isinstance(rows, list):
        raise BadPayload(f"{ctx}: expected a list of OHLCV rows, got {type(rows).__name__}")
    recs = []
    for i, r in enumerate(rows):
        if not isinstance(r, Mapping):
            raise BadPayload(f"{ctx}[{i}]: expected an OHLCV object")
        rec = {k: _as_float(_require(r, k, f"{ctx}[{i}]"), f"{ctx}[{i}].{k}")
               for k in ("open", "high", "low", "close")}
        rec["volume"] = _as_float(r.get("volume", 0.0), f"{ctx}[{i}].volume")
        recs.append(rec)
    return pd.DataFrame(recs, columns=["open", "high", "low", "close", "volume"])


def _ribbon_state(obj: Any, ctx: str) -> Optional[RibbonState]:
    """Build a RibbonState (or None) from a {fast,pivot,slow,spread_cents,stack} object."""
    if obj is None:
        return None
    if not isinstance(obj, Mapping):
        raise BadPayload(f"{ctx}: expected a ribbon object or null, got {type(obj).__name__}")
    return RibbonState(
        fast=_as_float(_require(obj, "fast", ctx), f"{ctx}.fast"),
        pivot=_as_float(_require(obj, "pivot", ctx), f"{ctx}.pivot"),
        slow=_as_float(_require(obj, "slow", ctx), f"{ctx}.slow"),
        spread_cents=_as_float(_require(obj, "spread_cents", ctx), f"{ctx}.spread_cents"),
        stack=str(_require(obj, "stack", ctx)),
    )


def _ribbon_frame(rows: Any, ctx: str) -> pd.DataFrame:
    """Build the ribbon DataFrame the duration/momentum gates walk via ribbon_at."""
    if not isinstance(rows, list):
        raise BadPayload(f"{ctx}: expected a list of ribbon rows, got {type(rows).__name__}")
    recs = []
    for i, r in enumerate(rows):
        if not isinstance(r, Mapping):
            raise BadPayload(f"{ctx}[{i}]: expected a ribbon object")
        recs.append({
            "fast": _as_float(r.get("fast", float("nan")), f"{ctx}[{i}].fast"),
            "pivot": _as_float(r.get("pivot", float("nan")), f"{ctx}[{i}].pivot"),
            "slow": _as_float(r.get("slow", float("nan")), f"{ctx}[{i}].slow"),
            "spread_cents": _as_float(r.get("spread_cents", 0.0), f"{ctx}[{i}].spread_cents"),
            "stack": str(r.get("stack", "WARMUP")),
        })
    return pd.DataFrame(recs, columns=["fast", "pivot", "slow", "spread_cents", "stack"])


def _parse_time(v: Any, ctx: str) -> dt.time:
    """Parse an "HH:MM" (or "HH:MM:SS") string into a datetime.time."""
    if not isinstance(v, str):
        raise BadPayload(f"{ctx}: expected an 'HH:MM' time string, got {v!r}")
    try:
        parts = [int(x) for x in v.split(":")]
    except ValueError:
        raise BadPayload(f"{ctx}: malformed time {v!r} (expected 'HH:MM')")
    if not (1 <= len(parts) <= 3):
        raise BadPayload(f"{ctx}: malformed time {v!r} (expected 'HH:MM')")
    try:
        return dt.time(*parts)
    except ValueError as exc:
        raise BadPayload(f"{ctx}: invalid time {v!r} ({exc})")


def _coerce_score_kwargs(raw: Any, ctx: str) -> dict:
    """Forward score kwargs verbatim, decoding the few time-typed ones.

    ``no_trade_before`` -> dt.time, ``no_trade_window`` -> (dt.time, dt.time),
    ``disable_filters`` -> list[int]. Everything else passes through unchanged so
    this boundary never drifts from the underlying evaluate_* signatures.
    """
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise BadPayload(f"{ctx}: expected an object, got {type(raw).__name__}")
    out = dict(raw)
    if "no_trade_before" in out and out["no_trade_before"] is not None:
        out["no_trade_before"] = _parse_time(out["no_trade_before"], f"{ctx}.no_trade_before")
    if "no_trade_window" in out and out["no_trade_window"] is not None:
        win = out["no_trade_window"]
        if not isinstance(win, (list, tuple)) or len(win) != 2:
            raise BadPayload(f"{ctx}.no_trade_window: expected ['HH:MM','HH:MM']")
        out["no_trade_window"] = (
            _parse_time(win[0], f"{ctx}.no_trade_window[0]"),
            _parse_time(win[1], f"{ctx}.no_trade_window[1]"),
        )
    if "disable_filters" in out and out["disable_filters"] is not None:
        df = out["disable_filters"]
        if not isinstance(df, list):
            raise BadPayload(f"{ctx}.disable_filters: expected a list of ints")
        out["disable_filters"] = [_as_int(x, f"{ctx}.disable_filters[]") for x in df]
    return out


def build_bar_context(d: Mapping[str, Any]) -> BarContext:
    """Construct a filters.BarContext from the ``bar_ctx`` JSON object.

    Validates every field at the boundary; any gap raises ``BadPayload`` (rendered
    as SKIP_BAD_INPUT). Optional fields take the SAME defaults the BarContext
    dataclass declares.
    """
    ctx = "bar_ctx"
    ts_raw = _require(d, "timestamp_et", ctx)
    try:
        timestamp_et = dt.datetime.fromisoformat(str(ts_raw))
    except ValueError as exc:
        raise BadPayload(f"{ctx}.timestamp_et: not ISO-8601 ({exc}): {ts_raw!r}")

    ribbon_history_raw = d.get("ribbon_history", [])
    if not isinstance(ribbon_history_raw, list):
        raise BadPayload(f"{ctx}.ribbon_history: expected a list")
    ribbon_history = [
        _ribbon_state(r, f"{ctx}.ribbon_history[{i}]")
        for i, r in enumerate(ribbon_history_raw)
    ]

    levels_active = d.get("levels_active", [])
    if not isinstance(levels_active, list):
        raise BadPayload(f"{ctx}.levels_active: expected a list of floats")
    multi_day_levels = d.get("multi_day_levels", [])
    if not isinstance(multi_day_levels, list):
        raise BadPayload(f"{ctx}.multi_day_levels: expected a list of floats")

    level_states = d.get("level_states", {})
    if not isinstance(level_states, Mapping):
        raise BadPayload(f"{ctx}.level_states: expected an object")

    htf = d.get("htf_15m_stack", None)
    if htf is not None and not isinstance(htf, str):
        raise BadPayload(f"{ctx}.htf_15m_stack: expected a string or null")

    fhh = d.get("fhh_level", None)

    return BarContext(
        bar_idx=_as_int(_require(d, "bar_idx", ctx), f"{ctx}.bar_idx"),
        timestamp_et=timestamp_et,
        bar=_bar_series(_require(d, "bar", ctx), f"{ctx}.bar"),
        prior_bars=_bars_frame(_require(d, "prior_bars", ctx), f"{ctx}.prior_bars"),
        ribbon_now=_ribbon_state(d.get("ribbon_now"), f"{ctx}.ribbon_now"),
        ribbon_history=ribbon_history,
        vix_now=_as_float(_require(d, "vix_now", ctx), f"{ctx}.vix_now"),
        vix_prior=_as_float(_require(d, "vix_prior", ctx), f"{ctx}.vix_prior"),
        vol_baseline_20=_as_float(d.get("vol_baseline_20", 0.0), f"{ctx}.vol_baseline_20"),
        range_baseline_20=_as_float(d.get("range_baseline_20", 0.0), f"{ctx}.range_baseline_20"),
        levels_active=[_as_float(x, f"{ctx}.levels_active[]") for x in levels_active],
        multi_day_levels=[_as_float(x, f"{ctx}.multi_day_levels[]") for x in multi_day_levels],
        htf_15m_stack=htf,
        level_states=dict(level_states),
        fhh_level=(None if fhh is None else _as_float(fhh, f"{ctx}.fhh_level")),
        vix_5d_ma=_as_float(d.get("vix_5d_ma", 0.0), f"{ctx}.vix_5d_ma"),
        vix_20d_ma=_as_float(d.get("vix_20d_ma", 0.0), f"{ctx}.vix_20d_ma"),
    )


# --------------------------------------------------------------------------- #
# Side / quality-tier / has_level derivation.
#
# This is the ONLY glue in the shim. It is a VERBATIM mirror of the orchestrator's
# routing + quality-tier logic (backtest/lib/orchestrator.py ~1093-1196) — the
# portion that is PURE over the two score results (no per-day mutable state). It
# bridges score_bar's two-sided ScoreResult into the single GateContext the gates
# consume. ``test_engine_cli_parity.py`` proves it produces the SAME side/tier the
# orchestrator derives, so the shim adds no decision logic of its own.
#
# The orchestrator's quality-tier block ALSO computes a leg-2 ("TRENDLINE_LEG2")
# branch and the escalation lock — both depend on MUTABLE per-day state
# (setup_quality_taken_today / setup_last_stopped_today / last-exit time) that does
# NOT exist for a single stateless tick. None of the 15 entry gates reads the tier
# beyond the labels {"LEVEL","TRENDLINE","ELITE"} (gates 1,2,3,10), so the
# stateless derivation here yields the identical gate verdict. The leg-2 / lock
# decision (SKIP_QUALITY_LOCK) stays the caller's responsibility, as scoped.
# --------------------------------------------------------------------------- #


def _derive_routing(score: ScoreResult) -> tuple[Optional[str], list, Optional[float]]:
    """Return (winning_side, winning_triggers, winning_level). Mirror of orch ~1093-1119."""
    bear = score.bear
    bull = score.bull
    bear_passed = bear.passed
    bull_passed = bull is not None and bull.passed
    if bear_passed and bull_passed:
        if len(bear.triggers_fired) > len(bull.triggers_fired):
            return "P", list(bear.triggers_fired), bear.rejection_level
        if len(bull.triggers_fired) > len(bear.triggers_fired):
            return "C", list(bull.triggers_fired), bull.reclaim_level
        return None, [], None  # tied -> neither
    if bear_passed:
        return "P", list(bear.triggers_fired), bear.rejection_level
    if bull_passed:
        return "C", list(bull.triggers_fired), bull.reclaim_level
    return None, [], None


def _derive_tier(winning_side: str, winning_triggers: list) -> tuple[str, bool]:
    """Return (quality_tier, has_level). Stateless mirror of orch ~1150-1196.

    Stateless: the leg-2 / escalation-lock branches (which need per-day mutable
    state) are intentionally not reproduced — they do not change any of the 15
    entry gates' verdicts (the gates only read the labels LEVEL/TRENDLINE/ELITE).
    """
    level_tied_trig = "level_reclaim" if winning_side == "C" else "level_rejection"
    seq_trig = "sequence_reclaim" if winning_side == "C" else "sequence_rejection"
    has_level = level_tied_trig in winning_triggers
    has_confluence = "confluence" in winning_triggers
    has_sequence = seq_trig in winning_triggers
    has_ribbon_flip = "ribbon_flip" in winning_triggers
    has_trendline = "trendline_rejection" in winning_triggers
    n_triggers = len(winning_triggers)

    if (has_confluence and has_ribbon_flip) or n_triggers >= 3:
        return "SUPER", has_level
    if has_confluence or has_sequence:
        return "ELITE", has_level
    if has_level:
        return "LEVEL", has_level
    if has_trendline:
        return "TRENDLINE", has_level
    return "BASE", has_level


# --------------------------------------------------------------------------- #
# The decision boundary: payload dict -> verdict dict. Pure marshalling around
# score_bar + evaluate_gates. No I/O here (the I/O lives in main()).
# --------------------------------------------------------------------------- #


def decide_payload(payload: Mapping[str, Any]) -> dict:
    """Marshal a parsed JSON payload into a verdict dict.

    Pure: constructs the engine inputs, calls ``score_bar`` then ``evaluate_gates``,
    and assembles the verdict. Raises ``BadPayload`` on any malformed input. Adds NO
    decision logic beyond the documented orchestrator-verbatim routing/tier
    derivation (``_derive_routing`` / ``_derive_tier``).
    """
    if not isinstance(payload, Mapping):
        raise BadPayload("top-level payload must be a JSON object")

    bar_ctx_raw = _require(payload, "bar_ctx", "payload")
    if not isinstance(bar_ctx_raw, Mapping):
        raise BadPayload("payload.bar_ctx: expected an object")

    ctx = build_bar_context(bar_ctx_raw)

    score_params = payload.get("score_params", {})
    if not isinstance(score_params, Mapping):
        raise BadPayload("payload.score_params: expected an object")
    enable_bullish = bool(score_params.get("enable_bullish", True))
    bear_kwargs = _coerce_score_kwargs(score_params.get("bear_kwargs"), "score_params.bear_kwargs")
    bull_kwargs = _coerce_score_kwargs(score_params.get("bull_kwargs"), "score_params.bull_kwargs")

    # 1) SCORE both sides (the shared scoring entry point).
    score: ScoreResult = score_bar(
        ctx,
        enable_bullish=enable_bullish,
        bear_kwargs=bear_kwargs,
        bull_kwargs=bull_kwargs,
    )

    # 2) ROUTE to a winning side + quality tier (orchestrator-verbatim glue).
    winning_side, winning_triggers, winning_level = _derive_routing(score)

    gate_params = payload.get("gate_params", {})
    if not isinstance(gate_params, Mapping):
        raise BadPayload("payload.gate_params: expected an object")

    # Historical frames the two context-needing gates read (optional unless armed).
    spy_df = (
        _bars_frame(payload["spy_df"], "spy_df") if payload.get("spy_df") is not None else None
    )
    ribbon_df = (
        _ribbon_frame(payload["ribbon_df"], "ribbon_df")
        if payload.get("ribbon_df") is not None
        else None
    )

    # 3) Build verdict. No side won -> HOLD (no gates evaluated, matching the
    #    orchestrator: gates only run inside the winning_side branch).
    base = {
        "side": winning_side,
        "setup_name": None,
        "bear_score": score.bear_score,
        "bull_score": score.bull_score,
        "bear_blockers": list(score.bear_blockers),
        "bull_blockers": (None if score.bull_blockers is None else list(score.bull_blockers)),
        "triggers_fired": list(winning_triggers),
        "rejection_level": winning_level,
        "quality_tier": None,
        "gate": None,
    }

    if winning_side is None:
        base["verdict"] = "HOLD"
        base["reason"] = "no setup passed scoring (neither bear nor bull)"
        return base

    setup_name = (
        "BEARISH_REJECTION_RIDE_THE_RIBBON" if winning_side == "P"
        else "BULLISH_RECLAIM_RIDE_THE_RIBBON"
    )
    quality_tier, has_level = _derive_tier(winning_side, winning_triggers)
    base["setup_name"] = setup_name
    base["quality_tier"] = quality_tier

    gate_ctx = GateContext(
        winning_side=winning_side,
        winning_triggers=winning_triggers,
        quality_tier=quality_tier,
        has_level=has_level,
        bar=ctx.bar,
        bar_idx=ctx.bar_idx,
        bar_time=ctx.timestamp_et,
        vix_now=ctx.vix_now,
        ribbon_spread_cents=(ctx.ribbon_now.spread_cents if ctx.ribbon_now is not None else 0.0),
        ribbon_stack=(ctx.ribbon_now.stack if ctx.ribbon_now is not None else ""),
        spy_df=spy_df,
        ribbon_df=ribbon_df,
    )

    # 4) GATE the entry (the 15 ordered entry gates).
    gate: Optional[GateBlock] = evaluate_gates(gate_ctx, gate_params)

    if gate is not None:
        base["verdict"] = gate.action
        base["gate"] = {
            "gate_id": gate.gate_id,
            "action": gate.action,
            "blockers": list(gate.blockers),
        }
        base["reason"] = f"blocked by entry gate {gate.gate_id}"
        return base

    base["verdict"] = "ENTER_BEAR" if winning_side == "P" else "ENTER_BULL"
    base["reason"] = f"{setup_name} passed scoring + all entry gates (tier {quality_tier})"
    return base


# --------------------------------------------------------------------------- #
# CLI entry point — the only I/O. Reads stdin, writes ONE JSON line to stdout.
# --------------------------------------------------------------------------- #


def _emit(obj: dict) -> None:
    """Write one compact JSON object to stdout (the machine boundary's only output)."""
    sys.stdout.write(json.dumps(obj, separators=(",", ":"), default=str))
    sys.stdout.write("\n")
    sys.stdout.flush()


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="engine_cli",
        description=(
            "Pure stdin/stdout boundary over the shared decision core "
            "(score_bar + evaluate_gates). Reads ONE JSON payload on stdin, writes "
            "ONE compact JSON verdict on stdout. No I/O beyond stdin/stdout, "
            "deterministic, fail-closed on bad input. See the module docstring for "
            "the full input contract + output shape."
        ),
        epilog="echo '{\"bar_ctx\": {...}}' | python -m backtest.lib.engine.engine_cli",
    )
    parser.parse_args(argv)

    # Read + parse stdin. Any failure -> clean JSON SKIP_BAD_INPUT, exit 1.
    try:
        raw = sys.stdin.read()
    except Exception as exc:  # extremely defensive — stdin read should not fail
        _emit({"verdict": "SKIP_BAD_INPUT", "error": f"could not read stdin: {exc}",
               "side": None, "gate": None})
        return 1

    if not raw or not raw.strip():
        _emit({"verdict": "SKIP_BAD_INPUT", "error": "empty stdin (expected a JSON payload)",
               "side": None, "gate": None})
        return 1

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        _emit({"verdict": "SKIP_BAD_INPUT", "error": f"invalid JSON: {exc}",
               "side": None, "gate": None})
        return 1

    try:
        verdict = decide_payload(payload)
    except BadPayload as exc:
        _emit({"verdict": "SKIP_BAD_INPUT", "error": str(exc), "side": None, "gate": None})
        return 1
    except Exception as exc:  # never leak a traceback to a machine boundary
        _emit({"verdict": "SKIP_BAD_INPUT",
               "error": f"unexpected engine error: {type(exc).__name__}: {exc}",
               "side": None, "gate": None})
        return 1

    _emit(verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
