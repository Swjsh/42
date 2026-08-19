"""Guard: the book-exposure cap must not be inert for a whole session.

SCAR (2026-08-19). The cap was armed 2026-08-18 with `record_arm_equity` wired into
`heartbeat_core._execute` -- which only runs on an ENTER verdict. On 2026-08-19 the engine
ticked 772 times and the cap reported DEGRADED for the ENTIRE session, because no arm had
refreshed its equity before the first entry attempt. It failed OPEN exactly as designed, so
nothing was mis-blocked -- but the protection was inert all day.

A guard that only arms itself after the thing it guards has already happened is not a guard.
These tests pin the refresher's contract, and that the cap actually clears once it runs.
Pure/offline -- no network.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)  # type: ignore[union-attr]
    return m


be = _load("book_exposure_r", "setup/scripts/book_exposure.py")


def test_refresher_exists_and_is_importable() -> None:
    mod = _load("book_equity_refresh_g", "setup/scripts/book_equity_refresh.py")
    assert hasattr(mod, "refresh"), "no refresh() entrypoint"


def test_a_fresh_snapshot_clears_the_degrade(tmp_path) -> None:
    """THE POINT. Recording every active arm must take the cap from DEGRADED to OK."""
    (tmp_path / "fleet").mkdir()
    now = "2026-08-19T12:00:00"
    before = be.evaluate_live(tmp_path, now)
    assert before["degraded"], "expected a bare state dir to degrade"
    for arm in be.active_spy_arms():
        be.record_arm_equity(arm["arm_id"], 5000.0, tmp_path, now)
    after = be.evaluate_live(tmp_path, now)
    assert after["degraded"] is None, after["degraded"]
    assert after["book_equity"] > 0


def test_a_PARTIAL_refresh_still_degrades(tmp_path) -> None:
    """One missing arm must NOT silently shrink the denominator -- that tightens the cap
    (fail closed), the OP-32 lockout behaviour. All-or-nothing is correct here."""
    (tmp_path / "fleet").mkdir()
    now = "2026-08-19T12:00:00"
    arms = be.active_spy_arms()
    for arm in arms[:-1]:
        be.record_arm_equity(arm["arm_id"], 5000.0, tmp_path, now)
    r = be.evaluate_live(tmp_path, now)
    assert r["degraded"], "a partial snapshot was accepted as a complete denominator"
    assert r["allowed"] is True


def test_refresh_interval_is_inside_the_staleness_window() -> None:
    """The scheduled cadence must leave real margin under EQUITY_STALE_MINUTES, or the cap
    degrades between fires and we are back to an inert guard."""
    scheduled_every_min = 30          # Gamma_BookEquityRefresh
    assert scheduled_every_min * 2 < be.EQUITY_STALE_MINUTES, (
        f"refresh cadence {scheduled_every_min}m has under 2x margin against the "
        f"{be.EQUITY_STALE_MINUTES}m staleness window"
    )
