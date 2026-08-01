"""FLEET TICK-PAIRING RACE guard (2026-08-01, WEEKEND-TWELVE Next-Twelve #4) -- reproduces
Friday's exact interleaving that cost a full 3-min cadence slot.

THE INCIDENT (analysis/deep-research/WINNER-AUTOPSY-2026-07-31-1219.md, section 1).
heartbeat_core.py's main() writes the SAFE row for a tick, then the BOLD row ~1s later (two
sequential per-account passes inside one invocation -- each does its own network/scoring
work). Gamma_FleetExecutor ticks independently every 3 min (Interval PT3M, confirmed live via
Get-ScheduledTask) -- NOT synchronized with heartbeat_core's 1-min cadence (PT1M) -- and calls
build_shared_signal.build() at whatever instant its own scheduler fires.

On 2026-07-31, that fired at 12:16:02.508 ET: 0.45s AFTER the safe row for the 12:16 tick
landed (12:16:02), 0.5s BEFORE the bold row did (12:16:03). build()'s pre-fix logic ran TWO
INDEPENDENT "latest row for this account today" scans -- one for the top-level/safe block, one
for signal['bold'] (_bold_passed_blocks). The safe scan picked up the FRESH 12:16 row
(bull_score 11/11, an A+ BULLISH_RECLAIM_RIDE_THE_RIBBON setup). The bold scan, landing before
that tick's bold row existed, picked up the STALE 12:15 row instead. Result: one
shared-signal.json with a fresh safe perception paired against a one-tick-stale bold
perception -- signal['bold']['bull']['passed'] stayed False even though the A+ setup was
sitting right there in the safe row. The setup was invisible to every bold/loose-tier arm at
its freshest, cleanest point; the fleet did not act on it until 3 minutes later (12:19:02,
after the underlying setup had already partially decayed) -- see the autopsy doc's Facts
Ledger for the entry-price consequence.

THE FIX. heartbeat_core.py's main() now generates ONE core_tick_id per invocation (microsecond
ET timestamp) and threads it into BOTH accounts' run_account() calls, so every row logged this
tick -- safe AND bold -- carries the identical core_tick_id (purely additive ledger field).
After the per-account loop, main() writes automation/state/core-decisions-tick.json (atomic
temp-file + os.replace, overwritten never appended) with that core_tick_id -- but ONLY when
BOTH accounts logged a real (non-exception) row this invocation. build_shared_signal.py reads
that marker ONCE per build() call and pins EVERY block that reads core-decisions.jsonl
(top-level/safe, signal['bold'], probe, ladder, full_send) to the SAME core_tick_id, so a read
landing mid-write always resolves to the last COMPLETE tick, uniformly -- never a mismatched
pair, never a half-tick surfaced. Fails open: no marker (or a stale/wrong-day/corrupt one) ->
the exact pre-fix two-independent-scans behavior, byte-identical.

RAIL-4 CLEAR: test-only; imports + reads the producer, monkeypatches file paths to tmp_path,
mutates nothing in production. ENGINE-BENEFIT authoring (OP-22/OP-26) -- ships on green.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_FLEET = _REPO / "automation" / "state" / "fleet"
_SCRIPTS = _REPO / "setup" / "scripts"
for _p in (str(_FLEET), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_shared_signal as bss  # noqa: E402
import importlib  # noqa: E402

ET = timezone(timedelta(hours=-4))  # fixed-offset stand-in the sibling fleet tests already use


@pytest.fixture()
def hc():
    """heartbeat_core (lives in setup/scripts; sys.path insert above handles the import)."""
    return importlib.import_module("heartbeat_core")


# =============================================================================
# A. WRITE SIDE -- heartbeat_core.main() stamps + the marker contract
# =============================================================================
def test_main_stamps_shared_core_tick_id_and_writes_complete_marker(hc, monkeypatch, tmp_path):
    """Both accounts logged in one main() invocation must carry the IDENTICAL core_tick_id,
    and the tick-complete marker must land AFTER both, carrying that same id + both account
    names. This is the write-side half of the fix -- the read-side tests below depend on this
    contract holding."""
    now = dt.datetime(2026, 7, 31, 12, 16, 2)  # a real RTH Friday instant
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "STATE", tmp_path)  # hermetic: _write_tick_marker's mkdir target
    marker_path = tmp_path / "core-decisions-tick.json"
    monkeypatch.setattr(hc, "TICK_MARKER", marker_path)

    seen: list[tuple[str, str | None]] = []

    def _fake_run_account(account, core_tick_id=None):
        seen.append((account, core_tick_id))
        return {"account": account, "verdict": "HOLD", "core_tick_id": core_tick_id}

    monkeypatch.setattr(hc, "run_account", _fake_run_account)
    error_logs: list = []
    monkeypatch.setattr(hc, "_log", lambda rec: error_logs.append(rec))  # error path only

    rc = hc.main()

    assert rc == 0
    assert [a for a, _t in seen] == ["safe", "bold"], "safe processed before bold (dict order)"
    tick_ids = {t for _a, t in seen}
    assert len(tick_ids) == 1, "both accounts must share ONE core_tick_id per invocation"
    assert error_logs == [], "no account errored -- the _log error path must be untouched"
    assert marker_path.exists(), "marker must be written once both accounts logged clean"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker["core_tick_id"] == tick_ids.pop()
    assert marker["date"] == "2026-07-31"
    assert set(marker["accounts"]) == {"safe", "bold"}


def test_main_withholds_marker_when_one_account_errors(hc, monkeypatch, tmp_path):
    """An errored account must NOT advance the marker -- every reader keeps using the last
    GOOD paired tick until this one recovers. Proves the marker is written from ok_accounts,
    not unconditionally after the loop."""
    now = dt.datetime(2026, 7, 31, 12, 16, 2)
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "STATE", tmp_path)
    marker_path = tmp_path / "core-decisions-tick.json"
    monkeypatch.setattr(hc, "TICK_MARKER", marker_path)

    def _fake_run_account(account, core_tick_id=None):
        if account == "bold":
            raise RuntimeError("simulated bold failure")
        return {"account": account, "verdict": "HOLD", "core_tick_id": core_tick_id}

    monkeypatch.setattr(hc, "run_account", _fake_run_account)
    logged: list = []
    monkeypatch.setattr(hc, "_log", lambda rec: logged.append(rec))

    rc = hc.main()

    assert rc == 0, "main() must never raise/crash the tick, even on a per-account error"
    assert not marker_path.exists(), "an errored account must withhold the marker entirely"
    assert len(logged) == 1
    assert logged[0]["account"] == "bold" and logged[0]["verdict"] == "ERROR"


# =============================================================================
# B. READ SIDE -- build_shared_signal.build() consumes the marker
# =============================================================================
def _row(*, ts, core_tick_id, account, verdict, bull_score=2, bear_score=4, side=None,
        setup=None, triggers=None, spy=743.0):
    """Mirrors test_fleet_producer_keystone._seed_two_rows's row shape, plus the new additive
    core_tick_id field. `ts` (ts_et) and `core_tick_id` are DELIBERATELY independent knobs --
    exactly like the real ledger, where ts_et is each account's own write time (~1s apart) but
    core_tick_id is the ONE value shared by both rows of the same main() invocation."""
    return {"ts_et": ts, "account": account, "verdict": verdict, "action": verdict,
            "spy": spy, "ribbon": "BULL", "spread_cents": 30, "vix": 17.24, "htf_15m": "BULL",
            "side": side, "setup": setup, "bear_score": bear_score, "bull_score": bull_score,
            "triggers": triggers or [], "core_tick_id": core_tick_id}


def _write_marker(tmp_path, monkeypatch, *, core_tick_id, date):
    marker = tmp_path / "core-decisions-tick.json"
    marker.write_text(json.dumps({"core_tick_id": core_tick_id, "date": date,
                                  "ts_et": f"{date}T12:15:04", "accounts": ["bold", "safe"]}),
                      encoding="utf-8")
    monkeypatch.setattr(bss, "TICK_MARKER", marker)


def _seed_friday_interleaving(tmp_path, monkeypatch):
    """Reproduce Friday exactly: a COMPLETE prior tick (12:15, both accounts, tick id
    TICK-1215) already on disk, plus the 12:16 tick's SAFE row (tick id TICK-1216, the A+
    setup) -- its BOLD sibling deliberately ABSENT, matching the real incident where the bold
    row for 12:16 landed 0.5s AFTER the fleet's 12:16:02.508 read."""
    core = tmp_path / "core-decisions.jsonl"
    prior_safe = _row(ts="2026-07-31T12:15:03", core_tick_id="TICK-1215", account="safe",
                      verdict="HOLD", bull_score=2)
    prior_bold = _row(ts="2026-07-31T12:15:04", core_tick_id="TICK-1215", account="bold",
                      verdict="HOLD", bull_score=2)
    fresh_safe = _row(ts="2026-07-31T12:16:02", core_tick_id="TICK-1216", account="safe",
                      verdict="SKIP_ELITE_BULL_LEVEL_RECLAIM", bull_score=11, side="C",
                      setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
                      triggers=["level_reclaim", "confluence"], spy=743.54)
    # fresh_bold (core_tick_id TICK-1216) is INTENTIONALLY NOT WRITTEN -- the ~1s gap.
    core.write_text("\n".join(json.dumps(r) for r in (prior_safe, prior_bold, fresh_safe)) + "\n",
                    encoding="utf-8")
    monkeypatch.setattr(bss, "CORE_DECISIONS", core)
    monkeypatch.setattr(bss, "OUT", tmp_path / "shared-signal.json")
    monkeypatch.setattr(bss, "BEACON", tmp_path / "no-beacon.json")  # force the ledger path
    return prior_safe, prior_bold, fresh_safe


