# Research Backlog — Trading Knowledge, Strategies & Algo Tech

> **What this is:** the *external-knowledge intake loop* for Project Gamma. It is NOT a strategy list — those already exist and stay canonical:
> - **[`markdown/research/STRATEGY-DIRECTION-BACKLOG.md`](../markdown/research/STRATEGY-DIRECTION-BACKLOG.md)** — self-generated structural *classes/dimensions* (premium-selling, DTE expansion, regime-switch…). The loop drives through these.
> - **[`markdown/research/STRATEGY-HUNT-BACKLOG.md`](../markdown/research/STRATEGY-HUNT-BACKLOG.md)** — the tactical signal-family sweep + gate tally.
>
> **This file is the upstream feeder:** where do NEW ideas/techniques/data feeds enter from the outside world, on what cadence do we review them, prototype them cheaply, and log the lesson. An external idea that survives a quick prototype here graduates into one of the two backlogs above (or a `markdown/research/` study) for the full gate gauntlet.
>
> **Scope lock:** 0DTE/short-DTE SPY options + futures (MNQ/MES). Crypto is gym-only. Defined-risk only — never naked.
> **Bar to graduate out of "prototype":** real OPRA fills (C1) + the standing gate stack (OOS+ · posQ≥4/6 · beats-null L172 · no-look-ahead L171/C6 · risk-adjusted L175 · recency-survivable). A whiteboard idea is worth nothing until a $0 pure-Python sim says it clears.

---

## 1. Sources List

The recurring inputs we sweep. Each row = a vein. **Rank = expected signal density for OUR scope** (0DTE/short-DTE directional + defined-risk structure). Free/$0 unless noted.

### Tier A — highest density (sweep weekly)
| Source | What we mine it for | Access |
|---|---|---|
| **arXiv q-fin** (`q-fin.TR`, `q-fin.CP`, `q-fin.ST`) | Microstructure, optimal execution, intraday vol, options-MM models, RL-for-execution | web / RSS |
| **SSRN — Derivatives & Microstructure** | 0DTE flow studies, gamma-positioning, IV-surface, event-IV-crush empirics | web |
| **CBOE / OCC research + 0DTE whitepapers** | 0DTE volume structure, dealer flow, settlement mechanics, SPX vs SPY parity | web |
| **Quantitative Finance SE + Wilmott** | Practitioner-grade modeling gotchas (greeks, pin risk, theta decay shapes) | web |
| **Context7 / vendor docs** (Alpaca, TradingView, vectorbt, OptionSuite, QuantLib) | API/library capability checks before building anything new | Context7 MCP |

### Tier B — periodic (sweep biweekly / on-trigger)
| Source | What we mine it for | Access |
|---|---|---|
| **GitHub code search** (`gh search code/repos`) | Battle-tested sims, backtest frameworks, options pricers to port (per dev-workflow Step 0) | `gh` CLI |
| **PyPI / conda** (vectorbt, nautilus_trader, lean, optopsy, py_vollib, mibian) | Don't hand-roll — adopt proven libs | registry |
| **SpotGamma / Menthor / GEX writeups (free tier)** | Dealer gamma / charm / vanna framing — re-open trigger for structure research | web |
| **Fed/BLS/macro calendar + Alpaca news** | Event-IV-crush days, regime catalysts → `automation/state/news.json` | Alpaca MCP |
| **FinTwit / Substack practitioner threads** (curated, skeptic-filtered) | Idea *seeds* only — never trusted, always re-derived on our data (L172/C4) | web |

### Tier C — deep / on-demand (use `/deep-research` skill)
| Source | When |
|---|---|
| **Exa / broad web** | Only after GitHub + primary docs insufficient (per dev-workflow Step 0) |
| **Academic textbooks** (Sinclair *Volatility Trading*, Bennett *Trading Volatility*, Euan Sinclair *Positional Option Trading*) | When a whole technique class is new to us (e.g. vol-surface arb) |

**Source hygiene (load-bearing):** every external claim is a *hypothesis*, not a result. A published cross-sectional anomaly is **not** a per-trade option edge (L166/L175). It enters as a prototype, gets the real-fills + null + OOS treatment, and most die. That's expected — the funnel is the point.

---

## 2. Weekly Plan (cadence)

Runs in the **after-4pm work block** (16:00–23:59 ET) or weekends — never mid-session (Rule 9). One pass per week, ~2–4h total, $0 (pure-Python sims + free sources + Context7). Each step writes to the tracking log (§5).

