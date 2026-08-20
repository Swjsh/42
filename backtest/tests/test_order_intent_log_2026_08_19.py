"""Guards for the ORDER-INTENT LEDGER (2026-08-19) -- the WHY behind every order.

WHAT THIS PROTECTS
  order_intent_log.record_submit runs on the LIVE ORDER PATH: core entries
  (heartbeat_core._execute), fleet entries (fleet_live._place_live), every engine exit
  (exit_actuator.manage_tick), the EOD force-flatten (fleet_broker.close_all_spy_options),
  J-called intents (j_intent_executor.place_entry) and the fast path. It exists to record
  telemetry. It must therefore be incapable of costing a trade, and incapable of changing one.

FOUR CONTRACTS, one class each:

  1. TestWriterNeverRaises      -- record_submit is TOTAL. Full disk, unwritable path,
                                   unserialisable input, NaN, circular refs, a broken clock,
                                   a broken json module, no arguments at all: all return None.
  2. TestFillJoinsToItsIntent   -- a fill leg joins to its intent row and inherits the WHY,
                                   tagged provenance "logged".
  3. TestMissingIntentIsUnknown -- a fill with NO intent row yields an explicit "unknown"
                                   tag plus a human-readable note. NEVER a silent null.
  4. TestOrderPathUnchanged     -- the ORDER ITSELF is untouched. The payload posted to the
                                   broker is byte-identical whether telemetry is absent,
                                   present, or actively sabotaged.

RED-PROOF (how each was shown to actually fail without the fix) -- see the per-class
docstrings. Every one was run against a deliberately broken variant before being accepted;
none of them pass vacuously.
"""
from __future__ import annotations

import builtins
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
OIL_PATH = REPO / "setup" / "scripts" / "order_intent_log.py"
HC_PATH = REPO / "setup" / "scripts" / "heartbeat_core.py"
FLEET_DIR = REPO / "automation" / "state" / "fleet"


