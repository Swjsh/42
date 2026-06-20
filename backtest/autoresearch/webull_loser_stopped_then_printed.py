"""Mine J's Webull LOSERS for the "barely stopped, then it printed" pattern.

J's stated reason for quitting (verbatim): "I'd get in, it'd go negative, I'd get
stopped/panic-sold on a BARELY stop-out, then it absolutely printed (cheap contracts
hitting $1000). I knew in my gut what would happen but couldn't hold my rules or set
TP targets."

This module quantifies that exact pattern against his real losing round-trips and
validates Project Gamma's exit doctrine (chart-stop-primary, -50% catastrophe cap,
mechanical TP/runner, hold-to-15:50) against his lived failures.

THREE PARTS
-----------
PART A — loser BEHAVIOR (EXACT, from the ledger alone; no model):
  - hold-time asymmetry (losers vs winners)
  - loss-size distribution: the % loss at which he exited (the "barely stopped" tell)
  - adverse-excursion buckets (his realized exit loss %)
  - time-of-day + size of the panic exits

PART B — the "stopped then printed" reconstruction:
  - underlying path = EXACT (free SPY 5m IEX, SPX/SPY ~10:1 proxy)
  - after his exit, did the UNDERLYING continue in his thesis direction? (EXACT)
  - the 0DTE option payoff at the post-exit favorable extreme = ESTIMATE
    (Black-Scholes, IV backed out of HIS OWN entry premium — the most honest,
     self-consistent 0DTE IV; no fabricated VIX). Every $ here is labelled ESTIMATE.

PART C — the engine-exit counterfactual:
  - if each loser had used the ENGINE's exits (wide structural stop / -50% cap,
    mechanical TP, hold to 15:50) instead of his panic-cut, how many survive to a
    TP or EOD winner, and what is the P&L delta? (option $ = ESTIMATE)

HONESTY CONTRACT
----------------
  - Part A numbers are EXACT (his fills).
  - "printed after" DIRECTION is EXACT (SPY underlying continued or not).
  - Only the $ option payoff is MODELED — labelled ESTIMATE everywhere.
  - No exact 2021-23 option prices exist without a paid vendor; we don't pretend.

Reuses the winner-mining infra: credential loader + DST-correct ET conversion +
IEX 5m fetch pattern from webull_winner_journal.py. Pulls only the loser dates not
already cached. Idempotent: caches to analysis/webull-j-trades/loser_bar_cache.json.

Pure stdlib + the repo BS pricer (backtest/lib/pricing.py). py_compile clean.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import statistics
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

# Repo pricer (reuse — do not rebuild a BS).
REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "backtest"))
from lib.pricing import black_scholes  # noqa: E402

OUT_DIR = REPO / "analysis" / "webull-j-trades"
ROUNDTRIPS = OUT_DIR / "j_roundtrips.csv"
WINNER_CACHE = OUT_DIR / "winner_bar_cache.json"   # reuse dates already pulled
LOSER_CACHE = OUT_DIR / "loser_bar_cache.json"     # new, idempotent
OUT_JSON = OUT_DIR / "loser_analysis.json"

ALPACA_BARS_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
_ET = ZoneInfo("America/New_York")

# SPX/SPY ~10:1. J's SPX strikes (e.g. 4200) map to the SPY proxy via /SPX_SPY.
SPX_SPY = 10.0
RISK_FREE = 0.04
# Engine exit doctrine constants (v15) for the Part C counterfactual.
ENGINE_CATASTROPHE_CAP = -0.50   # -50% premium catastrophe cap (the "stop")
ENGINE_TP1_FRAC = 0.30           # +30% premium TP1 fallback (Safe book)
ENGINE_EOD_ET = dt.time(15, 50)  # hard time stop


# --------------------------------------------------------------------------- #
# Credentials (reused pattern — env first, then ~/.claude.json alpaca block)
# --------------------------------------------------------------------------- #
def _load_alpaca_creds() -> tuple[Optional[str], Optional[str]]:
    key = os.environ.get("ALPACA_API_KEY") or os.environ.get("APCA_API_KEY_ID")
    sec = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("APCA_API_SECRET_KEY")
    if key and sec:
        return key, sec
    cfg = Path(os.path.expanduser("~/.claude.json"))
    if not cfg.exists():
        return key, sec
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return key, sec
    found: dict[str, str] = {}

    def _walk(node: Any) -> None:
        if found:
            return
        if isinstance(node, dict):
            if node.get("ALPACA_API_KEY") and node.get("ALPACA_SECRET_KEY"):
                found["key"] = node["ALPACA_API_KEY"]
                found["sec"] = node["ALPACA_SECRET_KEY"]
                return
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(data)
    return (found.get("key") or key), (found.get("sec") or sec)


# --------------------------------------------------------------------------- #
# Bars
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Bar:
    t_et: dt.datetime  # naive ET
    o: float
    h: float
    l: float
    c: float
    v: int


def _utc_to_et(ts_z: str) -> dt.datetime:
    """UTC ISO ts -> naive ET (DST-correct via America/New_York; lesson C6)."""
    s = ts_z.replace("Z", "+00:00")
    base = dt.datetime.fromisoformat(s)
    if base.tzinfo is None:
        base = base.replace(tzinfo=dt.timezone.utc)
    return base.astimezone(_ET).replace(tzinfo=None)


def _fetch_spy_bars(date: str, key: str, sec: str) -> Optional[list[dict[str, Any]]]:
    """SPY 5m IEX bars for one ET date (full UTC day so RTH covered under any DST)."""
    start = f"{date}T08:00:00Z"
    end = f"{date}T23:59:00Z"
    params = (
        f"?timeframe=5Min&feed=iex&adjustment=raw&limit=2000"
        f"&start={start}&end={end}&sort=asc"
    )
    req = urllib.request.Request(
        ALPACA_BARS_URL + params,
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        print(f"    WARN fetch {date}: {exc}")
        return None
    bars = payload.get("bars") or []
    if not bars:
        return None
    return [{"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"],
             "c": b["c"], "v": int(b.get("v", 0))} for b in bars]


def _load_cache(path: Path) -> dict[str, list[dict[str, Any]]]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def build_loser_cache(loser_dates: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Idempotent: reuse winner cache + any existing loser cache; pull only misses."""
    winner = _load_cache(WINNER_CACHE)
    cache = _load_cache(LOSER_CACHE)
    # seed from winner cache (free reuse)
    for d in loser_dates:
        if d not in cache and d in winner:
            cache[d] = winner[d]
    missing = [d for d in loser_dates if d not in cache]
    if missing:
        key, sec = _load_alpaca_creds()
        if not (key and sec):
            print("    WARN no Alpaca creds — cannot pull missing dates:", len(missing))
        else:
            print(f"    pulling {len(missing)} missing loser dates from Alpaca IEX...")
            for i, d in enumerate(missing, 1):
                bars = _fetch_spy_bars(d, key, sec)
                if bars:
                    cache[d] = bars
                    print(f"      [{i}/{len(missing)}] {d}: {len(bars)} bars")
                else:
                    print(f"      [{i}/{len(missing)}] {d}: NO DATA")
            LOSER_CACHE.write_text(json.dumps(cache, separators=(",", ":")),
                                   encoding="utf-8")
    return cache


