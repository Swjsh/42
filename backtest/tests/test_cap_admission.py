"""Unit tests for lib.cap_admission — the order-ADMISSION layer.

The cap is the SINGLE live authority (risk_gate.check_order). These tests pin:
  * the cap boundaries (Safe $600 @ qty3 / Bold $824 @ qty5) EXACTLY, and the
    min_contracts DENY (not shrink);
  * enforce_cap=False returns the book BYTE-IDENTICAL to the input (no behaviour change);
  * enforce_cap=True excludes blocked fills entirely ($0), never qty-reducing;
  * the lib's account sizing tables stay byte-identical to pre_order_gate (one config);
  * median_notional_exceeds_cap (the guard trip-wire) is correct on both sides.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.cap_admission import (  # noqa: E402
    cap_allows,
    decide,
    admit_book,
    median_notional_exceeds_cap,
    params_for,
    SAFE_MAX_PREMIUM_TIERS,
    BOLD_MAX_PREMIUM_TIERS,
    SAFE_RISK_CAP,
    BOLD_RISK_CAP,
)
from lib.risk_gate import CODE_RISK_CAP, CODE_MIN_CONTRACTS  # noqa: E402


@dataclass(frozen=True)
class _Fill:
    """Minimal fill stub exposing the fields admit_book reads."""
    entry_premium: float
    dollar_pnl: float = 0.0
    qty: int = 3


# --- cap boundaries (the single authority, exact) ----------------------------

def test_safe_cap_boundary_exact() -> None:
    # Safe $2,000 -> 0.30 risk cap binds = $600. 2.00*3*100 = $600 == cap -> ALLOW.
    assert cap_allows("safe", 2000.0, 3, 2.00) is True
    # 2.01*3*100 = $603 > $600 -> BLOCK on RISK_CAP.
    assert cap_allows("safe", 2000.0, 3, 2.01) is False
    assert decide("safe", 2000.0, 3, 2.01).code == CODE_RISK_CAP


def test_bold_cap_boundary_exact() -> None:
    # Bold $1,648 -> 0.50 risk cap = $824. 1.648*5*100 = $824 == cap -> ALLOW.
    assert cap_allows("bold", 1648.0, 5, 1.648) is True
    # 1.70*5*100 = $850 > $824 -> BLOCK.
    assert cap_allows("bold", 1648.0, 5, 1.70) is False


def test_min_contracts_denies_not_shrinks() -> None:
    # qty below the floor is a hard DENY even at a trivial premium (never qty-reduced).
    assert cap_allows("safe", 2000.0, 2, 0.50) is False
    assert decide("safe", 2000.0, 2, 0.50).code == CODE_MIN_CONTRACTS
    assert cap_allows("bold", 1648.0, 4, 0.50) is False
    assert decide("bold", 1648.0, 4, 0.50).code == CODE_MIN_CONTRACTS


# --- config parity with pre_order_gate (one config, no drift) ----------------

def test_sizing_tables_match_pre_order_gate() -> None:
    sys.path.insert(0, str(REPO / "automation" / "scripts"))
    import pre_order_gate as pog  # noqa: PLC0415

    assert SAFE_MAX_PREMIUM_TIERS == pog.SAFE_MAX_PREMIUM_TIERS
    assert BOLD_MAX_PREMIUM_TIERS == pog.BOLD_MAX_PREMIUM_TIERS
    assert SAFE_RISK_CAP == pog.SAFE_RISK_CAP
    assert BOLD_RISK_CAP == pog.BOLD_RISK_CAP
    # And the assembled params match the live gate's, key-for-key (the sizing contract).
    assert params_for("safe") == pog._params_for("safe")
    assert params_for("bold") == pog._params_for("bold")


def test_cap_allows_agrees_with_pre_order_gate() -> None:
    """The lib's admission decision must agree with pre_order_gate.check verbatim."""
    sys.path.insert(0, str(REPO / "automation" / "scripts"))
    import pre_order_gate as pog  # noqa: PLC0415
    for acct, equity, qty, prem in [
        ("safe", 2000.0, 3, 2.00), ("safe", 2000.0, 3, 2.01),
        ("safe", 2000.0, 2, 0.50), ("bold", 1648.0, 5, 1.648),
        ("bold", 1648.0, 5, 1.70), ("bold", 1648.0, 4, 0.50),
    ]:
        passed, _ = pog.check(equity, qty, prem, acct)
        assert cap_allows(acct, equity, qty, prem) == passed, (acct, equity, qty, prem)


# --- admit_book: parity (cap-off) + exclusion (cap-on) -----------------------

def test_admit_book_cap_off_is_byte_identical() -> None:
    fills = (_Fill(1.00), _Fill(2.50), _Fill(0.40))   # 2.50 would block Safe @ qty3
    res = admit_book(fills, "safe", 2000.0, 3, enforce_cap=False)
    assert res.enforce_cap is False
    assert res.admitted == fills          # same objects, same order — byte-identical
    assert res.blocked == ()
    assert res.block_rate == 0.0
    assert res.n_total == 3


def test_admit_book_cap_on_excludes_blocked() -> None:
    affordable = _Fill(1.00)              # $300 <= $600 -> admit
    blocked = _Fill(2.50)                 # $750 > $600   -> exclude
    cheap = _Fill(0.40)                   # $120 <= $600  -> admit
    res = admit_book((affordable, blocked, cheap), "safe", 2000.0, 3, enforce_cap=True)
    assert res.enforce_cap is True
    assert res.admitted == (affordable, cheap)   # blocked EXCLUDED, not shrunk
    assert res.blocked == (blocked,)
    assert res.n_total == 3
    assert res.block_rate == round(1 / 3, 4)
    assert res.block_codes.get(CODE_RISK_CAP) == 1


def test_admit_book_empty_book() -> None:
    res = admit_book((), "safe", 2000.0, 3, enforce_cap=True)
    assert res.admitted == () and res.blocked == ()
    assert res.n_total == 0 and res.block_rate == 0.0


def test_admit_book_all_admitted_when_cheap() -> None:
    fills = tuple(_Fill(p) for p in (0.50, 1.00, 1.50, 1.99))   # all <= $600 @ qty3
    res = admit_book(fills, "safe", 2000.0, 3, enforce_cap=True)
    assert res.admitted == fills and res.block_rate == 0.0


# --- median_notional_exceeds_cap (the guard trip-wire) -----------------------

def test_median_notional_trip_wire() -> None:
    # Median premium $2.50 @ qty3 = $750 > $600 -> the config's median order is BLOCKED.
    expensive = tuple(_Fill(p) for p in (2.40, 2.50, 2.60))
    assert median_notional_exceeds_cap(expensive, "safe", 2000.0, 3) is True
    # Median premium $1.00 @ qty3 = $300 <= $600 -> within the cap.
    cheap = tuple(_Fill(p) for p in (0.80, 1.00, 1.20))
    assert median_notional_exceeds_cap(cheap, "safe", 2000.0, 3) is False
    # Empty book -> nothing to assert -> False (no trip).
    assert median_notional_exceeds_cap((), "safe", 2000.0, 3) is False


def test_unknown_account_raises() -> None:
    with pytest.raises(ValueError):
        params_for("wat")
