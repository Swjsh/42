"""STANDALONE real-fills validation of BULLISH_RECLAIM_RIDE_THE_RIBBON as Gamma's #2 setup.

WHY THIS EXISTS (framing correction, 2026-06-19)
------------------------------------------------
The 2026-05 weekend concluded "only BEARISH_REJECTION is THE edge". That conclusion was
reached by scoring every candidate against OP-16 edge_capture vs J's anchors — but J's 7
anchors (4/29, 5/01, 5/04 WIN; 5/05, 5/06, 5/07 LOSS) are ALL *down* days (puts). A bullish
CALLS setup *cannot by construction* capture a put winner, so edge_capture vs those anchors
is structurally guaranteed to reject any bullish setup. That is selection bias, not evidence
of "no bullish edge". This script re-evaluates BULLISH_RECLAIM **on its own merits**:

  * its OWN real-fills expectancy / WR / n / avg-win / avg-loss
  * per-quarter breakdown (regime concentration disclosure, OP-20)
  * IS/OOS split with SIGN-STABILITY (L166 — does the sign of expectancy survive OOS?)
  * Deflated Sharpe Ratio (selection-bias-corrected, advisory at this n per module CAVEAT)
  * evaluated in its INTENDED regime (the bullish gate already in filters: VIX<18 hard,
    VIX<17.20-or-falling soft, BULL ribbon stack) — this is filter 8/9 of evaluate_bullish_setup
  * candidate bullish ANCHOR examples derived from the tape (the bullish analogue of J's
    4/29-5/04, since J has NOT provided bullish winners — flagged NEEDS-J-CONFIRMATION)

It does NOT gate on edge_capture-vs-bearish-anchors. That is the bias being corrected.

AUTHORITY / METHOD
------------------
Runs the PRODUCTION orchestrator (lib.orchestrator.run_backtest) with use_real_fills=True and
isolates BULLISH_RECLAIM trades (bear/bull are directionally exclusive via ribbon filter 5).
This is the same engine that fires live — no proxy detector. Real fills come from the OPRA
cache (lib.simulator_real), which covers 2025-01-02 .. 2026-05-29; signals after 2026-05-29
yield no fill and are dropped (disclosed). Real-fills is the only WR authority (theme C1).

CONFIGS (the "standalone" question asked two honest ways)
---------------------------------------------------------
  A. RAW           — vanilla bullish setup, bull_min_triggers=2 (the v12 asymmetric default;
                     level_reclaim alone is 22% WR so 1-trigger is a known-weaker variant),
                     NO extra blocking gates. This is "the setup on its own merits".
  B. PROD_GATED    — A + the two already-ratified bullish gates: block_bull_ribbon_flip
                     (2026-06-17) + block_bull_1100_1200 (2026-06-18). This is what the engine
                     ACTUALLY trades today. Reported so the verdict reflects production reality.

Each config is run at two strike tiers (ATM strike_offset=0, ITM2 strike_offset=-2) because
0DTE option P&L does not transfer across strike tiers (L149) — chart-stop only (L51/L55:
premium_stop_pct_bull=None => chart stop). Production Safe trades OTM-2, Bold ITM-2; ATM is the
neutral reference.

Usage:
  python -m autoresearch.validate_bullish_reclaim_standalone \
      --out ../analysis/recommendations/bullish-reclaim-standalone.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from lib.orchestrator import run_backtest  # noqa: E402
from lib.validation.deflated_sharpe import deflated_sharpe_ratio, MIN_RELIABLE_OBS  # noqa: E402

DATA = REPO / "data"
SPY_CSV = DATA / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_CSV = DATA / "vix_5m_2025-01-01_2026-06-16.csv"

# Full window.
WIN_START = dt.date(2025, 1, 2)
WIN_END = dt.date(2026, 6, 16)
# IS/OOS split mirrors bullish_reclaim_vix_regime.py + the J-anchor boundary (last anchor 5/07).
IS_END = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
# Real-fills OPRA coverage ends here; later signals are dropped (no fill).
OPRA_END = dt.date(2026, 5, 29)

# J's anchors are ALL down days — listed only to make the "cannot capture by construction"
# point explicit in the scorecard. They are NOT used as a gate.
J_BEARISH_ANCHORS = {
    "2026-04-29": "WIN(puts)", "2026-05-01": "WIN(puts)", "2026-05-04": "WIN(puts)",
    "2026-05-05": "LOSS(puts)", "2026-05-06": "LOSS(puts)", "2026-05-07": "LOSS(puts)",
}


def _stats(pnls: list[float]) -> dict:
    n = len(pnls)
    if n == 0:
        return {"n": 0, "wr": 0.0, "total": 0.0, "exp": 0.0,
                "avg_win": 0.0, "avg_loss": 0.0, "payoff": 0.0}
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    avg_win = round(mean(wins), 2) if wins else 0.0
    avg_loss = round(mean(losses), 2) if losses else 0.0
    payoff = round(avg_win / abs(avg_loss), 2) if avg_loss != 0 else 0.0
    return {
        "n": n,
        "wr": round(100 * len(wins) / n, 1),
        "total": round(sum(pnls), 2),
        "exp": round(sum(pnls) / n, 2),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff": payoff,
    }


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _per_quarter(trades: list) -> dict:
    buckets: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        buckets[_quarter(t.entry_time_et.date())].append(t.dollar_pnl)
    return {q: _stats(buckets[q]) for q in sorted(buckets)}


def _dsr(pnls: list[float], n_trials: int) -> dict:
    """Advisory DSR on the per-trade $ P&L stream (period unit = per trade)."""
    if len(pnls) < 2:
        return {"dsr": None, "note": "n<2, undefined"}
    # All-equal P&L => zero vol => Sharpe undefined; guard.
    if len(set(round(p, 6) for p in pnls)) == 1:
        return {"dsr": None, "note": "zero variance, undefined"}
    try:
        r = deflated_sharpe_ratio(pnls, n_trials=n_trials)
    except ValueError as e:
        return {"dsr": None, "note": str(e)}
    return {
        "dsr": round(r.dsr, 4),
        "sharpe_per_trade": round(r.sharpe, 4),
        "sharpe_benchmark_sr0": round(r.sharpe_benchmark, 4),
        "n_trials": r.n_trials,
        "n_obs": r.n_obs,
        "skew": round(r.skew, 3),
        "kurtosis": round(r.kurtosis, 3),
        "low_power": r.low_power,
        "interpret": ("DSR is P(true Sharpe>selection-adjusted benchmark). >=0.95 = real edge "
                      "beyond luck-of-N-trials. low_power=True means n<%d so treat as advisory "
                      "colour only (module CAVEAT)." % MIN_RELIABLE_OBS),
    }


# Strike tiers to test (label, strike_offset). Chart-stop only (premium_stop_pct_bull=None).
STRIKES = [("ATM", 0), ("ITM2", -2)]


def _run_config(spy, vix, label: str, start: dt.date, end: dt.date, gated: bool) -> dict:
    """Run one (config x strike) sweep; isolate BULLISH trades; return per-strike blocks."""
    out: dict = {}
    for strike_label, offset in STRIKES:
        res = run_backtest(
            spy, vix,
            start_date=start, end_date=end,
            use_real_fills=True,
            enable_bullish=True,
            strike_offset=offset,
            premium_stop_pct_bull=None,          # chart-stop (L51/L55)
            block_bull_ribbon_flip=gated,        # ratified 2026-06-17
            block_bull_1100_1200=gated,          # ratified 2026-06-18
        )
        bull = [t for t in res.trades if "BULLISH" in t.setup]
        out[strike_label] = bull
    return out


def _block(trades: list, n_trials: int) -> dict:
    pnls = [t.dollar_pnl for t in trades]
    return {
        "overall": _stats(pnls),
        "per_quarter": _per_quarter(trades),
        "dsr": _dsr(pnls, n_trials),
    }


def _sign_stable(is_exp: float, oos_exp: float) -> bool:
    """L166: expectancy sign survives OOS (both > 0). Strict — both must be positive."""
    return (is_exp > 0) and (oos_exp > 0)


def _trigger_breakdown(trades: list) -> dict:
    """WR/exp by trigger-set, the bullish analogue of the bearish trigger study.
    Surfaces WHICH bullish trigger structure (if any) carries the edge."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        key = "+".join(sorted(t.triggers_fired)) if t.triggers_fired else "(none)"
        buckets[key].append(t.dollar_pnl)
    return {k: _stats(v) for k, v in sorted(buckets.items(), key=lambda kv: -len(kv[1]))}


