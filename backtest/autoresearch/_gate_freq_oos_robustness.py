"""OOS robustness cross-check for the gate-frequency audit's flagged candidates.

The main audit used one chronological split (2025 IS / 2026 OOS) and found 4
gates flagged OVER_RESTRICTIVE on the full window but 0 surviving OOS. This script
stress-tests that "0 shippable" verdict for the strongest candidates under TWO
additional independent partitions, so the rejection doesn't rest on one cut:

  (1) 70/30 chronological split (first 70% of dates IS, last 30% OOS).
  (2) Calendar-half split (H1 2025 vs H2 2025+2026) — different boundary.

For a loosening to be even arguably shippable it must show total_delta>0 AND a
NON-NEGATIVE OOS delta in EVERY partition (sign-stable). We expect all to fail —
this confirms the gates earn their keep / the gains are IS-regime artifacts.

$0, real fills, propose-only.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(REPO / "backtest"))

from autoresearch import runner  # noqa: E402

PARAMS_PATH = REPO / "automation" / "state" / "params.json"
FULL_START, FULL_END = dt.date(2025, 1, 2), dt.date(2026, 5, 29)


def _live() -> dict:
    p = json.loads(PARAMS_PATH.read_text(encoding="utf-8-sig"))
    p["use_real_fills"] = True
    return p


# The flagged candidates (the only ones worth stress-testing).
CANDS = {
    "vix_bear_cap_off": lambda p: p.__setitem__("vix_bear_hard_cap", None),
    "vix_bear_cap_30": lambda p: p.__setitem__("vix_bear_hard_cap", 30.0),
    "body_gate_10": lambda p: p.__setitem__("entry_bar_body_pct_min", 0.10),
    "body_gate_off": lambda p: p.__setitem__("entry_bar_body_pct_min", 0.0),
}

# Independent partitions: (label, is_start, is_end, oos_start, oos_end)
PARTITIONS = [
    ("chrono_70_30", dt.date(2025, 1, 2), dt.date(2026, 1, 31), dt.date(2026, 2, 1), dt.date(2026, 5, 29)),
    ("calendar_half", dt.date(2025, 1, 2), dt.date(2025, 6, 30), dt.date(2025, 7, 1), dt.date(2026, 5, 29)),
]


def _total(params, spy, vix, s, e):
    res, _ = runner.run_with_params(params, s, e, spy, vix)
    return round(sum(float(t.dollar_pnl) for t in res.trades), 2), len(res.trades)


def main() -> int:
    spy, vix = runner.load_data(FULL_START, FULL_END)
    live = _live()
    print("OOS ROBUSTNESS CROSS-CHECK (flagged loosening candidates)")
    print("=" * 88)
    for label, is_s, is_e, oos_s, oos_e in PARTITIONS:
        base_is = _total(live, spy, vix, is_s, is_e)
        base_oos = _total(live, spy, vix, oos_s, oos_e)
        print(f"\n[{label}]  baseline IS={base_is}  OOS={base_oos}")
        print(f"  {'candidate':<20} {'IS_delta':>10} {'OOS_delta':>10}  sign-stable?")
        for cid, mut in CANDS.items():
            p = copy.deepcopy(live)
            mut(p)
            is_t = _total(p, spy, vix, is_s, is_e)
            oos_t = _total(p, spy, vix, oos_s, oos_e)
            is_d = round(is_t[0] - base_is[0], 2)
            oos_d = round(oos_t[0] - base_oos[0], 2)
            stable = "YES" if (is_d > 0 and oos_d >= 0) else "no (reject)"
            print(f"  {cid:<20} ${is_d:>+9.0f} ${oos_d:>+9.0f}  {stable}")
    print("\n" + "=" * 88)
    print("If every candidate shows 'no (reject)' in at least one partition, the main")
    print("audit's '0 shippable loosening' verdict is robust across independent cuts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
