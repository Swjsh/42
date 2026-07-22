"""Guards for prospector.py -- Gamma_Prospector, the exogenous-idea organ (J
2026-07-09: "gamma hasn't introduced a single new idea like this at all yet").

Pure-logic + isolated-I/O tests only -- NO network (scan_beat's provider call is
always injected via scan_fn/call_fn). Covers the 4 explicitly-required
guarantees plus the promotion/rendering contract:

  1. Ledger idempotency/dedupe (by dedupe_key).
  2. A killed idea can NEVER re-enter the ledger or be (re-)promoted.
  3. Beat rotation cycles through all 7 beats and wraps.
  4. Fail-open: every model failing (no free lane up) still exits cleanly with
     the ledger fully intact and readable -- never raises.
  5. The promoted _chef-inbox/*.md stub matches the REAL consumer's expected
     format. Project Gamma's task brief named `queue.md` / `cook-queue.jsonl` /
     `_skill-inbox`-style as the candidate intakes to inspect; this module
     promotes into `_chef-inbox/` instead (see PROSPECTOR-SPEC.md for the
     citation of why), so the format fixture here is built from the REAL
     `strategy/candidates/_chef-inbox/README.md` item template rather than
     queue.md's.

House convention: import the module under test by file path (matches
test_trade_autopsy.py / test_firm_brief_autopsy_staleness.py / test_broker_fills.py).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "prospector", REPO / "setup" / "scripts" / "prospector.py")
pr = importlib.util.module_from_spec(_SPEC)
sys.modules["prospector"] = pr
_SPEC.loader.exec_module(pr)

CHEF_INBOX_README = REPO / "strategy" / "candidates" / "_chef-inbox" / "README.md"


# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers
# ─────────────────────────────────────────────────────────────────────────────


def test_slugify_basic():
    assert pr._slugify("Track VIX1D as a gate!!") == "track-vix1d-as-a-gate"
    assert pr._slugify("") == "untitled"
    assert pr._slugify("---") == "untitled"


def test_make_dedupe_key_stable_and_beat_namespaced():
    k1 = pr.make_dedupe_key("options_structure_metrics", "Read VIX1D as a gate")
    k2 = pr.make_dedupe_key("options_structure_metrics", "Read VIX1D as a gate")
    k3 = pr.make_dedupe_key("cross_asset_signals", "Read VIX1D as a gate")
    assert k1 == k2                      # stable -- same beat + same text -> same key
    assert k1 != k3                      # beat-namespaced -- different beat -> different key
    assert k1.startswith("options_structure_metrics:")


def test_extract_json_array_direct():
    text = '[{"idea": "x", "cost": "$0"}]'
    assert pr._extract_json_array(text) == [{"idea": "x", "cost": "$0"}]


def test_extract_json_array_fenced():
    text = '```json\n[{"idea": "x"}]\n```'
    assert pr._extract_json_array(text) == [{"idea": "x"}]


def test_extract_json_array_prose_wrapped():
    text = 'Sure, here is the array:\n[{"idea": "x"}]\nHope that helps!'
    assert pr._extract_json_array(text) == [{"idea": "x"}]


def test_extract_json_array_garbage_returns_none():
    assert pr._extract_json_array("no brackets here at all") is None
    assert pr._extract_json_array("") is None
    assert pr._extract_json_array("[not valid json") is None


def test_triage_one_valid_row():
    raw = {"idea": "Track VIX1D", "mechanism_1line": "shorter horizon than VIX",
           "data_source": "CBOE", "cost": "$0", "instrument_fit": "0dte",
           "testability": "battery-ready"}
    row = pr.triage_one("options_structure_metrics", raw)
    assert row["idea"] == "Track VIX1D"
    assert row["cost"] == "$0"
    assert row["instrument_fit"] == "0dte"
    assert row["testability"] == "battery-ready"
    assert row["id"] == row["dedupe_key"]
    assert row["beat"] == "options_structure_metrics"


def test_triage_one_missing_idea_returns_none():
    assert pr.triage_one("data_feeds_free", {"mechanism_1line": "no idea text"}) is None
    assert pr.triage_one("data_feeds_free", {"idea": "   "}) is None


def test_triage_one_non_dict_returns_none():
    assert pr.triage_one("data_feeds_free", "just a string") is None
    assert pr.triage_one("data_feeds_free", None) is None


def test_triage_one_invalid_enums_default_to_weakest_bucket():
    """A parsing fluke must never falsely qualify an idea as promotable: unknown
    cost -> 'paid' (never assert free), unknown fit -> 'both' (never wrongly
    narrow), unknown testability -> 'vague' (never falsely battery-ready)."""
    raw = {"idea": "some idea", "cost": "who knows", "instrument_fit": "crypto",
           "testability": "super promising"}
    row = pr.triage_one("data_feeds_free", raw)
    assert row["cost"] == "paid"
    assert row["instrument_fit"] == "both"
    assert row["testability"] == "vague"


# ─────────────────────────────────────────────────────────────────────────────
# Ledger idempotency / dedupe / kill-never-re-enters
# ─────────────────────────────────────────────────────────────────────────────


def _idea_row(dedupe_key, beat="data_feeds_free", testability="battery-ready", **kw):
    return {"kind": "idea", "id": dedupe_key, "dedupe_key": dedupe_key, "beat": beat,
            "idea": f"idea for {dedupe_key}", "mechanism_1line": "m", "data_source": "d",
            "cost": "$0", "instrument_fit": "both", "testability": testability,
            "status": "proposed", "date": "2026-07-09", **kw}


def test_append_ledger_rows_idempotent_by_dedupe_key(tmp_path):
    ledger = tmp_path / "ideas-ledger.jsonl"
    row = _idea_row("dup_key")
    n1 = pr.append_ledger_rows([row], ledger)
    n2 = pr.append_ledger_rows([row], ledger)          # same dedupe_key again
    assert n1 == 1
    assert n2 == 0                                       # idempotent -- no duplicate row
    assert len(pr.load_ledger(ledger)) == 1


def test_append_ledger_rows_mixed_new_and_dup(tmp_path):
    ledger = tmp_path / "ideas-ledger.jsonl"
    pr.append_ledger_rows([_idea_row("a")], ledger)
    n = pr.append_ledger_rows([_idea_row("a"), _idea_row("b")], ledger)
    assert n == 1                                        # only "b" is genuinely new
    assert {r["dedupe_key"] for r in pr.load_ledger(ledger)} == {"a", "b"}


def test_kill_idea_appends_kill_row_not_mutation(tmp_path):
    ledger = tmp_path / "ideas-ledger.jsonl"
    pr.append_ledger_rows([_idea_row("killme")], ledger)
    pr.kill_idea("killme", "duplicate of an existing engine filter", ledger)
    rows = pr.load_ledger(ledger)
    assert len(rows) == 2                                # append-only -- original row untouched
    assert rows[0]["dedupe_key"] == "killme" and rows[0]["kind"] == "idea"
    assert rows[1]["kind"] == "kill" and rows[1]["reason"]


def test_killed_idea_never_re_enters_ledger(tmp_path):
    """THE explicitly-required guarantee: 'ideas previously KILLED must never
    re-enter'. Even a FRESH idea row (different content, e.g. re-surfaced by a
    different beat's wording) sharing the same dedupe_key as a killed one must
    be rejected on append."""
    ledger = tmp_path / "ideas-ledger.jsonl"
    pr.kill_idea("zombie_idea", "already tried, doesn't work", ledger)
    n = pr.append_ledger_rows([_idea_row("zombie_idea")], ledger)
    assert n == 0
    rows = pr.load_ledger(ledger)
    assert len(rows) == 1 and rows[0]["kind"] == "kill"
    assert pr.existing_idea_keys(rows) == set()          # no idea row ever got in


def test_load_ledger_skips_malformed_lines(tmp_path):
    ledger = tmp_path / "ideas-ledger.jsonl"
    ledger.write_text('{"dedupe_key": "ok", "kind": "idea"}\nnot json\n\n', encoding="utf-8")
    rows = pr.load_ledger(ledger)
    assert len(rows) == 1 and rows[0]["dedupe_key"] == "ok"


def test_load_ledger_missing_file_returns_empty(tmp_path):
    assert pr.load_ledger(tmp_path / "does-not-exist.jsonl") == []


# ─────────────────────────────────────────────────────────────────────────────
# Beat rotation
# ─────────────────────────────────────────────────────────────────────────────


def test_pick_next_beat_default_zero():
    assert pr.pick_next_beat({}) == pr.BEATS[0]


def test_advance_beat_cycles_and_wraps_after_7():
    state = {"beat_index": 0}
    seen = []
    for _ in range(len(pr.BEATS)):
        seen.append(pr.pick_next_beat(state))
        state = pr.advance_beat(state)
    assert seen == list(pr.BEATS)                        # visits every beat exactly once
    assert pr.pick_next_beat(state) == pr.BEATS[0]        # wraps back to the start


def test_advance_beat_is_immutable_update():
    state = {"beat_index": 0, "other_key": "preserved"}
    new_state = pr.advance_beat(state)
    assert state["beat_index"] == 0                       # original untouched
    assert new_state["beat_index"] == 1
    assert new_state["other_key"] == "preserved"


def test_load_state_defaults_when_missing(tmp_path):
    state = pr.load_state(tmp_path / "nope.json")
    assert state["beat_index"] == 0
    assert state["promoted_dedupe_keys"] == []


def test_save_and_load_state_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    pr.save_state({"beat_index": 3, "fires_total": 5}, path)
    loaded = pr.load_state(path)
    assert loaded["beat_index"] == 3
    assert loaded["fires_total"] == 5
    assert "promoted_dedupe_keys" in loaded               # defaults still merged in


# ─────────────────────────────────────────────────────────────────────────────
# scan_beat -- fail-open across the whole free roster
# ─────────────────────────────────────────────────────────────────────────────


def _fake_call_ok(_model, **_kw):
    return {"ok": True, "content": json.dumps([{"idea": "x", "cost": "$0"}]), "error": None}


def _fake_call_fail(_model, **_kw):
    return {"ok": False, "content": "", "error": "429 rate limited"}


def _fake_call_raises(_model, **_kw):
    raise RuntimeError("network exploded")


def test_scan_beat_returns_ok_true_on_first_good_model():
    result = pr.scan_beat("data_feeds_free", models=["model-a"], call_fn=_fake_call_ok)
    assert result["ok"] is True
    assert result["model"] == "model-a"
    assert result["ideas_raw"] == [{"idea": "x", "cost": "$0"}]


def test_scan_beat_tries_next_model_on_failure():
    calls = []

    def call_fn(model, **_kw):
        calls.append(model)
        if model == "dead-model":
            return {"ok": False, "content": "", "error": "404 not found"}
        return _fake_call_ok(model, **_kw)

    result = pr.scan_beat("data_feeds_free", models=["dead-model", "live-model"], call_fn=call_fn)
    assert result["ok"] is True and result["model"] == "live-model"
    assert calls == ["dead-model", "live-model"]           # rotated through in order


def test_scan_beat_fail_open_when_all_models_fail():
    """THE explicitly-required guarantee: no free lane up -> ok=False, a
    descriptive error, and (critically) NO EXCEPTION."""
    result = pr.scan_beat("data_feeds_free", models=["a", "b", "c"], call_fn=_fake_call_fail)
    assert result["ok"] is False
    assert result["ideas_raw"] is None
    assert result["error"]


def test_scan_beat_never_raises_on_call_fn_exception():
    result = pr.scan_beat("data_feeds_free", models=["a"], call_fn=_fake_call_raises)
    assert result["ok"] is False
    assert "network exploded" in result["error"]


def test_scan_beat_treats_unparseable_content_as_failure_and_rotates():
    def call_fn(model, **_kw):
        if model == "verbose-model":
            return {"ok": True, "content": "I refuse to output JSON today.", "error": None}
        return _fake_call_ok(model, **_kw)

    result = pr.scan_beat("data_feeds_free", models=["verbose-model", "good-model"], call_fn=call_fn)
    assert result["ok"] is True and result["model"] == "good-model"


# ─────────────────────────────────────────────────────────────────────────────
# promote_top1
# ─────────────────────────────────────────────────────────────────────────────


def test_promote_top1_picks_oldest_battery_ready_fifo(tmp_path):
    rows = [_idea_row("old_one", testability="battery-ready"),
            _idea_row("vague_one", testability="vague"),
            _idea_row("new_one", testability="battery-ready")]
    inbox = tmp_path / "_chef-inbox"
    promoted = pr.promote_top1(rows, {}, date="2026-07-09", inbox_dir=inbox)
    assert promoted["dedupe_key"] == "old_one"             # first in list order (FIFO)
    assert (inbox / promoted["_chef_inbox_file"]).exists()


def test_promote_top1_idempotent_does_not_repromote(tmp_path):
    rows = [_idea_row("only_one", testability="battery-ready")]
    inbox = tmp_path / "_chef-inbox"
    state = {"promoted_dedupe_keys": ["only_one"]}         # already promoted a prior fire
    promoted = pr.promote_top1(rows, state, date="2026-07-09", inbox_dir=inbox)
    assert promoted is None


def test_promote_top1_skips_killed(tmp_path):
    rows = [{"kind": "kill", "dedupe_key": "was_killed", "reason": "no edge"},
            _idea_row("was_killed", testability="battery-ready")]
    promoted = pr.promote_top1(rows, {}, date="2026-07-09", inbox_dir=tmp_path / "_chef-inbox")
    assert promoted is None


def test_promote_top1_returns_none_when_nothing_eligible(tmp_path):
    rows = [_idea_row("needs_data_one", testability="needs-data"),
            _idea_row("vague_one", testability="vague")]
    promoted = pr.promote_top1(rows, {}, date="2026-07-09", inbox_dir=tmp_path / "_chef-inbox")
    assert promoted is None


def test_promote_top1_uses_hand_authored_spec_for_gex_flip(tmp_path):
    rows = [_idea_row("gex_flip_from_banked_cboe", testability="battery-ready")]
    inbox = tmp_path / "_chef-inbox"
    promoted = pr.promote_top1(rows, {}, date="2026-07-09", inbox_dir=inbox)
    text = (inbox / promoted["_chef_inbox_file"]).read_text(encoding="utf-8")
    assert "zero-gamma flip" in text
    assert "60-90 as-of days" in text                      # the real gex_regime feasibility bar


# ─────────────────────────────────────────────────────────────────────────────
# already_promoted_from_inbox / state-loss re-promotion regression
#
# Incident (found 2026-07-21): the 2026-06-27..07-13 git-stash-drop recovery
# (commit 41889a0) reset analysis/prospector/state.json, wiping
# promoted_dedupe_keys. Ledger rows from before the reset stayed in the
# ledger (append_ledger_rows is dedupe_key-idempotent, so they were never
# re-added) but WERE re-eligible for promote_top1 once state's
# promoted_dedupe_keys forgot them -- 37 of 65 _chef-inbox/prospector-*.md
# files ended up pure re-promotion noise of 17 ideas, 0 ever reviewed by
# chef. These tests pin the fix: promote_top1 must treat an EXISTING
# _chef-inbox file (by dedupe_key tail, any date, .md or .md.DONE) as
# already-promoted even when state.json has no memory of it at all.
# ─────────────────────────────────────────────────────────────────────────────


def test_already_promoted_from_inbox_matches_by_tail(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    inbox.mkdir()
    (inbox / "2026-07-10-prospector-tick-index-nyse-tick.md").write_text("x", encoding="utf-8")
    rows = [_idea_row("data_feeds_free:tick-index-nyse-tick", testability="battery-ready")]
    found = pr.already_promoted_from_inbox(rows, inbox_dir=inbox)
    assert found == {"data_feeds_free:tick-index-nyse-tick"}


def test_already_promoted_from_inbox_matches_done_files_too(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    inbox.mkdir()
    (inbox / "2026-07-10-prospector-vix1d_gate.md.DONE").write_text("x", encoding="utf-8")
    rows = [_idea_row("vix1d_gate", testability="battery-ready")]
    found = pr.already_promoted_from_inbox(rows, inbox_dir=inbox)
    assert found == {"vix1d_gate"}


def test_already_promoted_from_inbox_empty_or_missing_dir_returns_empty(tmp_path):
    rows = [_idea_row("something", testability="battery-ready")]
    assert pr.already_promoted_from_inbox(rows, inbox_dir=tmp_path / "nonexistent") == set()
    empty_inbox = tmp_path / "_chef-inbox"
    empty_inbox.mkdir()
    assert pr.already_promoted_from_inbox(rows, inbox_dir=empty_inbox) == set()


def test_already_promoted_from_inbox_ignores_non_prospector_files(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    inbox.mkdir()
    (inbox / "README.md").write_text("x", encoding="utf-8")
    (inbox / "2026-07-14-late-entry-ceiling-review.md").write_text("x", encoding="utf-8")
    rows = [_idea_row("data_feeds_free:tick-index-nyse-tick", testability="battery-ready")]
    assert pr.already_promoted_from_inbox(rows, inbox_dir=inbox) == set()


def test_promote_top1_does_not_repromote_after_state_loss_if_inbox_file_exists(tmp_path):
    """THE regression test: state.json has NO memory of the promotion (as if
    reset by a data-loss incident), but the inbox already carries a file for
    this idea from an earlier date -- promote_top1 must not write a duplicate."""
    inbox = tmp_path / "_chef-inbox"
    inbox.mkdir()
    (inbox / "2026-07-10-prospector-tick-index-nyse-tick.md").write_text("x", encoding="utf-8")
    rows = [_idea_row("data_feeds_free:tick-index-nyse-tick", testability="battery-ready")]
    promoted = pr.promote_top1(rows, {}, date="2026-07-21", inbox_dir=inbox)  # state={} = lost memory
    assert promoted is None
    assert len(list(inbox.iterdir())) == 1                 # no new file written


def test_promote_top1_still_promotes_new_candidate_when_inbox_has_unrelated_file(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    inbox.mkdir()
    (inbox / "2026-07-10-prospector-tick-index-nyse-tick.md").write_text("x", encoding="utf-8")
    rows = [_idea_row("data_feeds_free:tick-index-nyse-tick", testability="battery-ready"),
            _idea_row("data_feeds_free:brand-new-idea", testability="battery-ready")]
    promoted = pr.promote_top1(rows, {}, date="2026-07-21", inbox_dir=inbox)
    assert promoted["dedupe_key"] == "data_feeds_free:brand-new-idea"


def test_promote_top1_uses_generic_spec_for_unknown_idea(tmp_path):
    rows = [_idea_row("some_new_swarm_idea", testability="battery-ready")]
    inbox = tmp_path / "_chef-inbox"
    promoted = pr.promote_top1(rows, {}, date="2026-07-09", inbox_dir=inbox)
    text = (inbox / promoted["_chef_inbox_file"]).read_text(encoding="utf-8")
    assert pr._GENERIC_PASS_BAR in text


# ─────────────────────────────────────────────────────────────────────────────
# Concept-family dedupe (found live 2026-07-22: 5 VIX1D + 3 Volume-Profile
# chef-inbox items independently promoted under unique dedupe_keys because
# exact dedupe_key/tail matching never catches a re-worded re-discovery of
# the SAME underlying concept). See family_already_covered docstring.
# ─────────────────────────────────────────────────────────────────────────────


def test_idea_family_matches_vix1d_variants():
    assert pr.idea_family("CBOE VIX1D Index as a Volatility Gauge") == "vix1d"
    assert pr.idea_family("Track the VIX Term Structure: VIX1D minus VIX30") == "vix1d"
    assert pr.idea_family("A totally unrelated idea about FINRA short volume") is None


def test_idea_family_matches_volume_profile_variants():
    assert pr.idea_family("Volume Profile Visible Range (VPVR) shelves") == "volume_profile"
    assert pr.idea_family("Read TradingView's high-volume-node shelves") == "volume_profile"
    assert pr.idea_family("") is None


def test_family_already_covered_finds_existing_open_item(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    inbox.mkdir()
    (inbox / "2026-07-09-prospector-vix1d_gate.md").write_text(
        "idea for vix1d_gate: track VIX1D as a same-horizon vol gate.", encoding="utf-8")
    covered = pr.family_already_covered("CBOE VIX1D Index as a Volatility Gauge", inbox_dir=inbox)
    assert covered is not None
    assert covered.name == "2026-07-09-prospector-vix1d_gate.md"


def test_family_already_covered_finds_existing_done_item(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    inbox.mkdir()
    (inbox / "2026-07-11-prospector-vpvr-shows.md.DONE").write_text(
        "idea for volume_shelf_tv_vp: Volume Profile Visible Range shelves.",
        encoding="utf-8")
    covered = pr.family_already_covered(
        "Volume Profile Visible Range (VPVR) high-volume nodes", inbox_dir=inbox)
    assert covered is not None
    assert covered.name == "2026-07-11-prospector-vpvr-shows.md.DONE"


def test_family_already_covered_ignores_readme():
    readme = CHEF_INBOX_README
    # README.md documents the template and legitimately contains no family
    # keywords today, but even if it did, family_already_covered must never
    # treat README.md as a canonical "already covered" item.
    covered = pr.family_already_covered("CBOE VIX1D Index", inbox_dir=readme.parent)
    if covered is not None:
        assert covered.name != "README.md"


def test_family_already_covered_returns_none_for_family_less_idea(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    inbox.mkdir()
    (inbox / "2026-07-09-prospector-vix1d_gate.md").write_text(
        "idea for vix1d_gate", encoding="utf-8")
    covered = pr.family_already_covered("FINRA daily short-sale volume", inbox_dir=inbox)
    assert covered is None


def test_family_already_covered_returns_none_when_no_existing_family_match(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    inbox.mkdir()
    (inbox / "2026-07-14-prospector-finra-short-vol.md").write_text(
        "idea for finra_short_volume", encoding="utf-8")
    # first-of-its-family VIX1D idea: nothing in the inbox mentions vix1d yet
    covered = pr.family_already_covered("CBOE VIX1D Index as a Volatility Gauge", inbox_dir=inbox)
    assert covered is None


def test_promote_top1_folds_family_duplicate_instead_of_repromoting(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    inbox.mkdir()
    (inbox / "2026-07-09-prospector-vix1d_gate.md.DONE").write_text(
        "idea for vix1d_gate: VIX1D same-horizon vol gate, already screened.",
        encoding="utf-8")
    rows = [_idea_row("data_feeds_free:cboe-vix1d-index-as-volatility-gauge",
                      idea="CBOE VIX1D Index as a Volatility Gauge")]
    promoted = pr.promote_top1(rows, {}, date="2026-07-21", inbox_dir=inbox)
    assert promoted is not None
    assert promoted["_chef_inbox_file"] is None                         # no new file written
    assert promoted["_folded_into"] == "2026-07-09-prospector-vix1d_gate.md.DONE"
    assert len(list(inbox.iterdir())) == 1                              # still just the 1 pre-existing file


def test_promote_top1_still_writes_new_file_for_family_less_idea(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    inbox.mkdir()
    (inbox / "2026-07-09-prospector-vix1d_gate.md.DONE").write_text(
        "idea for vix1d_gate: VIX1D vol gate.", encoding="utf-8")
    rows = [_idea_row("data_feeds_free:finra-short-vol",
                      idea="FINRA daily short-sale volume as a positioning gauge")]
    promoted = pr.promote_top1(rows, {}, date="2026-07-21", inbox_dir=inbox)
    assert promoted is not None
    assert promoted.get("_folded_into") is None
    assert promoted["_chef_inbox_file"] is not None
    assert (inbox / promoted["_chef_inbox_file"]).exists()


# ─────────────────────────────────────────────────────────────────────────────
# _chef-inbox item format -- fixture built from the REAL README.md template
# ─────────────────────────────────────────────────────────────────────────────


def test_render_chef_inbox_item_matches_required_sections():
    """The real consumer is the `chef` agent, which reads every _chef-inbox item
    in the shape documented by strategy/candidates/_chef-inbox/README.md. This
    fixture is that real file's documented field list -- not invented -- so a
    format drift in either the README or this renderer fails loudly."""
    required_readme_fields = ["**Routed by:**", "**Priority:**", "**Category:**",
                              "**Source:**", "## The Finding", "## Research Question for Chef",
                              "## Backtest Request", "## Files for Reference",
                              "## Priority / Dependencies"]
    readme_text = CHEF_INBOX_README.read_text(encoding="utf-8")
    for field in required_readme_fields:
        assert field in readme_text, f"README template drifted -- {field} no longer documented"

    row = _idea_row("vix1d_gate", idea="Track VIX1D", mechanism_1line="shorter horizon")
    text = pr.render_chef_inbox_item(row, date="2026-07-09", hypothesis="H", data="D",
                                     null="N", pass_bar="P")
    assert text.startswith("# Chef Inbox — ")
    for field in required_readme_fields:
        assert field in text
    assert "vix1d_gate" in text                            # dedupe_key traceable for provenance


def test_render_chef_inbox_item_is_a_spec_not_code():
    """The task's explicit constraint: promote a STUDY SPEC, NOT code."""
    row = _idea_row("some_idea")
    text = pr.render_chef_inbox_item(row, date="2026-07-09", hypothesis="H", data="D",
                                     null="N", pass_bar="P")
    for banned in ("def ", "import ", "```python", "class "):
        assert banned not in text


