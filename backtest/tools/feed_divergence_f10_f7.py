"""feed_divergence_f10_f7.py -- IEX-vs-SIP divergence meter for bull filters 10 and 7.

Born 2026-08-07 (Lane 5, close-package): the live engine scores volume filters on
feed=iex bars (heartbeat_core._fetch_spy_5m, one fetch -> bar AND baseline same-feed),
while the backtest population that RATIFIED those filters is SIP-scale. IEX prints a
small, UNSTABLE fraction of consolidated volume (measured 1.3%..8.2% bar-to-bar on
2026-08-07) -- so per-bar volume-ratio tests (filter 10: vol >= mult * 20-bar SMA) and
bar-vs-bar volume comparisons (filter 7: recovery vol >= breakout vol) can diverge from
what the SAME rule would say on SIP volume. This tool MEASURES that divergence per bar
for a given date; it changes nothing.

Exhibit (2026-08-07, partial day to 12:00 ET): 3/28 bars f10-divergent (SIP pass, IEX
block) incl. the 11:05 bar where SIP printed 987,522 (a ~2x-baseline surge) and IEX
printed 12,799 (1.3%) -- the surge read as a dead bar; 5/28 bars f7-divergent.

Filter mirrors are LOCAL, verbatim-shaped copies of backtest/lib/filters.py
buyer_pressure_bar_v11 / _bullish_volume_divergence_failed (kept local so this tool
never imports the trading path; drift-checked by
backtest/tests/test_feed_divergence_tool_2026_08_07.py).

Usage:
    python backtest/tools/feed_divergence_f10_f7.py --date 2026-08-07
    # writes analysis/deep-research/FEED-DIVERGENCE-F10-F7-<date>.json

$0 -- two REST bar fetches, read-only, no OPRA, no trading-path imports.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[2]
ET = ZoneInfo("America/New_York")
F10_VOL_MULT = 0.7          # live default (params filter_9_vol_multiplier tie)
BASELINE_BARS = 20          # filters.VOL_BASELINE_BARS
SIP_SAFETY_LAG_MIN = 20     # free plan 403s when the query touches the last ~15 min


def _creds() -> dict[str, str]:
    env = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))[
        "mcpServers"]["alpaca"]["env"]
    return {"APCA-API-KEY-ID": env["ALPACA_API_KEY"],
            "APCA-API-SECRET-KEY": env["ALPACA_SECRET_KEY"]}


def fetch_5m(feed: str, date: dt.date, headers: dict) -> list[dict]:
    """RTH 5m bars for `date` plus the 2 prior calendar days (baseline warmup)."""
    start = (dt.datetime.combine(date, dt.time(8, 0), ET)
             - dt.timedelta(days=3)).isoformat(timespec="seconds")
    end_dt = dt.datetime.combine(date, dt.time(16, 30), ET)
    now = dt.datetime.now(ET)
    cap = now - dt.timedelta(minutes=SIP_SAFETY_LAG_MIN)
    if end_dt > cap:
        end_dt = cap
    end = end_dt.isoformat(timespec="seconds")
    url = ("https://data.alpaca.markets/v2/stocks/SPY/bars"
           f"?timeframe=5Min&start={start}&end={end}"
           f"&limit=2000&feed={feed}&adjustment=raw&sort=asc")
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    bars = r.json().get("bars", []) or []
    out = []
    for b in bars:
        ts = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET)
        if dt.time(9, 30) <= ts.time() < dt.time(16, 0):
            out.append({"et": ts, "o": b["o"], "h": b["h"], "l": b["l"],
                        "c": b["c"], "v": b["v"]})
    return out


def f10_pass(bars: list[dict], i: int, vol_mult: float = F10_VOL_MULT):
    """Mirror of filters.buyer_pressure_bar_v11 + vol_baseline_20bar (prior 20 bars,
    excluding bar i, RTH continuum incl. prior-day tail -- the live construction)."""
    b = bars[i]
    lo = max(0, i - BASELINE_BARS)
    base = sum(x["v"] for x in bars[lo:i]) / max(1, i - lo)
    return (b["c"] > b["o"] and b["v"] >= vol_mult * base), b["v"], base


def f7_fail(bars: list[dict], i: int) -> bool:
    """Mirror of filters._bullish_volume_divergence_failed."""
    if i < 2:
        return False
    for bo_i, rec_i in ((i - 1, i), (i - 2, i - 1), (i - 2, i)):
        bo, rec = bars[bo_i], bars[rec_i]
        if bo["c"] <= bo["o"]:
            continue
        if rec["c"] < rec["o"] and rec["v"] >= bo["v"]:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", required=True, help="YYYY-MM-DD (ET trading date)")
    ap.add_argument("--out", default=None,
                    help="output JSON (default analysis/deep-research/"
                         "FEED-DIVERGENCE-F10-F7-<date>.json)")
    args = ap.parse_args()
    date = dt.date.fromisoformat(args.date)
    headers = _creds()

    try:
        iex = fetch_5m("iex", date, headers)
        sip = fetch_5m("sip", date, headers)
    except requests.HTTPError as e:
        print(f"FATAL: bar fetch failed: {e}", file=sys.stderr)
        return 2
    if not iex or not sip:
        print(f"FATAL: empty bars (iex={len(iex)} sip={len(sip)}) -- "
              "feed entitlement or date problem, not silently 'no divergence'",
              file=sys.stderr)
        return 2

    iex_by_t = {b["et"]: b for b in iex}
    sip_by_t = {b["et"]: b for b in sip}
    common = sorted(set(iex_by_t) & set(sip_by_t))
    iex_a = [iex_by_t[t] for t in common]
    sip_a = [sip_by_t[t] for t in common]

    rows, n_f10_div, n_f7_div, n_bars = [], 0, 0, 0
    frac_sum = 0.0
    for i, t in enumerate(common):
        if t.date() != date or t.time() < dt.time(9, 35):
            continue
        p_i, v_i, b_i = f10_pass(iex_a, i)
        p_s, v_s, b_s = f10_pass(sip_a, i)
        s7_i, s7_s = f7_fail(iex_a, i), f7_fail(sip_a, i)
        n_bars += 1
        frac = v_i / v_s if v_s else 0.0
        frac_sum += frac
        d10, d7 = p_i != p_s, s7_i != s7_s
        n_f10_div += d10
        n_f7_div += d7
        rows.append({
            "bar_et": t.strftime("%H:%M"), "iex_vol": v_i, "sip_vol": v_s,
            "iex_frac_pct": round(100 * frac, 2),
            "f10_iex": p_i, "f10_sip": p_s, "f10_divergent": d10,
            "f7_blocks_iex": s7_i, "f7_blocks_sip": s7_s, "f7_divergent": d7,
        })

    out = {
        "_doc": ("IEX-vs-SIP divergence for bull filters 10/7, same rule + same "
                 "window construction both feeds. f10_divergent=True means the "
                 "engine's IEX verdict differs from the SIP verdict for that bar. "
                 "This is a MEASUREMENT, not a counterfactual P&L claim -- joint "
                 "blocker state per tick lives in core-decisions.jsonl."),
        "date": args.date,
        "generated_at_et": dt.datetime.now(ET).isoformat(timespec="seconds"),
        "partial_day": dt.datetime.now(ET).date() == date
                       and dt.datetime.now(ET).time() < dt.time(16, 30),
        "f10_vol_mult": F10_VOL_MULT,
        "bars_checked": n_bars,
        "f10_divergent_bars": n_f10_div,
        "f7_divergent_bars": n_f7_div,
        "mean_iex_fraction_pct": round(100 * frac_sum / n_bars, 2) if n_bars else None,
        "rows": rows,
    }
    out_path = Path(args.out) if args.out else (
        ROOT / "analysis" / "deep-research" / f"FEED-DIVERGENCE-F10-F7-{args.date}.json")
    out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    tag = " (PARTIAL DAY)" if out["partial_day"] else ""
    print(f"[feed-divergence] {args.date}{tag}: bars={n_bars} "
          f"f10_divergent={n_f10_div} f7_divergent={n_f7_div} "
          f"mean_iex_frac={out['mean_iex_fraction_pct']}% -> {out_path}")
    for r in rows:
        if r["f10_divergent"] or r["f7_divergent"]:
            print(f"  {r['bar_et']} iex={r['iex_vol']:.0f} sip={r['sip_vol']:.0f} "
                  f"({r['iex_frac_pct']}%) "
                  f"f10 iex/sip={r['f10_iex']}/{r['f10_sip']} "
                  f"f7 iex/sip={r['f7_blocks_iex']}/{r['f7_blocks_sip']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
