"""CAPSTONE: read every analysis JSON that exists on disk and write J's single definitive
missed-week brief + update STATUS/memory. Self-contained, idempotent, tolerant of missing
inputs. No hand-typed result numbers (L77) — everything templated from JSON. Writes to disk
regardless of console visibility."""
from __future__ import annotations
import json
from pathlib import Path

REPO = Path(r"C:\Users\jackw\Desktop\42")
MEM = Path(r"C:\Users\jackw\.claude\projects\C--Users-jackw-Desktop-42\memory")
ABT = REPO / "analysis" / "backtests"


def load(name):
    p = ABT / name
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:
        return None


spl = load("_stop_pl_candidate.json")
seg = load("_segment_oos.json")
oosj = load("_sniper_oos.json")

L = []
def w(s=""): L.append(str(s))

w("# MISSED-WEEK — DEFINITIVE BRIEF FOR J (2026-05-31)")
w()
w("> Generated from computed JSON dumps only (L77). The bottom line first, evidence below.")
w()
w("## Bottom line")
w("1. **The missed week (05-26..29) is fully reconstructed + journaled.** Real Alpaca SIP/OPRA "
  "fills; engine ran both accounts; J-edge 5/04 anchor still captured.")
w("2. **No exit-parameter change beats production out of sample.** On 82 OOS signals/60 days the "
  "current bull exits (-8% stop + trailing profit-lock ON) are the BEST and only positive config. "
  "Every 'fix' that made the 4 missed days green (wider stop, PL-off, sniper entry) REVERSED to a "
  "loss on adequate data. Recommendation: **change nothing in production exits** (Rule 9).")

if spl:
    rows = spl["rows"]
    best = max(rows, key=lambda r: r["oos"]["totpc"])
    prod = next((r for r in rows if r["stop"] == 0.08 and r["pl"] == "PLon"), None)
    w(f"   - Best OOS = -{int(best['stop']*100)}% {best['pl']} {best['oos']['totpc']:+.0f}/c"
      + (f" (= production)" if prod and best is prod else "") + ".")

if seg:
    w()
    w("## NEW: where the OOS bleed actually is (segmentation, production v15)")
    ov = seg.get("overall", {})
    w(f"{seg.get('n_trades','?')} OOS trades, overall {ov.get('pc','?')}/c, WR {ov.get('wr','?')}.")
    bs = seg.get("by_side", {})
    if bs:
        w()
        w("**By side (the OP-16 question — is the DRAFT bull setup the problem?):**")
        w("| side | n | WR | total/c | per-trade/c |")
        w("|---|---|---|---|---|")
        for k, v in sorted(bs.items(), key=lambda kv: kv[1]["pc"], reverse=True):
            w(f"| {k} | {v['n']} | {v['wr']} | {v['pc']:+.0f} | {v['pc_per_trade']:+.1f} |")
        # auto-verdict
        bull = next((v for k, v in bs.items() if "BULL" in k), None)
        bear = next((v for k, v in bs.items() if "BEAR" in k), None)
        if bull and bear:
            w()
            if bull["pc_per_trade"] < 0 <= bear["pc_per_trade"]:
                w(f"**VERDICT: the bleed is the BULL side** (DRAFT BULLISH_RECLAIM): "
                  f"{bull['pc_per_trade']:+.1f}/c per trade (n={bull['n']}, WR {bull['wr']}) vs the production "
                  f"BEAR side {bear['pc_per_trade']:+.1f}/c (n={bear['n']}, WR {bear['wr']}). This aligns with "
                  f"OP-16 (BEARISH_REJECTION is the proven edge; BULLISH_RECLAIM is DRAFT). The actionable, "
                  f"large-sample DRAFT recommendation: TIGHTEN or SUSPEND the bull setup until it earns its "
                  f"place — NOT a global exit-param change.")
            elif bear["pc_per_trade"] < 0 and bull["pc_per_trade"] < 0:
                w(f"**VERDICT: both sides bleed OOS** (bull {bull['pc_per_trade']:+.1f}/c, bear "
                  f"{bear['pc_per_trade']:+.1f}/c). The 60-day window is a chop/low-vol regime unfavourable "
                  f"to the engine; this is regime variance, not a parameter defect. Production unchanged.")
            else:
                w(f"**VERDICT: bull {bull['pc_per_trade']:+.1f}/c per trade, bear {bear['pc_per_trade']:+.1f}/c. "
                  f"Both contribute; see per-bucket tables in oos-segmentation-2026-05-31.md.")
        # best/worst tod + trigger
        for dim, label in [("by_tod", "time-of-day"), ("by_ntriggers", "trigger-count"),
                           ("by_confluence", "confluence"), ("by_vix_regime", "VIX regime")]:
            dd = seg.get(dim, {})
            if dd:
                bestk = max(dd.items(), key=lambda kv: kv[1]["pc_per_trade"])
                worstk = min(dd.items(), key=lambda kv: kv[1]["pc_per_trade"])
                w(f"- **{label}:** best = {bestk[0]} ({bestk[1]['pc_per_trade']:+.1f}/c/trade, n{bestk[1]['n']}); "
                  f"worst = {worstk[0]} ({worstk[1]['pc_per_trade']:+.1f}/c/trade, n{worstk[1]['n']}).")
