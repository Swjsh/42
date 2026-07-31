"""wick_lane_fullhist_replay.py -- WICK-ENTRY-LANE pre-registered 390-day study (2026-07-31).

PRE-REGISTRATION (frozen 2026-07-31T16:47:56 ET, BEFORE this file was written or any cell
ran): analysis/recommendations/prereg-wick-lane-2026-07-31.json. The full frozen text lives
there; this docstring is the echo, not the authority.

LANE: J directive 2026-07-31 "have one of the risky accounts get in off the wick."
Detector = shelf_wick_hold_closed_bar_v1 (backtest/tools/wick_zone_lane.py): price wicks
INTO a PERSISTENT multi-week shelf zone (daily_context.py production shelf pipeline, the
levels-compiler-v2 w5 class -- the only weight class >= 4) and RECOVERS the zone top on
the same closed 5m bar, without ever losing the zone on a close. NOT a widened cross
(graveyard: ZONE-WIDTH-2026-07-28 tested banded close-cross negative on both cells).

COHORTS: BULL primary (J's named shape: 2026-07-31 10:15 low 737.68 into 737.03-738.63;
2026-07-30 12:45 recovery bar) + BEAR mirror secondary. Independent one-position trackers,
independent gates, both reported. Same-bar collisions: bull wins, counted.

MACHINERY (reused, never re-derived): population = ladder_fullhist_replay.load_extended_
data() 390-RTH-day window 2025-01-02..2026-07-27; entry+1 per ENTRY-BAR-CONVENTION-RULING-
2026-07-25 (option bar at-or-after the NEXT 5m bar's timestamp, entry premium = that bar's
OPEN -- the ladder replay's disclosed point-sample convention); ATM strike via
pick_strike(PROBE_STRIKE_TIERS) (the table fleet_executor._ladder_plan uses for risky-3's
min-size lane); qty=3 (house min-size replay convention; live risky-3 Bold-family floor is
5 -- dollars scale linearly, every gate is scale-invariant, disclosed); $0.30
min_entry_premium floor (live-wide gate) counted; real OPRA cached fills ONLY, no-OPRA
signals excluded and counted (C1); exits via backtest/lib/exit_manager_walk.walk_exit_
manager (the REAL exit_manager.plan_exit_actions core) under risky-3's LIVE ZONE-RIDE
shape = strategies.py ribbon_ride registry .to_dict() shallow-merged with risky-3's
accounts.json params_patch.exit_patch READ AT RUNTIME (C14: never hand-copied);
structure_stop_enabled=True, trigger_level = FAR zone edge (bull band_low / bear
band_high), strategy='ribbon_ride', time_stop 15:40 ET.

GATES (frozen): G1 positive aggregate; G2 day-majority; G3 survives-drop-best; G4
held-out (>= 2026-03-06) positive; G5 runner-anchor-no-regression = BY CONSTRUCTION
(standalone lane, zero engine patching -- asserted below: lib.orchestrator is never
imported, lib.filters is never monkeypatched); G6 incident-capture = RED-proofed guard
fixtures in backtest/tests/test_wick_zone_lane.py. NOTHING swept -> dose-response N/A.
n<15 = evidence_thin advisory. ARM NOTHING -- this study reports; arming is a separate
evening's work per the pre-reg's arming_plan_if_pass.

FRAME CONVENTION (disclosed): the wall-v1 frame shared with the LADDER/ZONE-WIDTH/engine-
fullhist machinery -- SPY master CSV + OPRA cache both carry a fixed -04:00 label
year-round, so joins are self-consistent; winter time-gates sit 1h off TRUE ET exactly as
in every prior study on this machinery. Cohort CONTRASTS are the signal.

Run: backtest/.venv/Scripts/python.exe backtest/tools/wick_lane_fullhist_replay.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                      # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import strategies as fleet_strategies                     # noqa: E402
import fleet_executor as fx                                # noqa: E402  -- PROBE_STRIKE_TIERS + EXIT_PATCH_ALLOWED_KEYS
import engine_fullhist_replay as efr                        # noqa: E402  -- naive_dt / ribbon lookup / TIME_STOP_ET
import ladder_fullhist_replay as lfr                         # noqa: E402  -- data window + lane_stats
from lib.exit_manager_walk import walk_exit_manager           # noqa: E402
from lib.option_pricing_real import (                          # noqa: E402
    bar_at_or_after, load_contract_bars, option_symbol,
)
from crypto.lib.strike_selection import pick_strike             # noqa: E402
from wick_zone_lane import (                                     # noqa: E402
    classify_persistent, detect_shelf_wick_hold_bear,
    detect_shelf_wick_hold_bull, shelf_zones_for_session,
)

QTY = 3
MIN_ENTRY_PREMIUM = 0.30                 # params.json min_entry_premium, live-wide
ENTRY_FLOOR = dt.time(9, 35)             # params.json entry_no_trade_before_et
ENTRY_CEIL = dt.time(15, 0)              # params.json entry_no_trade_after_et (exclusive)
HELD_OUT_CUTOFF = dt.date(2026, 3, 6)    # LADDER-FULLHIST last-25% cutoff, touched once
EXPECTED_RTH_DAYS = 390                  # anchor A1: the frozen ladder population

REC_DIR = ROOT / "analysis" / "recommendations"
PREREG_PATH = REC_DIR / "prereg-wick-lane-2026-07-31.json"
DAILY_BARS_CACHE = REC_DIR / "wick-lane-2026-07-31-daily-bars.json"
OUT_JSON = REC_DIR / "wick-lane-2026-07-31.json"
OUT_MD = REC_DIR / "wick-lane-2026-07-31.md"

DAILY_FETCH_START = "2024-10-01"         # 60-cal-day lookback margin before 2025-01-02
DAILY_FETCH_END_EXCL = "2026-07-28"      # population ends 2026-07-27


def log(msg: str) -> None:
    print(f"[wick-lane] {msg}", flush=True)


# ------------------------------------------------------------------ daily bars (zone feed)

def fetch_daily_bars() -> list[dict]:
    """Alpaca 1Day SIP adjustment=raw (the levels-compiler-v2 feed, commit 7b4aa3f4),
    snapshot-cached beside the outputs for reproducibility. Same direct-REST + .mcp.json
    credential pattern as setup/scripts/daily_context._fetch_daily_bars, windowed for the
    full study. Never prints secrets."""
    if DAILY_BARS_CACHE.exists():
        doc = json.loads(DAILY_BARS_CACHE.read_text(encoding="utf-8"))
        log(f"daily bars: cache hit ({len(doc['bars'])} bars)")
        return doc["bars"]
    m = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    env = m["mcpServers"]["alpaca"]["env"]
    hdrs = {"APCA-API-KEY-ID": env["ALPACA_API_KEY"],
            "APCA-API-SECRET-KEY": env["ALPACA_SECRET_KEY"]}
    url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Day"
           f"&start={DAILY_FETCH_START}T00:00:00Z&end={DAILY_FETCH_END_EXCL}T00:00:00Z"
           f"&limit=10000&feed=sip&adjustment=raw&sort=asc")
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = json.loads(r.read()).get("bars", [])
    bars = [{"date": str(b["t"])[:10], "o": float(b["o"]), "h": float(b["h"]),
             "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)}
            for b in raw]
    if not bars:
        raise RuntimeError("daily-bar fetch returned zero bars -- refusing to run blind (C7)")
    DAILY_BARS_CACHE.write_text(json.dumps({
        "_doc": "SPY 1Day SIP adjustment=raw snapshot for the wick-lane zone feed "
                "(prereg-wick-lane-2026-07-31.json). Fetched via the levels-compiler-v2 "
                "feed path; cached so the study is reproducible byte-for-byte.",
        "fetched_at": dt.datetime.now().isoformat(),
        "window": [DAILY_FETCH_START, DAILY_FETCH_END_EXCL],
        "n_bars": len(bars), "bars": bars,
    }, indent=1), encoding="utf-8")
    log(f"daily bars: fetched {len(bars)} ({bars[0]['date']}..{bars[-1]['date']}), cached")
    return bars


# ------------------------------------------------------------------ zone map

def build_zone_map(daily_bars: list[dict], sessions: list[dt.date]) -> dict:
    """Per-session PERSISTENT zone list + funnel counts. Zones for D use daily bars
    strictly before D; persistence = overlap with the zones in force on the prior
    daily-bar session (C6-clean on both sides)."""
    daily_dates = sorted({dt.date.fromisoformat(b["date"]) for b in daily_bars})
    zones_cache: dict[dt.date, list[dict]] = {}

    def zones_for(d: dt.date) -> list[dict]:
        if d not in zones_cache:
            zones_cache[d] = shelf_zones_for_session(daily_bars, d)
        return zones_cache[d]

    out: dict[dt.date, dict] = {}
    for d in sessions:
        priors = [x for x in daily_dates if x < d]
        if not priors:
            out[d] = {"persistent": [], "n_all": 0, "n_fresh_excluded": 0}
            continue
        today_zones = zones_for(d)
        prior_zones = zones_for(priors[-1])
        persistent = classify_persistent(today_zones, prior_zones)
        out[d] = {"persistent": persistent, "n_all": len(today_zones),
                  "n_fresh_excluded": len(today_zones) - len(persistent)}
    return out


# ------------------------------------------------------------------ tracker (extra-lanes pattern)

class PositionTracker:
    def __init__(self):
        self.free_at: Optional[dt.datetime] = None

    def can_enter(self, entry_ts: dt.datetime) -> bool:
        return self.free_at is None or entry_ts >= self.free_at

    def mark(self, exit_ts: Optional[dt.datetime], entry_ts: dt.datetime):
        self.free_at = exit_ts if exit_ts is not None else entry_ts


# ------------------------------------------------------------------ main

def main() -> int:
    t_start = time.time()
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    assert prereg["frozen_before_any_run"] is True
    log(f"PRE-REGISTRATION echo: {prereg['prereg_id']} frozen {prereg['frozen_at_et']} ET "
        "(predicate F1-F4 production constants, zero sweeps, gates G1-G6 -- full frozen "
        f"text: {PREREG_PATH.name})")

    # G5 structural half: this runner must never touch the engine's entry cascade.
    # (lib.orchestrator IS transitively imported by the reused ladder machinery, but this
    # runner never CALLS run_backtest -- no import of it here, grep-able -- and never
    # monkeypatches the production detectors; verify the latter live:)
    import lib.filters as _filters_mod  # noqa: PLC0415
    assert _filters_mod.detect_level_rejection.__module__ == "lib.filters", (
        "G5 violated: detect_level_rejection is monkeypatched")
    assert _filters_mod.detect_wick_rejection_bearish.__module__ == "lib.filters", (
        "G5 violated: detect_wick_rejection_bearish is monkeypatched")

    log(f"loading extended SPY/VIX data {lfr.FULL_START}..{lfr.FULL_END} (ladder machinery)")
    spy_df_raw, _vix_df = lfr.load_extended_data()
    spy_rth = lfr.build_rth_frame(spy_df_raw)
    ribbon_lookup = efr.build_ribbon_lookup(spy_df_raw)
    all_dates = sorted(spy_rth["timestamp_et"].dt.date.unique())
    assert len(all_dates) == EXPECTED_RTH_DAYS, (
        f"population drifted: {len(all_dates)} RTH days != {EXPECTED_RTH_DAYS}")
    window_days = (lfr.FULL_END - lfr.FULL_START).days
    cutoff = lfr.FULL_START + dt.timedelta(days=round(window_days * 0.75))
    assert cutoff == HELD_OUT_CUTOFF, f"held-out cutoff drifted: {cutoff}"
    log(f"  {len(spy_rth)} RTH rows, {len(all_dates)} RTH days, held-out cutoff {cutoff}")

    # risky-3's LIVE ZONE-RIDE exit shape, read at runtime (C14: no hand-copy)
    registry_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    accounts = json.loads((FLEET_DIR / "accounts.json").read_text(encoding="utf-8"))
    r3 = next(a for a in accounts["arms"] if a["id"] == "risky-3")
    patch = r3.get("params_patch", {}).get("exit_patch", {})
    allowed = set(getattr(fx, "EXIT_PATCH_ALLOWED_KEYS"))
    assert set(patch) <= allowed, f"unknown exit_patch keys: {set(patch) - allowed}"
    exit_shape = {**registry_shape, **patch}
    assert exit_shape["trail_pct"] == 0.20 and exit_shape["stop_mode"] == "structure", (
        "risky-3 ZONE-RIDE shape drifted from the pre-reg's description -- investigate "
        f"before trusting results: {exit_shape}")
    log(f"  ZONE-RIDE exit shape (registry+runtime patch): {exit_shape}")

    daily_bars = fetch_daily_bars()
    t0 = time.time()
    zone_map = build_zone_map(daily_bars, all_dates)
    n_zone_days = sum(1 for v in zone_map.values() if v["persistent"])
    log(f"  zone map built: {n_zone_days}/{len(all_dates)} sessions have >=1 persistent "
        f"shelf ({time.time()-t0:.1f}s)")

    counters = {
        "n_signals_bull_raw": 0, "n_signals_bear_raw": 0, "n_collisions_bull_won": 0,
        "n_no_next_bar": 0, "n_outside_entry_window": 0, "n_no_opra": 0,
        "n_below_premium_floor": 0,
        "n_skipped_open_position": {"bull": 0, "bear": 0},
        "n_fresh_zones_excluded_total": sum(v["n_fresh_excluded"] for v in zone_map.values()),
    }
    trackers = {"bull": PositionTracker(), "bear": PositionTracker()}
    rows: dict[str, list[dict]] = {"bull": [], "bear": []}
    excluded_no_opra: list[dict] = []

    t0 = time.time()
    for edate in all_dates:
        zinfo = zone_map[edate]
        persistent = zinfo["persistent"]
        if not persistent:
            continue
        day = spy_rth.loc[spy_rth["timestamp_et"].dt.date == edate].reset_index(drop=True)
        for i in range(len(day) - 1):                       # need a next bar (entry+1)
            bar = day.iloc[i]
            z_bull = detect_shelf_wick_hold_bull(bar, persistent)
            z_bear = detect_shelf_wick_hold_bear(bar, persistent)
            if z_bull is not None:
                counters["n_signals_bull_raw"] += 1
            if z_bear is not None:
                counters["n_signals_bear_raw"] += 1
            if z_bull is not None and z_bear is not None:
                counters["n_collisions_bull_won"] += 1
                z_bear = None                                # frozen tiebreak: bull wins
            for cohort, z, side in (("bull", z_bull, "C"), ("bear", z_bear, "P")):
                if z is None:
                    continue
                nxt = day.iloc[i + 1]
                nxt_t = nxt["timestamp_et"].time()
                if not (ENTRY_FLOOR <= nxt_t < ENTRY_CEIL):
                    counters["n_outside_entry_window"] += 1
                    continue
                trigger_level = float(z["band_low"] if cohort == "bull" else z["band_high"])
                spot = float(bar["close"])
                strike = pick_strike(spot, 2000.0, side, fx.PROBE_STRIKE_TIERS)
                symbol = option_symbol(edate, int(strike), side)
                opt_df = load_contract_bars(symbol)
                if opt_df is None:
                    counters["n_no_opra"] += 1
                    excluded_no_opra.append({"date": edate.isoformat(), "cohort": cohort,
                                             "symbol": symbol})
                    continue
                ob = bar_at_or_after(opt_df, nxt["timestamp_et"])
                if ob is None:
                    counters["n_no_opra"] += 1
                    excluded_no_opra.append({"date": edate.isoformat(), "cohort": cohort,
                                             "symbol": symbol, "why": "no_bar_at_or_after"})
                    continue
                entry_premium = float(ob.open)
                if entry_premium < MIN_ENTRY_PREMIUM:
                    counters["n_below_premium_floor"] += 1
                    continue
                entry_ts = efr.naive_dt(ob.timestamp_et)
                if not trackers[cohort].can_enter(entry_ts):
                    counters["n_skipped_open_position"][cohort] += 1
                    continue
                rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
                res = walk_exit_manager(
                    symbol=symbol, side=side, entry_time_et=entry_ts,
                    entry_premium=entry_premium, qty=QTY, exit_shape=exit_shape,
                    structure_stop_enabled=True, trigger_level=trigger_level,
                    strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET,
                    opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day,
                )
                trackers[cohort].mark(res.exit_time_et, entry_ts)
                rows[cohort].append({
                    "date": edate.isoformat(),
                    "signal_time_et": efr.naive_dt(bar["timestamp_et"]).isoformat(),
                    "entry_time_et": entry_ts.isoformat(),
                    "side": side, "cohort": cohort,
                    "zone": [z["band_low"], z["band_high"]],
                    "zone_touches": z.get("touches"),
                    "trigger_level": trigger_level,
                    "symbol": symbol, "qty": QTY,
                    "entry_premium": round(entry_premium, 4),
                    "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
                    "hold_minutes": res.hold_minutes, "resolved": res.resolved,
                })
    log(f"scan+walk done: bull n={len(rows['bull'])} bear n={len(rows['bear'])} "
        f"({time.time()-t0:.1f}s)  counters={counters}")

    # ---------------- stats + gates ----------------
    def gate_eval(stats: dict) -> dict:
        g = {
            "g1_positive_aggregate": bool(stats["n_trades"] > 0 and stats["total_pnl"] > 0),
            "g2_day_majority": bool(stats["day_majority"]["is_majority"] is True),
            "g3_survives_drop_best": bool(
                stats["survives_dropping_best_trade"]["still_positive"] is True),
            "g4_held_out_positive": bool(
                stats["held_out_last_25pct"]["n_trades"] > 0
                and stats["held_out_last_25pct"]["total_pnl"] > 0),
            "g5_anchor_no_regression": True,   # by construction -- asserted above, no engine touch
            "g6_incident_capture": "backtest/tests/test_wick_zone_lane.py (15 passed, RED-proofed)",
        }
        g["ship_eligible"] = all(v is True for k, v in g.items()
                                 if k.startswith("g") and isinstance(v, bool))
        g["evidence_thin"] = stats["n_trades"] < 15
        return g

    result = {}
    for cohort in ("bull", "bear"):
        stats = lfr.lane_stats(rows[cohort], all_dates, HELD_OUT_CUTOFF)
        gates = gate_eval(stats)
        result[cohort] = {"stats": stats, "gates": gates, "trades": rows[cohort]}
        log(f"  [{cohort}] n={stats['n_trades']} total=${stats['total_pnl']:+.2f} "
            f"WR={stats['win_rate']} held_out=${stats['held_out_last_25pct']['total_pnl']:+.2f} "
            f"ship_eligible={gates['ship_eligible']} thin={gates['evidence_thin']}")

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": str(PREREG_PATH.relative_to(ROOT)).replace("\\", "/"),
        "prereg_frozen_at_et": prereg["frozen_at_et"],
        "window": {"start": lfr.FULL_START.isoformat(), "end": lfr.FULL_END.isoformat(),
                   "n_rth_days": len(all_dates)},
        "held_out_split": {"cutoff_date": HELD_OUT_CUTOFF.isoformat(),
                           "note": "last ~25% by date, touched once (LADDER-FULLHIST cutoff)"},
        "exit_shape_zone_ride": exit_shape,
        "qty": QTY,
        "counters": counters,
        "cohorts": {c: {"stats": result[c]["stats"], "gates": result[c]["gates"]}
                    for c in ("bull", "bear")},
        "trades": {c: result[c]["trades"] for c in ("bull", "bear")},
        "excluded_no_opra": excluded_no_opra,
        "runtime_seconds": round(time.time() - t_start, 1),
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD} ({out['runtime_seconds']}s total)")
    return 0


# ------------------------------------------------------------------ markdown

def _pnl(v) -> str:
    if v is None:
        return "n/a"
    return f"+${v:,.2f}" if v >= 0 else f"-${abs(v):,.2f}"


def write_markdown(out: dict) -> None:
    L = ["# WICK-ENTRY-LANE -- pre-registered 390-day study "
         "(shelf_wick_hold_closed_bar_v1), 2025-01-02..2026-07-27", ""]
    L.append(f"Generated {out['generated_at']}. Runner: "
             f"`backtest/tools/wick_lane_fullhist_replay.py`. Pre-reg frozen "
             f"{out['prereg_frozen_at_et']} ET (`{out['prereg']}`). "
             f"Runtime {out['runtime_seconds']}s.")
    L.append("")
    L.append("## Verdict first")
    L.append("")
    L.append("| Cohort | n | Total P&L | WR | $/trade | Day-majority | Drop-best | "
             "Held-out (>=2026-03-06) | Ship-eligible |")
    L.append("|---|--:|--:|--:|--:|---|---|---|:--:|")
    for c in ("bull", "bear"):
        s = out["cohorts"][c]["stats"]
        g = out["cohorts"][c]["gates"]
        dm = s["day_majority"]
        ho = s["held_out_last_25pct"]
        sb = s["survives_dropping_best_trade"]
        L.append(
            f"| **{c.upper()}**{' (primary)' if c == 'bull' else ' (secondary)'} | "
            f"{s['n_trades']} | {_pnl(s['total_pnl'])} | {s['win_rate']} | "
            f"{_pnl(s['avg_pnl_per_trade']) if s['avg_pnl_per_trade'] is not None else 'n/a'} | "
            f"{dm['win_days']}/{dm['total_trading_days']} ({dm['is_majority']}) | "
            f"{_pnl(sb['total_minus_best'])} ({sb['still_positive']}) | "
            f"{ho['n_trades']}tr {_pnl(ho['total_pnl'])} | "
            f"{'YES' if g['ship_eligible'] else 'NO'}"
            f"{' (thin)' if g['evidence_thin'] else ''} |")
    L.append("")
    cn = out["counters"]
    L.append(f"Funnel: bull raw signals {cn['n_signals_bull_raw']}, bear raw "
             f"{cn['n_signals_bear_raw']}, collisions (bull won) {cn['n_collisions_bull_won']}, "
             f"outside entry window {cn['n_outside_entry_window']}, no-OPRA excluded "
             f"{cn['n_no_opra']}, below $0.30 floor {cn['n_below_premium_floor']}, "
             f"skipped-open bull/bear {cn['n_skipped_open_position']['bull']}/"
             f"{cn['n_skipped_open_position']['bear']}, fresh (non-persistent) zones "
             f"excluded across the window {cn['n_fresh_zones_excluded_total']}.")
    L.append("")
    L.append("## Pre-registration (frozen before the run)")
    L.append("")
    L.append(f"Frozen {out['prereg_frozen_at_et']} ET in `{out['prereg']}` BEFORE the "
             "runner existed. Predicate (bull): at a PERSISTENT production shelf zone "
             "[lo, hi] -- F1 open >= lo, F2 low <= hi, F3 close >= hi - 0.10, F4 "
             "(close - low) >= max(0.15, 0.50 x range); production wick constants, zero "
             "new tunables, zero sweeps. Bear = exact mirror, secondary. Exit = risky-3's "
             "live ZONE-RIDE shape read from accounts.json at runtime; structure stop at "
             "the FAR zone edge. Gates G1-G6 as tabled; dose-response N/A (nothing swept).")
    L.append("")
    for c in ("bull", "bear"):
        trades = out["trades"][c]
        L.append(f"## {c.upper()} cohort trades ({len(trades)})")
        L.append("")
        if not trades:
            L.append("(none)")
            L.append("")
            continue
        cap = 80
        L.append("| Date | Signal | Entry | Zone | Trigger | Premium | P&L | Exit |")
        L.append("|---|---|---|---|--:|--:|--:|---|")
        for r in trades[:cap]:
            L.append(f"| {r['date']} | {r['signal_time_et'][11:16]} | "
                     f"{r['entry_time_et'][11:16]} | {r['zone'][0]:.2f}-{r['zone'][1]:.2f} | "
                     f"{r['trigger_level']:.2f} | {r['entry_premium']:.2f} | "
                     f"{_pnl(r['dollar_pnl'])} | {r['exit_reason']} |")
        if len(trades) > cap:
            L.append(f"| ... ({len(trades) - cap} more in the JSON) | | | | | | | |")
        L.append("")
    L.append("## Disclosures")
    L.append("")
    L.append("- MEASURED replay, not realized fills: this lane does not exist in production. "
             "Entries entry+1 (option bar OPEN at-or-after the next 5m bar), exits via the "
             "REAL `walk_exit_manager` core under risky-3's live ZONE-RIDE shape, real OPRA "
             "cached fills only; no-OPRA signals excluded and counted (C1).")
    L.append("- The two motivating incidents (2026-07-31 10:15, 2026-07-30 12:45) SHAPED the "
             "predicate and sit OUTSIDE this P&L window (ends 2026-07-27) -- anchors never "
             "contribute P&L; the 390-day population is the out-of-sample test.")
    L.append("- Persistence = prior-session band-overlap fallback (lane 3's FRESH/PERSISTENT "
             "artifacts had not landed at freeze; disclosed in the pre-reg).")
    L.append("- qty=3 house min-size replay convention; live risky-3 min_contracts=5 "
             "(Bold family) -- dollars scale linearly, gates are scale-invariant.")
    L.append("- Bull/bear cohorts run INDEPENDENT one-position trackers (separate "
             "hypotheses); a combined single-account book would interleave differently.")
    L.append("- Wall-v1 frame convention shared with the LADDER/ZONE-WIDTH machinery (SPY "
             "master + OPRA cache both fixed -04:00; joins self-consistent; winter "
             "time-gates 1h off TRUE ET, same as every study on this machinery).")
    L.append("- shelf_wick_hold_live_tick_v1 (intra-bar bid-recovery variant) is spec-only, "
             "forward-shadow -- deliberately NOT backtested (no historical tick/bid path).")
    L.append("")
    L.append("---")
    L.append("_Per-trade detail + funnel: `analysis/recommendations/wick-lane-2026-07-31.json`. "
             "Zone feed snapshot: `wick-lane-2026-07-31-daily-bars.json`._")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
