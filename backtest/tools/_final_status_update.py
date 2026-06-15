"""Final STATUS + memory update with anchor gate confirmation. Binary-safe, idempotent."""
from pathlib import Path

REPO = Path(r"C:\Users\jackw\Desktop\42")
MEM = Path(r"C:\Users\jackw\.claude\projects\C--Users-jackw-Desktop-42\memory")

def appendf(p, marker, t):
    cur = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
    if marker in cur:
        print("SKIP", p.name); return
    sep = b"" if (cur.endswith("\n") or cur == "") else b"\n"
    with p.open("ab") as fh:
        fh.write(sep + t.encode("utf-8"))
    print("APPEND", p.name)

appendf(REPO / "STATUS.md", "ANCHOR GATE PASS confirmed",
"""
## 2026-05-31 (ANCHOR GATE PASS confirmed) -- selectivity gate complete evidence package

Anchor gate check (2026-04-27..05-07, filter-8-off): ungated n=10 pc=-15/c -> gated n=7 pc=+4/c.
5/04 721P KEPT at +53.6/c. 4/29 12:15 trendline loser (-25.2/c) CORRECTLY suppressed.
Full evidence package: analysis/recommendations/selectivity-gate-impl-proposal.md (DRAFT for J).
Option A vs B grinder implementation queued. Kitchen daemon alive; 35+ cooks pending.
""")

appendf(MEM / "project_missed_week_2026_05.md", "ANCHOR GATE PASS",
"\n\n**ANCHOR GATE PASS 2026-05-31:** selectivity gate (G_NO_midday_trendline) anchor check: "
"gated pc=+4/c vs ungated -15/c, 5/04 kept +53.6, 4/29 loser suppressed. Full proposal at "
"analysis/recommendations/selectivity-gate-impl-proposal.md. Option A vs B grinder impl queued.")
print("DONE")