def _load(name: str, path: Path):
    """Load a production module by explicit path (this suite's standing convention)."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def oil():
    return _load("_oil_probe", OIL_PATH)


@pytest.fixture()
def ledger(tmp_path):
    return tmp_path / "order-intents.jsonl"


def _rows(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


# =====================================================================================
# 1. THE WRITER NEVER RAISES
# =====================================================================================

class TestWriterNeverRaises:
    """record_submit must be TOTAL. A logging failure must never cost a trade.

    RED-PROOF: each case below was first run against a variant of record_submit with the
    outer `except Exception` removed. Every case raised -- OSError(ENOSPC) for the full disk,
    OSError/FileNotFoundError for the bad path, RecursionError for the circular reference,
    ValueError("Out of range float values are not JSON compliant") for NaN under
    allow_nan=False, TypeError for the no-argument call under a positional signature. With
    the guard in place all of them return None. The tests are therefore not vacuous.
    """

    def test_unwritable_path_returns_none(self, oil):
        # A path whose parent cannot be created (a file used as a directory).
        assert oil.record_submit(path="/proc/definitely/not/a/dir/x.jsonl", arm="safe-2") is None

    def test_full_disk_returns_none(self, oil, ledger, monkeypatch):
        """ENOSPC mid-write is the realistic disk failure. It must be swallowed."""
        real_open = Path.open

        def enospc(self, *a, **k):
            if self == ledger:
                raise OSError(28, "No space left on device")
            return real_open(self, *a, **k)

        monkeypatch.setattr(Path, "open", enospc)
        assert oil.record_submit(path=ledger, arm="safe-2", symbol="SPY", side="buy") is None

    def test_unserialisable_input_returns_none_and_still_writes_the_row(self, oil, ledger):
        """An object that cannot even be repr'd must not take the whole record down."""
        class Hostile:
            def __repr__(self):
                raise RuntimeError("no repr for you")

            def __str__(self):
                raise RuntimeError("no str either")

        assert oil.record_submit(path=ledger, arm="safe-2", symbol="SPY", side="sell",
                                 qty=3, leg_role="tp1", intent="EXIT", reason="r",
                                 source="t", hostile=Hostile()) is None
        rows = _rows(ledger)
        assert len(rows) == 1, "the row must still land -- a bad extra field is not fatal"
        assert rows[0]["arm"] == "safe-2"

    def test_circular_reference_returns_none(self, oil, ledger):
        d = {}
        d["self"] = d
        assert oil.record_submit(path=ledger, arm="safe-2", circular=d) is None

    def test_nan_and_infinity_never_produce_invalid_json(self, oil, ledger):
        """json.dumps emits bare NaN/Infinity by default -- INVALID JSON that would make the
        row unreadable to every consumer. They must be nulled, not emitted."""
        assert oil.record_submit(path=ledger, arm="safe-2", symbol="SPY", side="buy", qty=1,
                                 leg_role="core", intent="ENTRY", reason="r", source="t",
                                 spy_at_submit=float("nan"),
                                 nbbo={"bid": float("inf"), "ask": 1.0}) is None
        raw = ledger.read_text(encoding="utf-8").strip()
        assert "NaN" not in raw and "Infinity" not in raw
        row = json.loads(raw)                       # would ValueError on invalid JSON
        assert row["spy_at_submit"] is None
        assert row["nbbo_bid"] is None
        assert row["nbbo_ask"] == 1.0

    def test_no_arguments_at_all_returns_none(self, oil):
        """The signature is **fields precisely so a WRONG CALL cannot TypeError into an
        order submission. A positional signature would raise here."""
        assert oil.record_submit() is None

    def test_broken_clock_returns_none_and_still_writes(self, oil, ledger, monkeypatch):
        """et_clock is imported inside _now_parts. If it explodes, we lose the timestamps,
        not the row and certainly not the trade."""
        real_import = builtins.__import__

        def boom(name, *a, **k):
            if name == "et_clock":
                raise RuntimeError("clock module exploded")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", boom)
        assert oil.record_submit(path=ledger, arm="safe-2", symbol="SPY", side="buy", qty=1,
                                 leg_role="core", intent="ENTRY", reason="r",
                                 source="t") is None
        rows = _rows(ledger)
        assert len(rows) == 1
        assert rows[0]["ts_et"] is None, "a dead clock yields a null stamp, not a fake one"

    def test_broken_json_module_returns_none(self, oil, ledger, monkeypatch):
        monkeypatch.setattr(oil.json, "dumps",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("json down")))
        assert oil.record_submit(path=ledger, arm="safe-2") is None

    def test_missing_required_fields_are_flagged_not_dropped(self, oil, ledger):
        """A partial record beats no record -- but the gap must be VISIBLE, never a silent
        null (the exact failure mode this whole build exists to end)."""
        oil.record_submit(path=ledger, arm="safe-2", symbol="SPY")
        row = _rows(ledger)[0]
        assert "_incomplete" in row
        for missing in ("side", "qty", "leg_role", "intent", "reason", "source"):
            assert missing in row["_incomplete"]

    def test_absent_nbbo_says_so_rather_than_pretending(self, oil, ledger):
        oil.record_submit(path=ledger, arm="safe-2", symbol="SPY", side="buy", qty=1,
                          leg_role="core", intent="ENTRY", reason="r", source="t")
        row = _rows(ledger)[0]
        assert row["nbbo_bid"] is None
        assert row["nbbo_source"] == "not_in_hand_at_submit"

    def test_caller_dict_is_never_mutated(self, oil, ledger):
        """The writer takes a copy. A telemetry call must not perturb caller state."""
        nbbo = {"bid": 0.4, "ask": 0.45}
        before = dict(nbbo)
        oil.record_submit(path=ledger, arm="safe-2", symbol="SPY", side="buy", qty=1,
                          leg_role="core", intent="ENTRY", reason="r", source="t", nbbo=nbbo)
        assert nbbo == before

    def test_pytest_never_writes_the_production_ledger(self, oil, monkeypatch):
        """THE SEAM. This module is called from inside the PRODUCTION submit functions, and
        dozens of pre-existing tests drive those functions with a stubbed broker. On the first
        full suite run that put 53 fabricated rows (arms "safe-3-test2",
        "pytest-killswitch-exits") into the real order-intents.jsonl. Nothing reads it on the
        decision path so no trade was affected -- but this ledger IS the forensic record, and
        a forensic record with invented rows is worse than none.

        RED-PROOF: with the `PYTEST_CURRENT_TEST` branch removed from _intents_path, this
        asserted-equal check fails immediately -- the resolved path comes back as the real
        automation/state/order-intents.jsonl.
        """
        monkeypatch.delenv(oil._PATH_ENV, raising=False)
        resolved = oil._intents_path()
        assert resolved != oil.INTENTS_PATH, (
            f"under pytest the writer resolved to the PRODUCTION ledger {resolved} -- "
            "a test run must never be able to fabricate rows in the real book")
        assert "automation" not in str(resolved).replace("\\", "/"), (
            "test output must not land anywhere under automation/state")

    def test_explicit_path_and_env_still_beat_the_test_divert(self, oil, tmp_path, monkeypatch):
        """The seam must not make the writer untestable: a caller naming its own file wins."""
        explicit = tmp_path / "explicit.jsonl"
        assert oil._intents_path(explicit) == explicit
        env_path = tmp_path / "env.jsonl"
        monkeypatch.setenv(oil._PATH_ENV, str(env_path))
        assert oil._intents_path() == env_path

    def test_append_only_never_truncates(self, oil, ledger):
        for i in range(5):
            oil.record_submit(path=ledger, arm="safe-2", symbol=f"S{i}", side="buy", qty=1,
                              leg_role="core", intent="ENTRY", reason="r", source="t")
        assert len(_rows(ledger)) == 5


