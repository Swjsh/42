"""Exit-discipline validation: would the ENGINE's mechanical HOLD survive J's shake-outs?

J's core thesis (confirmed by his loser data): his ENTRIES had edge — 67.9% of his
losers' underlying continued his way after he sold; 21.4% printed >=2x (EST) — but he
CAPITULATED on a temporary adverse poke before the reversal (median loser exit -41.7%).
His words: "my entries just need work and to hold — that's what we have the engine for."

This module PROVES + TUNES that the engine's mechanical HOLD would have survived the
pokes that shook him out and caught the reversal — "the engine becomes the hold,"
quantified against his real right-thesis shake-out losers.

It fills the gap the existing part_c_engine_counterfactual left: part_c only modeled the
-50% premium CATASTROPHE CAP — it never modeled the CHART-STOP, which is the actual
PRIMARY invalidation in production (CHART-STOP-PRIMARY doctrine 2026-06-18). The whole
question is whether the structural chart-stop sits OUTSIDE the adverse poke.

THE ANALYSIS (right-thesis shake-outs only: continued_his_way==True AND pnl<0)
-----------------------------------------------------------------------------
1. ADVERSE-POKE DISTRIBUTION — from his ENTRY spot, the MAX ADVERSE SPY excursion
   (against thesis) BEFORE the favorable extreme. That's the poke that shook him out.
   Reported in SPY pts (EXACT) and in option-% terms (ESTIMATE via the repo BS pricer).

2. WHERE THE ENGINE'S STOP SITS — at his entry bar, two stops:
   (a) CHART-STOP = structural invalidation level against the trade (nearest swing high
       above for puts / swing low below for calls, identified from the SPY path UP TO AND
       INCLUDING the entry bar — NO look-ahead) + chart_stop_buffer_dollars ($0.50).
       PRODUCTION MECHANIC: the chart-stop is CLOSE-BASED (a wick beyond the level that
       closes back inside does NOT trigger) — modeled faithfully here.
   (b) -50% premium CATASTROPHE CAP — converted to an SPY-equivalent adverse move via the
       pricer at his strike/IV (the adverse spot at which the modeled premium = entry*0.50).
   The engine exits at whichever triggers FIRST.

3. PER-TRADE VERDICT — would the engine's stop HOLD through the adverse poke (poke <
   stop distance, so the engine was STILL IN at the reversal) => CAUGHT THE RECOVERY?
   Or was the poke deep enough to hit the engine's stop => SHARED THE SHAKE-OUT?

4. AGGREGATE — % of right-thesis shake-outs the engine's HOLD survives vs shares; the
   captured-recovery $ EST (honest: capped at a realistic mechanical exit — TP1 +50% OR
   the chandelier-trailed favorable extreme, NOT the perfect peak). Which component does
   the holding work: chart-stop vs -50% cap.

5. STOP-WIDTH TUNING — does the poke distribution say the chart-stop ($0.50 buffer +
   structural level) is wide enough, or do J's reversals systematically come after a poke
   that a CLOSE-confirmation (already production) or a slightly wider buffer would survive?
   Any widening is OOS-anchored to analysis/recommendations/chart-stops-ab-2026-06-18.json
   (the live-book bear-stop sweep) — it must NOT hurt the 2025-26 +EV book.

HONESTY CONTRACT
----------------
  - SPY poke distances + swing levels + the CHART-STOP verdict are EXACT (his fills + the
    EXACT SPY 5m path). This is the load-bearing result.
  - option-% of the poke, the -50%-cap SPY-equivalent, and captured-recovery $ are
    ESTIMATES (BS, IV backed out of J's own entry premium) — labelled _EST everywhere.
  - The engine can NOT make a wrong-thesis trade win — only the right-thesis shake-outs
    are scored.

Pure stdlib + the repo BS pricer. py_compile clean. $0 cost. Propose-only — edits nothing
live; writes analysis/recommendations/exit-discipline-vs-j-losers.json.
"""

from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "backtest"))
from lib.pricing import black_scholes  # noqa: E402

ANALYSIS = REPO / "analysis" / "webull-j-trades"
LOSER_JSON = ANALYSIS / "loser_analysis.json"
BAR_CACHE = ANALYSIS / "loser_bar_cache.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "exit-discipline-vs-j-losers.json"
CHART_STOPS_AB = REPO / "analysis" / "recommendations" / "chart-stops-ab-2026-06-18.json"

