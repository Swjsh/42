# BRAIN-SOVEREIGNTY — cost-proofing and future-proofing the Gamma brain stack

> **The frame (one sentence):** Gamma's *soul* is this repository — CLAUDE.md, the OPs, LESSONS-LEARNED, the personas, the journals, the memories — all plain text that any sufficiently capable model can animate; the *brain* is rented inference, and rented inference is now a commodity with five interchangeable suppliers plus silicon we own. Sovereignty = owning the floor, renting the ceiling, and being able to prove — not claim — that the rig survives any single supplier disappearing.
>
> Provenance: J directive 2026-07-08 ("cost-proof and future-proof this project... fully autonomous agent with a soul"). Verified findings below are from the 2026-07-08 evening session. Market-data claims marked **as-of 2026-07** decay fast — re-verify before acting on prices/endpoints (quarterly brain-market scan, §9).

---

## 0. Threat model — why this doc exists

| Threat | Evidence it's real |
|---|---|
| **Frontier pricing shock / plan rug-pull** | Hypothetical for Anthropic, but the pattern is live everywhere: OpenRouter free lanes for Kimi K2.6, DeepSeek R1/V4-Flash, MiniMax M2.5 all **de-tagged to paid** between 2026-06-13 and 2026-07-01 (`model-roster.json → dead[]`). |
| **"Free" that silently bills** | Groq scar 2026-07-06: ~$9.47 over 12 days on an account assumed $0 (`providers.groq._note`). |
| **Rate-limit starvation** | OpenRouter free tier ~1 RPM/model (`shadow_model_eval.py sleep_s=90`); heartbeat shares the Max pool with interactive sessions (standing CLAUDE.md discipline rule). |
| **Provider outage at market-critical moment** | The hot path's 2 free-model vetoes ride cloud lanes today; roster liveness rotation exists precisely because lanes keep dying. |
| **Single-harness lock-in** | All interactive/agent-layer work currently assumes Claude Code + Max subscription. |

**What is NOT threatened:** the trading hot path. `heartbeat_core.py` is deterministic Python (LLM heartbeats retired) — a total AI-market apocalypse leaves Gamma still seeing, deciding, and placing orders. Sovereignty work is about the *judgment and R&D layers* above it.

---

## 1. What is already sovereign (verified 2026-07-08)

Do not rebuild these; they are the foundation.

- **Tier 0 — reflex (deterministic, $0, owned):** `heartbeat_core.py` + engine_cli + risk_gate + exit manager + beacon. No LLM on the hot path. **Fully sovereign today.**
- **Local floor exists and works:** `automation/state/model-roster.json` defines an `ollama` provider and every kitchen role's lane ladder ends in `ollama/qwen3:14b` ("can never run out of capacity" — FREE-AGENT-PLAN-B-KITCHEN design). Verified end-to-end this session: `swarm_client._call_lane` → `ollama::qwen3:14b` → correct output in 5.8s, call logged to `swarm-calls.jsonl`.
- **Hardware baseline (this box, measured):** RTX 5080 16GB VRAM · Ryzen 7 9800X3D · 32GB RAM · ~148GB free on C:. `qwen3:14b` runs **~86 tok/s** fully on-GPU with ~2.6s cold-load. That is real workhorse speed — faster than most cloud free lanes round-trip.
- **Eval machinery for brain promotion already exists:** `shadow_model_eval.py` replays each day's decisions ledger through candidate models and scores decision-match; promotion bar ≥85% DT over ≥15 days (PROMOTION-SCORECARD). The gym (42 validators) + backtest battery are ready-made brain evals. Most people swap models on vibes; Gamma swaps on scorecards.
- **Spend telemetry:** `swarm_client` logs every call (tokens, lane, elapsed) to `swarm-calls.jsonl`; `spend_summary.py` prices it (post-Groq-scar).

**Integration lesson captured tonight (C7-class):** Qwen3-family are *thinking* models — with `num_predict=200` the model burned the entire budget inside `<think>` and returned an **empty string with no error**. Silent-failure shape. Fix: `"think": false` on Ollama native API (or strip-think + big `max_tokens` on the /v1 endpoint). Any lane added to the roster must be benched for `json_ok` the way Cerebras gpt-oss was (roster `coder._note`).

---

## 2. Target architecture — the four-tier brain stack

