"""spy_production_calibration.py -- point the null harness at the KNOWN-POSITIVE control.

WHY THIS EXISTS
---------------
The multi-lane Stage A harness scored SPY itself at -0.007% / 49.8% hit -- statistically
nothing -- over the same window in which the PRODUCTION SPY engine booked three consecutive
green sessions. Both cannot be casually true. This script resolves that, by running the
IDENTICAL metric and IDENTICAL null construction against the production engine's own decision
ledger (`automation/state/core-decisions.jsonl`), where the real curated levels, trendlines and
multi-day memory sat behind every signal.

It answers one question: **can this measuring device detect a directional edge when a known-good
one is present?** If yes, the multi-lane null is a true negative and the fork lost a real INPUT.
If no, the metric does not capture where this engine's money comes from -- and the gate every
future candidate is judged by has to be rebuilt.

Frozen decision rule: analysis/recommendations/prereg-spy-production-calibration-2026-08-20.json

TWO POPULATIONS, deliberately separated (per the prereg):
  A -- every row with verdict in {ENTER_BEAR, ENTER_BULL}, deduped across the safe/bold accounts.
       This is the RAW TRIGGER, upstream of the entry gates: 815 of the 886 were blocked from
       ever trading, so scoring all of them carries no survivorship and no conditioning on the
       profitable subset. This is the headline.
  B -- the subset with action == PLACED. Where money was actually risked. Reported separately
       and never as the headline: thin (n~71) and conditioned on gates tuned in this same window.

If A fails and B passes, the information lives in the GATES rather than the trigger -- a third
pre-committed outcome, and the most transplantable one.

READ-ONLY. Touches no parameter, arms nothing, places nothing.

Run:  backtest/.venv/Scripts/python.exe backtest/tools/spy_production_calibration.py
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi import core as mcore  # noqa: E402  -- reuse the SAME bar fetcher, traps and all
from multi.lib import creds as mcreds  # noqa: E402

LEDGER = REPO / "automation" / "state" / "core-decisions.jsonl"
OUT = REPO / "analysis" / "multi-lane" / "spy-production-calibration.json"
HORIZONS = (2, 6, 12)          # 5-min bars -> +10 / +30 / +60 min. UNCHANGED from Stage A.
HEADLINE = 6
NULL_DRAWS = 200
SEED = 20260820


# --- population ---------------------------------------------------------------------------

def load_signals(path: Path = LEDGER) -> tuple[list[dict], list[dict]]:
    """Population A (raw trigger, deduped) and B (PLACED subset).

    Dedupe is by (ts_et, verdict): the safe and bold accounts each evaluate the same tick and
    each write a row, so counting both would inflate n with copies of one signal -- a fake
    sample size, which is the exact failure the prereg's n-minimum exists to prevent.
    """
    seen: set[tuple] = set()
    pop_a: list[dict] = []
    pop_b: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue  # tolerate a crash-truncated line; never silently drop a whole file
            verdict = str(r.get("verdict") or "")
            if not verdict.startswith("ENTER"):
                continue
            ts, spy = r.get("ts_et"), r.get("spy")
            if not ts or not isinstance(spy, (int, float)):
                continue
            key = (ts, verdict)
            rec = {"ts_et": ts, "direction": "bull" if verdict.endswith("BULL") else "bear",
                   "spy": float(spy), "setup": r.get("setup"), "action": r.get("action")}
            if r.get("action") == "PLACED":
                pop_b.append(rec)
            if key in seen:
                continue
            seen.add(key)
            pop_a.append(rec)
    return pop_a, pop_b


# --- scoring ------------------------------------------------------------------------------

def _bar_index(bars: pd.DataFrame) -> dict:
    """ts (minute resolution, ET) -> positional index. The ledger stamps a signal at the tick
    that produced it, which is not necessarily a bar boundary; we snap to the bar the tick fell
    in and measure forward from ITS close. Never snap forward -- that would read a bar the
    signal could not have seen (C6)."""
    return {t.strftime("%Y-%m-%dT%H:%M"): i for i, t in enumerate(bars.index)}


def _snap(ts_et: str, idx: dict, bars: pd.DataFrame) -> int | None:
    """Find the bar containing this timestamp, searching BACKWARD only (up to 5 minutes)."""
    try:
        t = pd.Timestamp(ts_et)
    except ValueError:
        return None
    for back in range(0, 5):
        key = (t - pd.Timedelta(minutes=back)).strftime("%Y-%m-%dT%H:%M")
        if key in idx:
            return idx[key]
    return None


def forward_returns(entries: list[dict], bars: pd.DataFrame) -> list[dict]:
    """Signed forward return IN THE SIGNAL'S OWN DIRECTION. Positive = the trigger was right.
    Identical definition to multi-lane Stage A -- deliberately unchanged so the two runs are
    apples-to-apples."""
    idx = _bar_index(bars)
    closes = bars["close"].to_numpy()
    n = len(closes)
    out: list[dict] = []
    for e in entries:
        i = _snap(e["ts_et"], idx, bars)
        if i is None:
            continue
        entry_px = float(closes[i])
        if entry_px <= 0:
            continue
        rec = {"ts_et": e["ts_et"], "direction": e["direction"], "day": e["ts_et"][:10]}
        ok = False
        for h in HORIZONS:
            j = i + h
            if j >= n:
                rec[f"r{h}"] = None
                continue
            raw = (float(closes[j]) - entry_px) / entry_px
            rec[f"r{h}"] = raw if e["direction"] == "bull" else -raw
            ok = True
        if ok:
            out.append(rec)
    return out


def _mean(vals: list[float]) -> float | None:
    v = [x for x in vals if x is not None]
    return sum(v) / len(v) if v else None


def summarize(scored: list[dict]) -> dict:
    s: dict = {"n": len(scored)}
    for h in HORIZONS:
        vals = [r[f"r{h}"] for r in scored if r.get(f"r{h}") is not None]
        if not vals:
            s[f"h{h}"] = None
            continue
        hits = sum(1 for v in vals if v > 0)
        s[f"h{h}"] = {
            "n": len(vals),
            "mean_pct": round(100.0 * sum(vals) / len(vals), 5),
            "hit_rate_pct": round(100.0 * hits / len(vals), 2),
            "abs_mean_pct": round(100.0 * sum(abs(v) for v in vals) / len(vals), 5),
        }
    # C4: per-day dispersion alongside the pooled mean -- 33 days invites day-level clustering.
    by_day: dict[str, list[float]] = {}
    for r in scored:
        v = r.get(f"r{HEADLINE}")
        if v is not None:
            by_day.setdefault(r["day"], []).append(v)
    day_means = {d: round(100.0 * sum(v) / len(v), 4) for d, v in sorted(by_day.items())}
    s["per_day_headline_pct"] = day_means
    if day_means:
        pos = sum(1 for v in day_means.values() if v > 0)
        s["days_positive"] = f"{pos}/{len(day_means)}"
    return s


def random_null(scored: list[dict], bars: pd.DataFrame, draws: int = NULL_DRAWS) -> dict:
    """Same count, same direction mix, same session-bar population. Compared at MAX, never mean
    -- with 3 horizons examined, beating an average null is easy by chance."""
    rng = random.Random(SEED)
    n = len(scored)
    if n == 0:
        return {}
    dirs = [r["direction"] for r in scored]
    days = sorted({r["day"] for r in scored})
    day_set = set(days)
    # Only bars from the SAME sessions the signals came from.
    pool = [i for i, t in enumerate(bars.index) if t.strftime("%Y-%m-%d") in day_set]
    closes = bars["close"].to_numpy()
    total = len(closes)
    per_h: dict[int, list[float]] = {h: [] for h in HORIZONS}
    for _ in range(draws):
        picks = [rng.choice(pool) for _ in range(n)]
        rng.shuffle(dirs)
        for h in HORIZONS:
            vals = []
            for i, d in zip(picks, dirs):
                j = i + h
                if j >= total:
                    continue
                px = float(closes[i])
                if px <= 0:
                    continue
                raw = (float(closes[j]) - px) / px
                vals.append(raw if d == "bull" else -raw)
            if vals:
                per_h[h].append(sum(vals) / len(vals))
    out = {}
    for h in HORIZONS:
        v = per_h[h]
        if not v:
            continue
        v_sorted = sorted(v)
        out[f"h{h}"] = {
            "draws": len(v),
            "null_mean_pct": round(100.0 * sum(v) / len(v), 5),
            "null_max_pct": round(100.0 * v_sorted[-1], 5),
            "null_p95_pct": round(100.0 * v_sorted[int(0.95 * (len(v) - 1))], 5),
        }
    return out


def verdict_for(summary: dict, null: dict) -> dict:
    """Apply the frozen rule. Beat the null's MAX at the headline horizon, or it is a fail."""
    res = {}
    for h in HORIZONS:
        sh, nh = summary.get(f"h{h}"), null.get(f"h{h}")
        if not sh or not nh:
            res[f"h{h}"] = "NO_DATA"
            continue
        res[f"h{h}"] = "BEATS_NULL_MAX" if sh["mean_pct"] > nh["null_max_pct"] else "FAILS"
    return res


