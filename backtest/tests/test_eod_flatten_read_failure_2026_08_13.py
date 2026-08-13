"""Guard: a failed position read must never render as "already flat" at the 15:55 flatten.

THE UNBOUNDED CASE. fleet_broker.get_positions collapses ANY read failure to []:

    res = _request(creds, "positions")
    return res if isinstance(res, list) else []      # a timeout returns {"_error": ...}

so an unreadable arm is indistinguishable from a flat one. eod_flatten read that [], computed
qty_total == 0, logged "EOD_FLATTEN_NOOP -- already flat", and returned.

On 2026-08-13 bold-2's /v2/positions hung at 15s for ~15 minutes while /v2/clock and /v2/orders
answered in 0.2s -- that arm only. In the exit loop that cost $40 (a stop fired ~15 min late, at
0.24 against a 0.32 stop level). Had the same window covered 15:55, a live 0DTE contract would
have EXPIRED while the log said everything was fine. On 0DTE a missed flatten is not a delayed
exit, it is total loss.

WHY get_positions ITSELF IS UNCHANGED: its fail-open behaviour is deliberate and documented for
the exit manager's per-tick re-derivation ("simply re-tries every minute regardless"). That
reasoning holds for INDEPENDENT failures. Today's were CORRELATED -- one endpoint down for 15
minutes -- which is exactly when "it'll retry" stops being true. Flipping a documented default
under every caller is a bigger change than adding the checked read for callers that cannot
tolerate a false "flat", which is the shape the repo already chose on 2026-08-02
(open_buy_orders_checked / symbol_position_qty_checked).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FB = REPO / "automation" / "state" / "fleet" / "fleet_broker.py"
EOD = REPO / "setup" / "scripts" / "eod_flatten.py"


@pytest.fixture(scope="module")
def fb():
    sys.path.insert(0, str(FB.parent))
    spec = importlib.util.spec_from_file_location("_fb_probe", FB)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_fb_probe"] = m
    spec.loader.exec_module(m)
    return m


CREDS = {"key": "k", "secret": "s", "base_url": "https://x"}


def test_a_failed_read_is_distinguishable_from_flat(fb, monkeypatch):
    """THE WHOLE POINT. Both return an empty list; only `ok` separates them."""
    monkeypatch.setattr(fb, "_request", lambda *a, **k: {"_error": "TimeoutError"})
    pos, ok = fb.open_spy_option_positions_checked(CREDS)
    assert (pos, ok) == ([], False), "a failed read must report ok=False"

    monkeypatch.setattr(fb, "_request", lambda *a, **k: [])
    pos2, ok2 = fb.open_spy_option_positions_checked(CREDS)
    assert (pos2, ok2) == ([], True), "a genuinely flat account must report ok=True"


def test_a_raising_request_is_also_ok_false(fb, monkeypatch):
    """Never raises -- a guard primitive that crashes the 15:55 tick is worse than the bug."""
    def boom(*a, **k):
        raise RuntimeError("network gone")
    monkeypatch.setattr(fb, "_request", boom)
    assert fb.open_spy_option_positions_checked(CREDS) == ([], False)


def test_real_positions_still_come_through(fb, monkeypatch):
    monkeypatch.setattr(fb, "_request", lambda *a, **k: [
        {"symbol": "SPY260813C00777000", "qty": "3", "asset_class": "option"},
        {"symbol": "AAPL", "qty": "10", "asset_class": "us_equity"},
    ])
    pos, ok = fb.open_spy_option_positions_checked(CREDS)
    assert ok is True
    assert [p["symbol"] for p in pos] == ["SPY260813C00777000"], "SPY-option filter broke"


def test_the_unchecked_variant_still_fails_open(fb, monkeypatch):
    """Pins the PREMISE. If get_positions is ever made fail-closed, every caller's behaviour
    changes at once and this whole guard needs re-deriving rather than trusting."""
    monkeypatch.setattr(fb, "_request", lambda *a, **k: {"_error": "TimeoutError"})
    assert fb.get_positions(CREDS) == [], "get_positions no longer fails open -- re-derive this"
    assert fb.is_flat_spy_options(CREDS) is True, (
        "is_flat_spy_options no longer returns True on a failed read. That is arguably better, "
        "but it changes the entry path too -- verify fleet_live's placement gate before "
        "accepting it, and update this guard in that commit.")


# ------------------------------------------------------------------ the consumer


def test_eod_flatten_uses_the_checked_read_and_never_reports_NOOP_on_failure():
    """C7. 'Could not measure' must never render as 'measured and fine' -- especially in the
    one routine whose failure mode is a 0DTE expiry."""
    src = EOD.read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert "open_spy_option_positions_checked" in code, (
        "eod_flatten no longer uses the checked read -- a broker timeout will again be logged "
        "as 'already flat' while a live 0DTE contract expires")
    assert "READ_FAILED" in code, "the READ_FAILED outcome was removed"
    # the failure branch must return BEFORE the qty_total==0 NOOP branch
    i_fail = code.index("READ_FAILED")
    i_noop = code.index("EOD_FLATTEN_NOOP")
    assert i_fail < i_noop, (
        "the READ_FAILED check no longer precedes the NOOP branch -- an unreadable arm can "
        "reach 'already flat' again")


def test_eod_flatten_retries_before_giving_up():
    src = EOD.read_text(encoding="utf-8")
    assert "READ_ATTEMPTS" in src and "READ_RETRY_S" in src
    ns: dict = {}
    for line in src.splitlines():
        if line.startswith("READ_ATTEMPTS") or line.startswith("READ_RETRY_S"):
            exec(line, ns)  # noqa: S102 -- reading two module constants
    assert ns["READ_ATTEMPTS"] >= 2, "a single attempt cannot distinguish a blip from an outage"
    assert ns["READ_ATTEMPTS"] * ns["READ_RETRY_S"] <= 30, (
        "total retry budget is too long for the 15:55 flatten window")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
