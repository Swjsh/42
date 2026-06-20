"""J-data REGIME SPLIT (C1 VIX / C2 trend-vs-range day / C3 year-transfer).

PART 1 of the C-angle campaign: his Webull data DEFINES the regime hypotheses.
(PART 2 — forward-validation on OUR 2025-26 OPRA fills — lives in
 j_regime_forward_validate.py, reusing the VWAP-pullback detector + real-fill sim.)

What this does (his data only, no fills rebuilt):
  C1  VIX regime: split his SPX-family round-trips by VIX LEVEL (day open, the
      causal 09:30 proxy) into low/mid/high doctrine bands (regime_book
      VIX_LOW_CEIL=16, VIX_HIGH_VOL_FLOOR=19) AND by VIX CHARACTER (change_1d =
      open - prior_close, rising/flat/falling). Per-setup (trigger x side).
  C2  Day-type: classify each trade DAY trend vs range from the cached intraday
      SPY bars (range_ratio = total_path / net_move, ADX-like; plus open->close
      vs intraday-range). Same classifier for winners AND losers (no winners-only
      bias). Which of his setups worked on which day-type.
  C3  Year/regime transfer: his edge by calendar year (2021 bull / 2022 bear /
      2023 chop) AND by VIX-band-within-year, to expose transfer risk.

CAUSALITY: VIX level uses the DAY OPEN (known at 09:30, before any entry). VIX
character uses open-minus-prior-close (overnight, causal). Day-type uses full-day
intraday bars — this is a POST-HOC day label on HIS trades (descriptive), so it is
fine for "which day-type did his edge appear on"; the FORWARD gate (part 2) only
uses look-ahead-safe features. Thin-cache days (<60 RTH bars) are flagged.

Outputs: analysis/webull-j-trades/_j_regime_split.json (intermediate; consumed by
the deliverable writer). Pure python, $0.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WJ = REPO / "analysis" / "webull-j-trades"

# Doctrine VIX bands (backtest/lib/engine/regime_book.py) — NOT freshly fit.
VIX_LOW_CEIL = 16.0          # VIX < 16 => low-vol
VIX_HIGH_VOL_FLOOR = 19.0    # VIX >= 19 => high-vol  (16..19 = mid)
VIX_CHAR_DEADBAND = 0.05     # matches regime_book / filters character deadband (on VIX points use 0.3)
VIX_CHAR_DEADBAND_PTS = 0.30  # |change_1d| < 0.30 VIX pts => "flat" overnight

MIN_RTH_BARS_FULL = 60       # >=60 5m bars (~5h) => treat day-type as reliable


def _safe_div(a, b):
    return a / b if b else float("nan")


def wilson_lcb(wins, n, z=1.96):
    """Wilson lower confidence bound on a win-rate proportion (small-N honesty)."""
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def summarize(trades):
    """Standard P&L block for a list of round-trips."""
    n = len(trades)
    if n == 0:
        return {"n": 0, "wins": 0, "wr": None, "total_pnl": 0.0,
                "exp_per_trade": None, "avg_win": None, "avg_loss": None,
                "profit_factor": None, "wr_wilson_lcb": None}
    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] != "WIN"]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    tot = sum(t["pnl"] for t in trades)
    return {
        "n": n,
        "wins": len(wins),
        "wr": round(len(wins) / n, 4),
        "wr_wilson_lcb": round(wilson_lcb(len(wins), n), 4),
        "total_pnl": round(tot, 1),
        "exp_per_trade": round(tot / n, 2),
        "avg_win": round(gross_win / len(wins), 2) if wins else None,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else None,
        "profit_factor": round(_safe_div(gross_win, gross_loss), 3) if gross_loss else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Day-type classifier (trend vs range) — same logic for winners & losers
# ─────────────────────────────────────────────────────────────────────────────
def day_type_metrics(bars):
    """Return raw (range_ratio, oc_over_range, meta) for a day's intraday SPY 5m bars.

    range_ratio = sum(|close_i - close_{i-1}|) / |close_last - close_first|
                  (path / net) — LOW ratio => trend (price moved efficiently);
                  HIGH ratio => range/chop (lots of back-and-forth, little net move).
    oc_over_range = |close_last - close_first| / (high_day - low_day)
                  — HIGH => closed near an extreme (trend); LOW => closed mid-range.

    NOTE: range_ratio scale is granularity-dependent. On these 5m sessions the
    median is ~8 (NOT ~2.5). So the trend/range split is made DATA-DRIVEN by the
    sample's own range_ratio terciles in main() — never a hard-coded magic number.
    """
    closes = [b["c"] for b in bars]
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]
    if len(closes) < 6:
        return None, None, {"reason": "too_few_bars", "n_bars": len(closes)}
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    net = abs(closes[-1] - closes[0])
    day_range = max(highs) - min(lows)
    rr = _safe_div(path, net) if net > 1e-9 else float("inf")
    oc = _safe_div(abs(closes[-1] - closes[0]), day_range) if day_range > 1e-9 else 0.0
    meta = {
        "range_ratio": round(rr, 2) if math.isfinite(rr) else None,
        "oc_over_range": round(oc, 3),
        "net_move_pts": round(closes[-1] - closes[0], 2),
        "day_range_pts": round(day_range, 2),
        "n_bars": len(closes),
    }
    return rr, oc, meta


def vix_band(vix_level):
    if vix_level is None:
        return "unknown"
    if vix_level < VIX_LOW_CEIL:
        return "low"
    if vix_level >= VIX_HIGH_VOL_FLOOR:
        return "high"
    return "mid"


def vix_character(change_1d):
    if change_1d is None:
        return "unknown"
    if change_1d > VIX_CHAR_DEADBAND_PTS:
        return "rising"
    if change_1d < -VIX_CHAR_DEADBAND_PTS:
        return "falling"
    return "flat"


def main():
    rt = json.load(open(WJ / "j_roundtrips.json"))["round_trips"]
    vix = json.load(open(WJ / "vix_daily_2021_2023.json"))
    wbc = json.load(open(WJ / "winner_bar_cache.json"))
    lbc = json.load(open(WJ / "loser_bar_cache.json"))
    bar_cache = dict(lbc)
    bar_cache.update(wbc)  # winner cache wins on overlap (both are SPY same-day bars)

    spx = [r for r in rt if r.get("is_spx_family")]

    # ---- precompute day-type metrics per day; derive DATA-DRIVEN terciles ----
    day_rr = {}      # date -> range_ratio
    day_oc = {}      # date -> oc_over_range
    day_type_meta = {}
    for d in set(r["date"] for r in spx):
        bars = bar_cache.get(d)
        if bars:
            rr, oc, meta = day_type_metrics(bars)
            day_type_meta[d] = meta
            if rr is not None and meta.get("n_bars", 0) >= MIN_RTH_BARS_FULL and math.isfinite(rr):
                day_rr[d] = rr
                day_oc[d] = oc
        else:
            day_type_meta[d] = {"reason": "no_bar_cache"}
    # terciles of range_ratio over RELIABLE days: low tercile=trend, high=range/chop
    rr_vals = sorted(day_rr.values())
    if rr_vals:
        t_lo = rr_vals[len(rr_vals) // 3]            # 33rd pct
        t_hi = rr_vals[2 * len(rr_vals) // 3]        # 67th pct
    else:
        t_lo = t_hi = float("nan")

    def label_day(d):
        if d not in day_rr:
            return None
        rr = day_rr[d]
        if rr <= t_lo:
            return "trend"          # efficient move, low path/net
        if rr >= t_hi:
            return "range"          # choppy, high path/net
        return "mixed"

    # ---- enrich each trade with regime tags (causal where it matters) ----
    for r in spx:
        d = r["date"]
        vd = vix.get(d, {})
        r["_vix_open"] = vd.get("open")
        r["_vix_close"] = vd.get("close")
        r["_vix_change_1d"] = vd.get("change_1d")
        r["_vix_band"] = vix_band(vd.get("open"))          # day-open level => causal 09:30 proxy
        r["_vix_band_close"] = vix_band(vd.get("close"))    # robustness cross-check
        r["_vix_char"] = vix_character(vd.get("change_1d"))
        r["_year"] = d[:4]
        r["_day_type"] = label_day(d)
        r["_day_type_reliable"] = d in day_rr

    # ============================ C1: VIX ============================
    c1 = {}
    c1["overall"] = summarize(spx)
    c1["by_vix_band"] = {b: summarize([r for r in spx if r["_vix_band"] == b])
                         for b in ("low", "mid", "high")}
    c1["by_vix_band_close_robustness"] = {
        b: summarize([r for r in spx if r["_vix_band_close"] == b])
        for b in ("low", "mid", "high")}
    c1["by_vix_character"] = {c: summarize([r for r in spx if r["_vix_char"] == c])
                              for c in ("rising", "flat", "falling")}
    # band x character grid
    c1["band_x_character"] = {}
    for b in ("low", "mid", "high"):
        for c in ("rising", "flat", "falling"):
            cell = [r for r in spx if r["_vix_band"] == b and r["_vix_char"] == c]
            if cell:
                c1["band_x_character"][f"{b}/{c}"] = summarize(cell)
    # per-setup (trigger x side) — but trigger not on every roundtrip; use winner_features
    #   we instead split by side (bias) which IS on every roundtrip
    c1["by_side_x_band"] = {}
    for side in ("bull", "bear"):
        for b in ("low", "mid", "high"):
            cell = [r for r in spx if r["bias"] == side and r["_vix_band"] == b]
            if cell:
                c1["by_side_x_band"][f"{side}/{b}"] = summarize(cell)
    # continuous: VIX-open histogram of winners vs losers (mean/median)
    wv = [r["_vix_open"] for r in spx if r["result"] == "WIN" and r["_vix_open"]]
    lv = [r["_vix_open"] for r in spx if r["result"] != "WIN" and r["_vix_open"]]
    cv = [r["_vix_change_1d"] for r in spx if r["result"] == "WIN" and r["_vix_change_1d"] is not None]
    cl = [r["_vix_change_1d"] for r in spx if r["result"] != "WIN" and r["_vix_change_1d"] is not None]
    c1["vix_level_winners_vs_losers"] = {
        "winner_mean_vix": round(sum(wv) / len(wv), 2) if wv else None,
        "loser_mean_vix": round(sum(lv) / len(lv), 2) if lv else None,
        "winner_median_vix": round(sorted(wv)[len(wv) // 2], 2) if wv else None,
        "loser_median_vix": round(sorted(lv)[len(lv) // 2], 2) if lv else None,
        "winner_mean_change1d": round(sum(cv) / len(cv), 3) if cv else None,
        "loser_mean_change1d": round(sum(cl) / len(cl), 3) if cl else None,
    }

    # ============================ C2: DAY TYPE ============================
    c2 = {}
    reliable = [r for r in spx if r["_day_type"] is not None and r["_day_type_reliable"]]
    c2["classifier"] = {
        "method": "data-driven range_ratio terciles over reliable days (>=60 RTH 5m bars)",
        "range_ratio_tercile_low_trend_lt": round(t_lo, 2) if math.isfinite(t_lo) else None,
        "range_ratio_tercile_high_range_gt": round(t_hi, 2) if math.isfinite(t_hi) else None,
        "n_reliable_days": len(rr_vals),
    }
    c2["coverage"] = {
        "n_spx": len(spx),
        "n_with_day_type": len([r for r in spx if r["_day_type"] is not None]),
        "n_reliable_day_type": len(reliable),
        "note": "reliable = >=60 cached RTH bars; thin days excluded from headline. "
                "trend=low range_ratio tercile (efficient move); range=high tercile (chop); "
                "mixed=middle tercile.",
    }
    c2["by_day_type"] = {dt: summarize([r for r in reliable if r["_day_type"] == dt])
                         for dt in ("trend", "mixed", "range")}
    # side x day_type
    c2["side_x_day_type"] = {}
    for side in ("bull", "bear"):
        for dt in ("trend", "mixed", "range"):
            cell = [r for r in reliable if r["bias"] == side and r["_day_type"] == dt]
            if cell:
                c2["side_x_day_type"][f"{side}/{dt}"] = summarize(cell)
    # day_type x vix_band (the router cross-product)
    c2["day_type_x_vix_band"] = {}
    for dt in ("trend", "mixed", "range"):
        for b in ("low", "mid", "high"):
            cell = [r for r in reliable if r["_day_type"] == dt and r["_vix_band"] == b]
            if cell:
                c2["day_type_x_vix_band"][f"{dt}/{b}"] = summarize(cell)

    # ============================ C3: YEAR / TRANSFER ============================
    c3 = {}
    c3["by_year"] = {y: summarize([r for r in spx if r["_year"] == y])
                     for y in ("2021", "2022", "2023")}
    c3["by_year_x_side"] = {}
    for y in ("2021", "2022", "2023"):
        for side in ("bull", "bear"):
            cell = [r for r in spx if r["_year"] == y and r["bias"] == side]
            if cell:
                c3["by_year_x_side"][f"{y}/{side}"] = summarize(cell)
    c3["by_year_x_vix_band"] = {}
    for y in ("2021", "2022", "2023"):
        for b in ("low", "mid", "high"):
            cell = [r for r in spx if r["_year"] == y and r["_vix_band"] == b]
            if cell:
                c3["by_year_x_vix_band"][f"{y}/{b}"] = summarize(cell)
    # VIX-band edge sign STABILITY across years = the transfer test
    c3["vix_band_edge_sign_across_years"] = {}
    for b in ("low", "mid", "high"):
        signs = {}
        for y in ("2021", "2022", "2023"):
            cell = [r for r in spx if r["_year"] == y and r["_vix_band"] == b]
            s = summarize(cell)
            signs[y] = {"n": s["n"], "exp": s["exp_per_trade"]}
        exps = [v["exp"] for v in signs.values() if v["n"] >= 10 and v["exp"] is not None]
        c3["vix_band_edge_sign_across_years"][b] = {
            "per_year": signs,
            "n_years_ge10": len(exps),
            "all_same_sign": (all(e > 0 for e in exps) or all(e < 0 for e in exps)) if exps else None,
        }

    out = {
        "_generated": datetime.utcnow().isoformat() + "Z",
        "_what": "C1/C2/C3 regime split on J's 668 SPX-family Webull round-trips (2021-23). "
                 "His data DEFINES the hypotheses; forward-validation is separate.",
        "_causality": "VIX band from DAY OPEN (causal 09:30 proxy); VIX character from "
                      "open-minus-prior-close (overnight, causal). Day-type is a post-hoc "
                      "full-day label (descriptive of WHERE his edge appeared, not a live gate).",
        "_doctrine_bands": {"VIX_LOW_CEIL": VIX_LOW_CEIL,
                            "VIX_HIGH_VOL_FLOOR": VIX_HIGH_VOL_FLOOR,
                            "vix_char_deadband_pts": VIX_CHAR_DEADBAND_PTS},
        "_honesty": "J's SPX-family book is net NEGATIVE (-$12,885, WR 46.9%, PF 0.75). "
                    "We are locating WHERE within it the edge is least-bad / positive, NOT "
                    "claiming his raw book is profitable. Small-N cells carry Wilson LCB.",
        "C1_vix": c1,
        "C2_day_type": c2,
        "C3_year_transfer": c3,
        "_day_type_meta_sample": {k: day_type_meta[k] for k in list(day_type_meta)[:5]},
    }
    outpath = WJ / "_j_regime_split.json"
    json.dump(out, open(outpath, "w"), indent=2)
    print("WROTE", outpath)

    # ---- console digest ----
    print("\n=== C1 VIX BAND (day-open level) ===")
    for b in ("low", "mid", "high"):
        s = c1["by_vix_band"][b]
        print(f"  {b:5s} n={s['n']:3d} WR={s['wr']} exp=${s['exp_per_trade']} "
              f"tot=${s['total_pnl']} PF={s['profit_factor']}")
    print("=== C1 VIX CHARACTER ===")
    for c in ("rising", "flat", "falling"):
        s = c1["by_vix_character"][c]
        print(f"  {c:8s} n={s['n']:3d} WR={s['wr']} exp=${s['exp_per_trade']} tot=${s['total_pnl']}")
    print(f"=== C2 DAY TYPE (terciles rr<={c2['classifier']['range_ratio_tercile_low_trend_lt']} trend / "
          f">={c2['classifier']['range_ratio_tercile_high_range_gt']} range) ===")
    for dt in ("trend", "mixed", "range"):
        s = c2["by_day_type"][dt]
        print(f"  {dt:5s} n={s['n']:3d} WR={s['wr']} exp=${s['exp_per_trade']} tot=${s['total_pnl']}")
    print("=== C3 YEAR ===")
    for y in ("2021", "2022", "2023"):
        s = c3["by_year"][y]
        print(f"  {y} n={s['n']:3d} WR={s['wr']} exp=${s['exp_per_trade']} tot=${s['total_pnl']}")
    print("=== C3 VIX-band sign stability across years ===")
    for b, v in c3["vix_band_edge_sign_across_years"].items():
        print(f"  {b:5s} same_sign={v['all_same_sign']} years_ge10={v['n_years_ge10']} "
              f"per_year={ {y: d['exp'] for y, d in v['per_year'].items()} }")


if __name__ == "__main__":
    main()
