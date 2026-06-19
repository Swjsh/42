"""Parity: engine_cli verdict == direct score_bar + evaluate_gates.

Spec: ``docs/SHARED-DECISION-LIBRARY-MIGRATION.md`` §3 "Phase 3 — ... a thin CLI
``backtest/lib/engine/engine_cli.py`` ... reads a BarContext-equivalent JSON on
stdin ... calls ``decide()`` ... prints the EngineVerdict as JSON".

The shim is a PURE BOUNDARY: JSON <-> engine objects -> JSON. It must add no
decision logic — its verdict for any payload must equal what calling
``engine.score.score_bar`` + ``engine.gates.evaluate_gates`` DIRECTLY produces
(with the orchestrator-verbatim side/tier derivation the shim mirrors). These
tests prove exactly that, reusing the fixtures from ``test_engine_score_parity.py``
(BarContext builders) and ``test_engine_gates_parity.py`` (gate scenarios).

Three kinds of proof:
  1. ``test_cli_verdict_matches_direct_*`` — the in-process ``decide_payload``
     verdict == a direct, independent re-computation (score -> route -> tier ->
     gate). This is the "shim adds no logic" proof.
  2. ``test_cli_subprocess_*`` — the REAL process boundary: pipe JSON to
     ``python -m backtest.lib.engine.engine_cli`` and assert a well-formed verdict
     on stdout + exit 0, and that it equals the in-process verdict.
  3. ``test_cli_bad_input_*`` — malformed payloads yield a clean JSON
     ``SKIP_BAD_INPUT`` error on stdout + nonzero exit, never a traceback.

Run:  cd backtest && python -m pytest tests/test_engine_cli_parity.py -q
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.engine.engine_cli import _coerce_score_kwargs, decide_payload  # noqa: E402
from lib.engine.gates import GateContext, evaluate_gates  # noqa: E402
from lib.engine.score import score_bar  # noqa: E402
from lib.filters import BarContext  # noqa: E402
from lib.ribbon import RibbonState  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures — same builders as test_engine_score_parity.py (BarContext) so the CLI
# corpus exercises the identical clean-pass + boundary contexts, with NO master-CSV
# dependency (always runs).
# --------------------------------------------------------------------------- #


def _bear_ribbon(spread_cents: float = 50.0) -> RibbonState:
    return RibbonState(fast=539.0, pivot=540.0, slow=541.0, spread_cents=spread_cents, stack="BEAR")


def _bull_ribbon(spread_cents: float = 50.0) -> RibbonState:
    return RibbonState(fast=541.0, pivot=540.0, slow=539.0, spread_cents=spread_cents, stack="BULL")


def _make_bar(open_=540.5, high=541.5, low=539.5, close=540.3, volume=900_000) -> pd.Series:
    return pd.Series({"open": open_, "high": high, "low": low, "close": close, "volume": volume})


def _prior_bars() -> pd.DataFrame:
    return pd.DataFrame(
        [{"open": 540.0, "high": 540.4, "low": 539.6, "close": 540.0, "volume": 800_000}
         for _ in range(30)]
    )


def _bear_ctx(time_str="10:00", vix_now=17.5, vix_prior=17.3, ribbon=None,
              bar=None, vol_baseline=1_000_000.0, levels_active=None) -> BarContext:
    ts = dt.datetime.fromisoformat(f"2026-05-20 {time_str}:00").replace(
        tzinfo=dt.timezone(dt.timedelta(hours=-4))
    )
    return BarContext(
        bar_idx=4, timestamp_et=ts,
        bar=_make_bar() if bar is None else bar,
        prior_bars=_prior_bars(),
        ribbon_now=_bear_ribbon() if ribbon is None else ribbon,
        ribbon_history=[_bear_ribbon() if ribbon is None else ribbon],
        vix_now=vix_now, vix_prior=vix_prior,
        vol_baseline_20=vol_baseline, range_baseline_20=1.0,
        levels_active=[540.8] if levels_active is None else levels_active,
        multi_day_levels=[], htf_15m_stack="BEAR", level_states={},
    )


def _bull_ctx(time_str="10:00", vix_now=17.1, vix_prior=17.3, ribbon=None,
              bar=None, vol_baseline=1_000_000.0, levels_active=None) -> BarContext:
    ts = dt.datetime.fromisoformat(f"2026-05-20 {time_str}:00").replace(
        tzinfo=dt.timezone(dt.timedelta(hours=-4))
    )
    green = _make_bar(open_=540.0, high=541.5, low=539.8, close=541.2, volume=750_000)
    return BarContext(
        bar_idx=4, timestamp_et=ts,
        bar=green if bar is None else bar,
        prior_bars=_prior_bars(),
        ribbon_now=_bull_ribbon() if ribbon is None else ribbon,
        ribbon_history=[_bull_ribbon() if ribbon is None else ribbon],
        vix_now=vix_now, vix_prior=vix_prior,
        vol_baseline_20=vol_baseline, range_baseline_20=1.0,
        levels_active=[540.5] if levels_active is None else levels_active,
        multi_day_levels=[], htf_15m_stack="BULL", level_states={},
    )


# --------------------------------------------------------------------------- #
# JSON marshalling helpers — turn a BarContext / ribbon frame into the payload
# shape the CLI accepts. (These mirror the documented input contract.)
# --------------------------------------------------------------------------- #


def _bar_to_json(bar: pd.Series) -> dict:
    return {k: float(bar[k]) for k in ("open", "high", "low", "close", "volume")}


def _ribbon_to_json(r):
    if r is None:
        return None
    return {"fast": r.fast, "pivot": r.pivot, "slow": r.slow,
            "spread_cents": r.spread_cents, "stack": r.stack}


def _ctx_to_json(ctx: BarContext) -> dict:
    return {
        "bar_idx": ctx.bar_idx,
        "timestamp_et": ctx.timestamp_et.isoformat(),
        "bar": _bar_to_json(ctx.bar),
        "prior_bars": [_bar_to_json(r) for _, r in ctx.prior_bars.iterrows()],
        "ribbon_now": _ribbon_to_json(ctx.ribbon_now),
        "ribbon_history": [_ribbon_to_json(r) for r in ctx.ribbon_history],
        "vix_now": ctx.vix_now,
        "vix_prior": ctx.vix_prior,
        "vol_baseline_20": ctx.vol_baseline_20,
        "range_baseline_20": ctx.range_baseline_20,
        "levels_active": list(ctx.levels_active),
        "multi_day_levels": list(ctx.multi_day_levels),
        "htf_15m_stack": ctx.htf_15m_stack,
        "level_states": {},
        "vix_5d_ma": ctx.vix_5d_ma,
        "vix_20d_ma": ctx.vix_20d_ma,
    }


def _ribbon_df_to_json(df: pd.DataFrame) -> list:
    return [
        {"fast": float(r["fast"]), "pivot": float(r["pivot"]), "slow": float(r["slow"]),
         "spread_cents": float(r["spread_cents"]), "stack": str(r["stack"])}
        for _, r in df.iterrows()
    ]


# --------------------------------------------------------------------------- #
# Independent re-implementation of the verdict, computed DIRECTLY from score_bar +
# evaluate_gates (NOT via the CLI). This is the oracle the shim must match. It
# repeats the orchestrator's routing/tier derivation so the comparison is against
# the engine primitives, not against the shim's own helpers.
# --------------------------------------------------------------------------- #


def _direct_verdict(ctx: BarContext, gate_params: dict, *, enable_bullish=True,
                    bear_kwargs=None, bull_kwargs=None,
                    spy_df=None, ribbon_df=None) -> dict:
    score = score_bar(ctx, enable_bullish=enable_bullish,
                      bear_kwargs=bear_kwargs or {}, bull_kwargs=bull_kwargs or {})
    bear, bull = score.bear, score.bull
    bear_passed = bear.passed
    bull_passed = bull is not None and bull.passed

    side, trigs, level = None, [], None
    if bear_passed and bull_passed:
        if len(bear.triggers_fired) > len(bull.triggers_fired):
            side, trigs, level = "P", list(bear.triggers_fired), bear.rejection_level
        elif len(bull.triggers_fired) > len(bear.triggers_fired):
            side, trigs, level = "C", list(bull.triggers_fired), bull.reclaim_level
    elif bear_passed:
        side, trigs, level = "P", list(bear.triggers_fired), bear.rejection_level
    elif bull_passed:
        side, trigs, level = "C", list(bull.triggers_fired), bull.reclaim_level

    out = {
        "side": side, "setup_name": None,
        "bear_score": score.bear_score, "bull_score": score.bull_score,
        "bear_blockers": list(score.bear_blockers),
        "bull_blockers": (None if score.bull_blockers is None else list(score.bull_blockers)),
        "triggers_fired": list(trigs), "rejection_level": level,
        "quality_tier": None, "gate": None,
    }
    if side is None:
        out["verdict"] = "HOLD"
        out["reason"] = "no setup passed scoring (neither bear nor bull)"
        return out

    level_tied = "level_reclaim" if side == "C" else "level_rejection"
    seq = "sequence_reclaim" if side == "C" else "sequence_rejection"
    has_level = level_tied in trigs
    if ("confluence" in trigs and "ribbon_flip" in trigs) or len(trigs) >= 3:
        tier = "SUPER"
    elif "confluence" in trigs or seq in trigs:
        tier = "ELITE"
    elif has_level:
        tier = "LEVEL"
    elif "trendline_rejection" in trigs:
        tier = "TRENDLINE"
    else:
        tier = "BASE"
    setup_name = ("BEARISH_REJECTION_RIDE_THE_RIBBON" if side == "P"
                  else "BULLISH_RECLAIM_RIDE_THE_RIBBON")
    out["setup_name"] = setup_name
    out["quality_tier"] = tier

    gctx = GateContext(
        winning_side=side, winning_triggers=trigs, quality_tier=tier, has_level=has_level,
        bar=ctx.bar, bar_idx=ctx.bar_idx, bar_time=ctx.timestamp_et, vix_now=ctx.vix_now,
        ribbon_spread_cents=(ctx.ribbon_now.spread_cents if ctx.ribbon_now else 0.0),
        ribbon_stack=(ctx.ribbon_now.stack if ctx.ribbon_now else ""),
        spy_df=spy_df, ribbon_df=ribbon_df,
    )
    gate = evaluate_gates(gctx, gate_params)
    if gate is not None:
        out["verdict"] = gate.action
        out["gate"] = {"gate_id": gate.gate_id, "action": gate.action,
                       "blockers": list(gate.blockers)}
        out["reason"] = f"blocked by entry gate {gate.gate_id}"
        return out
    out["verdict"] = "ENTER_BEAR" if side == "P" else "ENTER_BULL"
    out["reason"] = f"{setup_name} passed scoring + all entry gates (tier {tier})"
    return out


def _roundtrip_json(obj: dict) -> dict:
    """Normalise a verdict through JSON so float/list types match the CLI's output."""
    return json.loads(json.dumps(obj, default=str))


