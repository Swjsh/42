#!/usr/bin/env python3
"""
context_audit.py -- Project Gamma context-leanness engine.

Measures, scores, and integrity-checks always-loaded context files (CLAUDE.md)
so the prefix that is cache-read on EVERY Claude Code turn stays lean.

This file is the single source of truth for the leanness BENCHMARKS and GUARD
SCORES. The PowerShell guard (check-context-budget.ps1) and the context-leanness
skill both call this; do not hardcode budgets elsewhere.

Modes:
  --report   per-section token table + movable-block candidates (human/skill view)
  --check    score the file, write state json, print one status line (fail-open)
  --verify   run integrity invariants; exit 1 if any fail (used AFTER an edit)

Token method: tiktoken cl100k_base if importable, else bytes/3.6 estimate
(calibrated on CLAUDE.md: ~3.5-3.6 bytes/token). Method is recorded in state.

Exit codes:
  --check  : 0 always unless --strict (then 1 on RED).  Guards must fail OPEN
             (CLAUDE.md OP-25: no automated process may break J's session).
  --verify : 0 all-pass, 1 any-fail.
"""
from __future__ import annotations
import argparse, datetime, json, os, re, sys

# ---- BENCHMARKS / GUARD SCORES (single source of truth) --------------------
BUDGET_TOKENS = 8000          # hard ceiling for CLAUDE.md
WARN_PCT      = 95            # >= this % of budget -> YELLOW (NEAR)
BYTES_PER_TOKEN = 3.6         # fallback estimate divisor
MOVABLE_MIN_TOKENS = 500      # OP/section blocks above this are relocation candidates

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# repo root = two levels up from setup/scripts/. When run from /tmp for testing,
# allow --file/--repo overrides.

