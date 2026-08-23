"""Guard against the 2026-08-10 trades.csv data-loss bug.

ROOT CAUSE: `automation/prompts/futures-eod.md` (fired daily 16:05 ET by the
`Gamma_FuturesEod` scheduled task, see `setup/scripts/run-futures-eod.ps1`) hardcoded its
OWN copy of the `journal/futures/trades.csv` schema in its Step 4 instructions -- a stale
23-column layout (`date,instrument,direction,entry,stop,tp1,...,rule_break`) that diverged
from the schema the code-owned writer (`backtest/futures/futures_journal.py`'s
`TRADE_COLUMNS`) actually uses (30 columns, `date,session_phase,instrument,...`).

Every time the EOD persona followed that stale instruction and (re)wrote the file's header,
the NEXT tick's `record_trade()` -> `_ensure_csv()` mismatch-guard detected a header it did
not recognize and rotated the whole file aside to `trades.legacy-<stamp>.csv` -- correctly
non-destructive AT THAT INSTANT, but the persona's own overwrite had already destroyed
whatever round trips had accumulated since the last rotation. This is how the 2026-08-10
session's 3 real round trips (-$41.49 stop, +$1.26 TP1, +$6.26 TP1) went missing: two
legacy-rotation artifacts sit on disk at 2026-08-10T10:10:03 and 2026-08-11T11:20:04,
both header-only, bracketing the exact window the trades vanished in.

This guard fails loudly if the prompt ever regains a hardcoded schema that disagrees with
the code's TRADE_COLUMNS -- the only way two independent writers of the same append-only
ledger can silently diverge again.
"""
from __future__ import annotations

import csv
import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROMPT = REPO / "automation" / "prompts" / "futures-eod.md"
JOURNAL_MODULE = REPO / "backtest" / "futures" / "futures_journal.py"
TRADES_CSV = REPO / "journal" / "futures" / "trades.csv"


def _load_journal():
    spec = importlib.util.spec_from_file_location("futures_journal", JOURNAL_MODULE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["futures_journal"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_prompt_exists():
    assert PROMPT.exists(), f"missing {PROMPT}"


def test_eod_prompt_carries_no_hardcoded_csv_schema():
    """The prompt must never re-embed its own trades.csv column list -- that is exactly
    the drift that caused the 2026-08-10 data loss. It should defer to the code writer."""
    text = PROMPT.read_text(encoding="utf-8")
    # The old stale schema string, verbatim -- must never reappear.
    stale = ("date,instrument,direction,entry,stop,tp1,runner,qty,tp1_qty,setup,watcher,"
             "confidence,vix,entry_time,tp1_time,exit_time,exit_price,exit_reason,"
             "pnl_pts,pnl_usd,hold_bars,thesis,rule_break")
    assert stale not in text, (
        "futures-eod.md re-embedded the stale 23-column trades.csv schema -- this is the "
        "exact bug that clobbered the 2026-08-10 session's trades")
    assert "futures_journal" in text, (
        "Step 4 must defer to backtest/futures/futures_journal.py's record_trade()/"
        "TRADE_COLUMNS rather than hand-writing a CSV row/header")


def test_any_csv_header_line_in_prompt_matches_trade_columns():
    """Belt-and-suspenders: if a future edit adds ANY literal comma-separated header line
    that looks like a trades.csv schema, it must match TRADE_COLUMNS exactly, not just
    avoid the one known-stale string."""
    m = _load_journal()
    text = PROMPT.read_text(encoding="utf-8")
    header_line_re = re.compile(r"^([a-z_]+(?:,[a-z_]+){10,})$", re.MULTILINE)
    for match in header_line_re.finditer(text):
        cols = match.group(1).split(",")
        assert cols == m.TRADE_COLUMNS, (
            f"a CSV-header-shaped line in futures-eod.md ({cols}) disagrees with the "
            f"code-owned schema ({m.TRADE_COLUMNS}) -- this is the exact drift that "
            "silently loses trades.csv rows"
        )


def test_trades_csv_header_matches_trade_columns():
    """The on-disk file must currently carry the code's schema, not a stale one."""
    m = _load_journal()
    assert TRADES_CSV.exists(), f"missing {TRADES_CSV}"
    with TRADES_CSV.open(newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh), [])
    assert header == m.TRADE_COLUMNS


def test_ensure_csv_rotates_mismatched_file_without_raising(tmp_path, monkeypatch):
    """Reproduces the mismatch-guard mechanism: a foreign-schema file must be rotated
    aside (not silently appended-under, not raised) so the next write starts clean."""
    m = _load_journal()
    monkeypatch.setattr(m, "JOURNAL_DIR", tmp_path)
    monkeypatch.setattr(m, "TRADES_CSV", tmp_path / "trades.csv")
    (tmp_path / "trades.csv").write_text(
        "date,instrument,direction,entry,stop,tp1,runner,qty,tp1_qty,setup,watcher,"
        "confidence,vix,entry_time,tp1_time,exit_time,exit_price,exit_reason,pnl_pts,"
        "pnl_usd,hold_bars,thesis,rule_break\n",
        encoding="utf-8",
    )
    m._ensure_csv()
    assert m.TRADES_CSV.exists()
    with m.TRADES_CSV.open(newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh), [])
    assert header == m.TRADE_COLUMNS
    legacy = list(tmp_path.glob("trades.legacy-*.csv"))
    assert legacy, "mismatched file was not rotated aside"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
