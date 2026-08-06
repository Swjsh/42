"""stop_width_grid_20260805.py -- SEQUENTIAL stop-width counterfactual on REAL OPRA.

LENS 1 of the 2026-08-05 EOD audit. Answers J's literal question: "were they good
trades, and would a wider stop have saved them?" -- with a number, not an opinion.

WHY SEQUENTIAL (the thing this repo has been burned by twice)
------------------------------------------------------------
You cannot price a stop-width change by re-pricing each of the five 776C round trips
independently and summing. A wider stop keeps you IN the position, which SUPPRESSES the
later re-entries -- you cannot be stopped out and re-enter if you are still holding.
So the simulation walks the session ONE POSITION AT A TIME and only re-enters when
(a) it is flat and (b) the engine's OWN signal was live on that minute.

SIGNAL AVAILABILITY IS TAKEN FROM THE ENGINE'S OWN LEDGER, NOT INVENTED
----------------------------------------------------------------------
`automation/state/fleet/<arm>/decisions.jsonl` records, for every 1-minute tick:
  * action=ENTER_BULL/ENTER_BEAR  -> strategy fired AND the arm was flat  -> entered
  * risk_code=NOT_FLAT            -> strategy fired but a position was already open
  * reason="no qualifying setup"  -> strategy genuinely did not fire
The union of the first two is the minute-set on which the engine WOULD have entered had
it been flat. That series is observed independently of our counterfactual position state
(the ledger carries both fired and not-fired rows while non-flat), so re-using it is not
look-ahead -- it is the engine's own live opinion, minute by minute.

PRICE SERIES: ENGINE-OBSERVED BID FIRST, REAL OPRA SECOND
---------------------------------------------------------
The live exit pass runs at ~:04-:07s of each minute and compares `worst_premium` (the
BID) to the stop. Those exact quotes are in the ledger whenever ANY arm held the
contract -- that is broker-truth at the exact sample instant, better than any bar proxy.
Priority per minute:
  1. `exit_pass[].worst_premium`  (engine-observed bid, exact)
  2. `premium` on an ENTER/NOT_FLAT row minus half-spread   (engine-observed mid)
  3. real OPRA 1-min `close(m-1) + PROXY_BIAS`              (fitted fallback)
PROXY_BIAS and the fill offsets below were FITTED on the 14 minutes where the ledger and
the OPRA cache overlap (mean -0.026, sd 0.058) -- see `--calibrate`. Cells that depend
mostly on tier-3 fallback carry that sd as an explicit uncertainty band.

Every cell is live-executable: the stop level is known at entry and the re-entry minutes
come from the engine's own contemporaneous signal. NO ORACLE COLUMNS.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HIRES = ROOT / "backtest" / "data" / "highres"
FLEET = ROOT / "automation" / "state" / "fleet"

# --- fitted micro-structure constants (see --calibrate) -----------------------------
PROXY_BIAS = -0.026     # OPRA close(m-1) -> engine-observed bid
PROXY_SD = 0.058        # 1sd of that fit; used as the uncertainty band
HALF_SPREAD = 0.025     # ledger `premium` (mid) -> bid
EXIT_FILL_EDGE = +0.02  # market-sell fills land ~2c above the last observed bid
ENTRY_FILL_EDGE = +0.02  # marketable-limit buys fill ~2c above the observed mid

EOD_FLATTEN_ET = "15:50"

STOP_WIDTHS = [
    ("-6% (LIVE)", -0.06),
    ("-10%", -0.10),
    ("-12%", -0.12),
    ("-15%", -0.15),
    ("-20%", -0.20),
    ("-25%", -0.25),
    ("-50% catastrophe-only", -0.50),
]


def et_of(ts_utc: str) -> str:
    """'2026-08-05T14:01:00Z' -> '10:01' ET. EDT months only (this rig trades Mar-Nov)."""
    hh = int(ts_utc[11:13])
    return f"{(hh - 4) % 24:02d}:{ts_utc[14:16]}"


def minute_range(lo: str, hi: str) -> list[str]:
    out, h, m = [], int(lo[:2]), int(lo[3:])
    eh, em = int(hi[:2]), int(hi[3:])
    while (h, m) <= (eh, em):
        out.append(f"{h:02d}:{m:02d}")
        m += 1
        if m == 60:
            m, h = 0, h + 1
    return out


def load_bars(symbol: str, date: str) -> dict[str, dict]:
    p = HIRES / f"{symbol}_1m_{date}.csv"
    if not p.exists():
        raise FileNotFoundError(f"missing real-OPRA cache: {p}")
    out: dict[str, dict] = {}
    with p.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[et_of(r["timestamp"])] = {
                "o": float(r["open"]), "h": float(r["high"]),
                "l": float(r["low"]), "c": float(r["close"]), "v": float(r["volume"]),
            }
    return out


def ledger_rows(arm: str, date: str) -> list[dict]:
    p = FLEET / arm / "decisions.jsonl"
    out = []
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if str(r.get("ts_et", "")).startswith(date):
                out.append(r)
    return out


def build_quote_series(arms: list[str], date: str, symbol: str,
                       bars: dict[str, dict]) -> tuple[dict[str, float], dict[str, str]]:
    """Hybrid engine-observed-bid series. Returns ({et: bid}, {et: provenance})."""
    bid: dict[str, float] = {}
    prov: dict[str, str] = {}
    for arm in arms:
        for r in ledger_rows(arm, date):
            m = str(r["ts_et"])[11:16]
            for e in (r.get("exit_pass") or []):
                if e.get("symbol") == symbol and e.get("worst_premium") is not None:
                    bid.setdefault(m, float(e["worst_premium"]))
                    prov.setdefault(m, "engine_bid")
    for arm in arms:
        for r in ledger_rows(arm, date):
            m = str(r["ts_et"])[11:16]
            if m in bid:
                continue
            prem = r.get("premium")
            strike = r.get("strike")
            if prem is None or strike is None:
                continue
            if f"{int(strike) * 1000:08d}" not in symbol:
                continue
            bid[m] = round(float(prem) - HALF_SPREAD, 4)
            prov[m] = "engine_mid"
    mins = sorted(bars)
    for i, m in enumerate(mins):
        if m in bid or i == 0:
            continue
        bid[m] = round(bars[mins[i - 1]]["c"] + PROXY_BIAS, 4)
        prov[m] = "opra_proxy"
    return bid, prov


@dataclass
class Wave:
    arm: str
    symbol: str
    qty: int
    signal_minutes: list[str]
    real_entries: list[tuple[str, float, int]] = field(default_factory=list)
    real_exits: list[tuple[str, float, int]] = field(default_factory=list)
    setup: str = ""
    side: str = ""


def load_wave(arm: str, date: str, symbol: str, setups: set[str]) -> Wave:
    minutes, qty, side, setup = [], 0, "", ""
    for r in ledger_rows(arm, date):
        if r.get("setup_name") not in setups:
            continue
        act, rc = str(r.get("action") or ""), str(r.get("risk_code") or "")
        if not (act.startswith("ENTER") or rc == "NOT_FLAT"):
            continue
        minutes.append(str(r["ts_et"])[11:16])
        if act.startswith("ENTER"):
            qty = int(r.get("qty") or qty)
            side = str(r.get("side") or side)
            setup = str(r.get("setup_name"))
    return Wave(arm=arm, symbol=symbol, qty=qty,
                signal_minutes=sorted(set(minutes)), setup=setup, side=side)


def attach_real_fills(wave: Wave, fills: list[dict]) -> None:
    for f in fills:
        if f.get("symbol") != wave.symbol:
            continue
        et, px, q = et_of(f["transaction_time"]), float(f["price"]), int(f["qty"])
        (wave.real_entries if f.get("side") == "buy" else wave.real_exits).append((et, px, q))
    wave.real_entries.sort()
    wave.real_exits.sort()


def fifo_pnl(buys: list[tuple[str, float, int]],
             sells: list[tuple[str, float, int]]) -> float:
    """FIFO realized P&L. Handles partial fills (risky-3 10:17 filled 1+7)."""
    book: list[list] = [[px, q] for _, px, q in buys]
    pnl = 0.0
    for _, spx, sq in sells:
        rem = sq
        while rem > 0 and book:
            bpx, bq = book[0]
            take = min(rem, bq)
            pnl += (spx - bpx) * take * 100
            rem -= take
            book[0][1] -= take
            if book[0][1] == 0:
                book.pop(0)
    return pnl


@dataclass
class Leg:
    entry_et: str
    entry_px: float
    exit_et: str
    exit_px: float
    qty: int
    stage: str
    pnl: float = 0.0


@dataclass
class CellResult:
    label: str
    width: float
    legs: list[Leg] = field(default_factory=list)
    total_pnl: float = 0.0
    n_entries: int = 0
    proxy_minutes: int = 0

    def as_dict(self) -> dict:
        return {"label": self.label, "width": self.width, "n_entries": self.n_entries,
                "total_pnl": round(self.total_pnl, 2),
                "proxy_dependent_minutes": self.proxy_minutes,
                "legs": [{"entry_et": l.entry_et, "entry_px": round(l.entry_px, 4),
                          "exit_et": l.exit_et, "exit_px": round(l.exit_px, 4),
                          "qty": l.qty, "stage": l.stage, "pnl": round(l.pnl, 2)}
                         for l in self.legs]}


def simulate(wave: Wave, bars: dict[str, dict], bid: dict[str, float],
             prov: dict[str, str], width: float, label: str, *,
             invalid_state: dict[str, bool] | None = None,
             real_entry_map: dict[str, float] | None = None,
             end_et: str = EOD_FLATTEN_ET) -> CellResult:
    """Walk the session ONE POSITION AT A TIME under a single stop width.

    `invalid_state[m]` (chart/structure cell only) is the STATE of the setup's chart
    invalidation at minute m -- "the most recent CLOSED 5m bar is on the wrong side of
    VWAP". It is a market state, not a one-shot event: it exits an open position AND
    blocks re-entry while true, and re-entry resumes if the state clears. Modelling it
    as a one-shot timestamp produces a degenerate enter/exit-every-minute loop.
    """
    res = CellResult(label=label, width=width)
    if not wave.signal_minutes:
        return res
    sig = set(wave.signal_minutes)
    minutes = minute_range(wave.signal_minutes[0], end_et)

    holding = False
    entry_px = 0.0
    entry_et = ""
    stop_level = 0.0

    for m in minutes:
        px = bid.get(m)
        invalid = bool(invalid_state.get(m)) if invalid_state is not None else False
        if holding:
            if px is not None and prov.get(m) == "opra_proxy":
                res.proxy_minutes += 1
            hit_stop = px is not None and px <= stop_level
            eod = m >= end_et
            if invalid or hit_stop or eod:
                fill = max((px if px is not None else 0.01) + EXIT_FILL_EDGE, 0.01)
                stage = ("structure_stop" if invalid else
                         "premium_stop" if hit_stop else "eod_flatten")
                res.legs.append(Leg(entry_et, entry_px, m, fill, wave.qty, stage,
                                    (fill - entry_px) * wave.qty * 100))
                holding = False
                if eod:
                    break
                continue

        if not holding and m in sig and m < end_et and not invalid:
            if real_entry_map and m in real_entry_map:
                e = real_entry_map[m]
            elif px is not None:
                e = px + HALF_SPREAD + ENTRY_FILL_EDGE
            else:
                continue
            holding, entry_px, entry_et = True, round(e, 4), m
            stop_level = round(entry_px * (1.0 + width), 4)
            res.n_entries += 1

    res.total_pnl = sum(l.pnl for l in res.legs)
    return res


def reconstruct_invalid_state(spy: dict[str, dict], side: str) -> tuple[dict[str, bool], str | None]:
    """RECONSTRUCTED chart-invalidation STATE for VWAP_CONTINUATION.

    The live setup carried trigger_level=None, so NO such level existed in production --
    this is a reconstruction and is labelled as one wherever it is reported.

    Definition, fixed before running: session-anchored VWAP. The setup is INVALID at
    minute m iff the most recently CLOSED 5-minute bar (closes at :34,:39,:44,... off the
    09:30 anchor) closed on the wrong side of VWAP. State, not one-shot event -- it exits
    an open position and blocks re-entry while true, and clears if price reclaims.
    Uses only information available at m (no look-ahead: the 5m bar must have closed).
    """
    cum_pv = cum_v = 0.0
    vwap: dict[str, float] = {}
    for m in sorted(spy):
        if not ("09:30" <= m <= "16:00"):
            continue
        b = spy[m]
        cum_pv += (b["h"] + b["l"] + b["c"]) / 3.0 * b["v"]
        cum_v += b["v"]
        vwap[m] = cum_pv / cum_v if cum_v else 0.0

    state: dict[str, bool] = {}
    first_true: str | None = None
    cur = False
    for m in sorted(vwap):
        # the bar closing at m becomes actionable on the NEXT minute
        state[m] = cur
        if cur and first_true is None:
            first_true = m
        if int(m[3:]) % 5 == 4:
            c = spy[m]["c"]
            cur = (c < vwap[m]) if side == "C" else (c > vwap[m])
    return state, first_true


def mc_band(wave: Wave, bars: dict[str, dict], bid: dict[str, float], prov: dict[str, str],
            width: float, *, n: int = 400, seed: int = 20260805) -> dict:
    """Monte-Carlo the cell under the fitted proxy noise (sd=PROXY_SD) on the minutes that
    fall back to the OPRA proxy. Engine-observed minutes are exact and are NOT perturbed.
    Answers: is this cell's number robust, or is it riding a one-cent knife edge?"""
    import random
    rng = random.Random(seed)
    tot = []
    for _ in range(n):
        jb = dict(bid)
        for m, p in prov.items():
            if p == "opra_proxy" and m in jb:
                jb[m] = round(jb[m] + rng.gauss(0.0, PROXY_SD), 4)
        tot.append(simulate(wave, bars, jb, prov, width, "mc").total_pnl)
    tot.sort()
    return {"p05": round(tot[int(0.05 * n)], 2), "p50": round(tot[n // 2], 2),
            "p95": round(tot[int(0.95 * n) - 1], 2), "mean": round(st.mean(tot), 2)}


def calibrate(arms: list[str], date: str, symbol: str, bars: dict[str, dict]) -> dict:
    obs: dict[str, list[float]] = {}
    for arm in arms:
        for r in ledger_rows(arm, date):
            m = str(r["ts_et"])[11:16]
            for e in (r.get("exit_pass") or []):
                if e.get("symbol") == symbol and e.get("worst_premium") is not None:
                    obs.setdefault(m, []).append(float(e["worst_premium"]))
    mins = sorted(bars)
    prevc = {mins[i]: bars[mins[i - 1]]["c"] for i in range(1, len(mins))}
    errs = [sum(v) / len(v) - prevc[m] for m, v in obs.items() if m in prevc]
    return {"n": len(errs), "mean": round(st.mean(errs), 4) if errs else None,
            "sd": round(st.pstdev(errs), 4) if errs else None,
            "mae": round(st.mean([abs(x) for x in errs]), 4) if errs else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-08-05")
    ap.add_argument("--fills", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    fills_all = json.loads(Path(args.fills).read_text(encoding="utf-8"))
    spy = load_bars("SPY", args.date)
    symbol = "SPY260805C00776000"
    arms = ["risky-1", "risky-3"]
    bars = load_bars(symbol, args.date)
    bid, prov = build_quote_series(arms, args.date, symbol, bars)
    cal = calibrate(arms, args.date, symbol, bars)

    report = {
        "date": args.date,
        "data_source": "Alpaca /v1beta1/options/bars 1Min (REAL OPRA) + engine ledger quotes",
        "calibration_fit": cal,
        "model": {"proxy_bias": PROXY_BIAS, "proxy_sd": PROXY_SD,
                  "half_spread": HALF_SPREAD, "exit_fill_edge": EXIT_FILL_EDGE,
                  "sequential": True,
                  "quote_priority": ["engine_bid", "engine_mid", "opra_proxy"]},
        "waves": {},
    }
    print(f"calibration fit (engine bid vs OPRA prev-close): {cal}")

    for arm in arms:
        wave = load_wave(arm, args.date, symbol, {"VWAP_CONTINUATION"})
        attach_real_fills(wave, fills_all.get(arm, []))
        real_pnl = fifo_pnl(wave.real_entries, wave.real_exits)
        real_map = {e: p for e, p, _ in wave.real_entries}
        inval, struct_et = reconstruct_invalid_state(spy, wave.side)

        cells = []
        for lab, w in STOP_WIDTHS:
            c = simulate(wave, bars, bid, prov, w, lab).as_dict()
            c["mc_band"] = mc_band(wave, bars, bid, prov, w)
            cells.append(c)
        cs = simulate(wave, bars, bid, prov, -0.50,
                      "chart/structure (RECONSTRUCTED)", invalid_state=inval)
        cd = cs.as_dict()
        cd["structure_first_invalid_et"] = struct_et
        cd["reconstructed"] = True
        cells.append(cd)

        calibcell = simulate(wave, bars, bid, prov, -0.06,
                             "-6% CALIBRATION (real entry fills)", real_entry_map=real_map)

        report["waves"][arm] = {
            "arm": arm, "symbol": symbol, "qty": wave.qty, "setup": wave.setup,
            "signal_minutes": wave.signal_minutes,
            "real_entries": [{"et": e, "px": p, "qty": q} for e, p, q in wave.real_entries],
            "real_exits": [{"et": e, "px": p, "qty": q} for e, p, q in wave.real_exits],
            "real_pnl": round(real_pnl, 2),
            "calibration_cell": calibcell.as_dict(),
            "calibration_delta": round(calibcell.total_pnl - real_pnl, 2),
            "cells": cells,
        }

        print(f"\n===== {arm} {symbol} qty={wave.qty} setup={wave.setup}")
        print(f"  signal minutes ({len(wave.signal_minutes)}): {' '.join(wave.signal_minutes)}")
        print(f"  REAL broker P&L (FIFO): {real_pnl:+.2f}  "
              f"({len(wave.real_entries)} buys / {len(wave.real_exits)} sells)")
        print(f"  CALIBRATION -6% w/ real entries: {calibcell.total_pnl:+.2f} "
              f"({calibcell.n_entries} entries)  delta {calibcell.total_pnl - real_pnl:+.2f}")
        print(f"  reconstructed first-invalid minute: {struct_et}")
        print(f"  {'cell':<34s} {'entries':>7s} {'pnl':>10s} {'proxy':>6s}  {'MC p05..p95':>20s}")
        for c in cells:
            mb = c.get("mc_band")
            band = f"{mb['p05']:+.0f} .. {mb['p95']:+.0f}" if mb else "-"
            print(f"  {c['label']:<34s} {c['n_entries']:>7d} {c['total_pnl']:>+10.2f} "
                  f"{c['proxy_dependent_minutes']:>6d}  {band:>20s}")

    Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
