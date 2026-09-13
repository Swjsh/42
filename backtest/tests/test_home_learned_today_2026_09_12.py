"""Guard for GOAL-EARN-YOUR-KEEP-2026-09-12 item 2: '## What Gamma learned today' on
HOME.md -- the H1 challenger (risky-3) vs control (risky-1) block.

setup/scripts/obsidian_vault_sync.py::render_learned_today() joins two fixture ledgers
under a tmp dir (never the real automation/state/fleet or pnl-statement.json):
  - a per-arm decisions.jsonl (same schema fleet_live.py::_log writes; the field this
    reads is `reason` == "gate: anchor_class_denied:<label>" from
    fleet_executor.py::_gate_check, GOAL-EARN-YOUR-KEEP item 1)
  - a pnl-statement.json per_day block (the T1 broker-truth realized-$ source
    fleet_journal_bridge.py cites in journal/trades.csv notes)
  - the prereg's own §8 Challenger LADDER table (for the "next row" lookup)

Covers: the "no sessions yet" pre-09-14 form, a populated session with one refused
signal the control lost on (F1 < 0, tally 1/6, "no change"), and the KILL-fires path
(refused >= 6 AND net >= 0 -> names the next `[ ]` LADDER row, read not hardcoded).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VAULT_SYNC = REPO / "setup" / "scripts" / "obsidian_vault_sync.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _write_decisions(fleet_dir: Path, arm: str, rows: list[dict]) -> None:
    d = fleet_dir / arm
    d.mkdir(parents=True, exist_ok=True)
    with (d / "decisions.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _row(date: str, hh: str, *, setup: str | None, action: str = "HOLD",
         reason: str = "no qualifying setup (no strategy fired)") -> dict:
    return {
        "ts_et": f"{date}T{hh}:00:00-04:00",
        "setup_name": setup,
        "action": action,
        "reason": reason,
    }


def _write_pnl_statement(path: Path, per_day: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"per_day": per_day}), encoding="utf-8")


PREREG_FIXTURE = """# fixture prereg

## 8. Challenger LADDER

