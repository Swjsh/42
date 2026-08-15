"""RE-ENTRY LOCK ABSENCE PINS (J directive 2026-07-02) + G15 incident record.

HISTORY (two events, same file):
  1. G15 tz-crash (morning): _prior_fill_stopped built an AWARE last_exit while
     _et_now() is naive ET -> 6 bold ERROR ticks 11:50-11:55 killed an ALLOW-path
     re-entry. Fixed 253f64b (last_exit normalized to naive ET).
  2. LOCK DELETED (evening, J's written order): "Gone. We no longer have it in our
     codebase." The 'already stopped out on this setup today' re-entry suppression
     (SKIP_QUALITY_LOCK incl. _prior_fill_stopped + the leg-2 45-min gap machinery,
     where the tz fix had landed hours earlier) was Claude-invented, never
     A/B-validated, and cost the 2026-07-02 midday trade. The whole path is gone.

THIS FILE NOW PINS THE LOCK'S ABSENCE:
  * heartbeat_core exposes NONE of the lock symbols;
  * _execute's source contains no SKIP_QUALITY_LOCK branch;
  * functionally: an ENTER after a same-setup stop-out earlier today routes to the
    placement path (reaches the broker/strike stage), it is NOT suppressed.
RED here = someone re-introduced re-entry suppression without evidence. Any future
cooldown gate ships only with A/B evidence (analysis/recommendations/
reentry-cooldown-ab.json) via a conductor proposal — never as a silent refactor.

The G15 Python-semantics repro + incident-ledger pins are kept as the executable
historical record (they are code-independent).

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_tz_quality_lock_2026_07_02.py
"""
from __future__ import annotations

import datetime as dt
import importlib
import inspect
import json
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_SCRIPTS = ROOT / "setup" / "scripts"
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT / "backtest"), str(ROOT), str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

hc = importlib.import_module("heartbeat_core")

CORE_LEDGER = ROOT / "automation" / "state" / "core-decisions.jsonl"
ERR_MSG = "can't subtract offset-naive and offset-aware datetimes"
SETUP = "BEARISH_REJECTION_RIDE_THE_RIBBON"
_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}

