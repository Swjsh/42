"""NEW-STRATEGY HUNT: opening_gap_fade ("gap and crap" / gap-fill mean reversion).

The OPPOSITE of our gap_and_go (continuation). FADE the opening gap toward prior
close: down-gap -> buy CALL targeting the gap fill; up-gap -> buy PUT. 0DTE SPY
single-leg directional. Real-fills (C1) is the authority.

================================================================================
SOURCED RULES (STEP 1 — research, every URL cited; no invented rules)
================================================================================
Strategy = "Fading the Gap" / gap-fill mean reversion. Canonical rule set:

 * Gap definition: prior RTH close -> today's RTH open. Down-gap => fade UP (CALL);
   up-gap => fade DOWN (PUT).
   - mypivots "Fading the Gap": "a measure from the close of the previous trading
     session to the opening price of the following trading session's RTH."
 * Target = the gap FILL = prior day's close touched.
   - mypivots: exit "when a trading session's closing price has been touched during
     the following trading day."
 * Stops: the source FOUND STOPS INEFFECTIVE ("the optimum solution was to use such
   a large percentage that it was the equivalent of not using stops"); otherwise hold
   to fill or to EOD. -> maps to our loose-premium-stop arm (premium_stop_pct ~ -0.99,
   chart-stop-only) and the v15 15:50 time stop.
 * Fill rate by gap SIZE (smaller fills more often):
   - mypivots (ES points): ~76% of ALL gaps fill same-day RTH; 1pt->93%, 2pt->90%,
     3pt->82%; >15pt "Extreme Range" only ~35%. Half-gap fills ~80% for >2pt gaps.
   - SharePlanner / TradeThatSwing (SPY/QQQ %): <0.3-0.5% gaps fill ~70-90% same day;
     1-1.99% gaps ~45%; 2%+ gaps ~30-33%.
   - Quantified Strategies: fades every gap 0.1%-0.6%, target = 75% of the gap.
 * Direction asymmetry (down-gaps fill slightly more / bounce):
   - SharePlanner: "~47% of 1-2% down gaps filled intraday vs ~45% of up gaps";
     across all 1%+ declines "average open-to-close change is +0.21%" (a bounce),
     gap-ups average "-0.2%" (mild fade). => CALL (down-gap fade) edge >= PUT.
 * Inside-prior-range filter (strong gate):
   - search synthesis (ainvest/TradeThatSwing): gaps opening INSIDE the prior day's
     range fill ~70%; gaps opening OUTSIDE (above PDH / below PDL) only ~43-47%.
 * Regime: VIX > 25 -> intraday mean-reversion dominates, gap fills higher-prob
   (search synthesis). We log VIX bands; do NOT hard-gate (sample is mostly low-VIX).

SOURCES (cited in the JSON too):
  https://www.mypivots.com/article/details/43/fading-the-gap
  https://www.shareplanner.com/blog/strategies-for-trading/fading-the-gap-how-large-overnight-moves-in-spy-and-qqq-play-out-during-the-trading-day.html
  https://www.quantifiedstrategies.com/gap-fill-trading-strategies/
  https://tradethatswing.com/sp-500-spy-es-gap-fill-strategy-and-statistics/
  https://www.ainvest.com/news/500-gap-trade-edge-filter-small-volume-gaps-high-fill-setup-2604/

================================================================================
0DTE ADAPTATION (STEP 2 — signal on SPY 5m, causal, no look-ahead)
================================================================================
 * One signal per day (the opening gap is a once-daily event).
 * gap_pct = (today_open - prior_close) / prior_close, computed at the RTH open.
 * Entry on the FIRST RTH bar at/after the 09:35 ET engine gate (we use the bar whose
   time >= 09:35). The trigger bar is that bar; simulator_real fills on the NEXT bar's
   open (its built-in no-look-ahead rule). gap_pct uses only the 09:30 open + the
   already-known prior close -> fully causal.
 * Minimum gap magnitude filter swept (avoid noise gaps).
 * rejection_level = the invalidation = the opening extreme AGAINST the fade:
     - down-gap CALL: support = the session low up to & including the entry bar
       (if price keeps falling below the open low, the fade is wrong).
     - up-gap   PUT : resistance = the session high up to & including the entry bar.
   This makes the chart-stop meaningful (a fade that keeps going the gap's way = wrong).
 * Cooldown is moot (1/day) but we keep a guard for safety.

================================================================================
STEP 3 — REAL-FILLS sweep  |  STEP 4 — deterministic self-verify gate
================================================================================
Sweep strike_offset {-2,-1,0,1,2} x premium_stop_pct {-0.08,-0.20,-0.50,-0.99},
v15 default exits otherwise, qty=3. For EACH cell: overall/IS/OOS/by-quarter/top5.
For the BEST cell additionally: drop-top-5-days per-trade.

CANDIDATE bar (a cell clears ONLY if ALL hold):
   OOS per-trade > 0  AND  positive_quarters >= 4/6  AND  top5_day_pct < 200%
   AND  n >= 20  AND  drop-top-5-days per-trade > 0.

OP-20: report per-trade EXPECTANCY (not WR); IS/OOS; positive_quarters; top5+drop-top5.
Anti-pattern 2.10: if the only positive cell is thin-N / high-concentration / OOS-neg,
say so and set clears_bar=false. NO cherry-picking.

Pure Python, $0. Writes analysis/recommendations/newhunt-opening-gap-fade.json.
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

OUT_JSON = ROOT / "analysis" / "recommendations" / "newhunt-opening-gap-fade.json"

# ── Fixed params ────────────────────────────────────────────────────────────────
QTY = 3
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
ENTRY_GATE = dt.time(9, 35)          # v15 09:35 ET entry gate
COOLDOWN_MIN = 45                     # moot at 1/day; kept as a guard

# Gap magnitude band (fraction of prior close). Sourced bands:
#   QS fades 0.1%-0.6%; SharePlanner: <0.5% fills ~70-90%, >2% fills ~30%.
# We require a MINIMUM gap so we are not fading noise, and cap the MAX so we stay in
# the high-fill regime (avoid the "extreme range gap" ~35% bucket). Swept as a sub-cut.
GAP_MIN_PCT = 0.0015                  # 0.15% minimum (below this = noise, no clean gap)
GAP_MAX_PCT = 0.0150                  # 1.50% maximum (above = low-fill "run" regime)

# Sweep grid (STEP 3)
STRIKE_OFFSETS = [-2, -1, 0, 1, 2]
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]

SOURCES = [
    "https://www.mypivots.com/article/details/43/fading-the-gap",
    "https://www.shareplanner.com/blog/strategies-for-trading/fading-the-gap-how-large-overnight-moves-in-spy-and-qqq-play-out-during-the-trading-day.html",
    "https://www.quantifiedstrategies.com/gap-fill-trading-strategies/",
    "https://tradethatswing.com/sp-500-spy-es-gap-fill-strategy-and-statistics/",
    "https://www.ainvest.com/news/500-gap-trade-edge-filter-small-volume-gaps-high-fill-setup-2604/",
]


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


class _Acc:
    """Per-cut accumulator (mirrors confluence_real_fills_validate._Acc)."""
    __slots__ = ("n", "wins", "pnl", "by_day")

    def __init__(self) -> None:
        self.n = 0
        self.wins = 0
        self.pnl = 0.0
        self.by_day: dict[str, float] = defaultdict(float)

    def add(self, pnl: float, day: str) -> None:
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
            "avg_pnl": round(self.pnl / self.n, 1),   # per-trade EXPECTANCY (OP-14)
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


# ── STEP 2: build one gap-fade signal per trading day ───────────────────────────
def build_signals(rth: pd.DataFrame) -> list[dict]:
    """One causal opening-gap-fade signal per day.

    rth: RTH-filtered SPY frame with a 'date' column, sorted by timestamp.
    Returns signal dicts with the global rth index of the entry (trigger) bar.
    """
    rth = rth.reset_index(drop=True)
    # day -> list of global indices (already time-sorted)
    day_rows: dict[dt.date, list[int]] = defaultdict(list)
    for i, d in enumerate(rth["date"]):
        day_rows[d].append(i)
    ordered_days = sorted(day_rows.keys())

    signals: list[dict] = []
    last_sig_time: dt.datetime | None = None
    prev_close: float | None = None  # prior session's last RTH close

    for d in ordered_days:
        idxs = day_rows[d]
        if not idxs:
            continue
        today_open = float(rth["open"].iloc[idxs[0]])
        today_last_close = float(rth["close"].iloc[idxs[-1]])

        # Need a prior session close to define a gap. First day -> just seed prev_close.
        if prev_close is None or prev_close <= 0:
            prev_close = today_last_close
            continue

        gap_abs = today_open - prev_close
        gap_pct = gap_abs / prev_close

        # Find the entry (trigger) bar: first RTH bar at/after the 09:35 gate.
        entry_i: int | None = None
        for gi in idxs:
            t = rth["timestamp_et"].iloc[gi]
            tt = t.time() if hasattr(t, "time") else pd.Timestamp(t).time()
            if tt >= ENTRY_GATE:
                entry_i = gi
                break
        if entry_i is None:
            prev_close = today_last_close
            continue

        # Gap magnitude band gate (sourced: high-fill regime only).
        if abs(gap_pct) < GAP_MIN_PCT or abs(gap_pct) > GAP_MAX_PCT:
            prev_close = today_last_close
            continue

        # Direction: FADE the gap toward prior close.
        if gap_pct < 0:
            side = "C"            # down-gap -> buy CALL (fade up to fill)
            direction = "down_gap_fade_long"
        else:
            side = "P"            # up-gap -> buy PUT (fade down to fill)
            direction = "up_gap_fade_short"

        # rejection_level = opening extreme AGAINST the fade, measured ONLY on bars
        # up to & including the entry bar (causal). For a CALL: session low so far
        # (support; if price breaks below, the fade failed). For a PUT: session high.
        upto = [gi for gi in idxs if gi <= entry_i]
        sess_low = float(rth["low"].iloc[upto].min())
        sess_high = float(rth["high"].iloc[upto].max())
        rejection_level = sess_low if side == "C" else sess_high

        entry_time = rth["timestamp_et"].iloc[entry_i]
        et_naive = (entry_time.tz_localize(None) if getattr(entry_time, "tz", None) is not None
                    else pd.Timestamp(entry_time)).to_pydatetime()

        # Cooldown guard (1/day so always passes, but defensive).
        if last_sig_time is not None and (et_naive - last_sig_time).total_seconds() / 60.0 < COOLDOWN_MIN:
            prev_close = today_last_close
            continue
        last_sig_time = et_naive

        # Did the gap actually fill same-day RTH? (descriptive stat only; not a filter)
        if side == "C":
            filled = today_last_close >= prev_close or float(rth["high"].iloc[idxs].max()) >= prev_close
        else:
            filled = today_last_close <= prev_close or float(rth["low"].iloc[idxs].min()) <= prev_close

        signals.append({
            "idx": entry_i,
            "date": d,
            "side": side,
            "direction": direction,
            "gap_pct": round(gap_pct * 100, 3),       # report in %
            "gap_abs": round(gap_abs, 2),
            "prev_close": round(prev_close, 2),
            "today_open": round(today_open, 2),
            "rejection_level": round(rejection_level, 2),
            "entry_spot": round(float(rth["close"].iloc[entry_i]), 2),
            "time": et_naive.strftime("%H:%M"),
            "gap_filled_sameday": bool(filled),
        })

        prev_close = today_last_close

    return signals


# ── VIX alignment (ffill), same approach as the reference scripts ───────────────
def _vix_series(vix_full: pd.DataFrame, rth: pd.DataFrame) -> list[float]:
    vix_full = vix_full.copy()
    vix_full["timestamp_et"] = pd.to_datetime(
        vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index)
    vix_ser = (vix_full.set_index("timestamp_et")["close"]
               if "close" in vix_full.columns else vix_full.iloc[:, 0])
    rth_naive = (rth["timestamp_et"].dt.tz_localize(None)
                 if rth["timestamp_et"].dt.tz is not None else rth["timestamp_et"])
    out: list[float] = []
    for ts in rth_naive:
        try:
            j = vix_ser.index.get_indexer([ts], method="ffill")[0]
            out.append(float(vix_ser.iloc[j]) if j >= 0 else 17.0)
        except Exception:
            out.append(17.0)
    return out


# ── STEP 3: one full pass for a given (strike_offset, premium_stop_pct) cell ────
def run_cell(rth: pd.DataFrame, signals: list[dict], vix_arr: list[float],
             strike_offset: int, premium_stop_pct: float) -> dict:
    overall = _Acc()
    by_side = {"C": _Acc(), "P": _Acc()}
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    no_data = 0
    rows: list[dict] = []

    for s in signals:
        fill = simulate_trade_real(
            entry_bar_idx=s["idx"],
            entry_bar=rth.iloc[s["idx"]],
            spy_df=rth,
            ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["opening_gap_fade", s["direction"]],
            side=s["side"],
            qty=QTY,
            setup="OPENING_GAP_FADE",
            premium_stop_pct=premium_stop_pct,
            strike_offset=strike_offset,
        )
        if fill is None:
            no_data += 1
            continue
        pnl = fill.dollar_pnl
        day = s["date"].isoformat()
        overall.add(pnl, day)
        by_side[s["side"]].add(pnl, day)
        by_sample["IS_2025" if s["date"].year == 2025 else "OOS_2026"].add(pnl, day)
        by_q[_quarter(s["date"])].add(pnl, day)
        rows.append({
            "date": day, "time": s["time"], "side": s["side"],
            "direction": s["direction"], "gap_pct": s["gap_pct"],
            "strike": fill.strike, "entry_premium": round(fill.entry_premium, 3),
            "pnl": round(pnl, 2),
            "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason),
        })

    q_reports = {k: by_q[k].report() for k in sorted(by_q)}
    pos_q = sum(1 for r in q_reports.values() if r.get("total_pnl", 0) and r["total_pnl"] > 0)
    return {
        "strike_offset": strike_offset,
        "premium_stop_pct": premium_stop_pct,
        "n_completed": overall.n,
        "n_no_opra_data": no_data,
        "overall": overall.report(),
        "by_side": {k: v.report() for k, v in by_side.items()},
        "by_sample": {k: v.report() for k, v in by_sample.items()},
        "by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{len(q_reports)}",
        "_pos_q_count": pos_q,
        "_n_quarters": len(q_reports),
        "_rows": rows,                    # kept internal; only best cell's rows persisted
        "_overall_acc": overall,          # kept internal for drop-top5
    }


# ── STEP 4: deterministic self-verify on the best cell ─────────────────────────
def _drop_top5_from_rows(rows: list[dict]) -> tuple[float | None, float | None, int]:
    """(drop_top5_per_trade, top5_day_pct, n_after) computed from the per-trade rows.

    Exact: aggregate to day P&L, drop the 5 highest-P&L days entirely (all their
    trades), recompute per-trade expectancy on what remains.
    """
    if not rows:
        return None, None, 0
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(r["pnl"])
    day_pnl = {d: sum(v) for d, v in by_day.items()}
    total = sum(day_pnl.values())
    top5_days = [d for d, _ in sorted(day_pnl.items(), key=lambda kv: kv[1], reverse=True)[:5]]
    top5_sum = sum(day_pnl[d] for d in top5_days)
    top5_pct = round(100 * top5_sum / total, 0) if total > 0 else None
    remaining = [p for r in rows if r["date"] not in set(top5_days) for p in [r["pnl"]]]
    if not remaining:
        return None, top5_pct, 0
    return round(sum(remaining) / len(remaining), 1), top5_pct, len(remaining)


def run() -> dict:
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= RTH_OPEN)
                   & (spy_full["timestamp_et"].dt.time < RTH_CLOSE)].reset_index(drop=True)
    rth["date"] = rth["timestamp_et"].dt.date
    log.info("RTH bars: %d", len(rth))

    vix_arr = _vix_series(vix_full, rth)

    signals = build_signals(rth)
    n_filled = sum(1 for s in signals if s["gap_filled_sameday"])
    n_down = sum(1 for s in signals if s["side"] == "C")
    n_up = sum(1 for s in signals if s["side"] == "P")
    log.info("Signals: %d (down-gap CALL=%d, up-gap PUT=%d). Same-day gap-fill rate: %.1f%%",
             len(signals), n_down, n_up, 100 * n_filled / len(signals) if signals else 0)

    # ── STEP 3: sweep the grid ──────────────────────────────────────────────────
    cells: list[dict] = []
    for so in STRIKE_OFFSETS:
        for ps in PREMIUM_STOPS:
            cell = run_cell(rth, signals, vix_arr, so, ps)
            ov = cell["overall"]
            log.info("cell so=%+d ps=%.2f  n=%s avg=$%s OOS=%s posQ=%s top5=%s%%",
                     so, ps, ov.get("n"), ov.get("avg_pnl"),
                     cell["by_sample"]["OOS_2026"].get("avg_pnl"),
                     cell["positive_quarters"], ov.get("top5_day_pct"))
            cells.append(cell)

    # ── STEP 4: deterministic gate-check on EVERY cell (no cherry-picking) ───────
    # Compute the full candidate gate for each cell, then SELECT honestly:
    #   - if any cell clears ALL gates, pick the gate-clearing cell with the highest
    #     OOS per-trade (the gates are the bar; OOS expectancy is the tiebreak);
    #   - else pick the best-overall-per-trade cell purely for DISCLOSURE (and report
    #     it as clears_bar=false). This prevents both (a) missing a real candidate that
    #     isn't top-overall and (b) anti-pattern 2.10 cherry-picking a concentrated cell.
    for c in cells:
        d5, t5, na = _drop_top5_from_rows(c["_rows"])
        oos_c = c["by_sample"]["OOS_2026"]
        oos_pt_c = oos_c.get("avg_pnl") if oos_c.get("n") else None
        n_c = c["overall"].get("n", 0)
        pq_c = c["_pos_q_count"]
        c["_drop_top5_pt"] = d5
        c["_top5_pct"] = t5
        c["_n_after_drop"] = na
        c["_oos_pt"] = oos_pt_c
        c["_clears"] = bool(
            oos_pt_c is not None and oos_pt_c > 0
            and pq_c >= 4
            and (t5 is not None and t5 < 200)
            and n_c >= 20
            and (d5 is not None and d5 > 0)
        )

    clearing = [c for c in cells if c["_clears"]]
    if clearing:
        best = max(clearing, key=lambda c: (c["_oos_pt"] or -1e9))
    else:
        best = max(cells, key=lambda c: (c["overall"].get("avg_pnl") or -1e9))

    drop_top5_pt = best["_drop_top5_pt"]
    top5_pct = best["_top5_pct"]
    n_after = best["_n_after_drop"]
    oos = best["by_sample"]["OOS_2026"]
    oos_pt = best["_oos_pt"]
    overall_pt = best["overall"].get("avg_pnl")
    n = best["overall"].get("n", 0)
    pos_q = best["_pos_q_count"]
    clears = best["_clears"]

    # Honesty (anti-pattern 2.10): also flag if the best cell is OOS-thin.
    oos_thin = (oos.get("n", 0) < 10)

    verdict_bits = []
    if oos_pt is None or oos_pt <= 0:
        verdict_bits.append("OOS per-trade <= 0")
    if pos_q < 4:
        verdict_bits.append(f"only {pos_q}/6 positive quarters")
    if top5_pct is None or top5_pct >= 200:
        verdict_bits.append(f"top5 concentration {top5_pct}% >= 200%")
    if n < 20:
        verdict_bits.append(f"n={n} < 20")
    if drop_top5_pt is None or drop_top5_pt <= 0:
        verdict_bits.append("drop-top-5-days per-trade <= 0")
    if oos_thin:
        verdict_bits.append(f"OOS n={oos.get('n', 0)} is thin (<10)")

    if clears:
        verdict = ("REAL CANDIDATE — opening_gap_fade clears all gates "
                   "(OOS+, >=4/6 quarters, top5<200%, n>=20, survives drop-top-5).")
    else:
        verdict = ("NOT A CANDIDATE — opening_gap_fade fails: "
                   + "; ".join(verdict_bits) + ". Per anti-pattern 2.10, not promoting.")

    log.info("BEST cell: so=%+d ps=%.2f  overall_pt=$%s OOS_pt=$%s posQ=%d/6 top5=%s%% "
             "drop_top5_pt=$%s n=%d  -> clears=%s",
             best["strike_offset"], best["premium_stop_pct"], overall_pt, oos_pt,
             pos_q, top5_pct, drop_top5_pt, n, clears)

    # Strip internal keys before serializing the grid.
    def _clean(c: dict) -> dict:
        return {k: v for k, v in c.items() if not k.startswith("_")}

    summary = {
        "run_date": dt.date.today().isoformat(),
        "strategy": "opening_gap_fade",
        "hypothesis": ("Fade the opening gap toward prior close (gap-fill / 'gap and crap'); "
                       "down-gap -> buy CALL, up-gap -> buy PUT. OPPOSITE of gap_and_go."),
        "window": f"{START}..{END}",
        "sourced_rules": (
            "Gap = prior RTH close -> today RTH open; fade toward prior close. "
            "Target = gap fill (prior close touched). Stops found ineffective by source "
            "-> loose-premium-stop arm + v15 15:50 time stop. Smaller gaps fill more "
            "(~76% all gaps; 1-2pt ES ~90-93%; <0.5% SPY ~70-90%; 2%+ ~30%). Down-gaps "
            "fill slightly more than up-gaps. Gap band gated to "
            + f"{GAP_MIN_PCT * 100:.2f}%-{GAP_MAX_PCT * 100:.2f}% "
            + "(high-fill regime, avoid extreme-range run bucket)."
        ),
        "sources": SOURCES,
        "params_fixed": {
            "qty": QTY, "entry_gate_et": ENTRY_GATE.strftime("%H:%M"),
            "gap_min_pct": GAP_MIN_PCT, "gap_max_pct": GAP_MAX_PCT,
            "rejection_level": "opening extreme against the fade (causal, up to entry bar)",
            "exits": "v15 defaults (tp1 0.50 / runner 2.5x / 15:50 time stop / chandelier off)",
        },
        "sweep_grid": {"strike_offset": STRIKE_OFFSETS, "premium_stop_pct": PREMIUM_STOPS},
        "n_signals": len(signals),
        "n_down_gap_call": n_down,
        "n_up_gap_put": n_up,
        "sameday_gap_fill_rate_pct": round(100 * n_filled / len(signals), 1) if signals else None,
        "best_cell": {
            "strike_offset": best["strike_offset"],
            "premium_stop_pct": best["premium_stop_pct"],
            "overall": best["overall"],
            "by_side": best["by_side"],
            "by_sample": best["by_sample"],
            "by_quarter": best["by_quarter"],
            "positive_quarters": best["positive_quarters"],
        },
        "self_verify": {
            "overall_per_trade": overall_pt,
            "oos_per_trade": oos_pt,
            "positive_quarters": f"{pos_q}/6",
            "top5_day_pct": top5_pct,
            "drop_top5_per_trade": drop_top5_pt,
            "n_after_drop_top5": n_after,
            "n_trades": n,
            "oos_thin_flag": oos_thin,
            "gates": {
                "oos_per_trade_gt_0": bool(oos_pt is not None and oos_pt > 0),
                "positive_quarters_ge_4": bool(pos_q >= 4),
                "top5_lt_200pct": bool(top5_pct is not None and top5_pct < 200),
                "n_ge_20": bool(n >= 20),
                "drop_top5_gt_0": bool(drop_top5_pt is not None and drop_top5_pt > 0),
            },
        },
        "clears_bar": clears,
        "n_cells_clearing_all_gates": len(clearing),
        "verdict": verdict,
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) — SPY-direction gap-fill rate != option edge (C3/L58)",
            "per_trade": "avg_pnl is per-trade EXPECTANCY, not WR alone (OP-14)",
            "concentration": "top5_day_pct + drop-top-5-days per-trade reported (OP-20 #5)",
            "is_oos": "IS=2025, OOS=2026-to-05-15 (OP-11)",
            "anti_pattern_2_10": ("ranking selects the top per-trade cell, but a cell is only a "
                                  "REAL CANDIDATE if it clears every gate; a thin-N / "
                                  "high-concentration / OOS-negative best cell is reported as "
                                  "clears_bar=false (no cherry-picking)."),
            "option_data_caveat": ("OPRA cache holds ATM +/-5 strikes/day; strike_offset cells far "
                                   "from ATM may return NO_OPRA_DATA (counted, excluded)."),
        },
        "full_grid": [_clean(c) for c in cells],
        "best_cell_trades": best["_rows"],
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    print("\n=== OPENING_GAP_FADE — NEW-STRATEGY HUNT VERDICT ===")
    print(f"signals={len(signals)}  down-gap CALL={n_down}  up-gap PUT={n_up}")
    print(f"same-day gap-fill rate (SPY price)={summary['sameday_gap_fill_rate_pct']}%")
    print(f"BEST cell: strike_offset={best['strike_offset']} premium_stop={best['premium_stop_pct']}")
    print(f"  overall per-trade=${overall_pt}  OOS per-trade=${oos_pt}  n={n}")
    print(f"  positive_quarters={pos_q}/6  top5={top5_pct}%  drop-top5 per-trade=${drop_top5_pt}")
    print(f"CLEARS BAR: {clears}")
    print(f"VERDICT: {verdict}")
    return summary


if __name__ == "__main__":
    run()