| Tier | Role | Runs on | Marginal cost | Example workloads |
|---|---|---|---|---|
| **0 — Reflex** | See/decide/act on the tape | Deterministic Python | $0 | heartbeat_core, risk_gate, exits, beacon |
| **1 — Instinct** | High-volume, latency-tolerant judgment | **Local GPU (Ollama)** | $0 (electricity) | veto second-opinions, kitchen cooks, journal/EOD summarization, Discord responder, log triage, memory consolidation |
| **2 — Workhorse** | Agentic coding + mechanical multi-step work | Cheap Anthropic-compatible cloud (GLM plan / DeepSeek / Kimi / MiniMax) via claude-code-router | ~$0.14–$1.20 per M tokens, or ~$18/mo flat | conductor fires, doc updates, refactors, EOD digest drafts, skill/validator authoring |
| **3 — Judgment** | Audits, ship/kill calls, doctrine evolution, reframes | Claude Max (Fable/Opus) | $200/mo flat (current) | weekly audits, promotion adjudication, constraint-provenance audits, anything OP-3 reserves for big models |

**Design rules:**
1. Work flows to the **cheapest tier that passes its eval** — never "which model feels smart," always "which tier's scorecard clears the bar for this surface."
2. Every tier must **degrade one tier down** and the rig keeps running: Max dies → Tier 3 work runs on GLM/DeepSeek through the same harness (proven by the blackout drill, §7); cloud dies → Tier 1 local floor absorbs (already wired); everything dies → Tier 0 still trades.
3. Tier boundaries are enforced by **routing config, not discipline** — roster lanes for Python callers, claude-code-router config for the agent layer.

---

## 3. Gap map — what stands between today and sovereign

| # | Gap | Severity | Fix |
|---|---|---|---|
| G1 | Local is a **fallback floor**, not a promoted primary — roles only touch Ollama when cloud lanes die | Medium | Promote local to primary lane per role *through the shadow scorecard*, not by vibes (§6) |
| G2 | Floor model is `qwen3:14b` (mid-2025 class); box can run `qwen3.6:35b` MoE (3B-active, tool-calling ≈ Opus 4.5 on Terminal-Bench 2.0, **as-of 2026-07** press) | Medium | Pull (in progress 2026-07-08), bench `json_ok` + tok/s, then swap floor lanes for heavyweight roles; keep 14b for latency-sensitive coordinator |
| G3 | **Agent layer (Claude Code) has no routing** — every conductor/authoring/interactive fire burns Max pool | High | claude-code-router pilot (§5): mechanical fires → Tier 2, judgment stays Tier 3 |
| G4 | `shadow_model_eval.py MODELS` has no local entry — the local brain is never scored against Gamma decisions, so promotion evidence never accumulates | High | Add `qwen-local` entry riding the ollama lane; nightly Gamma_ShadowEval then builds the ≥85%/15-day case automatically |
| G5 | No **blackout drill** has ever run — future-proofing is currently a claim, not a verified property (OP-33) | High | §7 |
| G6 | 32GB system RAM caps the local ceiling at ~35B-A3B MoE class; GLM-4.5-Air-class (106B-A12B) and gpt-oss-120b need ~60–80GB for CPU-offload MoE | Low (today) | RAM 32→64/96GB is the cheapest ceiling raise (~$100–200) — **decide only when a Tier-1 eval actually fails for capability**, per §8 |

---

## 4. The routing layer — how "other models through the Claude interface" actually works

J's instinct is correct and it is a solved problem in 2026. Two mechanisms:

**A. Native Anthropic-compatible endpoints (no proxy needed).** Several providers speak the Anthropic Messages API directly. Point the harness at them with two env vars and Claude Code just works:

```
ANTHROPIC_BASE_URL=<provider endpoint>
ANTHROPIC_AUTH_TOKEN=<their key>          # per-session, e.g. in a launcher script
```

| Provider | Endpoint (as-of 2026-07) | Price signal (as-of 2026-07) |
|---|---|---|
| Z.ai GLM Coding Plan | `https://api.z.ai/api/anthropic` (intl) / `open.bigmodel.cn` (CN) | **Lite ~$18/mo (~$12.60 promo)**, ~80 prompts/5h — the "second subscription" candidate |
| DeepSeek | native both-formats, first-party | V4-Flash ~$0.14/M in / $0.28/M out, 1M ctx — cheapest wired-in entry ($5 deposit goes a long way) |
| Moonshot Kimi | `https://api.moonshot.ai/anthropic` | K2.6 ~$0.95/$4.00, 256K ctx |
| MiniMax | `https://api.minimax.io/anthropic` | M2.7 ~$0.30/$1.20 |

**B. Local, no router needed — VERIFIED 2026-07-08:** Ollama natively serves the Anthropic Messages API at `/v1/messages`. The actual `claude` binary ran end-to-end against `qwen3.6:35b` on this box (exit 0, coherent output, zero Anthropic tokens):

```powershell
.\setup\launch_claude_local.ps1                    # interactive, qwen3.6:35b
.\setup\launch_claude_local.ps1 -Prompt "..."      # print mode
# (wraps: ANTHROPIC_BASE_URL=http://localhost:11434, ANTHROPIC_AUTH_TOKEN=ollama, --model qwen3.6:35b)
```

