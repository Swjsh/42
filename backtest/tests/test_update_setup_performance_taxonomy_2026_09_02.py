"""Guard: update_setup_performance.py applies canonical_setup() at read time (queue
SETUP-TAXONOMY-UNNORMALIZED-ACROSS-PNL-SURFACES, 2026-09-02) -- the standing per-setup
P&L generator wired into every EOD path (module docstring: "wired into
run-eod-summary.ps1"). Fixture-level guard against a regression to raw-string grouping;
the real journal/trades.csv reconciliation lives in test_setup_taxonomy_2026_09_02.py."""
from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_MOD_PATH = REPO / "backtest" / "scripts" / "update_setup_performance.py"
_spec = importlib.util.spec_from_file_location("update_setup_performance_under_test", _MOD_PATH)
usp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(usp)


def _write_fixture_csv(path: Path) -> None:
    fieldnames = ["setup", "dollar_pnl", "premium_paid", "dollar_risk", "hold_minutes",
                 "hold_quality_pct", "iv_regime", "tod_bucket", "tape_assistance",
                 "trade_grade_score", "setup_quality", "trade_grade", "archetype_match_json"]
    rows = [
        {"setup": "VWAP_CONTINUATION", "dollar_pnl": "10"},
        {"setup": "vwap_continuation", "dollar_pnl": "-3"},
        {"setup": "Vwap_Continuation", "dollar_pnl": "5"},
        {"setup": "UNKNOWN", "dollar_pnl": "1"},
        {"setup": "", "dollar_pnl": "2"},
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            full = {k: "" for k in fieldnames}
            full.update(r)
            w.writerow(full)


def test_case_variants_and_blank_rows_collapse_into_canonical_buckets(tmp_path, monkeypatch):
    csv_path = tmp_path / "trades.csv"
    _write_fixture_csv(csv_path)
    out_path = tmp_path / "setup-performance.json"
    monkeypatch.setattr(usp, "TRADES_CSV", csv_path)
    monkeypatch.setattr(usp, "OUT_PATHS", (out_path,))
    monkeypatch.setattr(usp, "REPO", tmp_path)  # only used for the relative_to() print line

    rc = usp.main.__wrapped__() if hasattr(usp.main, "__wrapped__") else None
    # main() parses sys.argv via argparse -- call with a clean argv so pytest's own args
    # don't leak in.
    old_argv = sys.argv
    sys.argv = ["update_setup_performance.py"]
    try:
        rc = usp.main()
    finally:
        sys.argv = old_argv
    assert rc == 0

    import json
    out = json.loads(out_path.read_text(encoding="utf-8"))
    assert "VWAP_CONTINUATION" in out
    assert "vwap_continuation" not in out and "Vwap_Continuation" not in out
    assert out["VWAP_CONTINUATION"]["n_trades"] == 3
    assert "UNATTRIBUTED" in out
    assert out["UNATTRIBUTED"]["n_trades"] == 2  # UNKNOWN + genuinely-blank row, both counted
    assert "UNKNOWN" not in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
