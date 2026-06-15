"""Binary-safe CORRECTION append to STATUS.md + memory: the earlier '0 of 512 green'
claim was false (written from a crashed sweep). Real result: 4 all-green configs.
Idempotent. cp1252-safe read + binary append."""
from pathlib import Path

REPO = Path(r"C:\Users\jackw\Desktop\42")
MEM = Path(r"C:\Users\jackw\.claude\projects\C--Users-jackw-Desktop-42\memory")

def appendf(p: Path, marker: str, text: str):
    cur = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
    if marker in cur:
        print(f"SKIP (present) {p.name}"); return
    sep = b"" if (cur.endswith("\n") or cur == "") else b"\n"
    with p.open("ab") as fh:
        fh.write(sep + text.encode("utf-8"))
    print(f"APPENDED +{len(text)}b {p.name}")

STATUS_CORR = """
## 2026-05-31 (CORRECTION) -- the week IS fixable; earlier '0 green' claim was wrong

SELF-CORRECTION (L77, 4th occurrence): an earlier STATUS entry + FINDINGS draft claimed the
512-config sweep found '0 all-green, 05-28 red under every config'. That was written from a
sweep run that had CRASHED (SyntaxError) before producing output. After fixing the script the
256-combo sweep actually COMPLETED. CORRECTED result (real fills, analysis/missed-green-sweep.md
+ green-config-validation.md):
- **4 configs make all 4 missed days GREEN.** Best: ATM strike, -50% premium stop, trailing-PL
  OFF, mtb1 -> +521/+676/+393/+788 = +129.4/contract. 05-28 goes +393.
- TWO culprits: (a) -8% stop too tight, (b) trailing profit-lock harmful in chop (armed then
  stopped out) -- every all-green config has trailing-PL OFF.
- Anchor gate (OP-16): GREEN still CAPTURES 5/04 721P (+31.2/c) and 4/29 (+41.8), net +5.7/c on
  the anchor window (vs PROD -14.7/c) -- BUT worst put loss deepens to -58/c vs -25/c. Real
  risk tradeoff for J.
- Confirms J's entry thesis: a -50% stop is brute-force proof the ENTRY is too early (needs half
  the premium as room to survive the retest). Sniper entry = same wins, less risk. Cooking now.
- Authoritative: analysis/missed-week-FINDINGS-2026-05-31.md (corrected).
"""
appendf(REPO / "STATUS.md", "the week IS fixable", STATUS_CORR)

MEM_CORR = ("\n\n**CORRECTION 2026-05-31:** the 'entry-is-the-problem, 0 configs green' claim was "
            "WRONG (written from a crashed sweep -- L77 4th occurrence). Real result: the 256-combo "
            "sweep found 4 ALL-GREEN configs; best = ATM + -50% stop + trailing-PL OFF -> "
            "+521/+676/+393/+788 (+129/c), 05-28 +393. TWO fixes: stop too tight AND trailing "
            "profit-lock harmful in chop (turn off). Still captures 5/04 anchor (+31.2/c) but "
            "deepens worst loss to -58/c. Confirms entry thesis: -50% stop = brute-force proof entry "
            "is early; sniper entry gets same wins with less risk. See missed-week-FINDINGS-2026-05-31.md.")
appendf(MEM / "project_missed_week_2026_05.md", "CORRECTION 2026-05-31", MEM_CORR)
print("DONE")