| # | State | Hypothesis | Ship criterion | Kill criterion | n needed |
|---|---|---|---|---|---|
| H1 | `[~]` live | deny INTRADAY_SWING_ | F1-F5 | refused net >= 0 over >= 6 | 6 refused signals |
| H2 | `[ ]` next | deny MEMORY_* as trigger anchor | same F1-F5 on MEMORY refusals | refused net >= 0 over >= 6 | 6 refused signals |
| H3 | `[ ]` | compression sit-out | its own | its own | 5 sat-out sessions |
"""


def _module(tmp_path):
    return _load(VAULT_SYNC, f"obsidian_vault_sync_learned_{id(tmp_path)}")


# --------------------------------------------------------------------- no data yet


def test_no_sessions_yet_renders_before_challenger_start(tmp_path):
    m = _module(tmp_path)
    fleet_dir = tmp_path / "fleet"
    pnl_path = tmp_path / "pnl-statement.json"
    prereg_path = tmp_path / "prereg.md"
    prereg_path.write_text(PREREG_FIXTURE, encoding="utf-8")
    # risky-3 has old pre-activation rows only, all before CHALLENGER_START.
    _write_decisions(fleet_dir, "risky-3", [_row("2026-08-28", "10:00", setup=None)])
    _write_decisions(fleet_dir, "risky-1", [_row("2026-09-11", "10:00", setup="X")])
    _write_pnl_statement(pnl_path, {})

    out = m.render_learned_today(fleet_dir=fleet_dir, pnl_path=pnl_path,
                                 prereg_path=prereg_path)
    text = "\n".join(out)
    assert "## What Gamma learned today" in text
    assert "no sessions yet (first 2026-09-14)" in text
    assert "Tomorrow's change:** none (H1 clock running: 0/6 refused)" in text


def test_no_sessions_yet_never_raises_on_missing_files(tmp_path):
    m = _module(tmp_path)
    out = m.render_learned_today(
        fleet_dir=tmp_path / "does-not-exist",
        pnl_path=tmp_path / "also-missing.json",
        prereg_path=tmp_path / "missing-prereg.md",
    )
    assert "no sessions yet (first 2026-09-14)" in "\n".join(out)


# ------------------------------------------------------------- one refused signal, F1<0


def test_one_refused_signal_control_lost_gives_negative_f1_and_tally_1_of_6(tmp_path):
    m = _module(tmp_path)
    fleet_dir = tmp_path / "fleet"
    pnl_path = tmp_path / "pnl-statement.json"
    prereg_path = tmp_path / "prereg.md"
    prereg_path.write_text(PREREG_FIXTURE, encoding="utf-8")

    date = "2026-09-14"
    # risky-1 (control): fires and ENTERs the swing-pivot signal, then loses on it.
    _write_decisions(fleet_dir, "risky-1", [
        _row(date, "10:00", setup="INTRADAY_SWING_LOW", action="ENTER_BULL",
             reason="ribbon_ride C (ELITE)"),
    ])
    # risky-3 (challenger): same tick, refused by the anchor-class denylist.
    _write_decisions(fleet_dir, "risky-3", [
        _row(date, "10:00", setup="INTRADAY_SWING_LOW", action="HOLD",
             reason="gate: anchor_class_denied:INTRADAY_SWING_LOW_2026-09-14"),
    ])
    _write_pnl_statement(pnl_path, {date: {
        "risky-1": {"realized_pnl": -145.0},
        "risky-3": {"realized_pnl": 0.0},
    }})

    out = m.render_learned_today(fleet_dir=fleet_dir, pnl_path=pnl_path,
                                 prereg_path=prereg_path)
    text = "\n".join(out)
    assert "no sessions yet" not in text
    assert "risky-1 (control)" in text
    assert "risky-3 (H1: deny INTRADAY_SWING_ anchors)" in text
    assert "-145.00" in text  # control's realized $ on the session, reconciled verbatim
    assert "refused signals **1/6**" in text
    assert "-145.00 over 1 refusal-day(s) -- < 0 (holding)" in text
    assert "Tomorrow's change:** none (H1 clock running: 1/6 refused)" in text


# ------------------------------------------------------------------- KILL fires -> H2


def test_kill_criterion_names_next_ladder_row_from_prereg(tmp_path):
    m = _module(tmp_path)
    fleet_dir = tmp_path / "fleet"
    pnl_path = tmp_path / "pnl-statement.json"
    prereg_path = tmp_path / "prereg.md"
    prereg_path.write_text(PREREG_FIXTURE, encoding="utf-8")

    dates = [f"2026-09-{14 + i}" for i in range(6)]  # 6 refused signals, one per day
    risky1_rows, risky3_rows, per_day = [], [], {}
    for d in dates:
        risky1_rows.append(_row(d, "10:00", setup="INTRADAY_SWING_LOW", action="ENTER_BULL",
                                reason="ribbon_ride C (ELITE)"))
        risky3_rows.append(_row(d, "10:00", setup="INTRADAY_SWING_LOW", action="HOLD",
                                reason=f"gate: anchor_class_denied:INTRADAY_SWING_LOW_{d}"))
        # control WINS every one of these -> refused net >= 0 -> H1 kill criterion.
        per_day[d] = {"risky-1": {"realized_pnl": 50.0}, "risky-3": {"realized_pnl": 0.0}}
    _write_decisions(fleet_dir, "risky-1", risky1_rows)
    _write_decisions(fleet_dir, "risky-3", risky3_rows)
    _write_pnl_statement(pnl_path, per_day)

    out = m.render_learned_today(fleet_dir=fleet_dir, pnl_path=pnl_path,
                                 prereg_path=prereg_path)
    text = "\n".join(out)
    assert "refused signals **6/6**" in text
    assert ">= 0 (kill-side)" in text
    assert "H1 KILL criterion met" in text
    assert "H2 -- deny MEMORY_* as trigger anchor" in text


def test_kill_fires_but_prereg_unreadable_renders_na_not_exception(tmp_path):
    m = _module(tmp_path)
    fleet_dir = tmp_path / "fleet"
    pnl_path = tmp_path / "pnl-statement.json"
    dates = [f"2026-09-{14 + i}" for i in range(6)]
    risky1_rows, risky3_rows, per_day = [], [], {}
    for d in dates:
        risky1_rows.append(_row(d, "10:00", setup="INTRADAY_SWING_LOW", action="ENTER_BULL",
                                reason="ribbon_ride C (ELITE)"))
        risky3_rows.append(_row(d, "10:00", setup="INTRADAY_SWING_LOW", action="HOLD",
                                reason=f"gate: anchor_class_denied:INTRADAY_SWING_LOW_{d}"))
        per_day[d] = {"risky-1": {"realized_pnl": 50.0}, "risky-3": {"realized_pnl": 0.0}}
    _write_decisions(fleet_dir, "risky-1", risky1_rows)
    _write_decisions(fleet_dir, "risky-3", risky3_rows)
    _write_pnl_statement(pnl_path, per_day)

    out = m.render_learned_today(fleet_dir=fleet_dir, pnl_path=pnl_path,
                                 prereg_path=tmp_path / "does-not-exist.md")
    text = "\n".join(out)
    assert "H1 KILL criterion met" in text
    assert "n/a: could not read next LADDER row" in text


# ------------------------------------------------------- HOME wiring / single-section


def test_build_home_carries_exactly_one_learned_today_block(tmp_path, monkeypatch):
    m = _module(tmp_path)
    # Point every producer build_home touches at empty/tmp so this stays offline.
    monkeypatch.setattr(m, "STATE", tmp_path)
    monkeypatch.setattr(m, "JOURNAL", tmp_path)
    monkeypatch.setattr(m, "FLEET_DIR", tmp_path / "fleet")
    monkeypatch.setattr(m, "PNL_STATEMENT_PATH", tmp_path / "pnl-statement.json")
    monkeypatch.setattr(m, "PREREG_ANCHOR_CLASS_PATH", tmp_path / "does-not-exist.md")
    snap = {"ok": False, "arms": {}, "total_day": 0.0, "error": "offline test"}
    home = m.build_home("2026-09-12", "stamp", False, snap)
    assert home.count("## What Gamma learned today") == 1


# ------------------------------------------------------- plain-language brief summary (item 6B)
#
# GOAL-EARN-YOUR-KEEP item 6 part B: setup/scripts/daily_brief.py --mode eod appends "What Gamma
# learned today" via obsidian_vault_sync.learned_today_summary(), which reuses this file's own
# helpers/constants so it can never disagree with the HOME.md table above.


def test_learned_today_summary_no_sessions_yet(tmp_path):
    m = _module(tmp_path)
    fleet_dir = tmp_path / "fleet"
    _write_decisions(fleet_dir, "risky-3", [_row("2026-08-28", "10:00", setup=None)])
    _write_decisions(fleet_dir, "risky-1", [_row("2026-09-11", "10:00", setup="X")])
    out = m.learned_today_summary(fleet_dir=fleet_dir, pnl_path=tmp_path / "missing.json",
                                  prereg_path=tmp_path / "missing.md")
    assert out == "Challenger starts Monday; nothing to score yet."


def test_learned_today_summary_one_refused_signal(tmp_path):
    m = _module(tmp_path)
    fleet_dir = tmp_path / "fleet"
    pnl_path = tmp_path / "pnl-statement.json"
    date = "2026-09-14"
    _write_decisions(fleet_dir, "risky-1", [
        _row(date, "10:00", setup="INTRADAY_SWING_LOW", action="ENTER_BULL",
             reason="ribbon_ride C (ELITE)"),
    ])
    _write_decisions(fleet_dir, "risky-3", [
        _row(date, "10:00", setup="INTRADAY_SWING_LOW", action="HOLD",
             reason="gate: anchor_class_denied:INTRADAY_SWING_LOW_2026-09-14"),
    ])
    _write_pnl_statement(pnl_path, {date: {
        "risky-1": {"realized_pnl": -145.0},
        "risky-3": {"realized_pnl": 0.0},
    }})
    out = m.learned_today_summary(fleet_dir=fleet_dir, pnl_path=pnl_path,
                                  prereg_path=tmp_path / "missing.md")
    assert out == ("Challenger risky-3 refused 1 swing-pivot signal today that the control lost "
                   "$145.00 on. H1 clock 1 of 6. Tomorrow: no change.")


def test_learned_today_summary_kill_fires_names_next_row(tmp_path):
    m = _module(tmp_path)
    fleet_dir = tmp_path / "fleet"
    pnl_path = tmp_path / "pnl-statement.json"
    prereg_path = tmp_path / "prereg.md"
    prereg_path.write_text(PREREG_FIXTURE, encoding="utf-8")
    dates = [f"2026-09-{14 + i}" for i in range(6)]
    risky1_rows, risky3_rows, per_day = [], [], {}
    for d in dates:
        risky1_rows.append(_row(d, "10:00", setup="INTRADAY_SWING_LOW", action="ENTER_BULL",
                                reason="ribbon_ride C (ELITE)"))
        risky3_rows.append(_row(d, "10:00", setup="INTRADAY_SWING_LOW", action="HOLD",
                                reason=f"gate: anchor_class_denied:INTRADAY_SWING_LOW_{d}"))
        per_day[d] = {"risky-1": {"realized_pnl": 50.0}, "risky-3": {"realized_pnl": 0.0}}
    _write_decisions(fleet_dir, "risky-1", risky1_rows)
    _write_decisions(fleet_dir, "risky-3", risky3_rows)
    _write_pnl_statement(pnl_path, per_day)
    out = m.learned_today_summary(fleet_dir=fleet_dir, pnl_path=pnl_path, prereg_path=prereg_path)
    assert "H1 kill criterion met" in out
    assert "H2 -- deny MEMORY_* as trigger anchor" in out


def test_learned_today_summary_never_raises_on_missing_files(tmp_path):
    m = _module(tmp_path)
    out = m.learned_today_summary(
        fleet_dir=tmp_path / "does-not-exist",
        pnl_path=tmp_path / "also-missing.json",
        prereg_path=tmp_path / "missing-prereg.md",
    )
    assert out == "Challenger starts Monday; nothing to score yet."


def test_eod_brief_learned_today_line_present(monkeypatch, tmp_path):
    """setup/scripts/daily_brief.py::compose_eod_text must append the plain-language
    'What Gamma learned today' line, sourced from obsidian_vault_sync.learned_today_summary()."""
    daily_brief_path = REPO / "setup" / "scripts" / "daily_brief.py"
    db = _load(daily_brief_path, f"daily_brief_learned_{id(tmp_path)}")

    class _Fake:
        @staticmethod
        def learned_today_summary():
            return ("Challenger risky-3 refused 1 swing-pivot signal today that the control lost "
                    "$145.00 on. H1 clock 1 of 6. Tomorrow: no change.")

    monkeypatch.setitem(sys.modules, "obsidian_vault_sync", _Fake())

    facts = db.gather_eod_facts(
        "2026-09-14", pnl={"total_pnl": 0.0, "by_arm": []},
        trade_today={}, setups=[], queue_titles=[], dojo_info={"exists": False, "n_exhibits": 0},
    )
    text = db.compose_eod_text(facts)
    assert "What Gamma learned today" in text
    assert "Challenger risky-3 refused 1 swing-pivot signal today" in text
    assert "H1 clock 1 of 6" in text


def test_eod_brief_learned_today_no_sessions_yet(monkeypatch, tmp_path):
    daily_brief_path = REPO / "setup" / "scripts" / "daily_brief.py"
    db = _load(daily_brief_path, f"daily_brief_learned_none_{id(tmp_path)}")

    class _Fake:
        @staticmethod
        def learned_today_summary():
            return "Challenger starts Monday; nothing to score yet."

    monkeypatch.setitem(sys.modules, "obsidian_vault_sync", _Fake())

    facts = db.gather_eod_facts(
        "2026-09-13", pnl={"total_pnl": 0.0, "by_arm": []},
        trade_today={}, setups=[], queue_titles=[], dojo_info={"exists": False, "n_exhibits": 0},
    )
    text = db.compose_eod_text(facts)
    assert "What Gamma learned today: Challenger starts Monday; nothing to score yet." in text