# =====================================================================================
# 2. A FILL JOINS TO ITS INTENT
# =====================================================================================

def _fill(order_id: str, **kw) -> dict:
    base = {"order_id": order_id, "arm": "safe-2", "symbol": "SPY260819C00645000",
            "side": "sell", "qty": 2.0, "price": 0.55, "date_et": "2026-08-19",
            "ts_et": "2026-08-19T14:05:00", "is_crypto": False, "is_option": True}
    base.update(kw)
    return base


class TestFillJoinsToItsIntent:
    """A fill leg must inherit its WHY from the intent row written at submit.

    RED-PROOF: run against a joiner that ignored the intent index (returned the fill
    unchanged) -- every assertion below failed: exit_reason was absent, leg_role was absent,
    and provenance was missing entirely.
    """

    def test_exit_leg_inherits_reason_role_and_quote(self, oil, ledger):
        oil.record_submit(path=ledger, arm="safe-2", symbol="SPY260819C00645000", side="sell",
                          qty=2, leg_role=oil.ROLE_TP1, intent="EXIT",
                          reason="SELL_PARTIAL:tp1 tp1 @ +100%",
                          source="exit_actuator.manage_tick",
                          broker_response={"id": "ord-abc"},
                          nbbo={"bid": 0.54, "ask": 0.58, "source": "hilo"},
                          decision_tick_id="2026-08-19T14:05:00",
                          entry_link="entry-1")
        intents = oil.load_intents(ledger)
        assert "ord-abc" in intents

        out = oil.enrich_fill(_fill("ord-abc"), intents)
        assert out["intent_matched"] is True
        assert out["exit_reason"] == "SELL_PARTIAL:tp1 tp1 @ +100%"
        assert out["leg_role"] == oil.ROLE_TP1
        assert out["nbbo_bid"] == 0.54
        assert out["nbbo_ask"] == 0.58
        assert out["entry_link"] == "entry-1"
        assert out["decision_tick_id"] == "2026-08-19T14:05:00"
        for field in ("exit_reason", "leg_role", "nbbo_bid", "nbbo_ask",
                      "entry_link", "decision_tick_id"):
            assert out["provenance"][field] == oil.PROV_LOGGED, field
            assert out["provenance_note"][field], f"{field} must name its source"

    def test_entry_leg_reason_lands_on_entry_reason_not_exit_reason(self, oil, ledger):
        """An ENTRY has no exit reason. Putting one there would be a lie the analytics
        would then average over."""
        oil.record_submit(path=ledger, arm="safe-2", symbol="SPY260819C00645000", side="buy",
                          qty=3, leg_role=oil.ROLE_CORE, intent="ENTRY",
                          reason="ENTER_BEAR BEARISH_REJECTION", source="heartbeat_core._execute",
                          broker_response={"id": "ord-entry"})
        out = oil.enrich_fill(_fill("ord-entry", side="buy"), oil.load_intents(ledger))
        assert out["entry_reason"] == "ENTER_BEAR BEARISH_REJECTION"
        assert out["exit_reason"] is None
        assert out["provenance"]["exit_reason"] == oil.PROV_UNKNOWN

    def test_ten_contracts_three_legs_each_keeps_its_own_role_and_reason(self, oil, ledger):
        """J's literal question: with ten contracts, what did each leg do and why.
        Entry 10 -> TP1 8 -> runner 2, each with its own order_id, role and reason."""
        legs = [
            ("ord-e", "buy", 10, oil.ROLE_CORE, "ENTRY", "ENTER_BULL BULLISH_RECLAIM"),
            ("ord-t", "sell", 8, oil.ROLE_TP1, "EXIT", "SELL_PARTIAL:tp1 tp1 @ +100%"),
            ("ord-r", "sell", 2, oil.ROLE_RUNNER, "EXIT", "SELL_ALL:runner_target +250%"),
        ]
        for oid, side, qty, role, intent, reason in legs:
            oil.record_submit(path=ledger, arm="safe-2", symbol="SPY260819C00645000",
                              side=side, qty=qty, leg_role=role, intent=intent,
                              reason=reason, source="t", broker_response={"id": oid})
        intents = oil.load_intents(ledger)
        got = {oid: oil.enrich_fill(_fill(oid, side=side, qty=qty), intents)
               for oid, side, qty, *_ in legs}
        assert got["ord-e"]["leg_role"] == oil.ROLE_CORE
        assert got["ord-t"]["leg_role"] == oil.ROLE_TP1
        assert got["ord-t"]["exit_reason"] == "SELL_PARTIAL:tp1 tp1 @ +100%"
        assert got["ord-r"]["leg_role"] == oil.ROLE_RUNNER
        assert got["ord-r"]["exit_reason"] == "SELL_ALL:runner_target +250%"

    def test_recovery_rate_counts_logged_fields(self, oil, ledger):
        oil.record_submit(path=ledger, arm="safe-2", symbol="S", side="sell", qty=1,
                          leg_role=oil.ROLE_TP1, intent="EXIT", reason="why",
                          source="t", broker_response={"id": "a"})
        intents = oil.load_intents(ledger)
        enriched = [oil.enrich_fill(_fill("a"), intents), oil.enrich_fill(_fill("missing"), intents)]
        rr = oil.recovery_rate(enriched)
        assert rr["total_legs"] == 2
        assert rr["fields"]["exit_reason"]["logged"] == 1
        assert rr["fields"]["exit_reason"]["unknown"] == 1
        assert rr["fields"]["exit_reason"]["pct_recovered"] == 50.0


