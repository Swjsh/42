"""Tests for setup/scripts/crypto_twin_entry_quality.py + crypto_twin_core.place_entry_ab
-- TWIN-B3: passive-limit entry LIVE measurement (EDGE-1 graduation).

Covers: deterministic A/B alternation (marketable-first, persisted counter, fail-open),
entry-quality metric computation on fixture fills (fill rate / abandonment / time-to-fill
/ price improvement vs the marketable baseline), the recent-list retention cap (OP-22),
the passive actuator's full order lifecycle against a fake broker (fill, patience-
exhausted timeout + REAL cancel, fill-during-cancel race, partial-fill crumb flatten),
the place_entry_ab dispatcher (marketable-first alternation through run_tick, passive
fill registers a REAL exit_manager position, passive miss surfaces PASSIVE_ENTRY_MISSED
and leaves the account flat, no-quote fallback still enters via the marketable path,
WATCH mode never burns an A/B index), and scenario-scheduler compatibility (a passive
miss on a forced branch never marks the branch in-flight -- it is retried later).

Mirrors test_crypto_twin_scenarios.py's _twin_cfg(tmp_path) isolation convention + its
local _FakeBroker fixture shape (kept local, not imported, per this codebase's per-file
self-containment convention) -- every test runs fully isolated from the real
automation/state/crypto-twin/ ledger (no LIVE-ledger writes from tests).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", "automation/state/fleet", ""):
    sys.path.insert(0, str(REPO / _p) if _p else str(REPO))

import crypto_twin_core as ctc  # noqa: E402
import crypto_twin_entry_quality as eqm  # noqa: E402
import crypto_twin_scenarios as cts  # noqa: E402


def _twin_cfg(tmp_path: Path, **overrides) -> ctc.TwinConfig:
    state_dir = tmp_path / "automation" / "state" / "crypto-twin"
    overrides.setdefault("passive_poll_seconds", 0.0)  # never sleep in tests
    return ctc.TwinConfig(state_dir=state_dir, **overrides)


def _raw_bar(ts: datetime, o: float, h: float, l: float, c: float, v: float = 1.0) -> dict:
    return {"t": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": o, "h": h, "l": l, "c": c, "v": v}


def _flat_bars(now: datetime, price: float = 64000.0, n: int = 80) -> list[dict]:
    return [_raw_bar(now - timedelta(minutes=5 * i), price, price + 1, price - 1, price, 1.0)
           for i in range(n, 0, -1)]


# ============================================================================
# Fake broker (local; extends the scenarios fixture shape with limit-order +
# get_order/cancel_order support for the passive lifecycle)
# ============================================================================
class _FakeBroker:
    def __init__(self):
        self.orders = []
        self.sells = []
        self.cancels = []
        self.position_qty = 0.0
        self.quote = (64010.0, 63990.0)  # (ask, bid) -- $20 spread around 64000
        # scripted passive-order behavior:
        self.limit_fill_on_poll = None    # fill the limit order on the Nth get_order poll
        self.fill_after_cancel = False    # simulate the fill-during-cancel race
        self.partial_qty_after_cancel = 0.0  # simulate a partial-fill remnant
        self._polls = 0
        self._cancelled = False
        self._last_entry_price = 64000.0

    def place_crypto_order(self, creds, *, symbol, side, notional=None, qty=None,
                           order_type="market", limit_price=None, live):
        self.orders.append({"symbol": symbol, "side": side, "notional": notional, "qty": qty,
                            "order_type": order_type, "limit_price": limit_price, "live": live})
        if qty and side == "buy":
            self.position_qty = qty
        return {"id": f"order-{len(self.orders)}", "status": "accepted"}

    def poll_fill(self, creds, order_id, attempts=4, sleep_sec=1.5):
        return {"filled": True, "status": "filled", "filled_qty": self.position_qty,
               "filled_avg_price": self._last_entry_price, "order": {}}

    def get_order(self, creds, order_id):
        if self._cancelled:
            if self.fill_after_cancel:  # the fill-during-cancel race
                return {"id": order_id, "status": "filled", "filled_qty": self.position_qty,
                        "filled_avg_price": self._limit_price_of(order_id)}
            if self.partial_qty_after_cancel:  # a partial-fill remnant survived the cancel
                return {"id": order_id, "status": "canceled",
                        "filled_qty": self.partial_qty_after_cancel,
                        "filled_avg_price": self._limit_price_of(order_id)}
            return {"id": order_id, "status": "canceled", "filled_qty": 0, "filled_avg_price": None}
        self._polls += 1
        if self.limit_fill_on_poll is not None and self._polls >= self.limit_fill_on_poll:
            return {"id": order_id, "status": "filled", "filled_qty": self.position_qty,
                    "filled_avg_price": self._limit_price_of(order_id)}
        return {"id": order_id, "status": "new", "filled_qty": 0, "filled_avg_price": None}

    def _limit_price_of(self, order_id) -> float:
        for o in reversed(self.orders):
            if o.get("limit_price") is not None:
                return o["limit_price"]
        return self._last_entry_price

    def cancel_order(self, creds, order_id, *, live):
        self.cancels.append({"order_id": order_id, "live": live})
        self._cancelled = True
        if not self.fill_after_cancel and not self.partial_qty_after_cancel:
            self.position_qty = 0.0
        return {"status": "canceled"}

    def get_crypto_position_qty(self, creds, symbol="BTC/USD"):
        return self.position_qty

    def get_crypto_quote_hilo(self, symbol="BTC/USD", creds=None):
        return self.quote

    def market_sell_crypto(self, creds, *, symbol, qty, live):
        self.sells.append({"symbol": symbol, "qty": qty, "live": live})
        return {"id": f"sell-{len(self.sells)}", "status": "accepted"}

    def close_all_crypto(self, creds, *, symbol="BTC/USD", live):
        self.position_qty = 0.0
        return {"id": "close-1", "status": "accepted"}


@pytest.fixture
def fake_broker(monkeypatch):
    fb = _FakeBroker()
    # ctc.broker and eqm's broker are the SAME module object (sys.modules) -- patching
    # via ctc.broker covers both call sites.
    for name in ("place_crypto_order", "poll_fill", "get_order", "cancel_order",
                 "get_crypto_position_qty", "get_crypto_quote_hilo", "market_sell_crypto",
                 "close_all_crypto"):
        monkeypatch.setattr(ctc.broker, name, getattr(fb, name))
    return fb


_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.alpaca.markets"}


@pytest.fixture(autouse=True)
def _stub_account(monkeypatch):
    monkeypatch.setattr(ctc.broker, "get_twin_creds", lambda verify_crypto_status=True: _CREDS)
    monkeypatch.setattr(ctc.broker, "get_account", lambda creds: {"equity": 10000.0})


# ============================================================================
# A/B alternation -- deterministic, persisted, fail-open
# ============================================================================
def test_alternation_is_deterministic_and_marketable_first(tmp_path):
    state_dir = tmp_path / "automation" / "state" / "crypto-twin"
    seq = [eqm.allocate_cohort(state_dir) for _ in range(4)]
    assert seq == [("marketable", 0), ("passive", 1), ("marketable", 2), ("passive", 3)]


def test_alternation_counter_persists_across_loads(tmp_path):
    state_dir = tmp_path / "automation" / "state" / "crypto-twin"
    eqm.allocate_cohort(state_dir)
    eqm.allocate_cohort(state_dir)
    doc = eqm.load_entry_quality(state_dir)
    assert doc["ab_counter"] == 2
    assert eqm.allocate_cohort(state_dir) == ("marketable", 2)


def test_allocate_cohort_fail_open_returns_legacy_marketable(tmp_path):
    """An unwritable state_dir (a FILE occupying the path) must degrade to the legacy
    marketable path with ab_index=-1 -- never raise, never block an entry."""
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("occupied", encoding="utf-8")
    cohort, ab_index = eqm.allocate_cohort(blocked / "crypto-twin")
    assert (cohort, ab_index) == ("marketable", -1)


def test_load_entry_quality_corrupt_file_degrades_to_fresh(tmp_path):
    state_dir = tmp_path / "crypto-twin"
    state_dir.mkdir(parents=True)
    (state_dir / eqm.ENTRY_QUALITY_FILENAME).write_text("{not json", encoding="utf-8")
    doc = eqm.load_entry_quality(state_dir)
    assert doc["ab_counter"] == 0
    assert doc["recent"] == []


# ============================================================================
# Metric computation on fixture fills
# ============================================================================
def test_compute_improvement_positive_when_filled_below_baseline():
    usd, bps = eqm.compute_improvement(64000.0, 63968.0)
    assert usd == pytest.approx(32.0)
    assert bps == pytest.approx(5.0)


def test_compute_improvement_none_on_missing_inputs():
    assert eqm.compute_improvement(None, 63968.0) == (None, None)
    assert eqm.compute_improvement(64000.0, None) == (None, None)


def test_record_attempt_aggregates_fixture_fills(tmp_path):
    state_dir = tmp_path / "crypto-twin"
    eqm.record_attempt(state_dir, {"cohort": "passive", "outcome": "filled",
                                   "baseline_ask": 64000.0, "fill_price": 63968.0,
                                   "time_to_fill_sec": 40.0})
    eqm.record_attempt(state_dir, {"cohort": "passive", "outcome": "missed"})
    doc = eqm.load_entry_quality(state_dir)
    agg = doc["cohorts"]["passive"]
    assert agg["attempts"] == 2
    assert agg["fills"] == 1
    assert agg["misses"] == 1
    assert agg["fill_rate"] == pytest.approx(0.5)
    assert agg["abandonment_rate"] == pytest.approx(0.5)
    assert agg["avg_time_to_fill_sec"] == pytest.approx(40.0)
    assert agg["avg_improvement_usd_per_btc"] == pytest.approx(32.0)
    assert agg["avg_improvement_bps"] == pytest.approx(5.0)


def test_record_attempt_fallback_never_enters_fill_denominators(tmp_path):
    state_dir = tmp_path / "crypto-twin"
    eqm.record_attempt(state_dir, {"cohort": "passive", "outcome": "fallback",
                                   "fallback_reason": "no_quote"})
    agg = eqm.load_entry_quality(state_dir)["cohorts"]["passive"]
    assert agg["fallbacks"] == 1
    assert agg["attempts"] == 0
    assert agg["fill_rate"] is None


def test_recent_list_is_capped(tmp_path):
    state_dir = tmp_path / "crypto-twin"
    for i in range(eqm.RECENT_ATTEMPTS_CAP + 5):
        eqm.record_attempt(state_dir, {"cohort": "marketable", "outcome": "filled",
                                       "baseline_ask": 64000.0, "fill_price": 64000.0, "i": i})
    doc = eqm.load_entry_quality(state_dir)
    assert len(doc["recent"]) == eqm.RECENT_ATTEMPTS_CAP
    assert doc["recent"][-1]["i"] == eqm.RECENT_ATTEMPTS_CAP + 4  # newest retained
    assert doc["cohorts"]["marketable"]["attempts"] == eqm.RECENT_ATTEMPTS_CAP + 5  # lifetime intact


def test_record_attempt_never_raises_on_unwritable_dir(tmp_path):
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("occupied", encoding="utf-8")
    assert eqm.record_attempt(blocked / "crypto-twin",
                              {"cohort": "passive", "outcome": "filled"}) is None


# ============================================================================
# passive_limit_price -- non-marketable by construction
# ============================================================================
def test_passive_limit_price_mid_spread():
    assert eqm.passive_limit_price(64010.0, 63990.0, 0.5) == pytest.approx(64000.0)


def test_passive_limit_price_clamped_below_ask_on_tight_spread():
    limit = eqm.passive_limit_price(64000.01, 64000.0, 0.5)
    assert limit is not None and limit < 64000.01


def test_passive_limit_price_none_on_degenerate_quote():
    assert eqm.passive_limit_price(0.0, 63990.0, 0.5) is None
    assert eqm.passive_limit_price(63990.0, 64010.0, 0.5) is None  # crossed


# ============================================================================
# place_passive_entry -- the live actuator lifecycle against the fake broker
# ============================================================================
def _passive_kwargs(cfg, journal_rows):
    return dict(creds=_CREDS, symbol=cfg.symbol, qty_btc=ctc.entry_qty_btc(cfg),
                units=cfg.units_per_entry, unit_qty_btc=cfg.unit_qty_btc, side="bull",
                price=64000.0, trigger_level=None, scenario_tag=None, ab_index=1, live=True,
                patience_polls=cfg.passive_patience_polls,
                poll_seconds=cfg.passive_poll_seconds,
                limit_fraction=cfg.passive_limit_fraction,
                journal=lambda event, **f: journal_rows.append({"event": event, **f}))


def test_passive_entry_fills_on_poll(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    fake_broker.limit_fill_on_poll = 2
    rows = []
    res = eqm.place_passive_entry(**_passive_kwargs(cfg, rows))
    assert res["outcome"] == "filled"
    assert res["fill_price"] == pytest.approx(64000.0)  # filled at the mid-spread limit
    assert res["time_to_fill_sec"] >= 0
    assert res["race_fill"] is False
    assert fake_broker.orders[0]["order_type"] == "limit"
    assert fake_broker.orders[0]["limit_price"] == pytest.approx(64000.0)
    assert not fake_broker.cancels  # a fill never cancels
    placed = [r for r in rows if r["event"] == "PLACED"]
    assert placed and placed[0]["entry_mode"] == "passive"


def test_passive_entry_timeout_cancels_the_real_order(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    fake_broker.limit_fill_on_poll = None  # never fills
    rows = []
    res = eqm.place_passive_entry(**_passive_kwargs(cfg, rows))
    assert res["outcome"] == "missed"
    assert res["cancelled_by_core"] is True  # entry_manager's own CANCEL resolved it
    assert res["polls_used"] == cfg.passive_patience_polls
    assert len(fake_broker.cancels) == 1  # ONE real cancel
    assert res["partial_flattened"] is None


def test_passive_entry_fill_during_cancel_race_is_a_fill(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    fake_broker.limit_fill_on_poll = None
    fake_broker.fill_after_cancel = True
    rows = []
    res = eqm.place_passive_entry(**_passive_kwargs(cfg, rows))
    assert res["outcome"] == "filled"
    assert res["race_fill"] is True
    assert len(fake_broker.cancels) == 1


def test_passive_entry_partial_fill_remnant_is_flattened(tmp_path, fake_broker):
    """Unit-lot integrity (B1a): a partial-fill crumb left after the cancel is market-
    sold immediately, never left to corrupt the 3-unit exit split."""
    cfg = _twin_cfg(tmp_path)
    fake_broker.limit_fill_on_poll = None
    fake_broker.partial_qty_after_cancel = 0.0008
    rows = []
    res = eqm.place_passive_entry(**_passive_kwargs(cfg, rows))
    assert res["outcome"] == "missed"
    assert res["partial_flattened"]["qty_btc"] == pytest.approx(0.0008)
    assert fake_broker.sells and fake_broker.sells[0]["qty"] == pytest.approx(0.0008)
    assert any(r["event"] == "ENTRY_PARTIAL_FLATTENED" for r in rows)


def test_passive_entry_no_quote_is_a_fallback(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    fake_broker.quote = None
    res = eqm.place_passive_entry(**_passive_kwargs(cfg, []))
    assert res["outcome"] == "fallback"
    assert res["fallback_reason"] == "no_quote"
    assert not fake_broker.orders  # nothing was placed


# ============================================================================
# place_entry_ab + run_tick integration
# ============================================================================
def test_run_tick_first_entry_marketable_second_passive(tmp_path, fake_broker):
    """The dispatcher's alternation through the REAL run_tick path: entry #1 on a fresh
    state_dir takes the legacy marketable path (byte-identical pre-B3 behavior -- the
    property that keeps every pre-B3 test green), entry #2 goes passive."""
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    r1 = ctc.run_tick(cfg, live=True, force_entry="bull", now_utc=now, raw_bars=_flat_bars(now))
    assert r1["action"] == "ENTERED"
    assert r1["entry_mode"] == "marketable"
    assert fake_broker.orders[0]["order_type"] == "market"

    # close it out so the next tick is flat
    fake_broker.position_qty = 0.0
    ctc._save_positions(cfg, {})

    fake_broker.limit_fill_on_poll = 1
    now2 = now + timedelta(minutes=10)
    r2 = ctc.run_tick(cfg, live=True, force_entry="bull", now_utc=now2, raw_bars=_flat_bars(now2))
    assert r2["action"] == "ENTERED"
    assert r2["entry_mode"] == "passive"
    assert fake_broker.orders[-1]["order_type"] == "limit"

    doc = eqm.load_entry_quality(cfg.state_dir)
    assert doc["cohorts"]["marketable"]["fills"] == 1
    assert doc["cohorts"]["passive"]["fills"] == 1
    assert doc["ab_counter"] == 2


