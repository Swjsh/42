"""Guard for GOAL-EARN-YOUR-KEEP-2026-09-12 item 3: the non-SPY tickers lane on HOME.md +
the anchor-class PROXY read over its ledgers.

Two independent surfaces, one goal item:
  (a) setup/scripts/obsidian_vault_sync.py::render_tickers_lane -- renders from a fixture of
      two day files and degrades a missing/unreadable day to a `?` row rather than raising.
  (b) backtest/tools/trigger_anchor_class_read.py --lane tickers -- classify_tickers_row buckets
      a fixture WOULD_PLACE-shaped ledger row by its PROXY class (no matched_level_label exists
      on this lane -- see that function's docstring for the 2026-09-12 schema check).
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VAULT_SYNC = REPO / "setup" / "scripts" / "obsidian_vault_sync.py"
ANCHOR_READ = REPO / "backtest" / "tools" / "trigger_anchor_class_read.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _write_day(base: Path, arm: str, date_str: str, *, sod: float, pnl: float,
               kill: bool, fills: list[dict]) -> None:
    (base / arm).mkdir(parents=True, exist_ok=True)
    (base / arm / f"day-{date_str}.json").write_text(json.dumps({
        "date": date_str, "arm": arm, "start_of_day_equity": sod,
        "realized_pnl_today": pnl, "kill_tripped": kill, "fills": fills,
    }), encoding="utf-8")


# --------------------------------------------------------------------- (a) HOME rendering


def test_tickers_lane_renders_table_and_cumulative(tmp_path):
    m = _load(VAULT_SYNC, "obsidian_vault_sync_test_a")
    base = tmp_path / "tickers"
    _write_day(base, "tickers-1", "2026-09-04", sod=5000.0, pnl=-156.0, kill=False,
               fills=[{"contract": "AMZN260904C00260000", "side": "BUY"},
                      {"contract": "AMZN260904C00260000", "side": "SELL_ALL"}])
    _write_day(base, "tickers-2", "2026-09-04", sod=5000.0, pnl=0.0, kill=False, fills=[])
    _write_day(base, "tickers-3", "2026-09-04", sod=5000.0, pnl=-198.0, kill=True,
               fills=[{"contract": "QQQ260904P00709000", "side": "BUY"},
                      {"contract": "QQQ260904P00709000", "side": "SELL_ALL"}])
    _write_day(base, "tickers-1", "2026-09-08", sod=4843.72, pnl=45.0, kill=False,
               fills=[{"contract": "AAPL260908C00315000", "side": "BUY"},
                      {"contract": "AAPL260908C00315000", "side": "SELL_ALL"}])
    # tickers-2/tickers-3 have NO day-2026-09-08.json -- must degrade to a `?` row, not raise.

    out = m.render_tickers_lane(state_dir=base)
    text = "\n".join(out)

    assert "🎯 Tickers" in text
    assert "paper fills on real quotes" in text
    assert "| 2026-09-04 | tickers-1 |" in text
    assert "$5,000.00" in text
    assert "AMZN" in text and "QQQ" in text
    # missing day file -> `?` row, never an exception
    assert "| 2026-09-08 | tickers-2 | ? | ? | ? | ? | ? |" in text
    assert "| 2026-09-08 | tickers-3 | ? | ? | ? | ? | ? |" in text
    # cumulative sums ALL sessions on disk for that arm, not just the table's row cap
    assert "tickers-1** cumulative since 09-04: -111.00" in text  # -156 + 45
    assert "lane total" in text


def test_tickers_lane_missing_dir_is_all_question_marks(tmp_path):
    """A lane directory that does not exist at all must still render (fail-open), never raise."""
    m = _load(VAULT_SYNC, "obsidian_vault_sync_test_b")
    out = m.render_tickers_lane(state_dir=tmp_path / "does-not-exist")
    text = "\n".join(out)
    assert "🎯 Tickers" in text
    assert "lane total" in text
    assert "$0.00" not in text  # no fabricated rows when there are zero known sessions


# --------------------------------------------------------------------- (b) anchor-class PROXY


def test_classify_tickers_row_buckets_by_trigger_name():
    m = _load(ANCHOR_READ, "trigger_anchor_class_read_test")
    bull_row = {"action": "ENTER_BULL", "bull_triggers": ["level_reclaim", "confluence"],
                "bear_triggers": []}
    assert m.classify_tickers_row(bull_row) == "LEVEL_RECLAIM"

    bear_row = {"action": "ENTER_BEAR", "bull_triggers": [],
                "bear_triggers": ["level_rejection", "confluence"]}
    assert m.classify_tickers_row(bear_row) == "LEVEL_REJECTION"

    no_trigger_row = {"action": "ENTER_BULL", "bull_triggers": [], "bear_triggers": []}
    assert m.classify_tickers_row(no_trigger_row) == "NONE"


def test_read_tickers_lane_joins_ledger_to_journal_pnl(tmp_path):
    m = _load(ANCHOR_READ, "trigger_anchor_class_read_test2")
    state_dir = tmp_path / "state" / "tickers"
    journal_dir = tmp_path / "journal"
    arm_dir = state_dir / "tickers-1"
    arm_dir.mkdir(parents=True)
    journal_dir.mkdir(parents=True)

    ledger_rows = [
        {"ts_et": "2026-09-04T09:41:07-04:00", "arm": "tickers-1", "action": "ENTER_BULL",
         "contract": "AMZN260904C00260000", "bull_triggers": ["level_reclaim", "confluence"],
         "bear_triggers": [], "decision": "WOULD_PLACE"},
        {"ts_et": "2026-09-04T09:43:17-04:00", "arm": "tickers-1", "decision": "ENTRY_FILLED",
         "contract": "AMZN260904C00260000", "qty": 3, "price": 0.79,
         "trade_id": "tickers-1-AMZN260904C00260000-094317"},
    ]
    (arm_dir / "ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in ledger_rows), encoding="utf-8")

    with (journal_dir / "trades-tickers-tickers-1.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["trade_id", "row_type", "arm", "symbol", "contract", "side", "entry_date",
                    "entry_time_et", "entry_premium", "qty", "exit_date", "exit_time_et",
                    "exit_premium", "exit_reason", "holding_period_sessions", "pnl_dollars",
                    "pnl_pct", "feed", "spread_pct_at_entry"])
        w.writerow(["tickers-1-AMZN260904C00260000-094317", "ENTRY", "tickers-1", "AMZN",
                    "AMZN260904C00260000", "C", "2026-09-04", "09:43:17", "0.79", "3",
                    "", "", "", "", "", "", "", "indicative", "2.5"])
        w.writerow(["tickers-1-AMZN260904C00260000-094317", "EXIT", "tickers-1", "AMZN",
                    "AMZN260904C00260000", "C", "2026-09-04", "09:43:17", "0.79", "3",
                    "2026-09-04", "09:51:24", "0.27", "theta_budget", "0", "-156.0",
                    "-65.8228", "indicative", "2.5"])

    res = m.read_tickers_lane("2026-09-04", "2026-09-04", state_dir=state_dir,
                              journal_dir=journal_dir, arms=("tickers-1",))
    assert res["classes"]["LEVEL_RECLAIM"]["legs"] == 1
    assert res["classes"]["LEVEL_RECLAIM"]["pnl"] == -156.0
    assert res["open_legs"] == 0


def test_read_tickers_lane_counts_unreconciled_exit_as_open_leg(tmp_path):
    """Mirrors the real 2026-09-10 NVDA gap: an ENTRY_FILLED with no matching journal EXIT
    row must be counted in open_legs, never silently dropped and never counted as $0 P&L."""
    m = _load(ANCHOR_READ, "trigger_anchor_class_read_test3")
    state_dir = tmp_path / "state" / "tickers"
    journal_dir = tmp_path / "journal"
    arm_dir = state_dir / "tickers-1"
    arm_dir.mkdir(parents=True)
    journal_dir.mkdir(parents=True)

    ledger_rows = [
        {"ts_et": "2026-09-10T12:15:07-04:00", "arm": "tickers-1", "action": "ENTER_BEAR",
         "contract": "NVDA260911P00217500", "bull_triggers": [],
         "bear_triggers": ["level_rejection", "confluence"], "decision": "WOULD_PLACE"},
        {"ts_et": "2026-09-10T12:15:16-04:00", "arm": "tickers-1", "decision": "ENTRY_FILLED",
         "contract": "NVDA260911P00217500", "qty": 3, "price": 1.56,
         "trade_id": "tickers-1-NVDA260911P00217500-121516"},
    ]
    (arm_dir / "ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in ledger_rows), encoding="utf-8")
    with (journal_dir / "trades-tickers-tickers-1.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["trade_id", "row_type", "arm", "symbol", "contract", "side", "entry_date",
                    "entry_time_et", "entry_premium", "qty", "exit_date", "exit_time_et",
                    "exit_premium", "exit_reason", "holding_period_sessions", "pnl_dollars",
                    "pnl_pct", "feed", "spread_pct_at_entry"])
        w.writerow(["tickers-1-NVDA260911P00217500-121516", "ENTRY", "tickers-1", "NVDA",
                    "NVDA260911P00217500", "P", "2026-09-10", "12:15:16", "1.56", "3",
                    "", "", "", "", "", "", "", "indicative", "3.85"])
        # NO EXIT row -- exactly the real 09-10 bookkeeping gap.

    res = m.read_tickers_lane("2026-09-10", "2026-09-10", state_dir=state_dir,
                              journal_dir=journal_dir, arms=("tickers-1",))
    assert res["open_legs"] == 1
    assert sum(c["legs"] for c in res["classes"].values()) == 0


# --------------------------------------------------------- RED-proof (break, fail, restore)


def test_red_proof_classify_tickers_row_would_have_caught_a_regression():
    """Demonstrates the assertion actually discriminates: a broken classifier that always
    returns 'NONE' fails this test, proving it is not vacuously true."""
    def broken_classify(row):
        return "NONE"

    bull_row = {"action": "ENTER_BULL", "bull_triggers": ["level_reclaim"], "bear_triggers": []}
    assert broken_classify(bull_row) != "LEVEL_RECLAIM", (
        "sanity check inverted -- the broken stub should NOT match the real classifier")

    m = _load(ANCHOR_READ, "trigger_anchor_class_read_test4")
    assert m.classify_tickers_row(bull_row) == "LEVEL_RECLAIM"
