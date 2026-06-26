---
name: chart-read
description: The Chart Master's one-shot structured chart read for SPY. Fuses MARKET STRUCTURE (trend from swings, HH/HL/LH/LL sequence, BOS/CHoCH — the layer the engine was missing) + CHART PATTERNS (double bottom/top, H&S, rejection, momentum, inside-bar) + nearest named LEVEL into one object + a plain-English line in J's language. Connectivity-gated head-to-toe — runs connectivity-gate FIRST, and the detector itself FAILS LOUD (flags STATUS.md, exits non-zero) on an empty/stale feed rather than writing a confident read to thin air. Three modes: morning (premarket bias), intraday ("what's the structure right now"), backtest (offline CSV/gym). Invoke at premarket, any time J asks "what's the chart doing / are we making higher highs / what's the structure", or before a discretionary read. NEVER trades, NEVER a trigger — READ-ONLY.
---

# Skill: chart-read

> "We need to be better charting. You need to be a chart master." — J, 2026-06-20.
> This is the daily reader. It answers J's literal question — *are we making higher highs and lower lows?* — that the ribbon-only engine could not.

Pairs the **[market_structure.py](../../../crypto/lib/market_structure.py)** detector (new — swing labeling + trend + BOS/CHoCH), the existing **[chart_patterns.py](../../../crypto/lib/chart_patterns.py)** library, and **key-levels.json** into a single read via **[backtest/autoresearch/chart_read.py](../../../backtest/autoresearch/chart_read.py)**.

Reference for what every term means + cited geometry: **[TA-PATTERN-REFERENCE.md](../../../markdown/research/TA-PATTERN-REFERENCE.md)**. Capability map + gaps: **[TA-CAPABILITY-AND-GAPS-2026-06-20.md](../../../markdown/research/TA-CAPABILITY-AND-GAPS-2026-06-20.md)**.

---

## Connectivity FIRST — the no-thin-air contract (two layers)

J's hard requirement: *"connectivity checks built in, so we're not writing to thin air."* This skill enforces it at **two** layers so a read can never be confidently produced from a dead feed (the frozen-but-200 TradingView SPOF from the autonomy blueprint):

1. **Skill layer (you, before pulling bars):** invoke **`connectivity-gate`**. If RED → STOP. Report the failed node + heal hint. Do NOT fabricate a read.
2. **Module layer (the detector, always):** `chart_read.py` refuses to compute on 0 usable bars or a degraded feed — it appends a RED line to `automation/overnight/STATUS.md` "Known broken" and exits non-zero. So even if fired by cron or another skill without the gate, it cannot write to thin air.

---

## Procedure

### Mode: `intraday` ("what is the chart doing right now") and `morning` (premarket bias)

1. **Connectivity gate.** Run `connectivity-gate` (or the `tradingview-ops` guard). RED → stop.
2. **Pull bars from TradingView MCP.** `chart_set_symbol("BATS:SPY")`, `chart_set_timeframe("5")`, then `data_get_ohlcv(count=60, summary=true)`. Pass the RAW bars through — **do not hand-filter the in-progress bar**; the module drops it via `--drop-last-bar` (closed-bar discipline lives in code, not LLM prose).
   - `morning`: pull `count=80` so prior-day context is included for the structural read + bias.
3. **Write the bars** to `automation/state/_chart-read-bars.json` as a JSON list of `{time, open, high, low, close, volume}` (time = ISO or epoch s/ms — both handled).
4. **Run the reader:**
   ```
   python backtest/autoresearch/chart_read.py --mode intraday --bars-json automation/state/_chart-read-bars.json --symbol SPY --drop-last-bar
   ```
   (use `--mode morning` for the premarket read.)
5. **Report** the printed one-line summary + open `analysis/chart-read-{date}.json` for the detail. Describe the chart to J in structure + candlestick language: e.g. *"SPY downtrend — last two swings LH then LL, bearish BOS below 733.10; rejection_at_level fired at 735.4; nearest level Carry 735.40, 0.12 above."*

### Mode: `backtest` (offline / gym — no MCP)

```
python backtest/autoresearch/chart_read.py --mode backtest --csv backtest/data/spy_5m_2025-01-01_2026-05-15.csv --date 2026-05-04 --print-only
```
No connectivity gate needed (the CSV is the source of truth). Level proximity is skipped in this mode (historical bars vs current levels are not contemporaneous).

---

## What it reads (the three layers)

| Layer | Source | Output fields |
|---|---|---|
| **Market structure** | `crypto/lib/market_structure.py` | `trend` (uptrend/downtrend/range/unknown), `recent_label_sequence` (HH/HL/LH/LL), `last_swing_high/low`, `last_event` (BOS/CHoCH + direction), `structure_confidence` |
| **Chart patterns** | `crypto/lib/chart_patterns.py` | `patterns[]` — double_bottom, double_top, head_and_shoulders, failed_breakdown_wick, rejection_at_level, momentum_acceleration, inside_bar_consolidation (bias + confidence + key_price) |
| **Level proximity** | `automation/state/key-levels.json` | `nearest_level` (name, price, tier, distance, side) — live/morning only |

Tunables: `--window N` (swing strictness; 2 = 5m default — **validated on 93 real SPY days, 0 indecisive**), `--drop-last-bar` (drop in-progress bar in-module), `--tf-seconds`, `--out`.

SPY-history audit (offline coverage): `python backtest/autoresearch/chart_read.py --scan --csv backtest/data/spy_5m_2025-01-01_2026-05-15.csv --date <start> --scan-end <end>` → trend distribution + BOS/CHoCH density + crash count over the range.

---

## Success criteria
- Connectivity gate GREEN before any live pull.
- A one-line summary printed + `analysis/chart-read-{date}.json` written **only when bars are real**.
- On a dark/empty/degraded feed: STATUS.md "Known broken" gets a RED line, exit code ≠ 0, **no read file written**.

## Failure → cause → heal
| Symptom | Cause | Heal |
|---|---|---|
| `RED: 0 usable bars` | TV feed dark / bars-json empty | run `connectivity-gate -Heal`; re-pull bars |
| `structure read degraded` (< 10 bars) | too few bars pulled | raise `count` on `data_get_ohlcv` |
| `trend=unknown` on a full day | < 2 swings each side at this `window` | lower `--window` to 1 |
| nearest_level nonsensical | stale/empty key-levels.json | refresh levels (premarket); harmless in backtest (skipped) |

## Guardrails
- **READ-ONLY.** Never places orders, never edits params.json / heartbeat.md, **never a trigger.** It is telemetry + situational awareness, exactly like the WATCH_ONLY watcher fleet.
- Pure Python after the MCP pull — `$0` recurring, no LLM in the detection loop.
- Detector correctness is proven by the gym validator **`crypto/validators/v46_market_structure.py`** (13/13 offline + live). Re-run via `python -m crypto.validators.runner`.
