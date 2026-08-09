"""Guards for futures_trader_core + futures_journal + the live data spine.

These pin the SEAMS -- the places where this lane talks to something it does not own
(the broker's return shapes, the broker's ledger field names, the journal's disclosure
column). Every bug this file would catch is a silent one: the code keeps running and
quietly produces nothing, or produces something undisclosed.
"""
from __future__ import annotations

import csv
import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from futures.fill_sim_broker import FillSimBroker  # noqa: E402
from futures.instruments import MES  # noqa: E402
from futures import futures_trader_core as core  # noqa: E402
from futures import futures_journal as fj  # noqa: E402
from futures.futures_risk_rails import FuturesRiskRails  # noqa: E402

RTH_WED = dt.datetime(2026, 8, 12, 11, 0)


@pytest.fixture()
def broker(tmp_path):
    b = FillSimBroker(state_dir=tmp_path, start_equity=2_000.0)
    b.connect()
    return b


# ── broker seam ───────────────────────────────────────────────────────────────

class TestBrokerSeam:
    def test_factory_returns_fillsim_by_default(self, tmp_path):
        b = core.make_broker("fillsim", state_dir=tmp_path)
        assert core.backend_name(b) == "FillSimBroker"
        assert core.is_simulated(b) is True

    def test_unknown_backend_is_a_loud_error(self):
        with pytest.raises(ValueError, match="unknown broker backend"):
            core.make_broker("definitely-not-a-broker")

    def test_process_quote_returns_a_flat_event_not_a_list(self, broker):
        """The exact shape bug the drills caught: run_tick read ev["events"] (a list)
        when process_quote returns ONE flat dict keyed "event". Reading the wrong key
        recorded zero exits forever while the fill engine worked perfectly."""
        broker.place_bracket("MES", "BUY", 1, 7_800.0, 7_820.0, 7_790.0)
        broker.process_quote("MES", 7_800.0, bar_open=7_802.0, bar_high=7_803.0,
                             bar_low=7_799.0)
        ev = broker.process_quote("MES", 7_789.0, bar_open=7_798.0, bar_high=7_799.0,
                                  bar_low=7_788.0)
        assert "events" not in ev, "shape changed -- run_tick's exit reader must follow"
        assert ev["event"] == "stop" and ev["action"] == "FULL_STOP"
        assert ev["qty_open_after"] == 0

    def test_session_pnl_reads_the_real_ledger_fields(self, broker):
        """The C14 dead-knob guard. If the broker renames daily_pnl / last_reset_date_et,
        _session_realized_pnl silently returns 0.0 forever and the session-loss rail
        quietly stops working. This fails loudly instead."""
        snap = broker.get_account_snapshot()
        assert core._PNL_FIELD in snap, f"{core._PNL_FIELD} gone from the account ledger"
        assert core._PNL_DATE_FIELD in snap, f"{core._PNL_DATE_FIELD} gone from the ledger"

    def test_session_pnl_is_read_when_the_date_matches(self, broker, monkeypatch):
        today = dt.datetime(2026, 8, 12, 11, 0)
        monkeypatch.setattr(broker, "get_account_snapshot",
                            lambda: {core._PNL_FIELD: -137.5,
                                     core._PNL_DATE_FIELD: "2026-08-12"})
        assert core._session_realized_pnl(broker, today) == -137.5

    def test_stale_session_date_does_not_leak_into_today(self, broker, monkeypatch):
        """Yesterday's losses must not consume today's session budget."""
        monkeypatch.setattr(broker, "get_account_snapshot",
                            lambda: {core._PNL_FIELD: -900.0,
                                     core._PNL_DATE_FIELD: "2026-08-11"})
        assert core._session_realized_pnl(broker, dt.datetime(2026, 8, 12, 11, 0)) == 0.0

    def test_unreadable_ledger_degrades_to_zero_not_a_crash(self, broker, monkeypatch):
        def boom():
            raise RuntimeError("ledger unreadable")
        monkeypatch.setattr(broker, "get_account_snapshot", boom)
        assert core._session_realized_pnl(broker, RTH_WED) == 0.0


