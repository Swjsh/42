# Plan B — Autonomous Multi-Agent Free Kitchen + Web Forager

**Date:** 2026-06-24 (hardened)
**Status:** HARDENED v2 — implementation-ready spec. Supersedes the 2026-06-24 rough draft.
**Companion:** [`FREE-AGENT-PLAN-A-SHADOW-EVALS.md`](FREE-AGENT-PLAN-A-SHADOW-EVALS.md)
**Hardened from:** 2 codebase audits (data layer + LLM/swarm layer) + 3 web-research sweeps (free-model landscape, free data sources, strategy-mining + audit) — June 2026. Source URLs in the Appendix.

> **What this is.** The rough draft proposed turning the single-model Kitchen into a swarm of specialized free models. This version keeps that vision, grounds it in what the repo *actually* already has, and adds the piece J asked for: **an always-on free web agent that forages market data + strategy ideas to feed the gym — with a hard audit gate so it can't poison the gym with garbage.** It also confronts the one inconvenient truth the rough draft skipped: *free intraday 0DTE options data does not exist*, which bounds what "refuel the gym" can mean and forces a specific hybrid design.

---

## 0. TL;DR — what changed from the rough draft

1. **The swarm is ~70% already built.** `swarm_consult.py` already does parallel multi-model fan-out + synthesis (5 modes: audit/brainstorm/critique/rank/decide). `run_minimax.call_minimax()` is a universal OpenRouter adapter with key-loading, a pricing table, per-call telemetry, and a 4-tier fallback ladder with per-tier 429 cooldowns. The Kitchen queue (`cook-queue.jsonl`) is an append-only event log with claim/reap/retry. **Plan B = compose these + add two new roles, not rebuild coordination from scratch.**
2. **The Forager is split into two, because they have different contracts.** A **Data Forager** (gathers candlesticks/VIX/enrichment → must hit the gym's CSV data contract → gated by a data-quality auditor) and a **Strategy Forager** (gathers strategy *ideas* → structured intake schema → gated by a 6-stage statistical-rigor + 0DTE-applicability quarantine). Lumping them was the draft's biggest gap.
3. **Free intraday 0DTE *options* data does not exist.** Spot data (SPY/VIX 5m) refuels freely forever; option *real-fills* do not. The design is a **3-layer hybrid**: keep the existing Alpaca-indicative daily append (free, Feb-2024-forward), add a **Black-Scholes synthetic layer flagged `is_synthetic` for ranking-only** (never WR authority — this is literally Lesson C1), and **flag** a ~$40/mo ThetaData / Databento-credit upgrade as OFF-by-default for the day J wants true deep OPRA history.
4. **The Forager is a multiple-testing machine, so its value is the *audit gate*, not the harvest.** Public strategies decay ~26% out-of-sample / ~58% post-publication (McLean–Pontiff); ~65% of published anomalies fail to replicate (Hou–Xue–Zhang). The Strategy Forager increments a **trial counter `N`**, and each idea must clear a **Deflated-Sharpe hurdle that grows with `N`** before it's allowed to spend gym compute. Harvesting is cheap; the quarantine is the product.
5. **Throughput is the binding constraint, and "super free" is a lane pool with a local floor.** OpenRouter `:free` floors at **50 req/day**. *Making 3 OpenRouter accounts does NOT help — it's a bannable ToS violation AND ineffective (OR governs free capacity globally per-person).* The real multiplier is **different providers** (Groq ~14,400 req/day, Cerebras 1M tok/day, Gemini 1M-ctx, Mistral 1B tok/mo — each an independent legal free bucket) **plus a local Ollama model as the never-dark floor** (no quota, no ToS, fully private). Net: ~15K+ req/day + ~3B tok/mo + a 1M-ctx lane + an unlimited local floor, all $0 and ToS-clean. Full design in §7.
6. **Two new non-negotiable guards.** (a) **Privacy routing** — Gemini/Mistral free tiers *train on your inputs*; only public scraped pages may go there, never anything touching account state, keys, or proprietary edge logic. (b) **Injection sanitization** — a scraped "strategy" page is untrusted input (OWASP-LLM 2026); the forager *extracts into a fixed schema*, it never treats page text as instructions.
7. **Model ids are perishable.** Kimi K2.6 silently lost its `:free` tag on 2026-06-13 → 404. Every always-on task reads its model from a **`model-roster.json` with liveness auto-rotation** — never a hardcoded `:free` id.

---

## Build status — 2026-06-24 evening (autonomous build session)

**Phase 0 keystone — BUILT + VERIFIED:**
- [`automation/state/model-roster.json`](../../automation/state/model-roster.json) — lane config (roles → ordered lanes → local floor, privacy flags). ✓
- [`setup/scripts/swarm_client.py`](../../setup/scripts/swarm_client.py) — lane-pool client (privacy gate, per-lane 429 cooldown, cross-provider failover, JSON-validate-or-repair). ✓ **9/9 offline tests** ([`test_swarm_client.py`](../../setup/scripts/test_swarm_client.py)).
- **Local Ollama floor — INSTALLED + PROVEN.** Ollama 0.30.9, `qwen3:14b` pulled; `swarm_client` returns `pong` from the local lane end-to-end.
- **Live failover PROVEN under real load:** a `coordinator` call hit groq (401, no key yet) → OpenRouter (**429 — the free tier is currently exhausted by the running 24/7 kitchen daemon, which is itself 429-ing right now**) → **fell through to the local floor and returned correctly.** The never-dark guarantee fired for real, and it's live proof that OpenRouter's 50/day floor is the binding constraint (§7).

**Phase 2 start — BUILT + VERIFIED:**
- [`backtest/tools/data_auditor.py`](../../backtest/tools/data_auditor.py) — row-level quality gate (schema, **tz/DST mislabel detection**, OHLC integrity, stale/jump, options vwap, quarantine + fail-loud). ✓ **9/9 offline tests** ([`test_data_auditor.py`](../../backtest/tools/test_data_auditor.py)). Complements the existing `data_coverage_manifest.py` (freshness vs quality).

**Broker-data question — RESOLVED (§4a):** free Alpaca already = true-OPRA bars; ThetaData/WeBull buy nothing; WeBull rejected (ban-risk). **No spend.**

**Needs J (non-blocking):**
1. **Free provider keys** so the cloud lanes light up and the swarm stops competing with the kitchen for OpenRouter's 50/day: **Groq** (biggest win, ~14.4K req/day), **Gemini** (AI Studio), **Cerebras**. Drop each into `automation/state/.{groq,gemini,cerebras}.key` (gitignored).
2. **Disk:** C: ~99% full (11GB free after I cleaned up); D: (767GB)/E: (466GB) have room. For bigger local models, relocate Ollama to D: deliberately (`OLLAMA_MODELS=D:\ollama-models`) — left for a supervised step (harness guards block autonomous disk surgery).
3. The running **kitchen daemon is currently dark on OpenRouter (429s)** — wiring `swarm_client` into it (Phase 1) gives it local-floor failover so it never goes dark. Touches live infra → queued for a reviewed step, not done unsupervised.

---

## 1. Background (read this cold)

**Project Gamma** — autonomous 0DTE SPY options trading system. J does not sit at a desk during market hours; the engine trades for him. Repo: `https://github.com/Swjsh/42` (PUBLIC — treat everything committed as world-visible). Strict secrets discipline: keys live only in gitignored files (`.openrouter.key`, `.mcp.json`, …), loaded at runtime.

**The Kitchen (exists today).** A 24/7 free-tier R&D loop, three coupled scheduled tasks:

```
Gamma_KitchenSeeder       (hourly :20)    Nemotron brainstorms 5 cook tasks  → cook-queue.jsonl
Gamma_KitchenDaemonKeepalive (5 min)      kitchen_daemon.py polls queue → cooks → strategy/candidates/
Gamma_KitchenReviewer     (every 2h :45)  Nemotron triages PROMOTE/VALIDATE/DUPLICATE/LOW_QUALITY
```

All on `nvidia/nemotron-3-super-120b-a12b:free`, $0. The daemon never touches production files (`heartbeat.md`, `params*.json`, `decisions.jsonl`), never places orders. Full spec: [`markdown/infra/KITCHEN-SPEC.md`](../infra/KITCHEN-SPEC.md).

**Plan A (in flight, prerequisite).** Benchmarks two more free models as shadow evaluators with their own hardened "iron-gate" rubric files in `setup/rubrics/`: `qwen` and `deepseek-r1`, plus an ensemble vote. The hardening method — pick a free model, wrap it in one markdown rubric, replay history, add a rule per hallucination, repeat to ≥85% decision-tick agreement — is the same method Plan B uses to onboard every new swarm model.

---

## 2. Three reality checks that reshape the plan

### RC-1 — The coordination layer mostly exists. Reuse it.

| Plan B concept | Already exists as | Verdict |
|---|---|---|
| Multi-model fan-out + synthesis (Coordinator/Critic panel) | `setup/scripts/swarm_consult.py` → `consult(mode, question, context, models, synthesizer)`; `ThreadPoolExecutor` fan-out, per-model perspectives, synthesizer pass; modes audit/brainstorm/critique/rank/decide | **Direct reuse** as the swarm primitive |
| Per-model call with fallback + cost + 429 handling | `run_minimax.call_minimax(prompt, system, model, max_tokens, temperature, timeout, task_id, enforce_cap, stream)` → envelope `{ok, content, model, input_tokens, output_tokens, cost_usd, elapsed_s, error}` | **Direct reuse** as the call adapter |
| Model ladder w/ per-tier 429 cooldown | `chef_nemotron.MODEL_LADDER` + `kitchen_daemon._build_effective_ladder()` / `_update_tier_429_state()` | **Direct reuse**; extend to cross-provider |
| Task inbox / dispatch / claim / retry | `cook-queue.jsonl` append-only event log + `kitchen_daemon` loop | **Direct reuse**; add `task_type` routing |
| OpenRouter key load | `run_minimax._load_api_key()` — env `OPENROUTER_API_KEY` → else `automation/state/.openrouter.key`, asserts `sk-or-` prefix | **Direct reuse** |
| Per-model rubric files | `shadow_model_eval.MODELS` + `load_rubric()` reading `setup/rubrics/{model}.md` | **Direct reuse** pattern |
| Cost telemetry + daily cap | `automation/state/minimax-calls.jsonl` + `enforce_cap` | **Direct reuse** |

**Implication:** the "Coordination Layer" in the rough draft's Phase 1 is mostly a *wiring* job (route `task_type` → role → model via the existing primitives), not a build. Budget the saved effort into the Forager + audit pipelines, which are genuinely new.

### RC-2 — The gym's fuel is two different fuels, and one of them isn't free.

The gym consumes two data classes with **different contracts and different free-availability**:

| Fuel | Contract (verified in repo) | Free to refuel? |
|---|---|---|
| **Spot bars** (SPY, VIX) | `backtest/data/spy_5m_{START}_{END}.csv`, cols `timestamp_et,open,high,low,close,volume`, ET-aware ISO timestamps, 5-min, 04:00–16:00 ET. Loaded by `backtest/run.py`. Versioned by SHA256 in `analysis/backtests/data-versions.jsonl`. | **Yes, forever.** Alpha Vantage + Alpaca IEX + Stooq + FRED VIX. Solved problem. |
| **Option real-fills** (OPRA) | `backtest/data/options/{OCC}.csv`, cols `timestamp_et,open,high,low,close,volume,vwap,trade_count`, OCC symbol `SPY{YYMMDD}{C\|P}{strike*1000:08d}`. Loaded by `backtest/lib/option_pricing_real.load_contract_bars()`; consumed by `simulator_real.py` — **the only WR authority (Lesson C1)**. Cache built by `backtest/tools/expand_opra_cache.py` from Alpaca. | **No.** Free intraday 0DTE OPRA history effectively does not exist (see §6a). |

This is the single most important correction to the rough draft. "An agent on the web refueling candlesticks" works beautifully for **spot**, and is the right design. It **cannot** freely refuel **option real-fills**, which is what the gym's win-rate authority actually runs on. The plan must say this out loud and design around it (§6a) instead of implying infinite free option data.

### RC-3 — A forager that harvests public strategies is a false-discovery factory unless gated.

The web is a multiple-testing machine and so is any bot that scrapes it:
- McLean & Pontiff: published predictors decay ~26% OOS, ~58% post-publication.
- Hou, Xue & Zhang: ~65% of 452 anomalies fail to replicate.
- This gym *already* paid to learn the domain-specific version (Lessons C3/C4): **a SPY-underlying price edge ≠ a 0DTE option edge** (theta/delta/stop-misfire erase it), and a structural-gate pass a random-entry null reproduces is an exit artifact, not alpha.

So the Strategy Forager's entire value is the **quarantine pipeline** (§6b), whose two load-bearing gates are (1) a **Deflated-Sharpe screen whose hurdle grows with the forager's own trial count `N`**, applied *before* spending gym compute, and (2) the **0DTE-option-translation gate**. Harvesting is the cheap, easy 10%.

---

## 3. Hardened architecture

### 3.1 Roles (now 7)

| Role | Default model (primary / fallback) | What it does | Source of model strength |
|---|---|---|---|
| **Coordinator / router** | `meta-llama/llama-3.3-70b-instruct:free` / `nvidia/nemotron-3-nano-30b-a3b:free` | Reads swarm state, routes `task_type`→role→model, tracks workloads + approval rates, schedules hardening passes. Cheap, fast, predictable JSON/tool-calls. | Llama-3.3 has the most reliable free JSON-mode for a dispatcher |
| **Strategist** (ideation) | `nvidia/nemotron-3-ultra-550b-a55b:free` / `deepseek/deepseek-v4-flash:free` | Generates strategy hypotheses *with reasoning traces*; the trace is the rationale saved for Chef. | Biggest free reasoner + 1M ctx; DeepSeek-V4 near-frontier reasoning backup |
| **Coder** (structured output) | `qwen/qwen3-coder:free` / `qwen/qwen3-next-80b-a3b-instruct:free` | Hypothesis → valid backtest-config JSON + candidate spec. **Non-reasoning** model so JSON isn't polluted by `<think>`. | Best free code/JSON emitter |
| **Validator** | `nvidia/nemotron-3-super-120b-a12b:free` | DT-agreement reality anchor (shadow eval) on any candidate; flags claim-vs-real divergence. | The 27/27-DT proven workhorse |
| **Critic** (adversarial) | `deepseek/deepseek-v4-flash:free` + `nvidia/nemotron-3-super-120b-a12b:free` (2-model panel) | "Try hard to kill this candidate." Diversity > redundancy for adversarial review. | Sharp reasoning chains; second opinion from a different family |
| **Data Forager** | `gemini-3-flash` (Google AI Studio, own key) / `nvidia/nemotron-3-super-120b-a12b:free` | Pulls + audits market data (spot bars, VIX, enrichment) from free sources; writes contract-conforming CSVs only after the data-auditor passes them. | Gemini Flash = 1M ctx on its *own* quota; keeps page-reading off the OR cap. **Public data only** (privacy). |
| **Strategy Forager** | `gemini-3-flash` (own key) / `nvidia/nemotron-3-super-120b-a12b:free` | Harvests strategy ideas from sanctioned APIs; extracts into intake schema; runs the quarantine pipeline. | Long-context extraction; **public pages only** |

> **Why two foragers share a model but not a pipeline:** same long-context extraction muscle, but the Data Forager's output is gated by *numeric data-quality checks* and the Strategy Forager's by *statistical-rigor + applicability checks*. Different gates, different output contracts, different quarantine dirs.

### 3.2 Model roster is config, not code (deprecation survival)

A single file `automation/state/model-roster.json` maps `role → [ordered model ids] → provider`. Every always-on task resolves its model through this file. A daily **liveness probe** (one cheap ping per id) demotes any id returning 404 / "no endpoints" and promotes the next in its list, then writes a flag to `STATUS.md`. This is the structural answer to "Kimi lost `:free` on 2026-06-13." **No always-on task may hardcode a `:free` id.**

Each role is an **ordered list of lanes** `(provider, model)`, always ending in the **local floor** so a role can never run out of capacity. `privacy: "sensitive"` roles are restricted to no-train lanes (Groq/Cerebras/NVIDIA/local); `privacy: "public_ok"` roles may use training-on-input lanes (Gemini/Mistral) because they only ever see public scraped pages.

```jsonc
// automation/state/model-roster.json  — provider creds live in .openrouter.key / per-provider key files (gitignored)
{
  "updated_utc": "2026-06-24T21:40:00Z",
  "local_floor": { "provider": "ollama", "base_url": "http://localhost:11434/v1/", "model": "qwen3:14b" },
  "roles": {
    "coordinator": { "privacy": "sensitive", "lanes": [
      { "provider": "groq", "model": "llama-3.1-8b-instant" },
      { "provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct:free" },
      { "provider": "ollama", "model": "qwen3:14b" } ] },
    "strategist":  { "privacy": "sensitive", "lanes": [
      { "provider": "openrouter", "model": "deepseek/deepseek-r1:free" },
      { "provider": "openrouter", "model": "nvidia/nemotron-3-ultra-550b-a55b:free" },
      { "provider": "ollama", "model": "qwen3:14b" } ] },
    "coder":       { "privacy": "sensitive", "lanes": [
      { "provider": "cerebras", "model": "qwen-3-coder-30b" },
      { "provider": "openrouter", "model": "qwen/qwen3-coder:free" },
      { "provider": "ollama", "model": "qwen3:14b" } ] },
    "validator":   { "privacy": "sensitive", "lanes": [
      { "provider": "openrouter", "model": "nvidia/nemotron-3-super-120b-a12b:free" },
      { "provider": "ollama", "model": "qwen3:14b" } ] },
    "critic":      { "privacy": "sensitive", "lanes": [
      { "provider": "openrouter", "model": "deepseek/deepseek-r1:free" },
      { "provider": "cerebras", "model": "qwen-3-32b" },
      { "provider": "ollama", "model": "qwen3:14b" } ] },
    "forager":     { "privacy": "public_ok", "lanes": [
      { "provider": "google_aistudio", "model": "gemini-3-flash-lite" },
      { "provider": "openrouter", "model": "nvidia/nemotron-3-super-120b-a12b:free" },
      { "provider": "ollama", "model": "qwen3:14b" } ] }
  },
  "dead": [ { "id": "moonshotai/kimi-k2.6:free", "since": "2026-06-13", "reason": "404 no endpoints" } ]
}
```

### 3.3 Communication — file bus (no direct model-to-model calls)

Models never call each other; they read/write shared files. Two write disciplines, to avoid races:
- **Append-only event logs** (multi-writer safe): `cook-queue.jsonl`, `forage-log.jsonl`, `strategy-intake.jsonl`, `kitchen-critic-log.jsonl`, `data-versions.jsonl`. Collapse-on-read like the existing queue.
- **Single-writer atomic snapshots** (one owner, tmp→rename): `kitchen-swarm-state.json` (Coordinator only), `kitchen-status.json` (daemon only), `model-roster.json` (liveness probe only). Readers never write them.

```
cook-queue.jsonl            task inbox (all roles read; append-only)
kitchen-swarm-state.json    who's doing what + approval rates (Coordinator writes; atomic)
model-roster.json           role→model map (liveness probe writes; atomic)
strategy/candidates/        Coder writes → Validator scores → Critic grades
backtest/data/ (+ _quarantine/)  Data Forager writes ONLY after auditor passes
strategy-intake.jsonl       Strategy Forager intake + quarantine state (append-only)
forage-log.jsonl            every forage attempt + outcome (append-only; silent-failure ban)
setup/rubrics/*.md          per-model iron-gate rubrics (Coordinator appends ## Failures)
kitchen-critic-log.jsonl    Critic adversarial verdicts (append-only)
```

---

## 4. The Forager subsystem (the core new build)

### 4a. Data Forager — refuel the candlesticks, audit everything in

**Job:** keep the gym's *spot* fuel deep and fresh, add free enrichment, and be brutally honest about option data.

**Free spot/index sources (ranked, all $0):**

| Rank | Source | Use | Free limit / depth | Notes |
|---|---|---|---|---|
| 1 | **Alpha Vantage** | SPY/VIX 1–60min + daily backfill | 25 req/day, ~2 yr intraday via `month=YYYY-MM` slices | SIP-aggregated; ration the 25/day for slow deep backfill |
| 2 | **Alpaca IEX** *(already wired)* | SPY 1-min forward | generous; free=IEX feed, `end`≥15min old | thinner prints than SIP but SPY is liquid enough |
| 3 | **FRED** | VIX (`VIXCLS`), rates (`DGS1MO`,`SOFR`) | free key, decades | authoritative VIX + BS inputs |
| 4 | **Stooq** | SPY/index cross-check | 5-min ≈ last ~1 month; daily decades | referee source for reconciliation |
| 5 | **FirstRate / Kaggle dumps** | frozen fixtures | ~2-week samples / static | one-time fixtures, not a feed |

**Enrichment (free):** VIX term structure / futures curve (`vix_utils` PyPI → CBOE CFE; contango/backwardation is a strong 0DTE regime feature, ties to Lesson C5 "VIX *character* > level"), put/call ratio (CBOE CSVs), economic calendar (FRED release API for the *value* + Finnhub for the forward *schedule* → feeds existing `news.json`).

**The data-quality auditor (gate before any write).** A new module `backtest/tools/data_auditor.py` runs the full checklist; **failures route to `backtest/data/_quarantine/` and never enter `backtest/data/` or `data-versions.jsonl`.** Checklist (thresholds are starting points):

- **Schema/structure:** required cols present + typed; per-RTH-day bar count == 78 (5-min) — `>1` bar deviation WARN, `>5%` REJECT day; timestamps monotonic, unique, evenly spaced.
- **Timezone/DST (this repo's #1 historical bug class, Lessons C6):** assert source tz explicitly (where does the 09:30 ET open bar land?); verify the UTC offset *flips by 1h* across Mar/Nov DST boundaries; localize naive ET as `America/New_York` **never UTC**; round-trip `localize→to_utc→back == original`; first/last daily bar == 09:30 / 16:00 ET.
- **OHLC integrity:** `low ≤ {open,close} ≤ high`, `high ≥ low`, all prices `> 0`; zero-volume on SPY during RTH ⇒ WARN (fabricated bar); bar-to-bar `|Δclose/close| > 10%` non-news ⇒ flag + cross-check; ≥3 identical O=H=L=C runs ⇒ stale/forward-fill flag.
- **Adjustment:** split-discontinuity scan (clean 2×/3× overnight gap w/o news); adjusted vs raw consistency; ex-div gap matches `adjusted` flag.
- **Cross-source reconciliation (strongest single check):** compare two independent free sources on overlapping dates; SPY 5-min close median abs %diff `>0.1%` investigate, `>0.5%` reject suspect window; VIX close vs FRED `VIXCLS` must match ~0.01.
- **Survivorship/look-ahead:** as-of filtering (`≤ t` and bar closed); point-in-time adjustment; no silent strike-drop in historical chains; every row tagged `source`, `fetched_at`, `is_synthetic`.
- **Audit-the-output discipline (Lesson C7):** emit a scorecard artifact (rows ingested/rejected, per-check pass/fail, cross-source diff stats); **fail loud** (non-zero exit + STATUS.md flag) on REJECT — never log "OK" off an exit code; verify new files git-tracked.

#### The option-data design (RC-2, corrected by the broker-route workflow 2026-06-24)

The instinct to buy a cheap option feed turns out to be **unnecessary** — a 7-route, ToS-and-ban-verified workflow (WeBull/Tradier/IBKR/Tastytrade/Schwab/Alpaca/Databento) found the gym's option-data need is already met for **$0**:

- **Alpaca's free tier already returns true-OPRA historical option BARS.** The "indicative" label degrades only the most-recent-15-min of *live* quotes — **not** the recorded 5-min history that `expand_opra_cache.py` already writes. So the gym's WR authority is already true-OPRA-grade at $0 (Lesson C1 stands, and is *better* than the rough draft assumed).
- **Option history is hard-capped at ~Feb-2024 on EVERY vendor** (Alpaca, ThetaData, Databento) — that's OPRA's retail-availability floor, **not** a paywall. The repo's window sits fully inside it, so **$40/mo ThetaData buys zero extra depth.**
- **WeBull: don't tap it.** Its API options-data price is unpublished (the $2.99 app OPRA is display-only, doesn't cross to the API), fidelity is a derived best-bid/ask (no better than Alpaca), the official MCP omits options, eligibility adds a $100 net-value floor + trading-history screen, and the **unofficial `tedchou12` lib = HIGH ban risk on a funded real-money account.** No gain over the free Alpaca path. (Same conclusion ruled out Tradier/Tastytrade/Schwab for *warehousing* — their non-pro/OPRA-subscriber terms disfavor archiving a reusable dataset, and a public repo makes any stored quote a clear breach.)

**So the layered design simplifies to:**

1. **Real layer (authority) = the existing free Alpaca `expand_opra_cache.py` path.** True-OPRA 5-min bars, Feb-2024-forward (the universal floor), $0, already wired (MCP + REST + `.mcp.json` loader). Coverage already tracked by **`backtest/tools/data_coverage_manifest.py`** (flags DEGRADED when the option cache lags SPY bars → `automation/state/data-coverage.json`, which the conductor/health-beacon read). The Data Forager's option job is just: keep that cache fresh + run the coverage manifest.
2. **Synthetic BS layer (`is_synthetic`, ranking-only)** — *deprioritized*. Its only unique value was pre-Feb-2024 history that **no vendor sells anyway**, so it's now just cheap candidate-funnel widening, never WR (Lesson C1 hard-wall still enforced).
3. **Paid levers (off by default, §9):** $99/mo Alpaca `feed=opra` ONLY if the *live engine* ever needs true sub-15-min NBBO (a 1-line flip, engine not gym — and confirm the OPRA "Non-Display Use" entitlement first, since an always-on engine on real-time OPRA is a separate license class); Databento ~$20-100 one-off only if a future need ever exceeds the Feb-2024 floor.

> **`data_auditor.py` vs `data_coverage_manifest.py`:** different jobs — coverage manifest answers *"do we have enough / fresh data?"* (and feeds the health beacon); the new `data_auditor.py` answers *"is this newly-foraged file clean enough to trust?"* (row-level OHLC/tz/integrity gate before ingestion). The Data Forager runs both: auditor on intake, manifest on freshness.

### 4b. Strategy Forager — harvest ideas, quarantine ruthlessly

**Sanctioned sources only (legal + extractable + machine-parseable first):**

| Priority | Source | Channel (sanctioned) | S/N for 0DTE-intraday |
|---|---|---|---|
| 1 | **arXiv q-fin** (TR/ST/CP) | OAI-PMH bulk metadata (CC0); single-PDF fetch ≤1 req/3s | Med — cleanest methodology; filter hard for intraday/options |
| 2 | **Quantpedia / QuantConnect** | free screener (≈70) + QC public Lean algos (Apache-2.0 engine) | Med — structured rules + built-in OOS replication |
| 3 | **GitHub** (`awesome-quant`, `awesome-systematic-trading`, vectorbt/backtrader repos) | REST/GraphQL API, capture SPDX license per repo | Med — code + READMEs; GPL ⇒ idea-only, don't vendor |
| 4 | **Stack Exchange Quant.SE** | API + Data Dump (CC BY-SA, attribute) | Low for signals, **High for audit knowledge** |
| 5 | **Reddit / TradingView / blogs** | PRAW free tier / RSS only — **never crawl TradingView (ToS forbids)** | **Low** — injection-prone *hypothesis seeds only* |

**Intake schema** — one append-only JSONL record per idea (`strategy-intake.jsonl`), fields chosen so the audit can gate on the record alone. Load-bearing fields: `applies_to_0dte_options` (defaults `unknown`, must be *proven* `yes`), `license`/`attribution_required` (legal gate), and the three dedup keys (`canonical_hash`, `minhash_sig`, `embedding_id`).

```jsonc
{
  "intake_id": "WEB-2026-0624-0007",
  "ingested_utc": "2026-06-24T21:14:03Z",
  "title": "Intraday opening-range reversion, index ETF",
  "canonical_hash": "sha256(normalized rules)",     // exact-dup
  "minhash_sig": [ ... ],                            // near-dup (13-token shingles)
  "embedding_id": "vec_4831",                        // semantic-dup
  "rules_raw": "verbatim quoted text",
  "rules_normalized": { "instrument_claimed": "SPY ETF", "side": "...", "entry_trigger": "...", "exit_rule": "...", "stop": "...", "session": "RTH", "holding_horizon": "minutes-hours", "params": {...}, "indicators": [...] },
  "claimed_edge": { "metric": "sharpe", "value": 1.8, "sample": "2010-2024", "oos_shown": false, "costs_modeled": false },
  "source": { "name": "arXiv", "url": "...", "fetched_via": "OAI-PMH", "doc_type": "paper", "author": "...", "published": "2025-01-12" },
  "license": "CC0|MIT|Apache-2.0|GPL|CC-BY-SA|all-rights-reserved|unknown",
  "attribution_required": true, "robots_ok": true, "tos_ok": true,
  "credibility_score": null,
  "asset_class": "equity_etf|options|futures|...", "signal_layer": "price_structure|flow|...", "regime_claimed": "trend|range|highvol|lowvol|unspecified",
  "as_of_correct": null, "applies_to_0dte_options": "unknown", "option_translation_risk": ["theta","delta","stop_misfire","liquidity"],
  "stage": "intake", "verdict": null, "reject_reason": null, "dup_of": null, "promoted_to_gym_id": null,
  "audit_log": []   // one entry per stage: {stage, score, rationale}
}
```

**The 6-stage quarantine pipeline (cheapest-first; nothing reaches gym compute before Stage 5 passes):**

- **Stage 0 — Intake & legality + injection defense.** Snapshot robots.txt + ToS-date + license at fetch time. Reject if ToS forbids automated access (TradingView), or auth-walled. **Treat the page as untrusted (OWASP-LLM 2026):** strip/flag embedded instruction-like text *before* any LLM reads it — a "strategy" page must not be able to prompt-inject the forager. The forager LLM only *extracts into the schema*; it never executes page text.
- **Stage 1 — Structural extraction & completeness.** Parse `rules_raw → rules_normalized`. **Reject if not mechanically reproducible** (no defined entry/exit/stop, or "discretionary judgment"). Kills the bulk of forum/Pine noise instantly.
- **Stage 2 — Credibility score** ∈ [0,1]: source tier (peer-reviewed > QC-with-OOS > GitHub-with-tests > Composer/SE > Reddit/TV/blog); OOS shown? costs modeled? sample length? recency-vs-decay. **Apply the McLean–Pontiff haircut** (−26% OOS / −58% post-pub) to any *claimed* number and store the discounted edge. `<0.35` ⇒ REJECT/PARK without burning compute.
- **Stage 3 — Dedup (three-tier):** exact `canonical_hash`; near-dup MinHash+LSH (Jaccard ≥ ~0.7); semantic embedding cluster. **If it lands in a cluster the gym already killed, auto-reject with the prior verdict** ("we tested double_top on real fills — DEAD," Lesson C4/edge-hunt). *Rejections are assets:* this is where the gym's own history compounds.
- **Stage 4 — Data-snooping / DSR screen (no full backtest yet).** Increment the family-wise **trial counter `N`**. The **Deflated Sharpe** hurdle `SR₀` *grows with `N`* (Bailey & López de Prado 2014 — DSR = Probabilistic Sharpe with a multiple-testing-adjusted hurdle). Record the DSR bar the idea must later clear; an idea harvested as forager-trial #800 faces a higher bar than #5. Reject if the *post-haircut* claimed Sharpe can't beat `SR₀(N)`. Flag param-family size (White's Reality Check / Hansen's SPA territory — best-in-sample of a sweep is a false discovery against the joint null). **Park, don't promote**, when borderline.
- **Stage 5 — 0DTE-applicability gate (the C3 gate — the most important).** A surviving idea is at best a *SPY-underlying* signal. Mandatory translation check: re-express entry/exit on **option P&L** with realistic theta/delta and *this engine's* stop logic (chart-stop-primary, −50% cap). Daily/swing-horizon underlying edge ⇒ REJECT for 0DTE. Too-low delta / signal slower than theta burn / stops that misfire on premium ⇒ `applies_to_0dte_options="no"` ⇒ REJECT. Graduating ideas must be framed as *a hypothesis to be tested against a random-entry null on real fills* (C3/L172 — beat the null MAX).
- **Stage 6 — PROMOTE or REJECT.** PROMOTE ⇒ write a DRAFT candidate to `strategy/candidates/` *with provenance + the DSR hurdle it must beat*, then hand off to the **existing** real-fills + OOS + anchor-no-regression + A/B-scorecard rails (the repo's auto-ratify gate). **The forager never auto-ships; it only feeds the gym.** REJECT/PARK ⇒ logged so Stage 3 auto-kills its future twins.

---

## 5. Self-evolution loop (kept, hardened)

The differentiator from the rough draft survives, with guards:

```
1. Coder generates a candidate
2. Validator checks DT-agreement (does it align with how the real heartbeat fires?)
3. Critic panel (2 models) does adversarial review
4. A Critic finds a hallucination class in Coder's output
   → Coordinator appends a rule to setup/rubrics/<coder-model>.md  ## Failures
5. Next time Coder fires it reads its updated rubric → can't repeat that mistake
```

Each rubric has an auto-growing `## Failures` section (per Plan A). The Coordinator tracks each model's **Critic approval rate over time** and routes more work to the best model per task type; a model whose approval rate stays low after many rounds = an un-fixable hallucination class → demote it in `model-roster.json`, try another. **Guards:** rubric edits are append-only (never delete a hardening rule); a rubric change that *drops* approval rate is auto-reverted (the rubric is versioned in git); the Coordinator may never edit a `LIVE_DOCTRINE_DENYLIST` file (`heartbeat.md`, `params*.json`, `CLAUDE.md`) — Rule 9.

---

## 6. Edge cases & failure modes (the "think through scenarios" ask)

| # | Failure mode | Trigger | Guard |
|---|---|---|---|
| **LLM-1** | Silent model deprecation | `:free` tag pulled (Kimi, 2026-06-13) → 404 "no endpoints" | `model-roster.json` + daily liveness probe auto-demotes dead ids; never hardcode `:free`; existing ladder already fails over |
| **LLM-2** | Free-tier exhaustion mid-day | one lane (e.g. OpenRouter 50/day) burned | lane pool across providers (§7.2); quota-aware routing; cross-provider failover on 429; **terminal local floor never rate-limits** (§7.3) — the kitchen can't fully go dark |
| **LLM-2b** | Multi-account ban | making 3 OpenRouter accounts to dodge limits | **forbidden** — ToS §7 violation (auto-terminate + forfeit credits) AND ineffective (global per-person governance). Multiply *providers* + local floor instead (§7.1) |
| **LLM-3** | Privacy leak to training tiers | Account/edge text sent to Gemini/Mistral free (they train on inputs) | **Routing rule** + structural fix: `privacy:"sensitive"` roles restricted to no-train lanes (Groq/Cerebras/NVIDIA) or the **local floor**; only public scraped pages → Gemini/Mistral |
| **LLM-4** | Reasoning runaway → timeout/token burn | R1/Nemotron-reasoning won't stop `<think>` | hard `max_tokens` + client timeout; structured-output role uses a **non-reasoning** model (Qwen-Coder/Llama) |
| **LLM-5** | Invalid JSON from structured role | flaky free-tier JSON-mode | schema-validate every structured response at the boundary; repair-or-retry; one retry then route to fallback model |
| **LLM-6** | Prompt injection from scraped page | a "strategy" page embeds instructions (OWASP-LLM 2026; 5–10 poisoned docs skew a RAG) | Stage-0 sanitization; forager extracts into fixed schema only; page text is data, never instructions |
| **DATA-1** | Bad data poisons the gym | vendor outage, bad ticks, mis-adjusted split | `data_auditor.py` gate → `_quarantine/`; failed data never written to `backtest/data/` or `data-versions.jsonl` |
| **DATA-2** | Timezone/DST bug (repo's #1 bug class) | UTC-vs-ET-naive confusion, constant-offset source | explicit tz assert + DST-flip test + round-trip localize check (§4a) |
| **DATA-3** | Synthetic price sets a win-rate | BS-reconstructed row leaks into `simulator_real` | `is_synthetic` hard wall; WR computation rejects any synthetic row; CI test asserts it |
| **DATA-4** | Silent source rot | yfinance 429s / Yahoo blacklist; AV 25/day exhausted | each source has a liveness check + cross-source referee; forage-log records every attempt; STATUS.md flag on sustained failure |
| **DATA-5** | Reproducibility break | new data changes a frozen historical run_id | append-only `data-versions.jsonl` + `REGISTRY.jsonl`; historical runs stay frozen (Karpathy repro, OP-11); new data = new run_id |
| **STRAT-1** | False-discovery flood | forager harvests thousands of overfit ideas | DSR hurdle grows with `N` (Stage 4); credibility floor; **park-not-promote** default |
| **STRAT-2** | Re-testing a dead idea | a twin of an already-killed strategy | 3-tier dedup auto-rejects with the prior verdict (Stage 3) — the compounding asset |
| **STRAT-3** | Underlying edge ≠ option edge | a SPY price signal that theta/delta kills | mandatory 0DTE-translation gate (Stage 5); beat-the-null requirement |
| **STRAT-4** | Legal exposure | scraping auth-walled / ToS-forbidden content | sanctioned APIs only; honor robots.txt; no TradingView crawl; no login-walled scrape; capture license per item; EU AI-Act TDM opt-out (in force 2 Aug 2026) |
| **SYS-1** | Shared-state race | two roles write `kitchen-swarm-state.json` | single-writer (Coordinator) atomic tmp→rename; everyone else append-only event logs |
| **SYS-2** | Operator lockout | a guard blocks J's interactive Claude session | **fail-open always** (OP-25/OP-32 scar); no swarm process may kill/block J's session or starve the heartbeat |
| **SYS-3** | Silent success = silent failure | a forage/cook/audit finishes with no logged outcome | every fire writes an outcome to its log OR a flag to `STATUS.md ## Known broken` (OP-25) |
| **SYS-4** | Unbounded append-only growth | `strategy-intake.jsonl` / `forage-log.jsonl` balloon | retention cap per producer → CONSOLIDATION (prune/dedupe/archive) on cap hit (OP-22); learned from the watcher-obs 5.1MB RED |
| **SYS-5** | Window flash / cost creep | new task spawns a console window or burns paid tokens | wscript→pythonw chain (`fix-powershell-task-flash.ps1` pattern); $0 free-tier only; paid lever off by default (§9); register every task in `SCHEDULED-TASKS.md` with TZ-correct (Mountain) schedule |
| **SYS-6** | Market-hours contention | heavy swarm fan-out 09:30–15:55 ET starves heartbeat (shared Max pool) | foragers/swarm are after-hours-weighted; the OpenRouter/free-provider swarm is *separate* from the Max pool, but any interactive driving stays out of market hours |

---

## 7. The Super-Free Throughput Engine

The binding constraint is requests/day, not model quality. This is where "super free" is won. The design is a **lane pool**: every `(provider, key, model)` is a *lane* with its own independent quota bucket, reset clock, privacy class, and health state. A quota-aware router spreads work across all lanes and **terminates at a local model floor that never rate-limits**. The result, entirely within every provider's ToS and at $0: **~15K+ requests/day + ~3B tokens/month + a 1M-context lane + an unlimited local floor.**

### 7.1 The multi-account trap — do NOT make 3 OpenRouter accounts

Verified against primary sources (June 2026), the "3 emails → 3 keys" idea fails twice:
- **It's a bannable ToS violation.** OpenRouter [Terms §7](https://openrouter.ai/terms) prohibits "create … multiple accounts as a single user, for purposes of bypassing or circumventing use limits"; [§9](https://openrouter.ai/terms): violation auto-terminates access + forfeits credits. This is the FOMC credit-cliff "go dark" scar, self-inflicted.
- **It doesn't even work.** OpenRouter [rate-limit docs](https://openrouter.ai/docs/api/reference/limits) verbatim: *"Making additional accounts or API keys will not affect your rate limits, as we govern capacity globally."* They govern free capacity per-person, not per-account. 3 emails ≠ 3 buckets.
- **Multiple keys under one account** = fine for hygiene (per-env caps, separate logs) but **share** the one account limit. Not a multiplier.

**The legitimate multiplier is different *providers*** (and the local floor). Don't multi-account anywhere to dodge limits — the local floor (§7.3) makes it unnecessary.

### 7.2 The lane pool — independent free buckets across providers

Each provider below is its own additive free bucket, explicitly ToS-legal, one account each:

| Lane | Free budget (verify live — limits shift) | Big ctx? | Trains on input? | Best for |
|---|---|---|---|---|
| **Groq** — `llama-3.1-8b-instant` | **~14,400 req/day** (!), 30 RPM, fast (300+ tok/s) | ~128K | No | high-volume classification / routing / per-tick labeling |
| **Cerebras** — Qwen3-32B / Llama-4-Scout | **1M tokens/day**, 30 RPM, **8K ctx cap** | No (8K) | No | high-volume *short* reasoning/validation |
| **Google AI Studio** — `gemini-3-flash-lite` | ~500 req/day, 5–15 RPM, **1M ctx** | **Yes (1M)** | **Yes** | the **forager** reading scraped pages — *public data only* |
| **Mistral La Plateforme** | **~1B tokens/month**, 1 req/s | up to 128K | **Yes (free=opt-in)** | ideation / codegen on *public* context |
| **OpenRouter `:free`** | 50 req/day → **1,000/day after one-time $10** (lever, off) | up to 1M | per-model | model *variety* (DeepSeek-R1, Qwen3-Coder, Nemotron) + single-pane router |
| **NVIDIA NIM** (build.nvidia.com) | ~1,000 credits (5,000 on request), 40 RPM | model | No | overflow / no-train lane |
| **Cloudflare Workers AI** | 10,000 neurons/day (resets 00:00 UTC) | model | No | overflow |
| **Cohere / GitHub Models** | 1,000 req/mo · ~50–150 req/day | small | varies | overflow |
| **LOCAL (Ollama)** | **∞ — no quota, no ToS, no rate limit** | model | **No (fully private)** | the never-dark floor + the *sensitive-prompt* lane (§7.3) |

### 7.3 The local floor — the kitchen never goes dark (and never leaks)

The single most important "super free" idea. Every API lane can be exhausted, throttled, deprecated, or silently degraded. **A local model has no quota, no ToS, no rate limit, and full privacy.** It terminates every fallback ladder so the kitchen is *never* fully blocked — directly retiring the FOMC "go dark" failure class.

**The rig (confirmed 2026-06-24):** NVIDIA **RTX 5080 (16GB VRAM)** + Ryzen 7 **9800X3D** (8-core) + **31GB RAM**. This is strong enough that local is not just a floor — it's a capable *primary* lane for a large share of the kitchen at zero quota.

- **Wiring is one line.** Ollama serves an OpenAI-compatible endpoint at `http://localhost:11434/v1/`. All our callers already speak OpenAI-compatible (the OpenRouter client), so the local lane is just `base_url="http://localhost:11434/v1/"`, `api_key="ollama"`. No code changes — the ladder simply ends in `…→localhost`.
- **Model picks for 16GB (Q4_K_M):**
  - **Qwen3 14B** (~10GB) — the fast local daily-driver: best small-class tool-calling + JSON in 2026, fully GPU-resident, high tok/s on the 5080. *Default local floor.*
  - **Qwen3-Coder 30B-A3B** (MoE, ~3B active; ~18GB Q4 → fits with light CPU offload into the 31GB RAM, or Q3_K_M ~14GB fully on-GPU) — the local **Coder** lane: reasons ≈30B at ~7B speed, 256K ctx. Pull as a second model.
  - Keep a tiny **Qwen3 4B** pulled as the instant-fallback if the 14B is busy.
- **Privacy dividend:** because it's local + no-train, the **sensitive-prompt lane** routes here — anything touching account state, keys, or proprietary edge logic runs locally, never on a training-on-input free API. (Resolves §6 LLM-3 structurally.)
- **Market-hours courtesy:** local inference shares the box with the live engine. Throttle/queue heavy local jobs during 09:30–15:55 ET so they never contend with the heartbeat; the GPU is mostly idle for the trading workload, so after-hours it's wide open (SYS-6).
- **Setup:** install Ollama (Windows native), `ollama pull qwen3:14b` + `qwen3-coder:30b-a3b` + `qwen3:4b`, smoke-test the endpoint. *(Not yet installed — first Phase-0 action.)*

### 7.4 Outside-the-box tactics (stretch every free token)

1. **Prompt caching = repeats are free.** Groq excludes cached tokens from rate limits (+50% discount); Gemini 2.5/3.x implicit-cache gives 90% off cached tokens. Design **every** kitchen prompt as `[stable preamble][variable tail]` so the invariant strategy-context block caches — repeats stop burning quota.
2. **Batch to cut request count.** Request-metered lanes (Groq/OpenRouter/Gemini) meter *requests*, not just tokens. Pack N items into one call ("classify these 20 setups → JSON array") → 1 request, not 20. Groq's 14,400 req/day × 20-batch ≈ **288K classifications/day** free.
3. **Schedule around reset clocks.** OpenRouter + Cloudflare reset **00:00 UTC**; Gemini resets **midnight Pacific**; Groq/Cerebras roll continuously. A reset-aware scheduler fires the biggest backlog right after each lane refills, chaining fresh buckets across the 24h day.
4. **Kaggle for batch, not hosting.** Kaggle's ~30 GPU-h/week is great for heavy *batch* R&D (scoring a big candidate matrix overnight). **Not** an always-on endpoint — Colab ToS explicitly bans serving/tunnels, and Kaggle sessions time out. The local floor is the ToS-clean "always-on" answer.
5. **Quota-aware routing** (the router's core logic): track each lane's remaining budget + reset clock + health; prefer the cheapest *capable* lane with budget; on 429 cool that lane and failover (never retry-storm one endpoint); degrade gracefully to local when all APIs are tapped.

### 7.5 Lane → role assignment

| Role | Primary lane | Why |
|---|---|---|
| High-volume classification / routing | **Groq** `llama-3.1-8b-instant` | 14,400 req/day + 300+ tok/s |
| Structured JSON / code | **Cerebras** Qwen3-Coder *or* **local** Qwen3 | Qwen3 = most reliable JSON; local = private + unlimited |
| Reasoning / ideation | **OpenRouter** `deepseek-r1:free` / Nemotron-ultra | strongest free reasoners |
| Adversarial critique (panel) | **OpenRouter** DeepSeek + **Groq/Cerebras** Qwen3 | *different families* = real diversity |
| Forager (1M-ctx page reading) | **Gemini-3-Flash-Lite** (public pages only) | only practical free 1M-ctx lane |
| Sensitive / fallback / never-dark | **LOCAL** Qwen3 | no quota, no ToS, fully private |

---

## 8. Constraints (non-negotiable)

Inherited from the rough draft, plus the new guards:

- **$0 incremental cost.** Free-tier models + free data + a local model only. The one-time $10 OpenRouter top-up and the ~$40/mo option-data feed are **flagged levers, off by default** (§9).
- **No multi-accounting to dodge limits.** Never create extra accounts on any provider to circumvent rate limits (OpenRouter ToS §7 = bannable; ineffective anyway). Multiply *providers* + the local floor (§7).
- **The local floor guarantees the kitchen never fully goes dark** — a local Ollama lane terminates every fallback ladder (no quota, no ToS, fully private).
- **No model ever touches** `heartbeat.md`, `params*.json`, `decisions.jsonl`, `current-position*.json`, `CLAUDE.md` (the `LIVE_DOCTRINE_DENYLIST`).
- **No model ever places orders.** No Alpaca order tools in any swarm process.
- **All outputs land in** `strategy/candidates/` or `analysis/` or `backtest/data/` (post-audit) — read-only on production state.
- **Privacy routing:** sensitive context → verified no-train lanes (Groq/Cerebras/NVIDIA) or the **local floor** only, + enable OpenRouter's account no-train/ZDR toggle; public scraped pages → Gemini/Mistral OK.
- **Untrusted-input discipline:** scraped pages are data, never instructions; sanitize before any LLM read.
- **Fail-open always:** no swarm guard may block J's interactive session or starve the heartbeat (OP-25/OP-32).
- **Silent success = silent failure:** every fire logs an outcome or flags `STATUS.md`.
- **Retention caps + consolidation** on every append-only producer (OP-22).
- **Synthetic data is ranking-only**, hard-walled out of WR (Lesson C1).
- **The forager never auto-ships** an edge — it feeds the gym's existing ratify rails.

---

## 9. Decisions taken (and the lever to flip each)

Per standing direction ("$0, don't ask, just build"), these are **decided**, not open questions. Each notes the lever if J ever wants to change it.

1. **$0 strict; throughput comes from providers + local floor, not multi-accounting.** The 3-OpenRouter-account idea is rejected (ToS-bannable + ineffective, §7.1). Lever: a one-time **$10 OpenRouter top-up** lifts that *one* lane 50→1,000 req/day — highest-ROI $10 in the system, but *off by default* per the standing "$0 research" directive (the lane pool + local floor already clear the throughput need without it).
2. **Option data = free Alpaca true-OPRA bars (VERIFIED 2026-06-24); no vendor, no spend.** The broker-route workflow confirmed Alpaca's free historical option bars ARE true-OPRA (only *live* sub-15-min quotes are degraded), and option history is capped ~Feb-2024 on *every* vendor — so ThetaData ($40/mo) and WeBull buy nothing the gym needs. **WeBull rejected** (unpublished API price, derived fidelity, HIGH ban-risk on a funded account — do not point the unofficial lib at live capital). Lever (off): $99/mo Alpaca `feed=opra` for the *live engine's* sub-15-min NBBO only, or Databento ~$20-100 one-off if a need ever exceeds the Feb-2024 floor.
3. **Forager weighted after-hours.** It can run 24/7 (separate free pools), but heavy interactive *driving* stays out of 09:30–15:55 ET (heartbeat shares the Max pool). Lever: none — load-bearing discipline.
4. **Strategy Forager promotes to `strategy/candidates/` only**, never to the leaderboard or live. Lever: none — this is the OP-11 eval-first gate.
5. **Local Ollama model is the never-dark floor + the sensitive-prompt lane.** Decided in. Hardware resolved (RTX 5080 16GB / 9800X3D / 31GB) → **Qwen3 14B** default + Qwen3-Coder 30B-A3B for the coder role. No open ask. Lever: none — this is the structural fix for the FOMC "go dark" + the privacy class.

---

## 10. Phased roadmap (dependency-ordered, each with a definition-of-done)

> **Prerequisite:** Plan A complete (Qwen + DeepSeek-R1 rubrics hardened in `setup/rubrics/`, `--model` flag live). Phases 1–2 can start in parallel with Plan A's hardening since they reuse the same primitives.

### Phase 0 — Foundations: the lane pool + local floor (build first; unblocks everything)
- `automation/state/model-roster.json` (ordered lanes per role, ending in the local floor) + a `resolve_lane(role)` helper + daily liveness probe task.
- **Install Ollama + `ollama pull qwen3:14b` (+ `qwen3-coder:30b-a3b`, `qwen3:4b`)** and smoke-test the OpenAI-compatible endpoint at `localhost:11434/v1/`. (Rig confirmed: RTX 5080 16GB / 9800X3D / 31GB.)
- `swarm_client.py` — a thin lane-aware wrapper over `call_minimax()` that adds: **multi-provider routing** (OpenRouter/Groq/Cerebras/Gemini/Mistral/NVIDIA + `ollama` base_url swap), **quota-aware lane selection** (per-lane token-bucket + reset-clock + health), **privacy routing** (sensitive → no-train/local only), **cache-friendly prompt shaping** (`[stable preamble][variable tail]`), **batch helper** (pack N items → 1 call), and **schema-validate-or-retry** for structured roles.
- **DoD:** every role resolves a live lane; forcing 429 on every API lane **falls through to the local floor and still returns** (the never-dark guarantee); a forced-404 auto-rotates + flags STATUS.md; a sensitive-tagged prompt never routes to a training-on-input lane (unit-tested); structured-role JSON validates or retries once then fails over.

### Phase 1 — Coordination wiring (mostly compose, not build)
- Add `task_type` → role routing to `kitchen_daemon` dispatch (reuse `_pick_next_task` + `_build_effective_ladder`).
- Add `kitchen-swarm-state.json` (single-writer, atomic) + Coordinator read/write helpers (workloads, approval rates, coordination log).
- Upgrade `KitchenSeeder` to call Strategist (ideation) and `KitchenReviewer` to call the 2-model Critic panel — both via `swarm_consult.consult()`.
- **DoD:** a task flows seeder→queue→correct-model→candidate→critic with state visible in `kitchen-swarm-state.json`; no shared-state race under concurrent fires.

### Phase 2 — Data Forager
- `backtest/tools/data_auditor.py` (the full §4a checklist; quarantine + scorecard + fail-loud).
- Extend `backtest/tools/fetch_data.py` into a multi-source forager (Alpha Vantage + Alpaca IEX + Stooq + FRED) writing contract-conforming CSVs *only after* the auditor passes; append `data-versions.jsonl`.
- `backtest/tools/bs_reconstruct.py` synthetic layer (`is_synthetic=true`, WR-walled) + a CI test that asserts synthetic rows can't reach `simulator_real`.
- Wire VIX-term-structure + put/call + FRED econ-calendar enrichment into `news.json`.
- **DoD:** a fresh SPY/VIX backfill passes the auditor, lands versioned, and a backtest run picks it up with a new `run_id`; a deliberately corrupted file is quarantined + flagged, never written; the WR-wall test is green.

### Phase 3 — Strategy Forager
- `forage_strategies.py`: sanctioned-API harvesters (arXiv OAI-PMH, GitHub API, Quantpedia/QC) with robots/ToS/license capture + Stage-0 injection sanitization.
- `strategy_quarantine.py`: the 6-stage pipeline (extraction → credibility+haircut → 3-tier dedup → DSR-with-`N` → 0DTE-translation gate → promote), writing `strategy-intake.jsonl` + DRAFT candidates with provenance.
- The trial counter `N` + DSR-hurdle bookkeeping; the dedup corpus seeded with the gym's already-killed ideas (double_top, etc.).
- **DoD:** harvest a known arXiv intraday-momentum paper → it's extracted, scored, dedup-checked, DSR-gated, 0DTE-translation-checked, and either promoted with a stated DSR bar or rejected with a logged reason; a re-harvest of the same idea auto-dedups; a known-dead idea auto-rejects with the prior verdict.

### Phase 4 — Self-improving swarm
- Coordinator rubric auto-update (`## Failures` append on Critic findings) + approval-rate routing + auto-revert on approval-rate regression.
- New-free-model onboarding playbook (clone rubric template → Plan-A hardening → add to roster).
- **DoD:** a seeded Coder hallucination is caught by the Critic, a rule lands in the Coder rubric, and the same hallucination doesn't recur on the next fire; a rubric edit that lowers approval rate auto-reverts.

### Phase 5 — Consolidation & long-run hygiene
- Retention caps + consolidation jobs for `strategy-intake.jsonl`, `forage-log.jsonl`, `data-versions.jsonl`.
- `SCHEDULED-TASKS.md` registry entries (TZ-correct Mountain, wscript→pythonw, no window flash) for the forager + liveness probe.
- Update `markdown/infra/KITCHEN-SPEC.md` with the swarm + forager architecture.
- **DoD:** every new append-only file has a cap + consolidation; every new scheduled task is registered, flash-free, and self-healing via a keepalive; the audit script passes.

---

## 11. Files to create / modify

```
# Create
automation/state/model-roster.json              role→ordered-lanes map (+ local floor) + dead-id graveyard
automation/state/kitchen-swarm-state.json        Coordinator single-writer state
automation/state/strategy-intake.jsonl           Strategy Forager intake + quarantine
automation/state/forage-log.jsonl                every forage attempt + outcome
setup/scripts/swarm_client.py                    lane pool (multi-provider + local Ollama floor) + quota/privacy/cache/batch routing + JSON-validate, over call_minimax()
backtest/tools/data_auditor.py                   the §4a data-quality gate (+ _quarantine/)
backtest/tools/bs_reconstruct.py                 synthetic option layer (is_synthetic, WR-walled)
setup/scripts/forage_strategies.py               sanctioned-API harvesters + Stage-0 sanitization
setup/scripts/strategy_quarantine.py             6-stage intake pipeline + DSR/N bookkeeping
kitchen-critic-log.jsonl                         Critic adversarial verdicts

# Modify
setup/scripts/kitchen_daemon.py                  task_type→role routing; swarm-state R/W
setup/scripts/kitchen_seeder.py                  Strategist ideation via swarm_consult
setup/scripts/kitchen_reviewer.py                2-model Critic panel via swarm_consult
backtest/tools/fetch_data.py                     multi-source forager + auditor gate + versioning
automation/state/SCHEDULED-TASKS.md              register forager + liveness-probe tasks
markdown/infra/KITCHEN-SPEC.md                   document swarm + forager architecture
setup/rubrics/*.md                               per-role iron-gate rubrics (from Plan A; ## Failures auto-grow)
```

---

## 12. Appendix — research sources (June 2026)

**Free-model landscape:** OpenRouter [rate-limit docs](https://openrouter.ai/docs/api/reference/limits) · [free-models collection](https://openrouter.ai/collections/free-models) · ["keep your agent running when models disappear"](https://openrouter.ai/blog/tutorials/keep-your-agent-running-when-models-disappear/) · [provider-logging/privacy](https://openrouter.ai/docs/guides/privacy/provider-logging) · [Google AI rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) · [Groq limits](https://console.groq.com/docs/rate-limits) · [Cerebras limits](https://inference-docs.cerebras.ai/support/rate-limits) · [Mistral tiers](https://docs.mistral.ai/admin/user-management-finops/tier) · [cheahjs/free-llm-api-resources](https://github.com/cheahjs/free-llm-api-resources).

**Free data sources:** [Alpaca market-data](https://docs.alpaca.markets/us/docs/about-market-data-api) + [historical options](https://docs.alpaca.markets/us/docs/historical-option-data) · [Alpha Vantage docs](https://www.alphavantage.co/documentation/) · [Polygon/Massive pricing](https://polygon.io/pricing) · [Tiingo IEX](https://www.tiingo.com/documentation/iex) · [Stooq](https://stooq.com/db/h/) · [yfinance rate-limit issue](https://github.com/ranaroussi/yfinance/issues/2128) · [Databento OPRA](https://databento.com/datasets/OPRA.PILLAR) · [ThetaData subscriptions](https://docs.thetadata.us/Articles/Getting-Started/Subscriptions.html) · [FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS) + [API](https://fred.stlouisfed.org/docs/api/fred/) · [vix_utils](https://github.com/dougransom/vix_utils) · [DoltHub options](https://www.dolthub.com/repositories/dolthub/options) · [Kaggle SPY chains 2020-22](https://www.kaggle.com/datasets/kylegraupe/spy-daily-eod-options-quotes-2020-2022).

**Strategy mining + audit:** [Deflated Sharpe Ratio (Bailey & López de Prado)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551) · [PBO / backtest overfitting (LBL)](https://sdm.lbl.gov/oapapers/ssrn-id2507040-bailey.pdf) · [pypbo](https://github.com/esvhd/pypbo) · [White's Reality Check / Hansen SPA (Hsu & Kuan)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=685361) · [Replicating Anomalies (Hou-Xue-Zhang)](https://www.nber.org/system/files/working_papers/w23394/w23394.pdf) · [arXiv q-fin.TR](https://arxiv.org/list/q-fin.TR/recent) + [OAI policy](https://info.arxiv.org/help/oa/index.html) + [API ToU](https://info.arxiv.org/help/api/tou.html) · [awesome-systematic-trading](https://github.com/paperswithbacktest/awesome-systematic-trading) · [Quantpedia free screener](https://quantpedia.com/screener?screener_tab=screener-classic&FilterSubscription=Only+Free) · [QuantConnect/Lean](https://github.com/quantconnect/lean) · [OWASP-LLM Top-10 2026](https://repello.ai/blog/owasp-llm-top-10-2026) · [indirect prompt injection in RAG](https://arxiv.org/pdf/2601.10923) · [web-scraping legality 2026](https://use-apify.com/blog/web-scraping-legal-guide).

---

*Hardened spec — ready to build Phase 0. Prerequisite: Plan A rubric hardening. Two foragers, one audit doctrine: nothing the web brings in touches the gym until it survives the gate.*
