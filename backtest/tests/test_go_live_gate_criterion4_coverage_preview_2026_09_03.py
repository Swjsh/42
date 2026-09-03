"""Guard: go_live_gate.py criterion 4 (BEHAVIOURAL) coverage_preview -- ADDITIVE, disclosure
only (queue.md CRITERION-4-CANNOT-READ-ITS-OWN-AUDITOR, filed 2026-09-02; prereg
analysis/recommendations/prereg-criterion-4-coverage-read-2026-09-03.md, frozen 2026-09-03).

The bug this patches: criterion 4's staleness signal is rule-breaks.jsonl's file MTIME, and a
clean nightly audit (Gamma_RuleBreakAudit, shipped 4689dacd) correctly writes NOTHING on a
clean night -- so a genuinely-audited-and-clean window is indistinguishable from an abandoned
ledger, and the status sticks at PASS_UNVERIFIED forever. This build ships a PREVIEW of the
pre-registered fix (read rule-break-audit.json's coverage instead) WITHOUT changing the real
verdict -- the prereg's effective date for the real rule is 2026-09-29.

Covers exactly what the prereg's own proof obligation (section 5) requires:
  (a) mutation-proof -- with the coverage artifact present vs. deleted vs. corrupted, criterion
      4's real `pass` and `rule_breaks_in_window.status` stay byte-identical; only
      `coverage_preview` differs.
  (b) the preview flips as specified on synthetic artifacts: covers_window True/False,
      would_pass_under_prereg True only when (0 breaks) AND (covers_window) AND (rules
      disclosed).
  (c) build_report() carries the key at criteria.behavioural.coverage_preview, additive.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = str(REPO / "setup" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import go_live_gate as glg  # noqa: E402


def _write_audit(tmp_path, **overrides):
    payload = {
        "generated_at_et": "2026-09-03 01:36:05",
        "date_range": ["2026-06-21", "2026-09-02"],
        "rules_checked": {
            "RULE_1_NAMED_SETUP": "entry's setup is a named playbook pattern",
            "RULE_6_RISK_CAP": "position cost is within the arm's per-trade risk cap",
        },
        "rules_NOT_checked": {
            "RULE_9_NO_MIDSESSION_RULE_CHANGES": "no RTH open/close hash snapshot exists yet",
        },
    }
    payload.update(overrides)
    p = tmp_path / "rule-break-audit.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# --------------------------------------------------------------------------------------- #
# (a) mutation-proof -- real verdict byte-identical with artifact present/deleted/corrupted
# --------------------------------------------------------------------------------------- #
def test_real_behavioural_verdict_unchanged_when_artifact_present(tmp_path, monkeypatch):
    audit = _write_audit(tmp_path, date_range=["2026-08-05", "2026-09-02"])
    monkeypatch.setattr(glg, "RULE_BREAK_AUDIT_PATH", audit)
    monkeypatch.setattr(glg, "RULE_BREAKS_PATH", tmp_path / "does-not-exist-rule-breaks.jsonl")

    rows = [{"date": f"2026-08-{d:02d}", "attribution": "engine", "arm": "safe-3",
             "symbol": "SPY000000C00000000"} for d in range(5, 26)]
    baseline = glg.behavioural_criterion(rows, recon={"per_arm": {}})

    # now delete the artifact and re-run -- the real pass/status keys must not move.
    monkeypatch.setattr(glg, "RULE_BREAK_AUDIT_PATH", tmp_path / "gone.json")
    deleted = glg.behavioural_criterion(rows, recon={"per_arm": {}})

    # and corrupt it.
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(glg, "RULE_BREAK_AUDIT_PATH", corrupt)
    corrupted = glg.behavioural_criterion(rows, recon={"per_arm": {}})

    for other in (deleted, corrupted):
        assert other["pass"] == baseline["pass"]
        assert other["rule_breaks_in_window"]["status"] == baseline["rule_breaks_in_window"]["status"]
        assert other["rule_breaks_in_window"]["count"] == baseline["rule_breaks_in_window"]["count"]
        assert other["trailing_window"] == baseline["trailing_window"]
        assert other["manual_or_mixed_attribution_fills_in_window"] == \
            baseline["manual_or_mixed_attribution_fills_in_window"]

    # the preview itself DID change (proves the monkeypatch was live, not a no-op).
    assert deleted["coverage_preview"]["artifact_status"] == "missing"
    assert deleted["coverage_preview"]["would_pass_under_prereg"] is False
    assert corrupted["coverage_preview"]["artifact_status"] == "unreadable"
    assert corrupted["coverage_preview"]["would_pass_under_prereg"] is False
    assert baseline["coverage_preview"]["artifact_status"] == "ok"


def test_build_report_overall_verdict_unaffected_by_missing_coverage_artifact(tmp_path, monkeypatch):
    """Same proof at the build_report() level, per the prereg's 'run --no-refresh before and
    after, diff everything except the new key' obligation."""
    monkeypatch.setattr(glg, "RULE_BREAK_AUDIT_PATH", tmp_path / "gone.json")
    monkeypatch.setattr(glg, "operational_criterion", lambda: {"guards": {}, "pass": True})
    monkeypatch.setattr(glg, "reconciliation_criterion", lambda rows: {"per_arm": {}, "pass": True})
    monkeypatch.setattr(glg, "prod_shadow_criterion", lambda engine_rows: {"pass": False, "status": "NOT_WIRED"})
    monkeypatch.setattr(glg, "ACTIVE_ARMS", ["safe-3"])
    rows = [{"date": f"2026-08-{d:02d}", "attribution": "engine", "arm": "safe-3",
             "symbol": "SPY000000C00000000", "pnl_dollars": 10.0, "qty": 1.0, "exit_px_avg": 1.0}
            for d in range(5, 26)]
    monkeypatch.setattr(glg, "load_ledger_rows", lambda: rows)

    report = glg.build_report()
    assert "coverage_preview" in report["criteria"]["behavioural"]
    assert report["criteria"]["behavioural"]["coverage_preview"]["artifact_status"] == "missing"
    # the real gate byte is untouched by a missing preview artifact.
    assert report["criteria"]["behavioural"]["pass"] is True


