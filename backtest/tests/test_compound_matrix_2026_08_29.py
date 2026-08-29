"""Guard: setup/scripts/compound_matrix.py (2026-08-29) -- the compounding-path matrix.

Analysis-path only -- this pins the MATH (capacity-bend formula + bootstrap determinism),
not any live trading behavior. Nothing here reads or writes params*.json / heartbeat_core.py
/ risk_gate.py / filters.py / strategies.py / fleet_executor.py / exit_manager.py /
fleet_broker.py, and nothing arms anything.

THE LOAD-BEARING PROPERTIES:
  1. DETERMINISTIC SEEDING: deterministic_seed() must be process-independent (Python's
     builtin hash() on str/tuple is randomized per-process via PYTHONHASHSEED unless
     disabled -- using it silently breaks "run this twice, get the same answer"). Guarded
     directly, and by a same-process regression: two separate `random.Random` streams
     built from the same deterministic_seed() inputs must draw identically.
  2. THE CAPACITY-BEND FORMULA is pinned algebraically: E* = threshold * depth * P_entry *
     100 / deployment_fraction. A regression here means either the derivation drifted or
     the market-depth constants it reads (analysis/recommendations/_b2_depth_2026_08_28.json)
     changed without anyone noticing.
  3. THE SIMULATION STEP FUNCTION (_step) must cap DEPLOYABLE equity at E*, never equity
     itself -- i.e. equity can still exceed E* (compounding continues, just linearly), the
     cap only zeroes out the MARGINAL dollar contribution above E*. This is the exact
     mechanism that turns "exponential" into "bends toward linear" -- get it backwards
     (capping equity itself) and every milestone number in the report is wrong.
  4. FULL-RUN REPRODUCIBILITY: two full invocations of main() must produce byte-identical
     JSON (excluding the generated_at_et timestamp) -- this is the actual deliverable
     requirement ("guard test pinning ... the bootstrap reproducibility (fixed seed)").
"""
from __future__ import annotations

import importlib
import json
import random
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
cm = importlib.import_module("compound_matrix")


# ---------------------------------------------------------------------------
# 1. deterministic_seed() -- process-independent, not builtin hash()
# ---------------------------------------------------------------------------
class TestDeterministicSeed:
    def test_same_inputs_same_output_within_process(self):
        a = cm.deterministic_seed(20260829, "post_fix", 1.00, "all_days", 5000.0)
        b = cm.deterministic_seed(20260829, "post_fix", 1.00, "all_days", 5000.0)
        assert a == b

    def test_different_inputs_usually_differ(self):
        a = cm.deterministic_seed(20260829, "post_fix", 1.00, "all_days", 5000.0)
        b = cm.deterministic_seed(20260829, "august", 1.00, "all_days", 5000.0)
        assert a != b

    def test_does_not_use_builtin_hash_randomization(self):
        """The historical bug this guards: SEED + hash((...)) % 1000 using Python's
        builtin hash() on a tuple containing strings, which is randomized per-process
        (PYTHONHASHSEED) unless explicitly seeded -- silently non-reproducible."""
        import subprocess
        script = (
            "import sys; sys.path.insert(0, r'" + str(REPO / "setup" / "scripts") + "'); "
            "import compound_matrix as cm; "
            "print(cm.deterministic_seed(20260829, 'post_fix', 1.00, 'all_days', 5000.0))"
        )
        r1 = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True,
            env={"PYTHONHASHSEED": "1", **_minimal_env()},
        )
        r2 = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True,
            env={"PYTHONHASHSEED": "2", **_minimal_env()},
        )
        assert r1.returncode == 0, r1.stderr
        assert r2.returncode == 0, r2.stderr
        assert r1.stdout.strip() == r2.stdout.strip(), (
            "deterministic_seed() output changed between two different PYTHONHASHSEED "
            "values -- it is (re-)using Python's randomized builtin hash() somewhere."
        )

    def test_random_streams_built_from_it_are_identical(self):
        seed = cm.deterministic_seed(20260829, "x", "y", "z")
        rng1 = random.Random(seed)
        rng2 = random.Random(seed)
        draws1 = [rng1.random() for _ in range(50)]
        draws2 = [rng2.random() for _ in range(50)]
        assert draws1 == draws2


