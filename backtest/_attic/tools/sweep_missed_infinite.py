"""INFINITE missed-week engine sweep.

Continuously brute-forces the production engine's params over the 4 missed-week days
(2026-05-26..29) with REAL OPRA fills, hunting configs that flip the premium-stop CHOP
(memory: "right direction, chopped by premium stops") into green days.

Runs FOREVER as a detached background process. $0 — pure Python, zero LLM, zero API,
does NOT touch the heartbeat rate-limit pool, so it is safe to grind through market hours.

Search space is centered on the chop problem: premium stop magnitude, tp1 level, qty
fraction, strike offset (ITM<->OTM), profit-lock mode/trail, min triggers, entry time.
Alternates an exhaustive discrete grid with continuous random sampling so it keeps finding
new points between grid nodes after the first pass.

J directive 2026-05-31: overfitting the missed days is INTENDED for this exploration.
Any promoted config STILL needs J-anchor no-regression validation (OP-16) before going
live — that is the separate full-history grinder's job, NOT this overfit hunt.

Outputs (rewritten continuously):
  analysis/missed-infinite-sweep.md       -- live leaderboard (top configs)
  analysis/missed-infinite-keepers.jsonl  -- append-only: every new all-time-best / all-green
  analysis/missed-infinite-status.json    -- iteration count, combos tested, best (for monitoring)
  automation/state/logs/missed-infinite.log -- progress log
"""
from __future__ import annotations

import sys
import datetime as dt
import itertools
import json
import random
import time
import traceback
from pathlib import Path

# --- self-contained imports (works whether or not venv site-packages is on PYTHONPATH) ---
REPO = Path(__file__).resolve().parents[1]            # backtest/
_VENV_SITE = REPO / ".venv" / "Lib" / "site-packages"
if _VENV_SITE.exists():
    sys.path.insert(0, str(_VENV_SITE))
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402

DATA = REPO / "data"
ANALYSIS = REPO.parent / "analysis"
LOGDIR = REPO.parent / "automation" / "state" / "logs"
LOGDIR.mkdir(parents=True, exist_ok=True)
OUT_MD = ANALYSIS / "missed-infinite-sweep.md"
KEEPERS = ANALYSIS / "missed-infinite-keepers.jsonl"
STATUS = ANALYSIS / "missed-infinite-status.json"
LOG = LOGDIR / "missed-infinite.log"

MISSED = [dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)]


