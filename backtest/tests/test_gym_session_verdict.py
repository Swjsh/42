"""Tests for autoresearch.gym_session._aggregate_verdict — the gym roll-up semantics.

Guards the fix for the chronic gym false-RED: the verdict must be ANCHORED on the
chart-reading harness (crypto-gym). Operational engine-health audits (pin/mcp/pulse/
watcher) — already owned with their own alerter by engine-health.json — may only surface
as YELLOW, never drive the chart-reading scorecard to RED. Genuine chart/trade-critical
REDs (detector harness, chart-data divergence, in-progress-bar entry) stay RED.

Root incident: gym `overall_verdict` was RED 6-of-7 days (2026-06-15..06-23) while the
crypto-gym detector harness was GREEN 7-of-7 — every RED came from absent peripheral
producers, the L39 pulse max-gap artifact, or the intentional Bold v15.2 pin "mismatch".
That false-RED permanently tripped the conductor's STAGE-0 "don't touch detectors" gate.
"""

from __future__ import annotations

import pytest

from autoresearch.gym_session import (
    AuditResult,
    _DETECTOR_HARNESS,
    _RED_CAPABLE,
    _aggregate_verdict,
)


def _a(name: str, verdict: str) -> AuditResult:
    return AuditResult(name=name, source_file=f"{name}.json", verdict=verdict, summary="")


# Names matching the production audit set (see gym_session.run).
HARNESS = _DETECTOR_HARNESS
CDV = "chart-data-verify"
TICK = "heartbeat-tick-audit"
PIN = "pin-chain-verify"
MCP = "heartbeat-mcp-self-test"
PULSE = "heartbeat-pulse-check"
WATCH = "watcher-state-inspector"


def _all_green() -> list[AuditResult]:
    return [
        _a(HARNESS, "GREEN"), _a(CDV, "GREEN"), _a(TICK, "GREEN"), _a(PIN, "GREEN"),
        _a(MCP, "GREEN"), _a(PULSE, "NOT_APPLICABLE"), _a(WATCH, "GREEN"),
    ]


def test_red_capable_set_is_exactly_the_three_chart_trade_critical_audits():
    assert _RED_CAPABLE == frozenset({HARNESS, CDV, TICK})


def test_all_green_is_green():
    assert _aggregate_verdict(_all_green()) == "GREEN"


def test_detector_harness_red_is_red():
    r = _all_green()
    r[0] = _a(HARNESS, "RED")
    assert _aggregate_verdict(r) == "RED"


def test_detector_harness_missing_is_red_fail_closed():
    r = _all_green()
    r[0] = _a(HARNESS, "MISSING")
    assert _aggregate_verdict(r) == "RED"


def test_chart_data_divergence_red_is_red():
    # A real CSV/yfinance divergence corrupts detector input — must stay RED (e.g. 06-19).
    r = _all_green()
    r[1] = _a(CDV, "RED")
    assert _aggregate_verdict(r) == "RED"


def test_tick_audit_decision_critical_red_is_red():
    # tick-audit only ever returns RED for a real ENTER/EXIT on an in-progress bar.
    r = _all_green()
    r[2] = _a(TICK, "RED")
    assert _aggregate_verdict(r) == "RED"


@pytest.mark.parametrize("op_audit", [PIN, MCP, PULSE, WATCH])
def test_operational_red_is_capped_at_yellow(op_audit):
    # The L39 pulse max-gap artifact, the intentional Bold v15.2 pin mismatch, watcher-obs
    # producer noise — all operational REDs that engine-health already owns. Cry-wolf, not
    # a chart-reading failure: must surface as YELLOW, never RED.
    r = _all_green()
    idx = {PIN: 3, MCP: 4, PULSE: 5, WATCH: 6}[op_audit]
    r[idx] = _a(op_audit, "RED")
    assert _aggregate_verdict(r) == "YELLOW"


@pytest.mark.parametrize("op_audit", [PIN, MCP, PULSE, WATCH])
def test_operational_missing_is_capped_at_yellow(op_audit):
    # Absent peripheral producer (or a read/timing race) → degraded observability, not RED.
    r = _all_green()
    idx = {PIN: 3, MCP: 4, PULSE: 5, WATCH: 6}[op_audit]
    r[idx] = _a(op_audit, "MISSING")
    assert _aggregate_verdict(r) == "YELLOW"


def test_2026_06_23_exact_case_is_yellow_not_red():
    # The triggering incident: crypto-gym GREEN, tick + watcher MISSING (one a 3-second
    # write race), chart-data + pin YELLOW. Old logic → RED. Correct → YELLOW.
    results = [
        _a(HARNESS, "GREEN"),
        _a(CDV, "YELLOW"),
        _a(TICK, "MISSING"),
        _a(PIN, "YELLOW"),
        _a(MCP, "GREEN"),
        _a(PULSE, "NOT_APPLICABLE"),
        _a(WATCH, "MISSING"),
    ]
    assert _aggregate_verdict(results) == "YELLOW"


def test_2026_06_18_pulse_l39_artifact_downgrades_from_red():
    # 06-17/06-18: only the pulse-check 15min max-gap (L39 SKIP-not-FIRE artifact) was RED.
    results = [
        _a(HARNESS, "GREEN"), _a(CDV, "GREEN"), _a(TICK, "GREEN"), _a(PIN, "YELLOW"),
        _a(MCP, "GREEN"), _a(PULSE, "RED"), _a(WATCH, "YELLOW"),
    ]
    assert _aggregate_verdict(results) == "YELLOW"


def test_chart_data_red_still_reds_even_with_operational_noise():
    # 06-16: chart-data RED (real) alongside pin RED (Bold v15.2 intentional). Stays RED on
    # the chart-data signal — operational noise does not mask a genuine detector-input RED.
    results = [
        _a(HARNESS, "GREEN"), _a(CDV, "RED"), _a(TICK, "GREEN"), _a(PIN, "RED"),
        _a(MCP, "GREEN"), _a(PULSE, "YELLOW"), _a(WATCH, "YELLOW"),
    ]
    assert _aggregate_verdict(results) == "RED"