# ─────────────────────────────────────────────────────────────────────────────
# Seed data (tonight's 12 entries)
# ─────────────────────────────────────────────────────────────────────────────

_REQUIRED_KEYS = {"id", "beat", "idea", "mechanism_1line", "data_source", "cost",
                  "instrument_fit", "testability", "dedupe_key"}


def test_seed_ideas_count_is_12():
    assert len(pr.SEED_IDEAS) == 12


def test_seed_ideas_all_have_required_schema_keys_and_valid_enums():
    for row in pr.SEED_IDEAS:
        missing = _REQUIRED_KEYS - set(row.keys())
        assert not missing, f"{row.get('id')} missing keys: {missing}"
        assert row["id"] == row["dedupe_key"]
        assert row["beat"] in pr.BEATS
        assert row["cost"] in pr._VALID_COST
        assert row["instrument_fit"] in pr._VALID_FIT
        assert row["testability"] in pr._VALID_TESTABILITY
        assert row["source"] in ("J-2026-07-09", "fable-2026-07-09")


def test_seed_ideas_unique_dedupe_keys():
    keys = [r["dedupe_key"] for r in pr.SEED_IDEAS]
    assert len(keys) == len(set(keys))


def test_seed_ideas_exactly_3_battery_ready_per_instruction():
    battery_ready = [r["id"] for r in pr.SEED_IDEAS if r["testability"] == "battery-ready"]
    assert set(battery_ready) == {"gex_flip_from_banked_cboe", "vix1d_gate", "volume_shelf_tv_vp"}


