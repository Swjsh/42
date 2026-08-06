"""stop_width_population_grid.py -- the HONEST GENERALIZATION of the 08-05 stop-width question.

A stop width that wins on one day and loses over the population is not a fix. This runs a
stop-width grid over the FULL real-fill population and splits the result by day-archetype so
the regime-conditionality is visible instead of averaged away.

WHAT IS VARIED, AND WHAT IS HELD FIXED
    ONLY `premium_stop_pct`. Every other exit knob is pinned to one BASELINE shape
    (TP1 +30% on 0.8 of the lot, fixed profit-lock, 15:50 time stop) so the grid isolates
    the stop-width axis. The exits are computed by the LIVE decision core --
    `exit_manager.plan_exit_actions`, driven through `exit_shape_parity_study.replay_position`
    -- not by a hand-rolled loop.

    FIRST DRAFT OF THIS TOOL DID hand-roll the loop, with no TP1 and no runner. Every winner
    then rode to the 15:50 flatten and the "-6% live" cell printed +$12,115 against a
    broker-truth +$317 -- a 38x artifact. That is why the live core is used here. Recorded
    so the next reader does not re-make it.

SEQUENTIAL, NEVER RECOMBINED
    Positions are grouped into WAVES = (arm, date, symbol). 43% of this population sits
    inside a multi-entry wave, so re-pricing positions independently and summing would
    misprice nearly half of it. Inside a wave the simulation holds ONE position at a time:
    a wider stop still holding at the next observed entry time SUPPRESSES that re-entry.
    Re-entry candidates are the wave's OWN observed entry timestamps -- the study never
    invents an entry the engine did not actually take.

    DISCLOSED CONSERVATISM: if a wider stop exits AFTER the wave's last observed entry, that
    re-entry is lost rather than shifted later, so wide stops take FEWER trades than live.
    On a population whose repeat entries were mostly losers this flatters wide stops. The
    single-entry sub-population (no re-entry interaction at all) is therefore reported
    separately as the clean, unconfounded read.

WHAT THIS DOES NOT MODEL (inherited, disclosed -- same limitation as exit_shape_parity_study)
    Chart-stop / ribbon-flip-back invalidation is NOT reconstructed (`ribbon_flip_back=False`
    always). On the live arms that run chart-stop-primary, the modelled baseline will
    therefore differ from broker-truth in ABSOLUTE dollars. The deliverable is the RANKING
    of stop widths under identical other-assumptions, not an absolute P&L forecast. The
    model-vs-actual gap is printed, never hidden.

PRICES: real Alpaca OPRA 1-min bars (/v1beta1/options/bars). Entries use the REAL broker
fill price. NO ORACLE COLUMNS.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import exit_shape_parity_study as esp  # noqa: E402
import fleet_broker as fb  # noqa: E402

CACHE = REPO / "backtest" / "data" / "opra_1m_cache"
ARCHETYPES = REPO / "analysis" / "regime-library" / "day-archetypes.json"

BASELINE_SHAPE = {"tp1_premium_pct": 0.30, "tp1_qty_fraction": 0.8,
                  "profit_lock_mode": "fixed"}

STOP_WIDTHS = [
    ("-6%", -0.06), ("-10%", -0.10), ("-12%", -0.12), ("-15%", -0.15),
    ("-20%", -0.20), ("-25%", -0.25), ("-50% catastrophe-only", -0.50),
]

TREND_LIKE = {"trend-up", "trend-down", "gap-go"}
CHOP_LIKE = {"range-chop", "pin-day", "gap-fade", "V-reversal", "inverted-V"}


def _creds() -> dict:
    allc = fb.load_creds()
    for arm in ("risky-1", "risky-3", "safe-2", "bold-2", "safe-3"):
        c = allc.get(arm)
        if not c:
            continue
        a = fb.get_account(c)
        if isinstance(a, dict) and a and not a.get("_error"):
            return c
    raise RuntimeError("no live arm creds for market data")


def get_bars(symbol: str, date: str, creds: dict) -> list[dict]:
    """Real OPRA 1-min bars, disk-cached, in exit_shape_parity_study's expected shape."""
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{symbol}_{date}.csv"
    if not p.exists():
        url = ("https://data.alpaca.markets/v1beta1/options/bars"
               f"?symbols={symbol}&timeframe=1Min&start={date}T13:00:00Z"
               f"&end={date}T20:15:00Z&limit=10000")
        req = urllib.request.Request(url, headers={
            "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                bars = (json.loads(r.read().decode()).get("bars") or {}).get(symbol) or []
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                ConnectionError, ValueError) as exc:
            print(f"  [warn] bar fetch failed {symbol} {date}: {exc}", file=sys.stderr)
            bars = []
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["t", "o", "h", "l", "c", "v"])
            for b in bars:
                w.writerow([b["t"], b["o"], b["h"], b["l"], b["c"], b.get("v", 0)])
        time.sleep(0.12)
    out = []
    with p.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append({"t": r["t"], "o": float(r["o"]), "h": float(r["h"]),
                        "l": float(r["l"]), "c": float(r["c"])})
    return out