# ── the tick ──────────────────────────────────────────────────────────────────

class TestRunTick:
    def test_weekend_tick_holds(self, broker, tmp_path, monkeypatch):
        monkeypatch.setattr(core, "STATE_DIR", tmp_path)
        monkeypatch.setattr(core, "LEDGER", tmp_path / "decisions.jsonl")
        monkeypatch.setattr(core, "LAST_TICK", tmp_path / "last-tick.json")
        monkeypatch.setattr(core, "HEARTBEAT", tmp_path / "heartbeat.json")
        rec = core.run_tick("MES", broker=broker,
                            now_et=dt.datetime(2026, 8, 8, 12, 0), refresh=False)
        assert rec["action"] == "HOLD"
        assert "WEEKEND" in rec["reason"]

    def test_heartbeat_is_written_even_on_a_no_op(self, broker, tmp_path, monkeypatch):
        """A beacon only written when something happens cannot distinguish a quiet
        market from a dead lane -- the whole reason the crypto twin went dark unnoticed."""
        hb = tmp_path / "heartbeat.json"
        monkeypatch.setattr(core, "STATE_DIR", tmp_path)
        monkeypatch.setattr(core, "LEDGER", tmp_path / "decisions.jsonl")
        monkeypatch.setattr(core, "LAST_TICK", tmp_path / "last-tick.json")
        monkeypatch.setattr(core, "HEARTBEAT", hb)
        core.run_tick("MES", broker=broker,
                      now_et=dt.datetime(2026, 8, 8, 12, 0), refresh=False)
        assert hb.exists(), "no beacon on a HOLD tick -- staleness becomes undetectable"


# ── journal ───────────────────────────────────────────────────────────────────

