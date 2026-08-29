"""Guard: the Discord bridge must not deliver stale alerts, and must not call itself healthy
while delivering nothing (2026-08-12).

WHAT HAPPENED. J: "we literally built a whole app and a whole gamma automation thing. But here I
am figuring everything out again." The audit found why. The bridge is the ONE push-capable channel
Gamma has, and:

  * 1,837 messages sat undelivered in automation/state/discord-outbox.jsonl.
  * MEDIAN AGE 15.6 DAYS. Oldest 29.6 days. Only 232 were under a day old.
  * The last successful send (2026-08-10 16:31 MT) was dispatching 2026-07-14 content -- so even
    while the bridge WAS "working", J was receiving month-old 0DTE trade alerts describing
    positions closed weeks earlier.
  * Throughout, discord-bridge-heartbeat.json reported a fresh `last_tick_at` and
    `consecutive_errors: 0`. The frozen-bridge watchdog reads that file and saw green.

TWO DISTINCT DEFECTS, GUARDED SEPARATELY BELOW:

1. NO STALENESS POLICY. The outbox is FIFO with no expiry, so falling behind is not self-healing --
   it is permanent. A late 0DTE ping is not partial credit, it is misinformation. drain_outbox now
   drops anything older than MAX_MESSAGE_AGE_MIN.

2. THE HEALTH SIGNAL MEASURED LIVENESS, NOT DELIVERY. `last_tick_at` + `consecutive_errors` only
   prove the loop is spinning. A drain that sends zero messages raises no error and logs no line
   (the tick log was gated on `if in_count or out_count`), so total delivery failure was
   indistinguishable from a quiet day. This is C7 in its purest form, and it is the same shape as
   the bg_status gap found hours earlier: the monitor could not see the thing it monitored.

DESIGN RULE PINNED HERE: an undateable message is SENT, never dropped. Dropping is the destructive
branch, so it must require positive evidence of staleness -- absence of a timestamp is not that.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "setup" / "scripts" / "discord-bridge.py"


def _load():
    """Hyphen in the filename means it cannot be imported normally."""
    spec = importlib.util.spec_from_file_location("_discord_bridge_probe", BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def bridge():
    return _load()


def _ago(**kw):
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(**kw)


# ----------------------------------------------------------------- staleness policy


def test_a_message_older_than_the_cap_is_stale(bridge):
    """The 15.6-day median of the real backlog. Shipping these is the defect."""
    age = bridge._row_age_min({"queued_at": _ago(days=15.6).isoformat().replace("+00:00", "Z")})
    assert age is not None and age > bridge.MAX_MESSAGE_AGE_MIN


def test_a_fresh_message_is_not_stale(bridge):
    age = bridge._row_age_min({"queued_at": _ago(minutes=2).isoformat().replace("+00:00", "Z")})
    assert age is not None and age < bridge.MAX_MESSAGE_AGE_MIN


@pytest.mark.parametrize("fmt", ["z", "offset", "naive"])
def test_all_three_on_disk_timestamp_formats_parse(bridge, fmt):
    """Producers write a mix of '...Z', '...+00:00' and naive stamps -- all three appear in the
    real outbox. A format this misses would be silently treated as undateable.

    2026-08-29 (n-th full-suite run): the stamp used to be computed once at
    parametrize-collection time (`_ago(minutes=30)` evaluated when pytest COLLECTED this
    module), then asserted against at TEST-EXECUTION time with only a +-5min window. In a
    10k+ test full-suite run (20+ min wall clock), any file that happens to execute more
    than ~5min after collection flakes with a false "format not parsed"-adjacent failure
    -- not a real regression, a self-inflicted time bomb. Computing `_ago()` HERE, inside
    the test body, means it is evaluated at execution time, so the assertion window is
    always measured against the instant it actually needs to hold for.
    """
    base = _ago(minutes=30)
    stamp = {
        "z": base.isoformat().replace("+00:00", "Z"),
        "offset": base.isoformat(),
        "naive": base.replace(tzinfo=None).isoformat(),
    }[fmt]
    age = bridge._row_age_min({"queued_at": stamp})
    assert age is not None, f"format not parsed: {stamp!r}"
    assert 25 < age < 35, f"expected ~30min, got {age}"


def test_ts_key_is_honoured_not_just_queued_at(bridge):
    """Two producer schemas exist ({queued_at,content} and {ts,channel,source,message}); 520 of
    the 1,837 backlogged rows used the `ts` form. Reading only queued_at would make every one of
    them undateable and therefore permanently unskippable."""
    assert bridge._row_age_min({"ts": _ago(days=9).isoformat()}) is not None


@pytest.mark.parametrize("row", [{}, {"content": "x"}, {"queued_at": "not-a-date"},
                                 {"queued_at": ""}, {"queued_at": None}])
def test_undateable_messages_fail_TOWARD_delivery(bridge, row):
    """THE SAFETY DIRECTION. Dropping is destructive, so it needs positive proof of staleness.
    None means 'cannot judge age', and the caller sends on None. If this ever flips to returning a
    number for an undateable row, real messages start disappearing."""
    assert bridge._row_age_min(row) is None


def test_the_cap_is_env_overridable_and_defaults_sanely(bridge):
    assert bridge.MAX_MESSAGE_AGE_MIN == 120
    src = BRIDGE.read_text(encoding="utf-8")
    assert "GAMMA_DISCORD_MAX_AGE_MIN" in src


def test_drop_branch_persists_the_watermark(bridge):
    """The pre-existing silent-skip branches advance the IN-MEMORY watermark without calling
    save_watermarks, so a restart re-processes them. The drop branch must persist, or a bridge
    restart replays the entire stale backlog it just decided to discard."""
    src = BRIDGE.read_text(encoding="utf-8")
    block = src.split("age_min = _row_age_min(row)")[1].split("continue")[0]
    assert "save_watermarks(wm)" in block, "the staleness drop does not persist its watermark"


# ----------------------------------------------------------------- health signal


def test_heartbeat_reports_delivery_not_just_liveness(bridge):
    """last_tick_at + consecutive_errors reported GREEN for 2+ days of total delivery failure.
    These are the fields that can actually go RED."""
    src = BRIDGE.read_text(encoding="utf-8")
    hb = src.split("HEARTBEAT_PATH.write_text(")[1][:800]
    for field in ("outbox_pending", "last_delivery_at", "dropped_stale_total"):
        assert field in hb, f"heartbeat no longer reports {field} -- it is back to measuring only liveness"


def test_drain_outbox_reports_pending_to_its_caller(bridge):
    """A drain that returns only `sent` cannot distinguish 'nothing to send' from 'sent nothing'.
    That ambiguity IS the bug: 0 was indistinguishable from a quiet day for two days straight."""
    import inspect
    sig = inspect.signature(bridge.drain_outbox)
    assert "tuple" in str(sig.return_annotation), (
        f"drain_outbox returns {sig.return_annotation} -- it must report (sent, dropped, pending)")


def test_tick_is_logged_when_messages_are_dropped(bridge):
    """Silent dropping would replace one invisible failure with another."""
    src = BRIDGE.read_text(encoding="utf-8")
    assert "if in_count or out_count or dropped:" in src, (
        "the tick log no longer fires on drops -- discards would be invisible")
    assert "dropped %d outbox message(s) older than" in src


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
