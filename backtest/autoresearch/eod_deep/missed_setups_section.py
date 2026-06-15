"""Markdown formatter for the missed-setups scanner output.

Consumes the dict returned by ``missed_setups_scanner.scan_missed_setups``
and emits a markdown section ready to splice into ``journal/YYYY-MM-DD.md``
or to surface in the EOD deep-dive markdown projection.

Output structure:

    ### Engine Misses Today

    **Total opportunities on the chart: N missed setups, $X paper P&L left
    on the table.**
    **Engine captured: Y% of available edge.**

    | Time | Level | Type | Setup | Direction | Would-be P&L | Why missed |
    |---|---|---|---|---|---|---|
    | 09:30 | 741.84 | Open Rejection | SHOTGUN_T1 | PUT | +$1,450 | ... |

    **Root causes (deduplicated):**
    - Closed-bar lag (3 of 4 misses)
    - SHOTGUN_SCALPER not yet live (4 of 4)

The formatter is pure (no I/O, no side effects). Tests assert structure not
exact string contents.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


SECTION_HEADER = "### Engine Misses Today"

INTERACTION_TYPE_LABELS = {
    "rejection": "Rejection",
    "break": "Break",
    "reclaim": "Reclaim",
    "touch": "Touch",
}

SETUP_SHORT = {
    "SHOTGUN_SCALPER_TIER_1": "SHOTGUN_T1",
    "SHOTGUN_SCALPER_TIER_2": "SHOTGUN_T2",
    "SHOTGUN_SCALPER_TIER_3": "SHOTGUN_T3",
    "BEARISH_REJECTION_RIDE_THE_RIBBON": "BEAR_REJECT_RIBBON",
    "BULLISH_RECLAIM_RIDE_THE_RIBBON": "BULL_RECLAIM_RIBBON",
    "SNIPER_LEVEL_BREAK": "SNIPER_BREAK",
}


def render_section(scan_result: dict[str, Any]) -> str:
    """Render the scanner result as a markdown section.

    Args:
        scan_result: dict produced by ``scan_missed_setups``.

    Returns:
        A markdown string (no leading/trailing newline) safe to splice into
        a daily journal. Always returns a non-empty header — even if zero
        missed setups, we emit a clean "no misses" message so the section is
        always present for grep-ability.
    """
    if not isinstance(scan_result, dict):
        return f"{SECTION_HEADER}\n\n_(scanner produced no result)_"

    missed_count = int(scan_result.get("missed_setup_count", 0) or 0)
    total_pnl = float(scan_result.get("missed_setup_total_pnl_dollars", 0.0) or 0.0)
    edge_capture_pct = float(scan_result.get("edge_capture_pct", 0.0) or 0.0)
    engine_trades = int(scan_result.get("engine_trades_today", 0) or 0)
    engine_pnl = float(scan_result.get("engine_pnl_today", 0.0) or 0.0)
    warnings = scan_result.get("scan_warnings") or []
    opra = scan_result.get("opra_available", False)

    lines: list[str] = [SECTION_HEADER, ""]

    if missed_count == 0:
        lines.append(
            "No qualifying missed setups detected on the chart today — engine "
            f"took {engine_trades} trade(s) with ${engine_pnl:,.2f} P&L."
        )
        if warnings:
            lines.append("")
            lines.append(f"_(scanner warnings: {len(warnings)})_")
        return "\n".join(lines)

    pnl_label = f"+${total_pnl:,.0f}" if total_pnl >= 0 else f"-${abs(total_pnl):,.0f}"
    lines.append(
        f"**Total opportunities on the chart: {missed_count} missed setups, "
        f"{pnl_label} paper P&L left on the table.**"
    )
    lines.append(
        f"**Engine captured: {edge_capture_pct:.0f}% of available edge "
        f"(engine took {engine_trades} trade(s), ${engine_pnl:,.2f}).**"
    )
    lines.append("")

    # Table.
    lines.append("| Time | Level | Type | Setup | Dir | Strike | Would-be P&L | Hold | Why missed |")
    lines.append("|---|---|---|---|---|---|---|---|---|")

    rows = _flatten_to_rows(scan_result)
    # Sort by would-be P&L (descending) so the biggest misses surface first.
    rows.sort(key=lambda r: r["pnl"], reverse=True)
    for r in rows:
        pnl_cell = f"+${r['pnl']:,.0f}" if r["pnl"] >= 0 else f"-${abs(r['pnl']):,.0f}"
        lines.append(
            f"| {r['time']} | {r['level']:.2f} | {r['itype']} | {r['setup']} | "
            f"{r['direction']} | {r['strike']} | {pnl_cell} | {r['hold']}m | "
            f"{r['why']} |"
        )

    # Root causes.
    why_counter: Counter[str] = Counter(r["why"] for r in rows)
    if why_counter:
        lines.append("")
        lines.append("**Root causes (deduplicated):**")
        for cause, n in why_counter.most_common():
            lines.append(f"- {cause} ({n} of {missed_count})")

    if not opra:
        lines.append("")
        lines.append(
            "_(Pricing source: BS estimate fallback — OPRA cache unavailable. "
            "Premiums are first-order approximations only.)_"
        )

    if warnings:
        lines.append("")
        lines.append(f"_(scanner warnings: {len(warnings)} — see eod-deep JSON.)_")

    return "\n".join(lines)


def _flatten_to_rows(scan_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten level_interactions[].qualifying_setups[] into a row list."""
    out: list[dict[str, Any]] = []
    interactions = scan_result.get("level_interactions") or []
    for inter in interactions:
        time_str = inter.get("bar_time", "??:??")
        level_price = float(inter.get("level", 0.0) or 0.0)
        itype = INTERACTION_TYPE_LABELS.get(inter.get("interaction_type", ""), "?")
        for setup in inter.get("qualifying_setups") or []:
            out.append({
                "time": time_str,
                "level": level_price,
                "itype": itype,
                "setup": SETUP_SHORT.get(setup.get("setup", ""), setup.get("setup", "?")),
                "direction": setup.get("direction", "?"),
                "strike": setup.get("strike", "?"),
                "pnl": float(setup.get("would_be_pnl_dollars", 0.0) or 0.0),
                "hold": int(setup.get("would_be_hold_minutes", 0) or 0),
                "why": setup.get("why_missed") or "engine did not fire",
            })
    return out


__all__ = ["render_section"]
