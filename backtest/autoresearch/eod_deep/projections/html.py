"""HTML projection — the visual trade card.

Refactored from the hand-rolled trade-card-2026-05-14.html.
Reads only from EodDeepDive dataclass — no parallel data.

Same visual style as the original card (GitHub dark theme palette).
"""
from __future__ import annotations

import html as html_mod

from ..schema import EodDeepDive, CATEGORY_KEYS


CSS = """
:root {
  --bg: #0d1117; --panel: #161b22; --panel-2: #1c2128; --border: #30363d;
  --text: #c9d1d9; --text-dim: #8b949e;
  --green: #3fb950; --green-bg: rgba(63, 185, 80, 0.15);
  --red: #f85149; --red-bg: rgba(248, 81, 73, 0.15);
  --gold: #d29922; --gold-bg: rgba(210, 153, 34, 0.15);
  --blue: #58a6ff; --blue-bg: rgba(88, 166, 255, 0.15);
  --purple: #bc8cff;
}
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: var(--bg); color: var(--text); margin: 0; padding: 24px; line-height: 1.5; }
.container { max-width: 1280px; margin: 0 auto; }
header { text-align: center; margin-bottom: 32px; padding-bottom: 24px; border-bottom: 2px solid var(--border); }
header .date { font-size: 14px; color: var(--text-dim); letter-spacing: 2px; text-transform: uppercase; margin-bottom: 8px; }
header h1 { margin: 0; font-size: 36px; font-weight: 700; }
header h1.green { color: var(--green); }
header h1.red { color: var(--red); }
header .setup { font-size: 16px; color: var(--purple); margin-top: 8px; font-family: 'SF Mono', Consolas, monospace; }
header .pnl-headline { margin-top: 16px; font-size: 48px; font-weight: 800; font-family: 'SF Mono', Consolas, monospace; }
header .pnl-pct { font-size: 24px; color: var(--text-dim); font-weight: normal; }
.grid { display: grid; gap: 20px; }
.grid-2 { grid-template-columns: 1fr 1fr; }
.grid-3 { grid-template-columns: repeat(3, 1fr); }
.grid-4 { grid-template-columns: repeat(4, 1fr); }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
.card-header { font-size: 12px; color: var(--text-dim); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 8px; }
.card-value { font-size: 28px; font-weight: 700; font-family: 'SF Mono', Consolas, monospace; }
.card-sub { color: var(--text-dim); font-size: 14px; margin-top: 4px; }
.green { color: var(--green); } .red { color: var(--red); }
.gold { color: var(--gold); } .blue { color: var(--blue); }
section { margin: 32px 0; }
section h2 { font-size: 18px; color: var(--text); border-left: 4px solid var(--green); padding-left: 12px; margin: 32px 0 16px; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); }
th { color: var(--text-dim); font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 1px; }
td.mono { font-family: 'SF Mono', Consolas, monospace; }
td.pnl-pos { color: var(--green); font-weight: 700; }
td.pnl-neg { color: var(--red); font-weight: 700; }
.score-bar { display: inline-block; width: 200px; height: 18px; background: var(--panel-2); border-radius: 3px; vertical-align: middle; overflow: hidden; }
.score-bar > span { display: block; height: 100%; transition: width 0.3s; }
.score-good > span { background: var(--green); }
.score-mid > span { background: var(--gold); }
.score-bad > span { background: var(--red); }
.category-row { display: grid; grid-template-columns: 60px 200px 100px 240px 1fr; gap: 12px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border); }
.category-row .num { color: var(--text-dim); font-family: 'SF Mono', Consolas, monospace; }
.category-row .name { font-weight: 600; text-transform: uppercase; font-size: 13px; letter-spacing: 1px; }
.category-row .score { font-family: 'SF Mono', Consolas, monospace; font-weight: 700; }
.category-row .narrative { color: var(--text-dim); font-size: 13px; }
footer { text-align: center; color: var(--text-dim); font-size: 12px; margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--border); }
.warning-box { background: var(--gold-bg); border-left: 4px solid var(--gold); padding: 12px 16px; border-radius: 6px; margin: 12px 0; }
"""


