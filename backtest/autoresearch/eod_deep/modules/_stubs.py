"""Stub implementations for Phase 2 modules.

Each stub is a function returning a CategoryScore with score=50 (neutral),
evidence={'phase': 'stub'}, and a narrative indicating Phase 2 work needed.

This lets us ship the full 12-category JSON structure in Phase 1 even
though only `edge` is fully implemented. Each stub gets replaced one-by-one
in Phase 2.
"""
from __future__ import annotations

from ..schema import CategoryScore
from ..ingest import IngestedData


def _stub(category_name: str, narrative_extra: str = "") -> CategoryScore:
    return CategoryScore(
        score=50.0,
        evidence={"phase": "stub", "module": category_name},
        narrative=f"[STUB] {category_name} module pending Phase 2 implementation. {narrative_extra}",
        actions=[],
    )


def analyze_execution(data: IngestedData, trades) -> CategoryScore:
    """How well did entries/exits fire vs the plan?

    Phase 1: shallow — count fills, check slippage from current-position.json
    Phase 2: full slippage analysis, fill timing vs trigger bar, partial-fill detection.
    """
    if not trades:
        return _stub("execution", "No trades to analyze.")

    fills_count = sum(len(t.fills) for t in trades)
    # phase-1 shallow read
    avg_slippage = 0
    slip_records = [f.slippage_cents for t in trades for f in t.fills if f.slippage_cents is not None]
    if slip_records:
        avg_slippage = sum(slip_records) / len(slip_records)

    score = 95.0 if abs(avg_slippage) <= 10 else 80.0

    return CategoryScore(
        score=score,
        evidence={
            "trade_count": len(trades),
            "fill_count": fills_count,
            "avg_slippage_cents": round(avg_slippage, 1),
            "phase": "1-shallow",
        },
        narrative=(f"{len(trades)} trades / {fills_count} fills. "
                   f"Avg slippage {avg_slippage:.1f}c. "
                   f"Phase 1 SHALLOW — Phase 2 adds fill-timing-vs-trigger and partial-fill analysis."),
        actions=[],
    )


def analyze_detection(data: IngestedData, trades) -> CategoryScore:
    """Did engine SEE every setup the playbook predicted?"""
    return _stub("detection", "Phase 2 will compare today's bars vs setup definitions to find missed triggers.")


def analyze_doctrine(data: IngestedData, trades) -> CategoryScore:
    """Did we follow v15 rules?"""
    if not trades:
        return _stub("doctrine", "No trades, no doctrine to evaluate.")
    # Phase 1: simple — any rule breaks in today's rule-breaks.jsonl?
    breaks_today = data.rule_breaks_today
    if not breaks_today:
        return CategoryScore(
            score=100.0,
            evidence={"rule_breaks_count": 0, "trade_count": len(trades)},
            narrative=f"100% doctrine compliance. {len(trades)} trades, 0 rule breaks logged.",
            actions=[],
        )
    return CategoryScore(
        score=max(0.0, 100.0 - 20.0 * len(breaks_today)),
        evidence={"rule_breaks_count": len(breaks_today), "breaks": breaks_today},
        narrative=f"{len(breaks_today)} rule breaks logged today.",
        actions=[],
    )


def analyze_risk(data: IngestedData, trades) -> CategoryScore:
    """Position sizing, max drawdown, daily loss budget usage."""
    if not trades:
        return _stub("risk")
    # Phase 1 shallow: size as % of equity at entry
    equity = data.alpaca_account.get("last_equity") or "101272.15"
    try:
        equity_f = float(equity)
    except (ValueError, TypeError):
        equity_f = 101272.15
    sizes_pct = []
    for t in trades:
        buy = next((f for f in t.fills if f.side == "buy"), None)
        if not buy:
            continue
        cost = buy.qty * buy.price * 100
        sizes_pct.append(cost / equity_f * 100)
    max_size_pct = max(sizes_pct) if sizes_pct else 0.0

    score = 100.0 if max_size_pct < 20.0 else (50.0 if max_size_pct < 50.0 else 0.0)

    return CategoryScore(
        score=score,
        evidence={"max_size_pct_of_equity": round(max_size_pct, 2), "v15_hard_gate": 20.0},
        narrative=f"Max position size {max_size_pct:.2f}% of equity (v15 hard gate: 20%). Phase 1 SHALLOW.",
        actions=[],
    )