# =====================================================================================
# 3. A MISSING INTENT IS "unknown", NOT A SILENT NULL
# =====================================================================================

class TestMissingIntentIsUnknown:
    """The five force-flatten exits must come out UNKNOWN -- explicitly, with a reason.

    This is the whole ethic of the build: an unrecoverable field is labelled unrecoverable.
    A bare null is indistinguishable from "the value was legitimately zero/none", and that
    ambiguity is what let a -$440 exit sit unexplained.

    RED-PROOF: run against a joiner that returned the fill untouched when no intent existed
    -- `"provenance" in out` was False and the KeyError/absent-tag assertions below all
    failed. Also run against a joiner that emitted the fields as plain nulls with no
    provenance dict: the tag assertions failed while the value assertions passed, which is
    exactly the silent-null failure this class is here to catch.
    """

    def test_every_field_is_tagged_unknown_with_a_note(self, oil, ledger):
        out = oil.enrich_fill(_fill("never-logged"), oil.load_intents(ledger))
        assert out["intent_matched"] is False
        for field in oil.ENRICHED_FIELDS:
            assert field in out, f"{field} must be PRESENT (as null), not absent"
            assert out[field] is None
            assert out["provenance"][field] == oil.PROV_UNKNOWN, field
            assert out["provenance_note"][field], f"{field} must explain WHY it is unknown"

    def test_unknown_is_distinguishable_from_a_logged_null(self, oil, ledger):
        """An intent row that EXISTS but carries no nbbo is a different fact from no intent
        row at all. Both are 'unknown', and their notes must say which."""
        oil.record_submit(path=ledger, arm="safe-2", symbol="S", side="sell", qty=1,
                          leg_role=oil.ROLE_FLATTEN, intent="EXIT", reason="EOD flatten",
                          source="fleet_broker.close_all_spy_options",
                          broker_response={"id": "flat-1"},
                          nbbo={"bid": None, "ask": None, "source": "not_read_on_flatten"})
        intents = oil.load_intents(ledger)
        has_row = oil.enrich_fill(_fill("flat-1"), intents)
        no_row = oil.enrich_fill(_fill("nothing"), intents)

        assert has_row["provenance"]["nbbo_bid"] == oil.PROV_UNKNOWN
        assert no_row["provenance"]["nbbo_bid"] == oil.PROV_UNKNOWN
        assert has_row["provenance_note"]["nbbo_bid"] != no_row["provenance_note"]["nbbo_bid"]
        # ...but the flatten's REASON is recovered, which is the entire point of wiring it.
        assert has_row["exit_reason"] == "EOD flatten"
        assert has_row["provenance"]["exit_reason"] == oil.PROV_LOGGED

    def test_provenance_vocabulary_is_closed(self, oil, ledger):
        """Only three tags are legal. A fourth would let a guess masquerade as a fact."""
        legal = {oil.PROV_LOGGED, oil.PROV_DERIVED, oil.PROV_UNKNOWN}
        out = oil.enrich_fill(_fill("x"), oil.load_intents(ledger))
        assert set(out["provenance"].values()) <= legal


