"""G15 tz-crash guards — the 2026-07-02 11:50-11:55 bold quality-lock ERROR window.

INCIDENT: 2026-07-02 the core BOLD account logged verdict=ERROR
"can't subtract offset-naive and offset-aware datetimes" for exactly 6 ticks
(11:50:02-11:55:02 ET), then "self-cleared". During the same minutes SAFE emitted
ENTER_BEAR -> SKIP_QUALITY_LOCK (re-entry lock after its 09:30 stop-out).

ROOT CAUSE (one sentence):
    _prior_fill_stopped builds last_exit from datetime.fromisoformat('...+00:00')
    (tz-AWARE, and the +timedelta ET shift PRESERVES tzinfo — heartbeat_core.py:798-801)
    while _et_now() is NAIVE ET (et_clock convention), so the leg-2 re-entry gap check
    `gap_min = (now_et - last_exit).total_seconds()` (heartbeat_core.py:855) raises
    TypeError whenever it is reached.

WHY ONLY BOLD (verified from today's ledger + fill funnel):
  * Both accounts entered 09:30 on the same rank-1 TRENDLINE setup and stopped out, so
    both later hit the rank == prior_quality leg-2 branch that calls _prior_fill_stopped.
  * BOLD's 5-lot premium_stop SELL_ALL (09:32:04) filled in ONE execution -> one sell
    FILL activity -> had_partial=False -> prior_stopped=True + aware last_exit -> the
    gap subtraction RAN -> crash.
  * SAFE's 3-lot SELL_ALL (09:31) filled in MULTIPLE partial executions (funnel
    exited=3 vs bold's 1) -> >=2 same-symbol sell activities -> had_partial=True ->
    prior_stopped=False -> line 854 short-circuits BEFORE the subtraction -> clean
    SKIP_QUALITY_LOCK. Safe was lucky, not immune: one single-execution stop-out and
    it crashes identically.

WHY IT SELF-CLEARED AT 11:56: the bear signal died (safe went HOLD "no setup passed
scoring" at 11:56:03) — _execute stopped being called, so the crash line stopped being
reached. The bug stayed latent, not fixed.

IMPACT: the 6 dead ticks were ALLOW-path ticks — bold's gap was ~138 min >= 45, so the
leg-2 exemption would have permitted the re-entry the crash killed. Bold ended the day
with a single 09:30 stop-out and zero recovery entries; SPY fell 745.38 -> 744.63 by
11:56 and ~742.67 by 12:45 (favorable for the blocked put).

Part A (evidence pins) pass TODAY and keep passing. Part B (fix guards) skip until the
staged patch lands, then arm automatically via a FUNCTIONAL probe (no hasattr — the fix
adds no symbol; we detect it by driving _prior_fill_stopped through a stubbed broker
response and checking last_exit.tzinfo). The strict-xfail sentinel FORCES the apply
commit to delete its marker (no silent-skip-forever, C7).

STAGED FIX: markdown/audits/tz-quality-lock-fix-2026-07-02.patch — apply AFTER the
entry-floor patch per markdown/audits/TZ-QUALITY-LOCK-FIX-PLAN-2026-07-02.md.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_tz_quality_lock_2026_07_02.py
"""
from __future__ import annotations

