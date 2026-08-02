"""risky1_lane_composition_check.py -- instrumented dry-run proof of how risky-1's TWO
back-to-back 2026-07-31/08-01 experiments actually compose, using the REAL
fleet_executor.plan_all + build_shared_signal.build_from_rows (not a reading of the code,
not a repeat of a prior claim -- same technique the score-ladder/full-send lanes themselves
used to prove routing, "score 7 routes full-send, score 11 routes the normal lane").

THE TWO EXPERIMENTS ON ONE ARM
-------------------------------
  (a) FULL-SEND (commit e28d210c, 2026-07-31 16:21): risky-1's gate_override was REPLACED
      (not merged) with {"full_send": true} -- min_triggers/require_confluence_or_sequence
      were DELETED, not layered under. Prices PROBE_STRIKE_TIERS (ATM under $10K) via
      _full_send_plan, fires ONLY when the normal lane produces zero ENTER this tick, and
      hard-clamps qty to params.min_contracts on EVERY entry this arm makes (both lanes --
      see _apply_full_send_min_sizing, keyed off gate_override.full_send, not lane).
  (b) FLEET-STRIKE-TIER-ATM-EXTENSION (commit 43bb979d, 2026-07-31 23:13): accounts.json
      params_patch.strike_tier_table='bold_core' repoints risky-1's NORMAL lane
      (_tiers_for_arm) from V15_BOLD_TIERS (OTM-3 under $2K) to V15_BOLD_CORE_TIERS
      (ATM under $2K).

CORRECTION OF RECORD (why this script exists): the 2026-08-02 day+1 audit
(analysis/recommendations/fleet-strike-tier-atm-2026-08-02.md) described risky-1's normal
lane as "tight-gated (min_triggers=2 + confluence/sequence required)" and called it "the
primary [path]". That is WRONG on the CURRENT accounts.json -- (a) REPLACED that
gate_override, it did not layer on top of it (git show e28d210c -- accounts.json). This was
ALREADY independently caught and recorded the SAME night, hours before that audit ran:
queue.md's FLEET-PARITY-TESTS-READ-LIVE-STATE entry (commit dea5b2e2, 2026-08-01 ~02:00 ET)
rewrote a stale test that "still asserted the pre-conversion HOLD-on-non-elite behavior"
with the explicit note "risky-1 ... its normal lane is now UNGATED same as risky-3." The
audit's claim conflicts with a fix already on record in the SAME file tree.
Likely source of the audit's error: accounts.json's own top-level `grid.map` metadata
block still reads `"risky-1": "risky x tight"` (never updated when full-send armed) even
though the arm's OWN `cell` field already says `"risky x FULL-SEND"` -- a stale doc, not a
live config value. Fixed alongside this script.

WHAT THIS SCRIPT PROVES (all four points verified by REAL execution below, not inferred):
  1. risky-1's normal lane is UNGATED (_gate_check has nothing left to check -- no
     min_triggers, no require_confluence_or_sequence -- once gate_override is only
     {"full_send": true}). A plain passing signal enters via the NORMAL lane, not full-send.
  2. At risky-1's CURRENT equity (<$2,000), V15_BOLD_CORE_TIERS (normal lane) and
     PROBE_STRIKE_TIERS (full-send lane) happen to agree exactly (both ATM) -- but this is
     an EQUITY-CONTINGENT COINCIDENCE, not a structural guarantee: both tables' $2K-10K
     bracket differs (bold_core -> OTM-2, PROBE_STRIKE_TIERS -> stays ATM), so a fill above
     $2,000 prices 2 STRIKES apart depending on which lane produced it.
  3. The two lanes are POPULATION-DISJOINT by construction (passed_full_send requires
     `action in FULL_SEND_ALLOWED_VERDICTS`, mutually exclusive with a normal "passed"
     tick) AND separately TAGGED (EntryPlan.reason: "{strategy} {side} ({quality})" for
     normal vs "FULL_SEND cohort=..." for full-send) -- the SAME tag setup/scripts/
     full_send_vs_gated.py's `_lane()` already parses. Attribution between the two
     experiments is NOT lost at the per-fill level.
  4. ADDITIONAL FINDING (adjacent, flagged not fixed here): risky-3's own designed-for-this
     rescue mechanism (gate_params.hard_skip_verdicts=[], GATE-TIERS-IMPLEMENT 2026-07-23,
     meant to let it trade through require_bearish_fill_bar) is NEVER CONSULTED by the
     live path -- fleet_live.py calls ONLY plan_all (FIX2/_plan_from_strategies), which
     reads signal['strategies'] (built ONCE, uniformly, with no per-arm hard-skip rescue);
     _effective_passed (the function that reads hard_skip_verdicts) is only ever called
     from plan_entry, which production does not call. Verified empirically below: risky-3
     stays HELD on a SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY tick even at a score comfortably
     above its own scoring peak. This makes risky-1's full-send lane the ONLY fleet
     mechanism currently capable of trading ANY cohort-vetoed tick, on any arm --
     independent confirmation this lane is not redundant "learning rate" cosmetics.

$0, offline, read-only. Calls ONLY existing pure functions (build_shared_signal.
build_from_rows, fleet_executor.plan_all) -- writes no state, places no orders, never
touches accounts.json/params.json/heartbeat_core.py (all read-only).

Run: backtest/.venv/Scripts/python.exe setup/scripts/risky1_lane_composition_check.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
for _p in (str(FLEET), str(REPO / "backtest")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_shared_signal as bss  # noqa: E402
import fleet_executor as fx  # noqa: E402

ACCOUNTS_PATH = FLEET / "accounts.json"
BOLD_PARAMS_PATH = REPO / "automation" / "state" / "aggressive" / "params.json"

# Live-verified 2026-08-02 (analysis/recommendations/fleet-strike-tier-atm-2026-08-02.md) --
# this script has no live balance feed of its own for the custom_rest/fleet_rest accounts
# (only safe-2/bold-2 are MCP-wired); re-verify against that audit or a fresh fleet balance
# pull before trusting this number more than a day or two stale.
RISKY1_LIVE_EQUITY = 1756.87
ABOVE_2K_EQUITY = 2500.0  # representative equity past the strike-table boundary


def _accounts() -> dict:
    return json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))


def _bold_params() -> dict:
    return json.loads(BOLD_PARAMS_PATH.read_text(encoding="utf-8"))


def _arm(accounts: dict, arm_id: str) -> dict:
    for a in accounts["arms"]:
        if a.get("id") == arm_id:
            return a
    raise KeyError(arm_id)


def _row(*, verdict: str, side: str, setup: str, score: int, trig: Optional[str],
         level: Optional[float], spy: float = 745.0, vix: float = 16.4) -> dict:
    """A REAL-SHAPED core-decisions row (same fields _map_core_row/_vetoed_core_row in
    test_full_send_arm.py use)."""
    return {
        "ts_et": "2026-08-01T12:15:02-04:00", "account": "bold", "spy": spy,
        "ribbon": "BEAR" if side == "P" else "BULL", "spread_cents": 12, "vix": vix,
        "htf_15m": "BEAR" if side == "P" else "BULL",
        "verdict": verdict, "action": verdict, "side": side, "setup": setup,
        "bear_score": score if side == "P" else 2,
        "bull_score": score if side == "C" else 2,
        "triggers": [trig] if trig else [],
        "trigger_level_exact": level,
        "bull_reclaim_level_raw": level if side == "C" else None,
        "bear_rejection_level_raw": level if side == "P" else None,
    }


def _signal(row: dict) -> dict:
    """Build the live-shaped shared signal via the REAL producer, exactly like
    test_full_send_arm.py's _signal_from -- default flags (scoring_peak/emit_strategies/
    full_send all None) resolve to the LIVE production defaults (SCORING_PEAK_LIVE=True,
    EMIT_STRATEGIES=True, FULL_SEND_LIVE=True), so this dry-run exercises the SAME code
    path fleet_live.py drives, not a hand-relaxed test-only shape."""
    mapped = bss._map_core_row(row)
    now = dt.datetime(2026, 8, 1, 12, 15, tzinfo=bss.ET)
    return bss.build_from_rows(mapped, now, bold_row=mapped, probe_row=mapped,
                               run_vwap=False, write=False)


def enter_plans(accounts: dict, arm_id: str, sig: dict, equity: float, params: dict):
    arm = _arm(accounts, arm_id)
    plans = fx.plan_all(arm, sig, equity, params, probe_cfg=accounts.get("probe_arm"))
    return [p for p in plans if p.action == "ENTER"], plans


def _lane(reason: str) -> str:
    """Same prefix convention as setup/scripts/full_send_vs_gated.py's _lane()."""
    for needle, tag in (("FULL_SEND", "FULL_SEND"), ("PROBE_ARM", "PROBE"),
                        ("SCORE_LADDER", "LADDER")):
        if str(reason).startswith(needle):
            return tag
    return "normal"