def _log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def _load_market() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load a SPY/VIX 5m CSV pair that covers the missed week. Prefer the proven file."""
    candidates = sorted(DATA.glob("spy_5m_2026-05-19_*.csv"))
    if not candidates:
        raise FileNotFoundError("no spy_5m_2026-05-19_*.csv covering the missed week")
    spy_path = candidates[0]
    vix_path = DATA / spy_path.name.replace("spy_5m_", "vix_5m_")
    if not vix_path.exists():
        vcand = sorted(DATA.glob("vix_5m_2026-05-19_*.csv"))
        vix_path = vcand[0]
    spy = pd.read_csv(spy_path)
    vix = pd.read_csv(vix_path)
    # Normalise timestamp to the tz-aware string the loader expects (mirrors sweep_missed_green).
    for _df in (spy, vix):
        _ts = pd.to_datetime(_df["timestamp_et"], format="ISO8601", utc=True).dt.tz_convert("America/New_York")
        _df["timestamp_et"] = _ts.dt.strftime("%Y-%m-%d %H:%M:%S-04:00")
    _log(f"loaded {spy_path.name} ({len(spy)} bars) + {vix_path.name} ({len(vix)} bars)")
    return spy, vix


# --- discrete grid (the chop problem lives mostly in stop magnitude + strike + entry time) ---
STOPS = [-0.06, -0.08, -0.10, -0.12, -0.15, -0.20, -0.25, -0.30, -0.35, -0.45, -0.55]
TP1S = [0.20, 0.30, 0.40, 0.50, 0.65, 0.75]
QFRACS = [0.33, 0.50, 0.667]
STRIKES = [-2, -1, 0, 2, 3]            # ITM2, ITM1, ATM, OTM2, OTM3 (calls: atm+offset)
PLS = [("fixed", 0.0, 0.0), ("trailing", 0.05, 0.20), ("trailing", 0.05, 0.10),
       ("trailing", 0.10, 0.20), ("trailing", 0.03, 0.15)]
MTBULLS = [1, 2, 3]
NTBS = [dt.time(9, 35), dt.time(9, 40), dt.time(9, 45), dt.time(10, 0)]


def _grid_iter():
    combos = list(itertools.product(STOPS, TP1S, QFRACS, STRIKES, PLS, MTBULLS, NTBS))
    random.shuffle(combos)
    for stop, tp1, qf, soff, pl, mtb, ntb in combos:
        yield stop, tp1, qf, soff, pl, mtb, ntb


def _random_combo():
    stop = -round(random.uniform(0.05, 0.60), 3)
    tp1 = round(random.uniform(0.15, 0.85), 2)
    qf = random.choice(QFRACS)
    soff = random.choice(STRIKES)
    if random.random() < 0.3:
        pl = ("fixed", 0.0, 0.0)
    else:
        pl = ("trailing", round(random.uniform(0.03, 0.12), 3), round(random.uniform(0.08, 0.30), 3))
    mtb = random.choice(MTBULLS)
    ntb = random.choice(NTBS)
    return stop, tp1, qf, soff, pl, mtb, ntb


def _score(spy, vix, stop, tp1, qf, soff, pl, mtb, ntb):
    plm, plt, plr = pl
    r = run_backtest(
        spy, vix, start_date=MISSED[0], end_date=MISSED[-1], use_real_fills=True,
        premium_stop_pct=stop, tp1_premium_pct=tp1, tp1_qty_fraction=qf,
        strike_offset=soff, min_triggers_bull=mtb,
        profit_lock_mode=plm, profit_lock_threshold_pct=plt, profit_lock_trail_pct=plr,
        no_trade_before=ntb,
    )
    per_day = {d: 0.0 for d in MISSED}
    pc_day = {d: 0.0 for d in MISSED}
    for t in r.trades:
        d = t.entry_time_et.date()
        if d in per_day:
            per_day[d] += t.dollar_pnl
            pc_day[d] += t.dollar_pnl / max(1, t.qty)
    green = sum(1 for d in MISSED if per_day[d] > 0)
    return {
        "stop": stop, "tp1": tp1, "qf": qf, "soff": soff,
        "plm": plm, "plt": plt, "plr": plr, "mtb": mtb, "ntb": ntb.strftime("%H:%M"),
        "green": green, "tot": round(sum(per_day.values()), 2),
        "totpc": round(sum(pc_day.values()), 2), "n": len(r.trades),
        "per_day": {str(d): round(per_day[d], 1) for d in MISSED},
    }


def _label(r):
    pl = "fixed" if r["plm"] == "fixed" else f"trail{r['plt']}/{r['plr']}"
    return (f"stop{int(r['stop']*100)} tp1{int(r['tp1']*100)} qf{r['qf']} "
            f"strike{r['soff']:+d} {pl} mtb{r['mtb']} entry{r['ntb']}")


def _write_leaderboard(best, baseline, combos_tested, started_at):
    best_sorted = sorted(best, key=lambda x: (x["green"], x["totpc"]), reverse=True)[:25]
    lines = ["# Missed-week INFINITE sweep — live leaderboard", "",
             f"Real engine, real OPRA fills over {MISSED[0]}..{MISSED[-1]}. Overfit by design (J 5/31).",
             f"Combos tested: **{combos_tested:,}** | running since {started_at} | updated {dt.datetime.now():%Y-%m-%d %H:%M:%S}", ""]
    if baseline:
        lines += [f"**Baseline (≈production):** {baseline['green']}/4 green, {baseline['totpc']:+.1f}/c, "
                  f"{baseline['tot']:+.0f}$ — {_label(baseline)}", ""]
    lines += ["## Top 25 by (green days, per-contract $)", "",
              "| green | per-day $ (26/27/28/29) | tot/c | tot$ | n | config |",
              "|---|---|---|---|---|---|"]
    for r in best_sorted:
        pd_ = " / ".join(f"{r['per_day'][str(d)]:+.0f}" for d in MISSED)
        lines.append(f"| **{r['green']}/4** | {pd_} | {r['totpc']:+.1f} | {r['tot']:+.0f} | {r['n']} | {_label(r)} |")
    allg = [r for r in best_sorted if r["green"] == 4]
    lines += ["", f"## ALL-4-GREEN configs in top set: {len(allg)}"]
    for r in allg[:10]:
        lines.append(f"- {_label(r)} (tot/c {r['totpc']:+.1f}, n={r['n']})")
    lines += ["", "> NOTE: overfit to 4 days. Promote ONLY after J-anchor no-regression (OP-16)."]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main():
    _log("=== missed-week INFINITE sweep starting ===")
    spy, vix = _load_market()
    started_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    # Baseline ~production (symmetric -8% stop, tp1 50%, ATM, trailing chandelier, 09:35).
    try:
        baseline = _score(spy, vix, -0.08, 0.50, 0.50, 0, ("trailing", 0.05, 0.20), 2, dt.time(9, 35))
        _log(f"baseline {baseline['green']}/4 green tot/c {baseline['totpc']:+.1f} :: {_label(baseline)}")
    except Exception as e:
        baseline = None
        _log(f"baseline failed: {e}")

    best = []                       # all-time top results (capped)
    best_key = set()                # dedupe by config signature
    best_totpc = baseline["totpc"] if baseline else -1e9
    best_green = baseline["green"] if baseline else 0
    combos_tested = 0
    errors = 0
    pass_num = 0

    while True:
        pass_num += 1
        use_grid = (pass_num % 2 == 1)   # alternate full grid passes with random passes
        _log(f"--- pass {pass_num} ({'grid' if use_grid else 'random'}) | tested={combos_tested:,} best={best_green}/4 {best_totpc:+.1f}/c ---")
        gen = _grid_iter() if use_grid else (_random_combo() for _ in range(40000))
        for combo in gen:
            try:
                r = _score(spy, vix, *combo)
            except Exception:
                errors += 1
                continue
            combos_tested += 1
            sig = (r["stop"], r["tp1"], r["qf"], r["soff"], r["plm"], r["plt"], r["plr"], r["mtb"], r["ntb"])
            is_new_best = (r["green"], r["totpc"]) > (best_green, best_totpc)
            if (r["green"] == 4 or is_new_best) and sig not in best_key:
                best_key.add(sig)
                best.append(r)
                best.sort(key=lambda x: (x["green"], x["totpc"]), reverse=True)
                best = best[:200]
                with KEEPERS.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"found_at": dt.datetime.now().isoformat(timespec="seconds"), **r}) + "\n")
                if is_new_best:
                    best_green, best_totpc = r["green"], r["totpc"]
                    _log(f"NEW BEST {r['green']}/4 tot/c {r['totpc']:+.1f} :: {_label(r)} :: per-day {r['per_day']}")
            if combos_tested % 25 == 0:
                _write_leaderboard(best, baseline, combos_tested, started_at)
                STATUS.write_text(json.dumps({
                    "updated": dt.datetime.now().isoformat(timespec="seconds"),
                    "started_at": started_at, "pass": pass_num, "combos_tested": combos_tested,
                    "errors": errors, "best_green": best_green, "best_totpc": best_totpc,
                    "best_label": _label(best[0]) if best else None,
                    "baseline_green": baseline["green"] if baseline else None,
                    "baseline_totpc": baseline["totpc"] if baseline else None,
                }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _log("FATAL:\n" + traceback.format_exc())
        raise
