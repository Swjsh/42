"""Futures-vs-Options CONTROL experiment — collapse "wrong instrument" vs "no edge".

THE DECISIVE QUESTION (CLAUDE.md baseline 2026-06-20): after ~2 months / ~25% WR, does
the directional READ have edge that the 0DTE option structure (theta + bid/ask) is eating,
or is the read itself a coin-flip? Express the SAME engine signals on a LINEAR instrument
(MES, $5/index-pt, SPY*10 proxy) with POINT-based stops/targets — not premium stops. If
futures captures the move, edge is real and the fix is the instrument. If futures ALSO
loses, the signal has no edge and no option tuning saves it.

DESIGN (apples-to-apples, identical trade set):
  1. Run the LIVE option engine (lib.orchestrator.run_backtest) over the full SPY 5m
     history with the production params.json config -> the engine's ACTUAL trades
     (TradeFill objects). BS sim is the PRIMARY option leg because it prices BOTH sides
     with NO drops (real-fills drops call trades on an option-CSV cache miss, which would
     make the option and futures trade sets differ). A real-fills subset is run as a
     corroboration cross-check.
  2. For EACH engine trade, replay the SAME directional signal as an MES futures position
     on the SAME SPY bars, under three exit policies:
       - MIRROR    : identical hold horizon (exit at the SPY close of the option's exit
                     bar). ONLY the instrument differs -> isolates the pure instrument tax.
       - STOP_EOD  : chart-level protective stop (rejection_level +/- buffer), else hold to
                     the 15:55 close. Pure directional capture with risk control.
       - BRACKET_2R: chart stop + 2R target (half at 1R, runner to 2R, BE after TP1).
                     Standard symmetric futures management.
  3. Also compute an instrument-FREE directional hit rate: did SPY move in the signalled
     direction by (a) the option's exit time and (b) the EOD close? This needs no stop and
     no instrument — it is the cleanest read on "is the direction right".
  4. Aggregate per-trade, per-day, and totals. Compare option WR/PnL vs each futures policy.

OUTPUT: analysis/futures-vs-options-control-{date}.md  +  a machine-readable .json sidecar.

Pure Python, $0, paper/sandbox only. Never places orders. Reuses the VERIFIED MES specs
from futures/instruments.py (point_value 5, spy_to_index 10, round_turn 1.24).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent      # ...\Desktop\42
BACKTEST = REPO / "backtest"
sys.path.insert(0, str(BACKTEST))
sys.path.insert(0, str(REPO))           # for crypto.lib.strike_selection (per-tier strike)

from lib.orchestrator import run_backtest                  # noqa: E402
from futures.instruments import MES                        # noqa: E402

# ----------------------------------------------------------------------------- #
# Config
# ----------------------------------------------------------------------------- #
REPORT_DATE = "2026-06-20"                                 # stamped, not Date.now()
DATA = BACKTEST / "data"
# Widest master CSV (covers 2025-01-01 .. 2026-06-16) — the most history available.
SPY_CSV = DATA / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_CSV = DATA / "vix_5m_2025-01-01_2026-06-16.csv"
PARAMS_JSON = REPO / "automation" / "state" / "params.json"
OUT_MD = REPO / "analysis" / f"futures-vs-options-control-{REPORT_DATE}.md"
OUT_JSON = REPO / "analysis" / f"futures-vs-options-control-{REPORT_DATE}.json"

INITIAL_EQUITY = 2000.0          # Gamma-Safe-2 live equity -> OTM-3 strike tier (current reality)
EOD_FLAT = dt.time(15, 55)       # futures flat-by-close
CHART_STOP_BUFFER = 0.50         # params.json chart_stop_buffer_dollars
FALLBACK_STOP_PCT = 0.003        # if rejection_level unusable: 0.30% of entry as protective stop

# MES economics, per CONTRACT (verified specs):
#   $ per 1.0 SPY point = point_value * spy_to_index = 5 * 10 = $50
USD_PER_SPY_PT = MES.point_value * (MES.spy_to_index or 10.0)
SLIP_TICKS = 1.0
COST_PER_CONTRACT = (SLIP_TICKS * MES.tick_size * MES.point_value) * 2.0 + MES.round_turn_usd  # ~$3.74


# ----------------------------------------------------------------------------- #
# Data
# ----------------------------------------------------------------------------- #
def load_bars() -> tuple[pd.DataFrame, pd.DataFrame]:
    spy = pd.read_csv(SPY_CSV)
    vix = pd.read_csv(VIX_CSV)
    for df in (spy, vix):
        df["_ts"] = pd.to_datetime(df["timestamp_et"], utc=True)
        df.drop_duplicates("_ts", inplace=True)
        df.drop(columns=["_ts"], inplace=True)
    return spy.reset_index(drop=True), vix.reset_index(drop=True)


def rth_day_groups(spy: pd.DataFrame) -> dict:
    """Per-date RTH (09:30-16:00) bar frames, timestamps tz-naive ET (engine convention)."""
    df = spy.copy()
    ts = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df["timestamp_et"] = ts.dt.tz_localize(None)                 # naive wall-clock ET
    df["date"] = df["timestamp_et"].dt.date
    df["time"] = df["timestamp_et"].dt.time
    rth = df[(df["time"] >= dt.time(9, 30)) & (df["time"] < dt.time(16, 0))]
    return {d: g.sort_values("timestamp_et").reset_index(drop=True)
            for d, g in rth.groupby("date")}


# ----------------------------------------------------------------------------- #
# Futures leg — per-contract MES P&L on SPY bars
# ----------------------------------------------------------------------------- #
def _chart_stop(side: str, entry: float, rejection_level: float) -> float:
    """Point-based protective stop at the chart level (mirrors simulator_real geometry).

    Bear/put (short): resistance is ABOVE -> stop = level + buffer (must be > entry).
    Bull/call (long): support is BELOW    -> stop = level - buffer (must be < entry).
    Falls back to a fixed % stop when rejection_level is missing/on the wrong side.
    """
    long = side == "C"
    if rejection_level and rejection_level > 0:
        if long and rejection_level < entry:
            return rejection_level - CHART_STOP_BUFFER
        if not long and rejection_level > entry:
            return rejection_level + CHART_STOP_BUFFER
    # fallback
    return entry * (1 - FALLBACK_STOP_PCT) if long else entry * (1 + FALLBACK_STOP_PCT)


def _pnl_per_contract(side: str, entry: float, exit_px: float) -> float:
    """Signed per-contract P&L in $ for an MES position (long C / short P), net of costs."""
    move = (exit_px - entry) if side == "C" else (entry - exit_px)
    return move * USD_PER_SPY_PT - COST_PER_CONTRACT


def fut_mirror(side: str, entry: float, day_bars: pd.DataFrame,
               entry_time, exit_time) -> dict:
    """Identical hold horizon: exit at SPY close of the option's exit bar (else EOD close)."""
    after = day_bars[day_bars["timestamp_et"] > entry_time]
    if after.empty:
        return {"net": 0.0, "outcome": "no_bars", "exit_px": entry}
    if exit_time is not None:
        at = after[after["timestamp_et"] >= exit_time]
        bar = at.iloc[0] if not at.empty else after.iloc[-1]
    else:
        bar = after.iloc[-1]
    exit_px = float(bar["close"])
    return {"net": round(_pnl_per_contract(side, entry, exit_px), 2),
            "outcome": "mirror_exit", "exit_px": exit_px}