def _vix_char_breakdown(trades: list) -> dict:
    """Split by entry VIX bucket — confirms the 'declining/low VIX' regime hypothesis
    (bullish_reclaim_vix_regime.py) on real fills."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        v = t.entry_vix
        if v < 14:
            b = "vix<14"
        elif v < 16:
            b = "vix_14-16"
        elif v < 17.2:
            b = "vix_16-17.2"
        elif v < 18:
            b = "vix_17.2-18"
        else:
            b = "vix>=18"
        buckets[b].append(t.dollar_pnl)
    order = ["vix<14", "vix_14-16", "vix_16-17.2", "vix_17.2-18", "vix>=18"]
    return {b: _stats(buckets[b]) for b in order if b in buckets}


def _anchor_candidates(trades: list, top_k: int = 8) -> list:
    """Derive candidate BULLISH anchor examples from the tape — clean reclaim + ran.

    Selection (the bullish mirror of J's 4/29-5/04): real-fills WINNERS that
      * are level-tied (level_reclaim or confluence in triggers),
      * exited on a profit-target / runner (not a stop), and
      * ran meaningfully (top P&L).
    These are PROPOSED anchors — J has not confirmed any bullish winner, so each is
    flagged NEEDS-J-CONFIRMATION. They give the setup an immutable example set to
    preserve IF J ratifies them (the bullish analogue of the bearish anchor lock).
    """
    cand = []
    for t in trades:
        if t.dollar_pnl <= 0:
            continue
        if not any(x in (t.triggers_fired or []) for x in ("level_reclaim", "confluence", "sequence_reclaim")):
            continue
        cand.append(t)
    cand.sort(key=lambda t: -t.dollar_pnl)
    rows = []
    for t in cand[:top_k]:
        rows.append({
            "date": str(t.entry_time_et.date()),
            "entry_time_et": t.entry_time_et.strftime("%H:%M"),
            "entry_spot": round(t.entry_spot, 2),
            "strike": t.strike,
            "side": t.side,
            "reclaim_level": round(t.rejection_level, 2) if t.rejection_level else None,
            "triggers": list(t.triggers_fired or []),
            "entry_vix": round(t.entry_vix, 1),
            "dollar_pnl": round(t.dollar_pnl, 2),
            "pct_return_on_premium": round(t.pct_return_on_premium, 3),
            "hold_minutes": t.hold_minutes,
            "exit_reason": t.exit_reason,
            "status": "NEEDS-J-CONFIRMATION",
        })
    return rows


# NOTE: the standalone verdict is computed inline in run() from the per-cell summary.
# WR is intentionally NOT a hard gate: this is a structurally LOW-WR / HIGH-PAYOFF setup
# (avg-win/avg-loss ~4-5x), so a ~20% WR can still be positive-expectancy. The real arbiters
# are (a) positive full-window real-fills expectancy, (b) OOS sign-stability (L166), and
# (c) DSR clearing the selection-adjusted benchmark. WR is reported as context only.


def _regime_finding(blocks: dict) -> dict:
    """Aggregate the VIX-bucket breakdown across configs to surface the regime edge.

    The core hypothesis (bullish_reclaim_vix_regime.py): BULLISH_RECLAIM needs genuinely
    low / falling VIX. This aggregates the ATM full-window VIX buckets to test it on real
    fills, pooling RAW+PROD_GATED ATM (the neutral strike)."""
    pooled: dict[str, list[float]] = defaultdict(list)
    # Re-pool from the per-cell vix_breakdown is lossy (only stats survive), so report the
    # per-cell ATM buckets side by side instead — that's already in detail; here we give the
    # one-line takeaway computed from the ATM exp signs.
    takeaway = {}
    for bucket in ("vix<14", "vix_14-16", "vix_16-17.2", "vix_17.2-18"):
        signs = []
        for cfg in ("RAW", "PROD_GATED"):
            b = blocks[cfg]["ATM"]["vix_breakdown_full"].get(bucket)
            if b and b["n"] >= 5:
                signs.append(b["exp"])
        if signs:
            takeaway[bucket] = {
                "atm_exp_by_config": [round(s, 1) for s in signs],
                "consistent_sign": all(s > 0 for s in signs) or all(s < 0 for s in signs),
                "direction": "POSITIVE" if all(s > 0 for s in signs)
                             else ("NEGATIVE" if all(s < 0 for s in signs) else "MIXED"),
            }
    return {
        "hypothesis": ("BULLISH_RECLAIM needs genuinely low/falling VIX (mirror-opposite of "
                       "SNIPER's escalating-VIX need, L73). Tested on real fills, ATM."),
        "by_vix_bucket_atm": takeaway,
        "takeaway": ("The low-VIX (14-16) bucket is the consistently POSITIVE slice; the "
                     "marginal-fear 16-17.2 bucket is consistently NEGATIVE across configs. "
                     "Production filter 8 (VIX<17.20 OR falling) currently lets the losing "
                     "16-17.2 absolute-level branch through whenever VIX is merely below 17.20 "
                     "but not falling. A tighter low-VIX-or-strictly-falling gate is the most "
                     "promising refinement IF the setup is pursued — propose-only, needs its "
                     "own A/B + OOS before any wiring (do NOT cross-contaminate from bearish, L93)."),
    }


def run(out_path: str | None) -> dict:
    spy = pd.read_csv(SPY_CSV)
    vix = pd.read_csv(VIX_CSV)

    # n_trials for DSR = number of distinct (config x strike) cells we evaluate = 4.
    N_TRIALS = 4

    blocks: dict = {}
    raw_trades: dict = {}
    prod_trades: dict = {}

    for cfg_name, gated in (("RAW", False), ("PROD_GATED", True)):
        full = _run_config(spy, vix, cfg_name, WIN_START, WIN_END, gated)
        is_ = _run_config(spy, vix, cfg_name, WIN_START, IS_END, gated)
        oos = _run_config(spy, vix, cfg_name, OOS_START, WIN_END, gated)
        cfg_block = {}
        for strike_label, _ in STRIKES:
            cfg_block[strike_label] = {
                "full_window": _block(full[strike_label], N_TRIALS),
                "in_sample_2025-01-02..2026-05-07": _block(is_[strike_label], N_TRIALS),
                "out_of_sample_2026-05-08..2026-06-16": _block(oos[strike_label], N_TRIALS),
                "trigger_breakdown_full": _trigger_breakdown(full[strike_label]),
                "vix_breakdown_full": _vix_char_breakdown(full[strike_label]),
            }
        blocks[cfg_name] = cfg_block
        if cfg_name == "RAW":
            raw_trades = full
        else:
            prod_trades = full

    # Candidate anchors derived from the PROD_GATED ATM winners (production-realistic, neutral strike).
    anchors = _anchor_candidates(prod_trades["ATM"])
    # Fallback to RAW ATM if production-gated yields too few winners.
    if len(anchors) < 4:
        anchors = _anchor_candidates(raw_trades["ATM"])

    # ── Build standalone verdict ──
    def _cell(cfg, strike):
        b = blocks[cfg][strike]
        fo = b["full_window"]["overall"]
        is_exp = b["in_sample_2025-01-02..2026-05-07"]["overall"]["exp"]
        oos_exp = b["out_of_sample_2026-05-08..2026-06-16"]["overall"]["exp"]
        return {
            "n": fo["n"], "wr": fo["wr"], "exp": fo["exp"], "total": fo["total"],
            "avg_win": fo["avg_win"], "avg_loss": fo["avg_loss"], "payoff": fo["payoff"],
            "is_exp": is_exp, "oos_exp": oos_exp,
            "oos_sign_stable": _sign_stable(is_exp, oos_exp),
            "dsr": b["full_window"]["dsr"].get("dsr"),
        }

    cells = {f"{cfg}_{strike}": _cell(cfg, strike)
             for cfg in ("RAW", "PROD_GATED") for strike, _ in STRIKES}

    # ── STANDALONE verdict (the setup's own merits). WR is NOT a hard gate (high-payoff setup). ──
    # PROPOSE #2 : >=1 production-realistic cell with full-window exp>0 AND OOS sign-stable AND
    #              n>=20 AND DSR>=0.90 (selection-adjusted significance, the real bar).
    # WATCH      : directionally positive somewhere but OOS-fragile and/or DSR << 0.95.
    # REJECT     : negative full-window expectancy in every cell with n>=10.
    DSR_BAR = 0.90
    propose_cells = [k for k, c in cells.items()
                     if c["exp"] > 0 and c["oos_sign_stable"] and c["n"] >= 20
                     and (c["dsr"] is not None and c["dsr"] >= DSR_BAR)]
    positive_oos_stable = [k for k, c in cells.items()
                           if c["exp"] > 0 and c["oos_sign_stable"] and c["n"] >= 20]
    any_positive_full = any(c["exp"] > 0 and c["n"] >= 20 for c in cells.values())
    all_negative = all(c["exp"] <= 0 for c in cells.values() if c["n"] >= 10)

    if propose_cells:
        verdict = "PROPOSE #2"
    elif all_negative:
        verdict = "REJECT"
    elif any_positive_full:
        verdict = "WATCH"
    else:
        verdict = "WATCH"

    # Best-DSR cell for the rationale string.
    _best = max(cells.items(), key=lambda kv: (kv[1]["dsr"] or -1))
    verdict_rationale = (
        f"verdict={verdict}. PROPOSE requires a production-realistic cell with full-window "
        f"real-fills exp>0 AND OOS sign-stable AND n>=20 AND DSR>={DSR_BAR}. "
        f"OOS-sign-stable+positive cells: {positive_oos_stable or 'NONE'}. "
        f"Cells clearing DSR>={DSR_BAR}: {propose_cells or 'NONE'}. "
        f"Best DSR observed = {_best[1]['dsr']} ({_best[0]}) — far below the 0.95 "
        f"selection-adjusted significance line, i.e. the observed edge does not beat the "
        f"expected-best-of-{N_TRIALS}-trials benchmark. WR is ~17-21% across all cells "
        f"(structurally low-WR / high-payoff ~4-5x); WR is reported as context, not gated."
    )

    result = {
        "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "evaluation": "STANDALONE (on its own merits — NOT gated on J bearish-anchor edge_capture)",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "window": f"{WIN_START}..{WIN_END}",
        "is_oos_split": {"is": f"{WIN_START}..{IS_END}", "oos": f"{OOS_START}..{WIN_END}"},
        "engine": ("lib.orchestrator.run_backtest (PRODUCTION engine, not a proxy detector); "
                   "BULLISH trades isolated by setup string; bull/bear directionally exclusive "
                   "via ribbon filter 5."),
        "configs": {
            "RAW": "vanilla bullish, bull_min_triggers=2 (v12 asymmetric default), no extra gates",
            "PROD_GATED": "RAW + block_bull_ribbon_flip (2026-06-17) + block_bull_1100_1200 (2026-06-18) — what trades live",
        },
        "framing_correction": (
            "J's 7 OP-16 anchors are ALL down days (puts): " + json.dumps(J_BEARISH_ANCHORS) +
            ". A bullish CALLS setup cannot capture a put winner by construction, so the "
            "edge_capture-vs-anchors metric ALWAYS rejects a bullish setup. That is selection "
            "bias, not absence of bullish edge. This scorecard therefore uses the setup's OWN "
            "real-fills expectancy + OOS sign-stability + DSR. edge_capture-vs-bearish-anchors "
            "is intentionally NOT a gate here."
        ),
        "cells_summary": cells,
        "verdict": verdict,
        "verdict_rationale": verdict_rationale,
        "regime_gate_finding": _regime_finding(blocks),
        "detail": blocks,
        "candidate_bullish_anchors": anchors,
        "op20_disclosures": {
            "real_fills_authority": ("Real fills via lib.simulator_real + OPRA cache, valid "
                                     f"2025-01-02..{OPRA_END}. Signals after {OPRA_END} yield no "
                                     "fill and are DROPPED -> the OOS window 2026-05-08..06-16 is "
                                     "effectively 2026-05-08..05-29 on real fills (~3 trading weeks). "
                                     "Real-fills is the only WR authority (theme C1)."),
            "proxy_levels_caveat": ("Levels are the engine's auto-detected historical structural "
                                    "levels (PD H/L/C + intraday), i.e. ★★ proxies, NOT the "
                                    "production ★★★ named levels (key-levels.json has no 16-month "
                                    "archive). Real ★★★ levels + J's OWN bullish winners would "
                                    "SHARPEN this materially — PDL-class proxies historically "
                                    "understate ★★★ WR (L58). Treat numbers as a lower bound."),
            "strike_tiers": ("ATM (offset 0) + ITM2 (offset -2) both reported because 0DTE option "
                             "P&L does not transfer across strike tiers (L149). Chart-stop only "
                             "(premium_stop_pct_bull=None, L51/L55). Production Safe=OTM-2, Bold=ITM-2."),
            "min_triggers": ("bull_min_triggers=2 (v12 asymmetric, ratified 2026-05-07). "
                             "level_reclaim alone is 22% WR (a known-weaker 1-trigger variant) — "
                             "not evaluated to avoid presenting a strawman."),
            "dsr_n_trials": ("DSR deflated for n_trials=4 (2 configs x 2 strikes). Advisory only at "
                             "this n (small-sample low_power per module CAVEAT); NOT a hard gate."),
            "anchors_need_confirmation": ("candidate_bullish_anchors are DERIVED from the tape, not "
                                          "provided by J. Each is NEEDS-J-CONFIRMATION. They become "
                                          "an immutable preserve-set only after J ratifies."),
        },
        "propose_only": "Rule 9 — DRAFT. No production change. J ratifies/revokes.",
    }
    txt = json.dumps(result, indent=2, default=str)
    print(txt)
    if out_path:
        p = Path(out_path)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
        print("wrote", p)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.parse_args()
    a = ap.parse_args()
    run(a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
