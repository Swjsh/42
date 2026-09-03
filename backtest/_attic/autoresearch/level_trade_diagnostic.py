"""
Level-trade diagnostic: classify IS trades by direction, tier, VIX regime, and wick geometry.

Answers:
  1. Direction split — are there CALL trades in BEARISH_REVERSAL IS? (vix_bull_max anomaly)
  2. Tier breakdown — LEVEL vs TRENDLINE vs ELITE vs SUPER P&L by tier
  3. LEVEL VIX buckets — where are LEVEL losses concentrated?
  4. LEVEL wick geometry — body-vs-wick ratio on entry bar
"""

import sys
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

# ── constants ──────────────────────────────────────────────────────────────────
DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START = dt.date(2025, 1, 2)
IS_END   = dt.date(2026, 5, 7)

BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
)


def classify_tier(triggers):
    """Infer quality tier from triggers_fired list."""
    t = [x.split("_")[0] if "_" in x else x for x in triggers]
    full = [x.lower() for x in triggers]
    has_confluence = any("confluence" in x for x in full)
    has_ribbon_flip = any("ribbon_flip" in x for x in full)
    has_sequence = any("sequence_rejection" in x for x in full)
    has_level = any(x in ("level_rejection", "level_reclaim") for x in full)
    has_trendline = any("trendline_rejection" in x for x in full)
    n = len(triggers)
    if n >= 3 and has_confluence and has_ribbon_flip:
        return "SUPER"
    elif n >= 2 and (has_confluence or has_sequence):
        return "ELITE"
    elif has_level:
        return "LEVEL"
    elif has_trendline:
        return "TRENDLINE"
    else:
        return "BASE"


def vix_bucket(vix):
    if vix < 17.30:
        return "A_flat(<17.3)"
    elif vix < 20:
        return "B_normal(17.3-20)"
    elif vix < 30:
        return "C_elevated(20-30)"
    else:
        return "D_crisis(30+)"


def print_table(rows, header, fmt):
    """rows: list of dicts; header: list of (label, key); fmt: per-key format spec."""
    col_w = {h: max(len(label), max(len(str(r[k])) for r in rows)) for label, k in header for h, k in [(label, k)]}
    hdr = "  ".join(f"{label:<{col_w[label]}}" for label, _ in header)
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print("  ".join(f"{str(r[k]):<{col_w[label]}}" for label, k in header))