import datetime as dt
import importlib
import inspect
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_SCRIPTS = ROOT / "setup" / "scripts"
for _p in (str(ROOT / "backtest"), str(ROOT), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

hc = importlib.import_module("heartbeat_core")

CORE_LEDGER = ROOT / "automation" / "state" / "core-decisions.jsonl"
ERR_MSG = "can't subtract offset-naive and offset-aware datetimes"
SETUP = "BEARISH_REJECTION_RIDE_THE_RIBBON"
CREDS = {"base_url": "https://paper-api.test.invalid", "key": "k", "secret": "s"}


# --------------------------------------------------------------------------- #
# offline broker stub + functional fix probe
# --------------------------------------------------------------------------- #
def _stub_urlopen_factory(activities: list[dict]):
    """A urllib.request.urlopen replacement returning a canned activities payload.
    _prior_fill_stopped does `import urllib.request` INSIDE the function, so patching
    the module-global attribute intercepts it (attribute lookup happens at call time)."""
    payload = json.dumps(activities).encode()

    class _Resp:
        def read(self):
            return payload

    return lambda *a, **k: _Resp()


_ONE_SELL_FILL = [{
    "symbol": "SPY260702P00743000", "side": "sell", "type": "fill",
    "transaction_time": "2026-07-02T13:32:04Z",  # 09:32:04 ET (EDT = UTC-4)
}]


def _probe_prior_fill_stopped() -> "tuple[bool, dt.datetime | None]":
    """Drive the REAL _prior_fill_stopped through the stub — offline + deterministic."""
    import urllib.request as _ur
    orig = _ur.urlopen
    _ur.urlopen = _stub_urlopen_factory(_ONE_SELL_FILL)
    try:
        return hc._prior_fill_stopped(CREDS, "SPY260702P00743000")
    finally:
        _ur.urlopen = orig


_PROBE_STOPPED, _PROBE_EXIT = _probe_prior_fill_stopped()
# Fix applied <=> the ET-shifted exit timestamp comes back NAIVE (subtraction-safe).
TZ_APPLIED = bool(_PROBE_STOPPED) and _PROBE_EXIT is not None and _PROBE_EXIT.tzinfo is None
_NOT_APPLIED = ("tz-quality-lock patch not applied yet "
                "(staged: markdown/audits/TZ-QUALITY-LOCK-FIX-PLAN-2026-07-02.md)")


# =============================================================================
# Part A — EVIDENCE PINS (pass today; pin the diagnosed mechanism)
# =============================================================================
class TestEvidenceClockConvention:
    def test_et_now_is_naive(self):
        """The engine-wide convention the fix normalizes to: _et_now() (via
        et_clock.et_now) returns a NAIVE ET datetime. If this ever becomes aware,
        the quality-lock contract flips and this whole guard file must be revisited."""
        now = hc._et_now()
        assert now.tzinfo is None

    def test_gap_check_subtracts_now_minus_last_exit(self):
        """Pin the crash site's shape: the leg-2 gap is computed by direct datetime
        subtraction inside _quality_lock_check — which is only safe while BOTH operands
        stay naive. (The fix normalizes last_exit; this pin keeps the site honest.)"""
        src = inspect.getsource(hc._quality_lock_check)
        assert "gap_min = (now_et - last_exit).total_seconds()" in src

    def test_leg2_branch_only_runs_on_equal_rank(self):
        """Why safe 'escaped' for a different reason than bold: _prior_fill_stopped
        (and therefore the gap subtraction) is only reached when rank == prior_quality
        AND prior_stopped is True AND last_exit is not None."""
        src = inspect.getsource(hc._quality_lock_check)
        assert "if rank == prior_quality:" in src
        assert "if prior_stopped and last_exit is not None:" in src


class TestEvidenceMechanismUnitRepro:
    """Self-contained repro of the exact failure — Python semantics pin, passes forever."""

    def test_naive_minus_aware_raises_the_incident_error(self):
        # exactly what heartbeat_core.py:798+801 produced pre-fix:
        aware_utc = dt.datetime.fromisoformat("2026-07-02T13:32:04+00:00")
        aware_et_wallclock = aware_utc + dt.timedelta(hours=-4)  # tzinfo PRESERVED
        assert aware_et_wallclock.tzinfo is not None, "timedelta addition must keep tzinfo"
        naive_now = dt.datetime(2026, 7, 2, 11, 50, 2)  # _et_now() at the first ERROR tick
        with pytest.raises(TypeError, match=ERR_MSG):
            naive_now - aware_et_wallclock  # noqa: B018 — the subtraction IS the assertion


class TestEvidenceIncidentLedger:
    """Executable record of the incident rows (soft pin — skips if ledger pruned)."""

    def _rows(self):
        if not CORE_LEDGER.exists():
            pytest.skip("core-decisions.jsonl absent (retention prune)")
        rows = []
        for line in CORE_LEDGER.read_text(encoding="utf-8").splitlines():
            if '"2026-07-02T11:5' not in line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = str(r.get("ts_et", ""))
            if "2026-07-02T11:50" <= ts < "2026-07-02T11:56":
                rows.append(r)
        if not rows:
            pytest.skip("2026-07-02 11:5x rows pruned from ledger")
        return rows

    def test_exactly_six_bold_error_ticks(self):
        errs = [r for r in self._rows()
                if r.get("account") == "bold" and r.get("verdict") == "ERROR"]
        assert len(errs) == 6, "incident record: 6 bold ERROR ticks 11:50:02-11:55:02"
        assert all(r.get("error") == ERR_MSG for r in errs)

    def test_safe_hit_quality_lock_cleanly_same_minutes(self):
        safes = [r for r in self._rows() if r.get("account") == "safe"]
        assert len(safes) == 6
        assert all(r.get("verdict") == "ENTER_BEAR" and r.get("action") == "SKIP_QUALITY_LOCK"
                   for r in safes), "safe must show the crash-free path through the same lock"


# =============================================================================
# Part B — FIX GUARDS (skip until applied; arm automatically; RED on regression)
# =============================================================================
class TestFixAppliedSentinel:
    """strict xfail: XFAIL (green) while the patch is staged; XPASS (RED) the moment
    the fix lands — forcing the apply commit to delete this marker, which proves the
    probe-gated guards below actually armed. Apply-plan step 4 removes the marker."""

    @pytest.mark.xfail(reason=_NOT_APPLIED, strict=True)
    def test_fix_is_applied(self):
        assert TZ_APPLIED


@pytest.mark.skipif(not TZ_APPLIED, reason=_NOT_APPLIED)
class TestPriorFillStoppedNaiveEt:
    def test_last_exit_is_naive_et_wallclock(self):
        """13:32:04Z on a July date == 09:32:04 ET (EDT), returned NAIVE — the exact
        shape _et_now() subtraction requires."""
        assert _PROBE_STOPPED is True
        assert _PROBE_EXIT == dt.datetime(2026, 7, 2, 9, 32, 4)
        assert _PROBE_EXIT.tzinfo is None

    def test_partial_fills_still_mean_not_stopped(self):
        """The safe-account path must survive the fix byte-identically: >=2 same-symbol
        sell fills -> had_partial -> (False, ...) -> lock blocks without the gap check."""
        import urllib.request as _ur
        two = [dict(_ONE_SELL_FILL[0]), dict(_ONE_SELL_FILL[0], transaction_time="2026-07-02T13:31:30Z")]
        orig = _ur.urlopen
        _ur.urlopen = _stub_urlopen_factory(two)
        try:
            stopped, _ = hc._prior_fill_stopped(CREDS, "SPY260702P00743000")
        finally:
            _ur.urlopen = orig
        assert stopped is False


@pytest.mark.skipif(not TZ_APPLIED, reason=_NOT_APPLIED)
class TestIncidentReplayLeg2:
    """The 11:50:02 bold tick, end-to-end through the REAL _quality_lock_check.
    Pre-fix this exact call raised the incident TypeError; post-fix it must ALLOW
    (rank 1 == prior 1, prior stopped, gap ~138min >= 45)."""

    _TAKEN_ROW = {
        "account": "bold", "ts_et": "2026-07-02T09:30:38", "action": "PLACED",
        "exec": {"status": "PLACED", "setup": SETUP, "quality_rank": 1,
                 "symbol": "SPY260702P00743000"},
    }

    def _check(self, monkeypatch, now_et: dt.datetime) -> dict:
        import urllib.request as _ur
        monkeypatch.setattr(hc, "_todays_ledger_rows", lambda account: [dict(self._TAKEN_ROW)])
        monkeypatch.setattr(_ur, "urlopen", _stub_urlopen_factory(_ONE_SELL_FILL))
        return hc._quality_lock_check("bold", "P", ["trendline_rejection"], SETUP,
                                      CREDS, now_et)

    def test_1150_tick_allows_leg2_no_crash(self, monkeypatch):
        ql = self._check(monkeypatch, dt.datetime(2026, 7, 2, 11, 50, 2))
        assert ql["allow"] is True, "the crash killed an ALLOW-path re-entry"
        assert ql["prior_quality"] == 1 and ql["rank"] == 1
        assert ql["prior_stopped"] is True
        assert 137.5 < ql["gap_min"] < 138.5  # 09:32:04 -> 11:50:02 = ~137.97 min

    def test_sub_45min_gap_still_blocks(self, monkeypatch):
        """The 45-min leg-2 cooldown must survive the fix (gap logic itself unchanged)."""
        ql = self._check(monkeypatch, dt.datetime(2026, 7, 2, 9, 50, 2))
        assert ql["allow"] is False
        assert ql["prior_stopped"] is True
        assert 17.5 < ql["gap_min"] < 18.5  # 09:32:04 -> 09:50:02 = ~17.97 min
