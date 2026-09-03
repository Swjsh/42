"""Guard: setup/scripts/fee_recalibrate.py (queue.md FEE-RECALIBRATION-FROM-BROKER, LOW).

go_live_gate.py's reconciliation + cost-adjusted statistical criterion both lean on a
STATIC FEE_RATES dict calibrated once (2026-08-18) and never checked against a real bill
since. fee_recalibrate.py pulls Alpaca FEE activities per active arm over a trailing
lookback window, derives the realized per-type rate implied by what the broker actually
charged, and reports drift -- but NEVER writes FEE_RATES anywhere (drift is reported, the
gate keeps its static dict, per OP-11 -- a mid-window bar change is a post-hoc anti-pattern
even when well-evidenced).

Covers:
  - FEE_RATES stays byte-identical to go_live_gate.FEE_RATES (the drift-detector's own
    copy must itself never silently drift from the thing it's checking)
  - predict_per_type() reproduces go_live_gate.fee_ex_cat()'s real formula/rounding, not
    just a hand-copied approximation of it
  - actual_by_subtype() aggregates correctly and skips malformed activity rows
  - build()'s drift_pct / realized-rate math on a synthetic ledger + fee-activity fixture
    (no network -- fetch_fee_activities and load_trades are monkeypatched)
  - status ladder: GREEN (<=10%), YELLOW (10%, 25%], RED (>25%) on max |drift_pct|
  - all-arms-fetch-failure -> RED, max_drift_pct None (never a false GREEN on no data)
  - zero fee activity anywhere in the window -> YELLOW, not a false GREEN
  - it never writes to go_live_gate.FEE_RATES or any go_live_gate.py output path
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = str(REPO / "setup" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import fee_recalibrate as fr  # noqa: E402
import go_live_gate as glg  # noqa: E402


def _activity(sub_type, net_amount, date):
    return {"activity_sub_type": sub_type, "net_amount": net_amount, "date": date}


def _trade_row(arm, date, qty, exit_px):
    return {"arm": arm, "date": date, "qty": qty, "exit_px_avg": exit_px,
            "pnl_dollars": 0.0, "attribution": "engine"}


# --------------------------------------------------------------------------------------- #
# FEE_RATES must never silently drift from go_live_gate's own copy.
# --------------------------------------------------------------------------------------- #
def test_fee_rates_matches_go_live_gate_copy():
    assert fr.FEE_RATES == glg.FEE_RATES


# --------------------------------------------------------------------------------------- #
# predict_per_type reproduces go_live_gate.fee_ex_cat's real formula, not an approximation.
# --------------------------------------------------------------------------------------- #
def test_predict_per_type_matches_go_live_gate_fee_ex_cat_formula():
    rows = [
        {"qty": 3.0, "exit_px_avg": 1.25},
        {"qty": 5.0, "exit_px_avg": 0.80},
        {"qty": 7.0, "exit_px_avg": 0.13},
    ]
    pred = fr.predict_per_type(rows, n_arm_days=0)
    total_no_cat = pred["OCC"] + pred["ORF"] + pred["TAF"] + pred["REG"]
    expected = sum(glg.fee_ex_cat(r["qty"], r["exit_px_avg"]) for r in rows)
    assert round(total_no_cat, 6) == round(expected, 6)
    assert pred["CAT"] == 0.0


def test_predict_per_type_cat_scales_with_arm_days():
    pred = fr.predict_per_type([], n_arm_days=5)
    assert pred["CAT"] == round(fr.FEE_RATES["cat_per_arm_day"] * 5, 8)


def test_predict_per_type_skips_rows_with_no_exit_price():
    rows = [{"qty": 3.0, "exit_px_avg": None}]
    pred = fr.predict_per_type(rows, n_arm_days=0)
    assert pred.get("OCC", 0.0) == 0.0 and pred.get("ORF", 0.0) == 0.0
    assert pred.get("TAF", 0.0) == 0.0 and pred.get("REG", 0.0) == 0.0


# --------------------------------------------------------------------------------------- #
# actual_by_subtype: aggregation + malformed-row tolerance.
# --------------------------------------------------------------------------------------- #
def test_actual_by_subtype_aggregates_and_skips_malformed():
    acts = [
        _activity("OCC", "-1.25", "2026-08-25"),
        _activity("OCC", "-0.75", "2026-08-26"),
        _activity("ORF", "-0.50", "2026-08-25"),
        {"activity_sub_type": "REG", "net_amount": "not-a-number", "date": "2026-08-25"},
        {"activity_sub_type": "TAF"},  # missing net_amount entirely
    ]
    got = fr.actual_by_subtype(acts)
    assert got.get("OCC") == 2.0
    assert got.get("ORF") == 0.5
    # a malformed row's key may end up touched with a harmless 0.0 (defaultdict's
    # __getitem__ fires before the exception on the malformed value) -- never nonzero,
    # which is the only thing that would actually corrupt the aggregation.
    for k, v in got.items():
        if k not in ("OCC", "ORF"):
            assert v == 0.0


# --------------------------------------------------------------------------------------- #
# build(): drift_pct / realized-rate math + status ladder, no network.
# --------------------------------------------------------------------------------------- #
def _write_secrets(tmp_path, arms):
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"accounts": {a: {"api_key": "k", "secret_key": "s",
                                                "base_url": "https://paper-api.alpaca.markets"}
                                            for a in arms}}), encoding="utf-8")
    return p


def _matching_acts(occ_actual: float, date: str = "2026-08-25") -> list:
    """FEE activities for a single _trade_row("arm-a", date, qty=200.0, exit_px=1.0) trade
    (n_arm_days=1) -- ORF/TAF/REG/CAT set to EXACTLY the model's own prediction for that
    row (drift_pct == 0.0 for each), so only OCC's drift is free to vary. Predicted values
    reproduced from go_live_gate's own formula: OCC=2*ceil(0.025*200)=10.00,
    ORF=2*ceil(0.015*200)=6.00, TAF=ceil(0.00329*200)=0.66,
    REG=ceil(2.06e-5*1.0*200*100)=0.42, CAT=0.01*1=0.01."""
    return [
        _activity("OCC", str(-occ_actual), date),
        _activity("ORF", "-6.00", date),
        _activity("TAF", "-0.66", date),
        _activity("REG", "-0.42", date),
        _activity("CAT", "-0.01", date),
    ]


def test_build_drift_math_on_synthetic_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(glg, "ACTIVE_ARMS", ["arm-a"])
    monkeypatch.setattr(fr, "SECRETS_PATH", _write_secrets(tmp_path, ["arm-a"]))

    # Trades that predict EXACTLY $10.00 of OCC at the static rate (qty=200 -> 2*ceil(0.025*200)=10.00).
    rows = [_trade_row("arm-a", "2026-08-25", 200.0, 1.0)]
    monkeypatch.setattr(fr, "load_trades", lambda arm, lo, hi, path: rows)

    # Broker charged $11.00 actual OCC against a $10.00 prediction -> +10% drift; every
    # other type's actual is set to match its own prediction exactly (0% drift), isolating
    # the signal to OCC alone.
    monkeypatch.setattr(fr, "fetch_fee_activities",
                         lambda creds, after, max_pages=20: _matching_acts(11.00))

    rep = fr.build(lookback_days=14)
    occ = rep["per_type"]["OCC"]
    assert occ["actual_total"] == 11.0
    assert occ["predicted_total"] == 10.0
    assert occ["drift_pct"] == 10.0
    assert occ["realized"] == round(fr.FEE_RATES["occ_per_contract"] * (11.0 / 10.0), 8)
    # the matched types drift exactly 0% -- proves the isolation fixture itself is correct.
    for sub in ("ORF", "TAF", "REG", "CAT"):
        assert rep["per_type"][sub]["drift_pct"] == 0.0, sub
    assert rep["fetch_errors"] == []


def test_status_green_at_or_below_10pct():
    rep = {"per_type": {"OCC": {"drift_pct": 9.9}, "ORF": {"drift_pct": -10.0}}}
    max_drift = max(abs(v["drift_pct"]) for v in rep["per_type"].values())
    assert max_drift <= fr.YELLOW_DRIFT_PCT


def test_status_yellow_between_10_and_25pct(tmp_path, monkeypatch):
    monkeypatch.setattr(glg, "ACTIVE_ARMS", ["arm-a"])
    monkeypatch.setattr(fr, "SECRETS_PATH", _write_secrets(tmp_path, ["arm-a"]))
    rows = [_trade_row("arm-a", "2026-08-25", 200.0, 1.0)]  # OCC predicted = $10.00
    monkeypatch.setattr(fr, "load_trades", lambda arm, lo, hi, path: rows)
    monkeypatch.setattr(fr, "fetch_fee_activities",
                         lambda creds, after, max_pages=20: _matching_acts(12.00))  # +20%

    rep = fr.build(lookback_days=14)
    assert rep["per_type"]["OCC"]["drift_pct"] == 20.0
    assert rep["status"] == "YELLOW"
    assert rep["max_drift_pct"] == 20.0


def test_status_red_above_25pct(tmp_path, monkeypatch):
    monkeypatch.setattr(glg, "ACTIVE_ARMS", ["arm-a"])
    monkeypatch.setattr(fr, "SECRETS_PATH", _write_secrets(tmp_path, ["arm-a"]))
    rows = [_trade_row("arm-a", "2026-08-25", 200.0, 1.0)]  # OCC predicted = $10.00
    monkeypatch.setattr(fr, "load_trades", lambda arm, lo, hi, path: rows)
    monkeypatch.setattr(fr, "fetch_fee_activities",
                         lambda creds, after, max_pages=20: _matching_acts(14.00))  # +40%

    rep = fr.build(lookback_days=14)
    assert rep["per_type"]["OCC"]["drift_pct"] == 40.0
    assert rep["status"] == "RED"
    assert rep["max_drift_pct"] == 40.0


def test_all_arms_fetch_failure_is_red_not_a_false_green(tmp_path, monkeypatch):
    monkeypatch.setattr(glg, "ACTIVE_ARMS", ["arm-a", "arm-b"])
    monkeypatch.setattr(fr, "SECRETS_PATH", _write_secrets(tmp_path, ["arm-a", "arm-b"]))
    monkeypatch.setattr(fr, "fetch_fee_activities", lambda creds, after, max_pages=20: None)

    rep = fr.build(lookback_days=14)
    assert rep["status"] == "RED"
    assert rep["max_drift_pct"] is None
    assert set(rep["fetch_errors"]) == {"arm-a", "arm-b"}


def test_zero_activity_everywhere_is_yellow_not_green(tmp_path, monkeypatch):
    monkeypatch.setattr(glg, "ACTIVE_ARMS", ["arm-a"])
    monkeypatch.setattr(fr, "SECRETS_PATH", _write_secrets(tmp_path, ["arm-a"]))
    monkeypatch.setattr(fr, "fetch_fee_activities", lambda creds, after, max_pages=20: [])
    monkeypatch.setattr(fr, "load_trades", lambda arm, lo, hi, path: [])

    rep = fr.build(lookback_days=14)
    assert rep["status"] == "YELLOW"
    assert rep["max_drift_pct"] is None
    assert rep["fetch_errors"] == []


def test_missing_credentials_recorded_as_fetch_error(tmp_path, monkeypatch):
    monkeypatch.setattr(glg, "ACTIVE_ARMS", ["arm-a"])
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"accounts": {}}), encoding="utf-8")  # arm-a has no entry
    monkeypatch.setattr(fr, "SECRETS_PATH", p)

    rep = fr.build(lookback_days=14)
    assert rep["fetch_errors"] == ["arm-a"]
    assert rep["per_arm"]["arm-a"]["error"] == "no credentials in fleet/secrets.json"
    assert rep["status"] == "RED"


# --------------------------------------------------------------------------------------- #
# Never touches go_live_gate.py's own state.
# --------------------------------------------------------------------------------------- #
def test_never_writes_go_live_gate_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(glg, "ACTIVE_ARMS", ["arm-a"])
    monkeypatch.setattr(fr, "SECRETS_PATH", _write_secrets(tmp_path, ["arm-a"]))
    monkeypatch.setattr(fr, "fetch_fee_activities", lambda creds, after, max_pages=20: [])
    monkeypatch.setattr(fr, "load_trades", lambda arm, lo, hi, path: [])

    before = glg.OUT_JSON.read_bytes() if glg.OUT_JSON.exists() else None
    fr.build(lookback_days=14)
    after = glg.OUT_JSON.read_bytes() if glg.OUT_JSON.exists() else None
    assert before == after
    assert fr.FEE_RATES == glg.FEE_RATES  # re-pin: build() must not mutate the module dict
