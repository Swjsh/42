"""Tests for the deterministic post-tick decisions writer.

Covers: HB# line parsing (canonical + degraded), tick iteration, dedup vs
existing LLM rows, PAUSED/TRIPPED exclusion, per-tick recency guard, backfill
count, and loop-state recovery (degraded-only). Pure stdlib + pytest.
"""
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MOD_PATH = os.path.join(ROOT, "setup", "scripts", "heartbeat_persist_writer.py")

_spec = importlib.util.spec_from_file_location("hb_persist_writer", MOD_PATH)
hpw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hpw)


# --- parse_hb_line ----------------------------------------------------------
def test_parse_canonical_line():
    p = hpw.parse_hb_line(
        "HB#3 11:45 HOLD | spy=734.78 ribbon=16c(BEAR) vix=17.88(falling) "
        "bear=5/10 bull=4/11 htf=null | spread_tight 16c<30c_min BEACON_ACTIVE")
    assert p["action"] == "HOLD"
    assert p["time_et"] == "11:45"
    assert p["spy"] == 734.78
    assert p["ribbon_stack"] == "BEAR"
    assert p["ribbon_spread_cents"] == 16
    assert p["vix"] == 17.88 and p["vix_dir"] == "falling"
    assert p["bear_score"] == 5 and p["bull_score"] == 4
    assert p["reason"] == "spread_tight 16c<30c_min BEACON_ACTIVE"


def test_parse_degraded_empty_fields():
    p = hpw.parse_hb_line(
        "HB#847 11:57 SKIP_TV_DATA_STALE | BEACON_STALE | spy= ribbon= vix= "
        "bear=?/10 bull=?/11 htf= | all data layers down 90min")
    assert p["action"] == "SKIP_TV_DATA_STALE"
    assert p["spy"] is None and p["vix"] is None
    assert p["bear_score"] is None and p["bull_score"] is None
    assert p["reason"] == "all data layers down 90min"


def test_parse_paused_with_dashdash_label():
    p = hpw.parse_hb_line("HB#-- 11:24 PAUSED | kill-switch-active")
    assert p["action"] == "PAUSED"
    assert p["time_et"] == "11:24"


def test_parse_time_zero_pads():
    p = hpw.parse_hb_line("HB#3 9:39 HOLD | spy=737.0 ribbon=2c(MIXED) vix=17.0(flat) bear=0/10 bull=0/11 htf=null | x")
    assert p["time_et"] == "09:39"


def test_parse_non_hb_line_returns_none():
    assert hpw.parse_hb_line("2026-06-25 11:49:16 ET === END tick exit=0 ===") is None


# --- iter_ticks -------------------------------------------------------------
SAMPLE_LOG = """2026-06-25 11:45:02 ET FIRE mode=HOT idx=45 model=haiku pos_open=False htf=False score=0
2026-06-25 11:45:04 ET === START tick (timeout=280s effort=low budget=1 model=haiku freeMB=7571) ===
HB#3 11:45 HOLD | spy=734.78 ribbon=16c(BEAR) vix=17.88(falling) bear=5/10 bull=4/11 htf=null | spread_tight
2026-06-25 11:46:06 ET === END tick exit=0 ===
2026-06-25 11:48:02 ET FIRE mode=HOT idx=46 model=haiku pos_open=False htf=True score=0
2026-06-25 11:48:03 ET === START tick (timeout=280s effort=low budget=1 model=haiku freeMB=7568) ===
HB#3 11:48 PAUSED | kill-switch-active
2026-06-25 11:49:16 ET === END tick exit=0 ===
2026-06-25 11:57:02 ET FIRE mode=HOT idx=49 model=haiku pos_open=False htf=False score=0
2026-06-25 11:57:02 ET === START tick (timeout=280s effort=low budget=1 model=haiku freeMB=7561) ===
HB#4 11:57 HOLD | spy=734.10 ribbon=26c(BEAR) vix=17.88(cached) bear=0/10 bull=0/11 htf=null | chop_zone
2026-06-25 11:57:27 ET === END tick exit=0 ===
"""


def test_iter_ticks_picks_fire_idx_and_hb():
    ticks = list(hpw.iter_ticks(SAMPLE_LOG))
    assert len(ticks) == 3
    assert ticks[0]["fire_idx"] == 45
    assert ticks[0]["hb"]["action"] == "HOLD"
    assert ticks[1]["fire_idx"] == 46
    assert ticks[1]["hb"]["action"] == "PAUSED"
    assert ticks[2]["fire_idx"] == 49


def test_iter_ticks_start_without_hb_yields_none():
    log = ("2026-06-25 12:00:00 ET === START tick (timeout=280s) ===\n"
           "2026-06-25 12:04:40 ET TIMEOUT after 280s - killing root pid=1\n"
           "2026-06-25 12:04:41 ET === END tick exit=124 (timeout) ===\n")
    ticks = list(hpw.iter_ticks(log))
    assert len(ticks) == 1
    assert ticks[0]["hb"] is None


# --- end-to-end via process() ----------------------------------------------
def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _setup_env(tmp_path, monkeypatch, log_text, existing_rows=None, loop_state=None):
    state = tmp_path / "automation" / "state"
    decisions = state / "decisions.jsonl"
    loop = state / "loop-state.json"
    pos = state / "current-position.json"
    logp = state / "logs" / "heartbeat-2026-06-25.log"
    _write(str(logp), log_text)
    _write(str(pos), json.dumps({"status": None}))
    if existing_rows is not None:
        _write(str(decisions), "".join(json.dumps(r) + "\n" for r in existing_rows))
    if loop_state is not None:
        _write(str(loop), loop_state)
    monkeypatch.setattr(hpw, "LOG_DIR", str(state / "logs"))
    monkeypatch.setitem(hpw.ACCOUNTS, "safe", {
        "log_task": "heartbeat", "decisions": str(decisions),
        "loop_state": str(loop), "position": str(pos),
    })
    return decisions, loop