def test_seed_ideas_source_attribution_matches_instruction():
    j_sourced = {r["id"] for r in pr.SEED_IDEAS if r["source"] == "J-2026-07-09"}
    fable_sourced = {r["id"] for r in pr.SEED_IDEAS if r["source"] == "fable-2026-07-09"}
    assert j_sourced == {"volume_shelf_tv_vp", "community_pine_sr", "finra_short_volume",
                         "dix_daily", "pattern_grammar"}
    assert fable_sourced == {"gex_flip_from_banked_cboe", "vix1d_gate", "tick_add_internals",
                             "moc_imbalance_window", "globex_levels", "cot_mes_positioning",
                             "timeofday_seasonality_own_fills"}


def test_seed_ideas_gex_flip_is_first_for_fifo_promotion():
    assert pr.SEED_IDEAS[0]["id"] == "gex_flip_from_banked_cboe"


# ─────────────────────────────────────────────────────────────────────────────
# cmd_seed() end-to-end (isolated tmp paths -- never touches the real repo state)
# ─────────────────────────────────────────────────────────────────────────────


def _tmp_paths(tmp_path):
    return dict(ledger_path=tmp_path / "ideas-ledger.jsonl",
               state_path=tmp_path / "state.json",
               last_json_path=tmp_path / "prospector-last.json",
               inbox_dir=tmp_path / "_chef-inbox")