# the exact incident instant: 0.45s after the safe write, 0.5s before the bold write
_INCIDENT_NOW = datetime(2026, 7, 31, 12, 16, 2, 508000, tzinfo=ET)


def test_old_logic_pairs_fresh_safe_with_stale_bold_BITE(tmp_path, monkeypatch):
    """RED on the OLD logic / BITE (non-vacuous): with NO marker on disk (the pre-fix world --
    the concept did not exist), build() falls back to two independent last-row scans and
    genuinely reproduces Friday's mismatch: the top-level/safe block sees the FRESH 12:16 A+
    setup while signal['bold'] is still on the STALE 12:15 HOLD. Proves the fix below closes a
    real gap rather than asserting something that was already true."""
    _seed_friday_interleaving(tmp_path, monkeypatch)
    assert not (tmp_path / "core-decisions-tick.json").exists()  # no marker -> old fallback

    sig = bss.build(now=_INCIDENT_NOW, scoring_peak=True, emit_strategies=False, run_vwap=False)

    assert sig["time_et"] == "12:16", "top-level (safe) sees the FRESH tick"
    assert sig["bull"]["score"] == 11, "top-level scored the fresh A+ setup"
    assert sig["bold"]["bull"]["score"] == 2, "bold perception is STILL on the stale prior tick"
    assert sig["bold"]["bull"]["passed"] is False, "the A+ setup is INVISIBLE to bold -- the bug"


