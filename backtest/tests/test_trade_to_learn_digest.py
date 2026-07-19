"""Guard: TRADE-TO-LEARN-CUMULATIVE-DIGEST (F3 close 2026-07-18 follow-up).

Pins the "since-arm date, real fills only" cumulative digest for trade-to-learn
setups (`backtest/autoresearch/trade_to_learn_digest.py`), folded into
`license_monitor.py`'s nightly STATUS block. Rule 9 (visibility only, never
auto-disarms) + C14 (a new `extra_setup_exec_armed` True key with no matching
`ARM_DATES` entry must fail LOUD, not silently drop out of the digest).
"""
from __future__ import annotations

import json

import pytest

from autoresearch import trade_to_learn_digest as t2l


@pytest.fixture()
def synthetic_csv(tmp_path):
    p = tmp_path / "trades.csv"
    header = "date,time_entry,time_exit,setup,dollar_pnl,account_id\n"
    rows = [
        # 2 fills for vwap_continuation AFTER its 2026-07-01 arm date
        "2026-07-05,09:31,09:40,VWAP_CONTINUATION,25.5,safe",
        "2026-07-06,10:00,10:05,vwap_continuation,-10,safe",
        # 1 fill BEFORE the documented arm date -- must be EXCLUDED
        "2026-06-15,09:31,09:40,VWAP_CONTINUATION,999,safe",
        # a setup not in ARM_DATES / not armed at all -- must never appear
        "2026-07-05,11:00,11:10,SOME_UNRELATED_SETUP,50,safe",
        # bollinger_squeeze, armed 2026-07-02 -- one fill on the arm date itself (inclusive)
        "2026-07-02,13:00,13:05,bollinger_squeeze,12,safe",
    ]
    p.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
    return p


@pytest.fixture()
def synthetic_params(tmp_path):
    p = tmp_path / "params.json"
    p.write_text(json.dumps({
        "extra_setup_exec_armed": {
            "vwap_continuation": True,
            "vwap_reclaim_failed_break": True,
            "vix_regime_dayside": False,   # False -> must NOT appear in output
            "bollinger_squeeze": True,
        }
    }), encoding="utf-8")
    return p


def test_sums_only_fills_at_or_after_the_documented_arm_date(synthetic_csv, synthetic_params):
    d = t2l.compute_since_arm(csv_path=synthetic_csv, params_path=synthetic_params,
                               today=__import__("datetime").date(2026, 7, 18))
    vc = d["setups"]["vwap_continuation"]
    assert vc["n_fills"] == 2, "the pre-arm-date 999 fill must be excluded"
    assert vc["total_dollar_pnl"] == pytest.approx(15.5)
    assert vc["first_fill"] == "2026-07-05"
    assert vc["status"] == "ACTIVE"


def test_case_insensitive_setup_matching(synthetic_csv, synthetic_params):
    d = t2l.compute_since_arm(csv_path=synthetic_csv, params_path=synthetic_params)
    # one row is UPPERCASE ("VWAP_CONTINUATION"), one is lowercase -- both must count
    assert d["setups"]["vwap_continuation"]["n_fills"] == 2


def test_arm_date_boundary_is_inclusive(synthetic_csv, synthetic_params):
    d = t2l.compute_since_arm(csv_path=synthetic_csv, params_path=synthetic_params)
    bsq = d["setups"]["bollinger_squeeze"]
    assert bsq["n_fills"] == 1
    assert bsq["arm_date"] == "2026-07-02"
    assert bsq["first_fill"] == "2026-07-02"


def test_disabled_setup_never_appears(synthetic_csv, synthetic_params):
    d = t2l.compute_since_arm(csv_path=synthetic_csv, params_path=synthetic_params)
    assert "vix_regime_dayside" not in d["setups"], (
        "extra_setup_exec_armed=False must not surface in the digest")


def test_armed_but_zero_fills_reports_no_fills_since_arm(synthetic_csv, synthetic_params):
    d = t2l.compute_since_arm(csv_path=synthetic_csv, params_path=synthetic_params)
    vrfb = d["setups"]["vwap_reclaim_failed_break"]
    assert vrfb["n_fills"] == 0
    assert vrfb["status"] == "NO_FILLS_SINCE_ARM"
    assert vrfb["total_dollar_pnl"] == 0
    line = [ln for ln in t2l.format_lines(d) if ln.startswith("vwap_reclaim_failed_break")][0]
    assert "0 fills since arm" in line


