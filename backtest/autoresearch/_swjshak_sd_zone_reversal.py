"""SwjshAK 'sd_zone_reversal' (Boba supply/demand) — REAL-FILLS validation (OPRA sim).

STRATEGY (class = REVERSION; source: SwjshAK docs/boba_strategy/STRATEGY_RULES.md,
extracted in markdown/research/SWJSHAK-STRATEGY-EXTRACTION-2026-06-20.md row #5):

  Mark a FRESH (untested) supply/demand zone left by an IMPULSE candle
  (body > 2x ATR). On the FIRST retest of that zone, take a REVERSAL entry:
    - demand zone (impulse was a strong GREEN up-candle) -> price falls back
      into the zone -> CALL (fade the pullback, expect bounce up).
    - supply zone (impulse was a strong RED down-candle) -> price rallies back
      into the zone -> PUT (fade the rally, expect rejection down).
  Morning only: 09:30-11:00 ET. One retest per zone (fresh-only). Cooldown 30-45m.

WHY WE EXPECT FAILURE (honesty, per the prompt + the 0DTE-wall doctrine):
  REVERSION class. The 0DTE wall has killed reversion 7x (C3/L58, C16, L52/59/75):
  a SPY-PRICE mean-reversion edge dies on 0DTE options because (1) you are fighting
  the just-established impulse/trend, (2) theta bleeds while you wait for the bounce,
  (3) delta on a counter-trend entry is working against you. The ONLY structure that
  survived our whole fleet is sustained-DIRECTIONAL continuation (vwap_continuation:
  ITM-2 + tight -8% stop + morning). A counter-trend fade is the opposite shape.
  So: test it HONESTLY, report per-trade expectancy (not WR), and expect it to fail
  the OP-11 / random-null / truncation gates. A clean documented NULL is the success.

NO LOOK-AHEAD (C6):
  - ATR and the impulse/zone are computed only from bars at/<= the current bar.
  - A zone is created by the impulse bar; the earliest retest we accept is a LATER
    bar (strictly after the impulse bar), so the zone is fully formed before entry.
  - Trigger fires on the CLOSE of the retest bar; simulator_real fills on the NEXT
    bar's open (its own no-look-ahead contract). entry_time_et localized America/NY.

HARD SELF-VERIFY (all three MANDATORY — these caught 2 fakes last run):
  (a) OP-11:  OOS(2026) per-trade>0 AND positive_quarters>=4/6 AND top5-day<200%
              AND n>=20 AND drop-top-5-days still>0.
  (b) RANDOM-NULL: re-run with RANDOM entry bars (same count/day-distribution, same
              exit bracket/stop/strike), ~20 seeds; the strategy per-trade MUST beat
              the null mean. If random ties it, the edge is the bracket, not the
              signal -> FAIL.
  (c) NO-TRUNCATION: the SIGN of per-trade must NOT invert between the -8% stop and
              chart-stop-only (-0.99). Positive only because -8% truncates losers =
              stop artifact -> FAIL.

PRIMARY config = SURVIVOR STRUCTURE: strike_offset=-2 (ITM-2), premium_stop_pct=-0.08,
default v15 exits, qty=3. Then a small secondary sweep strike_offset {-2,-1,0} x
stop {-0.08,-0.20,-0.50,-0.99}.

rejection_level = strategy invalidation (for a CALL: support BELOW entry = the far
edge of the demand zone; for a PUT: resistance ABOVE = the far edge of the supply
zone). If price closes through it, the zone failed.

Pure Python, $0, no live orders. Writes analysis/recommendations/swjshak-sd-zone-reversal.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import random
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

# ── Strategy parameters (Boba) ───────────────────────────────────────────────
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)
ATR_LEN = 14                       # bars for ATR (5m)
IMPULSE_BODY_ATR_MULT = 2.0       # body > 2x ATR = impulse candle (zone-maker)
MORNING_START = dt.time(9, 30)
MORNING_END = dt.time(11, 0)      # entries only 09:30-11:00 ET
RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)
COOLDOWN_MIN = 30                 # 30-45m band; 30 = most generous for signal count
ZONE_MAX_AGE_BARS = 48            # a zone older than ~4h (same session) is stale; drop
RETEST_TOL = 0.05                 # fraction-of-zone-height slop when testing "entered zone"
WARMUP_BARS = ATR_LEN + 1         # need ATR history before first impulse

# ── Real-fills config ────────────────────────────────────────────────────────
QTY = 3
SURVIVOR_STRIKE_OFFSET = -2       # ITM-2
SURVIVOR_STOP = -0.08             # tight -8% premium stop
SWEEP_OFFSETS = [-2, -1, 0]
SWEEP_STOPS = [-0.08, -0.20, -0.50, -0.99]
RANDOM_SEEDS = 20
NY = "America/New_York"


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


class _Acc:
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
            "avg_pnl": round(self.pnl / self.n, 1),
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


def _load_rth() -> tuple[pd.DataFrame, list[float]]:
    """Load SPY RTH bars (tz-naive ET) + per-bar VIX (ffill). America/New_York localized."""
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"], utc=True)
    # convert to America/New_York then drop tz -> naive ET (the engine convention, C6/L161)
    spy_full["ts_ny"] = spy_full["timestamp_et"].dt.tz_convert(NY).dt.tz_localize(None)
    rth = spy_full[(spy_full["ts_ny"].dt.time >= RTH_START)
                   & (spy_full["ts_ny"].dt.time < RTH_END)].reset_index(drop=True)
    # simulator_real consumes spy_df['timestamp_et'] — give it the naive-ET series.
    rth["timestamp_et"] = rth["ts_ny"]
    rth["date"] = rth["ts_ny"].dt.date
    log.info("RTH bars: %d", len(rth))

    # VIX aligned by ffill on naive-ET timestamps
    vix_full["timestamp_et"] = pd.to_datetime(
        vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index)
    vix_ser = vix_full.set_index("timestamp_et")["close"] if "close" in vix_full.columns else vix_full.iloc[:, 0]
    vix_arr: list[float] = []
    for ts in rth["ts_ny"]:
        try:
            j = vix_ser.index.get_indexer([ts], method="ffill")[0]
            vix_arr.append(float(vix_ser.iloc[j]) if j >= 0 else 17.0)
        except Exception:
            vix_arr.append(17.0)
    return rth, vix_arr


def _compute_atr(rth: pd.DataFrame) -> list[float]:
    """Wilder-ish ATR(14) computed causally per-bar, reset each day (intraday ATR).

    Uses only bars at/<= current bar (rolling mean of true range). No look-ahead.
    """
    atr: list[float] = [0.0] * len(rth)
    prev_close: float | None = None
    cur_date = None
    trs: list[float] = []
    for i in range(len(rth)):
        d = rth["date"].iloc[i]
        h = float(rth["high"].iloc[i]); l = float(rth["low"].iloc[i]); c = float(rth["close"].iloc[i])
        if d != cur_date:
            cur_date = d
            prev_close = None
            trs = []
        if prev_close is None:
            tr = h - l
        else:
            tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
        if len(trs) >= ATR_LEN:
            atr[i] = sum(trs[-ATR_LEN:]) / ATR_LEN
        else:
            atr[i] = sum(trs) / len(trs)  # partial-warmup ATR (still causal)
        prev_close = c
    return atr


def scan_signals(rth: pd.DataFrame, atr: list[float], vix_arr: list[float],
                 win_start: dt.time = MORNING_START, win_end: dt.time = MORNING_END) -> list[dict]:
    """Causal scan for fresh-zone first-retest reversal signals.

    Zone bookkeeping is per-day (0DTE — zones don't carry across sessions).
    A demand zone = body of a strong GREEN impulse (low..high of impulse body region);
    supply zone = body of a strong RED impulse. Fresh = not yet retested. First retest
    = a LATER bar whose price re-enters the zone band -> reversal entry, then zone consumed.

    win_start/win_end gate the ENTRY (retest) time. PRIMARY uses the hypothesis morning
    window (09:30-11:00); the all-RTH companion (09:30-16:00) widens it so the random-null
    / truncation gates have enough n to actually discriminate (the morning gate alone
    yields n=3, uninvestigable). The signal LOGIC is identical either way.
    """
    signals: list[dict] = []
    # day index boundaries
    day_start: dict[dt.date, int] = {}
    for i, d in enumerate(rth["date"]):
        if d not in day_start:
            day_start[d] = i

    # active fresh zones for the CURRENT day only
    cur_date = None
    demand_zones: list[dict] = []   # each: {created_i, lo, hi}
    supply_zones: list[dict] = []
    last_sig_time: dt.datetime | None = None

    for i in range(len(rth)):
        d = rth["date"].iloc[i]
        if d != cur_date:
            cur_date = d
            demand_zones = []
            supply_zones = []
        i0 = day_start[d]
        local = i - i0
        o = float(rth["open"].iloc[i]); h = float(rth["high"].iloc[i])
        l = float(rth["low"].iloc[i]); c = float(rth["close"].iloc[i])
        a = atr[i]
        ts = rth["ts_ny"].iloc[i].to_pydatetime()  # naive ET
        tt = ts.time()

        # ── 1) RETEST CHECK FIRST (before this bar can also create a new zone) ──
        # Enter only in the configured window. A retest = current bar's range overlaps a
        # fresh zone created on an EARLIER bar (strictly created_i < i).
        if win_start <= tt <= win_end and local >= WARMUP_BARS:
            cooldown_ok = (
                last_sig_time is None
                or (ts - last_sig_time).total_seconds() / 60.0 >= COOLDOWN_MIN
            )
            if cooldown_ok:
                # Demand zone retest -> price dipped back DOWN into the zone -> CALL.
                hit = _first_retest(demand_zones, i, l, h, side="demand")
                if hit is not None:
                    z = hit
                    # invalidation = far (lower) edge of the demand zone minus slop
                    rej = z["lo"] - 0.01
                    signals.append(_mk_signal(rth, i, ts, "C", z, rej, vix_arr[i],
                                              a, "demand_retest"))
                    last_sig_time = ts
                    demand_zones.remove(z)
                else:
                    hit = _first_retest(supply_zones, i, l, h, side="supply")
                    if hit is not None:
                        z = hit
                        # invalidation = far (upper) edge of the supply zone plus slop
                        rej = z["hi"] + 0.01
                        signals.append(_mk_signal(rth, i, ts, "P", z, rej, vix_arr[i],
                                                  a, "supply_retest"))
                        last_sig_time = ts
                        supply_zones.remove(z)

        # ── 2) IMPULSE DETECTION -> create a fresh zone (any RTH bar can seed) ──
        # Zone seeded by impulse is testable starting the NEXT bar (created_i < retest_i).
        if local >= WARMUP_BARS and a > 0:
            body = abs(c - o)
            if body > IMPULSE_BODY_ATR_MULT * a:
                if c > o:
                    # strong GREEN -> demand zone = impulse body (open..close)
                    demand_zones.append({"created_i": i, "lo": o, "hi": c})
                elif c < o:
                    # strong RED -> supply zone = impulse body (close..open)
                    supply_zones.append({"created_i": i, "lo": c, "hi": o})

        # ── 3) age out stale zones (same-day only; reset handled at day flip) ──
        demand_zones = [z for z in demand_zones if i - z["created_i"] <= ZONE_MAX_AGE_BARS]
        supply_zones = [z for z in supply_zones if i - z["created_i"] <= ZONE_MAX_AGE_BARS]

    return signals


def _first_retest(zones: list[dict], i: int, bar_low: float, bar_high: float, side: str):
    """Return the first (oldest) fresh zone the current bar re-enters, else None.

    Retest = the current bar's range overlaps the zone band. created strictly before i.
    """
    for z in zones:
        if z["created_i"] >= i:
            continue
        lo, hi = z["lo"], z["hi"]
        height = max(1e-6, hi - lo)
        pad = RETEST_TOL * height
        # range overlap test
        if bar_high >= (lo - pad) and bar_low <= (hi + pad):
            return z
    return None


def _mk_signal(rth, i, ts, side, zone, rej, vix, atr_val, trigger) -> dict:
    return {
        "idx": i,
        "date": rth["date"].iloc[i],
        "time": ts.strftime("%H:%M"),
        "side": side,
        "zone_lo": round(zone["lo"], 2),
        "zone_hi": round(zone["hi"], 2),
        "rejection_level": float(rej),
        "vix": round(vix, 1),
        "atr": round(atr_val, 3),
        "trigger": trigger,
    }


def _run_fills(rth, signals, strike_offset, premium_stop_pct, entry_idx_override=None):
    """Run simulator_real over signals; return (rows, accumulators dict).

    entry_idx_override: optional list[int] of entry bar indices to use INSTEAD of the
    signal's own idx (for the random-null control). Same length as signals.
    """
    overall = _Acc()
    by_bias = {"C": _Acc(), "P": _Acc()}
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    rows: list[dict] = []
    no_data = 0
    # per-trade list for drop-top-5-days proper recompute
    trade_recs: list[dict] = []

    for k, s in enumerate(signals):
        idx = entry_idx_override[k] if entry_idx_override is not None else s["idx"]
        if idx + 2 >= len(rth):
            no_data += 1
            continue
        side = s["side"]
        # For the random control, recompute a plausible invalidation from the entry bar
        # so the bracket is comparable (chart-stop far enough not to instantly fire).
        if entry_idx_override is not None:
            spot = float(rth["close"].iloc[idx])
            rej = (spot - 3.0) if side == "C" else (spot + 3.0)
        else:
            rej = s["rejection_level"]
        fill = simulate_trade_real(
            entry_bar_idx=idx, entry_bar=rth.iloc[idx], spy_df=rth, ribbon_df=None,
            rejection_level=rej,
            triggers_fired=["sd_zone_reversal", s.get("trigger", "retest"),
                            "demand" if side == "C" else "supply"],
            side=side, qty=QTY, setup="SD_ZONE_REVERSAL",
            premium_stop_pct=premium_stop_pct, strike_offset=strike_offset)
        if fill is None:
            no_data += 1
            continue
        pnl = fill.dollar_pnl
        day = s["date"].isoformat()
        overall.add(pnl, day)
        by_bias[side].add(pnl, day)
        by_sample["IS_2025" if s["date"].year == 2025 else "OOS_2026"].add(pnl, day)
        by_q[_quarter(s["date"])].add(pnl, day)
        trade_recs.append({"day": day, "pnl": pnl, "year": s["date"].year})
        if entry_idx_override is None:
            rows.append({
                "date": day, "time": s["time"], "side": side,
                "zone": f"{s['zone_lo']}-{s['zone_hi']}", "vix": s["vix"],
                "trigger": s.get("trigger"), "strike": fill.strike,
                "entry_premium": round(fill.entry_premium, 3), "pnl": round(pnl, 2),
                "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason),
            })
    return rows, {
        "overall": overall, "by_bias": by_bias, "by_sample": by_sample,
        "by_q": by_q, "no_data": no_data, "trade_recs": trade_recs,
    }


def _drop_top5_days_per_trade(trade_recs: list[dict]) -> float | None:
    """Per-trade expectancy after removing the 5 highest-P&L *days* entirely."""
    if not trade_recs:
        return None
    by_day: dict[str, float] = defaultdict(float)
    for t in trade_recs:
        by_day[t["day"]] += t["pnl"]
    top5_days = set(d for d, _ in sorted(by_day.items(), key=lambda kv: kv[1], reverse=True)[:5])
    kept = [t for t in trade_recs if t["day"] not in top5_days]
    if not kept:
        return None
    return round(sum(t["pnl"] for t in kept) / len(kept), 2)


def _sign(x):
    return 0 if x is None or x == 0 else (1 if x > 0 else -1)


def _analyze_population(rth, signals, label, run_sweep=False):
    """Run the full battery on one signal population: primary survivor-structure fills,
    20-seed random-null, truncation check, and the 3 OP-11/null/truncation gates.

    `signals` already encode their entry window (the scan gated on it). The random-null
    draws random bars from the SAME window each signal occupies, per day, so it controls
    for the bracket and the time-of-day distribution — isolating the SIGNAL.
    """
    rows, acc = _run_fills(rth, signals, SURVIVOR_STRIKE_OFFSET, SURVIVOR_STOP)
    overall = acc["overall"]
    is_r = acc["by_sample"]["IS_2025"].report()
    oos_r = acc["by_sample"]["OOS_2026"].report()
    q_reports = {k: acc["by_q"][k].report() for k in sorted(acc["by_q"])}
    pos_q = sum(1 for r in q_reports.values() if r.get("total_pnl", 0) and r["total_pnl"] > 0)
    n_q = len(q_reports)
    drop_top5_pt = _drop_top5_days_per_trade(acc["trade_recs"])
    oos_pt = oos_r.get("avg_pnl")
    overall_pt = overall.report().get("avg_pnl")
    overall_top5 = overall.report().get("top5_day_pct")

    # window for the random-null draw = the actual span the signals occupy
    if signals:
        times = sorted(s["time"] for s in signals)
        w_start = dt.datetime.strptime(times[0], "%H:%M").time()
        w_end = dt.datetime.strptime(times[-1], "%H:%M").time()
    else:
        w_start, w_end = MORNING_START, MORNING_END
    day_win_idx: dict[dt.date, list[int]] = defaultdict(list)
    for i in range(len(rth)):
        tt = rth["ts_ny"].iloc[i].time()
        if w_start <= tt <= w_end and i + 2 < len(rth):
            day_win_idx[rth["date"].iloc[i]].append(i)
    null_means: list[float] = []
    for seed in range(RANDOM_SEEDS):
        rng = random.Random(1000 + seed)
        override = []
        for s in signals:
            cands = day_win_idx.get(s["date"], [])
            override.append(rng.choice(cands) if cands else s["idx"])
        _, nacc = _run_fills(rth, signals, SURVIVOR_STRIKE_OFFSET, SURVIVOR_STOP,
                             entry_idx_override=override)
        nrep = nacc["overall"].report()
        if nrep.get("n"):
            null_means.append(nrep["avg_pnl"])
    random_null_mean = round(sum(null_means) / len(null_means), 2) if null_means else None
    beats_random = (overall_pt is not None and random_null_mean is not None
                    and overall_pt > random_null_mean)

    _, cacc = _run_fills(rth, signals, SURVIVOR_STRIKE_OFFSET, -0.99)
    chartstop_pt = cacc["overall"].report().get("avg_pnl")
    truncation_safe = (chartstop_pt is not None and overall_pt is not None
                       and _sign(overall_pt) == _sign(chartstop_pt))

    sweep: dict[str, dict] = {}
    best_cfg = None
    best_oos_pt = None
    if run_sweep:
        for off in SWEEP_OFFSETS:
            for st in SWEEP_STOPS:
                _, sacc = _run_fills(rth, signals, off, st)
                sov = sacc["overall"].report()
                soos = sacc["by_sample"]["OOS_2026"].report()
                key = f"off{off}_stop{int(st*100)}"
                sweep[key] = {"strike_offset": off, "premium_stop_pct": st,
                              "overall": sov, "oos": soos}
                if soos.get("n", 0) >= 20 and soos.get("avg_pnl") is not None:
                    if best_oos_pt is None or soos["avg_pnl"] > best_oos_pt:
                        best_oos_pt = soos["avg_pnl"]
                        best_cfg = key

    op11_pass = (oos_pt is not None and oos_pt > 0
                 and pos_q >= 4 and n_q >= 6
                 and (overall_top5 is not None and overall_top5 < 200)
                 and overall.n >= 20
                 and (drop_top5_pt is not None and drop_top5_pt > 0))
    clears_bar = bool(op11_pass and beats_random and truncation_safe)

    return {
        "label": label, "rows": rows, "acc": acc, "overall": overall,
        "is_r": is_r, "oos_r": oos_r, "q_reports": q_reports, "pos_q": pos_q, "n_q": n_q,
        "drop_top5_pt": drop_top5_pt, "oos_pt": oos_pt, "overall_pt": overall_pt,
        "overall_top5": overall_top5, "random_null_mean": random_null_mean,
        "random_null_min": round(min(null_means), 2) if null_means else None,
        "random_null_max": round(max(null_means), 2) if null_means else None,
        "beats_random": beats_random, "chartstop_pt": chartstop_pt,
        "truncation_safe": truncation_safe, "sweep": sweep, "best_cfg": best_cfg,
        "best_oos_pt": best_oos_pt, "op11_pass": op11_pass, "clears_bar": clears_bar,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tag", default="sd-zone-reversal")
    args = p.parse_args(argv)

    rth, vix_arr = _load_rth()
    atr = _compute_atr(rth)

    # PRIMARY population = the hypothesis morning window (09:30-11:00 ET).
    signals = scan_signals(rth, atr, vix_arr, MORNING_START, MORNING_END)
    side_counts = {"C": sum(1 for s in signals if s["side"] == "C"),
                   "P": sum(1 for s in signals if s["side"] == "P")}
    log.info("PRIMARY signals (morning 09:30-11:00 ET): %d  by side %s", len(signals), side_counts)

    # COMPANION population = same signal logic, all-RTH retest window (09:30-16:00).
    # The morning gate alone yields n=3 (uninvestigable); the all-RTH cut gives the
    # 3-gate battery enough n to actually discriminate. Diagnostic, not the hypothesis.
    sig_allrth = scan_signals(rth, atr, vix_arr, RTH_START, dt.time(15, 55))
    side_counts_all = {"C": sum(1 for s in sig_allrth if s["side"] == "C"),
                       "P": sum(1 for s in sig_allrth if s["side"] == "P")}
    log.info("COMPANION signals (all-RTH 09:30-15:55 ET): %d  by side %s",
             len(sig_allrth), side_counts_all)

    log.info("Analyzing PRIMARY (morning) population...")
    P = _analyze_population(rth, signals, "morning_0930_1100", run_sweep=True)
    log.info("Analyzing COMPANION (all-RTH) population...")
    A = _analyze_population(rth, sig_allrth, "all_rth_0930_1555", run_sweep=True)

    # The HYPOTHESIS verdict is on the PRIMARY (morning) population.
    overall = P["overall"]; oos_pt = P["oos_pt"]; overall_pt = P["overall_pt"]
    random_null_mean = P["random_null_mean"]; chartstop_pt = P["chartstop_pt"]
    op11_pass = P["op11_pass"]; beats_random = P["beats_random"]
    truncation_safe = P["truncation_safe"]; clears_bar = P["clears_bar"]
    is_r = P["is_r"]; oos_r = P["oos_r"]; q_reports = P["q_reports"]
    pos_q = P["pos_q"]; n_q = P["n_q"]; drop_top5_pt = P["drop_top5_pt"]
    overall_top5 = P["overall_top5"]; rows = P["rows"]; acc = P["acc"]
    best_cfg = P["best_cfg"]; best_oos_pt = P["best_oos_pt"]

    if overall.n < 20:
        comp = A
        comp_clears = comp["clears_bar"]
        comp_fails = [g for g, ok in [("OP-11", comp["op11_pass"]),
                                       ("random-null", comp["beats_random"]),
                                       ("truncation", comp["truncation_safe"])] if not ok]
        verdict = (
            f"NULL/REJECT (insufficient morning sample) — the hypothesis morning-only "
            f"(09:30-11:00 ET) cut yields just n={overall.n} fillable trades over 16mo, "
            f"too few for OP-11. The 09:30-11:00 retest of a fresh impulse zone is a "
            f"near-non-existent event on SPY 5m (4 signals / 342 days). The all-RTH "
            f"companion (n={comp['overall'].n}, same signal logic) "
            + ("ALSO FAILS [" + ", ".join(comp_fails) + "]"
               if not comp_clears else "unexpectedly CLEARS the bar")
            + f": OOS per-trade={comp['oos_pt']}, random-null mean={comp['random_null_mean']}, "
            f"chart-stop-only per-trade={comp['chartstop_pt']}. Net: sd_zone_reversal is "
            f"NOT a usable 0DTE edge — consistent with the 0DTE wall killing counter-trend "
            f"reversion (C3/L58, C16)."
        )
    elif clears_bar:
        verdict = ("SHIP — survivor-structure sd_zone_reversal cleared OP-11 + "
                   "random-null + truncation on the morning population. (Unexpected for "
                   "a reversion class — double-check before flipping live.)")
    else:
        fails = [g for g, ok in [("OP-11", op11_pass), ("random-null", beats_random),
                                  ("truncation", truncation_safe)] if not ok]
        verdict = (f"NULL/REJECT — sd_zone_reversal (REVERSION) FAILED: "
                   f"{', '.join(fails)}. Consistent with the 0DTE wall killing "
                   f"counter-trend reversion (C3/L58, C16). OOS per-trade="
                   f"{oos_pt}, random-null mean={random_null_mean}, "
                   f"chart-stop-only per-trade={chartstop_pt}.")
    sweep = P["sweep"]

    summary = {
        "run_date": dt.date.today().isoformat(),
        "strategy": "sd_zone_reversal",
        "cls": "reversion",
        "source": "SwjshAK docs/boba_strategy/STRATEGY_RULES.md (Boba supply/demand zone reversal)",
        "hypothesis": ("Fresh untested S/D zone from impulse candle (body>2xATR); first "
                       "retest reversal entry (demand->CALL, supply->PUT); 09:30-11:00 ET."),
        "window": f"{START}..{END}",
        "params": {
            "atr_len": ATR_LEN, "impulse_body_atr_mult": IMPULSE_BODY_ATR_MULT,
            "morning_window": f"{MORNING_START.strftime('%H:%M')}-{MORNING_END.strftime('%H:%M')} ET",
            "cooldown_min": COOLDOWN_MIN, "zone_max_age_bars": ZONE_MAX_AGE_BARS,
            "qty": QTY,
        },
        "primary_config": {
            "strike_offset": SURVIVOR_STRIKE_OFFSET, "premium_stop_pct": SURVIVOR_STOP,
            "note": "SURVIVOR STRUCTURE (ITM-2 + tight -8% stop + default v15 exits)",
        },
        "n_signals": len(signals),
        "n_signals_by_side": side_counts,
        "n_trades": overall.n,
        "n_no_opra_data": acc["no_data"],
        "overall": overall.report(),
        "by_bias": {("CALL" if k == "C" else "PUT"): v.report() for k, v in acc["by_bias"].items()},
        "by_sample": {"IS_2025": is_r, "OOS_2026": oos_r},
        "by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{n_q}",
        "self_verify": {
            "op11": {
                "pass": bool(op11_pass),
                "oos_per_trade": oos_pt,
                "oos_per_trade_gt0": bool(oos_pt is not None and oos_pt > 0),
                "positive_quarters": f"{pos_q}/{n_q}",
                "positive_quarters_ok": bool(pos_q >= 4 and n_q >= 6),
                "top5_day_pct": overall_top5,
                "top5_lt_200": bool(overall_top5 is not None and overall_top5 < 200),
                "n_trades": overall.n, "n_ge_20": bool(overall.n >= 20),
                "drop_top5_days_per_trade": drop_top5_pt,
                "drop_top5_still_positive": bool(drop_top5_pt is not None and drop_top5_pt > 0),
            },
            "random_null": {
                "beats_random_null": bool(beats_random),
                "strategy_per_trade": overall_pt,
                "random_null_mean": random_null_mean,
                "random_null_min": P["random_null_min"],
                "random_null_max": P["random_null_max"],
                "seeds": RANDOM_SEEDS,
                "delta_vs_null": (round(overall_pt - random_null_mean, 2)
                                  if (overall_pt is not None and random_null_mean is not None) else None),
            },
            "truncation": {
                "truncation_safe": bool(truncation_safe),
                "survivor_stop_per_trade": overall_pt,
                "chartstop_only_per_trade": chartstop_pt,
                "note": "sign must not invert between -8% stop and -99% (chart-stop-only)",
            },
        },
        "secondary_sweep": sweep,
        "best_sweep_config_oos": best_cfg,
        "best_sweep_oos_per_trade": best_oos_pt,
        "verdict": verdict,
        "clears_bar": clears_bar,
        "companion_all_rth": {
            "note": ("Same signal logic, retest window widened to all-RTH (09:30-15:55 ET) "
                     "so the 3-gate battery has enough n to discriminate. The morning-only "
                     "hypothesis cut is n=3 (uninvestigable). This is a DIAGNOSTIC, not the "
                     "hypothesis verdict."),
            "n_signals": len(sig_allrth),
            "n_signals_by_side": side_counts_all,
            "n_trades": A["overall"].n,
            "overall": A["overall"].report(),
            "by_bias": {("CALL" if k == "C" else "PUT"): v.report()
                        for k, v in A["acc"]["by_bias"].items()},
            "by_sample": {"IS_2025": A["is_r"], "OOS_2026": A["oos_r"]},
            "by_quarter": A["q_reports"],
            "positive_quarters": f"{A['pos_q']}/{A['n_q']}",
            "self_verify": {
                "op11_pass": bool(A["op11_pass"]),
                "oos_per_trade": A["oos_pt"],
                "drop_top5_days_per_trade": A["drop_top5_pt"],
                "top5_day_pct": A["overall_top5"],
                "beats_random_null": bool(A["beats_random"]),
                "strategy_per_trade": A["overall_pt"],
                "random_null_mean": A["random_null_mean"],
                "random_null_min": A["random_null_min"],
                "random_null_max": A["random_null_max"],
                "truncation_safe": bool(A["truncation_safe"]),
                "chartstop_only_per_trade": A["chartstop_pt"],
            },
            "secondary_sweep": A["sweep"],
            "best_sweep_config_oos": A["best_cfg"],
            "best_sweep_oos_per_trade": A["best_oos_pt"],
            "clears_bar": A["clears_bar"],
        },
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) — the only WR/expectancy authority",
            "metric": "per-trade expectancy (avg_pnl) reported, not WR alone (OP-14/OP-20)",
            "concentration": "top5_day_pct + drop-top-5-days per-trade shown (OP-20 #5)",
            "is_oos": "IS=2025, OOS=2026; per-quarter breakdown shown",
            "random_null": "20-seed random-entry control on same bracket (signal vs bracket)",
            "truncation": "sign-invert check between -8% and chart-stop-only (stop artifact guard)",
            "class_caveat": ("REVERSION class — counter-trend fade. The 0DTE wall "
                             "(theta+delta+stop-misfire) has killed reversion repeatedly "
                             "(C3/L58, C16). Failure is the expected, honest outcome."),
            "no_cherry_pick": "single honest read; sweep reported in full, not best-of (anti-2.10)",
        },
        "results": rows,
    }

    out = ROOT / "analysis" / "recommendations" / f"swjshak-{args.tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", out)

    print("\n=== SwjshAK sd_zone_reversal (REVERSION) — REAL-FILLS VERDICT ===")
    print("--- PRIMARY (hypothesis morning 09:30-11:00 ET) ---")
    print(f"signals={len(signals)} (by side {side_counts}) trades={overall.n} no_opra={acc['no_data']}")
    print(f"OVERALL  : {overall.report()}")
    print(f"CALL     : {acc['by_bias']['C'].report()}")
    print(f"PUT      : {acc['by_bias']['P'].report()}")
    print(f"IS 2025  : {is_r}")
    print(f"OOS 2026 : {oos_r}")
    print(f"pos_quarters={pos_q}/{n_q}  by_quarter={q_reports}")
    print(f"[a] OP-11 pass={op11_pass}  oos_pt={oos_pt}  drop_top5_pt={drop_top5_pt}  top5%={overall_top5}")
    print(f"[b] beats_random={beats_random}  strat_pt={overall_pt}  null_mean={random_null_mean} "
          f"(min={P['random_null_min']} max={P['random_null_max']})")
    print(f"[c] truncation_safe={truncation_safe}  -8%_pt={overall_pt}  -99%_pt={chartstop_pt}")
    print(f"best_sweep_oos={best_cfg} ({best_oos_pt})")
    print(f"PRIMARY CLEARS_BAR={clears_bar}")
    print("--- COMPANION (all-RTH 09:30-15:55 ET, same signal logic, diagnostic) ---")
    print(f"signals={len(sig_allrth)} (by side {side_counts_all}) trades={A['overall'].n}")
    print(f"OVERALL  : {A['overall'].report()}")
    print(f"IS 2025  : {A['is_r']}")
    print(f"OOS 2026 : {A['oos_r']}")
    print(f"pos_quarters={A['pos_q']}/{A['n_q']}")
    print(f"[a] OP-11 pass={A['op11_pass']}  oos_pt={A['oos_pt']}  drop_top5_pt={A['drop_top5_pt']}  top5%={A['overall_top5']}")
    print(f"[b] beats_random={A['beats_random']}  strat_pt={A['overall_pt']}  null_mean={A['random_null_mean']}")
    print(f"[c] truncation_safe={A['truncation_safe']}  -8%_pt={A['overall_pt']}  -99%_pt={A['chartstop_pt']}")
    print(f"best_sweep_oos={A['best_cfg']} ({A['best_oos_pt']})")
    print(f"COMPANION CLEARS_BAR={A['clears_bar']}")
    print(f"\nVERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
