# Project Gamma — Deep Review & Self-Improvement Roadmap
**Date:** 2026-06-14 · **Scope:** entire project (SPY engine, infrastructure, crypto, dashboard, docs) · **Mode:** review first, no changes made this session

---

## 1. The one-paragraph verdict

You have built genuinely sophisticated scaffolding for an autonomous, self-improving trading research system — a real-fills backtester, a content-addressed reproducibility layer, a shadow/auto-ratify "Karpathy loop," a 24/7 Kitchen R&D daemon, self-healing PowerShell harness, and a disciplined doctrine. **The problem is not capability — it's that the self-improvement loop does not close.** Almost every mechanism that would convert research into a live improvement is currently disabled, stalled, starved, or human-gated with no human acting. Meanwhile the system generates enormous *motion* — 558 Kitchen cooks, a 1.6 GB crypto data hoard, 370 strategy candidates — that is mistaken for *progress*: **zero candidates have ever been ratified to live, the live account is down ~29% on only 12 trades in a month, and the very files meant to signal health are themselves stale.** To make this project actually improve itself, the priority is not more features. It is: (1) make it reversible, (2) make staleness loud, (3) close the loop on *one* real candidate end-to-end, (4) make what it learns trustworthy, and (5) stop the motion that doesn't compound.

---

## 2. What I actually reviewed (and a note on "every line")

I read the load-bearing files firsthand (CLAUDE.md, `params.json`, all four heartbeat/EOD/premarket prompt families, `shadow-version.json`, `circuit-breaker.json`, `.mcp.json`, the corrupted root files, `trades.csv`, state mtimes) and fanned four parallel investigators across `automation/`, `backtest/`, `setup/scripts/`, `crypto/`, `dashboard/`, `strategy/`, and the docs corpus. Every headline finding below was verified against an actual file or line.

Literally reading "every single line" is the wrong goal, and *that itself is a finding*: the repo is ~24,000 files — but that's ~159 K lines of hand-written code plus **~111 K lines of markdown across 1,153 files**, much of it duplicated, contradictory, or stale (e.g., three overlapping lessons files; `ARCHITECTURE.md` untouched since May 9 and now actively misleading; `STATUS.md` at 2,100 lines with encoding rot). A system that wants to read and reason over itself cannot afford a corpus this noisy. Pruning the corpus *is* part of making it self-improving.

---

## 3. Core diagnosis — the loop doesn't close

Your intended self-improvement engine (OP-11, the "Karpathy method") has three loops. Here is where each one breaks today:

**Inner loop (per-tick shadow).** `heartbeat.md` is supposed to run production params *and* a shadow overlay every tick. **BREAK:** `shadow-version.json` is permanently `enabled: false, version: null, overrides: {}`. No candidate is ever staged, so the shadow has never run, ever. The directory `analysis/shadow-scorecards/` does not exist.

**Mid loop (daily flywheel).** EOD is supposed to diff the shadow, refresh aggregates, and feed `append_today.py`. **BREAK:** `setup-performance.json` — the gate input — **does not exist**; `equity-curve.json` is frozen at 2026-05-18. The EOD chain is not completing. Worker D short-circuits to `{"shadow_enabled": false}` nightly.

**Outer loop (weekly auto-ratify).** Weekly review is supposed to auto-ratify a dominating shadow into `params.json` (you as REVOKE, not approve). **BREAK:** there is no shadow data to dominate; the ≥20-trade gate is unreachable (only 12 trades exist); `setup-promotion-log.jsonl` was never created. **No setup has ever been auto-promoted or auto-demoted. No `recommendations/*.json` has ever been auto-ratified.**

**Net:** the only genuinely-alive component is the Kitchen, which cooks 24/7 and writes DRAFT candidates that pile up waiting for a human promotion step that stopped happening on 2026-05-24. Every closing mechanism is dormant. The machine is running on ~10% of its designed machinery, and nothing flags that fact.

---

## 4. Findings by severity

Evidence in parentheses. Dedupe of all four investigations + my firsthand checks.

### CRITICAL

