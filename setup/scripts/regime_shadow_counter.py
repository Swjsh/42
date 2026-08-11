#!/usr/bin/env python
"""regime_shadow_counter.py -- nightly SHADOW measurement for REGIME-CONDITIONAL-EXIT-2026-08-11.

Prereg: analysis/recommendations/prereg-regime-conditional-exit-2026-08-11.json (frozen BEFORE
any forward evidence existed). This script measures; it decides nothing and arms nothing.

WHAT IT LOGS, one row per trading day, append-only:
  S1  ER30 = |close(09:55) - open(09:30)| / (high - low) over 09:30-09:59 SPY 5m, plus the
      day's realized engine P&L. ER30 is knowable at 10:00 ET from CLOSED bars only.
  S2  Per-position: did the pre-TP1 ladder floor ARM, and did it FIRE -- tagged with the day's
      ER30 bucket. Read from the live exit ledger, not modelled.
  S3  The prereg's G5 kill-watch: the running share of LOW-ER days that printed GREEN. If that
      exceeds 30% the discriminator is DEAD and the prereg says close it. This script prints
      that verdict every night so the kill is automatic, not something anyone has to remember.

WHY A SHADOW AND NOT A GATE. The motivating evidence is n=6-8 days in the low-ER cohort, both
findings come from the SAME 22-day window (so they are not independent confirmations), and
2026-08-06 is an outright false negative -- ER 0.29 yet +$1,465, the 3rd best day in the book.
A discriminator with a known false negative and n=8 is a hypothesis, not a filter.

READ-ONLY. Places no orders, edits no params, touches no arm config. $0, stdlib + pandas.
Output: analysis/regime-library/er30-shadow.jsonl (append-only)
"""

from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "analysis" / "regime-library" / "er30-shadow.jsonl"
ER_THRESHOLD = 0.35          # FROZEN by the prereg. Re-tuning on the origin window is forbidden.
G5_KILL_SHARE = 0.30         # >30% of low-ER days green -> discriminator DEAD
# The prereg was frozen on this date. Every day up to and including it is the ORIGIN window
# that GENERATED the hypothesis; it can never count as forward confirmation of itself.
# The first version of this script printed "G1 progress: 29/25 forward days" off the origin
# window and would have declared the gate satisfied on day one -- the exact circularity this
# whole audit exists to stamp out.
PREREG_FROZEN = "2026-08-11"


