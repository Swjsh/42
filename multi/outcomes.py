"""multi/outcomes.py -- turn evaluation cards into EVIDENCE by stamping what happened next.

THE GAP THIS CLOSES. `multi/evaluate.py` writes a rich card for every ticker every 30 minutes:
zone map, structure, scores, named blockers, prospective trade. None of it carried an outcome.
A surface that records what it SAW but never what FOLLOWED is a dashboard, not a flywheel --
you can read it forever and learn nothing. This module reads the append-only card history and
stamps each card with what the underlying actually did at +10 / +30 / +60 minutes.

WHAT THAT BUYS. Every card already records the exact state that produced a decision -- bull and
bear scores, which named filters blocked, distance to the nearest zone in ATR, whether that zone
was a supply/demand shelf, the structure trend. Stamping outcomes onto that makes the accumulated
history answer questions no backtest can, because it is OUR live pipeline on OUR universe:

    * When bull score is 9 but F10:level_tied_trigger blocks, what does price do next?
      (i.e. is the blocker SAVING us or COSTING us? -- an unblockable question until now)
    * Do cards nearer a shelf resolve better than cards far from one?
    * Does the score have ANY monotone relationship with forward return on non-SPY names?

The last one is the live version of the null gate that killed this lane. If the score carries no
information here either, that accumulates as independent confirmation at zero risk. If it does,
that is the first honest evidence for arming -- earned forward, not fitted backward.

DELIBERATELY UNDERLYING-ONLY IN V1. The card's prospective trade carries a real contract and
premium, so option-level outcomes are tempting. They are also where intraday option data is
sparse (~20% of 5-minute intervals actually print), and forward-filling a sparse option series
fabricates a price path. Same staging that worked before: settle the SIGNAL question on the
underlying first; option expression is a separate stage with its own coverage disclosure.

NO LOOK-AHEAD, NO REWRITING. Cards are only stamped once they are old enough for the horizon to
have completed, outcomes are written to a SEPARATE file so the card history stays append-only
and immutable, and a card already stamped is never re-stamped.

READ-ONLY against the market. Places nothing, arms nothing.

Run:  backtest/.venv/Scripts/python.exe -m multi.outcomes
      backtest/.venv/Scripts/python.exe -m multi.outcomes --report-only
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi import core as mcore  # noqa: E402
from multi.lib import creds as mcreds  # noqa: E402

EVAL_DIR = REPO / "analysis" / "multi-lane" / "evaluations"
HISTORY = EVAL_DIR / "card-history.jsonl"
OUTCOMES = EVAL_DIR / "card-outcomes.jsonl"
REPORT = EVAL_DIR / "learning-report.json"
PARAMS = REPO / "automation" / "state" / "multi" / "params.json"

HORIZON_MIN = (10, 30, 60)
SETTLE_MIN = max(HORIZON_MIN) + 5      # a card is stampable only once its longest horizon closed


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate a crash-truncated tail line
    return out


def _key(card: dict) -> str:
    return f"{card.get('symbol')}|{card.get('as_of_et')}"


def stamp(cards: list[dict], bars_by_symbol: dict, now: dt.datetime) -> list[dict]:
    """Attach forward underlying returns. Only cards whose horizons have fully elapsed.

    The return is signed into the card's OWN directional lean so 'positive = the read was
    right' means the same thing on every row. Lean comes from the scores, which is what a human
    reading the card would act on; a card with no lean is recorded as flat and excluded from
    directional stats rather than silently counted as a win.
    """
    out = []
    for c in cards:
        ts = c.get("as_of_et")
        sym = c.get("symbol")
        spot = c.get("spot")
        if not ts or not sym or not isinstance(spot, (int, float)):
            continue
        try:
            t0 = dt.datetime.fromisoformat(ts)
        except ValueError:
            continue
        age_min = (now - t0).total_seconds() / 60.0
        if age_min < SETTLE_MIN:
            continue                      # not settled: stamping now would read an open window
        bars = bars_by_symbol.get(sym)
        if bars is None or bars.empty:
            continue

        setup = c.get("setup") or {}
        bull = (setup.get("bull") or {}).get("score")
        bear = (setup.get("bear") or {}).get("score")
        lean = None
        if isinstance(bull, (int, float)) and isinstance(bear, (int, float)):
            if bull > bear:
                lean = "bull"
            elif bear > bull:
                lean = "bear"

        rec = {
            "symbol": sym, "as_of_et": ts, "spot_at_card": float(spot),
            "verdict": c.get("verdict"),
            "bull_score": bull, "bear_score": bear, "lean": lean,
            "bull_blockers": (setup.get("bull") or {}).get("blockers") or [],
            "bear_blockers": (setup.get("bear") or {}).get("blockers") or [],
            "trend": (c.get("structure") or {}).get("trend"),
            "nearest_zone_atr": ((c.get("zones") or {}).get("nearest") or {}).get("distance_atr"),
            "nearest_is_shelf": ((c.get("zones") or {}).get("nearest") or {}).get("is_shelf"),
            "stamped_at_et": now.isoformat(timespec="seconds"),
        }

        idx = bars.index
        ok = False
        for h in HORIZON_MIN:
            target = t0 + dt.timedelta(minutes=h)
            after = idx[idx >= target]
            if len(after) == 0:
                rec[f"fwd_{h}m_pct"] = None
                continue
            px = float(bars.loc[after[0], "close"])
            raw = 100.0 * (px / float(spot) - 1.0)
            rec[f"fwd_{h}m_pct"] = round(raw, 4)
            rec[f"signed_{h}m_pct"] = (None if lean is None
                                       else round(raw if lean == "bull" else -raw, 4))
            ok = True
        if ok:
            out.append(rec)
    return out


def _stats(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0}
    n = len(vals)
    hits = sum(1 for v in vals if v > 0)
    hr = 100.0 * hits / n
    se = math.sqrt(0.25 / n) * 100.0
    return {"n": n, "hit_rate_pct": round(hr, 2),
            "sigma": round((hr - 50.0) / se, 2) if se else None,
            "mean_pct": round(sum(vals) / n, 4)}


def report(rows: list[dict]) -> dict:
    """The learning surface. Every cut carries its n, because a 63% hit rate on 8 rows is not a
    finding and must never be printed as though it were."""
    signed = [r for r in rows if r.get("signed_30m_pct") is not None]
    rep: dict = {
        "rows_total": len(rows),
        "rows_with_directional_lean": len(signed),
        "_reading": ("Every cut reports n. Nothing here is evidence until n is large and the "
                     "sigma is meaningful; these are OBSERVATIONS accumulating toward a "
                     "question, not a result. The lane remains STOPPED."),
        "overall": {f"{h}m": _stats([r[f"signed_{h}m_pct"] for r in signed
                                     if r.get(f"signed_{h}m_pct") is not None])
                    for h in HORIZON_MIN},
    }

    by_sym = defaultdict(list)
    for r in signed:
        if r.get("signed_30m_pct") is not None:
            by_sym[r["symbol"]].append(r["signed_30m_pct"])
    rep["by_symbol_30m"] = {k: _stats(v) for k, v in sorted(by_sym.items())}

    # THE question this file exists for: is a high score actually predictive on these names?
    by_score = defaultdict(list)
    for r in signed:
        s = r.get("bull_score") if r.get("lean") == "bull" else r.get("bear_score")
        if isinstance(s, (int, float)) and r.get("signed_30m_pct") is not None:
            by_score[int(s)].append(r["signed_30m_pct"])
    rep["by_lean_score_30m"] = {str(k): _stats(v) for k, v in sorted(by_score.items())}

    # Is a blocker saving us or costing us? Grouped by the blocker on the LEANING side.
    by_blocker = defaultdict(list)
    for r in signed:
        bl = r.get("bull_blockers") if r.get("lean") == "bull" else r.get("bear_blockers")
        if r.get("signed_30m_pct") is None:
            continue
        for b in (bl or []):
            by_blocker[b].append(r["signed_30m_pct"])
    rep["by_blocker_30m"] = {k: _stats(v) for k, v in
                             sorted(by_blocker.items(), key=lambda kv: -len(kv[1]))}

    shelf = [r["signed_30m_pct"] for r in signed
             if r.get("nearest_is_shelf") and r.get("signed_30m_pct") is not None]
    noshelf = [r["signed_30m_pct"] for r in signed
               if r.get("nearest_is_shelf") is False and r.get("signed_30m_pct") is not None]
    rep["shelf_vs_not_30m"] = {"nearest_is_shelf": _stats(shelf), "not_a_shelf": _stats(noshelf)}
    return rep


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report-only", action="store_true", help="re-report without stamping")
    args = ap.parse_args(argv)

    cards = _read_jsonl(HISTORY)
    existing = _read_jsonl(OUTCOMES)
    done = {f"{r.get('symbol')}|{r.get('as_of_et')}" for r in existing}
    print(f"[outcomes] cards in history: {len(cards)}   already stamped: {len(done)}")

    if not args.report_only:
        pending = [c for c in cards if _key(c) not in done]
        if pending:
            symbols = sorted({c.get("symbol") for c in pending if c.get("symbol")})
            params = json.loads(PARAMS.read_text(encoding="utf-8"))
            cr = mcreds.resolve(params)
            bars = mcore.fetch_bars_batch(cr, symbols, "5Min", limit=600)
            new = stamp(pending, bars, mcore.now_et())
            if new:
                OUTCOMES.parent.mkdir(parents=True, exist_ok=True)
                with OUTCOMES.open("a", encoding="utf-8") as fh:
                    for r in new:
                        fh.write(json.dumps(r, default=str) + "\n")
            unsettled = len(pending) - len(new)
            print(f"[outcomes] newly stamped: {len(new)}"
                  f"   still unsettled (< {SETTLE_MIN} min old): {unsettled}")
            existing = existing + new
        else:
            print("[outcomes] nothing pending")

    rep = report(existing)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")

    print("\n" + "=" * 74)
    print(f"LEARNING REPORT -- {rep['rows_total']} stamped cards "
          f"({rep['rows_with_directional_lean']} with a directional lean)")
    for h in HORIZON_MIN:
        s = rep["overall"].get(f"{h}m") or {}
        if s.get("n"):
            print(f"  +{h:>2}m  n={s['n']:<5} hit={s['hit_rate_pct']}%  "
                  f"sigma={s['sigma']}  mean={s['mean_pct']}%")
    if rep["by_lean_score_30m"]:
        print("\n  by lean score @30m (is a higher score actually better?)")
        for k, s in rep["by_lean_score_30m"].items():
            if s.get("n"):
                print(f"    score {k:>2}: n={s['n']:<5} hit={s['hit_rate_pct']}%  mean={s['mean_pct']}%")
    if rep["by_blocker_30m"]:
        print("\n  by blocker @30m (did the block SAVE us or COST us?)")
        for k, s in list(rep["by_blocker_30m"].items())[:6]:
            if s.get("n"):
                print(f"    {k:<26} n={s['n']:<5} hit={s['hit_rate_pct']}%  mean={s['mean_pct']}%")
    print("=" * 74)
    print(f"  {rep['_reading']}")
    print(f"[outcomes] wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