def _minimal_env() -> dict:
    import os
    # PATH/etc so the subprocess python can actually run
    return {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}


# ---------------------------------------------------------------------------
# 2. capacity-bend formula, algebraic pin
# ---------------------------------------------------------------------------
class TestCapacityBendFormula:
    def test_e_star_algebra(self):
        """E* = threshold * depth * P_entry * 100 / f -- solved from
        contracts_per_entry(E) = f*E/(P_entry*100) == threshold*depth."""
        depth, p_entry, f, threshold = 46.0, 1.15, 0.17, 0.25
        e_star = threshold * depth * p_entry * 100.0 / f
        contracts_at_e_star = f * e_star / (p_entry * 100.0)
        assert contracts_at_e_star == pytest.approx(threshold * depth, rel=1e-9)

    def test_e_star_decreases_as_deployment_fraction_increases(self):
        """More aggressive deployment (higher f) hits the SAME depth ceiling at a LOWER
        equity -- capacity_bend_analysis must preserve this monotonic relationship."""
        depth, p_entry, threshold = 46.0, 1.15, 0.25
        e_lo = threshold * depth * p_entry * 100.0 / 0.10
        e_hi = threshold * depth * p_entry * 100.0 / 0.25
        assert e_hi < e_lo

    def test_capacity_bend_analysis_matches_hand_computation(self):
        rows = cm.load_trades()
        depth_doc = cm.load_depth()
        result = cm.capacity_bend_analysis(rows, depth_doc)
        depth_thin = depth_doc["buckets"] and next(
            b["bid_med"] for b in depth_doc["buckets"] if b["bucket"] == "$1.50-$2.50"
        )
        p_entry = result["winner_cohort_median_entry_premium"]
        f, t = 0.17, 0.25
        expected = round(t * depth_thin * p_entry * 100.0 / f, 0)
        assert result["headline_central"]["E_star_stress"] == expected

    def test_depth_wall_uses_thin_bucket_not_deep_bucket(self):
        """The wall MUST be keyed to the $1.50-2.50 bucket (where winners exit), not the
        $0.00-0.20 bucket (deep, where losers exit) -- using the wrong bucket would silently
        report a wall an order of magnitude too permissive."""
        rows = cm.load_trades()
        depth_doc = cm.load_depth()
        result = cm.capacity_bend_analysis(rows, depth_doc)
        assert result["depth_thin_bucket_1_50_2_50_contracts"] < result["depth_deep_bucket_0_00_0_20_contracts"]
        # E* computed off the THIN bucket must be far smaller than if it had used the deep one
        f, t = 0.17, 0.25
        p_entry = result["winner_cohort_median_entry_premium"]
        e_star_thin = t * result["depth_thin_bucket_1_50_2_50_contracts"] * p_entry * 100.0 / f
        e_star_deep = t * result["depth_deep_bucket_0_00_0_20_contracts"] * p_entry * 100.0 / f
        # headline_central rounds to the nearest dollar -- compare post-rounding
        assert round(e_star_thin, 0) == result["headline_central"]["E_star_stress"]
        assert e_star_thin < e_star_deep