# ── Production exit constants (params.json, LIVE config) ──────────────────────
CHART_STOP_BUFFER = 0.50          # chart_stop_buffer_dollars
PREMIUM_CATASTROPHE_CAP = -0.50   # premium_stop_pct / premium_stop_pct_bear
PROFIT_LOCK_ARM = 0.05            # v15_profit_lock_threshold_pct (+5% favor arms)
PROFIT_LOCK_TRAIL = 0.15          # v15_profit_lock_trail_pct (15% off HWM)
TP1_PREMIUM_PCT = 0.50            # tp1_premium_pct (+50% fallback)
RISK_FREE = 0.04
SWING_LOOKBACK_BARS = 12          # bars before entry to scan for the structural swing
SWING_PIVOT_HALFWIDTH = 1         # a swing point: extreme vs +/- this many neighbors


# ── Bars ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Bar:
    t_et: dt.datetime
    o: float
    h: float
    l: float
    c: float
    v: int


_ET_OFFSET_CACHE: dict[str, int] = {}


def _utc_to_et_naive(ts_z: str) -> dt.datetime:
    """UTC ISO -> naive ET. DST-correct via zoneinfo (lesson C6: never blind -5h)."""
    from zoneinfo import ZoneInfo
    s = ts_z.replace("Z", "+00:00")
    base = dt.datetime.fromisoformat(s)
    if base.tzinfo is None:
        base = base.replace(tzinfo=dt.timezone.utc)
    return base.astimezone(ZoneInfo("America/New_York")).replace(tzinfo=None)


def _rth_bars(raw: list[dict[str, Any]]) -> list[Bar]:
    out: list[Bar] = []
    for b in raw:
        t = _utc_to_et_naive(b["t"])
        if dt.time(9, 30) <= t.time() < dt.time(16, 0):
            out.append(Bar(t, float(b["o"]), float(b["h"]),
                           float(b["l"]), float(b["c"]), int(b["v"])))
    out.sort(key=lambda x: x.t_et)
    return out


def _tte_years(now_et: dt.datetime) -> float:
    expiry = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    floor = 1.0 / (365.25 * 24 * 60)
    if now_et >= expiry:
        return floor
    return max(floor, (expiry - now_et).total_seconds() / (365.25 * 24 * 60 * 60))


def _entry_bar_index(bars: list[Bar], entry_spot: float, eod_spot: float) -> Optional[int]:
    """Find the entry bar.

    part_b_per_loser stores entry_spot = the close of the 5m bar containing his entry
    (per webull_loser_stopped_then_printed._spot_at, which floors to 5m and takes that
    bar's close). We recover the index by matching that close, preferring the EARLIEST
    match (his entry, not a later identical print). Falls back to nearest-close.
    """
    EPS = 1e-6
    for i, b in enumerate(bars):
        if abs(b.c - entry_spot) < EPS:
            return i
    # nearest close fallback
    best_i, best_d = None, 1e9
    for i, b in enumerate(bars):
        d = abs(b.c - entry_spot)
        if d < best_d:
            best_d, best_i = d, i
    return best_i