# =========================================================================== #
# 1. SHIM == DIRECT — the core "pure boundary" proof
# =========================================================================== #


# (label, ctx-builder, gate_params, score_params)
_SCORE_CORPUS = [
    ("bear_clean_no_gates", _bear_ctx(), {}, {}),
    ("bull_clean_no_gates", _bull_ctx(), {}, {}),
    ("bear_before_0935", _bear_ctx(time_str="09:30"), {}, {}),
    ("bear_ribbon_bull", _bear_ctx(ribbon=_bull_ribbon()), {}, {}),
    ("bear_vix_falling", _bear_ctx(vix_now=17.25, vix_prior=17.50), {}, {}),
    ("bear_no_level", _bear_ctx(levels_active=[200.0]), {}, {}),
    ("bull_vix_hard_cap", _bull_ctx(vix_now=18.0, vix_prior=18.3), {}, {}),
    ("bull_no_level", _bull_ctx(levels_active=[200.0]), {}, {}),
    # gates armed on top of a passing setup
    ("bear_vix_cap_armed", _bear_ctx(vix_now=17.5), {"vix_bear_hard_cap": 15.0}, {}),
    ("bear_level_rej_gate", _bear_ctx(), {"block_level_rejection": True}, {}),
    ("bear_body_gate", _bear_ctx(), {"entry_bar_body_pct_min": 0.95}, {}),
    ("bull_body_gate", _bull_ctx(), {"entry_bar_body_pct_min_bull": 0.95}, {}),
    # score kwargs forwarded
    ("bear_soft_mode_kw", _bear_ctx(vix_now=17.25, vix_prior=17.50), {},
     {"bear_kwargs": {"vix_soft_mode": True}}),
    ("bear_no_bull", _bear_ctx(), {}, {"enable_bullish": False}),
    ("bear_no_trade_before_kw", _bear_ctx(time_str="09:45"), {},
     {"bear_kwargs": {"no_trade_before": "10:00"}}),
]