# --- SCENARIOS -----------------------------------------------------------------------------
SCENARIOS = {
    "1_NORMAL_PASS": _row(
        verdict="ENTER_BEAR", side="P", setup="BEARISH_REJECTION_RIDE_THE_RIBBON",
        score=9, trig="level_rejection", level=743.0),
    "2_COHORT_VETO_BELOW_PEAK": _row(
        verdict="SKIP_ELITE_BULL_LEVEL_RECLAIM", side="C",
        setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
        score=7, trig="confluence", level=743.25),  # score BELOW BULL_PEAK_THRESHOLD(9)
    "3_HARD_SKIP_FILL_BAR_ABOVE_PEAK": _row(
        verdict="SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY", side="P",
        setup="BEARISH_REJECTION_RIDE_THE_RIBBON",
        score=9, trig="level_rejection", level=743.0),  # score ABOVE BEAR_PEAK_THRESHOLD(8)
}


def run() -> dict:
    """Pure compute -- returns the full result dict; main() prints it. Kept separate so a
    guard test can assert on structured output instead of scraping stdout."""
    accounts = _accounts()
    params = _bold_params()
    risky1 = _arm(accounts, "risky-1")
    risky3 = _arm(accounts, "risky-3")

    out: dict = {
        "risky1_gate_override": risky1.get("gate_override"),
        "risky1_gate_params": risky1.get("gate_params"),
        "risky3_gate_override": risky3.get("gate_override"),
        "risky3_gate_params": risky3.get("gate_params"),
        "grid_map_risky1": (accounts.get("grid") or {}).get("map", {}).get("risky-1"),
        "risky1_cell_field": risky1.get("cell"),
        "scenarios": {},
        "strike_table_agreement_by_equity": [],
    }

    for eq_label, equity in (("live_lt_2k", RISKY1_LIVE_EQUITY), ("above_2k", ABOVE_2K_EQUITY)):
        for name, row in SCENARIOS.items():
            sig = _signal(row)
            r1_enters, r1_all = enter_plans(accounts, "risky-1", sig, equity, params)
            r3_enters, r3_all = enter_plans(accounts, "risky-3", sig, equity, params)
            key = f"{name}@{eq_label}"
            out["scenarios"][key] = {
                "verdict": row["verdict"], "side": row["side"], "equity": equity,
                "risky1": ({"action": "ENTER", "lane": _lane(r1_enters[0].reason),
                            "strike": r1_enters[0].strike, "qty": r1_enters[0].qty,
                            "reason": r1_enters[0].reason} if r1_enters else {"action": "HOLD"}),
                "risky3": ({"action": "ENTER", "lane": _lane(r3_enters[0].reason),
                            "strike": r3_enters[0].strike, "qty": r3_enters[0].qty,
                            "reason": r3_enters[0].reason} if r3_enters else {"action": "HOLD"}),
            }

    # structural qty isolation: full_send's clamp (deterministic) vs today's recency-RED
    # clamp (live, time-varying, applies to BOTH arms and would confound a naive qty
    # comparison if not isolated).
    params_no_recency = dict(params)
    params_no_recency["recency_min_size_enabled"] = False
    sig = _signal(SCENARIOS["1_NORMAL_PASS"])
    for label, p in (("recency_on_live_default", params), ("recency_off_isolated", params_no_recency)):
        r1e, _ = enter_plans(accounts, "risky-1", sig, ABOVE_2K_EQUITY, p)
        r3e, _ = enter_plans(accounts, "risky-3", sig, ABOVE_2K_EQUITY, p)
        out.setdefault("qty_isolation", {})[label] = {
            "risky1_qty": r1e[0].qty if r1e else None, "risky1_reason": r1e[0].reason if r1e else None,
            "risky3_qty": r3e[0].qty if r3e else None, "risky3_reason": r3e[0].reason if r3e else None,
        }

    for eq in (1756.87, 1999.99, 2000.0, 2500.0, 9999.0):
        bc = fx.strike_selection.pick_tier(eq, fx.strike_selection.V15_BOLD_CORE_TIERS)
        ps = fx.strike_selection.pick_tier(eq, fx.PROBE_STRIKE_TIERS)
        out["strike_table_agreement_by_equity"].append({
            "equity": eq, "bold_core_offset": bc.strike_offset, "bold_core_label": bc.label,
            "probe_offset": ps.strike_offset, "probe_label": ps.label,
            "agree": bc.strike_offset == ps.strike_offset,
        })
    return out


