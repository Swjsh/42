"""Guards for the SIZING-DEADLOCK diagnostic (2026-07-30 incident).

THE INCIDENT. Core Safe ran a full session at equity $1,160.42 and produced 9 x
RISK_DENY_RISK_CAP. Every one was a STRUCTURAL deadlock, not an oversize proposal:

    per_trade_risk_cap_pct 0.30 x $1,160.42 = $348.13 effective cap
    min_contracts 3 x premium x 100         = $426-$603 notional (ATM 0DTE $1.42-$2.01)
    => max_affordable_qty == 0 at EVERY price quoted that day.

The ledger could not say so — a deadlock row and an ordinary "too big, size down" row
were textually indistinguishable. These guards pin the diagnostic that fixes that, and
pin it AGAINST the real gate so the two can never silently diverge (C14).

WHAT EACH GUARD WOULD CATCH (RED-proof targets):
  * test_deadlock_matches_check_order_over_grid — explain_block()["deadlock"] disagreeing
    with what check_order actually does. This is the anti-divergence guard: if someone
    re-types cap math in explain_block instead of calling the shared helpers, this REDs.
  * test_incident_2026_07_30_* — the exact live numbers from the incident.
  * test_ceiling_is_floored_to_the_cent — a ceiling that ROUNDS UP would print a premium
    the gate refuses (bold-2: 1.1975 -> "$1.20" but $1.20 is still a deadlock).
  * test_explain_block_fails_open_* — monitoring must NEVER raise into the entry path.
  * test_explain_block_never_mentions_equity_dollar — free_model_audit_heartbeat_veto.py
    regex-scrapes `equity \\$N` from the SERIALIZED decision row; a second such substring
    in this block could shadow the real one and corrupt that audit's equity_hint.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest/lib", "automation/state/fleet"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import risk_gate as rg  # noqa: E402

# --- the two REAL param shapes, read from disk (never re-typed literals) -------
SAFE_PARAMS = json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
BOLD_PARAMS = json.loads(
    (REPO / "automation" / "state" / "aggressive" / "params.json").read_text(encoding="utf-8"))

# Live-verified equities, 2026-07-30 18:4x ET (accounts_status.py / Alpaca REST).
EQ_SAFE_2 = 1160.42
EQ_BOLD_2 = 1197.52


def _check_order_denies_for_cap(equity, premium, qty, params) -> bool:
    """True iff the REAL gate refuses this order for a per-order SIZING reason."""
    d = rg.check_order(
        "test", equity=equity, start_of_day_equity=equity, proposed_qty=qty,
        premium=premium, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
        current_position_status=None, day_trades_used_5d=0, kill_switch_tripped=False,
        prior_stops_today=[], params={**params, "pdt_gate_mode": "margin_pdt"},
    )
    return (not d.allowed) and d.code in (
        rg.CODE_RISK_CAP, rg.CODE_MAX_PREMIUM_TIER, rg.CODE_MIN_CONTRACTS)


# --- 1. ANTI-DIVERGENCE: the diagnostic must agree with the real gate ---------
@pytest.mark.parametrize("params", [SAFE_PARAMS, BOLD_PARAMS], ids=["safe", "bold"])
def test_deadlock_matches_check_order_over_grid(params):
    """`deadlock` is True EXACTLY when no qty >= min_contracts clears check_order.

    Cross-checked against the live gate over an equity x premium grid, so a future
    edit that re-derives cap math inside explain_block (instead of calling the shared
    helpers) cannot silently drift.
    """
    min_c = int(params["min_contracts"])
    checked = 0
    for equity in (500.0, 900.0, 1160.42, 1197.52, 1500.0, 1893.04, 2000.0, 2500.0, 5000.0):
        for premium in (0.31, 0.50, 0.90, 1.16, 1.20, 1.42, 1.89, 2.01, 2.80, 5.00):
            exp = rg.explain_block(equity=equity, premium=premium, params=params)
            assert exp["available"], exp
            # Ground truth: does ANY legal qty clear the real gate?
            any_qty_ok = any(
                not _check_order_denies_for_cap(equity, premium, q, params)
                for q in range(min_c, min_c + 60)
            )
            assert exp["deadlock"] is (not any_qty_ok), (
                f"equity={equity} premium={premium} min_contracts={min_c}: "
                f"explain_block.deadlock={exp['deadlock']} but real gate "
                f"any_qty_ok={any_qty_ok}"
            )
            checked += 1
    assert checked == 90, "grid shrank — the anti-divergence guard lost coverage"


def test_max_affordable_qty_agrees_with_deadlock_flag():
    """deadlock is definitionally max_affordable_qty == 0 — pinned, both directions."""
    for equity, premium, params in (
        (EQ_SAFE_2, 1.42, SAFE_PARAMS),   # the incident
        (EQ_SAFE_2, 1.00, SAFE_PARAMS),   # affordable
        (EQ_BOLD_2, 2.12, BOLD_PARAMS),   # bold, incident-day premium
        (EQ_BOLD_2, 1.00, BOLD_PARAMS),   # affordable
    ):
        exp = rg.explain_block(equity=equity, premium=premium, params=params)
        afford = rg.max_affordable_qty(equity=equity, premium=premium, params=params)
        assert exp["max_affordable_qty"] == afford
        assert exp["deadlock"] is (afford == 0)


# --- 2. THE INCIDENT, pinned to the live numbers ------------------------------
@pytest.mark.parametrize("premium", [1.42, 1.52, 1.56, 1.58, 1.63, 1.88, 1.94, 2.00, 2.01])
def test_incident_2026_07_30_every_denied_premium_is_a_deadlock(premium):
    """All 9 core-Safe RISK_DENY_RISK_CAP premiums from 2026-07-30 were deadlocks.

    Premiums sourced verbatim from automation/state/core-decisions.jsonl rows
    2026-07-30T11:32:02..11:46:02 (account=safe).
    """
    exp = rg.explain_block(equity=EQ_SAFE_2, premium=premium, params=SAFE_PARAMS,
                           proposed_qty=3)
    assert exp["available"]
    assert exp["deadlock"] is True, f"${premium} should be a deadlock at ${EQ_SAFE_2}"
    assert exp["max_affordable_qty"] == 0
    assert "DEADLOCK" in exp["headline"]


def test_incident_2026_07_30_safe_ceiling_is_1_16():
    """The operator-facing number: core Safe could not trade above $1.16/contract."""
    exp = rg.explain_block(equity=EQ_SAFE_2, premium=1.00, params=SAFE_PARAMS)
    assert exp["effective_cap_dollars"] == pytest.approx(348.13, abs=0.01)
    assert exp["binding_cap"] == "risk_cap"  # 0.30 blanket beats the 0.40 tier at this equity
    assert exp["premium_ceiling_cents"] == 1.16
    # And the ceiling is REAL: $1.16 clears, one cent more does not.
    assert rg.max_affordable_qty(equity=EQ_SAFE_2, premium=1.16, params=SAFE_PARAMS) == 3
    assert rg.max_affordable_qty(equity=EQ_SAFE_2, premium=1.17, params=SAFE_PARAMS) == 0


def test_ceiling_is_floored_to_the_cent_not_rounded():
    """bold-2's raw ceiling is 1.1975. Rounding renders "$1.20" — a price the gate REFUSES.

    Guards the operator-facing string: a ceiling must never name an untradeable premium.
    """
    exp = rg.explain_block(equity=EQ_BOLD_2, premium=2.12, params=BOLD_PARAMS)
    assert exp["premium_ceiling"] == pytest.approx(1.1975, abs=1e-4)
    assert exp["premium_ceiling_cents"] == 1.19, "ceiling must FLOOR to the cent"
    assert "$1.19/contract" in exp["headline"]
    # Proof the distinction is real, not pedantic:
    assert rg.max_affordable_qty(equity=EQ_BOLD_2, premium=1.19, params=BOLD_PARAMS) == 5
    assert rg.max_affordable_qty(equity=EQ_BOLD_2, premium=1.20, params=BOLD_PARAMS) == 0


def test_sizing_miss_is_not_labelled_a_deadlock():
    """The other half of the distinction: a too-big proposal that CAN size down."""
    # Safe at $2,500: cap = min(0.30, tier 0.30) x 2500 = $750 -> 6 contracts at $1.25.
    exp = rg.explain_block(equity=2500.0, premium=1.25, params=SAFE_PARAMS, proposed_qty=20)
    assert exp["deadlock"] is False
    assert exp["max_affordable_qty"] >= int(SAFE_PARAMS["min_contracts"])
    assert exp["headline"].startswith("SIZING:")
    assert exp["proposed_qty"] == 20
    assert exp["proposed_notional"] == pytest.approx(1.25 * 20 * 100)


# --- 3. FAIL-OPEN: monitoring must never raise into the entry path ------------
@pytest.mark.parametrize("kwargs", [
    {"equity": None, "premium": 1.0, "params": SAFE_PARAMS},
    {"equity": float("nan"), "premium": 1.0, "params": SAFE_PARAMS},
    {"equity": -5.0, "premium": 1.0, "params": SAFE_PARAMS},
    {"equity": 1000.0, "premium": None, "params": SAFE_PARAMS},
    {"equity": 1000.0, "premium": 0.0, "params": SAFE_PARAMS},
    {"equity": 1000.0, "premium": 1.0, "params": None},
    {"equity": 1000.0, "premium": 1.0, "params": "not-a-mapping"},
    {"equity": 1000.0, "premium": 1.0, "params": {}},
    {"equity": 1000.0, "premium": 1.0, "params": {"min_contracts": "abc"}},
])
def test_explain_block_fails_open_never_raises(kwargs):
    out = rg.explain_block(**kwargs)
    assert out["available"] is False
    assert "why" in out


def test_explain_block_fails_open_on_uncovered_tier():
    """Equity outside every v15 tier = the same uncertainty check_order denies on.

    The diagnostic must REPORT it, not guess a cap.
    """
    p = dict(SAFE_PARAMS)
    p["v15_max_premium_pct_of_account"] = [
        {"equity_min": 0, "equity_max": 100, "max_pct": 0.4}]
    out = rg.explain_block(equity=50_000.0, premium=1.0, params=p)
    assert out["available"] is False
    assert "tier" in out["why"]


def test_min_equity_for_premium_uses_scan_not_bisection():
    """The cap is NOT monotonic in equity — a bisection would return a wrong answer.

    v15 tiers step DOWN (0.40 -> 0.30 -> 0.25 -> 0.20), so cap($9,999) = $2,999.70 but
    cap($10,000) = $2,500. This pins the real non-monotonicity AND the scan's answer.
    """
    assert rg._effective_per_trade_cap_dollars(9_999.0, SAFE_PARAMS) > \
        rg._effective_per_trade_cap_dollars(10_000.0, SAFE_PARAMS), \
        "expected a cap DROP across the $10K tier boundary"
    # Safe: min_contracts 3, cap 0.30 -> need equity >= premium * 3 * 100 / 0.30 = premium * 1000
    got = rg.min_equity_for_premium(premium=1.42, params=SAFE_PARAMS)
    assert got == pytest.approx(1420.0, abs=1.0)
    assert rg.max_affordable_qty(equity=got, premium=1.42, params=SAFE_PARAMS) >= 3
    assert rg.min_equity_for_premium(premium=1.42, params=None) is None


# --- 4. The ledger-scraper contract ------------------------------------------
def test_explain_block_never_mentions_equity_dollar():
    """free_model_audit_heartbeat_veto._scan_equity_hint regexes `equity \\$N` out of the
    SERIALIZED decision row and takes the FIRST match. A second such substring introduced
    by this telemetry could shadow the real one. Numeric fields only — never that prose.
    """
    import re

    blob = json.dumps(rg.explain_block(equity=EQ_SAFE_2, premium=1.42, params=SAFE_PARAMS,
                                       proposed_qty=3))
    assert not re.search(r"equity \$[0-9]", blob), \
        "binding telemetry must not emit an 'equity $N' substring (shadows equity_hint)"


def test_binding_block_is_json_serialisable():
    """It rides into decisions.jsonl — every value must be JSON-native."""
    for params, eq in ((SAFE_PARAMS, EQ_SAFE_2), (BOLD_PARAMS, EQ_BOLD_2)):
        blob = json.dumps(rg.explain_block(equity=eq, premium=1.42, params=params,
                                           proposed_qty=3))
        assert json.loads(blob)["available"] is True


# --- 5. check_order itself is UNCHANGED by any of this ------------------------
def test_check_order_behaviour_unchanged_by_diagnostic():
    """The diagnostic decides nothing. An allowable order still ALLOWs; the incident
    order still denies with the same code — explain_block is pure telemetry."""
    allow = rg.check_order(
        "safe", equity=EQ_SAFE_2, start_of_day_equity=EQ_SAFE_2, proposed_qty=3,
        premium=1.00, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
        current_position_status=None, day_trades_used_5d=0, kill_switch_tripped=False,
        prior_stops_today=[], params={**SAFE_PARAMS, "pdt_gate_mode": "margin_pdt"})
    assert allow.allowed is True

    deny = rg.check_order(
        "safe", equity=EQ_SAFE_2, start_of_day_equity=EQ_SAFE_2, proposed_qty=3,
        premium=1.42, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
        current_position_status=None, day_trades_used_5d=0, kill_switch_tripped=False,
        prior_stops_today=[], params={**SAFE_PARAMS, "pdt_gate_mode": "margin_pdt"})
    assert deny.allowed is False and deny.code == rg.CODE_RISK_CAP
