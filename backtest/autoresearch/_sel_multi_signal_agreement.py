"""SELECTION hypothesis -- MULTI-SIGNAL DETECTOR AGREEMENT -- real 0DTE fills (OPRA sim).

HYPOTHESIS (genuinely new): does INDEPENDENT-DETECTOR CONFLUENCE create an edge that no
single watcher had? Using automation/state/watcher-observations.jsonl (every watcher's
fires over 16 months), find bars where >= N DISTINCT, INDEPENDENT watchers fire the SAME
direction within a short window (default 15 min). Enter a 0DTE option on that agreement,
SURVIVOR structure (strike_offset=-2 ITM-2, premium_stop=-0.08, v15 chandelier exits),
real OPRA fills (C1 -- the only WR authority). Sweep the agreement threshold (>=2 vs >=3).

"SELECTION is the edge" thesis: mechanical daily signals are coin-flips (WR 30-38%, no raw
entry edge); the one survivor (vwap_continuation) is SELECTIVE. This asks whether requiring
multiple INDEPENDENT confirmations -- the literal essence of selection -- converts a
coin-flip into an edge. It may also fail; tested honestly behind ALL gates.

ENTRY MODEL (causal, no look-ahead -- C6):
  * Walk the obs log chronologically (sorted by bar_timestamp_et).
  * For each directional fire, count DISTINCT watcher_names that fired the SAME direction
    within the prior `window_min` (causal lookback only -- agreement is "formed by now").
  * When that distinct count first reaches the threshold, that bar is an AGREEMENT entry.
  * Per-direction cooldown (default 45 min, anti-pattern 2.7) prevents stacking the same
    agreement cluster into many duplicate trades.
  * direction long -> CALL ('C'), short -> PUT ('P').
  * rejection_level (chart-stop reference) = the firing watcher's stop_price.

ALL GATES MANDATORY (deterministic, no cherry-picking -- anti-pattern 2.10). A config CLEARS
only if every one of these holds on the COOLED (cd>0) run:
  (1) OOS(2026) per-trade > 0
  (2) positive_quarters >= 4 of 6
  (3) top5-day concentration < 200%
  (4) n >= 20
  (5) drop-top-5-DAYS total still > 0 (not carried by a handful of days)
  (6) BEATS a random-entry null (same exit/strike/stop, same count & side mix, ~20 seeds):
      real OOS per-trade > mean(null OOS per-trade) -- confluence must add over random timing.
  (7) NO sign inversion at chart-stop-only (premium_stop=-0.99): if the edge flips sign when
      the premium stop is removed, it was a stop artifact not an entry edge (no-truncation).
  (8) IN-SAMPLE (2025) half is ALSO positive (reject IS-neg/OOS-pos single-regime artifacts
      -- the futures trap).

Pure Python, $0 in the sim loop. No live orders. Writes
analysis/recommendations/sel-multi-signal-agreement.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

# ── SURVIVOR STRUCTURE (per task spec + params.json v15) ──────────────────────
QTY = 3
STRIKE_OFFSET = -2                # ITM-2 (survivor structure)
PREMIUM_STOP_PCT = -0.08          # v15 asymmetric stop (survivor structure)
# v15 chandelier profit-lock (from automation/state/params.json):
PL_MODE = "trailing"
PL_THRESHOLD = 0.05               # arm at +5% favorable
PL_TRAIL = 0.15                   # trail 15% off HWM (v15 current; doc 2026-06-19)

OBS_PATH = ROOT / "automation" / "state" / "watcher-observations.jsonl"
OUT_JSON = ROOT / "analysis" / "recommendations" / "sel-multi-signal-agreement.json"

START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)
OOS_YEAR = 2026

# Gate thresholds
BAR_N = 20
BAR_POS_Q = 4          # of 6 quarters
BAR_TOP5 = 200.0       # top5-day pct must be < this
NULL_SEEDS = 20

# Sweep
WINDOW_MIN = 15
THRESHOLDS = [2, 3]
COOLDOWN_MIN = 45


# ── DATA LOADING ──────────────────────────────────────────────────────────────
def load_rth() -> tuple[pd.DataFrame, dict]:
    spy, _vix = ar_runner.load_data(START, END)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    rth = spy[(spy["timestamp_et"].dt.time >= dt.time(9, 30))
              & (spy["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    rth_naive = (rth["timestamp_et"].dt.tz_localize(None)
                 if rth["timestamp_et"].dt.tz is not None else rth["timestamp_et"])
    idx_map = {ts.to_pydatetime(): i for i, ts in enumerate(rth_naive)}
    return rth, idx_map


def load_observations() -> list[tuple[dt.datetime, str, str, float, float]]:
    """Return sorted (bar_dt_naive, watcher_name, direction, stop_price, entry_price)."""
    out: list[tuple[dt.datetime, str, str, float, float]] = []
    n_bad = 0
    for line in OBS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            n_bad += 1
            continue
        if "watcher_name" not in o:
            continue
        t = o.get("bar_timestamp_et")
        if not isinstance(t, str):
            continue
        d = o.get("direction")
        if d not in ("long", "short"):
            continue
        try:
            pt = dt.datetime.fromisoformat(t).replace(tzinfo=None)
        except Exception:
            n_bad += 1
            continue
        out.append((pt, o["watcher_name"], d,
                    o.get("stop_price"), o.get("entry_price")))
    out.sort(key=lambda x: x[0])
    log.info("Loaded %d directional observations (%d unparseable lines skipped)", len(out), n_bad)
    return out


# ── AGREEMENT DETECTION (causal, distinct-watcher) ────────────────────────────
@dataclass
class AgreementSignal:
    bar_dt: dt.datetime
    side: str            # 'C' or 'P'
    direction: str       # 'long' / 'short'
    n_distinct: int
    watchers: tuple[str, ...]
    stop_price: float | None


def detect_agreements(obs, *, window_min: int, threshold: int, cooldown_min: int) -> list[AgreementSignal]:
    """First bar at which >= `threshold` DISTINCT watchers agree on a direction within the
    causal lookback window. Per-direction cooldown collapses a cluster into one entry."""
    byday: dict[dt.date, list] = defaultdict(list)
    for o in obs:
        byday[o[0].date()].append(o)
    sigs: list[AgreementSignal] = []
    for d in sorted(byday):
        lst = sorted(byday[d], key=lambda x: x[0])
        last_long: dt.datetime | None = None
        last_short: dt.datetime | None = None
        for i, (t, w, dir_, sp, ep) in enumerate(lst):
            names = {w}
            for j in range(i - 1, -1, -1):
                tj, wj, dj, spj, epj = lst[j]
                if (t - tj).total_seconds() > window_min * 60:
                    break
                if dj == dir_:
                    names.add(wj)
            if len(names) < threshold:
                continue
            last = last_long if dir_ == "long" else last_short
            if last is not None and (t - last).total_seconds() < cooldown_min * 60:
                continue
            if dir_ == "long":
                last_long = t
            else:
                last_short = t
            sigs.append(AgreementSignal(
                bar_dt=t, side=("C" if dir_ == "long" else "P"), direction=dir_,
                n_distinct=len(names), watchers=tuple(sorted(names)),
                stop_price=(float(sp) if sp is not None else None)))
    return sigs


# ── SIM ───────────────────────────────────────────────────────────────────────
@dataclass
class TradeRow:
    date: str
    time: str
    side: str
    n_distinct: int
    strike: int
    entry_premium: float
    pnl: float
    exit_reason: str


def _default_stop(rth: pd.Series, side: str, sig_stop: float | None) -> float:
    """rejection_level for the chart stop. Use the firing watcher's stop_price when present,
    else a sane fallback just past entry (won't bind before premium stop)."""
    if sig_stop is not None and sig_stop > 0:
        return sig_stop
    spot = float(rth["close"])
    return spot + 0.50 if side == "P" else spot - 0.50


def simulate(sigs: list[AgreementSignal], rth: pd.DataFrame, idx_map: dict,
             *, premium_stop_pct: float, use_chandelier: bool = True,
             entry_offsets: dict[dt.datetime, int] | None = None) -> tuple[list[TradeRow], dict]:
    rows: list[TradeRow] = []
    n_total = len(sigs)
    n_no_bar = n_sim_none = n_filled = 0
    for sg in sigs:
        # entry bar (optionally jittered for the null test)
        base_idx = idx_map.get(sg.bar_dt)
        if base_idx is None:
            n_no_bar += 1
            continue
        idx = base_idx
        if entry_offsets is not None:
            idx = base_idx + entry_offsets.get(sg.bar_dt, 0)
            if idx < 0 or idx >= len(rth):
                n_no_bar += 1
                continue
            # keep the random entry on the SAME trading day (causal, comparable)
            if rth["timestamp_et"].iloc[idx].date() != sg.bar_dt.date():
                idx = base_idx
        bar = rth.iloc[idx]
        rej = _default_stop(bar, sg.side, sg.stop_price)
        fill = simulate_trade_real(
            entry_bar_idx=idx, entry_bar=bar, spy_df=rth, ribbon_df=None,
            rejection_level=rej,
            triggers_fired=["multi_signal_agreement", f"n{sg.n_distinct}", sg.direction],
            side=sg.side, qty=QTY, setup="SEL_MULTI_SIGNAL_AGREEMENT",
            premium_stop_pct=premium_stop_pct, strike_offset=STRIKE_OFFSET,
            profit_lock_mode=(PL_MODE if use_chandelier else "fixed"),
            profit_lock_threshold_pct=(PL_THRESHOLD if use_chandelier else 0.0),
            profit_lock_trail_pct=(PL_TRAIL if use_chandelier else 0.0))
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(
            date=str(bar["timestamp_et"].date()),
            time=bar["timestamp_et"].strftime("%H:%M"),
            side=sg.side, n_distinct=sg.n_distinct, strike=int(fill.strike),
            entry_premium=round(float(fill.entry_premium), 3),
            pnl=round(float(fill.dollar_pnl), 2),
            exit_reason=(fill.exit_reason.name if fill.exit_reason else "NONE")))
    cov = {"signals": n_total, "filled": n_filled, "no_bar": n_no_bar, "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ── METRICS (OP-20 disclosure) ────────────────────────────────────────────────
def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _by_day(rows: list[TradeRow]) -> dict[str, float]:
    bd: dict[str, float] = defaultdict(float)
    for r in rows:
        bd[r.date] += r.pnl
    return bd


def metrics(rows: list[TradeRow]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]

    def _exp(rs):
        return round(float(np.mean([r.pnl for r in rs])), 2) if rs else None

    def _tot(rs):
        return round(float(np.sum([r.pnl for r in rs])), 2) if rs else 0.0

    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_quarter(r.date)].append(r.pnl)
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)

    bd = _by_day(rows)
    total = sum(bd.values())
    days_sorted = sorted(bd.values(), reverse=True)
    top5 = sum(days_sorted[:5])
    top5_pct = round(100 * top5 / total, 1) if total > 0 else None
    drop_top5_total = round(total - top5, 2)
    drop_top5_per_trade = (round((total - top5) / max(1, (n - _count_in_top5_days(rows, bd))), 2)
                           if total > 0 else None)

    by_side = {}
    for sd in ("C", "P"):
        s = [r.pnl for r in rows if r.side == sd]
        if s:
            by_side[sd] = {"n": len(s), "exp": round(sum(s) / len(s), 2),
                           "wr": round(100 * float((np.array(s) > 0).mean()), 1),
                           "total": round(sum(s), 2)}

    exit_hist: dict[str, int] = defaultdict(int)
    for r in rows:
        exit_hist[r.exit_reason] += 1

    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": top5_pct,
        "drop_top5_days_total": drop_top5_total,
        "drop_top5_days_per_trade": drop_top5_per_trade,
        "by_side": by_side,
        "exit_hist": dict(sorted(exit_hist.items())),
    }