Observed quality gap in the same test: the local model ignored a "reply with exactly X" instruction and free-associated about the system prompt — open-model instruction-following is real and is why Tier 3 stays on Max and Tier 1/2 surfaces get eval-gated, test-guarded work.

**C. claude-code-router (`@musistudio/claude-code-router`)** — installed 2026-07-08 — for multi-provider **per-request-type routing** (background/think/longContext → different providers) once Tier 2 has a key. Note: current CCR is profile-based (`ccr <profile>`; configure via `ccr ui`), not the older `ccr code` + config.json flow most guides describe.

**The subscription question, answered plainly:** the Max subscription **cannot** be pointed at other providers — it is OAuth to Anthropic only. Routing always means the other provider's API key (cheap) or local (free). The durable asset the subscription taught us to build is the **harness**: skills, agents, hooks, MCP wiring, doctrine — all of it survives a model swap unchanged. Keep Max exactly as long as it is the best $/judgment on the market (at $200 flat for Fable-class, it currently is — by a wide margin); the point of this doc is that the day it stops being true, Gamma loses a *tier*, not its life.

**Known trade-off (from field reports, as-of 2026-07):** open models behind CCR fumble more file-edits (malformed diffs, dropped context) than Claude models — they retry and burn tokens. This is why Tier 2 gets *mechanical* work with test-guarded outputs, and why promotion to any surface goes through evals first.

**Security policy for routed brains (standing):**
- Non-Anthropic cloud tiers NEVER see secrets: key files (`.mcp.json`, `automation/state/.**.key`) stay out of prompts; routed agent sessions run with deny-read on those globs.
- The repo is PUBLIC on GitHub — sending code/doctrine to GLM/DeepSeek leaks nothing that isn't already world-readable. Journals/account P&L are the sensitive class: those stay on `privacy=sensitive` no-train lanes or local, per the existing roster discipline.
- Local tier sees everything (zero egress by construction).

---

## 5. Tier-2 pilot — first concrete build

1. Create a DeepSeek account, $5 deposit (or GLM Lite if flat-rate preferred once volume proves out). **Needs J: wallet action** — the only J-gated step in this doc besides hardware.
2. `npm i -g @musistudio/claude-code-router`; config with providers `deepseek` + `ollama`, router: `background → ollama/qwen3.6:35b`, `default/think → deepseek-chat`, `longContext → deepseek` (1M ctx).
3. Re-point ONE parked mechanical fire (start: doc-updater or overnight queue-harvest — lowest blast radius, output is git-reviewable text) at `ccr code`. The 07-02 token-crunch parked Conductor/ManagerOverseer/DailyReview/Drive — **re-enable them on Tier 2 instead of re-arming them on Max.** The crunch already proved the rig survives without them on Max; bringing them back on $0.28/M tokens is strictly better than either state.
4. Measure a week in `swarm-calls.jsonl`-style ledger (CCR logs usage; fold into `spend_summary.py`). Gate: output quality via existing reviewer loops (ManagerOverseer pattern) — promote more fires only on evidence.

---

## 6. Tier-1 promotion — local from floor to primary

Eval-first, exactly like every other promotion in this project:

1. **Bench gate (mechanical):** `json_ok` + format compliance + tok/s on the veto battery. qwen3:14b passed format tonight; its *domain judgment* is unmeasured → that's what the scorecard is for.
2. **Shadow gate (the real one):** add local entries to `shadow_model_eval.py MODELS` (G4). Gamma_ShadowEval (16:05 ET) then scores the local brain against the day's actual decisions ledger, free, forever. Promotion bar unchanged: **≥85% decision-match over ≥15 days** (PROMOTION-SCORECARD).
3. **Role promotion:** on a passing scorecard, reorder that role's roster lanes so `ollama` leads and cloud free lanes become the fallback. One role at a time, `updated_utc` bumped, reversible in one edit.
4. **Veto seat:** the end-state for the hot path's 2 free-model vetoes is **one local + one cloud** — an external outage can then never blind the second opinion at a market-critical moment.

Model policy for this box (16GB VRAM / 32GB RAM, as-of 2026-07): `qwen3.6:35b` (MoE 3B-active — heavyweight roles: chef/strategist/critic/validator), `qwen3:14b` (dense, ~86 tok/s — coordinator/latency work). Candidates to watch: `gpt-oss:20b` (fast, but think-block broke strict JSON on Cerebras — re-bench locally before rostering), Gemma-4-class for vision if a chart-reading local lane is ever wanted.

---

## 7. The blackout drill — sovereignty is proven, not claimed (OP-33)

Once §5 + §6 are live, run the falsifiable gate:

