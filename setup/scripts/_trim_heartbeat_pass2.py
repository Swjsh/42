"""Pass 2: trim remaining reference prose from heartbeat.md.

Same assertion-guarded marker-slice contract as pass 1. The Gates E-I region is
REWRITTEN compactly: every params key, value, condition, side guard, SKIP token,
and blocker name is preserved verbatim; only the IS/OOS evidence + orchestrator
line refs (now in heartbeat-provenance.md) are dropped. All other regions remove
pure citation/rationale prose. Aborts with NO write if any marker is off.
"""
import re
import sys

PATH = "automation/prompts/heartbeat.md"
src = open(PATH, encoding="utf-8").read()
orig_len = len(src)

GATES_EI = """**PORTED BACKTEST GATES (Gates E-I).** Five config-gated BLOCK gates (each no-op when its `params.json` key is `false`/`0`/`null`). Evaluate AFTER scoring + Gates A-D, BEFORE the pre-execution gate sequence. **Tier mapping:** `quality_tier=="LEVEL"` = a BEAR (put) entry whose firing trigger is `level_rejection`/`level_reject` vs a named level (`has_level`); `quality_tier=="ELITE"` = trigger set includes `confluence` OR `sequence_*`. Evidence + scorecards: `markdown/0dte/heartbeat-provenance.md`.

**Gate E - vix_bear_hard_cap:** Read `params.json#vix_bear_hard_cap` (23.0). If non-null AND side==BEAR (put / `winning_side=="P"`) AND `vix_now >= vix_bear_hard_cap` -> emit `SKIP_VIX_BEAR_HIGH`, log `decisions.jsonl` (blocker `VIX_BEAR_HARD_CAP`), do NOT enter. Revert: `vix_bear_hard_cap: null`.

**Gate F - block_level_rejection:** Read `params.json#block_level_rejection` (true). If true AND side==BEAR (put) AND entry is a LEVEL-tier `level_rejection` (`quality_tier=="LEVEL" and has_level and winning_side=="P"` -- only/primary qualifying trigger is `level_reject` vs a named resistance/transition/broken_to_resistance level, NOT confluence/sequence/ribbon_flip) -> emit `SKIP_LEVEL_REJECTION_GATE`, log (blocker `LEVEL_REJECTION_GATE`), do NOT enter. BULL `level_reclaim` NOT blocked. Revert: `block_level_rejection: false`.

**Gate G - entry_bar_body_pct_min:** Read `params.json#entry_bar_body_pct_min` (0.20). If `> 0.0` AND side==BEAR (put) AND entry-bar `body_pct < entry_bar_body_pct_min` where `body_pct = abs(close-open)/(high-low)` of the last closed bar (doji/wick-dominant = no conviction) -> emit `SKIP_DOJI_ENTRY_BAR`, log (blocker `ENTRY_BAR_BODY_PCT_GATE`), do NOT enter. BEAR-side only. Revert: `entry_bar_body_pct_min: 0.0`.

**Gate H - block_bull_1100_1200:** Read `params.json#block_bull_1100_1200` (true). If true AND side==BULL (call / `winning_side=="C"`) AND `11:00 ET <= now_et < 12:00 ET` (signal bar) -> emit `SKIP_BULL_1100_1200`, log (blocker `BLOCK_BULL_1100_1200`), do NOT enter. Revert: `block_bull_1100_1200: false`.

**Gate I - block_elite_bull:** Read `params.json#block_elite_bull` (true), `block_elite_bull_vix_low` (0.0), `block_elite_bull_vix_high` (25.0). If `block_elite_bull` true AND side==BULL (call) AND entry is ELITE with `level_reclaim` present (`quality_tier=="ELITE" and "level_reclaim" in winning_triggers`) AND `block_elite_bull_vix_low <= vix_now < block_elite_bull_vix_high` -> emit `SKIP_ELITE_BULL_LEVEL_RECLAIM`, log (blocker `BLOCK_ELITE_BULL`), do NOT enter. Revert: `block_elite_bull: false`.

"""

REGIONS = [
    # first-entry-after-stop validation-status blockquote -> drop
    ("first_entry_status",
     "> **Backtest validation status (2026-05-09):**",
     "Before scoring, read `loop-state.first_entry_lock[]`",
     ""),
    # exit-hierarchy: profit-lock chandelier provenance parenthetical
    ("chandelier_cite",
     " (Source: T50 trailing-PL test 2026-05-13 established the trailing chandelier;",
     "\n- **PRIMARY — time stop 15:40 ET hard**",
     " (provenance + scorecards: `markdown/0dte/heartbeat-provenance.md`; params: `v15_profit_lock_trail_pct`=0.125.)"),
    # exit-hierarchy: BACKSTOP -50% rationale/evidence/revert
    ("backstop_cite",
     " Rationale: fixed-% premium stops whipsaw 0DTE options out of eventual winners",
     "\n- **TP1 (BEAR-side)",
     " The premium cap exists only for blinded-heartbeat cases (rate limit, crash). Real-fills evidence + revert (to premium-primary): `markdown/0dte/heartbeat-provenance.md`."),
    # quality-tier sizing rationale paragraph
    ("sizing_rationale",
     "ELITE is 58% WR / $159 avg / +22% over baseline; BASE is 47% WR / $48 avg.",
     "ONE action max per tick.",
     ""),
    # Gates E-I full rewrite (compact, every executable detail preserved)
    ("gates_ei",
     "**PORTED BACKTEST GATES (Gates E–I) — ported from `backtest/lib/orchestrator.py` to live 2026-06-18.**",
     "Apply Gates E–I in order; the FIRST one that fires SKIPs the entry",
     GATES_EI),
    # MACRO BIAS worked-example illustration -> drop
    ("macro_example",
     "This is what the 2026-05-07 12:30 BULL trade looks like under v2:",
     "Always write `macro_pre_event_bias` to loop-state on every loop-state write",
     ""),
]


def slice_replace(text, name, start_m, end_m, repl):
    sc = text.count(start_m)
    if sc != 1:
        sys.exit(f"ABORT [{name}]: start marker count={sc} (expected 1): {start_m!r}")
    si = text.index(start_m)
    if text.count(end_m) < 1 or end_m not in text[si + len(start_m):]:
        sys.exit(f"ABORT [{name}]: end marker not found after start: {end_m!r}")
    ei = text.index(end_m, si + len(start_m))
    return text[:si] + repl + text[ei:]


for name, s, e, r in REGIONS:
    before = len(src)
    src = slice_replace(src, name, s, e, r)
    print(f"  {name:20s} -{before - len(src):>6d} bytes")

with open(PATH, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(src)
print(f"\nheartbeat.md: {orig_len} -> {len(src)} bytes (-{orig_len - len(src)})")
