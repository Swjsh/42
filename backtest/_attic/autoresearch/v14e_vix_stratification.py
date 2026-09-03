"""V14E bear-only VIX regime stratification.

Stratifies v14_enhanced_watcher bear-only observations by VIX level
to check if WR=58.5% is regime-robust or regime-concentrated.
Joins observations with VIX 5m CSV by bar timestamp.

Output: automation/state/logs/v14e-vix-stratification.json
"""
from __future__ import annotations

import json
import math
import datetime as dt
from pathlib import Path
from collections import defaultdict

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OBS_PATH = ROOT / "automation" / "state" / "watcher-observations.jsonl"
DATA_DIR = ROOT / "backtest" / "data"
OUT = ROOT / "automation" / "state" / "logs" / "v14e-vix-stratification.json"


def _load_vix() -> pd.DataFrame:
    for name in [
        "vix_5m_2025-01-01_2026-05-19_merged.csv",
        "vix_5m_2025-01-01_2026-05-15.csv",
        "vix_5m_2025-01-01_2026-05-12.csv",
        "vix_5m_2025-01-01_2026-05-07.csv",
    ]:
        p = DATA_DIR / name
        if p.exists():
            df = pd.read_csv(p)
            df["ts"] = pd.to_datetime(df["timestamp_et"])
            return df.set_index("ts")[["close"]].rename(columns={"close": "vix"})
    raise FileNotFoundError("No VIX CSV found")


def _sharpe(pnls: list[float]) -> float:
    if len(pnls) < 2:
        return float("nan")
    n = len(pnls)
    mean = sum(pnls) / n
    var = sum((p - mean) ** 2 for p in pnls) / (n - 1)
    if var <= 0:
        return float("nan")
    return (mean / math.sqrt(var)) * math.sqrt(252)


def _vix_bucket(vix: float) -> str:
    if vix < 15:
        return "vix<15"
    elif vix < 20:
        return "vix15-20"
    elif vix < 25:
        return "vix20-25"
    else:
        return "vix25+"


def main() -> None:
    vix_df = _load_vix()
    print(f"Loaded VIX data: {len(vix_df)} bars")

    # Load + dedup v14e obs by bar_timestamp_et[:16] (L67 — one row per 5-min bar).
    # Gamma_Heartbeat fires every 3 min; multiple ticks per bar inflate N ~2-4×.
    raw_lines = [l for l in OBS_PATH.read_text(encoding="utf-8").strip().split("\n") if l.strip()]
    _raw: list[dict] = []
    for line in raw_lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("watcher_name") != "v14_enhanced_watcher":
            continue
        if d.get("would_be_pnl_dollars") is None:
            continue
        _raw.append(d)
    _raw.sort(key=lambda x: x.get("bar_timestamp_et") or "")
    _seen_dedup: set[str] = set()
    lines_deduped: list[dict] = []
    for _d in _raw:
        _k = (_d.get("bar_timestamp_et") or "")[:16]
        if _k not in _seen_dedup:
            _seen_dedup.add(_k)
            lines_deduped.append(_d)

    bear_obs = []
    bull_obs = []
    vix_miss = 0
    for d in lines_deduped:
        bar_ts_str = d.get("bar_timestamp_et", "")
        try:
            bar_ts = pd.Timestamp(bar_ts_str)
        except Exception:
            continue

        # Look up VIX at this bar
        bar_ts_naive = bar_ts.tz_localize(None) if bar_ts.tzinfo else bar_ts
        candidates = [bar_ts_naive]
        for delta in [pd.Timedelta("5min"), pd.Timedelta("-5min"), pd.Timedelta("10min")]:
            candidates.append(bar_ts_naive + delta)

        vix_val = None
        for ts in candidates:
            if ts in vix_df.index:
                vix_val = float(vix_df.loc[ts, "vix"])
                break

        if vix_val is None:
            vix_miss += 1
            continue

        entry = {
            "date": bar_ts.date() if hasattr(bar_ts, "date") else None,
            "pnl": d["would_be_pnl_dollars"],
            "vix": vix_val,
            "confidence": d.get("confidence", "?"),
            "direction": d.get("direction", "?"),
        }
        if d.get("direction") == "short":
            bear_obs.append(entry)
        else:
            bull_obs.append(entry)

    print(f"V14E bear obs with VIX: {len(bear_obs)} (missed: {vix_miss})")
    print(f"V14E bull obs with VIX: {len(bull_obs)}")
    print()

    def analyze(obs: list[dict], label: str) -> dict:
        if not obs:
            print(f"{label}: NO DATA")
            return {}
        pnls = [o["pnl"] for o in obs]
        wins = sum(1 for p in pnls if p > 0)
        print(f"{label} OVERALL: N={len(pnls)} WR={wins/len(pnls):.1%} P&L=${sum(pnls):+.0f}")

        buckets: dict[str, list[float]] = defaultdict(list)
        for o in obs:
            b = _vix_bucket(o["vix"])
            buckets[b].append(o["pnl"])

        bucket_stats = {}
        for b in ["vix<15", "vix15-20", "vix20-25", "vix25+"]:
            bpnls = buckets.get(b, [])
            if not bpnls:
                bucket_stats[b] = {"n": 0, "wr": None, "total_pnl": 0.0}
                print(f"  {b}: NO DATA")
                continue
            wins = sum(1 for p in bpnls if p > 0)
            bucket_stats[b] = {
                "n": len(bpnls),
                "wr": round(wins / len(bpnls), 4),
                "total_pnl": round(sum(bpnls), 2),
                "avg_pnl": round(sum(bpnls) / len(bpnls), 2),
                "sharpe": round(_sharpe(bpnls), 4) if len(bpnls) >= 2 else None,
            }
            print(f"  {b}: N={len(bpnls)} WR={wins/len(bpnls):.1%} P&L=${sum(bpnls):+.0f} avg=${sum(bpnls)/len(bpnls):+.1f}")

        # Quarterly
        quarters: dict[str, list[float]] = defaultdict(list)
        for o in obs:
            if o["date"] is None:
                continue
            qn = (o["date"].month - 1) // 3 + 1
            q = f"{o['date'].year}-Q{qn}"
            quarters[q].append(o["pnl"])

        q_stats = {}
        pos_q = 0
        print(f"  Quarterly:")
        for q in sorted(quarters):
            qpnls = quarters[q]
            wins = sum(1 for p in qpnls if p > 0)
            q_stats[q] = {"n": len(qpnls), "wr": round(wins/len(qpnls), 4), "total_pnl": round(sum(qpnls), 2)}
            if sum(qpnls) > 0:
                pos_q += 1
            print(f"    {q}: N={len(qpnls)} WR={wins/len(qpnls):.0%} P&L=${sum(qpnls):+.0f}")
        print(f"  Positive quarters: {pos_q}/{len(quarters)}")
        print()

        return {"bucket_stats": bucket_stats, "quarterly": q_stats, "positive_quarters": pos_q, "total_quarters": len(quarters)}

    print("=" * 50)
    bear_result = analyze(bear_obs, "BEAR branch")
    bull_result = analyze(bull_obs, "BULL branch")

    result = {
        "analysis": "V14E VIX regime stratification",
        "generated_at": dt.datetime.now().isoformat(),
        "bear_branch": bear_result,
        "bull_branch": bull_result,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"Output: {OUT}")


if __name__ == "__main__":
    main()