def _count_in_top5_days(rows: list[TradeRow], bd: dict[str, float]) -> int:
    top5_days = set(d for d, _ in sorted(bd.items(), key=lambda kv: kv[1], reverse=True)[:5])
    return sum(1 for r in rows if r.date in top5_days)


# ── NULL TEST (random-entry-timing) ───────────────────────────────────────────
def random_null(sigs, rth, idx_map, *, seeds: int) -> dict:
    """Same count/side mix, same exit/strike/stop -- but enter on a RANDOM bar of the SAME
    trading day instead of the agreement bar. If real OOS per-trade does not beat the null
    mean, the agreement TIMING added nothing over random."""
    # precompute per-day RTH bar index ranges
    day_idx: dict[dt.date, list[int]] = defaultdict(list)
    for i, ts in enumerate(rth["timestamp_et"]):
        day_idx[ts.date()].append(i)
    oos_means: list[float] = []
    is_means: list[float] = []
    full_means: list[float] = []
    for seed in range(seeds):
        rng = random.Random(1000 + seed)
        offsets: dict[dt.datetime, int] = {}
        for sg in sigs:
            base = idx_map.get(sg.bar_dt)
            if base is None:
                continue
            day = sg.bar_dt.date()
            choices = [i for i in day_idx.get(day, []) if i < day_idx[day][-1] - 2]  # leave room to exit
            if not choices:
                offsets[sg.bar_dt] = 0
                continue
            pick = rng.choice(choices)
            offsets[sg.bar_dt] = pick - base
        rows, _ = simulate(sigs, rth, idx_map, premium_stop_pct=PREMIUM_STOP_PCT,
                           use_chandelier=True, entry_offsets=offsets)
        if not rows:
            continue
        m = metrics(rows)
        if m.get("oos_exp") is not None:
            oos_means.append(m["oos_exp"])
        if m.get("is_exp") is not None:
            is_means.append(m["is_exp"])
        full_means.append(m["exp_dollar"])
    return {
        "seeds": seeds,
        "null_oos_exp_mean": round(float(np.mean(oos_means)), 2) if oos_means else None,
        "null_oos_exp_std": round(float(np.std(oos_means)), 2) if oos_means else None,
        "null_is_exp_mean": round(float(np.mean(is_means)), 2) if is_means else None,
        "null_full_exp_mean": round(float(np.mean(full_means)), 2) if full_means else None,
    }