# --------------------------------------------------------------------------------------- #
# (b) the preview flips exactly as specified on synthetic artifacts
# --------------------------------------------------------------------------------------- #
def test_covers_window_true_when_audited_range_spans_trailing_window():
    preview = glg.behavioural_coverage_preview(
        w_start="2026-08-05", w_end="2026-09-02", rb_in_window_count=0)
    # no monkeypatch here -- exercises the real repo artifact, which is present and covers a
    # very wide range; assert only the shape, not repo-state-dependent values.
    assert set(preview.keys()) == {
        "audited_range", "covers_window", "rules_checked", "rules_not_checked",
        "would_pass_under_prereg", "prereg_path", "artifact_status",
    }
    assert preview["prereg_path"] == \
        "analysis/recommendations/prereg-criterion-4-coverage-read-2026-09-03.md"


def test_covers_window_false_when_audited_range_starts_after_window(tmp_path, monkeypatch):
    audit = _write_audit(tmp_path, date_range=["2026-08-10", "2026-09-02"])
    monkeypatch.setattr(glg, "RULE_BREAK_AUDIT_PATH", audit)
    preview = glg.behavioural_coverage_preview(
        w_start="2026-08-05", w_end="2026-09-02", rb_in_window_count=0)
    assert preview["covers_window"] is False
    assert preview["would_pass_under_prereg"] is False
    assert preview["artifact_status"] == "ok"


def test_covers_window_false_when_audited_range_ends_before_window(tmp_path, monkeypatch):
    audit = _write_audit(tmp_path, date_range=["2026-06-21", "2026-08-20"])
    monkeypatch.setattr(glg, "RULE_BREAK_AUDIT_PATH", audit)
    preview = glg.behavioural_coverage_preview(
        w_start="2026-08-05", w_end="2026-09-02", rb_in_window_count=0)
    assert preview["covers_window"] is False
    assert preview["would_pass_under_prereg"] is False


def test_would_pass_under_prereg_false_when_breaks_in_window_even_if_covered(tmp_path, monkeypatch):
    audit = _write_audit(tmp_path, date_range=["2026-08-05", "2026-09-02"])
    monkeypatch.setattr(glg, "RULE_BREAK_AUDIT_PATH", audit)
    preview = glg.behavioural_coverage_preview(
        w_start="2026-08-05", w_end="2026-09-02", rb_in_window_count=1)
    assert preview["covers_window"] is True
    assert preview["would_pass_under_prereg"] is False  # (a) fails even though (b) holds


def test_would_pass_under_prereg_true_when_all_three_conditions_hold(tmp_path, monkeypatch):
    audit = _write_audit(tmp_path, date_range=["2026-08-05", "2026-09-02"])
    monkeypatch.setattr(glg, "RULE_BREAK_AUDIT_PATH", audit)
    preview = glg.behavioural_coverage_preview(
        w_start="2026-08-05", w_end="2026-09-02", rb_in_window_count=0)
    assert preview["covers_window"] is True
    assert preview["would_pass_under_prereg"] is True
    assert preview["rules_checked"]  # disclosed, non-empty


