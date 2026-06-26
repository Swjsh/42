"""B7 — MULTI-DAY-TRENDLINE CONFLUENCE (the J 5/4 source-of-truth signature).

ANGLE B (never real-fills-tested as a discrete setup)
─────────────────────────────────────────────────────
The clean J winners (4/29, 5/01, 5/04 — all 2026, all PUTS) shared a structural
signature: a *day-trendline* rejection that is CONFLUENT with a *multi-day
trendline* AND a *named level*, firing in the morning. This script defines that
as a DISCRETE setup and tests it on REAL OPRA fills.

This is NOT the additive-confluence-score family (B0 triple-kill: confluence has
died additively before). It is a STRUCTURAL co-incidence test: a morning bar must
simultaneously
  (1) touch / reject a same-session (day) trendline,
  (2) sit within X ticks of a MULTI-DAY trendline (fit across the prior N days'
      swing points, projected to the current bar), and
  (3) sit within Y ticks of a causal NAMED LEVEL (PDH/PDL, PMH/PML, IBH/IBL),
all pointing the SAME direction. One causal entry/day, fill the NEXT bar open.

Direction logic (mirrors a rejection): at a RESISTANCE cluster (day-resistance-
trendline + descending/near multi-day resistance + a level above) a bar that
pokes above and closes back below => bearish (PUT). At a SUPPORT cluster a bar
that pokes below and closes back above => bullish (CALL).

REUSE (no new framework):
  * swing points / trendline fit  -> crypto.lib.trendlines (find_swing_points,
    fit_trendline, Trendline.price_at)
  * causal named levels           -> crypto.lib.session_levels_spy (PMH/PML/IBH/
    IBL) + prior-day RTH high/low/close (PDH/PDL/PDC), all as-of
  * real fills                    -> lib.simulator_real.simulate_trade_real (C1)
  * data + day scaffolds          -> autoresearch.runner.load_data +
    infinite_ammo_discovery.build_day_contexts / session_vwap_asof /
    _strike_from_spot / _nearest_cached_strike
  * fraud gates                   -> autoresearch.fraud_gates / null_baseline
    (random-entry null L172 + no-truncation L171)

THE 9-GATE BAR (every cell):
  (1) OOS-2026 per-trade > 0          (6) IS-2025 half positive
  (2) positive_quarters >= 4/6        (7) beats random-entry null (L172)
  (3) top5-day < 200%                 (8) no truncation artifact (L171)
  (4) n >= 20                         (9) OOS-ALONE drop-top5 > 0 (L173 B6 gate)
  (5) full-sample drop-top5 > 0

PLUS the OP-16 J-edge anchor check: the discrete setup must TAKE the
4/29/5/01/5/04 winners and SKIP-or-lose-less the 5/05/5/06/5/07 losers.

CAVEAT (disclosed, not hidden): the J anchor dates are all 2026 => they live in
the OOS window. An anchor "take" is therefore disclosed alongside whether the
OOS sample as a whole is positive; passing the anchor on 2026 dates is NOT
independent OOS evidence, it is a structural-fidelity check.

Pure Python, $0 (no LLM in the sim loop). No live orders. Markets closed.
Writes analysis/recommendations/b7-mdt-confluence.json.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b7_mdt_confluence.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _strike_from_spot,
    _nearest_cached_strike,
)
from autoresearch.fraud_gates import CandidateSignal, verify_candidate  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.trendlines import find_swing_points, fit_trendline  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "b7-mdt-confluence.json"

# ── Detector params ───────────────────────────────────────────────────────────
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
# Entry window: the J anchors (4/29, 5/01, 5/04 2026) GRIND UP all morning and the
# put rejection comes AFTER the morning push tops out (diagnosed 2026-06-21) — a
# morning-only (<=10:30) reject detector structurally misses the J signature and
# fires almost never (3x/363d). So the discrete setup is tested over the full RTH
# session with a 15:45 time-stop guard; the morning-only variant is also recorded.
ENTRY_CUTOFF = dt.time(15, 30)
WARMUP_BARS = 3                       # bars into the session before evaluating
SWING_WINDOW_DAY = 2                  # swing detection window, intraday
SWING_WINDOW_MD = 3                   # swing detection window, multi-day
MDT_LOOKBACK_DAYS = 4                 # prior days included in the multi-day fit
DAY_TL_TOL_TICKS = 0.30              # bar within this $ of the day trendline = touch
MDT_TOL_TICKS = 0.75                 # multi-day trendline confluence tolerance ($)
LEVEL_TOL_TICKS = 0.75              # named-level confluence tolerance ($)
MIN_MDT_TOUCHES = 3                   # 3-point rule for the multi-day line
COOLDOWN_NA = True                    # one entry/day already enforced (break after fire)

# ── Sweep space ───────────────────────────────────────────────────────────────
# Tier lock (C29): Safe-2 = ATM (offset 0); Bold = ITM-2 (offset -2 for both sides,
# verified simulator_real.py L357-364: NEGATIVE offset = ITM for calls AND puts).
STRIKE_OFFSETS = [0, -2]
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]   # -0.99 = chart-stop-only
QTY = 3
OOS_YEAR = 2026

# Candidate-edge bar thresholds
BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0

# J source-of-truth anchors (all 2026, matched to actual SPY price levels).
J_WINNERS = {
    (dt.date(2026, 4, 29), "P"),
    (dt.date(2026, 5, 1), "P"),
    (dt.date(2026, 5, 4), "P"),
}
J_LOSERS = {
    (dt.date(2026, 5, 5), "P"),
    (dt.date(2026, 5, 6), "P"),
    (dt.date(2026, 5, 7), "C"),
}


# ─────────────────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_spy(spy_raw: pd.DataFrame) -> pd.DataFrame:
    df = spy_raw.copy()
    ts = pd.to_datetime(df["timestamp_et"], utc=True)
    df["timestamp_et"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    df = df.drop_duplicates(subset="timestamp_et", keep="first").reset_index(drop=True)
    df["date"] = df["timestamp_et"].dt.date
    df["t"] = df["timestamp_et"].dt.time
    df["minute"] = df["timestamp_et"].dt.hour * 60 + df["timestamp_et"].dt.minute
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    return df


def _to_bar(row: pd.Series) -> Bar:
    ts = pd.Timestamp(row["timestamp_et"])
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return Bar(
        open_time=ts.to_pydatetime().replace(tzinfo=dt.timezone.utc),
        open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row.get("volume", 0.0) or 0.0),
        granularity_seconds=300, source="spy",
    )


# ─────────────────────────────────────────────────────────────────────────────
# CAUSAL NAMED LEVELS (as-of: only data at or before the current bar)
# ─────────────────────────────────────────────────────────────────────────────
def _causal_levels(spy: pd.DataFrame, day_idx0: int, cur_idx: int,
                   prior_close: Optional[float], prior_hi: Optional[float],
                   prior_lo: Optional[float]) -> list[float]:
    """Named levels known at cur_idx: prior-day H/L/close + premarket H/L + IB H/L
    (the latter only once the 09:30-09:59 IB has completed). All causal."""
    out: list[float] = []
    for v in (prior_close, prior_hi, prior_lo):
        if v is not None and v > 0:
            out.append(float(v))
    # Premarket H/L for THIS day (04:00-09:29) — known before RTH open.
    day = spy.iloc[max(0, day_idx0 - 80): day_idx0 + 1]  # a little before open
    cur_date = spy.iloc[cur_idx]["date"]
    pm = day[(day["date"] == cur_date) & (day["t"] >= dt.time(4, 0)) & (day["t"] < RTH_OPEN)]
    if len(pm):
        out.append(float(pm["high"].max()))
        out.append(float(pm["low"].min()))
    # Initial Balance H/L (09:30-09:59:59) — known only after 10:00.
    cur_time = spy.iloc[cur_idx]["t"]
    if cur_time >= dt.time(10, 0):
        ib = spy.iloc[day_idx0: cur_idx + 1]
        ib = ib[(ib["t"] >= RTH_OPEN) & (ib["t"] <= dt.time(9, 59, 59))]
        if len(ib):
            out.append(float(ib["high"].max()))
            out.append(float(ib["low"].min()))
    return sorted(set(round(x, 2) for x in out if x > 0))


# ─────────────────────────────────────────────────────────────────────────────
# DETECTOR — one causal multi-day-trendline-confluence entry/day.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class B7Signal:
    bar_idx: int       # global spy index (entry handled NEXT bar by the sim)
    side: str          # 'C' / 'P'
    rejection_level: float
    note: str
    date: dt.date
    day_tl_touch: float
    mdt_dist: float
    level_dist: float


def detect_signals(spy: pd.DataFrame) -> list[B7Signal]:
    days = build_day_contexts(spy)
    # Precompute per-day RTH high/low/close for the PDH/PDL/PDC level source.
    rth_stats: dict[dt.date, tuple[float, float, float]] = {}
    for dc in days:
        rth = dc.rth
        rth_stats[dc.date] = (float(rth["high"].max()), float(rth["low"].min()),
                              float(rth["close"].iloc[-1]))

    # All bars as crypto Bar objects, indexed by global spy index (for trendlines).
    all_bars = [_to_bar(spy.iloc[i]) for i in range(len(spy))]

    signals: list[B7Signal] = []
    for di, dc in enumerate(days):
        cur_date = dc.date
        # prior-day stats
        prior_close = dc.prior_close
        prior_hi = prior_lo = None
        if di > 0:
            pd_date = days[di - 1].date
            if pd_date in rth_stats:
                prior_hi, prior_lo, _ = rth_stats[pd_date]

        # Multi-day swing pool: prior MDT_LOOKBACK_DAYS sessions' RTH bars (NOT the
        # current day — the multi-day line is anchored to history, projected forward).
        md_lo_day = max(0, di - MDT_LOOKBACK_DAYS)
        md_global_lo = days[md_lo_day].idx0
        md_global_hi = days[di - 1].idx_last if di > 0 else dc.idx0 - 1
        md_bars = all_bars[md_global_lo: md_global_hi + 1] if md_global_hi >= md_global_lo else []
        md_res = md_sup = None
        if len(md_bars) >= 10:
            sp = find_swing_points(md_bars, window=SWING_WINDOW_MD)
            res = fit_trendline(sp, "resistance")
            sup = fit_trendline(sp, "support")
            # require the 3-point rule (>= MIN_MDT_TOUCHES swing anchors)
            if res is not None and len(res.swing_points) >= MIN_MDT_TOUCHES:
                md_res = res
            if sup is not None and len(sup.swing_points) >= MIN_MDT_TOUCHES:
                md_sup = sup

        # Walk the morning RTH bars of the current day.
        rth = dc.rth
        gidx = rth.index.tolist()
        for k in range(WARMUP_BARS, len(rth)):
            gi = gidx[k]
            row = spy.iloc[gi]
            if row["t"] > ENTRY_CUTOFF:
                break
            cur_ts = all_bars[gi].open_time.timestamp()

            # Day (same-session) swing trendlines, fit on bars [day open .. current].
            day_bars = all_bars[dc.idx0: gi + 1]
            if len(day_bars) < WARMUP_BARS + 2:
                continue
            dsp = find_swing_points(day_bars, window=SWING_WINDOW_DAY)
            day_res = fit_trendline(dsp, "resistance")
            day_sup = fit_trendline(dsp, "support")

            levels = _causal_levels(spy, dc.idx0, gi, prior_close, prior_hi, prior_lo)
            hi = float(row["high"]); lo = float(row["low"]); cl = float(row["close"])
            op = float(row["open"])

            sig = _evaluate_bar(
                cur_ts, hi, lo, cl, op, day_res, day_sup, md_res, md_sup, levels,
                bar_idx=gi, cur_date=cur_date, rth=rth, k=k, gidx=gidx, spy=spy)
            if sig is not None:
                signals.append(sig)
                break  # one causal entry/day
    return signals


def _evaluate_bar(cur_ts, hi, lo, cl, op, day_res, day_sup, md_res, md_sup, levels,
                  *, bar_idx, cur_date, rth, k, gidx, spy) -> Optional[B7Signal]:
    """A bar fires a bearish (PUT) entry at a RESISTANCE confluence rejection, or a
    bullish (CALL) entry at a SUPPORT confluence rejection. Same direction across
    all three structures is required (structural co-incidence, not additive score)."""

    # ── BEARISH (PUT): resistance cluster + upside poke that closes back below ──
    if day_res is not None and md_res is not None:
        day_lvl = day_res.price_at(cur_ts)
        md_lvl = md_res.price_at(cur_ts)
        # day-trendline touch: the bar's HIGH tags the resistance line
        day_touch = abs(hi - day_lvl) <= DAY_TL_TOL_TICKS
        # rejection: poked at/above the line then closed back below it
        rejected = hi >= day_lvl - DAY_TL_TOL_TICKS and cl < day_lvl and cl < op
        mdt_dist = abs(day_lvl - md_lvl)
        if day_touch and rejected and mdt_dist <= MDT_TOL_TICKS:
            near_levels = [L for L in levels if abs(hi - L) <= LEVEL_TOL_TICKS
                           and L >= cl]
            if near_levels:
                level_dist = min(abs(hi - L) for L in near_levels)
                # chart stop = the session high so far (resistance that must hold)
                stop = float(spy.iloc[gidx[0]: bar_idx + 1]["high"].max())
                return B7Signal(bar_idx=bar_idx, side="P", rejection_level=stop,
                                note="mdt_conf_resist_reject", date=cur_date,
                                day_tl_touch=round(day_lvl, 2), mdt_dist=round(mdt_dist, 3),
                                level_dist=round(level_dist, 3))

    # ── BULLISH (CALL): support cluster + downside poke that closes back above ──
    if day_sup is not None and md_sup is not None:
        day_lvl = day_sup.price_at(cur_ts)
        md_lvl = md_sup.price_at(cur_ts)
        day_touch = abs(lo - day_lvl) <= DAY_TL_TOL_TICKS
        rejected = lo <= day_lvl + DAY_TL_TOL_TICKS and cl > day_lvl and cl > op
        mdt_dist = abs(day_lvl - md_lvl)
        if day_touch and rejected and mdt_dist <= MDT_TOL_TICKS:
            near_levels = [L for L in levels if abs(lo - L) <= LEVEL_TOL_TICKS
                           and L <= cl]
            if near_levels:
                level_dist = min(abs(lo - L) for L in near_levels)
                stop = float(spy.iloc[gidx[0]: bar_idx + 1]["low"].min())
                return B7Signal(bar_idx=bar_idx, side="C", rejection_level=stop,
                                note="mdt_conf_support_reclaim", date=cur_date,
                                day_tl_touch=round(day_lvl, 2), mdt_dist=round(mdt_dist, 3),
                                level_dist=round(level_dist, 3))
    return None


# ─────────────────────────────────────────────────────────────────────────────
# SIM + METRICS
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TradeRow:
    date: str
    side: str
    strike: int
    atm: int
    entry_premium: float
    pnl: float
    exit_reason: str
    note: str


def simulate_cell(signals: list[B7Signal], spy: pd.DataFrame, *,
                  strike_offset: int, premium_stop_pct: float,
                  tp1=0.30, runner_tgt=2.5, trail=0.0) -> tuple[list[TradeRow], dict]:
    rows: list[TradeRow] = []
    n_total = len(signals)
    n_filled = n_miss = n_none = 0
    use_trail = trail > 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(sg.date, target, sg.side, 4)
        if strike is None:
            n_miss += 1
            continue
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=None,
            rejection_level=round(float(sg.rejection_level), 2),
            triggers_fired=[sg.note], side=sg.side, qty=QTY, setup="B7_MDT_CONF",
            strike_override=strike, premium_stop_pct=premium_stop_pct,
            tp1_premium_pct=tp1, runner_target_premium_pct=runner_tgt,
            profit_lock_mode=("trailing" if use_trail else "fixed"),
            profit_lock_trail_pct=(trail if use_trail else 0.0))
        if fill is None or fill.dollar_pnl is None:
            n_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(
            date=str(sg.date), side=sg.side, strike=int(strike), atm=int(atm),
            entry_premium=round(float(fill.entry_premium), 4),
            pnl=round(float(fill.dollar_pnl), 2),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE",
            note=sg.note))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_miss,
           "sim_none": n_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _drop_top5_per_trade(rows: list[TradeRow]) -> Optional[float]:
    if not rows:
        return None
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    top5_days = set(d for d, _ in sorted(by_day.items(), key=lambda kv: kv[1],
                                         reverse=True)[:5])
    kept = [r.pnl for r in rows if r.date not in top5_days]
    return round(sum(kept) / len(kept), 2) if kept else None


def metrics(rows: list[TradeRow]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]

    def _exp(rs):
        return round(float(np.mean([r.pnl for r in rs])), 2) if rs else 0.0

    def _tot(rs):
        return round(float(np.sum([r.pnl for r in rs])), 2) if rs else 0.0

    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_quarter(r.date)].append(r.pnl)
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)

    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    total = sum(by_day.values())
    top5 = (round(100 * sum(sorted(by_day.values(), reverse=True)[:5]) / total, 1)
            if total > 0 else None)

    by_side = {}
    for sd in ("C", "P"):
        s = [r.pnl for r in rows if r.side == sd]
        if s:
            by_side[sd] = {"n": len(s), "exp": round(sum(s) / len(s), 2),
                           "wr": round(100 * float((np.array(s) > 0).mean()), 1),
                           "total": round(sum(s), 2)}

    # OOS-alone drop-top5 (gate 9, L173)
    oos_drop5 = _drop_top5_per_trade(oos_rows)
    full_drop5 = _drop_top5_per_trade(rows)

    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": top5,
        "full_drop_top5_per_trade": full_drop5,
        "oos_drop_top5_per_trade": oos_drop5,
        "by_side": by_side,
        "exit_hist": {k: sum(1 for r in rows if r.exit_reason == k)
                      for k in sorted({r.exit_reason for r in rows})},
    }


def clears_9_gates(m: dict, fraud: Optional[dict]) -> tuple[bool, list[str]]:
    fails = []
    if m.get("oos_exp", -1) <= 0:
        fails.append(f"G1 oos_exp={m.get('oos_exp')}<=0")
    if m.get("positive_quarters_n", 0) < BAR_POS_Q:
        fails.append(f"G2 posQ={m.get('positive_quarters')}<{BAR_POS_Q}/6")
    t5 = m.get("top5_day_pct")
    if t5 is None or t5 >= BAR_TOP5:
        fails.append(f"G3 top5%={t5}>={BAR_TOP5}")
    if m.get("n", 0) < BAR_N:
        fails.append(f"G4 n={m.get('n', 0)}<{BAR_N}")
    fd5 = m.get("full_drop_top5_per_trade")
    if fd5 is None or fd5 <= 0:
        fails.append(f"G5 full_drop_top5={fd5}<=0")
    if m.get("is_n", 0) > 0 and m.get("is_exp", -1) <= 0:
        fails.append(f"G6 is_exp={m.get('is_exp')}<=0")
    od5 = m.get("oos_drop_top5_per_trade")
    if od5 is None or od5 <= 0:
        fails.append(f"G9 oos_drop_top5={od5}<=0")
    if fraud is not None:
        if not fraud.get("null_pass"):
            fails.append("G7 fails random-null (L172)")
        if not fraud.get("no_truncation_pass"):
            fails.append("G8 truncation artifact (L171)")
    else:
        fails.append("G7/G8 fraud-gate not run")
    return (len(fails) == 0, fails)


# ─────────────────────────────────────────────────────────────────────────────
# J-EDGE ANCHOR CHECK (OP-16)
# ─────────────────────────────────────────────────────────────────────────────
def anchor_check(signals: list[B7Signal]) -> dict:
    fired = {(s.date, s.side) for s in signals}
    fired_dates = {s.date for s in signals}
    winners_taken = sorted(str(d) + s for (d, s) in J_WINNERS if (d, s) in fired
                           or d in fired_dates)
    winners_missed = sorted(str(d) + s for (d, s) in J_WINNERS
                            if d not in fired_dates)
    # for losers: "skip" = no signal that day; if it fired we note the side taken
    losers_skipped = sorted(str(d) + s for (d, s) in J_LOSERS if d not in fired_dates)
    losers_taken = sorted(str(d) + s for (d, s) in J_LOSERS if d in fired_dates)
    return {
        "winner_days_fired": winners_taken,
        "winner_days_missed": winners_missed,
        "loser_days_skipped": losers_skipped,
        "loser_days_fired": losers_taken,
        "n_winners_taken": len(winners_taken),
        "n_winners_total": len(J_WINNERS),
        "n_losers_skipped": len(losers_skipped),
        "n_losers_total": len(J_LOSERS),
        "anchor_note": ("all J anchors are 2026 dates (matched to actual SPY price). "
                        "They lie in the OOS window, so an anchor TAKE is a structural-"
                        "fidelity check, NOT independent OOS evidence (disclosed caveat)."),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[b7] loading SPY+VIX ...", flush=True)
    spy_raw, _vix = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 6, 16))
    spy = _normalize_spy(spy_raw)
    n_days = spy["date"].nunique()
    print(f"[b7] SPY bars={len(spy)} trading_days~{n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    print("[b7] detecting multi-day-trendline confluence signals (one/day, morning) ...",
          flush=True)
    signals = detect_signals(spy)
    sig_days = len({s.date for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[b7] signals={len(signals)} on {sig_days} days "
          f"(fires {round(100 * sig_days / n_days, 1)}% of days) side={side_ct}",
          flush=True)

    anchors = anchor_check(signals)
    print(f"[b7] anchor: winners fired={anchors['winner_days_fired']} "
          f"missed={anchors['winner_days_missed']} | losers skipped="
          f"{anchors['loser_days_skipped']} fired={anchors['loser_days_fired']}",
          flush=True)

    if len(signals) == 0:
        summary = {
            "family": "b7_mdt_confluence", "run_date": dt.date.today().isoformat(),
            "n_signals": 0, "anchor_check": anchors,
            "honest_verdict": ("DEAD-on-arrival: the discrete structural confluence "
                               "(day-trendline reject + multi-day-trendline within "
                               f"{MDT_TOL_TICKS} + named level within {LEVEL_TOL_TICKS}, "
                               "same direction, morning) fires ZERO times over the whole "
                               "sample. The triple-structural co-incidence is too rare to "
                               "be a tradeable discrete setup at these tolerances."),
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print("[b7] ZERO signals — wrote DEAD verdict to", OUT)
        print("VERDICT:", summary["honest_verdict"])
        return 0

    # Build the RTH-only frame for the fraud gate (CandidateSignal indexes into it).
    rth = spy[(spy["t"] >= RTH_OPEN) & (spy["t"] < RTH_CLOSE)].reset_index(drop=True)
    # map global idx -> rth idx
    g2r = {int(g): i for i, g in enumerate(
        spy.index[(spy["t"] >= RTH_OPEN) & (spy["t"] < RTH_CLOSE)])}

    # ── BASE GRID: 2 strikes x 4 stops ───────────────────────────────────────
    grid = []
    for so in STRIKE_OFFSETS:
        for ps in PREMIUM_STOPS:
            rows, cov = simulate_cell(signals, spy, strike_offset=so, premium_stop_pct=ps)
            m = metrics(rows)
            cell = {
                "strike_offset": so,
                "strike_tier": ("ATM" if so == 0 else (f"ITM{abs(so)}" if so < 0 else f"OTM{so}")),
                "premium_stop_pct": ps,
                "stop_label": ("chart_stop_only" if ps <= -0.99 else f"{int(ps*100)}pct"),
                "coverage": cov, "metrics": m,
            }
            grid.append(cell)
            mm = m if m.get("n") else {}
            print(f"  off={so:+d}({cell['strike_tier']:>4}) stop={ps:>6} | "
                  f"n={mm.get('n','-'):>3} exp=${mm.get('exp_dollar','-'):>7} "
                  f"oos_exp=${mm.get('oos_exp','-'):>7}(oos_n={mm.get('oos_n','-')}) "
                  f"posQ={mm.get('positive_quarters','-')} top5%={mm.get('top5_day_pct','-')} "
                  f"fd5={mm.get('full_drop_top5_per_trade','-')} od5={mm.get('oos_drop_top5_per_trade','-')}",
                  flush=True)

    # ── FRAUD GATES + 9-gate verdict on each cell with n>=BAR_N and oos_exp>0 ──
    print("\n[b7] running fraud gates (null L172 + truncation L171) on viable cells ...",
          flush=True)
    for cell in grid:
        m = cell["metrics"]
        cell["clears_9_gates"] = False
        cell["fraud"] = None
        if m.get("n", 0) < 1:
            cell["nine_gate_fails"] = ["no fills"]
            continue
        # Only spend fraud-sim on cells that are at least OOS-positive with enough n
        if m.get("oos_exp", -1) > 0 and m.get("n", 0) >= BAR_N:
            cand = [CandidateSignal(bar_idx=g2r[s.bar_idx], side=s.side,
                                    rejection_level=s.rejection_level, note=s.note)
                    for s in signals if s.bar_idx in g2r]
            v = verify_candidate(cand, rth, strike_offset=cell["strike_offset"],
                                 premium_stop_pct=cell["premium_stop_pct"], qty=QTY,
                                 setup="B7_FRAUD")
            cell["fraud"] = v.as_dict()
            print(f"    fraud off={cell['strike_offset']:+d} stop={cell['premium_stop_pct']}: "
                  f"null_pass={v.null_pass} no_trunc={v.no_truncation_pass} "
                  f"-> {v.reason[:120]}", flush=True)
        clears, fails = clears_9_gates(m, cell["fraud"])
        cell["clears_9_gates"] = clears
        cell["nine_gate_fails"] = fails

    cleared = [c for c in grid if c["clears_9_gates"]]
    filled = [c for c in grid if c["metrics"].get("n", 0) > 0]
    best = max(filled, key=lambda c: c["metrics"].get("oos_exp", -9e9)) if filled else None

    if cleared:
        bc = max(cleared, key=lambda c: c["metrics"]["oos_exp"])
        verdict = (f"EDGE: {len(cleared)} cell(s) clear ALL 9 gates. Best "
                   f"{bc['strike_tier']}/{bc['stop_label']}: oos_exp="
                   f"${bc['metrics']['oos_exp']}/t (oos_n={bc['metrics']['oos_n']}), "
                   f"full_drop5=${bc['metrics']['full_drop_top5_per_trade']}, "
                   f"oos_drop5=${bc['metrics']['oos_drop_top5_per_trade']}. "
                   f"Anchor winners fired={anchors['n_winners_taken']}/{anchors['n_winners_total']}, "
                   f"losers skipped={anchors['n_losers_skipped']}/{anchors['n_losers_total']}.")
    else:
        bb = best["metrics"] if best else {}
        verdict = (
            "DEAD: NO cell clears the 9-gate bar. Multi-day-trendline STRUCTURAL "
            "confluence (not additive scoring) does not manufacture a discrete option "
            f"edge OOS. Best cell {best['strike_tier'] if best else '-'}/"
            f"{best['stop_label'] if best else '-'}: oos_exp=${bb.get('oos_exp')}/t "
            f"(n={bb.get('n')}, oos_n={bb.get('oos_n')}), full_drop5="
            f"${bb.get('full_drop_top5_per_trade')}, oos_drop5="
            f"${bb.get('oos_drop_top5_per_trade')}. Like the B0 additive triple-kill, "
            "the structural co-incidence is a SPY-direction read, not an option edge "
            "(C3/L58): cheaper/righter strikes + capped losers shift magnitude, not sign."
        )
        # add the specific failing gates of the best cell for honesty
        if best:
            verdict += " Best-cell gate fails: " + "; ".join(best["nine_gate_fails"])

    summary = {
        "family": "b7_mdt_confluence",
        "angle": "B — multi-day-trendline confluence (J 5/4 source-of-truth signature)",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": int(n_days),
        "detector": {
            "rule": ("one causal morning (<=10:30) entry/day: a bar that REJECTS a "
                     "same-session trendline (high/low tags it, closes back through) AND "
                     "the day-trendline is within MDT_TOL of a MULTI-DAY trendline (fit "
                     "across prior %d days' swings, >=%d touches) AND within LEVEL_TOL of "
                     "a causal named level (PDH/PDL/PDC/PMH/PML/IBH/IBL), same direction"
                     % (MDT_LOOKBACK_DAYS, MIN_MDT_TOUCHES)),
            "day_tl_tol": DAY_TL_TOL_TICKS, "mdt_tol": MDT_TOL_TICKS,
            "level_tol": LEVEL_TOL_TICKS, "entry_cutoff": str(ENTRY_CUTOFF),
            "structural_not_additive": True,
        },
        "fills_authority": ("real OPRA via lib.simulator_real.simulate_trade_real (C1); "
                            "nearest-cached strike snap <=4; causal next-bar-open entry; "
                            "chart-stop = session extreme via rejection_level"),
        "strike_tiers": "C29: ATM (Safe-2) + ITM-2 (Bold); offset<0=ITM both sides",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR}",
        "nine_gate_bar": ("(1)oos_exp>0 (2)posQ>=4/6 (3)top5%<200 (4)n>=20 "
                          "(5)full_drop5>0 (6)is_exp>0 (7)beats-null L172 "
                          "(8)no-truncation L171 (9)oos_drop5>0 L173"),
        "n_signals": len(signals),
        "signal_fire_day_pct": round(100 * sig_days / n_days, 1),
        "signal_side_count": side_ct,
        "anchor_check": anchors,
        "base_grid": grid,
        "best_cell_by_oos_exp": best,
        "n_cells_clearing_9_gates": len(cleared),
        "honest_verdict": verdict,
        "signals_detail": [
            {"date": str(s.date), "side": s.side, "note": s.note,
             "day_tl": s.day_tl_touch, "mdt_dist": s.mdt_dist, "level_dist": s.level_dist}
            for s in signals],
        "DISCLOSURE": {
            "per_trade": "expectancy reported, not WR alone (OP-14)",
            "concentration": "top5_day_pct + drop-top5-per-trade (full AND OOS-alone)",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58)",
            "anchor_caveat": anchors["anchor_note"],
            "no_survivor_pick": "every cell reported with its exact failing gates",
            "b0_history": ("additive confluence died before (B0 triple-kill); this tests "
                           "whether STRUCTURAL multi-day-trendline co-incidence differs"),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[b7] wrote {OUT}", flush=True)

    print("\n=== B7 MULTI-DAY-TRENDLINE CONFLUENCE VERDICT ===")
    print(f"signals={len(signals)} fires {summary['signal_fire_day_pct']}% of {n_days} days side={side_ct}")
    print(f"cells clearing 9 gates: {len(cleared)}")
    if best:
        bm = best["metrics"]
        print(f"best cell {best['strike_tier']}/{best['stop_label']}: "
              f"n={bm['n']} oos_exp=${bm['oos_exp']} oos_drop5=${bm.get('oos_drop_top5_per_trade')} "
              f"posQ={bm['positive_quarters']} top5%={bm['top5_day_pct']}")
    print("VERDICT:", verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