# =====================================================================================
# 4. THE ORDER PATH IS UNCHANGED
# =====================================================================================

def _sabotage(monkeypatch, module):
    """Replace record_submit with the worst-behaved telemetry imaginable: it mutates every
    dict handed to it and then raises. If the order path survives THIS, it survives anything.
    Returns the list of calls it saw."""
    seen: list = []

    def hostile(**fields):
        seen.append(fields)
        for v in fields.values():
            if isinstance(v, dict):
                v["INJECTED"] = "corrupted"
            elif isinstance(v, list):
                v.append("corrupted")
        raise RuntimeError("telemetry exploded")

    monkeypatch.setattr(module._oil, "record_submit", hostile, raising=False)
    return seen


class TestOrderPathUnchanged:
    """PROOF that adding this telemetry changed no order.

    The method is a genuine before/after equivalence computed AT TEST TIME, not a frozen
    literal that could drift: each placement is driven twice against the same inputs -- once
    with record_submit stubbed to a no-op (the "before" world, telemetry absent) and once
    with it live (and once sabotaged) -- and the payload dict actually posted to the broker
    is compared byte-for-byte via json.dumps(sort_keys=True).

    RED-PROOF: run against a deliberately broken variant of _place_simple_entry that let the
    telemetry block touch the order (`order["qty"] = str(qty + 1)` inserted next to the
    record_submit call). The byte-comparison failed immediately with a qty mismatch. A second
    RED run removed the try/except around the call site and had record_submit raise: the
    placement propagated RuntimeError instead of returning the broker response, failing
    test_a_raising_telemetry_never_breaks_the_placement.
    """

    # ---- core entry: heartbeat_core._place_simple_entry -----------------------------
    @staticmethod
    def _drive_core(monkeypatch, hc, sabotage: bool):
        posts: list = []

        def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
            posts.append({"endpoint": endpoint, "method": method,
                          "data": json.loads(json.dumps(data)) if data else data})
            return {"id": "ord-1", "status": "accepted"}

        import fleet_broker as fb
        monkeypatch.setattr(fb, "_request", fake_request)
        if sabotage:
            _sabotage(monkeypatch, hc)
        else:
            monkeypatch.setattr(hc._oil, "record_submit", lambda **k: None, raising=False)
        res = hc._place_simple_entry({"key": "k", "secret": "s",
                                      "base_url": "https://paper-api.alpaca.markets"},
                                     symbol="SPY260819C00645000", qty=3, limit_price=1.23)
        return posts, res

    def test_core_entry_payload_is_byte_identical(self, monkeypatch):
        sys.path.insert(0, str(FLEET_DIR))
        sys.path.insert(0, str(REPO / "setup" / "scripts"))
        hc = _load("_hc_orderpath_probe", HC_PATH)

        with monkeypatch.context() as m:
            before, res_before = self._drive_core(m, hc, sabotage=False)
        with monkeypatch.context() as m:
            after, res_after = self._drive_core(m, hc, sabotage=True)

        assert before, "the probe must actually have posted an order"
        assert json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True), (
            "the broker payload changed when telemetry was introduced -- "
            "this build is only allowed to ADD a write, never to touch the order")
        assert before[0]["data"] == {
            "symbol": "SPY260819C00645000", "qty": "3", "side": "buy",
            "type": "limit", "limit_price": "1.23", "time_in_force": "day"}
        assert res_before.get("id") == res_after.get("id") == "ord-1"

    def test_a_raising_telemetry_never_breaks_the_placement(self, monkeypatch):
        """The sabotaging stub RAISES. The placement must still return the broker response."""
        sys.path.insert(0, str(FLEET_DIR))
        hc = _load("_hc_orderpath_probe2", HC_PATH)
        with monkeypatch.context() as m:
            posts, res = self._drive_core(m, hc, sabotage=True)
        assert res.get("id") == "ord-1"
        assert res.get("_simple_first") is True
        assert len(posts) == 1, "exactly one POST -- telemetry must not re-submit anything"

    # ---- force-flatten: fleet_broker.close_all_spy_options ---------------------------
    @staticmethod
    def _drive_flatten(monkeypatch, fb, sabotage: bool, **call_kw):
        posts: list = []
        positions = [{"symbol": "SPY260819C00645000", "qty": "5", "asset_class": "option",
                      "avg_entry_price": "1.00", "unrealized_pl": "-440"}]
        state = {"n": 0}

        def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
            if endpoint == "positions":
                state["n"] += 1
                return positions if state["n"] == 1 else []
            posts.append({"endpoint": endpoint, "method": method,
                          "data": json.loads(json.dumps(data)) if data else data})
            return {"id": "flat-1", "status": "accepted"}

        monkeypatch.setattr(fb, "_request", fake_request)
        if sabotage:
            _sabotage(monkeypatch, fb)
        else:
            monkeypatch.setattr(fb._oil, "record_submit", lambda **k: None, raising=False)
        res = fb.close_all_spy_options({"key": "k", "secret": "s", "base_url": "x"},
                                       live=True, **call_kw)
        return posts, res

    def test_flatten_payload_and_return_shape_are_byte_identical(self, monkeypatch):
        sys.path.insert(0, str(FLEET_DIR))
        fb = _load("_fb_orderpath_probe", FLEET_DIR / "fleet_broker.py")

        with monkeypatch.context() as m:
            before, res_before = self._drive_flatten(m, fb, sabotage=False)
        with monkeypatch.context() as m:
            after, res_after = self._drive_flatten(
                m, fb, sabotage=True, arm="risky-1", reason="EOD sweep")

        assert json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True), (
            "adding arm/reason labels must not change a single byte of the sell payload")
        assert before[0]["data"] == {"symbol": "SPY260819C00645000", "qty": "5",
                                     "side": "sell", "type": "market", "time_in_force": "day"}
        # The return contract every caller reads is unchanged.
        assert res_before == res_after
        assert set(res_before) == {"closed", "errors", "remaining"}
        assert res_before["closed"] == ["SPY260819C00645000"]

    def test_flatten_records_the_intent_the_old_path_threw_away(self, monkeypatch, tmp_path):
        """The regression that motivated all of this: this function used to keep only the
        SYMBOL and discard the broker response -- order_id included -- so its exits were
        unexplainable forever. It must now write a row carrying the order_id and a reason."""
        sys.path.insert(0, str(FLEET_DIR))
        fb = _load("_fb_intent_probe", FLEET_DIR / "fleet_broker.py")
        led = tmp_path / "oi.jsonl"
        monkeypatch.setenv("GAMMA_ORDER_INTENTS_PATH", str(led))
        with monkeypatch.context() as m:
            self._drive_flatten(m, fb, sabotage=False, arm="risky-1",
                                reason="FLEET_EOD_FLATTEN sweep")
            # re-run with the REAL writer (the no-op stub above is scoped to that context)
        with monkeypatch.context() as m:
            posts, _ = self._drive_flatten_real(m, fb, arm="risky-1",
                                                reason="FLEET_EOD_FLATTEN sweep")
        rows = _rows(led)
        assert len(rows) == 1, "the flatten must write exactly one intent row per sold symbol"
        row = rows[0]
        assert row["order_id"] == "flat-1"
        assert row["arm"] == "risky-1"
        assert row["leg_role"] == "flatten"
        assert row["intent"] == "EXIT"
        assert "FLEET_EOD_FLATTEN" in row["reason"]
        assert row["submit_status"] == "ACCEPTED"

    @staticmethod
    def _drive_flatten_real(monkeypatch, fb, **call_kw):
        posts: list = []
        positions = [{"symbol": "SPY260819C00645000", "qty": "5", "asset_class": "option"}]
        state = {"n": 0}

        def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
            if endpoint == "positions":
                state["n"] += 1
                return positions if state["n"] == 1 else []
            posts.append({"endpoint": endpoint, "data": data})
            return {"id": "flat-1", "status": "accepted"}

        monkeypatch.setattr(fb, "_request", fake_request)
        return posts, fb.close_all_spy_options({"key": "k", "secret": "s", "base_url": "x"},
                                               live=True, **call_kw)

    def test_flatten_defaults_keep_every_existing_caller_byte_identical(self, monkeypatch):
        """arm/reason default to None. A caller that never passes them behaves exactly as
        before -- the additive-signature promise, asserted rather than assumed."""
        sys.path.insert(0, str(FLEET_DIR))
        fb = _load("_fb_default_probe", FLEET_DIR / "fleet_broker.py")
        with monkeypatch.context() as m:
            no_labels, res_no = self._drive_flatten(m, fb, sabotage=False)
        with monkeypatch.context() as m:
            labels, res_yes = self._drive_flatten(m, fb, sabotage=False,
                                                  arm="safe-2", reason="whatever")
        assert json.dumps(no_labels, sort_keys=True) == json.dumps(labels, sort_keys=True)
        assert res_no == res_yes

    # ---- exits: exit_actuator.manage_tick -------------------------------------------
    def test_exit_sell_arguments_are_byte_identical(self, monkeypatch, tmp_path):
        sys.path.insert(0, str(FLEET_DIR))
        ea = _load("_ea_orderpath_probe", FLEET_DIR / "exit_actuator.py")
        em = _load("_em_orderpath_probe", FLEET_DIR / "exit_manager.py")

        def run(sabotage: bool) -> list:
            sells: list = []

            class Broker:
                @staticmethod
                def get_position_qty(creds, symbol):
                    return 3

                @staticmethod
                def get_option_quote_hilo(creds, symbol):
                    return (0.10, 0.09)          # (ask, bid) -- deep under the stop

                @staticmethod
                def market_sell(creds, *, symbol, qty, live):
                    sells.append({"symbol": symbol, "qty": qty, "live": live})
                    return {"id": f"sell-{len(sells)}", "status": "accepted"}

                @staticmethod
                def open_sell_orders(creds, symbol):
                    return []

            with monkeypatch.context() as m:
                m.setattr(ea, "FLEET_DIR", tmp_path / ("sab" if sabotage else "clean"))
                (tmp_path / ("sab" if sabotage else "clean")).mkdir(exist_ok=True)
                if sabotage:
                    _sabotage(m, ea)
                else:
                    m.setattr(ea._oil, "record_submit", lambda **k: None, raising=False)
                st = em.ExitState(symbol="SPY260819C00645000", side="C", entry_premium=1.00,
                                  total_qty=3, tp1_qty=2, runner_qty=1,
                                  premium_stop_pct=-0.50, tp1_premium_pct=1.0,
                                  profit_lock_mode="fixed", runner_stop_premium=0.50)
                ea.save_states("armX", {"SPY260819C00645000": st})
                ea.manage_tick("armX", {"key": "k"}, live=True, broker=Broker())
            return sells

        clean = run(sabotage=False)
        sabotaged = run(sabotage=True)
        assert clean, "the probe must actually have sold something"
        assert json.dumps(clean, sort_keys=True) == json.dumps(sabotaged, sort_keys=True), (
            "the sell arguments changed when telemetry was introduced")

    def test_exit_records_reason_role_and_the_free_quote(self, monkeypatch, tmp_path):
        """The exit leg must carry the exit manager's OWN words, the tranche, and the bid/ask
        that were already in hand -- with no extra broker call."""
        sys.path.insert(0, str(FLEET_DIR))
        ea = _load("_ea_intent_probe", FLEET_DIR / "exit_actuator.py")
        em = _load("_em_intent_probe", FLEET_DIR / "exit_manager.py")
        led = tmp_path / "oi.jsonl"
        monkeypatch.setenv("GAMMA_ORDER_INTENTS_PATH", str(led))
        quote_calls = {"n": 0}

        class Broker:
            @staticmethod
            def get_position_qty(creds, symbol):
                return 3

            @staticmethod
            def get_option_quote_hilo(creds, symbol):
                quote_calls["n"] += 1
                return (0.10, 0.09)

            @staticmethod
            def market_sell(creds, *, symbol, qty, live):
                return {"id": "sell-1", "status": "accepted"}

            @staticmethod
            def open_sell_orders(creds, symbol):
                return []

        monkeypatch.setattr(ea, "FLEET_DIR", tmp_path)
        st = em.ExitState(symbol="SPY260819C00645000", side="C", entry_premium=1.00,
                          total_qty=3, tp1_qty=2, runner_qty=1, premium_stop_pct=-0.50,
                          tp1_premium_pct=1.0, profit_lock_mode="fixed",
                          runner_stop_premium=0.50, strategy="ribbon_ride")
        ea.save_states("armY", {"SPY260819C00645000": st})
        ea.manage_tick("armY", {"key": "k"}, live=True, broker=Broker())

        rows = _rows(led)
        assert len(rows) == 1
        row = rows[0]
        assert row["intent"] == "EXIT"
        assert row["arm"] == "armY"
        assert row["leg_role"] in ("core", "runner", "tp1")
        assert row["reason"], "the exit manager's own words must be recorded"
        assert row["nbbo_bid"] == 0.09 and row["nbbo_ask"] == 0.10
        assert row["exit_state"]["entry_premium"] == 1.00
        assert row["exit_state"]["stop_premium"] == 0.50
        assert quote_calls["n"] == 1, (
            "telemetry must reuse the tick's existing quote -- a second fetch would put a "
            "network round-trip on the exit path")


