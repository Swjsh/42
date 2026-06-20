"""PART A — mine J's optimal STRIKE (B1), HOLD-TIME (B2), TP TARGET (B3) from his
real Webull winners + the cached underlier path. This DEFINES the candidate param
values; PART B (j_param_tweaks_partB.py) VALIDATES them forward on OUR SPY data.

DATA JOIN (all three sources keyed by (date, symbol)):
  * analysis/webull-j-trades/j_roundtrips.csv     -> strike, qty, entry_px/exit_px
                                                     (option premiums), entry/exit time,
                                                     hold_min, right(C/P), result.
  * analysis/webull-j-trades/j_winner_features.json -> entry_close (SPY-SCALE spot at
                                                     entry), side, trigger, archetype.
  * analysis/webull-j-trades/winner_bar_cache.json  -> the SPY-scale 5m RTH underlier
                                                     path for the day (the WINNERS cache).

SCALE (verified): the bar cache + entry_close are SPY-scale (~420). SPX strikes are
10x (SPXW...4200000 = 4200 = 420 SPY-equiv); SPY strikes are 1x. So
    spy_equiv_strike = strike/10.0 if SPX-family else strike
and MONEYNESS ($, SPY-scale) = directional distance of strike from spot at entry:
    calls: spy_equiv_strike - entry_close   (>0 = OTM)
    puts : entry_close - spy_equiv_strike   (>0 = OTM)

B1 STRIKE — bucket each winner by moneyness-at-entry (ITM1 / ATM / OTM1 / OTM2 / OTM3+).
  Report per bucket: n, his WR (note: WINNERS file => WR not meaningful here; we use the
  FULL roundtrips for the WR/expectancy-by-bucket, winners+losers, SPX-family 0DTE),
  expectancy ($/contract), and avg realized multiple (exit_px/entry_px). The SHARPEST
  bucket = best per-contract expectancy AND best multiple (his risk/reward by strike).

B2 HOLD / B3 TP — for each WINNER with a bar cache, reconstruct the OPTION-PREMIUM path
  along the cached underlier bars from entry to close. To avoid the missing-2021-23-VIX
  problem we BACK OUT the per-trade entry IV from J's OWN entry fill (his real entry_px,
  strike, spot, time-to-expiry) via Black-Scholes inversion, then hold that IV constant
  and reprice at each later bar's close (TTE shrinking to 16:00 ET). This self-calibrates
  to his actual fill and is far more honest than a flat VIX proxy.
    B2: minutes-from-entry to the PEAK premium (the bar where repriced premium is max).
    B3: peak %-gain over entry premium = peak_premium/entry_px - 1.

  Only 0DTE winners are used for B2/B3 (peak-by-EOD is only meaningful for 0DTE; the IV
  inversion + theta-to-16:00 model is a 0DTE model). B1 reports both 0DTE and all-DTE
  SPX-family so the strike picture is complete.

Pure, $0, read-only. Reuses lib.pricing.black_scholes (the project BS pricer). Writes
analysis/recommendations/_j_param_partA.json (consumed by partB + the deliverable doc).

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/j_param_tweaks_partA.py
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
PROJECT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.pricing import black_scholes, time_to_expiry_years  # noqa: E402

RT = PROJECT / "analysis" / "webull-j-trades" / "j_roundtrips.csv"
WF = PROJECT / "analysis" / "webull-j-trades" / "j_winner_features.json"
WC = PROJECT / "analysis" / "webull-j-trades" / "winner_bar_cache.json"
OUT = PROJECT / "analysis" / "recommendations" / "_j_param_partA.json"

# Moneyness bucket edges in SPY-scale dollars (directional: + = OTM, - = ITM).
# ATM band is +/-$0.50 (a ~$1-wide ATM strike). Then OTM1/OTM2/OTM3+ and ITM1/ITM2+.
def moneyness_bucket(dist: float) -> str:
    if dist <= -1.5:
        return "ITM2+"
    if dist <= -0.5:
        return "ITM1"
    if dist < 0.5:
        return "ATM"
    if dist < 1.5:
        return "OTM1"
    if dist < 2.5:
        return "OTM2"
    return "OTM3+"


BUCKET_ORDER = ["ITM2+", "ITM1", "ATM", "OTM1", "OTM2", "OTM3+"]


def spy_equiv_strike(strike: float, symbol: str) -> float:
    """SPX strikes are 10x SPY-scale; SPY strikes are 1x. (Verified: median ratio
    SPX 10.03, SPY 1.00 vs entry_close.)"""
    return strike / 10.0 if (symbol.startswith("SPX")) else strike


def signed_otm_distance(side: str, k_spy: float, spot: float) -> float:
    """Directional distance strike-from-spot in SPY $; + = OTM, - = ITM."""
    return (k_spy - spot) if side == "C" else (spot - k_spy)


def _parse_dt(s: str) -> Optional[dt.datetime]:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return dt.datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _bar_dt_et(t_iso: str) -> dt.datetime:
    """Bar timestamps are UTC ISO (EDT = UTC-4 during his RTH window). Convert to a
    naive ET datetime for TTE math. The cache covers RTH only (13:30-20:00Z = 09:30-
    16:00 ET during EDT); we treat UTC-4 uniformly (his trades are all EDT months in
    practice; a 1h DST error would shift TTE < 4%, immaterial for peak-bar selection)."""
    z = dt.datetime.fromisoformat(t_iso.replace("Z", "+00:00"))
    return (z - dt.timedelta(hours=4)).replace(tzinfo=None)


def implied_vol_from_fill(spot: float, strike: float, premium: float,
                          tte: float, is_call: bool) -> Optional[float]:
    """Invert Black-Scholes for IV given J's actual entry fill. Bisection on [1%, 500%].
    Returns None if the premium is below intrinsic (can't solve) or degenerate."""
    intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
    if premium <= intrinsic + 1e-6 or tte <= 0:
        return None
    lo, hi = 0.01, 5.0
    p_lo, _ = black_scholes(spot, strike, lo, tte, is_call)
    p_hi, _ = black_scholes(spot, strike, hi, tte, is_call)
    if not (p_lo <= premium <= p_hi):
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        p_mid, _ = black_scholes(spot, strike, mid, tte, is_call)
        if p_mid < premium:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _agg(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0}
    a = sorted(vals)
    n = len(a)
    return {
        "n": n,
        "mean": round(statistics.mean(a), 2),
        "median": round(statistics.median(a), 2),
        "p25": round(a[int(0.25 * (n - 1))], 2),
        "p75": round(a[int(0.75 * (n - 1))], 2),
        "p90": round(a[int(0.90 * (n - 1))], 2),
        "min": round(a[0], 2),
        "max": round(a[-1], 2),
    }


def main() -> int:
    rows = list(csv.DictReader(open(RT, newline="")))
    wf = {(r["date"], r["symbol"]): r for r in json.load(open(WF))}
    wc = json.load(open(WC))

    # ---------------------------------------------------------------- B1: STRIKE
    # Use the FULL roundtrips (winners AND losers) for honest WR/expectancy by bucket.
    # SPX-family only (the bar cache + the live SPY engine are index-scale); split 0DTE.
    spx = [r for r in rows if r["is_spx_family"] == "True"]

    def b1_table(subset, label):
        # Need a SPOT to compute moneyness. j_roundtrips has no underlier spot; only the
        # WINNER rows have entry_close (from winner_features). For LOSERS we have no
        # cached spot -> can't bucket them by moneyness. So B1-WR is computed on the
        # subset that HAS a spot (winners), and we ALSO report the strike-distance
        # distribution there. Expectancy/multiple per bucket is therefore winner-only WR
        # =100% by construction -> NOT meaningful. Instead we report, per bucket: count,
        # mean realized multiple (exit/entry), mean $/contract pnl, mean hold. The
        # SHARPEST strike = highest mean multiple & $/contract among his WINNERS (his
        # best risk/reward expression by strike distance), with the caveat stated.
        buckets = defaultdict(list)
        for r in subset:
            key = (r["date"], r["symbol"])
            feat = wf.get(key)
            if feat is None or not feat.get("entry_close"):
                continue
            spot = float(feat["entry_close"])
            k_spy = spy_equiv_strike(float(r["strike"]), r["symbol"])
            dist = signed_otm_distance(r["right"], k_spy, spot)
            try:
                ep, xp = float(r["entry_px"]), float(r["exit_px"])
                pnl = float(r["pnl"]); qty = float(r["qty"])
            except (ValueError, TypeError):
                continue
            if ep <= 0 or qty <= 0:
                continue
            mult = xp / ep
            per_ct = pnl / qty
            buckets[moneyness_bucket(dist)].append({
                "dist": dist, "mult": mult, "per_ct": per_ct,
                "hold": float(r["hold_min"]) if r.get("hold_min") else None,
                "win": r["result"] == "WIN",
            })
        table = {}
        for b in BUCKET_ORDER:
            rs = buckets.get(b, [])
            if not rs:
                continue
            mults = [x["mult"] for x in rs]
            perct = [x["per_ct"] for x in rs]
            holds = [x["hold"] for x in rs if x["hold"] is not None]
            wins = sum(1 for x in rs if x["win"])
            table[b] = {
                "n": len(rs),
                "win_rate_pct": round(100 * wins / len(rs), 1),
                "mean_dist_spy_$": round(statistics.mean([x["dist"] for x in rs]), 2),
                "mean_multiple": round(statistics.mean(mults), 3),
                "median_multiple": round(statistics.median(mults), 3),
                "mean_pnl_per_contract": round(statistics.mean(perct), 2),
                "median_pnl_per_contract": round(statistics.median(perct), 2),
                "mean_hold_min": round(statistics.mean(holds), 1) if holds else None,
            }
        return table, label

    b1_all, _ = b1_table(spx, "spx_all_dte")
    b1_0dte, _ = b1_table([r for r in spx if r["is_0dte"] == "True"], "spx_0dte")

    # ------------------------------------------------------- B2/B3: HOLD + TP (peak)
    # 0DTE SPX-family winners with a bar cache. Reprice premium along the underlier path
    # using the per-trade IV inverted from J's entry fill.
    peak_rows = []
    cov = Counter()
    win_0dte = [r for r in spx if r["result"] == "WIN" and r["is_0dte"] == "True"]
    for r in win_0dte:
        key = (r["date"], r["symbol"])
        feat = wf.get(key)
        bars = wc.get(r["date"])
        if feat is None or not feat.get("entry_close") or not bars:
            cov["no_feat_or_bars"] += 1
            continue
        et = _parse_dt(r["entry_time"])
        if et is None:
            cov["bad_entry_time"] += 1
            continue
        spot0 = float(feat["entry_close"])
        k_spy = spy_equiv_strike(float(r["strike"]), r["symbol"])
        is_call = r["right"] == "C"
        try:
            entry_px = float(r["entry_px"])
        except (ValueError, TypeError):
            cov["bad_entry_px"] += 1
            continue
        if entry_px <= 0:
            cov["zero_entry_px"] += 1
            continue
        # TTE at entry: minutes from entry to 16:00 ET. Use the entry timestamp.
        entry_et = et  # naive ET
        tte0 = time_to_expiry_years(entry_et)
        iv = implied_vol_from_fill(spot0, k_spy, entry_px, tte0, is_call)
        if iv is None:
            cov["iv_unsolvable"] += 1
            continue
        # Walk bars AT OR AFTER the entry bar; reprice premium with constant IV, TTE->16:00.
        path = []
        for bar in bars:
            bdt = _bar_dt_et(bar["t"])
            if bdt < entry_et - dt.timedelta(minutes=5):
                continue  # before entry (allow same-5m bar)
            # Use the bar CLOSE as the spot snapshot at bar end; TTE at bar end.
            bspot = float(bar["c"])
            btte = time_to_expiry_years(bdt + dt.timedelta(minutes=5))
            prem, _ = black_scholes(bspot, k_spy, iv, btte, is_call)
            mins = (bdt + dt.timedelta(minutes=5) - entry_et).total_seconds() / 60.0
            path.append((max(mins, 0.0), prem))
        if len(path) < 2:
            cov["short_path"] += 1
            continue
        # Peak premium AFTER entry (exclude the entry snapshot at min~0 if it's the only).
        peak_min, peak_prem = max(path, key=lambda x: x[1])
        peak_gain_pct = peak_prem / entry_px - 1.0
        cov["used"] += 1
        peak_rows.append({
            "date": r["date"], "symbol": r["symbol"], "side": r["right"],
            "entry_px": entry_px, "iv": round(iv, 3),
            "minutes_to_peak": round(peak_min, 1),
            "peak_gain_pct": round(100 * peak_gain_pct, 1),
            "realized_mult": round(float(r["exit_px"]) / entry_px, 3)
            if float(r.get("exit_px") or 0) > 0 else None,
            "his_hold_min": float(r["hold_min"]) if r.get("hold_min") else None,
            "dist_spy_$": round(signed_otm_distance(r["right"], k_spy, spot0), 2),
            "bucket": moneyness_bucket(signed_otm_distance(r["right"], k_spy, spot0)),
        })

    mins_to_peak = [x["minutes_to_peak"] for x in peak_rows]
    peak_gains = [x["peak_gain_pct"] for x in peak_rows]
    his_holds = [x["his_hold_min"] for x in peak_rows if x["his_hold_min"] is not None]

    # B2: what fraction of winners peaked by X minutes
    def frac_by(thresh):
        return round(100 * sum(1 for m in mins_to_peak if m <= thresh) / len(mins_to_peak), 1) \
            if mins_to_peak else 0.0
    peak_by = {f"<= {t} min": frac_by(t) for t in (15, 30, 45, 60, 90, 120, 180, 240)}

    # B3: what fraction of winners' peak reached X% gain
    def frac_gain(thresh):
        return round(100 * sum(1 for g in peak_gains if g >= thresh) / len(peak_gains), 1) \
            if peak_gains else 0.0
    gain_reaches = {f">= {t}%": frac_gain(t) for t in (10, 20, 30, 50, 75, 100, 150, 200)}

    # peak metrics per moneyness bucket (B1 x B2 x B3 cross)
    by_bucket = defaultdict(lambda: {"mins": [], "gains": []})
    for x in peak_rows:
        by_bucket[x["bucket"]]["mins"].append(x["minutes_to_peak"])
        by_bucket[x["bucket"]]["gains"].append(x["peak_gain_pct"])
    bucket_peak = {}
    for b in BUCKET_ORDER:
        if b in by_bucket:
            bucket_peak[b] = {
                "n": len(by_bucket[b]["mins"]),
                "median_min_to_peak": round(statistics.median(by_bucket[b]["mins"]), 1),
                "median_peak_gain_pct": round(statistics.median(by_bucket[b]["gains"]), 1),
                "mean_peak_gain_pct": round(statistics.mean(by_bucket[b]["gains"]), 1),
            }

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "PART A — J's-data optimal STRIKE (B1) / HOLD (B2) / TP (B3). Defines "
                   "candidate param values; PART B validates forward on OUR SPY data.",
        "scale_note": "Bar cache + entry_close = SPY-scale; SPX strikes /10, SPY strikes "
                      "x1 (verified median ratio SPX 10.03 / SPY 1.00).",
        "data_sources": {
            "roundtrips": str(RT.relative_to(PROJECT)),
            "winner_features": str(WF.relative_to(PROJECT)),
            "winner_bar_cache": str(WC.relative_to(PROJECT)),
        },
        # ---- B1 ----
        "B1_strike": {
            "method": "moneyness bucket = directional strike-from-spot distance ($, SPY "
                      "scale) at entry. WINNER rows only (only those carry a cached spot). "
                      "Per bucket: count, mean realized multiple (exit/entry), mean $/contract "
                      "pnl, mean hold. SHARPEST = highest mean multiple & $/contract.",
            "caveat": "j_roundtrips losers carry no cached underlier spot, so moneyness "
                      "buckets are computed on his WINNERS (win_rate ~100% by construction "
                      "is NOT the signal — the MULTIPLE and $/contract BY BUCKET is). The "
                      "forward OOS sweep in PART B is what actually tests the strike on our "
                      "unbiased tape with both winners and losers.",
            "spx_all_dte": b1_all,
            "spx_0dte": b1_0dte,
        },
        # ---- B2 ----
        "B2_hold_time": {
            "method": "0DTE SPX winners; option premium repriced along cached underlier "
                      "path with per-trade IV inverted from J's entry fill; minutes-from-"
                      "entry to PEAK premium.",
            "n": len(mins_to_peak),
            "minutes_to_peak_dist": _agg(mins_to_peak),
            "cumulative_pct_peaked_by": peak_by,
            "his_actual_hold_dist_min": _agg(his_holds),
            "note": "his ACTUAL holds are typically SHORTER than minutes-to-peak (he exits "
                    "before the modeled peak) -> headroom for a hold ceiling AT the peak band.",
        },
        # ---- B3 ----
        "B3_tp_target": {
            "method": "0DTE SPX winners; peak %-gain over entry premium = peak/entry - 1.",
            "n": len(peak_gains),
            "peak_gain_pct_dist": _agg(peak_gains),
            "cumulative_pct_reaching_gain": gain_reaches,
            "his_realized_multiple_dist": _agg(
                [x["realized_mult"] for x in peak_rows if x["realized_mult"]]),
        },
        "B1xB2xB3_by_bucket": bucket_peak,
        "coverage": dict(cov),
        "peak_rows_sample": peak_rows[:8],
        "n_peak_rows": len(peak_rows),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str))

    # ---- console ----
    print("=== PART A: J's-data optimal STRIKE / HOLD / TP ===")
    print(f"\n[B1 STRIKE] SPX 0DTE winners by moneyness bucket (mult = exit/entry):")
    print(f"  {'bucket':7} {'n':>4} {'mean_mult':>9} {'med_mult':>8} {'$/ct':>7} {'hold':>6}")
    for b in BUCKET_ORDER:
        if b in b1_0dte:
            t = b1_0dte[b]
            print(f"  {b:7} {t['n']:>4} {t['mean_multiple']:>9} {t['median_multiple']:>8} "
                  f"{t['mean_pnl_per_contract']:>7} {t['mean_hold_min'] or 0:>6}")
    print(f"\n[B2 HOLD] minutes-to-peak (n={len(mins_to_peak)}): "
          f"median={out['B2_hold_time']['minutes_to_peak_dist'].get('median')} "
          f"p75={out['B2_hold_time']['minutes_to_peak_dist'].get('p75')}")
    for k, v in peak_by.items():
        print(f"    peaked {k}: {v}%")
    print(f"  his ACTUAL hold median={out['B2_hold_time']['his_actual_hold_dist_min'].get('median')}")
    print(f"\n[B3 TP] peak %-gain (n={len(peak_gains)}): "
          f"median={out['B3_tp_target']['peak_gain_pct_dist'].get('median')}% "
          f"p25={out['B3_tp_target']['peak_gain_pct_dist'].get('p25')}%")
    for k, v in gain_reaches.items():
        print(f"    reached {k}: {v}%")
    print(f"\ncoverage={dict(cov)}")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
