# STUDY-CURRICULUM — Gamma's standing learning rotation

> **Living doc — APPEND ONLY, never fork.** Owned by the conductor STUDY MODE fire
> (`automation/prompts/conductor.md` MODES → STUDY) and the deterministic helper
> `setup/scripts/study_curriculum.py`. Origin: `automation/overnight/queue.md` item
> `GAMMA-STUDY-CURRICULUM` (MED, filed 2026-07-22 night, J-directed "learn new things —
> TA, indicators, risk management... like a person" — CLAUDE.md memory
> `feedback_gamma_presence_not_prompting_2026_07_22` / `feedback_gamma_must_generate_hypotheses_2026_07_08`).
>
> **What this is:** a rotation of TA/market-structure/risk topics Gamma reads about, one
> topic per night at most, using $0 free public sources. Each study session writes a
> 10-line note under the topic (below) and MAY file 0–2 testable hypotheses to
> `strategy/candidates/_chef-inbox/` in the canonical battery format — same validation
> gates as every other idea (chef → real-fills → OP-16 edge_capture, no shortcuts).
> **This doc never gets wired directly into the trading path.** It is Gamma's visible
> "reading a book" loop — the output is notes + hypotheses, both of which flow through
> the SAME standing machinery as everything else.
>
> **Cost:** $0 fetches (`backtest/lib/http_fetch.py`, GET only, public URLs). The LLM
> distillation piggybacks on the conductor's existing AFTERHOURS per-fire budget — see
> `automation/prompts/conductor.md` MODES table ($10 cap/fire) and
> `setup/scripts/conductor_budget.py` (nightly governor, `$30/day` cap / 8 fires max,
> self-report corrected ×2.16). No new spend line.

---

## Topic rotation

Source URLs were verified live on **2026-09-03 (ET)** via a plain GET with a
browser-like User-Agent (same helper `backtest/lib/http_fetch.py` uses) — status codes
below. Re-verify with `python setup/scripts/study_curriculum.py verify-sources` (or by
hand) if a fetch starts failing; a source that goes durably 403/404 should be swapped,
not silently skipped (L241 — a UA/rate block looks exactly like "dead source" if you
don't check the code).

| Topic | Slug | Sources | Last Studied (ET) | Status |
|---|---|---|---|---|
| Candlestick pattern taxonomies | candlestick_taxonomies | 3 | never | seed |
| Volume profile | volume_profile | 3 | never | seed |
| Market internals (TICK/ADD) | market_internals_tick_add | 3 | never | seed |
| Intraday 0DTE greeks behaviour | 0dte_greeks_intraday | 3 | never | seed |
| Risk-of-ruin / position sizing literature | risk_of_ruin_sizing | 3 | never | seed |
| VWAP bands | vwap_bands | 3 | never | seed |
| Opening range theory | opening_range_theory | 3 | never | seed |

`Last Studied (ET)` is an ISO date (`YYYY-MM-DD`) or the literal `never`. Updated ONLY
by `study_curriculum.py record` — never hand-edit this column, the parser expects the
exact table shape above (pipe-delimited, one row per topic, in this column order).

---

## Sources

### candlestick_taxonomies -- Candlestick pattern taxonomies
- https://en.wikipedia.org/wiki/Candlestick_pattern (200, verified 2026-09-03)
- https://en.wikipedia.org/wiki/Candlestick_chart (200, verified 2026-09-03)
- https://www.cboe.com/education/ (200, verified 2026-09-03 — portal, browse from here; CBOE's deep-linked article paths return 403/404 for a scripted fetch)

### volume_profile -- Volume profile
- https://en.wikipedia.org/wiki/Market_profile (200, verified 2026-09-03)
- https://www.tradingview.com/support/solutions/43000502040-volume-profile/ (200, verified 2026-09-03)
- https://www.cboe.com/education/ (200, verified 2026-09-03 — portal)

### market_internals_tick_add -- Market internals (TICK/ADD)
- https://en.wikipedia.org/wiki/Market_breadth (200, verified 2026-09-03)
- https://en.wikipedia.org/wiki/Advance%E2%80%93decline_line (200, verified 2026-09-03)
- https://www.nasdaq.com/market-activity (200, verified 2026-09-03)

### 0dte_greeks_intraday -- Intraday 0DTE greeks behaviour
- https://en.wikipedia.org/wiki/Greeks_(finance) (200, verified 2026-09-03)
- https://en.wikipedia.org/wiki/Option_time_value (200, verified 2026-09-03)
- https://www.cboe.com/education/ (200, verified 2026-09-03 — portal; CBOE hosts the only free 0DTE-specific primary material, deep links rot fast so start from the portal and search "0DTE")

### risk_of_ruin_sizing -- Risk-of-ruin / position sizing literature
- https://en.wikipedia.org/wiki/Risk_of_ruin (200, verified 2026-09-03)
- https://en.wikipedia.org/wiki/Kelly_criterion (200, verified 2026-09-03)
- https://www.investor.gov/introduction-investing/investing-basics/glossary/risk (200, verified 2026-09-03 — SEC's investor-education site)

### vwap_bands -- VWAP bands
- https://en.wikipedia.org/wiki/Volume-weighted_average_price (200, verified 2026-09-03)
- https://en.wikipedia.org/wiki/Time-weighted_average_price (200, verified 2026-09-03 — contrast case, VWAP vs TWAP)
- https://www.nasdaq.com/glossary/v/vwap (200, verified 2026-09-03)

### opening_range_theory -- Opening range theory
- https://en.wikipedia.org/wiki/Breakout_(technical_analysis) (200, verified 2026-09-03)
- https://en.wikipedia.org/wiki/Support_and_resistance (200, verified 2026-09-03)
- https://www.cboe.com/education/ (200, verified 2026-09-03 — portal)

**Sources that were tried and rejected (2026-09-03 verification pass) — don't re-add
without re-checking:** `investopedia.com/*` (Cloudflare 403 for every scripted fetch
regardless of UA/headers — human-only), `www.cmegroup.com/*` (403), `school.stockcharts.com`
/ `chartschool` (SSL handshake failure, domain appears retired/restructured),
`en.wikipedia.org/wiki/Point_of_control` and `/Tick_index` (404 — no such article).

---

## Study notes

Each fire appends ONE `#### YYYY-MM-DD (ET)` block under its topic with exactly 10
lines (numbered `1.`–`10.`) distilling what was read — facts/definitions, not trading
advice, and never a claim of an edge (that's what a filed hypothesis + the validation
gates are for). Oldest topic (by `Last Studied`) gets picked next by
`study_curriculum.py next-topic`; a topic never studied sorts before any studied date.

### candlestick_taxonomies -- Candlestick pattern taxonomies
_none yet — filed by the conductor STUDY-mode fire._

### volume_profile -- Volume profile
_none yet — filed by the conductor STUDY-mode fire._

### market_internals_tick_add -- Market internals (TICK/ADD)
_none yet — filed by the conductor STUDY-mode fire._

### 0dte_greeks_intraday -- Intraday 0DTE greeks behaviour
_none yet — filed by the conductor STUDY-mode fire._

### risk_of_ruin_sizing -- Risk-of-ruin / position sizing literature
_none yet — filed by the conductor STUDY-mode fire._

### vwap_bands -- VWAP bands
_none yet — filed by the conductor STUDY-mode fire._

### opening_range_theory -- Opening range theory
_none yet — filed by the conductor STUDY-mode fire._