@pytest.mark.parametrize("label,ctx,gate_params,score_params",
                         _SCORE_CORPUS, ids=[c[0] for c in _SCORE_CORPUS])
def test_cli_verdict_matches_direct(label, ctx, gate_params, score_params):
    """decide_payload(payload) must equal the direct score_bar+evaluate_gates verdict."""
    payload = {
        "bar_ctx": _ctx_to_json(ctx),
        "gate_params": gate_params,
        "score_params": score_params,
    }
    shim = decide_payload(payload)
    # Build the SAME engine inputs the shim does (reuse its kwarg coercion) so the
    # oracle is a direct engine call, not a re-guess of the score kwargs.
    direct = _direct_verdict(
        ctx, gate_params,
        enable_bullish=bool(score_params.get("enable_bullish", True)),
        bear_kwargs=_coerce_score_kwargs(score_params.get("bear_kwargs"), "t.bear"),
        bull_kwargs=_coerce_score_kwargs(score_params.get("bull_kwargs"), "t.bull"),
    )
    assert _roundtrip_json(shim) == _roundtrip_json(direct), (
        f"[{label}] shim verdict != direct engine verdict\n"
        f"shim={shim}\ndirect={direct}"
    )


def test_cli_verdict_with_historical_frames_matches_direct():
    """Gates needing spy_df/ribbon_df (look-ahead fill + ribbon momentum) parity."""
    # require_bearish_fill_bar with a BULLISH fill bar -> SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY.
    ctx = _bear_ctx()
    object.__setattr__(ctx, "bar_idx", 0)  # trigger at idx 0; fill bar at idx 1
    spy_df = pd.DataFrame([
        {"open": 540.5, "high": 541.5, "low": 539.5, "close": 540.3, "volume": 1},
        {"open": 540.3, "high": 541.9, "low": 540.0, "close": 541.8, "volume": 1},  # green fill
    ])
    gate_params = {"require_bearish_fill_bar": True}
    payload = {
        "bar_ctx": _ctx_to_json(ctx),
        "gate_params": gate_params,
        "spy_df": [_bar_to_json(r) for _, r in spy_df.iterrows()],
    }
    shim = decide_payload(payload)
    direct = _direct_verdict(ctx, gate_params, spy_df=spy_df)
    assert _roundtrip_json(shim) == _roundtrip_json(direct)
    # only meaningful if this ctx actually routes to a bear entry pre-gate
    if direct["side"] == "P":
        assert shim["verdict"] == "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY"


