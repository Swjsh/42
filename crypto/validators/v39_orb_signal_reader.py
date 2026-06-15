"""v39_orb_signal_reader — ORB heartbeat integration regression gate.

Background:
  2026-05-24: Integration spec filed at
  `strategy/candidates/_analysis/2026-05-24-orb-heartbeat-integration-spec.md`.

  The spec describes Path A for ORB heartbeat integration: heartbeat reads
  watcher-observations.jsonl for ORB_RETEST_LONG signals with confidence==medium
  that fired within the last 10 minutes on today's date.

  This validator tests that exact read/filter logic — the "inner loop" of the
  heartbeat ORB branch — so a regression in the filter logic produces a FAIL
  before it silently breaks live signal detection.

  Key filtering rules (from spec §3 Change A):
    1. watcher_name == "orb_watcher"
    2. setup_name == "ORB_RETEST_LONG"
    3. confidence == "medium"  (high=$-198/9 fires = consensus trap; medium=+EV)
    4. bar_timestamp_et.date == today_et
    5. (now_et - bar_timestamp_et) <= 10 min  (retest window still live)

  If all 5 pass → signal is "active". Most recent active signal wins.

Offline tests (8):
  T1  Valid medium-conf ORB signal 5 min old → returned
  T2  ORB signal confidence=high → excluded (consensus trap)
  T3  ORB signal confidence=low → excluded (no edge at low tier)
  T4  Valid ORB signal but 15 min stale → excluded (retest window closed)
  T5  Valid ORB signal but yesterday's date → excluded (stale from prior session)
  T6  Different watcher_name (v14_enhanced) → excluded (wrong watcher)
  T7  Two signals: older medium-conf + newer medium-conf → newest returned
  T8  No ORB signals in observations → returns None

Live audit:
  Reads automation/state/watcher-observations.jsonl for all ORB_RETEST_LONG
  observations and reports: count by confidence, count by week since 2026-05-21,
  would-be-stale rate at 3/5/10 min windows, and OP-21 accumulation projection.
  pass=True always (informational — not a blocking gate).

Modes:
  offline  8 deterministic tests. All 8 must PASS.
  live     Audit mode — pass=True always.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Core signal reader (the logic heartbeat.md would use)
# ---------------------------------------------------------------------------

def read_active_orb_signal(
    obs_source,  # path-like or file-like with JSONL content
    now_et: dt.datetime,
    stale_minutes: int = 10,
) -> Optional[dict]:
    """Return the most recent active ORB_RETEST_LONG medium-conf signal.

    Active = watcher_name==orb_watcher AND setup_name==ORB_RETEST_LONG AND
             confidence==medium AND bar_timestamp_et.date==today AND
             (now_et - bar_timestamp_et) <= stale_minutes.

    Returns the newest qualifying row dict, or None if none qualify.
    """
    today = now_et.date()
    stale_cutoff = now_et - dt.timedelta(minutes=stale_minutes)

    lines: list[str] = []
    if isinstance(obs_source, (str, Path)):
        p = Path(obs_source)
        if not p.exists():
            return None
        with p.open(encoding="utf-8") as fh:
            lines = fh.readlines()
    else:
        # file-like (StringIO)
        obs_source.seek(0)
        lines = obs_source.readlines()

    # Scan newest-first (tail of file is newest)
    best: Optional[dict] = None
    best_ts: Optional[dt.datetime] = None

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Filter 1 — correct watcher
        if row.get("watcher_name") != "orb_watcher":
            continue

        # Filter 2 — correct setup
        if row.get("setup_name") != "ORB_RETEST_LONG":
            continue

        # Filter 3 — medium confidence only
        if row.get("confidence") != "medium":
            continue

        # Filter 4 — today's date
        bar_ts_str = row.get("bar_timestamp_et", "")
        try:
            bar_ts = dt.datetime.fromisoformat(bar_ts_str)
            # Make tz-naive for comparison if needed
            if bar_ts.tzinfo is not None:
                bar_ts = bar_ts.replace(tzinfo=None)
        except (ValueError, TypeError):
            continue

        if bar_ts.date() != today:
            continue

        # Filter 5 — not stale
        if bar_ts < stale_cutoff.replace(tzinfo=None):
            continue

        # Track newest qualifying signal
        if best_ts is None or bar_ts > best_ts:
            best = row
            best_ts = bar_ts

    return best


# ---------------------------------------------------------------------------
# Offline tests
# ---------------------------------------------------------------------------

def _make_obs(
    watcher_name: str = "orb_watcher",
    setup_name: str = "ORB_RETEST_LONG",
    confidence: str = "medium",
    bar_ts: Optional[dt.datetime] = None,
    entry_price: float = 560.50,
    stop_price: float = 559.90,
    tp1_price: float = 561.25,
    runner_price: float = 562.00,
) -> str:
    """Serialize one observation row as a JSONL line."""
    row = {
        "observed_at": "2026-05-24T10:30:00",
        "bar_timestamp_et": bar_ts.isoformat() if bar_ts else "2026-05-24T10:25:00",
        "watcher_name": watcher_name,
        "setup_name": setup_name,
        "direction": "long",
        "entry_price": entry_price,
        "stop_price": stop_price,
        "tp1_price": tp1_price,
        "runner_price": runner_price,
        "confidence": confidence,
        "reason": "ORH 560.00 broken, retested at 560.05 held + green close 560.50",
        "triggers_fired": ["orh_breakout_retest", "sma_bullish"],
        "metadata": {"or_high": 560.00, "or_low": 558.50, "or_range": 1.50,
                     "pt_05": 560.75, "pt_10": 561.50, "bars_to_retest": 3},
        "would_be_outcome": None,
        "would_be_pnl_dollars": None,
    }
    return json.dumps(row)


def run_offline() -> dict:
    results: list[dict] = []

    # Reference: now = 2026-05-24 10:30 ET
    NOW = dt.datetime(2026, 5, 24, 10, 30, 0)
    TODAY = NOW.date()
    YESTERDAY = TODAY - dt.timedelta(days=1)

    # --- T1: valid medium-conf ORB signal 5 min old → returned ---
    ts_5min = NOW - dt.timedelta(minutes=5)
    src = io.StringIO(_make_obs(bar_ts=ts_5min))
    sig = read_active_orb_signal(src, NOW)
    ok = sig is not None and sig["setup_name"] == "ORB_RETEST_LONG" and sig["confidence"] == "medium"
    results.append({"test": "T1", "pass": ok,
                    "desc": "valid medium-conf ORB 5 min old -> returned",
                    "detail": f"sig={'present' if sig else 'None'} conf={sig['confidence'] if sig else '?'}"})

    # --- T2: ORB signal confidence=high → excluded ---
    src = io.StringIO(_make_obs(confidence="high", bar_ts=ts_5min))
    sig = read_active_orb_signal(src, NOW)
    ok = sig is None
    results.append({"test": "T2", "pass": ok,
                    "desc": "ORB signal confidence=high -> excluded (consensus trap)",
                    "detail": f"sig={'None' if sig is None else sig['confidence']}"})

    # --- T3: ORB signal confidence=low → excluded ---
    src = io.StringIO(_make_obs(confidence="low", bar_ts=ts_5min))
    sig = read_active_orb_signal(src, NOW)
    ok = sig is None
    results.append({"test": "T3", "pass": ok,
                    "desc": "ORB signal confidence=low -> excluded (no edge at low tier)",
                    "detail": f"sig={'None' if sig is None else sig['confidence']}"})

    # --- T4: valid ORB signal but 15 min stale → excluded ---
    ts_15min = NOW - dt.timedelta(minutes=15)
    src = io.StringIO(_make_obs(bar_ts=ts_15min))
    sig = read_active_orb_signal(src, NOW)
    ok = sig is None
    results.append({"test": "T4", "pass": ok,
                    "desc": "ORB signal 15 min stale -> excluded (retest window closed)",
                    "detail": f"sig={'None' if sig is None else 'present'}"})

    # --- T5: valid ORB signal but yesterday's date → excluded ---
    ts_yesterday = dt.datetime(YESTERDAY.year, YESTERDAY.month, YESTERDAY.day, 10, 25, 0)
    src = io.StringIO(_make_obs(bar_ts=ts_yesterday))
    sig = read_active_orb_signal(src, NOW)
    ok = sig is None
    results.append({"test": "T5", "pass": ok,
                    "desc": "ORB signal from yesterday -> excluded (stale from prior session)",
                    "detail": f"sig={'None' if sig is None else 'present'}"})

    # --- T6: different watcher_name → excluded ---
    src = io.StringIO(_make_obs(watcher_name="v14_enhanced_watcher", bar_ts=ts_5min))
    sig = read_active_orb_signal(src, NOW)
    ok = sig is None
    results.append({"test": "T6", "pass": ok,
                    "desc": "watcher_name=v14_enhanced -> excluded (wrong watcher)",
                    "detail": f"sig={'None' if sig is None else 'present'}"})

    # --- T7: two signals, older then newer → newest returned ---
    ts_older = NOW - dt.timedelta(minutes=8)
    ts_newer = NOW - dt.timedelta(minutes=3)
    lines = "\n".join([
        _make_obs(bar_ts=ts_older, entry_price=560.20),  # older
        _make_obs(bar_ts=ts_newer, entry_price=560.80),  # newer (most recent)
    ])
    src = io.StringIO(lines)
    sig = read_active_orb_signal(src, NOW)
    ok = (sig is not None and abs(sig["entry_price"] - 560.80) < 0.01)
    results.append({"test": "T7", "pass": ok,
                    "desc": "two valid signals -> newest entry_price=560.80 returned",
                    "detail": f"entry_price={sig['entry_price'] if sig else 'None'} (expected 560.80)"})

    # --- T8: no ORB signals (only other watcher) → None ---
    src = io.StringIO(_make_obs(watcher_name="bullish_watcher", bar_ts=ts_5min))
    sig = read_active_orb_signal(src, NOW)
    ok = sig is None
    results.append({"test": "T8", "pass": ok,
                    "desc": "no ORB signals in observations -> returns None",
                    "detail": f"sig={'None' if sig is None else 'present'}"})

    all_pass = all(r["pass"] for r in results)
    passed_n = sum(1 for r in results if r["pass"])
    total_n = len(results)

    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        print(f"  [{status}] {r['test']}: {r['desc']}")
        if not r["pass"]:
            print(f"         detail={r['detail']}")

    return {"mode": "offline", "pass": all_pass, "passed": passed_n, "total": total_n,
            "tests": results}


# ---------------------------------------------------------------------------
# Live audit
# ---------------------------------------------------------------------------

def run_live() -> dict:
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        return {"mode": "live", "pass": True,
                "note": "watcher-observations.jsonl not found", "orb_total": 0}

    # Count all ORB_RETEST_LONG observations
    by_conf: dict[str, int] = {}
    by_week: dict[str, int] = {}         # ISO week key → count
    stale_3min: int = 0                   # how many had <3 min gap to next heartbeat tick
    stale_10min: int = 0                  # 3-10 min gap
    too_stale: int = 0                    # >10 min (would be missed)
    total_orb = 0

    WATCHER_LIVE_DATE = dt.date(2026, 5, 21)  # when ORB watcher went live

    rows: list[dict] = []
    with obs_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("watcher_name") != "orb_watcher":
                continue
            if row.get("setup_name") != "ORB_RETEST_LONG":
                continue
            rows.append(row)

    total_orb = len(rows)

    for row in rows:
        conf = row.get("confidence", "unknown")
        by_conf[conf] = by_conf.get(conf, 0) + 1

        bar_ts_str = row.get("bar_timestamp_et", "")
        obs_ts_str = row.get("observed_at", "")
        try:
            bar_ts = dt.datetime.fromisoformat(bar_ts_str)
            if bar_ts.tzinfo is not None:
                bar_ts = bar_ts.replace(tzinfo=None)
            week_key = f"{bar_ts.isocalendar().year}-W{bar_ts.isocalendar().week:02d}"
            by_week[week_key] = by_week.get(week_key, 0) + 1
        except (ValueError, TypeError):
            pass

        # Compute gap between bar_ts and observed_at (how quickly it's logged)
        try:
            obs_ts = dt.datetime.fromisoformat(obs_ts_str)
            if obs_ts.tzinfo is not None:
                obs_ts = obs_ts.replace(tzinfo=None)
            gap_min = (obs_ts - bar_ts).total_seconds() / 60
            # For staleness analysis: simulating if heartbeat ticks every 3-5 min
            # How many minutes after bar_close would heartbeat READ this signal?
            if gap_min <= 3:
                stale_3min += 1
            elif gap_min <= 10:
                stale_10min += 1
            else:
                too_stale += 1
        except (ValueError, TypeError):
            pass

    # Separate historical (backtest replay) from live observations
    # Historical = bar_timestamp_et < WATCHER_LIVE_DATE
    # Live = bar_timestamp_et >= WATCHER_LIVE_DATE
    live_medium_count = 0
    hist_medium_count = 0
    for row in rows:
        if row.get("confidence") != "medium":
            continue
        bar_ts_str = row.get("bar_timestamp_et", "")
        try:
            bar_ts = dt.datetime.fromisoformat(bar_ts_str)
            if bar_ts.tzinfo is not None:
                bar_ts = bar_ts.replace(tzinfo=None)
            if bar_ts.date() >= WATCHER_LIVE_DATE:
                live_medium_count += 1
            else:
                hist_medium_count += 1
        except (ValueError, TypeError):
            hist_medium_count += 1  # can't parse → assume historical

    medium_count = by_conf.get("medium", 0)

    # OP-21 accumulation projection — use LIVE observations only for rate
    # watcher-observations.jsonl contains historical backtest replay data + live data
    # Rate calculation must use only live data to avoid inflated replay-based projections
    days_live = max(1, (dt.date.today() - WATCHER_LIVE_DATE).days)
    live_rate_per_day = live_medium_count / days_live
    live_rate_per_week = live_rate_per_day * 7
    weeks_to_3wins: "float | None" = None
    if live_rate_per_week > 0:
        # Expected wins per signal = 0.818; need 3 wins -> need 3/0.818 = 3.67 signals
        signals_needed = 3 / 0.818
        weeks_to_3wins = round(signals_needed / live_rate_per_week, 1)
    else:
        # No live signals yet — use backtest rate as floor estimate
        # Backtest: N=32 deduped medium over ~16 months = ~2/month = ~0.5/week
        weeks_to_3wins = round(3 / 0.818 / 0.5, 1)  # ~7.3 weeks at backtest rate

    print(f"  [AUDIT] ORB_RETEST_LONG observations: total={total_orb}")
    print(f"         by confidence: {dict(sorted(by_conf.items()))}")
    print(f"         live (>={WATCHER_LIVE_DATE}): medium={live_medium_count} | historical (backtest replay): medium={hist_medium_count}")
    if by_week:
        # Print last 8 weeks only to avoid flooding
        sorted_weeks = sorted(by_week.items())
        recent = dict(sorted_weeks[-8:])
        print(f"         recent weeks: {recent}")
    print(f"         staleness (replay-skewed — not meaningful for historical rows): <=3min={stale_3min} 3-10min={stale_10min} >10min={too_stale}")
    if live_medium_count == 0:
        print(f"         OP-21 projection: 0 live medium-conf obs since {WATCHER_LIVE_DATE} ({days_live} days)")
        print(f"                           using backtest floor: ~7.3 weeks at 0.5 signals/week, 81.8% WR")
    else:
        print(f"         OP-21 projection: {live_medium_count} live medium-conf obs in {days_live} days (~{live_rate_per_week:.2f}/week)")
        print(f"                           ~{weeks_to_3wins} more weeks to accumulate 3 J wins at 81.8% WR")

    return {
        "mode": "live",
        "pass": True,
        "note": "audit only — pass=True regardless",
        "orb_total": total_orb,
        "by_confidence": by_conf,
        "by_week": by_week,
        "staleness_3min": stale_3min,
        "staleness_3_10min": stale_10min,
        "staleness_too_stale": too_stale,
        "medium_count": medium_count,
        "live_medium_count": live_medium_count,
        "hist_medium_count": hist_medium_count,
        "live_rate_per_week": round(live_rate_per_week, 3),
        "op21_weeks_projected": weeks_to_3wins,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", choices=["offline", "live"], default="offline")
    args = parser.parse_args()

    print(f"\n[v39] ORB_SIGNAL_READER — mode={args.mode}")
    if args.mode == "live":
        result = run_live()
    else:
        result = run_offline()

    status = "PASS" if result["pass"] else "FAIL"
    if args.mode == "offline":
        print(f"\n  [{status}] {result['passed']}/{result['total']} tests passed")
    else:
        print(f"\n  [{status}] audit complete")
    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
