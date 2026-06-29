"""engine_stress_swarm.py — counterfactual engine-stress swarm ("tenfold the swarm").

J 2026-06-28: "take this swarm idea and tenfold it ... give the free models data,
drive them like their CEO, put our engine through the test ... infinite possibilities.
what if the bars did this? what did the engine see? what if we got 5 contracts and
scaled out at 30%? what if we shorted that double bottom? cook all night, be ready."

DESIGN (the rigorous version — the ENGINE is ground truth, the LLMs reason ABOUT
its captured output, they NEVER hallucinate engine behavior):

  1. SEED      : real historical SPY/VIX days (diverse regimes) + N prior days of warmup.
  2. PERTURB   : counterfactual "what if the bars did this" — trend_flip, amplify,
                 dampen (erode the wave), vix_up/down, gap_open, add_noise.
  3. ENGINE    : feed each perturbed frame through run_backtest (the REAL engine) ->
                 capture the verdict/scores the engine SAW + the trades it took.
  4. VARIANTS  : sizing/exit/direction counterfactuals via run_backtest kwargs —
                 risk cap (3/5/10-contract proxy), tp1 (30%/50%/75% × all/split),
                 exit (chandelier vs fixed vs -50% cap), direction (bull on/off).
  5. SWARM     : the 5-model free swarm (swarm_consult) adversarially evaluates the
                 ANOMALIES + aggregate patterns — "was that the right call? what hole?"
  6. DOCUMENT  : ranked findings -> markdown report + JSONL ledger; improvement
                 candidates -> cook-queue for the existing pipeline.

DISCLOSURE (CLAUDE.md C1): synthetic/perturbed bars have NO OPRA chain, so option
P&L here is BS-sim => RANKING-ONLY, never a WR authority. Every output says so.
The engine's VERDICT (ENTER/HOLD/SKIP + score) is deterministic and real regardless
of fill model — that decision logic is what we stress-test.

COST: $0 (free swarm only). Engine runs are local Python.
OVERNIGHT: --max-minutes bounds a batch; a scheduled task re-fires to cook all night,
appending findings. Reaper-exempt via backtest/.venv (see CLAUDE.md grind-reaper note).

Usage:
  python engine_stress_swarm.py --seeds 8 --max-minutes 30          # one batch
  python engine_stress_swarm.py --smoke                             # tiny validation grid
  python engine_stress_swarm.py --no-swarm                          # engine grid only, skip LLM
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

from backtest.lib.orchestrator import run_backtest, _params_to_kwargs  # noqa: E402

DATA = REPO / "backtest" / "data"
OUT_DIR = REPO / "analysis" / "stress-swarm"
LEDGER = OUT_DIR / "_ledger.jsonl"
REPORT_DIR = REPO / "markdown" / "research"
PARAMS = json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8"))

WARMUP_DAYS = 5          # real prior days fed for ribbon/level warmup (NOT perturbed)
SAFE_EQUITY = 2000.0


# ────────────────────────────────────────────────────────────────────────────
# ET clock (no tzdata dep — same DST math as the rest of the rig)
# ────────────────────────────────────────────────────────────────────────────
def _et_now() -> dt.datetime:
    from datetime import timezone, timedelta
    now = dt.datetime.now(timezone.utc)
    y = now.year
    march = dt.datetime(y, 3, 1, tzinfo=timezone.utc)
    dst_start = (march + timedelta(days=(6 - march.weekday()) % 7 + 7)).replace(hour=7)
    nov = dt.datetime(y, 11, 1, tzinfo=timezone.utc)
    dst_end = (nov + timedelta(days=(6 - nov.weekday()) % 7)).replace(hour=6)
    off = -4 if (dst_start <= now < dst_end) else -5
    return (now + timedelta(hours=off)).replace(tzinfo=None)


# ────────────────────────────────────────────────────────────────────────────
# Data loading + diverse seed-day selection
# ────────────────────────────────────────────────────────────────────────────
def _load_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Newest SPY/VIX 5m CSVs in backtest/data. Returns (spy, vix) with a 'date' col."""
    spy_files = sorted(DATA.glob("spy_5m_*.csv"))
    vix_files = sorted(DATA.glob("vix_5m_*.csv"))
    if not spy_files or not vix_files:
        raise FileNotFoundError(f"no spy_5m_*/vix_5m_* CSVs in {DATA}")
    spy = pd.read_csv(spy_files[-1])
    vix = pd.read_csv(vix_files[-1])
    for df in (spy, vix):
        df["date"] = df["timestamp_et"].str[:10]
    return spy, vix