def _esc(s) -> str:
    return html_mod.escape(str(s)) if s is not None else ""


def _score_class(score: float) -> str:
    if score >= 80: return "score-good"
    if score >= 50: return "score-mid"
    return "score-bad"


def _money(x: float) -> str:
    if x is None: return "$0.00"
    return f"+${x:,.2f}" if x >= 0 else f"-${abs(x):,.2f}"


def render(d: EodDeepDive) -> str:
    pnl_class = "green" if d.day_pnl_dollars >= 0 else "red"
    pnl_sign = "+" if d.day_pnl_dollars >= 0 else ""
    setup_names = ", ".join(set(t.setup_name for t in d.trades)) if d.trades else "—"

    parts = ['<!DOCTYPE html>', '<html lang="en">', '<head>', '<meta charset="UTF-8">']
    parts.append(f'<title>EOD Deep-Dive — {_esc(d.date)}</title>')
    parts.append(f'<style>{CSS}</style></head><body>')
    parts.append('<div class="container">')

    # === Header ===
    parts.append('<header>')
    parts.append(f'<div class="date">EOD Deep-Dive · {_esc(d.date)} · Rule {_esc(d.rule_version_active)}</div>')
    if d.trades:
        title = "Trading day"
        parts.append(f'<h1 class="{pnl_class}">{_esc(title)}</h1>')
    else:
        parts.append('<h1 class="blue">No trades today (engine scanning)</h1>')
    parts.append(f'<div class="setup">{_esc(setup_names)}</div>')
    parts.append(f'<div class="pnl-headline {pnl_class}">{pnl_sign}${d.day_pnl_dollars:,.0f} <span class="pnl-pct">({d.day_pnl_pct:+.2f}%)</span></div>')
    parts.append('</header>')

    # === Summary cards ===
    parts.append('<section><h2>Day at a glance</h2><div class="grid grid-4">')
    parts.append(f'<div class="card"><div class="card-header">Account equity</div>'
                 f'<div class="card-value">${d.account_equity_end:,.0f}</div>'
                 f'<div class="card-sub">from ${d.account_equity_start:,.0f}</div></div>')
    parts.append(f'<div class="card"><div class="card-header">Trades</div>'
                 f'<div class="card-value">{d.day_trade_count}</div>'
                 f'<div class="card-sub">{sum(len(t.fills) for t in d.trades)} total fills</div></div>')
    parts.append(f'<div class="card"><div class="card-header">Process score</div>'
                 f'<div class="card-value {_score_class(d.process_score)}">{d.process_score}/100</div>'
                 f'<div class="card-sub">weighted across 12 dimensions</div></div>')
    parts.append(f'<div class="card"><div class="card-header">Edge capture</div>'
                 f'<div class="card-value {_score_class(d.edge_capture_pct)}">{d.edge_capture_pct:.1f}%</div>'
                 f'<div class="card-sub">actual vs perfect-hindsight</div></div>')
    parts.append('</div></section>')

    # === Market session ===
    mss = d.market_session_summary
    parts.append('<section><h2>Market session</h2><table>')
    parts.append(f'<tr><th>Field</th><th>Value</th></tr>')
    parts.append(f'<tr><td>SPY H/L/C</td><td class="mono">{_esc(mss.get("session_high"))} / {_esc(mss.get("session_low"))} / {_esc(mss.get("session_close"))}</td></tr>')
    parts.append(f'<tr><td>VIX close</td><td class="mono">{_esc(mss.get("vix_close"))} ({_esc(mss.get("vix_dir"))})</td></tr>')
    parts.append(f'<tr><td>Predicted regime</td><td>{_esc(mss.get("regime_predicted"))}</td></tr>')
    parts.append('</table></section>')

    # === Trades ===
    if d.trades:
        parts.append('<section><h2>Trades</h2>')
        for t in d.trades:
            parts.append('<div class="card" style="margin-bottom: 20px;">')
            parts.append(f'<div class="card-header">{_esc(t.id)} · {_esc(t.setup_name)}</div>')
            parts.append(f'<h3 style="margin: 4px 0 12px;">{_esc(t.underlying)} {int(t.strike)}{_esc(t.option_type)} · {_esc(t.direction)} · score {_esc(t.setup_score)}</h3>')
            parts.append(f'<div class="card-sub">Realized: <strong class="green">{_money(t.pnl_dollars_realized)}</strong> ({t.pnl_pct_on_capital:+.1f}%) · Hold: {t.hold_minutes} min · Doctrine: {t.doctrine_compliance_score:.0f}/100</div>')
            parts.append('<table><thead><tr><th>Time</th><th>Side</th><th>Qty</th><th>Price</th><th>Source</th><th>Reason</th></tr></thead><tbody>')
            for f in t.fills:
                pnl_cls = ""
                parts.append(f'<tr><td class="mono">{_esc(f.time_et)}</td><td>{_esc(f.side)}</td>'
                             f'<td class="mono">{f.qty}</td><td class="mono">${f.price:.2f}</td>'
                             f'<td>{_esc(f.source)}</td><td>{_esc(f.reason)}</td></tr>')
            parts.append('</tbody></table>')

            if t.counterfactuals:
                parts.append('<div class="card-header" style="margin-top: 16px;">COUNTERFACTUALS</div>')
                parts.append('<table><thead><tr><th>Scenario</th><th>P&amp;L</th><th>Δ vs actual</th><th>Method</th></tr></thead><tbody>')
                for cf in t.counterfactuals:
                    delta_cls = "pnl-pos" if cf.delta_vs_actual >= 0 else "pnl-neg"
                    parts.append(f'<tr><td>{_esc(cf.name)}</td>'
                                 f'<td class="mono">{_money(cf.pnl_dollars)}</td>'
                                 f'<td class="mono {delta_cls}">{_money(cf.delta_vs_actual)}</td>'
                                 f'<td style="font-size: 12px; color: var(--text-dim);">{_esc(cf.method)}</td></tr>')
                parts.append('</tbody></table>')

            parts.append('</div>')
        parts.append('</section>')

    # === Categories ===
    parts.append('<section><h2>The 12 dimensions</h2>')
    for i, key in enumerate(CATEGORY_KEYS, 1):
        cat = d.categories.get(key)
        if not cat: continue
        bar_pct = int(cat.score)
        parts.append(f'<div class="category-row">')
        parts.append(f'<div class="num">{i:02d}</div>')
        parts.append(f'<div class="name">{_esc(key)}</div>')
        parts.append(f'<div class="score {_score_class(cat.score)}">{cat.score}/100</div>')
        parts.append(f'<div class="score-bar {_score_class(cat.score)}"><span style="width: {bar_pct}%"></span></div>')
        parts.append(f'<div class="narrative">{_esc(cat.narrative)}</div>')
        parts.append('</div>')
    parts.append('</section>')

    # === Research handoffs ===
    rh = d.research_handoffs
    parts.append('<section><h2>Research handoffs · feedback to backtest pipeline</h2>')
    if rh.get("fixes_shipped_today"):
        parts.append(f'<div class="warning-box"><strong>Fixes shipped today:</strong> {", ".join(rh["fixes_shipped_today"])}</div>')
    if rh.get("ingest_warnings"):
        parts.append('<div class="warning-box"><strong>Ingest warnings:</strong><ul>')
        for w in rh["ingest_warnings"]:
            parts.append(f'<li>{_esc(w)}</li>')
        parts.append('</ul></div>')
    parts.append('</section>')

    # === Footer ===
    parts.append(f'<footer>Generated {_esc(d.generated_at_et)} · Schema {_esc(d.schema_version)} · {len(d.trades)} trades · '
                 f'Process {d.process_score}/100 · Edge {d.edge_capture_pct:.1f}%</footer>')
    parts.append('</div></body></html>')
    return "\n".join(parts)