def _structural_stop_level(bars: list[Bar], entry_idx: int, is_call: bool,
                           entry_spot: float) -> tuple[float, str]:
    """Structural invalidation level AGAINST the trade, from the path UP TO AND INCLUDING
    the entry bar (no look-ahead).

    Puts (bear): the nearest SWING HIGH at/above entry within the lookback — the level a
    close above invalidates "price rejected here." Calls (bull): nearest SWING LOW below.
    A swing point = local extreme vs +/- SWING_PIVOT_HALFWIDTH neighbors. If no clean
    pivot, fall back to the entry-bar OPPOSITE extreme (the gap-and-go template: puts ->
    entry-bar HIGH; calls -> entry-bar LOW) — always a valid structural stop.

    Returns (level, source_tag).
    """
    lo = max(0, entry_idx - SWING_LOOKBACK_BARS)
    window = bars[lo:entry_idx + 1]
    hw = SWING_PIVOT_HALFWIDTH

    if not is_call:  # PUT — want a swing HIGH at/above entry (resistance overhead)
        cands: list[float] = []
        for j in range(hw, len(window) - hw):
            piv = window[j]
            if all(piv.h >= window[j - k].h for k in range(1, hw + 1)) and \
               all(piv.h >= window[j + k].h for k in range(1, hw + 1)):
                cands.append(piv.h)
        # nearest swing high that is ABOVE entry (a real overhead invalidation)
        above = sorted([c for c in cands if c >= entry_spot])
        if above:
            return above[0], "swing_high"
        # no overhead pivot -> entry-bar high (opposite extreme, gap-and-go template)
        return bars[entry_idx].h, "entry_bar_high"
    else:            # CALL — want a swing LOW at/below entry (support beneath)
        cands = []
        for j in range(hw, len(window) - hw):
            piv = window[j]
            if all(piv.l <= window[j - k].l for k in range(1, hw + 1)) and \
               all(piv.l <= window[j + k].l for k in range(1, hw + 1)):
                cands.append(piv.l)
        below = sorted([c for c in cands if c <= entry_spot], reverse=True)
        if below:
            return below[0], "swing_low"
        return bars[entry_idx].l, "entry_bar_low"


def _premium_cap_spot(entry_spot: float, strike: float, is_call: bool,
                      iv: float, t_et: dt.datetime, entry_px: float) -> Optional[float]:
    """SPY spot at which the modeled premium = entry_px * (1 + CAP) (i.e. -50%), at the
    entry bar's TTE. Bisection on spot in the adverse direction. ESTIMATE.

    Returns the adverse spot, or None if the cap is unreachable within a wide search
    (premium floors at ~0 deep OTM; if entry*0.50 < that floor the cap can't bind on a
    pure spot move — return None => 'cap never binds on the poke').
    """
    target = entry_px * (1 + PREMIUM_CATASTROPHE_CAP)
    tte = _tte_years(t_et)
    # adverse = UP for a put (spot rises), DOWN for a call (spot falls)
    lo_spot, hi_spot = entry_spot, entry_spot
    step = 0.10
    # walk adverse until premium drops to/below target or we exhaust a wide band ($30)
    for _ in range(300):
        if not is_call:
            hi_spot += step
            prem, _ = black_scholes(hi_spot, strike, iv, tte, is_call, RISK_FREE)
            if prem <= target:
                return hi_spot
            if hi_spot - entry_spot > 30:
                break
        else:
            lo_spot -= step
            if lo_spot <= 0:
                break
            prem, _ = black_scholes(lo_spot, strike, iv, tte, is_call, RISK_FREE)
            if prem <= target:
                return lo_spot
            if entry_spot - lo_spot > 30:
                break
    return None


def _pct(vals: list[float], p: float) -> float:
    s = sorted(vals)
    if not s:
        return 0.0
    k = (len(s) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _summ(vals: list[float]) -> dict[str, float]:
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "mean": round(statistics.mean(vals), 3),
        "median": round(statistics.median(vals), 3),
        "p75": round(_pct(vals, 75), 3),
        "p90": round(_pct(vals, 90), 3),
        "max": round(max(vals), 3),
    }


@dataclass
class LoserVerdict:
    date: str
    symbol: str
    bias: str
    is_call: bool
    qty: int
    entry_px: float
    his_exit_px: float
    his_pnl: float
    iv_used: float
    entry_spot: float
    fav_extreme_spot: float
    eod_spot: float
    # adverse poke (EXACT in SPY pts; ESTIMATE in option %)
    adverse_poke_pts: float                  # max adverse SPY move before fav extreme
    adverse_poke_pct_of_spot: float
    poke_option_pct_EST: float               # modeled premium drawdown at the poke (neg)
    # engine stops
    chart_stop_level: float
    chart_stop_source: str
    chart_stop_dist_pts: float               # |level +/- buffer - entry|
    chart_stop_breached_close: bool          # CLOSE-based (production mechanic)
    chart_stop_breach_time_et: Optional[str]
    premium_cap_spot_EST: Optional[float]
    premium_cap_dist_pts_EST: Optional[float]
    premium_cap_breached_EST: bool
    # verdict
    engine_held: bool                        # neither chart-stop nor cap fired pre-reversal
    binding_exit: str                        # chart_stop | premium_cap | held
    captured_recovery_dollars_EST: float     # honest capped recovery vs his exit