def test_never_auto_disarms_pure_read_only():
    """Rule 9: the compute/read functions must never WRITE params.json (visibility
    only -- disarm is a J-facing call, per F3's own close)."""
    import inspect
    assert ".write_text" not in inspect.getsource(t2l.compute_since_arm)
    assert ".write_text" not in inspect.getsource(t2l.live_armed_setups)
    assert ".write_text" not in inspect.getsource(t2l.load_real_fills)


def test_arm_dates_cover_every_live_armed_setup():
    """PRESENCE RATCHET (C14): every extra_setup_exec_armed=True key in EITHER live
    params file must have a matching ARM_DATES entry -- else a newly-armed setup
    silently vanishes from the digest (`unmapped_armed_setups` would be non-empty
    and the digest would drop it from the STATUS block without saying so). This
    guard fails LOUD instead: add the setup's real arm date to ARM_DATES.
    """
    live_safe = t2l.live_armed_setups(t2l.PARAMS_JSON)
    missing = [s for s in live_safe if s not in t2l.ARM_DATES]
    assert not missing, (
        f"newly-armed setup(s) with no ARM_DATES entry: {missing} -- "
        f"add the real arm date (git log -S of extra_setup_exec_armed) to "
        f"trade_to_learn_digest.ARM_DATES")

    agg_params = t2l.ROOT / "automation" / "state" / "aggressive" / "params.json"
    if agg_params.exists():
        live_bold = t2l.live_armed_setups(agg_params)
        missing_bold = [s for s in live_bold if s not in t2l.ARM_DATES]
        assert not missing_bold, (
            f"newly-armed Bold setup(s) with no ARM_DATES entry: {missing_bold}")


def test_unmapped_armed_setup_is_surfaced_not_silently_dropped(synthetic_csv, tmp_path):
    """If a setup IS armed but has no ARM_DATES entry, compute_since_arm must still
    surface it via unmapped_armed_setups (never a silent drop) -- and format_lines
    must warn about it."""
    p = tmp_path / "params.json"
    p.write_text(json.dumps({"extra_setup_exec_armed": {"totally_new_setup": True}}),
                 encoding="utf-8")
    d = t2l.compute_since_arm(csv_path=synthetic_csv, params_path=p)
    assert d["unmapped_armed_setups"] == ["totally_new_setup"]
    assert "totally_new_setup" not in d["setups"]
    lines = t2l.format_lines(d)
    assert any("ARM_DATES missing" in ln and "totally_new_setup" in ln for ln in lines)


def test_smoke_against_real_journal_and_params():
    """End-to-end smoke on the REAL journal/trades.csv + params.json -- must not crash,
    must return a dict with the 5 currently-known armed setups (as of 2026-07-18)."""
    d = t2l.compute_since_arm()
    assert d["unmapped_armed_setups"] == []
    for expected in ("vwap_continuation", "vwap_reclaim_failed_break",
                      "vix_regime_dayside", "double_bottom_base_quiet", "bollinger_squeeze"):
        assert expected in d["setups"]
    # real evidence pinned 2026-07-18 (verified live this fire): bollinger_squeeze has
    # fired twice since arm and is net positive; this is a LOOSE non-regression pin
    # (>= 2, not an exact literal) since fresh fills will only ever ADD to it going forward.
    assert d["setups"]["bollinger_squeeze"]["n_fills"] >= 2


def test_real_csv_malformed_quoting_rows_still_parse_early_columns():
    """Known pre-existing defect (found while building this digest, 2026-07-18):
    `archetype_match_json` embeds literal unescaped `"` in some rows' notes text,
    corrupting LATER csv columns (account_id/notes_short) for those rows -- but
    date/setup/dollar_pnl (read BEFORE the bad quote) must still parse clean.
    This test proves the digest is unaffected by that defect, not just asserting
    it away."""
    rows = t2l.load_real_fills()
    # the 2026-07-16 VWAP_CONTINUATION rows are the known malformed-quoting rows;
    # they must still be present with a parseable pnl (not silently dropped).
    matched = [r for r in rows if r["setup_key"] == "vwap_continuation"
               and str(r["date"]) == "2026-07-16"]
    assert len(matched) == 2
    assert {round(r["pnl"]) for r in matched} == {-54, -14}