# =========================================================================== #
# 2. REAL PROCESS BOUNDARY — pipe JSON through the CLI as a subprocess
# =========================================================================== #


def _run_cli(stdin_text: str) -> subprocess.CompletedProcess:
    """Invoke `python -m backtest.lib.engine.engine_cli` from the repo root."""
    return subprocess.run(
        [sys.executable, "-m", "backtest.lib.engine.engine_cli"],
        input=stdin_text, capture_output=True, text=True, cwd=str(REPO),
    )


def test_cli_subprocess_returns_wellformed_verdict():
    """The real process: valid payload -> exit 0 + a verdict JSON == in-process."""
    ctx = _bear_ctx()
    payload = {"bar_ctx": _ctx_to_json(ctx), "gate_params": {}, "score_params": {}}
    proc = _run_cli(json.dumps(payload))
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    out = json.loads(proc.stdout)
    assert "verdict" in out and "side" in out and "gate" in out
    assert out["verdict"] in {"ENTER_BEAR", "ENTER_BULL", "HOLD"} or out["verdict"].startswith("SKIP_")
    # process-boundary verdict equals the in-process one
    assert out == _roundtrip_json(decide_payload(payload))


def test_cli_subprocess_skip_gate_verdict():
    """A payload whose gate fires returns the SKIP action over the process boundary."""
    ctx = _bear_ctx(vix_now=30.0)
    payload = {"bar_ctx": _ctx_to_json(ctx), "gate_params": {"vix_bear_hard_cap": 15.0}}
    proc = _run_cli(json.dumps(payload))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    # this ctx routes bear and VIX 30 >= cap 15 -> the VIX gate fires
    if out["side"] == "P":
        assert out["verdict"] == "SKIP_VIX_BEAR_HIGH"
        assert out["gate"]["gate_id"] == "vix_bear_hard_cap"


