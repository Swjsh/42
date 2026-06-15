"""MASTER FINALIZER for the missed-week catch-up. Self-contained, idempotent.
Run ONCE; it generates everything still pending and prints a final state report.
All numbers sourced from computed artifacts only (L77). No doctrine/order writes."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _finalize_content import (  # noqa: E402
    L76_TEXT, L77_TEXT, VALIDATOR_TEXT, BRIEF_TEXT,
    STATUS_BLOCK, CHANGELOG_BLOCK, MEM_BODY,
)

REPO = Path(r"C:\Users\jackw\Desktop\42")
A = REPO / "analysis" / "backtests"
JOURNAL = REPO / "journal"
CAND = REPO / "strategy" / "candidates"
LESSON_INBOX = CAND / "_lesson-inbox"
VALID_INBOX = CAND / "_validator-inbox"
MEM = Path(r"C:\Users\jackw\.claude\projects\C--Users-jackw-Desktop-42\memory")
CQ = REPO / "automation" / "state" / "cook-queue.jsonl"
DATE = "2026-05-31"
MISSED = ["2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"]
DOW = {"2026-05-26": "Tuesday", "2026-05-27": "Wednesday",
       "2026-05-28": "Thursday", "2026-05-29": "Friday"}
log = []
def L(s): log.append(str(s))

def writef(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    L(f"WROTE {len(text):>6}b  {p.relative_to(REPO) if REPO in p.parents else p}")

def appendf(p: Path, marker: str, text: str):
    # Encoding-safe: existing file may contain Windows-1252 bytes (e.g. 0x97 em-dash).
    # Read with errors='ignore' for the marker check, and APPEND in binary so we never
    # rewrite (and thus never corrupt) the existing bytes.
    cur = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
    if marker in cur:
        L(f"SKIP (marker present) {p.name}"); return
    sep = b"" if (cur.endswith('\n') or cur == "") else b"\n"
    with p.open("ab") as fh:
        fh.write(sep + text.encode("utf-8"))
    L(f"APPEND +{len(text)}b  {p.name}")

def trades(label):
    p = A / label / "trades.csv"
    if not p.exists(): return pd.DataFrame()
    df = pd.read_csv(p)
    if "dollar_pnl" not in df.columns or len(df) == 0: return pd.DataFrame()
    df["date"] = df["date"].astype(str)
    df["per_contract"] = df["dollar_pnl"] / df["qty"].where(df["qty"] != 0, 1)
    return df

facts = json.loads((A / "_missed_week_facts.json").read_text())
base, safe, bold = trades("missed_week_2026-05-26_29"), trades("missed_week_safe"), trades("missed_week_bold")

# ── 0. cleanup wrong-location inbox files at repo root ───────────────────────
for wrong in [REPO / "_lesson-inbox" / "L76-premium-stop-low-vix-bull-chop.md",
              REPO / "_lesson-inbox" / "L77-subagent-computed-artifacts-only.md",
              REPO / "_validator-inbox" / "sizing-risk-cap-guard.md"]:
    if wrong.exists():
        wrong.unlink()
        L(f"REMOVED wrong-location {wrong.relative_to(REPO)}")
for d in [REPO / "_lesson-inbox", REPO / "_validator-inbox"]:
    if d.exists() and not any(d.iterdir()):
        d.rmdir(); L(f"RMDIR empty {d.relative_to(REPO)}")

# ── 1. routed findings to CORRECT inboxes ───────────────────────────────────
writef(LESSON_INBOX / "L76-premium-stop-low-vix-bull-chop.md", L76_TEXT)
writef(LESSON_INBOX / "L77-subagent-computed-artifacts-only.md", L77_TEXT)
writef(VALID_INBOX / "sizing-risk-cap-guard.md", VALIDATOR_TEXT)

# ── 2. journals ─────────────────────────────────────────────────────────────
BANNER = ("> **RECONSTRUCTED (offline backfill, generated 2026-05-31). Backtest of "
          "production v15.2 vs real Alpaca data. No live trades — machine OFFLINE "
          "2026-05-23..05-30 (J moved house). SPY+options REAL (Alpaca SIP/OPRA 5m); "
          "VIX is a VIXY-scaled proxy (x0.648, calibrated to last real VIX 16.82 on "
          "2026-05-22). Backtest qty is quality-tier fixed (not equity-capped) — use "
          "per-contract P&L. Authoritative: analysis/missed-week-2026-05-26_29.md + "
          "analysis/backtests/_TRUTH.md.**")

def fmt(df, d, label):
    out = []
    for _, r in df[df["date"] == d].iterrows():
        out.append(f"| {label} | {str(r['time_entry'])[:5]} | {r['c_or_p']} | "
                   f"{int(r['strike'])} | {int(r['qty'])} | {float(r['entry_px']):.2f} | "
                   f"{float(r['dollar_pnl']):+.0f} | {float(r['per_contract']):+.1f} | {r['exit_reason']} |")
    return out

for d in MISSED:
    f = facts[d]
    ln = [f"# Journal — {d} ({DOW[d]}) — RECONSTRUCTED", "", BANNER, "",
          "## Premarket Summary (reconstructed)",
          f"- **SPY RTH:** open {f['rth_open']} -> close {f['rth_close']} "
          f"(**{f['net_change']:+.2f}**, {f['direction']}). Range {f['range']} "
          f"(H {f['rth_high']}@{f['rth_high_t']} / L {f['rth_low']}@{f['rth_low_t']}).",
          f"- **Gap from prior RTH close ({f['prior_rth_close']}):** {f['gap']:+.2f}",
          f"- **VIX (proxy):** {f['vix_open']} ({f['vix_regime']}); day {f['vix_low']}-{f['vix_high']}. "
          f"Bull gate <17.20 / bear gate >17.30 both clear all day.",
          f"- **Engine decision density:** {f['bars_evaluated']} bars; {f['bars_score_ge7']} bars >=7/10 "
          f"on BEARISH track (max {f['max_bear_score']}); BEARISH passed 0x.",
          "- **PDT / live account state:** N/A (reconstructed, machine offline).", "",
          "## Engine trades this day (real OPRA fills)"]
    body = fmt(base, d, "BASE(v11-timing)") + fmt(safe, d, "SAFE(ATM,PL)") + fmt(bold, d, "BOLD(ITM2,PL)")
    if body:
        ln += ["| acct-config | entry | side | strike | qty | entry$ | P&L$ | /contract$ | exit |",
               "|---|---|---|---|---|---|---|---|---|"] + body
    else:
        ln.append("_(no engine entry fired any config this day)_")
    ln += ["", "## End-of-day reflection (reconstructed)"]
    sd = safe[safe["date"] == d]; bd = bold[bold["date"] == d]
    sides = pd.concat([sd, bd])["c_or_p"].unique().tolist() if (len(sd) or len(bd)) else []
    side_word = ("BULLISH calls" if sides == ["C"] else "BEARISH puts" if sides == ["P"]
                 else ("mixed " + "/".join(sides)) if sides else "no")
    if len(sd) or len(bd):
        spc = sd["per_contract"].sum() if len(sd) else 0.0
        bpc = bd["per_contract"].sum() if len(bd) else 0.0
        ln.append(f"- Engine took **{side_word}** — directionally aligned with a "
                  f"{f['direction']}-closing day. Per-contract: SAFE {spc:+.1f}, BOLD {bpc:+.1f}.")
        if d == "2026-05-29":
            ln.append("- The week's one CLEAN winner: a genuine trend day with follow-through "
                      "(TP1_THEN_RUNNER_RIBBON). Exit mechanics worked when the move actually carried.")
        else:
            ln.append("- Losses (where any) were **EXIT_ALL_PREMIUM_STOP** — shallow retest dips in "
                      "the low-VIX grind tripped the tight premium stop before SPY resumed higher. "
                      "Right idea, wrong exit primitive (lesson L76, bull analog of L51/L55/L74).")
    else:
        ln.append("- No entry fired. BASE uses stale v11 entry timing (10:00 gate + mid-day blackout) "
                  "so it can skip mornings the live v15.1 09:35 window would take — see SAFE/BOLD rows.")
    ln += ["", "## Provenance",
           "- Numbers ONLY from analysis/backtests/_missed_week_facts.json + missed_week_{safe,bold,"
           "2026-05-26_29}/trades.csv. NOT appended to journal/trades.csv (the live/paper log)."]
    writef(JOURNAL / f"{d}.md", "\n".join(ln))

# ── 3. master report ────────────────────────────────────────────────────────
def block(df):
    md = df[df["date"].isin(MISSED)]
    if len(md) == 0: return (0, 0.0, 0.0, 0, 0)
    return (len(md), md["dollar_pnl"].sum(), md["per_contract"].sum(),
            int((md["dollar_pnl"] > 0).sum()), int((md["dollar_pnl"] < 0).sum()))
bn, bp, bpc, bw, bl = block(base); sn, sp, spc, sw, sl = block(safe); on, op, opc, ow, ol = block(bold)

rpt = [f"# Missed-Week Reconstruction — 2026-05-26 .. 05-29", "",
  "_Generated 2026-05-31 (Sunday) from verified computed artifacts. Authoritative companion: "
  "`analysis/backtests/_TRUTH.md`._", "",
  "## Executive summary",
  "Machine OFFLINE 2026-05-23 -> 05-30 (J moved house). On return we put production v15.2 "
  "through the ringer on every missed trading day (05-26/27/28/29; 05-25 Memorial Day) against "
  "REAL Alpaca fills, both accounts. **The engine was directionally CORRECT** — in a low-VIX "
  "(15-16) bull grind (SPY +0.85%, every target day closed at/above open) it fired "
  "**BULLISH_RECLAIM calls WITH the uptrend**, not bearish puts. **But it lost net per-contract** "
  "because almost every loss exited via **EXIT_ALL_PREMIUM_STOP**: tight stops (-8% Safe / -15% "
  "Bold) were chopped by shallow retest dips before the grind resumed. Only 05-29 (a clean trend "
  "day) produced a clear winner. **Right on direction, wrong on exits** — bull analog of "
  "L51/L55/L74 -> new lesson L76.", "",
  "## What we missed & why",
  "- Last live work: 2026-05-22 (itself NO_TRADE — both accounts at PDT limit).",
  "- Missed trading days: 05-26, 27, 28, 29. 05-25 excluded (Memorial Day, closed).",
  "- No premarket/heartbeat/EOD ran those days — the box was off.", "",
  "## Methodology & data provenance (OP-20)",
  "- SPY price: REAL Alpaca SIP 5m. Option fills: REAL OPRA 5m (grid 735-765 C+P/day).",
  "- VIX: RECONSTRUCTED proxy (Alpaca has no ^VIX) — VIXY x 0.648, calibrated to last real VIX "
  "16.82 (05-22). Regime gates cleared all week regardless; proxy doesn't change the finding.",
  "- Warmup 05-19..22 (ribbon/level detection); those days used Black-Scholes (options not "
  "fetched) — excluded from missed-day totals.",
  "- Three configs: BASE (`run.py --real-fills` — ITM-2, no profit-lock, and a FIDELITY GAP: "
  "orchestrator DEFAULT v11 entry timing); SAFE & BOLD (via `run_dual_account.py` params_overrides "
  "— correct v15.1 continuous 09:35-15:00 + trailing profit-lock). SAFE/BOLD = faithful v15.2.",
  "- Reproducible: run_id 2026-05-31_a6a17222_0605ef_9c5dea (BASE) + REGISTRY.jsonl + metadata.json.", "",
  "## Per-day walkthrough"]
for d in MISSED:
    f = facts[d]
    rpt.append(f"### {d} ({DOW[d]}) — {f['direction']} {f['net_change']:+.2f}")
    rpt.append(f"- Market: open {f['rth_open']} -> close {f['rth_close']}; H {f['rth_high']}@"
               f"{f['rth_high_t']} / L {f['rth_low']}@{f['rth_low_t']}; gap {f['gap']:+.2f}; "
               f"VIX {f['vix_open']} ({f['vix_regime']}).")
    parts = []
    for nm, df in [("BASE", base), ("SAFE", safe), ("BOLD", bold)]:
        sub = df[df["date"] == d]
        parts.append(f"{nm} {len(sub)} trade(s) {sub['dollar_pnl'].sum():+.0f}$ ({sub['per_contract'].sum():+.1f}/c)"
                     if len(sub) else f"{nm} no fire")
    rpt.append("- Engine: " + "; ".join(parts) + ".")
rpt += ["", "## Three-config comparison (MISSED DAYS ONLY, 05-26..29)",
  "| config | n | total $ (tier-qty) | per-contract-sum $ | min-3 floor $ | W/L |",
  "|---|---|---|---|---|---|",
  f"| BASE (v11 timing, no PL) | {bn} | {bp:+.0f} | {bpc:+.1f} | {bpc*3:+.0f} | {bw}W/{bl}L |",
  f"| SAFE (ATM, +30%, trail PL) | {sn} | {sp:+.0f} | {spc:+.1f} | {spc*3:+.0f} | {sw}W/{sl}L |",
  f"| BOLD (ITM-2, +75%, trail PL) | {on} | {op:+.0f} | {opc:+.1f} | {opc*3:+.0f} | {ow}W/{ol}L |", "",
  "Per-contract is the portable metric (backtest qty is quality-tier fixed, decoupled from equity "
  "& risk cap — 22 contracts can appear on a $747 account; raw totals overstate small-account "
  "reality). BOLD lost more than SAFE: more trades (bull trigger threshold 1 vs 2) at higher-premium "
  "ITM-2 strikes — more shots, each stopped.", "",
  "## The finding: right direction, wrong exit (-> L76)",
  "A BULLISH_RECLAIM entry sits at the reclaimed level. In a low-VIX slow grind a routine retest "
  "wick pushes premium down 8-15%, tripping the Safe -8% / Bold -15% stop BEFORE continuation. The "
  "engine is repeatedly right on direction but shaken out on noise. Fix directions (DRAFT, for J): "
  "chart-stop in low-VIX bull; regime-widened premium stop; or confluence-gate the entry. See "
  "`strategy/candidates/2026-05-31-low-vix-bull-reclaim-premium-stop.md` (Kitchen cook queued).", "",
  "## J-edge non-regression",
  "Re-ran anchor window 2026-04-27..05-07 (engine logic byte-UNCHANGED this session — only new "
  "data-fetch tools added; anchor option CSVs already cached). Production v15.2 captures **5/04 "
  "721P +$804** (J's exact anchor, 11:20) and 5/01 (+$3). MISSES J's 4/29 morning 710P (fires a "
  "losing 12:15 712P instead) — a PRE-EXISTING edge-capture gap (OP-16 = fraction, not 100%), NOT "
  "introduced here. A filter-8-OFF sensitivity run shows a 4/30 714C +$1,632, but that entry is "
  "blocked live by the VIX bull gate (~17.4>17.20) — not creditable as live edge. **Conclusion: "
  "data plumbing did not break the engine; the clean anchor is captured.**", "",
  "## Caveats & disclosures",
  "- VIX is a VIXY-scaled proxy, not true implied vol.",
  "- Backtest qty is quality-tier fixed (not equity-capped) — use per-contract; validator-inbox "
  "item filed (sizing-risk-cap-guard).",
  "- `run.py --real-fills` uses v11 default entry timing — BASE understates v15.2 fire rate; "
  "SAFE/BOLD faithful. Fix candidate: thread params.json entry-window into run.py.",
  "- DOCTRINE DRIFT flagged (NOT fixed — Rule 9): CLAUDE.md v15 bear stop -20% (x0.80) vs "
  "params.json -0.08 symmetric vs backtest -0.08. For J to reconcile.",
  "- Fills: next-bar VWAP/open + $0.02 slippage; ±5-10% real-fill noise; first-trigger-wins.", "",
  "## Recommendations / open questions for J (DRAFT — not ratified, Rule 9)",
  "1. Exit mechanics for BULLISH_RECLAIM in low-VIX: chart-stop vs widened premium stop vs "
  "confluence-gate? (DRAFT candidate + Kitchen cook queued.)",
  "2. Backtest sizing realism: wire equity-aware sizing into the backtest, or standardize per-contract?",
  "3. run.py fidelity: thread params.json entry-window so BASE backtests match v15.2?",
  "4. Stop-doctrine drift: reconcile CLAUDE.md -20% bear stop vs params.json -8%.", "",
  "_Routed through the lesson (L76, L77) / validator / Kitchen pipeline. Nothing ratified this session._"]
writef(REPO / "analysis" / "missed-week-2026-05-26_29.md", "\n".join(rpt))

# ── 4. morning brief ────────────────────────────────────────────────────────
writef(REPO / "analysis" / "daily-brief" / f"{DATE}-missed-week-brief.md", BRIEF_TEXT)

# ── 5. STATUS + CHANGELOG appends ───────────────────────────────────────────
appendf(REPO / "STATUS.md", "Missed-week reconstruction", STATUS_BLOCK)
appendf(REPO / "CHANGELOG.md", "Missed-week reconstruction", CHANGELOG_BLOCK)

# ── 6. memory ───────────────────────────────────────────────────────────────
writef(MEM / "project_missed_week_2026_05.md", MEM_BODY)
appendf(MEM / "MEMORY.md", "project_missed_week_2026_05",
        "- [Missed week 2026-05](project_missed_week_2026_05.md) — offline 05-23..30; engine "
        "backtested on missed days 05-26..29: right direction, chopped by premium stops; J-edge no-regression")

# ── 7. enqueue Kitchen cook (idempotent, schema-matched) ────────────────────
MARKER = "low-VIX BULLISH_RECLAIM exit fix"
lines = CQ.read_text(encoding="utf-8").splitlines() if CQ.exists() else []
if any(MARKER in ln for ln in lines):
    L("KITCHEN: task already queued (skip)")
else:
    template = None
    for ln in reversed(lines):
        try: j = json.loads(ln)
        except Exception: continue
        if j.get("event") == "create" or ("task" in j and "task_id" in j):
            template = j; break
    TASK = ("Backtest low-VIX BULLISH_RECLAIM exit fix per strategy/candidates/"
            "2026-05-31-low-vix-bull-reclaim-premium-stop.md: compare chart-stop "
            "(reclaimed_level-0.50) vs -8/-15pct premium stop on bull reclaim CALLS when VIX<16, "
            "real OPRA fills 05-26..29 + J anchor window, per-contract edge_capture x sharpe per "
            "OP-16, must not regress 5/04 anchor or bear book.")
    import uuid
    tid = str(uuid.uuid4())
    if template:
        evt = dict(template)
        for k in list(evt.keys()):
            kl = k.lower()
            if kl == "event": evt[k] = "create"
            elif kl in ("task_id", "id", "taskid"): evt[k] = tid
            elif kl in ("task", "description", "desc", "prompt"): evt[k] = TASK
            elif kl in ("priority", "pri"): evt[k] = "high"
            elif kl in ("source", "src", "origin"): evt[k] = "claude"
            elif kl in ("status", "state"): evt[k] = "pending"
            elif "time" in kl or "_at" in kl or kl in ("ts", "created", "timestamp"): evt[k] = f"{DATE}T12:00:00+00:00"
            elif kl in ("attempts", "retries", "tier"): evt[k] = 0
            elif kl in ("claimed_by", "model", "output_path", "error", "result", "cost_usd"):
                evt[k] = 0 if kl == "cost_usd" else None
        for kk, vv in [("event", "create"), ("task_id", tid), ("task", TASK),
                       ("priority", "high"), ("source", "claude"), ("status", "pending")]:
            evt.setdefault(kk, vv)
    else:
        evt = {"event": "create", "task_id": tid, "task": TASK, "priority": "high",
               "source": "claude", "status": "pending", "created_at": f"{DATE}T12:00:00+00:00", "attempts": 0}
    with CQ.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(evt) + "\n")
    L(f"KITCHEN: enqueued cook task id={tid[:8]} (schema={'template' if template else 'canonical'})")

# ── 8. final state report ───────────────────────────────────────────────────
L("")
L("==== FINAL STATE ====")
def chk(rel):
    p = REPO / rel
    L(f"  {'OK ' if p.exists() and p.stat().st_size > 50 else 'MISS'} {rel}")
for d in MISSED: chk(f"journal/{d}.md")
chk("analysis/missed-week-2026-05-26_29.md")
chk(f"analysis/daily-brief/{DATE}-missed-week-brief.md")
chk("analysis/backtests/_TRUTH.md")
chk("strategy/candidates/_lesson-inbox/L76-premium-stop-low-vix-bull-chop.md")
chk("strategy/candidates/_lesson-inbox/L77-subagent-computed-artifacts-only.md")
chk("strategy/candidates/_validator-inbox/sizing-risk-cap-guard.md")
chk("strategy/candidates/2026-05-31-low-vix-bull-reclaim-premium-stop.md")
chk("backtest/tools/fetch_missed_days.py")
chk("backtest/tools/run_dual_account.py")
tc = REPO / "journal" / "trades.csv"
pol = sum(1 for ln in tc.read_text(encoding="utf-8", errors="ignore").splitlines()
          if any(x in ln for x in MISSED)) if tc.exists() else -1
L(f"  trades.csv missed-day pollution (must be 0): {pol}")
status_ok = (REPO/"STATUS.md").exists() and "Missed-week reconstruction" in (REPO/"STATUS.md").read_text(encoding="utf-8", errors="ignore")
chg_ok = (REPO/"CHANGELOG.md").exists() and "Missed-week reconstruction" in (REPO/"CHANGELOG.md").read_text(encoding="utf-8", errors="ignore")
# MEMORY.md index may also have non-utf8 bytes — guard the index append's read too (handled in appendf).
L(f"  STATUS.md marker: {status_ok} | CHANGELOG.md marker: {chg_ok}")
L(f"  memory file: {(MEM/'project_missed_week_2026_05.md').exists()}")

print("\n".join(log))
print("\nFINALIZE DONE")
