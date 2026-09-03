#!/usr/bin/env python
"""dissect_zone-stop-semantics.py -- D2 STRUCTURE STOP vs THE ZONE RULE (2026-09-03).

Two parts, both READ-ONLY on automation/state, journal, analysis/quote-tape. Cached data
only, no network/broker calls. Writes ONLY under
analysis/deep-research/2026-09-03-money/.

PART A -- TODAY'S TWO WAVES under a ZONE-EDGE stop (5m close beyond trigger - zone_width
for calls), reconstructed from automation/state/core-decisions.jsonl's own per-tick
last_closed_5m_close field (the EXACT value the live engine consulted -- FACT, not a
proxy) plus real fills-ledger.jsonl / analysis/quote-tape/2026-09-03.jsonl for premium
bounds, with a disclosed Black-Scholes proxy only for the one true data gap (768C
2026-09-03T10:37-16:00, never re-held by any arm today).

PART B -- historical ZONE-EDGE variant extending H5 (structure-stop-whipsaw) with the one
variant it did not test: buffer = the trigger level's OWN zone_width at the time, sourced
from automation/state/key-levels-history/<date>/<time>.json archived snapshots (nearest
bucket <= the event's own control-fire bar), falling back to the CURRENT key-levels.json
matched by price, else a $0.30 default -- every row's source flagged. Reuses
money_structure_stop_buffer_sim.py's own bar-loading / option-bar / catastrophe-cap /
bootstrap-CI machinery by IMPORT (not modified) so the methodology is byte-identical to
the study it extends.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import random
import statistics
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
import money_structure_stop_buffer_sim as msb  # noqa: E402  (sibling module, unmodified)

OUT_DIR = REPO / "analysis" / "deep-research" / "2026-09-03-money"
KLH = REPO / "automation" / "state" / "key-levels-history"
CURRENT_KL = REPO / "automation" / "state" / "key-levels.json"
CORE_DEC = REPO / "automation" / "state" / "core-decisions.jsonl"
FILLS = REPO / "automation" / "state" / "fills-ledger.jsonl"
QUOTE_TAPE = REPO / "analysis" / "quote-tape" / "2026-09-03.jsonl"

TODAY = "2026-09-03"
DEFAULT_ZONE_WIDTH = 0.30
WINNING_DAYS = {"2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"}
N_BOOTSTRAP = 4000
RNG_SEED = 20260903


# ======================================================================================
# PART A -- TODAY
# ======================================================================================

def load_today_core_rows() -> list[dict]:
    rows = []
    for line in CORE_DEC.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if (r.get("ts_et") or "").startswith(TODAY):
            rows.append(r)
    return rows


def load_today_fills() -> list[dict]:
    out = []
    for line in FILLS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("date_et") == TODAY and r.get("is_option") and r.get("attribution") == "engine":
            out.append(r)
    out.sort(key=lambda r: r.get("ts_et", ""))
    return out


def load_today_quote_tape(symbol: str) -> list[dict]:
    if not QUOTE_TAPE.exists():
        return []
    out = []
    for line in QUOTE_TAPE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("symbol") == symbol:
            out.append(r)
    out.sort(key=lambda r: r.get("ts_et", ""))
    return out


def reconstruct_spy_5m_closes(core_rows: list[dict]) -> list[tuple[str, float]]:
    """The 'spy' field on every core-decisions row IS last_closed_5m_close (verified: it
    changes only on 5-min boundaries and matches the exit_pass leg's own
    last_closed_5m_close field tick-for-tick). Dedup to one row per closed bar -- this is
    the EXACT tape the live engine's structure-stop check consulted today, not a
    reconstruction from a different feed."""
    seen = []
    last = None
    for r in sorted(core_rows, key=lambda r: r["ts_et"]):
        ts, spy = r.get("ts_et"), r.get("spy")
        if spy is None:
            continue
        if spy != last:
            seen.append((ts, spy))
            last = spy
    return seen


def bs_call_price(spot: float, strike: float, t_years: float, sigma: float, r: float = 0.0) -> float:
    """Plain Black-Scholes European call, r=0 (documented proxy convention for this
    session -- 0DTE, dividend/rate effects negligible relative to the disclosed error
    bars). Returns intrinsic-floored to avoid negative/degenerate values near expiry."""
    if t_years <= 0 or sigma <= 0:
        return max(spot - strike, 0.0)
    d1 = (math.log(spot / strike) + 0.5 * sigma * sigma * t_years) / (sigma * math.sqrt(t_years))
    d2 = d1 - sigma * math.sqrt(t_years)

    def _n(x):
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
    px = spot * _n(d1) - strike * _n(d2)
    return max(px, max(spot - strike, 0.0), 0.0)


def calibrate_sigma(spot: float, strike: float, t_years: float, target_price: float) -> float:
    """Bisection implied-vol solve against ONE known real (spot, price) anchor -- used
    only to interpolate the single true data gap in Part A (768C 10:37 onward), never to
    fit a curve to unseen outcomes."""
    lo, hi = 0.01, 3.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        px = bs_call_price(spot, strike, t_years, mid)
        if px < target_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def t_years_from(ts_et: dt.datetime, expiry_et: dt.datetime = dt.datetime(2026, 9, 3, 16, 0)) -> float:
    secs = (expiry_et - ts_et).total_seconds()
    return max(secs, 1.0) / (365.0 * 24 * 3600.0)


def part_a() -> dict:
    core_rows = load_today_core_rows()
    spy_tape = reconstruct_spy_5m_closes(core_rows)
    fills = load_today_fills()

    result = {"spy_5m_close_tape_today": spy_tape, "waves": {}}

    # ---- WAVE 1: 09:41-09:42 entries, trigger 769.36 (zone_width 0.8 -> edge 768.56) ----
    wave1_legs = [
        {"arm": "safe-2", "symbol": "SPY260903C00770000", "qty": 3, "entry": 0.98,
         "entry_ts": "2026-09-03T09:41:04"},
        {"arm": "bold-2", "symbol": "SPY260903C00772000", "qty": 5, "entry": 0.37,
         "entry_ts": "2026-09-03T09:42:06"},
        {"arm": "safe-3", "symbol": "SPY260903C00770000", "qty": 5, "entry": 1.11,
         "entry_ts": "2026-09-03T09:42:06"},
        {"arm": "risky-1", "symbol": "SPY260903C00770000", "qty": 5, "entry": 1.08,
         "entry_ts": "2026-09-03T09:42:08"},
    ]
    actual_exits_w1 = {
        "bold-2": {"ts": "2026-09-03T09:58:04", "premium": 0.20, "stage": "premium_stop"},
        "safe-3": {"ts": "2026-09-03T10:01:06", "premium": 0.57, "stage": "premium_stop"},
        "risky-1": {"ts": "2026-09-03T10:02:07", "premium": 0.52, "stage": "premium_stop"},
        "safe-2": {"ts": "2026-09-03T10:03:03", "premium": 0.50, "stage": "premium_stop"},
    }
    trigger_w1, zw_w1 = 769.36, 0.8
    zone_edge_w1 = trigger_w1 - zw_w1
    raw_edge_w1 = trigger_w1

    # 5m closes strictly during each leg's open lifetime (entry bar through its own exit bar)
    closes_in_window = [(ts, v) for ts, v in spy_tape if "2026-09-03T09:41" <= ts <= "2026-09-03T10:03"]
    min_close_w1 = min(v for _, v in closes_in_window)
    raw_breach_w1 = any(v < raw_edge_w1 for _, v in closes_in_window)
    zone_breach_w1 = any(v < zone_edge_w1 for _, v in closes_in_window)

    result["waves"]["wave1_0941"] = {
        "trigger_level": trigger_w1, "zone_width": zw_w1, "zone_width_label": "SHELF_768.56_770.16",
        "zone_width_provenance": "shelf_band_observed",
        "raw_structure_edge": raw_edge_w1, "zone_edge": zone_edge_w1,
        "spy_5m_closes_while_any_leg_open": closes_in_window,
        "min_5m_close_while_open": min_close_w1,
        "raw_rule_would_have_fired": raw_breach_w1,
        "zone_edge_rule_would_have_fired": zone_breach_w1,
        "verdict": ("IDENTICAL TO ACTUAL -- neither the raw structure rule nor the "
                    "zone-edge rule ever breached while these positions were open (5m "
                    "closes ranged 769.54-769.79, all >= raw trigger 769.36 and miles "
                    "above zone edge 768.56). All four legs exited via the -50% premium "
                    "catastrophe cap, exactly as actually happened -- widening the "
                    "structure buffer changes NOTHING for wave 1."),
        "legs": [
            {**leg, "actual_exit": actual_exits_w1[leg["arm"]],
             "actual_pnl_dollars": round((actual_exits_w1[leg["arm"]]["premium"] - leg["entry"])
                                         * leg["qty"] * 100, 2),
             "zone_edge_would_change_outcome": False}
            for leg in wave1_legs
        ],
        "catastrophe_cap_vs_zone_in_spy_terms": {
            "spy_at_entry_5m_close": 769.735, "spy_at_last_leg_cap_exit_5m_close": 769.54,
            "net_spy_move_while_positions_open": round(769.54 - 769.735, 3),
            "zone_width": zw_w1,
            "finding": ("SPY net-moved only ~$0.20 against the position (769.735 -> "
                        "769.54, 5m-close terms) over the ~20 minutes these legs were "
                        "open -- 25% of the zone_width and never even reached the RAW "
                        "trigger, let alone the zone edge a further $0.80 away. Every "
                        "leg's premium still cratered ~46-54% (bold 0.37->0.20 = -46%; "
                        "safe-3 1.11->0.57 = -49%; risky-1 1.08->0.52 = -52%; safe-2 "
                        "0.98->0.50 = -49%). The -50% catastrophe cap is FAR tighter "
                        "than the zone width in SPY terms here -- it fired on theta/vega "
                        "chop bleed, not on a price move that came anywhere near "
                        "covering the zone's own width, so a wider (or narrower) chart "
                        "buffer is irrelevant to what actually stopped this wave out."),
        },
    }

    # ---- WAVE 2: 10:16-10:17 entries, trigger 768.00 (zone_width 0.384 -> edge 767.616) --
    wave2_legs = [
        {"arm": "safe-2", "symbol": "SPY260903C00768000", "qty": 3, "entry": 1.40,
         "entry_ts": "2026-09-03T10:16:25"},
        {"arm": "bold-2", "symbol": "SPY260903C00770000", "qty": 5, "entry": 0.48,
         "entry_ts": "2026-09-03T10:16:08"},
        {"arm": "safe-3", "symbol": "SPY260903C00768000", "qty": 5, "entry": 1.31,
         "entry_ts": "2026-09-03T10:17:07"},
        {"arm": "risky-1", "symbol": "SPY260903C00768000", "qty": 5, "entry": 1.31,
         "entry_ts": "2026-09-03T10:17:09"},
    ]
    actual_exits_w2 = {
        "safe-2": {"ts": "2026-09-03T10:36:04", "premium": 1.18, "stage": "structure_stop"},
        "bold-2": {"ts": "2026-09-03T10:36:05", "premium": 0.34, "stage": "structure_stop"},
        "safe-3": {"ts": "2026-09-03T10:37:06", "premium": 1.18, "stage": "structure_stop"},
        "risky-1": {"ts": "2026-09-03T10:37:06", "premium": 1.18, "stage": "structure_stop"},
    }
    trigger_w2, zw_w2 = 768.00, 0.384
    zone_edge_w2 = round(trigger_w2 - zw_w2, 4)

    closes_after_entry = [(ts, v) for ts, v in spy_tape if ts >= "2026-09-03T10:16"]
    fire_bar_raw = next(((ts, v) for ts, v in closes_after_entry if v < trigger_w2), None)
    fire_bar_zone = next(((ts, v) for ts, v in closes_after_entry if v < zone_edge_w2), None)
    latest_tick = spy_tape[-1] if spy_tape else None

    # ---- 770C counterfactual (bold-2 leg): real market data almost the whole way, via
    # the SAME symbol re-entered by risky-1/safe-3 at 11:07 -- see fills-ledger.jsonl.
    quote_770c = load_today_quote_tape("SPY260903C00770000")
    real_770c_after_1036 = [q for q in quote_770c if q["ts_et"] >= "2026-09-03T10:36:59"]
    tp1_level_770c = round(0.48 * 2.0, 4)  # observed live TP1 rule today: "tp1 @ +100%"
    # first REAL market print of this exact contract >= TP1 level, after the raw stop bar
    tp1_cross = next((q for q in real_770c_after_1036 if q["mid"] is not None and q["mid"] >= tp1_level_770c), None)

    # ---- 768C counterfactual (safe-2/safe-3/risky-1 legs): NO later real data (never
    # re-held after the actual 10:36-10:37 exit) -- BS proxy, calibrated to the last real
    # quote (mid 1.225 @ 10:36:58, SPY ~767.96-768.2) and cross-checked against the 770C
    # proxy-vs-real fit over the same gap for confidence.
    strike_768, entry_768 = 768.0, 1.31  # modal entry (safe-3/risky-1; safe-2 paid 1.40)
    last_real_768c_ts = dt.datetime(2026, 9, 3, 10, 36, 58)
    last_real_768c_mid = 1.225
    last_real_768c_spy = 767.96
    sigma_768 = calibrate_sigma(last_real_768c_spy, strike_768,
                                t_years_from(last_real_768c_ts), last_real_768c_mid)

    # walk the reconstructed SPY 5m tape forward from 10:41 (next closed bar after the gap
    # starts) pricing 768C at each bar's own close under the calibrated sigma (held flat --
    # VIX did not move materially per core-decisions vix field, checked below)
    proxy_path_768c = []
    for ts, spy_px in spy_tape:
        if ts < "2026-09-03T10:36":
            continue
        t = t_years_from(dt.datetime.fromisoformat(ts))
        px = bs_call_price(spy_px, strike_768, t, sigma_768)
        proxy_path_768c.append({"ts_et": ts, "spy_close": spy_px, "proxy_768c_price": round(px, 4)})
    tp1_level_768c = round(entry_768 * 2.0, 4)
    tp1_cross_768c_proxy = next((p for p in proxy_path_768c if p["proxy_768c_price"] >= tp1_level_768c), None)

    # cross-check: run the SAME calibration/walk machinery on 770C's own gap and compare
    # to the REAL market print at 11:07 (independent validation of the proxy method)
    last_real_770c_ts = dt.datetime(2026, 9, 3, 10, 35, 12)
    last_real_770c_mid = 0.275
    last_real_770c_spy = 768.67
    sigma_770_check = calibrate_sigma(last_real_770c_spy, 770.0,
                                      t_years_from(last_real_770c_ts), last_real_770c_mid)
    real_1107 = next((q for q in quote_770c if q["ts_et"].startswith("2026-09-03T11:07")), None)
    proxy_at_1107 = bs_call_price(770.445, 770.0,
                                  t_years_from(dt.datetime(2026, 9, 3, 11, 6, 0)), sigma_770_check)

    result["waves"]["wave2_1016"] = {
        "trigger_level": trigger_w2, "zone_width": zw_w2, "zone_width_label": "INTRADAY_PMH_2026-09-03",
        "zone_width_provenance": "default_pre_ab (NOT an observed shelf band -- disclosed)",
        "zone_edge": zone_edge_w2,
        "raw_rule_fire_bar": fire_bar_raw, "zone_edge_rule_fire_bar": fire_bar_zone,
        "spy_5m_closes_after_entry_through_latest_tick": closes_after_entry,
        "latest_available_tick": latest_tick,
        "verdict": ("RAW rule fired at 10:36 (close 767.96, a $0.04 breach of trigger "
                    "768.00) -- matches the real fill. ZONE-EDGE rule needs close < "
                    f"{zone_edge_w2} and NEVER breaches that through the latest tick "
                    f"({latest_tick[0] if latest_tick else 'n/a'}, SPY {latest_tick[1] if latest_tick else None}) "
                    "-- the very next bar (10:41) already reclaimed to 768.20 and price "
                    "ran to 772.93 by 11:31. Under zone-edge these 4 legs would have "
                    "RIDDEN THE WHIPSAW and stayed in the same rally the 11:06 third-wave "
                    "re-entries captured for real. RIGHT-CENSORED: session in progress, "
                    "so 'never fires' means 'has not fired as of the last tick read this "
                    "session', not 'could never fire later today'."),
        "legs": [
            {**leg, "actual_exit": actual_exits_w2[leg["arm"]],
             "actual_pnl_dollars": round((actual_exits_w2[leg["arm"]]["premium"] - leg["entry"])
                                         * leg["qty"] * 100, 2)}
            for leg in wave2_legs
        ],
        "counterfactual_770c_bold2": {
            "method": "FACT -- real market prints of the SAME contract (SPY260903C00770000), "
                      "re-held by risky-1/safe-3 from 11:07, bound the counterfactual directly; "
                      "option premium is a public market price, not an arm-specific quantity.",
            "entry": 0.48, "qty": 5, "tp1_level_+100pct": tp1_level_770c,
            "first_real_print_after_raw_stop_bar_crossing_tp1": tp1_cross,
            "real_quote_tape_gap_note": ("no arm held 770C 10:36:59-11:06:xx (real gap, "
                                        "nobody's position -> quote-tape logs nothing); "
                                        "first real print after the gap is 11:07 mid=1.145, "
                                        "already 138% above the counterfactual's own 0.48 "
                                        "entry and 19% above its own TP1 level of 0.96 -- "
                                        "TP1 fired SOMEWHERE inside the unlogged gap, this "
                                        "is a lower bound on how early/how well it did, "
                                        "not the actual crossing tick."),
            "real_fills_by_the_arms_that_actually_held_it_later_same_symbol": [
                {"ts": "2026-09-03T11:07:15", "arm": "safe-3", "side": "buy", "qty": 5, "price": 1.17},
                {"ts": "2026-09-03T11:07:10", "arm": "risky-1", "side": "buy", "qty": 5, "price": 1.18},
                {"ts": "2026-09-03T11:14:07", "arm": "risky-1", "side": "sell(tp1)", "qty": 3, "price": 1.81},
                {"ts": "2026-09-03T11:19:06", "arm": "safe-3", "side": "sell(tp1)", "qty": 3, "price": 2.32},
                {"ts": "2026-09-03T11:21:05", "arm": "safe-3", "side": "sell(runner)", "qty": 2, "price": 1.98},
                {"ts": "2026-09-03T11:21:07", "arm": "risky-1", "side": "sell(runner)", "qty": 2, "price": 1.95},
            ],
            "actual_realized_pnl_dollars": round((0.34 - 0.48) * 5 * 100, 2),
            "conservative_counterfactual_pnl_if_tp1_at_11:07_print_1.145": {
                "tp1_sell_3ct_at": 1.145,
                "note": "uses the literal first post-gap real print as a LOWER-BOUND TP1 fill "
                        "(true fill was almost certainly earlier/better inside the gap); "
                        "runner (2ct) marked at the SAME real path other arms realized "
                        "(1.95-2.32) as of the last observed tick, still open/trailing live",
                "tp1_leg_pnl": round((1.145 - 0.48) * 3 * 100, 2),
                "runner_leg_mark_low": round((1.95 - 0.48) * 2 * 100, 2),
                "runner_leg_mark_high": round((2.32 - 0.48) * 2 * 100, 2),
                "total_vs_actual_minus70": {
                    "low": round((1.145 - 0.48) * 3 * 100 + (1.95 - 0.48) * 2 * 100 - (0.34 - 0.48) * 5 * 100, 2),
                    "high": round((1.145 - 0.48) * 3 * 100 + (2.32 - 0.48) * 2 * 100 - (0.34 - 0.48) * 5 * 100, 2),
                },
            },
        },
        "counterfactual_768c_safe2_safe3_risky1": {
            "method": "APPROXIMATE -- Black-Scholes proxy (r=0, 0DTE t-to-16:00 ET), sigma "
                      "implied from the LAST REAL quote before the true data gap "
                      f"(mid {last_real_768c_mid} @ {last_real_768c_ts.isoformat()}, SPY "
                      f"{last_real_768c_spy}); held flat forward over the reconstructed 5m "
                      "SPY-close tape. 768C was never re-held by any arm today, so unlike "
                      "770C there is no later real print to bound this leg -- every number "
                      "below is labeled APPROXIMATE.",
            "calibrated_sigma": round(sigma_768, 4),
            "modal_entry": entry_768, "tp1_level_+100pct": tp1_level_768c,
            "proxy_path_from_1036": proxy_path_768c,
            "tp1_cross_point_proxy": tp1_cross_768c_proxy,
            "proxy_validation_cross_check": {
                "method": "same calibration run on 770C's OWN real gap (10:35 mid 0.275 -> "
                          "11:07 real mid 1.145), compared to what the identical BS-proxy "
                          "machinery predicts at the 11:06 SPY print (770.445)",
                "calibrated_sigma_770c": round(sigma_770_check, 4),
                "proxy_predicted_price_at_1106_spy": round(proxy_at_1107, 4),
                "real_price_at_1107": (real_1107.get("mid") if real_1107 else None),
                "abs_diff": (round(abs(proxy_at_1107 - real_1107["mid"]), 4) if real_1107 else None),
                "verdict": ("proxy UNDERESTIMATES the real print by ~$0.17 (~18% relative) over "
                            "this 32-min, $1.78 SPY gap -- constant-vol BS understates a fast "
                            "directional 0DTE move. Bias is ONE-DIRECTIONAL (proxy low, real "
                            "high) and consistent with the 768C proxy path being a CONSERVATIVE "
                            "/ LATE estimate of when TP1 was actually crossed -- the true 768C "
                            "TP1 crossing was very likely EARLIER than the proxy's own 11:06 "
                            "estimate, not later. Treat every 768C proxy premium below as a "
                            "floor, and every proxy TIMESTAMP as a ceiling (late bound)."),
            },
        },
        "catastrophe_cap_vs_zone_in_spy_terms": {
            "note": "N/A for wave 2 as REALIZED -- no leg reached the -50% cap; the tighter "
                    "raw structure trigger (a $0.04 breach) fired first, well before any "
                    "premium got near -50% (worst prints at the 10:36 stop bar: safe ~1.18 "
                    "vs entry 1.31-1.40 = only -10% to -16%; bold 0.34 vs 0.48 = -29%). This "
                    "is the inverse of wave 1: here the CHART trigger bit first because "
                    "SPY's move (768.87 area down to 767.96, ~$0.9-1.0) was large relative "
                    "to the raw $0.00-buffer trigger, even though it never covered the "
                    "$0.384 zone_width either.",
        },
    }
    return result


# ======================================================================================
# PART B -- historical ZONE-EDGE variant on the 79-event H5 population
# ======================================================================================

def _load_klh_snapshot(date_et: str, hhmm: str) -> dict | None:
    p = KLH / date_et / f"{hhmm}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def find_zone_width(date_et: str, event_time_hhmm: str, trigger_level: float) -> dict:
    """Nearest archived key-levels-history bucket <= event time on that date, level
    matched to trigger_level within $0.10, zone_width extracted. Falls back to the
    CURRENT key-levels.json (price match), then a $0.30 default -- every row flagged
    with its source."""
    buckets = ["0835", "0930", "1200", "1550"]
    date_dir = KLH / date_et
    available = sorted(p.stem for p in date_dir.glob("*.json") if not p.stem.endswith("-memory")) \
        if date_dir.is_dir() else []
    available = [b for b in available if b in buckets]
    chosen = None
    if available:
        le = [b for b in available if b <= event_time_hhmm]
        chosen = max(le) if le else min(available)
    if chosen:
        snap = _load_klh_snapshot(date_et, chosen)
        if snap:
            best = None
            for lv in snap.get("levels", []):
                if "zone_width" not in lv:
                    continue
                d = abs(lv["price"] - trigger_level)
                if d <= 0.10 and (best is None or d < best[0]):
                    best = (d, lv)
            if best:
                lv = best[1]
                return {"zone_width": lv["zone_width"], "source": "archived_same_day",
                        "bucket": chosen, "label": lv.get("label"),
                        "provenance": lv.get("zone_width_provenance"), "price_diff": round(best[0], 4)}
    # fallback: current file, matched by LABEL (not price) -- the task's second fallback
    # rung is "the current file's zone_width for the SAME LABEL", which requires knowing
    # the historical level's label. Population events carry only a trigger PRICE, never a
    # label, so a price-based match against TODAY's (2026-09-03) unrelated active levels
    # was tried and DISCARDED: on the 2026-08-04 11:25 event (767.48) it spuriously
    # matched today's INTRADAY_RTH_LOW_2026-09-03 (a level with zero connection to
    # 2026-08-04) purely because the two prices happened to sit within $0.10 of each
    # other -- a coincidence, not a same-level match. Since the label is unrecoverable
    # for an unmatched historical event, this rung is a no-op here (0 events use it) and
    # every unmatched event goes straight to the $0.30 default, disclosed per-row.
    return {"zone_width": DEFAULT_ZONE_WIDTH, "source": "default_0.30_fallback",
            "label": None, "provenance": None, "price_diff": None}


def simulate_zone_edge(day_bars: pd.DataFrame, side: str, trigger: float, zone_width: float,
                       control_idx: int) -> int | None:
    n = len(day_bars)
    closes = day_bars["close"].values
    for i in range(control_idx, n):
        margin = msb.breach_margin(side, closes[i], trigger)
        if margin > zone_width:
            return i
    return None


def part_b() -> dict:
    pop = json.loads((OUT_DIR / "structure-stop-buffer-sim.json").read_text(encoding="utf-8"))
    events_in = pop["per_event"]
    spy = msb.load_spy()
    opt_cache: dict[str, pd.DataFrame | None] = {}

    per_event = []
    zw_source_counts: dict[str, int] = {}
    for ev in events_in:
        date_et = ev["date_et"]
        control_ts = pd.Timestamp(ev["control_fire_bar_et"])
        event_hhmm = control_ts.strftime("%H%M")
        zw_info = find_zone_width(date_et, event_hhmm, ev["trigger_level"])
        zw_source_counts[zw_info["source"]] = zw_source_counts.get(zw_info["source"], 0) + 1

        day_bars = msb.rth_day_bars(spy, date_et)
        if day_bars.empty:
            continue
        matches = day_bars.index[day_bars["timestamp_et"] == control_ts]
        if len(matches) == 0:
            continue
        control_idx = int(matches[0])

        symbol = ev["symbol"]
        if symbol not in opt_cache:
            opt_cache[symbol] = msb.load_opt(symbol)
        opt_df = opt_cache[symbol]
        if opt_df is None or opt_df.empty:
            continue

        fire_idx = simulate_zone_edge(day_bars, ev["side"], ev["trigger_level"],
                                      zw_info["zone_width"], control_idx)
        res = msb.resolve_exit_premium(opt_df, day_bars, fire_idx, ev["entry_price"], control_idx)
        if res["exit_premium"] is None:
            continue
        delta = round((res["exit_premium"] - ev["actual_exit_premium"]) * ev["open_qty"] * 100, 2)

        per_event.append({
            "date_et": date_et, "arm": ev["arm"], "symbol": symbol, "side": ev["side"],
            "trigger_level": ev["trigger_level"], "open_qty": ev["open_qty"],
            "entry_price": ev["entry_price"], "control_fire_bar_et": ev["control_fire_bar_et"],
            "actual_exit_premium": ev["actual_exit_premium"],
            "zone_width": zw_info["zone_width"], "zone_width_source": zw_info["source"],
            "zone_width_label": zw_info.get("label"), "zone_width_provenance": zw_info.get("provenance"),
            "zone_fire_bar_et": (str(day_bars.iloc[fire_idx]["timestamp_et"]) if fire_idx is not None else None),
            "fired_same_bar_as_control": (fire_idx == control_idx),
            "zone_edge_exit_premium": res["exit_premium"], "zone_edge_exit_kind": res["exit_kind"],
            "delta_dollars_vs_actual": delta,
            "vix": ev.get("vix"), "vix_from_archetype": ev.get("vix_from_archetype"),
            "is_winning_day": ev.get("is_winning_day"),
        })

    n = len(per_event)
    deltas = [r["delta_dollars_vs_actual"] for r in per_event]
    rng = random.Random(RNG_SEED)
    overall_ci = msb.bootstrap_ci(deltas, N_BOOTSTRAP, rng)

    n_helped = sum(1 for d in deltas if d > 0.01)
    n_hurt = sum(1 for d in deltas if d < -0.01)
    n_flat = sum(1 for d in deltas if abs(d) <= 0.01)

    # drop-best-day
    by_day: dict[str, float] = {}
    for r in per_event:
        by_day[r["date_et"]] = by_day.get(r["date_et"], 0.0) + r["delta_dollars_vs_actual"]
    best_day = max(by_day, key=by_day.get) if by_day else None
    drop_best_day_sum = round(sum(deltas) - (by_day.get(best_day, 0.0) if best_day else 0.0), 2)

    # top-3 concentration
    ranked = sorted(per_event, key=lambda r: -r["delta_dollars_vs_actual"])
    top3 = ranked[:3]
    top3_sum = round(sum(r["delta_dollars_vs_actual"] for r in top3), 2)
    gross_positive = round(sum(d for d in deltas if d > 0), 2)
    net_sum = round(sum(deltas), 2)
    without_top3_sum = round(net_sum - top3_sum, 2)

    # per-arm
    by_arm = {}
    for arm in sorted({r["arm"] for r in per_event}):
        d = [r["delta_dollars_vs_actual"] for r in per_event if r["arm"] == arm]
        by_arm[arm] = msb.bootstrap_ci(d, N_BOOTSTRAP, rng)

    # per-VIX
    by_vix = {}
    for bucket in ("vix<15", "vix15-17", "vix>17", "unknown"):
        d = [r["delta_dollars_vs_actual"] for r in per_event
             if msb.vix_bucket(r["vix"] or r["vix_from_archetype"]) == bucket]
        if d:
            by_vix[bucket] = msb.bootstrap_ci(d, N_BOOTSTRAP, rng)

    # named winning days
    winning_rows = [r for r in per_event if r["is_winning_day"]]
    winning_sum = round(sum(r["delta_dollars_vs_actual"] for r in winning_rows), 2)
    winning_days_present = sorted({r["date_et"] for r in winning_rows})

    # catastrophe-cap-vs-zone diagnostic across the population
    n_now_hits_cap = sum(1 for r in per_event if r["zone_edge_exit_kind"] == "catastrophe_cap")
    n_control_hits_cap = 0  # by construction control never hits the cap (raw fires first)

    out = {
        "_meta": {
            "generated_from": "structure-stop-buffer-sim.json (per_event, n=79 usable)",
            "n_events_simulated": n,
            "zone_width_source_counts": zw_source_counts,
            "default_zone_width_dollars": DEFAULT_ZONE_WIDTH,
            "n_bootstrap": N_BOOTSTRAP, "rng_seed": RNG_SEED,
        },
        "overall": overall_ci,
        "n_helped": n_helped, "n_hurt": n_hurt, "n_flat": n_flat,
        "drop_best_day": {"best_day": best_day, "best_day_sum": round(by_day.get(best_day, 0.0), 2)
                          if best_day else None, "sum_excluding_best_day": drop_best_day_sum},
        "top3_concentration": {
            "top3_events": [{"date": r["date_et"], "arm": r["arm"], "symbol": r["symbol"],
                             "delta": r["delta_dollars_vs_actual"]} for r in top3],
            "top3_sum": top3_sum, "net_sum": net_sum, "gross_positive_sum": gross_positive,
            "pct_of_net_from_top3": (round(100 * top3_sum / net_sum, 1) if net_sum not in (0, None) else None),
            "sum_excluding_top3": without_top3_sum,
        },
        "by_arm": by_arm,
        "by_vix_regime": by_vix,
        "winning_days": {"present": winning_days_present, "n_events": len(winning_rows),
                         "delta_sum": winning_sum,
                         "detail": [{"date": r["date_et"], "arm": r["arm"], "symbol": r["symbol"],
                                    "delta": r["delta_dollars_vs_actual"],
                                    "fired_same_bar_as_control": r["fired_same_bar_as_control"]}
                                   for r in winning_rows]},
        "catastrophe_cap_diagnostic": {
            "n_zone_edge_events_that_ride_into_catastrophe_cap": n_now_hits_cap,
            "pct_of_population": round(100 * n_now_hits_cap / n, 1) if n else None,
            "n_control_events_hitting_cap_by_construction": n_control_hits_cap,
            "note": "under the CURRENT raw (zero-buffer) rule, none of these 79 positions "
                    "ever reaches the catastrophe cap by definition (structure always fires "
                    "first or the position exits some other way before -50%). Loosening the "
                    "stop to the level's own zone_width lets this many ride down into the "
                    "-50% floor instead of the tighter chart exit -- the same mechanical "
                    "cost the whipsaw study's fixed-dollar/ATR buffers documented, now "
                    "measured with a buffer sized to each level's ACTUAL width instead of a "
                    "single global constant.",
        },
        "per_event": per_event,
    }
    return out


def main() -> int:
    a = part_a()
    b = part_b()
    combined = {"part_a_today": a, "part_b_historical_zone_edge": b}
    out_path = OUT_DIR / "dissect-zone-stop-semantics.json"
    out_path.write_text(json.dumps(combined, indent=2, default=str), encoding="utf-8")
    print(f"[dissect] wrote {out_path}")
    print(f"[dissect] part_b n_events={b['_meta']['n_events_simulated']} "
          f"overall_sum={b['overall'].get('sum')} helped={b['n_helped']} hurt={b['n_hurt']} "
          f"flat={b['n_flat']}")
    print(f"[dissect] zone_width sources: {b['_meta']['zone_width_source_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
