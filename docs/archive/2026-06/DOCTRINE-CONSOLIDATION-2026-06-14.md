# Project Gamma — Doctrine Consolidation Proposal
**Date:** 2026-06-14 · **Status:** proposal for J approval — no doctrine changed yet · **Companion to:** DEEP-REVIEW-2026-06-14.md

> Goal: shrink the doctrine so the system is small and coherent enough to actually follow its own rules. This proposal **replaces sprawl with a leaner set** — approving it is a net deletion, not an addition.

---

## 1. The core finding about the doctrine itself

The doctrine has an **asymmetry**: the "go" side of autonomy is hard-wired (daemons, keepalives, banned stop-phrases, "the queue is INFINITE"), while the "whoa" side (prune, dedupe, declare good-enough, cap resources, keep the human in control) is absent — or was deleted as too dangerous after OP-32 locked you out. That single asymmetry explains most of what the deep review found: 1.6 GB crypto hoard, 367-file candidate flood, three subsystems failing silently, and a loop that never closes.

And the lessons confirm your own instinct that "we listened to some and not others." **Eight problem families recurred *after* being written down** — meaning prose failed as a control. The fix isn't more prose; it's graduating those eight from text into assertions (Part C). That is the single highest-leverage move in this whole project.

## 2. The sprawl, quantified

| Artifact | Now | Target |
|---|---|---|
| Operating Principles (active inline) | 6 (of 32 ever written) | **8 sharp OPs**, no archive bloat inline |
| "Lessons absorbed" lines inline in CLAUDE.md | 51 one-liners | **18-row themed index** (full prose stays in LESSONS-LEARNED.md) |
| Distinct lessons (LESSONS-LEARNED.md) | 76 | 76 prose kept; **8 graduate to code** |
| CLAUDE.md size | 38 KB | ~15–18 KB (est. >50% cut) |
| strategy/candidates files | 367 | bounded + curated (Part D) |

---

## 3. Part A — Operating Principles: 6 active (32 historical) → 8 sharp

### Three contradictions that MUST be reconciled (doctrine claims ≠ reality)

1. **OP-11 (Karpathy self-improvement loop) is largely fiction.** `shadow-version.json` is `enabled:false` and has never run; no `recommendations/*.json` verdict has ever been `auto_ratify`. The doctrine describes a flywheel that produces zero ratifications. → *Decision #2 (operate it) fixes this — but until it runs, OP-11 should be marked STAGED, not presented as live.*
2. **OP-16 (J-edge floor is the hard primary gate) is contradicted by the code.** `v14_enhanced_grinder.py:211-220` explicitly **drops** the edge_capture floor ("let wide_pnl do the differentiating") because real-fills made `edge_capture` permanently fail the old $771 number. So the stated primary metric is not enforced by the primary grinder. **You must pick one:** re-enable the floor recalibrated to real-fills values, **or** rewrite OP-16's number to match reality. Right now it's neither.
3. **OP-22 + OP-25 ("never stop / never done / 'all done' is banned") are actively causing the hoarding.** A doctrine that forbids stopping guarantees accumulation without consolidation. This is the root cause, not a side effect.

### Proposed consolidated OP set

