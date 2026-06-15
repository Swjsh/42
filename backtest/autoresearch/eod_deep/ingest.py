"""Ingest layer — reads all sources, returns plain dicts.

Modules consume the IngestedData object. Modules MUST NOT read files directly —
they receive everything via the ingested data so they're testable + deterministic.

Sources (in order of read):
  1. State JSON files (params, loop-state, current-position, today-bias, news)
  2. Journal files (today's markdown, trades.csv)
  3. JSONL state logs (decisions, watcher-observations, watcher-live-diag, hypothesis-grades, rule-breaks)
  4. Alpaca (orders, account, portfolio history) — optional via MCP, skip if unreachable
  5. TradingView (chart screenshot, ribbon, levels) — optional, skip if CDP down

Failure mode for optional sources: log + return empty dict + record in `ingest_warnings`.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent.parent.parent
# REPO = C:\Users\jackw\Desktop\42

STATE_DIR = REPO / "automation" / "state"
PROMPTS_DIR = REPO / "automation" / "prompts"
JOURNAL_DIR = REPO / "journal"


@dataclass
class IngestedData:
    """All data collected for a single EOD analysis run."""
    date: str
    ingested_at_et: str

    # State files
    params: dict[str, Any] = field(default_factory=dict)
    loop_state: dict[str, Any] = field(default_factory=dict)
    current_position: dict[str, Any] = field(default_factory=dict)
    today_bias: dict[str, Any] = field(default_factory=dict)
    news: dict[str, Any] = field(default_factory=dict)

    # Journal
    journal_md: str = ""
    trades_csv_rows: list[dict[str, Any]] = field(default_factory=list)

    # JSONL logs (today's entries only)
    decisions_today: list[dict[str, Any]] = field(default_factory=list)
    watcher_obs_today: list[dict[str, Any]] = field(default_factory=list)
    watcher_diag_today: list[dict[str, Any]] = field(default_factory=list)
    hypothesis_grades_today: list[dict[str, Any]] = field(default_factory=list)
    rule_breaks_today: list[dict[str, Any]] = field(default_factory=list)

    # Optional (may be empty if MCP unreachable)
    alpaca_orders_today: list[dict[str, Any]] = field(default_factory=list)
    alpaca_account: dict[str, Any] = field(default_factory=dict)
    alpaca_portfolio_intraday: list[dict[str, Any]] = field(default_factory=list)
    tv_chart_state: dict[str, Any] = field(default_factory=dict)
    tv_chart_screenshot_path: Optional[str] = None
    tv_ribbon: dict[str, Any] = field(default_factory=dict)

    # Warnings / failed sources
    ingest_warnings: list[str] = field(default_factory=list)


def _read_json_file(path: Path) -> dict:
    """Read JSON file, return empty dict on any error (logged in warnings caller-side)."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def _read_jsonl_today(path: Path, date_str: str, date_field: str = "observed_at") -> list[dict]:
    """Read JSONL, filter to today's entries by string-prefix match on date_field.

    Resilient to:
      - single-line JSONL (normal case)
      - multi-line pretty-printed JSON entries (heartbeat sometimes writes these)
    """
    if not path.exists():
        return []
    rows = []
    try:
        text = path.read_text(encoding="utf-8-sig")
        # First pass: try strict one-line-per-record
        for line in text.split("\n"):
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            if not (line.endswith("}") or line.endswith("},")):
                continue
            try:
                obj = json.loads(line.rstrip(","))
                val = obj.get(date_field, "")
                if isinstance(val, str) and val.startswith(date_str):
                    rows.append(obj)
            except json.JSONDecodeError:
                continue

        # Second pass: brace-counting parser for multi-line records
        # Only run if first pass found NOTHING or far fewer than expected
        if len(rows) < 10:  # heuristic; full RTH should be ~100+ for decisions
            depth = 0
            buf = []
            for ch in text:
                if ch == "{":
                    depth += 1
                if depth > 0:
                    buf.append(ch)
                if ch == "}":
                    depth -= 1
                    if depth == 0 and buf:
                        candidate = "".join(buf).strip()
                        try:
                            obj = json.loads(candidate)
                            val = obj.get(date_field, "")
                            if isinstance(val, str) and val.startswith(date_str):
                                # Dedupe — multi-line parser may pick up rows
                                # already matched by single-line parser
                                if obj not in rows:
                                    rows.append(obj)
                        except json.JSONDecodeError:
                            pass
                        buf = []
    except Exception:
        pass
    return rows


