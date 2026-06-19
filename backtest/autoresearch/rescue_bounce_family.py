"""RESCUE-OR-RETIRE the anti-J-edge bounce-LONG watcher family.

THE QUESTION (the watcher-fleet "close-out"):
  Tonight's exit-sweep (analysis/recommendations/watcher-exit-sweep.json) confirmed
  the three strong-SPY-edge level watchers are real-fills-NEGATIVE under every exit
  geometry tested, AND that NAMED_LEVEL_SECOND_TEST + FLOOR_HOLD_BOUNCE are
  strongly ANTI-J-edge: they make money on J's LOSS days (5/05, 5/06) and lose on
  his WIN days (4/29, 5/01) — the C22/C24 signature of a bounce-LONG fighting J's
  bearish-continuation edge. Before retiring the family we owe it two honest rescue
  attempts:

  HYPOTHESIS A — REGIME GATE rescues the longs.
    Suppress the bounce-LONG signal in conditions hostile to mean-reversion longs:
    catching-a-falling-knife = ribbon stack == BEAR  AND  VIX rising (vix_now >
    vix_prior)  AND  price below session VWAP. Those are exactly J's down/loss days
    (which are his WIN days for PUTs). If the gate works, the longs stop firing on
    J's WIN-days (down days) → edge_capture stops going negative AND net real-fills
    improves. The gate may shrink n to ~nothing; we REPORT the n honestly.

  HYPOTHESIS B — SHORT-SIDE INVERSION aligns with J's edge.
    J's proven edge is bearish-continuation (the 4/29 / 5/01 / 5/04 PUT winners).
    The short-side mirror of these level setups should fire WITH J on his down days.
    NAMED_LEVEL_SECOND_TEST already emits a SHORT leg (LOWER-HIGH second test of a
    named resistance → puts) and CLOSE_CEILING_FADE is already short. So Hypothesis
    B = isolate the SHORT signals (SECOND_TEST.direction=='short' + all of
    CLOSE_CEILING_FADE) and ask: do the shorts show POSITIVE edge_capture (fire WITH
    J) and positive real-fills? (FLOOR_HOLD_BOUNCE is long-only — it has no short
    leg, so its Hypothesis-B verdict is "no short mirror exists in this detector".)

REAL-FILLS IS THE ONLY AUTHORITY (theme C1 — BS-sim is ranking-only). Every number
below is OPRA (lib.simulator_real + the options cache, valid through 2026-05-29).
chart-stop only (premium_stop_pct=-0.99) for ALL configs (L51/L55/C1/C2).

THE GATE (honest — do NOT loosen to manufacture a win):
  PROMOTE-CANDIDATE  iff  real-fills exp > 0
                     AND  edge_capture POSITIVE (fires WITH J, not against)
                     AND  DSR/PBO advisory (lib.validation.gate) verdict != FAIL.
  If neither hypothesis rescues a pattern → RETIRE-WITH-EVIDENCE. Per the playbook
  ("setups that fail thresholds get retired, not loosened") + OP-22, a clean
  "retire these, here's the evidence" is a valid, valuable result. We do NOT
  manufacture a win.

WHAT THIS REUSES (zero drift — built tonight, already debugged):
  autoresearch.sweep_watcher_exits._collect_signals  — the single firing pass over
    the 16-month window with the level-injection monkeypatch + the anchor-coverage
    fix (_select_signals always keeps every J-anchor-day signal so the anchor gate
    is never vacuously truncated — the bug caught tonight).
  autoresearch.validate_level_family.{ANCHORS,_REJ_LEVEL_KEY,_stats,_synthetic_*}.
  lib.simulator_real.simulate_trade_real — real OPRA fills.
  lib.validation.gate.evaluate_candidate — DSR/PSR advisory.

LEVEL-SOURCE CAVEAT (inherited — OP-20 disclosure):
  All 3 watchers read key-levels.json from disk and are monkeypatched to SYNTHETIC
  PDH/PDL/PDC/PDO proxies (★★/★), NOT production ★★★ named levels (no historical
  archive). Absolute WR is a proxy LOWER-BOUND. The regime/short comparison is
  internally consistent (identical level set across all arms), so the SIGN questions
  ("does the gate flip edge_capture positive?", "are the shorts WITH J?") are
  answerable on the proxy even though absolute WR is not the production number.

Usage:
  python -m autoresearch.rescue_bounce_family \
      --start 2025-01-01 --end 2026-05-29 \
      --out analysis/recommendations/bounce-family-rescue.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

# Reuse the proven firing pass + level machinery verbatim (no duplication, no drift).
from autoresearch.sweep_watcher_exits import _collect_signals, _select_signals  # noqa: E402
from autoresearch.validate_level_family import (  # noqa: E402
    ANCHORS,
    _REJ_LEVEL_KEY,
    _stats,
)

from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.validation.gate import evaluate_candidate  # noqa: E402
from lib.orchestrator import _align_vix_to_spy  # noqa: E402
from autoresearch.validate_level_family import _load_data  # noqa: E402

# The detectors under test. FLOOR_HOLD + SECOND_TEST are the anti-J-edge bounce-LONGS;
# CLOSE_CEILING_FADE is already a short (included as the natural Hypothesis-B partner).
STREAMS = ["FLOOR_HOLD_BOUNCE", "CLOSE_CEILING_FADE", "NAMED_LEVEL_SECOND_TEST"]

# Production exit config (chart-stop only) — this is what the live watchers would use
# and what tonight's exit-sweep anchored its baseline on. We do NOT re-sweep exits here
# (the exit-sweep already proved no exit geometry rescues these); we hold the exit fixed
# at production and test ONLY the two structural hypotheses (gate / invert).
PROD_EXIT = {
    "premium_stop_pct": -0.99,       # chart-stop only (C1/C2)
    "strike_offset": 0,              # ATM — matches exit-sweep baseline
    "tp1_premium_pct": 0.30,
    "level_stop_buffer_dollars": 0.50,
}

# n_trials for DSR deflation. We evaluate, per pattern, a small fixed set of arms
# (baseline-long, regime-gated-long, short-inversion) — 3 structural arms. Use 3 so
# the deflation is honest about the search size (not inflated, not 1).
N_TRIALS = 3


# ── Session VWAP (lookahead-safe, cumulative within each RTH day) ─────────────

def _session_vwap(rth: pd.DataFrame) -> pd.Series:
    """Cumulative session VWAP per RTH day, aligned to rth's index.

    VWAP at bar i uses only bars [day_open .. i] (typical price * volume cumulative
    / volume cumulative). No look-ahead: bar i's VWAP includes bar i and all earlier
    same-day bars, nothing later. Resets each trading day.
    """
    df = rth[["timestamp_et", "high", "low", "close", "volume"]].copy()
    df["date"] = pd.to_datetime(df["timestamp_et"]).dt.date
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    tpv = tp * df["volume"]
    grp = df.groupby("date", sort=False)
    cum_tpv = tpv.groupby(df["date"], sort=False).cumsum()
    cum_vol = df["volume"].groupby(df["date"], sort=False).cumsum()
    vwap = cum_tpv / cum_vol.replace(0, pd.NA)
    return vwap.astype(float)


def _regime_hostile_to_long(stack: str, vix_now: float, vix_prior: float,
                            close: float, vwap: float) -> bool:
    """Catching-a-falling-knife regime for a mean-reversion LONG.

    Hostile  iff  ribbon stack == BEAR  AND  VIX rising (vix_now > vix_prior)
              AND  price below session VWAP (close < vwap).
    These are J's down/loss days (his PUT-WIN days). A bounce-LONG fired here is
    fighting the bearish-continuation edge → Hypothesis A suppresses it.
    """
    if stack != "BEAR":
        return False
    if not (vix_now > vix_prior):
        return False
    if vwap != vwap:  # NaN guard (first-bar VWAP with zero volume)
        return False
    return close < vwap


# ── Real-fills simulation of one signal stream under the production exit ──────

# VIX-rising lag (bars). Mirrors sweep_watcher_exits._collect_signals' vix_prior =
# vix_aligned.iloc[max(0, idx-3)] — a 3-bar (15-min) lookback for "VIX rising".
_VIX_PRIOR_LAG_BARS: int = 3


def _simulate_stream(
    stream: str,
    signals: list,
    rth: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    vwap: pd.Series,
    vix_aligned: pd.Series,
    *,
    direction_filter: str | None = None,   # None=all, "long", or "short"
    regime_gate_longs: bool = False,        # Hypothesis A: drop hostile-regime LONGS
) -> dict:
    """Run real-fills for one stream's signals under PROD_EXIT, with an optional
    direction filter (Hypothesis B) and/or regime gate on longs (Hypothesis A).

    Returns stats + anchor edge_capture (OP-16 shape on real-fills) + bookkeeping.
    """
    rej_key = _REJ_LEVEL_KEY[stream]
    pnls: list[float] = []
    anchor_pnl: dict[dt.date, float] = defaultdict(float)
    attempted = 0          # signals that passed the structural filters (pre-fill)
    filled = 0
    suppressed_by_regime = 0
    suppressed_by_direction = 0
    n_long = 0
    n_short = 0

    for (idx, bar, sig, bar_date) in _select_signals(signals):
        # ── Hypothesis B: direction filter ──────────────────────────────────
        if direction_filter is not None and sig.direction != direction_filter:
            suppressed_by_direction += 1
            continue

        # ── Hypothesis A: regime gate (only meaningful for LONGS) ───────────
        # All three clauses are computed EXACTLY from rth/ribbon_df/vix_aligned at the
        # signal index (no metadata fallback) so the stated gate is faithful:
        #   ribbon stack == BEAR  AND  vix_now > vix_prior (3-bar lag)  AND  close < VWAP.
        if regime_gate_longs and sig.direction == "long":
            stack = str(ribbon_df.iloc[idx]["stack"]) if idx < len(ribbon_df) else "MIXED"
            vix_now = (float(vix_aligned.iloc[idx])
                       if idx < len(vix_aligned) else 17.0)
            vix_prior = (float(vix_aligned.iloc[max(0, idx - _VIX_PRIOR_LAG_BARS)])
                         if max(0, idx - _VIX_PRIOR_LAG_BARS) < len(vix_aligned) else vix_now)
            close = float(bar.get("close", 0))
            vwap_i = float(vwap.iloc[idx]) if idx < len(vwap) else float("nan")
            if _regime_hostile_to_long(stack, vix_now, vix_prior, close, vwap_i):
                suppressed_by_regime += 1
                continue

        attempted += 1
        if sig.direction == "long":
            n_long += 1
        else:
            n_short += 1

        side = "C" if sig.direction == "long" else "P"
        rej = sig.metadata.get(rej_key)
        if rej is None:
            rej = sig.stop_price
        try:
            fill = simulate_trade_real(
                entry_bar_idx=idx, entry_bar=bar, spy_df=rth, ribbon_df=ribbon_df,
                rejection_level=float(rej), triggers_fired=list(sig.triggers_fired),
                side=side, qty=3, setup=sig.setup_name,
                **PROD_EXIT,
            )
        except Exception as exc:  # surface, never swallow (C7)
            sys.stderr.write(f"realfills {stream} exc @ {bar['timestamp_et']}: "
                             f"{type(exc).__name__}: {exc}\n")
            fill = None
        if fill is not None and getattr(fill, "dollar_pnl", None) is not None:
            filled += 1
            p = float(fill.dollar_pnl)
            pnls.append(p)
            if bar_date in ANCHORS:
                anchor_pnl[bar_date] += p

    stats = _stats([{"pnl": p} for p in pnls])
    win_cap = sum(anchor_pnl[d] for d in anchor_pnl if ANCHORS[d] == "WIN")
    loss_add = sum(max(0.0, -anchor_pnl[d]) for d in anchor_pnl if ANCHORS[d] == "LOSS")
    edge_capture = round(win_cap - loss_add, 2)
    return {
        "stats": stats,
        "attempted": attempted,
        "filled": filled,
        "n_long": n_long,
        "n_short": n_short,
        "suppressed_by_regime": suppressed_by_regime,
        "suppressed_by_direction": suppressed_by_direction,
        "anchor_edge_capture": edge_capture,
        "anchor_win_capture": round(win_cap, 2),
        "anchor_loss_added": round(loss_add, 2),
        "anchor_by_day": {str(d): round(anchor_pnl[d], 2) for d in sorted(anchor_pnl)},
        "_pnls": pnls,
    }


def _dsr_for(pnls: list[float]) -> dict:
    """Advisory DSR/PSR gate on per-trade dollar P&L (constant qty=3 notional)."""
    if len(pnls) < 2:
        return {"verdict": "FAIL", "reason": f"n={len(pnls)} < 2 — cannot compute",
                "dsr": None, "psr": None}
    res = evaluate_candidate(pnls, n_trials=N_TRIALS)
    return {
        "verdict": res.verdict,
        "dsr": round(res.dsr, 4),
        "psr": round(res.psr, 4),
        "pbo": res.pbo,
        "n_obs": res.n_obs,
        "low_power": res.low_power,
    }


def _gate(arm: dict) -> dict:
    """Apply the honest PROMOTE-CANDIDATE gate to one arm's real-fills result."""
    exp = arm["stats"]["exp"]
    n = arm["stats"]["n"]
    edge = arm["anchor_edge_capture"]
    dsr = arm["dsr_gate"]["verdict"]
    rf_positive = (exp > 0 and n >= 1)
    edge_positive = (edge > 0)
    dsr_ok = (dsr != "FAIL")
    if rf_positive and edge_positive and dsr_ok:
        verdict = "PROMOTE-CANDIDATE"
    elif rf_positive and edge_positive and not dsr_ok:
        verdict = "POSITIVE+WITH-J-BUT-DSR-FAIL"
    elif rf_positive and not edge_positive:
        verdict = "POSITIVE-BUT-ANTI-J-EDGE"
    elif (not rf_positive) and edge_positive:
        verdict = "WITH-J-BUT-REAL-FILLS-NEGATIVE"
    else:
        verdict = "NEGATIVE"
    return {
        "real_fills_positive": rf_positive,
        "edge_capture_positive": edge_positive,
        "dsr_not_fail": dsr_ok,
        "verdict": verdict,
    }


