# Skill: chart-data-verify

Cross-check the last N closed SPY 5m bars across data sources: master CSV (in `backtest/data/spy_5m_*.csv`) vs live yfinance fetch. Compare close prices within ±$0.05 tolerance. AUDIT, DIAGNOSE, optionally HEAL via in-memory yfinance top-up. Reports per-bar divergence.

> Per CLAUDE.md OP-25 lessons absorbed (T76 + 2026-05-13 watcher_live silent no-op + T48 BS-sim mispricing). When the CSV is stale or the live feed diverges, EVERY downstream system (heartbeat decisions, watcher signals, simulator, backtest) makes wrong calls. This skill catches stale-CSV / wrong-bar / source-divergence problems before they propagate.

---

## When to invoke

- **Daily, automatically** — overnight wake fires after 16:00 ET to verify EOD appender ran cleanly
- **Pre-market 08:30 ET** before premarket fires (catches CSV gap from yesterday)
- **When `watcher-live-diag.jsonl` shows V=0 sentinel bars during market hours** (yfinance returning in-progress)
- **When EOD-summary's drift_check verdict surprises** (could be data drift, not strategy drift)
- **When investigating a "wrong fill price" — was the bar wrong, or the engine wrong?**

---

## Steps

1. **Run the verification (defaults to most recent weekday):**

```powershell
cd C:\Users\jackw\Desktop\42\backtest
python -m autoresearch.chart_data_verify
```

2. **Verify a specific date with N trailing bars:**

```powershell
python -m autoresearch.chart_data_verify --date 2026-05-12 --bars 10
```

3. **Auto-heal (re-fetches yfinance — in-memory only, does NOT touch CSV):**

```powershell
python -m autoresearch.chart_data_verify --heal
```

4. **Read structured JSON output:**

```powershell
Get-Content "C:\Users\jackw\Desktop\42\automation\state\chart-data-verify-2026-05-12.json"
```

---

## Verdict criteria

| Verdict | Trigger |
|---------|---------|
| **GREEN** | All bars match within ±$0.05 close-price tolerance |
| **YELLOW** | (a) Max divergence $0.05-$0.10 (consolidated-vs-single-venue rounding); OR (b) CSV stale / EOD-appender hasn't run yet but yfinance has bars; OR (c) yfinance fetch failed but CSV present |
| **RED** | Max divergence > $0.10 (cache-stale or wrong-bar match); OR neither source has bars |

---

## Healing actions (auto-applied with `-Heal`)

| Condition | Action | Idempotent? |
|-----------|--------|-------------|
| RED + yfinance available | Re-fetch yfinance bars in-memory; report row count | YES |
| RED + yfinance dead | NO auto-heal (network issue or rate-limit); logs `yfinance-refetch-failed` | n/a |

**Never modifies:**
- The on-disk CSV at `backtest/data/spy_5m_*.csv` — that's the EOD appender's exclusive responsibility (rule 9 / no-mid-session-changes)
- TradingView chart state
- Any heartbeat/watcher state files

---

## Output files

| File | What |
|------|------|
| `automation/state/chart-data-verify-{date}.json` | Verdict + per-bar comparison + max divergence + heal action |
| stdout | Human-readable verdict + first 5 row comparisons |

JSON schema:
```json
{
  "skill": "chart-data-verify",
  "target_date": "YYYY-MM-DD",
  "verdict": "GREEN|YELLOW|RED",
  "reason": "human description",
  "csv_path": "C:/Users/jackw/Desktop/42/backtest/data/spy_5m_2026-05-08_2026-05-14.csv",
  "max_divergence_dollars": 0.0034,
  "rows_compared": 5,
  "heal_action": "no-op",
  "rows": [
    {"ts": "2026-05-12 15:50:00", "csv_close": 748.33, "yf_close": 748.32, "divergence": 0.01}
  ]
}
```

---

## TradingView MCP variant (LLM-assisted)

When invoked from a Claude session (rather than a wake-fire batch), the LLM CAN call TV MCP directly to add a 3-way cross-check (CSV vs yfinance vs TradingView). Pattern:

```
1. Run python -m autoresearch.chart_data_verify --date YYYY-MM-DD
2. If verdict YELLOW or RED, call mcp__tradingview__data_get_ohlcv with symbol=SPY interval=5 count=10
3. Compare TV close prices to the JSON output's `rows[].csv_close` and `rows[].yf_close`
4. If TV matches yfinance but not CSV → CSV stale (heal: re-run EOD appender for that date)
5. If TV matches CSV but not yfinance → yfinance API issue
6. If TV diverges from BOTH → TV CDP feed broken, run heartbeat-mcp-self-test -Heal
```

The standalone Python tool can't call MCP (no SDK in-process), but the LLM-assisted variant gives ground-truth from the most authoritative venue (IBKR via TV).

---

## Caveats

1. **yfinance returns consolidated bars; TV uses IBKR (single-venue)** — 1-3 cent divergence is normal and expected. Tolerance is set accordingly.
2. **CSV master file is updated post-close by EOD appender** — during market hours, today's bars come from yfinance intraday top-up (per OP-25 lesson 2026-05-13 08:42 ET). Stale CSV during market hours is NORMAL — only `RED` if both CSV AND yfinance fail.
3. **The auto-heal does NOT modify the on-disk CSV.** Per rule 9, EOD appender owns that file — we just verify and re-fetch in-memory for downstream re-eval.
4. **If yfinance returns in-progress bars (V=0)**, the comparison may show very small divergence (the snapshot was a few seconds early). T76 fix in watcher_live tolerates this.
5. Exit codes: `0` for GREEN/YELLOW, `1` for RED.

---

## Cross-references

- **Tool source:** `backtest/autoresearch/chart_data_verify.py`
- **Companion skills:** `heartbeat-tick-audit` (validates heartbeat reads correct closed bar), `watcher-state-inspector` (uses same CSV pipeline)
- **Production CSV updater:** `backtest/autoresearch/append_today.py` (EOD appender)
- **Production live-fetch:** `backtest/autoresearch/watcher_live.py` (yfinance intraday top-up)
- **CLAUDE.md OP-25 lessons:** "watcher_live silently no-ops pre-market because CSV ends at yesterday" (2026-05-13 08:42 ET); "BS sim systematically over-estimates entry premium" (2026-05-13 05:20 ET — different but related data-trust issue)
