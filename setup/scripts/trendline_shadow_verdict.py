"""trendline_shadow_verdict.py -- recompute the trendline shadow lane's statistical verdict
on the CURRENT ledger, using the same method as the 2026-08-20 verdict, and freeze a
pre-registered numeric promotion bar for the lane.

WHY THIS EXISTS (overnight queue item TRENDLINE-SHADOW-VERDICT-RECOMPUTE, filed 2026-08-29
Fable full review): the 08-20 verdict ("65 sessions, n=1332: +0.041 SPY pts/trade, ABOVE a
random-entry null, session-clustered 95% CI [-0.039, +0.124], top 3 sessions supply >100% of
all profit" -- commit ed8e78bd) was a ONE-OFF computation done at ship time and never saved as
a reusable script. analysis/trendlines/shadow-ledger.jsonl had grown to 4,786 rows through
08-28 (now 4,959 through 09-02, 73 sessions) with the verdict never re-stamped -- SHADOW.md had
no row for this lane at all (obsidian_vault_sync.py's build_preregs_board never wired one in
despite the lane accruing since 08-20), so "what does the trendline shadow lane show" had no
answer anywhere on the shared surface.

METHOD, reproduced not reinvented:
  1. WHOLE-SAMPLE STATS -- trendline_shadow.baseline()'s own sessions_total / all_trades /
     all_points_per_trade / top3_share_of_total fields (added in the SAME commit that produced
     the 08-20 verdict, ed8e78bd) are already computed over the FULL ledger regardless of the
     `sessions`/`end_date` window passed in -- calling it with any window still returns the
     correct whole-sample numbers. This is the exact function the 08-20 numbers came from.
  2. SESSION-CLUSTERED 95% CI -- no dedicated bootstrap helper existed in trendline_shadow.py
     on 2026-08-20 (the repo's now-canonical day-level bootstrap,
     setup/scripts/lib/scorecard_guards.py::day_level_bootstrap, was built a week later,
     2026-08-27). Rather than inventing a second bootstrap shape, this reuses that SAME
     day-level (resample whole SESSIONS with replacement, pool their trades) algorithm --
     the one concept this repo already treats as canonical for "session-clustered" -- applied
     to trendline theo_points instead of dollar pnl, seeded (1337) and at the SAME 95% level
     the original verdict reported. No new knobs: n_boot/seed/ci_level all take
     scorecard_guards' own defaults except ci_level, which is set to 0.95 to match the ORIGINAL
     verdict's stated level (scorecard_guards defaults to 0.90 for its own callers).

Writes:
  analysis/trendlines/shadow-verdict.json -- APPENDS a dated entry to `history`; never
  overwrites a prior entry (this file itself is the "source the vault generator reads" queue.md
  asked to update, wired into obsidian_vault_sync.py::build_preregs_board in the same change).

Read-only w.r.t. the ledger and every other file. Never arms, never places an order.

Run: backtest/.venv/Scripts/python.exe setup/scripts/trendline_shadow_verdict.py
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "lib"))

import trendline_shadow as T  # noqa: E402

LEDGER = REPO / "analysis" / "trendlines" / "shadow-ledger.jsonl"
OUT = REPO / "analysis" / "trendlines" / "shadow-verdict.json"

# Frozen with THIS recompute (queue.md: "no pre-registered numeric promotion bar was found for
# this lane -- freeze one"). Never loosened without a fresh dated entry recording why.
PROMOTION_BAR = {
    "ci_clears_zero": "session-clustered 95% CI lower bound (pts/trade) > 0",
    "concentration_resolved": "top-3-session share of total profit < 0.50 (50%)",
    "n_sessions_min": 60,
    "no_new_knobs": "promotion criteria evaluated on the EXISTING shadow ledger/method only -- "
                     "no new detector parameter, gate, or entry rule may be introduced to clear it",
}

# Same day-level/session-clustered bootstrap concept as
# setup/scripts/lib/scorecard_guards.py::day_level_bootstrap (built 2026-08-27, a week after
# the original 08-20 verdict), applied to POINTS-PER-TRADE MEAN rather than total pnl/PF --
# the shape the trendline verdict has always reported. Defaults match that module's own
# (n_boot=2000, seed=1337) except ci_level, set to 0.95 to match the original verdict's stated
# level (that module defaults to 0.90 for its own callers).
DEFAULT_N_BOOT = 2000
DEFAULT_SEED = 1337
DEFAULT_CI = 0.95


def _session_clustered_mean_ci(
    day_points: dict, n_boot: int = DEFAULT_N_BOOT, seed: int = DEFAULT_SEED,
    ci_level: float = DEFAULT_CI,
) -> dict:
    """Block-bootstrap by SESSION (never by trade): resample sessions with replacement, pool
    their theo_points, take the mean. Returns the CI on the MEAN pts/trade, matching the
    "+X.XXX pts/trade" shape this lane has always reported (scorecard_guards' own helper
    reports total pnl/PF, a different shape -- this is the trendline-lane-specific variant of
    the SAME resampling idea, not a different method)."""
    dates = sorted(day_points.keys())
    n_days = len(dates)
    result = {
        "n_sessions": n_days, "n_boot": n_boot, "seed": seed, "ci_level": ci_level,
        "mean": None, "ci_low": None, "ci_high": None, "insufficient_sessions": n_days < 2,
    }
    if n_days < 2:
        return result
    rng = random.Random(seed)
    day_lists = [day_points[d] for d in dates]
    means = []
    for _ in range(n_boot):
        picks = [day_lists[rng.randrange(n_days)] for _ in range(n_days)]
        pooled = [p for day in picks for p in day]
        if pooled:
            means.append(sum(pooled) / len(pooled))
    means.sort()
    n = len(means)
    lo_idx = int((1 - ci_level) / 2 * n)
    hi_idx = min(int((1 + ci_level) / 2 * n) - 1, n - 1)
    result["mean"] = round(sum(means) / n, 4) if n else None
    result["ci_low"] = round(means[lo_idx], 4) if n else None
    result["ci_high"] = round(means[hi_idx], 4) if n else None
    return result


def _load_day_points(ledger: Path = LEDGER) -> dict:
    by_day: dict = {}
    try:
        for line in ledger.open(encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("theo_points") is not None and r.get("date"):
                by_day.setdefault(r["date"], []).append(r["theo_points"])
    except OSError:
        return {}
    return by_day


def compute_verdict(end_date: str, ledger: Path = LEDGER) -> dict[str, Any]:
    bl = T.baseline(end_date, sessions=5, path=ledger)
    if not bl.get("ok"):
        return {"ok": False, "reason": bl.get("reason", "baseline unavailable")}
    day_points = _load_day_points(ledger)
    ci = _session_clustered_mean_ci(day_points)
    return {
        "ok": True,
        "date": end_date,
        "method": "trendline_shadow.baseline() whole-sample stats + session-clustered "
                  "(day-level) bootstrap CI on mean pts/trade, seed=1337, n_boot=2000, "
                  "ci_level=0.95 -- same concept as scorecard_guards.day_level_bootstrap, "
                  "applied to trendline theo_points.",
        "sessions_total": bl["sessions_total"],
        "n_trades": bl["all_trades"],
        "points_per_trade": bl["all_points_per_trade"],
        "win_rate": bl["all_wr"],
        "sessions_positive": bl["sessions_positive"],
        "top3_session_share_of_profit": bl["top3_share_of_total"],
        "session_clustered_ci_95": [ci["ci_low"], ci["ci_high"]],
        "ci_clears_zero": (ci["ci_low"] is not None and ci["ci_low"] > 0),
        "above_zero": bl["all_points_per_trade"] > 0,
    }


ORIGINAL_VERDICT_2026_08_20 = {
    "ok": True,
    "date": "2026-08-20",
    "method": "one-off computation at ship time (commit ed8e78bd) -- never saved as a script; "
              "reconstructed here from that commit's own message for the historical record.",
    "sessions_total": 65,
    "n_trades": 1332,
    "points_per_trade": 0.041,
    "session_clustered_ci_95": [-0.039, 0.124],
    "ci_clears_zero": False,
    "top3_session_share_of_profit": None,  # reported qualitatively as ">100%", exact fraction
                                            # not preserved in the commit message
    "top3_gt_100pct_of_profit": True,
    "above_zero": True,
}


def main(argv: Optional[list] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", default=None, help="end date (default: latest date in the ledger)")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    end_date = a.date
    if end_date is None:
        day_points = _load_day_points()
        end_date = max(day_points) if day_points else None
    if end_date is None:
        print("[trendline_shadow_verdict] no dated rows in the ledger -- nothing to compute")
        return 1

    verdict = compute_verdict(end_date)
    out_path = Path(a.out)
    doc = {"_meta": {"promotion_bar": PROMOTION_BAR,
                      "original_verdict_note": "the 2026-08-20 verdict is preserved as "
                      "history[0] for comparison; every later entry is a real recompute on "
                      "the then-current ledger via compute_verdict() in this file."},
           "history": [ORIGINAL_VERDICT_2026_08_20]}
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if existing.get("history"):
                doc["history"] = existing["history"]
        except (OSError, ValueError):
            pass
    # Idempotent per date: replace an existing entry for the SAME date rather than duplicating.
    doc["history"] = [h for h in doc["history"] if h.get("date") != verdict.get("date")]
    doc["history"].append(verdict)
    doc["latest"] = verdict
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    print(f"[trendline_shadow_verdict] {verdict['sessions_total']} sessions, "
          f"n={verdict['n_trades']}: {verdict['points_per_trade']:+.4f} pts/trade, "
          f"CI95 {verdict['session_clustered_ci_95']}, "
          f"top3={verdict['top3_session_share_of_profit']:.1%} of profit -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
