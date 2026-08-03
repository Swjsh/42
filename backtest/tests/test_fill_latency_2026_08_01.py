"""FILL-PIPELINE LATENCY INSTRUMENT guard (2026-08-01, WEEKEND-TWELVE Next-Twelve #5).

Covers:
  A. setup/scripts/fill_latency.py -- the pure decomposition/summary functions + an
     end-to-end build_ledger() over synthetic on-disk fixtures shaped exactly like the real
     fills-ledger.jsonl / {arm}/decisions.jsonl / core-decisions.jsonl schemas.
  B. The new additive instrument fields themselves, at their source:
     - automation/state/fleet/fleet_live.py: _place_live's returned dict now carries
       "submit_ts"; run()'s per-arm row now carries "core_tick_id"/"signal_written_at".
     - automation/state/fleet/build_shared_signal.py: build()'s output now carries
       "core_tick_id" (the join key fill_latency.py uses to reach the core verdict).

RAIL-4 CLEAR: test-only, monkeypatches file paths to tmp_path, mutates nothing in production.
"""
from __future__ import annotations

import importlib
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
import fill_latency as flat        # noqa: E402
import fleet_live as fl            # noqa: E402
import fleet_executor as fx        # noqa: E402

ET = timezone(timedelta(hours=-4))


# =============================================================================
# A1. fill_latency pure functions
# =============================================================================
def test_parse_iso_handles_z_suffix_and_naive_and_none():
    assert flat._parse_iso("2026-07-31T16:19:03.936711Z") is not None
    assert flat._parse_iso("2026-07-31T12:19:03.936711") is not None
    assert flat._parse_iso(None) is None
    assert flat._parse_iso("") is None
    assert flat._parse_iso("not-a-timestamp") is None
    assert flat._parse_iso(12345) is None  # wrong type, never raises


def test_stage_deltas_full_population_computes_every_hop():
    stages = {
        "bar_close_ts": "2026-08-03T09:40:00-04:00",
        "core_verdict_ts": "2026-08-03T09:46:02-04:00",
        "signal_written_ts": "2026-08-03T09:46:05-04:00",
        "plan_ts": "2026-08-03T09:46:05.200000-04:00",
        "submit_ts": "2026-08-03T09:46:05.400000-04:00",
        "broker_submitted_ts": "2026-08-03T09:46:05.600000-04:00",
        "fill_ts": "2026-08-03T09:46:05.700000-04:00",
    }
    d = flat.stage_deltas(stages)
    assert d["bar_close_ts_to_core_verdict_ts_s"] == pytest.approx(362.0)
    assert d["core_verdict_ts_to_signal_written_ts_s"] == pytest.approx(3.0)
    assert d["signal_written_ts_to_plan_ts_s"] == pytest.approx(0.2)
    assert d["plan_ts_to_submit_ts_s"] == pytest.approx(0.2)
    assert d["submit_ts_to_broker_submitted_ts_s"] == pytest.approx(0.2)
    assert d["broker_submitted_ts_to_fill_ts_s"] == pytest.approx(0.1)
    assert d["total_s"] == pytest.approx(365.7)
    assert d["n_resolvable_stages"] == 7


def test_stage_deltas_partial_population_never_fabricates_a_missing_hop():
    """The PRE-FIX real-world shape (2026-07-31 history): only broker_submitted_ts + fill_ts
    exist. Every hop touching a missing stage is None -- never interpolated."""
    stages = {"bar_close_ts": None, "core_verdict_ts": None, "signal_written_ts": None,
             "plan_ts": None, "submit_ts": None,
             "broker_submitted_ts": "2026-07-31T16:19:03.838732Z",
             "fill_ts": "2026-07-31T16:19:03.936711Z"}
    d = flat.stage_deltas(stages)
    assert d["bar_close_ts_to_core_verdict_ts_s"] is None
    assert d["core_verdict_ts_to_signal_written_ts_s"] is None
    assert d["broker_submitted_ts_to_fill_ts_s"] == pytest.approx(0.098, abs=0.001)
    assert d["n_resolvable_stages"] == 2
    assert d["total_s"] == pytest.approx(0.098, abs=0.001)


