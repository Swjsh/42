"""eod_full_audit.py — "everything Gamma did, thought, logged today" in ONE report. $0.

Aggregates every append-only ledger into a single EOD audit so nothing is invisible
(OP-25: silent success = silent failure). READ-ONLY. Writes
analysis/daily-brief/{date}-FULL-AUDIT.md. Run at EOD (after flatten).

Sources: decisions.jsonl (engine), fleet/decisions/*.jsonl (each fleet arm),
manager-log.jsonl (the free Manager), swarm-calls.jsonl + minimax-calls.jsonl (free
models), live-shadow-scorecard.json (sight validation), contender-rank-*.json (ranker),
manager-feedback.md (Sonnet overseer), journal/{date}.md + trades.csv (trades),
discord-outbox.jsonl (what J was pinged), spend-{date}.json (cost), STATUS.md (broken).
"""
from __future__ import annotations

import glob
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1].parent
STATE = REPO / "automation" / "state"
sys.path.insert(0, str(REPO / "setup" / "scripts"))
from et_clock import et_now as _et_clock_now  # DST-aware ET (TZ-SYSTEMIC fix)


def _et_now() -> datetime:
    """ET from UTC via DST-aware et_clock (replaces hardcoded -4)."""
    return _et_clock_now()


TODAY = _et_now().strftime("%Y-%m-%d")


def _jsonl(p: Path) -> list[dict]:
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="replace").strip().splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _today(rows: list[dict], key="date") -> list[dict]:
    return [r for r in rows if (r.get(key) or r.get("date_et") or (r.get("ts", "")[:10])) == TODAY]


def _today_ts(rows: list[dict]) -> list[dict]:
    out = []
    cut = datetime.now(timezone.utc) - timedelta(hours=14)
    for r in rows:
        t = r.get("ts") or r.get("ts_et") or ""
        try:
            dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cut:
                out.append(r)
        except ValueError:
            continue
    return out


def section(title: str) -> str:
    return f"\n## {title}\n"


