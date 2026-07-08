"""Guard: per-entry greeks/IV capture (G8, 2026-07-07 Fable gap-audit).

The engine now logs the traded contract's greeks (delta/gamma/theta/vega/rho + IV) at every
entry, so future 'does a dynamic stop beat a static one' research runs on REAL greeks instead
of VIX-proxied IV + a fixed per-tier delta. It is LOG-ONLY and FAIL-OPEN: a broken/slow feed
must yield {} and never delay or break a fill. These guards pin both properties.

Run: cd backtest && python -m pytest tests/test_greeks_capture.py -q
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
SCRIPTS = REPO / "setup" / "scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------- fleet_broker._parse_option_greeks
_SNAP = {
    "snapshots": {
        "SPY260708P00745000": {
            "greeks": {"delta": -0.42, "gamma": 0.03, "theta": -0.55, "vega": 0.12, "rho": -0.01},
            "impliedVolatility": 0.187,
            "latestQuote": {"bp": 1.2, "ap": 1.3},
        }
    }
}


def _fb():
    if str(FLEET) not in sys.path:
        sys.path.insert(0, str(FLEET))
    return _load("fleet_broker", FLEET / "fleet_broker.py")


def test_parse_greeks_happy_path():
    g = _fb()._parse_option_greeks(_SNAP, "SPY260708P00745000")
    assert g["delta"] == -0.42 and g["theta"] == -0.55 and g["iv"] == 0.187
    assert set(g) >= {"delta", "gamma", "theta", "vega", "rho", "iv"}


def test_parse_greeks_missing_symbol_is_none():
    assert _fb()._parse_option_greeks(_SNAP, "SPY260708C00999000") is None


def test_parse_greeks_malformed_is_none():
    fb = _fb()
    assert fb._parse_option_greeks({"snapshots": {"X": {"greeks": {}}}}, "X") is None   # empty greeks
    assert fb._parse_option_greeks({}, "X") is None                                     # no snapshots
    assert fb._parse_option_greeks("not a dict", "X") is None                           # wrong type
    assert fb._parse_option_greeks({"snapshots": {"X": {"greeks": {"delta": True}}}}, "X") is None  # bool != number


# --------------------------------------------------------- heartbeat_core._capture_greeks
def _hc():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    return importlib.import_module("heartbeat_core")


def test_capture_greeks_fail_open_on_raise():
    """The load-bearing safety property: a fetch that raises yields {} (never propagates)."""
    def boom(creds, symbol):
        raise RuntimeError("feed down")
    assert _hc()._capture_greeks({"key": "k", "secret": "s"}, "SYM", fetch=boom) == {}


def test_capture_greeks_passes_through_dict():
    g = {"delta": -0.4, "iv": 0.2}
    assert _hc()._capture_greeks({}, "SYM", fetch=lambda c, s: g) == g


def test_capture_greeks_none_becomes_empty():
    assert _hc()._capture_greeks({}, "SYM", fetch=lambda c, s: None) == {}