def test_stage_deltas_all_missing_is_all_none():
    stages = {k: None for k in flat.STAGE_ORDER}
    d = flat.stage_deltas(stages)
    assert d["n_resolvable_stages"] == 0
    assert d["total_s"] is None
    assert all(v is None for k, v in d.items() if k.endswith("_s") and k != "total_s")


# =============================================================================
# A2. latency_row_from_fill -- the exclusion contract
# =============================================================================
_FULL_CORE_ROW = {"ts_et": "2026-08-03T09:46:02", "trigger_bar_et": "2026-08-03T09:40:00-04:00"}
_FULL_DECISION_ROW = {
    "core_tick_id": "TICK-1", "signal_written_at": "2026-08-03T09:46:05-04:00",
    "placement": {"plan_ts": "2026-08-03T09:46:05.200000-04:00",
                 "submit_ts": "2026-08-03T09:46:05.400000-04:00",
                 "broker": {"submitted_at": "2026-08-03T13:46:05.600000Z", "id": "oid-1"}},
}
_FULL_FILL = {"order_id": "oid-1", "ts_utc": "2026-08-03T13:46:05.700000Z",
             "date_et": "2026-08-03", "arm": "risky-3", "symbol": "SPY260803C00600000"}


def test_latency_row_from_fill_fully_instrumented_row_resolves_all_7_stages():
    row = flat.latency_row_from_fill(_FULL_FILL, _FULL_DECISION_ROW, _FULL_CORE_ROW)
    assert row is not None
    assert row["n_resolvable_stages"] == 7
    assert row["core_tick_id"] == "TICK-1"
    assert row["total_s"] is not None and row["total_s"] > 0


def test_latency_row_from_fill_pre_fix_shape_still_resolves_two_stages():
    """Even with NO decision_row at all (order_id genuinely unmatched -- caller's job, not
    this function's), a fill carrying only its own broker/fill data resolves nothing without
    a decision_row; WITH a pre-fix-shaped decision_row (no core_tick_id/plan_ts/submit_ts,
    but broker.submitted_at present, matching every real historical row) two stages
    resolve -- meets MIN_RESOLVABLE_STAGES, included."""
    pre_fix_decision = {"core_tick_id": None, "signal_written_at": None,
                        "placement": {"broker": {"submitted_at": "2026-07-31T16:19:03.838732Z"}}}
    row = flat.latency_row_from_fill(_FULL_FILL, pre_fix_decision, None)
    assert row is not None
    assert row["n_resolvable_stages"] == 2
    assert row["stages"]["core_verdict_ts"] is None


def test_latency_row_from_fill_excludes_when_below_min_resolvable():
    """No decision_row, no core_row -- only fill_ts resolves (1 stage) -> excluded (None),
    the caller counts it in n_excluded_missing_instrumentation, never fabricates a row."""
    row = flat.latency_row_from_fill(_FULL_FILL, None, None)
    assert row is None


# =============================================================================
# A3. summarize
# =============================================================================
def test_summarize_computes_median_p90_and_flags_small_n():
    rows = [{"total_s": v, **{k: None for k in flat.STAGE_ORDER}} for v in (1.0, 2.0, 3.0, 4.0, 5.0)]
    for r in rows:
        for a, b in zip(flat.STAGE_ORDER, flat.STAGE_ORDER[1:]):
            r[f"{a}_to_{b}_s"] = None
    s = flat.summarize(rows)
    assert s["n_scored"] == 5
    assert s["small_n"] is False  # exactly SMALL_N (5) is NOT below it
    assert s["hops"]["total_s"]["median_s"] == 3.0
    assert s["hops"]["total_s"]["max_s"] == 5.0