def build() -> str:
    L = [f"# FULL AUDIT — {TODAY} (everything Gamma did / thought / logged)",
         f"_generated {_et_now():%H:%M} ET — read-only aggregate of every ledger_"]

    # ENGINE
    dec = _today(_jsonl(STATE / "decisions.jsonl"))
    acts = Counter(r.get("action") for r in dec)
    L.append(section("ENGINE (heartbeat) — every tick"))
    L.append(f"- ticks today: **{len(dec)}** | actions: {dict(acts)}")
    if dec:
        last = dec[-1]
        L.append(f"- last tick {last.get('time_et')}: action={last.get('action')} "
                 f"spy={last.get('spy')} vix={last.get('vix')} ribbon={last.get('ribbon_stack')} "
                 f"setup={last.get('setup_name')}")
    enters = [r for r in dec if "ENTER" in (r.get("action") or "")]
    exits = [r for r in dec if "EXIT" in (r.get("action") or "") or "FILL" in (r.get("action") or "")]
    L.append(f"- ENTER ticks: {len(enters)} | EXIT/FILL ticks: {len(exits)}")

    # TRADES
    tcsv = REPO / "journal" / "trades.csv"
    n_trades_today = 0
    if tcsv.exists():
        for line in tcsv.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
            if TODAY in line:
                n_trades_today += 1
    L.append(section("TRADES"))
    L.append(f"- trades.csv rows tagged today: **{n_trades_today}** "
             f"(see journal/{TODAY}.md for the full per-trade log)")

    # FLEET (the other accounts)
    L.append(section("FLEET ARMS — per-account decisions"))
    for fp in sorted(glob.glob(str(STATE / "fleet" / "decisions" / "*.jsonl"))):
        arm = Path(fp).stem
        rows = _today(_jsonl(Path(fp)))
        a = Counter(r.get("action") or r.get("decision") for r in rows)
        placed = sum(1 for r in rows if "ENTER" in str(r.get("action") or r.get("decision") or "").upper())
        L.append(f"- **{arm}**: {len(rows)} decisions | placed/ENTER: {placed} | {dict(a)}")

    # FREE WORKFORCE
    L.append(section("FREE WORKFORCE"))
    mgr = _today_ts(_jsonl(STATE / "manager-log.jsonl"))
    disp = [r for r in mgr if r.get("phase") in ("dispatch", "python")]
    roles = Counter(r.get("role") or r.get("tool") for r in disp)
    L.append(f"- **Manager** cycles: {len(mgr)} | dispatched: {dict(roles)} "
             f"| outputs in analysis/manager/")
    # Kitchen candidates today
    cands = [p for p in glob.glob(str(REPO / "strategy" / "candidates" / "2026-*.md"))
             if Path(p).name.startswith(TODAY)]
    L.append(f"- **Kitchen** candidates cooked today: {len(cands)}")
    # Validator
    sc = STATE / "live-shadow-scorecard.json"
    if sc.exists():
        try:
            c = json.loads(sc.read_text(encoding="utf-8"))
            L.append(f"- **Sight validator**: n={c.get('n')} sight_accuracy={c.get('sight_accuracy')} "
                     f"dt_agreement={c.get('dt_agreement')} commit_rate={c.get('commit_rate')}")
        except (json.JSONDecodeError, OSError):
            pass
    # Ranker
    rk = REPO / "analysis" / "recommendations" / f"contender-rank-{TODAY}.json"
    if rk.exists():
        try:
            c = json.loads(rk.read_text(encoding="utf-8"))
            L.append(f"- **Contender ranker**: scored {c.get('total_scored')}/{c.get('total_rows')} "
                     f"| survivors over {c.get('j_edge_floor')} floor: **{c.get('survivors_over_floor')}** "
                     f"| WF-strong: {c.get('n_wf_strong')}")
        except (json.JSONDecodeError, OSError):
            pass

    # FREE-MODEL CALLS
    sw = _today_ts(_jsonl(STATE / "swarm-calls.jsonl"))
    mm = _today_ts(_jsonl(STATE / "minimax-calls.jsonl"))
    sw_fail = sum(1 for r in sw if not r.get("ok"))
    mm_fail = sum(1 for r in mm if not r.get("ok"))
    L.append(section("FREE-MODEL CALLS"))
    L.append(f"- swarm (manager/validators): {len(sw)} calls, {sw_fail} fail")
    L.append(f"- kitchen (seeder/reviewer/cooks): {len(mm)} calls, {mm_fail} fail")

    # FLAGS SENT TO J
    L.append(section("FLAGS SENT TO DISCORD (what J was told)"))
    ob = _today_ts(_jsonl(STATE / "discord-outbox.jsonl"))
    if ob:
        for r in ob[-12:]:
            L.append(f"- {r.get('source','?')}: {str(r.get('alert') or r.get('reason') or '')[:140]}")
    else:
        L.append("- (none today)")

    # COST
    L.append(section("COST"))
    sp = REPO / "automation" / "state" / f"spend-{TODAY}.json"
    if sp.exists():
        try:
            c = json.loads(sp.read_text(encoding="utf-8"))
            L.append(f"- claude_cost: **${c.get('claude_cost_usd', 0):.2f}** "
                     f"({c.get('claude_sessions', 0)} sessions) | minimax: ${c.get('minimax_cost_usd', 0):.4f} "
                     f"| free-pool: $0")
        except (json.JSONDecodeError, OSError):
            pass
    else:
        L.append("- (spend-summary not yet run for today)")

    # BROKEN
    L.append(section("KNOWN BROKEN / FLAGS"))
    st = (REPO / "automation" / "overnight" / "STATUS.md")
    flags = []
    if st.exists():
        import re
        for ln in st.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.search(r"BROKEN|RED:|STALL", ln) and TODAY in ln:
                flags.append(ln.strip()[:160])
    L.append("\n".join(f"- {f}" for f in flags[:6]) if flags else "- (none flagged today)")

    return "\n".join(L)


def main() -> int:
    out = build()
    dest = REPO / "analysis" / "daily-brief" / f"{TODAY}-FULL-AUDIT.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(out, encoding="utf-8")
    print(f"wrote {dest.relative_to(REPO)} ({len(out)} chars)")
    print(out[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