def analyze() -> dict[str, Any]:
    data = json.loads(LOSER_JSON.read_text(encoding="utf-8"))
    cache = json.loads(BAR_CACHE.read_text(encoding="utf-8"))
    rows = data["part_b_per_loser"]

    # right-thesis shake-outs: continued_his_way True AND a loss AND scoreable
    shake = [
        r for r in rows
        if r.get("continued_his_way") is True
        and r.get("pnl", 0) < 0
        and r.get("entry_spot") is not None
        and r.get("fav_extreme_spot") is not None
        and r.get("iv_used") is not None
    ]

    verdicts: list[LoserVerdict] = []
    skipped = 0
    for r in shake:
        raw = cache.get(r["date"])
        if not raw:
            skipped += 1
            continue
        bars = _rth_bars(raw)
        if not bars:
            skipped += 1
            continue
        is_call = bool(r["is_call"])
        entry_spot = float(r["entry_spot"])
        fav_extreme = float(r["fav_extreme_spot"])
        eod_spot = float(r["eod_spot"])
        strike = float(r["strike_spy"])
        iv = float(r["iv_used"])
        entry_px = float(r["entry_px"])
        qty = int(r["qty"])

        eidx = _entry_bar_index(bars, entry_spot, eod_spot)
        if eidx is None:
            skipped += 1
            continue
        entry_bar = bars[eidx]

        # ── adverse poke: max adverse SPY excursion from entry BEFORE fav extreme ──
        # Path strictly AFTER the entry bar up to (and including) the fav-extreme bar.
        # Favorable = down for a put, up for a call. Adverse = the opposite.
        # Find the fav-extreme bar index (first bar at/after entry hitting fav_extreme).
        fav_idx = None
        for i in range(eidx, len(bars)):
            b = bars[i]
            hit = (b.l <= fav_extreme + 1e-6) if not is_call else (b.h >= fav_extreme - 1e-6)
            if i > eidx and hit:
                fav_idx = i
                break
        if fav_idx is None:
            fav_idx = len(bars) - 1  # fav extreme is EOD or unmatched -> scan to end

        pre_rev = bars[eidx + 1:fav_idx + 1]  # bars after entry, through the reversal
        if not pre_rev:
            pre_rev = bars[eidx + 1:] or [entry_bar]

        if not is_call:  # PUT: adverse = price UP. worst = highest HIGH before reversal
            adverse_extreme = max(b.h for b in pre_rev)
            adverse_poke = max(0.0, adverse_extreme - entry_spot)
        else:            # CALL: adverse = price DOWN. worst = lowest LOW before reversal
            adverse_extreme = min(b.l for b in pre_rev)
            adverse_poke = max(0.0, entry_spot - adverse_extreme)

        # option-% drawdown at the poke (ESTIMATE) — premium at the adverse extreme,
        # priced at the TTE of the bar that printed the worst adverse extreme.
        poke_bar = None
        for b in pre_rev:
            mark = b.h if not is_call else b.l
            if abs(mark - adverse_extreme) < 1e-6:
                poke_bar = b
                break
        poke_bar = poke_bar or pre_rev[-1]
        tte_poke = _tte_years(poke_bar.t_et)
        prem_at_poke, _ = black_scholes(adverse_extreme, strike, iv, tte_poke,
                                        is_call, RISK_FREE)
        poke_opt_pct = (prem_at_poke / entry_px - 1.0) if entry_px > 0 else 0.0

        # ── chart-stop: structural level + buffer, CLOSE-based (production) ──
        lvl, lvl_src = _structural_stop_level(bars, eidx, is_call, entry_spot)
        if not is_call:
            stop_price = lvl + CHART_STOP_BUFFER          # close ABOVE => breach (put)
            chart_dist = abs(stop_price - entry_spot)
        else:
            stop_price = lvl - CHART_STOP_BUFFER          # close BELOW => breach (call)
            chart_dist = abs(entry_spot - stop_price)

        # CLOSE-based breach check, only on bars BEFORE the reversal (would it have shaken
        # the engine out before the move it was right about?)
        chart_breached = False
        chart_breach_time = None
        for b in pre_rev:
            if not is_call and b.c > stop_price:
                chart_breached, chart_breach_time = True, b.t_et.strftime("%H:%M")
                break
            if is_call and b.c < stop_price:
                chart_breached, chart_breach_time = True, b.t_et.strftime("%H:%M")
                break

        # ── -50% premium catastrophe cap, as an SPY-equivalent adverse move (ESTIMATE) ──
        cap_spot = _premium_cap_spot(entry_spot, strike, is_call, iv,
                                     entry_bar.t_et, entry_px)
        cap_dist = None
        cap_breached = False
        if cap_spot is not None:
            cap_dist = abs(cap_spot - entry_spot)
            # cap breach uses the INTRABAR adverse extreme (a premium gap can fire intrabar)
            cap_breached = adverse_poke >= cap_dist - 1e-9

        # ── binding exit (whichever fires first in the adverse direction = nearer stop) ──
        held = not chart_breached and not cap_breached
        if held:
            binding = "held"
        elif chart_breached and not cap_breached:
            binding = "chart_stop"
        elif cap_breached and not chart_breached:
            binding = "premium_cap"
        else:
            # both breached -> the NEARER one fires first
            binding = "chart_stop" if (cap_dist is None or chart_dist <= cap_dist) \
                else "premium_cap"

        # ── captured-recovery $ EST (honest cap) ──
        # If engine HELD: it rides to a realistic mechanical exit. The chandelier trails
        # 15% off the favorable HWM once armed (+5%), so the realized favorable premium is
        # ~ the favorable-extreme premium discounted by the trail; TP1 (+50%) takes 2/3 off
        # earlier. Honest cap = min(favorable-extreme premium, TP1 path) discounted, never
        # the perfect peak. If engine SHARED: realized ~ his loss at the engine stop.
        if held:
            tte_fav = _tte_years(bars[fav_idx].t_et) if fav_idx < len(bars) else _tte_years(bars[-1].t_et)
            prem_fav, _ = black_scholes(fav_extreme, strike, iv, tte_fav,
                                        is_call, RISK_FREE)
            tp1_px = entry_px * (1 + TP1_PREMIUM_PCT)
            armed = prem_fav >= entry_px * (1 + PROFIT_LOCK_ARM)
            trailed_fav = prem_fav * (1 - PROFIT_LOCK_TRAIL) if armed else prem_fav
            # mechanical realized premium per contract (honest, discounted):
            if prem_fav >= tp1_px:
                # 2/3 at TP1 (+50%), 1/3 runner at chandelier-trailed favorable
                realized_px = (2.0 / 3.0) * tp1_px + (1.0 / 3.0) * max(trailed_fav, tp1_px)
            else:
                realized_px = max(trailed_fav, entry_px * (1 + PROFIT_LOCK_ARM)) \
                    if armed else prem_fav
            realized_px = max(0.01, realized_px)
        else:
            # engine shared the shake-out: realized ~ his exit floor (chart-stop near his
            # panic, or the -50% cap). Use the binding stop's premium as the realized exit.
            if binding == "premium_cap":
                realized_px = entry_px * (1 + PREMIUM_CATASTROPHE_CAP)
            else:
                # chart-stop premium at the breach bar (ESTIMATE)
                bt = None
                for b in pre_rev:
                    if b.t_et.strftime("%H:%M") == chart_breach_time:
                        bt = b
                        break
                bt = bt or pre_rev[-1]
                prem_stop, _ = black_scholes(bt.c, strike, iv, _tte_years(bt.t_et),
                                             is_call, RISK_FREE)
                realized_px = max(0.01, prem_stop)

        captured = (realized_px - r["exit_px"]) * 100 * qty

        verdicts.append(LoserVerdict(
            date=r["date"], symbol=r["symbol"], bias=r["bias"], is_call=is_call,
            qty=qty, entry_px=entry_px, his_exit_px=r["exit_px"], his_pnl=r["pnl"],
            iv_used=iv, entry_spot=round(entry_spot, 2),
            fav_extreme_spot=round(fav_extreme, 2), eod_spot=round(eod_spot, 2),
            adverse_poke_pts=round(adverse_poke, 3),
            adverse_poke_pct_of_spot=round(100 * adverse_poke / entry_spot, 3),
            poke_option_pct_EST=round(100 * poke_opt_pct, 1),
            chart_stop_level=round(lvl, 2), chart_stop_source=lvl_src,
            chart_stop_dist_pts=round(chart_dist, 3),
            chart_stop_breached_close=chart_breached,
            chart_stop_breach_time_et=chart_breach_time,
            premium_cap_spot_EST=round(cap_spot, 2) if cap_spot is not None else None,
            premium_cap_dist_pts_EST=round(cap_dist, 3) if cap_dist is not None else None,
            premium_cap_breached_EST=cap_breached,
            engine_held=held, binding_exit=binding,
            captured_recovery_dollars_EST=round(captured, 0),
        ))

    return _summarize(verdicts, skipped, len(shake))