# =========================================================================== #
# 3. FAIL-CLOSED — malformed input -> clean JSON error, nonzero exit, no traceback
# =========================================================================== #


@pytest.mark.parametrize("bad_stdin,why", [
    ("", "empty stdin"),
    ("   \n  ", "whitespace only"),
    ("{not json", "broken json"),
    ("[1,2,3]", "top-level not an object"),
    ("{}", "missing bar_ctx"),
    (json.dumps({"bar_ctx": {"bar_idx": 4}}), "bar_ctx missing required fields"),
    (json.dumps({"bar_ctx": {
        "bar_idx": "x", "timestamp_et": "2026-05-20T10:00:00-04:00",
        "bar": {"open": 1, "high": 1, "low": 1, "close": 1}, "prior_bars": [],
        "vix_now": 1, "vix_prior": 1}}), "non-int bar_idx"),
    (json.dumps({"bar_ctx": {
        "bar_idx": 4, "timestamp_et": "not-a-date",
        "bar": {"open": 1, "high": 1, "low": 1, "close": 1}, "prior_bars": [],
        "vix_now": 1, "vix_prior": 1}}), "bad timestamp"),
])
def test_cli_bad_input_in_process(bad_stdin, why):
    """decide_payload raises BadPayload (caught by main) — confirm the rendered shape
    by exercising the process boundary, which is what the heartbeat sees."""
    proc = _run_cli(bad_stdin)
    assert proc.returncode == 1, f"[{why}] expected exit 1, got {proc.returncode}"
    # stdout is a clean JSON SKIP_BAD_INPUT object; no traceback anywhere.
    out = json.loads(proc.stdout)
    assert out["verdict"] == "SKIP_BAD_INPUT", f"[{why}] {out}"
    assert isinstance(out.get("error"), str) and out["error"], f"[{why}] missing error msg"
    assert out["side"] is None and out["gate"] is None
    assert "Traceback" not in proc.stdout, f"[{why}] traceback leaked to stdout"


def test_cli_no_traceback_on_stdout_ever():
    """Even a payload that trips an unexpected internal error must not leak a traceback."""
    # prior_bars as a non-list passes the early checks differently; ensure clean error.
    payload = {"bar_ctx": {
        "bar_idx": 4, "timestamp_et": "2026-05-20T10:00:00-04:00",
        "bar": {"open": 540.5, "high": 541.5, "low": 539.5, "close": 540.3, "volume": 1},
        "prior_bars": "not-a-list", "vix_now": 17.5, "vix_prior": 17.3}}
    proc = _run_cli(json.dumps(payload))
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["verdict"] == "SKIP_BAD_INPUT"
    assert "Traceback" not in proc.stdout and "Traceback" not in (proc.stdout or "")


# =========================================================================== #
# 4. DETERMINISM — same payload, same verdict
# =========================================================================== #


def test_cli_is_deterministic():
    ctx = _bear_ctx()
    payload = {"bar_ctx": _ctx_to_json(ctx), "gate_params": {"vix_bear_hard_cap": 23.0}}
    v1 = decide_payload(payload)
    v2 = decide_payload(json.loads(json.dumps(payload)))
    assert _roundtrip_json(v1) == _roundtrip_json(v2)
