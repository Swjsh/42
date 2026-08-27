"""Guards for the nightly REAL-broker dress rehearsal (setup/scripts/dress_rehearsal.py).

Pins, RED-on-regression:

  PAYLOAD PARITY — the rehearsal proves the ENGINE'S order path, so its fallback replica
    must stay byte-identical to heartbeat_core._place_simple_entry's POST. If either side
    drifts (a key renamed, order_class sneaking back in), the parity test REDs — the
    rehearsal must never green-light a payload the engine doesn't actually send.

  OCC PARITY — same for the engine's contract-symbol construction (_occ), a historical
    killer class (wrong OCC symbol -> broker 404/422 at the open).

  $10 CRYPTO CAP — the rehearsal's real-fill crypto round-trip may NEVER place more than
    $10 notional; _place_crypto_market refuses above the cap BEFORE any POST.

  VERDICT LOGIC — overall is GREEN only when every check is GREEN; INCONCLUSIVE never
    softens to GREEN; any RED dominates (J's green-lit-then-fails-at-open pain class).

  SELF-CHECK READER — self_check.check_dress_rehearsal flags BROKEN on overall RED or a
    >24h-stale artifact on a weekday evening; INCONCLUSIVE surfaces as DEGRADED.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_dress_rehearsal.py
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "setup" / "scripts"), str(ROOT / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}


@pytest.fixture()
def dr():
    return importlib.import_module("dress_rehearsal")


@pytest.fixture()
def hc():
    return importlib.import_module("heartbeat_core")


@pytest.fixture()
def sc():
    return importlib.import_module("self_check")


# ── payload parity: engine vs rehearsal replica ───────────────────────────────

class TestPayloadParity:
    def test_replica_post_is_byte_identical_to_engine(self, dr, hc, monkeypatch):
        import fleet_broker as fb
        posts: list = []
        monkeypatch.setattr(fb, "_request",
                            lambda creds, endpoint, method="GET", data=None, timeout=15:
                            posts.append({"endpoint": endpoint, "method": method,
                                          "data": json.loads(json.dumps(data))})
                            or {"id": "x", "status": "accepted"})
        kw = dict(symbol="SPY260702P00707000", qty=1, limit_price=0.01)
        hc._place_simple_entry(_CREDS, **kw)
        dr._replica_simple_entry(_CREDS, **kw)
        assert len(posts) == 2
        assert posts[0] == posts[1], (
            "PAYLOAD DRIFT: heartbeat_core._place_simple_entry and the rehearsal replica "
            f"no longer send identical POSTs.\n engine: {posts[0]}\n replica: {posts[1]}")

    def test_probe_payload_shape(self, dr, monkeypatch):
        import fleet_broker as fb
        posts: list = []
        monkeypatch.setattr(fb, "_request",
                            lambda creds, endpoint, method="GET", data=None, timeout=15:
                            posts.append(data) or {"id": "x", "status": "accepted"})
        dr._replica_simple_entry(_CREDS, symbol="S", qty=1, limit_price=0.01)
        d = posts[0]
        assert "order_class" not in d and "take_profit" not in d and "stop_loss" not in d
        assert d == {"symbol": "S", "qty": "1", "side": "buy", "type": "limit",
                     "limit_price": "0.01", "time_in_force": "day"}

    def test_replica_refuses_bad_inputs_without_post(self, dr, monkeypatch):
        import fleet_broker as fb
        monkeypatch.setattr(fb, "_request",
                            lambda *a, **k: pytest.fail("must not POST on bad inputs"))
        assert "_refused" in dr._replica_simple_entry(_CREDS, symbol="S", qty=0, limit_price=0.01)
        assert "_refused" in dr._replica_simple_entry(_CREDS, symbol="S", qty=1, limit_price=0)


class TestOccParity:
    @pytest.mark.parametrize("side,strike", [
        ("P", 707.0), ("C", 707.0), ("P", 702.5), ("C", 5.0), ("P", 1000.0)])
    def test_occ_matches_engine(self, dr, hc, side, strike):
        exp = dt.datetime(2026, 7, 2)
        assert dr._replica_occ(side, strike, exp) == hc._occ(side, strike, exp)


# ── $10 crypto cap ─────────────────────────────────────────────────────────────

class TestCryptoCap:
    def test_notional_constant_within_cap(self, dr):
        assert dr.CRYPTO_NOTIONAL <= dr.CRYPTO_NOTIONAL_CAP == 10.0

    @pytest.mark.parametrize("notional", [10.01, 11.0, 100.0, 5000.0])
    def test_refuses_above_cap_before_any_post(self, dr, monkeypatch, notional):
        import fleet_broker as fb
        monkeypatch.setattr(fb, "_request",
                            lambda *a, **k: pytest.fail("must NOT POST above the $10 cap"))
        res = dr._place_crypto_market(_CREDS, side="buy", notional=notional)
        assert "_refused" in res

    def test_at_cap_posts_gtc_market(self, dr, monkeypatch):
        import fleet_broker as fb
        posts: list = []
        monkeypatch.setattr(fb, "_request",
                            lambda creds, endpoint, method="GET", data=None, timeout=15:
                            posts.append({"endpoint": endpoint, "method": method, "data": data})
                            or {"id": "x", "status": "pending_new"})
        dr._place_crypto_market(_CREDS, side="buy", notional=10.0)
        assert posts == [{"endpoint": "orders", "method": "POST",
                          "data": {"symbol": "BTC/USD", "side": "buy", "type": "market",
                                   "time_in_force": "gtc", "notional": "10.00"}}]


# ── verdict logic ──────────────────────────────────────────────────────────────

class TestOverallVerdict:
    def test_all_green(self, dr):
        assert dr.compute_overall({"a": {"verdict": "GREEN"}, "b": {"verdict": "GREEN"}}) == "GREEN"

    def test_inconclusive_never_greens(self, dr):
        checks = {"a": {"verdict": "GREEN"}, "b": {"verdict": "INCONCLUSIVE_AFTER_HOURS"}}
        assert dr.compute_overall(checks) == "INCONCLUSIVE"

    def test_red_dominates(self, dr):
        checks = {"a": {"verdict": "GREEN"}, "b": {"verdict": "INCONCLUSIVE_AFTER_HOURS"},
                  "c": {"verdict": "RED"}}
        assert dr.compute_overall(checks) == "RED"

    def test_missing_verdict_is_red(self, dr):
        assert dr.compute_overall({"a": {}}) == "RED"

    def test_rejection_classifier(self, dr):
        assert dr._classify_rejection(401, "")[0] == "RED"
        assert dr._classify_rejection(422, '{"code": 42210000}')[0] == "RED"
        assert dr._classify_rejection(422, "complex orders not supported")[0] == "RED"
        v, _ = dr._classify_rejection(422, "market is closed")
        assert v == "INCONCLUSIVE_AFTER_HOURS"
        assert dr._classify_rejection(422, "mystery")[0] == "RED"  # unknown NEVER softens


# ── end-state open-orders/positions listing lag tolerance (L found 2026-07-21) ─
#
# Alpaca's GET /v2/orders?status=open list is backed by a different index than
# the single-order GET check1 just polled to a confirmed terminal status, and
# can lag it by ~1-2s. Found LIVE on the nightly run: safe RED'd on a stale
# listing (order still shown "open" after a confirmed cancel) while bold
# GREENed moments later on the identical code path — non-determinism, not a
# real broker-side residue. These guards pin the retry-before-NOT-CLEAN fix.

class _FakeTime:
    def sleep(self, _s):
        pass


class TestEndStateRetryTolerance:
    def _rig(self, monkeypatch, dr, open_orders_sequence):
        import fleet_broker as fb
        calls = {"open_orders": 0}

        def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
            if endpoint.startswith("options/contracts"):
                return {"option_contracts": [{"symbol": "SPY260722P00709000",
                                               "strike_price": "709.0",
                                               "close_price": "0.05", "tradable": True}]}
            if endpoint == "orders" and method == "POST":
                return {"id": "oid1", "status": "accepted"}
            if endpoint.startswith("orders?status=open"):
                idx = min(calls["open_orders"], len(open_orders_sequence) - 1)
                calls["open_orders"] += 1
                return open_orders_sequence[idx]
            raise AssertionError(f"unexpected _request endpoint {endpoint!r}")

        monkeypatch.setattr(fb, "_request", fake_request)
        monkeypatch.setattr(fb, "cancel_order", lambda creds, oid, live=True: {})
        monkeypatch.setattr(fb, "get_order", lambda creds, oid: {"status": "canceled"})
        monkeypatch.setattr(fb, "get_positions", lambda creds: [])
        monkeypatch.setattr(dr, "_time", _FakeTime())
        return calls

    def _run(self, dr):
        occ_fn = lambda side, strike, expiry: "SPY260722P00709000"  # noqa: E731
        place_fn = lambda creds, symbol, qty, limit_price: {"id": "oid1", "status": "accepted"}  # noqa: E731
        return dr.check1_options_acceptance("safe", _CREDS, place_fn, occ_fn,
                                            "2026-07-22", 747.95)

    def test_transient_stale_listing_clears_on_retry(self, dr, monkeypatch):
        calls = self._rig(monkeypatch, dr, [[{"id": "oid1"}], [{"id": "oid1"}], []])
        out = self._run(dr)
        assert out["verdict"] == "GREEN", out["evidence"]
        assert calls["open_orders"] == 3, "must actually retry, not just get lucky on try 1"

    def test_persistent_open_order_stays_red_not_silently_green(self, dr, monkeypatch):
        calls = self._rig(monkeypatch, dr, [[{"id": "oid1"}]])  # never clears
        out = self._run(dr)
        assert out["verdict"] == "RED", "genuine residue must never be softened to GREEN"
        assert calls["open_orders"] == dr.END_STATE_RETRIES, (
            "must give up after a bounded number of retries, not hang or under-try")

    def test_immediate_clean_needs_only_one_try(self, dr, monkeypatch):
        calls = self._rig(monkeypatch, dr, [[]])
        out = self._run(dr)
        assert out["verdict"] == "GREEN"
        assert calls["open_orders"] == 1, "the common case must not pay retry latency"


# ── check3 beacon-freshness weekend exemption (2026-07-26 false-RED root-cause) ─
#
# Gamma_DressRehearsal fires every calendar day (DaysInterval=1), including
# weekends. Before this fix, check3_sanity's beacon-freshness sub-check had no
# weekend exemption (unlike engine_health.py's "market closed -- quiet OK"
# idiom), so it RED'd every Sat/Sun night forever on a beacon that is CORRECTLY
# stale since Friday's close. Root-caused live: automation/state/dress-
# rehearsal.json 2026-07-25T20:45:01 (Saturday), beacon age 52.3h.

class TestCheck3SanityWeekendExemption:
    def _rig(self, monkeypatch, dr, *, beacon_age_h: float, beacon_exists: bool = True):
        import fleet_broker as fb
        creds_map = {"safe": _CREDS}
        monkeypatch.setattr(fb, "_request",
                            lambda creds, endpoint, method="GET", data=None, timeout=15:
                            {"next_open": "2026-07-27T09:30:00-04:00"})
        monkeypatch.setattr(fb, "get_account",
                            lambda creds: {"status": "ACTIVE", "options_approved_level": 3})
        fake_mtime = __import__("time").time() - beacon_age_h * 3600.0
        fake_beacon = type("FakeBeacon", (), {
            "exists": staticmethod(lambda: beacon_exists),
            "stat": staticmethod(lambda: type("S", (), {"st_mtime": fake_mtime})()),
        })()
        monkeypatch.setattr(dr, "BEACON", fake_beacon)
        return creds_map

    def test_stale_beacon_on_weekday_is_red(self, dr, monkeypatch):
        creds_map = self._rig(monkeypatch, dr, beacon_age_h=52.3)
        out = dr.check3_sanity(creds_map, "2026-07-27", is_weekend=False)
        assert out["verdict"] == "RED"
        assert any("FAIL: beacon stale" in e for e in out["evidence"])

    def test_stale_beacon_on_weekend_is_green_quiet_ok(self, dr, monkeypatch):
        creds_map = self._rig(monkeypatch, dr, beacon_age_h=52.3)
        out = dr.check3_sanity(creds_map, "2026-07-27", is_weekend=True)
        assert out["verdict"] == "GREEN", out["evidence"]
        assert any("quiet OK" in e for e in out["evidence"])

    def test_fresh_beacon_on_weekday_is_green_regardless(self, dr, monkeypatch):
        creds_map = self._rig(monkeypatch, dr, beacon_age_h=2.0)
        out = dr.check3_sanity(creds_map, "2026-07-27", is_weekend=False)
        assert out["verdict"] == "GREEN"

    def test_missing_beacon_stays_red_even_on_weekend(self, dr, monkeypatch):
        """A MISSING beacon is a genuine unknown (never ran, or the file was deleted) --
        the weekend exemption only softens KNOWN-stale-by-design, never absence."""
        creds_map = self._rig(monkeypatch, dr, beacon_age_h=0, beacon_exists=False)
        out = dr.check3_sanity(creds_map, "2026-07-27", is_weekend=True)
        assert out["verdict"] == "RED"
        assert any("MISSING" in e for e in out["evidence"])

    def test_main_passes_et_weekday_derived_is_weekend(self, dr):
        import inspect
        assert "is_weekend=et_weekday() >= 5" in inspect.getsource(dr.main)


# ── artifact schema (validates the LIVE artifact when present) ────────────────

class TestArtifactSchema:
    REQUIRED = ("ran_at_et", "next_trading_day", "overall", "checks")

    def test_live_artifact_schema(self, dr):
        if not dr.OUT.exists():
            pytest.skip("no live rehearsal artifact yet")
        d = json.loads(dr.OUT.read_text(encoding="utf-8"))
        for k in self.REQUIRED:
            assert k in d, f"artifact missing key {k!r}"
        assert d["overall"] in ("GREEN", "RED", "INCONCLUSIVE")
        for name, c in d["checks"].items():
            assert "verdict" in c and "evidence" in c, f"check {name} malformed"
            assert isinstance(c["evidence"], list)


# ── idempotent-by-default + --force (backup AtLogOn trigger, 2026-08-26) ───────
# Root cause: J's machine reboots most evenings in the 18:00-22:00 MT window
# (Kernel-Power event log), landing directly in the primary 20:45 ET trigger's
# window on 2026-08-24/25/26 (3 consecutive missed runs, self_check RED). The fix
# adds a backup AtLogOn trigger to the SAME task, made safe by making every run
# skip real work by default when today's artifact already exists (--force overrides).
# These guards pin that the skip never eats a genuine daily run and that --force
# always does real work regardless of an existing artifact.

class TestIdempotentSkipByDefault:
    def test_ran_today_already_true_when_artifact_dated_today(self, dr, tmp_path, monkeypatch):
        p = tmp_path / "dress-rehearsal.json"
        p.write_text(json.dumps({"ran_at_et": "2026-08-26T20:45:01", "overall": "GREEN"}),
                     encoding="utf-8")
        monkeypatch.setattr(dr, "OUT", p)
        assert dr._ran_today_already(dt.datetime(2026, 8, 26, 22, 10)) is True

    def test_ran_today_already_false_when_artifact_dated_yesterday(self, dr, tmp_path, monkeypatch):
        p = tmp_path / "dress-rehearsal.json"
        p.write_text(json.dumps({"ran_at_et": "2026-08-23T20:45:01", "overall": "GREEN"}),
                     encoding="utf-8")
        monkeypatch.setattr(dr, "OUT", p)
        assert dr._ran_today_already(dt.datetime(2026, 8, 26, 22, 10)) is False

    def test_ran_today_already_false_when_artifact_missing(self, dr, tmp_path, monkeypatch):
        monkeypatch.setattr(dr, "OUT", tmp_path / "does-not-exist.json")
        assert dr._ran_today_already(dt.datetime(2026, 8, 26, 22, 10)) is False

    def test_ran_today_already_false_when_artifact_unreadable(self, dr, tmp_path, monkeypatch):
        p = tmp_path / "dress-rehearsal.json"
        p.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(dr, "OUT", p)
        assert dr._ran_today_already(dt.datetime(2026, 8, 26, 22, 10)) is False

    def test_default_run_skips_real_work_when_already_ran(self, dr, tmp_path, monkeypatch):
        p = tmp_path / "dress-rehearsal.json"
        p.write_text(json.dumps({"ran_at_et": dr.et_now().strftime("%Y-%m-%dT%H:%M:%S"),
                                 "overall": "GREEN"}), encoding="utf-8")
        monkeypatch.setattr(dr, "OUT", p)
        called = {"n": 0}
        monkeypatch.setattr(dr.fb, "load_creds", lambda: called.update(n=called["n"] + 1) or {})
        rc = dr.main([])
        assert rc == 0
        assert called["n"] == 0, "a plain re-fire (e.g. the AtLogOn backup trigger) must not " \
                                  "touch the broker when today already ran"

    def test_default_run_does_real_work_when_not_yet_run_today(self, dr, tmp_path, monkeypatch):
        p = tmp_path / "dress-rehearsal.json"
        p.write_text(json.dumps({"ran_at_et": "2026-08-23T20:45:01", "overall": "GREEN"}),
                     encoding="utf-8")
        monkeypatch.setattr(dr, "OUT", p)
        called = {"n": 0}
        monkeypatch.setattr(dr.fb, "load_creds", lambda: called.update(n=called["n"] + 1) or {})
        dr.main([])
        assert called["n"] == 1, "the primary nightly trigger must always do real work " \
                                  "the first time today"

    def test_force_flag_always_does_real_work(self, dr, tmp_path, monkeypatch):
        p = tmp_path / "dress-rehearsal.json"
        p.write_text(json.dumps({"ran_at_et": dr.et_now().strftime("%Y-%m-%dT%H:%M:%S"),
                                 "overall": "GREEN"}), encoding="utf-8")
        monkeypatch.setattr(dr, "OUT", p)
        called = {"n": 0}
        monkeypatch.setattr(dr.fb, "load_creds", lambda: called.update(n=called["n"] + 1) or {})
        dr.main(["--force"])
        assert called["n"] == 1, "--force must bypass the already-ran-today skip"


# ── self_check reader ──────────────────────────────────────────────────────────

_EVENING = dt.datetime(2026, 7, 1, 21, 30)   # Wednesday 21:30 ET
_WEEKEND = dt.datetime(2026, 7, 4, 21, 30)   # Saturday


def _write(tmp_path, overall, ran_at):
    p = tmp_path / "dress-rehearsal.json"
    p.write_text(json.dumps({"ran_at_et": ran_at, "overall": overall, "checks": {}}),
                 encoding="utf-8")
    return p


class TestSelfCheckReader:
    def test_fresh_green_is_silent(self, sc, tmp_path):
        p = _write(tmp_path, "GREEN", "2026-07-01T20:45:00")
        assert sc.check_dress_rehearsal(_EVENING, path=p) == []

    def test_overall_red_is_broken(self, sc, tmp_path):
        p = _write(tmp_path, "RED", "2026-07-01T20:45:00")
        probs = sc.check_dress_rehearsal(_EVENING, path=p)
        assert probs and sc._problem_is_broken(probs[0])

    def test_stale_on_weekday_evening_is_broken(self, sc, tmp_path):
        p = _write(tmp_path, "GREEN", "2026-06-29T20:45:00")  # >24h old
        probs = sc.check_dress_rehearsal(_EVENING, path=p)
        assert probs and any(sc._problem_is_broken(x) for x in probs)

    def test_inconclusive_is_degraded_not_broken(self, sc, tmp_path):
        p = _write(tmp_path, "INCONCLUSIVE", "2026-07-01T20:45:00")
        probs = sc.check_dress_rehearsal(_EVENING, path=p)
        assert probs and not any(sc._problem_is_broken(x) for x in probs)

    def test_missing_artifact_broken_only_on_weekday_evening(self, sc, tmp_path):
        p = tmp_path / "nope.json"
        assert sc.check_dress_rehearsal(_WEEKEND, path=p) == []
        probs = sc.check_dress_rehearsal(_EVENING, path=p)
        assert probs and sc._problem_is_broken(probs[0])

    def test_wired_into_run(self, sc):
        import inspect
        assert "check_dress_rehearsal(now)" in inspect.getsource(sc.run)


# ── deep-OTM band widening (2026-07-28 false-RED fix) ──────────────────────────
# Live-verified 2026-07-28 (spot 738.85): the original fixed target-10 window found
# only strikes 695/700/701 (SPY's far-OTM chain is NOT $1-spaced), all pricing
# $0.06-$0.08 -- above MAX_PREMIUM $0.05 -- so the probe RED'd on BOTH accounts every
# night without ever reaching order placement. _pick_deep_otm_put must escalate
# through wider bands rather than give up after one narrow query.

class TestDeepOtmBandWidening:
    def _rig(self, monkeypatch, dr, bands_and_contracts: dict):
        """bands_and_contracts: {band_offset: [contract dicts]} — fake _request routes
        on the strike_price_gte value implied by each band so we can assert exactly
        which bands got queried."""
        import fleet_broker as fb

        target = 738.85 * (1.0 - dr.DEEP_OTM_PCT)
        gte_by_band = {band: round(target - band, 2) for band in bands_and_contracts}
        calls = []

        def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
            calls.append(endpoint)
            for band, gte in gte_by_band.items():
                if f"strike_price_gte={gte:.2f}" in endpoint:
                    return {"option_contracts": bands_and_contracts[band]}
            raise AssertionError(f"unexpected endpoint {endpoint!r}")

        monkeypatch.setattr(fb, "_request", fake_request)
        return calls

    def _contract(self, strike, close_price):
        return {"symbol": f"SPY_TEST_{strike}", "strike_price": str(strike),
                "close_price": close_price, "tradable": True}

    def test_narrow_band_all_rich_escalates_to_wider_band(self, dr, monkeypatch):
        """The exact 2026-07-28 shape: band=10 has only rich contracts (no <= MAX_PREMIUM);
        a wider band has a qualifying one. Must NOT RED — must pick from the wider band."""
        ev: list = []
        calls = self._rig(monkeypatch, dr, {
            10: [self._contract(701, "0.08"), self._contract(700, "0.06"),
                 self._contract(695, "0.06")],
            30: [self._contract(701, "0.08"), self._contract(700, "0.06"),
                 self._contract(695, "0.06"), self._contract(690, "0.05")],
        })
        picked = dr._pick_deep_otm_put(_CREDS, "2026-07-28", 738.85, ev)
        assert picked is not None, f"should have escalated to band=30 and found strike 690; evidence={ev}"
        assert picked["strike_price"] == "690"
        assert len(calls) == 2, "must query band=10 first, then escalate to band=30 — not skip ahead"

    def test_first_band_success_never_queries_wider_bands(self, dr, monkeypatch):
        """When band=10 already has a qualifying contract, don't waste calls widening."""
        calls = self._rig(monkeypatch, dr, {
            10: [self._contract(701, "0.04")],
        })
        ev: list = []
        picked = dr._pick_deep_otm_put(_CREDS, "2026-07-28", 738.85, ev)
        assert picked is not None
        assert picked["strike_price"] == "701"
        assert len(calls) == 1, "must not escalate once the narrowest band already qualifies"

    def test_all_bands_rich_still_reds_with_evidence(self, dr, monkeypatch):
        """If every band is genuinely rich, still return None (RED) — never fabricate a pick —
        but the evidence must name the full escalation, not just the first band."""
        rich = {10: [self._contract(701, "0.08")], 30: [self._contract(690, "0.07")],
                60: [self._contract(670, "0.09")], 100: [self._contract(640, "0.06")]}
        monkeypatch.setattr(dr, "STRIKE_SEARCH_BANDS", tuple(rich.keys()))
        self._rig(monkeypatch, dr, rich)
        ev: list = []
        picked = dr._pick_deep_otm_put(_CREDS, "2026-07-28", 738.85, ev)
        assert picked is None
        assert any("across bands" in e for e in ev)

    def test_all_bands_empty_reds_distinctly_from_all_bands_rich(self, dr, monkeypatch):
        """Empty-chain and rich-chain are different failure modes — evidence must distinguish
        them (a genuinely broken chain read vs a real-but-rich market)."""
        monkeypatch.setattr(dr, "STRIKE_SEARCH_BANDS", (10, 30))
        self._rig(monkeypatch, dr, {10: [], 30: []})
        ev: list = []
        picked = dr._pick_deep_otm_put(_CREDS, "2026-07-28", 738.85, ev)
        assert picked is None
        assert any("no tradable contracts found" in e for e in ev)