| # | Finding | Evidence |
|---|---|---|
| C1 | **The self-improvement loop is theater.** Shadow disabled forever; outer loop never fired; gate inputs missing. The flagship feature does not function. | `shadow-version.json` (`enabled:false`); `setup-performance.json` MISSING; no `shadow-scorecards/`, no `setup-promotion-log.jsonl` |
| C2 | **No version control = no safe rollback for a system designed to edit itself.** `params.json` has a single `.lastgood` mirror; the append-only `.jsonl` ledgers have zero corruption protection or backup. There is no way to undo a bad auto-ratify. | not a git repo; `_shared.ps1:159` self-heals `*.json` only |
| C3 | **`params.json` contradicts its own version + the two accounts run different rules.** Header says `v15.3`, but the exits section still carries v14 values: `premium_stop_pct:-0.08` (CLAUDE.md v15 doctrine says bear −20%), `tp1_qty_fraction:0.667` (doctrine 0.50), `runner_max_premium_pct:3.0` (doctrine 2.5). Safe=v15.3, Bold runs `aggressive/params.json`=v15.2. The pin-check only compares the *version string*, so this body drift is invisible to the kill-switch. | `params.json` L16,20,23 vs CLAUDE.md "strategy" section; `params_safe/bold.json` have **no `rule_version` field at all** |

### HIGH

| # | Finding | Evidence |
|---|---|---|
| H1 | **Live account down ~28.6% on 12 trades in a month** — far below the 20-trade deployment gate. The system is "running" but barely trading and losing. | `circuit-breaker.json` ($713.50 / $1,000); `trades.csv` = 12 rows, last 2026-06-03 |
| H2 | **Daily lifecycle is degraded and nobody is told.** Premarket last reset 2026-06-08 and fired at **15:21 ET, not 08:30** (its own note: "LATE RUN"); Safe `decisions.jsonl` stops 6/03; STATUS files stale. Staleness is invisible because nothing asserts freshness. | `circuit-breaker.json` `_note`; mtimes (decisions 6/03, news 5/21, equity 5/18) |
| H3 | **The research engine optimizes the wrong objective → overfit-prone promotions.** Grinders search in BS-sim then validate in real-fills (`use_real_fills=False` hardcoded); the OP-16 edge-capture floor — your one anti-overfit gate — is *disabled* in `v14_enhanced_grinder`; the "OOS" window overlaps the optimizer's anchor days. | `runner.py:179`; `v14_enhanced_grinder.py:212-234`; `v14_enhanced_walk_forward.py:62,255-262` |
| H4 | **ENTER decisions never reach `decisions.jsonl` (L17, known ~13 mo).** Every downstream learning signal (decision precision, shadow diff, grading) silently undercounts. | `wake-protocol.md:248`; ledger has 1 ENTER row vs 12 trades |
| H5 | **Mangled-path orphan decision logs** at repo root — an LLM agent wrote a literal `C:\...` absolute path while on the Linux mount, fragmenting real trade decisions away from the canonical ledger. Will recur on every cross-platform session. | two root files `C:Usersjackw...decisions.jsonl` (41 + 4 real rows) |
| H6 | **Crypto = 1.6 GB write-only hoard.** `grinder.jsonl` is 212 MB and still growing today; 13 unpruned archives ~1.5 GB of raw BTC bars no consumer reads. ~95% of repo non-code bloat. | `crypto/data/scorecards/grinder*.jsonl` |
| H7 | **Kitchen candidate flood, decoupled from curation.** 370 candidate files, the large majority auto-generated, 43 are empty "0 keepers" files; leaderboard curation lags far behind generation (latest reviewer reference 6/07, but the bulk of June drafts went untriaged); **zero ever ratified to live.** Generation ≫ curation ≫ ratification (=0). | `strategy/candidates/` (370 files, 43 empty); `_LEADERBOARD.md` |
| H8 | **Secrets in plaintext.** Both Alpaca key-pairs sit unencrypted in `.mcp.json`, which is **not** in `.gitignore`. Paper-only so low blast radius, but it's the one secrets file left uncovered while OpenRouter's key is correctly externalized. | `.mcp.json` L13-14,24-25; `.gitignore` |

### MEDIUM (condensed)

- **Self-healing gaps:** `Repair-StateFiles` covers only `*.json` (jsonl ledgers unprotected); it promotes any *parseable* file to `.lastgood`, so a stale-but-valid state can be locked in and restored over good writes.
- **Dead subsystems still wired in:** swarm (all agents failing since 6/03), Discord (abandoned 5/23, 10+ orphan state files), `news.json` (24 d stale, superseded by scout). All fail "gracefully" → silently → never repaired.
- **Backtest correctness latent bugs:** look-ahead vector (`prior_bars=` full day frame) safe only by convention; strike-parity param-passed not asserted (the exact OP-16 gate that cost a weekend); data frozen at 2026-05-22 because the flywheel appends files the canonical loader can't read.
- **`queue.md` choked** with ~33 duplicate CRITICAL self-noise (`HARVEST-REGFAIL`), steering every wake fire into stale failures.
- **`STATUS.md`:** 2,100 lines, contradictory task counts (9 vs 14 vs 27), mojibake encoding — the "wake to a signal" file is unreadable.
- **Dashboard dormant:** 670 MB (3D engine deps for a pixel-art viewer), unbuilt, source stale since 5/17, outside the trading loop.