def test_run_tick_passive_fill_registers_real_exit_state(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    fake_broker.limit_fill_on_poll = 1
    row = ctc.run_tick(cfg, live=True, force_entry="bull", now_utc=now, raw_bars=_flat_bars(now),
                       entry_mode_override="passive")
    assert row["action"] == "ENTERED"
    positions = ctc._load_positions(cfg)
    rec = positions["BTC/USD"]
    assert rec["entry_mode"] == "passive"
    assert rec["exit_state"]["total_qty"] == cfg.units_per_entry  # unit-lot preserved
    assert rec["exit_state"]["entry_premium"] == pytest.approx(64000.0)  # the LIMIT fill price


def test_run_tick_passive_miss_action_and_flat(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    fake_broker.limit_fill_on_poll = None  # never fills
    row = ctc.run_tick(cfg, live=True, force_entry="bull", now_utc=now, raw_bars=_flat_bars(now),
                       entry_mode_override="passive")
    assert row["action"] == "PASSIVE_ENTRY_MISSED"
    assert row["entry_mode"] == "passive"
    assert row["position_status"] == "flat"
    assert ctc._load_positions(cfg) == {}
    doc = eqm.load_entry_quality(cfg.state_dir)
    assert doc["cohorts"]["passive"]["misses"] == 1
    journal = [json.loads(l) for l in
               (cfg.state_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(r["event"] == "ENTRY_MISSED" for r in journal)
    quality = [r for r in journal if r["event"] == "ENTRY_QUALITY"]
    assert quality and quality[0]["tier"] == "LIVE" and quality[0]["cohort"] == "passive"


def test_run_tick_passive_no_quote_falls_back_to_marketable(tmp_path, fake_broker):
    """Fail-open: the passive path degrading (no quote) must still ENTER via the
    marketable path -- the twin's uptime never hinges on the measurement layer."""
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    fake_broker.quote = None
    row = ctc.run_tick(cfg, live=True, force_entry="bull", now_utc=now, raw_bars=_flat_bars(now),
                       entry_mode_override="passive")
    assert row["action"] == "ENTERED"
    assert row["entry_mode"] == "marketable"
    assert fake_broker.orders[-1]["order_type"] == "market"
    agg = eqm.load_entry_quality(cfg.state_dir)["cohorts"]["passive"]
    assert agg["fallbacks"] == 1


def test_watch_mode_never_burns_an_ab_index(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    result = ctc.place_entry_ab(cfg, creds=_CREDS, side="bull", price=64000.0,
                                trigger_level=None, live=False)
    assert result["placed"] is False
    assert result["ab_index"] is None
    assert eqm.load_entry_quality(cfg.state_dir)["ab_counter"] == 0


def test_entry_mode_override_does_not_consume_ab_index(tmp_path, fake_broker):
    cfg = _twin_cfg(tmp_path)
    fake_broker.limit_fill_on_poll = 1
    result = ctc.place_entry_ab(cfg, creds=_CREDS, side="bull", price=64000.0,
                                trigger_level=None, live=True, entry_mode_override="passive")
    assert result["placed"] is True
    assert result["ab_index"] is None
    assert eqm.load_entry_quality(cfg.state_dir)["ab_counter"] == 0  # counter untouched


# ============================================================================
# Scenario-scheduler compatibility (BRANCH_REGISTRY untouched; a passive miss on a
# forced branch never marks it in-flight -- retried later, never a false INCIDENT)
# ============================================================================
def test_scenario_tick_passive_miss_does_not_mark_branch_active(tmp_path, fake_broker, monkeypatch):
    monkeypatch.setattr(cts, "_pick_next_branch", lambda coverage, *, today: "ENTRY_CAT_CAP")
    cfg = _twin_cfg(tmp_path)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    # force the NEXT A/B index to be passive (odd), and never fill it
    eqm.allocate_cohort(cfg.state_dir)  # burn index 0 (marketable)
    fake_broker.limit_fill_on_poll = None
    paths = {"coverage_path": cfg.state_dir / "path-coverage.json",
             "scenario_state_path": cfg.state_dir / "scenario-state.json"}
    result = cts.run_scenario_tick(cfg, live=True, now_utc=now, raw_bars=_flat_bars(now), **paths)
    assert result["row"]["action"] == "PASSIVE_ENTRY_MISSED"
    assert result["bookkeeping_error"] is None
    scenario_state = json.loads((cfg.state_dir / "scenario-state.json").read_text()) \
        if (cfg.state_dir / "scenario-state.json").exists() else {}
    assert scenario_state == {}  # NOT in flight -- branch stays available for retry
    coverage = json.loads((cfg.state_dir / "path-coverage.json").read_text())
    assert coverage["branches"]["ENTRY_CAT_CAP"]["status"] == "PENDING"  # never IN_PROGRESS

    # next tick retries the same branch (marketable this time -- index 2 is even)
    now2 = now + timedelta(minutes=5)
    r2 = cts.run_scenario_tick(cfg, live=True, now_utc=now2, raw_bars=_flat_bars(now2), **paths)
    assert r2["scheduler_decision"]["forced_branch"] == "ENTRY_CAT_CAP"
    assert r2["row"]["action"] == "ENTERED"


def test_branch_registry_untouched_by_b3():
    """TWIN-B3 hard rail: the BRANCH_REGISTRY schema is not modified by this build."""
    live = [n for n, m in cts.BRANCH_REGISTRY.items() if m["tier"] == "LIVE"]
    sim = [n for n, m in cts.BRANCH_REGISTRY.items() if m["tier"] == "SIM"]
    assert len(live) == 6 and len(sim) == 3
    for meta in cts.BRANCH_REGISTRY.values():
        assert set(meta.keys()) == {"tier", "expected_stage", "description"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
