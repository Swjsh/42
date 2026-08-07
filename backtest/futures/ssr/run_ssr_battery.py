"""SSR battery orchestrator -- CLI: --family A|B [--refresh-data].

Runs the FROZEN grid (backtest/futures/analysis/SSR-battery/DESIGN.md sec 4)
across each family's symbols x directions x combos, scores every cell against
a random-entry null and a buy-and-hold-to-timestop null, BH-FDRs the family,
and writes:
    analysis/recommendations/futures-ssr-smoke.json   (family A)
    analysis/recommendations/futures-ssr-regime.json  (family B)
    backtest/futures/analysis/SSR-battery/RESULTS.md   (both -- marker-scoped
        per-family section, re-running a family replaces only its own section)

Contract modules `data_fetch`, `levels`, `detector`, `ssr_instruments` are
sibling, parallel-built files under this same `ssr/` package -- imported
LAZILY inside the functions that need them (HARD RULE: "modules may not
exist yet"). `battery`, `swing_sim.wilder_atr`, `futures_sim.simulate_futures`
are the pre-existing, stable shared modules -- imported at top level.

Run:
    backtest/.venv/Scripts/python.exe backtest/futures/ssr/run_ssr_battery.py --family A
    backtest/.venv/Scripts/python.exe backtest/futures/ssr/run_ssr_battery.py --family B --refresh-data
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_BACKTEST_DIR = Path(__file__).resolve().parents[2]
if str(_BACKTEST_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKTEST_DIR))
_REPO = _BACKTEST_DIR.parent

from futures import battery  # noqa: E402
from futures.swing_sim import wilder_atr  # noqa: E402
from futures.futures_sim import simulate_futures  # noqa: E402
from futures.ssr import backtest_runner  # noqa: E402

REC_DIR = _REPO / "analysis" / "recommendations"
RESULTS_MD = _BACKTEST_DIR / "futures" / "analysis" / "SSR-battery" / "RESULTS.md"

# Grid FROZEN (DESIGN.md sec 4): zone_atr_mult x sweep_atr_mult, 2x2 = 4 combos.
GRID = [{"zone_atr_mult": z, "sweep_atr_mult": s} for z in (0.25, 0.5) for s in (0.10, 0.25)]

FAMILIES = {
    "A": {
        "symbols": ["GC=F", "NQ=F", "ES=F"],
        "interval": "15m",
        "period": "60d",
        "oos_cut": dt.date(2026, 7, 20),
        "output_name": "futures-ssr-smoke.json",
        "shadow_symbols": {"NQ=F", "ES=F"},
        "headline_split": True,
        "label": "smoke",
    },
    "B": {
        "symbols": ["GC=F"],
        "interval": "1h",
        "period": "730d",
        "oos_cut": dt.date(2026, 1, 1),
        "output_name": "futures-ssr-regime.json",
        "shadow_symbols": set(),
        "headline_split": False,
        "label": "regime",
    },
}

EXHIBIT_DATE = dt.date(2026, 8, 7)  # exhibit-contamination disclosure, DESIGN.md sec 2
MAG7 = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA"]
MAG7_LOOKBACK_PERIOD = "2y"
ENTRY_WINDOW_START = dt.time(3, 0)
ENTRY_WINDOW_END = dt.time(15, 0)
N_NULL_DRAWS = 300
MIN_OOS_N = 5
ALPHA = 0.05
NULL_RNG_SEED = 1337


def log(msg: str) -> None:
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Small pure stats helpers (kept local -- battery.py's are OOS-scoped and
# private; this battery's own contract computes p-values over the FULL cell,
# see build_cell's docstring).
# ---------------------------------------------------------------------------

def _stats(nets: list[float]) -> dict:
    n = len(nets)
    if n == 0:
        return {"n": 0, "wr": None, "total": 0.0, "mean": None}
    arr = np.asarray(nets, dtype=float)
    return {"n": n, "wr": round(float((arr > 0).mean()), 4),
            "total": round(float(arr.sum()), 2), "mean": round(float(arr.mean()), 2)}


def _drop_top3(nets: list[float]) -> float:
    if len(nets) <= 3:
        return 0.0
    return round(float(sum(sorted(nets, reverse=True)[3:])), 2)


def _bh_net(direction: str, entry: float, future_bars: pd.DataFrame, instrument,
            *, qty: int = 3, slippage_ticks: float = 1.0) -> float:
    """No-stop, no-target: hold `entry` to `future_bars`'s last close. Mirrors
    futures_sim.simulate_futures's cost formula exactly (read, not modified)
    for an apples-to-apples 'same slippage+commission' buy-and-hold null."""
    sign = 1.0 if direction == "long" else -1.0
    last = float(future_bars.iloc[-1]["close"]) if len(future_bars) else entry
    pts = (last - entry) * sign
    gross = pts * instrument.point_value * qty
    slippage_cost = slippage_ticks * instrument.tick_size * instrument.point_value * qty * 2.0
    commissions = instrument.round_turn_usd * qty
    return gross - slippage_cost - commissions


def _entry_idx_for_ts(bars: pd.DataFrame, ts) -> Optional[int]:
    matches = np.flatnonzero((bars["timestamp_et"] == ts).to_numpy())
    return int(matches[0]) if matches.size else None


def _eligible_null_indices(bars: pd.DataFrame) -> list[int]:
    """Bars in the 03:00-15:00 ET entry window with a next bar available."""
    times = bars["timestamp_et"].dt.time
    in_window = ((times >= ENTRY_WINDOW_START) & (times <= ENTRY_WINDOW_END)).to_numpy()
    n = len(bars)
    return [i for i in range(n - 1) if in_window[i]]


def _random_entry_null_pool(bars: pd.DataFrame, eligible_idx: list[int], direction: str,
                             r_points: float, instrument, *, n_draws: int,
                             rng: np.random.Generator) -> list[float]:
    """300 draws of eligible bar indices, SAME exit shape as the real cell
    (fixed R = median R of the cell's real trades, tp1=1.5R, runner=3R FIXED
    -- not level-based, per DESIGN.md sec 5), SAME truncation/costs/qty."""
    if not eligible_idx:
        return []
    sign = 1.0 if direction == "long" else -1.0
    picks = rng.choice(eligible_idx, size=n_draws, replace=True)
    pool: list[float] = []
    for raw_i in picks:
        i = int(raw_i)
        entry_idx = i + 1
        if entry_idx >= len(bars):
            continue
        entry = float(bars["open"].iloc[entry_idx])
        stop = entry - sign * r_points
        tp1 = entry + sign * 1.5 * r_points
        runner = entry + sign * 3.0 * r_points
        ts_et = bars["timestamp_et"].iloc[i]
        future_bars = backtest_runner.future_bars_through_flat(bars, entry_idx, ts_et)
        if len(future_bars) == 0:
            continue
        result = simulate_futures(direction, entry, stop, tp1, runner, future_bars, instrument,
                                   qty=3, tp1_fraction=2.0 / 3.0, slippage_ticks=1.0, px_to_points=1.0)
        pool.append(result["net"])
    return pool


def _buy_and_hold_total(trades: list[dict], bars: pd.DataFrame, instrument) -> float:
    total = 0.0
    for t in trades:
        entry_idx = _entry_idx_for_ts(bars, t["ts_entry_et"])
        if entry_idx is None:
            continue
        future_bars = backtest_runner.future_bars_through_flat(bars, entry_idx, t["ts_entry_et"])
        total += _bh_net(t["direction"], t["entry"], future_bars, instrument)
    return round(total, 2)


# ---------------------------------------------------------------------------
# Shadow columns (NQ/ES cells only, DESIGN.md sec 5) -- logged, never gates.
# ---------------------------------------------------------------------------

def _vix_agree_for_trade(vix_bars: Optional[pd.DataFrame], entry_ts, direction: str) -> Optional[bool]:
    """FROZEN simple definition: VIX 15m close direction over the prior 4
    bars (close[t] - close[t-4], t = the VIX bar at/just before entry)
    OPPOSITE to trade direction. Long wants VIX falling (dir < 0); short
    wants VIX rising (dir > 0). None if VIX data/alignment unavailable
    (fail-open, counted by the caller)."""
    if vix_bars is None or len(vix_bars) == 0:
        return None
    ts = vix_bars["timestamp_et"]
    pos = int(ts.searchsorted(entry_ts, side="right")) - 1
    if pos < 4:
        return None
    vix_dir = float(vix_bars["close"].iloc[pos]) - float(vix_bars["close"].iloc[pos - 4])
    return bool(vix_dir < 0) if direction == "long" else bool(vix_dir > 0)


def _mag7_breadth_for_trade(mag7_daily: dict, trade_date: dt.date, direction: str) -> Optional[int]:
    """FROZEN simple definition: for each of the 7 tickers, the sign of its
    day-change on the last COMPLETED trading day strictly BEFORE `trade_date`
    (no look-ahead into the trade's own, possibly still-open, session) versus
    the day before that. +1 if that sign agrees with trade direction, -1 if
    it opposes, 0 if flat; summed across all 7 -> range -7..+7. Returns None
    (fail-open, counted by the caller) if ANY ticker's data is missing or has
    insufficient prior history for this date -- a partial breadth over fewer
    than 7 tickers is not comparable to a full one, so it is not reported."""
    sign = 1 if direction == "long" else -1
    total = 0
    for ticker in MAG7:
        df = mag7_daily.get(ticker)
        if df is None or len(df) == 0:
            return None
        dates = df["timestamp_et"].dt.date
        prior_closes = df.loc[dates < trade_date, "close"]
        if len(prior_closes) < 2:
            return None
        change = float(prior_closes.iloc[-1]) - float(prior_closes.iloc[-2])
        total += sign * (1 if change > 0 else (-1 if change < 0 else 0))
    return total


def _attach_shadow_columns(trades: list[dict], vix_bars, mag7_daily, direction: str) -> tuple[list[dict], dict]:
    fb = {"vix": 0, "mag7": 0}
    out = []
    for t in trades:
        va = _vix_agree_for_trade(vix_bars, t["ts_entry_et"], direction)
        if va is None:
            fb["vix"] += 1
        mb = _mag7_breadth_for_trade(mag7_daily, t["date"], direction) if mag7_daily is not None else None
        if mb is None:
            fb["mag7"] += 1
        out.append({**t, "vix_agree": va, "mag7_breadth": mb})
    return out, fb


def _fetch_vix_bars(interval: str, period: str, refresh: bool):
    from futures.ssr import data_fetch
    try:
        return data_fetch.fetch_bars("^VIX", interval, period, refresh=refresh)
    except Exception as e:  # noqa: BLE001 -- shadow-only fail-open, DESIGN.md sec 5; counted by caller
        log(f"WARNING: ^VIX fetch failed ({e!r}) -- vix_agree will be None for shadow cells this family")
        return None


def _fetch_mag7_daily(period: str, refresh: bool) -> dict:
    from futures.ssr import data_fetch
    out: dict = {}
    for ticker in MAG7:
        try:
            out[ticker] = data_fetch.fetch_bars(ticker, "1d", period, refresh=refresh)
        except Exception as e:  # noqa: BLE001 -- shadow-only fail-open, DESIGN.md sec 5; counted by caller
            log(f"WARNING: mag7 daily fetch failed for {ticker} ({e!r}) -- excluded from mag7_breadth")
            out[ticker] = None
    return out


# ---------------------------------------------------------------------------
# Per-cell scoring
# ---------------------------------------------------------------------------

def build_cell(
    symbol: str, direction: str, combo: dict, trades: list[dict],
    bars: pd.DataFrame, instrument, oos_cut: dt.date, rng: np.random.Generator,
    *, shadow: bool, vix_bars, mag7_daily, fallback_counts: dict,
) -> dict:
    """Full metrics for ONE (symbol, direction, combo) cell.

    Bootstrap p-value uses the OVERALL cell mean/n (IS+OOS combined) per the
    work order's literal wording ("observed_mean=cell mean_net ... n_obs=n"),
    which differs from battery.py's OOS-scoped convention -- disclosed here,
    not silently reused. The CLEARS gate separately requires oos_n>=5 and
    oos_mean>0 (also per the work order), so a cell can have a significant
    overall p-value yet still fail to clear on thin/negative OOS evidence.
    drop_top3_net and the halves-stability split are likewise computed over
    ALL (IS+OOS) trades, matching total_net's own scope.
    """
    nets = [t["net"] for t in trades]
    overall = _stats(nets)
    is_trades = [t for t in trades if t["date"] < oos_cut]
    oos_trades = [t for t in trades if t["date"] >= oos_cut]
    is_stats = _stats([t["net"] for t in is_trades])
    oos_stats = _stats([t["net"] for t in oos_trades])

    null_unavailable = overall["n"] == 0
    null_summary = {"n_pool": 0, "null_mean": None, "p_value": None, "r_median_points": None}
    if not null_unavailable:
        r_median = float(statistics.median(t["r_points"] for t in trades))
        eligible_idx = _eligible_null_indices(bars)
        null_pool = _random_entry_null_pool(bars, eligible_idx, direction, r_median, instrument,
                                             n_draws=N_NULL_DRAWS, rng=rng)
        if null_pool:
            p, null_mean = battery.bootstrap_null_pvalue(overall["mean"], null_pool, overall["n"])
            null_summary = {"n_pool": len(null_pool),
                             "null_mean": (round(null_mean, 2) if np.isfinite(null_mean) else None),
                             "p_value": (round(p, 4) if np.isfinite(p) else None),
                             "r_median_points": round(r_median, 4)}
        else:
            null_unavailable = True  # no eligible bars to draw from -- disclose, exclude from FDR

    bh_total = _buy_and_hold_total(trades, bars, instrument) if trades else 0.0
    beats_bh = bool(overall["total"] is not None and overall["total"] > bh_total)
    drop_top3 = _drop_top3(nets)

    sorted_trades = sorted(trades, key=lambda t: t["date"])
    mid = len(sorted_trades) // 2
    halves = {
        "first_half_total": round(sum(t["net"] for t in sorted_trades[:mid]), 2),
        "second_half_total": round(sum(t["net"] for t in sorted_trades[mid:]), 2),
        "first_half_n": mid, "second_half_n": len(sorted_trades) - mid,
    }

    out_trades = trades
    if shadow:
        out_trades, sh_fb = _attach_shadow_columns(trades, vix_bars, mag7_daily, direction)
        fallback_counts["vix_agree_fallback"] += sh_fb["vix"]
        fallback_counts["mag7_breadth_fallback"] += sh_fb["mag7"]

    return {
        "symbol": symbol, "direction": direction, "combo": combo,
        "n": overall["n"], "wr": overall["wr"], "total_net": overall["total"], "mean_net": overall["mean"],
        "is": is_stats, "oos": oos_stats,
        "null_unavailable": null_unavailable, "null": null_summary,
        "buy_and_hold_total": bh_total, "beats_bh": beats_bh,
        "drop_top3_net": drop_top3, "halves_stability": halves,
        "trades": out_trades,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _instrument_symbol(data_symbol: str) -> str:
    """data_fetch/yfinance ticker (e.g. "GC=F", "^VIX") -> ssr_instruments/
    instruments registry key (e.g. "GC"). ssr_instruments.get_ssr() indexes
    on the bare contract root (verified against backtest/futures/ssr/
    ssr_instruments.py + the shared backtest/futures/instruments.py), not
    the yfinance suffix convention this battery's symbol list uses."""
    return data_symbol.split("=")[0].lstrip("^").upper()


def fetch_bars_for(symbol: str, cfg: dict, refresh: bool) -> pd.DataFrame:
    from futures.ssr import data_fetch
    bars = data_fetch.fetch_bars(symbol, cfg["interval"], cfg["period"], refresh=refresh)
    if bars is None or len(bars) == 0:
        raise RuntimeError(f"data_fetch.fetch_bars returned empty for {symbol} {cfg['interval']}/{cfg['period']}")
    return bars.reset_index(drop=True)


def _headline_with_without_exhibit(all_cells: list[dict]) -> dict:
    with_total = 0.0
    without_total = 0.0
    n_exhibit = 0
    for c in all_cells:
        for t in c["trades"]:
            with_total += t["net"]
            if t["date"] == EXHIBIT_DATE:
                n_exhibit += 1
            else:
                without_total += t["net"]
    return {"with_2026_08_07": round(with_total, 2), "without_2026_08_07": round(without_total, 2),
            "n_trades_on_2026_08_07": n_exhibit}


def _headline_by_symbol_exhibit(all_cells: list[dict]) -> dict:
    """Per-symbol breakdown of exhibit-date (2026-08-07) trades: n, total_net,
    n_winners, n_losers. Exists so any prose describing "what fired on the
    exhibit date" is grounded in a computed, persisted figure instead of a
    hand tally over the (symbol, direction, combo) cell table -- a manual
    count over that 24-row grid undercounted by omitting an entire symbol's
    rows and mischaracterized winning trades as "marginal" (round-1 fixer
    finding, 2026-08-07). sum(n) across symbols MUST equal
    headline_with_without_exhibit_2026_08_07.n_trades_on_2026_08_07 --
    enforced by test_ssr_exhibit_day_breakdown.py."""
    by_symbol: dict[str, dict] = {}
    for c in all_cells:
        for t in c["trades"]:
            if t["date"] != EXHIBIT_DATE:
                continue
            slot = by_symbol.setdefault(c["symbol"], {"n": 0, "total_net": 0.0, "n_winners": 0, "n_losers": 0})
            slot["n"] += 1
            slot["total_net"] += t["net"]
            if t["net"] > 0:
                slot["n_winners"] += 1
            else:
                slot["n_losers"] += 1
    for slot in by_symbol.values():
        slot["total_net"] = round(slot["total_net"], 2)
    return by_symbol


def _write_results_md(family: str, cfg: dict, all_cells: list[dict], verdict: str, n_clear: int,
                       provenance: dict, fallback_counts: dict, headline: Optional[dict],
                       skip_counts_total: dict, headline_by_symbol: Optional[dict] = None) -> None:
    start_marker = f"<!-- SSR-FAMILY-{family}:START -->"
    end_marker = f"<!-- SSR-FAMILY-{family}:END -->"

    lines = [
        start_marker,
        f"## Family {family} -- {cfg['label']}",
        "",
        f"**VERDICT: {verdict}** ({n_clear}/{len(all_cells)} cells clear) -- "
        f"generated {dt.datetime.now().isoformat()}",
        "",
        f"Symbols: {', '.join(cfg['symbols'])} @ {cfg['interval']}/{cfg['period']}, "
        f"OOS cut {cfg['oos_cut']}",
        "",
        "### Data provenance",
        "",
    ]
    for sym, prov in provenance.items():
        lines.append(f"- {sym}: {prov['rows']} rows, {prov['first_ts']} .. {prov['last_ts']}")

    lines += [
        "",
        "### Cell table",
        "",
        "| symbol | dir | zone | sweep | n | oos_n | oos_mean | total_net | beats_bh | fdr | drop_top3 | clears |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in sorted(all_cells, key=lambda c: (c["symbol"], c["direction"],
                                               c["combo"]["zone_atr_mult"], c["combo"]["sweep_atr_mult"])):
        lines.append(
            f"| {c['symbol']} | {c['direction']} | {c['combo']['zone_atr_mult']} | {c['combo']['sweep_atr_mult']} "
            f"| {c['n']} | {c['oos']['n']} | {c['oos']['mean']} | {c['total_net']} | {c['beats_bh']} "
            f"| {c.get('fdr_survivor', False)} | {c['drop_top3_net']} | {'YES' if c['clears'] else 'no'} |"
        )

    n_null_unavail = sum(1 for c in all_cells if c["null_unavailable"])
    lines += [
        "",
        "### Nulls & disclosures",
        "",
        f"- null_unavailable cells (0 trades or no eligible null bars, excluded from BH-FDR family): "
        f"{n_null_unavail}/{len(all_cells)}",
        f"- shadow-column fallback counts: {fallback_counts}",
        f"- skip/degenerate counts (summed across all cells): {skip_counts_total}",
    ]
    if headline is not None:
        lines += [
            "",
            "### Headline with/without 2026-08-07 exhibit date",
            "",
            f"- WITH: ${headline['with_2026_08_07']:,.2f}  "
            f"WITHOUT: ${headline['without_2026_08_07']:,.2f}  "
            f"(n={headline['n_trades_on_2026_08_07']} trades on that date)",
        ]
    if headline_by_symbol:
        lines += [
            "",
            "### Exhibit-date (2026-08-07) trades by symbol",
            "",
            "| symbol | n | total_net | n_winners | n_losers |",
            "|---|---|---|---|---|",
        ]
        for sym in sorted(headline_by_symbol):
            b = headline_by_symbol[sym]
            lines.append(f"| {sym} | {b['n']} | {b['total_net']} | {b['n_winners']} | {b['n_losers']} |")
    lines += ["", end_marker, ""]
    section = "\n".join(lines)

    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    if RESULTS_MD.exists():
        text = RESULTS_MD.read_text(encoding="utf-8")
    else:
        text = "# SSR Battery -- RESULTS\n\n> Written by run_ssr_battery.py. Verdict-first per family.\n\n"

    if start_marker in text and end_marker in text:
        pre = text.split(start_marker)[0]
        post = text.split(end_marker)[1]
        text = pre + section + post
    else:
        text = text.rstrip() + "\n\n" + section + "\n"
    RESULTS_MD.write_text(text, encoding="utf-8")


