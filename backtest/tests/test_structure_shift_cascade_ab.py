"""Guards backtest/tools/structure_shift_cascade_ab.py -- the pre-reg #2 CONTROL-vs-
TREATMENT full-engine replay (analysis/recommendations/prereg-structure-shift-cascade-
2026-07-28.json, commit 58bb61fa).

Two classes:
  TestBaselineAnchorReproduction  -- SLOW (real ~80s full 18mo+ backtest). Marked `slow`
      per backtest/pytest.ini's convention (excluded from the per-edit fast hook, runs
      nightly/on-demand). Proves the tool's CONTROL path reproduces the stored
      engine-fullhist-replay-2026-07-23 scorecard (n=190, $5,064.75) as a strict prefix of
      the extended (thru 2026-07-27) window -- the same "must reproduce or ABORT" gate the
      tool itself enforces before running the treatment.
  TestSyntheticTreatmentCase       -- FAST, no OPRA/backtest needed. Exercises this tool's
      OWN plumbing (`bar_ctx_from_orch_ctx` + `score_candidate`, i.e. the actual
      engine_cli.decide_payload route the module docstring documents) against the pinned
      2026-07-27 09:40 incident fixture (test_why_not_provenance.py's `_ctx("BULL")` --
      bear_score=9, blockers=[5], the exact "blocked-by-exactly-the-lagging-gate" class this
      A/B targets) -- proving the flag OFF stays blocked (verdict HOLD) and flag ON flips to
      ENTER_BEAR, WITHOUT mutating the ribbon (confirms an OR-alternative, not a swap).

RED-PROOFED 2026-07-28: ran with `assert v_on["verdict"] != "ENTER_BEAR"` (inverted) on
`test_blockers5_candidate_flips_to_enter_bear_under_flag_via_own_plumbing` -- confirmed FAIL
(`AssertionError: assert 'ENTER_BEAR' != 'ENTER_BEAR'`) -- then reverted to the correct
assertion below (`git diff` on this file is the correct, final version only).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "backtest" / "tools"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (str(REPO), str(REPO / "backtest"), str(TOOLS), str(REPO / "backtest" / "tests"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

import structure_shift_cascade_ab as ssc  # noqa: E402
from test_why_not_provenance import _ctx as _incident_0727_ctx  # noqa: E402


# --------------------------------------------------------------------- (a) baseline anchor


class TestBaselineAnchorReproduction:
    @pytest.mark.slow
    def test_control_prefix_reproduces_stored_scorecard(self):
        """The <=2026-07-22 prefix of the tool's own extended-window CONTROL run must
        reproduce n=190 trades / $5,064.75 -- the exact same check
        structure_shift_cascade_ab.main() performs before it will run the treatment at all
        (fail-closed). This test calls the tool's OWN functions (run_control_with_
        candidate_capture + derive_control_rows), not a reimplementation."""
        import engine_fullhist_replay as efr

        r, _captured_kw, _bear_candidates, spy_df, _g5_scan = ssc.run_control_with_candidate_capture()
        ribbon_lookup = efr.build_ribbon_lookup(spy_df)
        correct_shape = ssc.fleet_strategies.by_name("ribbon_ride").exit.to_dict()
        control_rows = ssc.derive_control_rows(r, spy_df, ribbon_lookup, correct_shape)

        prefix = [row for row in control_rows if dt.date.fromisoformat(row["date"]) <= efr.FULL_END]
        prefix_total = round(sum(row["dollar_pnl"] for row in prefix), 2)

        assert len(prefix) == 190, (
            f"expected 190 trades in the <=2026-07-22 prefix (stored engine-fullhist-"
            f"replay-2026-07-23 scorecard), got {len(prefix)}"
        )
        assert abs(prefix_total - 5064.75) <= 1.00, (
            f"expected prefix total ~$5,064.75, got ${prefix_total:+.2f}"
        )


# ----------------------------------------------------------------- (b) synthetic treatment


class TestSyntheticTreatmentCase:
    def test_blockers5_candidate_flips_to_enter_bear_under_flag_via_own_plumbing(self):
        ctx = _incident_0727_ctx("BULL")
        assert ctx.ribbon_now.stack == "BULL"  # sanity: the fixture's own known shape

        bar_ctx = ssc.bar_ctx_from_orch_ctx(ctx)
        # BAR_CTX_WINDOW=200 >> ctx.bar_idx+1=43 bars-thru-trigger for this fixture -- no
        # window-START truncation occurs, so the local index must equal the original
        # bar_idx exactly. prior_bars is INTENTIONALLY bar_idx+1 long (bars 0..bar_idx
        # inclusive) -- the fixture's 44th row (index 43, AFTER the trigger) must NOT
        # appear, or the payload would leak a look-ahead bar. This catches both an
        # off-by-one in the window/local-index rebase AND an accidental look-ahead leak.
        assert bar_ctx["bar_idx"] == ctx.bar_idx == 42
        assert len(bar_ctx["prior_bars"]) == ctx.bar_idx + 1 == 43

        v_off, v_on = ssc.score_candidate(bar_ctx, {}, {})

        # ---- flag OFF: byte-identical to the pinned incident (test_why_not_provenance.py) ----
        assert v_off["bear_score"] == 9
        assert v_off["bear_blockers"] == [5]
        assert v_off["verdict"] == "HOLD"

        # ---- flag ON: filter 5 cleared via the OR-alternative, bear now passes + all gates ----
        assert v_on["bear_score"] == 10
        assert v_on["bear_blockers"] == []
        assert v_on["verdict"] == "ENTER_BEAR"
        assert v_on["rejection_level"] == 744.9

        # The ribbon itself was NEVER mutated -- confirms this is an OR-alternative to the
        # ribbon check, not a swap of the underlying setup.
        assert ctx.ribbon_now.stack == "BULL"

    def test_qty_resolution_applies_min_premium_gate_and_risk_cap(self):
        # LEVEL/ELITE/SUPER tiers below the min-premium floor are skipped entirely.
        qty, skip = ssc.resolve_candidate_qty("ELITE", 0.10)
        assert qty is None and skip == "SKIP_MIN_PREMIUM"

        # ELITE base qty=10 costs 10*$1.00*100=$1,000 > the $524.03 risk cap
        # ($1,746.75 * 0.30) -> scaled down to floor(524.03/100)=5.
        qty, skip = ssc.resolve_candidate_qty("ELITE", 1.00)
        assert skip is None
        assert qty == 5

        # TRENDLINE is not premium-gated; a cheap fill keeps the base qty=3 (well under cap).
        qty, skip = ssc.resolve_candidate_qty("TRENDLINE", 0.10)
        assert skip is None and qty == 3