def select_seed_days(spy: pd.DataFrame, n: int) -> list[str]:
    """Pick N diverse RTH days spanning regimes: strong-up, strong-down, chop,
    high-range, low-range — so the stress grid isn't all one regime."""
    rth = spy[(spy["timestamp_et"].str[11:16] >= "09:30") & (spy["timestamp_et"].str[11:16] <= "16:00")]
    rows = []
    for d, g in rth.groupby("date"):
        if len(g) < 60:
            continue
        o, c = g.iloc[0]["open"], g.iloc[-1]["close"]
        hi, lo = g["high"].max(), g["low"].min()
        rng_pct = (hi - lo) / o * 100.0
        ret_pct = (c - o) / o * 100.0
        rows.append({"date": d, "ret_pct": ret_pct, "rng_pct": rng_pct, "absret": abs(ret_pct)})
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    if df.empty:
        return []
    picks: list[str] = []
    # extremes across two axes => regime diversity
    picks.append(df.loc[df["ret_pct"].idxmax(), "date"])   # strong up
    picks.append(df.loc[df["ret_pct"].idxmin(), "date"])   # strong down
    picks.append(df.loc[df["rng_pct"].idxmax(), "date"])   # high range
    picks.append(df.loc[df["absret"].idxmin(), "date"])    # flattest / chop
    picks.append(df.loc[df["rng_pct"].idxmin(), "date"])   # tightest range
    # fill the rest by even spacing across the calendar (recency + variety)
    remaining = [d for d in df["date"].tolist() if d not in picks]
    if remaining and len(picks) < n:
        step = max(1, len(remaining) // max(1, n - len(picks)))
        picks.extend(remaining[::step][: n - len(picks)])
    # de-dup preserve order, cap at n
    seen, out = set(), []
    for d in picks:
        if d not in seen:
            seen.add(d); out.append(d)
        if len(out) >= n:
            break
    return out


def _window_for(spy: pd.DataFrame, vix: pd.DataFrame, seed: str) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Seed day + WARMUP_DAYS real prior trading days (for ribbon/level warmup)."""
    all_days = sorted(spy["date"].unique())
    if seed not in all_days:
        return pd.DataFrame(), pd.DataFrame(), []
    i = all_days.index(seed)
    window_days = all_days[max(0, i - WARMUP_DAYS): i + 1]
    s = spy[spy["date"].isin(window_days)].reset_index(drop=True)
    v = vix[vix["date"].isin(window_days)].reset_index(drop=True)
    return s, v, window_days


# ────────────────────────────────────────────────────────────────────────────
# Perturbations — "what if the bars did this" (applied to the SEED day only)
# ────────────────────────────────────────────────────────────────────────────
def _perturb_seed(spy_window: pd.DataFrame, vix_window: pd.DataFrame, seed: str,
                  kind: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return a COPY of the window with the seed day's bars perturbed. Prior warmup
    days are left untouched (realistic context). Perturbations operate in return
    space and rescale O/H/L proportionally around the new close path — no look-ahead
    (the whole day is transformed before the engine sees any bar)."""
    s = spy_window.copy()
    v = vix_window.copy()
    mask = s["date"] == seed
    day = s[mask].copy()
    if day.empty:
        return s, v

    o = day["open"].to_numpy(dtype=float)
    h = day["high"].to_numpy(dtype=float)
    l = day["low"].to_numpy(dtype=float)
    c = day["close"].to_numpy(dtype=float)
    base = c[0] if len(c) else 0.0

    def _rebuild(new_close: np.ndarray) -> None:
        # rescale OHLC to follow new_close, preserving each bar's intrabar shape ratio
        for i in range(len(c)):
            if c[i] == 0:
                continue
            k = new_close[i] / c[i]
            day.iat[i, day.columns.get_loc("close")] = new_close[i]
            day.iat[i, day.columns.get_loc("open")] = o[i] * k
            day.iat[i, day.columns.get_loc("high")] = h[i] * k
            day.iat[i, day.columns.get_loc("low")] = l[i] * k

    rets = np.diff(c, prepend=c[0]) / np.where(c == 0, 1, c)  # bar-to-bar returns

    if kind == "baseline":
        pass
    elif kind == "trend_flip":
        # invert directional drift, keep volatility magnitude => ribbon stack flips
        new = base * np.cumprod(1 - rets)
        _rebuild(new)
    elif kind == "amplify":
        new = base * np.cumprod(1 + rets * 1.6)              # bigger swings
        _rebuild(new)
    elif kind == "dampen":
        new = base * np.cumprod(1 + rets * 0.4)              # "erode the wave" — chop
        _rebuild(new)
    elif kind == "gap_open":
        # shove the first bar +0.6% vs prior close to create an opening gap
        gap = 1.006
        new = c.copy(); new[0] = c[0] * gap
        new[1:] = new[0] * np.cumprod(1 + rets[1:])
        _rebuild(new)
    elif kind == "add_noise":
        rng = np.random.default_rng(abs(hash(seed)) % (2**32))
        noise = rng.normal(0, 0.0008, size=len(c))
        new = base * np.cumprod(1 + rets + noise)
        _rebuild(new)
    elif kind == "vix_up":
        vmask = v["date"] == seed
        for col in ("open", "high", "low", "close"):
            if col in v.columns:
                v.loc[vmask, col] = v.loc[vmask, col] + 4.0   # +4 VIX pts
        s.loc[mask, :] = day.values
        return s, v
    elif kind == "vix_down":
        vmask = v["date"] == seed
        for col in ("open", "high", "low", "close"):
            if col in v.columns:
                v.loc[vmask, col] = (v.loc[vmask, col] - 4.0).clip(lower=8.0)
        s.loc[mask, :] = day.values
        return s, v

    s.loc[mask, :] = day.values
    return s, v


PERTURBATIONS = ["baseline", "trend_flip", "amplify", "dampen", "gap_open", "vix_up", "vix_down", "add_noise"]


# ────────────────────────────────────────────────────────────────────────────
# Variant axes — sizing / exit / direction counterfactuals (run_backtest kwargs)
# ────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Variant:
    name: str
    overrides: dict


def variant_grid(full: bool) -> list[Variant]:
    """Sizing/exit/direction variants. 'full' = the wide overnight grid; otherwise a
    focused set that covers J's named examples (5 contracts @30% scale-out, etc.)."""
    base = [
        Variant("base_v15", {}),                                                           # production defaults
        Variant("tp1_30_allout", {"tp1_premium_pct": 0.30, "tp1_qty_fraction": 1.0}),       # "scaled out 30% on all"
        Variant("tp1_30_split", {"tp1_premium_pct": 0.30, "tp1_qty_fraction": 0.667}),
        Variant("tp1_50_split", {"tp1_premium_pct": 0.50, "tp1_qty_fraction": 0.667}),
        Variant("tp1_75_split", {"tp1_premium_pct": 0.75, "tp1_qty_fraction": 0.667}),
        Variant("risk_15pct", {"per_trade_risk_cap_pct": 0.15}),
        Variant("risk_50pct", {"per_trade_risk_cap_pct": 0.50}),                            # ~bigger contract count
        Variant("exit_chandelier", {"profit_lock_mode": "chandelier", "profit_lock_threshold_pct": 0.05}),
        Variant("exit_fixed_tight", {"profit_lock_mode": "fixed", "premium_stop_pct": -0.20}),
        Variant("bull_off", {"enable_bullish": False}),                                     # direction counterfactual
    ]
    if not full:
        return base
    extra = [
        Variant("tp1_30_allout_risk50", {"tp1_premium_pct": 0.30, "tp1_qty_fraction": 1.0, "per_trade_risk_cap_pct": 0.50}),
        Variant("runner_2x", {"runner_target_premium_pct": 2.0}),
        Variant("runner_3x", {"runner_target_premium_pct": 3.0}),
        Variant("stop_catastrophe_only", {"premium_stop_pct": -0.50}),
        Variant("min_trig_bull_1", {"min_triggers_bull": 1}),
    ]
    return base + extra


# ────────────────────────────────────────────────────────────────────────────
# Engine run — the deterministic ground truth
# ────────────────────────────────────────────────────────────────────────────
@dataclass
class StressResult:
    seed: str
    perturbation: str
    variant: str
    n_trades: int
    total_pnl: float
    wins: int
    losses: int
    sides: dict                 # {"P": n, "C": n}
    setups: dict
    verdicts: dict              # what the engine SAW (counts of ENTER/HOLD/SKIP_*)
    sample_trades: list         # a few trade summaries
    error: Optional[str] = None


def _run_one(spy_w: pd.DataFrame, vix_w: pd.DataFrame, seed: str, pert: str, variant: Variant) -> StressResult:
    try:
        kwargs = _params_to_kwargs(PARAMS, account_equity=SAFE_EQUITY)
        kwargs.update(variant.overrides)
        res = run_backtest(
            spy_w, vix_w,
            start_date=dt.date.fromisoformat(seed),
            end_date=dt.date.fromisoformat(seed),
            use_real_fills=False,   # synthetic/perturbed bars -> BS-sim, RANKING-ONLY
            **kwargs,
        )
        trades = res.trades
        verdicts: dict = {}
        for d in res.decisions:
            a = d.get("action") or d.get("verdict") or "?"
            verdicts[a] = verdicts.get(a, 0) + 1
        sides, setups = {}, {}
        wins = losses = 0
        total = 0.0
        sample = []
        for t in trades:
            pnl = float(getattr(t, "dollar_pnl", 0.0) or 0.0)
            total += pnl
            wins += 1 if pnl > 0 else 0
            losses += 1 if pnl < 0 else 0
            sd = getattr(t, "side", "?")
            sides[sd] = sides.get(sd, 0) + 1
            su = getattr(t, "setup", "?")
            setups[su] = setups.get(su, 0) + 1
            if len(sample) < 4:
                sample.append({
                    "setup": su, "side": sd, "pnl": round(pnl, 1),
                    "entry_et": str(getattr(t, "entry_time_et", "")),
                    "triggers": list(getattr(t, "triggers_fired", []) or [])[:4],
                    "exit": str(getattr(t, "exit_reason", "")),
                })
        return StressResult(seed, pert, variant.name, len(trades), round(total, 1),
                            wins, losses, sides, setups, verdicts, sample)
    except Exception as exc:  # noqa: BLE001 — one cell failing must not kill the grid
        return StressResult(seed, pert, variant.name, 0, 0.0, 0, 0, {}, {}, {}, [],
                            error=f"{type(exc).__name__}: {str(exc)[:160]}")


# ────────────────────────────────────────────────────────────────────────────
# Anomaly ranking — what the swarm should look at first
# ────────────────────────────────────────────────────────────────────────────
def find_anomalies(results: list[StressResult]) -> list[dict]:
    """Surface the rows most worth a swarm's adversarial attention:
      - wrong-way: engine took BEAR on an amplified-UP / bull-flip day (or vice-versa)
      - big_loss: worst P&L cells
      - sizing_fragile: same (seed,pert) where P&L swings hugely across variants
      - missed: strong-move scenario where the engine took 0 trades
    """
    anomalies: list[dict] = []
    # big losses
    for r in sorted([x for x in results if not x.error], key=lambda r: r.total_pnl)[:8]:
        if r.total_pnl < 0:
            anomalies.append({"kind": "big_loss", **_digest(r)})
    # sizing fragility: variance of total_pnl across variants for a (seed,pert)
    by_sp: dict = {}
    for r in results:
        if r.error:
            continue
        by_sp.setdefault((r.seed, r.perturbation), []).append(r)
    for (seed, pert), rows in by_sp.items():
        pnls = [r.total_pnl for r in rows]
        if len(pnls) >= 3 and (max(pnls) - min(pnls)) > 400:
            best = max(rows, key=lambda r: r.total_pnl)
            worst = min(rows, key=lambda r: r.total_pnl)
            anomalies.append({
                "kind": "sizing_fragile", "seed": seed, "perturbation": pert,
                "spread": round(max(pnls) - min(pnls), 1),
                "best_variant": best.variant, "best_pnl": best.total_pnl,
                "worst_variant": worst.variant, "worst_pnl": worst.total_pnl,
            })
    # missed strong moves
    for r in results:
        if r.error:
            continue
        if r.perturbation in ("amplify", "trend_flip") and r.n_trades == 0 and r.variant == "base_v15":
            anomalies.append({"kind": "missed_strong_move", **_digest(r)})
    return anomalies[:40]


def _digest(r: StressResult) -> dict:
    return {
        "seed": r.seed, "perturbation": r.perturbation, "variant": r.variant,
        "n_trades": r.n_trades, "total_pnl": r.total_pnl, "sides": r.sides,
        "setups": r.setups, "sample": r.sample_trades,
    }


# ────────────────────────────────────────────────────────────────────────────
# Free-swarm evaluation — the 5-model adversarial CEO panel
# ────────────────────────────────────────────────────────────────────────────
def swarm_evaluate(anomalies: list[dict], grid_summary: dict) -> Optional[dict]:
    """Send the anomaly digest + grid summary to the 5-model free swarm for an
    adversarial 'what hole does this reveal' read. Returns the swarm result dict
    (or None if swarm unavailable). $0."""
    try:
        from swarm_consult import consult
    except Exception as exc:  # noqa: BLE001
        return {"error": f"swarm import failed: {exc}"}
    if not anomalies:
        return {"note": "no anomalies surfaced this batch"}

    context = (
        "ENGINE-STRESS GRID (deterministic engine ground truth; option P&L is BS-sim => "
        "RANKING-ONLY, not a WR authority). The engine was fed REAL historical SPY days "
        "PERTURBED ('what if the bars did this') and run under sizing/exit/direction "
        "variants. Below are the GRID SUMMARY and the ranked ANOMALIES.\n\n"
        f"GRID SUMMARY: {json.dumps(grid_summary)}\n\n"
        f"ANOMALIES ({len(anomalies)}): {json.dumps(anomalies, default=str)[:6000]}"
    )
    question = (
        "You are a panel stress-testing a 0DTE SPY options engine. For the anomalies above: "
        "(1) which reveal a REAL engine hole vs a synthetic-data artifact? "
        "(2) for 'sizing_fragile' rows, which variant is the robust choice and why? "
        "(3) for 'wrong-way'/'big_loss' rows, did the engine make a defensible decision given "
        "what it SAW, or is there a gate/logic gap? "
        "(4) name the 3 highest-value, concretely-testable engine improvements this batch implies. "
        "Be specific and adversarial; ignore artifacts of BS-sim fills."
    )
    try:
        res = consult(mode="critique", question=question, context=context,
                      max_tokens_per_perspective=1400, max_tokens_synthesis=2000)
        return {
            "perspectives_ok": sum(1 for p in res.perspectives if p.ok),
            "n_models": len(res.perspectives),
            "synthesis": (res.synthesis.content if res.synthesis and res.synthesis.ok else None),
            "models": [p.model for p in res.perspectives if p.ok],
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"consult failed: {exc}"}


# ────────────────────────────────────────────────────────────────────────────
# Batch driver
# ────────────────────────────────────────────────────────────────────────────
def run_batch(*, n_seeds: int, full_variants: bool, max_minutes: float,
              do_swarm: bool, smoke: bool) -> dict:
    spy, vix = _load_frames()
    seeds = select_seed_days(spy, n_seeds)
    perts = PERTURBATIONS[:3] if smoke else PERTURBATIONS
    variants = variant_grid(full_variants)
    if smoke:
        seeds = seeds[:2]
        variants = variants[:3]

    deadline = time.monotonic() + max_minutes * 60.0
    results: list[StressResult] = []
    n_planned = len(seeds) * len(perts) * len(variants)
    print(f"[stress] grid: {len(seeds)} seeds x {len(perts)} perts x {len(variants)} variants = {n_planned} runs")

    for seed in seeds:
        spy_w, vix_w, _ = _window_for(spy, vix, seed)
        if spy_w.empty:
            continue
        for pert in perts:
            ps, pv = _perturb_seed(spy_w, vix_w, seed, pert)
            for variant in variants:
                results.append(_run_one(ps, pv, seed, pert, variant))
                if time.monotonic() > deadline:
                    print(f"[stress] hit max-minutes after {len(results)} runs")
                    break
            else:
                continue
            break
        else:
            continue
        break

    ok = [r for r in results if not r.error]
    errs = [r for r in results if r.error]
    grid_summary = {
        "runs": len(results), "ok": len(ok), "errors": len(errs),
        "total_pnl_all": round(sum(r.total_pnl for r in ok), 1),
        "trades_all": sum(r.n_trades for r in ok),
        "seeds": seeds, "perturbations": perts, "variants": [v.name for v in variants],
        "err_samples": [r.error for r in errs[:3]],
    }
    anomalies = find_anomalies(results)
    swarm = swarm_evaluate(anomalies, grid_summary) if do_swarm else {"skipped": True}

    batch = {
        "ts_et": _et_now().isoformat(timespec="seconds"),
        "grid_summary": grid_summary,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "swarm": swarm,
        "disclosure": "Perturbed/synthetic bars -> BS-sim option fills -> RANKING-ONLY, not a WR authority (CLAUDE.md C1).",
    }
    _persist(batch, results)
    return batch


def _persist(batch: dict, results: list[StressResult]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(batch, default=str) + "\n")
    # full per-cell results to a timestamped json for deep dives
    stamp = batch["ts_et"].replace(":", "").replace("-", "")
    (OUT_DIR / f"grid-{stamp}.json").write_text(
        json.dumps([asdict(r) for r in results], default=str, indent=2), encoding="utf-8")
    _write_report(batch)


def _write_report(batch: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    gs = batch["grid_summary"]
    lines = [
        "# Engine-Stress Swarm — Batch Report",
        "",
        f"**Generated:** {batch['ts_et']} ET",
        f"**Disclosure:** {batch['disclosure']}",
        "",
        "## Grid",
        f"- Runs: {gs['runs']} ({gs['ok']} ok / {gs['errors']} errors)",
        f"- Seeds: {', '.join(gs['seeds'])}",
        f"- Perturbations: {', '.join(gs['perturbations'])}",
        f"- Variants: {', '.join(gs['variants'])}",
        f"- Aggregate BS-sim P&L (ranking-only): ${gs['total_pnl_all']} over {gs['trades_all']} trades",
        "",
        f"## Anomalies surfaced: {batch['anomaly_count']}",
    ]
    for a in batch["anomalies"][:20]:
        lines.append(f"- **{a.get('kind')}** seed={a.get('seed')} pert={a.get('perturbation')} "
                     f"variant={a.get('variant', a.get('best_variant',''))} "
                     f"pnl={a.get('total_pnl', a.get('spread',''))}")
    lines += ["", "## Swarm verdict (5-model free panel)"]
    sw = batch.get("swarm", {})
    if sw.get("synthesis"):
        lines.append(f"_models: {', '.join(sw.get('models', []))} ({sw.get('perspectives_ok')}/{sw.get('n_models')} ok)_")
        lines.append("")
        lines.append(sw["synthesis"])
    else:
        lines.append(f"_(no synthesis: {json.dumps({k: v for k, v in sw.items() if k != 'synthesis'})})_")
    (REPORT_DIR / "ENGINE-STRESS-SWARM-LATEST.md").write_text("\n".join(lines), encoding="utf-8")


def _main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--max-minutes", type=float, default=30.0)
    ap.add_argument("--full-variants", action="store_true", help="wide overnight variant grid")
    ap.add_argument("--no-swarm", action="store_true", help="engine grid only, skip the LLM panel")
    ap.add_argument("--smoke", action="store_true", help="tiny validation grid (2 seeds x 3 perts x 3 variants)")
    args = ap.parse_args()

    batch = run_batch(
        n_seeds=args.seeds, full_variants=args.full_variants,
        max_minutes=args.max_minutes, do_swarm=not args.no_swarm, smoke=args.smoke,
    )
    gs = batch["grid_summary"]
    print(f"[stress] DONE runs={gs['runs']} ok={gs['ok']} err={gs['errors']} "
          f"anomalies={batch['anomaly_count']} pnl=${gs['total_pnl_all']}")
    print(f"[stress] report: markdown/research/ENGINE-STRESS-SWARM-LATEST.md")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