def test_seed_then_promote_picks_gex_flip_first(tmp_path):
    paths = _tmp_paths(tmp_path)
    result = pr.cmd_seed(date="2026-07-09", **paths)
    assert result["n_added"] == 12
    assert result["promoted"]["dedupe_key"] == "gex_flip_from_banked_cboe"
    assert (paths["inbox_dir"] / result["promoted"]["_chef_inbox_file"]).exists()
    state = pr.load_state(paths["state_path"])
    assert state["promoted_dedupe_keys"] == ["gex_flip_from_banked_cboe"]


def test_cmd_seed_ledger_append_is_idempotent(tmp_path):
    paths = _tmp_paths(tmp_path)
    pr.cmd_seed(date="2026-07-09", **paths)
    second = pr.cmd_seed(date="2026-07-09", **paths)
    assert second["n_added"] == 0                           # all 12 already present
    assert len(pr.load_ledger(paths["ledger_path"])) == 12   # no duplicate rows


def test_cmd_seed_repeated_calls_drain_battery_ready_pool_then_stop(tmp_path):
    """promote_top1 promotes exactly ONE new eligible idea per call -- with 3
    battery-ready seeds, repeated cmd_seed() calls promote gex_flip, then
    vix1d_gate, then volume_shelf_tv_vp (FIFO order), then correctly stop
    (nothing left eligible) -- and never promote the same idea twice."""
    paths = _tmp_paths(tmp_path)
    promoted_order = []
    for _ in range(4):
        result = pr.cmd_seed(date="2026-07-09", **paths)
        promoted_order.append(result["promoted"]["dedupe_key"] if result["promoted"] else None)

    assert promoted_order == ["gex_flip_from_banked_cboe", "vix1d_gate",
                              "volume_shelf_tv_vp", None]
    state = pr.load_state(paths["state_path"])
    assert sorted(state["promoted_dedupe_keys"]) == sorted(
        ["gex_flip_from_banked_cboe", "vix1d_gate", "volume_shelf_tv_vp"])
    assert state["promoted_total"] == 3
    # exactly one _chef-inbox file per promoted idea, none duplicated
    inbox_files = list(paths["inbox_dir"].glob("*.md"))
    assert len(inbox_files) == 3


