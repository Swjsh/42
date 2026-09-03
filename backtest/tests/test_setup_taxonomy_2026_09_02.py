"""Guard: SETUP-TAXONOMY-UNNORMALIZED-ACROSS-PNL-SURFACES (queue, filed 2026-09-02).

backtest/lib/setup_taxonomy.py is the ONE canonical setup-name mapping. journal/trades.csv
had case-variant duplicates (VWAP_CONTINUATION n=45 vs vwap_continuation n=7), a legacy
UNKNOWN placeholder (n=25, +$115), and a pre-rename legacy name (BULLISH_RECLAIM, n=1)
splitting per-setup P&L into buckets that don't reconcile with analysis/trades-enriched
.jsonl's independently-derived setup taxonomy. This pins canonical_setup()'s contract and
the real-data reconciliation this session verified against journal/trades.csv:

    BEFORE (raw groupby): VWAP_CONTINUATION n=45 $-1114 + vwap_continuation n=7 $-164
                          VWAP_RECLAIM_FAILED_BREAK n=3 $-200 + vwap_reclaim_failed_break n=9 $-279
                          UNKNOWN n=25 $+115  (separate from genuinely blank rows)
                          BULLISH_RECLAIM n=1 $-18  (no counterpart bucket)
    AFTER  (canonical):   VWAP_CONTINUATION n=52 $-1278
                          VWAP_RECLAIM_FAILED_BREAK n=12 $-479
                          UNATTRIBUTED n=25 $+115
                          BULLISH_RECLAIM_RIDE_THE_RIBBON n=316 $+5098  (315+1, 5116-18)
                    14 raw buckets -> 11 canonical buckets, same total n=569, same total
                    pnl (accounting invariant: canonicalizing changes ATTRIBUTION, never
                    the sum)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_BACKTEST_DIR = REPO / "backtest"
if str(_BACKTEST_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKTEST_DIR))

from lib.setup_taxonomy import canonical_setup, rollup_by_setup, UNATTRIBUTED  # noqa: E402


# --- canonical_setup: the mapping contract ---------------------------------------------
def test_blank_and_none_map_to_unattributed():
    assert canonical_setup(None) == UNATTRIBUTED
    assert canonical_setup("") == UNATTRIBUTED
    assert canonical_setup("   ") == UNATTRIBUTED


def test_unknown_marker_maps_to_unattributed():
    assert canonical_setup("UNKNOWN") == UNATTRIBUTED
    assert canonical_setup("unknown") == UNATTRIBUTED
    assert canonical_setup("  Unknown  ") == UNATTRIBUTED


def test_case_variants_collapse_to_one_canonical_bucket():
    assert canonical_setup("VWAP_CONTINUATION") == canonical_setup("vwap_continuation")
    assert canonical_setup("vwap_continuation") == "VWAP_CONTINUATION"
    assert canonical_setup("Vwap_Continuation") == "VWAP_CONTINUATION"


def test_legacy_alias_resolves_to_current_name():
    assert canonical_setup("BULLISH_RECLAIM") == "BULLISH_RECLAIM_RIDE_THE_RIBBON"
    assert canonical_setup("bullish_reclaim") == "BULLISH_RECLAIM_RIDE_THE_RIBBON"


def test_legacy_name_with_no_counterpart_stays_its_own_bucket_normalized():
    """bollinger_squeeze / vix_regime_dayside / TRENDLINE_BREAK_RETEST have no alias --
    they are genuinely distinct setups, just normalized to upper case."""
    assert canonical_setup("bollinger_squeeze") == "BOLLINGER_SQUEEZE"
    assert canonical_setup("vix_regime_dayside") == "VIX_REGIME_DAYSIDE"
    assert canonical_setup("TRENDLINE_BREAK_RETEST") == "TRENDLINE_BREAK_RETEST"


def test_mapping_is_idempotent():
    for raw in ("VWAP_CONTINUATION", "vwap_continuation", "BULLISH_RECLAIM", None, "",
               "UNKNOWN", "bollinger_squeeze", "BEARISH_REJECTION_RIDE_THE_RIBBON"):
        once = canonical_setup(raw)
        twice = canonical_setup(once)
        assert once == twice, f"not idempotent for {raw!r}: {once!r} != {twice!r}"


# --- rollup_by_setup: the read-side aggregator ------------------------------------------
def test_rollup_merges_case_variants_into_one_bucket():
    rows = [
        {"setup": "VWAP_CONTINUATION", "dollar_pnl": "10"},
        {"setup": "vwap_continuation", "dollar_pnl": "-3"},
        {"setup": "Vwap_Continuation", "dollar_pnl": "5"},
    ]
    out = rollup_by_setup(rows)
    assert set(out.keys()) == {"VWAP_CONTINUATION"}
    assert out["VWAP_CONTINUATION"]["n"] == 3
    assert out["VWAP_CONTINUATION"]["pnl"] == 12.0


def test_rollup_routes_blank_and_unknown_to_unattributed():
    rows = [{"setup": "", "dollar_pnl": "1"}, {"setup": "UNKNOWN", "dollar_pnl": "2"},
           {"setup": None, "dollar_pnl": "3"}]
    out = rollup_by_setup(rows)
    assert set(out.keys()) == {UNATTRIBUTED}
    assert out[UNATTRIBUTED]["n"] == 3
    assert out[UNATTRIBUTED]["pnl"] == 6.0


def test_rollup_never_fabricates_pnl_for_missing_values():
    rows = [{"setup": "X", "dollar_pnl": ""}, {"setup": "X", "dollar_pnl": None}]
    out = rollup_by_setup(rows)
    assert out["X"]["n"] == 2
    assert out["X"]["pnl"] == 0.0  # counted, never guessed


# --- real-data reconciliation (RED-PROOF of the queue item's own numbers) ---------------
def test_real_trades_csv_before_after_bucket_reconciliation():
    """End-to-end against the REAL journal/trades.csv (read-only -- Rule 8, never rewritten).
    Reproduces the queue item's exact BEFORE numbers and asserts the AFTER merge."""
    import csv
    trades_csv = REPO / "journal" / "trades.csv"
    with trades_csv.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    rows = [{(k.lstrip("﻿") if k else k): v for k, v in r.items()} for r in rows]

    def _pnl(r):
        v = (r.get("dollar_pnl") or "").strip()
        try:
            return float(v)
        except ValueError:
            return 0.0

    raw_before: dict[str, dict] = {}
    for r in rows:
        s = (r.get("setup") or "").strip()
        if not s:
            continue
        b = raw_before.setdefault(s, {"n": 0, "pnl": 0.0})
        b["n"] += 1
        b["pnl"] += _pnl(r)

    # the queue item's own disclosed split-bucket numbers must still be present pre-fix
    # (guards against silently editing trades.csv out from under this test)
    assert raw_before.get("VWAP_CONTINUATION", {}).get("n") == 45
    assert raw_before.get("vwap_continuation", {}).get("n") == 7
    assert round(raw_before["vwap_continuation"]["pnl"], 2) == -164.0
    assert raw_before.get("VWAP_RECLAIM_FAILED_BREAK", {}).get("n") == 3
    assert raw_before.get("vwap_reclaim_failed_break", {}).get("n") == 9
    assert round(raw_before["vwap_reclaim_failed_break"]["pnl"], 2) == -279.0

    after = rollup_by_setup(rows)
    assert "VWAP_CONTINUATION" in after
    assert "vwap_continuation" not in after and "VWAP_continuation" not in after
    assert after["VWAP_CONTINUATION"]["n"] == 52  # 45 + 7
    assert after["VWAP_RECLAIM_FAILED_BREAK"]["n"] == 12  # 3 + 9
    assert after["BULLISH_RECLAIM_RIDE_THE_RIBBON"]["n"] == 316  # 315 + 1 legacy alias

    # accounting invariant: canonicalizing changes ATTRIBUTION, never the total pnl or n
    assert sum(b["n"] for b in after.values()) == len(rows)
    total_before_pnl = sum(_pnl(r) for r in rows)
    total_after_pnl = sum(b["pnl"] for b in after.values())
    assert round(total_before_pnl, 2) == round(total_after_pnl, 2)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