| New OP | Folds in | Essence |
|---|---|---|
| **OP-A — Rules over P&L** | rule 10, OP-9/10 | The 10 hard rules beat any profit. Rule-breaking winners still get red-flagged. |
| **OP-B — Evidence or it didn't happen** | OP-2, 11, 14, 16, 20 | Every "edge"/"ready" claim needs OOS + real-fills + concentration disclosure. edge_capture primary, WR awareness-only. *(Resolve the OP-16 reconciliation above.)* |
| **OP-C — Fix-on-find, no drift, no deferral** | OP-1, 4, 8 | Fix now; keep dual implementations in sync; no "later." |
| **OP-D — Engine-benefit autonomy** | OP-18, 19, 21 | Ship infra/validators/watchers without per-decision approval. Anything touching live orders / heartbeat.md / params.json → J ratifies (Rule 9). |
| **OP-E — Compound, don't accumulate** *(replaces never-stop)* | OP-22, 25 | *see rewrite below* |
| **OP-F — The Kitchen** | OP-31 | Operational spec only (daemon, ladder, $3/day cap, guardrails). The "never stop" framing moves to OP-E. |
| **OP-G — Lean cost & footprint** | OP-3 | Extends the $100/mo dollar gate to **disk + file-count budgets**: retention caps on append-only logs, candidate-dir ceiling, archive rotation. Governs bytes, not just dollars. |
| **OP-H — Bounded autonomy infra** | OP-15, 30, anti-OP-32 | Concurrency/effort caps, free-tier-first. **Any guard MUST fail open and MUST exempt J's interactive session** — the OP-32 scar, encoded as a constraint. |

### OP-E rewrite — "Compound, don't accumulate" (preserves your autonomy, removes the foot-guns)

1. **Always-on means always-*improving*, not always-*emitting*.** A session is measured by net leaderboard/doctrine improvement, not files created. A 368th untriaged candidate is debt, not progress.
2. **"Good enough" is a valid terminal state for a task.** Drop the banned-phrase list. Ban only *silent* stopping (stop with no logged outcome) and *blocked-on-J with no reason*. Allowed: "task meets its bar; promoting result, selecting next."
3. **Bounded resources, enforced (ties to OP-G).** Every append-only producer gets a retention cap; hitting it triggers *consolidation*, not a bigger disk.
4. **Prune is a first-class scheduled task.** Weekly: dedupe candidates → leaderboard, archive stale seeds, compress logs. Consolidation counts as output.
5. **Human holds the off-switch — by design, never by lockout.** No automated process may ever kill or block your interactive session. When "done," the agent surfaces a clear signal and picks the next *bounded* task — it does not manufacture motion to avoid the word "done."

Net: still 24/7, still never silently idle — but it compounds instead of accumulating, and you always hold the off-switch.

---

## 4. Part B — Lessons: 76 prose + 51 inline → 18-row themed index

Keep all 76 full writeups in LESSONS-LEARNED.md. **Replace the 51 inline one-liners in CLAUDE.md with this index + count.** That alone removes most of CLAUDE.md's bulk.

| # | Canonical lesson | Folds in (Lxx) |
|---|---|---|
| C1 | Real-fills is the only WR authority; BS-sim is ranking-only | L02,12,23,50,71 |
| C2 | First-strike entries: chart-stop only, premium-stop disabled | L51,55,64 |
| C3 | SPY-price edge ≠ option edge (delta/theta/stop-misfire) | L58,74 |
| C4 | Disclose concentration, normalize OOS, stratify by regime | L01,04,05,10,11,22,46,48 |
| C5 | VIX *character* > VIX level; as-of trigger time | L40,44,45,73 |
| C6 | No look-ahead: filter ≤ current bar; verify bar closed; slice prior_bars | L14,34,57,61 |
| C7 | Silent success is failure — audit outputs, not exit codes | L19,26,28,32,39,53,62,67 |
| C8 | Headless Windows spawn = system-pythonw + CREATE_NO_WINDOW + WMI liveness | L20,27,33,41 |
| C9 | Anchor paths to `__file__`; update ALL state consumers; dual-account symmetry | L21,42,49,60 |
| C10 | Rate-limit pool: separate prod key; never automate operator lockout | L54,62,68,69 |
| C11 | Broker is source of truth: verify flat before entry; atomic brackets | L47,76 |
| C12 | Stateful detectors need warmup / persisted state | L30,35 |
| C13 | Confidence tiers must be reachable AND diverse over N≥20 | L63,65 |
| C14 | Dead/stale knobs: vary-and-assert; sync tracker to production params | L38,70,72 |
| C15 | Gates interact multiplicatively — trace session cascades | L07,08,09,66 |
| C16 | Multi-bar reversal vs single-bar continuation discriminator | L52,59,75 |
| C17 | Build reusable skills + crypto validation, not one-shots | L36,37 |
| C18 | Never sign off silently / status-format discipline | L06,15,17,18 |

