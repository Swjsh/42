"""Characterize whether a price-structure VETO is safe for OP-16 source-of-truth trades.

Veto rule: block direction-fighting-structure entries.
  - veto BEAR/P when classify_trend == 'uptrend'
  - veto BULL/C when classify_trend == 'downtrend'
  - range/unknown => NO veto

For each (date, side, entry_et) compute crypto.lib.market_structure on the SPY bars
UP TO entry, on 5m AND 15m swings. Report trend, with/against, would-veto-block.
The decisive question: would the veto block ANY of the 3 PUT WINNERS?
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crypto.lib.bar import Bar
from crypto.lib.market_structure import analyze_structure, classify_trend, label_swings
from crypto.lib.trendlines import find_swing_points

CSV = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-18.csv"

# (date, side, entry_et_HHMM, label, is_winner)
ANCHORS = [
    ("2026-04-29", "P", "10:25", "710P WINNER", True),
    ("2026-05-01", "P", "13:09", "721P WINNER", True),
    ("2026-05-04", "P", "10:27", "721P WINNER", True),
    ("2026-05-05", "P", "13:00", "722P loser", False),
    ("2026-05-06", "P", "13:09", "730P loser", False),
    ("2026-05-07", "C", "12:30", "734C loser", False),
    ("2026-05-07", "C", "11:14", "737C loser", False),
]

ET = timezone(timedelta(hours=-4))  # data stamped -04:00 (EDT)


def load_5m() -> pd.DataFrame:
    df = pd.read_csv(CSV)
    df["ts"] = pd.to_datetime(df["timestamp_et"], utc=True)  # parse with offset -> UTC
    return df


def bars_from_df(df: pd.DataFrame, gran: int) -> list[Bar]:
    out = []
    for _, r in df.iterrows():
        ot = r["ts"].to_pydatetime()  # tz-aware UTC
        out.append(Bar(open_time=ot, open=float(r["open"]), high=float(r["high"]),
                       low=float(r["low"]), close=float(r["close"]),
                       volume=float(r["volume"]), granularity_seconds=gran, source="spy_5m_csv"))
    return out


def resample_15m(df_day: pd.DataFrame) -> pd.DataFrame:
    d = df_day.set_index("ts")
    agg = d.resample("15min", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum")).dropna()
    agg = agg.reset_index()
    return agg


def trend_for(bars: list[Bar], window: int) -> dict:
    """Return both: (a) classify_trend on labeled swings (the rule under test),
    and (b) the authoritative analyze_structure trend, for cross-check."""
    if len(bars) < 5:
        return {"classify": "unknown", "structure": "unknown", "n_bars": len(bars),
                "n_swings": 0, "seq": []}
    swings = find_swing_points(bars, window=window, inclusive_right=True)
    labeled = label_swings(swings)
    ct = classify_trend(labeled)
    msr = analyze_structure(bars, window=window)
    seq = [s.label for s in labeled[-6:]]
    return {"classify": ct, "structure": msr.trend, "structure_basis": msr.trend_basis,
            "n_bars": len(bars), "n_swings": len(swings), "seq": seq,
            "last_high": msr.last_swing_high, "last_low": msr.last_swing_low}


def would_block(side: str, trend: str) -> bool:
    if side == "P":  # bear entry; blocked in uptrend
        return trend == "uptrend"
    if side == "C":  # bull entry; blocked in downtrend
        return trend == "downtrend"
    return False


def main():
    df = load_5m()
    rows = []
    for date, side, hhmm, label, is_winner in ANCHORS:
        h, m = map(int, hhmm.split(":"))
        entry_utc = datetime(int(date[:4]), int(date[5:7]), int(date[8:10]), h + 4, m, tzinfo=timezone.utc)
        # Bars CLOSED at/before entry: close_time <= entry. 5m bar stamped at OPEN time.
        day_mask = df["ts"].dt.tz_convert(ET).dt.strftime("%Y-%m-%d") == date
        df_day = df[day_mask].copy()
        # bars up to entry: include bars whose CLOSE (open+5m) <= entry
        df_5m_upto = df[df["ts"] + pd.Timedelta(minutes=5) <= entry_utc].copy()
        # restrict 5m to a trailing window so swings reflect recent session structure.
        # Use full history available up to entry (intraday + prior days) for robust swings,
        # but ALSO compute a same-day-only read.
        df_5m_day_upto = df_day[df_day["ts"] + pd.Timedelta(minutes=5) <= entry_utc].copy()

        bars_5m_full = bars_from_df(df_5m_upto.tail(120), 300)   # ~2 sessions trailing
        bars_5m_day = bars_from_df(df_5m_day_upto, 300)

        # 15m: resample same-day-up-to-entry plus prior day tail for swing context
        df_15_src = df[df["ts"] + pd.Timedelta(minutes=5) <= entry_utc].copy()
        df_15 = resample_15m(df_15_src)
        # keep only 15m bars fully closed before entry
        df_15 = df_15[df_15["ts"] + pd.Timedelta(minutes=15) <= entry_utc].copy()
        bars_15m = bars_from_df(df_15.tail(80), 900)

        t5_full = trend_for(bars_5m_full, window=2)
        t5_day = trend_for(bars_5m_day, window=2)
        t15 = trend_for(bars_15m, window=2)

        rows.append({
            "date": date, "side": side, "label": label, "winner": is_winner,
            "entry_et": hhmm,
            "px_at_entry": round(float(df_5m_upto.tail(1)["close"].iloc[0]), 2) if len(df_5m_upto) else None,
            "t5_full": t5_full, "t5_day": t5_day, "t15": t15,
            "block_5m_full": would_block(side, t5_full["classify"]),
            "block_5m_day": would_block(side, t5_day["classify"]),
            "block_15m": would_block(side, t15["classify"]),
        })

    # Report
    print("=" * 110)
    print("STRUCTURE-VETO ANCHOR CHECK  (classify_trend; veto blocks direction-fighting-trend)")
    print("=" * 110)
    for r in rows:
        tag = "WINNER(MUST KEEP)" if r["winner"] else "loser(should skip)"
        print(f"\n{r['date']} {r['side']} {r['label']:14s} entry {r['entry_et']} px~{r['px_at_entry']}  [{tag}]")
        for tf, key in (("5m-trailing", "t5_full"), ("5m-sameday", "t5_day"), ("15m", "t15")):
            t = r[key]
            print(f"   {tf:12s} classify={t['classify']:9s} structure={t.get('structure','?'):9s}"
                  f" basis={t.get('structure_basis','?'):16s} nbars={t['n_bars']:3d} nsw={t['n_swings']:2d} seq={t['seq']}")
        print(f"   -> WOULD-BLOCK:  5m-trailing={r['block_5m_full']}  5m-sameday={r['block_5m_day']}  15m={r['block_15m']}")

    print("\n" + "=" * 110)
    print("SAFETY VERDICT")
    print("=" * 110)
    for tf, k in (("5m-trailing", "block_5m_full"), ("5m-sameday", "block_5m_day"), ("15m", "block_15m")):
        winners_blocked = [r["label"] for r in rows if r["winner"] and r[k]]
        losers_blocked = [r["label"] for r in rows if (not r["winner"]) and r[k]]
        safe = len(winners_blocked) == 0
        print(f"\n[{tf}]  winners_blocked={winners_blocked or 'NONE'}  | losers_blocked={losers_blocked or 'none'}"
              f"  | VETO_SAFE={safe}  | losers_caught={len(losers_blocked)}/4")


if __name__ == "__main__":
    main()