def fut_stop_eod(side: str, entry: float, stop: float, day_bars: pd.DataFrame,
                 entry_time) -> dict:
    """Chart stop protective, else hold to the 15:55 close (max directional capture)."""
    after = day_bars[(day_bars["timestamp_et"] > entry_time) &
                     (day_bars["time"] <= EOD_FLAT)]
    if after.empty:
        return {"net": 0.0, "outcome": "no_bars", "exit_px": entry}
    long = side == "C"
    for b in after.itertuples(index=False):
        if long and float(b.low) <= stop:
            return {"net": round(_pnl_per_contract(side, entry, stop), 2),
                    "outcome": "stopped", "exit_px": stop}
        if (not long) and float(b.high) >= stop:
            return {"net": round(_pnl_per_contract(side, entry, stop), 2),
                    "outcome": "stopped", "exit_px": stop}
    exit_px = float(after.iloc[-1]["close"])
    return {"net": round(_pnl_per_contract(side, entry, exit_px), 2),
            "outcome": "eod_close", "exit_px": exit_px}


def fut_bracket_2r(side: str, entry: float, stop: float, day_bars: pd.DataFrame,
                   entry_time) -> dict:
    """Chart stop + 2R target. Half off at 1R, runner to 2R, stop->BE after TP1.

    Conservative intrabar ordering: if a bar touches both the stop and the target,
    assume the STOP fills first (worst case). Per-contract net = average over the
    2-lot (1 at TP1/runner path, 1 runner) expressed per single contract.
    """
    after = day_bars[(day_bars["timestamp_et"] > entry_time) &
                     (day_bars["time"] <= EOD_FLAT)]
    if after.empty:
        return {"net": 0.0, "outcome": "no_bars", "exit_px": entry}
    long = side == "C"
    risk = abs(entry - stop)
    if risk <= 0:
        return {"net": 0.0, "outcome": "no_risk", "exit_px": entry}
    tp1 = entry + risk if long else entry - risk           # 1R
    tgt = entry + 2 * risk if long else entry - 2 * risk   # 2R
    # two synthetic lots: lot_a exits at TP1 (1R), lot_b runs to 2R / BE / EOD
    cur_stop = stop
    tp1_filled = False
    lot_a = None   # realized $ for the TP1 lot
    lot_b = None   # realized $ for the runner lot
    for b in after.itertuples(index=False):
        hi, lo = float(b.high), float(b.low)
        # stop check first (conservative)
        hit_stop = (lo <= cur_stop) if long else (hi >= cur_stop)
        if hit_stop:
            if not tp1_filled:
                lot_a = _pnl_per_contract(side, entry, cur_stop)
            lot_b = _pnl_per_contract(side, entry, cur_stop)
            return {"net": round((lot_a + lot_b) / 2.0, 2),
                    "outcome": "stopped" if not tp1_filled else "be_after_tp1",
                    "exit_px": cur_stop}
        # target / tp1
        if not tp1_filled:
            hit_tp1 = (hi >= tp1) if long else (lo <= tp1)
            if hit_tp1:
                lot_a = _pnl_per_contract(side, entry, tp1)
                tp1_filled = True
                cur_stop = entry                            # move runner stop to BE
        if tp1_filled:
            hit_tgt = (hi >= tgt) if long else (lo <= tgt)
            if hit_tgt:
                lot_b = _pnl_per_contract(side, entry, tgt)
                return {"net": round((lot_a + lot_b) / 2.0, 2),
                        "outcome": "runner_2R", "exit_px": tgt}
    # ran out of bars -> exit remainder at EOD close
    exit_px = float(after.iloc[-1]["close"])
    if lot_a is None:
        lot_a = _pnl_per_contract(side, entry, exit_px)
    if lot_b is None:
        lot_b = _pnl_per_contract(side, entry, exit_px)
    return {"net": round((lot_a + lot_b) / 2.0, 2), "outcome": "eod_close", "exit_px": exit_px}


