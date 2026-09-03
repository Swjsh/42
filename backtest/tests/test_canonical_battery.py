"""Guard tests for backtest/lib/canonical_battery.py (BATTERY-LOGIC-DUPLICATED-ACROSS-TOOLS
fold, 2026-09-03).

Three things pinned here:
  1. BYTE-IDENTICAL REGRESSION -- the six relocated functions (one_sample_p, bh_fdr,
     drop_top_n, cohort_metrics, is_oos_split, g_battery) produce the EXACT SAME output on a
     fixed synthetic fixture as they did before the port (captured from
     backtest/tools/gate_revalidation_ab.py's pre-port function bodies, verified via a live
     smoke-run of the pre-port code during this fold -- see canonical_battery.py's module
     docstring for the audit trail).
  2. run_g_battery's DEFAULTS match what 100% of the four existing G-battery producers
     (gate_revalidation_ab.py's own main() + the 3 files that `import gate_revalidation_ab as
     grab`) pass today: drop_n=3, alpha(q)=0.10, oos_fraction=0.5, n_floor=15. No producer was
     found using a different value for any of these -- this fold found NO threshold
     disagreement to preserve-not-reconcile.
  3. Every producer that calls bh_fdr passes `q=` EXPLICITLY (never relies on the function's
     own default) -- a repo-grep guard so a future new caller can't silently drift onto
     whatever the default happens to be without that being visible in its own source line.

Pure unit tests on synthetic fixtures -- no live core-decisions.jsonl / OPRA cache
dependency, so these stay green regardless of what today's ledger looks like.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from lib import canonical_battery as cb  # noqa: E402

FIXTURE_PNLS = [100.0, -40.0, 60.0, -20.0, 80.0, 30.0, -15.0, 45.0]
FIXTURE_ROWS = [{"pnl": p} for p in FIXTURE_PNLS]


# ==================================================================== byte-identical regression
# Expected values captured live (this fold, 2026-09-03) from gate_revalidation_ab.py's
# PRE-PORT function bodies on FIXTURE_PNLS/FIXTURE_ROWS, before any code moved.
def test_one_sample_p_byte_identical_to_pre_port():
    assert cb.one_sample_p(FIXTURE_PNLS) == 0.09380697241136171


def test_bh_fdr_byte_identical_to_pre_port():
    assert cb.bh_fdr([0.01, 0.04, 0.20], q=0.10) == [True, True, False]


def test_drop_top_n_byte_identical_to_pre_port():
    # drops the 3 largest winners (100, 80, 60 = 240) from the 240 total -> 0.0
    assert cb.drop_top_n(FIXTURE_PNLS, 3) == (0.0, 3)


def test_cohort_metrics_byte_identical_to_pre_port():
    assert cb.cohort_metrics(FIXTURE_ROWS) == {
        "n": 8, "total": 240.0, "mean": 30.0, "wr_pct": 62.5,
        "drop_top3": 0.0, "n_dropped_for_drop_top3": 3,
        "best": 100.0, "worst": -40.0,
    }


def test_is_oos_split_byte_identical_to_pre_port():
    is_rows, oos_rows = cb.is_oos_split(FIXTURE_ROWS)
    assert is_rows == FIXTURE_ROWS[:4]
    assert oos_rows == FIXTURE_ROWS[4:]


def test_g_battery_byte_identical_to_pre_port():
    cohort = cb.cohort_metrics(FIXTURE_ROWS)
    is_rows, oos_rows = cb.is_oos_split(FIXTURE_ROWS)
    oos_metrics = cb.cohort_metrics(oos_rows)
    pval = cb.one_sample_p(FIXTURE_PNLS)
    bh_sig = cb.bh_fdr([pval], q=0.10)
    battery = cb.g_battery(cohort, oos_metrics, pval, bh_sig[0])
    assert battery == {
        "gates": {
            "G_mean": True, "G_oos": True, "G_drop3": False,
            "G_bhfdr": True, "G_n": False,
        },
        "verdict": "NOT-UNBLOCK-ELIGIBLE",
        "pval": round(pval, 4),
    }


# ==================================================================== gate_revalidation_ab.py
# re-export parity -- the module that used to DEFINE these now only imports them; confirm the
# re-exported names on `grab` produce identical output to calling canonical_battery directly.
def test_gate_revalidation_ab_reexports_are_identical():
    sys.path.insert(0, str(REPO / "backtest" / "tools"))
    import gate_revalidation_ab as grab  # noqa: PLC0415

    assert grab.one_sample_p(FIXTURE_PNLS) == cb.one_sample_p(FIXTURE_PNLS)
    assert grab.bh_fdr([0.01, 0.04, 0.20], q=0.10) == cb.bh_fdr([0.01, 0.04, 0.20], q=0.10)
    assert grab.drop_top_n(FIXTURE_PNLS, 3) == cb.drop_top_n(FIXTURE_PNLS, 3)
    assert grab.cohort_metrics(FIXTURE_ROWS) == cb.cohort_metrics(FIXTURE_ROWS)
    assert grab.is_oos_split(FIXTURE_ROWS) == cb.is_oos_split(FIXTURE_ROWS)
    assert grab.g_battery({"n": 20, "mean": 5, "drop_top3": 3}, {"n": 10, "mean": 2}, 0.01, True) \
        == cb.g_battery({"n": 20, "mean": 5, "drop_top3": 3}, {"n": 10, "mean": 2}, 0.01, True)
    # identity, not just equality -- confirms grab.g_battery IS canonical_battery.g_battery,
    # not a second copy that merely happens to agree today.
    assert grab.g_battery is cb.g_battery
    assert grab.bh_fdr is cb.bh_fdr
    assert grab.one_sample_p is cb.one_sample_p
    assert grab.drop_top_n is cb.drop_top_n
    assert grab.cohort_metrics is cb.cohort_metrics
    assert grab.is_oos_split is cb.is_oos_split


# ==================================================================== run_g_battery (new
# convenience wrapper -- no existing caller uses it yet) ========================================
def test_run_g_battery_matches_manual_orchestration_on_fixture():
    manual_cohort = cb.cohort_metrics(FIXTURE_ROWS)
    manual_is, manual_oos = cb.is_oos_split(FIXTURE_ROWS)
    manual_oos_m = cb.cohort_metrics(manual_oos)
    manual_p = cb.one_sample_p(FIXTURE_PNLS)
    manual_bh = cb.bh_fdr([manual_p], q=0.10)
    manual_battery = cb.g_battery(manual_cohort, manual_oos_m, manual_p, manual_bh[0])

    out = cb.run_g_battery(FIXTURE_PNLS)
    assert out["cohort"] == manual_cohort
    assert out["oos_half"] == manual_oos_m
    assert out["one_sample_p"] == round(manual_p, 4)
    assert out["bh_fdr_significant"] == manual_bh[0]
    assert out["g_battery"] == manual_battery


def test_run_g_battery_rejects_non_half_oos_fraction():
    import pytest  # noqa: PLC0415
    with pytest.raises(ValueError):
        cb.run_g_battery(FIXTURE_PNLS, oos_fraction=0.3)


def test_run_g_battery_honors_explicit_n_floor():
    out_default = cb.run_g_battery(FIXTURE_PNLS)  # n=8 < 15 -> G_n False
    assert out_default["g_battery"]["gates"]["G_n"] is False
    out_low_floor = cb.run_g_battery(FIXTURE_PNLS, n_floor=5)
    assert out_low_floor["g_battery"]["gates"]["G_n"] is True


# ==================================================================== defaults match the
# majority (here: 100%) of existing callers -- no silent drift from what's actually deployed
def test_defaults_match_existing_caller_majority():
    import inspect  # noqa: PLC0415

    sig = inspect.signature(cb.run_g_battery)
    assert sig.parameters["drop_n"].default == 3        # cohort_metrics hardcodes drop_top_n(pnls, 3)
    assert sig.parameters["alpha"].default == 0.10       # every producer's own bh_fdr(..., q=0.10)
    assert sig.parameters["oos_fraction"].default == 0.5  # is_oos_split's floor-division 50/50 split
    assert sig.parameters["n_floor"].default == 15        # g_battery's own hardcoded `n >= 15`


# ==================================================================== every real caller's
# bh_fdr call passes q= explicitly -- guards against a future caller silently inheriting
# whatever the function default happens to be instead of stating its own threshold.
_BH_FDR_CALL_SITES = [
    REPO / "backtest" / "tools" / "gate_revalidation_ab.py",
    REPO / "backtest" / "tools" / "gate_revalidation_structure_veto_extended_2026_08_23.py",
    REPO / "backtest" / "tools" / "gate_revalidation_bearish_fill_bar_extended_2026_08_23.py",
    REPO / "backtest" / "tools" / "gate_revalidation_bearish_fill_bar_wholebook_2026_08_30.py",
]
_BH_FDR_CALL_RE = re.compile(r"\bbh_fdr\(\s*[^)]*?\)")


def test_every_g_battery_caller_passes_q_explicitly():
    checked = 0
    for path in _BH_FDR_CALL_SITES:
        assert path.exists(), f"expected G-battery caller missing: {path}"
        text = path.read_text(encoding="utf-8")
        for m in _BH_FDR_CALL_RE.finditer(text):
            call = m.group(0)
            if "def bh_fdr" in call:
                continue  # skip the function definition itself where present
            checked += 1
            assert "q=" in call, f"{path.name}: bh_fdr call has no explicit q= -- {call!r}"
    assert checked >= 4, f"expected at least 4 bh_fdr call sites across the 4 G-battery files, found {checked}"