def main() -> int:
    r = run()
    print("=" * 100)
    print("risky-1 LANE COMPOSITION CHECK -- REAL fleet_executor.plan_all + "
          "build_shared_signal.build_from_rows, production-default flags")
    print("=" * 100)
    print(f"\nrisky-1 gate_override (verbatim): {r['risky1_gate_override']}")
    print(f"risky-1 gate_params:              {r['risky1_gate_params']}")
    print(f"risky-3 gate_override (verbatim): {r['risky3_gate_override']}")
    print(f"risky-3 gate_params:              {r['risky3_gate_params']}")
    print(f"\nSTALE DOC CHECK: accounts.json grid.map['risky-1'] = {r['grid_map_risky1']!r}"
          f"   (arm's own 'cell' field = {r['risky1_cell_field']!r})")

    print("\n" + "-" * 100)
    print("SCENARIO RESULTS")
    print("-" * 100)
    for key, s in r["scenarios"].items():
        print(f"\n[{key}]  verdict={s['verdict']}  side={s['side']}  equity=${s['equity']:,.2f}")
        for arm_id in ("risky1", "risky3"):
            d = s[arm_id]
            if d["action"] == "ENTER":
                print(f"  {arm_id}: ENTER lane={d['lane']:10} strike={d['strike']:>4} "
                      f"qty={d['qty']}  reason={d['reason']}")
            else:
                print(f"  {arm_id}: HOLD")

    print("\n" + "-" * 100)
    print("QTY ISOLATION (full_send's structural clamp vs today's live recency-RED clamp)")
    print("-" * 100)
    for label, d in r["qty_isolation"].items():
        print(f"  [{label}] risky-1 qty={d['risky1_qty']} ({d['risky1_reason']})")
        print(f"  [{label}] risky-3 qty={d['risky3_qty']} ({d['risky3_reason']})")

    print("\n" + "=" * 100)
    print("STRIKE-TABLE AGREEMENT IS EQUITY-CONTINGENT, NOT STRUCTURAL")
    print("=" * 100)
    for row in r["strike_table_agreement_by_equity"]:
        tag = "SAME" if row["agree"] else "DIVERGE"
        print(f"  equity=${row['equity']:>10,.2f}  bold_core(normal)={row['bold_core_label']:12} "
              f"offset={row['bold_core_offset']:+d}   probe(full-send)={row['probe_label']:12} "
              f"offset={row['probe_offset']:+d}   -> {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
