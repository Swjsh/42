"""RED-proofed guard for run_cmd_hidden.py's W14 fix (goal
GOAL-WHY-THIS-WEEK-2026-09-10, item W14).

FINDING this guards: when a Gamma_* scheduled task action omits --log (measured live
this session: 92 of 104 tasks invoking run_cmd_hidden.py do), the pre-fix launcher ran
the child with `subprocess.run(..., capture_output=True)` and only ever logged
`proc.returncode` -- the captured stdout/stderr was read into memory and discarded,
even for a crashing child with a live traceback on stderr. This is the suspected root
enabler of this codebase's C7 failure class ("silent success is failure"; see W10 in
GOAL-WHY-THIS-WEEK-2026-09-10.md for a concrete incident this discarded channel
prevented from being root-caused).

Coverage (per the goal's HARD CONSTRAINTS):
  1. Output IS captured to a file when --log is absent (the core fix).
  2. --log still behaves exactly as before when supplied (no regression).
  3. Retention: per-file rotation + directory age/size pruning.
  4. FAIL-OPEN: a broken default-log path must not prevent the child from running,
     and must not change the returned exit code.

These tests invoke the REAL run_cmd_hidden.py module in-process (importlib, matching
the existing test_self_check_run_cmd_hidden_masked_exit.py convention) so they exercise
the actual code, not a re-implementation. They redirect AUTO_LOG_DIR (and the sentinel)
to a tmp_path per test so no test run pollutes or depends on the live
automation/state/logs/auto/ directory.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "run_cmd_hidden.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_cmd_hidden_w14", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rebind_auto_dir(mod, tmp_path: Path) -> Path:
    """Point the module's auto-log constants at an isolated tmp dir so tests never
    touch (or depend on) the live automation/state/logs/auto/ directory."""
    auto_dir = tmp_path / "auto"
    mod.AUTO_LOG_DIR = auto_dir
    mod._AUTO_PRUNE_SENTINEL = auto_dir / ".last-prune"
    # Point the launcher's own per-date log at tmp_path too, so _log() calls during
    # the test don't append to the real repo's dated log file.
    mod._LAUNCHER_LOG = tmp_path / "launcher.log"
    return auto_dir


# ---- 1. Output is captured when --log is absent (the core fix) --------------------

def test_default_auto_log_captures_stdout_when_log_absent(tmp_path):
    mod = _load_module()
    auto_dir = _rebind_auto_dir(mod, tmp_path)

    marker = "W14_PROBE_STDOUT_abc123"
    rc = mod.main(["run_cmd_hidden.py", "--cwd", str(tmp_path),
                   "--", sys.executable, "-c", f"print('{marker}')"])
    assert rc == 0

    logs = list(auto_dir.glob("*.log"))
    assert logs, "no --log given must still produce a captured log file, not silence"
    combined = "\n".join(p.read_text(encoding="utf-8") for p in logs)
    assert marker in combined, "the child's stdout must be captured to the default auto-log"


def test_default_auto_log_captures_stderr_traceback_when_log_absent(tmp_path):
    """The exact scenario the goal calls out: a crashing child's traceback must now
    be recoverable instead of thrown away."""
    mod = _load_module()
    auto_dir = _rebind_auto_dir(mod, tmp_path)

    rc = mod.main(["run_cmd_hidden.py", "--cwd", str(tmp_path),
                   "--", sys.executable, "-c", "raise ValueError('W14_PROBE_CRASH_xyz')"])
    assert rc != 0

    logs = list(auto_dir.glob("*.log"))
    assert logs, "a crashing child with no --log must still leave a log file behind"
    combined = "\n".join(p.read_text(encoding="utf-8") for p in logs)
    assert "W14_PROBE_CRASH_xyz" in combined, (
        "the traceback must be on disk -- this is the exact channel W10 found missing"
    )
    assert "ValueError" in combined


def test_default_auto_log_filename_derived_from_command(tmp_path):
    mod = _load_module()
    auto_dir = _rebind_auto_dir(mod, tmp_path)
    fake_script = tmp_path / "totally_fake_script.py"
    fake_script.write_text("print('hi')\n", encoding="utf-8")

    rc = mod.main(["run_cmd_hidden.py", "--cwd", str(tmp_path),
                   "--", sys.executable, str(fake_script)])
    assert rc == 0
    assert (auto_dir / "totally_fake_script.log").exists(), (
        "default log path must be named after the invoked script, not a generic name"
    )


# ---- 2. --log still behaves exactly as before when supplied -----------------------

def test_explicit_log_path_unchanged_and_no_auto_log_created(tmp_path):
    mod = _load_module()
    auto_dir = _rebind_auto_dir(mod, tmp_path)
    explicit_log = tmp_path / "explicit" / "mine.log"

    marker = "W14_PROBE_EXPLICIT_log_path"
    rc = mod.main(["run_cmd_hidden.py", "--cwd", str(tmp_path), "--log", str(explicit_log),
                   "--", sys.executable, "-c", f"print('{marker}')"])
    assert rc == 0
    assert explicit_log.exists()
    assert marker in explicit_log.read_text(encoding="utf-8")
    # An explicit --log must not ALSO spray a duplicate into the auto dir.
    assert not auto_dir.exists() or not list(auto_dir.glob("*.log"))


def test_explicit_log_exit_code_contract_matches_default_path(tmp_path):
    """Same failing command, once with --log and once without -- both must return the
    identical exit code (the EXIT CODE CONTRACT requirement)."""
    mod = _load_module()
    _rebind_auto_dir(mod, tmp_path)
    explicit_log = tmp_path / "explicit.log"

    rc_explicit = mod.main(["run_cmd_hidden.py", "--cwd", str(tmp_path), "--log", str(explicit_log),
                            "--", sys.executable, "-c", "import sys; sys.exit(7)"])
    rc_default = mod.main(["run_cmd_hidden.py", "--cwd", str(tmp_path),
                           "--", sys.executable, "-c", "import sys; sys.exit(7)"])
    assert rc_explicit == 7
    assert rc_default == 7


# ---- 3. Retention: rotation + prune ------------------------------------------------

def test_oversized_auto_log_rotates_to_backup(tmp_path):
    mod = _load_module()
    auto_dir = _rebind_auto_dir(mod, tmp_path)
    auto_dir.mkdir(parents=True, exist_ok=True)
    target = auto_dir / "big_script.log"
    target.write_bytes(b"x" * (mod.AUTO_LOG_MAX_FILE_BYTES + 1))

    mod._rotate_if_oversized(target)

    backup = auto_dir / "big_script.log.1"
    assert backup.exists(), "an oversized auto-log must rotate to a .1 backup"
    assert not target.exists() or target.stat().st_size == 0, (
        "the original path must be freed for a fresh log after rotation"
    )


def test_prune_deletes_files_older_than_max_age(tmp_path):
    mod = _load_module()
    auto_dir = _rebind_auto_dir(mod, tmp_path)
    auto_dir.mkdir(parents=True, exist_ok=True)
    old = auto_dir / "ancient.log"
    old.write_text("stale", encoding="utf-8")
    old_time = dt.datetime.now().timestamp() - (mod.AUTO_LOG_MAX_AGE_DAYS + 1) * 86400
    import os
    os.utime(old, (old_time, old_time))

    mod._prune_auto_log_dir()

    assert not old.exists(), "a file older than AUTO_LOG_MAX_AGE_DAYS must be pruned"


def test_prune_enforces_total_dir_size_cap_oldest_first(tmp_path):
    mod = _load_module()
    auto_dir = _rebind_auto_dir(mod, tmp_path)
    auto_dir.mkdir(parents=True, exist_ok=True)
    mod.AUTO_LOG_MAX_DIR_BYTES = 100  # tiny cap for the test
    mod.AUTO_LOG_MAX_AGE_DAYS = 9999  # isolate the size-cap path from the age-cap path

    import os
    now = dt.datetime.now().timestamp()
    older = auto_dir / "older.log"
    newer = auto_dir / "newer.log"
    older.write_bytes(b"a" * 60)
    newer.write_bytes(b"b" * 60)
    os.utime(older, (now - 100, now - 100))
    os.utime(newer, (now - 10, now - 10))

    mod._prune_auto_log_dir()

    assert not older.exists(), "over the dir size cap, the OLDEST file must be pruned first"
    assert newer.exists(), "the newer file must survive while the cap is met by pruning the older one"


def test_prune_is_time_gated_and_never_touches_non_auto_dirs(tmp_path):
    """A sibling directory (standing in for logs/archive/) must never be touched by
    the auto-dir pruner, and a fresh sentinel must skip a second scan within the
    gate window (cheap for 1-minute-cadence tasks)."""
    mod = _load_module()
    auto_dir = _rebind_auto_dir(mod, tmp_path)
    auto_dir.mkdir(parents=True, exist_ok=True)
    sibling_dir = tmp_path / "archive"
    sibling_dir.mkdir()
    sibling_file = sibling_dir / "do_not_touch.log"
    sibling_file.write_text("pre-existing, not ours", encoding="utf-8")

    old_in_auto = auto_dir / "old.log"
    old_in_auto.write_text("x", encoding="utf-8")
    import os
    old_time = dt.datetime.now().timestamp() - (mod.AUTO_LOG_MAX_AGE_DAYS + 1) * 86400
    os.utime(old_in_auto, (old_time, old_time))

    mod._prune_auto_log_dir()
    assert not old_in_auto.exists()
    assert sibling_file.exists(), "pruning must never reach outside AUTO_LOG_DIR"

    # Second call immediately after: sentinel gate should skip re-scanning. Recreate
    # an old file and confirm it survives because the gate is still warm.
    old_in_auto.write_text("y", encoding="utf-8")
    os.utime(old_in_auto, (old_time, old_time))
    mod._prune_auto_log_dir()
    assert old_in_auto.exists(), "within AUTO_PRUNE_INTERVAL_SECONDS, prune must no-op (cheap 1-min cadence)"


# ---- 4. FAIL-OPEN: the hard requirement --------------------------------------------

def test_fail_open_when_default_log_setup_raises(tmp_path, monkeypatch):
    """If _default_auto_log_path raises for any reason, the command must STILL run
    and the exit code must be unchanged -- a logging improvement must never be able
    to block a scheduled task launch."""
    mod = _load_module()
    _rebind_auto_dir(mod, tmp_path)

    def _boom(cmd):
        raise RuntimeError("simulated disk/permission failure")

    monkeypatch.setattr(mod, "_default_auto_log_path", _boom)

    marker = "W14_PROBE_FAIL_OPEN_ran_anyway"
    rc = mod.main(["run_cmd_hidden.py", "--cwd", str(tmp_path),
                   "--", sys.executable, "-c", f"print('{marker}')"])
    assert rc == 0, "the child command must still run and succeed even if default-log setup raises"


def test_fail_open_preserves_nonzero_exit_code_of_child(tmp_path, monkeypatch):
    mod = _load_module()
    _rebind_auto_dir(mod, tmp_path)

    def _boom(cmd):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(mod, "_default_auto_log_path", _boom)

    rc = mod.main(["run_cmd_hidden.py", "--cwd", str(tmp_path),
                   "--", sys.executable, "-c", "import sys; sys.exit(3)"])
    assert rc == 3, "EXIT CODE CONTRACT: fail-open path must still surface the child's real exit code"


def test_fail_open_when_auto_log_open_itself_fails(tmp_path, monkeypatch):
    """Distinguish setup-time failure (above) from open-time failure: even if
    _default_auto_log_path SUCCEEDS in resolving a path, but opening it for append
    fails (e.g. a race), the launch must still degrade to discard-mode rather than
    crash main()."""
    mod = _load_module()
    auto_dir = _rebind_auto_dir(mod, tmp_path)
    auto_dir.mkdir(parents=True, exist_ok=True)

    real_path = auto_dir / "probe_open_fail.log"
    monkeypatch.setattr(mod, "_default_auto_log_path", lambda cmd: real_path)

    real_open = Path.open

    def _boom_open(self, *a, **kw):
        if self == real_path:
            raise OSError("simulated open failure")
        return real_open(self, *a, **kw)

    monkeypatch.setattr(Path, "open", _boom_open)

    rc = mod.main(["run_cmd_hidden.py", "--cwd", str(tmp_path),
                   "--", sys.executable, "-c", "import sys; sys.exit(0)"])
    assert rc == 0, "an open-time failure on the auto-log must still let the child run and report its own exit"


# ---- No console window regression (documentation-level check) ---------------------

def test_all_subprocess_calls_still_pass_create_no_window():
    """Static guard: every subprocess.run call added/kept in this file must carry
    creationflags=_CREATE_NO_WINDOW -- a regression here is the exact 'popup on
    screen' class of bug J has flagged as unacceptable multiple times."""
    src = MOD_PATH.read_text(encoding="utf-8")
    # Match actual invocations ("proc = subprocess.run(") not the docstring's prose
    # mentions of "subprocess.run(...)".
    calls = src.count("proc = subprocess.run(")
    creationflags_count = src.count("creationflags=_CREATE_NO_WINDOW")
    assert calls > 0
    assert creationflags_count == calls, (
        f"found {calls} subprocess.run(...) call(s) but only {creationflags_count} pass "
        "creationflags=_CREATE_NO_WINDOW -- every one must, to avoid a console popup regression"
    )