# ── next-trading-day: broker clock is authoritative, not a calendar guess ──────
# 2026-07-28 scar: _next_trading_day guessed via calendar?start=today+1, which is only
# correct when called AFTER today's close. An off-schedule run before today's own open
# (e.g. manual verification at 01:xx ET) skipped today and returned tomorrow, disagreeing
# with check3_sanity's own clock read and false-RED-ing an otherwise-fixed rehearsal.

class TestNextTradingDayUsesClock:
    def test_uses_clock_next_open_not_calendar_endpoint(self, dr, monkeypatch):
        import fleet_broker as fb

        calls = []

        def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
            calls.append(endpoint)
            if endpoint == "clock":
                return {"is_open": False, "next_open": "2026-07-28T09:30:00-04:00"}
            raise AssertionError(f"should not query the calendar endpoint: {endpoint!r}")

        monkeypatch.setattr(fb, "_request", fake_request)
        result = dr._next_trading_day(_CREDS, dt.datetime(2026, 7, 28, 1, 16))
        assert result == "2026-07-28"
        assert calls == ["clock"], "must read the clock, never fall through to the calendar guess when it succeeds"

    def test_falls_back_to_calendar_when_clock_unreadable(self, dr, monkeypatch):
        import fleet_broker as fb

        def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
            if endpoint == "clock":
                return {"_error": "boom"}
            return [{"date": "2026-07-29"}]

        monkeypatch.setattr(fb, "_request", fake_request)
        result = dr._next_trading_day(_CREDS, dt.datetime(2026, 7, 28, 1, 16))
        assert result == "2026-07-29"