SAFE_PARAMS = json.loads(
    (ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8"))


# =============================================================================
# Part A — LOCK ABSENCE PINS (the new load-bearing guards)
# =============================================================================
class TestLockSymbolsGone:
    @pytest.mark.parametrize("symbol", [
        "_quality_lock_check", "_prior_fill_stopped", "_quality_rank",
        "_todays_ledger_rows",
    ])
    def test_heartbeat_core_has_no_lock_machinery(self, symbol):
        assert not hasattr(hc, symbol), (
            f"{symbol} re-introduced — the re-entry lock was DELETED per J's written "
            "order 2026-07-02 ('Gone. We no longer have it in our codebase.')")

    def test_execute_source_has_no_quality_lock_branch(self):
        src = inspect.getsource(hc._execute)
        assert "SKIP_QUALITY_LOCK" not in src
        assert "_quality_lock_check" not in src

    def test_fast_path_executor_has_no_first_entry_lock_filter(self):
        fpe = importlib.import_module("fast_path_executor")
        assert not hasattr(fpe, "_compute_filter_first_entry_lock")
        src = inspect.getsource(fpe.evaluate_alert)
        assert "_compute_filter_first_entry_lock" not in src


class TestReentryAfterStopRoutesToExecute:
    """FUNCTIONAL absence pin: the exact shape the lock used to suppress — an ENTER
    on a setup that already entered AND stopped out earlier today — must now route
    to the placement path. We drive the REAL _execute with a stubbed broker; the
    prior stop-out exists both in the ledger shape and at the (stubbed) broker.
    Reaching PLACED means no re-entry suppression fired anywhere on the way."""

    def _run(self, monkeypatch, tmp_path):
        import fleet_broker as fb
        posts: list = []
        monkeypatch.setattr(fb, "_request",
                            lambda creds, endpoint, method="GET", data=None, timeout=15:
                            posts.append({"endpoint": endpoint, "method": method, "data": data})
                            or {"id": "ord-1", "status": "accepted"})
        monkeypatch.setattr(fb, "load_creds", lambda: {"safe-2": _CREDS, "bold-2": _CREDS})
        monkeypatch.setattr(fb, "is_flat_spy_options", lambda c: True)  # stop-out -> flat again
        monkeypatch.setattr(fb, "get_option_mid", lambda c, s: 1.00)
        monkeypatch.setattr(fb, "marketable_limit_price",
                            lambda c, s, side="buy", buffer=0.03: 1.08)
        monkeypatch.setattr(fb, "open_buy_orders", lambda c, s: [])
        # ADDED 2026-08-15. The entry path's order-level idempotency guard (71cce7ac /
        # b80b799c, 2026-08-01..03) calls the *_checked* primitives, which fail CLOSED on an
        # unverifiable query -- deliberately, since "a missed entry is cheap, a double entry
        # is not". This fake stubbed only the fail-OPEN `open_buy_orders`, so the real checked
        # variants ran against the stubbed `_request` and returned ok=False, turning both
        # tests into SKIP_ORDER_QUERY_ERROR. Stubbing the clean state (no pending BUY, no held
        # qty, query SUCCEEDED) is what lets them reach the placement they exist to assert --
        # it does not weaken the guard, which keeps its own coverage elsewhere.
        monkeypatch.setattr(fb, "open_buy_orders_checked", lambda c, s: ([], True))
        monkeypatch.setattr(fb, "symbol_position_qty_checked", lambda c, s: (0, True))
        monkeypatch.setattr(fb, "cancel_order", lambda *a, **k: {})
        monkeypatch.setattr(hc, "STATE", tmp_path)
        now = dt.datetime(2026, 7, 2, 11, 50, 2)  # the tick the old lock/crash killed
        monkeypatch.setattr(hc, "_et_now", lambda: now)
        monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", True)
        monkeypatch.setitem(sys.modules, "exit_actuator",
                            types.SimpleNamespace(register_entry=lambda *a, **k: None))
        monkeypatch.setitem(sys.modules, "strategies",
                            types.SimpleNamespace(by_name=lambda n: None))

        class _Resp:
            def read(self):
                return json.dumps({"equity": "2000.0"}).encode("utf-8")

        import urllib.request as _ur
        monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: _Resp())
        # SAME setup + SAME rank-1 trigger as the 09:30 stop-out — the old lock's
        # exact block case (rank == prior, would have needed the leg-2 exemption).
        verdict = {"verdict": "ENTER_BEAR", "setup_name": SETUP,
                   "triggers_fired": ["trendline_rejection"]}
        payload = {"bar_ctx": {"timestamp_et": "2026-07-02 11:45:00",
                               "bar": {"close": 620.0}}}
        return hc._execute("safe", verdict, payload, SAFE_PARAMS, dry=False), posts

    def test_same_setup_reentry_after_stop_is_placed_not_locked(self, monkeypatch, tmp_path):
        plan, posts = self._run(monkeypatch, tmp_path)
        assert plan["status"] != "SKIP_QUALITY_LOCK", plan
        assert plan["status"] == "PLACED", plan
        assert len(posts) == 1 and posts[0]["method"] == "POST"

    def test_no_broker_activities_probe_on_the_entry_path(self, monkeypatch, tmp_path):
        """The lock's tell was a /v2/account/activities/FILL probe before placement.
        The entry path must not query activities at all anymore."""
        plan, posts = self._run(monkeypatch, tmp_path)
        assert plan["status"] == "PLACED"
        assert all("activities" not in str(p.get("endpoint", "")) for p in posts)


# =============================================================================
# Part B — G15 incident record (code-independent; kept as executable history)
# =============================================================================
class TestG15MechanismUnitRepro:
    """Python-semantics pin of the original tz crash — passes forever, documents
    WHY naive-ET is the engine-wide convention (et_clock)."""

    def test_naive_minus_aware_raises_the_incident_error(self):
        aware_utc = dt.datetime.fromisoformat("2026-07-02T13:32:04+00:00")
        aware_et_wallclock = aware_utc + dt.timedelta(hours=-4)  # tzinfo PRESERVED
        assert aware_et_wallclock.tzinfo is not None
        naive_now = dt.datetime(2026, 7, 2, 11, 50, 2)
        with pytest.raises(TypeError, match=ERR_MSG):
            naive_now - aware_et_wallclock  # noqa: B018 — the subtraction IS the assertion


class TestG15IncidentLedger:
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

    def test_safe_hit_quality_lock_same_minutes_historical(self):
        """Historical ledger record only — SKIP_QUALITY_LOCK no longer exists in code
        (TestLockSymbolsGone); these rows are why J ordered the lock deleted."""
        safes = [r for r in self._rows() if r.get("account") == "safe"]
        assert len(safes) == 6
        assert all(r.get("verdict") == "ENTER_BEAR" and r.get("action") == "SKIP_QUALITY_LOCK"
                   for r in safes)
