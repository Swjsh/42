"""futures_journal.py -- "if it's not in the journal, it didn't happen", for futures.

WHY A SEPARATE JOURNAL. The SPY journal (`journal/trades.csv`, 44 columns) is shaped
around option contracts: strike, dte, c_or_p, premium_paid, delta/iv/theta at entry.
Not one of those exists for a futures trade, and the fields that DO matter here --
point value, tick, stop in POINTS, contract month, session phase, whether the fill was
simulated -- have nowhere to live in that schema. Forcing futures rows into it would
produce a ledger that is mostly empty columns and silently wrong in the few it fills
(`premium_paid` for a margin product is a category error, and any downstream P&L or
WR aggregation over a mixed file would be nonsense).

So: same DISCIPLINE, own schema.
  journal/futures/trades.csv          one row per closed round trip
  journal/futures/YYYY-MM-DD.md       the human daily log (thesis before, outcome after)
  journal/futures/mistakes.md         rule breaks, same role as the SPY mistakes file

THE DISCLOSURE COLUMN IS NOT OPTIONAL. Every row carries `fills` = SIMULATED or BROKER
and `backend`. A simulated round trip is mechanism evidence, never edge evidence, and
the ledger has to say so on the row itself -- not in a doc someone might not read. Any
consumer that aggregates without filtering on this column is producing a number that
means nothing, and the column existing is what makes that mistake visible.

Nothing in this module can raise into the trading path. A journal that can break a tick
is worse than no journal.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

JOURNAL_DIR = REPO / "journal" / "futures"
TRADES_CSV = JOURNAL_DIR / "trades.csv"
MISTAKES_MD = JOURNAL_DIR / "mistakes.md"

TRADE_COLUMNS = [
    "date", "session_phase", "instrument", "contract_month",
    "time_entry_et", "time_exit_et", "hold_minutes",
    "setup", "watcher", "confidence", "direction", "side",
    "qty", "entry_px", "exit_px", "stop_px", "tp1_px", "runner_px",
    "stop_points", "point_value", "risk_usd", "dollar_pnl", "r_multiple",
    "exit_reason", "equity_pre", "equity_post",
    "fills", "backend", "followed_rules", "rails_checked", "notes",
]


def _et_now() -> dt.datetime:
    p = str(REPO / "setup" / "scripts")
    if p not in sys.path:
        sys.path.insert(0, p)
    from et_clock import et_now  # noqa: PLC0415

    return et_now().replace(tzinfo=None)


def _ensure_dir() -> None:
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_csv() -> None:
    """Guarantee TRADES_CSV exists AND that its header is the one we write.

    A pre-existing file with a DIFFERENT header is the dangerous case, and it is not
    hypothetical: an abandoned 2026-06-17 `journal/futures/trades.csv` sits on disk with
    a completely different column set. Appending our rows under someone else's header
    writes values into the wrong columns forever, and every row still LOOKS well-formed
    -- the fixed-position CSV foot-gun (L294). So a mismatched file is rotated aside
    with its timestamp rather than appended to or silently overwritten.
    """
    _ensure_dir()
    if TRADES_CSV.exists():
        try:
            with TRADES_CSV.open(newline="", encoding="utf-8") as fh:
                existing = next(csv.reader(fh), [])
        except OSError:
            existing = []
        if existing == TRADE_COLUMNS:
            return
        stamp = _et_now().strftime("%Y%m%d-%H%M%S")
        TRADES_CSV.replace(TRADES_CSV.with_name(f"trades.legacy-{stamp}.csv"))
    with TRADES_CSV.open("w", newline="", encoding="utf-8") as fh:
        csv.DictWriter(fh, fieldnames=TRADE_COLUMNS).writeheader()


def daily_path(day: Optional[dt.date] = None) -> Path:
    day = day or _et_now().date()
    return JOURNAL_DIR / f"{day.isoformat()}.md"


# ── writes ────────────────────────────────────────────────────────────────────

def journal_entry(tick: dict) -> None:
    """Record the PRE-TRADE thesis at the moment of entry (Rule 8: thesis before order).

    Called from the tick right after the bracket is placed, so the stop and target are
    on the record before the market can move them.
    """
    try:
        entry = tick.get("entry") or {}
        if not entry:
            return
        _ensure_dir()
        path = daily_path()
        header = ""
        if not path.exists():
            header = (f"# Futures journal — {_et_now().date().isoformat()}\n\n"
                      f"> Fills marked SIMULATED are mechanism evidence, never edge evidence.\n\n")
        fills = "SIMULATED" if tick.get("simulated_fills") else "BROKER"
        block = (
            f"## {tick.get('ts_et', '')} — {entry.get('setup', '?')} "
            f"({entry.get('direction', '?')}) [{fills}]\n\n"
            f"- **Instrument:** {tick.get('instrument')} · session {tick.get('session_phase')}\n"
            f"- **Thesis:** {entry.get('watcher', '?')} fired "
            f"{entry.get('setup', '?')} at {entry.get('confidence', '?')} confidence\n"
            f"- **Entry:** {entry.get('entry')} · **Stop:** {entry.get('stop')} "
            f"({entry.get('stop_points')} pts) · **TP1:** {entry.get('tp1')} · "
            f"**Runner:** {entry.get('runner')}\n"
            f"- **Size:** {entry.get('qty')} contract(s) · **$ at risk:** "
            f"${entry.get('risk_usd', 0):.2f}\n"
            f"- **Equity pre:** ${tick.get('equity', 0):.2f} · "
            f"**session P&L:** ${tick.get('session_realized_pnl', 0):.2f}\n"
            f"- **Feed:** {tick.get('freshness')} · newest bar {tick.get('newest_bar_et')}\n"
            f"- **Backend:** {tick.get('backend')} · order ids {tick.get('order_ids')}\n\n"
        )
        with path.open("a", encoding="utf-8") as fh:
            if header:
                fh.write(header)
            fh.write(block)
    except Exception:  # noqa: BLE001 -- journaling never breaks the trading path
        pass


def journal_exit(*, instrument: str, event: dict, backend: str = "",
                 simulated: bool = True) -> None:
    """Append a fill/exit event to the daily log as it happens."""
    try:
        _ensure_dir()
        path = daily_path()
        fills = "SIMULATED" if simulated else "BROKER"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"- `{event.get('time_et', _et_now().isoformat(timespec='seconds'))}` "
                     f"**{event.get('action', event.get('event', '?'))}** {instrument} "
                     f"qty={event.get('exit_qty', event.get('qty', '?'))} "
                     f"@ {event.get('fill_price', '?')} "
                     f"pnl={event.get('pnl', '?')} [{fills}/{backend}]\n")
    except Exception:  # noqa: BLE001
        pass


def record_trade(row: dict) -> None:
    """Append one CLOSED round trip to journal/futures/trades.csv.

    Unknown keys are dropped and missing ones default to "" so a schema change on the
    caller side can never corrupt the column alignment of rows already written.
    """
    try:
        _ensure_csv()
        clean = {k: row.get(k, "") for k in TRADE_COLUMNS}
        if not clean.get("fills"):
            # Refuse to write an undisclosed row: an unlabeled fill is exactly the
            # ambiguity this column exists to prevent.
            clean["fills"] = "UNKNOWN"
        with TRADES_CSV.open("a", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=TRADE_COLUMNS).writerow(clean)
    except Exception:  # noqa: BLE001
        pass


def record_mistake(*, what: str, rule: str, cost_usd: float = 0.0, fix: str = "") -> None:
    """Log a rule break. Same role as journal/mistakes.md on the SPY side."""
    try:
        _ensure_dir()
        if not MISTAKES_MD.exists():
            MISTAKES_MD.write_text(
                "# Futures rule breaks\n\n"
                "> One entry per break. A winning trade that broke a rule still lands here.\n\n",
                encoding="utf-8")
        with MISTAKES_MD.open("a", encoding="utf-8") as fh:
            fh.write(f"## {_et_now().isoformat(timespec='seconds')} — {rule}\n\n"
                     f"- **What happened:** {what}\n"
                     f"- **Cost:** ${cost_usd:.2f}\n"
                     f"- **Fix:** {fix or 'TBD'}\n\n")
    except Exception:  # noqa: BLE001
        pass


# ── reads ─────────────────────────────────────────────────────────────────────

def read_trades(*, fills: Optional[str] = None) -> list[dict]:
    """Read the trade ledger, optionally filtered to SIMULATED or BROKER rows.

    Callers computing any statistic should pass `fills` explicitly. Mixing simulated
    and broker fills in one number is the mistake the column exists to make visible.
    """
    try:
        if not TRADES_CSV.exists():
            return []
        with TRADES_CSV.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        return [r for r in rows if fills is None or r.get("fills") == fills]
    except Exception:  # noqa: BLE001
        return []


def summarize(fills: str = "SIMULATED") -> dict:
    """Book summary over ONE fill class. Never aggregates across classes."""
    rows = read_trades(fills=fills)
    pnls = []
    for r in rows:
        try:
            pnls.append(float(r.get("dollar_pnl") or 0.0))
        except (TypeError, ValueError):
            continue
    wins = [p for p in pnls if p > 0]
    return {
        "fills": fills,
        "n_trades": len(pnls),
        "total_pnl": round(sum(pnls), 2),
        "win_rate": round(len(wins) / len(pnls), 4) if pnls else None,
        "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else None,
        "best": round(max(pnls), 2) if pnls else None,
        "worst": round(min(pnls), 2) if pnls else None,
        "evidence_class": ("mechanism only -- simulated fills are never edge evidence"
                           if fills == "SIMULATED" else "broker fills"),
    }


def main(argv=None) -> int:
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(description="Futures journal reader")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--fills", default="SIMULATED", choices=["SIMULATED", "BROKER", "UNKNOWN"])
    args = ap.parse_args(argv)
    if args.summary:
        print(json.dumps(summarize(args.fills), indent=2))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