# ---------------------------------------------------------------------------
# 3. the simulation step: caps DEPLOYABLE equity, never equity itself
# ---------------------------------------------------------------------------
class TestStepFunctionCapsDeployableNotTotalEquity:
    def test_below_wall_is_a_pure_passthrough(self):
        e_star = 10_000.0
        out = cm._step(equity=5000.0, pct_return=10.0, e_star=e_star)
        assert out == pytest.approx(5000.0 + 0.10 * 5000.0)

    def test_above_wall_dollar_gain_is_capped_at_e_star_not_at_equity(self):
        e_star = 10_000.0
        out = cm._step(equity=50_000.0, pct_return=10.0, e_star=e_star)
        # WRONG (equity-capping) implementation would give 50_000 + 0.10*10_000 = 51_000
        # but so would this one -- the discriminating case is the ASSERTION on the delta:
        assert out - 50_000.0 == pytest.approx(0.10 * e_star)
        assert out - 50_000.0 != pytest.approx(0.10 * 50_000.0)

    def test_equity_itself_is_never_hard_capped(self):
        """Equity must be allowed to keep growing past E* (just more slowly) -- a model
        that hard-caps equity at E* would make every milestone above E* unreachable, which
        is NOT the intended 'bends toward linear' shape."""
        e_star = 10_000.0
        equity = 50_000.0
        equity2 = cm._step(equity, 5.0, e_star)
        assert equity2 > 50_000.0
        assert equity2 > e_star

    def test_negative_returns_are_also_capped_at_e_star_above_the_wall(self):
        """Symmetric: losses above the wall are ALSO sized off the capped deployable
        equity, not the full (larger) equity -- contracts are capped both ways."""
        e_star = 10_000.0
        out = cm._step(equity=50_000.0, pct_return=-10.0, e_star=e_star)
        assert 50_000.0 - out == pytest.approx(0.10 * e_star)

    def test_none_e_star_is_uncapped(self):
        out_capped = cm._step(equity=50_000.0, pct_return=10.0, e_star=10_000.0)
        out_naive = cm._step(equity=50_000.0, pct_return=10.0, e_star=None)
        assert out_naive == pytest.approx(50_000.0 + 0.10 * 50_000.0)
        assert out_naive > out_capped


# ---------------------------------------------------------------------------
# 4. bootstrap reproducibility -- the actual deliverable requirement
# ---------------------------------------------------------------------------
class TestBootstrapReproducibility:
    def test_bootstrap_paths_identical_across_two_calls_same_seed(self):
        pool = [1.5, -2.0, 3.25, -0.5, 4.0, -1.25, 2.75]
        r1 = cm.bootstrap_paths(pool, 5000.0, 8000.0, n_sims=200, n_days=63, seed=42)
        r2 = cm.bootstrap_paths(pool, 5000.0, 8000.0, n_sims=200, n_days=63, seed=42)
        assert r1 == r2

    def test_bootstrap_paths_differs_with_different_seed(self):
        pool = [1.5, -2.0, 3.25, -0.5, 4.0, -1.25, 2.75]
        r1 = cm.bootstrap_paths(pool, 5000.0, 8000.0, n_sims=200, n_days=63, seed=42)
        r2 = cm.bootstrap_paths(pool, 5000.0, 8000.0, n_sims=200, n_days=63, seed=43)
        assert r1["equity_paths"] != r2["equity_paths"]

    def test_simulate_milestones_identical_across_two_calls_same_seed(self):
        pool = [1.5, -2.0, 3.25, -0.5, 4.0, -1.25, 2.75]
        targets = {"10k": 10_000.0}
        r1 = cm.simulate_milestones(pool, 5000.0, 8000.0, targets, n_sims=100, max_days=252, seed=7)
        r2 = cm.simulate_milestones(pool, 5000.0, 8000.0, targets, n_sims=100, max_days=252, seed=7)
        assert r1 == r2


@pytest.mark.slow
class TestFullRunReproducibility:
    """The real end-to-end guard -- run main() twice, diff the JSON. Marked slow (this
    invokes the full ~2000-sim x 96-combo grid, ~15s) so default `pytest -m "not slow"`
    runs stay fast; CI / pre-commit should still cover it."""

    def test_two_full_runs_produce_byte_identical_json(self, tmp_path, monkeypatch):
        out1 = _run_main_capture_json(tmp_path / "run1")
        out2 = _run_main_capture_json(tmp_path / "run2")
        out1.pop("generated_at_et", None)
        out2.pop("generated_at_et", None)
        assert out1 == out2