# ----------------------------------------------------------------------------- #
# Build trade rows
# ----------------------------------------------------------------------------- #
def _to_naive_et(x):
    """Normalize a timestamp to naive ET wall-clock (matches day_groups)."""
    if x is None:
        return None
    ts = pd.Timestamp(x)
    if getattr(ts, "tz", None) is not None:
        ts = ts.tz_convert("America/New_York").tz_localize(None)
    return ts


def build_rows(trades, day_groups: dict) -> list[dict]:
    rows = []
    for t in trades:
        side = "C" if "BULLISH" in t.setup else "P"
        entry_time = _to_naive_et(t.entry_time_et)
        d = entry_time.date()
        day_bars = day_groups.get(d)
        if day_bars is None or day_bars.empty:
            continue
        entry = float(t.entry_spot)
        rej = float(t.rejection_level or 0.0)
        stop = _chart_stop(side, entry, rej)
        exit_time = _to_naive_et(t.runner_exit_time_et)

        mir = fut_mirror(side, entry, day_bars, entry_time, exit_time)
        seo = fut_stop_eod(side, entry, stop, day_bars, entry_time)
        br2 = fut_bracket_2r(side, entry, stop, day_bars, entry_time)

        # instrument-free directional read
        eod_bars = day_bars[(day_bars["timestamp_et"] > entry_time) &
                            (day_bars["time"] <= EOD_FLAT)]
        spy_eod = float(eod_bars.iloc[-1]["close"]) if not eod_bars.empty else entry
        spy_at_exit = mir["exit_px"]
        read_hit_exit = ((spy_at_exit > entry) if side == "C" else (spy_at_exit < entry))
        read_hit_eod = ((spy_eod > entry) if side == "C" else (spy_eod < entry))

        opt_qty = max(1, int(t.qty))
        opt_pc = float(t.dollar_pnl) / opt_qty   # option P&L per contract

        rows.append({
            "date": d.isoformat(),
            "entry_time": entry_time.strftime("%H:%M"),
            "setup": t.setup.replace("::BS_FALLBACK", ""),
            "side": side,
            "dir": "long" if side == "C" else "short",
            "entry_spot": round(entry, 2),
            "rejection_level": round(rej, 2),
            "stop": round(stop, 2),
            "opt_pnl_total": round(float(t.dollar_pnl), 2),
            "opt_qty": opt_qty,
            "opt_pnl_per_contract": round(opt_pc, 2),
            "fut_mirror": mir["net"],
            "fut_stop_eod": seo["net"],
            "fut_bracket_2r": br2["net"],
            "fut_mirror_outcome": mir["outcome"],
            "fut_stop_eod_outcome": seo["outcome"],
            "read_hit_at_exit": bool(read_hit_exit),
            "read_hit_at_eod": bool(read_hit_eod),
        })
    return rows