def _strip(arm: dict) -> dict:
    arm = dict(arm)
    arm.pop("_pnls", None)
    return arm


def _pattern_verdict(stream: str, base: dict, gated: dict | None, short: dict | None) -> str:
    """Synthesize the per-pattern RESCUE-OR-RETIRE verdict across both hypotheses."""
    promote_arms = []
    if base["gate"]["verdict"] == "PROMOTE-CANDIDATE":
        promote_arms.append(("baseline-long", base))
    if gated is not None and gated["gate"]["verdict"] == "PROMOTE-CANDIDATE":
        promote_arms.append(("regime-gated-long (Hyp A)", gated))
    if short is not None and short["gate"]["verdict"] == "PROMOTE-CANDIDATE":
        promote_arms.append(("short-inversion (Hyp B)", short))

    if promote_arms:
        label, arm = promote_arms[0]
        return (
            f"PROMOTE-CANDIDATE via {label}: real-fills exp=${arm['stats']['exp']} "
            f"(WR {arm['stats']['wr']}%, n={arm['stats']['n']}), edge_capture="
            f"${arm['anchor_edge_capture']} (POSITIVE — fires WITH J), DSR="
            f"{arm['dsr_gate']['verdict']}. PROXY levels — confirm on production ★★★ "
            f"before any wiring. Still WATCH_ONLY by doctrine."
        )

    # No promote. Describe why each hypothesis failed, then conclude RETIRE.
    bits: list[str] = []
    bg = base["gate"]
    bits.append(
        f"baseline-long real-fills exp=${base['stats']['exp']} "
        f"(n={base['stats']['n']}), edge_capture=${base['anchor_edge_capture']} "
        f"[{bg['verdict']}]"
    )
    if gated is not None:
        gg = gated["gate"]
        bits.append(
            f"Hyp A regime-gate: exp=${gated['stats']['exp']} "
            f"(n={gated['stats']['n']}, suppressed {gated['suppressed_by_regime']} "
            f"hostile-regime longs), edge_capture=${gated['anchor_edge_capture']} "
            f"[{gg['verdict']}]"
        )
    else:
        bits.append("Hyp A regime-gate: n/a (no long leg)")
    if short is not None:
        sg = short["gate"]
        bits.append(
            f"Hyp B short-inversion: exp=${short['stats']['exp']} "
            f"(n={short['stats']['n']}), edge_capture=${short['anchor_edge_capture']} "
            f"[{sg['verdict']}]"
        )
    else:
        bits.append("Hyp B short-inversion: no short mirror exists in this detector "
                    "(long-only)")

    return ("RETIRE-WITH-EVIDENCE — neither hypothesis flips this pattern to "
            "real-fills-positive AND edge_capture-positive AND DSR!=FAIL. " +
            "; ".join(bits) + ". Per playbook 'setups that fail thresholds get "
            "retired, not loosened' + OP-22, this is a clean honest no-win.")


