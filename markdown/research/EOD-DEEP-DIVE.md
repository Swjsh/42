# EOD Deep-Dive — User Manual

> Canonical end-of-day review skill. ONE source of truth per trading day, MANY projections.
> First shipped Phase 1 on 2026-05-14 (the day v15 went live and delivered +$1,500 on 745C).

---

## What problem does this solve

Before EOD Deep-Dive:
- Same trade lived in 4+ files (journal MD + trades.csv + trade-card.html + decisions.jsonl)
- Lessons got written 3-4x times across LESSONS-LEARNED + journal + CHANGELOG + FUTURE-IMPROVEMENTS
- No machine-readable common source → backtest pipeline couldn't ingest day's data automatically
- Daily review was free-form, not comparable day-to-day or week-to-week
- The 12 dimensions of a good trading day were never made explicit

After EOD Deep-Dive:
- ONE canonical JSON per day at `analysis/eod-deep-YYYY-MM-DD.json`
- Markdown, HTML, journal sections, sessions ledger are all PROJECTIONS of that JSON
- 12 dimensions explicitly scored (0-100 each + weighted aggregate)
- Counterfactuals for every trade (v14, v15, stepped-PL, perfect-hindsight)
- `research_handoffs` block feeds back into backtest / autoresearch pipeline

---

## The 12 dimensions

| # | Category | Weight | What it measures |
|---|---|---|---|
| 1 | execution | 15% | Did entries/exits fire as the plan said? |
| 2 | detection | 10% | Did engine SEE every setup the playbook predicted? |
| 3 | edge | 15% | Did we capture the available P&L vs perfect hindsight? |
| 4 | doctrine | 15% | Did we follow v15 rules? |
| 5 | risk | 10% | Did we stay safe (sizing, drawdown, daily budget)? |
| 6 | process | 5% | Did we journal/document/learn properly? |
| 7 | macro | 5% | Did we read the regime correctly? |
| 8 | technical | 5% | Did we read the chart correctly? |
| 9 | engine_health | 5% | Did the autonomous infrastructure work? |
| 10 | watcher_fleet | 5% | Did the observation layer work? |
| 11 | lessons | 5% | What did we learn that we didn't know yesterday? |
| 12 | tomorrow | 5% | What carries forward? |

Each category gets `{score: 0-100, evidence: {...}, narrative: "...", actions: [...]}`.

---

## How to invoke

### From an interactive Claude session (with MCP available)

```bash
# Step 1: dump MCP data to a file (Alpaca orders + account, TV chart state)
# Step 2: run the helper
python -m autoresearch.eod_deep.run_with_mcp_data \
    --date 2026-05-14 \
    --alpaca-data-file analysis/_mcp_dump_2026-05-14.json
```

### From the scheduled task (post-EodSummary at 16:05 ET)

```powershell
# Wired into Gamma_EodDeepDive task (Phase 1.10)
& "C:\Users\jackw\Desktop\42\setup\scripts\run-eod-deep-dive.ps1"
```

The scheduled-task path runs pure Python with no MCP — uses snapshot files written by EodSummary.

### Manual one-shot for any date

```bash
python -m autoresearch.eod_deep.main --date 2026-05-14 --rerun
```

---

## Outputs

| File | Format | Purpose |
|---|---|---|
| `analysis/eod-deep-YYYY-MM-DD.json` | JSON | Canonical source of truth (machine-readable) |
| `analysis/eod-deep-YYYY-MM-DD.md` | Markdown | Narrative for J's morning coffee read |
| `analysis/trade-card-YYYY-MM-DD.html` | HTML | Visual card (open in browser) |
| `analysis/sessions.jsonl` | JSONL (append-only) | Multi-day ledger for weekly review / backtest |

---

## Schema (eod-deep-v1)

Top-level `EodDeepDive`:

