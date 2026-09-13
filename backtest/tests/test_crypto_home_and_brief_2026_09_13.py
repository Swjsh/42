"""Guards for GOAL-EARN-YOUR-KEEP item 7d -- the crypto (24/7 proving ground) surfaces:
obsidian_vault_sync.py::render_crypto_challenger_block() (HOME.md's new subsection, living
INSIDE the existing '## What Gamma learned today' block, never a second block) and
daily_brief.py::_crypto_challenger_brief_line() (the shared morning/EOD one-liner). Both
read the SAME challenger-h1-summary.json (crypto_twin_challenger.py, item 7c) so the two
surfaces can never disagree.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VAULT_SYNC = REPO / "setup" / "scripts" / "obsidian_vault_sync.py"
DAILY_BRIEF = REPO / "setup" / "scripts" / "daily_brief.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _ovs(tmp_path):
    return _load(VAULT_SYNC, f"obsidian_vault_sync_crypto_{id(tmp_path)}")


def _brief(tmp_path):
    return _load(DAILY_BRIEF, f"daily_brief_crypto_{id(tmp_path)}")


_FIXTURE_SUMMARY = {
    "generated_at_utc": "2026-09-14T12:00:00+00:00",
    "h1_refuse_class": "SWING_PIVOT",
    "h1_forward_start_utc": "2026-09-13T16:25:00+00:00",
    "kill_n": 6, "ship_n": 20,
    "windows": {
        "last_4h": {"control_n": 1, "control_net_usd": -2.5, "refused_n": 1,
                   "refused_net_usd": -2.5, "challenger_net_usd": 0.0},
        "last_24h": {"control_n": 3, "control_net_usd": 4.0, "refused_n": 1,
                    "refused_net_usd": -2.5, "challenger_net_usd": 6.5},
        "forward_since_start": {"control_n": 3, "control_net_usd": 4.0, "refused_n": 1,
                               "refused_net_usd": -2.5, "challenger_net_usd": 6.5},
        "historical_in_sample": {"control_n": 215, "control_net_usd": -23.42, "refused_n": 78,
                                "refused_net_usd": -21.32, "challenger_net_usd": -2.10},
    },
    "kill_ship_status": {"status": "RUNNING", "n": 1, "net_usd": -2.5,
                        "kill_progress": "1/6", "ship_progress": "1/20", "f1_sign_holds": True},
    "f1_sign": "refused net < 0 (holds)",
    "tomorrow_change": "none (H1-crypto clock running: 1/6 refused)",
    "n_ledger_rows": 216,
}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# ============================================================================
# obsidian_vault_sync.render_crypto_challenger_block()
# ============================================================================
def test_render_crypto_block_na_when_summary_missing(tmp_path, monkeypatch):
    m = _ovs(tmp_path)
    monkeypatch.setattr(m, "STATE", tmp_path)
    monkeypatch.setattr(m, "_pid_alive", lambda pid: None)
    out = m.render_crypto_challenger_block()
    text = "\n".join(out)
    assert text.startswith("### Crypto (24/7 proving ground)")
    assert "n/a" in text
    # no live-health data files either -> the health line still renders, all n/a
    assert "pid `n/a`" in text


def test_render_crypto_block_populated_shows_all_four_windows(tmp_path, monkeypatch):
    m = _ovs(tmp_path)
    monkeypatch.setattr(m, "STATE", tmp_path)
    monkeypatch.setattr(m, "_pid_alive", lambda pid: True)
    _write_json(tmp_path / "crypto-twin" / "challenger-h1-summary.json", _FIXTURE_SUMMARY)
    _write_json(tmp_path / "twin-health.json", {"last_tick_et": "2026-09-14T12:00:00"})
    _write_json(tmp_path / "crypto-twin-loop.pid", {"pid": 4242, "launched_at": "2026-09-13T10:00:00"})
    _write_json(tmp_path / "crypto-twin" / "breaker.json",
               {"tripped": False, "current_equity": 8950.12})

    out = m.render_crypto_challenger_block()
    text = "\n".join(out)

    assert "### Crypto (24/7 proving ground)" in text
    assert "refuse `SWING_PIVOT`" in text
    assert "Last 4h" in text and "Last 24h" in text
    assert "Forward since start" in text and "Historical (in-sample)" in text
    # last_24h control/refused numbers land in the table
    assert "3" in text and "-2.50" in text
    assert "1/6" in text and "1/20" in text
    assert "none (H1-crypto clock running: 1/6 refused)" in text
    assert "pid `4242` (alive)" in text
    assert "last tick `2026-09-14T12:00:00`" in text
    assert "breaker ok" in text
    assert "equity +8,950.12" in text
    assert "cash n/a" in text  # no state file carries cash -- honestly labelled, not fabricated


def test_render_crypto_block_never_adds_a_level2_heading(tmp_path, monkeypatch):
    """Structural guard for the task's own DONE-WHEN: this subsection must live INSIDE
    the existing '## What Gamma learned today' block, so grep -c "What Gamma learned
    today" stays == 1 after this subsection is appended. Confirmed by construction: the
    block never emits a '## ' (level-2) heading, only '### ' (level-3)."""
    m = _ovs(tmp_path)
    monkeypatch.setattr(m, "STATE", tmp_path)
    monkeypatch.setattr(m, "_pid_alive", lambda pid: None)
    _write_json(tmp_path / "crypto-twin" / "challenger-h1-summary.json", _FIXTURE_SUMMARY)
    out = m.render_crypto_challenger_block()
    assert not any(line.startswith("## ") for line in out)
    assert any(line.startswith("### Crypto") for line in out)


def test_render_crypto_block_breaker_tripped_true(tmp_path, monkeypatch):
    m = _ovs(tmp_path)
    monkeypatch.setattr(m, "STATE", tmp_path)
    monkeypatch.setattr(m, "_pid_alive", lambda pid: False)
    _write_json(tmp_path / "crypto-twin" / "breaker.json", {"tripped": True, "current_equity": 8000.0})
    out = m.render_crypto_challenger_block()
    text = "\n".join(out)
    assert "breaker TRIPPED" in text
    assert "pid `n/a` (n/a)" in text  # no pid file -> pid n/a, alive not even checked


# ============================================================================
# daily_brief._crypto_challenger_brief_line()
# ============================================================================
def test_brief_line_none_when_summary_missing(tmp_path, monkeypatch):
    m = _brief(tmp_path)
    monkeypatch.setattr(m, "REPO", tmp_path)
    assert m._crypto_challenger_brief_line() is None


def test_brief_line_matches_the_required_template(tmp_path, monkeypatch):
    m = _brief(tmp_path)
    monkeypatch.setattr(m, "REPO", tmp_path)
    _write_json(tmp_path / "automation" / "state" / "crypto-twin" / "challenger-h1-summary.json",
               _FIXTURE_SUMMARY)
    line = m._crypto_challenger_brief_line()
    assert line == ("Crypto 24/7: control 3 trades $+4.00 last 24h; H1 refused 1, "
                    "net $-2.50; tomorrow: none (H1-crypto clock running: 1/6 refused)")


def test_brief_line_wired_into_eod_and_morning(tmp_path, monkeypatch):
    m = _brief(tmp_path)
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "_crypto_challenger_brief_line",
                        lambda: "Crypto 24/7: control 3 trades $+4.00 last 24h; H1 refused 1, "
                                "net $-2.50; tomorrow: none (H1-crypto clock running: 1/6 refused)")
    monkeypatch.setattr(m, "_liveness_alarm", lambda day: None)
    monkeypatch.setattr(m, "_blind_alarm", lambda day: None)
    monkeypatch.setattr(m, "_refusals_eod_line", lambda day: None)
    monkeypatch.setattr(m, "_learned_today_eod_line", lambda day: None)
    monkeypatch.setattr(m, "_crypto_overnight_line", lambda: "Crypto overnight: n/a.")
    monkeypatch.setattr(m, "_trendline_morning_line", lambda: "Trendlines: n/a.")

    eod_facts = {"day": "2026-09-14", "total_pnl": None, "n_filled": 0, "n_unfilled": 0,
                "by_arm": [], "setups": [], "queue_titles": [], "dojo": {}}
    eod_text = m.compose_eod_text(eod_facts)
    assert "Crypto 24/7: control 3 trades" in eod_text

    morning_facts = {"day": "2026-09-14", "readiness_line": None, "bias": "flat",
                    "bias_reason": "n/a", "levels": [], "safe_breaker": "ok",
                    "bold_breaker": "ok", "overnight_headers": [], "ribbon_scope": None}
    morning_text = m.compose_morning_text(morning_facts)
    assert "Crypto 24/7: control 3 trades" in morning_text
