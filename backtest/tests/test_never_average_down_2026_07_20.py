"""NEVER-AVERAGE-DOWN graduated guard (lesson-inbox 2026-07-01, processed 2026-07-20).

Source: strategy/candidates/_lesson-inbox/2026-07-01-never-average-down-graduated-guard.md
(J's real 2021-23 WeBull fills: 567 closed family episodes, net -$12,885; the 67 scaled-in
episodes lost -$9,281, 94% of which (63/67) averaged DOWN -- added at a LOWER premium than
the first fill. Sharpened attribution: no-add alone recovers only +$794 at fixed exits; the
recoverable money is the PACKAGE of no-add + the -50% catastrophe cap (+$3,428 bound on the
scaled-in cohort, +$6,176 bound book-wide) -- scale-in is the highest-signal MARKER of a
trade being managed by hope, not a standalone lever). See LESSONS-LEARNED.md L203.

This file does NOT build a new guard -- it PROVES one already exists structurally (Rule 4:
"No adding without a NEW confirmed trigger") and pins it so a future refactor cannot silently
reopen a stacking path. Every route into a live order --
  (a) heartbeat_core._execute (core primary ribbon route AND the extra-setup G4 route --
      both call the SAME _execute, setup/scripts/heartbeat_core.py:1369-1454)
  (b) automation/state/fleet/fleet_live.py's per-arm entry gate (line ~531)
-- refuses ANY new entry attempt while fb.is_flat_spy_options(creds) is False, UNCONDITIONALLY
(no bypass parameter exists anywhere in the call chain -- see TestNoBypassParameter below).
This is STRONGER than the lesson's proposed fix #1 (which only asked for "no add at a premium
at-or-below the first fill"): the live guard blocks ALL stacking, at any premium, for any
setup, with no "new confirmed trigger" carve-out -- once a position is open, the account MUST
go flat (via a stop/TP1/time-stop exit) before any code path can place a second entry. Rule 4
is satisfied trivially and completely by "you cannot add, period."

RED-PROOF: monkeypatch fb.is_flat_spy_options to raise AttributeError (simulating the check
being removed/renamed) -- every test below fails loudly instead of silently passing, because
none of them mock around the check itself; they drive the REAL _execute / decide_arm+run()
gate with a real return of False.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_never_average_down_2026_07_20.py
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
BACKTEST = ROOT / "backtest"
_SCRIPTS = ROOT / "setup" / "scripts"
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(ROOT), str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SAFE_PARAMS = json.loads((ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
BOLD_PARAMS = json.loads((ROOT / "automation" / "state" / "aggressive" / "params.json").read_text(encoding="utf-8"))
_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}


@pytest.fixture()
def hc():
    return importlib.import_module("heartbeat_core")


@pytest.fixture()
def fl():
    return importlib.import_module("fleet_live")


# =============================================================================
# (a) core _execute -- both the primary ribbon verdict AND the extra-setup G4
#     route call this SAME function, so one set of assertions covers both lanes.
# =============================================================================
class TestCoreExecuteRefusesStackedEntry:
    def _wire(self, hc, monkeypatch, tmp_path, *, account_flat: bool):
        import fleet_broker as fb
        posts: list = []

        def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
            posts.append({"endpoint": endpoint, "method": method, "data": data})
            return {"id": "ord-1", "status": "accepted"}

        def _boom_pick_strike(*a, **k):
            raise AssertionError("strike selection must never run when NOT_FLAT -- proves "
                                  "the flat-check short-circuits BEFORE any pricing happens")

        monkeypatch.setattr(fb, "_request", fake_request)
        monkeypatch.setattr(fb, "load_creds", lambda: {"safe-2": _CREDS, "bold-2": _CREDS})
        monkeypatch.setattr(fb, "is_flat_spy_options", lambda c: account_flat)
        monkeypatch.setattr(fb, "get_option_mid", lambda c, s: 1.00)
        monkeypatch.setattr(fb, "marketable_limit_price",
                            lambda c, s, side="buy", buffer=0.03: 1.08)
        monkeypatch.setattr(fb, "open_buy_orders", lambda c, s: [])
        monkeypatch.setattr(fb, "open_spy_option_positions",
                            lambda c: [] if account_flat else [{"symbol": "SPY260720C00748000"}])
        monkeypatch.setattr(fb, "cancel_order", lambda *a, **k: {})
        try:
            import strike_selection as ss
            monkeypatch.setattr(ss, "pick_strike", _boom_pick_strike)
        except Exception:  # noqa: BLE001
            pass
        monkeypatch.setattr(hc, "STATE", tmp_path)
        monkeypatch.setattr(hc, "_et_now", lambda: dt.datetime(2026, 7, 20, 11, 0))
        monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", True)
        monkeypatch.setattr(hc, "_adopt_untracked_positions", lambda *a, **k: [])
        monkeypatch.setitem(sys.modules, "exit_actuator",
                            types.SimpleNamespace(register_entry=lambda *a, **k: None))
        monkeypatch.setitem(sys.modules, "strategies",
                            types.SimpleNamespace(by_name=lambda n: None))

        class _Resp:
            def read(self):
                return json.dumps({"equity": "1750.0"}).encode("utf-8")

        import urllib.request as _ur
        monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: _Resp())
        return posts

    @pytest.mark.parametrize("account,params,verdict_dir", [
        ("safe", SAFE_PARAMS, "ENTER_BEAR"),
        ("safe", SAFE_PARAMS, "ENTER_BULL"),
        ("bold", BOLD_PARAMS, "ENTER_BEAR"),
        ("bold", BOLD_PARAMS, "ENTER_BULL"),
    ])
    def test_primary_route_refuses_when_not_flat(self, hc, monkeypatch, tmp_path,
                                                 account, params, verdict_dir):
        """Rule 4 / never-average-down, primary ribbon route: an open position (any
        premium, any direction) blocks a second entry outright -- no averaging up OR
        down is possible because no add of any kind is possible."""
        posts = self._wire(hc, monkeypatch, tmp_path, account_flat=False)
        verdict = {"verdict": verdict_dir,
                  "setup_name": ("BEARISH_REJECTION_RIDE_THE_RIBBON" if verdict_dir == "ENTER_BEAR"
                                 else "BULLISH_RECLAIM_RIDE_THE_RIBBON")}
        plan = hc._execute(account, verdict,
                           {"bar_ctx": {"timestamp_et": "2026-07-20 11:00:00",
                                        "bar": {"close": 748.0}}},
                           params, dry=False)
        assert plan["status"] == "NOT_FLAT", plan
        assert not posts, "an order POST was attempted while an existing position was open"

    def test_extra_setup_route_refuses_when_not_flat(self, hc, monkeypatch, tmp_path):
        """The G4 extra-setup route calls the SAME _execute (heartbeat_core.py line
        ~1827) -- confirm a non-primary setup is equally blocked, not just the ribbon path."""
        posts = self._wire(hc, monkeypatch, tmp_path, account_flat=False)
        verdict = {"verdict": "ENTER_BULL", "setup_name": "vwap_continuation",
                  "triggers_fired": ["vwap_continuation"]}
        plan = hc._execute("safe", verdict,
                           {"bar_ctx": {"timestamp_et": "2026-07-20 11:00:00",
                                        "bar": {"close": 748.0}}},
                           SAFE_PARAMS, dry=False)
        assert plan["status"] == "NOT_FLAT", plan
        assert not posts

    def test_control_when_flat_the_route_still_works(self, hc, monkeypatch, tmp_path):
        """Sanity control: the harness itself is capable of a PLACED result when
        account_flat=True, proving the NOT_FLAT result above is the flat-check firing,
        not a harness artifact swallowing every attempt."""
        posts = self._wire(hc, monkeypatch, tmp_path, account_flat=True)
        # strike_selection.pick_strike is boobytrapped in this harness (see _boom_pick_strike)
        # specifically so a regression that reaches pricing while NOT_FLAT would blow up loud;
        # here (flat=True) it is expected to be reached, so unbooby-trap it for this one case.
        import strike_selection as ss
        monkeypatch.setattr(ss, "pick_strike", lambda spy, equity, side, tiers: 748)
        verdict = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON"}
        plan = hc._execute("safe", verdict,
                           {"bar_ctx": {"timestamp_et": "2026-07-20 11:00:00",
                                        "bar": {"close": 748.0}}},
                           SAFE_PARAMS, dry=False)
        assert plan["status"] == "PLACED", plan
        assert posts, "control case: flat account must reach the broker POST"


# =============================================================================
# (b) fleet_live.run() -- the same unconditional block, fleet-wide
# =============================================================================
class TestFleetLiveRefusesStackedEntry:
    def test_run_never_places_when_not_flat_even_with_a_live_enter_decision(self, fl, monkeypatch, tmp_path):
        """Force decide_arm to return an ENTER verdict (as if a fresh trigger fired) while
        is_flat_spy_options reports False -- fleet_live's own AND-gate (line ~531:
        `arm_live and decision.action in (...) and flat and usable_signal`) must refuse
        placement regardless of what decide_arm says. _place_live is monkeypatched to
        raise if ever called -- the only way this test can pass is the `flat` term in
        that AND-gate actually gating."""
        import fleet_executor as fx

        def _boom_place_live(*a, **k):
            raise AssertionError("_place_live must never be called while flat=False -- "
                                  "this is exactly the average-down/stacking path Rule 4 forbids")

        fake_decision = fx.ArmDecision(
            arm_id="safe-1", action="ENTER_BEAR", side="P", setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
            strike=748, qty=3, premium=1.10, quality="TRENDLINE", risk_code="ALLOW",
            reason="forced-for-guard-test")

        monkeypatch.setattr(fl, "decide_arm",
                            lambda *a, **k: (fake_decision, {"premium_stop_pct": -0.50, "tp1_premium_pct": 0.30}))
        monkeypatch.setattr(fl, "_place_live", _boom_place_live)
        monkeypatch.setattr(fl.fb, "load_creds",
                            lambda: {a["id"]: _CREDS for a in
                                     json.loads((_FLEET / "accounts.json").read_text(encoding="utf-8"))
                                     .get("arms", [])})
        monkeypatch.setattr(fl.fb, "get_account", lambda c: {"equity": "2000.0", "daytrade_count": 0})
        monkeypatch.setattr(fl.fb, "is_flat_spy_options", lambda c: False)  # <-- the load-bearing line
        monkeypatch.setattr(fl.ea, "manage_tick", lambda *a, **k: [])
        monkeypatch.setattr(fl, "FLEET_DIR", tmp_path)
        # A minimal usable signal so `usable_signal` is truthy (isolates the `flat` term --
        # without this the AND-gate would refuse for a DIFFERENT reason and the test would
        # pass for the wrong cause).
        sig_path = tmp_path / "shared-signal.json"
        sig_path.write_text(json.dumps({
            "tick_id": "t1", "generated_at_et": "2026-07-20T11:00:00",
            "ribbon_stack": "BEAR", "spot": 748.0,
        }), encoding="utf-8")
        monkeypatch.setattr(fl, "SIGNAL_MAX_AGE_SEC", 10_000_000)  # never stale in this harness

        results = fl.run(sig_path, master_live=True)

        assert results, "harness produced no rows -- broke before reaching the gate under test"
        for row in results:
            placement = row.get("placement") or {}
            assert placement.get("placed") is not True, (
                f"{row.get('arm_id')}: an order was placed while flat=False -- {row}")
            if row.get("action") in ("ENTER_BEAR", "ENTER_BULL"):
                assert placement.get("reason") == "not_flat", row


# =============================================================================
# no-bypass pin: is_flat_spy_options has no force/override parameter, anywhere
# =============================================================================
class TestNoBypassParameter:
    def test_is_flat_spy_options_signature_has_no_bypass_arg(self):
        import fleet_broker as fb
        sig = inspect.signature(fb.is_flat_spy_options)
        assert list(sig.parameters) == ["creds"], (
            f"is_flat_spy_options gained a new parameter {list(sig.parameters)} -- if this is "
            "a force/override/skip-check flag, it reopens the averaging-down path this guard "
            "exists to keep closed; update this pin only after confirming no caller can set it "
            "to bypass the flat-check on a live route.")

    def test_execute_signature_has_no_stack_or_add_kwarg(self, hc):
        sig = inspect.signature(hc._execute)
        forbidden = {"allow_stack", "force", "bypass_flat", "add", "stack"}
        present = set(sig.parameters) & forbidden
        assert not present, f"_execute grew a bypass-shaped kwarg: {present}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