| Day-of-week (flexible within the week) | Phase | Action | Output |
|---|---|---|---|
| **Mon** | **HARVEST** | Sweep Tier-A sources. Skim titles/abstracts; capture anything in-scope as a 1-line idea card in the log (`status: new`). Read `journal/mistakes.md` first (Monday ritual). | N idea cards |
| **Tue** | **TRIAGE** | Score each new card: *plausibility × testability-on-data-we-hold × edge-if-true*. Kill the obvious dead. Promote top 1–3 to `status: prototyping`. | Sprint shortlist |
| **Wed–Thu** | **PROTOTYPE** | For each shortlisted card: cheapest possible $0 pure-Python sim on data we already hold (reuse `backtest/autoresearch/` sims). One idempotent script per card (per `serial-python-for-dependent-io`). Real fills where options-priced. | `status: tested` + verdict |
| **Fri** | **LOG & ROUTE** | Write the lesson (win OR death + root cause). Graduate survivors → STRATEGY-DIRECTION/HUNT backlog or a `markdown/research/` study. Fold any new foot-gun → `_lesson-inbox/`. Append L# if it's a reusable anti-pattern. | Lessons + routing |
| **(continuous)** | **CAPTURE** | Any in-scope idea spotted any day (from kitchen, Discord, a backtest tangent) drops into the log as `status: new`. The queue is non-empty by construction. | — |

**Guardrails:** (a) cost ≤ ~$0.20/week (OP-3 — free sources + $0 sims); (b) no source claim ships without the full gate stack; (c) silent stop = failure — every week ends with a logged outcome OR a flagged blocker (OP-25).

---

## 3. Current Sprint

> **Week of 2026-06-21.** Sprint goal: re-open the structure frontier with NEW external inputs, since the in-house signal+structure+expiry search is exhaustively mined (per the ★ CONVERGENCE note in STRATEGY-DIRECTION-BACKLOG). The convergence note explicitly names the re-open triggers: **a new data feed (wide-OPRA band, GEX/IV-surface)** or a regime flip. This sprint chases the data-feed trigger.

**Theme:** *What external technique or data feed could give premium-selling the SELECTION alpha it lacked?* — the Iron Condor LEAD cleared 7/8 gates but died on the L172 strike-null (generic theta, no selection rule). The answer, if it exists, comes from outside our current feeds.

**In flight this sprint:** the three topics in §6 below.

**Definition of done for the sprint:** each of the 3 topics has a logged verdict (`tested` + win/death + root cause). At least one either (a) graduates a concrete next-step into STRATEGY-DIRECTION-BACKLOG, or (b) is logged DEAD with a reusable lesson so we never re-spend on it.

---

## 4. Next Actions

Ordered. Top of queue is the next thing the loop does.

