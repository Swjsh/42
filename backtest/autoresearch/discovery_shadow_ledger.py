"""discovery_shadow_ledger.py — the DISCOVERY engine (J's "$100K x all strategies x long
and short the same trade, just document what works" — executed as a free shadow ledger).

WHY A LEDGER, NOT ORDERS (swarm 9/10): literally placing long+short the same 0DTE bleeds two
spreads + theta on both legs — a money-loser by construction. Shadow-logging what BOTH
directions WOULD have done (forward price, multiple stops) is free, zero-risk, and turns
EVERY detected setup into TWO clean data points. This is the EXPLORE engine; the design-swarm
+ this file's FDR screen are the validator; the $2K production fleet is the exploit engine.
Kept SEPARATE from the $2K accounts on purpose ($100K paper dynamics don't transfer).

DISCLOSURE: forward SPY-move-with-stop is a DIRECTION proxy (ranking-only, C1) — the option
P&L of survivors is confirmed by the design-swarm on real OPRA fills. Multiple-comparisons:
with many (setup x direction x stop x regime) groups, something looks great by luck, so the
screen applies a Benjamini-Hochberg FDR correction before anything is called an edge.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
import datetime as dt
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for _s in ("stdout", "stderr"):
    try: getattr(sys, _s).reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "backtest"))
from backtest.lib.orchestrator import run_backtest, _params_to_kwargs  # noqa: E402

DATA = REPO / "backtest" / "data"
OUT = REPO / "analysis" / "discovery"
LEDGER = OUT / "shadow-ledger.jsonl"
PARAMS = json.loads((REPO / "automation/state/params.json").read_text(encoding="utf-8"))

STOPS_PCT = [0.0015, 0.0030, 0.0060]   # SPY-move stop levels (0.15% / 0.30% / 0.60%)
MAX_FWD_BARS = 18                       # ~90 min forward horizon (0DTE intraday)


def _forward(closes, highs, lows, i, side, stop_pct):
    """Outcome of entering at close[i] going `side`, with a stop_pct adverse move, else the
    move at MAX_FWD_BARS or EOD. Returns signed % captured (positive = winning direction)."""
    entry = closes[i]
    end = min(i + MAX_FWD_BARS, len(closes) - 1)
    for j in range(i + 1, end + 1):
        if side == "long":
            if (entry - lows[j]) / entry >= stop_pct:   # adverse = down
                return -stop_pct * 100
            if j == end:
                return (closes[j] - entry) / entry * 100
        else:  # short
            if (highs[j] - entry) / entry >= stop_pct:  # adverse = up
                return -stop_pct * 100
            if j == end:
                return (entry - closes[j]) / entry * 100
    return 0.0


def generate(start="2025-07-01", end="2026-06-18") -> dict:
    spy = pd.read_csv(DATA / "spy_5m_2025-01-01_2026-06-18.csv")
    vix = pd.read_csv(DATA / "vix_5m_2025-01-01_2026-06-18.csv")
    spy = spy[(spy["timestamp_et"] >= start) & (spy["timestamp_et"] < end + "T23:59")].reset_index(drop=True)
    vix = vix[(vix["timestamp_et"] >= start) & (vix["timestamp_et"] < end + "T23:59")].reset_index(drop=True)

    # Run the engine to get per-bar DETECTED setups (triggers_fired) — "all strategies" = every
    # setup the engine recognizes, both directions logged regardless of which side it picked.
    kwargs = _params_to_kwargs(PARAMS, account_equity=2000.0)
    kwargs["disable_filters"] = list(range(1, 12))   # detector-only: see every setup, gate nothing
    res = run_backtest(spy, vix, start_date=dt.date.fromisoformat(start), end_date=dt.date.fromisoformat(end),
                       use_real_fills=False, **kwargs)

    spy["date"] = spy["timestamp_et"].str[:10]; spy["hm"] = spy["timestamp_et"].str[11:16]
    by_day = {d: g.reset_index(drop=True) for d, g in spy.groupby("date")}

    OUT.mkdir(parents=True, exist_ok=True)
    rows = 0
    with LEDGER.open("w", encoding="utf-8") as fh:
        for dec in res.decisions:
            ts = str(dec.get("timestamp_et", "")); date, hm = ts[:10], ts[11:16]
            trig = dec.get("triggers_fired") or []
            if not trig or not ("09:35" <= hm <= "14:30"):
                continue
            g = by_day.get(date)
            if g is None: continue
            sub = g[g["hm"] >= hm]
            if len(sub) < 4: continue
            closes = sub["close"].astype(float).tolist(); highs = sub["high"].astype(float).tolist(); lows = sub["low"].astype(float).tolist()
            vixv = float(dec.get("vix", 0) or 0)
            regime = "vix_hi" if vixv >= 18 else "vix_lo"
            tod = "open" if hm < "10:30" else ("mid" if hm < "13:00" else "pm")
            setup = "+".join(sorted(t for t in trig if isinstance(t, str)))[:40] or "any"
            for side in ("long", "short"):
                for stop in STOPS_PCT:
                    out = _forward(closes, highs, lows, 0, side, stop)
                    fh.write(json.dumps({"date": date, "hm": hm, "setup": setup, "direction": side,
                                         "stop_pct": stop, "regime": regime, "tod": tod,
                                         "fwd_pct": round(out, 4)}) + "\n")
                    rows += 1
    return {"ledger_rows": rows, "ledger": str(LEDGER), "window": f"{start}..{end}"}


def fdr_screen(alpha=0.10) -> dict:
    """Group the ledger by (setup, direction, stop, regime); test mean forward move > 0;
    apply Benjamini-Hochberg FDR across all groups. Survivors = candidate edges to hand the
    design-swarm for real-fills confirmation."""
    import math
    if not LEDGER.exists():
        return {"error": "no ledger — run generate() first"}
    groups = {}
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        r = json.loads(line)
        k = (r["setup"], r["direction"], r["stop_pct"], r["regime"])
        groups.setdefault(k, []).append(r["fwd_pct"])
    tested = []
    for k, xs in groups.items():
        n = len(xs)
        if n < 30: continue                       # need a real sample
        mean = sum(xs) / n
        sd = (sum((x - mean) ** 2 for x in xs) / (n - 1)) ** 0.5 if n > 1 else 0
        if sd == 0: continue
        t = mean / (sd / math.sqrt(n))
        # one-sided normal-approx p for mean>0
        p = 0.5 * math.erfc(t / math.sqrt(2))
        tested.append({"group": k, "n": n, "mean_fwd": round(mean, 4), "t": round(t, 2), "p": p})
    # Benjamini-Hochberg
    tested.sort(key=lambda d: d["p"])
    m = len(tested); survivors = []
    for i, d in enumerate(tested, 1):
        d["bh_threshold"] = round(alpha * i / m, 5) if m else 0
        d["significant"] = d["p"] <= (alpha * i / m if m else 0)
    # the largest i meeting p<=alpha*i/m makes all up to i significant (BH step-up)
    sig_cut = max([i for i, d in enumerate(tested, 1) if d["p"] <= (alpha * i / m if m else 0)], default=0)
    for i, d in enumerate(tested, 1):
        d["significant"] = i <= sig_cut
        if d["significant"] and d["mean_fwd"] > 0:
            survivors.append(d)
    out = {"groups_tested": m, "fdr_alpha": alpha, "survivors": survivors[:30],
           "n_survivors": len(survivors)}
    (OUT / "fdr-screen.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--screen-only", action="store_true")
    args = ap.parse_args()
    if not args.screen_only:
        g = generate(); print("[discovery] ", json.dumps(g))
    s = fdr_screen()
    print(f"\n=== DISCOVERY FDR SCREEN ({s.get('groups_tested')} groups, alpha={s.get('fdr_alpha')}) ===")
    print(f"survivors (FDR-significant, positive forward edge): {s.get('n_survivors')}")
    for d in s.get("survivors", [])[:15]:
        setup, side, stop, regime = d["group"]
        print(f"  {setup[:30]:32} {side:5} stop={stop} {regime:7} n={d['n']:4} mean_fwd={d['mean_fwd']:+.3f}% p={d['p']:.4f}")
    print("\nSurvivors = candidate edges -> hand to design-swarm for real-OPRA-fills confirmation.")