# ─────────────────────────────────────────────────────────────────────────────
# run() end-to-end -- fail-open guarantee at the orchestration level
# ─────────────────────────────────────────────────────────────────────────────


def test_run_fail_open_swarm_down_ledger_still_served(tmp_path):
    """THE explicitly-required guarantee, at the orchestration level: swarm
    down -> exits cleanly (no exception) AND a pre-existing ledger is left
    fully intact/readable ('still served')."""
    paths = _tmp_paths(tmp_path)
    pr.append_ledger_rows([_idea_row("pre_existing")], paths["ledger_path"])

    result = pr.run(beat="data_feeds_free", scan_fn=lambda b: pr.scan_beat(
        b, models=["a", "b"], call_fn=_fake_call_fail), **paths)

    assert result["scan_ok"] is False
    assert result["error"]
    assert result["n_added"] == 0
    rows = pr.load_ledger(paths["ledger_path"])
    assert len(rows) == 1 and rows[0]["dedupe_key"] == "pre_existing"  # still served, untouched
    assert paths["last_json_path"].exists()                 # surfaced even on failure


def test_run_scan_fn_raising_is_fail_open_too(tmp_path):
    paths = _tmp_paths(tmp_path)

    def exploding_scan(_beat):
        raise RuntimeError("boom")

    result = pr.run(beat="data_feeds_free", scan_fn=exploding_scan, **paths)
    assert result["scan_ok"] is False
    assert "boom" in result["error"]


