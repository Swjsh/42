"""V14E Bear Chart-Stop Research — L51 Analog.

Question: for the 5 stopped BEAR_HIGH_CONF observations, does the -8% premium
stop fire during initial noise BEFORE the directional bearish move develops?

L51 lesson (LBFS): on high-vol level-break entries, SPY can retest the broken
level from below, driving ATM put premium DOWN >8% in bar 1, firing the stop
before the bear move develops. Only chart-stop (-0.99) discriminates genuine
breaks from false ones.

For v14e bear entries (level REJECTION at key level), the analog is:
  - Entry bar: bearish rejection closes at C
  - Bar 1 (entry fill bar): SPY may spike up slightly before rolling
  - If SPY goes up enough, the ATM put premium drops >8%
  - Stop fires at -8% BEFORE the actual bearish continuation

This script:
  1. Loads the 5 stopped high-conf bear observations
  2. For each, traces SPY 5m bars and OTM-2 put bars for bars 0-10 after entry
  3. Computes: earliest bar where put premium drops to <= entry_premium * 0.92
  4. Computes: earliest bar where SPY close drops below entry (confirming bear move)
  5. Conclusion: if stop_bar <= bear_confirmation_bar, the -8% stop is interfering

Output: analysis/backtests/v14e-bear-gate/chartstop_research.json + .md
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from lib.option_pricing_real import bar_at_or_after, load_contract_bars, option_symbol  # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────────
SPY_CSV = REPO / "data" / "spy_5m_2025-01-01_2026-05-19_merged.csv"
OUT_DIR = ROOT / "analysis" / "backtests" / "v14e-bear-gate"
OUT_JSON = OUT_DIR / "chartstop_research.json"
OUT_MD = OUT_DIR / "chartstop_research.md"

PREMIUM_STOP_PCT = -0.08   # production stop
CHART_STOP_STOP_PCT = -0.99  # "disabled" = chart-stop only
STRIKE_OFFSET = 2           # v14e default: OTM-2 puts
LOOKFORWARD_BARS = 12       # bars to trace after entry fill
ET = "America/New_York"

# ── The 5 stopped high-conf bear observations ─────────────────────────────────
# Sourced from watcher-observations.jsonl (score != None, would_be_outcome=stopped)
STOPPED_OBS = [
    {
        "date": "2025-01-07",
        "time": "10:35",   # bar timestamp (5m bar closes at this time)
        "entry_price": 596.25,
        "stop_price_spy": 597.20,   # chart stop level
        "pnl": -95.0,
        "score": 9,
        "vix": 17.82,      # from fingerprint analysis
        "regime": "VIX_MODERATE",
        "triggers": ["trendline_rejection", "level_rejection", "confluence"],
        "notes": "Jan 7 2025 — the sole VIX_MODERATE loss"
    },
    {
        "date": "2025-02-27",
        "time": "11:00",
        "entry_price": 591.85,
        "stop_price_spy": 592.20,
        "pnl": -35.0,
        "score": 10,
        "vix": 21.16,
        "regime": "VIX_ELEVATED",
        "triggers": ["ribbon_flip", "level_rejection", "confluence"],
        "notes": "Feb 27 2025 — VIX_ELEVATED"
    },
    {
        "date": "2025-05-05",
        "time": "11:05",
        "entry_price": 564.69,
        "stop_price_spy": 565.20,
        "pnl": -51.0,
        "score": 10,
        "vix": 23.64,
        "regime": "VIX_ELEVATED",
        "triggers": ["seq_rejection", "trendline_rejection", "level_rejection", "confluence"],
        "notes": "May 5 2025 — VIX_ELEVATED"
    },
    {
        "date": "2025-10-10",
        "time": "11:05",
        "entry_price": 665.71,
        "stop_price_spy": 666.26,
        "pnl": -55.0,
        "score": 10,
        "vix": 21.63,
        "regime": "VIX_ELEVATED",
        "triggers": ["ribbon_flip", "level_rejection", "confluence"],
        "notes": "Oct 10 2025 — VIX_ELEVATED"
    },
    {
        "date": "2026-03-06",
        "time": "11:05",
        "entry_price": 671.02,
        "stop_price_spy": 673.04,   # wide stop from observation (score=10 version)
        "pnl": -137.2,
        "score": 10,
        "vix": 29.51,
        "regime": "VIX_HIGH",
        "triggers": ["trendline_rejection", "level_rejection", "confluence"],
        "notes": "Mar 6 2026 — VIX_HIGH, worst loss -$137"
    },
]


def _load_spy() -> pd.DataFrame:
    df = pd.read_csv(SPY_CSV)
    df["timestamp_et"] = (
        pd.to_datetime(df["timestamp_et"], utc=True)
        .dt.tz_convert(ET)
        .dt.tz_localize(None)
    )
    df = df.sort_values("timestamp_et").reset_index(drop=True)
    df["date"] = df["timestamp_et"].dt.date
    df["time"] = df["timestamp_et"].dt.time
    return df


def _bar_idx(spy: pd.DataFrame, date_str: str, time_str: str) -> int:
    d = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    t = dt.datetime.strptime(time_str, "%H:%M").time()
    mask = (spy["date"] == d) & (spy["time"] == t)
    matches = spy[mask]
    if matches.empty:
        return -1
    return int(matches.index[0])


def _occ_strike(spot: float, offset: int) -> int:
    """OTM put strike = round(spot) - offset."""
    return int(round(spot)) - offset


def _analyze_obs(obs: dict, spy: pd.DataFrame) -> dict:
    result = obs.copy()

    # ── Locate trigger bar (closes at the stated time) ────────────────────────
    trigger_idx = _bar_idx(spy, obs["date"], obs["time"])
    if trigger_idx < 0:
        result["error"] = f"trigger bar not found: {obs['date']} {obs['time']}"
        return result

    trigger_bar = spy.iloc[trigger_idx]
    entry_bar_idx = trigger_idx + 1  # entry fills at NEXT bar open
    if entry_bar_idx >= len(spy):
        result["error"] = "entry bar out of range"
        return result

    # ── Load OTM-2 put bars ────────────────────────────────────────────────────
    trade_date = dt.datetime.strptime(obs["date"], "%Y-%m-%d").date()
    strike = _occ_strike(obs["entry_price"], STRIKE_OFFSET)
    sym = option_symbol(trade_date, strike, "P")
    opt_df = load_contract_bars(sym)

    # Fallback: try ATM put (offset=0) if OTM-2 not available
    atm_sym = None
    if opt_df is None:
        strike_atm = int(round(obs["entry_price"]))
        atm_sym = option_symbol(trade_date, strike_atm, "P")
        opt_df = load_contract_bars(atm_sym)

    # Normalize option timestamp to tz-naive (SPY timestamps are already tz-naive).
    # option_pricing_real.load_contract_bars does pd.to_datetime() which preserves
    # the stored tz offset string — resulting in tz-aware Series. Strip it.
    if opt_df is not None and hasattr(opt_df["timestamp_et"].dtype, "tz") and \
            opt_df["timestamp_et"].dtype.tz is not None:
        opt_df = opt_df.copy()
        opt_df["timestamp_et"] = opt_df["timestamp_et"].dt.tz_localize(None)

    result["option_symbol_used"] = sym if atm_sym is None else atm_sym
    result["strike_used"] = strike if atm_sym is None else int(round(obs["entry_price"]))
    result["option_loaded"] = opt_df is not None

    # ── Entry fill: open of the first bar AFTER trigger bar ───────────────────
    entry_bar = spy.iloc[entry_bar_idx]
    entry_bar_ts = entry_bar["timestamp_et"]
    result["entry_bar_time"] = str(entry_bar_ts.time())
    result["spy_entry_bar_open"] = round(float(entry_bar["open"]), 2)
    result["spy_entry_bar_high"] = round(float(entry_bar["high"]), 2)

    # ── Per-bar trace (bars 0 = entry bar, 1-11 = subsequent bars) ────────────
    spy_path = []   # per-bar SPY data
    opt_path = []   # per-bar option premium data

    for i in range(LOOKFORWARD_BARS + 1):
        bar_idx = entry_bar_idx + i
        if bar_idx >= len(spy):
            break
        spy_bar = spy.iloc[bar_idx]
        spy_path.append({
            "bar": i,
            "time": str(spy_bar["timestamp_et"].time()),
            "open": round(float(spy_bar["open"]), 2),
            "high": round(float(spy_bar["high"]), 2),
            "low": round(float(spy_bar["low"]), 2),
            "close": round(float(spy_bar["close"]), 2),
        })

        if opt_df is not None:
            # Option bar covers the same 5-minute window
            spy_ts = spy_bar["timestamp_et"]
            # Ensure tz-naive for comparison (option df was already normalized above)
            if hasattr(spy_ts, "tzinfo") and spy_ts.tzinfo is not None:
                spy_ts = spy_ts.replace(tzinfo=None)
            opt_bar = bar_at_or_after(opt_df, spy_ts)
            if opt_bar is not None:
                opt_path.append({
                    "bar": i,
                    "time": str(opt_bar.timestamp_et.time()),
                    "open": round(opt_bar.open, 4),
                    "high": round(opt_bar.high, 4),
                    "low": round(opt_bar.low, 4),
                    "close": round(opt_bar.close, 4),
                    "vwap": round(opt_bar.vwap, 4),
                })

    result["spy_path"] = spy_path
    result["opt_path"] = opt_path

    if not opt_path:
        result["conclusion"] = "NO_OPTION_DATA"
        result["spy_adverse_move_first"] = _spy_adverse_first(obs, spy_path)
        return result

    # ── Entry premium: first option bar VWAP ─────────────────────────────────
    entry_prem = opt_path[0]["vwap"] if opt_path else None
    if not entry_prem or entry_prem <= 0:
        entry_prem = opt_path[0]["open"] if opt_path else None
    result["entry_premium"] = entry_prem

    if not entry_prem:
        result["conclusion"] = "NO_ENTRY_PREMIUM"
        return result

    stop_threshold = round(entry_prem * (1 + PREMIUM_STOP_PCT), 4)  # entry * 0.92
    result["premium_stop_threshold"] = stop_threshold
    result["premium_stop_pct"] = PREMIUM_STOP_PCT

    # ── Find first bar where premium stop fires (<= threshold) ──────────────
    prem_stop_bar = None
    for ob in opt_path[1:]:  # skip entry bar (bar 0), start from bar 1
        if ob["low"] <= stop_threshold:
            prem_stop_bar = ob["bar"]
            result["premium_stop_fires_bar"] = prem_stop_bar
            result["premium_stop_fires_time"] = ob["time"]
            result["premium_stop_bar_low"] = ob["low"]
            result["premium_drop_at_stop"] = round(
                (ob["low"] - entry_prem) / entry_prem * 100, 1
            )
            break

    if prem_stop_bar is None:
        result["premium_stop_fires_bar"] = None
        result["note_premium"] = "premium never crossed -8% threshold (odd for a stopped obs)"

    # ── Find first bar where SPY closes BELOW entry (bearish confirmation) ───
    bear_conf_bar = _spy_bear_conf_bar(obs, spy_path)
    result["bear_confirmation_bar"] = bear_conf_bar

    # ── Find first bar where SPY hits chart stop level ────────────────────────
    chart_stop_spy = obs["stop_price_spy"]
    chart_stop_bar = None
    for sb in spy_path[1:]:
        if sb["high"] >= chart_stop_spy:
            chart_stop_bar = sb["bar"]
            result["chart_stop_fires_bar"] = chart_stop_bar
            result["chart_stop_fires_time"] = sb["time"]
            break
    if chart_stop_bar is None:
        result["chart_stop_fires_bar"] = None

    # ── Conclusion ─────────────────────────────────────────────────────────────
    if prem_stop_bar is not None and (
        bear_conf_bar is None or prem_stop_bar <= bear_conf_bar
    ):
        result["conclusion"] = "PREMIUM_STOP_FIRES_BEFORE_BEAR_MOVE"
        result["l51_analog"] = True
    elif prem_stop_bar is None and chart_stop_bar is not None:
        result["conclusion"] = "CHART_STOP_FIRES_NO_PREMIUM_STOP"
        result["l51_analog"] = False
    elif prem_stop_bar is not None and bear_conf_bar is not None and prem_stop_bar > bear_conf_bar:
        result["conclusion"] = "BEAR_MOVE_BEFORE_PREMIUM_STOP"
        result["l51_analog"] = False
    else:
        result["conclusion"] = "INDETERMINATE"
        result["l51_analog"] = None

    result["spy_adverse_move_first"] = _spy_adverse_first(obs, spy_path)
    return result


def _spy_bear_conf_bar(obs: dict, spy_path: list[dict]) -> int | None:
    """First bar (>= bar 1) where SPY close < entry price."""
    entry_close = obs["entry_price"]
    for sb in spy_path[1:]:
        if sb["close"] < entry_close:
            return sb["bar"]
    return None


def _spy_adverse_first(obs: dict, spy_path: list[dict]) -> bool:
    """Did SPY go ABOVE entry price before going below it?
    Adverse for a short = SPY going up (put premiums drop).
    """
    entry_close = obs["entry_price"]
    for sb in spy_path[1:]:
        if sb["high"] > entry_close:
            return True  # adverse move first
        if sb["close"] < entry_close:
            return False  # bear move first
    return False


def _spy_bar1_3_max_adverse(obs: dict, spy_path: list[dict]) -> float:
    """Max SPY high in bars 1-3 minus entry price (adverse exposure in first 3 bars)."""
    entry_close = obs["entry_price"]
    max_h = max((sb["high"] for sb in spy_path[1:4]), default=entry_close)
    return round(max_h - entry_close, 2)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[chartstop] loading SPY data...")
    spy = _load_spy()
    print(f"[chartstop] spy rows: {len(spy)}")

    results = []
    l51_count = 0
    no_data_count = 0

    for obs in STOPPED_OBS:
        print(f"\n[chartstop] analyzing {obs['date']} {obs['time']} entry={obs['entry_price']} vix={obs['vix']}")
        r = _analyze_obs(obs, spy)

        # add derived summary
        r["spy_bar1_3_max_adverse_cents"] = _spy_bar1_3_max_adverse(obs, r.get("spy_path", []))
        print(f"  option: {r.get('option_symbol_used')}  loaded={r.get('option_loaded')}")
        print(f"  entry_premium: {r.get('entry_premium')}  stop_threshold: {r.get('premium_stop_threshold')}")
        print(f"  premium_stop_fires_bar: {r.get('premium_stop_fires_bar')}  bear_conf_bar: {r.get('bear_confirmation_bar')}")
        print(f"  chart_stop_fires_bar: {r.get('chart_stop_fires_bar')}")
        print(f"  spy_adverse_move_first: {r.get('spy_adverse_move_first')}  spy_bar1-3_max_adverse: +{r.get('spy_bar1_3_max_adverse_cents')}c")
        print(f"  CONCLUSION: {r.get('conclusion')}  l51_analog={r.get('l51_analog')}")

        if r.get("l51_analog"):
            l51_count += 1
        if not r.get("option_loaded"):
            no_data_count += 1

        results.append(r)

    # ── Summary ────────────────────────────────────────────────────────────────
    summary = {
        "total_obs": len(STOPPED_OBS),
        "l51_analog_count": l51_count,
        "no_option_data_count": no_data_count,
        "l51_analog_fraction": round(l51_count / max(len(STOPPED_OBS) - no_data_count, 1), 3),
        "recommendation": (
            "SWITCH_TO_CHART_STOP" if l51_count >= 3
            else "INVESTIGATE_FURTHER" if l51_count >= 1
            else "PREMIUM_STOP_OK"
        ),
        "obs": results,
    }

    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[chartstop] wrote {OUT_JSON}")

    # ── Markdown report ────────────────────────────────────────────────────────
    _write_md(summary)
    print(f"[chartstop] wrote {OUT_MD}")

    print(f"\n[chartstop] SUMMARY: {l51_count}/{len(STOPPED_OBS) - no_data_count} obs show L51 analog")
    print(f"  Recommendation: {summary['recommendation']}")


def _write_md(summary: dict):
    lines = [
        "# V14E Bear Chart-Stop Research — L51 Analog",
        "",
        f"> Generated: 2026-05-21 by v14e_chartstop_research.py",
        f"> Question: does the -8% premium stop fire BEFORE the directional bear move?",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Total stopped high-conf bear obs | {summary['total_obs']} |",
        f"| L51 analog confirmed | {summary['l51_analog_count']} / {summary['total_obs'] - summary['no_option_data_count']} with data |",
        f"| No option data | {summary['no_option_data_count']} |",
        f"| **Recommendation** | **{summary['recommendation']}** |",
        "",
        "## Per-Observation Detail",
        "",
    ]

    for r in summary["obs"]:
        lines.append(f"### {r['date']} {r['time']} — {r['regime']} (VIX={r['vix']}, score={r['score']})")
        lines.append("")
        lines.append(f"- Entry: SPY {r['entry_price']} | Chart stop: {r['stop_price_spy']} (+{round(r['stop_price_spy'] - r['entry_price'], 2)}) | Original P&L: ${r['pnl']}")
        lines.append(f"- Triggers: {r['triggers']}")
        lines.append(f"- {r.get('notes', '')}")
        lines.append("")
        if r.get("option_loaded"):
            lines.append(f"**Option data:** {r.get('option_symbol_used')} (strike {r.get('strike_used')})")
            lines.append(f"- Entry premium (bar-0 VWAP): ${r.get('entry_premium')}")
            lines.append(f"- -8% stop threshold: ${r.get('premium_stop_threshold')}")
            lines.append(f"- Premium stop fires: bar {r.get('premium_stop_fires_bar')} ({r.get('premium_stop_fires_time')}) drop={r.get('premium_drop_at_stop')}%")
            lines.append(f"- Bear confirmation (SPY<entry): bar {r.get('bear_confirmation_bar')}")
            lines.append(f"- Chart stop (SPY>{r.get('stop_price_spy')}): bar {r.get('chart_stop_fires_bar')}")
        else:
            lines.append(f"**Option data: NOT AVAILABLE** ({r.get('option_symbol_used')})")
        lines.append(f"- SPY adverse move first: {r.get('spy_adverse_move_first')}")
        lines.append(f"- Max adverse exposure bars 1-3: +{r.get('spy_bar1_3_max_adverse_cents')}c")
        lines.append(f"- **Conclusion: {r.get('conclusion')}** | L51 analog: {r.get('l51_analog')}")
        lines.append("")

        # show SPY path bars 0-5
        spy_path = r.get("spy_path", [])[:6]
        if spy_path:
            lines.append("**SPY path (bars 0-5 after entry fill):**")
            lines.append("")
            lines.append("| Bar | Time | O | H | L | C | vs_entry |")
            lines.append("|---|---|---|---|---|---|---|")
            entry_price = r["entry_price"]
            for b in spy_path:
                vs = round(b["close"] - entry_price, 2)
                sign = "+" if vs >= 0 else ""
                lines.append(f"| {b['bar']} | {b['time']} | {b['open']} | {b['high']} | {b['low']} | {b['close']} | {sign}{vs} |")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append("- Entry fill = first bar after trigger bar (at that bar's open as proxy)")
    lines.append("- Entry premium = first option bar VWAP after entry bar timestamp")
    lines.append("- -8% threshold = entry_premium × 0.92")
    lines.append("- L51 analog = premium stop fires at or before first bar where SPY close < entry")
    lines.append("- Chart stop = SPY high crosses stop_price_spy (rejection_level + $0.20)")
    lines.append("- Options: OTM-2 puts first; ATM puts as fallback (strike_offset=0)")
    lines.append("")
    lines.append("## Comparison: Production Stop vs Chart-Stop-Only")
    lines.append("")
    lines.append("| Mode | Fires when | Effect on L51-analog obs |")
    lines.append("|---|---|---|")
    lines.append("| Production (-8%) | Put premium drops 8% | Fires during initial bounce BEFORE bear move |")
    lines.append("| Chart stop (-0.99) | SPY crosses rejection_level + $0.20 | Fires ONLY if the rejection fails (false signal) |")
    lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