def test_empty_rules_checked_blocks_would_pass_even_if_covered(tmp_path, monkeypatch):
    """Condition (c) -- an artifact whose rules_checked is empty must never yield
    would_pass_under_prereg True, even with 0 breaks and full coverage."""
    audit = _write_audit(tmp_path, date_range=["2026-08-05", "2026-09-02"], rules_checked={})
    monkeypatch.setattr(glg, "RULE_BREAK_AUDIT_PATH", audit)
    preview = glg.behavioural_coverage_preview(
        w_start="2026-08-05", w_end="2026-09-02", rb_in_window_count=0)
    assert preview["would_pass_under_prereg"] is False


def test_missing_artifact_reports_status_missing_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(glg, "RULE_BREAK_AUDIT_PATH", tmp_path / "does-not-exist.json")
    preview = glg.behavioural_coverage_preview(
        w_start="2026-08-05", w_end="2026-09-02", rb_in_window_count=0)
    assert preview["artifact_status"] == "missing"
    assert preview["audited_range"] is None
    assert preview["covers_window"] is False
    assert preview["would_pass_under_prereg"] is False


def test_corrupted_artifact_reports_status_unreadable_not_a_crash(tmp_path, monkeypatch):
    bad = tmp_path / "rule-break-audit.json"
    bad.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(glg, "RULE_BREAK_AUDIT_PATH", bad)
    preview = glg.behavioural_coverage_preview(
        w_start="2026-08-05", w_end="2026-09-02", rb_in_window_count=0)
    assert preview["artifact_status"] == "unreadable"
    assert preview["would_pass_under_prereg"] is False


def test_non_dict_json_reports_status_unreadable(tmp_path, monkeypatch):
    weird = tmp_path / "rule-break-audit.json"
    weird.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(glg, "RULE_BREAK_AUDIT_PATH", weird)
    preview = glg.behavioural_coverage_preview(
        w_start="2026-08-05", w_end="2026-09-02", rb_in_window_count=0)
    assert preview["artifact_status"] == "unreadable"


# --------------------------------------------------------------------------------------- #
# (c) additive in build_report() -- key present, existing disclosure keys untouched
# --------------------------------------------------------------------------------------- #
def test_coverage_preview_additive_in_build_report(tmp_path, monkeypatch):
    audit = _write_audit(tmp_path, date_range=["2026-08-05", "2026-09-02"])
    monkeypatch.setattr(glg, "RULE_BREAK_AUDIT_PATH", audit)
    monkeypatch.setattr(glg, "ACTIVE_ARMS", ["safe-3"])
    monkeypatch.setattr(glg, "operational_criterion", lambda: {"guards": {}, "pass": True})
    monkeypatch.setattr(glg, "reconciliation_criterion", lambda rows: {"per_arm": {}, "pass": True})
    monkeypatch.setattr(glg, "prod_shadow_criterion", lambda engine_rows: {"pass": False, "status": "NOT_WIRED"})
    rows = [{"date": f"2026-08-{d:02d}", "attribution": "engine", "arm": "safe-3",
             "symbol": "SPY000000C00000000", "pnl_dollars": 10.0, "qty": 1.0, "exit_px_avg": 1.0}
            for d in range(5, 26)]
    monkeypatch.setattr(glg, "load_ledger_rows", lambda: rows)

    report = glg.build_report()
    b = report["criteria"]["behavioural"]
    assert "coverage_preview" in b
    # every pre-existing behavioural key is still present -- additive, not a replacement.
    assert {"trailing_window", "trailing_window_trading_days", "rule_breaks_in_window",
            "manual_or_mixed_attribution_fills_in_window", "sizing_up_events", "pass",
            "note"} <= set(b.keys())


def test_render_markdown_includes_coverage_preview_section(tmp_path, monkeypatch):
    audit = _write_audit(tmp_path, date_range=["2026-08-05", "2026-09-02"])
    monkeypatch.setattr(glg, "RULE_BREAK_AUDIT_PATH", audit)
    monkeypatch.setattr(glg, "ACTIVE_ARMS", ["safe-3"])
    monkeypatch.setattr(glg, "operational_criterion", lambda: {"guards": {}, "pass": True})
    monkeypatch.setattr(glg, "reconciliation_criterion", lambda rows: {"per_arm": {}, "pass": True})
    monkeypatch.setattr(glg, "prod_shadow_criterion",
                         lambda engine_rows: {"pass": False, "status": "NOT_WIRED", "note": "test fixture"})
    rows = [{"date": f"2026-08-{d:02d}", "attribution": "engine", "arm": "safe-3",
             "symbol": "SPY000000C00000000", "pnl_dollars": 10.0, "qty": 1.0, "exit_px_avg": 1.0}
            for d in range(5, 26)]
    monkeypatch.setattr(glg, "load_ledger_rows", lambda: rows)

    report = glg.build_report()
    md = glg.render_markdown(report)
    assert "Criterion 4 coverage preview" in md
    assert "would_pass_under_prereg=True" in md