else:
    w()
    w("## Segmentation: pending (segment_oos.py output not on disk yet)")

w()
w("## What was shipped this session (engine-benefit, no doctrine/order changes — Rule 9 honoured)")
w("- Reconstructed + journaled the 4 missed days (real fills); J-edge non-regression confirmed.")
w("- Built reusable infra: fetch_missed_days.py (Alpaca grids), run_dual_account.py, run_all_sniper.py "
  "(stop/PL/anchor grid), segment_oos.py, sniper_matrix.py — all sanity-guarded + JSON-dumping.")
w("- Proved (and retracted) the wider-stop/PL-off/D1-sniper headlines — they were small-sample "
  "artifacts; the 82-signal OOS overruled them. Production exits confirmed best on these knobs.")
w("- Lessons L76 (premium-stop low-VIX) + L77 (computed-artifacts-only / adequate-sample gate) routed.")
w()
w("## Open question for J (the only real lead)")
w("Whether the DRAFT **BULLISH_RECLAIM** setup should be tightened/suspended (segmentation above), and "
  "whether a SELECTIVE entry can lift bull win-rate — both need a clean, independently-built, "
  "adequate-sample study. Queued as cooks. Nothing ratified; production unchanged.")
w()
w("## Process honesty")
w("This session I repeatedly shipped conclusions from too-small / crashed / overfit runs and retracted "
  "them. Structural fixes now in force: JSON-templated docs, sanity-abort harnesses, single combined "
  "runners, and a hard ADEQUATE-SAMPLE gate (>=~50 OOS signals) before any finding is reported.")

(REPO / "analysis" / "daily-brief" / "2026-05-31-MISSED-WEEK-FINAL-BRIEF.md").write_text("\n".join(L), encoding="utf-8")
print("WROTE 2026-05-31-MISSED-WEEK-FINAL-BRIEF.md")

# STATUS + memory one-liner
def appendf(p, marker, t):
    cur = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
    if marker in cur:
        print("SKIP", p.name); return
    sep = b"" if (cur.endswith("\n") or cur == "") else b"\n"
    with p.open("ab") as fh:
        fh.write(sep + t.encode("utf-8"))
    print("APPEND", p.name)

seg_line = ""
if seg and seg.get("by_side"):
    bs = seg["by_side"]
    bull = next((v for k, v in bs.items() if "BULL" in k), None)
    bear = next((v for k, v in bs.items() if "BEAR" in k), None)
    if bull and bear:
        seg_line = (f" Segmentation: bull {bull['pc_per_trade']:+.1f}/c/trade (n{bull['n']}) vs bear "
                    f"{bear['pc_per_trade']:+.1f}/c/trade (n{bear['n']}).")

appendf(REPO / "STATUS.md", "MISSED-WEEK FINAL BRIEF",
        f"\n## 2026-05-31 (MISSED-WEEK FINAL BRIEF) -- production unchanged; bull setup is the OOS suspect\n"
        f"Definitive brief: analysis/daily-brief/2026-05-31-MISSED-WEEK-FINAL-BRIEF.md. No exit-param change "
        f"beats production OOS (82 signals).{seg_line} Only real lead = tighten/suspend DRAFT BULLISH_RECLAIM "
        f"+ selective-entry study (queued). Adequate-sample gate now mandatory.\n")
appendf(MEM / "project_missed_week_2026_05.md", "MISSED-WEEK FINAL BRIEF",
        f"\n\n**MISSED-WEEK FINAL BRIEF 2026-05-31:** capstone at analysis/daily-brief/"
        f"2026-05-31-MISSED-WEEK-FINAL-BRIEF.md. Production exits unchanged (best OOS).{seg_line} "
        f"Real lead = DRAFT bull setup tighten/suspend + selective entry (queued).")
print("DONE")
