"""Graduated guard (HANDOFF-2026-07-09-TRUTH-AND-EXITS, T2): no fill-truth surface may derive
fills/P&L from a decision ledger. Broker = truth for fills/P&L (ground rule 2); decisions.jsonl/
core-decisions.jsonl/fleet/*/decisions.jsonl are DECISIONS-only and structurally lack fleet
fills. This is the May-13/2026-07-08 lesson ("poll Alpaca for 'did we trade'") converted into a
static, red-proofed assertion over the four named consumers.

RED-PROOF: written against the pre-T2 code. sim_live_parity.py's `_dig_fill_price` scanned a
decision row itself for `filled_avg_price` (which the writer never populates -> permanent false
"0 fills ever"), and fill_funnel.py's `trades_pnl_today` read journal/trades.csv as its ONLY
P&L source. Both are grep-detectable anti-patterns; this test goes RED on that code and GREEN
once T2 rewires both onto setup/scripts/broker_fills.py's fills-ledger.jsonl / pnl-statement.json.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"


def _source(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_sim_live_parity_reads_broker_fills_ledger_not_decision_rows():
    src = _source("sim_live_parity.py")
    assert "fills-ledger" in src or "broker_fills" in src, (
        "sim_live_parity.py must source its fill count/prices from T1's "
        "fills-ledger.jsonl (broker_fills.py), not scan decision rows for filled_avg_price")
    # The old bug: digging for 'filled_avg_price' INSIDE a decisions.jsonl/core-decisions.jsonl
    # row is exactly the anti-pattern T1 exists to kill (that field is never populated there).
    # Check for the FUNCTION DEFINITION only -- the docstring is allowed to mention the name
    # in prose explaining why it was removed.
    assert "def _dig_fill_price" not in src, (
        "sim_live_parity.py still DEFINES the old decisions-row filled_avg_price digger -- "
        "this is the function that produced the permanent false '0 fills ever'")


def test_fill_funnel_pnl_reads_pnl_statement_not_only_trades_csv():
    src = _source("fill_funnel.py")
    assert "pnl-statement" in src or "pnl_statement" in src, (
        "fill_funnel.trades_pnl_today must source realized P&L from T1's "
        "pnl-statement.json (broker-truth), not journal/trades.csv alone")


def test_eod_fallback_quant_section_still_ledger_free():
    """Pre-existing guard (test_eod_quant_guard.py) covers the LLM-prompt side of this; this
    is a narrower static check that the deterministic quant builder itself never inlines a
    raw decisions.jsonl/loop-state.json read for a fill/trade count."""
    src = _source("eod_fallback.py")
    assert "STATE / \"decisions.jsonl\"" not in src.replace("'", '"'), (
        "eod_fallback.py must not read the legacy decisions.jsonl directly for trade counts")


def test_trade_today_watcher_still_broker_sourced():
    """trade_today_watcher.py was already correct (queries Alpaca get_orders directly) --
    this locks that in so a future edit can't quietly regress it onto decisions.jsonl. The
    docstring is allowed to MENTION decisions.jsonl (explaining why it's avoided); what must
    never appear is an actual path construction that would read it."""
    src = _source("trade_today_watcher.py")
    assert "fb._request" in src or "fleet_broker" in src, (
        "trade_today_watcher.py must keep querying Alpaca directly for fills")
    assert 'STATE / "decisions.jsonl"' not in src and "STATE / 'decisions.jsonl'" not in src, (
        "trade_today_watcher.py must never construct a path to read a decisions ledger")