**Archive candidates** (tied to removed subsystems): L13/L18/L29 (Discord), L68/L69 mechanics (OP-32 firewall — keep the *lesson*, drop the implementation), BS-sim absolute-P&L targets (superseded by real-fills).

---

## 5. Part C — The graduation list (prose → assertion) — THE high-leverage work

These 8 families each recurred *after* being documented. Every one is mechanically checkable. Convert each from a CLAUDE.md sentence into a check that fails loudly. This is what "make the system follow its own lessons" actually means.

| Recurrence chain | Why prose failed | The assertion that ends it |
|---|---|---|
| **Rate-pool starvation** L54→L62→L68→L69 | exhortation can't stop a shared pool | **Separate production API key** for heartbeat (the named permanent fix) + heartbeat writes any 429 to STATUS sentinel |
| **pythonw venv-stub re-exec** L20→L27→L33→L41→(all 13 grinders, 5/23) | every script re-derived the path | startup `assert "Python313" in sys.executable`; CI grep-ban `Path(sys.executable).parent/"pythonw"` |
| **Premium-stop on first-strike** L51→L55→L64 | re-derived per setup | watcher invariant: entry-bar-is-the-move ⇒ `premium_stop=-0.99`; unit test; stop-misfire >35% auto-block |
| **Look-ahead** L14→L34→L57 | convention, not enforcement | `BarContext.__post_init__` asserts `len(prior_bars)==idx+1`; latest-bar read asserts `bar_close_et<=now` |
| **Stale/dead knobs** L38→L70→L72 | tracker drifted from params | pre-ratification assert `j_edge_tracker overrides == params.json` exit knobs; vary-knob-assert-output-differs |
| **Broker/state drift** 05-11→05-19→05-21→L76 | local state trusted over broker | `get_all_positions` empty before entry (L76 shipped this — the model to copy) |
| **Silent zero-observation** L28→L32→L35→L56 | task exited 0, did nothing | EOD asserts obs-count>0 per active watcher; flag within 24h |
| **Unreachable confidence tiers** L63→L65 | fix created all-true tier | `assert all tiers count>0 over N≥20` before shipping tier logic |

---

## 6. Sequencing (with your 3 locked decisions folded in)

1. **Consolidate doctrine** (this proposal, on approval): rewrite CLAUDE.md to the 8 OPs + 18-lesson index; move full prose to LESSONS-LEARNED.md; archive dead-subsystem lessons.
2. **Phase 0 — safe git setup**: scrub Alpaca keys from `.mcp.json`, write `.gitignore` (secrets, `.venv`, `node_modules`, `crypto/data`, `backtest/data`, build artifacts), first clean commit to `github.com/Swjsh/42`.
3. **Graduate the 8 families to assertions** (Part C) — these become the "make staleness loud" backbone of Phase 1.
4. **Close the loop**: operate the shadow on one real candidate (**#2**), unstick EOD, freshness watchdog.
5. **Build**: real-fills selection + re-enable edge floor; crypto → pre-merge gate (**#3**); fail-open cooldown + heartbeat token-optimization (**#4**).

---

## 7. What I need from you to proceed

1. **Approve the 8-OP consolidation** (Part A) — or tell me which to keep/split.
2. **OP-16 reconciliation:** re-enable the edge floor (recalibrated to real-fills) **or** rewrite the doctrine number? This is a real fork — it changes what the grinder is allowed to promote.
3. **Approve the lessons collapse** (Part B) — 51 inline lines → 18-row index, full prose preserved.
4. **Green-light the graduation work** (Part C) as the first build task after Phase 0 — this is where prose becomes enforcement.

Once you approve, the order is: consolidate CLAUDE.md → safe git commit → graduate the 8 assertions → close the loop.

*No files modified in producing this proposal.*
