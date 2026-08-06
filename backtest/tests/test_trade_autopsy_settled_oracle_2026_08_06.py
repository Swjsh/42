"""Guards for the two 2026-08-06 trade_autopsy.py fixes.

FIX 1 -- SETTLED hypotheses stop re-emitting.
    `H-*-stop-noise` (mechanism `stop_inside_noise_floor`) auto-emitted on 07-08, 07-16,
    07-21, 07-29 and 08-04 and was never run until 2026-08-06. HYP_DEDUPE_DAYS=7 is a
    COOLDOWN, not an answer, so an answered question returned weekly forever.

FIX 2 -- the hold_to_time ORACLE stops setting the headline number.
    hold_to_time is premium_stop -95% / tp1 999 / runner 999: it holds the full position
    to the time exit with effectively no stop, so it wins "best counterfactual" on every
    trend day BY CONSTRUCTION and loses worst on reversal days. It was being mixed into
    max(ALL counterfactuals), which set `stop_cost_vs_best` -- the "$ left on the table"
    figure J reads weekly (the misleading $6,976-on-a--$104-trade shape).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "setup" / "scripts"))

import trade_autopsy as ta  # noqa: E402


TODAY = "2026-08-06"
STOP_NOISE = {"id": f"H-{TODAY}-stop-noise", "mechanism": "stop_inside_noise_floor"}
OTHER = {"id": f"H-{TODAY}-entry-spike", "mechanism": "paying_the_signal_spike"}


# ------------------------------------------------------------- FIX 1: SETTLED

def test_settled_mechanism_is_suppressed_forever():
    """THE incident: 5 emissions of an unanswered-then-answered question."""
    settled = {"stop_inside_noise_floor": {"mechanism": "stop_inside_noise_floor"}}
    out = ta.dedupe_hypotheses([STOP_NOISE], existing_rows=[], today=TODAY, settled=settled)
    assert out == [], "a SETTLED mechanism must not re-emit"


def test_settled_suppression_survives_the_cooldown_window():
    """Past HYP_DEDUPE_DAYS the cooldown lapses; SETTLED must still hold."""
    settled = {"stop_inside_noise_floor": {"mechanism": "stop_inside_noise_floor"}}
    stale = [{"mechanism": "stop_inside_noise_floor", "date": "2026-01-01"}]
    assert ta.dedupe_hypotheses([STOP_NOISE], stale, TODAY, settled) == []


def test_unsettled_mechanisms_still_emit():
    """The registry must silence ONE mechanism, not the whole queue."""
    settled = {"stop_inside_noise_floor": {"mechanism": "stop_inside_noise_floor"}}
    out = ta.dedupe_hypotheses([STOP_NOISE, OTHER], [], TODAY, settled)
    assert [h["mechanism"] for h in out] == ["paying_the_signal_spike"]


def test_cooldown_still_works_with_no_registry():
    """Back-compat: the settled arg is optional and defaults to no suppression."""
    recent = [{"mechanism": "stop_inside_noise_floor", "date": TODAY}]
    assert ta.dedupe_hypotheses([STOP_NOISE], recent, TODAY) == []
    assert ta.dedupe_hypotheses([STOP_NOISE], [], TODAY) == [STOP_NOISE]


def test_revisit_after_reopens_on_the_stated_date():
    settled = {"stop_inside_noise_floor": {"mechanism": "stop_inside_noise_floor",
                                           "revisit_after": "2026-09-01"}}
    assert ta.is_settled("stop_inside_noise_floor", settled, "2026-08-06") is True
    assert ta.is_settled("stop_inside_noise_floor", settled, "2026-09-01") is False


def test_null_revisit_after_means_settled_indefinitely():
    settled = {"m": {"mechanism": "m", "revisit_after": None}}
    assert ta.is_settled("m", settled, "2099-01-01") is True


def test_missing_or_corrupt_registry_fails_open(tmp_path, monkeypatch):
    """A broken registry must silence NOTHING -- never everything."""
    monkeypatch.setattr(ta, "SETTLED_HYP", tmp_path / "nope.json")
    assert ta.load_settled_mechanisms() == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(ta, "SETTLED_HYP", bad)
    assert ta.load_settled_mechanisms() == {}


def test_shipped_registry_settles_the_recurring_stop_noise_hypothesis():
    """The real on-disk registry must actually answer the incident mechanism."""
    rows = ta.load_settled_mechanisms()
    assert "stop_inside_noise_floor" in rows, "the 5x-repeated hypothesis is still unsettled"
    row = rows["stop_inside_noise_floor"]
    assert row.get("verdict"), "a settled row must carry a verdict"
    assert row.get("evidence"), "a settled row must cite its evidence artifact"


def test_shipped_registry_is_valid_json_with_expected_shape():
    payload = json.loads(ta.SETTLED_HYP.read_text(encoding="utf-8-sig"))
    assert isinstance(payload.get("settled"), list) and payload["settled"]
    for row in payload["settled"]:
        assert row.get("mechanism") and row.get("verdict") and row.get("evidence")


# ------------------------------------------------------------- FIX 2: ORACLE

def _cf(**kw):
    base = {"wide_stop_-50": 10.0, "no_stop_ride": 20.0, "hold_to_time": 5000.0}
    base.update(kw)
    return base


def test_oracle_never_becomes_best_counterfactual():
    """THE incident shape: a huge hold_to_time must not set the headline number."""
    r = ta.classify_position(actual_pnl=-104.0, entry_price=1.0, entry_bar_low=1.0,
                             post_exit_high=None, cf_pnls=_cf())
    assert r["best_counterfactual"] != "hold_to_time"
    assert r["best_counterfactual"] == "no_stop_ride"
    assert r["stop_cost_vs_best"] == 124.0, "must be 20.0 - (-104.0), not 5000 - (-104)"


def test_oracle_is_still_reported_separately():
    """Quarantined, not deleted -- the diagnostic question survives."""
    r = ta.classify_position(-104.0, 1.0, 1.0, None, _cf())
    assert r["oracle_best_pnl"] == 5000.0
    assert r["oracle_delta_vs_actual"] == 5104.0
    assert "not shippable" in r["oracle_note"]


def test_hold_to_time_is_registered_as_diagnostic():
    assert "hold_to_time" in ta.DIAGNOSTIC_COUNTERFACTUALS


def test_every_diagnostic_name_is_a_real_counterfactual():
    """A typo'd name in the frozenset would silently quarantine nothing."""
    for name in ta.DIAGNOSTIC_COUNTERFACTUALS:
        assert name in ta.COUNTERFACTUALS, f"{name} is not a defined counterfactual"


def test_at_least_one_shippable_counterfactual_remains():
    """Quarantining must never empty the shippable set."""
    assert set(ta.COUNTERFACTUALS) - set(ta.DIAGNOSTIC_COUNTERFACTUALS)


def test_exit_beat_theta_tag_still_uses_the_oracle():
    """The honesty tag ('our exit was RIGHT vs riding') must keep working."""
    r = ta.classify_position(-50.0, 1.0, 1.0, None, _cf(hold_to_time=-900.0))
    assert "exit_beat_theta" in r["tags"]


def test_all_diagnostic_cfs_yields_no_best_rather_than_an_oracle_best():
    r = ta.classify_position(-100.0, 1.0, 1.0, None, {"hold_to_time": 5000.0})
    assert r["best_counterfactual"] is None
    assert r["stop_cost_vs_best"] is None
    assert r["oracle_best_pnl"] == 5000.0
