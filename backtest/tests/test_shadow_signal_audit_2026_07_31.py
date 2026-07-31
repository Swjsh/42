"""Guard for setup/scripts/shadow_signal_audit.py (2026-07-31 shadow-signal inventory).

WHAT THIS PINS -- the three mechanics that make the audit's output trustworthy. Each has
already produced a WRONG answer once during this build; these tests are the RED-proof that
the fixes hold.

1. SAME-FILE CALLSITES COUNT (for detectors). filters.py both defines AND calls
   detect_wick_reclaim_bullish. The first implementation discarded same-file hits as
   "the producer's own file", which reported EVERY live detector as having zero consumers
   -- it would have declared the entire live engine orphaned.

2. THE AUDIT MUST NOT COUNT ITSELF. Its REGISTRY names every symbol it tracks, so scanning
   its own source credits every orphan with one phantom consumer -- a self-fulfilling
   artifact that hid the one real orphan on the first run.

3. A MONITOR IS NOT A CONSUMER. engine_health.py reads a state file's mtime, not its
   content as a signal. Counting it would let a completely dead shadow file look wired
   purely because a health check watches it.

Plus the three invariants the instrument's honesty rests on:
4. SHADOW_BY_DESIGN on a live-path file requires a NAMED, EXISTING guard test; otherwise
   the claim is downgraded to UNPROVEN_SHADOW (L249: never take a docstring's word).
5. The script is FAIL-OPEN -- it is an instrument, never a gate (OP-25).
6. EVERY EMITTED STAMP IS REAL ET (added 2026-07-31 evening, after the verifier caught the
   bug). The first build used dt.datetime.now() -- bare MOUNTAIN local -- and rendered it
   with an " ET" suffix into the machine state, the inventory AUTOGEN header and STATUS.md.
   Every stamp was 2h early and mislabeled: the repo's most-scarred defect class.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "setup" / "scripts" / "shadow_signal_audit.py"
sys.path.insert(0, str(REPO / "setup" / "scripts"))
from et_clock import et_now  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location("shadow_signal_audit", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["shadow_signal_audit"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load()


def test_same_file_callsites_are_counted_for_detectors(mod):
    """filters.py defines AND calls its detectors -- those calls are real consumers.

    RED-PROOF: revert scan_references to skipping the producer's own file and this fails
    with n_live == 0, i.e. the live bull/bear scoring path reported as orphaned.
    """
    files = mod.iter_source_files()
    refs = mod.scan_references(files, "detect_level_reclaim", "backtest/lib/filters.py")
    assert refs["live"], (
        "detect_level_reclaim is called inside backtest/lib/filters.py (a LIVE_PATH_FILE); "
        f"the scan must count that same-file callsite. got live={refs['live']}"
    )
    assert any("filters.py" in h for h in refs["live"]), (
        f"expected the filters.py same-file callsite among live hits, got {refs['live']}"
    )


def test_definition_line_is_not_counted_as_a_consumer(mod):
    """A `def foo(` line is the producer, not a consumer of itself."""
    files = mod.iter_source_files()
    refs = mod.scan_references(files, "detect_candlestick_pattern_bullish",
                              "backtest/lib/filters.py")
    # NOTE: this guard file itself names the symbol, so a `tests` hit is expected and
    # correct. What must be empty is the set of REAL consumers -- live + research.
    real = refs["live"] + refs["research"]
    assert real == [], (
        "detect_candlestick_pattern_bullish has no live/research consumer anywhere; its "
        f"own `def` line must not register as one. got {real}"
    )


def test_audit_never_counts_itself_as_a_consumer(mod):
    """The REGISTRY names every tracked symbol -- scanning self would fake a consumer.

    RED-PROOF: delete the `rel == self_rel` skip in iter_source_files and this fails,
    because shadow_signal_audit.py names detect_candlestick_pattern_bullish in REGISTRY.
    """
    self_rel = SCRIPT.relative_to(REPO).as_posix()
    scanned = {p.relative_to(REPO).as_posix() for p in mod.iter_source_files()}
    assert self_rel not in scanned, "the audit must exclude its own source from the scan"


def test_monitor_files_are_not_consumers(mod):
    """A freshness monitor reads mtime, not the signal -- it must not mask a dead file."""
    assert "setup/scripts/engine_health.py" in mod.MONITOR_ONLY_FILES
    files = mod.iter_source_files()
    refs = mod.scan_references(files, "automation/state/confluence-zones.json",
                              "setup/scripts/confluence_producer.py", skip_own=True)
    for hit in refs["live"] + refs["research"]:
        assert not hit.startswith("setup/scripts/engine_health.py"), (
            f"engine_health.py is freshness-only and must be bucketed as a monitor, got {hit}"
        )


def test_shadow_claim_without_existing_guard_is_downgraded(mod):
    """SHADOW_BY_DESIGN on a live-path file demands a NAMED, EXISTING guard test."""
    live_refs = dict(live=["backtest/lib/filters.py:1"], research=[], tests=[], monitors=[])

    no_guard = dict(expected="SHADOW_BY_DESIGN", provenance="2026-07-15 some decision, no guard named")
    cls, _ = mod.classify(no_guard, live_refs)
    assert cls == "UNPROVEN_SHADOW", f"unnamed guard must downgrade, got {cls}"

    missing = dict(expected="SHADOW_BY_DESIGN",
                   provenance="2026-07-15 decision; guard test_this_guard_does_not_exist.py")
    cls, _ = mod.classify(missing, live_refs)
    assert cls == "UNPROVEN_SHADOW", f"non-existent guard must downgrade, got {cls}"

    real = dict(expected="SHADOW_BY_DESIGN",
                provenance="2026-07-15 decision; guard test_bull_trendline_wick_reclaim_shadow_only.py")
    cls, _ = mod.classify(real, live_refs)
    assert cls == "SHADOW_BY_DESIGN", f"existing named guard must hold, got {cls}"


def test_zero_consumer_without_decision_is_orphaned(mod):
    """No consumers + no dated decision = ORPHANED, whatever the registry wishes."""
    empty = dict(live=[], research=[], tests=[], monitors=[])
    cls, _ = mod.classify(dict(expected="SHADOW_BY_DESIGN", provenance=""), empty)
    assert cls == "ORPHANED", f"shadow claim with no decision must be ORPHANED, got {cls}"


def test_bh_fdr_controls_multiplicity():
    """Three signals tested at once: a lone p=0.04 must NOT survive q=0.10 unaided.

    Lives in the measurement script (shadow_signal_edge_2026_07_31.py), which is what
    actually adjudicates the promotion verdict across all three shadow signals.
    """
    spec = importlib.util.spec_from_file_location(
        "shadow_edge", REPO / "backtest" / "tools" / "shadow_signal_edge_2026_07_31.py")
    edge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(edge)
    assert edge.bh_fdr([0.04, 0.60, 0.90], q=0.10) == [False, False, False]
    assert edge.bh_fdr([0.001, 0.002, 0.90], q=0.10)[:2] == [True, True]
    # p must never be reported as exactly 0 from a 30-sample screen (erfc underflow)
    assert edge.one_sample_p([-50.0] * 30) >= 1e-16


def test_audit_is_fail_open(mod):
    """An instrument must never block a session or a scheduled fire (OP-25)."""
    # main() is not invoked here: it rewrites automation/state + STATUS.md. Pin the
    # contract structurally instead -- no raise, no non-zero exit, on any code path.
    src = SCRIPT.read_text(encoding="utf-8")
    assert "return 0  # ALWAYS fail-open" in src, "main() must unconditionally return 0"
    assert "raise SystemExit(main())" in src
    assert "sys.exit(1)" not in src and "SystemExit(1)" not in src, (
        "the audit must never exit non-zero -- it is an instrument, not a gate"
    )


def test_first_run_seeds_baseline_silently(mod, tmp_path, monkeypatch):
    """A monitor that shouts 29 lines on day one teaches the reader to ignore it (C18).

    RED-PROOF: remove the `if not OUT_JSON.exists(): return None` baseline guard and this
    fails -- the first run appends a STATUS.md line listing every pre-existing orphan.
    """
    monkeypatch.setattr(mod, "OUT_JSON", tmp_path / "never-written.json")
    monkeypatch.setattr(mod, "STATUS_MD", tmp_path / "STATUS.md")
    spoke = mod.fail_loud_on_transition(
        dict(generated_at_et="2026-07-31T00:00:00", orphan_ids=["a", "b"],
             drift_ids=["c"], unregistered=[dict(module="m.py", symbol="detect_x")]))
    assert spoke is None, "first run must seed the baseline without shouting"
    assert not (tmp_path / "STATUS.md").exists(), "first run must not touch STATUS.md"


# ---------------------------------------------------------------------------
# 6. EVERY EMITTED STAMP IS REAL ET  (TZ-SYSTEMIC scar -- CLAUDE.md, C9/L-TZ)
# ---------------------------------------------------------------------------
def test_generated_stamp_is_real_ET(mod, monkeypatch):
    """build_report()'s `generated_at_et` must match et_clock ET within 60s.

    This is the END-TO-END assertion: it runs the REAL build_report and reads the REAL
    field that gets written to automation/state/shadow-signal-audit.json, spliced into
    the inventory AUTOGEN header and appended to STATUS.md -- all three rendered with an
    " ET" suffix. The scan itself is stubbed out (empty registry / no source files) so
    the guard costs milliseconds; the timestamp path is untouched and fully exercised.

    RED-PROOF: revert stamp_et() to `dt.datetime.now().strftime(...)` and this fails on
    this rig with a ~7200s delta (box is MOUNTAIN time; ET = local + 2h).
    """
    monkeypatch.setattr(mod, "REGISTRY", [])
    monkeypatch.setattr(mod, "SCAN_MODULES", ())
    monkeypatch.setattr(mod, "iter_source_files", lambda: [])

    rep = mod.build_report()
    stamp = dt.datetime.strptime(rep["generated_at_et"], "%Y-%m-%dT%H:%M:%S")
    delta = abs((stamp - et_now()).total_seconds())
    assert delta <= 60, (
        f"generated_at_et={rep['generated_at_et']} is {delta:.0f}s from et_clock ET "
        f"({et_now():%Y-%m-%dT%H:%M:%S}). Every emitted stamp carries an ' ET' suffix, so "
        "it MUST come from et_clock.et_now() -- this rig is on Mountain time and bare "
        "dt.datetime.now() reads 2h early (7200s)."
    )


def test_stamp_et_is_the_single_source_and_uses_et_clock(mod):
    """One stamping helper, wired to the canonical clock -- not a second local-now copy.

    Behavioral half: stamp_et() itself tracks et_now(). Structural half: the emitter does
    not reintroduce a rendered local-time stamp elsewhere (a `.timestamp()` epoch delta is
    timezone-invariant and stays legal).
    """
    delta = abs((dt.datetime.strptime(mod.stamp_et(), "%Y-%m-%dT%H:%M:%S")
                 - et_now()).total_seconds())
    assert delta <= 60, f"stamp_et() is {delta:.0f}s off et_clock ET"

    src = SCRIPT.read_text(encoding="utf-8")
    assert "from et_clock import et_now" in src, "must import the canonical DST-aware clock"
    assert "dt.datetime.now().strftime" not in src, (
        "a RENDERED stamp must never come from local time -- use stamp_et()"
    )


def test_status_line_and_autogen_carry_the_ET_stamp(mod, tmp_path, monkeypatch):
    """The two human-facing surfaces must print the stamp they were handed, with ' ET'."""
    rep = dict(generated_at_et="2026-07-31T18:44:27", n_registered=0, n_orphaned=1,
               n_drift=0, n_unregistered=0, orphan_ids=["x"], drift_ids=[],
               rows=[], unregistered=[])
    assert "2026-07-31T18:44:27 ET" in mod.render_autogen(rep)

    monkeypatch.setattr(mod, "OUT_JSON", tmp_path / "prev.json")
    (tmp_path / "prev.json").write_text('{"orphan_ids": [], "drift_ids": [], '
                                        '"unregistered": []}', encoding="utf-8")
    monkeypatch.setattr(mod, "STATUS_MD", tmp_path / "STATUS.md")
    (tmp_path / "STATUS.md").write_text("# S\n## Known broken\n", encoding="utf-8")
    line = mod.fail_loud_on_transition(rep)
    assert line is not None and line.startswith("- [2026-07-31T18:44:27 ET] "), line
