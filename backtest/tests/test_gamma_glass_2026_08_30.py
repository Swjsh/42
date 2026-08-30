"""The trading slice must be right or absent -- never plausible.

J, 2026-08-30: "make my dashboard like single pane of glass ai trading command center".
The page had `hasEquity:false, hasPosition:false` in its live DOM: 3 of 18 payload
sections rendered, and every dropped one was the trading half.

This file exists because the FIRST run of gamma_glass.py returned a complete, confident,
entirely wrong answer: `net_all: 0.0` across every arm. Nothing threw. Every field was
present and well-typed. The only reason it was caught is that the number was run and
compared to a known figure (+$1,815 over 39 days) instead of being read back and believed
-- calendar-data.json stores `pnl_net`, and the code had been written against `n`, which
is the PAYLOAD's compressed rewrite of the same file.

A zero P&L is the single most dangerous output this module can produce, because it looks
exactly like a flat week. So the tests below pin the KEY NAMES against the real file and
cross-foot the arms against the book, rather than merely asserting the shape.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "setup" / "scripts"))
import gamma_glass as gg  # noqa: E402


class TestTheZeroPnlTrap:
    """The exact bug that shipped-and-was-caught. Never again silently."""

    def test_day_net_reads_pnl_net_not_the_payload_alias(self):
        assert gg._day_net({"pnl_net": -60.29, "pnl_gross": -60.0}) == -60.29
        # `n` is the payload's compressed alias. Reading it here yielded 0.0 everywhere.
        assert gg._day_net({"n": -60.29}) is None, (
            "reading the payload alias instead of the raw key is the 0.0-P&L bug")

    def test_day_net_is_net_not_gross(self):
        """Gross would flatter every figure by exactly the fee drag."""
        assert gg._day_net({"pnl_gross": 322.0, "pnl_net": 321.42}) == 321.42

    def test_missing_or_malformed_is_none_never_zero(self):
        """None renders as 'no data'. 0.0 renders as a flat day. They are not the same."""
        for row in ({}, None, {"pnl_net": None}, {"pnl_net": "322"}, []):
            assert gg._day_net(row) is None

    def test_real_calendar_file_still_uses_pnl_net(self):
        """A schema change upstream must break this test, not the dashboard silently."""
        d = json.loads(gg.CALENDAR_FILE.read_text(encoding="utf-8"))
        views = d["views"]
        arm = next(k for k in views if k != gg.BOOK_VIEW)
        day = next(iter(views[arm]["days"].values()))
        assert "pnl_net" in day, "calendar-data.json schema changed -- glass P&L is now wrong"


class TestBookDoesNotDoubleCount:
    def test_book_view_excluded_from_per_arm_sums(self):
        """calendar-data.json ships a precomputed BOOK view beside the per-arm ones.

        Including it in the arm loop doubles the whole book's P&L -- and the result still
        looks like a plausible number, which is what makes it worth a test.
        """
        p = gg.group_pnl()
        assert p["ok"]
        assert gg.BOOK_VIEW not in {a["arm"] for a in p["arms"]}

    def test_arms_cross_foot_to_the_book_total(self):
        """The one arithmetic identity that proves the aggregation is real."""
        p = gg.group_pnl()
        s = sum(a["net"] for a in p["arms"] if a["net"] is not None)
        assert abs(s - p["net_all"]) < 0.5, (
            "arm nets {} != book net {}".format(round(s, 2), p["net_all"]))

    def test_series_cum_ends_at_net_all(self):
        p = gg.group_pnl()
        assert p["series"], "no series to draw"
        # series is windowed to the last 60 sessions; cum is running from the start.
        assert abs(p["series"][-1]["cum"] - p["net_all"]) < 0.5


class TestPositionHonesty:
    """`flat` and `nobody-is-writing-the-file` must never look the same."""

    def test_stale_position_file_reports_unknown_not_flat(self, monkeypatch):
        monkeypatch.setattr(gg, "_age_h", lambda p: gg.POSITION_STALE_H + 1)
        monkeypatch.setattr(gg, "_read", lambda p: {"status": None})
        monkeypatch.setattr(gg, "_today_fills", lambda: [])
        out = gg.group_position()
        assert out["state"] == "unknown"
        assert out["note"], "an unknown state must say WHY it is unknown"

    def test_fresh_and_empty_is_flat(self, monkeypatch):
        monkeypatch.setattr(gg, "_age_h", lambda p: 0.1)
        monkeypatch.setattr(gg, "_read", lambda p: {"status": None})
        monkeypatch.setattr(gg, "_today_fills", lambda: [])
        assert gg.group_position()["state"] == "flat"

    @pytest.mark.parametrize("status", ["long_call", "short_put", "open", "LONG"])
    def test_fresh_with_a_real_status_is_open(self, monkeypatch, status):
        monkeypatch.setattr(gg, "_age_h", lambda p: 0.1)
        monkeypatch.setattr(gg, "_read", lambda p: {"status": status})
        monkeypatch.setattr(gg, "_today_fills", lambda: [])
        assert gg.group_position()["state"] == "open"

    @pytest.mark.parametrize("status", ["flat", "FLAT", "closed", "none", " out "])
    def test_a_flat_WORD_is_flat_not_open(self, monkeypatch, status):
        """`if d.get("status")` treated ANY truthy string as a position, so the
        literal "flat" rendered IN A TRADE. Flagged by an adversarial review."""
        monkeypatch.setattr(gg, "_age_h", lambda p: 0.1)
        monkeypatch.setattr(gg, "_read", lambda p: {"status": status})
        monkeypatch.setattr(gg, "_today_fills", lambda: [])
        assert gg.group_position()["state"] == "flat"

    def test_no_file_at_all_is_unknown_not_flat(self, monkeypatch):
        """Nobody has told us anything. That is not the same as being flat."""
        monkeypatch.setattr(gg, "_age_h", lambda p: None)
        monkeypatch.setattr(gg, "_read", lambda p: None)
        monkeypatch.setattr(gg, "_today_fills", lambda: [])
        out = gg.group_position()
        assert out["state"] == "unknown" and out["note"]

    def test_real_call_returns_a_known_state(self):
        assert gg.group_position()["state"] in {"open", "flat", "unknown"}


class TestFleetRegistryIsAList:
    """accounts.json stores arms as a LIST; treating it as a dict produced an empty
    registry AND a phantom 'BOOK' row on the money roster."""

    def test_real_registry_is_a_list_of_dicts_with_ids(self):
        d = json.loads(gg.FLEET_FILE.read_text(encoding="utf-8"))
        assert isinstance(d["arms"], list)
        assert all(isinstance(a, dict) and a.get("id") for a in d["arms"])

    def test_no_book_row_on_the_money_roster(self):
        assert gg.BOOK_VIEW not in {r["arm"] for r in gg.group_arms()["arms"]}

    def test_no_all_empty_rows(self):
        """A row with no equity and no traded day teaches the reader to skip rows."""
        for r in gg.group_arms()["arms"]:
            assert r["equity"] is not None or r["days_traded"], (
                "{} is an empty row".format(r["arm"]))

    def test_every_arm_with_equity_appears(self):
        eq = {a["arm"] for a in gg.group_equity()["arms"]}
        shown = {r["arm"] for r in gg.group_arms()["arms"]}
        assert eq <= shown, "arms holding real money are missing: {}".format(eq - shown)


class TestBuildContract:
    def test_build_has_every_group_the_glass_renders(self):
        out = gg.build()
        for k in ("equity", "pnl", "position", "bias", "arms"):
            assert k in out, "{} missing -- the renderer would show 'no data'".format(k)

    def test_a_failing_group_is_reported_in_place(self, monkeypatch):
        """Omitting the key would let the renderer show 'no data' for a real breakage."""
        monkeypatch.setattr(gg, "group_equity",
                            lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        out = gg.build()
        assert out["equity"]["ok"] is False and "boom" in out["equity"]["error"]

    def test_every_group_carries_provenance(self):
        out = gg.build()
        for k in ("equity", "pnl", "position", "bias", "arms"):
            g = out[k]
            assert any("source" in kk for kk in g), "{} has no source".format(k)

    def test_output_is_json_serialisable(self):
        json.dumps(gg.build(), default=str)

    def test_build_is_read_only(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("gamma_glass must never write")
        monkeypatch.setattr(Path, "write_text", boom)
        monkeypatch.setattr(Path, "write_bytes", boom)
        gg.build()

    def test_market_open_is_false_on_a_weekend(self):
        now = dt.datetime.now(gg.ET)
        if now.weekday() >= 5:
            assert gg.build()["market_open"] is False


class TestNoFabricatedNumbers:
    """Every figure on the glass is sourced or absent."""

    def test_equity_total_is_none_when_unreadable(self, monkeypatch):
        monkeypatch.setattr(gg, "_read", lambda p: None)
        out = gg.group_equity()
        assert out["ok"] is False and out["total"] is None, (
            "an unreadable equity file must not render as $0.00")

    def test_pnl_absent_rather_than_zero_when_calendar_missing(self, monkeypatch):
        monkeypatch.setattr(gg, "_calendar_views", lambda: {})
        out = gg.group_pnl()
        assert out["ok"] is False
        assert "net_all" not in out or out.get("net_all") is None

    def test_today_is_none_when_no_session_today(self):
        """A day with no trading is None (no session), never 0.00 (traded flat)."""
        p = gg.group_pnl()
        if not p.get("traded_today"):
            assert p.get("today") is None
