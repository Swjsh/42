# Skills Catalog — re-usable diagnostic + audit tools

> **Why this exists:** OP-25 self-correction mandate says "encode the prevention so it CANNOT happen again." When we build a re-usable tool to catch a foot-gun, future fires need to find it instead of rebuilding from scratch. This catalog is the index.
>
> **Owner:** Gamma (auto-updated when we ship new tools per OP-25). J doesn't curate — but does read this when he wants to know "is there already a tool for X?"
>
> **Three categories:**
> 1. **Claude Code skills** (`.claude/skills/*/SKILL.md`) — slash-command-callable patterns
> 2. **Python diagnostic tools** (`backtest/autoresearch/*.py`) — re-runnable Python scripts
> 3. **PowerShell audit scripts** (`setup/scripts/*.ps1`) — system-level health checks

---

## 1. Claude Code skills (slash-command-callable)

Project skills live in `.claude/skills/{skill-name}/SKILL.md`. Each defines: when to invoke, steps to run, success criteria. Future Claude sessions can read these directly.

| Skill | Purpose | Invocation |
|-------|---------|------------|
| `backtest-compare` | Run current strategy vs all historical days, flag regressions | `python tools\compare.py` |
| `heartbeat-tick-audit` | Classify every heartbeat tick today as ALIGNED/MISALIGNED — verify R1 closed-bar fix held | `python -m autoresearch.heartbeat_tick_audit --date YYYY-MM-DD` |
| `watcher-fleet-status` | Per-watcher observation count last N days; flag any silent-failure pattern | `python backtest/autoresearch/_smoke_watchers.py` |
| **`watcher-promotion-gates`** | OP-21 promotion gate dashboard for all 13 watchers. Shows H/WF/RF/LIVE gate status + live win counts toward promotion. Reads `watcher-observations.jsonl` filtering by `bar_timestamp_et >= 2026-05-18` (live only, not replay). Writes `automation/state/watcher-promotion-snapshot.json`. | `python backtest/autoresearch/watcher_promotion_gates.py [--json]` |
| **`heartbeat-pulse-check`** (Self-heal #1) | Verify Gamma_Heartbeat scheduled task firing on schedule (every 3 min during market hours). RED if any 15-min gap. Auto-heals task-Disabled state. | `& setup\scripts\heartbeat-pulse-check.ps1 [-Date YYYY-MM-DD] [-Heal]` |
| **`heartbeat-mcp-self-test`** (Self-heal #2) | Verify TV CDP port 9222 listening + alpaca-mcp process alive. Auto-heals TV (kill+restart). | `& setup\scripts\heartbeat-mcp-self-test.ps1 [-Heal]` |
| **`heartbeat-decision-trace`** (Self-heal #3) | Per-tick filter walk diagnostic. Walks filter 1-11 against `decisions.jsonl` + `params.json` thresholds. Pure DIAGNOSTIC. | `python -m autoresearch.heartbeat_decision_trace --date YYYY-MM-DD --tick N` |
| **`watcher-state-inspector`** (Self-heal #4) | Dump ORB + ODF state-machine `_orb_state[date]` and `_odf_state[date]` after T82 warmup. RED if state stuck. Heals via `audit-silent-watcher-days.ps1`. | `python -m autoresearch.watcher_state_inspector [--date YYYY-MM-DD] [--heal]` |
| **`chart-data-verify`** (Self-heal #5) | Cross-check last N closed SPY 5m bars across CSV + yfinance (LLM mode adds TradingView). RED if divergence > $0.10. Heals via in-memory yfinance top-up. | `python -m autoresearch.chart_data_verify [--date YYYY-MM-DD] [--bars N] [--heal]` |
| **`pin-chain-verify`** (Self-heal #6) | Verify rule_version pin agreement: params.json + heartbeat.md + premarket.md. RED if drift. NEVER auto-edits production prompts (rule 9). | `python -m autoresearch.pin_chain_verify` |
| **`validator-author`** (Skills Pipeline #1, OP-29) | Authors gym validators from items in `_validator-inbox/`. Writes `crypto/validators/v{NN}_{slug}.py`, registers in `runner.py`, runs gym, bumps CLAUDE.md OP-26 count on PASS. Engine-benefit autonomy (no ratification). NEVER edits live doctrine. | `/validator-author` (forked subagent) |
| **`skill-author`** (Skills Pipeline #2, OP-29) | Authors Claude Code skills from items in `_skill-inbox/`. Writes `.claude/skills/{slug}/SKILL.md` + `backtest/autoresearch/{slug}.py` + SKILLS-CATALOG.md row + tool-selection-guide row. Routes `kind: tune` items to `skill_tune.py`. | `/skill-author` (forked subagent) |
| **`lesson-author`** (Skills Pipeline #3, OP-29) | Encodes one-off foot-guns into permanent doctrine. Appends L## entry to `docs/LESSONS-LEARNED.md` AND OP-25 absorbed-lesson bullet to `CLAUDE.md`. The ONLY author with OP-25 write access (per OP-25 self-correction mandate). | `/lesson-author` (forked subagent) |
| **`gym-session`** (Skills Pipeline #4, OP-29) | Unified daily chart-reading audit "physical exam". Aggregates 7 audits → ONE GREEN/YELLOW/RED scorecard. Re-runs stale (>2h) audits in-process. Auto-fires 17:00 ET via `Gamma_GymSession`; pure Python, `$0/fire. | `/gym-session` or `python -m autoresearch.gym_session [--date]` |
| **`skill-tune`** (Skills Pipeline #5, OP-29) | Fine-tuning loop. Replays a target skill across N historical weekdays with monkey-patched parameter values, measures detection rate, recommends best threshold. Writes DRAFT to `_skill-inbox/` (or `_lesson-inbox/` if denylisted per Rule 9). Pure Python, $0. | `python -m autoresearch.skill_tune --skill {slug} --param {name} --range start,stop,step` |
| **`j-winner-audit`** (OP-16 gate) | Compute OP-16 edge_capture scorecard for any candidate params. Classifies each of J's 7 source-of-truth days as CAUGHT / MISSED / AVOIDED / OVERTRADED. Verdict: PROMISING (≥$771) or REJECTED (<$771). Writes JSON + MD report to `analysis/j-edge/`. Replaces one-shot `audit_j_winners.py`. | `python -m autoresearch.j_winner_audit [--params path] [--slug label]` |
| **`swarm-health`** (OP-25 foot-gun: silent swarm failure) | Check `automation/swarm/state/swarm_output.json` freshness + status. Emits SWARM_OK / SWARM_STALE / SWARM_DEGRADED / SWARM_FAILED. Appends flag to STATUS.md on non-OK. Invoke at premarket Step 1c before reading swarm context. | `python -m autoresearch.swarm_health [--stale-hours N] [--no-status-write]` |

---

## 2. Python diagnostic tools (re-runnable)

### Heartbeat / chart-data audits

| Tool | Purpose | When to run | CLI |
|------|---------|-------------|-----|
| `backtest/autoresearch/heartbeat_tick_audit.py` | Classify every heartbeat tick on a given day (ALIGNED / MISALIGNED-BENIGN / MISALIGNED-CRITICAL / STALE_PAUSED / NO_DATA). Auto-included in EOD pipeline at Stage 4a.4. | After any heartbeat.md change, daily via EOD, ad-hoc when J questions a specific tick | `cd backtest && python -m autoresearch.heartbeat_tick_audit --date 2026-05-14` |
| **`backtest/autoresearch/heartbeat_pulse_check.py`** | Python port of `heartbeat-pulse-check.ps1`. Reads the heartbeat log file, measures gaps between consecutive FIRE lines during 09:30-15:55 ET, returns GREEN/YELLOW/RED verdict. GREEN = all gaps ≤6 min; YELLOW = 1+ gaps 6-15 min; RED = any gap >15 min or zero market-hour fires; NOT_APPLICABLE = weekend / no log. Used by `gym_session.py` stale-rerun path when the PS1 output file is missing. Writes `automation/state/heartbeat-pulse-check-{date}.json`. | Daily via gym_session.py (auto-rerun if stale >2h); ad-hoc when rate-limit or scheduling issues suspected | `cd backtest && python -m autoresearch.heartbeat_pulse_check --date YYYY-MM-DD` |
| **`backtest/autoresearch/heartbeat_decision_trace.py`** | Per-tick filter walk: walks filter 1-11 against decisions.jsonl + params.json. Output per-filter PASS/BLOCK table + bull/bear blockers. Pure diagnostic. | When J asks "why did tick #N do X?" | `python -m autoresearch.heartbeat_decision_trace --date 2026-05-14 --tick 27` |
| **`backtest/autoresearch/chart_data_verify.py`** | Cross-check trailing N closed 5m SPY bars: CSV vs yfinance. RED if divergence > $0.10. LLM-mode adds TradingView 3-way check. | Daily post-EOD; pre-market; on T76-style data-source suspicion | `python -m autoresearch.chart_data_verify --date 2026-05-14 --bars 5` |
| **`backtest/autoresearch/pin_chain_verify.py`** | Verify rule_version pin chain: params.json + heartbeat.md + premarket.md. RED on drift; reports proposed fix-diff but NEVER auto-edits (rule 9). | Daily Stage 0 self-test; after rule_version bump; before backtest ratification | `python -m autoresearch.pin_chain_verify` |
| **`backtest/autoresearch/gym_session.py`** (OP-29) | Daily gym-session aggregator. Reads 7 audit scorecards + re-runs stale ones + writes unified GREEN/YELLOW/RED scorecard. Auto-fires 17:00 ET via `Gamma_GymSession`. | Daily post-EOD; pre-promotion of any candidate strategy; ad-hoc audit | `cd backtest && python -m autoresearch.gym_session --date YYYY-MM-DD` |
| **`backtest/autoresearch/skill_tune.py`** (OP-29) | Parameter sweep against a target skill across N historical weekdays. Produces sweep table + recommendation + DRAFT update item. Target skill must expose `evaluate_at(date, **overrides)` adapter. | When a threshold seems mis-calibrated; when Analyst queues `kind: tune` to `_skill-inbox/` | `cd backtest && python -m autoresearch.skill_tune --skill {slug} --param {name} --range start,stop,step --window N` |

### Watcher-fleet diagnostics

| Tool | Purpose | When to run | CLI |
|------|---------|-------------|-----|
| `backtest/autoresearch/_smoke_watchers.py` | Run the silent watchers (vwap / odf / pff) directly on today's bars + full-day scan. Bypasses runner.py confidence filter to surface raw detector behavior. | When watcher-observations.jsonl shows 0 obs for a date that should have signals | `cd backtest && python autoresearch/_smoke_watchers.py` |
| **`backtest/autoresearch/watcher_state_inspector.py`** | Dump `_orb_state[date]` and `_odf_state[date]` module-level dicts after running T82 warmup loop. Verify state machines progressing as expected. | Daily post-15:55 ET; after watcher_live.py warmup change; on suspicious 0-obs sessions | `python -m autoresearch.watcher_state_inspector --date 2026-05-14` |
| `backtest/autoresearch/_smoke_vwap_diag.py` | Trace per-bar failure reason for vwap_watcher (proximity / body / vol / rejection / ribbon). | When VWAP fires 0 times on a session you expected fires | `python backtest/autoresearch/_smoke_vwap_diag.py` |
| `backtest/autoresearch/t80_orb_bull_regression.py` | Bypass runner.py L98+L104 medium-confidence filter and trace raw ORB/BULL detector returns across N dates. Used to pinpoint regression boundaries. | When silent-failure regression suspected | `python backtest/autoresearch/t80_orb_bull_regression.py` |
| `backtest/autoresearch/t82_orb_warmup_test.py` | 3-scenario test for stateful-watcher fix: SEQUENTIAL / FRESH / PROD-MIMIC. Validates that warmup recovers state-machine fires. | Before patching watcher_live.py to add a new stateful-watcher warmup | `python backtest/autoresearch/t82_orb_warmup_test.py` |
| `backtest/autoresearch/t62_t63_verify.py` | Verifies T62 multi_day_rth invariant + T63 stderr unmask shipped to runner.py | After any runner.py change to confirm silent-except removal still works | `python backtest/autoresearch/t62_t63_verify.py` |

### Engine-state / trace tools

| Tool | Purpose | When to run | CLI |
|------|---------|-------------|-----|
| `backtest/autoresearch/trace_j_entries.py` | Reproduce J's exact entry decisions on historical days against current engine doctrine. Used for "would the engine catch this?" gap analysis. | When J asks "would v15 have entered my 5/13 trade?" | `python backtest/autoresearch/trace_j_entries.py` |
| `backtest/autoresearch/v15_j_edge_test.py` | OP-16 J-edge score harness — measures `edge_capture` across J anchor days for the current engine | Before any rule_version bump | `python backtest/autoresearch/v15_j_edge_test.py` |
| **`backtest/autoresearch/j_winner_audit.py`** | Parameterized OP-16 scorecard. Runs a single-window backtest over J's 7 anchor days (4/29-5/07), computes edge_capture, classifies CAUGHT/MISSED/AVOIDED/OVERTRADED, writes JSON + MD to `analysis/j-edge/`. Supports `--params` for any candidate and `--slug` for labeling. Intended to replace one-off J-audit scripts. | Before any candidate ratification brief; after any heartbeat.md change; when J asks "what's our edge capture?" | `cd backtest && python -m autoresearch.j_winner_audit [--params path] [--slug label]` |
| `backtest/autoresearch/self_audit.py` | Hourly engine-state self-audit (consistency between current-position.json / decisions.jsonl / Alpaca orders) | Hourly via Gamma_SelfAudit task | `python backtest/autoresearch/self_audit.py` |
| `backtest/autoresearch/alt_scoring_audit.py` | Re-score grinder keepers with alternate floors (loose / strict / J-edge primary) | When grinder produces 0 keepers but candidates show wide_pnl gains | `python backtest/autoresearch/alt_scoring_audit.py` |

### Stress / regime / robustness

| Tool | Purpose | When to run | CLI |
|------|---------|-------------|-----|
| `backtest/autoresearch/sub_window_test.py` | Test a candidate's per-quarter stability across the 16-month backtest window | Before ratifying any candidate (Stage 4 gate) | `python backtest/autoresearch/sub_window_test.py` |
| `backtest/autoresearch/stress_test_seed6.py` | Stress-test a specific seed against regime variations | When a candidate looks too good on aggregate (overfit suspicion) | `python backtest/autoresearch/stress_test_seed6.py` |
| `backtest/autoresearch/trade_5_13_variants.py` | 4,410-combo grid replay of 5/13 11:38 bullish reclaim — found J's "buy under $100" style outperforms ITM-1 on % gain | When a single trade needs deep variant analysis | `python backtest/autoresearch/trade_5_13_variants.py` |
| **`backtest/autoresearch/combination_search.py`** (Cycle-18, 2026-05-20) | Systematic combo search across 6 dimensions (detector × regime × proximity × confidence × time × VIX) — ~3,888 combos at full corpus. Calls existing `pattern_backtest.run_pattern_backtest` per day, harvests per-hit records, re-filters at aggregate-time, ranks survivors by sign-safe `edge_capture × sharpe_proxy` (per OP-16) with OP-20 gates (min_n / WR floor / month stability / max concentration). Outputs `analysis/combination-search-{range}.{json,md}` leaderboard. Observer-only per OP-22/OP-25 — survivors graduate via OP-21 watcher path, never direct heartbeat wiring. | When tuning detector × filter stacks for the watcher fleet; pre-promotion screening; nightly autoresearch | `cd backtest && python -m autoresearch.combination_search --range START END [--min-n] [--wr-floor] [--no-vix] [--top-n]` |

### Swarm hypothesis engine diagnostics

| Tool | Purpose | When to run | CLI |
|------|---------|-------------|-----|
| `automation/swarm/swarm_grader.py` | Grade swarm consensus vs actual SPY direction for a given day. Appends to `analysis/swarm-scorecard.jsonl` and rebuilds `analysis/swarm-scorecard.json` aggregate. | Called automatically by EOD Section 8d; also ad-hoc to backfill a missed day | `python automation/swarm/swarm_grader.py --date YYYY-MM-DD --actual-bias bullish\|bearish\|no_trade` |
| *Swarm output inspection* | Read `automation/swarm/state/swarm_output.json` directly to inspect `vote_map`, `consensus_bias`, `swarm_confidence`, `dissent_flag`, and `level_priority[]` for today's run | When premarket shows `SWARM_DISSENT` or `SWARM_LOW_CONVICTION` and you want detail | `Get-Content automation/swarm/state/swarm_output.json | ConvertFrom-Json` |
| *Scorecard aggregate* | Read `analysis/swarm-scorecard.json` for overall swarm accuracy, per-agent accuracy, confidence calibration, and Phase 2 eligibility | Weekly review; when checking if 20-day Phase 2 gate is met | `Get-Content analysis/swarm-scorecard.json | ConvertFrom-Json` |
| *Runner log* | Daily swarm execution log in `automation/state/logs/swarm-premarket-YYYY-MM-DD.log` | When swarm_output.json is missing or stale and you need to know why | `Get-Content automation/state/logs/swarm-premarket-YYYY-MM-DD.log` |
| **`backtest/autoresearch/swarm_health.py`** | Check `swarm_output.json` status + staleness (>4h). Returns SWARM_OK / SWARM_STALE / SWARM_DEGRADED / SWARM_FAILED verdict. Appends STATUS.md flag on non-OK. Exit 0 = OK, exit 1 = degraded. | Premarket Step 1c before reading swarm context; after overnight swarm failure; daily gym_session | `cd backtest && python -m autoresearch.swarm_health [--stale-hours N] [--no-status-write]` |

**Swarm health one-liner (check output freshness + task status):**
```powershell
$s = Get-Content automation\swarm\state\swarm_output.json -ErrorAction SilentlyContinue | ConvertFrom-Json
"swarm generated_at=$($s.generated_at) bias=$($s.consensus_bias) confidence=$($s.swarm_confidence)"
Get-ScheduledTask -TaskName 'Gamma_SwarmPremarket' | Get-ScheduledTaskInfo | Select LastTaskResult,NumberOfMissedRuns,LastRunTime
```

### EOD pipeline (auto-runs nightly via Gamma_EodDeepDive)

| Module | Purpose | Invocation |
|--------|---------|------------|
| `backtest/autoresearch/eod_deep/main.py` | 13-category EOD deep-dive orchestrator. Auto-runs at 16:05 ET via Gamma_EodDeepDive | `cd backtest && python -m autoresearch.eod_deep.main --date YYYY-MM-DD` |
| `backtest/autoresearch/eod_deep/modules/forensics.py` | Phase 2.3 winner-forensics — tight fingerprint matching + simulator_real hit-rate | called from main.py |
| `backtest/autoresearch/eod_deep/modules/detection.py` | Phase 3 orchestrator-replay — engine-actual diff per RTH bar | called from main.py |
| `backtest/autoresearch/eod_deep/drift.py` | 30-day P&L distribution proxy — drift_check verdict | called from main.py |
| `backtest/autoresearch/eod_deep/knob_round_trip.py` | Per-trade ±2-level sweep across 7 v15 knobs (Phase 2.5 + 2.6 analog fallback) | called from main.py |
| `backtest/autoresearch/eod_deep/feedback.py` | Auto-dispatch findings to queue.jsonl / alerts.jsonl / lessons-candidates.jsonl with fingerprint-hash dedupe | called from main.py |

---

## 3. PowerShell audit scripts (system-level)

| Script | Purpose | When to run | Command |
|--------|---------|-------------|---------|
| **`setup/scripts/heartbeat-pulse-check.ps1`** | Verify Gamma_Heartbeat scheduled task fired on schedule today. RED if any 15-min gap during market hours. Auto-heals task-Disabled state with `-Heal`. | Daily; post-market; on suspicious silence | `& setup\scripts\heartbeat-pulse-check.ps1 [-Date YYYY-MM-DD] [-Heal]` |
| **`setup/scripts/heartbeat-mcp-self-test.ps1`** | Verify TV CDP port 9222 listening + alpaca-mcp process alive. Auto-heals TV via kill+launch. | Stage 0 of every wake fire; pre-market; after-midnight; mid-session if ERROR_TV recurs | `& setup\scripts\heartbeat-mcp-self-test.ps1 [-Heal]` |
| `setup/scripts/fire-stage0-selftest.ps1` | Full Stage 0 self-test for any wake fire — TV CDP + Discord + cron + budget + STATUS freshness | Every wake fire (per wake-protocol.md) | `& setup\scripts\fire-stage0-selftest.ps1` |
| `setup/scripts/preflight-readiness-audit.ps1` | Full pre-market readiness audit — verifies all 11 Gamma_* tasks Ready + pin chain intact + state files clean | Daily ~04:30 ET overnight fire | `& setup\scripts\preflight-readiness-audit.ps1` |
| `setup/scripts/overnight-health-check.ps1` | Health-check for the wake-fire harness itself (cron alive, STATUS fresh, queue non-empty) | When a fire suspects the harness is broken | `& setup\scripts\overnight-health-check.ps1` |
| `setup/scripts/audit-silent-watcher-days.ps1` | Per-watcher observation count last N days — flags silent-failure patterns | When debugging watcher-observations.jsonl gaps | `& setup\scripts\audit-silent-watcher-days.ps1` |
| `setup/scripts/opra-cache-audit.ps1` | OPRA contract cache integrity audit (file count, size, J-anchor day coverage) | Before any real-fills validation run | `& setup\scripts\opra-cache-audit.ps1` |
| `setup/scripts/opra-anchor-spotcheck-v2.ps1` | Verify all 8 J-anchor days have ±$5 strike windows in OPRA cache | Same — pair with cache-audit | `& setup\scripts\opra-anchor-spotcheck-v2.ps1` |
| `setup/scripts/verify-news-json.ps1` | Validate news.json schema + freshness (date matches today, has events_today array, all severities valid) | Before any premarket fire | `& setup\scripts\verify-news-json.ps1` |
| `setup/scripts/ensure-discord-bridge-alive.ps1` | Restart Discord bridge if PID dead. Watchdog uses this. | When bridge dies | `& setup\scripts\ensure-discord-bridge-alive.ps1` |

---

## 4. Tool selection guide (when you suspect X, run Y)

| Symptom / question | First diagnostic |
|--------------------|------------------|
| Heartbeat made a strange decision today | `python -m autoresearch.heartbeat_tick_audit --date YYYY-MM-DD` |
| **Why did heartbeat tick #N do X?** | **`python -m autoresearch.heartbeat_decision_trace --date YYYY-MM-DD --tick N`** |
| **Heartbeat went silent for 15+ min** | **`& setup\scripts\heartbeat-pulse-check.ps1 [-Heal]`** or **`python -m autoresearch.heartbeat_pulse_check --date YYYY-MM-DD`** (Python equivalent used by gym_session stale-rerun) |
| **TV chart returns "fetch failed" or ERROR_TV in heartbeat** | **`& setup\scripts\heartbeat-mcp-self-test.ps1 -Heal`** (auto-restarts TV) |
| **rule_version drift suspected** | **`python -m autoresearch.pin_chain_verify`** |
| **CSV vs live data sources disagree** | **`python -m autoresearch.chart_data_verify --date YYYY-MM-DD`** |
| **ORB / ODF watcher state machine stuck** | **`python -m autoresearch.watcher_state_inspector --date YYYY-MM-DD`** |
| Watcher fired 0 times on a session you expected fires | `python autoresearch/_smoke_watchers.py` (full-day scan) |
| One specific watcher silent — was it the detector or the runner? | `t48_sniper_*.py` pattern (detector vs watcher wrapper test) |
| New stateful watcher returns None in production | `t82_orb_warmup_test.py` 3-scenario pattern |
| Engine entered/exited at "wrong" price | `python -m autoresearch.heartbeat_tick_audit` to see if mid-bar misalignment caused it |
| A historical winner doesn't repro on new doctrine | `trace_j_entries.py` |
| **"What's our OP-16 edge_capture?" or "did the engine catch [J-day]?"** | **`python -m autoresearch.j_winner_audit [--params path] [--slug label]`** (or `/j-winner-audit`) |
| New strategy ratification readiness | `sub_window_test.py` + `simulator_real` real-fills + walk-forward |
| **Tune detector × filter combinations (which stack maximizes edge?)** | **`cd backtest && python -m autoresearch.combination_search --range START END`** (OP-16 ranked leaderboard) |
| Wake fire harness broken | `setup\scripts\overnight-health-check.ps1` |
| Pre-market 08:30 ET pin chain | `setup\scripts\preflight-readiness-audit.ps1` |
| **Daily chart-reading "physical exam" (overall engine green/red)** | **`cd backtest && python -m autoresearch.gym_session`** (or `/gym-session`) |
| **Threshold tuning suspicion on an audit skill** | **`cd backtest && python -m autoresearch.skill_tune --skill {slug} --param {name} --range {r}`** |
| **EOD finding → new gym validator** | Drop item to `strategy/candidates/_validator-inbox/`, wake fire picks up via `/validator-author` (OP-29) |
| **EOD finding → new diagnostic skill** | Drop item to `strategy/candidates/_skill-inbox/`, wake fire picks up via `/skill-author` (OP-29) |
| **EOD finding → encode lesson into doctrine** | Drop item to `strategy/candidates/_lesson-inbox/`, wake fire picks up via `/lesson-author` (OP-29) |
| **Swarm output missing / stale / failed at premarket** | `python -m autoresearch.swarm_health` — emits SWARM_OK / SWARM_STALE / SWARM_DEGRADED / SWARM_FAILED + flags STATUS.md on non-OK |
| **Swarm output missing/stale at premarket (detail log)** | Check `automation/state/logs/swarm-premarket-YYYY-MM-DD.log` for SWARM_FAIL/TIMEOUT; re-run `python automation/swarm/runner.py` manually if needed |
| **Swarm accuracy after N trading days** | `python automation/swarm/swarm_grader.py` (backfill) → read `analysis/swarm-scorecard.json#phase2_eligibility` |
| OPRA cache missing days | `setup\scripts\opra-cache-audit.ps1` |
| Watcher fleet silent-failure suspicion | `setup\scripts\audit-silent-watcher-days.ps1` |

---

## 5. Adding a new skill — protocol

When you build a new diagnostic / audit tool that's likely to be useful again:

1. **Place it correctly:**
   - Python: `backtest/autoresearch/{descriptive-name}.py` with `--date` or similar parameterization
   - PowerShell: `setup/scripts/{descriptive-name}.ps1`
   - Claude Code skill: `.claude/skills/{name}/SKILL.md` (one dir per skill, SKILL.md inside)

2. **Make it parameterized + re-runnable:**
   - Don't hardcode dates / paths
   - Take CLI args (argparse for Python, `param()` for PowerShell)
   - Auto-discover input files where possible

3. **Add an entry to this catalog** (`docs/SKILLS-CATALOG.md`) under the right category. Include: tool name, purpose, when to run, CLI invocation.

4. **Cross-link from CLAUDE.md OP-25 lessons absorbed** if it encodes a foot-gun prevention.

5. **If it's auto-runnable nightly, wire it into EOD pipeline** (`backtest/autoresearch/eod_deep/main.py`) so it doesn't need manual triggering.

---

## 6. Cross-references

- **Wake-fire operating manual:** `automation/overnight/wake-protocol.md`
- **Doctrine + lessons absorbed:** `CLAUDE.md` (especially OP-25 "Lessons absorbed")
- **Anti-patterns + foot-guns:** `docs/LESSONS-LEARNED.md`
- **Backtest playbook:** `docs/BACKTESTING-PLAYBOOK.md`
- **Future improvements:** `docs/FUTURE-IMPROVEMENTS.md`

---

_Last updated: 2026-05-19T23:45 ET (EOD pipeline audit: `heartbeat_pulse_check.py` Python module added to Section 2 + tool-selection-guide; 5 gym_session.py key-name/encoding bugs fixed; 4 broken persona scripts repaired; `heartbeat_pulse_check.py` wired into gym stale-rerun path)._
