# Skill: j-winner-audit

Compute the OP-16 edge_capture scorecard for any candidate params — the gate metric that determines whether a strategy candidate is PROMISING or REJECTED. Classifies each of J's 7 source-of-truth days (3 winners + 4 losers) as CAUGHT / MISSED / AVOIDED / OVERTRADED and reports how close the engine came to J's actual results.

> **Replaces:** `backtest/autoresearch/audit_j_winners.py` (one-shot, hard-coded to current params). This skill is parameterized and machine-readable.

---

## When to invoke

- **After any candidate params change** — verify edge_capture hasn't regressed below OP-16 floor ($771)
- **Before Weekend ratification brief** — every Chef candidate should have a fresh j-winner scorecard
- **After a new J-anchor trade is added** to the OP-16 source-of-truth list
- **From the Chef persona** when ranking strategy candidates (`/chef` invokes it as a standard scoring step)
- **Ad-hoc:** when J asks "did the engine catch [date]?" or "what was our edge_capture this week?"

---

## Steps

### Quick run (default: current production params)

```powershell
cd C:\Users\jackw\Desktop\42\backtest
python -m autoresearch.j_winner_audit
```

### Run against a specific candidate params file

```powershell
python -m autoresearch.j_winner_audit --params automation/state/params_safe.json --slug v15.2-safe
python -m autoresearch.j_winner_audit --params strategy/candidates/f27-params-draft.json --slug F27-draft
```

### Compare last 5 candidates

The tool automatically loads up to 5 most-recent scorecards from `analysis/j-edge/` and prints a comparison table at the end.

---

## Interpreting the output

### Verdict

| OP-16 verdict | Meaning |
|---|---|
| **PROMISING** | edge_capture ≥ $771 (≥ 50% of $1542 max) — candidate eligible for next-stage validation |
| **REJECTED** | edge_capture < $771 — candidate fails the OP-16 gate regardless of aggregate Sharpe/P&L |

### Classification table

| Day | J result | Engine must | Good classification |
|---|---|---|---|
| 4/29 | +$342 winner | Take the trade and profit | **CAUGHT** |
| 5/01 | +$470 winner | Take the trade and profit | **CAUGHT** |
| 5/04 | +$730 winner | Take the trade and profit | **CAUGHT** |
| 5/05 | −$260 loser | Skip or lose ≤ J's loss | **AVOIDED** |
| 5/06 | −$300 loser | Skip or lose ≤ J's loss | **AVOIDED** |
| 5/07 | −$165 loser | Skip or lose ≤ J's loss | **AVOIDED** |

- `MISSED` = engine failed to profit on a day J won → significant edge gap
- `OVERTRADED` = engine lost money on a day J lost → cost compounds the score

### The formula

```
edge_capture = sum(engine_pnl for day in winner_days) - sum(max(0, -engine_pnl) for day in loser_days)
max_possible = $1,542  (sum of all J winner P&Ls)
floor        = $771    (50% of max — candidates below this are REJECTED per OP-16)
```

---

## Output files

| File | What |
|------|------|
| `analysis/j-edge/{date}-{slug}.json` | Machine-readable scorecard with per-day breakdown + OP-16 verdict |
| `analysis/j-edge/{date}-{slug}.md` | Human-readable report with classification table |

---

## Adding a new J source-of-truth trade

When J adds a new anchor trade to OP-16 (CLAUDE.md OP-16 source-of-truth section):

1. Update `J_WINNER_DAYS` or `J_LOSER_DAYS` in `j_winner_audit.py` (lines ~36-44)
2. Update `MAX_EDGE` to `sum(J_WINNER_DAYS.values())`
3. Re-run the audit against current production params to establish the new baseline
4. Update CLAUDE.md OP-16 "Max possible" reference

---

## Caveats

1. Results use `use_real_fills=True` backtest mode against OPRA bars — same as production validation pipeline.
2. The J-day window (2026-04-29 to 2026-05-07) is a narrow 7-day slice. edge_capture SUPPLEMENTS aggregate metrics (Sharpe, max-DD, N=16mo) — don't use it as the only ranking dimension.
3. If the SPY/VIX data CSV doesn't cover 2026-04-29 forward, the audit will return `engine_pnl=0` for missing days (MISSED on winners). Check `backtest/data/spy_5m_2025-01-01_2026-05-15.csv` covers this range.

---

## Cross-references

- **OP-16 source:** `CLAUDE.md` section "J's edge is the source of truth" (OP-16)
- **Formula in production:** `backtest/autoresearch/vix_soft_walk_forward.py` `op16_stats()`
- **Reference one-shot:** `backtest/autoresearch/audit_j_winners.py` (original, hard-coded)
- **Skills catalog:** `markdown/infra/SKILLS-CATALOG.md` (j-winner-audit entry)
