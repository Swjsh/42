# HEARTBEAT-INTEGRATION.md — Port guide: crypto/lib/ → production SPY heartbeat

> Use this when porting a validated primitive from `crypto/lib/` into the production
> SPY heartbeat. Enforces OP 4 (no code drift) — both code paths (LLM prompt + programmatic)
> must reference the same canonical logic.

---

## Mapping: crypto/lib/ → production code

| Validated primitive | Where it ports to in production | Notes |
|---|---|---|
| `crypto.lib.bar_reader.last_closed_bar` | `automation/prompts/heartbeat.md` lines 200, 214, 220 (already shipped as v15.1 fix). Backstop: `backtest/lib/filters.py` for programmatic users. | The 5/14 floor fix. |
| `crypto.lib.bar.Bar` / `BarSeries` | `backtest/lib/types.py` (when consolidated) | Internal value type; LLM prompt doesn't reference directly. |
| `crypto.lib.indicators.rsi/ema/atr/vwap` | `backtest/autoresearch/heartbeat_indicators.py` (proposed) and prompt should reference `data_get_study_values` not these — but backtest replay should use these as truth. | Math is identical. |
| `crypto.lib.candlesticks.detect_*` | Heartbeat awareness layer (per OP 6 candlesticks are awareness-only). Add to `automation/state/decisions.jsonl` as a metadata field. | Don't promote candlesticks to triggers without backtest evidence. |
| `crypto.lib.levels.classify_bar_at_level` | `automation/prompts/heartbeat.md` reclaim/break/reject trigger evaluation (currently inline doctrine). | Replace inline logic with a deterministic check. |
| `crypto.lib.trendlines.find_swing_points` | New file `backtest/lib/trendlines.py`. Heartbeat prompt then asks LLM to verify swing-point reads. | Prompt remains LLM-driven; programmatic backtest validates. |
| `crypto.lib.volume.is_volume_confirmed` | `automation/prompts/heartbeat.md` volume-gate logic | Currently inline ("vol >= 1.5x 20-bar avg"); make it explicit. |
| `crypto.lib.ribbon.compute_ribbon` | Already done by TV (`Saty Pivot Ribbon`); use this for backtest cross-check. | Validates TV's ribbon math. |
| `crypto.lib.regime.classify_regimes` | New regime tag in `loop-state.json`. Future trigger gate. | DRAFT — not yet ratified. |
| `crypto.lib.divergence.find_divergences` | Future trigger gate (DRAFT). Not enabled in v15. | OP 16 — encode J's edge first; divergence is a candidate. |
| `crypto.lib.breakout.detect_quality_breakouts` | Direct replacement for inline break-detection in heartbeat. | Use `require_clean_prior=5` (validated in v11). |
| `crypto.benchmarks.replay_5_14` | Run before any heartbeat.md change ships to production. | Pre-merge gate. |
| `crypto.validators.v13_tv_mcp_parity` | Run interactively whenever TV MCP behavior is suspect. | Capture a fresh fixture, rerun. |

---

## The integration cycle (OP 4 enforcement)

When porting a primitive:

1. **Confirm green**: `python crypto/validators/runner.py` shows OVERALL PASS.
2. **Identify the production target**: find the inline logic in `automation/prompts/heartbeat.md` or `backtest/lib/*.py` that the primitive replaces.
3. **Decide port mode**:
   - **LLM-prompt port**: the prompt now describes the algorithm in words PLUS references the canonical Python (for the backtest engine to use). Both must match.
   - **Programmatic port**: import directly from `crypto.lib.*`. Add a re-export in `backtest/lib/` if the existing import surface is namespaced differently.
4. **Backtest sync** (per OP 4): if a primitive is used in BOTH the live LLM heartbeat and the offline `backtest/autoresearch/*` engines, both must update together. Use `gamma-sync` skill or equivalent.
5. **Append to CLAUDE.md `Lessons absorbed`** (OP 25) if this port closed a previously-encoded foot-gun.
6. **Tag the canonical version**: file header line in each ported file should state "Source of truth: crypto/lib/<file>.py — sync via this path."

---

## Active integration: `last_closed_bar` (already shipped v15.1)

| Component | Status | Mirror of |
|---|---|---|
| LLM prompt | SHIPPED in `automation/prompts/heartbeat.md` v15.1 line 200, 214 | `crypto.lib.bar_reader.last_closed_bar` |
| Programmatic backtest | Recommended for next pass — add `backtest/lib/bar_filter.py` re-exporting from `crypto.lib.bar_reader` | Same |
| Regression check | `crypto/validators/v01_closed_bar.py` runs offline + live every grinder iteration. `crypto/benchmarks/replay_5_14.py` replays 5/14 ticks. | — |