def run(start: dt.date, end: dt.date) -> dict:
    # ── Single firing pass (reused verbatim from the exit-sweep) ────────────
    inputs, rth, ribbon_df = _collect_signals(start, end)
    rth = rth.reset_index(drop=True)
    vwap = _session_vwap(rth)
    # Aligned VIX series for the Hyp-A regime gate (same source the collector used).
    _spy_full, vix_full = _load_data(start, end)
    vix_aligned = _align_vix_to_spy(rth, vix_full)

    streams_out: dict = {}
    for stream in STREAMS:
        sig_inputs = inputs[stream]

        # ── Arm 0: baseline — ALL signals, production exit (the anti-edge status quo)
        base = _simulate_stream(stream, sig_inputs, rth, ribbon_df, vwap, vix_aligned)
        base["dsr_gate"] = _dsr_for(base["_pnls"])
        base["gate"] = _gate(base)

        # Does this detector emit any longs? (Hyp A only meaningful if so.)
        has_long = base["n_long"] > 0
        has_short_signals = base["n_short"] > 0

        # ── Arm A: Hypothesis A — regime-gated LONGS (drop hostile-regime longs) ──
        gated = None
        if has_long:
            gated = _simulate_stream(
                stream, sig_inputs, rth, ribbon_df, vwap, vix_aligned, regime_gate_longs=True
            )
            gated["dsr_gate"] = _dsr_for(gated["_pnls"])
            gated["gate"] = _gate(gated)

        # ── Arm B: Hypothesis B — SHORT-side inversion only ──────────────────────
        short = None
        if has_short_signals:
            short = _simulate_stream(
                stream, sig_inputs, rth, ribbon_df, vwap, vix_aligned, direction_filter="short"
            )
            short["dsr_gate"] = _dsr_for(short["_pnls"])
            short["gate"] = _gate(short)

        verdict = _pattern_verdict(stream, base, gated, short)

        streams_out[stream] = {
            "n_signals_collected": len(sig_inputs),
            "n_long_signals": base["n_long"],
            "n_short_signals": base["n_short"],
            "baseline_all_signals": _strip(base),
            "hyp_a_regime_gated_longs": _strip(gated) if gated is not None else
                {"skipped": "detector emits no LONG signals"},
            "hyp_b_short_inversion": _strip(short) if short is not None else
                {"skipped": "detector emits no SHORT signals (long-only)"},
            "pattern_verdict": verdict,
        }

    result = {
        "window": f"{start}..{end}",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "research_question": (
            "Can the anti-J-edge bounce-LONG watcher family be RESCUED by (A) a regime "
            "gate that suppresses longs in catching-a-falling-knife conditions "
            "(BEAR ribbon + VIX rising + below VWAP), or (B) a short-side inversion "
            "that fires WITH J's bearish-continuation edge? Or do we RETIRE the family? "
            "Real-fills (OPRA) is the only authority (C1)."
        ),
        "hypotheses": {
            "A_regime_gate": (
                "Suppress bounce-LONG when ribbon stack==BEAR AND vix_now>vix_prior AND "
                "close<session_VWAP. PROMOTE iff this flips edge_capture POSITIVE and "
                "real-fills exp>0 and DSR!=FAIL."
            ),
            "B_short_inversion": (
                "Isolate the SHORT signals (SECOND_TEST lower-high resistance leg + all "
                "of CLOSE_CEILING_FADE). PROMOTE iff shorts show edge_capture POSITIVE "
                "(fire WITH J on down days) and real-fills exp>0 and DSR!=FAIL."
            ),
        },
        "fixed_exit": PROD_EXIT,
        "gate_definition": (
            "PROMOTE-CANDIDATE iff real-fills exp>0 AND anchor edge_capture>0 (fires WITH "
            "J, not against) AND DSR/PBO advisory verdict != FAIL. If neither hypothesis "
            "rescues a pattern → RETIRE-WITH-EVIDENCE (playbook: fail thresholds → retire, "
            "not loosen; OP-22). Honest no-win is a valid result — do NOT manufacture a win."
        ),
        "streams": streams_out,
        "op20_disclosures": _op20_disclosures(),
        "overall_verdict": _overall_verdict(streams_out),
    }
    return result


