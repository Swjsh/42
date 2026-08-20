"""multi/lib/positions.py -- symbol-generic position filtering for the multi-symbol lane.

THE PROBLEM THIS EXISTS TO SOLVE. `automation/state/fleet/fleet_broker.py`
(`open_spy_option_positions`) filters an Alpaca `/v2/positions` payload with:

    str(p.get("symbol", "")).startswith("SPY") and len(str(p.get("symbol", ""))) >= 15

That is exactly two hardcodes this lane must not repeat: (1) a fixed underlying ticker
(SPY-only), and (2) a length check that happens to work for 3-char roots but was never
validated against 4-char roots (NVDA/AAPL/TSLA -- `automation/state/multi/params.json`'s
`universe` trades ~70 names, most of them 4+ chars).

THE FIX. An OCC-shaped option symbol is ROOT + YYMMDD (6 digits) + C|P + 8-digit strike,
where ROOT is 1-6 uppercase letters. The regex below anchors on the FIXED-WIDTH tail (15
chars: 6-digit date + 1-char right + 8-digit strike) rather than a fixed offset from the
front, so it is root-length-agnostic by construction -- SPY (3 chars), NVDA (4 chars), and
a hypothetical 1- or 6-char root all parse identically. There is no ticker allowlist here;
membership in the "options" set is determined ENTIRELY by shape.

WHY THIS MATTERS BEYOND CORRECTNESS: account PA38EG1JTFBT (this lane's account, see
multi/lib/creds.py) simultaneously runs the crypto twin
(setup/scripts/crypto_twin_broker.py), trading BTC/USD every ~60s. A crypto position's
symbol ("BTCUSD" or "BTC/USD") can never match this regex -- it has no C/P right, no
8-digit strike, and its "date" segment doesn't parse as 6 digits either. That is what
makes it STRUCTURALLY impossible (not merely policy) for this lane to see, count, or
close the twin's BTC position: the predicate excludes it by shape, not by name.

Pure and side-effect-free: no network, no file I/O, no dependency on multi/lib/broker.py
or multi/lib/creds.py. broker.py imports THIS module, never the other way around.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

# ROOT (1-6 letters) + YYMMDD (6 digits) + C|P + strike (8 digits, thousandths of a dollar).
# Anchored full-string (^...$) so a symbol with extra trailing/leading junk never matches.
_OCC_RE = re.compile(r"^[A-Z]{1,6}\d{6}[CP]\d{8}$")

# Fixed-width tail: 6-digit date + 1-char right + 8-digit strike = 15 chars, ALWAYS, regardless
# of root length. This is what occ_root() slices against instead of a fixed front-offset.
_OCC_TAIL_LEN = 15


def is_occ_option_symbol(symbol: Any) -> bool:
    """True iff `symbol` has the OCC shape: 1-6 letter ROOT + YYMMDD + C|P + 8-digit strike.

    Root-length-agnostic (SPY/QQQ/GLD and NVDA/AAPL/TSLA are treated identically) and,
    critically, this is the ONLY gate multi/lib/broker.py uses to decide "is this an
    equity option position/order this lane may read or touch" -- a non-option symbol of
    ANY shape (crypto, equity, a malformed/empty string) returns False.
    """
    return bool(_OCC_RE.match(str(symbol) if symbol is not None else ""))


def occ_root(symbol: Any) -> Optional[str]:
    """Underlying root ticker parsed out of an OCC symbol, or None if not OCC-shaped.

    Slices from the FIXED-WIDTH tail (15 chars from the right), not a fixed front offset --
    this is the root-length-agnostic fix `is_occ_option_symbol` describes: SPY260622C00745000
    (18 chars) and NVDA260622C00745000 (19 chars) both correctly yield "SPY"/"NVDA" because
    the slice point is computed from the end, not a hardcoded index.
    """
    s = str(symbol) if symbol is not None else ""
    if not is_occ_option_symbol(s):
        return None
    return s[: -_OCC_TAIL_LEN]


def equity_option_positions(
    positions: Iterable[dict], *, allowed_roots: Optional[Iterable[str]] = None
) -> list[dict]:
    """Filter a raw broker `/v2/positions` payload down to equity OPTION positions only.

    THE crypto-safety boundary. A BTCUSD / BTC/USD crypto position is excluded because it
    can never match the OCC shape -- there is no startswith()/asset_class allowlist to
    rot out of date as the universe grows (unlike fleet_broker's `startswith("SPY")`),
    and no separate crypto-exclusion list to keep in sync with the twin's own symbol
    conventions. One predicate, checked against every candidate, is the entire filter.

    `allowed_roots`, when given, ADDITIONALLY narrows to symbols whose root is in that set
    (case-insensitive) -- this is the optional multi-lane `universe` scoping mentioned in
    the task brief, layered ON TOP of the OCC-shape safety boundary, never a substitute for
    it. Passing `allowed_roots=None` (the default) applies no extra narrowing: any
    OCC-shaped symbol passes, regardless of underlying.
    """
    roots = {str(r).upper() for r in allowed_roots} if allowed_roots is not None else None
    out: list[dict] = []
    for p in positions:
        sym = str(p.get("symbol", ""))
        if not is_occ_option_symbol(sym):
            continue
        if roots is not None:
            root = occ_root(sym)
            if root is None or root.upper() not in roots:
                continue
        out.append(p)
    return out


def is_flat_equity_options(positions: Iterable[dict], **kwargs: Any) -> bool:
    """True iff `equity_option_positions(positions, **kwargs)` is empty. Pure convenience
    wrapper -- the broker-level flat-check (with retry tolerance for Alpaca's documented
    list-lag) lives in multi/lib/broker.py as `is_flat_equity_options`, which calls this
    after fetching live positions."""
    return len(equity_option_positions(positions, **kwargs)) == 0
