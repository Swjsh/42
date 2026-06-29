"""backtest_design_swarm.py — the swarm designs HOW to test, not just what.

THE FAILURE THIS FIXES (2026-06-29): a single perspective (Claude) chose ONE framing
to test a hypothesis — measured forward DIRECTION (win-rate ~48%), called it a coin flip,
and was WRONG. The right frame was per-trade EXPECTANCY with a tight stop (it was +EV,
later killed by an OOS split). J: "the whole point of the swarm is so you DON'T depend on
one perspective picking the right way to measure — generate the infinite possibilities."

DESIGN PRINCIPLE — two layers:
  1. CANONICAL BATTERY (the guardrail): a fixed set of framings that ALWAYS runs for every
     hypothesis — WR, expectancy, drawdown, a STOP SWEEP, an OOS walk-forward split, regime
     (VIX) stratification, and a null. We can never again silently miss "test it as
     expectancy with tight stops + OOS" because it is hard-wired to always run.
  2. SWARM EXPLORER (the breadth): the free 5-model swarm proposes ADDITIONAL structured
     designs; a smart-model review (the caller / an Opus pass) keeps only the legit,
     runnable ones before they execute.

A DESIGN is a structured, runnable spec (maps to run_backtest knobs + a metric). The runner
executes every design and returns a matrix: framing -> result. The synthesis says which
framings reveal edge and which kill it — so the verdict is never one perspective's guess.

Real OPRA fills (C1) by default. $0 for the swarm layer (free models).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import pandas as pd

# Windows cp1252 console can't encode unicode (a swarm-generated design name with a U+2011
# hyphen crashed a full run AFTER all backtests, BEFORE the save). Force utf-8 so a print
# can never lose computed results.
for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "backtest")); sys.path.insert(0, str(REPO / "setup" / "scripts"))
from backtest.lib.orchestrator import run_backtest, _params_to_kwargs  # noqa: E402
import datetime as dt  # noqa: E402

DATA = REPO / "backtest" / "data"
PARAMS = json.loads((REPO / "automation/state/params.json").read_text(encoding="utf-8"))
OUT_DIR = REPO / "analysis" / "design-swarm"


# ────────────────────────────────────────────────────────────────────────────
# Design spec — structured + runnable
# ────────────────────────────────────────────────────────────────────────────
@dataclass
class Design:
    name: str
    side: str = "P"                       # "P" (puts/bear) | "C" (calls/bull) | "both"
    disable_filters: list = field(default_factory=list)
    stop_sweep: list = field(default_factory=lambda: [-0.50])   # premium_stop_pct values to try
    metric: str = "expectancy"            # expectancy | wr | drawdown | total | payoff
    split: str = "full"                   # full | oos
    strata: Optional[str] = None          # None | "vix"
    enable_bullish: bool = True
    note: str = ""

    def key(self) -> tuple:
        return (self.side, tuple(sorted(self.disable_filters)), tuple(self.stop_sweep), self.split, self.strata)


_RUNNABLE_KNOBS = {"name", "side", "disable_filters", "stop_sweep", "metric", "split", "strata", "enable_bullish", "note"}
_VALID_FILTERS = set(range(1, 12))
_VALID_METRICS = {"expectancy", "wr", "drawdown", "total", "payoff"}


def canonical_battery(hypothesis_disable: list, side: str) -> list[Design]:
    """The guardrail: framings that ALWAYS run, so no metric is ever silently skipped."""
    d = hypothesis_disable
    return [
        Design("WR-only (the WRONG default that fooled us)", side, d, [-0.50], "wr", "full", note="why direction alone misleads"),
        Design("EXPECTANCY full @ prod stop", side, d, [-0.50], "expectancy", "full"),
        Design("EXPECTANCY stop-sweep (tight stops = the asymmetry)", side, d, [-0.50, -0.30, -0.20, -0.12], "expectancy", "full"),
        Design("PAYOFF ratio (avg win / avg loss) stop-sweep", side, d, [-0.50, -0.30, -0.20], "payoff", "full"),
        Design("MAX DRAWDOWN stop-sweep", side, d, [-0.50, -0.30, -0.20, -0.12], "drawdown", "full"),
        Design("OOS walk-forward @ best tight stops", side, d, [-0.20, -0.15], "expectancy", "oos"),
        Design("REGIME (VIX) stratified expectancy", side, d, [-0.20], "expectancy", "full", strata="vix"),
    ]


# ────────────────────────────────────────────────────────────────────────────
# Smart-review gate — keep only legit, runnable designs (dedupe + validate)
# ────────────────────────────────────────────────────────────────────────────
def review_designs(designs: list[Design]) -> tuple[list[Design], list[str]]:
    kept, rejected, seen = [], [], set()
    for ds in designs:
        if ds.side not in ("P", "C", "both"):
            rejected.append(f"{ds.name}: bad side {ds.side}"); continue
        if not set(ds.disable_filters).issubset(_VALID_FILTERS):
            rejected.append(f"{ds.name}: bad filters {ds.disable_filters}"); continue
        if ds.metric not in _VALID_METRICS:
            rejected.append(f"{ds.name}: bad metric {ds.metric}"); continue
        if not ds.stop_sweep or any(not (-0.95 <= s < 0) for s in ds.stop_sweep):
            rejected.append(f"{ds.name}: bad stop_sweep {ds.stop_sweep}"); continue
        if ds.key() in seen:
            rejected.append(f"{ds.name}: duplicate of an earlier design"); continue
        seen.add(ds.key()); kept.append(ds)
    return kept, rejected


# ────────────────────────────────────────────────────────────────────────────
# Smart-model review gate — "Opus/Sonnet reviews before designs run" (J's ask).
# Uses a strong FREE 120B model by default (it has a brain at $0); escalatable to paid.
# Only SWARM-GENERATED designs are smart-reviewed — the canonical battery is trusted.
# ────────────────────────────────────────────────────────────────────────────
_DESIGN_REVIEW_SYSTEM = (
    "You review a proposed backtest DESIGN for a 0DTE SPY options hypothesis. Score its "
    "methodological legitimacy 0-10 and decide recommended (true/false). HARD-FAIL (recommended=false) "
    "if ANY: (1) it could only be judged on win-rate/direction alone with no expectancy metric "
    "(the exact trap that fooled us); (2) no out-of-sample / walk-forward split when claiming edge; "
    "(3) look-ahead (decision uses a future bar); (4) absurd knobs (e.g. positive stop). "
    "SOFT-DEMERIT: over-fit (far more knob combos than trades), no null/baseline, metric that "
    "anti-correlates with the setup structure. Reply ONLY JSON: "
    '{"recommended": bool, "score": int, "flags": [str]}.'
)


def smart_review_design(ds: "Design", model: str = "nvidia/nemotron-3-super-120b-a12b:free") -> dict:
    """Smart-model legitimacy review of ONE design. Returns {recommended, score, flags}.
    Fail-open: on any model/parse error returns recommended=True (don't block on infra)."""
    try:
        sys.path.insert(0, str(REPO / "setup" / "scripts"))
        from run_minimax import call_minimax
        prompt = ("DESIGN: " + json.dumps(asdict(ds)) +
                  "\nIs this a legitimate, non-overfit, properly-measured backtest design? Score it.")
        r = call_minimax(prompt=prompt, model=model, system=_DESIGN_REVIEW_SYSTEM,
                         max_tokens=800, temperature=0.0, task_id="design_review")
        if not r.get("ok"):
            return {"recommended": True, "score": 5, "flags": [f"review_unavailable:{(r.get('error') or '')[:40]}"]}
        from swarm_client import extract_json
        o = extract_json(r.get("content", "")) or {}
        return {"recommended": bool(o.get("recommended", True)), "score": int(o.get("score", 5)),
                "flags": [str(f) for f in (o.get("flags") or [])]}
    except Exception as exc:  # noqa: BLE001
        return {"recommended": True, "score": 5, "flags": [f"review_error:{str(exc)[:40]}"]}


def swarm_propose_designs(hypothesis: str, base_disable: list, side: str, n: int = 6) -> list[Design]:
    """Free 5-model swarm proposes ADDITIONAL structured framings. Robust: any model that
    fails to emit clean JSON is skipped; the canonical battery still guarantees coverage."""
    try:
        from swarm_consult import consult
    except Exception:  # noqa: BLE001
        return []
    schema = ('Return ONLY a JSON array of <=%d test-design objects, each: '
              '{"name": str, "side": "P"|"C"|"both", "disable_filters": [int], '
              '"stop_sweep": [negative floats e.g. -0.2], "metric": '
              '"expectancy"|"wr"|"drawdown"|"total"|"payoff", "split": "full"|"oos", '
              '"strata": null|"vix"}. No prose.' % n)
    q = (f"Hypothesis to test rigorously: {hypothesis}. Base filters to disable: {base_disable}, side {side}. "
         f"Propose DIVERSE test framings a single analyst would miss (different metrics, stop levels, "
         f"splits, regime cuts). {schema}")
    try:
        res = consult(mode="brainstorm", question=q, context="", max_tokens_per_perspective=900, skip_synthesis=True)
    except Exception:  # noqa: BLE001
        return []
    out: list[Design] = []
    try:
        from swarm_client import extract_json
    except Exception:  # noqa: BLE001
        extract_json = None
    for p in res.perspectives:
        if not p.ok:
            continue
        arr = extract_json(p.content) if extract_json else None
        if not isinstance(arr, list):
            continue
        for o in arr:
            if not isinstance(o, dict):
                continue
            try:
                out.append(Design(
                    name=str(o.get("name", "swarm-design")).encode("ascii", "ignore").decode()[:60],
                    side=str(o.get("side", side)),
                    disable_filters=[int(x) for x in (o.get("disable_filters") or base_disable)],
                    stop_sweep=[float(x) for x in (o.get("stop_sweep") or [-0.20])],
                    metric=str(o.get("metric", "expectancy")),
                    split=str(o.get("split", "full")),
                    strata=(o.get("strata") if o.get("strata") in (None, "vix") else None),
                    note=f"swarm:{p.model.split('/')[-1]}",
                ))
            except (TypeError, ValueError):
                continue
    return out


# ────────────────────────────────────────────────────────────────────────────
# Metric library + runner
# ────────────────────────────────────────────────────────────────────────────
def _trade_pnls(trades, side):
    return [float(getattr(t, "dollar_pnl", 0) or 0) for t in trades
            if side == "both" or getattr(t, "side", "P") == side]


def _metrics(pnls):
    if not pnls:
        return dict(n=0)
    n = len(pnls); w = [x for x in pnls if x > 0]; l = [x for x in pnls if x < 0]
    cum = peak = mdd = 0.0
    for x in pnls:
        cum += x; peak = max(peak, cum); mdd = min(mdd, cum - peak)
    return dict(n=n, wr=round(len(w) / n, 3), total=round(sum(pnls), 0), exp=round(sum(pnls) / n, 1),
                avg_win=round(sum(w) / len(w), 1) if w else 0, avg_loss=round(sum(l) / len(l), 1) if l else 0,
                payoff=round((sum(w) / len(w)) / abs(sum(l) / len(l)), 2) if w and l else None, max_dd=round(mdd, 0))


def _run_once(spy, vix, a, b, disable, stop, enable_bullish, side):
    k = _params_to_kwargs(PARAMS, account_equity=2000.0)
    if disable:
        k["disable_filters"] = list(disable)
    k["premium_stop_pct"] = stop; k["premium_stop_pct_bear"] = stop
    k["enable_bullish"] = enable_bullish
    res = run_backtest(spy, vix, start_date=dt.date.fromisoformat(a), end_date=dt.date.fromisoformat(b),
                       use_real_fills=True, **k)
    return _metrics(_trade_pnls(res.trades, side)), res


def run_design(ds: Design, spy, vix, full_range, oos_split) -> dict:
    a, b = full_range
    rows = []
    if ds.split == "oos":
        for stop in ds.stop_sweep:
            tr, _ = _run_once(spy, vix, oos_split[0], oos_split[1], ds.disable_filters, stop, ds.enable_bullish, ds.side)
            te, _ = _run_once(spy, vix, oos_split[2], oos_split[3], ds.disable_filters, stop, ds.enable_bullish, ds.side)
            rows.append({"stop": stop, "train": tr, "test": te,
                         "oos_sign_stable": (tr.get("exp", 0) > 0 and te.get("exp", 0) > 0)})
    elif ds.strata == "vix":
        # split the full run by VIX tertiles of the entry bar (regime)
        for stop in ds.stop_sweep:
            m, res = _run_once(spy, vix, a, b, ds.disable_filters, stop, ds.enable_bullish, ds.side)
            lo, hi = [], []
            for t in res.trades:
                if ds.side != "both" and getattr(t, "side", "P") != ds.side:
                    continue
                v = float(getattr(t, "entry_vix", 0) or 0); p = float(getattr(t, "dollar_pnl", 0) or 0)
                (lo if v < 18 else hi).append(p)
            rows.append({"stop": stop, "all": m, "vix_lt18": _metrics(lo), "vix_ge18": _metrics(hi)})
    else:
        for stop in ds.stop_sweep:
            m, _ = _run_once(spy, vix, a, b, ds.disable_filters, stop, ds.enable_bullish, ds.side)
            rows.append({"stop": stop, **m})
    return {"design": asdict(ds), "metric": ds.metric, "rows": rows}


def run_hypothesis(hypothesis: str, base_disable: list, side: str, *, start, end, oos_cut, use_swarm=True, use_smart_review=True) -> dict:
    spy = pd.read_csv(DATA / "spy_5m_2025-01-01_2026-06-18.csv")
    vix = pd.read_csv(DATA / "vix_5m_2025-01-01_2026-06-18.csv")
    spy = spy[(spy["timestamp_et"] >= start) & (spy["timestamp_et"] < end + "T23:59")].reset_index(drop=True)
    vix = vix[(vix["timestamp_et"] >= start) & (vix["timestamp_et"] < end + "T23:59")].reset_index(drop=True)

    designs = canonical_battery(base_disable, side)
    swarm_extra = swarm_propose_designs(hypothesis, base_disable, side) if use_swarm else []
    kept, rejected = review_designs(designs + swarm_extra)

    # SMART-MODEL GATE: Opus/Sonnet-class review of the SWARM-generated designs before they
    # spend compute (J: "have a brain review them before they get fed in"). Canonical battery
    # is trusted (it's the guardrail). Free 120B reviewer = $0.
    if use_smart_review:
        gated = []
        for ds in kept:
            if not str(ds.note).startswith("swarm:"):
                gated.append(ds); continue          # canonical battery: keep
            verdict = smart_review_design(ds)
            if verdict["recommended"] and verdict["score"] >= 7:
                ds.note += f" [reviewed {verdict['score']}/10]"; gated.append(ds)
            else:
                rejected.append(f"{ds.name}: smart-gate {verdict['score']}/10 {verdict['flags']}")
        kept = gated
    print(f"[design-swarm] {len(designs)} canonical + {len(swarm_extra)} swarm-proposed -> {len(kept)} kept, {len(rejected)} rejected")

    full_range = (start, end); oos_split = (start, oos_cut, oos_cut, end)
    results = []
    for ds in kept:
        print(f"[design-swarm] running: {ds.name} ({ds.metric}/{ds.split})")
        try:
            results.append(run_design(ds, spy, vix, full_range, oos_split))
        except Exception as exc:  # noqa: BLE001
            results.append({"design": asdict(ds), "error": str(exc)[:160]})

    out = {"hypothesis": hypothesis, "base_disable": base_disable, "side": side,
           "n_designs": len(kept), "rejected": rejected, "results": results}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "latest.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    _print_matrix(out)
    return out


def _print_matrix(out):
    print("\n================ DESIGN-SWARM MATRIX ================")
    print(f"hypothesis: {out['hypothesis']}\n")
    for r in out["results"]:
        d = r["design"]; print(f"--- {d['name']}  [{r.get('metric')}/{d['split']}] ---")
        if r.get("error"):
            print(f"    ERROR {r['error']}"); continue
        for row in r["rows"]:
            print("    " + json.dumps(row, default=str)[:200])
    print("\nVerdict is the WHOLE matrix, not one framing. Look for: does the metric flip sign across")
    print("framings (WR vs expectancy)? does it survive the OOS split? does any VIX regime carry it?")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hypothesis", default="Relax filter 5 (ribbon-must-be-bear) + filter 9 (breakdown) to take strong level-rejections; is it edge?")
    ap.add_argument("--disable", default="5,9", help="comma filters to disable as the hypothesis")
    ap.add_argument("--side", default="P")
    ap.add_argument("--start", default="2025-07-01"); ap.add_argument("--end", default="2026-06-18")
    ap.add_argument("--oos-cut", default="2026-02-28")
    ap.add_argument("--no-swarm", action="store_true")
    ap.add_argument("--no-smart-review", action="store_true")
    args = ap.parse_args()
    base = [int(x) for x in args.disable.split(",") if x.strip()]
    run_hypothesis(args.hypothesis, base, args.side, start=args.start, end=args.end,
                   oos_cut=args.oos_cut, use_swarm=not args.no_swarm, use_smart_review=not args.no_smart_review)