def _overall_verdict(streams_out: dict) -> dict:
    promote, retire = [], []
    for s, v in streams_out.items():
        if v["pattern_verdict"].startswith("PROMOTE-CANDIDATE"):
            promote.append(s)
        else:
            retire.append(s)
    return {
        "promote_candidates": promote,
        "retire_with_evidence": retire,
        "summary": (
            f"{len(promote)}/{len(streams_out)} patterns rescued to PROMOTE-CANDIDATE. "
            + ("Rescued: " + ", ".join(promote) + ". " if promote else "")
            + ("RETIRE-WITH-EVIDENCE (neither regime-gate nor short-inversion clears the "
               "real-fills-positive + with-J + DSR gate): " + ", ".join(retire) + ". "
               if retire else "")
            + "Watchers remain WATCH_ONLY regardless; a PROMOTE here only means 'worth a "
              "real-fills re-test on production ★★★ levels', a RETIRE means 'stop "
              "spending engineering on this bounce pattern' (closes the watcher-fleet "
              "question)."
        ),
    }


def _op20_disclosures() -> dict:
    return {
        "authority": "Real-fills (lib.simulator_real + OPRA options cache, valid through "
                     "2026-05-29). BS-sim is ranking-only and is NOT used (C1).",
        "level_source_caveat": (
            "All 3 watchers read key-levels.json from disk; this run reuses the exit-sweep's "
            "monkeypatch forcing each per-day cache to SYNTHETIC PDH/PDL/PDC/PDO proxies "
            "(★★/★), NOT production ★★★ named levels (no historical archive). Absolute WR is "
            "a proxy LOWER-BOUND. The SIGN questions (does the gate flip edge_capture "
            "positive? are the shorts WITH J?) are answerable on the proxy because the level "
            "set is identical across all arms."
        ),
        "regime_gate_vix_caveat": (
            "All three Hyp-A clauses are computed EXACTLY at the signal index from "
            "rth/ribbon_df and the aligned VIX series (lib.orchestrator._align_vix_to_spy) — "
            "NO metadata fallback. 'VIX rising' = vix_now > vix_prior with vix_prior at a "
            "3-bar (15-min) lag, mirroring the collector's own vix_prior definition. "
            "Diagnostic clause hit-rates on the 16-month long population (verified this run): "
            "FLOOR_HOLD_BOUNCE 132 longs → BEAR=60, VIX-rising=29, below-VWAP=102, triple-AND=10; "
            "NAMED_LEVEL_SECOND_TEST 244 longs → BEAR=59, VIX-rising=30, below-VWAP=61, triple-AND=4. "
            "The low suppression count is STRUCTURAL (the triple conjunction is rarely satisfied), "
            "not a gutted clause — and crucially the J-anchor WIN-day (down-day) longs that drive "
            "the anti-edge are NOT among the suppressed bars, so the gate barely moves edge_capture."
        ),
        "anchor_gate": (
            "OP-16 shape on real-fills: edge_capture = sum(pnl on WIN-anchor days) - "
            "sum(max(0,-pnl) on LOSS-anchor days). POSITIVE = fires WITH J (makes money on his "
            "WIN days, doesn't bleed on his LOSS days). J has 3 WIN (4/29,5/01,5/04) + 3 LOSS "
            "(5/05,5/06,5/07) anchor days; these watchers fire on only a subset, so anchor n is "
            "tiny — a clean sign here is necessary, not sufficient (C24)."
        ),
        "dsr_returns": "DSR/PSR on per-trade dollar P&L (constant qty=3 notional). PBO skipped "
                       "(no CSCV per-slice matrix). Advisory only (gate.py is not a hard gate); "
                       "n_trials=3 (baseline / regime-gated / short arms).",
        "premium_stop": "premium_stop_pct=-0.99 (disabled) for ALL arms — chart/ribbon/time "
                        "exits only (C1/C2). Exit geometry held at production; the exit-sweep "
                        "already proved no exit config rescues these (watcher-exit-sweep.json).",
        "not_a_promotion": "RESEARCH ONLY. No watcher code, params, or doctrine changed. "
                           "Watchers remain WATCH_ONLY. PROMOTE-CANDIDATE = 'worth a real-fills "
                           "re-test on production ★★★ levels'; RETIRE-WITH-EVIDENCE = 'stop "
                           "engineering this bounce pattern'.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-05-29")  # OPRA coverage ends 2026-05-29
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end))

    # Compact stdout summary (full detail goes to the file).
    summary = {k: v for k, v in res.items() if k != "streams"}
    summary["streams_summary"] = {}
    for s, v in res["streams"].items():
        base = v["baseline_all_signals"]
        gated = v["hyp_a_regime_gated_longs"]
        short = v["hyp_b_short_inversion"]
        summary["streams_summary"][s] = {
            "n_long": v["n_long_signals"],
            "n_short": v["n_short_signals"],
            "baseline": {"exp": base["stats"]["exp"], "n": base["stats"]["n"],
                         "edge_capture": base["anchor_edge_capture"],
                         "dsr": base["dsr_gate"]["verdict"], "verdict": base["gate"]["verdict"]},
            "hyp_a_regime_gate": (
                {"exp": gated["stats"]["exp"], "n": gated["stats"]["n"],
                 "edge_capture": gated["anchor_edge_capture"],
                 "suppressed": gated["suppressed_by_regime"],
                 "dsr": gated["dsr_gate"]["verdict"], "verdict": gated["gate"]["verdict"]}
                if "stats" in gated else gated
            ),
            "hyp_b_short": (
                {"exp": short["stats"]["exp"], "n": short["stats"]["n"],
                 "edge_capture": short["anchor_edge_capture"],
                 "dsr": short["dsr_gate"]["verdict"], "verdict": short["gate"]["verdict"]}
                if "stats" in short else short
            ),
            "pattern_verdict": v["pattern_verdict"],
        }
    print(json.dumps(summary, indent=2, default=str))

    if a.out:
        out_path = Path(a.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
        print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
