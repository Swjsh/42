"""NEW-STRATEGY HUNT: opening_range_fade (failed-breakout of the opening range).

HYPOTHESIS (counterpart to our ORB breakout): on range / reversal days, FADE the
30-minute opening-range extreme. Price pokes ABOVE the OR-high then closes back
INSIDE the range -> the upside break failed -> trapped longs -> buy a PUT. Price
pokes BELOW the OR-low then closes back inside -> failed downside break -> trapped
shorts -> buy a CALL. This is the contrarian mirror of the Toby-Crabel ORB.

EXACT RULES (sourced; see analysis/recommendations/newhunt-opening_range_fade.json
"sourced_rules"/"sources" for the verbatim citations):

  - Opening range = HIGH and LOW of the first 30 minutes of the RTH session.
    Crabel's original used the first ~10 min; the widely-published 0DTE/SPY
    convention is the first 5-30 min, "most use the first 15-30 minutes"
    (LiteFinance). We take 30 min (6 x 5-min bars) -- the upper, most-robust end,
    and the same window our own ORB counterpart would use.
        Sources: QuantifiedStrategies ORB; LiteFinance ORB; Unger Academy / Crabel.

  - FAILED-BREAKOUT (fade) entry (BuildAlpha "Setup 2", FBS, Bulls-on-Wall-Street):
      * SHORT (buy PUT): a bar's HIGH pokes strictly above OR-high, but the bar
        CLOSES back inside the range (close <= OR-high). "short when price falls
        back inside the range after the false break above."
      * LONG (buy CALL): a bar's LOW pokes strictly below OR-low, but the bar
        CLOSES back inside the range (close >= OR-low).
      * Entry is taken on the CLOSE of that reclaim bar; fill on the NEXT bar
        (no look-ahead -- handled by simulator_real).
        Sources: BuildAlpha ORB Setup 2; LiteFinance false-breakout note;
                 FBS "fade it: short when price falls back inside the range";
                 Bulls-on-Wall-Street failed-ORB reversal.

  - INVALIDATION / stop (Crabel "early entry failure"; FBS "keep stops tight, just
    outside the failed breakout's high or low"): the chart stop sits just BEYOND
    the poke extreme.
      * For a PUT (failed upside break): invalidation = the OR-high (resistance
        ABOVE) -- if SPY reclaims and holds above OR-high, the break was real.
        We pass rejection_level = OR-high so the simulator's level-stop is
        meaningful (a PUT level-stop fires when close > rejection_level + buffer).
      * For a CALL (failed downside break): invalidation = the OR-low (support
        BELOW). rejection_level = OR-low (CALL level-stop fires when
        close < rejection_level - buffer).
    (The published "stop just outside the poke extreme" is even tighter; using the
    OR edge itself is a slightly looser, defensible chart stop that lines up with
    the structure the failed break defines. The premium_stop_pct sweep covers the
    tighter premium-based stops.)

  - Window: only arm the fade AFTER the OR is fully formed (first 30 min done) and
    before the late session. We scan reclaim bars from OR-end through 15:00 ET-
    equivalent (entries late in a 0DTE day are theta-bleed; the published edge is
    an intraday-reversal one). Cooldown 45 min, max ONE fade per side per day, and
    at most the FIRST qualifying fade per side (the failed-breakout reverses fast --
    later re-poke after a clean reclaim is a different, weaker setup).

  - Published edge stat: ORB-family success rate "ranges from 40% to 60%"
    (LiteFinance). No source publishes a clean per-trade $ expectancy for the SPY
    0DTE single-leg fade -- that is exactly what this real-fills backtest measures.

WHY THIS IS NOT IN THE ENGINE: we run the ORB *continuation* logic; this is the
*reversal* of a failed OR break -- a genuinely new, opposite-direction signal.

METHOD (mirrors db_base_quiet_real_fills_validate.py + confluence_real_fills_validate.py):
  load 16mo SPY 5m -> RTH -> per-day session-open-anchored OR -> causal fade scan
  -> simulator_real.simulate_trade_real (C1 real OPRA fills, the WR authority)
  -> sweep strike_offset {-2,-1,0,1,2} x premium_stop_pct {-0.08,-0.20,-0.50,-0.99}
  -> per-cell self-verify: OOS(2026) per-trade>0, positive_quarters>=4/6, top5<200%,
     n>=20, drop-top-5-days per-trade still >0.

OP-20 (no theatre): reports per-trade EXPECTANCY (not WR), IS/OOS, positive_quarters,
top5 + drop-top5. anti-pattern 2.10: if the only positive cell is thin-N / high-
concentration / OOS-negative we SAY SO and set clears_bar=false. Pure Python, $0.

TIMEZONE NOTE (L57/L61): this CSV's "ET" stamps are inconsistent (most days the first
RTH bar is 09:30 but ~36 early-2025 days are shifted +1h to 10:30, and some days are
missing early bars). A fixed wall-clock 09:30 anchor would CORRUPT those days. We
anchor the OR to each day's FIRST RTH bar (the session open as represented in the
file) -- the same day_start anchoring confluence_real_fills_validate.py uses -- and
require the OR's 6 bars to be contiguous 5-min so malformed/gappy days are skipped.

Output: analysis/recommendations/newhunt-opening_range_fade.json
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "newhunt-opening_range_fade.json"

# ── Strategy parameters ───────────────────────────────────────────────────────
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)
OR_MINUTES = 30                       # opening range = first 30 min of RTH
OR_BARS = OR_MINUTES // 5             # 6 x 5-min bars
RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)
LATE_ENTRY_CUTOFF = dt.time(15, 0)    # no fresh fades after 15:00 (theta cliff)
COOLDOWN_MIN = 45
QTY = 3
POKE_MIN_TICKS = 0.0                  # bar.high must be STRICTLY > OR-high (any poke)

# Sweep grid (small, per the brief)
STRIKE_OFFSETS = [-2, -1, 0, 1, 2]
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]

# Candidate bar (real-fills) acceptance bar
MIN_N = 20
MIN_POS_QUARTERS = 4
MAX_TOP5_PCT = 200.0

SOURCED_RULES = (
    "OR = high/low of first 30 min of RTH (Crabel ~10min original; SPY/0DTE "
    "convention 5-30min, 'most use 15-30'). FADE: bar.high pokes > OR-high but "
    "closes back inside (close<=OR-high) -> buy PUT; bar.low pokes < OR-low but "
    "closes back inside (close>=OR-low) -> buy CALL. Entry on reclaim-bar close, "
    "fill next bar (no look-ahead). Invalidation = the OR edge just crossed "
    "(OR-high above for a PUT, OR-low below for a CALL); stop 'just outside the "
    "failed breakout' (Crabel early-entry-failure / FBS). Target/exit = v15 "
    "default exits (engine TP1/runner/time-stop). One fade per side per day, "
    "first qualifying poke, 45-min cooldown, no entries after 15:00 ET."
)
SOURCES = [
    "https://www.quantifiedstrategies.com/opening-range-breakout-strategy/",
    "https://www.buildalpha.com/opening-range-breakout/",
    "https://www.litefinance.org/blog/for-beginners/trading-strategies/opening-range-breakout-strategy/",
    "https://ungeracademy.com/blog/testing-toby-crabel-s-opening-range-breakout-does-it-really-work-code-backtest-on-nasdaq",
    "https://fbs.com/fbs-academy/traders-blog/opening-range-breakout-trading-strategy",
    "https://www.bullsonwallstreet.com/post/how-to-trade-the-opening-range-breakout",
]


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


class _Acc:
    """Per-cut accumulator with by-day P&L for concentration / drop-top-5."""

    __slots__ = ("n", "wins", "pnl", "by_day")

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.pnl = 0.0
        self.by_day: dict[str, float] = defaultdict(float)

    def add(self, pnl: float, day: str):
        self.n += 1
        self.wins += 1 if pnl > 0 else 0
        self.pnl += pnl
        self.by_day[day] += pnl

    def report(self) -> dict:
        if not self.n:
            return {"n": 0}
        days_sorted = sorted(self.by_day.values(), reverse=True)
        top5 = sum(days_sorted[:5])
        return {
            "n": self.n,
            "wr": round(100 * self.wins / self.n, 1),
            "total_pnl": round(self.pnl, 0),
            "per_trade": round(self.pnl / self.n, 2),
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


def _build_rth(spy_full: pd.DataFrame) -> pd.DataFrame:
    spy_full = spy_full.copy()
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[
        (spy_full["timestamp_et"].dt.time >= RTH_START)
        & (spy_full["timestamp_et"].dt.time < RTH_END)
    ].reset_index(drop=True)
    rth["date"] = rth["timestamp_et"].dt.date
    return rth


def _naive_dt(ts) -> dt.datetime:
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_localize(None)
    return t.to_pydatetime()


def scan_signals(rth: pd.DataFrame) -> list[dict]:
    """Causal opening-range-fade scan. Returns list of signal dicts.

    Per day: anchor OR to the first RTH bar; require 6 contiguous 5-min bars to form
    the OR. Then walk bars AFTER the OR window; the FIRST failed-breakout per side
    (poke beyond edge + close back inside) fires that side's fade. No look-ahead:
    OR is fully closed before any scan bar; the reclaim decision uses only the
    current (closed) bar.
    """
    # day -> list of integer row indices (already in chronological order in rth)
    day_rows: dict[dt.date, list[int]] = defaultdict(list)
    for i, d in enumerate(rth["date"].values):
        day_rows[d].append(i)

    signals: list[dict] = []
    skipped_days = 0

    for d, rows in day_rows.items():
        if d < START or d > END:
            continue
        if len(rows) < OR_BARS + 2:
            skipped_days += 1
            continue

        # ── Build the OR from the first OR_BARS bars; require contiguity ──
        or_rows = rows[:OR_BARS]
        first_t = _naive_dt(rth.iloc[or_rows[0]]["timestamp_et"])
        last_or_t = _naive_dt(rth.iloc[or_rows[-1]]["timestamp_et"])
        span_min = (last_or_t - first_t).total_seconds() / 60.0
        # 6 bars at 5-min spacing span 25 min start-to-start; allow <=30 to be safe.
        if span_min > (OR_MINUTES + 1):
            skipped_days += 1
            continue

        or_high = float(rth.iloc[or_rows]["high"].max())
        or_low = float(rth.iloc[or_rows]["low"].min())
        if or_high <= or_low:
            skipped_days += 1
            continue
        or_end_dt = last_or_t  # OR fully closed at this bar's close

        # ── Walk post-OR bars for the FIRST failed breakout per side ──
        put_done = False
        call_done = False
        last_sig_dt: dt.datetime | None = None

        for idx in rows[OR_BARS:]:
            if put_done and call_done:
                break
            bar = rth.iloc[idx]
            bt = _naive_dt(bar["timestamp_et"])
            if bt.time() > LATE_ENTRY_CUTOFF:
                break
            # Cooldown between the two possible same-day fades.
            if last_sig_dt is not None and (bt - last_sig_dt).total_seconds() / 60.0 < COOLDOWN_MIN:
                continue

            hi = float(bar["high"])
            lo = float(bar["low"])
            cl = float(bar["close"])

            # FAILED UPSIDE BREAK -> PUT: poked above OR-high, closed back inside.
            if (not put_done) and hi > or_high + POKE_MIN_TICKS and cl <= or_high:
                signals.append({
                    "date": d, "bar_idx": idx, "bar": bar, "side": "P",
                    "or_high": round(or_high, 2), "or_low": round(or_low, 2),
                    "rejection_level": round(or_high, 2),  # resistance ABOVE for a put
                    "entry_spot": round(cl, 2),
                    "poke_extreme": round(hi, 2),
                    "time": bt.strftime("%H:%M"),
                    "or_end": or_end_dt.strftime("%H:%M"),
                })
                put_done = True
                last_sig_dt = bt
                continue

            # FAILED DOWNSIDE BREAK -> CALL: poked below OR-low, closed back inside.
            if (not call_done) and lo < or_low - POKE_MIN_TICKS and cl >= or_low:
                signals.append({
                    "date": d, "bar_idx": idx, "bar": bar, "side": "C",
                    "or_high": round(or_high, 2), "or_low": round(or_low, 2),
                    "rejection_level": round(or_low, 2),  # support BELOW for a call
                    "entry_spot": round(cl, 2),
                    "poke_extreme": round(lo, 2),
                    "time": bt.strftime("%H:%M"),
                    "or_end": or_end_dt.strftime("%H:%M"),
                })
                call_done = True
                last_sig_dt = bt
                continue

    log.info("Scan: %d signals across %d days (%d days skipped: short/gappy/malformed OR)",
             len(signals), len(day_rows), skipped_days)
    return signals


def backtest_cell(rth: pd.DataFrame, signals: list[dict], strike_offset: int,
                  premium_stop_pct: float) -> dict:
    """Run real-fills for one (strike_offset, premium_stop_pct) cell."""
    overall = _Acc()
    by_side = {"C": _Acc(), "P": _Acc()}
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    no_data = 0
    rows_out: list[dict] = []

    for s in signals:
        fill = simulate_trade_real(
            entry_bar_idx=s["bar_idx"],
            entry_bar=s["bar"],
            spy_df=rth,
            ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["opening_range_fade", "failed_breakout",
                            "put_fade" if s["side"] == "P" else "call_fade"],
            side=s["side"],
            qty=QTY,
            setup="OPENING_RANGE_FADE",
            premium_stop_pct=premium_stop_pct,
            strike_offset=strike_offset,
        )
        if fill is None:
            no_data += 1
            continue
        pnl = float(fill.dollar_pnl)
        day = s["date"].isoformat()
        overall.add(pnl, day)
        by_side[s["side"]].add(pnl, day)
        by_sample["IS_2025" if s["date"].year == 2025 else "OOS_2026"].add(pnl, day)
        by_q[_quarter(s["date"])].add(pnl, day)
        rows_out.append({
            "date": day, "time": s["time"], "side": s["side"],
            "or_high": s["or_high"], "or_low": s["or_low"],
            "entry_spot": s["entry_spot"], "rejection_level": s["rejection_level"],
            "strike": fill.strike, "entry_premium": round(fill.entry_premium, 3),
            "pnl": round(pnl, 2),
            "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason),
        })

    q_reports = {k: by_q[k].report() for k in sorted(by_q)}
    pos_q = sum(1 for r in q_reports.values() if r.get("total_pnl", 0) and r["total_pnl"] > 0)

    # drop-top-5-DAYS per-trade on the OVERALL cut (deterministic self-verify)
    drop5_per_trade = None
    if overall.n > 0:
        day_pnls = sorted(overall.by_day.items(), key=lambda kv: kv[1], reverse=True)
        top5_days = {d for d, _ in day_pnls[:5]}
        kept_pnl = sum(v for d, v in overall.by_day.items() if d not in top5_days)
        # n excluding trades on the dropped days
        # (rebuild trade count on kept days from rows_out)
        kept_n = sum(1 for r in rows_out if r["date"] not in top5_days)
        drop5_per_trade = round(kept_pnl / kept_n, 2) if kept_n > 0 else None

    ov = overall.report()
    oos = by_sample["OOS_2026"].report()
    is_ = by_sample["IS_2025"].report()

    clears = bool(
        oos.get("n", 0) > 0 and oos.get("per_trade", -1) is not None
        and oos.get("per_trade", -1) > 0
        and pos_q >= MIN_POS_QUARTERS
        and (ov.get("top5_day_pct") is None or ov.get("top5_day_pct", 1e9) < MAX_TOP5_PCT)
        and ov.get("n", 0) >= MIN_N
        and drop5_per_trade is not None and drop5_per_trade > 0
    )

    return {
        "strike_offset": strike_offset,
        "premium_stop_pct": premium_stop_pct,
        "overall": ov,
        "by_side": {k: v.report() for k, v in by_side.items()},
        "by_sample": {"IS_2025": is_, "OOS_2026": oos},
        "by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{len(q_reports)}",
        "n_pos_quarters": pos_q,
        "n_quarters": len(q_reports),
        "drop_top5_days_per_trade": drop5_per_trade,
        "n_no_opra_data": no_data,
        "clears_bar": clears,
        "_rows": rows_out,
    }


def main() -> dict:
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, _vix = ar_runner.load_data(START, END)
    rth = _build_rth(spy_full)
    log.info("RTH bars: %d  days: %d", len(rth), rth["date"].nunique())

    signals = scan_signals(rth)
    if not signals:
        log.error("No signals -- aborting.")
    n_put = sum(1 for s in signals if s["side"] == "P")
    n_call = sum(1 for s in signals if s["side"] == "C")
    log.info("Signals: %d (PUT=%d, CALL=%d)", len(signals), n_put, n_call)

    cells: list[dict] = []
    for so in STRIKE_OFFSETS:
        for ps in PREMIUM_STOPS:
            cell = backtest_cell(rth, signals, so, ps)
            cells.append(cell)
            ov = cell["overall"]
            log.info("cell so=%+d ps=%.2f -> n=%s per_trade=%s OOS_pt=%s posQ=%s top5=%s drop5=%s clears=%s",
                     so, ps, ov.get("n"), ov.get("per_trade"),
                     cell["by_sample"]["OOS_2026"].get("per_trade"),
                     cell["positive_quarters"], ov.get("top5_day_pct"),
                     cell["drop_top5_days_per_trade"], cell["clears_bar"])

    # Pick "best": prefer cells that clear the bar; rank by OOS per-trade then overall per-trade.
    def _rank_key(c):
        oos_pt = c["by_sample"]["OOS_2026"].get("per_trade")
        ov_pt = c["overall"].get("per_trade")
        return (
            1 if c["clears_bar"] else 0,
            oos_pt if oos_pt is not None else -1e9,
            ov_pt if ov_pt is not None else -1e9,
        )

    cells_sorted = sorted(cells, key=_rank_key, reverse=True)
    best = cells_sorted[0]
    any_clears = any(c["clears_bar"] for c in cells)

    # Strip heavy per-cell row dumps from the non-best cells to keep the json lean;
    # keep the best cell's rows for audit.
    best_rows = best.pop("_rows", [])
    cells_summary = []
    for c in cells:
        c2 = {k: v for k, v in c.items() if k != "_rows"}
        cells_summary.append(c2)

    ov = best["overall"]
    oos = best["by_sample"]["OOS_2026"]
    best_cfg = f"strike_offset={best['strike_offset']}, premium_stop_pct={best['premium_stop_pct']}"

    if not any_clears:
        verdict = (
            "NO CANDIDATE CLEARS THE BAR. The opening_range_fade does not survive the "
            "real-fills / OOS / concentration gate across the swept grid. Best cell ("
            f"{best_cfg}) overall per-trade={ov.get('per_trade')} on n={ov.get('n')}, "
            f"OOS per-trade={oos.get('per_trade')}, positive_quarters={best['positive_quarters']}, "
            f"top5_day_pct={ov.get('top5_day_pct')}, drop-top5-per-trade="
            f"{best['drop_top5_days_per_trade']}. Per anti-pattern 2.10 this is reported "
            "as a non-survivor, not cherry-picked."
        )
    else:
        verdict = (
            f"CANDIDATE CLEARS THE BAR: {best_cfg}. overall per-trade={ov.get('per_trade')} "
            f"on n={ov.get('n')}, OOS per-trade={oos.get('per_trade')}, "
            f"positive_quarters={best['positive_quarters']}, top5_day_pct={ov.get('top5_day_pct')}, "
            f"drop-top5-per-trade={best['drop_top5_days_per_trade']}. Real OPRA fills (C1)."
        )

    summary = {
        "run_date": dt.date.today().isoformat(),
        "strategy": "opening_range_fade",
        "hypothesis": (
            "Fade the 30-min opening-range extreme on range/reversal days: poke above "
            "OR-high then close back inside -> PUT; poke below OR-low then close back "
            "inside -> CALL. Contrarian mirror of the ORB continuation."
        ),
        "sourced_rules": SOURCED_RULES,
        "sources": SOURCES,
        "published_edge_stat": "ORB-family success rate 40-60% (LiteFinance); no source publishes a clean SPY-0DTE single-leg per-trade $ expectancy for the fade -- measured here.",
        "window": f"{START}..{END}",
        "params": {
            "or_minutes": OR_MINUTES, "rth": "09:30-16:00 (per-day session-open anchored)",
            "late_entry_cutoff": LATE_ENTRY_CUTOFF.strftime("%H:%M"),
            "cooldown_min": COOLDOWN_MIN, "qty": QTY,
            "default_exits": "v15 (TP1 +30%/chart-level, runner 2.5x, 15:50 time stop)",
        },
        "n_signals": len(signals),
        "n_signals_put": n_put,
        "n_signals_call": n_call,
        "grid": {"strike_offset": STRIKE_OFFSETS, "premium_stop_pct": PREMIUM_STOPS},
        "acceptance_bar": {
            "oos_per_trade": ">0", "positive_quarters": f">={MIN_POS_QUARTERS}/6",
            "top5_day_pct": f"<{MAX_TOP5_PCT}", "n": f">={MIN_N}",
            "drop_top5_days_per_trade": ">0",
        },
        "any_cell_clears_bar": any_clears,
        "best_cell": {k: v for k, v in best.items()},
        "best_cell_rows": best_rows,
        "all_cells": cells_summary,
        "verdict": verdict,
        "DISCLOSURE": {
            "authority": "real OPRA fills via simulator_real.simulate_trade_real (C1)",
            "per_trade": "per-trade expectancy reported, NOT win-rate alone (OP-14)",
            "is_oos": "IS=2025, OOS=2026; both reported per cell",
            "concentration": "top5_day_pct + drop-top-5-DAYS per-trade reported (OP-20 #5)",
            "anti_cherry_pick": "anti-pattern 2.10 -- if the only positive cell is thin-N / high-concentration / OOS-negative, clears_bar=false and the verdict says so",
            "spy_vs_option": "SPY-price fade != option edge; this IS the option-edge test (C3)",
            "timezone": "OR anchored to each day's FIRST RTH bar (file TZ stamps inconsistent; ~36 early-2025 days shifted +1h). Contiguity-checked to skip gappy days (L57/L61).",
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    print("\n=== OPENING_RANGE_FADE — NEW-STRATEGY HUNT VERDICT ===")
    print(f"signals={len(signals)} (PUT={n_put} CALL={n_call})")
    print(f"any cell clears bar: {any_clears}")
    print(f"BEST cell: {best_cfg}")
    print(f"  overall : {ov}")
    print(f"  OOS 2026: {oos}")
    print(f"  IS  2025: {best['by_sample']['IS_2025']}")
    print(f"  pos_quarters={best['positive_quarters']}  drop-top5-per-trade={best['drop_top5_days_per_trade']}")
    print(f"VERDICT: {verdict}")
    return summary


if __name__ == "__main__":
    main()
