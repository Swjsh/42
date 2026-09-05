"""Guard: Stage-1-in-the-loop (GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05).

The provenance audit (GOAL-KITCHEN-INTEGRITY, commit 11a45e2d) found 81% of Kitchen
verdict files cite no artifact and 10% cite artifacts that don't exist -- because the
chef-cook path (kitchen_daemon._run_task) asked a free model for a verdict + numbers
without ever RUNNING anything. This goal put an EXISTING Stage-1 evaluator
(backtest.autoresearch.overnight_grinder.evaluate_combo, wrapped by
setup/scripts/kitchen_stage1_runner.py) INSIDE the loop, executed by the daemon BEFORE
any model call.

These tests RED-proof the three load-bearing structural guarantees:
  1. A numeric verdict is structurally impossible without an executed Stage-1 artifact
     (_run_task never reaches the model-call branch unless Stage-1 succeeded).
  2. The runner-failure path writes a candidate with ZERO numeric verdict content and
     ZERO model calls (cost-free, deterministic).
  3. The daemon's own `## Provenance` block always wins over anything the model wrote --
     a model-fabricated provenance line pointing at a fake/foreign artifact is stripped
     and replaced, never trusted.

kitchen_stage1_runner.py itself is exercised with autoresearch.overnight_grinder.evaluate_combo
STUBBED (no real 65s backtest per test) so this suite runs in under a second, matching the
existing stub-loader pattern (test_kitchen_daemon_starvation.py, test_kitchen_reviewer_
numeric_evidence.py).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "setup" / "scripts"


# ────────────────────────────────────────────────────────────────────────────
# kitchen_stage1_runner.py -- loaded with autoresearch.overnight_grinder.evaluate_combo
# stubbed so the suite doesn't spend ~65s per test running the real base-engine backtest.
# ────────────────────────────────────────────────────────────────────────────

def _load_stage1_runner(evaluate_combo_fn, monkeypatch):
    """Load kitchen_stage1_runner.py with a fake `autoresearch.overnight_grinder` module
    registered in sys.modules for the LIFE OF THE TEST (via monkeypatch.setitem, auto-
    reverted at teardown) -- kitchen_stage1_runner.main() imports evaluate_combo AT CALL
    TIME, not at module-load time, so the fake must still be present when the test later
    calls mod.main(), not just while this loader is exec'ing the module body."""
    fake_pkg = types.ModuleType("autoresearch")
    fake_mod = types.ModuleType("autoresearch.overnight_grinder")
    fake_mod.evaluate_combo = evaluate_combo_fn
    fake_pkg.overnight_grinder = fake_mod
    monkeypatch.setitem(sys.modules, "autoresearch", fake_pkg)
    monkeypatch.setitem(sys.modules, "autoresearch.overnight_grinder", fake_mod)
    spec = importlib.util.spec_from_file_location(
        "kitchen_stage1_runner_under_test", _SCRIPTS / "kitchen_stage1_runner.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _isolate_paths(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(mod, "RUN_LOG", tmp_path / "automation" / "state" / "kitchen-stage1-run-log.jsonl")
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path / "analysis" / "kitchen-review" / "stage1-runs")
    monkeypatch.setattr(mod, "LOCK_FILE", tmp_path / "automation" / "state" / "kitchen-stage1-runner.lock")