def test_summarize_empty_population_is_clean_not_a_crash():
    s = flat.summarize([])
    assert s["n_scored"] == 0
    assert s["small_n"] is True
    assert s["hops"] == {}


# =============================================================================
# A4. build_ledger -- end to end over synthetic on-disk fixtures
# =============================================================================
def test_build_ledger_end_to_end_synthetic_fixtures(tmp_path, monkeypatch):
    """Full disk-join: a synthetic fills-ledger.jsonl + risky-3/decisions.jsonl +
    core-decisions.jsonl, fully instrumented (post-fix shape) -> one scored row with all 7
    stages resolved, matching the exact join keys (order_id, core_tick_id)."""
    fills = tmp_path / "fills-ledger.jsonl"
    fills.write_text(json.dumps({
        "order_id": "oid-42", "arm": "risky-3", "symbol": "SPY260803C00600000",
        "side": "buy", "date_et": "2026-08-03", "ts_utc": "2026-08-03T13:46:05.700000Z",
        "ts_et": "2026-08-03T09:46:05.700000",
    }) + "\n", encoding="utf-8")

    core = tmp_path / "core-decisions.jsonl"
    core.write_text("\n".join(json.dumps(r) for r in (
        {"ts_et": "2026-08-03T09:46:02", "account": "bold", "core_tick_id": "TICK-1",
         "trigger_bar_et": "2026-08-03T09:40:00-04:00"},
        {"ts_et": "2026-08-03T09:46:01", "account": "safe", "core_tick_id": "TICK-1",
         "trigger_bar_et": "2026-08-03T09:40:00-04:00"},
    )) + "\n", encoding="utf-8")

    fleet_dir = tmp_path / "fleet"
    (fleet_dir / "risky-3").mkdir(parents=True)
    (fleet_dir / "risky-3" / "decisions.jsonl").write_text(json.dumps({
        "ts_et": "2026-08-03T09:46:05.100000-04:00", "arm_id": "risky-3",
        "core_tick_id": "TICK-1", "signal_written_at": "2026-08-03T09:46:05-04:00",
        "placement": {"placed": True, "plan_ts": "2026-08-03T09:46:05.200000-04:00",
                     "submit_ts": "2026-08-03T09:46:05.400000-04:00",
                     "broker": {"id": "oid-42", "submitted_at": "2026-08-03T13:46:05.600000Z"}},
    }) + "\n", encoding="utf-8")

    monkeypatch.setattr(flat, "FILLS_LEDGER", fills)
    monkeypatch.setattr(flat, "CORE_DECISIONS", core)
    monkeypatch.setattr(flat, "FLEET_DIR", fleet_dir)
    out = tmp_path / "latency.json"

    ledger = flat.build_ledger(date_et="2026-08-03", out_path=out)

    assert ledger["n_entry_fills"] == 1
    assert ledger["n_excluded_missing_instrumentation"] == 0
    assert ledger["n_excluded_no_decision_row"] == 0
    assert len(ledger["rows"]) == 1
    row = ledger["rows"][0]
    assert row["n_resolvable_stages"] == 7, "SAFE row (earlier) must win the core_tick_id join"
    assert row["stages"]["core_verdict_ts"] == "2026-08-03T09:46:01"  # the SAFE row, not bold
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8"))["date_et"] == "2026-08-03"