def _rth_bars(raw: list[dict[str, Any]]) -> list[Bar]:
    out = []
    for b in raw:
        t_et = _utc_to_et(b["t"])
        if dt.time(9, 30) <= t_et.time() < dt.time(16, 0):
            out.append(Bar(t_et=t_et, o=float(b["o"]), h=float(b["h"]),
                           l=float(b["l"]), c=float(b["c"]), v=int(b["v"])))
    out.sort(key=lambda x: x.t_et)
    return out


# --------------------------------------------------------------------------- #
# Ledger loading
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RoundTrip:
    date: str
    symbol: str
    underlier: str     # SPY / SPXW / SPX
    bias: str          # bull / bear
    right: str         # C / P
    strike: float      # raw strike (SPXW ~4200 ; SPY ~420)
    is_0dte: bool
    qty: int
    entry_dt: dt.datetime
    exit_dt: dt.datetime
    hold_min: float
    entry_px: float
    exit_px: float
    pnl: float

    @property
    def pct_move(self) -> float:
        """Realized premium move at exit: exit/entry - 1 (negative for a loss)."""
        if self.entry_px <= 0:
            return 0.0
        return self.exit_px / self.entry_px - 1.0

    @property
    def strike_spy(self) -> float:
        """Strike in SPY units (the proxy underlying path is SPY).

        SPXW/SPX strikes are ~10x SPY and must be divided by SPX_SPY; native SPY
        strikes are already in SPY units. Blindly /10 corrupts the SPY trades
        (e.g. a 443 SPY call would become a 44.3 strike — absurdly deep ITM)."""
        if self.underlier == "SPY":
            return self.strike
        return self.strike / SPX_SPY


