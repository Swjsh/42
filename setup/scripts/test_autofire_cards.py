"""Tests for autofire_cards.py -- the unattended runner that fires only the
cockpit action cards gamma_cockpit_cards.py already classified autofire_safe.

Covers the 7 scenarios the build asked for, plus a couple of guard-rail
extras: dry-run default, RTH refusal, halt-flag refusal, quiet-mode refusal
(+ override), per-run cap, per-day cap surviving a simulated restart, and an
unsafe card is never selected even when explicitly requested by id.

Run: pytest -v setup/scripts/test_autofire_cards.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "autofire_cards", Path(__file__).parent / "autofire_cards.py",
)
af = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(af)  # type: ignore[union-attr]


# --------------------------------------------------------------------- helpers

def _card(cid: str, rank: int, *, safe: bool = True, model: str = "sonnet") -> dict:
    return {
        "id": cid,
        "rank": rank,
        "title": "Card %s" % cid,
        "why": ["evidence for %s" % cid],
        "source_path": "automation/state/fake.json",
        "source_age_h": 1.0,
        "model": model,
        "gated": False,
        "autofire_safe": safe,
        "autofire_reason": "safe" if safe else "unsafe by design",
        "prompt": "OBJECTIVE: do the thing for %s" % cid,
    }


def _write_cards(tmp_path, monkeypatch, cards: list[dict]) -> None:
    p = tmp_path / "action-cards.json"
    p.write_text(json.dumps({"cards": cards}), encoding="utf-8")
    monkeypatch.setattr(af, "ACTION_CARDS_JSON", p)


def _wire_state(tmp_path, monkeypatch, *, rth: bool = False, quiet_active: bool = False,
                 halt: bool = False, token: str | None = "test-token-123",
                 ledger_seed: list[dict] | None = None) -> None:
    monkeypatch.setattr(af.et_clock, "is_market_hours", lambda *a, **k: rth)

    halt_flag = tmp_path / "companion-halt.flag"
    if halt:
        halt_flag.write_text("halted", encoding="utf-8")
    monkeypatch.setattr(af, "HALT_FLAG", halt_flag)

    quiet_json = tmp_path / "quiet-mode.json"
    quiet_json.write_text(json.dumps({"quiet_active": quiet_active}), encoding="utf-8")
    monkeypatch.setattr(af, "QUIET_MODE_JSON", quiet_json)

    token_file = tmp_path / ".companion-token"
    if token is not None:
        token_file.write_text(token, encoding="utf-8")
    monkeypatch.setattr(af, "TOKEN_FILE", token_file)

    ledger = tmp_path / "autofire-ledger.jsonl"
    if ledger_seed:
        ledger.write_text("\n".join(json.dumps(r) for r in ledger_seed) + "\n",
                           encoding="utf-8")
    monkeypatch.setattr(af, "LEDGER_JSONL", ledger)


def _read_ledger(tmp_path=None) -> list[dict]:
    return [json.loads(l) for l in af.LEDGER_JSONL.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def _fixed_et(monkeypatch, iso: str = "2026-08-29 20:00:00"):
    """Fixes et_clock.et_now() so ts_et/date_et are deterministic."""
    import datetime
    fixed = datetime.datetime.strptime(iso, "%Y-%m-%d %H:%M:%S")
    monkeypatch.setattr(af.et_clock, "et_now", lambda *a, **k: fixed)


# ------------------------------------------------------------------ dry-run default

def test_dry_run_is_the_default_and_never_posts(tmp_path, monkeypatch):
    _write_cards(tmp_path, monkeypatch, [_card("card-a", 1)])
    _wire_state(tmp_path, monkeypatch)
    _fixed_et(monkeypatch)

    called = {"n": 0}
    monkeypatch.setattr(af, "_post_approve", lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    rc = af.run(dry_run=True, max_per_run=2, max_per_day=6, allow_quiet=False, card_ids=None)
    assert rc == 0
    assert called["n"] == 0, "dry-run must never call _post_approve"

    rows = _read_ledger()
    assert len(rows) == 1
    assert rows[0]["decision"] == "dry-run"
    assert rows[0]["card_id"] == "card-a"


def test_cli_defaults_to_dry_run_when_neither_flag_passed(monkeypatch):
    captured = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(af, "run", _fake_run)
    monkeypatch.setattr(af.sys, "argv", ["autofire_cards.py"])

    rc = af.main()
    assert rc == 0
    assert captured["dry_run"] is True, "bare invocation (no --live) must resolve to dry_run=True"


def test_cli_explicit_live_flag_disables_dry_run(monkeypatch):
    captured = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(af, "run", _fake_run)
    monkeypatch.setattr(af.sys, "argv", ["autofire_cards.py", "--live"])

    rc = af.main()
    assert rc == 0
    assert captured["dry_run"] is False


# ------------------------------------------------------------------------- RTH

def test_rth_refuses_whole_run(tmp_path, monkeypatch):
    _write_cards(tmp_path, monkeypatch, [_card("card-a", 1)])
    _wire_state(tmp_path, monkeypatch, rth=True)
    _fixed_et(monkeypatch)

    posted = {"n": 0}
    monkeypatch.setattr(af, "_post_approve", lambda *a, **k: posted.__setitem__("n", posted["n"] + 1))

    rc = af.run(dry_run=False, max_per_run=2, max_per_day=6, allow_quiet=False, card_ids=None)
    assert rc == 0
    assert posted["n"] == 0

    rows = _read_ledger()
    assert len(rows) == 1
    assert rows[0]["decision"] == "refused"
    assert rows[0]["reason"] == "rth"
    assert rows[0]["card_id"] is None


# --------------------------------------------------------------------- halt-flag

def test_halt_flag_refuses_whole_run(tmp_path, monkeypatch):
    _write_cards(tmp_path, monkeypatch, [_card("card-a", 1)])
    _wire_state(tmp_path, monkeypatch, halt=True)
    _fixed_et(monkeypatch)

    rc = af.run(dry_run=True, max_per_run=2, max_per_day=6, allow_quiet=False, card_ids=None)
    assert rc == 0
    rows = _read_ledger()
    assert len(rows) == 1
    assert rows[0]["decision"] == "refused"
    assert rows[0]["reason"] == "halt-flag"


# --------------------------------------------------------------------- quiet-mode

def test_quiet_mode_refuses_whole_run_unless_overridden(tmp_path, monkeypatch):
    _write_cards(tmp_path, monkeypatch, [_card("card-a", 1)])
    _wire_state(tmp_path, monkeypatch, quiet_active=True)
    _fixed_et(monkeypatch)

    rc = af.run(dry_run=True, max_per_run=2, max_per_day=6, allow_quiet=False, card_ids=None)
    assert rc == 0
    rows = _read_ledger()
    assert len(rows) == 1
    assert rows[0]["decision"] == "refused"
    assert rows[0]["reason"] == "quiet-mode"


def test_quiet_mode_override_lets_the_run_proceed(tmp_path, monkeypatch):
    _write_cards(tmp_path, monkeypatch, [_card("card-a", 1)])
    _wire_state(tmp_path, monkeypatch, quiet_active=True)
    _fixed_et(monkeypatch)

    rc = af.run(dry_run=True, max_per_run=2, max_per_day=6, allow_quiet=True, card_ids=None)
    assert rc == 0
    rows = _read_ledger()
    # No whole-run refusal row; the one card gets a dry-run row instead.
    assert not any(r["decision"] == "refused" and r["reason"] == "quiet-mode" for r in rows)
    assert any(r["decision"] == "dry-run" and r["card_id"] == "card-a" for r in rows)


# ------------------------------------------------------------------------ caps

def test_per_run_cap_stops_after_n_selected(tmp_path, monkeypatch):
    cards = [_card("card-a", 1), _card("card-b", 2), _card("card-c", 3)]
    _write_cards(tmp_path, monkeypatch, cards)
    _wire_state(tmp_path, monkeypatch)
    _fixed_et(monkeypatch)

    rc = af.run(dry_run=True, max_per_run=2, max_per_day=6, allow_quiet=False, card_ids=None)
    assert rc == 0
    rows = _read_ledger()
    fired_or_dry = [r for r in rows if r["decision"] == "dry-run"]
    skipped = [r for r in rows if r["decision"] == "skipped"]
    assert len(fired_or_dry) == 2
    assert {r["card_id"] for r in fired_or_dry} == {"card-a", "card-b"}
    assert len(skipped) == 1
    assert skipped[0]["card_id"] == "card-c"
    assert skipped[0]["reason"] == "per-run-cap"


def test_per_day_cap_survives_a_simulated_restart(tmp_path, monkeypatch):
    """Seed the ledger as if 5 real fires already happened today (max_per_day=6),
    then start a FRESH `run()` call (a brand-new process, in spirit) and confirm
    only 1 more card fires even though max_per_run alone would allow more."""
    today = "2026-08-29"
    seed = [
        {"ts_et": "%s %02d:00:00" % (today, i), "date_et": today, "card_id": "seed-%d" % i,
         "rank": i, "decision": "fired", "reason": "posted", "dry_run": False,
         "ask_id": "ask-%d" % i, "http_status": 200}
        for i in range(5)
    ]
    cards = [_card("card-a", 1), _card("card-b", 2), _card("card-c", 3)]
    _write_cards(tmp_path, monkeypatch, cards)
    _wire_state(tmp_path, monkeypatch, ledger_seed=seed)
    _fixed_et(monkeypatch, iso="%s 20:00:00" % today)

    # Live mode this time -- but _post_approve is stubbed so nothing real is sent.
    fired_ids = []

    def _fake_post(card, token, base_url=af.DEFAULT_BASE_URL, timeout=af.POST_TIMEOUT_S):
        fired_ids.append(card["id"])
        return {"ok": True, "escalated": "ask-new-1", "status": 200}

    monkeypatch.setattr(af, "_post_approve", _fake_post)

    rc = af.run(dry_run=False, max_per_run=2, max_per_day=6, allow_quiet=False, card_ids=None)
    assert rc == 0
    assert fired_ids == ["card-a"], "day budget (6-5=1) must cap this run to exactly 1 fire"

    rows = _read_ledger()
    new_rows = [r for r in rows if r["card_id"] not in {"seed-%d" % i for i in range(5)}]
    fired = [r for r in new_rows if r["decision"] == "fired"]
    skipped = [r for r in new_rows if r["decision"] == "skipped"]
    assert len(fired) == 1 and fired[0]["card_id"] == "card-a"
    assert len(skipped) == 2
    assert {r["card_id"] for r in skipped} == {"card-b", "card-c"}
    assert all(r["reason"] == "per-day-cap" for r in skipped)


def test_fired_today_count_ignores_dry_run_and_fire_error_rows(tmp_path, monkeypatch):
    today = "2026-08-29"
    seed = [
        {"date_et": today, "card_id": "x1", "decision": "fired"},
        {"date_et": today, "card_id": "x2", "decision": "dry-run"},
        {"date_et": today, "card_id": "x3", "decision": "fire-error"},
        {"date_et": "2026-08-28", "card_id": "x4", "decision": "fired"},  # different day
    ]
    ledger = tmp_path / "autofire-ledger.jsonl"
    ledger.write_text("\n".join(json.dumps(r) for r in seed) + "\n", encoding="utf-8")
    monkeypatch.setattr(af, "LEDGER_JSONL", ledger)

    assert af._fired_today_count(today) == 1


# --------------------------------------------------------------- unsafe card guard

def test_unsafe_card_is_never_selected_even_when_requested_by_id(tmp_path, monkeypatch):
    cards = [_card("card-safe", 1, safe=True), _card("card-unsafe", 2, safe=False)]
    _write_cards(tmp_path, monkeypatch, cards)
    _wire_state(tmp_path, monkeypatch)
    _fixed_et(monkeypatch)

    posted = {"n": 0}
    monkeypatch.setattr(af, "_post_approve", lambda *a, **k: posted.__setitem__("n", posted["n"] + 1))

    rc = af.run(dry_run=False, max_per_run=2, max_per_day=6, allow_quiet=False,
                card_ids=["card-unsafe"])
    assert rc == 0
    assert posted["n"] == 0, "an unsafe card must never reach _post_approve, live or not"

    rows = _read_ledger()
    assert any(r["decision"] == "refused"
               and r["reason"] == "requested-card-not-autofire-safe"
               and r["card_id"] == "card-unsafe" for r in rows)
    # And no dry-run/fired/skipped row exists for it anywhere.
    assert not any(r["card_id"] == "card-unsafe" and r["decision"] in
                   ("dry-run", "fired", "skipped") for r in rows)


def test_requested_unknown_card_id_is_refused_not_crashed(tmp_path, monkeypatch):
    _write_cards(tmp_path, monkeypatch, [_card("card-a", 1)])
    _wire_state(tmp_path, monkeypatch)
    _fixed_et(monkeypatch)

    rc = af.run(dry_run=True, max_per_run=2, max_per_day=6, allow_quiet=False,
                card_ids=["card-does-not-exist"])
    assert rc == 0
    rows = _read_ledger()
    assert any(r["decision"] == "refused" and r["reason"] == "requested-card-not-found"
               for r in rows)


# ------------------------------------------------------------------ live wiring

def test_live_without_token_refuses_whole_run(tmp_path, monkeypatch):
    _write_cards(tmp_path, monkeypatch, [_card("card-a", 1)])
    _wire_state(tmp_path, monkeypatch, token=None)
    _fixed_et(monkeypatch)

    rc = af.run(dry_run=False, max_per_run=2, max_per_day=6, allow_quiet=False, card_ids=None)
    assert rc == 0
    rows = _read_ledger()
    assert len(rows) == 1
    assert rows[0]["decision"] == "refused"
    assert rows[0]["reason"] == "no-token"


def test_live_fire_posts_with_expected_shape(tmp_path, monkeypatch):
    _write_cards(tmp_path, monkeypatch, [_card("card-a", 1, model="sonnet")])
    _wire_state(tmp_path, monkeypatch, token="tok-abc")
    _fixed_et(monkeypatch)

    seen = {}

    def _fake_post(card, token, base_url=af.DEFAULT_BASE_URL, timeout=af.POST_TIMEOUT_S):
        seen["card_id"] = card["id"]
        seen["token"] = token
        return {"ok": True, "escalated": "ask-999", "status": 200}

    monkeypatch.setattr(af, "_post_approve", _fake_post)

    rc = af.run(dry_run=False, max_per_run=2, max_per_day=6, allow_quiet=False, card_ids=None)
    assert rc == 0
    assert seen["card_id"] == "card-a"
    assert seen["token"] == "tok-abc"

    rows = _read_ledger()
    assert rows[0]["decision"] == "fired"
    assert rows[0]["ask_id"] == "ask-999"


def test_fire_error_does_not_count_toward_day_cap(tmp_path, monkeypatch):
    _write_cards(tmp_path, monkeypatch, [_card("card-a", 1)])
    _wire_state(tmp_path, monkeypatch, token="tok-abc")
    _fixed_et(monkeypatch)

    monkeypatch.setattr(af, "_post_approve",
                         lambda *a, **k: {"ok": False, "error": "boom", "status": 500})

    rc = af.run(dry_run=False, max_per_run=2, max_per_day=6, allow_quiet=False, card_ids=None)
    assert rc == 0
    rows = _read_ledger()
    assert rows[0]["decision"] == "fire-error"
    assert af._fired_today_count("2026-08-29") == 0