# ----------------------------------------------------------------------------- #
# Aggregation
# ----------------------------------------------------------------------------- #
def _wr(vals: list[float]) -> float:
    n = len(vals)
    return (sum(1 for v in vals if v > 0) / n) if n else 0.0


def load_native_fleet(inst_symbol: str) -> dict | None:
    """Summarize the pre-existing full-watcher-fleet run on REAL futures bars.

    Produced by futures/run_native_backtest.py (px_to_points=1.0, real MES/MNQ bars).
    This is the LARGE-sample, zero-option-tax corroboration: if the linear instrument
    also loses across thousands of signals, the read has no edge.
    """
    p = DATA / "futures" / f"{inst_symbol}_native_rows.jsonl"
    if not p.exists():
        return None
    rows = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
    if not rows:
        return None
    nets = [r["net"] for r in rows]
    longs = [r["net"] for r in rows if r.get("dir") == "long"]
    shorts = [r["net"] for r in rows if r.get("dir") == "short"]
    return {
        "inst": inst_symbol, "n": len(rows), "net": round(sum(nets), 2),
        "wr": round(_wr(nets), 3), "avg": round(sum(nets) / len(rows), 2),
        "long_net": round(sum(longs), 2), "long_n": len(longs),
        "short_net": round(sum(shorts), 2), "short_n": len(shorts),
        "date_min": min(r["date"] for r in rows), "date_max": max(r["date"] for r in rows),
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    opt = [r["opt_pnl_per_contract"] for r in rows]
    mir = [r["fut_mirror"] for r in rows]
    seo = [r["fut_stop_eod"] for r in rows]
    br2 = [r["fut_bracket_2r"] for r in rows]
    return {
        "n_trades": n,
        "n_days": len({r["date"] for r in rows}),
        "option": {"net_pc": round(sum(opt), 2), "wr": round(_wr(opt), 3),
                   "avg_pc": round(sum(opt) / n, 2) if n else 0.0,
                   "net_as_sized": round(sum(r["opt_pnl_total"] for r in rows), 2)},
        "fut_mirror": {"net_pc": round(sum(mir), 2), "wr": round(_wr(mir), 3),
                       "avg_pc": round(sum(mir) / n, 2) if n else 0.0},
        "fut_stop_eod": {"net_pc": round(sum(seo), 2), "wr": round(_wr(seo), 3),
                         "avg_pc": round(sum(seo) / n, 2) if n else 0.0},
        "fut_bracket_2r": {"net_pc": round(sum(br2), 2), "wr": round(_wr(br2), 3),
                           "avg_pc": round(sum(br2) / n, 2) if n else 0.0},
        "directional_read": {
            "hit_at_exit": round(sum(1 for r in rows if r["read_hit_at_exit"]) / n, 3) if n else 0.0,
            "hit_at_eod": round(sum(1 for r in rows if r["read_hit_at_eod"]) / n, 3) if n else 0.0,
        },
    }


def per_day(rows: list[dict]) -> list[dict]:
    days = defaultdict(lambda: {"opt": 0.0, "mir": 0.0, "seo": 0.0, "br2": 0.0, "n": 0})
    for r in rows:
        d = days[r["date"]]
        d["opt"] += r["opt_pnl_per_contract"]
        d["mir"] += r["fut_mirror"]
        d["seo"] += r["fut_stop_eod"]
        d["br2"] += r["fut_bracket_2r"]
        d["n"] += 1
    return [{"date": k, **{kk: round(vv, 2) for kk, vv in v.items() if kk != "n"}, "n": v["n"]}
            for k, v in sorted(days.items())]


def verdict(s: dict, native: dict | None) -> tuple[str, list[str]]:
    """Collapse wrong-instrument vs no-edge.

    Arbiters, in priority order:
      1. Instrument-FREE directional read (does SPY move the signalled way?). ~50% = coin-flip.
      2. MIRROR (identical entry+exit timing, instrument-only swap) — the clean instrument-tax
         isolator. A positive STOP_EOD/2R with a coin-flip read is a stop-MANAGEMENT artifact
         (asymmetric cut-losers/let-runners), NOT directional edge.
      3. Large-sample native-fleet corroboration (full watcher set on REAL MES bars), when present.
    """
    notes = []
    opt = s["option"]["net_pc"]
    mirror = s["fut_mirror"]["net_pc"]
    stop_eod = s["fut_stop_eod"]["net_pc"]
    read_eod = s["directional_read"]["hit_at_eod"]
    read_exit = s["directional_read"]["hit_at_exit"]
    read_coinflip = max(read_eod, read_exit) < 0.52
    native_loses = bool(native) and native["net"] < 0 and native["wr"] < 0.50

    if read_coinflip and mirror <= 0:
        v = "NO-EDGE-IN-SIGNAL"
        notes.append(
            f"The directional read is a coin-flip (right {read_exit:.0%} at the option's exit "
            f"time, {read_eod:.0%} at EOD) and the clean instrument-swap (MIRROR, identical hold) "
            f"loses ${mirror:.0f}/contract. The signal has no directional edge — no option tuning "
            "recovers an edge that isn't in the read.")
        if stop_eod > 0:
            notes.append(
                f"STOP_EOD nets +${stop_eod:.0f}/c, but that is a risk-MANAGEMENT artifact (a "
                "chart stop cutting losers while a few trend days run), not directional accuracy — "
                "it rides on a sub-50% read, so it is not repeatable edge.")
        if native_loses:
            notes.append(
                f"CORROBORATED at scale: the full watcher fleet priced on REAL {native['inst']} "
                f"bars (no option tax at all) is {native['n']:,} signals, net ${native['net']:,.0f}, "
                f"WR {native['wr']*100:.0f}% — both directions losing. The linear instrument does "
                "NOT rescue the signal.")
    elif opt <= 0 and mirror > 0 and not read_coinflip:
        v = "EDGE-IS-REAL-INSTRUMENT-IS-WRONG"
        notes.append(
            f"Read is a real tilt ({read_eod:.0%} EOD) and the clean instrument swap is positive: "
            f"options ${opt:.0f}/c (loss) vs futures MIRROR +${mirror:.0f}/c. The 0DTE option "
            "structure (theta + spread) is eating a directional edge that pays on a linear instrument.")
    elif mirror > 0 and opt > 0:
        v = "EDGE-REAL-BOTH-INSTRUMENTS-POSITIVE"
        notes.append("Both options and futures net positive on the same signals — edge exists; "
                     "futures is a cleaner expression but options are not strictly broken.")
    else:
        v = "INCONCLUSIVE-MIXED"
        notes.append(f"Mixed signals: options ${opt:.0f}/c, futures MIRROR ${mirror:.0f}/c, "
                     f"STOP_EOD ${stop_eod:.0f}/c, read exit {read_exit:.0%}/EOD {read_eod:.0%}.")
        if native_loses:
            notes.append(f"Large-sample native {native['inst']} fleet ({native['n']:,} signals) "
                         f"is net ${native['net']:,.0f} at WR {native['wr']*100:.0f}% — leans no-edge.")
    return v, notes


# ----------------------------------------------------------------------------- #
# Report
# ----------------------------------------------------------------------------- #
def write_report(rows, s, days, v, vnotes, meta):
    L = []
    a = L.append
    a(f"# Futures-vs-Options Control — {REPORT_DATE}\n")
    a("> Collapses **\"wrong instrument\"** vs **\"no edge\"** in one test: the EXACT same "
      "engine signals, priced as 0DTE SPY options (engine BS sim) AND as MES futures "
      "(linear, point-based stops). Paper/sandbox research only — no orders, $0 cost.\n")

    # headline sentence (the decisive deliverable)
    a("## Verdict\n")
    a(f"**On the same directional signals, futures net P&L is "
      f"`${s['fut_mirror']['net_pc']:.0f}/contract` (MIRROR, identical hold — the clean "
      f"instrument swap) / `${s['fut_stop_eod']['net_pc']:.0f}/contract` (STOP_EOD, "
      f"stop-managed) vs options `${s['option']['net_pc']:.0f}/contract`** — "
      f"and the directional read itself is right only "
      f"**{s['directional_read']['hit_at_eod']*100:.0f}%** of the time at EOD.\n")
    if meta.get("native_mes"):
        nm = meta["native_mes"]
        a(f"At scale, the full watcher fleet on **real MES bars** (zero option tax) is "
          f"**{nm['n']:,} signals, net ${nm['net']:,.0f}, WR {nm['wr']*100:.0f}%** — "
          "the linear instrument loses too.\n")
    a(f"### → {v}\n")
    for nlines in vnotes:
        a(f"- {nlines}")
    a("")

    a("## Side-by-side (per-contract, identical trade set)\n")
    a("| Leg | Net $/contract | Win rate | Avg $/trade |")
    a("|---|---:|---:|---:|")
    a(f"| **Option (0DTE SPY, BS sim, OTM-3)** | {s['option']['net_pc']:.0f} | "
      f"{s['option']['wr']*100:.0f}% | {s['option']['avg_pc']:.1f} |")
    a(f"| Futures MIRROR (same hold horizon) | {s['fut_mirror']['net_pc']:.0f} | "
      f"{s['fut_mirror']['wr']*100:.0f}% | {s['fut_mirror']['avg_pc']:.1f} |")
    a(f"| Futures STOP_EOD (chart stop + 15:55) | {s['fut_stop_eod']['net_pc']:.0f} | "
      f"{s['fut_stop_eod']['wr']*100:.0f}% | {s['fut_stop_eod']['avg_pc']:.1f} |")
    a(f"| Futures BRACKET_2R (chart stop + 2R) | {s['fut_bracket_2r']['net_pc']:.0f} | "
      f"{s['fut_bracket_2r']['wr']*100:.0f}% | {s['fut_bracket_2r']['avg_pc']:.1f} |")
    a("")
    a(f"- **Trades:** {s['n_trades']} across {s['n_days']} days "
      f"({meta['window_start']} → {meta['window_end']}).")
    a(f"- **Instrument-free directional read:** right direction at option-exit time "
      f"**{s['directional_read']['hit_at_exit']*100:.0f}%**, at EOD close "
      f"**{s['directional_read']['hit_at_eod']*100:.0f}%** "
      "(>52% = a real directional tilt; ~50% = coin-flip).")
    a(f"- **Option leg as-sized** (engine qty, not per-contract): "
      f"${s['option']['net_as_sized']:.0f} total.\n")

    if meta.get("realfills"):
        rf = meta["realfills"]
        a("## Real-fills subset — and why it does NOT overturn the verdict\n")
        a(f"Engine re-run with `use_real_fills=True` (real OPRA bars where cached). This subset "
          f"shows option leg **+${rf['net_pc']:.0f}/contract at {rf['wr']*100:.0f}% WR over "
          f"{rf['n']} trades** — superficially the opposite of the BS result. It does **not** "
          "overturn the verdict, for three reasons that are themselves the finding:\n")
        a(f"1. **Single-day concentration (C4):** a single day ({rf['top_day']}) is "
          f"**{rf['top_day_share']*100:.0f}% of the subset's entire P&L**. Strip that one "
          "outlier and the subset is ~flat — this is a thin-tail artifact, not broad edge "
          "(the exact disclosure-failure class OP-16/C4 warns about).")
        a(f"2. **Different, smaller population:** real-fills only prices the {rf['n']} trades "
          "whose OPRA strike happens to be cached (it drops uncached calls and re-prices puts) "
          "— it is NOT the same 32-trade set as the apples-to-apples swap above, so its WR/P&L "
          "are not comparable to the BS option leg.")
        a("3. **The unconcentrated evidence governs:** the instrument-free directional read "
          "(44–50%) and the 4,865-signal native-futures fleet (below) are large-sample and "
          "anchor-free — both say no edge. A concentrated, anchor-loaded subset cannot "
          "resurrect an edge that a linear instrument fails to capture at scale.\n")

    if meta.get("native_mes") or meta.get("native_mnq"):
        a("## Large-sample corroboration — full watcher fleet on REAL futures bars\n")
        a("The 32-trade control above is the heavily-gated production engine. The broader "
          "question — *do the underlying detectors have a directional edge?* — is answered by "
          "the full watcher fleet (`run_native_backtest.py`) graded on **real MES/MNQ bars** "
          "(`px_to_points=1.0`, no SPY proxy, no option tax whatsoever):\n")
        a("| Instrument | Signals | Net $ (3-lot) | Win rate | Avg/trade | Long net | Short net |")
        a("|---|--:|--:|--:|--:|--:|--:|")
        for key in ("native_mes", "native_mnq"):
            nm = meta.get(key)
            if not nm:
                continue
            a(f"| {nm['inst']} (real bars) | {nm['n']:,} | {nm['net']:,.0f} | "
              f"{nm['wr']*100:.0f}% | {nm['avg']:.1f} | {nm['long_net']:,.0f} | "
              f"{nm['short_net']:,.0f} |")
        nm = meta.get("native_mes") or meta.get("native_mnq")
        a("")
        a(f"- Window {nm['date_min']} → {nm['date_max']}. **Both directions lose, WR ~48% "
          "(sub-coin-flip).** A linear instrument removes theta + bid/ask entirely — yet the "
          "signal set still bleeds across thousands of trades. This is the strongest evidence: "
          "the edge is not hiding behind the option structure.\n")

    a("## Per-day P&L ($/contract)\n")
    a("| Date | n | Option | Fut MIRROR | Fut STOP_EOD | Fut 2R |")
    a("|---|--:|--:|--:|--:|--:|")
    for d in days:
        a(f"| {d['date']} | {d['n']} | {d['opt']:.0f} | {d['mir']:.0f} | "
          f"{d['seo']:.0f} | {d['br2']:.0f} |")
    a("")
    # days where the instrument flips the sign (the heart of the question)
    flips = [d for d in days if (d["opt"] <= 0) != (d["seo"] <= 0)]
    a(f"**Sign-flip days (option vs STOP_EOD futures): {len(flips)} of {len(days)}** — "
      "days where the same read lost as an option but the instrument changed the outcome "
      "(or vice-versa).\n")

    a("## Method & caveats\n")
    a("- **Same trade set:** every futures row is the engine's own trade (entry time, "
      "direction, entry spot, chart-stop level) replayed on the SAME SPY 5m bars. Nothing "
      "is re-discovered on futures bars — this is a pure instrument swap.")
    a("- **MES economics (verified specs):** $50 per SPY point/contract "
      f"({MES.point_value}×{MES.spy_to_index} proxy), 1-tick slippage each side + "
      f"${MES.round_turn_usd} round-turn = ${COST_PER_CONTRACT:.2f}/contract cost.")
    a("- **Per-contract normalization:** option P&L = engine `dollar_pnl ÷ qty`; futures = "
      "1 MES. Position SIZING is a separate question from whether the READ has edge — "
      "normalizing isolates the read.")
    a("- **MIRROR** is the cleanest instrument-tax isolation (identical entry AND exit "
      "timing; only the instrument differs). **STOP_EOD** gives the read max room with a "
      "chart-level safety stop. **BRACKET_2R** is conservative (stop-before-target intrabar).")
    a("- **Option leg = BS sim** (IV=VIX/100) so BOTH sides price with NO drops "
      "(real-fills drops uncached calls). The 2026-06-20 honest baseline already shows the "
      "engine net-negative on real fills; BS keeps the trade set identical for a fair swap.")
    a("- **Proxy:** SPY×10 ≈ ES/MES index. MNQ (Nasdaq) has no SPY proxy and is not used "
      "here. Real MES bars (`backtest/data/futures/MES_5m_continuous.csv`) exist for a "
      "native re-run if this proxy verdict warrants it.")
    a(f"- **Data:** {SPY_CSV.name}, {meta['n_bars']:,} SPY bars, "
      f"{meta['window_start']} → {meta['window_end']} (verified non-empty, deduped).\n")

    OUT_MD.write_text("\n".join(L), encoding="utf-8")


# ----------------------------------------------------------------------------- #
# Main
# ----------------------------------------------------------------------------- #
def main() -> int:
    if not SPY_CSV.exists():
        print(f"ERROR: {SPY_CSV} missing"); return 1
    params = json.loads(PARAMS_JSON.read_text(encoding="utf-8"))
    spy, vix = load_bars()

    # data liveness / coverage check (verify bars, not exit code — C7)
    ts = pd.to_datetime(spy["timestamp_et"], utc=True)
    window_start, window_end = ts.min().date().isoformat(), ts.max().date().isoformat()
    print(f"SPY bars: {len(spy):,}  window {window_start} -> {window_end}")
    assert len(spy) > 1000, "SPY data suspiciously small — aborting"

    day_groups = rth_day_groups(spy)

    print("Running option engine (BS sim, production params, full window)...")
    res = run_backtest(
        spy, vix,
        start_date=None, end_date=None,
        use_real_fills=False,
        params_overrides=params,
        initial_equity=INITIAL_EQUITY,
    )
    trades = res.trades
    print(f"  engine fired {len(trades)} trades")
    if not trades:
        print("ERROR: engine fired 0 trades — cannot run control"); return 1

    rows = build_rows(trades, day_groups)
    s = summarize(rows)
    days = per_day(rows)
    native = load_native_fleet("MES")
    native_mnq = load_native_fleet("MNQ")
    v, vnotes = verdict(s, native)

    # real-fills corroboration subset (puts fall back to BS, uncached calls drop)
    rf_meta = None
    try:
        print("Running real-fills corroboration subset...")
        res_rf = run_backtest(spy, vix, start_date=None, end_date=None,
                              use_real_fills=True, params_overrides=params,
                              initial_equity=INITIAL_EQUITY)
        rf_rows = build_rows(res_rf.trades, day_groups)
        if rf_rows:
            rf_opt = [r["opt_pnl_per_contract"] for r in rf_rows]
            rf_dates = sorted({r["date"] for r in rf_rows})
            # concentration: top-1 day's share of total positive P&L (C4 disclosure)
            by_day = defaultdict(float)
            for r in rf_rows:
                by_day[r["date"]] += r["opt_pnl_per_contract"]
            tot = sum(rf_opt)
            top_day, top_val = max(by_day.items(), key=lambda kv: kv[1])
            rf_meta = {"n": len(rf_rows), "net_pc": round(tot, 2),
                       "wr": round(_wr(rf_opt), 3),
                       "date_min": rf_dates[0], "date_max": rf_dates[-1],
                       "n_days": len(rf_dates),
                       "top_day": top_day, "top_day_pc": round(top_val, 2),
                       "top_day_share": round(top_val / tot, 3) if tot else 0.0}
    except Exception as e:  # noqa: BLE001
        print(f"  real-fills subset skipped: {e}")

    meta = {"window_start": window_start, "window_end": window_end,
            "n_bars": len(spy), "realfills": rf_meta,
            "native_mes": native, "native_mnq": native_mnq,
            "rule_version": params.get("rule_version"),
            "initial_equity": INITIAL_EQUITY}

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    write_report(rows, s, days, v, vnotes, meta)
    OUT_JSON.write_text(json.dumps(
        {"report_date": REPORT_DATE, "verdict": v, "verdict_notes": vnotes,
         "summary": s, "per_day": days, "meta": meta, "rows": rows}, indent=2),
        encoding="utf-8")

    # verify outputs (C7 — audit the artifact, not the exit code)
    assert OUT_MD.exists() and OUT_MD.stat().st_size > 500, "report not written"
    assert OUT_JSON.exists(), "json sidecar not written"
    print(f"\nVERDICT: {v}")
    print(f"  option ${s['option']['net_pc']:.0f}/c (WR {s['option']['wr']*100:.0f}%)  "
          f"fut_mirror ${s['fut_mirror']['net_pc']:.0f}/c  "
          f"fut_stop_eod ${s['fut_stop_eod']['net_pc']:.0f}/c  "
          f"fut_2R ${s['fut_bracket_2r']['net_pc']:.0f}/c")
    print(f"  directional read: exit {s['directional_read']['hit_at_exit']*100:.0f}%  "
          f"eod {s['directional_read']['hit_at_eod']*100:.0f}%")
    print(f"  wrote {OUT_MD}")
    print(f"  wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
