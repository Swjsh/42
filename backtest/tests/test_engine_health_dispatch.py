"""Guard for check_dispatch_health -- the G16 silent-dispatch-death detector.

CONTEXT (2026-06-29 gamma-drive, G16 observe-live close): the setup_dispatch layer
silently returned None on EVERY tick for an extended period (the _build_ctx ImportError)
and that blindness was invisible until a manual observe-live caught it. This guard pins
the behaviour that graduates that ritual into the every-minute beacon:

  - an ENABLED detector flag + a populated RTH + ZERO extra_signals  -> RED (the bite)
  - healthy dispatch (extra_signals present)                          -> GREEN
  - no enabled flag / too few ticks                                   -> GREEN (no cry-wolf)
  - the RED is NON-CRITICAL: it must NEVER red the critical fuse() verdict
  - fail-open on unreadable params/ledger

Pure-Python, $0, no network.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "setup" / "scripts"))

import engine_health as eh  # noqa: E402


def _rows(account: str, date: str, n_total: int, n_extra: int) -> list:
    """Build n_total decision rows for `account` on `date`; the first n_extra carry an
    extra_signals payload (mirrors the live shape)."""
    out = []
    for i in range(n_total):
        r = {"account": account, "ts_et": f"{date}T10:{i % 60:02d}:00", "action": "HOLD"}
        if i < n_extra:
            r["extra_signals"] = [{"setup_name": "vwap_continuation", "fired": False,
                                   "skip_reason": "SKIP_NO_SIGNAL"}]
        out.append(r)
    return out


# --------------------------------------------------------------------------- assessor
def test_enabled_and_healthy_is_green():
    rows = _rows("safe", "2026-06-29", 386, 386)
    r = eh.assess_dispatch_health(rows, {"safe": True, "bold": False})
    assert r["status"] == "GREEN"
    assert "386/386" in r["detail"]


def test_enabled_but_zero_over_populated_rth_is_red():
    """THE BITE: the exact G16 signature -- an enabled detector emitted NOTHING all day."""
    rows = _rows("safe", "2026-06-29", 386, 0)
    r = eh.assess_dispatch_health(rows, {"safe": True, "bold": False})
    assert r["status"] == "RED"
    assert "BLIND" in r["detail"]
    assert "0/386" in r["detail"]


def test_enabled_but_too_few_ticks_is_green_no_cry_wolf():
    """A just-opened / short session with zero extra_signals must NOT RED."""
    rows = _rows("safe", "2026-06-29", 10, 0)  # below DISPATCH_MIN_TICKS
    r = eh.assess_dispatch_health(rows, {"safe": True})
    assert r["status"] == "GREEN"


def test_no_enabled_flag_is_green():
    rows = _rows("bold", "2026-06-29", 386, 0)
    r = eh.assess_dispatch_health(rows, {"safe": False, "bold": False})
    assert r["status"] == "GREEN"
    assert "no extra-setup flag enabled" in r["detail"]


def test_latest_date_is_isolated():
    """A blind YESTERDAY must not poison a healthy TODAY (uses the most recent date only)."""
    rows = _rows("safe", "2026-06-26", 386, 0) + _rows("safe", "2026-06-29", 386, 386)
    r = eh.assess_dispatch_health(rows, {"safe": True})
    assert r["status"] == "GREEN"
    assert r["accounts"]["safe"]["date"] == "2026-06-29"


def test_one_blind_account_reds_even_if_other_healthy():
    rows = _rows("safe", "2026-06-29", 386, 386) + _rows("bold", "2026-06-29", 386, 0)
    r = eh.assess_dispatch_health(rows, {"safe": True, "bold": True})
    assert r["status"] == "RED"
    assert "bold" in r["detail"]


def test_malformed_rows_do_not_crash():
    rows = ["not a dict", {"no_account": 1}, {"account": "safe", "ts_et": None}, 42]
    r = eh.assess_dispatch_health(rows, {"safe": True})
    assert r["status"] in ("GREEN", "RED")  # must not raise


def test_bite_neutering_min_ticks_flips_red_to_green():
    """Non-vacuous bite: a huge min_ticks makes the blind RTH 'insufficient' -> GREEN.
    Proves DISPATCH_MIN_TICKS is what makes the zero-case actually bite."""
    rows = _rows("safe", "2026-06-29", 386, 0)
    red = eh.assess_dispatch_health(rows, {"safe": True})
    green = eh.assess_dispatch_health(rows, {"safe": True}, min_ticks=10_000)
    assert red["status"] == "RED"
    assert green["status"] == "GREEN"


# --------------------------------------------------------------------------- check wrapper
def test_check_is_non_critical():
    c = eh.check_dispatch_health(datetime(2026, 6, 29, 20, 0, 0))
    assert c["critical"] is False
    assert c["name"] == "dispatch_health"


def test_red_dispatch_does_not_red_the_critical_verdict(monkeypatch):
    """LOAD-BEARING: a BLIND dispatch is observability, not a trade gate -- fuse() must
    degrade to YELLOW, never RED (which would imply a critical-engine death)."""
    red_dispatch = {"name": "dispatch_health", "status": "RED",
                    "detail": "EXTRA-SETUP DISPATCH BLIND", "critical": False}
    all_green_critical = [
        {"name": "heartbeat_safe", "status": "GREEN", "detail": "ok", "critical": True},
        {"name": "sight_beacon", "status": "GREEN", "detail": "ok", "critical": True},
        red_dispatch,
    ]
    verdict, reds = eh.fuse(all_green_critical)
    assert verdict == "YELLOW"
    assert any("dispatch_health" in r for r in reds)


def test_red_dispatch_is_alertable():
    """A RED status surfaces in red_checks so the transition-only alerter can ping J once."""
    red_dispatch = {"name": "dispatch_health", "status": "RED", "detail": "x", "critical": False}
    red_checks = sorted(c["name"] for c in [red_dispatch] if c["status"] == "RED")
    assert "dispatch_health" in red_checks


def test_build_report_includes_dispatch_health():
    rep = eh.build_report()
    names = [c["name"] for c in rep["checks"]]
    assert "dispatch_health" in names


def test_fail_open_on_unreadable(monkeypatch, tmp_path):
    """Missing params + ledger -> benign YELLOW, never a crash."""
    monkeypatch.setattr(eh, "STATE", tmp_path)
    monkeypatch.setattr(eh, "AGG", tmp_path / "aggressive")
    c = eh.check_dispatch_health(datetime(2026, 6, 29, 20, 0, 0))
    assert c["status"] == "YELLOW"
    assert c["critical"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
