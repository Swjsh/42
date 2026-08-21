"""G2 trendline-bypass A/B — RE-RUN on data through 2026-08-20.

WHY RE-RUN A SETTLED STUDY
--------------------------
The 2026-08-01 run returned NEITHER_SHIPS, but read the reason, not the verdict:

  ARM_EXTEND  full $-2,061.65 | recent $+1,616.15 | G1 **UNDETERMINED** -> NULL
  ARM_REMOVE  full $+2,693.55 | recent   $+279.60 | G4 FAIL            -> NULL

G1 is the PRIMARY gate (J's recency-over-aggregate directive) and it did not
FAIL for ARM_EXTEND — it was **UNDETERMINED**, because 3 of the 25 recent days
(2026-07-24, 07-27, 07-30) had ZERO cached OPRA contracts. The pre-reg counts
UNDETERMINED as NOT PASS, correctly and conservatively. But an unmeasurable gate
is a data problem, not a verdict about the edge.

Two things changed since:
  1. OPRA has partially backfilled (07-27 and 07-30 now have cached contracts).
  2. 20 more trading days exist (2026-08-01..2026-08-20), so the recent-25 window
     rolls forward to ~2026-07-16..2026-08-20 and mostly leaves the gap behind.

WHAT THIS FILE CHANGES — AND NOTHING ELSE
  * the data window (FULL_END, and the NEW_SPY/NEW_VIX tail files)
  * the output paths (dated 2026-08-20)

WHAT IT DELIBERATELY DOES NOT CHANGE
  * the five frozen gates, their rules, or which one is primary
  * the two arms or their scope values
  * any threshold, filter, or scoring logic
  * the reporting rule: ALL cells reported, both arms, both windows, pass or
    fail, no cherry-picking, synthetic P&L disclosed and excluded

It imports the original runner and overrides only those module constants, so the
measurement code itself is byte-identical. If this re-run makes an arm look good,
that must be because the DATA changed, never because the harness did.

MOTIVATION (2026-08-20 session): on a cleanly-called bear trend day the engine
traded only 12:56-15:40. Filter 8 needs VIX > 17.30 AND rising; VIX sat
15.49-16.13 all session, so a normal bear entry was structurally impossible and
the trendline bypass was the ONLY road in. Meanwhile the raw detectors fired
level_rejection 108x and confluence 67x — the STRONGER triggers, which get the
FULL filter set and therefore could never convert. That is exactly the inverted
priority this pre-reg was written to test.

USAGE
  backtest/.venv/Scripts/python.exe backtest/tools/g2_trendline_bypass_ab_2026_08_20.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))
sys.path.insert(0, str(ROOT / "backtest" / "tools"))

import g2_trendline_bypass_ab_2026_08_01 as g2   # noqa: E402  the frozen harness

DATA = ROOT / "backtest" / "data"

# --- the ONLY overrides: data window + output paths -------------------------
g2.NEW_SPY = DATA / "spy_5m_2026-05-19_2026-08-20.csv"
g2.NEW_VIX = DATA / "vix_5m_2026-05-19_2026-08-20.csv"
g2.FULL_END = dt.date(2026, 8, 20)
g2.OUT_JSON = ROOT / "analysis" / "recommendations" / "g2-trendline-bypass-2026-08-20.json"
g2.OUT_MD = ROOT / "analysis" / "recommendations" / "g2-trendline-bypass-2026-08-20.md"


def main() -> int:
    for name, want in (("RECENT_TRADING_DAYS", 25),
                       ("RUNNER_NO_REGRESSION_FLOOR", 0.95),
                       ("ARMS", ("ARM_EXTEND", "ARM_REMOVE"))):
        got = getattr(g2, name)
        assert got == want, "frozen constant %s was mutated: %r != %r" % (name, got, want)
    assert g2.SCOPE_FOR_ARM == {"ARM_EXTEND": "all_level_tied", "ARM_REMOVE": "none"}, \
        "arm scopes were mutated"
    print("[re-run] gates/arms verified unchanged; window -> %s, tail -> %s"
          % (g2.FULL_END, g2.NEW_SPY.name))
    return g2.main()


if __name__ == "__main__":
    raise SystemExit(main())
