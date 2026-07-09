"""Guard for open_bell_status.py -- the OPEN-BELL status push (OP-33e).

Covers the three load-bearing contracts the script must hold:
  1. Message composition is correct from fixture state (GREEN case; a stale-breaker
     case must show "re-armed-today NO" for the stale account only).
  2. Idempotency -- a second call the same ET day must NOT double-send.
  3. Fail-open -- every input file may be missing/garbled and the script must still
     exit 0 and compose SOME message, never raise.

Imports the script by path (not a package), matching this repo's engine_health.py test
convention (backtest/tests/test_engine_health_*.py).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

# --- import setup/scripts/open_bell_status.py by path ---
_REPO = Path(__file__).resolve().parents[2]
_OBS_PATH = _REPO / "setup" / "scripts" / "open_bell_status.py"
_spec = importlib.util.spec_from_file_location("open_bell_status_under_test", _OBS_PATH)
obs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(obs)


# --------------------------------------------------------------------------- #
# Pure message composition -- no IO, deterministic fixtures.
# --------------------------------------------------------------------------- #

_GREEN_ENGINE_HEALTH = {"verdict": "GREEN"}
_GREEN_SAFE_BREAKER = {"tripped": False, "last_reset": "2026-07-09T08:30:00-04:00"}
_GREEN_BOLD_BREAKER = {"tripped": False, "session_id": "2026-07-09"}
_NEWEST_TICK = {"ts_et": "2026-07-09T09:35:42", "account": "safe"}
_TRADE_TODAY_SOME_FILLS = {"spy_fills_today": 20, "placed_not_filled_today": 2}
_TRADE_TODAY_NONE = {"spy_fills_today": 0, "placed_not_filled_today": 0}


def _compose(**overrides):
    base = dict(
        today="2026-07-09", now_et_str="09:36", engine_health=_GREEN_ENGINE_HEALTH,
        safe_breaker=_GREEN_SAFE_BREAKER, bold_breaker=_GREEN_BOLD_BREAKER,
        newest_tick=_NEWEST_TICK, now_et_minutes=0.3, trade_today=_TRADE_TODAY_SOME_FILLS,
    )
    base.update(overrides)
    return obs.compose_message(**base)


def test_green_case_message_shows_verdict_and_both_armed_rearmed():
    msg = _compose()
    assert "GREEN" in msg
    assert "Safe armed, re-armed-today YES" in msg
    assert "Bold armed, re-armed-today YES" in msg
    assert "20 filled, 2 placed-not-filled" in msg
    assert "2026-07-09" in msg


def test_stale_breaker_case_shows_rearmed_today_no_for_stale_account_only():
    """The load-bearing case: safe is stale-dated (yesterday), bold is fresh -- the
    message must discriminate PER ACCOUNT, not blanket-fail both."""
    stale_safe = {"tripped": False, "last_reset": "2026-07-08T08:31:00-04:00"}
    msg = _compose(safe_breaker=stale_safe)
    assert "Safe armed, re-armed-today NO" in msg
    assert "Bold armed, re-armed-today YES" in msg


def test_tripped_breaker_overrides_rearm_status():
    tripped = {"tripped": True, "tripped_reason": "daily_loss_31.0%_>=_30%_limit",
               "last_reset": "2026-07-09T08:30:00-04:00"}
    msg = _compose(safe_breaker=tripped)
    assert "TRIPPED" in msg
    assert "daily_loss_31.0%" in msg


def test_no_fills_yet_is_explicit_not_blank():
    msg = _compose(trade_today=_TRADE_TODAY_NONE)
    assert "Fills: none yet" in msg


def test_bite_today_dated_flips_stale_case_to_yes():
    """Prove the date-equality check (not some unconditional branch) drives YES/NO."""
    fresh = {"tripped": False, "last_reset": "2026-07-09T08:30:00-04:00"}
    stale = {"tripped": False, "last_reset": "2026-07-08T08:30:00-04:00"}
    assert "re-armed-today YES" in _compose(safe_breaker=fresh).split("|")[0]
    assert "re-armed-today NO" in _compose(safe_breaker=stale).split("|")[0]


# --------------------------------------------------------------------------- #
# Fail-open: every input may be None/missing -- compose_message must never raise
# and must produce an honest "unknown" rather than a fabricated status.
# --------------------------------------------------------------------------- #

def test_all_inputs_none_never_raises_and_reports_unknown():
    msg = obs.compose_message(
        today="2026-07-09", now_et_str="09:36", engine_health=None,
        safe_breaker=None, bold_breaker=None, newest_tick=None,
        now_et_minutes=None, trade_today=None,
    )
    assert "UNKNOWN" in msg
    assert "unknown (breaker file unreadable)" in msg
    assert "no core-decisions.jsonl row found" in msg
    assert "unknown (trade-today.json unreadable)" in msg


# --------------------------------------------------------------------------- #
# main() end-to-end: idempotency + fail-open, against a monkeypatched tmp state dir.
# --------------------------------------------------------------------------- #

def _point_state(monkeypatch, tmp_path: Path, *, write_fixtures: bool = True):
    eh = tmp_path / "engine-health.json"
    safe_b = tmp_path / "circuit-breaker.json"
    bold_b = tmp_path / "circuit-breaker-bold.json"
    core = tmp_path / "core-decisions.jsonl"
    trade = tmp_path / "trade-today.json"
    outbox = tmp_path / "discord-outbox.jsonl"
    pinged = tmp_path / "open-bell-pinged.json"
    cfg = tmp_path / ".discord-config.json"

    if write_fixtures:
        eh.write_text(json.dumps(_GREEN_ENGINE_HEALTH), encoding="utf-8")
        safe_b.write_text(json.dumps(_GREEN_SAFE_BREAKER), encoding="utf-8")
        bold_b.write_text(json.dumps(_GREEN_BOLD_BREAKER), encoding="utf-8")
        core.write_text(json.dumps(_NEWEST_TICK) + "\n", encoding="utf-8")
        trade.write_text(json.dumps(_TRADE_TODAY_SOME_FILLS), encoding="utf-8")
        cfg.write_text(json.dumps({"user_id": "207983230618435584"}), encoding="utf-8")

    monkeypatch.setattr(obs, "ENGINE_HEALTH_PATH", eh)
    monkeypatch.setattr(obs, "SAFE_BREAKER_PATH", safe_b)
    monkeypatch.setattr(obs, "BOLD_BREAKER_PATH", bold_b)
    monkeypatch.setattr(obs, "CORE_DECISIONS_PATH", core)
    monkeypatch.setattr(obs, "TRADE_TODAY_PATH", trade)
    monkeypatch.setattr(obs, "OUTBOX", outbox)
    monkeypatch.setattr(obs, "PINGED_FILE", pinged)
    monkeypatch.setattr(obs, "DISCORD_CFG", cfg)
    return outbox, pinged


def _outbox_lines(outbox: Path) -> list[dict]:
    if not outbox.exists():
        return []
    return [json.loads(ln) for ln in outbox.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_main_sends_once_and_writes_pinged_marker(monkeypatch, tmp_path):
    outbox, pinged = _point_state(monkeypatch, tmp_path)
    rc = obs.main()
    assert rc == 0
    lines = _outbox_lines(outbox)
    assert len(lines) == 1
    assert lines[0]["source"] == "open_bell_status"
    assert "<@207983230618435584>" in lines[0]["content"]
    assert pinged.exists()
    marker = json.loads(pinged.read_text(encoding="utf-8"))
    assert marker["date"] == obs.et_today_str()


def test_main_second_call_same_day_does_not_double_send(monkeypatch, tmp_path):
    outbox, pinged = _point_state(monkeypatch, tmp_path)
    assert obs.main() == 0
    assert obs.main() == 0  # second fire, e.g. a manual re-run or retry
    lines = _outbox_lines(outbox)
    assert len(lines) == 1, "idempotency broken: a second same-day call must not re-queue"


def test_already_sent_today_short_circuits_before_any_read(monkeypatch, tmp_path):
    """If PINGED_FILE already claims today, main() must skip before touching engine-health
    etc. -- prove this via a picky boom-fixture that allows ONLY the PINGED_FILE read
    (which already_sent_today() itself needs) and raises on any OTHER path, so the test
    fails loudly if main() ever reaches a downstream read after the short-circuit."""
    outbox, pinged = _point_state(monkeypatch, tmp_path, write_fixtures=False)

    def picky(path):
        if path == pinged:
            return {"date": obs.et_today_str()}
        raise AssertionError(f"should not read {path} when already sent today")
    monkeypatch.setattr(obs, "_read_json", picky)
    assert obs.main() == 0
    assert _outbox_lines(outbox) == []


def test_main_fail_open_on_totally_missing_state(monkeypatch, tmp_path):
    """No fixtures written at all (missing engine-health/breakers/decisions/trade-today,
    missing discord config) -- main() must still exit 0 and still queue an honest
    'unknown everywhere' message rather than crashing the scheduled chain."""
    outbox, pinged = _point_state(monkeypatch, tmp_path, write_fixtures=False)
    rc = obs.main()
    assert rc == 0
    lines = _outbox_lines(outbox)
    assert len(lines) == 1
    assert "UNKNOWN" in lines[0]["content"]
    # No .discord-config.json -> _load_user_mention fails open to "" (no mention prefix).
    assert not lines[0]["content"].startswith("<@")


def test_main_never_raises_even_if_outbox_dir_is_unwritable(monkeypatch, tmp_path):
    """Point OUTBOX at a path whose parent doesn't exist -- the open() will fail; main()
    must catch it, print to stderr, and still return 0 (never crash the scheduled chain)."""
    _point_state(monkeypatch, tmp_path)
    monkeypatch.setattr(obs, "OUTBOX", tmp_path / "no_such_dir" / "outbox.jsonl")
    rc = obs.main()
    assert rc == 0
