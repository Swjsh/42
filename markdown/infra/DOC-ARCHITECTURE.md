# Doc-Architecture Doctrine — "Index of mid-sized single-topic files"

> **Why this exists:** J 2026-06-29 — *"you're making a new markdown file for every interaction; things are gonna get messy quick. Should we have a billion markdown files, or fold them into bigger ones, then folders, then a directory/index?"* Researched against Anthropic's context-engineering guidance, the Diátaxis framework, the `llms.txt`/`AGENTS.md` standards, and a live audit of our own 159-file sprawl. This is the canonical answer + the fold protocol. The `context-leanness` skill and `update-docs` skill both cross-link here.

> **ANSWER to J's question: NEITHER extreme.** Many tiny files retrieve as context-less slivers and bloat the index; few mega-docs blow the context budget or bury the answer in the "lost-in-the-middle" dead zone. The right end state is **topic FOLDERS + a README INDEX of mid-sized (~200–400 line) single-topic files, with ONE lean always-loaded soul file on top.** That is already Gamma's declared taxonomy — the rule is **ENFORCE it, don't drift.** The audit verdict: structure compliant, *hygiene* drifting (40+ dated one-offs dropped in instead of folded).

## The three tiers (granularity tracks *who/what reads it*, not aesthetics)

- **Tier 1 — `CLAUDE.md` (always loaded, every session).** Ruthlessly lean: identity, the 10 rules, the OP-0/OP-33-class load-bearing OPs, the tech-stack map, and POINTERS. **Pointers, not prose.** Nothing dated, nothing episodic, no inlined code/API docs. Hard budget ≤9K tokens (raised 8K→9K 2026-06-29 per Opus audit — the cap exists to bound *attention/context-rot*, not $; do NOT hand-shave load-bearing doctrine to undershoot it, and do NOT exceed ~10.5K; guarded by `check-context-budget.ps1` + `context-leanness` skill). The **pruning test** gates every line: *"would removing this line cause the agent to make a mistake?"* If no, cut it. If the agent keeps violating a rule, the file is TOO LONG and the rule is lost in noise — **prune, don't add emphasis.**
- **Tier 2 — `markdown/<topic>/` reference docs (loaded on demand).** ONE TOPIC PER FILE, ~200–400 lines (soft max 400; hard max 800). Header-structured so each section survives as a coherent retrieval chunk and the file loads whole without middle-burial. Grouped in topic folders under a README INDEX the agent reads FIRST to route. These are the living, evergreen docs — they carry CURRENT truth.
- **Tier 3 — dated/episodic artifacts (discovered via glob, NEVER linked individually from CLAUDE.md).** Post-mortems, audit snapshots, roadmap-of-the-day, recommendation JSON, STATUS archives, `journal/YYYY-MM-DD`. Append-only/immutable provenance, not prefix context. They age out under retention caps.

## Diátaxis altitude (light-touch — label, don't restructure)
Don't braid types into one mega-file. Map our existing folders to reader intent: `specs/` = **reference** (exact params, current truth) · `doctrine/` = **explanation** (the why) · `0dte/playbook` + skills = **how-to** · `audits/` + journal = the **episodic record**. A how-to that also dumps theory and reference serves no one — split when a file mixes types.

## CREATE a new file vs APPEND to a living doc — the decision rule
- **APPEND to an existing living doc** when the content is the SAME Diátaxis type AND SAME topic AND the merged result still loads cleanly (< ~400 lines, no mid-file burial). **This is the default.**
- **CREATE a new Tier-2 file** only when the content is a genuinely NEW topic, or an existing file would exceed ~400 lines / start mixing types. A new file MUST be added to that folder's README index in the same change.
- **CREATE a Tier-3 dated file** only for a FROZEN record: a decision + its rejected alternatives + the reasoning-at-the-time (post-mortem, ADR, daily audit). **Freeze the *why*;** never edit an accepted dated record — supersede it with a new one and link.

## How dated one-offs FOLD instead of accumulating (the OP-22 application)
The real violation the audit found is OP-22 "compound, don't accumulate." The discipline:
1. **A dated file's durable finding folds UP into the living doc.** A post-mortem that yields a stable fact ("the rig kills its own processes") → extract `symptom → root-cause → fix` into `LESSONS-LEARNED.md` as an L## (via `lesson-author`), leave the raw post-mortem as frozen provenance, let it age out. **Freeze the why, evolve the what.**
2. **A daily-snapshot series is a ROLLING LOG, not N docs.** `HEARTBEAT-TICK-AUDIT-YYYY-MM-DD.md`×7 collapses into ONE reverse-chronological log with a retention cap (keep last ~10) — OP-22's "append-only producer → CONSOLIDATION on cap."
3. **Superseded blueprints get demoted/archived, not kept loose.** Multiple same-initiative dated plans fold into ONE living roadmap; superseded snapshots go to `markdown/_attic/` or git history.
4. **Staleness is a smell, surfaced not silent.** A post-mortem older than N days whose finding hasn't been folded is a smell. An evergreen doc flagged STALE (ARCHITECTURE.md was, twice) is the #1 solo-dev risk — add a "last-verified" date + a staleness audit; that beats prose.

## Single source of truth (the drift killer)
"Single source of truth" = **NO duplicated fact**, NOT one giant file. Many small files each owning ONE fact + an index satisfies it. The real risk is the SAME fact in two places drifting — e.g. CLAUDE.md rule-version prose vs `params.json` (mitigated by "rule mismatch = kill-switch"). When you fold, dedupe: a fact lives in exactly ONE living doc; everything else points to it.

## Enforce with tools, not prose
If a linter/test/hook/budget-guard can enforce it, don't spend always-loaded budget on prose about it. Mechanical rules → config/hooks. Sometimes-relevant domain knowledge → **skills** (name+description is the only per-session cost; body loads just-in-time). This frees Tier-1 for the non-mechanical project knowledge only CLAUDE.md can carry.

## `llms.txt` / `AGENTS.md` (cheap public-repo wins)
`Swjsh/42` is public. Optional ~30-min adds, zero ongoing maintenance: a root `llms.txt` (machine twin of `markdown/README.md` — H1 + blockquote + H2 link-lists, with a `## Optional` section for skippable deep-dives) and a thin root `AGENTS.md` pointing at CLAUDE.md + the bash/venv commands, so Cursor/Aider/Codex read the repo too.

## The one-line test for "fold or split?"
**Fold** two files only if SAME type + SAME topic + merged result loads clean without mid-file burial. **Split** a file when it mixes Diátaxis types, exceeds ~400 lines, or covers two topics. Keep operational/append-only state (STATUS, logs, scorecards) OUT of reference docs and under retention caps.

---

### Sources (researched 2026-06-29)
- Anthropic — *Effective context engineering for AI agents* (finite "attention budget", context rot, just-in-time loading).
- Claude Code — *Best practices* ("CLAUDE.md loaded every session; only include what applies broadly; bloated files make Claude ignore your instructions; link don't inline; skills for sometimes-relevant; hooks for must-happen").
- *Diátaxis* (diataxis.fr) — four doc types, don't mix on one page.
- *Lost in the Middle* (TACL, Liu et al.) — U-shaped attention; mid-buried facts drop 30%+.
- `llms.txt` (llmstxt.org) + `AGENTS.md` (agents.md) — emerging machine-readable repo-index standards.
- *Architecture Decision Records* (Fowler) — dated records are append-only/immutable; supersede, never edit.