def analyze_process(data: IngestedData, trades) -> CategoryScore:
    """Journal/document/learn quality."""
    has_journal = len(data.journal_md) > 1000
    has_trades_csv = len(data.trades_csv_rows) > 0
    has_decisions = len(data.decisions_today) > 0
    score = 0
    if has_journal: score += 40
    if has_trades_csv: score += 30
    if has_decisions: score += 30
    return CategoryScore(
        score=float(score),
        evidence={
            "journal_md_len": len(data.journal_md),
            "trades_csv_rows": len(data.trades_csv_rows),
            "decisions_count": len(data.decisions_today),
        },
        narrative=f"Journal {len(data.journal_md)}B, trades.csv {len(data.trades_csv_rows)} rows, "
                  f"decisions.jsonl {len(data.decisions_today)} entries. Phase 1 SHALLOW.",
        actions=[],
    )


def analyze_macro(data: IngestedData, trades) -> CategoryScore:
    """News.json prediction vs actual macro reaction."""
    return _stub("macro", "Phase 2 will grade today's regime prediction vs realized.")


def analyze_technical(data: IngestedData, trades) -> CategoryScore:
    """Chart read — key levels, ribbon, trendlines, hypothesis grades."""
    grades = data.hypothesis_grades_today
    if not grades:
        return _stub("technical", "No hypothesis grades found yet.")
    passes = sum(1 for g in grades if g.get("verdict") == "PASS")
    score = (passes / len(grades) * 100) if grades else 50.0
    return CategoryScore(
        score=round(score, 1),
        evidence={"grades_count": len(grades), "passes": passes},
        narrative=f"{passes}/{len(grades)} hypotheses graded PASS. Phase 1 SHALLOW.",
        actions=[],
    )


def analyze_engine_health(data: IngestedData, trades) -> CategoryScore:
    """Heartbeat fired? Pin chain intact? CDP up?"""
    pin_v15 = data.params.get("rule_version") == "v15"
    diag_fires = len(data.watcher_diag_today)
    decisions = len(data.decisions_today)

    score = 50
    if pin_v15: score += 20
    if diag_fires > 50: score += 20  # ~76 expected for full RTH (5 min × 76 fires = full session)
    if decisions > 0: score += 10

    return CategoryScore(
        score=float(score),
        evidence={
            "rule_version_active": data.params.get("rule_version"),
            "watcher_diag_fires": diag_fires,
            "decisions_logged": decisions,
        },
        narrative=f"Rule {data.params.get('rule_version')}, {diag_fires} watcher diag fires, {decisions} decisions. Phase 1 SHALLOW.",
        actions=[],
    )


def analyze_watcher_fleet(data: IngestedData, trades) -> CategoryScore:
    """Per-watcher observability + would-be P&L."""
    obs_by_watcher = {}
    for ob in data.watcher_obs_today:
        w = ob.get("watcher_name", "unknown")
        obs_by_watcher[w] = obs_by_watcher.get(w, 0) + 1

    diag_fires = len(data.watcher_diag_today)
    diag_with_signals = sum(1 for d in data.watcher_diag_today if d.get("signals_emitted", 0) > 0)
    score = 30 + (50 * (diag_with_signals / max(1, diag_fires)))

    return CategoryScore(
        score=round(score, 1),
        evidence={
            "diag_fires_total": diag_fires,
            "diag_fires_with_signals": diag_with_signals,
            "observations_by_watcher": obs_by_watcher,
        },
        narrative=(f"{diag_with_signals}/{diag_fires} fires emitted signals. "
                   f"Observations: {obs_by_watcher}. Phase 1 SHALLOW."),
        actions=[],
    )


def analyze_lessons(data: IngestedData, trades) -> CategoryScore:
    """What did we learn today? Phase 2 cross-references LESSONS-LEARNED.md."""
    return _stub("lessons", "Phase 2 will scan today's incidents + fixes shipped to log new L## candidates.")


def analyze_tomorrow(data: IngestedData, trades) -> CategoryScore:
    """Forward look — carry levels, scheduled events, developing setups."""
    ls = data.loop_state
    dev = ls.get("developing_setup", {}) if ls else {}
    spy = ls.get("spy", {}) if ls else {}
    return CategoryScore(
        score=75.0,  # informational, score = "did we capture forward state cleanly?"
        evidence={
            "developing_setup": dev,
            "session_high": spy.get("session_high"),
            "session_low": spy.get("session_low"),
            "session_close": spy.get("last"),
        },
        narrative=("Forward state captured: developing setup, session H/L/C. "
                   "Phase 2 will add macro events for next session + key-levels-carry."),
        actions=[],
    )