1. **Stand up the tracking log** — write `research/session-log.jsonl` schema (§5) + seed the 3 sprint topics as `status: prototyping` cards. _(do first — everything else appends to it)_
2. **Topic 1 (GEX / dealer-gamma feed):** scope a free/cheap source for dealer gamma & 0DTE flow; prototype whether a gamma-regime label improves the directional edge's recency drawdown OR gives the condor a selection rule. _(see §6)_
3. **Topic 2 (Event IV-crush):** the one untested direction in STRATEGY-DIRECTION-BACKLOG (#6). Prototype selling defined-risk 0DTE premium INTO scheduled FOMC/CPI/NFP using the news calendar we already hold. _(see §6)_
4. **Topic 3 (Conformal / regime-aware gating):** survey conformal-prediction & online-changepoint methods for the recency-drawdown HOLD problem (`recency_check.py` currently RED on #1) — can a principled uncertainty band beat the current 2.2σ heuristic? _(see §6)_
5. **Wire a weekly fire (optional):** if the loop proves its weight, propose a `Gamma_ResearchSweep` scheduled task (after-hours, $0) to auto-fire the Monday HARVEST. _Propose as TEXT — do not register without J._
6. **Backfill sources RSS:** capture the Tier-A arXiv/SSRN feeds as concrete URLs in a `research/sources.json` so HARVEST is one command, not manual hunting.

---

## 5. Tracking Mechanism — `research/session-log.jsonl`

Lightweight append-only JSONL (one event per line — git-friendly, grep-friendly, no schema migration pain). Every loop phase appends. **Retention cap: 500 lines** → CONSOLIDATION (archive closed `dead`/`graduated` cards older than 90d to `research/session-log.archive.jsonl`), per OP-22.

**Card schema** (one line per idea, updated by appending a new event referencing the same `id`):
```json
{
  "ts": "2026-06-21",
  "id": "R-0001",
  "event": "new | triaged | prototyping | tested | graduated | dead",
  "topic": "GEX / dealer-gamma regime label",
  "source": "arXiv 2xxx.xxxxx | SpotGamma writeup | gh:owner/repo",
  "scope": "0dte-directional | premium-selling | futures | algo-tech",
  "hypothesis": "dealer gamma sign predicts intraday mean-reversion vs trend regime",
  "test_plan": "label each day by sign(GEX); split vwap_continuation OOS by label; compare expectancy",
  "verdict": null,
  "metrics": { "oos_exp_per_tr": null, "posQ": null, "beats_null": null, "recency_ok": null },
  "lesson": null,
  "routed_to": null,
  "cost_usd": 0.0
}
```

**Field notes:**
- `event` is the lifecycle stage; append a fresh line each transition (immutable history, never edit in place — C-immutability).
- `verdict` ∈ `WIN | DEAD | LEAD | NEEDS_DATA` once `event:tested`.
- `metrics` mirrors the gate stack so a glance tells you if it's graduate-able.
- `routed_to` = path it graduated into (e.g. `markdown/research/STRATEGY-DIRECTION-BACKLOG.md#7`) or the death-doc.
- **Why JSONL not a DB:** matches the rig's existing pattern (`decisions.jsonl`, `cook-queue.jsonl`, `recommendations-log.jsonl`) — same tooling, same retention discipline, zero new infra (OP-3).

A one-line roll-up (`research/session-log.summary.md`, regenerated on each LOG phase) can give J a glance-view: open cards by status, this-week verdicts, graduation count. _(generate later — JSONL is the source of truth.)_

---

## 6. First Three Topics — dive THIS week

Picked because each targets a **re-open trigger** the in-house search explicitly named, and each is testable on data we already hold or can fetch cheaply.

### Topic 1 — Dealer-gamma (GEX) regime labeling
- **Why now:** the ★ CONVERGENCE note names "GEX/IV-surface" as a literal re-open trigger for structure research. Our recency drawdown on the live edge (#1) is *time-clustered, not regime-separable* by any morning-causal label we've tried (per regime-switch #3 death). Dealer-gamma sign is a *different, exogenous* regime axis we have never tested.
- **Hypothesis:** `sign(net dealer GEX)` at the open partitions days into mean-reverting (positive gamma → dealers dampen) vs trending (negative gamma → dealers amplify). If true: it either (a) explains/avoids the #1 recency drawdown, or (b) gives the dead Iron Condor its missing selection rule (sell premium only on positive-gamma/pin days).
- **Cheap test:** find a free/historical GEX proxy (SpotGamma free posts, or compute a crude dealer-gamma proxy from the OPRA open-interest we can pull). Label our ~365 backtest days; split `vwap_continuation` and the condor OOS by gamma sign; compare expectancy + the L172 null. $0 if proxy-computable; small fetch otherwise.
- **Kill criterion:** if positive/negative-gamma split shows no expectancy separation beyond the random-null → DEAD, log it, never re-spend (same discipline that killed the 64 families).

### Topic 2 — Event IV-crush premium-selling
- **Why now:** STRATEGY-DIRECTION-BACKLOG **#6 is the single untested direction** in the entire structural tree, and it's the one premium-selling variant that DOESN'T rely on ambient-regime allocation (which died as #3) — it sells into a *scheduled* vol collapse. We already hold the event calendar (`automation/state/news.json`) + the OPRA caches.
- **Hypothesis:** defined-risk 0DTE premium (iron condor / iron fly) sold the morning of FOMC/CPI/NFP captures a post-print IV collapse large enough to beat the strike-null that killed the ambient-regime condor — because the edge here is *timing the vol event*, not *picking the strike*.
- **Cheap test:** reuse `backtest/lib/simulator_credit.py` + `backtest/lib/multileg_structures.py` (already built, 17/17 tests) — the same multi-leg sim used by `backtest/autoresearch/_calendar_premium_sim.py`. Restrict the universe to event days only; price the condor/fly on those days; measure expectancy vs (a) non-event days and (b) the random-strike null. The selection rule is *the event itself*, which the null can't replicate.
- **Kill criterion:** if event-day condors don't beat both their own null AND the directional sleeve's event-day P&L → DEAD (same load-bearing thesis check that killed #3).

### Topic 3 — Conformal / changepoint gating for the recency-drawdown HOLD
- **Why now:** the live edge (#1) is currently **HELD by `recency_check.py`** on a ~2.2σ heuristic (RED, n=10–11). That's a hand-tuned threshold doing a job that has a principled statistical answer. This is the "cutting-edge algo tech" lane — improving *how we decide to trade*, not *what we trade*.
- **Hypothesis:** an online changepoint detector (BOCPD) or conformal-prediction band over the rolling per-trade P&L gives a calibrated "is this a regime break or normal variance" signal that beats the σ-heuristic — fewer false HOLDs (missed recovery) and fewer false GREENs (trading into a real break).
- **Cheap test:** survey `ruptures` / `river` / conformal libs via Context7 + PyPI (don't hand-roll). Backtest the gate decision retrospectively: replay #1's equity curve through BOCPD vs the current heuristic; count how often each would have correctly HELD vs traded. Pure-Python, $0.
- **Kill criterion:** if the principled method doesn't reduce false-HOLD/false-GREEN vs the current heuristic on our own history → keep the heuristic, log that the simple thing won (a valid, common outcome — don't add complexity for its own sake, OP-3).

---

*Filing note: this file lives at `research/backlog.md` per J's explicit request. It is operational (the loop appends to it weekly) rather than a one-shot human-authored reference, so it sits with its `session-log.jsonl` data beside it — same pattern as `analysis/` and `automation/state/`. Canonical strategy doctrine stays under `markdown/research/`; this is the intake funnel that feeds it.*
