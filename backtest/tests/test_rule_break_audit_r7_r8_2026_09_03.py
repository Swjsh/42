"""Guards for the R7 (PDT awareness) / R8 (journal-every-trade) extension added to
setup/scripts/rule_break_audit.py on 2026-09-03 (queue item RULE-AUDIT-COVERAGE-GAPS).

Everything here is fixture-based -- no live broker call. The live run itself (quoted in
the queue closure) already found and fixed a real bug the fixtures below now pin down:
journal/trades.csv can record ONE broker fill as MULTIPLE same-timestamp, same-price legs
whose quantities sum to the fill (risky-1, 2026-09-02, qty=5 fill journaled as qty=1 +
qty=4 rows) -- an exact single-leg matcher misreports that as a Rule-8 break when every
contract genuinely was journaled. test_split_fill_* pins the fix; test_true_miss_is_
unmatched pins that a REAL gap still gets reported, so the split-fill fallback cannot
paper over an actual miss.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "setup" / "scripts" / "rule_break_audit.py"

_spec = importlib.util.spec_from_file_location("rule_break_audit_r7r8", MODULE)
assert _spec and _spec.loader
rba = importlib.util.module_from_spec(_spec)
sys.modules["rule_break_audit_r7r8"] = rba
_spec.loader.exec_module(rba)


# ---------------------------------------------------------------------------------------
# occ_symbol_from_contract -- pure string normalisation, no I/O.
# ---------------------------------------------------------------------------------------

def test_occ_symbol_from_journal_shape():
    assert rba.occ_symbol_from_contract("SPY 2026-08-27 768C") == "SPY260827C00768000"


def test_occ_symbol_from_journal_shape_put():
    assert rba.occ_symbol_from_contract("SPY 2026-06-26 732P") == "SPY260626P00732000"


def test_occ_symbol_passthrough_when_already_occ():
    assert rba.occ_symbol_from_contract("SPY260618C00746000") == "SPY260618C00746000"


def test_occ_symbol_none_on_garbage():
    assert rba.occ_symbol_from_contract("not a contract") is None
    assert rba.occ_symbol_from_contract("") is None
    assert rba.occ_symbol_from_contract(None) is None


# ---------------------------------------------------------------------------------------
# journal_legs_for_date -- reads journal/trades.csv from a fixture repo, not the real one.
# ---------------------------------------------------------------------------------------

CSV_HEADER = ("date,time_entry,time_exit,setup,contract,dte,strike,c_or_p,qty,entry_px,"
             "exit_px,account_id\n")


def _write_journal(tmp_path: Path, rows: list[str]) -> Path:
    j = tmp_path / "journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / "trades.csv").write_text(CSV_HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return tmp_path


def test_journal_legs_reads_entry_and_exit_leg_per_row(tmp_path):
    repo = _write_journal(tmp_path, [
        "2026-09-02,11:17:07,11:52:07,SETUP,SPY 2026-09-02 766C,0,766,C,3,0.93,0.63,safe-3",
    ])
    legs = rba.journal_legs_for_date("2026-09-02", repo=repo)
    assert len(legs) == 2
    entry = next(leg for leg in legs if leg["leg"] == "entry")
    exit_ = next(leg for leg in legs if leg["leg"] == "exit")
    assert entry["occ"] == "SPY260902C00766000"
    assert entry["side"] == "buy" and entry["qty"] == 3.0 and entry["px"] == 0.93
    assert exit_["side"] == "sell" and exit_["px"] == 0.63


def test_journal_legs_filters_to_the_requested_date(tmp_path):
    repo = _write_journal(tmp_path, [
        "2026-09-01,10:00:00,10:05:00,S,SPY 2026-09-01 766C,0,766,C,1,1.0,1.1,safe-3",
        "2026-09-02,11:00:00,11:05:00,S,SPY 2026-09-02 766C,0,766,C,1,1.0,1.1,safe-3",
    ])
    legs = rba.journal_legs_for_date("2026-09-02", repo=repo)
    assert len(legs) == 2  # one row -> entry + exit
    assert all(leg["occ"] == "SPY260902C00766000" for leg in legs)


# ---------------------------------------------------------------------------------------
# match_fills_to_journal -- the core R8 matcher. Fixtures only, no network.
# ---------------------------------------------------------------------------------------

def _leg(row, leg, account_id, occ, side, qty, px, ts_s):
    return {"row": row, "leg": leg, "account_id": account_id, "occ": occ, "side": side,
            "qty": qty, "px": px, "ts_s": ts_s, "ts_hms": f"{ts_s // 3600:02d}:00:00"}


def _fill(account_id, symbol, side, qty, px, ts_s):
    return {"account_id": account_id, "symbol": symbol, "side": side, "qty": qty,
            "px": px, "ts_s": ts_s, "filled_at_et": f"{ts_s // 3600:02d}:00:00"}


def test_exact_match():
    legs = [_leg(0, "entry", "safe-3", "SPY260902C00766000", "buy", 3, 0.93, 40627)]
    fills = [_fill("safe-3", "SPY260902C00766000", "buy", 3, 0.93, 40627)]
    out = rba.match_fills_to_journal(fills, legs)
    assert out["n_journaled"] == 1 and out["n_unmatched"] == 0 and out["match_rate"] == 1.0
    assert out["journaled"][0]["match_kind"] == "exact"


def test_tolerance_match_within_120s_and_2_cents():
    legs = [_leg(0, "entry", "safe-3", "SPY260902C00766000", "buy", 3, 0.93, 40627)]
    # journal timestamp 90s later, price a cent off -- inside tolerance
    fills = [_fill("safe-3", "SPY260902C00766000", "buy", 3, 0.94, 40627 + 90)]
    out = rba.match_fills_to_journal(fills, legs)
    assert out["n_journaled"] == 1 and out["n_unmatched"] == 0


def test_miss_outside_time_tolerance_is_unmatched_with_closest_candidate():
    legs = [_leg(0, "entry", "safe-3", "SPY260902C00766000", "buy", 3, 0.93, 40627)]
    fills = [_fill("safe-3", "SPY260902C00766000", "buy", 3, 0.93, 40627 + 121)]
    out = rba.match_fills_to_journal(fills, legs)
    assert out["n_journaled"] == 0 and out["n_unmatched"] == 1
    closest = out["unmatched"][0]["closest_candidate"]
    assert closest is not None and closest["row"] == 0


def test_true_miss_is_unmatched_when_no_journal_row_exists_at_all():
    """A REAL Rule-8 gap: the broker fill has no journal leg anywhere for that
    account/symbol/side. Guards that the split-fill fallback (below) never invents a
    match for a genuinely un-journaled fill."""
    legs: list[dict] = []
    fills = [_fill("safe-3", "SPY260902C00766000", "buy", 3, 0.93, 40627)]
    out = rba.match_fills_to_journal(fills, legs)
    assert out["n_journaled"] == 0 and out["n_unmatched"] == 1
    assert out["match_rate"] == 0.0
    assert out["unmatched"][0]["closest_candidate"] is None


def test_split_fill_qty_sums_to_one_broker_fill():
    """Pins the live-run bug (risky-1, 2026-09-02): one qty=5 broker fill, journaled as
    two same-time/same-price legs (qty=1 + qty=4). Must resolve as journaled, not a break."""
    legs = [
        _leg(10, "entry", "risky-1", "SPY260902C00765000", "buy", 1, 1.11, 43029),
        _leg(11, "entry", "risky-1", "SPY260902C00765000", "buy", 4, 1.11, 43029),
    ]
    fills = [_fill("risky-1", "SPY260902C00765000", "buy", 5, 1.11, 43029)]
    out = rba.match_fills_to_journal(fills, legs)
    assert out["n_journaled"] == 1 and out["n_unmatched"] == 0
    row = out["journaled"][0]
    assert row["match_kind"].startswith("split_fill")
    assert sorted(row["journal_row"]) == [10, 11]


def test_split_fill_does_not_over_claim_an_unrelated_leg():
    """A same-symbol leg at a DIFFERENT price/time must not be swept into the split-sum
    just because the quantities happen to add up -- price/time gating still applies to
    every candidate leg in the split search."""
    legs = [
        _leg(10, "entry", "risky-1", "SPY260902C00765000", "buy", 1, 1.11, 43029),
        _leg(11, "entry", "risky-1", "SPY260902C00765000", "buy", 4, 1.03, 46800),  # different day's trade
    ]
    fills = [_fill("risky-1", "SPY260902C00765000", "buy", 5, 1.11, 43029)]
    out = rba.match_fills_to_journal(fills, legs)
    assert out["n_journaled"] == 0 and out["n_unmatched"] == 1


def test_each_leg_consumed_at_most_once():
    """Two identical fills must not both claim the same single journal leg."""
    legs = [_leg(0, "entry", "safe-3", "SPY260902C00766000", "buy", 3, 0.93, 40627)]
    fills = [
        _fill("safe-3", "SPY260902C00766000", "buy", 3, 0.93, 40627),
        _fill("safe-3", "SPY260902C00766000", "buy", 3, 0.93, 40627),
    ]
    out = rba.match_fills_to_journal(fills, legs)
    assert out["n_journaled"] == 1 and out["n_unmatched"] == 1


def test_empty_fills_reports_none_match_rate():
    out = rba.match_fills_to_journal([], [_leg(0, "entry", "safe-3", "X", "buy", 1, 1.0, 0)])
    assert out["n_fills"] == 0 and out["match_rate"] is None


# ---------------------------------------------------------------------------------------
# fetch_r7_pdt_observations / fetch_r8_journal_join -- wiring only, broker monkeypatched
# so these tests never touch the network.
# ---------------------------------------------------------------------------------------

def test_r7_reports_break_checkable_false_when_field_absent(monkeypatch):
    def fake_module():
        class M:
            @staticmethod
            def load_creds():
                return {"safe-2": {"key": "k", "secret": "s", "base_url": "https://x"}}

            @staticmethod
            def get_account(creds):
                return {"equity": "5653.81", "intraday_adjustments": "0"}  # no PDT fields
        return M
    monkeypatch.setattr(rba, "_fleet_broker_module", fake_module)
    out = rba.fetch_r7_pdt_observations(repo=REPO)
    obs = out["arms"]["safe-2"]
    assert obs["reachable"] is True
    assert obs["pattern_day_trader_field_present"] is False
    assert obs["break_checkable"] is False
    assert obs["break"] is False


def test_r7_flags_a_break_when_pdt_true_and_field_present(monkeypatch):
    def fake_module():
        class M:
            @staticmethod
            def load_creds():
                return {"safe-2": {"key": "k", "secret": "s", "base_url": "https://x"}}

            @staticmethod
            def get_account(creds):
                return {"equity": "1000.00", "pattern_day_trader": True, "daytrade_count": 4}
        return M
    monkeypatch.setattr(rba, "_fleet_broker_module", fake_module)
    out = rba.fetch_r7_pdt_observations(repo=REPO)
    obs = out["arms"]["safe-2"]
    assert obs["break_checkable"] is True
    assert obs["break"] is True


def test_r7_fails_open_when_fleet_broker_unavailable(monkeypatch):
    monkeypatch.setattr(rba, "_fleet_broker_module", lambda: None)
    out = rba.fetch_r7_pdt_observations(repo=REPO)
    assert out["arms"] == {} and "error" in out


def test_r8_fails_open_when_fleet_broker_unavailable(monkeypatch, tmp_path):
    repo = _write_journal(tmp_path, [])
    monkeypatch.setattr(rba, "_fleet_broker_module", lambda: None)
    out = rba.fetch_r8_journal_join("2026-09-02", repo=repo)
    assert out["arms"] == {} and "error" in out


def test_run_without_include_r7_r8_never_touches_broker(monkeypatch):
    """Backward compatibility: run() with the default include_r7_r8=False must not even
    import fleet_broker -- every pre-existing caller/test keeps working unchanged."""
    def _boom():
        raise AssertionError("fleet_broker must not be imported when include_r7_r8=False")
    monkeypatch.setattr(rba, "_fleet_broker_module", _boom)
    out = rba.run(repo=REPO, write=False)
    assert "r7_pdt_observations" not in out["report"]
    assert "r8_journal_join" not in out["report"]


def test_run_include_r7_r8_wires_both_keys_additively(monkeypatch, tmp_path):
    repo = _write_journal(tmp_path, [
        "2026-09-02,11:17:07,11:52:07,SETUP,SPY 2026-09-02 766C,0,766,C,3,0.93,0.63,safe-3",
    ])

    def fake_module():
        class M:
            @staticmethod
            def load_creds():
                return {}
        return M
    monkeypatch.setattr(rba, "_fleet_broker_module", fake_module)
    out = rba.run(repo=repo, write=False, include_r7_r8=True, r8_date="2026-09-02")
    rep = out["report"]
    # additive only -- every pre-existing key from a network-free run() call is untouched
    assert "breaks_found" in rep and "coverage_by_rule" in rep and "honesty_note" in rep
    assert "r7_pdt_observations" in rep
    assert "r8_journal_join" in rep
    assert rep["r8_journal_join"]["date"] == "2026-09-02"