def test_success_writes_artifact_and_run_log_row(tmp_path, monkeypatch):
    mod = _load_stage1_runner(lambda combo: {"combo": combo, "wide_pnl": 123.45, "edge_capture": 200.0}, monkeypatch)
    _isolate_paths(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", [
        "kitchen_stage1_runner.py", "--combo-json", '{"super_stop": -0.1}', "--slug", "unit-test-ok",
        "--task-id", "unit-test",
    ])
    rc = mod.main()
    assert rc == 0
    artifacts = list(mod.OUT_DIR.glob("*.json"))
    assert len(artifacts) == 1, artifacts
    body = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert body["result"]["edge_capture"] == 200.0
    assert body["engine"] == "backtest.autoresearch.overnight_grinder.evaluate_combo"
    assert "MECHANISM EVIDENCE ONLY" in body["engine_note"]
    assert "NOT real-fills evidence" in body["engine_note"]
    rows = [json.loads(l) for l in mod.RUN_LOG.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["status"] == "PROVENANCE-OK"
    assert rows[-1]["artifact"] == str(artifacts[0].relative_to(tmp_path)).replace("\\", "/")
    assert not mod.LOCK_FILE.exists(), "lock must be released after a successful run"


def test_failure_writes_no_artifact_and_run_log_says_runner_failed(tmp_path, monkeypatch):
    def _boom(combo):
        raise RuntimeError("synthetic evaluator crash")
    mod = _load_stage1_runner(_boom, monkeypatch)
    _isolate_paths(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", [
        "kitchen_stage1_runner.py", "--combo-json", "{}", "--slug", "unit-test-fail",
        "--task-id", "unit-test-fail",
    ])
    rc = mod.main()
    assert rc != 0
    assert not mod.OUT_DIR.exists() or not list(mod.OUT_DIR.glob("*.json")), \
        "a crashed evaluator must never leave an artifact behind"
    rows = [json.loads(l) for l in mod.RUN_LOG.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["status"] == "RUNNER-FAILED"
    assert "RuntimeError" in rows[-1]["reason"]
    assert not mod.LOCK_FILE.exists(), "lock must be released even on failure"


def test_timeout_writes_no_artifact(tmp_path, monkeypatch):
    import time as _time

    def _slow(combo):
        _time.sleep(2.0)
        return {"edge_capture": 1.0}
    mod = _load_stage1_runner(_slow, monkeypatch)
    _isolate_paths(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", [
        "kitchen_stage1_runner.py", "--combo-json", "{}", "--slug", "unit-test-timeout",
        "--task-id", "unit-test-timeout", "--timeout-s", "0.05",
    ])
    rc = mod.main()
    assert rc != 0
    assert not mod.OUT_DIR.exists() or not list(mod.OUT_DIR.glob("*.json"))
    rows = [json.loads(l) for l in mod.RUN_LOG.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["status"] == "RUNNER-FAILED"
    assert "timeout" in rows[-1]["reason"]


def test_bad_combo_json_writes_no_artifact(tmp_path, monkeypatch):
    mod = _load_stage1_runner(lambda combo: {"edge_capture": 1.0}, monkeypatch)
    _isolate_paths(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", [
        "kitchen_stage1_runner.py", "--combo-json", "not-json{{", "--slug", "unit-test-badjson",
    ])
    rc = mod.main()
    assert rc != 0
    assert not mod.OUT_DIR.exists() or not list(mod.OUT_DIR.glob("*.json"))


def test_single_worker_lock_blocks_concurrent_run(tmp_path, monkeypatch):
    mod = _load_stage1_runner(lambda combo: {"edge_capture": 1.0}, monkeypatch)
    _isolate_paths(mod, tmp_path, monkeypatch)
    mod.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    mod.LOCK_FILE.write_text("held by a different in-flight run\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "kitchen_stage1_runner.py", "--combo-json", "{}", "--slug", "unit-test-locked",
    ])
    rc = mod.main()
    assert rc != 0
    assert not mod.OUT_DIR.exists() or not list(mod.OUT_DIR.glob("*.json"))
    # The lock this test didn't create must survive untouched (never unlink someone else's).
    assert mod.LOCK_FILE.exists()


# ────────────────────────────────────────────────────────────────────────────
# kitchen_daemon._run_task Stage-1 gating (structural guarantee: no verdict without an
# executed artifact; runner-failure path is $0 and numberless).
# ────────────────────────────────────────────────────────────────────────────

