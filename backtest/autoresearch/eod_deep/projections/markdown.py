"""Markdown projection of EodDeepDive.

Outputs a human-readable narrative for J's morning coffee read.
Single source of truth = the EodDeepDive dataclass; no parallel data.
"""
from __future__ import annotations

from ..schema import EodDeepDive, CATEGORY_KEYS


def _score_bar(score: float, width: int = 20) -> str:
    """ASCII progress bar for a 0-100 score."""
    filled = int(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _format_dollars(amount: float) -> str:
    sign = "+" if amount >= 0 else "-"
    return f"{sign}${abs(amount):,.2f}"


def render(d: EodDeepDive) -> str:
    lines = []
    lines.append(f"# EOD Deep-Dive — {d.date}")
    lines.append("")
    lines.append(f"_Generated {d.generated_at_et} · Rule version {d.rule_version_active} · Schema {d.schema_version}_")
    lines.append("")
    lines.append("---")
    lines.append("")

    # === Headline numbers ===
    lines.append("## Headline")
    lines.append("")
    lines.append(f"- **Day P&L:** {_format_dollars(d.day_pnl_dollars)} ({d.day_pnl_pct:+.2f}%)")
    lines.append(f"- **Account equity:** ${d.account_equity_start:,.2f} → ${d.account_equity_end:,.2f}")
    lines.append(f"- **Trades:** {d.day_trade_count}")
    lines.append(f"- **Process score:** {d.process_score}/100")
    lines.append(f"- **Edge capture:** {d.edge_capture_pct:.1f}%")
    lines.append("")

    # === Market session ===
    mss = d.market_session_summary
    lines.append("## Market session")
    lines.append("")
    lines.append(f"- SPY H/L/C: {mss.get('session_high')} / {mss.get('session_low')} / {mss.get('session_close')}")
    lines.append(f"- VIX close: {mss.get('vix_close')} ({mss.get('vix_dir')})")
    lines.append(f"- Predicted regime: {mss.get('regime_predicted')}")
    lines.append("")

    # === Trades ===
    if d.trades:
        lines.append("## Trades")
        lines.append("")
        for t in d.trades:
            lines.append(f"### {t.id}: {t.setup_name} — {t.underlying} {int(t.strike)}{t.option_type}")
            lines.append("")
            lines.append(f"- Direction: **{t.direction}** | Triggers: {', '.join(t.triggers_fired)} | Score: {t.setup_score}")
            lines.append(f"- Realized P&L: **{_format_dollars(t.pnl_dollars_realized)}** ({t.pnl_pct_on_capital:+.1f}% on ${t.qty_entered * t.entry_price * 100:,.0f} capital)")
            lines.append(f"- Hold time: {t.hold_minutes} min")
            lines.append(f"- Doctrine: {t.doctrine_compliance_score:.0f}/100 · Rule breaks: {len(t.rule_breaks)}")
            lines.append("")
            lines.append("#### Fills")
            lines.append("")
            lines.append("| Time | Side | Qty | Price | Source | Reason |")
            lines.append("|---|---|---|---|---|---|")
            for f in t.fills:
                lines.append(f"| {f.time_et} | {f.side} | {f.qty} | ${f.price:.2f} | {f.source} | {f.reason} |")
            lines.append("")

            if t.counterfactuals:
                lines.append("#### Counterfactuals")
                lines.append("")
                lines.append("| Scenario | P&L | Δ vs actual |")
                lines.append("|---|---|---|")
                for cf in t.counterfactuals:
                    lines.append(f"| {cf.name} | {_format_dollars(cf.pnl_dollars)} | {_format_dollars(cf.delta_vs_actual)} |")
                lines.append("")
                lines.append("**Counterfactual narratives:**")
                lines.append("")
                for cf in t.counterfactuals:
                    lines.append(f"- _{cf.name}:_ {cf.method}")
                lines.append("")
    else:
        lines.append("## Trades")
        lines.append("")
        lines.append("_No trades fired today._")
        lines.append("")

    # === Categories (12 dimensions) ===
    lines.append("## Category scores")
    lines.append("")
    lines.append("| # | Category | Score | Status |")
    lines.append("|---|---|---|---|")
    for i, key in enumerate(CATEGORY_KEYS, 1):
        cat = d.categories.get(key)
        if not cat:
            continue
        status = "✅" if cat.score >= 80 else ("⚠️" if cat.score >= 50 else "🔴")
        lines.append(f"| {i} | {key} | {cat.score}/100 | {status} `{_score_bar(cat.score)}` |")
    lines.append("")

    # === Category details ===
    lines.append("## Category narratives")
    lines.append("")
    for key in CATEGORY_KEYS:
        cat = d.categories.get(key)
        if not cat:
            continue
        lines.append(f"### {key.upper()} — {cat.score}/100")
        lines.append("")
        lines.append(cat.narrative)
        lines.append("")
        if cat.actions:
            lines.append("**Actions queued:**")
            lines.append("")
            for a in cat.actions:
                lines.append(f"- [{a.get('priority', 'MED')}] {a.get('type')}: {a.get('details', {})}")
            lines.append("")

    # === Research handoffs ===
    rh = d.research_handoffs
    lines.append("## Research handoffs")
    lines.append("")
    fixes = rh.get("fixes_shipped_today", [])
    if fixes:
        lines.append(f"**Fixes shipped today:** {', '.join(fixes)}")
        lines.append("")
    candidates = rh.get("doctrine_candidates_for_grinder", [])
    if candidates:
        lines.append("**Doctrine candidates for grinder:**")
        for c in candidates:
            lines.append(f"- {c}")
        lines.append("")
    warnings = rh.get("ingest_warnings", [])
    if warnings:
        lines.append("**Ingest warnings (data gaps):**")
        for w in warnings:
            lines.append(f"- ⚠️ {w}")
        lines.append("")

    # === Tomorrow ===
    lines.append("## Tomorrow")
    lines.append("")
    tomorrow = d.tomorrow_setup
    if tomorrow.get("developing_setup"):
        dev = tomorrow["developing_setup"]
        lines.append(f"- Developing setup at close: **{dev.get('name')}** (score {dev.get('score')}/{dev.get('score_max')})")
    lines.append(f"- Session H/L/C carry: {tomorrow.get('session_high')} / {tomorrow.get('session_low')} / {tomorrow.get('session_close')}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_End of report. See `.json` for full machine-readable data, `.html` for visual card._")
    return "\n".join(lines)