def _read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def test_backfill_writes_non_paused_skips_paused(tmp_path, monkeypatch):
    decisions, _ = _setup_env(tmp_path, monkeypatch, SAMPLE_LOG, existing_rows=[])
    n = hpw.process("safe", backfill=True, max_start_age_sec=999999,
                    now_override="2026-06-25T16:00:00", log_override=None,
                    dry_run=False, silent=True)
    rows = _read_rows(decisions)
    assert n == 2  # two HOLD ticks; the PAUSED one is excluded
    times = {r["time_et"] for r in rows}
    assert times == {"11:45", "11:57"}
    assert all(r["source"] == "post_tick_writer" for r in rows)


def test_dedup_skips_rows_llm_already_wrote(tmp_path, monkeypatch):
    existing = [{"tick_id": 45, "date": "2026-06-25", "time_et": "11:45",
                 "action": "HOLD", "spy": 734.78}]
    decisions, _ = _setup_env(tmp_path, monkeypatch, SAMPLE_LOG, existing_rows=existing)
    n = hpw.process("safe", backfill=True, max_start_age_sec=999999,
                    now_override="2026-06-25T16:00:00", log_override=None,
                    dry_run=False, silent=True)
    assert n == 1  # 11:45 already present -> only 11:57 backfilled
    rows = _read_rows(decisions)
    # original LLM row preserved, exactly one writer row added
    assert sum(1 for r in rows if r["time_et"] == "11:45") == 1
    assert sum(1 for r in rows if r.get("source") == "post_tick_writer") == 1


def test_per_tick_mode_respects_recency_guard(tmp_path, monkeypatch):
    decisions, _ = _setup_env(tmp_path, monkeypatch, SAMPLE_LOG, existing_rows=[])
    # 'now' is hours after the last START -> guard blocks, nothing written.
    n = hpw.process("safe", backfill=False, max_start_age_sec=360,
                    now_override="2026-06-25T16:00:00", log_override=None,
                    dry_run=False, silent=True)
    assert n == 0
    assert _read_rows(decisions) == []


def test_per_tick_mode_writes_last_when_fresh(tmp_path, monkeypatch):
    decisions, _ = _setup_env(tmp_path, monkeypatch, SAMPLE_LOG, existing_rows=[])
    # 'now' just after the last START (11:57:02) -> within guard, last tick written.
    n = hpw.process("safe", backfill=False, max_start_age_sec=360,
                    now_override="2026-06-25T11:58:00", log_override=None,
                    dry_run=False, silent=True)
    assert n == 1
    rows = _read_rows(decisions)
    assert rows[0]["time_et"] == "11:57"


def test_loop_state_recovered_only_when_degraded(tmp_path, monkeypatch):
    decisions, loop = _setup_env(tmp_path, monkeypatch, SAMPLE_LOG,
                                 existing_rows=[], loop_state="{}")
    hpw.process("safe", backfill=True, max_start_age_sec=999999,
                now_override="2026-06-25T16:00:00", log_override=None,
                dry_run=False, silent=True)
    seeded = json.loads(open(loop, encoding="utf-8").read())
    assert seeded["session_id"] == "2026-06-25"
    assert "post_tick_writer_recovery" in seeded["last_change_reason"]


def test_synthesized_row_conforms_to_canonical_contract():
    """Rows the writer emits must pass DecisionRowModel (the canonical ledger
    schema, extra='allow'). Skip if pydantic/contracts unavailable."""
    import pytest
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(ROOT, "backtest"))
        from lib.contracts import DecisionRowModel
    except Exception:
        pytest.skip("contracts/pydantic not importable in this interpreter")
    hb = hpw.parse_hb_line(
        "HB#3 11:45 HOLD | spy=734.78 ribbon=16c(BEAR) vix=17.88(falling) "
        "bear=5/10 bull=4/11 htf=null | spread_tight")
    row = hpw.synthesize_row(hb, 45, "2026-06-25", "safe", None)
    DecisionRowModel.model_validate(row)  # raises StateContractError if non-conformant
    # also a degraded (null-spy) row must still validate
    hb2 = hpw.parse_hb_line("HB#847 11:57 SKIP_TV_DATA_STALE | spy= ribbon= vix= bear=?/10 bull=?/11 htf= | down")
    DecisionRowModel.model_validate(hpw.synthesize_row(hb2, 49, "2026-06-25", "safe", None))


def test_loop_state_healthy_not_clobbered(tmp_path, monkeypatch):
    healthy = json.dumps({"schema_version": 3, "session_id": "2026-06-25",
                          "current_mode": "HOT", "ticks_today": 9,
                          "developing_setup": {"name": "X"}})
    decisions, loop = _setup_env(tmp_path, monkeypatch, SAMPLE_LOG,
                                 existing_rows=[], loop_state=healthy)
    hpw.process("safe", backfill=True, max_start_age_sec=999999,
                now_override="2026-06-25T16:00:00", log_override=None,
                dry_run=False, silent=True)
    after = json.loads(open(loop, encoding="utf-8").read())
    assert after["ticks_today"] == 9  # untouched
    assert after["developing_setup"] == {"name": "X"}
    assert "recovery" not in after.get("last_change_reason", "")