def _read_csv_today(path: Path, date_str: str, date_field: str = "date") -> list[dict]:
    """Read CSV, filter to today's rows."""
    if not path.exists():
        return []
    rows = []
    try:
        with path.open(encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if (r.get(date_field, "") or "").startswith(date_str):
                    rows.append(r)
    except Exception:
        pass
    return rows


def _read_md_file(path: Path) -> str:
    """Read markdown file; empty string if missing."""
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8-sig")
    except Exception:
        return ""


def ingest_state_files(data: IngestedData) -> None:
    """Read static state JSON files."""
    data.params = _read_json_file(STATE_DIR / "params.json")
    if not data.params:
        data.ingest_warnings.append("params.json missing or invalid")
    data.loop_state = _read_json_file(STATE_DIR / "loop-state.json")
    data.current_position = _read_json_file(STATE_DIR / "current-position.json")
    data.today_bias = _read_json_file(STATE_DIR / "today-bias.json")
    data.news = _read_json_file(STATE_DIR / "news.json")


def ingest_journal(data: IngestedData, date_str: str) -> None:
    """Read today's journal markdown + matching trades.csv rows."""
    data.journal_md = _read_md_file(JOURNAL_DIR / f"{date_str}.md")
    if not data.journal_md:
        data.ingest_warnings.append(f"journal/{date_str}.md not found")

    data.trades_csv_rows = _read_csv_today(JOURNAL_DIR / "trades.csv", date_str, date_field="date")


def ingest_jsonl_logs(data: IngestedData, date_str: str) -> None:
    """Read today's entries from rolling JSONL logs."""
    # decisions.jsonl uses "date" field (YYYY-MM-DD), not "timestamp_et"
    data.decisions_today = _read_jsonl_today(
        STATE_DIR / "decisions.jsonl", date_str, date_field="date"
    )
    # watcher-observations.jsonl has bar_timestamp_et
    data.watcher_obs_today = _read_jsonl_today(
        STATE_DIR / "watcher-observations.jsonl", date_str, date_field="bar_timestamp_et"
    )
    # watcher-live-diag.jsonl has fire_at
    data.watcher_diag_today = _read_jsonl_today(
        STATE_DIR / "watcher-live-diag.jsonl", date_str, date_field="fire_at"
    )
    data.hypothesis_grades_today = _read_jsonl_today(
        STATE_DIR / "hypothesis-grades.jsonl", date_str, date_field="graded_at"
    )
    data.rule_breaks_today = _read_jsonl_today(
        STATE_DIR / "rule-breaks.jsonl", date_str, date_field="occurred_at"
    )


def ingest_alpaca_orders_static(data: IngestedData, date_str: str) -> None:
    """Optional: read Alpaca orders from a cached file if MCP is unavailable.

    Phase 1: skip — Alpaca data comes via MCP at runtime when invoked from
    an active Claude session. Pure-Python lifecycle path will need a snapshot
    file (Phase 2).
    """
    pass


def ingest_all(date_str: str) -> IngestedData:
    """Top-level orchestrator: ingest everything available for the given date."""
    data = IngestedData(
        date=date_str,
        ingested_at_et=dt.datetime.now().isoformat(timespec="seconds"),
    )
    ingest_state_files(data)
    ingest_journal(data, date_str)
    ingest_jsonl_logs(data, date_str)
    ingest_alpaca_orders_static(data, date_str)
    return data


def attach_alpaca_orders(data: IngestedData, orders: list[dict]) -> None:
    """Caller (interactive Claude session) feeds Alpaca orders here.

    Use this when invoking from Claude Code with MCP available.
    """
    data.alpaca_orders_today = orders or []


def attach_alpaca_account(data: IngestedData, account: dict) -> None:
    """Caller feeds Alpaca account info."""
    data.alpaca_account = account or {}


def attach_tv_chart(data: IngestedData, screenshot_path: str, chart_state: dict, ribbon: dict) -> None:
    """Caller feeds TradingView chart capture."""
    data.tv_chart_screenshot_path = screenshot_path
    data.tv_chart_state = chart_state or {}
    data.tv_ribbon = ribbon or {}
