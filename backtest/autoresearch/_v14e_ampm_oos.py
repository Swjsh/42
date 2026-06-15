"""V14E bearish AM vs PM IS/OOS walk-forward split.

Extends _v14e_ampm_split.py by splitting the 156 deduped bear v14e observations
into IS (2025-01-01 to 2025-09-30) and OOS (2025-10-01 to 2026-05-22) to assess
whether the time-of-day quality split is stable OOS or an IS artifact.

The pre-merge gate for candidate #17 (V14E_BEAR_TIME_OF_DAY_GATE) requires an
OOS walk-forward to confirm the AM-bad / PM-good pattern before any watcher change.

Key question: Does the 11:xx worst-hour / 09:xx+12:xx best-hour pattern persist OOS?
And does the OP-16 anchor concern (4/29+5/04 at 10:xx) apply uniformly across IS+OOS?

CLI::
    python -m autoresearch._v14e_ampm_oos
"""
import collections
import datetime
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent  # .../backtest
ROOT = REPO.parent                             # .../42

OBS_PATH = ROOT / "automation" / "state" / "watcher-observations.jsonl"
IS_END   = datetime.date(2025, 9, 30)
OOS_START = datetime.date(2025, 10, 1)


def load_bear_v14e() -> list[dict]:
    """Load and deduplicate bear v14_enhanced_watcher observations (L67)."""
    obs: list[dict] = []
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
            dedup_key = ts[:16]
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            obs.append(r)

    return obs


def _obs_date(r: dict) -> datetime.date | None:
    ts = r.get("bar_timestamp_et", "")
    try:
        return datetime.datetime.fromisoformat(ts).date()
    except Exception:
        return None


def _obs_hour(r: dict) -> int:
    ts = r.get("bar_timestamp_et", "")
    try:
        return datetime.datetime.fromisoformat(ts).hour
    except Exception:
        return -1


def _stats(pnls: list[float]) -> str:
    if not pnls:
        return "N=0  WR=n/a  exp=n/a  total=n/a"
    wins = [p for p in pnls if p > 0]
    wr = len(wins) / len(pnls)
    total = sum(pnls)
    exp = total / len(pnls)
    return f"N={len(pnls)}  WR={wr:.1%}  exp=${exp:+.2f}  total=${total:+.2f}"


def _report_window(label: str, window_obs: list[dict]) -> dict:
    """Report full hourly + AM/PM breakdown for a window. Returns summary dict."""
    print(f"\n{'='*60}")
    print(f"{label}  (N={len(window_obs)} deduped obs)")
    print(f"{'='*60}")

    am_pnls: list[float] = []
    pm_pnls: list[float] = []
    hourly: dict[int, list[float]] = collections.defaultdict(list)
    conf_groups: dict[str, list[float]] = collections.defaultdict(list)
    high_am: list[float] = []
    high_pm: list[float] = []

    for r in window_obs:
        h = _obs_hour(r)
        pnl = float(r.get("would_be_pnl_dollars", 0) or 0)
        conf = r.get("confidence", "unknown")

        hourly[h].append(pnl)
        conf_groups[conf].append(pnl)

        if 9 <= h < 12:
            am_pnls.append(pnl)
            if conf == "high":
                high_am.append(pnl)
        elif 12 <= h < 16:
            pm_pnls.append(pnl)
            if conf == "high":
                high_pm.append(pnl)

    print(f"\n  AM (09-11):  {_stats(am_pnls)}")
    print(f"  PM (12-15):  {_stats(pm_pnls)}")

    print(f"\n  Hourly breakdown:")
    for h in sorted(hourly):
        if h < 9:
            continue
        marker = ""
        if sum(hourly[h]) < -50 or (len(hourly[h]) > 5 and len([p for p in hourly[h] if p > 0]) / len(hourly[h]) < 0.50):
            marker = " <-- WEAK"
        print(f"    {h:02d}:xx  {_stats(hourly[h])}{marker}")

    print(f"\n  Confidence split:")
    for c in sorted(conf_groups):
        print(f"    {c:8s}: {_stats(conf_groups[c])}")

    print(f"\n  HIGH+AM:  {_stats(high_am)}")
    print(f"  HIGH+PM:  {_stats(high_pm)}")

    # PM-only sim: drop 10:xx-11:xx, keep 09:xx and 12:xx+
    pm_only_pnls = [float(r.get("would_be_pnl_dollars", 0) or 0)
                    for r in window_obs
                    if _obs_hour(r) == 9 or _obs_hour(r) >= 12]
    chop_block_pnls = [float(r.get("would_be_pnl_dollars", 0) or 0)
                       for r in window_obs
                       if _obs_hour(r) not in (10, 11)]
    all_pnls = [float(r.get("would_be_pnl_dollars", 0) or 0) for r in window_obs]
    total_all = sum(all_pnls)
    total_pm_only = sum(pm_only_pnls)

    print(f"\n  All hours (baseline):  {_stats(all_pnls)}")
    print(f"  Chop-block (drop 10+11:xx): {_stats(chop_block_pnls)}")
    if total_all != 0:
        improvement = total_pm_only - total_all
        pct = improvement / abs(total_all) * 100
        print(f"  Block improvement vs baseline: ${improvement:+.2f} ({pct:+.1f}%)")

    am_exp = sum(am_pnls) / len(am_pnls) if am_pnls else 0.0
    pm_exp = sum(pm_pnls) / len(pm_pnls) if pm_pnls else 0.0

    return {
        "n": len(window_obs),
        "am_n": len(am_pnls), "am_wr": len([p for p in am_pnls if p > 0]) / len(am_pnls) if am_pnls else 0,
        "am_exp": am_exp, "am_total": sum(am_pnls),
        "pm_n": len(pm_pnls), "pm_wr": len([p for p in pm_pnls if p > 0]) / len(pm_pnls) if pm_pnls else 0,
        "pm_exp": pm_exp, "pm_total": sum(pm_pnls),
        "pm_over_am_ratio": (pm_exp / am_exp) if am_exp != 0 else float("inf"),
    }