def _run_main_capture_json(out_dir: Path) -> dict:
    import subprocess
    out_dir.mkdir(parents=True, exist_ok=True)
    script = (
        "import sys, pathlib; sys.path.insert(0, r'" + str(REPO / "setup" / "scripts") + "'); "
        "import compound_matrix as cm; "
        "cm.OUT_DIR = pathlib.Path(r'" + str(out_dir) + "'); "
        "cm.OUT_JSON = cm.OUT_DIR / 'matrix.json'; "
        "cm.OUT_MD = cm.OUT_DIR / 'MATRIX.md'; "
        "cm.main()"
    )
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    with (out_dir / "matrix.json").open(encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 5. sanity: output files exist and are internally consistent (regression net)
# ---------------------------------------------------------------------------
class TestShippedOutputs:
    JSON_PATH = REPO / "analysis" / "compound" / "matrix.json"
    MD_PATH = REPO / "analysis" / "compound" / "MATRIX.md"

    def test_outputs_exist(self):
        assert self.JSON_PATH.exists(), "run setup/scripts/compound_matrix.py first"
        assert self.MD_PATH.exists()

    def test_four_live_arms_not_five(self):
        data = json.loads(self.JSON_PATH.read_text(encoding="utf-8"))
        assert set(data["live_arms"]) == {"safe-2", "bold-2", "safe-3", "risky-1"}
        assert "risky-3" not in data["live_arms"]

    def test_post_fix_reproduces_j_session_count(self):
        """This script's own regime construction must land on J's exact n=23/8-sessions
        for the post-fix window -- a silent roster or cutoff-date drift would break this."""
        data = json.loads(self.JSON_PATH.read_text(encoding="utf-8"))
        s = data["regimes"]["post_fix"]["gross_stats"]
        assert s["n_arm_days"] == 23
        assert s["n_sessions"] == 8

    def test_all_history_median_is_negative(self):
        data = json.loads(self.JSON_PATH.read_text(encoding="utf-8"))
        assert data["regimes"]["all_history"]["gross_stats"]["median_pct"] < 0

    def test_three_regimes_present_and_never_pooled(self):
        data = json.loads(self.JSON_PATH.read_text(encoding="utf-8"))
        assert set(data["regimes"].keys()) == {"post_fix", "august", "all_history"}
        # each regime's n must differ (a pooling bug would make two of them identical)
        ns = {name: r["gross_stats"]["n_arm_days"] for name, r in data["regimes"].items()}
        assert len(set(ns.values())) == 3, ns

    def test_all_four_slippage_levels_present_in_every_regime(self):
        data = json.loads(self.JSON_PATH.read_text(encoding="utf-8"))
        expected = {f"slippage_{s:.2f}" for s in (0.0, 0.50, 1.00, 2.00)}
        for regime in data["bootstrap"].values():
            assert set(regime.keys()) == expected

    def test_drop_best_day_variant_present(self):
        data = json.loads(self.JSON_PATH.read_text(encoding="utf-8"))
        pf = data["bootstrap"]["post_fix"]["slippage_1.00"]
        assert "all_days" in pf and "drop_best_day" in pf
        # dropping the best day must never IMPROVE the p50 12mo outcome
        all_days_p50 = pf["all_days"]["start_5000"]["equity_paths"]["12mo"]["p50"]
        drop_best_p50 = pf["drop_best_day"]["start_5000"]["equity_paths"]["12mo"]["p50"]
        assert drop_best_p50 <= all_days_p50

    def test_no_trading_engine_files_were_touched(self):
        """Scope guard: this build is analysis-path only."""
        forbidden = [
            REPO / "automation" / "state" / "params.json",
            REPO / "automation" / "state" / "aggressive" / "params.json",
            REPO / "setup" / "scripts" / "heartbeat_core.py",
            REPO / "backtest" / "lib" / "risk_gate.py",
            REPO / "backtest" / "lib" / "filters.py",
            REPO / "automation" / "state" / "fleet" / "strategies.py",
            REPO / "automation" / "state" / "fleet" / "fleet_executor.py",
            REPO / "automation" / "state" / "fleet" / "exit_manager.py",
            REPO / "automation" / "state" / "fleet" / "fleet_broker.py",
        ]
        import subprocess
        diff = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"], capture_output=True, text=True, cwd=str(REPO),
        ).stdout.splitlines()
        diff += subprocess.run(
            ["git", "diff", "--name-only", "--cached", "HEAD"], capture_output=True, text=True, cwd=str(REPO),
        ).stdout.splitlines()
        changed = {(REPO / p).resolve() for p in diff}
        for f in forbidden:
            assert f.resolve() not in changed, f"forbidden file touched: {f}"