### LOW (condensed)

- `CLAUDE.md` is 38 KB despite "lean by design" (70+ inline "lessons absorbed" belong in `LESSONS-LEARNED.md`); `ARCHITECTURE.md` 5 weeks stale and misleading; journal infrastructure (43-column schema, empty `replays/`/`recaps/` dirs) is wildly over-built for 12 trades; `repro.py` records but never *enforces* reproducibility and its `code_hash` misses the entire `autoresearch/` tree; em-dashes in `.ps1` (comments only — no runtime break); CLAUDE.md says "15 tasks," registry says 27.

---

## 5. The deeper pattern: motion mistaken for progress

H6, H7, and most of the MED/LOW findings share one root cause: doctrine OP-22 ("Don't stop cooking… the work queue is INFINITE") and OP-25 ("Never sign off… the work is never done," with a banned-phrase list that forbids "all done"). A system *instructed* that it may never stop, never declare done, and must always generate more will reliably produce exactly what's here: an unbounded data hoard, a 370-file candidate flood, duplicated docs, and "busy" wake fires spinning on stale noise. It also produced the two worst operational incidents in your own logs — the OP-32 firewall that **locked you out of Claude entirely**, and repeated heartbeat starvation from the shared rate-limit pool.

A genuinely self-improving system needs the opposite capabilities: the ability to **stop**, to recognize "good enough," to **prune**, to keep bounded queues, and — critically — to keep the human able to interrupt at any time. Self-improvement is a *closed, reversible, measured* loop, not perpetual output. The roadmap below treats "the ability to stop and roll back" as a feature, not a failure.

---

## 6. Roadmap — making it improve itself (your choices: balanced rails+capability, keep auto-ratify with you as REVOKE)

Phased so each phase makes the next one safe. Rough effort in brackets.

### Phase 0 — Reversibility & safety net  *(do first; nothing autonomous is safe without it)* [~½ day]
1. **Give the self-editor an undo button.** Initialize git on the repo (or, if you avoid git deliberately, a timestamped snapshot of `automation/{state,prompts}`, `strategy/`, `params*.json` before every auto-ratify and every prompt/param edit). One-command rollback.
2. **Make REVOKE physically trivial.** Every auto-change to `params.json` or a prompt appends a one-line human-readable diff to a single `CHANGES-PENDING.md` you can revert in one edit. This *keeps* your "J revokes, not approves" model (your stated choice) while making the revoke a 5-second action.
3. **Fail-open invariant, encoded.** Any future guard that can kill a process or gate Claude must self-expire and must never block your interactive sessions (the OP-32 lesson, made structural).

### Phase 1 — Close the loop on ONE candidate + make staleness LOUD [~1–2 days]
4. **Freshness watchdog → 40-line STATUS header.** A single check that asserts {premarket ran today, EOD completed, decisions written ≤1 trading day ago, `params.json` not internally contradictory, Safe and Bold rule_versions match} and writes ONE red flag when anything fails. Replace the 2,100-line `STATUS.md`. Right now staleness is invisible; this makes "the loop stopped" impossible to miss.
5. **Unstick the EOD chain.** Fix the dead output paths (`analysis/equity-curve.json` → `state/equity-curve.json`), regenerate `setup-performance.json`, and add a post-EOD assertion that both refreshed today or it flags BROKEN.
6. **Run the shadow loop end-to-end exactly once.** Stage one real Kitchen candidate into `shadow-version.json`, let inner→mid→outer execute, and watch a real auto-ratify land (with Phase-0 snapshot + REVOKE). Prove the loop closes. **If you won't operate it, delete the shadow scaffolding** so the prompts stop claiming a loop that's off — theater is worse than absence.
7. **Fix the ENTER→`decisions.jsonl` gap (H4/L17)** so the data the loop learns from is complete.

