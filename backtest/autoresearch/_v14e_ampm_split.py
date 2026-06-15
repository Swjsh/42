"""V14E bearish AM vs PM quality split analysis.

Loads watcher-observations.jsonl, filters to v14_enhanced_watcher bear direction,
deduplicates by minute (L67), and breaks down by AM (09-12) vs PM (12-16),
hourly buckets, and confidence tier.

CLI::
    python -m autoresearch._v14e_ampm_split
"""
import collections
import datetime
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent  # .../backtest
ROOT = REPO.parent                             # .../42 (project root)
OBS_PATH = ROOT / "automation" / "state" / "watcher-observations.jsonl"


def load_bear_v14e() -> list[dict]:
    """Load and deduplicate bear v14_enhanced_watcher observations."""
    obs = []
    seen_keys: set[str] = set()

    with OBS_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("watcher_name") != "v14_enhanced_watcher":
                continue
            if r.get("direction") not in ("short", "bear"):
                continue
            ts = r.get("bar_timestamp_et", "")
            dedup_key = ts[:16]  # minute-level dedup per L67
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            obs.append(r)

    return obs


def _get_hour(ts: str) -> int:
    try:
        t = datetime.datetime.fromisoformat(ts).replace(tzinfo=None)
        return t.hour
    except Exception:
        return -1


def _stats(pnls: list[float]) -> str:
    if not pnls:
        return "N=0"
    wins = [p for p in pnls if p > 0]
    wr = len(wins) / len(pnls)
    total = sum(pnls)
    exp = total / len(pnls)
    return f"N={len(pnls)}  WR={wr:.1%}  exp=${exp:+.2f}  total=${total:+.2f}"


def main() -> None:
    obs = load_bear_v14e()
    print(f"Unique bear v14e obs (deduped by minute, L67): {len(obs)}")
    print()

    # AM / PM split
    am_pnls = []
    pm_pnls = []
    hourly: dict[int, list[float]] = collections.defaultdict(list)
    conf_groups: dict[str, list[float]] = collections.defaultdict(list)
    early_hours: dict[int, list[float]] = collections.defaultdict(list)  # finer 30-min?

    for r in obs:
        ts = r.get("bar_timestamp_et", "")
        h = _get_hour(ts)
        pnl = float(r.get("would_be_pnl_dollars", 0) or 0)
        conf = r.get("confidence", "unknown")

        hourly[h].append(pnl)
        conf_groups[conf].append(pnl)

        if 9 <= h < 12:
            am_pnls.append(pnl)
        elif 12 <= h < 16:
            pm_pnls.append(pnl)

    print("=== AM vs PM BEARISH V14E SPLIT (deduped) ===")
    print(f"  AM (09:xx-11:xx): {_stats(am_pnls)}")
    print(f"  PM (12:xx-15:xx): {_stats(pm_pnls)}")
    print()

    print("=== HOURLY BREAKDOWN ===")
    for h in sorted(hourly):
        if h < 9:
            continue
        pnls = hourly[h]
        print(f"  {h:02d}:xx  {_stats(pnls)}")
    print()

    print("=== CONFIDENCE SPLIT (bear v14e, deduped) ===")
    for c in sorted(conf_groups):
        pnls = conf_groups[c]
        print(f"  conf={c:8s}: {_stats(pnls)}")
    print()

    # Combined: AM + high-conf filter
    high_am = [
        r.get("would_be_pnl_dollars", 0) or 0
        for r in obs
        if r.get("confidence") == "high" and 9 <= _get_hour(r.get("bar_timestamp_et", "")) < 12
    ]
    high_pm = [
        r.get("would_be_pnl_dollars", 0) or 0
        for r in obs
        if r.get("confidence") == "high" and 12 <= _get_hour(r.get("bar_timestamp_et", "")) < 16
    ]
    print("=== HIGH-CONF ONLY: AM vs PM ===")
    print(f"  HIGH+AM: {_stats(high_am)}")
    print(f"  HIGH+PM: {_stats(high_pm)}")
    print()

    # J anchor cross-ref
    j_winners = [("2026-05-04", "10:27"), ("2026-04-29", "10:25"), ("2026-05-01", "13:09")]
    print("=== J ANCHOR CROSS-REFERENCE ===")
    for date_str, time_str in j_winners:
        prefix = f"{date_str}T{time_str}"
        matched = [r for r in obs if r.get("bar_timestamp_et", "").startswith(prefix)]
        direction = "AM" if int(time_str.split(":")[0]) < 12 else "PM"
        print(f"  J {date_str} {time_str} ({direction}): "
              f"{'FOUND in obs' if matched else 'NOT in obs'}")


if __name__ == "__main__":
    main()