def test_run_happy_path_appends_and_writes_last_json(tmp_path):
    paths = _tmp_paths(tmp_path)
    canned = {"ok": True, "model": "test-model", "ideas_raw": [
        {"idea": "Read VIX1D", "mechanism_1line": "m", "data_source": "CBOE",
         "cost": "$0", "instrument_fit": "0dte", "testability": "battery-ready"}]}
    result = pr.run(beat="options_structure_metrics", scan_fn=lambda b: canned, **paths)

    assert result["scan_ok"] is True
    assert result["n_added"] == 1
    rows = pr.load_ledger(paths["ledger_path"])
    assert len(rows) == 1 and rows[0]["idea"] == "Read VIX1D"
    assert result["promoted"] is not None                   # the row was battery-ready
    last = json.loads(paths["last_json_path"].read_text(encoding="utf-8"))
    assert last["n_new_ideas"] == 1


def test_run_advances_beat_index_in_state(tmp_path):
    paths = _tmp_paths(tmp_path)
    pr.run(beat="data_feeds_free", scan_fn=lambda b: {"ok": False, "error": "down"}, **paths)
    state = pr.load_state(paths["state_path"])
    assert state["last_beat"] == "data_feeds_free"
    assert state["beat_index"] == 1                          # advanced from 0 -> 1


def test_run_dry_run_never_writes_ledger_or_state(tmp_path):
    paths = _tmp_paths(tmp_path)
    canned = {"ok": True, "model": "m", "ideas_raw": [{"idea": "x", "cost": "$0"}]}
    pr.run(beat="data_feeds_free", dry_run=True, scan_fn=lambda b: canned, **paths)
    assert not paths["ledger_path"].exists()
    assert not paths["state_path"].exists()


# ─────────────────────────────────────────────────────────────────────────────
# main() -- the true entrypoint never raises
# ─────────────────────────────────────────────────────────────────────────────


def test_main_fail_open_when_run_itself_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["prospector.py"])
    monkeypatch.setattr(pr, "LAST_JSON", tmp_path / "prospector-last.json")

    def exploding_run(**_kw):
        raise RuntimeError("total meltdown")

    monkeypatch.setattr(pr, "run", exploding_run)
    assert pr.main() == 0                                    # exits 0 even on a hard crash
    payload = json.loads(pr.LAST_JSON.read_text(encoding="utf-8"))
    assert "total meltdown" in payload["error"]