### Phase 2 — Make what it learns TRUE (so it doesn't auto-promote overfit) [~2–3 days]
8. **Select in the space you validate.** Stop hardcoding `use_real_fills=False`; rank the final selection in real-fills (or real-fills re-rank of the BS top-K).
9. **Re-enable the OP-16 edge-capture floor** in the grinder, recalibrated to real-fills values — no candidate passes on aggregate `wide_pnl` alone (your own doctrine forbids it).
10. **Build a true frozen holdout** that never overlaps anchor days; gate `monday_ready=PASS` on positivity there.
11. **Three small structural guards:** assert sim strike == production tier strike; pass `prior_bars=df.iloc[:idx+1]` so look-ahead is *impossible*; refuse to promote if `data_hash` is >5 trading days old, and fix the flywheel→loader handoff so data isn't frozen at 5/22.
12. **Reconcile C3:** fix the `params.json` v14/v15.3 body contradiction, give `params_safe/bold.json` a `rule_version`, and make the pin-check compare body values + cross-account version, not just the string.

### Phase 3 — Cut the motion that doesn't compound [~½ day]
13. **Stop the crypto bleed:** disable the grinder keepalive, prune the 13 archives (~1.5 GB back), cap any retained logging. Move `crypto/lib/` (real shared production code — strike selection, chart patterns) to `backtest/lib/shared/`; retire the always-on validator theater, keep validators as a pre-merge gate only.
14. **Gate Kitchen output on `keepers>0`** (kills the 43 empty noise files + the future flood); reconnect reviewer verdicts → leaderboard, or pause the seeder. Build **one** shadow-anchor pipeline so top RATIFICATION_READY candidates can actually progress instead of waiting on a manual step that stopped.
15. **Decommission dead subsystems explicitly** (swarm, Discord, 4 stale heartbeat drafts, `news.json`): remove from read paths, archive orphan state. Slim `CLAUDE.md`, rewrite or delete `ARCHITECTURE.md`, right-size the journal, fix `STATUS.md` encoding.

### Phase 4 — The self-improving engine, properly *(ongoing, after 0–2)*
16. Once the loop is **closed (P1) + trustworthy (P2) + reversible (P0)**, weekly auto-ratify with you as REVOKE is exactly the model you chose — and now it's safe to leave running.
17. **Add a meta-monitor:** the system grades its *own* health weekly (did the loop close? did a candidate ship? is the trade-count gate progressing toward 20?) and surfaces **one** self-improvement proposal to you — not 158 candidate files.
18. **Introduce "good enough / stop"** to counter OP-22/25: bounded queues, dedup, and the ability to mark a subsystem DONE. Recommend softening the "never stop / never done" doctrine to **"compound, don't accumulate,"** with explicit bounded-resource guards and your ability to interrupt always preserved.

---

## 7. Decisions I need from you before Phase 0

1. **Git or snapshots?** Do you avoid git deliberately (the repo has a `.gitignore` but was never `git init`-ed)? Reversibility is the gate for everything else — I'll use git unless you'd rather I build a snapshot-only system.
2. **Shadow loop: operate it or delete it?** It's been off since inception. Either we run it for real (item 6) or we cut the scaffolding. I won't leave it as theater.
3. **Crypto: pre-merge gate or full retirement?** `crypto/lib` is real and stays. The 1.6 GB validator harness is the question.
4. **The market-hours / rate-pool problem.** You're currently on pure self-discipline after OP-32 locked you out. Want a *fail-open* lightweight cooldown guard, or keep it fully manual?

---

## 8. Appendix — key file references

`automation/state/shadow-version.json` · `automation/state/params.json` (L16,20,23) · `automation/state/circuit-breaker.json` · `automation/state/params_safe.json` / `params_bold.json` (no rule_version) · `automation/state/aggressive/params.json` (v15.2) · `journal/trades.csv` (12 rows) · `automation/prompts/heartbeat.md` · `automation/prompts/wake-protocol.md:248` · `backtest/autoresearch/runner.py:179` · `backtest/autoresearch/v14_enhanced_grinder.py:212-234` · `backtest/autoresearch/v14_enhanced_walk_forward.py:62,255-262` · `backtest/lib/simulator_real.py:62-63` · `setup/scripts/_shared.ps1:159-184` · `setup/scripts/kitchen_daemon.py` · `.mcp.json` · `crypto/data/scorecards/grinder.jsonl` · `strategy/candidates/_LEADERBOARD.md` · root: `C:Usersjackw...decisions.jsonl` (×2).

*No code or doctrine was modified in producing this review.*