def run_family(family: str, refresh_data: bool) -> dict:
    from futures.ssr import detector, levels, ssr_instruments

    cfg = FAMILIES[family]
    rng = np.random.default_rng(NULL_RNG_SEED)
    t0 = time.time()

    provenance: dict = {}
    all_cells: list[dict] = []
    fallback_counts = {"vix_agree_fallback": 0, "mag7_breadth_fallback": 0,
                        "vix_fetch_failed": 0, "mag7_fetch_failed": 0}
    skip_counts_total: dict = {}

    vix_bars = None
    mag7_daily = None
    if cfg["shadow_symbols"]:
        log("fetching ^VIX + Mag7 daily for shadow columns ...")
        vix_bars = _fetch_vix_bars(cfg["interval"], cfg["period"], refresh_data)
        if vix_bars is None:
            fallback_counts["vix_fetch_failed"] = 1
        mag7_daily = _fetch_mag7_daily(MAG7_LOOKBACK_PERIOD, refresh_data)
        fallback_counts["mag7_fetch_failed"] = sum(1 for v in mag7_daily.values() if v is None)

    for symbol in cfg["symbols"]:
        log(f"fetching {symbol} {cfg['interval']}/{cfg['period']} ...")
        bars = fetch_bars_for(symbol, cfg, refresh_data)
        provenance[symbol] = {"rows": len(bars), "first_ts": str(bars["timestamp_et"].min()),
                               "last_ts": str(bars["timestamp_et"].max())}
        atr = wilder_atr(bars, 14)
        snapshots = levels.build_levels(bars)
        instrument = ssr_instruments.get_ssr(_instrument_symbol(symbol))

        for combo in GRID:
            params = detector.SSRParams(zone_atr_mult=combo["zone_atr_mult"],
                                         sweep_atr_mult=combo["sweep_atr_mult"])
            signals = detector.SSRDetector(params).run(bars, snapshots, atr)
            log(f"  {symbol} combo {combo} -> {len(signals)} signals")

            for direction in ("long", "short"):
                dir_signals = [s for s in signals if s.direction == direction]
                cell_stats: dict = {}
                trades = backtest_runner.run_trades(bars, snapshots, dir_signals, instrument,
                                                     atr=atr, stats=cell_stats)
                shadow = symbol in cfg["shadow_symbols"]
                cell = build_cell(symbol, direction, combo, trades, bars, instrument, cfg["oos_cut"], rng,
                                   shadow=shadow, vix_bars=vix_bars, mag7_daily=mag7_daily,
                                   fallback_counts=fallback_counts)
                cell["skip_counts"] = cell_stats
                for k, v in cell_stats.items():
                    skip_counts_total[k] = skip_counts_total.get(k, 0) + v
                all_cells.append(cell)

    # FDR across the family's cells, excluding null_unavailable (disclosed exclusion).
    eligible = [c for c in all_cells if not c["null_unavailable"] and c["null"]["p_value"] is not None]
    pvals = [c["null"]["p_value"] for c in eligible]
    survivors = battery.bh_fdr(pvals, alpha=ALPHA)
    for c, surv in zip(eligible, survivors):
        c["fdr_survivor"] = bool(surv)
    for c in all_cells:
        c.setdefault("fdr_survivor", False)

    for c in all_cells:
        oos_n, oos_mean = c["oos"]["n"], c["oos"]["mean"]
        c["clears"] = bool(
            oos_n >= MIN_OOS_N and oos_mean is not None and oos_mean > 0
            and c["fdr_survivor"] and c["beats_bh"] and c["drop_top3_net"] > 0
        )

    n_clear = sum(1 for c in all_cells if c["clears"])
    verdict = "PASS" if n_clear > 0 else "KILL"
    headline = _headline_with_without_exhibit(all_cells) if cfg["headline_split"] else None
    headline_by_symbol = _headline_by_symbol_exhibit(all_cells) if cfg["headline_split"] else None

    payload = {
        "rule_id": f"futures-ssr-{cfg['label']}",
        "family": family, "generated_at": dt.datetime.now().isoformat(),
        "spec_origin": ["backtest/futures/analysis/SSR-battery/DESIGN.md",
                         "markdown/research/SSR-PIVOT-LIQUIDITY-STRATEGY.md"],
        "grid": GRID, "oos_cut": str(cfg["oos_cut"]),
        "symbols": cfg["symbols"], "interval": cfg["interval"], "period": cfg["period"],
        "data_provenance": provenance,
        "n_cells": len(all_cells), "n_bh_fdr_eligible": len(eligible),
        "n_clearing_cells": n_clear, "verdict": verdict,
        "min_oos_n": MIN_OOS_N, "alpha": ALPHA,
        "cells": all_cells,
        "skip_degenerate_fallback_counts": skip_counts_total,
        "shadow_fallback_counts": fallback_counts,
        "headline_with_without_exhibit_2026_08_07": headline,
        "exhibit_day_breakdown_by_symbol": headline_by_symbol,
        "exhibit_contamination_note": (
            "Strategy formalized from a 2026-08-07 GC trade; that date sits inside "
            "this smoke window. See headline_with_without_exhibit_2026_08_07."
        ) if family == "A" else None,
        "runtime_sec": round(time.time() - t0, 1),
    }

    REC_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REC_DIR / cfg["output_name"]
    out_path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    log(f"wrote {out_path}")

    _write_results_md(family, cfg, all_cells, verdict, n_clear, provenance, fallback_counts,
                       headline, skip_counts_total, headline_by_symbol)
    log(f"VERDICT family {family}: {verdict} ({n_clear}/{len(all_cells)} cells clear) "
        f"in {payload['runtime_sec']}s")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="SSR battery orchestrator")
    parser.add_argument("--family", choices=["A", "B"], required=True)
    parser.add_argument("--refresh-data", action="store_true")
    args = parser.parse_args()
    run_family(args.family, args.refresh_data)


if __name__ == "__main__":
    main()
