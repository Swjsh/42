"""eod_full_audit.py — "everything Gamma did, thought, logged today" in ONE report. $0.

Aggregates every append-only ledger into a single EOD audit so nothing is invisible
(OP-25: silent success = silent failure). READ-ONLY. Writes
analysis/daily-brief/{date}-FULL-AUDIT.md. Run at EOD (after flatten).

Sources: core-decisions.jsonl (the live deterministic engine, account-labeled safe/bold —
fixed 2026-07-14, see strategy/candidates/_validator-inbox/2026-07-14-tick-audit-zero-
count-bug.md; the old root decisions.jsonl was a dead pre-v15 LLM-heartbeat relic, last
written 2026-06-25 by the unscheduled heartbeat_persist_writer.py, and always silently
undercounted to 0), fleet/<arm>/decisions.jsonl (each active fleet arm — same fix, the old
fleet/decisions/*.jsonl mirror dir was a frozen WATCH-DEMO fixture snapshot, see
gamma_glance.py's identical prior fix), manager-log.jsonl (the free Manager),
swarm-calls.jsonl + minimax-calls.jsonl (free models), live-shadow-scorecard.json (sight
validation), contender-rank-*.json (ranker), manager-feedback.md (Sonnet overseer),
journal/{date}.md + trades.csv (trades), discord-outbox.jsonl (what J was pinged),
spend-{date}.json (cost), STATUS.md (broken).
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
from et_clock import ET_TZ as _ET_TZ


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
    """Rows dated TODAY, trying `key`, then `date_et`, then `ts`-prefix, then `ts_et`-prefix.

    core-decisions.jsonl / fleet/*/decisions.jsonl rows carry no 'date'/'date_et'/'ts'
    field at all -- only 'ts_et' (a full ISO timestamp, not a bare date) -- so a path-only
    source swap silently returns 0 rows without this fallback (2026-07-14 fix, see
    strategy/candidates/_validator-inbox/2026-07-14-tick-audit-zero-count-bug.md).
    """
    out = []
    for r in rows:
        val = r.get(key) or r.get("date_et") or (r.get("ts", "")[:10]) or (r.get("ts_et", "")[:10])
        if val == TODAY:
            out.append(r)
    return out


def _is_weekend(date_str: str) -> bool:
    return datetime.strptime(date_str, "%Y-%m-%d").weekday() >= 5


def _stale_source_note(path: Path, now: datetime) -> str | None:
    """Flag a source file whose mtime predates TODAY once market hours have started.

    A 0-row count is normal before 09:30 ET (engine hasn't ticked yet) or on a weekend
    (no fires expected) -- only flag once there's actually been an opportunity to write.
    Non-vacuity guard per the 2026-07-14 zero-count-bug fix: a 0 from a genuinely stale/
    dead path must never render identically to a genuinely quiet engine.
    """
    if _is_weekend(TODAY) or now.strftime("%H:%M") < "09:30":
        return None
    if not path.exists():
        return f"STALE SOURCE -- {path.name} does not exist"
    mtime_et = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(_ET_TZ)
    mtime_day = mtime_et.strftime("%Y-%m-%d")
    if mtime_day != TODAY:
        return (f"STALE SOURCE -- {path.name} last modified {mtime_day}, not {TODAY}; "
                f"a 0 count here may reflect a dead/misrouted path, not a quiet engine")
    return None


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

    # ENGINE — core-decisions.jsonl carries one row per ACCOUNT per tick (safe + bold),
    # unlike the old dead single-stream decisions.jsonl, so report both accounts.
    now = _et_now()
    core_path = STATE / "core-decisions.jsonl"
    dec = _today(_jsonl(core_path))
    stale = _stale_source_note(core_path, now)
    L.append(section("ENGINE (heartbeat_core) — every tick, per account"))
    if stale:
        L.append(f"- ⚠️ {stale}")
    for acct in ("safe", "bold"):
        acct_rows = [r for r in dec if r.get("account") == acct]
        acts = Counter(r.get("action") for r in acct_rows)
        L.append(f"- {acct} ticks today: **{len(acct_rows)}** | actions: {dict(acts)}")
        if acct_rows:
            last = acct_rows[-1]
            L.append(f"  - last {acct} tick {last.get('ts_et')}: action={last.get('action')} "
                     f"spy={last.get('spy')} vix={last.get('vix')} ribbon={last.get('ribbon')} "
                     f"setup={last.get('setup')}")
    enters = [r for r in dec if "ENTER" in (r.get("action") or "")]
    exits = [r for r in dec if "EXIT" in (r.get("action") or "") or "FILL" in (r.get("action") or "")]
    L.append(f"- ENTER ticks: {len(enters)} | EXIT/FILL ticks: {len(exits)} (both accounts combined)")

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

    # FLEET (the other accounts) — glob the real per-arm dirs, NOT the frozen
    # fleet/decisions/*.jsonl mirror (WATCH-DEMO fixture snapshot, 0 real rows; same fix
    # gamma_glance.py already made — see module docstring).
    L.append(section("FLEET ARMS — per-account decisions"))
    fleet_paths = sorted(glob.glob(str(STATE / "fleet" / "*" / "decisions.jsonl")))
    if not fleet_paths:
        L.append("- ⚠️ no fleet/<arm>/decisions.jsonl files found")
    for fp in fleet_paths:
        arm = Path(fp).parent.name
        fp_path = Path(fp)
        rows = _today(_jsonl(fp_path))
        stale = _stale_source_note(fp_path, now)
        a = Counter(r.get("action") or r.get("decision") for r in rows)
        placed = sum(1 for r in rows if "ENTER" in str(r.get("action") or r.get("decision") or "").upper())
        stale_tag = f" ⚠️ {stale}" if stale else ""
        L.append(f"- **{arm}**: {len(rows)} decisions | placed/ENTER: {placed} | {dict(a)}{stale_tag}")

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

    # TRENDLINES -- J directed 2026-08-20: "we need to check EVERY SINGLE DAY.
    # Do we see any trend lines? How do we act on them?" This section is mandatory
    # and must speak up when it has nothing, because a silent trendline section is
    # indistinguishable from a day with no lines (C7).
    L.append(section("TRENDLINES — do we see any? how would we act?"))
    try:
        sys.path.insert(0, str(REPO / "setup" / "scripts"))
        import trendline_shadow as _tls
        roll = _tls.daily_rollup(TODAY)
        if not roll.get("logged"):
            L.append(f"- ⚠️ **NO TRENDLINE DATA for {TODAY}** — {roll.get('reason')}. "
                     "The shadow did not run or found nothing; treat as BLIND, not as "
                     "'no lines today'. Re-run: `backtest/.venv/Scripts/python.exe "
                     "setup/scripts/trendline_shadow.py --date " + TODAY + "`")
        else:
            L.append(f"- **Yes — {roll['distinct_lines']} distinct line(s), "
                     f"{roll['events']} event(s)** "
                     f"({roll['ascending']} ascending / {roll['descending']} descending; "
                     f"{roll['breaks']} break, {roll['rejects']} reject)")
            if roll["theo_trades"]:
                L.append(f"- **How we'd act:** {roll['theo_trades']} theoretical trade(s) "
                         f"— WR {roll['theo_wr']:.0%}, {roll['theo_points']:+.2f} SPY pts "
                         f"({roll['theo_points_per_trade']:+.3f}/trade, "
                         f"best {roll['best']:+.2f} / worst {roll['worst']:+.2f})")
            else:
                L.append("- **How we'd act:** no line met the quality bar "
                         f"(>= {_tls.THEO_MIN_TOUCHES} touches, R² >= {_tls.THEO_MIN_R2}) "
                         "— we would have stood down.")
            wk = _tls.week_audit(TODAY)
            if wk.get("theo_trades"):
                L.append(f"- **Trailing {wk['sessions']} sessions** "
                         f"({wk['from']} → {wk['to']}): {wk['theo_trades']} trades, "
                         f"WR {wk['theo_wr']:.0%}, {wk['theo_points']:+.2f} pts "
                         f"({wk['theo_points_per_trade']:+.3f}/trade)")
                L.append("  - per session: " + ", ".join(
                    f"{d} {v:+.1f}" for d, v in wk["by_session"].items()))
                # A trailing window with no baseline re-cherry-picks itself every
                # day. Percentile + concentration ship WITH the number, never after.
                bl = _tls.baseline(TODAY)
                if bl.get("ok"):
                    pct = bl["window_percentile"]
                    share = bl["top_session_share_of_window"]
                    bits = []
                    if pct is not None:
                        bits.append(f"that window ranks **{pct:.0%}ile** of "
                                    f"{bl['windows']} comparable windows "
                                    f"({bl['windows_negative']} of them negative)")
                    if share:
                        bits.append(f"one session supplied **{share:.0%}** of it")
                    if bits:
                        L.append("  - ⚠️ context: " + "; ".join(bits))
                    L.append(f"  - whole sample ({bl['sessions_total']} sessions, "
                             f"{bl['all_trades']} trades): WR {bl['all_wr']:.0%}, "
                             f"**{bl['all_points_per_trade']:+.3f}/trade** — "
                             f"{bl['sessions_positive']}/{bl['sessions_total']} sessions "
                             f"positive, top 3 sessions = "
                             f"{bl['top3_share_of_total']:.0%} of all profit. "
                             "**The whole-sample number is the honest one.**")
        L.append("- _SHADOW ONLY — no order was placed and no live gate saw this. "
                 "Standing verdict 2026-08-20: above a random-entry null, but the "
                 "session-clustered 95% CI straddles zero and the per-trade edge is "
                 "smaller than the 0DTE bid-ask spread. Evidence accumulating; "
                 "NOT a green light._")
    except Exception as exc:  # noqa: BLE001 — a broken shadow must be VISIBLE, not silent
        L.append(f"- ⚠️ **trendline shadow FAILED to report**: {type(exc).__name__}: {exc}")

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
    # The report is written UTF-8 and is already safe on disk by this point. Echoing a
    # preview to a cp1252 console, however, raised UnicodeEncodeError on the em-dashes
    # and emoji -- so this task exited 1 EVERY night despite writing a perfect file.
    # An exit code that reports failure on success is the same C7 class as one that
    # reports success on failure: it trains everyone to ignore it. The preview is a
    # convenience, so it degrades; the write is the product, so it decides the code.
    try:
        print(out[:1200])
    except UnicodeEncodeError:
        sys.stdout.reconfigure(errors="replace")
        print(out[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