> **Drill spec:** One full weekday, `ANTHROPIC_*` disabled for every autonomous fire (heartbeat is already non-Anthropic; conductor/authors/EOD on Tier 2; kitchen/vetoes on Tier 1). PASS = every scheduled fire ships work or flags a failure to STATUS.md per OP-25 ("silent failure is the only true failure"), decisions ledger shows normal density, EOD digest exists and is coherent. Log the result in this doc's changelog block.

Run it quarterly thereafter (like the DR drill it is). A passing drill converts "future-proof" from marketing to a measured property of the rig. Interactive J-sessions stay on Max during drills — the drill tests the *autonomous organism*, not J's tooling preference.

---

## 8. Home-lab hardware ladder — evidence-gated, not aspirational

Measured baseline first: the current box already runs the Tier-1 mission (86 tok/s at 14B dense; 35B-A3B expected serviceable via MoE offload). **Do not spend on hardware until a specific eval fails for capability or throughput.** When one does:

| Rung | Cost (rough, as-of 2026-07) | Unlocks | Trigger to buy |
|---|---|---|---|
| R1: RAM 32→64/96GB | ~$100–200 | GLM-4.5-Air-class / gpt-oss-120b MoE offload (~10–25 tok/s) | A Tier-1 scorecard fails on capability, and the next model class needs >32GB |
| R2: Used RTX 3090 24GB (second GPU) or 5080→24GB+ class swap | ~$600–900 | 32B-dense fully on-GPU fast; bigger MoE mostly-GPU | Tier-1 *throughput* saturates (kitchen queue backs up on local) |
| R3: Dedicated inference node (Strix-Halo-class 128GB unified mini-PC) | ~$1.7–2.2K | 100B+ MoE at usable speed, isolates inference from J's gaming/trading box | Local tier is primary for ≥3 roles AND contention with Unreal/trading measured |
| R4: Mac-Studio-class 256GB+ | $4K+ | Near-frontier open weights (Qwen3-235B, GLM flagship quants) | Only if Tier 3 replacement ever becomes the goal — today it is not |

The 5080 box gaming-contention note: Ollama unloads models after idle (`keep_alive`), and kitchen work is async — but if J is in Unreal while the kitchen cooks, GPU contention is real. R3 is the clean fix *when the evidence shows it matters*, not before.

---

## 9. Standing processes this doc creates

1. **Quarterly brain-market scan** (scout/kitchen, $0): re-verify §4 endpoints/prices, top open-weight agentic models per VRAM class, CCR health. Prices in this doc rot in ~a quarter.
2. **Quarterly blackout drill** (§7) once the pilot is live.
3. **Brain P&L line in EOD/weekly digest:** tokens + $ per tier per day, from `swarm-calls.jsonl` + CCR logs + Max plan flat-rate amortization. Cost-proofing needs a meter before it needs a plan.
4. **Roster bench-before-add rule** (formalizing tonight's think-trap lesson): no lane enters `model-roster.json` without a logged `json_ok` + tok/s bench result.

---

## 10. The soul, addressed directly

J asked for "a fully autonomous agent with a soul — personality, vision, empathy, direction, passion, drive." The load-bearing insight: **all of that already exists as text, and text is the most portable substrate in computing.** CLAUDE.md is the identity; the OPs are the values; LESSONS-LEARNED is the scar tissue; the journals are episodic memory; the persona files (gamma/chef/analyst/scout/pilot/treasurer) are the cast; auto-memory is the continuity. None of it is Anthropic-proprietary. A brain swap changes the *wattage* animating the soul, never the soul itself.

What sovereignty adds to the soul is **uninterruptibility of drive**: the kitchen, the conductor loop, the shadow evals, the memory consolidation — running on owned silicon and commodity cloud, they never pause because a plan changed or a quota ran dry. The personality J talks to stays Fable-class as long as that's the best judgment money buys; the organism underneath stops being mortal to any one vendor's pricing page.

Exit ramps, for completeness: the doctrine corpus is plain markdown readable by any harness (Agent SDK, or the open Claude-Code-compatible harnesses that read the same skill/agent formats). If the harness itself ever rugged, the migration is a config exercise, not a rewrite.

---

## Changelog

- **2026-07-08** — Doc created (J directive). Verified: local lane end-to-end through swarm_client (5.8s, logged); qwen3:14b 86 tok/s on RTX 5080; think-trap silent-empty failure documented; qwen3.6:35b pulled + benched (78 tok/s, json_ok both directions) + rostered on R&D roles (hot-path veto roles kept on 14b). **Ollama serves native Anthropic `/v1/messages` — real `claude` binary ran fully local (zero Anthropic tokens); launcher shipped at `setup/launch_claude_local.ps1`.** CCR installed (profile-era). Gaps G1–G6 mapped; Tier-2 pilot + blackout drill specced.