def _parse_dt(s: str) -> dt.datetime:
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def load_roundtrips() -> list[RoundTrip]:
    rows = list(csv.DictReader(ROUNDTRIPS.open(encoding="utf-8")))
    out: list[RoundTrip] = []
    for r in rows:
        if r["is_spx_family"] != "True" or r["status"] != "closed":
            continue
        try:
            out.append(RoundTrip(
                date=r["date"], symbol=r["symbol"], underlier=r["underlier"],
                bias=r["bias"], right=r["right"],
                strike=float(r["strike"]), is_0dte=(r["is_0dte"] == "True"),
                qty=int(r["qty"]),
                entry_dt=_parse_dt(r["entry_time"]), exit_dt=_parse_dt(r["exit_time"]),
                hold_min=float(r["hold_min"]),
                entry_px=float(r["entry_px"]), exit_px=float(r["exit_px"]),
                pnl=float(r["pnl"]),
            ))
        except (ValueError, KeyError):
            continue
    return out


# --------------------------------------------------------------------------- #
# PART A — behaviour stats (EXACT from ledger)
# --------------------------------------------------------------------------- #
def _summ(vals: list[float]) -> dict[str, float]:
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "mean": round(statistics.mean(vals), 2),
        "median": round(statistics.median(vals), 2),
        "p25": round(_pct(vals, 25), 2),
        "p75": round(_pct(vals, 75), 2),
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
    }


