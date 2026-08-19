"""Guard: option_symbol() multi-root OCC symbol generalization (2026-08-18).

Covers the weekly-options-lane workstream in markdown/planning/WEEKLY-OPTIONS-PROGRAM.md
§5 "New" -- `option_symbol()` gained a `root` keyword parameter (default "SPY") so the
weekly lane can build real OCC symbols for GLD/QQQ/NVDA/TSLA/AAPL, not just SPY.

Two independent kinds of proof:
  1. BACKWARD COMPAT -- every existing 3-positional-arg call site must be byte-identical
     to its pre-2026-08-18 output. Pinned against TWO independently-known-good real
     strings already asserted elsewhere in this repo (not invented here).
  2. MULTI-ROOT CORRECTNESS -- round-trips real OCC symbols pulled from J's actual
     historical WeBull fills (analysis/webull-j-trades/j_roundtrips.json) for both a
     3-char root (SPY/GLD/QQQ) and a 4-char root (NVDA/TSLA/AAPL), proving the function
     does NOT pad the root to a fixed width (that would break both backward-compat and
     real-world correctness -- see option_symbol's own docstring for why).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.option_pricing_real import option_symbol  # noqa: E402


# --------------------------------------------------------------- backward compatibility

def test_existing_spy_positional_call_byte_identical_bull_gate_pin():
    """Matches test_bull_gate_f5class_requal_2026_08_01.py:178's independent assertion --
    same inputs, same expected output, proving option_symbol's SPY behavior did not move
    when the `root` kwarg was added."""
    assert option_symbol(dt.date(2026, 7, 31), 746, "C") == "SPY260731C00746000"


def test_existing_spy_positional_call_byte_identical_winter_opra_pin():
    """Matches test_et_frame_guards.py's WINTER_OPRA cache filename
    (backtest/data/options/SPY250102C00580000.csv) -- an independent real-cache-file
    ground truth, not invented for this guard."""
    assert option_symbol(dt.date(2025, 1, 2), 580, "C") == "SPY250102C00580000"


def test_default_root_kwarg_matches_explicit_spy():
    """The new `root` parameter's default must be indistinguishable from every one of the
    ~250 existing 3-positional-arg call sites -- explicit root="SPY" must produce the
    exact same string as omitting it."""
    d, strike, side = dt.date(2026, 8, 18), 645, "P"
    assert option_symbol(d, strike, side) == option_symbol(d, strike, side, root="SPY")


# -------------------------------------------------------- multi-root real-world round trip

# Ground truth: J's own real historical fills, analysis/webull-j-trades/j_roundtrips.json.
# Not invented -- these are the exact symbol strings that file records.
_REAL_OCC_SYMBOLS = [
    # (root, trade_date, strike, side, expected_symbol)
    ("TSLA", dt.date(2021, 6, 11), 620, "C", "TSLA210611C00620000"),   # 4-char root
    ("NVDA", dt.date(2021, 6, 18), 795, "C", "NVDA210618C00795000"),   # 4-char root
    ("AAPL", dt.date(2021, 7, 16), 145, "C", "AAPL210716C00145000"),   # 4-char root
    ("QQQ", dt.date(2021, 7, 23), 365, "C", "QQQ210723C00365000"),     # 3-char root
    ("TSLA", dt.date(2021, 11, 26), 1290, "C", "TSLA211126C01290000"),  # tests strike>=1000
]


@pytest.mark.parametrize("root,trade_date,strike,side,expected", _REAL_OCC_SYMBOLS)
def test_multi_root_matches_real_webull_fill_symbols(root, trade_date, strike, side, expected):
    assert option_symbol(trade_date, strike, side, root=root) == expected


def _split_root(symbol: str) -> str:
    """Decode helper (test-only): every root used in this codebase (SPY/GLD/QQQ/NVDA/
    TSLA/AAPL) is pure alphabetic, so the root is exactly the leading alpha run before the
    numeric YYMMDD begins. Used to prove option_symbol's output round-trips cleanly for
    roots of DIFFERENT lengths without hardcoding a length assumption here either."""
    i = 0
    while i < len(symbol) and symbol[i].isalpha():
        i += 1
    return symbol[:i]


@pytest.mark.parametrize(
    "root,trade_date,strike,side",
    [
        ("SPY", dt.date(2026, 8, 21), 645, "C"),    # 3-char
        ("GLD", dt.date(2026, 8, 21), 335, "P"),     # 3-char
        ("QQQ", dt.date(2026, 8, 21), 590, "C"),     # 3-char
        ("NVDA", dt.date(2026, 8, 21), 180, "C"),    # 4-char
        ("TSLA", dt.date(2026, 8, 21), 260, "P"),    # 4-char
        ("AAPL", dt.date(2026, 8, 21), 230, "C"),    # 4-char
    ],
)
def test_round_trip_root_date_side_strike_across_lengths(root, trade_date, strike, side):
    """Round-trips (root, date, side, strike) -> symbol -> decoded fields for BOTH 3-char
    and 4-char roots, proving option_symbol does not silently assume a fixed root width
    (the OCC-spec 6-char-padded field this shop's function deliberately does NOT emit --
    see option_symbol's docstring)."""
    symbol = option_symbol(trade_date, strike, side, root=root)

    decoded_root = _split_root(symbol)
    assert decoded_root == root, f"expected root {root!r}, decoded {decoded_root!r} from {symbol!r}"

    rest = symbol[len(root):]
    assert len(rest) == 15, f"expected 15 trailing chars (YYMMDD+side+8-digit strike), got {rest!r}"
    assert rest[:6] == trade_date.strftime("%y%m%d")
    assert rest[6] == side
    strike_field = rest[7:]
    assert len(strike_field) == 8
    assert int(strike_field) == strike * 1000

    # No space padding anywhere -- total length is root-length-DEPENDENT (this is the
    # exact property that makes the hardcoded `symbol[9]` parse in
    # setup/scripts/atomic_bracket_guard.py wrong for 4-char roots).
    assert len(symbol) == len(root) + 15
    assert " " not in symbol


def test_root_length_varies_symbol_length_not_padded():
    """Direct proof that 3-char and 4-char roots produce DIFFERENT total symbol lengths
    (18 vs 19 chars for these inputs: root + 6-digit date + 1 side char + 8-digit strike)
    -- if the root were padded to a fixed 6 chars (the formal OSI spec, deliberately NOT
    what this function emits -- see its docstring), both would be the same length."""
    spy_sym = option_symbol(dt.date(2026, 8, 21), 645, "C", root="SPY")
    nvda_sym = option_symbol(dt.date(2026, 8, 21), 180, "C", root="NVDA")
    assert len(spy_sym) == 18
    assert len(nvda_sym) == 19
    assert len(nvda_sym) - len(spy_sym) == 1  # exactly the root-length delta (4 - 3)


# ------------------------------------------------------------------------- input guards

def test_root_over_six_chars_rejected():
    """OSI root field width cap is 6 -- a longer root is a caller bug, not a silently
    truncated symbol."""
    with pytest.raises(AssertionError):
        option_symbol(dt.date(2026, 8, 21), 100, "C", root="TOOLONGROOT")


def test_root_lowercase_normalized_to_upper():
    """Real chain roots are upper-case; a caller passing lower-case must not silently
    build a different (and wrong) symbol than the canonical upper-case one."""
    assert option_symbol(dt.date(2026, 8, 21), 180, "C", root="nvda") == "NVDA260821C00180000"