```python
{
  "schema_version": "eod-deep-v1",
  "date": "2026-05-14",
  "rule_version_active": "v15",
  "account_equity_start": 101272.15,
  "account_equity_end":   102771.75,
  "day_pnl_dollars":      1499.60,
  "day_pnl_pct":          1.48,
  "day_trade_count":      1,
  "trades": [TradeRecord, ...],
  "categories": {
    "execution":     CategoryScore,
    "detection":     CategoryScore,
    ... (12 total)
  },
  "process_score":     73.5,            # weighted aggregate
  "edge_capture_pct":  56.6,            # actual / perfect-hindsight
  "research_handoffs": {
    "doctrine_candidates_for_grinder": [...],
    "fixes_shipped_today":            [...],
    "ingest_warnings":                [...]
  },
  "tomorrow_setup": {...}
}
```

`TradeRecord` includes `counterfactuals: [{name, pnl_dollars, method, delta_vs_actual}]`.

See `backtest/autoresearch/eod_deep/schema.py` for full dataclass definitions.

---

## Phase 1 (what's live now) vs Phase 2 (weekend roadmap)

**Phase 1 — SHIPPED 2026-05-14 evening:**
- Schema + ingest + main orchestrator
- 1 fully-implemented module: `edge` (counterfactuals real for v14/v15/stepped-PL/perfect-hindsight)
- 11 stub modules returning shallow / placeholder scores
- HTML + Markdown projections
- Sessions JSONL append
- Verified live on today's 745C trade: P&L $1,499.60 captured correctly

**Phase 2 — Weekend (~5 days dev):**
- Real implementations for the 11 stub modules
- OPRA-cache-backed perfect-hindsight (find true max bid, not heuristic)
- J-anchor compare (most similar historical J trade by date / setup / regime)
- Drift check (today's P&L vs current v15 backtest distribution percentile)
- Auto-update of `journal/YYYY-MM-DD.md` "EOD Reflection" + "Daily Review" sections
- Trade card includes embedded chart screenshot from TV at 16:00 ET

**Phase 3 — Following weekend:**
- Auto-append L## to LESSONS-LEARNED.md when new anti-pattern detected
- Auto-queue doctrine candidates to autoresearch pipeline
- Weekly review = aggregation of 5 daily JSON files
- Sessions JSONL becomes input for autoresearch backtest pipeline

---

## File structure

```
backtest/autoresearch/eod_deep/
├── __init__.py
├── schema.py              # dataclasses + serialization
├── ingest.py              # read all sources
├── main.py                # orchestrator + CLI entry
├── run_with_mcp_data.py   # injected-MCP helper for interactive Claude
├── modules/
│   ├── __init__.py
│   ├── edge.py            # Phase 1 REAL (counterfactuals)
│   └── _stubs.py          # Phase 1 stubs for 11 other categories
└── projections/
    ├── __init__.py
    ├── markdown.py        # narrative
    └── html.py            # visual card
```

---

## Lessons absorbed during Phase 1 development

1. **`LoopState` fields can be `None`** even when keys exist (developing_setup = null mid-session). All accessors use `or {}` pattern.
2. **`research_handoffs.fixes_shipped_today`** is a smart use of CHANGELOG-style anti-pattern detection — scans journal_md for known marker strings.
3. **Edge capture < 100% is OK** when scaling out — perfect-hindsight assumes hold-everything-to-peak which is unrealistic. Phase 2 will add a "realistic-hindsight" counterfactual that simulates a smart-trader scale-out plan.

---

## How to extend

To add a new dimension (e.g., "psychology" — was J in good mental state?):

1. Add `"psychology"` to `CATEGORY_KEYS` in `schema.py`
2. Add weight to `CATEGORY_WEIGHTS`
3. Create `modules/psychology.py` with `analyze_psychology(data, trades) -> CategoryScore`
4. Wire into `main.run()` at the analyze block

Done. JSON schema auto-expands. Projections auto-render.

To upgrade a stub to real implementation:

1. Find the stub function in `modules/_stubs.py`
2. Create dedicated module (`modules/<name>.py`)
3. Import + replace in `main.run()` analyze block
4. Keep the stub as fallback for tests

---

## Cost

Pure Python — $0 per run. No LLM in the loop. The whole thing runs in ~1 second.

EodSummary task at 16:00 ET (which uses Claude) generates the journal markdown; EodDeepDive at 16:05 ET (Phase 1.10) consumes that + state files + injected MCP snapshots and produces the canonical JSON. Total cost per day: ~$0.50 (the EodSummary tick) + $0 (this skill).