def _pct(vals: list[float], p: float) -> float:
    s = sorted(vals)
    if not s:
        return 0.0
    k = (len(s) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def part_a_behaviour(rts: list[RoundTrip]) -> dict[str, Any]:
    losers = [r for r in rts if r.pnl < 0]
    winners = [r for r in rts if r.pnl > 0]

    # 1. hold-time asymmetry
    hold = {
        "losers": _summ([r.hold_min for r in losers]),
        "winners": _summ([r.hold_min for r in winners]),
    }

    # 2. loss-size distribution (the "barely stopped" tell): exit premium % loss
    loss_pcts = [r.pct_move * 100 for r in losers]   # negative numbers
    # Buckets by severity of the realized adverse move.
    buckets = {
        "barely_0_to_-15%": 0,    # the panic-on-a-small-poke band
        "moderate_-15_to_-35%": 0,
        "deep_-35_to_-60%": 0,
        "blown_out_<-60%": 0,
    }
    for p in loss_pcts:
        if p > -15:
            buckets["barely_0_to_-15%"] += 1
        elif p > -35:
            buckets["moderate_-15_to_-35%"] += 1
        elif p > -60:
            buckets["deep_-35_to_-60%"] += 1
        else:
            buckets["blown_out_<-60%"] += 1
    n_los = len(losers)
    loss_size = {
        "exit_loss_pct": _summ(loss_pcts),
        "adverse_excursion_buckets": buckets,
        "adverse_excursion_buckets_pct": {
            k: round(100 * v / n_los, 1) for k, v in buckets.items()
        },
        "n_losers": n_los,
        # the headline "barely stopped" share = exited within -15%
        "share_barely_stopped_within_15pct": round(
            100 * buckets["barely_0_to_-15%"] / n_los, 1),
        "share_exited_within_25pct": round(
            100 * sum(1 for p in loss_pcts if p > -25) / n_los, 1),
    }

    # 4. time-of-day + size of panic exits
    def _bucket_30(t: dt.datetime) -> str:
        m = t.minute - (t.minute % 30)
        return t.replace(minute=m).strftime("%H:%M")

    tod: dict[str, dict[str, Any]] = {}
    for r in losers:
        b = _bucket_30(r.entry_dt)
        d = tod.setdefault(b, {"n": 0, "holds": [], "loss_pcts": []})
        d["n"] += 1
        d["holds"].append(r.hold_min)
        d["loss_pcts"].append(r.pct_move * 100)
    tod_out = {
        b: {
            "n": d["n"],
            "median_hold_min": round(statistics.median(d["holds"]), 1),
            "median_loss_pct": round(statistics.median(d["loss_pcts"]), 1),
        }
        for b, d in sorted(tod.items())
    }

    # size bands: does bigger size correlate with faster / worse panic?
    def _band(q: int) -> str:
        if q <= 2:
            return "1-2"
        if q <= 5:
            return "3-5"
        return "6+"

    size_bands: dict[str, dict[str, Any]] = {}
    for r in losers:
        b = _band(r.qty)
        d = size_bands.setdefault(b, {"holds": [], "loss_pcts": [], "pnls": []})
        d["holds"].append(r.hold_min)
        d["loss_pcts"].append(r.pct_move * 100)
        d["pnls"].append(r.pnl)
    size_out = {
        b: {
            "n": len(d["holds"]),
            "median_hold_min": round(statistics.median(d["holds"]), 1),
            "median_loss_pct": round(statistics.median(d["loss_pcts"]), 1),
            "mean_loss_dollars": round(statistics.mean(d["pnls"]), 0),
            "total_loss_dollars": round(sum(d["pnls"]), 0),
        }
        for b, d in sorted(size_bands.items())
    }

    return {
        "_source": "EXACT from j_roundtrips.csv (his real fills) — no model",
        "n_losers": n_los,
        "n_winners": len(winners),
        "hold_time_min": hold,
        "loss_size_distribution": loss_size,
        "time_of_day_panic_profile": tod_out,
        "size_band_panic_profile": size_out,
    }


# --------------------------------------------------------------------------- #
# PART B — "stopped then printed" (underlying EXACT, payoff ESTIMATE)
# --------------------------------------------------------------------------- #
def _tte_years(now_et: dt.datetime) -> float:
    expiry = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    if now_et >= expiry:
        return 1.0 / (365.25 * 24 * 60)
    return max(1.0 / (365.25 * 24 * 60),
              (expiry - now_et).total_seconds() / (365.25 * 24 * 60 * 60))


def _implied_iv_from_entry(spot: float, strike: float, is_call: bool,
                           tte: float, target_px: float) -> Optional[float]:
    """Back out IV that reproduces J's ACTUAL entry premium (bisection).

    This anchors the 0DTE option model to a real observed price (his fill) rather
    than a fabricated VIX — the most honest, self-consistent IV for that contract.
    Returns None if no IV in [1%, 600%] reproduces the price (e.g. price below
    intrinsic — then we fall back to intrinsic-aware pricing at the caller).
    """
    intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
    if target_px <= intrinsic + 1e-6:
        return None  # price at/under intrinsic — vol can't be solved
    lo, hi = 0.01, 6.0
    p_lo, _ = black_scholes(spot, strike, lo, tte, is_call, RISK_FREE)
    p_hi, _ = black_scholes(spot, strike, hi, tte, is_call, RISK_FREE)
    if not (p_lo <= target_px <= p_hi):
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        p_mid, _ = black_scholes(spot, strike, mid, tte, is_call, RISK_FREE)
        if abs(p_mid - target_px) < 1e-4:
            return mid
        if p_mid < target_px:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _spot_at(bars: list[Bar], t: dt.datetime) -> Optional[float]:
    """Underlying close of the 5m bar containing time t (floor to 5m)."""
    m = t.minute - (t.minute % 5)
    target = t.replace(minute=m, second=0, microsecond=0)
    best = None
    for b in bars:
        if b.t_et <= target:
            best = b
    return best.c if best else None


@dataclass(frozen=True)
class PrintedResult:
    date: str
    symbol: str
    bias: str
    is_call: bool
    strike_spx: float
    strike_spy: float
    qty: int
    entry_px: float
    exit_px: float
    pnl: float
    entry_spot: Optional[float]
    exit_spot: Optional[float]
    # underlying continuation AFTER exit (EXACT)
    fav_extreme_spot: Optional[float]      # best favorable spot from exit->EOD
    fav_move_pts: Optional[float]          # favorable underlying move (SPY pts)
    eod_spot: Optional[float]
    continued_his_way: Optional[bool]
    # option payoff (ESTIMATE)
    iv_used: Optional[float]
    iv_source: str
    est_value_at_fav_extreme: Optional[float]   # per-contract $ (×100)
    est_value_at_eod: Optional[float]
    est_missed_gain_vs_exit: Optional[float]    # (fav_value - exit_px)*100*qty
    est_peak_multiple: Optional[float]          # fav_value / exit_px


def reconstruct_printed(rts: list[RoundTrip],
                        cache: dict[str, list[dict[str, Any]]]) -> list[PrintedResult]:
    """For each 0DTE loser: did the underlying continue his way after his exit, and
    what would his EXACT contract have been worth at the post-exit favorable extreme?
    """
    results: list[PrintedResult] = []
    for r in rts:
        if r.pnl >= 0 or not r.is_0dte:
            continue
        raw = cache.get(r.date)
        is_call = r.right == "C"
        strike_spy = r.strike_spy
        base = dict(
            date=r.date, symbol=r.symbol, bias=r.bias, is_call=is_call,
            strike_spx=r.strike, strike_spy=round(strike_spy, 2), qty=r.qty,
            entry_px=r.entry_px, exit_px=r.exit_px, pnl=r.pnl,
        )
        if not raw:
            results.append(PrintedResult(
                **base, entry_spot=None, exit_spot=None, fav_extreme_spot=None,
                fav_move_pts=None, eod_spot=None, continued_his_way=None,
                iv_used=None, iv_source="no_bars", est_value_at_fav_extreme=None,
                est_value_at_eod=None, est_missed_gain_vs_exit=None,
                est_peak_multiple=None))
            continue
        bars = _rth_bars(raw)
        if not bars:
            results.append(PrintedResult(
                **base, entry_spot=None, exit_spot=None, fav_extreme_spot=None,
                fav_move_pts=None, eod_spot=None, continued_his_way=None,
                iv_used=None, iv_source="no_rth_bars", est_value_at_fav_extreme=None,
                est_value_at_eod=None, est_missed_gain_vs_exit=None,
                est_peak_multiple=None))
            continue

        entry_spot = _spot_at(bars, r.entry_dt)
        exit_spot = _spot_at(bars, r.exit_dt)
        eod_spot = bars[-1].c

        # Bars strictly AFTER his exit (look forward is intentional here — this is
        # the counterfactual of what he missed by exiting).
        m = r.exit_dt.minute - (r.exit_dt.minute % 5)
        exit_floor = r.exit_dt.replace(minute=m, second=0, microsecond=0)
        post = [b for b in bars if b.t_et > exit_floor]

        if exit_spot is None or not post:
            results.append(PrintedResult(
                **base, entry_spot=entry_spot, exit_spot=exit_spot,
                fav_extreme_spot=None, fav_move_pts=None, eod_spot=eod_spot,
                continued_his_way=None, iv_used=None, iv_source="no_post_bars",
                est_value_at_fav_extreme=None, est_value_at_eod=None,
                est_missed_gain_vs_exit=None, est_peak_multiple=None))
            continue

        # Favorable extreme AFTER exit (calls -> highest high; puts -> lowest low).
        if is_call:
            fav_extreme = max(b.h for b in post)
            fav_move = fav_extreme - exit_spot
            continued = fav_extreme > exit_spot
        else:
            fav_extreme = min(b.l for b in post)
            fav_move = exit_spot - fav_extreme   # favorable = down for a put
            continued = fav_extreme < exit_spot

        # ---- option payoff ESTIMATE ----
        # IV: back out from his ENTRY premium at his entry time + entry spot.
        iv = None
        iv_source = "entry_implied"
        if entry_spot is not None:
            tte_entry = _tte_years(r.entry_dt)
            iv = _implied_iv_from_entry(entry_spot, strike_spy, is_call,
                                        tte_entry, r.entry_px)
        if iv is None:
            # Fallback: back out from EXIT premium (still a real observed price).
            if exit_spot is not None:
                tte_exit = _tte_years(r.exit_dt)
                iv = _implied_iv_from_entry(exit_spot, strike_spy, is_call,
                                            tte_exit, r.exit_px)
                iv_source = "exit_implied"
        if iv is None:
            # Last resort: typical 0DTE IV proxy (~25%). Labelled.
            iv = 0.25
            iv_source = "fallback_0.25"

        # Time of the favorable-extreme bar (use the bar that printed the extreme).
        ext_bar = None
        for b in post:
            hit = (b.h == fav_extreme) if is_call else (b.l == fav_extreme)
            if hit:
                ext_bar = b
                break
        ext_time = ext_bar.t_et if ext_bar else post[-1].t_et
        tte_ext = _tte_years(ext_time)
        val_fav, _ = black_scholes(fav_extreme, strike_spy, iv, tte_ext,
                                   is_call, RISK_FREE)
        # EOD value (at the last bar, near-zero TTE -> intrinsic-dominated).
        tte_eod = _tte_years(bars[-1].t_et)
        val_eod, _ = black_scholes(eod_spot, strike_spy, iv, tte_eod,
                                   is_call, RISK_FREE)

        est_missed = (val_fav - r.exit_px) * 100 * r.qty
        peak_mult = (val_fav / r.exit_px) if r.exit_px > 0 else None

        results.append(PrintedResult(
            **base, entry_spot=round(entry_spot, 2) if entry_spot else None,
            exit_spot=round(exit_spot, 2),
            fav_extreme_spot=round(fav_extreme, 2),
            fav_move_pts=round(fav_move, 2),
            eod_spot=round(eod_spot, 2),
            continued_his_way=bool(continued),
            iv_used=round(iv, 3), iv_source=iv_source,
            est_value_at_fav_extreme=round(val_fav, 2),
            est_value_at_eod=round(val_eod, 2),
            est_missed_gain_vs_exit=round(est_missed, 0),
            est_peak_multiple=round(peak_mult, 2) if peak_mult else None,
        ))
    return results


def part_b_summary(prs: list[PrintedResult]) -> dict[str, Any]:
    scored = [p for p in prs if p.continued_his_way is not None]
    continued = [p for p in scored if p.continued_his_way]
    # "continued MEANINGFULLY" = favorable underlying move >= 0.25% of spot after exit
    # (0.25% ~ $1 on SPY; filters the trivial 1-tick-lower noise so the stat means
    #  "the move he was right about actually extended").
    cont_meaningful = [
        p for p in continued
        if p.fav_move_pts is not None and p.exit_spot
        and p.fav_move_pts >= 0.0025 * p.exit_spot
    ]
    # "printed big" = the modeled PEAK value was a multiple of his EXIT price
    printed_2x = [p for p in continued
                  if p.est_peak_multiple and p.est_peak_multiple >= 2.0]
    printed_3x = [p for p in continued
                  if p.est_peak_multiple and p.est_peak_multiple >= 3.0]
    printed_5x = [p for p in continued
                  if p.est_peak_multiple and p.est_peak_multiple >= 5.0]
    # PEAK missed gain (optimistic: best tick) — only positive cases
    missed_vals = [p.est_missed_gain_vs_exit for p in continued
                   if p.est_missed_gain_vs_exit and p.est_missed_gain_vs_exit > 0]
    # CONSERVATIVE: hold-to-EOD value vs his exit (what he could have done by NOT panicking)
    eod_better = []          # cases where EOD value > his exit value
    eod_missed_vals = []
    for p in scored:
        if p.est_value_at_eod is None:
            continue
        delta = (p.est_value_at_eod - p.exit_px) * 100 * p.qty
        if delta > 0:
            eod_better.append(p)
            eod_missed_vals.append(delta)
    fav_moves = [p.fav_move_pts for p in continued if p.fav_move_pts is not None]
    mults = [p.est_peak_multiple for p in continued if p.est_peak_multiple]

    return {
        "_underlying_source": "EXACT — free SPY 5m IEX (SPX/SPY ~10:1 proxy)",
        "_payoff_source": "ESTIMATE — Black-Scholes, IV implied from J's own fills",
        "n_losers_scored": len(scored),
        "n_no_bars": len([p for p in prs if p.continued_his_way is None]),
        # direction (EXACT) — two thresholds
        "n_continued_his_way_any": len(continued),
        "pct_continued_his_way_any": round(100 * len(continued) / len(scored), 1) if scored else 0,
        "n_continued_meaningfully_ge_0p25pct": len(cont_meaningful),
        "pct_continued_meaningfully": round(100 * len(cont_meaningful) / len(scored), 1) if scored else 0,
        "median_favorable_move_after_exit_spy_pts": round(statistics.median(fav_moves), 2) if fav_moves else 0,
        # PEAK payoff (optimistic, ESTIMATE)
        "n_printed_2x_after_exit_EST": len(printed_2x),
        "pct_printed_2x_EST": round(100 * len(printed_2x) / len(scored), 1) if scored else 0,
        "n_printed_3x_after_exit_EST": len(printed_3x),
        "n_printed_5x_after_exit_EST": len(printed_5x),
        "median_peak_multiple_EST": round(statistics.median(mults), 2) if mults else 0,
        "max_peak_multiple_EST": round(max(mults), 2) if mults else 0,
        "total_est_PEAK_missed_gain_dollars_EST": round(sum(missed_vals), 0),
        "median_est_PEAK_missed_gain_per_case_EST": round(statistics.median(missed_vals), 0) if missed_vals else 0,
        # CONSERVATIVE hold-to-EOD payoff (ESTIMATE)
        "n_better_if_held_to_EOD_EST": len(eod_better),
        "pct_better_if_held_to_EOD_EST": round(100 * len(eod_better) / len(scored), 1) if scored else 0,
        "total_est_HOLD_TO_EOD_missed_gain_dollars_EST": round(sum(eod_missed_vals), 0),
        "median_est_HOLD_TO_EOD_missed_gain_per_case_EST": round(statistics.median(eod_missed_vals), 0) if eod_missed_vals else 0,
    }


# --------------------------------------------------------------------------- #
# PART C — engine-exit counterfactual (option $ = ESTIMATE)
# --------------------------------------------------------------------------- #
def part_c_engine_counterfactual(rts: list[RoundTrip],
                                 cache: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Replay each 0DTE loser under the ENGINE's mechanical exits and compare.

    Engine exit model (premium-path, ESTIMATE via BS with entry-implied IV):
      - From entry, walk forward 5m. Price the contract each bar.
      - STOP only if premium <= entry*(1 + CATASTROPHE_CAP)  (i.e. -50%).
      - TP1: first bar where premium >= entry*(1 + TP1_FRAC) (+30%) -> sell TP1_qty
             half, runner rides with stop trailed to breakeven (entry).
      - Else hold to 15:50 ET, exit at that bar's modeled premium.
    Compares the engine P&L (ESTIMATE) to his ACTUAL P&L per loser.
    """
    import collections
    his_total = 0.0
    eng_total = 0.0
    survived = 0          # would NOT have hit the -50% cap (his panic-cut saved nothing)
    became_winner = 0     # engine exit P&L > 0
    scored = 0
    reason_tally: collections.Counter = collections.Counter()
    reason_pnl: dict[str, float] = collections.defaultdict(float)
    details: list[dict[str, Any]] = []

    for r in rts:
        if r.pnl >= 0 or not r.is_0dte:
            continue
        raw = cache.get(r.date)
        if not raw:
            continue
        bars = _rth_bars(raw)
        if not bars:
            continue
        entry_spot = _spot_at(bars, r.entry_dt)
        if entry_spot is None:
            continue
        is_call = r.right == "C"
        strike_spy = r.strike_spy
        tte_entry = _tte_years(r.entry_dt)
        iv = _implied_iv_from_entry(entry_spot, strike_spy, is_call,
                                    tte_entry, r.entry_px)
        if iv is None:
            iv = 0.25  # labelled fallback in JSON via iv_source absence

        m = r.entry_dt.minute - (r.entry_dt.minute % 5)
        entry_floor = r.entry_dt.replace(minute=m, second=0, microsecond=0)
        fwd = [b for b in bars if b.t_et >= entry_floor]
        if not fwd:
            continue
        scored += 1

        stop_px = r.entry_px * (1 + ENGINE_CATASTROPHE_CAP)
        tp1_px = r.entry_px * (1 + ENGINE_TP1_FRAC)
        qty = r.qty
        tp1_qty = max(1, int(round(qty * 0.50)))
        runner_qty = qty - tp1_qty

        # engine walk
        realized = 0.0          # $ booked
        runner_open = True
        runner_stop = stop_px   # trails to breakeven after TP1
        tp1_done = False
        exit_reason = "eod"
        for b in fwd:
            tte = _tte_years(b.t_et)
            # use the bar LOW/HIGH adverse price for stop, close for TP (conservative)
            prem_close, _ = black_scholes(b.c, strike_spy, iv, tte, is_call, RISK_FREE)
            # adverse extreme for stop check
            adverse_spot = b.l if is_call else b.h
            prem_adverse, _ = black_scholes(adverse_spot, strike_spy, iv, tte,
                                            is_call, RISK_FREE)
            # favorable extreme for TP check
            fav_spot = b.h if is_call else b.l
            prem_fav, _ = black_scholes(fav_spot, strike_spy, iv, tte,
                                        is_call, RISK_FREE)

            # stop on the still-open lots
            if not tp1_done and prem_adverse <= stop_px:
                realized += (stop_px - r.entry_px) * 100 * qty
                runner_open = False
                exit_reason = "catastrophe_stop"
                break
            if tp1_done and runner_open and prem_adverse <= runner_stop:
                realized += (runner_stop - r.entry_px) * 100 * runner_qty
                runner_open = False
                exit_reason = "runner_be_stop"
                break
            # TP1
            if not tp1_done and prem_fav >= tp1_px:
                realized += (tp1_px - r.entry_px) * 100 * tp1_qty
                tp1_done = True
                runner_stop = r.entry_px  # breakeven
                if b.t_et.time() >= ENGINE_EOD_ET:
                    realized += (prem_close - r.entry_px) * 100 * runner_qty
                    runner_open = False
                    exit_reason = "tp1_then_eod"
                    break
                continue
            # time stop
            if b.t_et.time() >= ENGINE_EOD_ET:
                live_qty = runner_qty if tp1_done else qty
                realized += (prem_close - r.entry_px) * 100 * live_qty
                runner_open = False
                exit_reason = "eod" if not tp1_done else "tp1_then_eod"
                break
        else:
            # ran out of bars before 15:50 (data ends early) — mark to last close
            last = fwd[-1]
            tte = _tte_years(last.t_et)
            prem_last, _ = black_scholes(last.c, strike_spy, iv, tte, is_call, RISK_FREE)
            live_qty = runner_qty if tp1_done else qty
            realized += (prem_last - r.entry_px) * 100 * live_qty
            exit_reason = "data_end"

        eng_pnl = realized
        his_total += r.pnl
        eng_total += eng_pnl
        reason_tally[exit_reason] += 1
        reason_pnl[exit_reason] += eng_pnl
        if exit_reason != "catastrophe_stop":
            survived += 1
        if eng_pnl > 0:
            became_winner += 1
        details.append({
            "date": r.date, "symbol": r.symbol, "qty": qty,
            "his_pnl": r.pnl, "eng_pnl_EST": round(eng_pnl, 0),
            "exit_reason": exit_reason, "iv": round(iv, 3),
        })

    return {
        "_payoff_source": "ESTIMATE — engine exits replayed via BS (entry-implied IV)",
        "n_scored": scored,
        "his_total_pnl_EXACT": round(his_total, 0),
        "engine_total_pnl_EST": round(eng_total, 0),
        "delta_engine_minus_his_EST": round(eng_total - his_total, 0),
        "n_would_survive_50pct_cap": survived,
        "pct_would_survive_50pct_cap": round(100 * survived / scored, 1) if scored else 0,
        "n_engine_exit_became_winner_EST": became_winner,
        "pct_engine_became_winner_EST": round(100 * became_winner / scored, 1) if scored else 0,
        "exit_reason_tally": dict(reason_tally),
        "exit_reason_pnl_EST": {k: round(v, 0) for k, v in reason_pnl.items()},
        "_detail_sample": sorted(details, key=lambda d: d["his_pnl"])[:15],
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    rts = load_roundtrips()
    losers0_dates = sorted(set(r.date for r in rts if r.pnl < 0 and r.is_0dte))
    print(f"loaded {len(rts)} spx-family closed round-trips")
    print(f"0DTE loser dates: {len(losers0_dates)}")

    cache = build_loser_cache(losers0_dates)
    have = sum(1 for d in losers0_dates if d in cache)
    print(f"loser bar cache: {have}/{len(losers0_dates)} dates available")

    part_a = part_a_behaviour(rts)
    prs = reconstruct_printed(rts, cache)
    part_b = part_b_summary(prs)
    part_c = part_c_engine_counterfactual(rts, cache)

    payload = {
        "_generated": dt.datetime.now().isoformat(timespec="seconds"),
        "_what": "J's Webull LOSERS — the 'barely stopped then it printed' analysis",
        "_honesty": {
            "part_a_behaviour": "EXACT from his real fills (ledger only)",
            "part_b_direction": "EXACT — SPY 5m underlying continued his way or not",
            "part_b_dollar_payoff": "ESTIMATE — BS, IV implied from J's own fills",
            "part_c_dollar_payoff": "ESTIMATE — engine exits replayed via BS",
            "note": "No exact 2021-23 option prices without a paid vendor; "
                    "all $ option values are modeled and labelled _EST.",
        },
        "universe": {
            "spx_family_closed_roundtrips": len(rts),
            "losers_all": len([r for r in rts if r.pnl < 0]),
            "winners_all": len([r for r in rts if r.pnl > 0]),
            "losers_0dte": len([r for r in rts if r.pnl < 0 and r.is_0dte]),
            "loser_0dte_dates": len(losers0_dates),
            "loser_0dte_dates_with_bars": have,
        },
        "part_a_behaviour": part_a,
        "part_b_stopped_then_printed": part_b,
        "part_c_engine_counterfactual": part_c,
        "part_b_per_loser": [vars(p) for p in prs],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {OUT_JSON}")

    # console headline
    print("\n" + "=" * 70)
    print("PART A — barely-stopped tell:",
          part_a["loss_size_distribution"]["share_barely_stopped_within_15pct"],
          "% exited within -15%")
    print("PART B — continued meaningfully:", part_b["pct_continued_meaningfully"],
          "%  |  printed >=2x (EST):", part_b["pct_printed_2x_EST"], "%")
    print("PART C — engine survives -50% cap:", part_c["pct_would_survive_50pct_cap"],
          "%  |  delta $ (EST):", part_c["delta_engine_minus_his_EST"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
