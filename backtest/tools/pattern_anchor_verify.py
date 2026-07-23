"""pattern_anchor_verify.py — the pre-ship + drift contract for pattern-grammar anchors.

Filed 2026-07-23 from a self-audit gap: after ENGULFING-AT-STRUCTURE-TRIGGER shipped
`engulfing_at_swing_shelf` (backtest/lib/patterns/registry.py) claiming to cover two
specific live-tape exhibits J called, the OP-33 falsification pass caught (only by manual
diligence, AFTER shipping) that the rule does NOT actually fire on either anchor bar. The
self-audit swarm named the real gap precisely: "the system lacks a reliable pre-ship
validation step that confirms a rule actually fires on the specific anchor bars J
identified" — this module IS that step, made reusable instead of a one-off manual check.

WHAT IT DOES: given a PatternRule.anchors entry (date/time_et/bias/expected_fire), loads
the real cached bar at that exact timestamp, builds a PatternContext ending at that bar
(never look-ahead — reuses pattern_prescreen.py's own causal bar/level loaders), and runs
the rule's predicate at that bar index. Returns whether it ACTUALLY fired and whether the
fired bias matches the declared anchor bias.

WHY THIS ALSO CATCHES DRIFT, NOT JUST PRE-SHIP MISS: `anchors` records the CURRENT honest
`expected_fire` state (True or False), and test_pattern_anchor_verify.py asserts actual ==
expected for every declared anchor. If a shared primitive changes later (e.g. the
K-bar-cluster follow-up primitive named in the 07-21 anchor's note) and a rule that was
honestly declared NOT to fire starts firing — or, more dangerously, a rule that WAS firing
on its cited anchor quietly stops (a silent regression in a shared primitive) — the guard
goes RED and forces a conscious registry update instead of nobody noticing (the same
"silently degrading production rule" gap the self-audit named for engulfing_at_level's
drift).

Run (from repo root):
  backtest\\.venv\\Scripts\\python.exe backtest\\tools\\pattern_anchor_verify.py
  backtest\\.venv\\Scripts\\python.exe backtest\\tools\\pattern_anchor_verify.py --rule engulfing_at_swing_shelf
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import re

from lib.patterns import PatternContext, REGISTRY, evaluate_rule  # noqa: E402
from lib.patterns.grammar import PatternRule  # noqa: E402
from tools.pattern_prescreen import (  # noqa: E402
    DATA_DIR,
    build_levels_by_date,
    df_to_bars,
    load_master,
    slice_rth,
)


def find_freshest_csv(data_dir: Path = DATA_DIR) -> Path:
    """Deliberately DIFFERENT selection from pattern_prescreen.find_master_csv (which
    picks WIDEST-HISTORY / earliest start — right for full-history frequency stats, but
    wrong here: the widest-history file can lag today by a day or more since it is
    extended less often than the short-window rolling cache). Anchor verification cares
    about covering a SPECIFIC recent date (often today's live tape), so this picks the
    LATEST end date instead, breaking ties toward the widest start range. Same discovery
    that caused the prior fire's manual OP-33 check to hand-pick
    spy_5m_2026-05-19_2026-07-23.csv over the wider-but-stale 2025-01-01 file."""
    pattern = re.compile(r"^spy_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(?:_\w+)?\.csv$")
    candidates = []
    for p in data_dir.glob("spy_5m_*.csv"):
        m = pattern.match(p.name)
        if m:
            candidates.append((m.group(2), m.group(1), p))
    if not candidates:
        raise FileNotFoundError(f"no spy_5m_*.csv under {data_dir}")
    candidates.sort(key=lambda c: (c[0], c[1]))
    latest_end = candidates[-1][0]
    tied = sorted((c for c in candidates if c[0] == latest_end), key=lambda c: c[1])
    return tied[0][2]


def _find_bar_index(bars: tuple, date_str: str, time_et_str: str) -> Optional[int]:
    """Exact match on (date, HH:MM) against each bar's own open_time — no nearest-bar
    fuzzing, so a typo'd anchor timestamp fails LOUD (KeyError-shaped None) rather than
    silently checking the wrong bar."""
    target_date = dt.date.fromisoformat(date_str)
    target_time = dt.time.fromisoformat(time_et_str)
    for i, b in enumerate(bars):
        if b.open_time.date() == target_date and b.open_time.time() == target_time:
            return i
    return None


def _load_context(*, timeframe: str = "5m") -> tuple[PatternContext, tuple]:
    """5m-only (anchor times are quoted in 5m bar-open convention); reuses
    pattern_prescreen.py's causal bar/level loaders so this tool can never silently
    diverge from the C27 prescreen's own data path."""
    csv_path = find_freshest_csv()
    df = load_master(csv_path)
    rth_5m = slice_rth(df)
    bars = df_to_bars(rth_5m, granularity_seconds=300, source=csv_path.name)
    levels_by_date = build_levels_by_date(rth_5m)
    ctx = PatternContext.build(bars, levels_by_date=levels_by_date)
    return ctx, bars


def verify_anchor(rule: PatternRule, anchor: dict, ctx: PatternContext) -> dict:
    """One anchor's verdict. Never raises — a bad timestamp reports as
    bar_found=False rather than crashing a batch run (rail-2 spirit: a broken anchor
    check must never itself become the reason a CI/guard run halts unhelpfully)."""
    idx = _find_bar_index(ctx.bars, anchor["date"], anchor["time_et"])
    if idx is None:
        return {
            "rule": rule.name, **anchor, "bar_found": False, "actual_fired": False,
            "actual_bias": None, "matches_expected": False,
            "detail": f"no bar at {anchor['date']} {anchor['time_et']} in the cached master CSV",
        }
    hit = evaluate_rule(rule, ctx, idx, timeframe="5m")
    actual_fired = hit is not None
    actual_bias = hit.bias if hit is not None else None
    bias_ok = (actual_bias == anchor["bias"]) if actual_fired else True
    matches_expected = (actual_fired == anchor["expected_fire"]) and bias_ok
    return {
        "rule": rule.name, **anchor, "bar_found": True, "actual_fired": actual_fired,
        "actual_bias": actual_bias, "matches_expected": matches_expected,
        "detail": "OK" if matches_expected else (
            f"expected_fire={anchor['expected_fire']} but actual_fired={actual_fired}"
            + ("" if bias_ok else f" (bias mismatch: declared {anchor['bias']}, got {actual_bias})")
        ),
    }


def check_registry_anchors(*, rule_name: Optional[str] = None) -> list[dict]:
    """Every declared anchor across the registry (or just one rule if `rule_name` is
    given). Loads the master CSV/context ONCE regardless of how many anchors are
    checked."""
    rules = [r for r in REGISTRY if r.anchors] if rule_name is None else (
        [r for r in REGISTRY if r.name == rule_name]
    )
    if not rules:
        return []
    ctx, _bars = _load_context()
    results = []
    for rule in rules:
        for anchor in rule.anchors:
            results.append(verify_anchor(rule, anchor, ctx))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rule", default=None, help="check only this rule's anchors")
    args = ap.parse_args()
    results = check_registry_anchors(rule_name=args.rule)
    if not results:
        print("no anchors declared" + (f" for rule {args.rule!r}" if args.rule else " in registry"))
        return 0
    bad = 0
    for r in results:
        ok = "OK" if r["matches_expected"] else "MISMATCH"
        if not r["matches_expected"]:
            bad += 1
        print(f"[{ok}] {r['rule']} @ {r['date']} {r['time_et']} ({r['bias']}) -- {r['detail']}")
    print(f"\n{len(results) - bad}/{len(results)} anchors match their declared expected_fire state")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