def test_marker_pins_both_sides_to_the_last_complete_tick(tmp_path, monkeypatch):
    """GREEN on the NEW logic: with the tick-complete marker present and pointing at the LAST
    COMPLETE tick (TICK-1215, both rows confirmed), build() pins BOTH the top-level/safe read
    AND signal['bold'] to that same tick -- even though the fresher 12:16 SAFE row already
    exists on disk, it is NOT surfaced (its bold sibling isn't there yet), so no mismatched
    pair is ever built. This is 'the last COMPLETE tick, never a half-tick' from the fix spec,
    reproducing the SAME seeded data as the BITE test above with only the marker added."""
    _seed_friday_interleaving(tmp_path, monkeypatch)
    _write_marker(tmp_path, monkeypatch, core_tick_id="TICK-1215", date="2026-07-31")

    sig = bss.build(now=_INCIDENT_NOW, scoring_peak=True, emit_strategies=False, run_vwap=False)

    assert sig["time_et"] == "12:15", "top-level held back to the last COMPLETE tick"
    assert sig["bull"]["score"] == 2, "top-level does NOT surface the unpaired fresh safe row"
    assert sig["bold"]["bull"]["score"] == 2, "bold reads its OWN complete-tick row"
    assert sig["bold"]["bull"]["passed"] is False
    # the two sides now describe the SAME tick -- no mismatch possible.
    assert sig["time_et"] == "12:15"


def test_once_bold_lands_the_marker_advances_and_both_sides_see_the_fresh_tick(tmp_path, monkeypatch):
    """Completeness / non-regression: once the bold row for the fresh tick ALSO lands and the
    marker advances to it (exactly what heartbeat_core.main() does the instant ok_accounts ==
    {'safe','bold'}), the very next build() call sees BOTH sides consistently on the NEW tick.
    The fix does not get stuck on the old tick forever -- it advances the moment the pair
    completes, so the fleet loses at most the ~1s gap, never a full 3-min cadence slot."""
    core = tmp_path / "core-decisions.jsonl"
    prior_safe = _row(ts="2026-07-31T12:15:03", core_tick_id="TICK-1215", account="safe",
                      verdict="HOLD", bull_score=2)
    prior_bold = _row(ts="2026-07-31T12:15:04", core_tick_id="TICK-1215", account="bold",
                      verdict="HOLD", bull_score=2)
    fresh_safe = _row(ts="2026-07-31T12:16:02", core_tick_id="TICK-1216", account="safe",
                      verdict="SKIP_ELITE_BULL_LEVEL_RECLAIM", bull_score=11, side="C",
                      setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
                      triggers=["level_reclaim", "confluence"], spy=743.54)
    fresh_bold = _row(ts="2026-07-31T12:16:03", core_tick_id="TICK-1216", account="bold",
                      verdict="SKIP_ELITE_BULL_LEVEL_RECLAIM", bull_score=11, side="C",
                      setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
                      triggers=["level_reclaim", "confluence"], spy=743.54)
    core.write_text("\n".join(json.dumps(r) for r in
                              (prior_safe, prior_bold, fresh_safe, fresh_bold)) + "\n",
                    encoding="utf-8")
    monkeypatch.setattr(bss, "CORE_DECISIONS", core)
    monkeypatch.setattr(bss, "OUT", tmp_path / "shared-signal.json")
    monkeypatch.setattr(bss, "BEACON", tmp_path / "no-beacon.json")
    _write_marker(tmp_path, monkeypatch, core_tick_id="TICK-1216", date="2026-07-31")

    now = datetime(2026, 7, 31, 12, 16, 3, 100000, tzinfo=ET)  # just after bold landed
    sig = bss.build(now=now, scoring_peak=True, emit_strategies=False, run_vwap=False)

    assert sig["time_et"] == "12:16"
    assert sig["bull"]["score"] == 11
    assert sig["bold"]["bull"]["score"] == 11, "bold's OWN fresh row, now correctly paired"
    assert sig["bold"]["bull"]["passed"] is True
