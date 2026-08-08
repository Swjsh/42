"""Guard: setup/scripts/gate_recency_report.py -- THE GATE-RECENCY WEEKLY INSTRUMENT
(J directive 2026-08-08: the gate-recency audit that found money-blocking stale gates must
become permanent doctrine + a standing instrument that keeps running).

Pin, in order:
  1. GATE_ROSTER static sanity -- unique ids, required keys, known count_rule kinds.
  2. fail-open loaders -- each source (registry / status / params / decisions ledger)
     independently degrades to a safe empty default on a missing/malformed file.
  3. load_window_rows -- trailing-N distinct armed=true trading day windowing.
  4. block-count mining -- field_equals / sole_blocker / extra_fired / fixed_zero, each
     correctly scoped per account.
  5. provenance resolution -- registry preferred over the audit-ported fallback; unknown
     provenance falls back to the 180-day proxy.
  6. recommendation logic -- dead_config, force_recommendation, force_if_blocked,
     blocks==0, RED, stale-and-blocked, fresh-and-blocked.
  7. build_rows / build_digest -- RED-first digest with EV note, WATCH fallback sorted by
     staleness_score, the empty-week reassurance line, schema stability on every row.
  8. build_report / main -- end-to-end from fixture files (present AND fully missing),
     --dry-run performs zero disk writes, a real run writes valid schema-stable JSON.
  9. static guard: read-only, never writes params.json / places an order.

Every module-level Path constant is monkeypatched onto tmp_path fixtures -- no test here
ever depends on this repo's real automation/state/* files (which change every session).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    p = str(REPO / _p) if _p else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

import gate_recency_report as grr  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────────────

def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""), encoding="utf-8")


def _decision_row(date: str, account: str, *, armed: bool = True, verdict: str = "HOLD",
                   action: str = "HOLD", bull_blockers=None, bear_blockers=None,
                   extra_signals=None, time: str = "10:15:00") -> dict:
    return {
        "ts_et": f"{date}T{time}",
        "account": account,
        "armed": armed,
        "verdict": verdict,
        "action": action,
        "bull_blockers": bull_blockers or [],
        "bear_blockers": bear_blockers or [],
        "extra_signals": extra_signals or [],
    }


REQUIRED_ROW_KEYS = {
    "name", "account", "setting", "last_validated", "days_stale", "blocks_15d",
    "expiry_verdict", "staleness_score", "recommendation", "category", "provenance",
    "red_ev_note",
}


@pytest.fixture
def state_paths(tmp_path, monkeypatch):
    paths = {
        "registry": tmp_path / "gate-registry.json",
        "status": tmp_path / "gate-registry-status.json",
        "params_safe": tmp_path / "params.json",
        "params_bold": tmp_path / "aggressive" / "params.json",
        "decisions": tmp_path / "core-decisions.jsonl",
        "out": tmp_path / "gate-recency-latest.json",
    }
    monkeypatch.setattr(grr, "GATE_REGISTRY", paths["registry"])
    monkeypatch.setattr(grr, "GATE_REGISTRY_STATUS", paths["status"])
    monkeypatch.setattr(grr, "PARAMS_SAFE", paths["params_safe"])
    monkeypatch.setattr(grr, "PARAMS_BOLD", paths["params_bold"])
    monkeypatch.setattr(grr, "CORE_DECISIONS", paths["decisions"])
    monkeypatch.setattr(grr, "OUT_JSON", paths["out"])
    return paths


# ─────────────────────────────────────────────────────────────────────────────
# 1. GATE_ROSTER static sanity
# ─────────────────────────────────────────────────────────────────────────────

_KNOWN_COUNT_KINDS = {"field_equals", "sole_blocker", "extra_fired", "fixed_zero"}


def test_roster_ids_are_unique():
    ids = [spec["id"] for spec in grr.GATE_ROSTER]
    assert len(ids) == len(set(ids)), "duplicate gate id in GATE_ROSTER"


def test_roster_ported_from_the_2026_08_08_audit_ranked_table():
    """The mission's own template -- every gate the audit ranked (all 17 rows) must have
    a roster row, so the weekly instrument never regresses to a narrower scope than the
    one-off audit that motivated it."""
    audited_ids = {
        "block_level_rejection", "filter_9_vol_multiplier", "filter_10_min_triggers_bull",
        "require_bearish_fill_bar", "extra_setup_exec_armed.vwap_continuation",
        "block_conf_lvl_rec_afternoon", "structure_veto_enabled", "free_model_veto",
        "entry_bar_body_pct_min", "block_bull_1100_1200",
        "extra_setup_exec_armed.vix_regime_dayside", "pdt_gate_mode",
        "block_level_rejection", "block_elite_bull", "liquidity_gate_bundle",
        "macro_veto_bundle", "vix_bear_hard_cap", "min_entry_premium",
    }
    roster_ids = {spec["id"] for spec in grr.GATE_ROSTER}
    missing = audited_ids - roster_ids
    assert not missing, f"gates from the 2026-08-08 audit missing from GATE_ROSTER: {missing}"


def test_roster_every_entry_has_required_shape():
    for spec in grr.GATE_ROSTER:
        assert "id" in spec and spec["id"]
        assert "category" in spec
        assert isinstance(spec.get("accounts"), dict) and spec["accounts"]
        assert isinstance(spec.get("setting_fallback"), dict)
        rule = spec.get("count_rule")
        assert isinstance(rule, dict) and rule.get("kind") in _KNOWN_COUNT_KINDS
        for acct in spec["accounts"]:
            assert acct in ("safe", "bold")


def test_roster_dead_config_gates_use_fixed_zero_rule():
    for spec in grr.GATE_ROSTER:
        if spec["category"] == "dead_config":
            assert spec["count_rule"]["kind"] == "fixed_zero"


# ─────────────────────────────────────────────────────────────────────────────
# 2. fail-open loaders
# ─────────────────────────────────────────────────────────────────────────────

def test_load_registry_missing_file_degrades_to_empty(state_paths):
    assert grr.load_registry() == {"gates": []}


def test_load_registry_malformed_json_degrades_to_empty(state_paths):
    state_paths["registry"].parent.mkdir(parents=True, exist_ok=True)
    state_paths["registry"].write_text("{not valid json", encoding="utf-8")
    assert grr.load_registry() == {"gates": []}


def test_load_status_missing_file_degrades_to_empty(state_paths):
    assert grr.load_status() == {"gates": {}}


def test_load_status_malformed_json_degrades_to_empty(state_paths):
    state_paths["status"].parent.mkdir(parents=True, exist_ok=True)
    state_paths["status"].write_text("not json at all", encoding="utf-8")
    assert grr.load_status() == {"gates": {}}


def test_load_params_missing_files_degrade_to_empty_per_account(state_paths):
    assert grr.load_params() == {"safe": {}, "bold": {}}


def test_load_params_one_account_present_other_missing(state_paths):
    _write_json(state_paths["params_safe"], {"block_level_rejection": True})
    out = grr.load_params()
    assert out["safe"] == {"block_level_rejection": True}
    assert out["bold"] == {}


def test_load_window_rows_missing_ledger_returns_empty(state_paths):
    rows, dates = grr.load_window_rows(state_paths["decisions"], 15)
    assert rows == []
    assert dates == []


def test_load_window_rows_empty_ledger_file_returns_empty(state_paths):
    state_paths["decisions"].parent.mkdir(parents=True, exist_ok=True)
    state_paths["decisions"].write_text("", encoding="utf-8")
    rows, dates = grr.load_window_rows(state_paths["decisions"], 15)
    assert rows == []
    assert dates == []


def test_load_window_rows_skips_unparseable_lines(state_paths, tmp_path):
    path = tmp_path / "decisions.jsonl"
    good = _decision_row("2026-08-01", "safe")
    path.write_text("not json\n" + json.dumps(good) + "\n\n", encoding="utf-8")
    rows, dates = grr.load_window_rows(path, 15)
    assert len(rows) == 1
    assert dates == ["2026-08-01"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. load_window_rows -- trailing-N distinct armed=true trading day windowing
# ─────────────────────────────────────────────────────────────────────────────

def test_load_window_rows_keeps_only_last_n_distinct_armed_dates(tmp_path):
    path = tmp_path / "decisions.jsonl"
    rows = []
    for day in range(1, 21):  # 20 distinct trading days, 08-01..08-20
        rows.append(_decision_row(f"2026-08-{day:02d}", "safe"))
    _write_jsonl(path, rows)
    window_rows, dates = grr.load_window_rows(path, 15)
    assert len(dates) == 15
    assert dates[0] == "2026-08-06"   # the 6th day is the earliest of the last 15
    assert dates[-1] == "2026-08-20"
    assert len(window_rows) == 15


def test_load_window_rows_excludes_armed_false_rows_from_date_set(tmp_path):
    path = tmp_path / "decisions.jsonl"
    rows = [
        _decision_row("2026-08-01", "safe", armed=False),  # off-hours/diagnostic -- excluded
        _decision_row("2026-08-02", "safe", armed=True),
    ]
    _write_jsonl(path, rows)
    window_rows, dates = grr.load_window_rows(path, 15)
    assert dates == ["2026-08-02"]
    assert len(window_rows) == 1


def test_load_window_rows_fewer_than_n_days_available_uses_what_exists(tmp_path):
    path = tmp_path / "decisions.jsonl"
    rows = [_decision_row("2026-08-01", "safe"), _decision_row("2026-08-02", "safe")]
    _write_jsonl(path, rows)
    window_rows, dates = grr.load_window_rows(path, 15)
    assert dates == ["2026-08-01", "2026-08-02"]
    assert len(window_rows) == 2


def test_load_window_rows_zero_lookback_is_empty_not_python_negative_slice_bug(tmp_path):
    """lst[-0:] == lst[0:] in Python -- a naive slice would silently return EVERYTHING for
    --lookback-days 0 instead of nothing. Pin the guard explicitly."""
    path = tmp_path / "decisions.jsonl"
    _write_jsonl(path, [_decision_row("2026-08-01", "safe")])
    window_rows, dates = grr.load_window_rows(path, 0)
    assert window_rows == []
    assert dates == []


# ─────────────────────────────────────────────────────────────────────────────
# 4. block-count mining
# ─────────────────────────────────────────────────────────────────────────────

def test_count_blocks_field_equals_scopes_by_account():
    rows = [
        _decision_row("2026-08-01", "safe", verdict="SKIP_LEVEL_REJECTION_GATE"),
        _decision_row("2026-08-01", "bold", verdict="SKIP_LEVEL_REJECTION_GATE"),
        _decision_row("2026-08-01", "safe", verdict="HOLD"),
    ]
    rule = {"kind": "field_equals", "field": "verdict", "value": "SKIP_LEVEL_REJECTION_GATE"}
    assert grr.count_blocks(rows, "safe", rule) == 1
    assert grr.count_blocks(rows, "bold", rule) == 1


def test_count_blocks_sole_blocker_requires_exact_single_element_list():
    rows = [
        _decision_row("2026-08-01", "safe", bull_blockers=[11]),        # sole blocker -> counts
        _decision_row("2026-08-01", "safe", bull_blockers=[7, 10, 11]), # co-fired -> does NOT count
        _decision_row("2026-08-01", "safe", bull_blockers=[]),
    ]
    rule = {"kind": "sole_blocker", "field": "bull_blockers", "index": 11}
    assert grr.count_blocks(rows, "safe", rule) == 1


def test_count_blocks_extra_fired_matches_setup_name_and_fired_true():
    rows = [
        _decision_row("2026-08-01", "safe", extra_signals=[
            {"setup_name": "vwap_continuation", "fired": True},
            {"setup_name": "gap_and_go", "fired": False},
        ]),
        _decision_row("2026-08-01", "safe", extra_signals=[
            {"setup_name": "vwap_continuation", "fired": False, "skip_reason": "SKIP_NO_SIGNAL"},
        ]),
    ]
    rule = {"kind": "extra_fired", "setup_name": "vwap_continuation"}
    assert grr.count_blocks(rows, "safe", rule) == 1


def test_count_blocks_fixed_zero_ignores_row_content():
    rows = [_decision_row("2026-08-01", "safe", verdict="ANYTHING")]
    assert grr.count_blocks(rows, "safe", {"kind": "fixed_zero"}) == 0


def test_count_blocks_empty_rows_is_zero_not_an_error():
    rule = {"kind": "field_equals", "field": "verdict", "value": "SKIP_LEVEL_REJECTION_GATE"}
    assert grr.count_blocks([], "safe", rule) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. provenance / setting resolution
# ─────────────────────────────────────────────────────────────────────────────

def test_live_setting_prefers_live_params_value():
    params = {"safe": {"filter_10_min_triggers_bull": 2}}
    val = grr._live_setting(params, "safe", "filter_10_min_triggers_bull", None, fallback=999)
    assert val == 2


def test_live_setting_falls_back_when_key_absent():
    params = {"safe": {}}
    val = grr._live_setting(params, "safe", "filter_10_min_triggers_bull", None, fallback=2)
    assert val == 2


def test_live_setting_nested_key_lookup():
    params = {"safe": {"extra_setup_exec_armed": {"vwap_continuation": False}}}
    val = grr._live_setting(params, "safe", "extra_setup_exec_armed", "vwap_continuation", fallback=True)
    assert val is False


def test_live_setting_nested_key_missing_falls_back():
    params = {"safe": {"extra_setup_exec_armed": {}}}
    val = grr._live_setting(params, "safe", "extra_setup_exec_armed", "vwap_continuation", fallback=False)
    assert val is False


def test_live_setting_no_params_key_returns_fallback():
    assert grr._live_setting({"safe": {"x": 1}}, "safe", None, None, fallback="Y") == "Y"


def test_days_stale_parses_iso_prefix():
    assert grr._days_stale("2026-07-10", dt.date(2026, 8, 8)) == 29


def test_days_stale_none_when_missing():
    assert grr._days_stale(None, dt.date(2026, 8, 8)) is None


def test_days_stale_none_when_malformed():
    assert grr._days_stale("not-a-date", dt.date(2026, 8, 8)) is None


# ─────────────────────────────────────────────────────────────────────────────
# 6. recommendation logic
# ─────────────────────────────────────────────────────────────────────────────

def test_recommend_dead_config_is_always_retire_candidate():
    spec = {"category": "dead_config"}
    assert grr._recommend(spec, expiry_verdict="GREEN", blocks=0, days_stale=None, interval_days=None) == "RETIRE-CANDIDATE"


def test_recommend_force_recommendation_wins():
    spec = {"category": "core_gate_order", "force_recommendation": "KEEP-MONITOR-TRIAL"}
    assert grr._recommend(spec, "GREEN", blocks=50, days_stale=200, interval_days=14) == "KEEP-MONITOR-TRIAL"


def test_recommend_force_if_blocked_only_when_blocks_positive():
    spec = {"category": "risk_gate_config", "force_if_blocked": "ACT-ON-PENDING-DECISION"}
    assert grr._recommend(spec, "GREEN", blocks=5, days_stale=2, interval_days=21) == "ACT-ON-PENDING-DECISION"
    # zero blocks -> falls through to the ordinary KEEP rule, not stuck on the special case
    assert grr._recommend(spec, "GREEN", blocks=0, days_stale=2, interval_days=21) == "KEEP"


def test_recommend_zero_blocks_is_keep():
    spec = {"category": "core_gate_order"}
    assert grr._recommend(spec, "STALE_UNVERIFIED", blocks=0, days_stale=500, interval_days=21) == "KEEP"


def test_recommend_red_verdict_is_revalidate():
    spec = {"category": "core_gate_order"}
    assert grr._recommend(spec, "RED", blocks=10, days_stale=5, interval_days=21) == "REVALIDATE"


def test_recommend_stale_and_still_blocking_is_revalidate():
    spec = {"category": "core_gate_order"}
    assert grr._recommend(spec, "GREEN", blocks=3, days_stale=99, interval_days=21) == "REVALIDATE"


def test_recommend_fresh_and_blocking_is_keep():
    spec = {"category": "core_gate_order"}
    assert grr._recommend(spec, "GREEN", blocks=3, days_stale=5, interval_days=21) == "KEEP"


# ─────────────────────────────────────────────────────────────────────────────
# 7. build_rows / build_digest
# ─────────────────────────────────────────────────────────────────────────────

_MINI_ROSTER = [
    {
        "id": "_test_gate_a",
        "category": "core_gate_order",
        "params_key": "test_gate_a",
        "count_rule": {"kind": "field_equals", "field": "verdict", "value": "SKIP_TEST_GATE_A"},
        "accounts": {"safe": True, "bold": False},
        "setting_fallback": {"safe": True},
        "audit_last_validated": "2026-06-01",
        "audit_interval_days": 21,
    },
    {
        "id": "_test_gate_b",
        "category": "scoring_filter",
        "params_key": None,
        "count_rule": {"kind": "sole_blocker", "field": "bull_blockers", "index": 3},
        "accounts": {"safe": True, "bold": True},
        "setting_fallback": {"safe": 2, "bold": 1},
        "audit_last_validated": None,
        "audit_interval_days": 21,
    },
]


def test_build_rows_schema_stability():
    window_rows = [_decision_row("2026-08-01", "safe", verdict="SKIP_TEST_GATE_A")]
    rows = grr.build_rows(_MINI_ROSTER, {}, {}, {"safe": {}, "bold": {}}, window_rows, dt.date(2026, 8, 8))
    assert len(rows) == 3  # gate_a/safe + gate_b/safe + gate_b/bold
    for row in rows:
        assert set(row.keys()) == REQUIRED_ROW_KEYS


def test_build_rows_registry_provenance_overrides_audit_fallback():
    registry_by_id = {"_test_gate_a": {"last_revalidated": "2026-08-01", "revalidation_interval_days": 5}}
    rows = grr.build_rows(_MINI_ROSTER, registry_by_id, {}, {"safe": {}, "bold": {}}, [], dt.date(2026, 8, 8))
    row = next(r for r in rows if r["name"] == "_test_gate_a")
    assert row["last_validated"] == "2026-08-01"
    assert row["days_stale"] == 7
    assert row["provenance"] == "registry"


def test_build_rows_unknown_provenance_uses_180_day_proxy():
    rows = grr.build_rows(_MINI_ROSTER, {}, {}, {"safe": {}, "bold": {}}, [], dt.date(2026, 8, 8))
    row = next(r for r in rows if r["name"] == "_test_gate_b" and r["account"] == "safe")
    assert row["last_validated"] is None
    assert row["days_stale"] == 180
    assert row["provenance"] == "unknown_180d_proxy"


def test_build_rows_staleness_score_is_days_times_blocks():
    window_rows = [_decision_row("2026-08-01", "safe", verdict="SKIP_TEST_GATE_A")] * 4
    registry_by_id = {"_test_gate_a": {"last_revalidated": "2026-07-01", "revalidation_interval_days": 5}}
    rows = grr.build_rows(_MINI_ROSTER, registry_by_id, {}, {"safe": {}, "bold": {}}, window_rows, dt.date(2026, 8, 8))
    row = next(r for r in rows if r["name"] == "_test_gate_a")
    assert row["blocks_15d"] == 4
    assert row["days_stale"] == 38
    assert row["staleness_score"] == 152


def test_build_rows_red_detection_and_ev_note_from_status():
    status_by_id = {
        "_test_gate_a": {
            "overall": "RED",
            "pnl_check": {"reason": "refused cohort would have EARNED $99.00/tr, n=12 -- COSTING money"},
        }
    }
    rows = grr.build_rows(_MINI_ROSTER, {}, status_by_id, {"safe": {}, "bold": {}}, [], dt.date(2026, 8, 8))
    row = next(r for r in rows if r["name"] == "_test_gate_a")
    assert row["expiry_verdict"] == "RED"
    assert "COSTING money" in row["red_ev_note"]


def test_build_rows_gate_not_in_expiry_checker_is_labeled_explicitly():
    rows = grr.build_rows(_MINI_ROSTER, {}, {}, {"safe": {}, "bold": {}}, [], dt.date(2026, 8, 8))
    row = next(r for r in rows if r["name"] == "_test_gate_b" and r["account"] == "safe")
    assert row["expiry_verdict"] == "NOT_IN_EXPIRY_CHECKER"
    assert row["red_ev_note"] is None


def test_build_rows_live_setting_read_from_params():
    params = {"safe": {"test_gate_a": False}, "bold": {}}
    rows = grr.build_rows(_MINI_ROSTER, {}, {}, params, [], dt.date(2026, 8, 8))
    row = next(r for r in rows if r["name"] == "_test_gate_a")
    assert row["setting"] is False  # live value, not the True fallback


def test_build_digest_names_red_gate_and_ev():
    rows = [{
        "name": "structure_veto_enabled", "account": "safe", "expiry_verdict": "RED",
        "red_ev_note": "refused cohort would have EARNED $32.69/tr, n=11 -- COSTING money",
        "recommendation": "REVALIDATE", "staleness_score": 1000, "blocks_15d": 10, "days_stale": 43,
    }]
    digest = grr.build_digest(rows)
    assert len(digest) == 1
    assert "structure_veto_enabled" in digest[0]
    assert "$32.69/tr" in digest[0]


def test_build_digest_caps_at_max_lines_and_prioritizes_red():
    rows = [
        {"name": f"red_{i}", "account": "safe", "expiry_verdict": "RED",
         "red_ev_note": f"note {i}", "recommendation": "REVALIDATE",
         "staleness_score": 100, "blocks_15d": 5, "days_stale": 20}
        for i in range(5)
    ]
    digest = grr.build_digest(rows, max_lines=3)
    assert len(digest) == 3
    assert all("RED --" in line for line in digest)


def test_build_digest_fills_remaining_slots_with_top_staleness_watch_rows():
    rows = [
        {"name": "red_gate", "account": "bold", "expiry_verdict": "RED",
         "red_ev_note": "costing money", "recommendation": "REVALIDATE",
         "staleness_score": 500, "blocks_15d": 5, "days_stale": 100},
        {"name": "low_stale_watch", "account": "safe", "expiry_verdict": "GREEN",
         "red_ev_note": None, "recommendation": "REVALIDATE",
         "staleness_score": 50, "blocks_15d": 1, "days_stale": 50},
        {"name": "high_stale_watch", "account": "safe", "expiry_verdict": "STALE_UNVERIFIED",
         "red_ev_note": None, "recommendation": "REVALIDATE",
         "staleness_score": 9999, "blocks_15d": 99, "days_stale": 101},
        {"name": "quiet_gate", "account": "safe", "expiry_verdict": "GREEN",
         "red_ev_note": None, "recommendation": "KEEP",
         "staleness_score": 0, "blocks_15d": 0, "days_stale": 5},
    ]
    digest = grr.build_digest(rows, max_lines=3)
    assert digest[0].startswith("RED -- red_gate")
    assert "high_stale_watch" in digest[1]  # higher staleness_score comes before low_stale_watch
    assert "low_stale_watch" in digest[2]


def test_build_digest_empty_week_gets_reassurance_line():
    rows = [{
        "name": "quiet_gate", "account": "safe", "expiry_verdict": "GREEN",
        "red_ev_note": None, "recommendation": "KEEP",
        "staleness_score": 0, "blocks_15d": 0, "days_stale": 5,
    }]
    digest = grr.build_digest(rows)
    assert len(digest) == 1
    assert "No RED" in digest[0]


# ─────────────────────────────────────────────────────────────────────────────
# 8. build_report / main -- end to end, including full-missing-input safety
# ─────────────────────────────────────────────────────────────────────────────

def test_build_report_all_sources_missing_is_empty_input_safe(state_paths):
    """The exact 'empty-input safe' bar from the build spec: every source absent must still
    produce a schema-complete report, never raise."""
    report = grr.build_report(lookback_days=15, today=dt.date(2026, 8, 8))
    assert report["schema"] == "gate-recency-report-v1"
    assert report["window"]["distinct_armed_dates_found"] == 0
    assert isinstance(report["gates"], list) and len(report["gates"]) > 0
    for row in report["gates"]:
        assert row["blocks_15d"] == 0
    assert report["reds"] == []
    assert len(report["digest"]) >= 1


def test_build_report_real_fixture_surfaces_a_red_gate(state_paths):
    _write_json(state_paths["registry"], {"gates": [
        {"id": "structure_veto_enabled", "last_revalidated": "2026-06-26", "revalidation_interval_days": 21},
    ]})
    _write_json(state_paths["status"], {"gates": {
        "structure_veto_enabled": {
            "overall": "RED",
            "pnl_check": {"reason": "refused cohort would have EARNED $32.69/tr, n=11 -- COSTING money"},
        },
    }})
    _write_json(state_paths["params_safe"], {"structure_veto_enabled": True})
    rows = [
        _decision_row("2026-08-01", "safe", verdict="SKIP_STRUCTURE_VETO"),
        _decision_row("2026-08-02", "safe", verdict="SKIP_STRUCTURE_VETO"),
    ]
    _write_jsonl(state_paths["decisions"], rows)

    report = grr.build_report(lookback_days=15, today=dt.date(2026, 8, 8))
    red_names = {r["name"] for r in report["reds"]}
    assert "structure_veto_enabled" in red_names
    assert any("COSTING money" in line for line in report["digest"])


def test_main_dry_run_writes_no_file(state_paths, capsys):
    rc = grr.main(["--dry-run"])
    assert rc == 0
    assert not state_paths["out"].exists()
    captured = capsys.readouterr()
    assert "no file written" in captured.out


def test_main_real_run_writes_valid_schema_stable_json(state_paths, capsys):
    rc = grr.main([])
    assert rc == 0
    assert state_paths["out"].exists()
    doc = json.loads(state_paths["out"].read_text(encoding="utf-8"))
    assert doc["schema"] == "gate-recency-report-v1"
    for key in ("generated_et", "window", "gates", "reds", "digest"):
        assert key in doc


def test_main_lookback_days_flag_is_honored(state_paths):
    rows = [_decision_row(f"2026-08-{d:02d}", "safe") for d in range(1, 6)]
    _write_jsonl(state_paths["decisions"], rows)
    rc = grr.main(["--lookback-days", "3", "--dry-run"])
    assert rc == 0  # exercised via CLI path; window correctness itself covered above


# ─────────────────────────────────────────────────────────────────────────────
# 9. static guard -- read-only, never places an order or writes params
# ─────────────────────────────────────────────────────────────────────────────

def test_module_never_writes_params_or_places_orders():
    src = (REPO / "setup" / "scripts" / "gate_recency_report.py").read_text(encoding="utf-8")
    forbidden = [
        "place_option_order", "place_stock_order", "risk_gate.check_order(",
        'params.json", "w', 'aggressive/params.json", "w', "PARAMS_SAFE.write",
        "PARAMS_BOLD.write",
    ]
    for token in forbidden:
        assert token not in src, f"gate_recency_report.py must never contain {token!r}"