class TestJournal:
    def test_every_trade_row_is_disclosed(self, tmp_path, monkeypatch):
        """An undisclosed fill class is the ambiguity the column exists to prevent."""
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        fj.record_trade({"date": "2026-08-12", "instrument": "MES", "dollar_pnl": 25.0})
        rows = list(csv.DictReader((tmp_path / "trades.csv").open(encoding="utf-8")))
        assert rows[0]["fills"] == "UNKNOWN"

    def test_unknown_keys_cannot_corrupt_column_alignment(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        fj.record_trade({"date": "2026-08-12", "fills": "SIMULATED",
                         "a_key_that_does_not_exist": "boom"})
        with (tmp_path / "trades.csv").open(encoding="utf-8") as fh:
            header = next(csv.reader(fh))
        assert header == fj.TRADE_COLUMNS

    def test_summarize_never_mixes_fill_classes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        fj.record_trade({"date": "2026-08-12", "fills": "SIMULATED", "dollar_pnl": 100.0})
        fj.record_trade({"date": "2026-08-12", "fills": "BROKER", "dollar_pnl": -500.0})
        sim = fj.summarize("SIMULATED")
        assert sim["n_trades"] == 1 and sim["total_pnl"] == 100.0
        assert fj.summarize("BROKER")["total_pnl"] == -500.0

    def test_a_foreign_header_is_rotated_not_appended_to(self, tmp_path, monkeypatch):
        """L294 guard: appending our rows under someone else's header writes every value
        into the wrong column, and each row still looks well-formed. A real abandoned
        2026-06-17 trades.csv with a different schema sat on disk when this was built."""
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        legacy = "date,instrument,direction,entry,pnl_usd\n2026-06-17,MES,long,1,2\n"
        (tmp_path / "trades.csv").write_text(legacy, encoding="utf-8")

        fj.record_trade({"date": "2026-08-12", "fills": "SIMULATED", "dollar_pnl": 25.0})

        with (tmp_path / "trades.csv").open(encoding="utf-8") as fh:
            header = next(csv.reader(fh))
        assert header == fj.TRADE_COLUMNS, "foreign header was appended to, not rotated"
        rotated = list(tmp_path.glob("trades.legacy-*.csv"))
        assert rotated, "legacy file was destroyed instead of preserved"
        assert "pnl_usd" in rotated[0].read_text(encoding="utf-8")

    def test_matching_header_is_left_alone(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")
        fj.record_trade({"date": "2026-08-12", "fills": "SIMULATED", "dollar_pnl": 1.0})
        fj.record_trade({"date": "2026-08-12", "fills": "SIMULATED", "dollar_pnl": 2.0})
        assert not list(tmp_path.glob("trades.legacy-*.csv"))
        assert len(fj.read_trades()) == 2

    def test_journal_never_raises_on_a_malformed_tick(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        fj.journal_entry({})            # no entry block
        fj.journal_entry({"entry": {}})  # empty entry block


# ── round-trip recording ──────────────────────────────────────────────────────

class TestRoundTripRecording:
    def test_closed_round_trip_writes_a_disclosed_ledger_row(self, broker, tmp_path,
                                                            monkeypatch):
        monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
        monkeypatch.setattr(fj, "TRADES_CSV", tmp_path / "trades.csv")

        broker.place_bracket("MES", "BUY", 1, 7_800.0, 7_820.0, 7_790.0)
        broker.process_quote("MES", 7_800.0, bar_open=7_802.0, bar_high=7_803.0,
                             bar_low=7_799.0)
        pre = core._position_snapshot(broker, "MES")
        assert pre.get("entry") == 7_800.0, "entry context must exist BEFORE the close"

        ev = broker.process_quote("MES", 7_789.0, bar_open=7_798.0, bar_high=7_799.0,
                                  bar_low=7_788.0)
        core._record_round_trip(broker, MES, pre, ev, RTH_WED, {"equity": 2_000.0})

        rows = list(csv.DictReader((tmp_path / "trades.csv").open(encoding="utf-8")))
        assert len(rows) == 1
        row = rows[0]
        assert row["fills"] == "SIMULATED"
        assert row["instrument"] == "MES"
        assert row["exit_reason"] == "FULL_STOP"
        assert float(row["entry_px"]) == 7_800.0
        assert float(row["dollar_pnl"]) < 0
        assert float(row["stop_points"]) == 10.0
        assert float(row["risk_usd"]) == 50.0   # 10 pts x $5 x 1

    def test_snapshot_is_empty_for_a_broker_without_one(self):
        class Bare:
            pass
        assert core._position_snapshot(Bare(), "MES") == {}


# ── data spine ────────────────────────────────────────────────────────────────

class TestDataSpine:
    def test_freshness_says_closed_not_stale_on_a_weekend(self):
        from futures import futures_live_data as fld  # noqa: PLC0415

        out = fld.freshness("MES", "5m", now_et=dt.datetime(2026, 8, 8, 12, 0))
        assert out["verdict"] in ("CLOSED", "BLIND")

    def test_only_green_authorizes_an_entry(self):
        rails = FuturesRiskRails()
        for v in ("RED", "YELLOW", "BLIND", "CLOSED", "WARMUP"):
            assert not rails.check_data_freshness(v).allow
        assert rails.check_data_freshness("GREEN").allow

    def test_live_and_master_paths_are_distinct(self):
        """The validated roll-adjusted master must never be the live write target."""
        from futures import futures_live_data as fld  # noqa: PLC0415

        assert fld.live_path("MES", "5m") != fld.master_path("MES", "5m")
        assert "continuous" in fld.master_path("MES", "5m").name
        assert "live" in fld.live_path("MES", "5m").name


# ── EOD review ────────────────────────────────────────────────────────────────

class TestFuturesEod:
    """The digest's job is to make a DEAD lane look different from a QUIET one."""

    def _rows(self, n, date="2026-08-12"):
        return [{"ts_et": f"{date}T10:{i:02d}:00", "action": "HOLD", "n_signals": 0,
                 "freshness": "GREEN"} for i in range(n)]

    def test_a_dark_lane_is_not_reported_as_a_quiet_one(self):
        from futures import futures_eod as eod  # noqa: PLC0415

        dark = eod.tick_coverage([], "2026-08-12")
        quiet = eod.tick_coverage(self._rows(78), "2026-08-12")
        assert dark["verdict"] == "DARK"
        assert quiet["verdict"] == "GREEN"
        assert dark["verdict"] != quiet["verdict"], (
            "zero trades from a dead engine must not render like zero trades from a "
            "disciplined one -- this is the whole point of the coverage metric")

    def test_partial_coverage_is_yellow_then_red(self):
        """Bands are fractions of the 78 expected ticks: >=90% GREEN, >=70% YELLOW,
        anything above zero below that RED. 65/78 = 83% and 40/78 = 51%."""
        from futures import futures_eod as eod  # noqa: PLC0415

        assert eod.tick_coverage(self._rows(72), "2026-08-12")["verdict"] == "GREEN"
        assert eod.tick_coverage(self._rows(65), "2026-08-12")["verdict"] == "YELLOW"
        assert eod.tick_coverage(self._rows(40), "2026-08-12")["verdict"] == "RED"

    def test_weekend_is_no_session_not_a_failure(self):
        from futures import futures_eod as eod  # noqa: PLC0415

        assert eod.tick_coverage([], "2026-08-08")["verdict"] == "WEEKEND"

    def test_dark_coverage_forces_a_red_digest_even_with_no_rule_breaks(self, monkeypatch):
        from futures import futures_eod as eod  # noqa: PLC0415

        monkeypatch.setattr(eod, "_read_ledger", lambda date: [])
        monkeypatch.setattr(eod, "round_trips",
                            lambda date, fills: {"fills": fills, "n": 0, "total_pnl": 0.0,
                                                 "win_rate": None, "best": None,
                                                 "worst": None, "by_setup": {},
                                                 "by_exit": {}, "rows": []})
        d = eod.build("2026-08-12")
        assert d["verdict"] == "RED" and not d["rule_breaks"]

    def test_post_hoc_audit_catches_an_entry_the_gate_should_have_blocked(self):
        """Independent of the pre-trade gate on purpose: a bypassed or mis-wired gate is
        invisible to a check that only runs inside that same gate."""
        from futures import futures_eod as eod  # noqa: PLC0415

        rows = [{"ts_et": "2026-08-12T10:00:00", "action": "ENTER", "freshness": "RED",
                 "entry": {"qty": 9, "risk_usd": 900.0, "stop": None}}]
        breaks = eod.rule_audit(rows, {"total_pnl": 0.0})
        rules = {b["rule"] for b in breaks}
        assert {"contract_cap", "per_trade_risk", "defined_stop", "data_freshness"} <= rules

    def test_a_clean_entry_raises_no_breaks(self):
        from futures import futures_eod as eod  # noqa: PLC0415

        rows = [{"ts_et": "2026-08-12T10:00:00", "action": "ENTER", "freshness": "GREEN",
                 "entry": {"qty": 1, "risk_usd": 50.0, "stop": 7790.0}}]
        assert eod.rule_audit(rows, {"total_pnl": 25.0}) == []

    def test_session_loss_cap_breach_is_flagged(self):
        from futures import futures_eod as eod  # noqa: PLC0415

        breaks = eod.rule_audit([], {"total_pnl": -250.0})
        assert any(b["rule"] == "session_loss_cap" for b in breaks)


# ── the corrected provisioning gate ───────────────────────────────────────────

class TestBrokerProvisioningGate:
    """Guards for futures_heartbeat_core's arm gate, CORRECTED 2026-08-09.

    These live here rather than in test_futures_heartbeat.py because that file has an
    autouse fixture which monkeypatches `_broker_provisioned` wholesale -- so every test
    in it passes without ever executing the gate's real body. The gate is what decides
    whether a live account routes, so it needs coverage that actually runs it.

    The behaviour being pinned: futures_bp is NOT the provisioning signal. Cert account
    5WW73759 reads futures_bp=0.0 and is_futures_approved=false while demonstrably
    routing AND filling real sandbox orders (proven end-to-end 2026-08-09 18:07-18:12 ET).
    Gating on futures_bp meant a working armed account routed nothing, forever, while
    reporting itself safe.
    """

    class _Broker:
        watch_only = False
        def __init__(self, connected=True):
            self._connected = connected
            self._account = object()
            self._session = object()
        def is_connected(self): return self._connected
        def connect(self): self._connected = True; return True
        def get_account_equity(self): return 2000.0

    def test_watch_only_never_provisions(self):
        from futures import futures_heartbeat_core as hb  # noqa: PLC0415

        b = self._Broker()
        b.watch_only = True
        ok, detail = hb._broker_provisioned(b)
        assert ok is False and detail["reason"] == "watch_only"

    def test_accepts_orders_fails_safe_without_a_session(self):
        from futures import futures_heartbeat_core as hb  # noqa: PLC0415

        class Bare:
            pass
        ok, why = hb._broker_accepts_orders(Bare())
        assert ok is False and why

    def test_zero_futures_bp_still_provisions_when_the_broker_accepts_orders(self, monkeypatch):
        """THE regression this change exists to prevent. futures_bp=0.0 is the REAL
        state of a sandbox account that routes and fills; it must not block arming."""
        from futures import futures_heartbeat_core as hb  # noqa: PLC0415

        monkeypatch.setattr(hb, "_read_futures_bp", lambda b: 0.0)
        monkeypatch.setattr(hb, "_broker_accepts_orders", lambda b: (True, "dry_run validated"))
        ok, detail = hb._broker_provisioned(self._Broker())
        assert ok is True, "futures_bp=0.0 blocked a broker that accepts orders -- the old bug"
        assert detail["futures_bp"] == 0.0
        assert detail["accepts_orders"] is True

    def test_refusal_to_accept_orders_blocks_even_with_healthy_futures_bp(self, monkeypatch):
        """The inverse: a fat futures_bp must not wave through a broker that is
        refusing orders. Proves the gate moved to the right signal, not just a looser one."""
        from futures import futures_heartbeat_core as hb  # noqa: PLC0415

        monkeypatch.setattr(hb, "_read_futures_bp", lambda b: 50_000.0)
        monkeypatch.setattr(hb, "_broker_accepts_orders",
                            lambda b: (False, "dry_run errors: ['not_allowed']"))
        ok, detail = hb._broker_provisioned(self._Broker())
        assert ok is False
        assert detail["futures_bp"] == 50_000.0, "bp is still reported as context"

    def test_probe_exception_fails_safe(self, monkeypatch):
        from futures import futures_heartbeat_core as hb  # noqa: PLC0415

        def boom(b):
            raise RuntimeError("broker exploded")
        monkeypatch.setattr(hb, "_broker_accepts_orders", boom)
        ok, detail = hb._broker_provisioned(self._Broker())
        assert ok is False and "probe_error" in detail.get("reason", "")


# ── lane isolation ────────────────────────────────────────────────────────────

class TestLaneIsolation:
    """Two lanes, same decisions, different execution backends -- and never a shared file.

    Also pins that path resolution reads the CURRENT module globals. An import-time
    frozen mapping silently defeats monkeypatch-based isolation, which is how the replay
    drill once wrote simulated trades into the real journal.
    """

    def test_the_two_lanes_never_share_a_state_dir(self):
        sim = core.lane_paths(backend="fillsim")
        brk = core.lane_paths(backend="tastytrade")
        assert sim["dir"] != brk["dir"]
        for key in ("ledger", "last_tick", "heartbeat", "loop_state"):
            assert sim[key] != brk[key], f"{key} collides across lanes"
        assert brk["dir"].name == core.BROKER_LANE_DIRNAME

    def test_fillsim_lane_keeps_the_original_paths(self):
        """No existing monitor entry or documented path may move."""
        sim = core.lane_paths(backend="fillsim")
        assert sim["dir"] == core.STATE_DIR
        assert sim["heartbeat"] == core.HEARTBEAT

    def test_paths_follow_a_monkeypatched_state_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(core, "STATE_DIR", tmp_path)
        monkeypatch.setattr(core, "HEARTBEAT", tmp_path / "heartbeat.json")
        monkeypatch.setattr(core, "LEDGER", tmp_path / "decisions.jsonl")
        monkeypatch.setattr(core, "LAST_TICK", tmp_path / "last-tick.json")
        monkeypatch.setattr(core, "LOOP_STATE", tmp_path / "loop-state.json")
        assert core.lane_paths(backend="fillsim")["dir"] == tmp_path
        # the broker lane must relocate WITH it, not stay pinned to the real tree
        assert core.lane_paths(backend="tastytrade")["dir"].parent == tmp_path.parent

    def test_explicit_state_dir_always_wins(self, tmp_path):
        p = core.lane_paths(state_dir=tmp_path, backend="tastytrade")
        assert p["dir"] == tmp_path


class TestBrokerLaneSafety:
    def test_an_unconnected_broker_lane_refuses_to_act(self, tmp_path, monkeypatch):
        """A lane that cannot reach its broker must not keep calling itself a broker
        lane -- that is how phantom BROKER rows enter a ledger whose interpretability
        rests entirely on that column."""
        monkeypatch.setattr(core, "STATE_DIR", tmp_path)
        monkeypatch.setattr(core, "LEDGER", tmp_path / "decisions.jsonl")
        monkeypatch.setattr(core, "LAST_TICK", tmp_path / "last-tick.json")
        monkeypatch.setattr(core, "HEARTBEAT", tmp_path / "heartbeat.json")

        class DeadBroker:
            watch_only = False
            def connect(self): return False
            def is_connected(self): return False
            def is_flat(self, s): return True
            def get_positions(self): return []
            def get_account_equity(self): return None

        rec = core.run_tick("MES", broker=DeadBroker(), state_dir=tmp_path,
                            now_et=RTH_WED, refresh=False, freshness_override="GREEN")
        assert rec["action"] == "HOLD"
        assert rec["reason"] == "broker_not_connected"
        assert rec["connected"] is False

    def test_a_simulated_lane_is_unaffected_by_the_connection_gate(self, broker, tmp_path,
                                                                  monkeypatch):
        monkeypatch.setattr(core, "STATE_DIR", tmp_path)
        monkeypatch.setattr(core, "LEDGER", tmp_path / "decisions.jsonl")
        monkeypatch.setattr(core, "LAST_TICK", tmp_path / "last-tick.json")
        monkeypatch.setattr(core, "HEARTBEAT", tmp_path / "heartbeat.json")
        rec = core.run_tick("MES", broker=broker, state_dir=tmp_path,
                            now_et=dt.datetime(2026, 8, 8, 12, 0), refresh=False)
        assert rec["reason"] != "broker_not_connected"

    def test_sandbox_reset_is_reconciled_not_mistaken_for_a_lost_fill(self, tmp_path):
        """The cert environment wipes positions every 24h. Reading that as 'we lost a
        fill' would strand the lane in a permanent no-stack HOLD."""
        paths = core.lane_paths(state_dir=tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "open-position.json").write_text(
            '{"positions": [{"symbol": "/MESU6", "qty": 1}]}', encoding="utf-8")

        class FlatBroker:
            watch_only = False
            def is_flat(self, s): return True
            def get_positions(self): return []

        note = core._reconcile_broker_reset(FlatBroker(), "MES", paths, RTH_WED)
        assert note and note["event"] == "broker_position_vanished"
        assert not (tmp_path / "open-position.json").exists(), "stale local record not cleared"

    def test_reset_reconciliation_never_runs_on_the_simulator(self, broker, tmp_path):
        """A fillsim disagreement is a real bug in OUR engine, not a venue reset --
        papering over it with 'must have been the sandbox' would hide it."""
        paths = core.lane_paths(state_dir=tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "open-position.json").write_text('{"positions": [1]}', encoding="utf-8")
        assert core._reconcile_broker_reset(broker, "MES", paths, RTH_WED) is None
        assert (tmp_path / "open-position.json").exists()