def test_build_ledger_out_of_scope_arm_is_ignored(tmp_path, monkeypatch):
    """safe-2/bold-2 (mcp_heartbeat) are explicitly out of scope (module docstring) -- a
    fill tagged to one must never be picked up even if it happens to sit in FLEET_REST_ARMS'
    directory space by coincidence of a stray file."""
    fills = tmp_path / "fills-ledger.jsonl"
    fills.write_text(json.dumps({"order_id": "oid-99", "arm": "safe-2", "symbol": "X",
                                 "side": "buy", "date_et": "2026-08-03",
                                 "ts_utc": "2026-08-03T13:00:00Z"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(flat, "FILLS_LEDGER", fills)
    monkeypatch.setattr(flat, "CORE_DECISIONS", tmp_path / "no-core.jsonl")
    monkeypatch.setattr(flat, "FLEET_DIR", tmp_path / "no-fleet-dir")
    ledger = flat.build_ledger(date_et="2026-08-03", out_path=tmp_path / "latency.json")
    assert ledger["n_entry_fills"] == 0  # arm not in FLEET_REST_ARMS -> filtered before join


# =============================================================================
# B1. build_shared_signal.build() emits core_tick_id
# =============================================================================
def test_build_emits_core_tick_id_on_the_signal(tmp_path, monkeypatch):
    core = tmp_path / "core-decisions.jsonl"
    base = {"spy": 600.0, "ribbon": "BEAR", "spread_cents": 30, "vix": 15.0,
           "htf_15m": "BEAR", "side": "C", "bear_score": 4, "bull_score": 2, "triggers": []}
    safe = {**base, "ts_et": "2026-08-03T11:00:00", "account": "safe", "core_tick_id": "T-A",
           "verdict": "HOLD", "action": "HOLD", "setup": None}
    bold = {**base, "ts_et": "2026-08-03T11:00:01", "account": "bold", "core_tick_id": "T-A",
           "verdict": "HOLD", "action": "HOLD", "setup": None}
    core.write_text(json.dumps(safe) + "\n" + json.dumps(bold) + "\n", encoding="utf-8")
    monkeypatch.setattr(bss, "CORE_DECISIONS", core)
    monkeypatch.setattr(bss, "TICK_MARKER", tmp_path / "no-marker.json")  # fail-open fallback
    monkeypatch.setattr(bss, "OUT", tmp_path / "shared-signal.json")
    monkeypatch.setattr(bss, "BEACON", tmp_path / "no-beacon.json")

    now = datetime(2026, 8, 3, 11, 0, 2, tzinfo=bss.ET)
    sig = bss.build(now=now, scoring_peak=True, emit_strategies=False, run_vwap=False)
    # no marker -> fallback path -> _core_tick_id resolves None (pre-fix-equivalent fallback);
    # this asserts the KEY exists and is wired, not a specific value (see the race-fix test
    # file for the marker-present case where it resolves to the real tick id).
    assert "core_tick_id" in sig


# =============================================================================
# B2. fleet_live._place_live emits submit_ts
# =============================================================================
class _FakeBroker:
    def __init__(self, mid):
        self.mid = mid

    def get_option_mid(self, creds, symbol):
        return self.mid

    def marketable_limit_price(self, creds, symbol, side="buy", buffer=0.03):
        return round(self.mid + buffer, 2)

    def open_buy_orders(self, creds, symbol):
        return []

    def cancel_order(self, creds, order_id, *, live):
        return {}

    def request(self, creds, endpoint, method="GET", data=None, timeout=15):
        # DE-FLAKED 2026-08-03 (EOD process audit): was a hardcoded "2026-08-03T15:00:00.5Z",
        # but _place_live stamps submit_ts from the REAL wall clock, so the ordering
        # assertion below only held when the suite ran before 11:00 ET (nightly 00:30 ET
        # runs passed; any afternoon run failed). The broker's server-side stamp is now
        # derived from real now + 500ms, making the our-clock-precedes-broker-clock
        # assertion structural instead of time-of-day-dependent.
        broker_now = datetime.now(timezone.utc) + timedelta(milliseconds=500)
        return {"id": "fake-order", "status": "accepted",
               "submitted_at": broker_now.isoformat().replace("+00:00", "Z")}


def test_place_live_returns_submit_ts_before_the_broker_post(monkeypatch, tmp_path):
    fake = _FakeBroker(1.00)
    monkeypatch.setattr(fl.fb, "get_option_mid", fake.get_option_mid)
    monkeypatch.setattr(fl.fb, "marketable_limit_price", fake.marketable_limit_price)
    monkeypatch.setattr(fl.fb, "open_buy_orders", fake.open_buy_orders)
    monkeypatch.setattr(fl.fb, "cancel_order", fake.cancel_order)
    monkeypatch.setattr(fl.fb, "_request", fake.request)
    # ORDER-LEVEL IDEMPOTENCY GUARD (2026-08-02): this file is about the submit_ts latency
    # field, not the guard -- stub its two broker primitives to "confirmed clear" and
    # sandbox the claim file (see test_entry_idempotency_guard.py for the guard's own
    # dedicated coverage).
    monkeypatch.setattr(fl.fb, "open_buy_orders_checked", lambda creds, symbol: ([], True))
    monkeypatch.setattr(fl.fb, "symbol_position_qty_checked", lambda creds, symbol: (0, True))
    monkeypatch.setattr(fl, "FLEET_DIR", tmp_path)
    monkeypatch.setattr(fl.ea, "FLEET_DIR", tmp_path)
    decision = fx.ArmDecision("risky-3", "ENTER_BEAR", "P", "BEARISH_REJECTION_RIDE_THE_RIBBON",
                              745, 5, 1.00, "BASE", "ALLOW", "test", trigger_level=None)
    now = datetime(2026, 8, 3, 11, 0, 0, tzinfo=ET)
    res = fl._place_live({}, {"id": "risky-3"}, decision, {}, {}, {}, now)
    assert res["placed"] is True
    assert "submit_ts" in res and res["submit_ts"] is not None
    # our clock (submit_ts, captured right before the POST) must precede the broker's own
    # submitted_at (captured server-side, after the request arrives) -- never the reverse.
    submit_dt = datetime.fromisoformat(res["submit_ts"])
    broker_dt = datetime.fromisoformat(res["broker"]["submitted_at"].replace("Z", "+00:00"))
    assert submit_dt <= broker_dt


# =============================================================================
# B3. fleet_live.run()'s row carries core_tick_id/signal_written_at (cheap no-creds path --
# the row dict is constructed BEFORE the no-creds bail, so this exercises the real code
# without needing the full account/exit-management/decide_arm machinery).
# =============================================================================
def test_run_row_carries_core_tick_id_and_signal_written_at(tmp_path, monkeypatch):
    accounts = {"arms": [{"id": "risky-3", "status": "active", "execution": "fleet_rest"}]}
    accounts_path = tmp_path / "accounts.json"
    accounts_path.write_text(json.dumps(accounts), encoding="utf-8")
    signal_path = tmp_path / "shared-signal.json"
    signal_path.write_text(json.dumps({
        "core_tick_id": "TICK-XYZ", "written_at": "2026-08-03T11:00:01-04:00",
        "written_at_iso": None,
    }), encoding="utf-8")
    # written_at must be ISO-parseable by _signal_age_sec for _load_signal to accept it as
    # fresh (not stale) -- use "now" itself for the fixture's own clock below.
    now = datetime(2026, 8, 3, 11, 0, 2, tzinfo=ET)
    signal_path.write_text(json.dumps({
        "core_tick_id": "TICK-XYZ", "written_at": now.isoformat(),
    }), encoding="utf-8")

    monkeypatch.setattr(fl, "ACCOUNTS_PATH", accounts_path)
    monkeypatch.setattr(fl, "FLEET_DIR", tmp_path)
    monkeypatch.setattr(fl.fb, "load_creds", lambda: {})  # no creds -> early bail, AFTER row built
    monkeypatch.setattr(fl, "_now_et", lambda: now)
    monkeypatch.setattr(fx, "validate_accounts_exit_patches", lambda accounts: None)

    results = fl.run(signal_path, master_live=False)

    assert len(results) == 1
    row = results[0]
    assert row["action"] == "ERROR" and row["reason"] == "no creds in secrets.json"
    assert row["core_tick_id"] == "TICK-XYZ"
    assert row["signal_written_at"] == now.isoformat()
