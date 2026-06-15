# Pressure Tests — TDD for Filter Creation

> **Multi-Agent Gamma 2.0 — Big Win #8 (and Hidden Gem #2).** Source pattern: obra/superpowers
> `writing-skills` meta-skill — every new skill is RED-GREEN-REFACTOR. Adapted to filter creation.
>
> **The methodology:** every recurring loss fingerprint becomes a failing replay test BEFORE
> any new filter is written. The minimal filter is added; replay must now block the loss; ratify.
> Closes the missing loop in the Karpathy method (operating principle 11): we have data flywheel
> + per-loss chart-walks, but no codified RED→GREEN cycle for filter creation. This is it.

---

## The 5-step cycle

### 1. RED — Write a failing pressure test

For each `R-NNNN` loss-pattern fingerprint identified in weekly-review Section 3.5, create
`test_R{NNNN}.py` in this directory.

The test:
- Loads SPY/VIX bars from a specific date+time window where the loss occurred
- Replays the live engine (`run_backtest` from `lib.orchestrator`) with **production v14 params**
- Asserts that the engine takes the losing trade (the one we want to block)
- **The test PASSES on RED** — i.e., the loss reproduces. If it doesn't reproduce, the
  fingerprint is wrong; revisit the loss-walk markdown.

### 2. Identify the minimal blocking filter

Look at the chart-walk in `journal/losses/{date}-{HHMM}-{setup}.md`. The "Candidate blocking
filter" section names the proposed filter. Examples:
- "Block BEARISH entry if VIX spread between two consecutive 5m bars > $0.40 (vol spike)"
- "Block BULLISH entry within 30min of a high-impact event already passed (post-event chop)"
- "Block any entry where prior bar is a doji larger than 1× 20-bar range"

The filter MUST be expressible as a function `(BarContext) -> bool`. If it requires a new state
field or new MCP call: stop, escalate to architectural review (operating principle 8 — ask J).

### 3. GREEN — Write the minimal filter

Add the filter to `backtest/lib/filters.py`. Wire it into the appropriate filter family (entry
gate or exit gate). Re-run the pressure test:
- The test must now FAIL the loss assertion (filter blocks the entry)
- A "should also pass" assertion can verify the filter does NOT over-trigger on a known winner
  bar (regression guard)

### 4. REGRESSION CHECK — Run full backtest

Run `python -m autoresearch.runner` (or call `runner.run_with_params` directly) on the validate
window with the new filter active.
- Net P&L must NOT regress more than 5% vs prior validate baseline
- N_trades must NOT drop more than 25% (else the filter is too aggressive)
- Sharpe must NOT regress more than 0.30
- If ANY of these gates fail: the filter is over-fitted to the loss; tighten the filter scope or
  abandon. Don't add a filter that costs more than it saves.

### 5. RATIFY — Bump rule version + log

If steps 1-4 pass:
- Bump `params.json#rule_version` (e.g., v14 → v14.1)
- Update `RULE_VERSION` constant in `automation/prompts/heartbeat.md`
- Update `RULE_VERSION_EXPECTED` in `automation/prompts/premarket.md`
- Append CHANGELOG entry with: pressure-test ID, before/after metrics, R-NNNN fingerprint
- Move the test from `pressure_tests/pending/` to `pressure_tests/ratified/` (folders below)

---

## Directory structure

```
pressure_tests/
├── README.md             ← this file
├── __init__.py
├── conftest.py           ← pytest fixtures (load_bars_at, load_filters_module, etc.)
├── pending/              ← tests authored, awaiting filter implementation
│   └── test_R0001.py     ← e.g., post-event chop bull entry
├── ratified/             ← tests where filter shipped + regression passed
│   └── test_R0002.py
└── examples/
    └── test_template.py  ← copy this as starting point for new tests
```

## Pytest configuration

Run all pressure tests:
```
pytest backtest/tests/pressure_tests/
```

Run a single test:
```
pytest backtest/tests/pressure_tests/pending/test_R0001.py -v
```

Use markers to filter:
```python
import pytest

@pytest.mark.pressure
@pytest.mark.r_id("R0001")
def test_post_event_chop_blocks_bull_entry():
    ...
```

`pytest backtest/tests/pressure_tests/ -m "pressure and r_id('R0001')"`

---

## CI hook (premarket gate)

Before market open each day, premarket Step 1c could be extended to run:
```
pytest backtest/tests/pressure_tests/ratified/ --tb=line -q
```

If ANY ratified test fails, the engine has regressed. Kill-switch the day. Cost: ~5 sec/day,
zero LLM tokens. Catches accidental filter-removal or import-order bugs that wouldn't otherwise
surface until a live loss reproduced the original pattern.

---

## Anti-patterns

| Anti-pattern | Why it's banned |
|---|---|
| Writing the filter first, then writing the "test" to confirm it works | The test is no longer a failing-first guard — it's a tautology. ALWAYS RED before GREEN. |
| Skipping the regression check ("the filter is just for that one loss, it can't hurt") | Every filter shrinks trade frequency. The regression check is the only way to verify net positive expectancy. |
| Adding 3 filters in one ratification cycle | Can't tell which filter actually moved the needle. Ratify ONE filter per cycle, observe live, then iterate. |
| Authoring a test that loads the wrong date/time and "happens to pass RED" | False confidence. Always cross-check the loaded bars match the loss-walk markdown's date/time. |

---

## Cost (operating principle 3)

Pure Python tests = $0 LLM. Manual filter writing = ~$0.20 per R-NNNN if I (Gamma) dispatch a
sub-agent. Premarket pytest gate = $0 LLM, ~5 sec wall-time. Total: under $5/mo even with
2-3 R-NNNN cycles per week.

---

## Cross-references

- `analysis/recommendations/SCORECARD_TEMPLATE.json` — gate template for ratification scorecard
- `automation/prompts/weekly-review.md` Section 3.5 — fingerprint clustering source
- `journal/losses/` — per-loss chart-walks generated by EOD-summary 7i
- CLAUDE.md operating principle 11 — Karpathy method (this is the missing GREEN loop)
- `docs/plans/multi-agent-gamma.md` Big Win #8 — origin doctrine