def _enc():
    try:
        import tiktoken
        e = tiktoken.get_encoding("cl100k_base")
        return (lambda s: len(e.encode(s))), "tiktoken-cl100k"
    except Exception:
        return (lambda s: int((len(s.encode("utf-8")) + BYTES_PER_TOKEN - 1) // BYTES_PER_TOKEN)), "bytes/3.6-estimate"

TOK, METHOD = _enc()

def et_now():
    # ET timestamp without external deps (UTC-4/-5 not DST-perfect; fine for a log stamp)
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def read(path): return open(path, encoding="utf-8").read()

def sections(txt):
    parts = re.split(r'(?m)^(?=## )', txt)
    out = []
    for p in parts:
        if not p.strip(): continue
        m = re.match(r'## (.+)', p)
        out.append(((m.group(1).strip() if m else "(preamble)")[:52], TOK(p)))
    return out

def movable_candidates(txt):
    """Reference-heavy blocks the skill may relocate to docs/ (never rule semantics)."""
    cands = []
    # <details> archives
    for m in re.finditer(r'(?s)<details>.*?</details>', txt):
        t = TOK(m.group(0))
        if t >= 200:
            head = re.search(r'<summary>(.*?)</summary>', m.group(0))
            cands.append((t, "details: " + (re.sub('<[^>]+>','',head.group(1))[:46] if head else "block")))
    # numbered Operating-Principle blocks over threshold
    op = re.search(r'(?ms)^## Operating principles.*?(?=^## )', txt)
    if op:
        for b in re.split(r'(?m)^(?=\d+\.\s+\*\*)', op.group(0)):
            mm = re.match(r'(\d+)\.\s+\*\*(.+?)\*\*', b)
            if mm and TOK(b) >= MOVABLE_MIN_TOKENS:
                cands.append((TOK(b), f"OP-{mm.group(1)}: {mm.group(2)[:42]}"))
    return sorted(cands, reverse=True)

# ---- INTEGRITY INVARIANTS (the safety net for autonomous edits) ------------
def integrity(txt, repo):
    checks = []
    def c(name, ok): checks.append((name, bool(ok)))
    c("All 10 rules present", all(re.search(rf'(?m)^{i}\. \*\*', txt) for i in range(1, 11)))
    c("Both account numbers present", "PA3S2PYAS2WQ" in txt and "PA33W2KUAT40" in txt)
    c("Kill-switch text present", "start-of-day equity" in txt or "start-of-day" in txt)
    c("Rule-version pinned", bool(re.search(r'Current rule version:\s*v\d+', txt)))
    c("Refusals section present", bool(re.search(r'(?m)^## What I will refuse', txt)))
    c("Work-cadence table present", "After-4pm work block" in txt)
    c("Lessons index table present", "Lessons index" in txt and "| C1 |" in txt)
    # pointer integrity: every relative md/json/py/ps1 link target must exist
    missing = []
    for m in re.finditer(r'\]\((?!https?://|#)([^)#]+)(?:#[^)]*)?\)', txt):
        tgt = m.group(1).strip()
        if not tgt or tgt.startswith("mailto:"): continue
        if re.search(r'\.(md|json|jsonl|py|ps1|csv|html|txt)$', tgt):
            if not os.path.exists(os.path.join(repo, tgt)):
                missing.append(tgt)
    c(f"All doc pointers resolve ({len(missing)} missing)", not missing)
    return checks, missing

def score(tokens, budget=BUDGET_TOKENS):
    # Status keys off TOKEN thresholds, not the rounded percent (avoids a 94.7%->95% edge).
    pct = round(tokens / budget * 100)
    warn_tokens = budget * WARN_PCT / 100.0
    status = "RED" if tokens > budget else ("YELLOW" if tokens >= warn_tokens else "GREEN")
    return pct, status

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["report", "check", "verify"])
    ap.add_argument("--file", default=None)
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--budget", type=int, default=BUDGET_TOKENS)
    ap.add_argument("--strict", action="store_true", help="--check exits 1 on RED")
    ap.add_argument("--state", default=None, help="state json path (default automation/state/context-budget.json)")
    a = ap.parse_args()
    repo = os.path.abspath(a.repo)
    path = a.file or os.path.join(repo, "CLAUDE.md")
    if not os.path.exists(path):
        print(json.dumps({"status": "MISSING", "file": path})); sys.exit(2)
    txt = read(path)
    tokens = TOK(txt); pct, status = score(tokens, a.budget)
    name = os.path.basename(path)

    if a.mode == "report":
        print(f"# context_audit report -- {name}")
        print(f"method={METHOD}  tokens={tokens}  budget={a.budget}  pct={pct}%  status={status}\n")
        print("## Sections by tokens")
        for title, t in sorted(sections(txt), key=lambda x: -x[1]):
            print(f"{t:6d}  {title}")
        print("\n## Movable candidates (relocate to docs/, leave a pointer -- NEVER rule semantics)")
        cands = movable_candidates(txt)
        if not cands: print("  (none above threshold -- file is lean)")
        for t, label in cands: print(f"{t:6d}  {label}")
        ck, missing = integrity(txt, repo)
        print("\n## Integrity")
        for nm, ok in ck: print(("  PASS " if ok else "  FAIL ") + nm)
        if missing: print("  missing pointers:", ", ".join(missing))
        return

    if a.mode == "verify":
        ck, missing = integrity(txt, repo)
        budget_ok = tokens <= a.budget
        ck.append((f"Under budget ({tokens}<= {a.budget})", budget_ok))
        allok = all(ok for _, ok in ck)
        for nm, ok in ck: print(("PASS " if ok else "FAIL ") + nm)
        if missing: print("missing pointers:", ", ".join(missing))
        sys.exit(0 if allok else 1)

    # check
    ck, missing = integrity(txt, repo)
    integ_ok = all(ok for _, ok in ck)
    state = {
        "ts": et_now(), "file": name, "method": METHOD,
        "bytes": len(txt.encode("utf-8")), "tokens": tokens,
        "budget": a.budget, "pct": pct, "status": status,
        "warn_pct": WARN_PCT, "integrity_ok": integ_ok,
        "missing_pointers": missing,
        "top_sections": [{"title": t9, "tokens": tk} for t9, tk in sorted(sections(txt), key=lambda x: -x[1])[:6]],
    }
    statep = a.state or os.path.join(repo, "automation", "state", "context-budget.json")
    try:
        os.makedirs(os.path.dirname(statep), exist_ok=True)
        json.dump(state, open(statep, "w", encoding="utf-8"), indent=2)
    except Exception as e:
        print("WARN could not write state:", e, file=sys.stderr)
    print(f"{status}  {name}: {tokens} tok / {a.budget} budget ({pct}%)  integrity={'ok' if integ_ok else 'FAIL'}  [{METHOD}]")
    sys.exit(1 if (a.strict and status == "RED") else 0)

if __name__ == "__main__":
    main()