# --- appended 2026-09-10 by the orchestrator's independent verification of W14 ---------
# Found during pre-commit verification: the reversed-token fallback picked the last FLAG for
# `python -m pkg.mod --flag`, so two DIFFERENT modules sharing a flag both resolved to
# '--flag.log' -- silently merging two producers into one evidence channel, which is the exact
# failure this auto-log exists to prevent. Zero live tasks used `-m` at the time (verified
# against the registry: 0 of the 92), so this closed a latent trap, not an outage.

def test_dash_m_module_invocations_use_the_module_not_the_flag():
    import run_cmd_hidden as r
    # dots are mapped to underscores by _sanitize_stem (filename hygiene) -- assert the
    # sanitizer's real contract, not a guessed one.
    assert r._derive_log_stem(["python", "-m", "backtest.autoresearch.runner", "--daily"]) \
        == "backtest_autoresearch_runner"


def test_two_different_m_modules_sharing_a_flag_do_not_collide():
    import run_cmd_hidden as r
    a = r._derive_log_stem(["python", "-m", "pkg.alpha", "--daily"])
    b = r._derive_log_stem(["python", "-m", "pkg.beta", "--daily"])
    assert a != b, f"distinct modules collapsed to one log: {a!r} == {b!r}"
    assert "daily" not in a and "daily" not in b


def test_script_path_still_wins_over_a_later_dash_m():
    """A real .py script token must keep priority -- don't regress the 92 live tasks."""
    import run_cmd_hidden as r
    assert r._derive_log_stem(["python", "setup/scripts/trade_autopsy.py", "-m", "x"]) == "trade_autopsy"


def test_dangling_dash_m_falls_back_without_raising():
    import run_cmd_hidden as r
    assert r._derive_log_stem(["python", "-m"])          # must not raise / not be empty
    assert r._derive_log_stem(["python", "-m", "--only-flags"])