def main():
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)
    print("  spy rows:", len(spy_df), "  vix rows:", len(vix_df))

    # Build timestamp index for fast bar lookup
    spy_df["ts"] = pd.to_datetime(spy_df["timestamp_et"], utc=True)
    spy_ts_idx = {row.ts: row for row in spy_df.itertuples()}

    print("Running IS backtest...")
    result = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **BASE)
    trades = result.trades
    print(f"  IS trades: {len(trades)}")

    # ── 1. Direction split ──────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("1. DIRECTION SPLIT (CALL vs PUT)")
    print("=" * 72)

    dir_stats = {}
    for t in trades:
        d = "PUT" if t.side == "P" else "CALL"
        if d not in dir_stats:
            dir_stats[d] = {"n": 0, "pnl": 0.0, "wins": 0}
        dir_stats[d]["n"] += 1
        dir_stats[d]["pnl"] += t.dollar_pnl
        if t.dollar_pnl > 0:
            dir_stats[d]["wins"] += 1

    for d, s in sorted(dir_stats.items()):
        wr = s["wins"] / s["n"] * 100 if s["n"] else 0
        avg = s["pnl"] / s["n"] if s["n"] else 0
        print(f"  {d:5s}  n={s['n']:4d}  WR={wr:4.1f}%  total_pnl={s['pnl']:+,.0f}  avg={avg:+.0f}")

    # ── 2. Tier breakdown ───────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("2. QUALITY TIER BREAKDOWN")
    print("=" * 72)

    tier_stats = {}
    for t in trades:
        tier = classify_tier(t.triggers_fired)
        if tier not in tier_stats:
            tier_stats[tier] = {"n": 0, "pnl": 0.0, "wins": 0, "dir": {"PUT": 0, "CALL": 0}}
        tier_stats[tier]["n"] += 1
        tier_stats[tier]["pnl"] += t.dollar_pnl
        if t.dollar_pnl > 0:
            tier_stats[tier]["wins"] += 1
        d = "PUT" if t.side == "P" else "CALL"
        tier_stats[tier]["dir"][d] += 1

    for tier in ["SUPER", "ELITE", "LEVEL", "TRENDLINE", "BASE"]:
        if tier not in tier_stats:
            continue
        s = tier_stats[tier]
        wr = s["wins"] / s["n"] * 100 if s["n"] else 0
        avg = s["pnl"] / s["n"] if s["n"] else 0
        print(f"  {tier:12s}  n={s['n']:4d}  WR={wr:4.1f}%  total_pnl={s['pnl']:+,.0f}  avg={avg:+.0f}  "
              f"(PUT={s['dir']['PUT']} CALL={s['dir']['CALL']})")

    # ── 3. LEVEL trade VIX buckets ──────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("3. LEVEL TIER: VIX-AT-ENTRY BUCKETS")
    print("=" * 72)

    level_trades = [t for t in trades if classify_tier(t.triggers_fired) == "LEVEL"]
    print(f"  Total LEVEL trades in IS: {len(level_trades)}")

    vix_buckets = {}
    for t in level_trades:
        b = vix_bucket(t.entry_vix)
        if b not in vix_buckets:
            vix_buckets[b] = {"n": 0, "pnl": 0.0, "wins": 0, "examples": []}
        vix_buckets[b]["n"] += 1
        vix_buckets[b]["pnl"] += t.dollar_pnl
        if t.dollar_pnl > 0:
            vix_buckets[b]["wins"] += 1
        if len(vix_buckets[b]["examples"]) < 3:
            vix_buckets[b]["examples"].append((t.entry_time_et.date(), t.entry_vix, t.dollar_pnl))

    for b in sorted(vix_buckets.keys()):
        s = vix_buckets[b]
        wr = s["wins"] / s["n"] * 100 if s["n"] else 0
        avg = s["pnl"] / s["n"] if s["n"] else 0
        print(f"  {b:25s}  n={s['n']:3d}  WR={wr:4.1f}%  total={s['pnl']:+,.0f}  avg={avg:+.0f}")

    # ── 4. LEVEL trade wick geometry ────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("4. LEVEL TIER: ENTRY BAR WICK GEOMETRY")
    print("=" * 72)

    wick_dominant_wins = 0
    wick_dominant_losses = 0
    body_dominant_wins = 0
    body_dominant_losses = 0
    no_match = 0

    for t in level_trades:
        # Find the entry bar in spy_df (match by timestamp)
        et = t.entry_time_et
        if not isinstance(et, dt.datetime):
            no_match += 1
            continue

        # Try tz-aware match
        if et.tzinfo is None:
            import pytz
            et_aware = pytz.timezone("US/Eastern").localize(et).astimezone(pytz.utc)
        else:
            et_aware = et.astimezone(dt.timezone.utc)

        # Get the row from spy_df closest to entry time
        try:
            ts_series = spy_df["ts"]
            idx = (ts_series - et_aware).abs().idxmin()
            row = spy_df.iloc[idx]
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]

            bar_range = h - l
            if bar_range == 0:
                no_match += 1
                continue

            body = abs(c - o)
            upper_wick = h - max(c, o)
            lower_wick = min(c, o) - l
            total_wick = upper_wick + lower_wick
            wick_dominant = total_wick > body

            if wick_dominant:
                if t.dollar_pnl > 0:
                    wick_dominant_wins += 1
                else:
                    wick_dominant_losses += 1
            else:
                if t.dollar_pnl > 0:
                    body_dominant_wins += 1
                else:
                    body_dominant_losses += 1
        except Exception:
            no_match += 1
            continue

    total_wick = wick_dominant_wins + wick_dominant_losses
    total_body = body_dominant_wins + body_dominant_losses

    print(f"  Wick-dominant bars: n={total_wick}  wins={wick_dominant_wins}  losses={wick_dominant_losses}"
          f"  WR={wick_dominant_wins/total_wick*100:.1f}%" if total_wick else
          f"  Wick-dominant bars: n=0")
    print(f"  Body-dominant bars: n={total_body}  wins={body_dominant_wins}  losses={body_dominant_losses}"
          f"  WR={body_dominant_wins/total_body*100:.1f}%" if total_body else
          f"  Body-dominant bars: n=0")
    if no_match:
        print(f"  No-match (ts lookup failed): {no_match}")

    # P&L split
    wick_pnl = sum(t.dollar_pnl for t in level_trades
                   if _is_wick_dominant(t, spy_df) is True)
    body_pnl = sum(t.dollar_pnl for t in level_trades
                   if _is_wick_dominant(t, spy_df) is False)
    print(f"  Wick-dominant P&L total: {wick_pnl:+,.0f}")
    print(f"  Body-dominant P&L total: {body_pnl:+,.0f}")

    # ── 5. LEVEL trade trigger breakdown ────────────────────────────────────────
    print("\n" + "=" * 72)
    print("5. LEVEL TIER: TRIGGER BREAKDOWN")
    print("=" * 72)

    trig_stats = {}
    for t in level_trades:
        # Normalize trigger (strip price suffix)
        normalized = []
        for tr in t.triggers_fired:
            base = tr
            for sep in ["_", " "]:
                parts = tr.split(sep)
                try:
                    float(parts[-1])
                    base = sep.join(parts[:-1])
                except (ValueError, IndexError):
                    pass
            normalized.append(base)

        key = "|".join(sorted(set(normalized)))
        if key not in trig_stats:
            trig_stats[key] = {"n": 0, "pnl": 0.0, "wins": 0}
        trig_stats[key]["n"] += 1
        trig_stats[key]["pnl"] += t.dollar_pnl
        if t.dollar_pnl > 0:
            trig_stats[key]["wins"] += 1

    for key, s in sorted(trig_stats.items(), key=lambda x: -abs(x[1]["pnl"])):
        wr = s["wins"] / s["n"] * 100 if s["n"] else 0
        avg = s["pnl"] / s["n"] if s["n"] else 0
        print(f"  {key:40s}  n={s['n']:3d}  WR={wr:4.1f}%  avg={avg:+.0f}")

    print("\n[ANALYSIS COMPLETE]")


def _is_wick_dominant(t, spy_df):
    """Return True/False/None for wick-dominant check on entry bar."""
    try:
        et = t.entry_time_et
        if et.tzinfo is None:
            import pytz
            et_aware = pytz.timezone("US/Eastern").localize(et).astimezone(pytz.utc)
        else:
            et_aware = et.astimezone(dt.timezone.utc)

        idx = (spy_df["ts"] - et_aware).abs().idxmin()
        row = spy_df.iloc[idx]
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        bar_range = h - l
        if bar_range == 0:
            return None
        body = abs(c - o)
        total_wick = (h - max(c, o)) + (min(c, o) - l)
        return total_wick > body
    except Exception:
        return None


if __name__ == "__main__":
    main()
