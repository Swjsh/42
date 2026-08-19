"""RUN the which-Friday expiry experiment, under the frozen pre-registration.

Prereg: analysis/recommendations/prereg-weekly-expiry-comparison-2026-08-18.json
Program doc: markdown/planning/WEEKLY-OPTIONS-PROGRAM.md §9b phase 6
J's ask, verbatim: "which Friday, one week or two week out, which expiration was better."

DESIGN (all of it fixed by the prereg BEFORE any result was seen):
  * PAIRED / within-subject. Every signal opens one position in EACH arm from the same
    underlying, same direction, same session. The only difference is the contract, so the
    contrast is not confounded by which signals an arm happened to catch.
  * DELTA-MATCHED strikes (option_iv_solve), not strike-matched -- the same strike is a
    different delta at different DTE.
  * EQUAL DOLLAR RISK per arm. Longer-DTE contracts cost more; a fixed contract count would
    silently compare different risk sizes and hand the win to the cheapest arm as a pure
    leverage artifact. This is the prereg's named #1 confound.
  * Primary metric = % return on premium, NOT win rate (the edge is a right tail).
  * Every row carries its data-completeness and modeling disclosures.

Reads only cached data + the frozen signal list. Places no orders. Writes one JSONL ledger
plus a summary; the STATISTICS are computed by the sibling reporter, not here -- this file
produces observations, it does not decide anything.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest" / "lib", REPO / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import multiday_walk as mw  # noqa: E402
import option_iv_solve as ivs  # noqa: E402
from weekly_fill_model import DEFAULT_SPREAD_PCT  # noqa: E402

DATA_ROOT = REPO / "backtest" / "data" / "weekly-options"
SIGNALS = REPO / "analysis" / "weekly-lane" / "signal-density-probe.json"
PARAMS = REPO / "automation" / "state" / "weekly" / "params.json"
OUT_DIR = REPO / "analysis" / "weekly-lane"
LEDGER = REPO / "automation" / "state" / "weekly" / "expiry-experiment-shadow-ledger.jsonl"

# Arms, exactly as frozen in the prereg. MONTHLY is a descriptive control.
ARMS = ("SAME_WEEK", "NEXT_WEEK", "TWO_WEEKS_OUT", "MONTHLY")
_MONTHLY_TARGET_DTE = 30
_MONTHLY_TOL = 7
TARGET_DELTA = 0.50           # midpoint of params entry.target_delta_min/max (0.40-0.70)
RISK_BUDGET_DOLLARS = 1500.0  # 30% of a $5,000 account -- identical for every arm
RATE = 0.036                  # Fed funds 3.50-3.75% as of 2026-08-18
DIV_YIELD = {"QQQ": 0.005, "GLD": 0.0}

_OCC = re.compile(r"^(?P<root>[A-Z]+)(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<right>[CP])(?P<strike>\d{8})$")


class ExperimentError(RuntimeError):
    """Fail loud rather than emit a partial ledger that looks like a complete run."""


def parse_occ(sym: str) -> dict | None:
    m = _OCC.match(sym)
    if not m:
        return None
    g = m.groupdict()
    return {
        "contract": sym,
        "root": g["root"],
        "expiry": dt.date(2000 + int(g["yy"]), int(g["mm"]), int(g["dd"])),
        "right": g["right"],
        "strike": int(g["strike"]) / 1000.0,
    }


def build_index(root: str) -> dict:
    """expiry -> right -> [contract meta]. Built from FILENAMES only (no file reads)."""
    d = DATA_ROOT / root
    if not d.exists():
        raise ExperimentError(f"no cached option data for {root} at {d}")
    idx: dict = defaultdict(lambda: defaultdict(list))
    for p in d.glob("*.csv"):
        meta = parse_occ(p.stem)
        if meta:
            idx[meta["expiry"]][meta["right"]].append(meta)
    if not idx:
        raise ExperimentError(f"{root}: cache directory exists but holds no parseable contracts")
    return idx


_BARS_CACHE: dict[str, list[mw.SessionBar]] = {}


def contract_bars(root: str, contract: str) -> list[mw.SessionBar]:
    if contract not in _BARS_CACHE:
        try:
            _BARS_CACHE[contract] = mw.load_contract_bars(contract, root)
        except mw.WalkError:
            _BARS_CACHE[contract] = []
    return _BARS_CACHE[contract]


def price_on(root: str, contract: str, session: dt.date) -> float | None:
    for b in contract_bars(root, contract):
        if b.date_et == session:
            return b.close
    return None


def select_expiry(rule: str, available: list[dt.date], as_of: dt.date, min_dte: int) -> dict | None:
    """Pure selection over the LIVE list of listed expiries (never a computed calendar Friday --
    NVDA's 2026-08-26 expiry is unlisted because earnings land that day)."""
    eligible = sorted(e for e in available if (e - as_of).days >= min_dte)
    if not eligible:
        return None
    fridays = [e for e in eligible if e.weekday() == 4]
    fallback = False
    if rule == "MONTHLY":
        best = min(eligible, key=lambda e: abs((e - as_of).days - _MONTHLY_TARGET_DTE))
        if abs((best - as_of).days - _MONTHLY_TARGET_DTE) > _MONTHLY_TOL:
            return None
        chosen = best
    else:
        n = {"SAME_WEEK": 0, "NEXT_WEEK": 1, "TWO_WEEKS_OUT": 2}[rule]
        pool = fridays or eligible
        if len(pool) <= n:
            return None
        chosen = pool[n]
        if not fridays:
            fallback = True
    return {"expiry": chosen, "dte": (chosen - as_of).days, "rule": rule, "fallback": fallback}


def run(symbols: list[str], params: dict, spread_pct: float) -> tuple[list[dict], dict]:
    sig_doc = json.loads(SIGNALS.read_text(encoding="utf-8"))
    min_dte = int(params["entry"]["min_dte_at_entry"])
    shape = params["exits"]

    rows: list[dict] = []
    stats: dict = defaultdict(int)

    for per_sym in sig_doc["per_symbol"]:
        sym = per_sym["symbol"]
        if sym not in symbols:
            continue
        idx = build_index(sym)
        expiries = sorted(idx)
        # Underlying close per session, from the option cache's own underlying-free view is not
        # available -- use the signal's recorded close as spot at entry, and skip the
        # thesis-progress path (theta budget then treats progress as zero = conservative).
        for s in per_sym["signals"]:
            entry_session = dt.date.fromisoformat(s["session"])
            spot = float(s["close"])
            right = "C" if s["direction"] == "bullish" else "P"
            stats["signals_seen"] += 1

            arm_results = {}
            for rule in ARMS:
                sel = select_expiry(rule, expiries, entry_session, min_dte)
                if sel is None:
                    stats[f"skip_no_expiry_{rule}"] += 1
                    continue
                cands = []
                for meta in idx[sel["expiry"]][right]:
                    px = price_on(sym, meta["contract"], entry_session)
                    if px and px > 0:
                        cands.append({"strike": meta["strike"], "price": px,
                                      "contract": meta["contract"]})
                if not cands:
                    stats[f"skip_no_prices_{rule}"] += 1
                    continue
                t_years = max(sel["dte"], 1) / 365.0
                pick = ivs.pick_delta_matched(
                    cands, TARGET_DELTA, spot=spot, t_years=t_years, right=right,
                    rate=RATE, div_yield=DIV_YIELD.get(sym, 0.0),
                )
                if pick is None:
                    stats[f"skip_no_solvable_{rule}"] += 1
                    continue
                # EQUAL DOLLAR RISK across arms -- the prereg's #1 confound control.
                qty = max(1, int(RISK_BUDGET_DOLLARS // (pick["price"] * 100.0)))
                bars = contract_bars(sym, pick["contract"])
                if not bars:
                    stats[f"skip_no_bars_{rule}"] += 1
                    continue
                pos = mw.MultiDayPosition(
                    contract=pick["contract"], symbol=sym, side=right,
                    entry_date=entry_session, entry_mid=pick["price"], qty=qty,
                    expiry=sel["expiry"], zone_width=float(s["zone_width"]),
                    entry_underlying=spot,
                )
                try:
                    res = mw.walk(pos, bars, shape, spread_pct=spread_pct, params=params)
                except (mw.WalkError, ValueError) as e:
                    stats[f"skip_walk_error_{rule}"] += 1
                    stats["walk_errors"] += 1
                    _ = e
                    continue
                arm_results[rule] = {
                    **res.as_row(),
                    "arm": rule, "dte_at_entry": sel["dte"],
                    "expiry": sel["expiry"].isoformat(),
                    "strike": pick["strike"], "delta": round(pick["delta"], 4),
                    "implied_vol": round(pick["implied_vol"], 4),
                    "delta_err": round(pick["delta_err"], 4),
                    "qty": qty, "expiry_fallback": sel["fallback"],
                    "candidates_considered": pick.get("candidates_considered"),
                    "candidates_skipped_unsolvable": pick.get("candidates_skipped_unsolvable"),
                }

            # PAIRING: only keep signals where the three weekly arms ALL produced a position.
            # A signal present in some arms but not others would bias the comparison toward
            # whichever arm happens to have data more often.
            core = ("SAME_WEEK", "NEXT_WEEK", "TWO_WEEKS_OUT")
            if all(a in arm_results for a in core):
                stats["paired_signals"] += 1
                for rule, r in arm_results.items():
                    rows.append({
                        "signal_session": s["session"], "symbol": sym,
                        "direction": s["direction"], "zone_family": s["zone_family"],
                        "confluence": s["confluence"], "spot_at_entry": spot,
                        **r,
                    })
            else:
                stats["unpaired_signals_dropped"] += 1

    return rows, dict(stats)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--spread-pct", type=float, default=DEFAULT_SPREAD_PCT)
    args = ap.parse_args(argv)

    params = json.loads(PARAMS.read_text(encoding="utf-8"))
    symbols = ([s.strip().upper() for s in args.symbols.split(",")]
               if args.symbols else list(params["universe"]["active"]))

    rows, stats = run(symbols, params, args.spread_pct)
    if not rows:
        print("ERROR: zero paired observations produced. That is a finding (the arms never "
              "co-occur on the cached data), not a successful run.", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")

    per_arm = defaultdict(list)
    for r in rows:
        per_arm[r["arm"]].append(r)
    summary = {
        "experiment": "weekly_expiry_comparison",
        "prereg": "analysis/recommendations/prereg-weekly-expiry-comparison-2026-08-18.json",
        "spread_pct_assumed": args.spread_pct,
        "symbols": symbols,
        "selection_stats": stats,
        "paired_signals": stats.get("paired_signals", 0),
        "min_pairs_required": 30,
        "per_arm_n": {a: len(v) for a, v in sorted(per_arm.items())},
        "_note": "Statistics are computed by weekly_expiry_experiment_report.py, not here.",
    }
    (OUT_DIR / "expiry-experiment-raw.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print(f"paired signals: {stats.get('paired_signals', 0)} "
          f"(dropped unpaired: {stats.get('unpaired_signals_dropped', 0)})", file=sys.stderr)
    print(f"rows per arm: {summary['per_arm_n']}", file=sys.stderr)
    print(f"wrote {LEDGER} and {OUT_DIR / 'expiry-experiment-raw.json'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