def main() -> None:
    obs = load_bear_v14e()
    print(f"Total unique bear v14e obs (deduped, full window): {len(obs)}")

    # Split by IS/OOS
    is_obs  = [r for r in obs if (d := _obs_date(r)) and d <= IS_END]
    oos_obs = [r for r in obs if (d := _obs_date(r)) and d >= OOS_START]

    print(f"IS  (2025-01-01 to 2025-09-30): {len(is_obs)} obs")
    print(f"OOS (2025-10-01 to 2026-05-22): {len(oos_obs)} obs")

    is_summ  = _report_window("IS  (2025-01-01 -> 2025-09-30)", is_obs)
    oos_summ = _report_window("OOS (2025-10-01 -> 2026-05-22)", oos_obs)

    # WF ratio for PM exp / AM exp
    print(f"\n{'='*60}")
    print("WALK-FORWARD SUMMARY (AM/PM pattern stability)")
    print(f"{'='*60}")
    print(f"  IS  PM exp: {is_summ['pm_exp']:+.2f}  AM exp: {is_summ['am_exp']:+.2f}")
    print(f"  OOS PM exp: {oos_summ['pm_exp']:+.2f}  AM exp: {oos_summ['am_exp']:+.2f}")

    # Key question: does PM remain better than AM OOS?
    is_pm_better  = is_summ['pm_exp'] > is_summ['am_exp']
    oos_pm_better = oos_summ['pm_exp'] > oos_summ['am_exp']
    print(f"\n  IS:  PM>AM = {is_pm_better}  (PM exp:{is_summ['pm_exp']:+.2f} vs AM:{is_summ['am_exp']:+.2f})")
    print(f"  OOS: PM>AM = {oos_pm_better} (PM exp:{oos_summ['pm_exp']:+.2f} vs AM:{oos_summ['am_exp']:+.2f})")

    if oos_pm_better:
        print("\n  OOS CONFIRMS: PM session remains superior to AM -- pattern is stable OOS.")
    else:
        print("\n  OOS FAILS: PM no longer superior to AM in OOS window -- pattern is IS artifact.")

    # J anchor cross-reference
    j_entries = [
        ("2026-04-29", "10:25", "winner", "+$342"),
        ("2026-05-01", "13:09", "winner", "+$470"),
        ("2026-05-04", "10:27", "winner", "+$730"),
    ]
    print(f"\n{'='*60}")
    print("J ANCHOR CROSS-REFERENCE (hard-block impact)")
    print(f"{'='*60}")
    for date_str, time_str, kind, pnl_label in j_entries:
        prefix = f"{date_str}T{time_str}"
        matched = [r for r in obs if r.get("bar_timestamp_et", "").startswith(prefix)]
        h = int(time_str.split(":")[0])
        session = "AM" if h < 12 else "PM"
        blocked = (10 <= h < 12)
        flag = " <-- HARD BLOCK WOULD REMOVE THIS WINNER" if (blocked and kind == "winner") else ""
        print(f"  {date_str} {time_str} {session} ({kind} {pnl_label}): "
              f"{'in obs' if matched else 'not in obs'}{flag}")


if __name__ == "__main__":
    main()