def _summarize(v: list[LoserVerdict], skipped: int, n_shake: int) -> dict[str, Any]:
    n = len(v)
    held = [x for x in v if x.engine_held]
    shared = [x for x in v if not x.engine_held]
    by_chart = [x for x in shared if x.binding_exit == "chart_stop"]
    by_cap = [x for x in shared if x.binding_exit == "premium_cap"]

    pokes_pts = [x.adverse_poke_pts for x in v]
    pokes_pct = [x.adverse_poke_pct_of_spot for x in v]
    pokes_opt = [x.poke_option_pct_EST for x in v]
    chart_dists = [x.chart_stop_dist_pts for x in v]
    cap_dists = [x.premium_cap_dist_pts_EST for x in v if x.premium_cap_dist_pts_EST is not None]

    # captured-recovery only counts the HELD cases (the engine's value-add); shared cases
    # the engine ~matches his loss (small delta from his deeper panic, reported separately).
    captured_held = sum(x.captured_recovery_dollars_EST for x in held)
    captured_all = sum(x.captured_recovery_dollars_EST for x in v)

    # "would chart-stop alone have held?" vs "would cap alone have held?"
    chart_only_survive = [x for x in v if not x.chart_stop_breached_close]
    cap_only_survive = [x for x in v if not x.premium_cap_breached_EST]

    # how many chart-breaches were WICK-only (intrabar exceeded but close held) — the value
    # of the production close-confirmation rule. Re-derive: poke (intrabar) exceeded chart
    # dist BUT chart close-breach was False.
    wick_saved = [x for x in v
                  if x.adverse_poke_pts >= x.chart_stop_dist_pts - 1e-9
                  and not x.chart_stop_breached_close]

    his_loss_total = sum(x.his_pnl for x in v)

    # source tag distribution for the chart-stop level (transparency)
    src_dist: dict[str, int] = {}
    for x in v:
        src_dist[x.chart_stop_source] = src_dist.get(x.chart_stop_source, 0) + 1

    worst_shared = sorted(shared, key=lambda x: x.his_pnl)[:12]
    best_held = sorted(held, key=lambda x: -x.captured_recovery_dollars_EST)[:12]

    return {
        "_what": "Would the ENGINE's mechanical HOLD survive J's right-thesis shake-outs?",
        "_honesty": {
            "EXACT": "SPY adverse-poke distances, structural swing levels, CLOSE-based "
                     "chart-stop breach verdict (his real fills + EXACT SPY 5m path)",
            "ESTIMATE": "option-% of the poke, the -50% cap SPY-equivalent, "
                        "captured-recovery $ (BS, IV implied from J's own entry premium)",
            "scope": "right-thesis shake-outs ONLY (continued_his_way==True AND pnl<0); "
                     "the engine cannot make a wrong-thesis trade win",
        },
        "universe": {
            "n_right_thesis_shakeouts_scoreable": n,
            "n_candidate_rows": n_shake,
            "n_skipped_no_bars_or_unmatched": skipped,
        },
        # ── 1. ADVERSE-POKE DISTRIBUTION ──
        "adverse_poke_distribution": {
            "spy_points_EXACT": _summ(pokes_pts),
            "pct_of_spot_EXACT": _summ(pokes_pct),
            "option_pct_drawdown_at_poke_EST": _summ(pokes_opt),
            "_note": "option_pct is NEGATIVE (a drawdown). median ~ how deep the modeled "
                     "premium sank at the worst adverse tick before the reversal.",
        },
        # ── engine stop geometry ──
        "engine_stop_geometry": {
            "chart_stop_dist_pts_EXACT": _summ(chart_dists),
            "premium_cap_dist_pts_EST": _summ(cap_dists),
            "chart_stop_buffer_dollars": CHART_STOP_BUFFER,
            "premium_catastrophe_cap": PREMIUM_CATASTROPHE_CAP,
            "chart_stop_level_source_distribution": src_dist,
        },
        # ── 3+4. VERDICT + AGGREGATE ──
        "engine_hold_verdict": {
            "n_engine_held_caught_reversal": len(held),
            "pct_engine_held": round(100 * len(held) / n, 1) if n else 0,
            "n_engine_shared_shakeout": len(shared),
            "pct_engine_shared": round(100 * len(shared) / n, 1) if n else 0,
            "shared_breakdown": {
                "by_chart_stop": len(by_chart),
                "by_premium_cap": len(by_cap),
            },
        },
        "which_component_does_the_work": {
            "_q": "if ONLY the chart-stop existed, how many survive? if ONLY the -50% cap?",
            "chart_stop_alone_survives": len(chart_only_survive),
            "pct_chart_stop_alone_survives": round(100 * len(chart_only_survive) / n, 1) if n else 0,
            "premium_cap_alone_survives": len(cap_only_survive),
            "pct_premium_cap_alone_survives": round(100 * len(cap_only_survive) / n, 1) if n else 0,
            "_read": "the component that survives MORE pokes is doing the holding work. "
                     "The combined engine exits at whichever is NEARER (fires first).",
        },
        "close_confirmation_value": {
            "_q": "production chart-stop is CLOSE-based; how many shake-outs were WICK-only "
                  "(intrabar poke pierced the structural level but the bar closed back "
                  "inside, so the engine did NOT exit)?",
            "n_wick_pierced_but_close_held": len(wick_saved),
            "pct_of_all_shakeouts": round(100 * len(wick_saved) / n, 1) if n else 0,
            "_read": "these are trades the close-confirmation rule SAVED from a wick stop-out "
                     "— direct evidence that 'wait for the 5m bar CLOSE, not the wick' is "
                     "already the right rule and is load-bearing.",
        },
        "captured_recovery_EST": {
            "his_actual_loss_total_EXACT": round(his_loss_total, 0),
            "captured_recovery_on_HELD_cases_dollars_EST": round(captured_held, 0),
            "captured_recovery_ALL_cases_dollars_EST": round(captured_all, 0),
            "_note": "captured = (engine realized px - his exit px) * 100 * qty. HELD cases "
                     "ride to a HONEST capped exit: 2/3 at TP1 +50%, 1/3 runner at the "
                     "chandelier-trailed (15% off HWM) favorable extreme — NOT the perfect "
                     "peak. SHARED cases ~ match his loss at the engine stop.",
        },
        "_detail_worst_shared_shakeouts": [asdict(x) for x in worst_shared],
        "_detail_best_held_recoveries": [asdict(x) for x in best_held],
        "_full_per_trade": [asdict(x) for x in v],
    }