def simulate_wave(wave: list[dict], bars: list[dict], width: float) -> dict:
    """Sequential replay of ONE (arm,date,symbol) wave: one position at a time, using the
    LIVE plan_exit_actions core. A position still open at the next observed entry time
    suppresses that re-entry."""
    shape = dict(BASELINE_SHAPE, premium_stop_pct=width)
    ordered = sorted(wave, key=lambda p: p["entry_ts_utc"])
    total, legs, n = 0.0, [], 0
    flat_after = ""
    for pos in ordered:
        if pos["entry_ts_utc"] < flat_after:
            continue                      # suppressed: still holding at this entry time
        r = esp.replay_position(pos, bars, shape)
        if r.get("pnl") is None:
            continue
        total += r["pnl"]
        n += 1
        exits = r.get("exits") or []
        flat_after = exits[-1]["ts_utc"] if exits else pos["entry_ts_utc"]
        legs.append({"entry_ts": pos["entry_ts_utc"], "qty": pos["entry_qty"],
                     "entry_px": pos["entry_price"], "pnl": r["pnl"],
                     "stages": [e["stage"] for e in exits]})
    return {"pnl": round(total, 2), "n_entries": n, "legs": legs}


def agg(rows: list, pred=None) -> dict:
    sel = [r for r in rows if pred is None or pred(r)]
    if not sel:
        return {"n_waves": 0, "total_pnl": 0.0, "actual_pnl": 0.0,
                "delta_vs_actual": 0.0, "win_rate": None}
    tot = sum(r["model"] for r in sel)
    act = sum(r["actual"] for r in sel)
    wins = sum(1 for r in sel if r["model"] > 0)
    return {"n_waves": len(sel), "total_pnl": round(tot, 2), "actual_pnl": round(act, 2),
            "delta_vs_actual": round(tot - act, 2), "win_rate": round(wins / len(sel), 3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    arche = json.loads(ARCHETYPES.read_text(encoding="utf-8"))["days"]
    creds = _creds()
    positions = esp.reconstruct_positions(
        esp.load_fleet_engine_fills(arms=esp.ALL_LIVE_ARMS))

    waves: dict[tuple, list[dict]] = defaultdict(list)
    for p in positions:
        waves[(p["arm"], p["date_et"], p["symbol"])].append(p)
    actual_total = sum(p["actual_exit_pnl"] for p in positions)
    print(f"population: {len(positions)} positions / {len(waves)} waves / "
          f"{len(set(k[1] for k in waves))} days / broker-truth {actual_total:+.2f}")

    per_cell: dict[str, list] = {lab: [] for lab, _ in STOP_WIDTHS}
    wave_rows, skipped = [], 0
    for i, (key, wave) in enumerate(sorted(waves.items()), 1):
        arm, date, symbol = key
        bars = get_bars(symbol, date, creds)
        if len(bars) < 30:
            skipped += 1
            continue
        actual = sum(p["actual_exit_pnl"] for p in wave)
        a = (arche.get(date) or {}).get("archetype", "unknown")
        row = {"arm": arm, "date": date, "symbol": symbol, "n_positions": len(wave),
               "archetype": a, "actual_pnl": round(actual, 2), "cells": {}}
        for lab, w in STOP_WIDTHS:
            r = simulate_wave(wave, bars, w)
            row["cells"][lab] = {"pnl": r["pnl"], "n_entries": r["n_entries"]}
            per_cell[lab].append({"key": key, "model": r["pnl"], "actual": actual,
                                  "n_pos": len(wave), "n_entries": r["n_entries"],
                                  "arche": a})
        wave_rows.append(row)
        if i % 25 == 0:
            print(f"  ...{i}/{len(waves)}")

    report = {
        "population": {"positions": len(positions), "waves": len(waves),
                       "waves_skipped_no_bars": skipped,
                       "days": sorted(set(k[1] for k in waves)),
                       "actual_total_pnl": round(actual_total, 2)},
        "method": {"varied": "premium_stop_pct only", "baseline_shape": BASELINE_SHAPE,
                   "core": "exit_manager.plan_exit_actions (LIVE decision core)",
                   "sequential": True, "entry_prices": "REAL broker fills",
                   "not_modeled": "chart-stop / ribbon_flip_back invalidation"},
        "cells": {}, "by_archetype": {}, "waves": wave_rows,
    }

    hdr = (f"\n{'cell':<24s}{'ALL':>10s}{'single':>10s}{'multi':>10s}"
           f"{'trend':>10s}{'chop':>10s}{'trades':>8s}{'WR':>7s}")
    print(hdr)
    for lab, _ in STOP_WIDTHS:
        rows = per_cell[lab]
        allr = agg(rows)
        cells = {
            "all": allr,
            "single_entry": agg(rows, lambda r: r["n_pos"] == 1),
            "multi_entry": agg(rows, lambda r: r["n_pos"] > 1),
            "trend_like": agg(rows, lambda r: r["arche"] in TREND_LIKE),
            "chop_like": agg(rows, lambda r: r["arche"] in CHOP_LIKE),
        }
        report["cells"][lab] = cells
        report["by_archetype"][lab] = {
            a: agg(rows, lambda r, a=a: r["arche"] == a)
            for a in sorted(set(r["arche"] for r in rows))}
        trades = sum(r["n_entries"] for r in rows)
        print(f"{lab:<24s}{cells['all']['total_pnl']:>+10.0f}"
              f"{cells['single_entry']['total_pnl']:>+10.0f}"
              f"{cells['multi_entry']['total_pnl']:>+10.0f}"
              f"{cells['trend_like']['total_pnl']:>+10.0f}"
              f"{cells['chop_like']['total_pnl']:>+10.0f}{trades:>8d}"
              f"{allr['win_rate']:>7.2f}")
    print(f"{'ACTUAL (broker truth)':<24s}{actual_total:>+10.0f}")

    Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nwrote {args.out}  (skipped {skipped} waves for missing bars)")


if __name__ == "__main__":
    main()
