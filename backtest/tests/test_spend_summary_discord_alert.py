"""Regression guard for spend_summary._alert_discord — the Fable insights-report gap.

THE GAP (2026-07-02, usage-insights report): spend_summary.py already threshold-warned
to STATUS.md on a >$50/day breach, but J only sees STATUS.md reactively -- the same
class of miss that let a previous session burn $52 re-litigating the exact inefficiency
it was meant to fix. self_check.py and github_audit.py already ping Discord the same
day a RED verdict fires; spend_summary was the one daily guardian still STATUS.md-only.

THE FIX: _alert_discord mirrors the established GREEN-silent/breach-pings pattern --
writes one terse row to discord-outbox.jsonl only when today's total >= threshold.

This guard pins: (a) no write below threshold, (b) exactly one write at/above threshold,
(c) the message names the actual dollar total so a refactor can't silently drop it back
to STATUS.md-only or blow the terse Discord budget with a wall of text.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "spend_summary.py"

_spec = importlib.util.spec_from_file_location("spend_summary", MOD_PATH)
ss = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ss  # dataclass field-type resolution needs the module registered first
_spec.loader.exec_module(ss)


def _make_report(total_claude: float, minimax: float = 0.0, sessions: int = 1) -> "ss.DayReport":
    report = ss.DayReport(date_et="2026-07-02")
    report.claude_sessions = sessions
    report.minimax_cost = minimax
    tier_key = "sonnet"
    agg = ss.TokenAgg()
    # Reverse-engineer input tokens that price out to the desired claude cost
    # at the sonnet input rate ($3/M) so claude_total_cost == total_claude.
    agg.input_tokens = int(total_claude / 3.0 * 1_000_000) if total_claude else 0
    report.claude_by_tier[tier_key] = agg
    return report


def test_no_alert_below_threshold(tmp_path, monkeypatch):
    outbox = tmp_path / "discord-outbox.jsonl"
    monkeypatch.setattr(ss, "DISCORD_OUTBOX", outbox)
    report = _make_report(total_claude=10.0)
    assert report.total_cost < 50.0
    ss._alert_discord(report, threshold=50.0)
    assert not outbox.exists()


def test_alert_fires_at_threshold_breach(tmp_path, monkeypatch):
    outbox = tmp_path / "discord-outbox.jsonl"
    monkeypatch.setattr(ss, "DISCORD_OUTBOX", outbox)
    report = _make_report(total_claude=60.0)
    assert report.total_cost >= 50.0
    ss._alert_discord(report, threshold=50.0)
    assert outbox.exists()
    lines = outbox.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["source"] == "spend_summary"
    assert "60.00" in row["message"]
    assert "2026-07-02" in row["message"]
    assert len(row["message"]) <= 500


def test_alert_message_stays_terse(tmp_path, monkeypatch):
    outbox = tmp_path / "discord-outbox.jsonl"
    monkeypatch.setattr(ss, "DISCORD_OUTBOX", outbox)
    report = _make_report(total_claude=500.0, minimax=12.3456, sessions=9)
    ss._alert_discord(report, threshold=50.0)
    row = json.loads(outbox.read_text(encoding="utf-8").strip())
    assert "9 session" in row["message"]
    assert len(row["message"]) <= 500