# ── GATE EVALUATION ───────────────────────────────────────────────────────────
def evaluate_gates(m: dict, m_chartstop: dict, null: dict) -> tuple[dict, bool]:
    g = {}
    g["n_ge_20"] = m.get("n", 0) >= BAR_N
    g["oos_per_trade_pos"] = (m.get("oos_exp") is not None and m["oos_exp"] > 0)
    g["is_per_trade_pos"] = (m.get("is_exp") is not None and m["is_exp"] > 0)
    g["pos_quarters_ge_4"] = m.get("positive_quarters_n", 0) >= BAR_POS_Q
    t5 = m.get("top5_day_pct")
    g["top5_under_200"] = (t5 is not None and t5 < BAR_TOP5)
    g["drop_top5_pos"] = (m.get("drop_top5_days_total") is not None and m["drop_top5_days_total"] > 0)
    nm = null.get("null_oos_exp_mean")
    g["beats_random_null"] = (m.get("oos_exp") is not None and nm is not None and m["oos_exp"] > nm)
    # no-truncation: sign must NOT invert at chart-stop-only
    real_oos = m.get("oos_exp")
    cs_oos = m_chartstop.get("oos_exp")
    if real_oos is None or cs_oos is None:
        g["no_sign_inversion_chartstop"] = False
    else:
        # require same sign (both >=0). If real is positive, chart-stop must also be >= 0.
        g["no_sign_inversion_chartstop"] = (real_oos > 0 and cs_oos >= 0)
    clears = all(g.values())
    return g, clears