# --- main ---------------------------------------------------------------------------------

def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bars", type=int, default=6000, help="5-min SPY bars to fetch")
    args = ap.parse_args(argv)

    pop_a, pop_b = load_signals()
    print(f"[calib] population A (raw trigger, deduped): {len(pop_a)}")
    print(f"[calib] population B (PLACED):               {len(pop_b)}")
    if not pop_a:
        print("[calib] FATAL: no ENTER_* rows found -- refusing to report anything", file=sys.stderr)
        return 1

    params = json.loads((REPO / "automation" / "state" / "multi" / "params.json").read_text(encoding="utf-8"))
    c = mcreds.resolve(params)
    frames = mcore.fetch_bars_batch(c, ["SPY"], "5Min", limit=args.bars)
    bars = frames.get("SPY")
    if bars is None or bars.empty:
        print("[calib] FATAL: no SPY bars returned -- refusing to fabricate a result", file=sys.stderr)
        return 1
    print(f"[calib] SPY 5m bars: {len(bars)}  {bars.index[0]} -> {bars.index[-1]}")

    report: dict = {
        "prereg": "analysis/recommendations/prereg-spy-production-calibration-2026-08-20.json",
        "bars": {"n": len(bars), "first": str(bars.index[0]), "last": str(bars.index[-1])},
        "populations": {},
    }
    for label, pop in (("A_raw_trigger", pop_a), ("B_placed", pop_b)):
        scored = forward_returns(pop, bars)
        if not scored:
            report["populations"][label] = {"error": "no signals fell inside the fetched bar window"}
            print(f"[calib] {label}: NO OVERLAP with bar window", file=sys.stderr)
            continue
        summary = summarize(scored)
        null = random_null(scored, bars)
        report["populations"][label] = {
            "requested": len(pop), "scored": len(scored),
            "_coverage_note": (f"{len(scored)} of {len(pop)} signals fell inside the fetched "
                               f"5m bar window; the rest predate it and are EXCLUDED, not imputed"),
            "summary": summary, "null": null, "verdict": verdict_for(summary, null),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("\n" + "=" * 78)
    for label in ("A_raw_trigger", "B_placed"):
        p = report["populations"].get(label) or {}
        if "summary" not in p:
            print(f"{label}: {p.get('error')}")
            continue
        s, nl, v = p["summary"], p["null"], p["verdict"]
        print(f"\n{label}  (n={p['scored']} of {p['requested']} requested)")
        print(f"  {'horizon':<10}{'mean%':>11}{'hit%':>9}{'absMean%':>11}{'nullMAX%':>11}   gate")
        for h in HORIZONS:
            sh, nh = s.get(f"h{h}"), nl.get(f"h{h}")
            if not sh or not nh:
                continue
            star = " <-- headline" if h == HEADLINE else ""
            print(f"  +{h*5:<9}{sh['mean_pct']:>11.5f}{sh['hit_rate_pct']:>9.2f}"
                  f"{sh['abs_mean_pct']:>11.5f}{nh['null_max_pct']:>11.5f}   {v[f'h{h}']}{star}")
        print(f"  days positive: {s.get('days_positive')}")
    print("=" * 78)
    print(f"[calib] wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