---

## Pending integration: `classify_bar_at_level` (level events)

| Component | Current state | Target |
|---|---|---|
| LLM prompt | Inline doctrine in `heartbeat.md` lines 322 (`level_reject`), 324 (`sequence_rejection`) | Replace with explicit reference: "use crypto.lib.levels.classify_bar_at_level definition; engine uses min_margin_pct=0.05 (5 bp) on SPY closes" |
| Programmatic backtest | None yet | Import `from crypto.lib.levels import classify_bar_at_level` into `backtest/autoresearch/runner.py` if/when level-event gates are added |
| Regression check | `crypto/validators/v05_levels.py` 10/10 offline + live | Continue |

Recommended ratification: weekend doctrine review. Update heartbeat.md v15.2 to reference the canonical definition.

---

## Pending integration: `detect_quality_breakouts`

| Component | Current state | Target |
|---|---|---|
| LLM prompt | Inline breakout doctrine scattered across `heartbeat.md` | Single section referencing `crypto.lib.breakout.detect_quality_breakouts` with knobs (`min_close_margin_pct=0.05`, `volume_threshold=1.5`, `require_clean_prior=5`) |
| Programmatic backtest | None yet | Add import + use in autoresearch when breakout-style strategies are evaluated |
| Regression check | `crypto/validators/v11_breakout.py` 4/4 offline + live (after `require_clean_prior=5` fix) | Continue |

---

## Pending: `regime`, `divergence`, `trendlines`

These are **NEW** primitives — they don't yet exist in heartbeat.md. Per OP 16 (encode J's edge first), they stay in `crypto/lib/` as instrumentation until backtest evidence justifies promoting them to trigger gates. The validators run continuously; the data accumulates; the case for promotion is built or rejected.

---

## Tracking knobs

| Knob | Current value | Source of truth | When to retune |
|---|---|---|---|
| Closed-bar stale threshold | `2 * granularity` (= 10 min on 5m) | `crypto/lib/bar_reader.py:last_closed_bar` | If grinder reports `stale_data` verdict > 5% of iterations |
| Source parity tolerance | 0.05% | `crypto/validators/v02_source_parity.py:PRICE_TOLERANCE_PCT` | If grinder reports `disagreements_above_tolerance` > 0 in > 20% of iterations |
| Level event margin | 0.05% | `crypto/lib/levels.py:classify_bar_at_level(min_margin_pct=0.05)` | If level events are dominated by `hold` (signal too noisy) |
| Volume confirmation | 1.5x 20-bar | `crypto/lib/volume.py:is_volume_confirmed(threshold=1.5)` | If breakout false-positive rate > 30% on backtest |
| Hammer wick ratio | 2.0x body | `crypto/lib/candlesticks.py:detect_hammer(wick_ratio=2.0)` | If hammer count > 10% of all bars (too sensitive) |
| Doji body ratio | 10% of range | `crypto/lib/candlesticks.py:detect_doji(body_ratio=0.10)` | If doji count > 5% of all bars |
| Breakout clean-prior | 5 bars | `crypto/validators/v11_breakout.py` live call | If breakout count < 1 per 100 bars (too strict) |
| EMA ribbon lengths | 9 / 21 / 55 | `crypto/lib/ribbon.py:compute_ribbon` | Match TV's Saty Pivot Ribbon defaults |

---

## CRITICAL DO-NOT-DOs

1. **Do NOT modify production CLAUDE.md params.json** from inside `crypto/` — that's project-doctrine territory, gated by J's ratification (rule 9 + OP 24).
2. **Do NOT place crypto orders** — `crypto/` is read-only on the trading surface. If we ever trade crypto, it goes in a separate folder.
3. **Do NOT skip `python crypto/validators/runner.py`** before merging heartbeat.md changes. Pre-merge gate, period.
4. **Do NOT trust an unverified port** — when a primitive is ported, capture a before/after benchmark proving the SPY behavior is unchanged (or improved) on at least one historical day.

---

## Quick reference

| Need | Command |
|---|---|
| Full validation + benchmark | `python crypto/validators/runner.py` |
| Just the 5/14 floor test | `python crypto/benchmarks/replay_5_14.py` |
| Grinder analysis | `python crypto/benchmarks/analyze_grinder.py` |
| TV MCP parity (interactive Claude session needed) | Re-capture fixture, run `python crypto/validators/v13_tv_mcp_parity.py --mode fixture` |
| Single validator | `python crypto/validators/v05_levels.py --mode both` |