# ── MAIN ───────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--window-min", type=int, default=WINDOW_MIN)
    p.add_argument("--cooldown-min", type=int, default=COOLDOWN_MIN)
    p.add_argument("--seeds", type=int, default=NULL_SEEDS)
    args = p.parse_args(argv)

    log.info("Loading RTH SPY %s..%s + observation log", START, END)
    rth, idx_map = load_rth()
    obs = load_observations()
    log.info("RTH bars=%d  obs=%d", len(rth), len(obs))

    configs: list[dict] = []
    any_clears = False
    best = None
    for thresh in THRESHOLDS:
        slug = f"agree_ge{thresh}"
        log.info("=== CONFIG %s  window=%dmin cooldown=%dmin ===", slug, args.window_min, args.cooldown_min)

        # cooled (gated) signals
        sigs = detect_agreements(obs, window_min=args.window_min, threshold=thresh,
                                 cooldown_min=args.cooldown_min)
        n_2025 = sum(1 for s in sigs if s.bar_dt.year == 2025)
        n_2026 = sum(1 for s in sigs if s.bar_dt.year == 2026)
        log.info("  agreement signals: %d (IS=%d OOS=%d)", len(sigs), n_2025, n_2026)

        rows, cov = simulate(sigs, rth, idx_map, premium_stop_pct=PREMIUM_STOP_PCT, use_chandelier=True)
        m = metrics(rows)

        # chart-stop-only (no-truncation) replication
        rows_cs, _ = simulate(sigs, rth, idx_map, premium_stop_pct=-0.99, use_chandelier=True)
        m_cs = metrics(rows_cs)

        # random-entry null
        log.info("  running random-entry null (%d seeds)...", args.seeds)
        null = random_null(sigs, rth, idx_map, seeds=args.seeds)

        # no-cooldown robustness (reported, not gated)
        sigs_nocd = detect_agreements(obs, window_min=args.window_min, threshold=thresh, cooldown_min=0)
        rows_nocd, _ = simulate(sigs_nocd, rth, idx_map, premium_stop_pct=PREMIUM_STOP_PCT, use_chandelier=True)
        m_nocd = metrics(rows_nocd)

        gates, clears = evaluate_gates(m, m_cs, null)
        any_clears = any_clears or clears

        cfg = {
            "config": slug,
            "threshold_distinct_watchers": thresh,
            "window_min": args.window_min,
            "cooldown_min": args.cooldown_min,
            "n_signals": len(sigs),
            "signals_is": n_2025, "signals_oos": n_2026,
            "coverage": cov,
            "metrics": m,
            "metrics_chartstop_only": {k: m_cs.get(k) for k in
                                       ("n", "exp_dollar", "oos_exp", "is_exp", "total_dollar")},
            "metrics_no_cooldown": {k: m_nocd.get(k) for k in
                                    ("n", "exp_dollar", "oos_exp", "is_exp", "positive_quarters", "top5_day_pct")},
            "random_null": null,
            "gates": gates,
            "clears_all_gates": clears,
        }
        configs.append(cfg)

        mm = m if m.get("n") else {}
        log.info("  RESULT n=%s exp=$%s oos_exp=$%s is_exp=$%s posQ=%s top5%%=%s clears=%s",
                 mm.get("n"), mm.get("exp_dollar"), mm.get("oos_exp"), mm.get("is_exp"),
                 mm.get("positive_quarters"), mm.get("top5_day_pct"), clears)
        log.info("  gates: %s", gates)

        # track best by OOS per-trade among configs with n>=20
        if m.get("n", 0) >= BAR_N and m.get("oos_exp") is not None:
            if best is None or m["oos_exp"] > best[1]:
                best = (slug, m["oos_exp"], clears)

    summary = {
        "run_date": dt.date.today().isoformat(),
        "hypothesis": "multi_signal_agreement: >=N independent watchers same direction within "
                      "a short window -> real-fills 0DTE edge (SELECTION/CONFLUENCE thesis)",
        "window": f"{START}..{END}",
        "survivor_structure": {
            "strike_offset": STRIKE_OFFSET, "premium_stop_pct": PREMIUM_STOP_PCT, "qty": QTY,
            "exits": f"v15 chandelier mode={PL_MODE} arm=+{PL_THRESHOLD} trail={PL_TRAIL}, "
                     "tp1 0.50@+0.30, runner 2.5x (simulator defaults)",
        },
        "gate_definitions": {
            "n_ge_20": "n >= 20",
            "oos_per_trade_pos": "OOS(2026) per-trade expectancy > 0",
            "is_per_trade_pos": "IN-SAMPLE(2025) per-trade expectancy > 0 (no single-regime artifact)",
            "pos_quarters_ge_4": "positive quarters >= 4 of 6",
            "top5_under_200": "top-5-day concentration < 200%",
            "drop_top5_pos": "P&L after dropping top-5 days still > 0",
            "beats_random_null": f"OOS per-trade > mean of {args.seeds}-seed random-entry null",
            "no_sign_inversion_chartstop": "OOS sign does NOT invert at premium_stop=-0.99 (no-truncation)",
        },
        "configs": configs,
        "best_config": (best[0] if best else None),
        "any_config_clears_all_gates": any_clears,
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) -- the only WR authority",
            "spy_vs_option": "SPY-direction != option edge; this is the option-edge test (C3/L58)",
            "per_trade": "per-trade expectancy reported, not WR alone (OP-14/C4)",
            "concentration": "top5_day_pct + drop-top-5-days shown (OP-20 #5)",
            "independence_caveat": "watchers are NOT fully independent (e.g. v14_enhanced + "
                                   "bearish_reversal_at_level both detect bearish rejections); "
                                   "DISTINCT watcher_name is the proxy for 'independent detector'.",
            "causality": "agreement counted with causal lookback only; entry on the bar agreement "
                         "is reached; null jitters entry within the SAME day (C6 no look-ahead).",
            "no_grid_search": "agreement threshold swept {2,3} only (the hypothesis's stated knob); "
                              "no hidden parameter mining.",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    print("\n=== SEL multi_signal_agreement -- VERDICT ===")
    for c in configs:
        m = c["metrics"]
        print(f"[{c['config']}] n={m.get('n')} (IS={m.get('is_n')}/OOS={m.get('oos_n')}) "
              f"exp=${m.get('exp_dollar')} oos_exp=${m.get('oos_exp')} is_exp=${m.get('is_exp')} "
              f"posQ={m.get('positive_quarters')} top5%={m.get('top5_day_pct')} "
              f"null_oos=${c['random_null'].get('null_oos_exp_mean')} "
              f"chartstop_oos=${c['metrics_chartstop_only'].get('oos_exp')} "
              f"-> CLEARS={c['clears_all_gates']}")
        print(f"        gates: {c['gates']}")
    print(f"ANY config clears all gates: {any_clears}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