def er30_by_day() -> dict:
    """{date: ER30} from the widest SPY 5m cache. Closed bars only, no look-ahead."""
    import pandas as pd
    # Pick by DISTINCT-DAY COVERAGE, not row count. Selecting on len(df) picked a dense
    # single-day supplement file and silently cut the population from 29 days to 16 on the
    # first run -- a coverage bug that would have quietly shrunk every future night's sample.
    frames = []
    for f in glob.glob(str(REPO / "backtest/data/spy_5m_*.csv")):
        try:
            d = pd.read_csv(f)
            d["ts"] = pd.to_datetime(d["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
            frames.append(d)
        except Exception:  # noqa: BLE001
            continue
    if not frames:
        return {}
    best = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["timestamp_et"])
    best = best.sort_values("ts")
    best["d"] = best["ts"].dt.strftime("%Y-%m-%d")
    best["hm"] = best["ts"].dt.strftime("%H:%M")
    out: dict = {}
    for day, g in best.groupby("d"):
        w = g[(g["hm"] >= "09:30") & (g["hm"] < "10:00")]
        if len(w) < 3:
            continue
        rng = float(w["high"].max()) - float(w["low"].min())
        if rng <= 0:
            continue
        out[day] = round(abs(float(w.iloc[-1]["close"]) - float(w.iloc[0]["open"])) / rng, 4)
    return out


def engine_pnl_by_day() -> dict:
    p = REPO / "automation" / "state" / "pnl-statement.json"
    if not p.exists():
        return {}
    out: dict = defaultdict(float)
    for rt in json.loads(p.read_text(encoding="utf-8")).get("round_trips", []):
        if rt.get("attribution") == "engine":
            out[rt["date_et"]] += float(rt["pnl"])
    return dict(out)


def ladder_events_by_day() -> dict:
    """S2 from the LIVE ledger: per day, how many positions had the ladder floor arm/fire.
    A pre-TP1 SELL whose runner_stop sits ABOVE entry is a ladder-floor exit."""
    out: dict = defaultdict(lambda: {"armed": 0, "fired": 0})
    for p in glob.glob(str(REPO / "automation/state/fleet/*/decisions.jsonl")):
        for line in open(p, encoding="utf-8"):
            if not line.strip() or "exit_pass" not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            day = str(r.get("ts_et", ""))[:10]
            for e in (r.get("exit_pass") or []):
                if e.get("tp1_filled"):
                    continue
                stop = e.get("runner_stop")
                ent = e.get("entry_premium")
                if stop is not None and ent and float(stop) > float(ent):
                    out[day]["armed"] += 1
                    for a in (e.get("actions") or []):
                        if a.get("kind") in ("SELL_ALL", "SELL_PARTIAL"):
                            out[day]["fired"] += 1
    return dict(out)


def main() -> int:
    er = er30_by_day()
    pnl = engine_pnl_by_day()
    lad = ladder_events_by_day()
    days = sorted(d for d in er if d in pnl)
    if not days:
        print("[regime-shadow] no overlapping days -- nothing to log")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(json.loads(line)["date"])
            except Exception:  # noqa: BLE001
                continue

    wrote = 0
    with OUT.open("a", encoding="utf-8") as fh:
        for d in days:
            if d in seen:
                continue
            row = {"date": d, "er30": er[d], "bucket": "LOW" if er[d] < ER_THRESHOLD else "HIGH",
                   "engine_pnl": round(pnl[d], 2),
                   "ladder_armed": lad.get(d, {}).get("armed", 0),
                   "ladder_fired": lad.get(d, {}).get("fired", 0),
                   "prereg": "REGIME-CONDITIONAL-EXIT-2026-08-11", "shadow_only": True}
            fh.write(json.dumps(row) + "\n")
            wrote += 1

    low = [(d, pnl[d]) for d in days if er[d] < ER_THRESHOLD]
    high = [(d, pnl[d]) for d in days if er[d] >= ER_THRESHOLD]
    low_green = sum(1 for _d, v in low if v > 0)
    share = low_green / len(low) if low else 0.0

    print(f"[regime-shadow] {wrote} new day(s) logged -> {OUT}")
    print(f"  LOW  ER<{ER_THRESHOLD}: n={len(low):>3d} total {sum(v for _d, v in low):>+8.0f} "
          f"green {low_green}/{len(low)}")
    print(f"  HIGH ER>={ER_THRESHOLD}: n={len(high):>3d} total {sum(v for _d, v in high):>+8.0f} "
          f"green {sum(1 for _d, v in high if v > 0)}/{len(high)}")
    print()
    if share > G5_KILL_SHARE:
        print(f"  G5 KILL-WATCH: {share:.0%} of LOW-ER days are GREEN (> {G5_KILL_SHARE:.0%}) "
              f"-> DISCRIMINATOR DEAD per the prereg. Close it; do not tune the threshold.")
    else:
        print(f"  G5 kill-watch: {share:.0%} of LOW-ER days green (kill at >{G5_KILL_SHARE:.0%}) "
              f"-- hypothesis still alive.")
    fwd = [d for d in days if d > PREREG_FROZEN]
    fwd_low = [(d, pnl[d]) for d in fwd if er[d] < ER_THRESHOLD]
    fwd_green = sum(1 for _d, v in fwd_low if v > 0)
    print(f"  ORIGIN window (<= {PREREG_FROZEN}): {len(days) - len(fwd)} days -- generated the "
          f"hypothesis, CANNOT confirm it.")
    print(f"  G1 FORWARD progress: {len(fwd)}/25 days | low-ER forward {len(fwd_low)}/8 needed"
          + (f" | forward low-ER green {fwd_green}/{len(fwd_low)}" if fwd_low else ""))
    if len(fwd) < 25:
        print(f"  -> gate NOT met. {25 - len(fwd)} more forward trading days required.")
    print("  SHADOW ONLY -- nothing armed, no order placed, no config touched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