# =====================================================================================
# 5. NO NEW UNLOGGED SUBMIT PATH
# =====================================================================================

class TestNoUnloggedSubmitPath:
    """Every live SPY-option order POST must sit next to a record_submit call.

    This is the guard that stops the next engine from being built blind. It greps the real
    source, so a NEW submit path added without telemetry turns this RED on the commit that
    adds it -- rather than being discovered months later as another unexplainable loss.

    KNOWN EXCLUSIONS, each with a stated reason (an exclusion without one is a hole):
      * spread_executor.py    -- BUILT DISARMED; nothing imports it on the live path, and it
                                 places multi-leg (mleg) spreads, not the single-leg SPY 0DTE
                                 orders the fills ledger tracks. Wire it when it is armed.
      * crypto_twin_broker.py -- the crypto validation twin. Its legs are is_crypto and are
                                 explicitly out of scope for the SPY decision logs.
      * dress_rehearsal.py    -- a self-test harness that places and immediately cancels.

    RED-PROOF: a scratch copy of heartbeat_core.py with the record_submit block deleted was
    fed to the same checker -- it reported heartbeat_core.py as unlogged and the test failed.
    """

    WIRED = {
        "setup/scripts/heartbeat_core.py",
        "setup/scripts/j_intent_executor.py",
        "setup/scripts/fast_path_executor.py",
        "automation/state/fleet/fleet_live.py",
        "automation/state/fleet/fleet_broker.py",
        "automation/state/fleet/exit_actuator.py",
    }

    def test_every_wired_module_still_calls_record_submit(self):
        missing = []
        for rel in sorted(self.WIRED):
            text = (REPO / rel).read_text(encoding="utf-8")
            if "_oil.record_submit(" not in text:
                missing.append(rel)
        assert not missing, (
            f"these order-submitting modules lost their order-intent write: {missing}. "
            "An order the engine cannot explain is the exact defect this ledger closed.")

    def test_every_record_submit_call_is_wrapped_against_argument_errors(self):
        """record_submit is total, but its ARGUMENTS are evaluated at the call site. Every
        call must sit inside a try/except so a telemetry expression can never raise into an
        order path."""
        offenders = []
        for rel in sorted(self.WIRED):
            lines = (REPO / rel).read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                if "_oil.record_submit(" not in line or "def " in line:
                    continue
                window = lines[max(0, i - 4):i]
                if not any(w.strip().startswith("try:") for w in window):
                    offenders.append(f"{rel}:{i + 1}")
        assert not offenders, (
            f"record_submit call(s) not guarded by a try: {offenders}")