def _load_kitchen_daemon():
    fakes = {}
    for name in ("chef_nemotron", "swarm_client"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            if name == "chef_nemotron":
                mod.CHEF_SYSTEM_PROMPT = "stub"
                mod.MODEL_LADDER = []
                mod.CANDIDATES_DIR = None  # set per-test via monkeypatch
                mod._call_with_ladder = lambda *a, **k: {"ok": False, "error": "stub-never-called"}
                mod._write_candidate = lambda *a, **k: (_ for _ in ()).throw(
                    AssertionError("model-write path must not be reached when Stage-1 failed"))
                mod._slugify = lambda s: "stub"
                mod._gather_common_inputs = lambda: ""
            else:
                mod.call_role = lambda *a, **k: (_ for _ in ()).throw(
                    AssertionError("pool model call must not happen when Stage-1 failed"))
            sys.modules[name] = mod
            fakes[name] = mod
    inserted = "kitchen_daemon" not in sys.modules
    try:
        spec = importlib.util.spec_from_file_location("kitchen_daemon_under_test", _SCRIPTS / "kitchen_daemon.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    finally:
        for name in fakes:
            sys.modules.pop(name, None)
        if inserted:
            sys.modules.pop("kitchen_daemon", None)
    return m


def test_run_task_runner_failed_writes_no_numbers_and_calls_no_model(tmp_path, monkeypatch):
    """Structural RED-proof #1+#2: when Stage-1 fails, _run_task must (a) never reach
    _swarm.call_role / _call_with_ladder (both raise AssertionError in this fixture if
    invoked) and (b) write a candidate carrying zero numeric verdict content -- verified
    against the REAL kitchen_provenance_audit numeric-verdict regex, not a hand-rolled
    check, so this test breaks if that regex's definition of "numeric" ever changes."""
    kd = _load_kitchen_daemon()
    cands_dir = tmp_path / "strategy" / "candidates"
    cands_dir.mkdir(parents=True)
    monkeypatch.setattr(kd, "REPO", tmp_path)
    monkeypatch.setattr(kd, "CANDIDATES_DIR", cands_dir)
    monkeypatch.setattr(
        kd, "_run_stage1",
        lambda combo, slug, task_id: {
            "ok": False, "artifact": None, "reason": "forced_test_failure",
            "elapsed_s": 1.0, "command": "FAKE CMD forced by test",
        },
    )
    result = kd._run_task({"task": "does knob X help", "task_id": "t1", "combo": {}}, paid_tier_blocked=True)
    assert result["ok"] is True  # candidate written; just no numbers
    assert result["cost_usd"] == 0.0
    assert "RUNNER-FAILED" in result["model"]
    target = tmp_path / result["output_path"]
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "RUNNER-FAILED" in text
    assert "forced_test_failure" in text

    # Cross-check against the REAL numeric-verdict detector this candidate will be
    # classified by in production.
    kpa_spec = importlib.util.spec_from_file_location(
        "kpa_under_test", _SCRIPTS / "kitchen_provenance_audit.py")
    kpa = importlib.util.module_from_spec(kpa_spec)
    sys.modules["kpa_under_test"] = kpa
    try:
        kpa_spec.loader.exec_module(kpa)
    finally:
        sys.modules.pop("kpa_under_test", None)
    classified = kpa.classify_file(target, repo_root=tmp_path)
    assert classified.status == "NOT-A-VERDICT", classified.status


def test_run_task_success_path_strips_fake_model_provenance(tmp_path, monkeypatch):
    """Structural RED-proof #3: even if the model tries to fabricate its own
    `## Provenance` section pointing at a nonexistent artifact, the daemon's real,
    executed command + artifact always wins -- the fake line must not survive."""
    kd = _load_kitchen_daemon()
    cands_dir = tmp_path / "strategy" / "candidates"
    cands_dir.mkdir(parents=True)
    real_artifact = tmp_path / "analysis" / "kitchen-review" / "stage1-runs" / "real-run.json"
    real_artifact.parent.mkdir(parents=True)
    real_artifact.write_text(json.dumps({"result": {"edge_capture": 42.0}}), encoding="utf-8")
    real_artifact_rel = str(real_artifact.relative_to(tmp_path)).replace("\\", "/")

    monkeypatch.setattr(kd, "REPO", tmp_path)
    monkeypatch.setattr(kd, "CANDIDATES_DIR", cands_dir)
    monkeypatch.setattr(
        kd, "_run_stage1",
        lambda combo, slug, task_id: {
            "ok": True, "artifact": real_artifact_rel, "reason": None,
            "elapsed_s": 12.3, "command": "REAL EXECUTED COMMAND",
        },
    )

    fake_model_content = (
        "# CANDIDATE: sneaky\n\n## Hypothesis\n\ntest\n\n"
        "## Provenance\n\nprovenance: totally-fabricated-command -> nonexistent/fake.json\n\n"
        "## Confidence\n\n9/10\n"
    )

    captured = {}

    def _fake_write_candidate(content, slug, *, model, cost_usd, ladder_used):
        captured["content"] = content
        p = cands_dir / f"{slug}.md"
        p.write_text(content, encoding="utf-8")
        return p

    monkeypatch.setattr(kd, "_write_candidate", _fake_write_candidate)
    monkeypatch.setattr(
        kd, "_swarm",
        types.SimpleNamespace(call_role=lambda *a, **k: {
            "ok": True, "content": fake_model_content, "lane": "fake-pool", "elapsed_s": 1.0,
        }),
    )

    result = kd._run_task({"task": "cook something", "task_id": "t2", "combo": {}}, paid_tier_blocked=True)
    assert result["ok"] is True
    written = captured["content"]
    assert "totally-fabricated-command" not in written
    assert "nonexistent/fake.json" not in written
    assert "REAL EXECUTED COMMAND" in written
    assert real_artifact_rel in written
    assert "daemon-executed" in written