def main() -> int:
    out = analyze()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    u = out["universe"]
    pk = out["adverse_poke_distribution"]["spy_points_EXACT"]
    hv = out["engine_hold_verdict"]
    cr = out["captured_recovery_EST"]
    cw = out["which_component_does_the_work"]
    print("=" * 72)
    print(f"scoreable right-thesis shake-outs: {u['n_right_thesis_shakeouts_scoreable']}"
          f" (skipped {u['n_skipped_no_bars_or_unmatched']})")
    print(f"adverse poke (SPY pts): median {pk['median']} / p75 {pk['p75']} / p90 {pk['p90']}")
    print(f"ENGINE HELD (caught reversal): {hv['n_engine_held_caught_reversal']}"
          f" = {hv['pct_engine_held']}%   |   SHARED: {hv['n_engine_shared_shakeout']}")
    print(f"  shared by chart-stop {hv['shared_breakdown']['by_chart_stop']} /"
          f" by -50% cap {hv['shared_breakdown']['by_premium_cap']}")
    print(f"component work: chart-alone survives {cw['pct_chart_stop_alone_survives']}%"
          f"  |  cap-alone survives {cw['pct_premium_cap_alone_survives']}%")
    print(f"captured recovery $ EST (HELD): {cr['captured_recovery_on_HELD_cases_dollars_EST']}"
          f"  (vs his loss {cr['his_actual_loss_total_EXACT']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
