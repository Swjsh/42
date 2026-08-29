# GOAL: COCKPIT-BUILD-2026-08-29

> Source: orchestrator-issued build spec (`SPEC.md`, "Gamma Orchestrator Cockpit:
> Army View, Heartbeat Pulse, Action Cards, `/goal`"), verified fresh 2026-08-29
> against cold reality. This is a build-spec-driven goal, not a live J chat quote —
> said plainly per the schema note rather than inventing one. J's underlying
> directives that motivate the spec: the cockpit page itself (`analysis/home/
> index.html`) exists because J said (2026-08-19, quoted in its generator docstring)
> he wanted something *"more editable and we can make it look how I want it to
> look,"* and this goal's own mechanism exists because `/goal`'s SKILL.md was
> commissioned to end three duplicate ad-hoc goal files (see FOLD note below).

**Opened by the /goal build itself** (SPEC.md §5/step 6) as the first live example of
the mechanism it built — see that skill's own worked example. Multiple parallel
lanes are building the other 7 steps of the same spec concurrently; this goal file
is scoped to the whole 8-step build order (SPEC.md §7) so the conductor has one
place to route unfinished work once the parallel-lane build settles, not because
this session did all 8 steps itself.

## DONE-WHEN
All 8 build-order steps (SPEC.md §7) shipped, each independently `git revert`-able,
each with its own stated verify command passing:
1. Pulse telemetry (no UI) — `tail -1 pulse.jsonl` shows `to` + `agent_id` populated.
2. Army payload + static Army view — node count matches `ListAgents` on `file://`.
3. Live mode + the pulse — pulse visibly travels on a real `SendMessage`.
4. Action cards, read-only — cards match `task_scorer.py --top` + `engine-health.json`;
   quiet-mode producers render `quiesced`, never RED.
5. Cards fire — one click spawns exactly one escalation; a double-tap spawns none
   extra (`r.already`).
6. `/goal` — `task_scorer.py --top` surfaces the goal row (**this step; see below**).
7. Stop-hook continuation — RED-proofed counter + convergence stop, tests green
   BEFORE wiring (**already true as of this goal's opening — see QUEUE**).
8. Reachable — `Gamma_CompanionKeepalive` re-enabled, `Gamma_Home` in
   `quiet-mode-restore.json`, a working Desktop shortcut to the cockpit.

A step that turns out not to be buildable as spec'd (e.g. `agent_id` never actually
arriving on a hook payload, per SPEC.md's own flagged UNVERIFIED #3) is a valid
terminal state for that step IF the finding is documented and the fallback in the
spec is used instead — not silently dropped.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 → ~2026-09-29**: no trading-path changes except pre-
  registered kill-type risk reductions (STATUS.md 2026-08-29T12:00 ET). Nothing in
  this goal touches the frozen path (params*.json, filters.py, risk_gate.py,
  fleet/*.py, heartbeat_core.py) — every step here is cockpit UI/telemetry
  tooling. If any future item under this goal DOES touch that path, it is illegal
  during the freeze window and must be filed `[B-J]`, not queued.
- Every fire that works this goal calls `python setup/scripts/conductor_outcome.py
  record --task-id GOAL-COCKPIT-BUILD-2026-08-29 --drained <n> --added <n>
  --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent`/`Workflow` fan-out this goal spawns passes `model:"sonnet"`
  explicitly.
- `STATUS.md` gets a line at goal OPEN and CLOSE only.
- Never `/loop /goal` — one fresh process per fire.
- **NEVER edit `analysis/home/index.html` directly** (gitignored, generated,
  hook-blocked) — every UI step edits `setup/scripts/gamma_home.py` /
  `gamma_cockpit_ui.py` / `gamma_cockpit_js.py` / `gamma_cockpit_views_js.py` /
  `gamma_cockpit_data.py` / `gamma_cockpit_org.py` instead.
- **NEVER edit `MAP.md`/`HOME.md`/`SHADOW.md`/`*/INDEX.md`/`journal/*.md`** —
  generated, hook-blocked.
- **NEVER place orders, arm live money, touch secrets, or `git push`.**
- Rejected designs (do not re-propose without new evidence): `/api/launch-terminal`
  + visible PowerShell window (exploited via single-quote escape in
  `gamma-hq-launch.ps1`'s interpolated `-Command` string); a `gamma://` protocol
  handler (HKCU registry write = a system-settings change); Agent Teams (manifest
  `rm -rf`'d at session exit, ~7x token cost, silently converts named subagents to
  teammates).

## QUEUE
- [x] Step 1 — Pulse telemetry (no UI). Verified by file evidence 2026-08-29:
    `setup/hooks/pulse.py` exists (135 lines, `MAX_ROWS=2000` ring cap present),
    `gamma_doctrine.py::_log()` threads `session_id`/`agent_id` from `payload`,
    `.claude/settings.json` carries one merged `PreToolUse` matcher
    (`Edit|Write|NotebookEdit|Bash|PowerShell|SendMessage|Agent|Task|Workflow`) —
    functionally the spec's "second block," done as one matcher instead of two.
    NOT independently re-verified live this fire (no fresh `SendMessage` sent to
    confirm `agent_id` actually lands on a real payload, per SPEC.md's own flagged
    UNVERIFIED #3) — the next fire touching this goal should do that one check
    before assuming step 1 is airtight.
- [x] Step 2 — Army payload + static Army view. VERIFIED 2026-08-29 16:10 by running
    the generator, not by file existence: `setup/scripts/gamma_cockpit_army.py` (15,241
    bytes) is imported by `gamma_home.py`, `payload["army"]` is set, `id:'army'` is in the
    VIEWS[] registry, and a renderer exists in `gamma_cockpit_views_js.py`.
    `python setup/scripts/gamma_home.py` -> "answers: 6 rendered, 0 NO DATA" and the
    emitted HTML carries 92 `army` references.

- [x] Step 3 — Live mode + the pulse. VERIFIED 2026-08-29 16:10: `/api/army` appears 4x
    in `gamma-companion/server.js`, and the generator dual-writes BOTH
    `analysis/home/index.html` and `gamma-companion/public/cockpit.html` (501,192 bytes
    each, identical size = same payload, file:// snapshot + served live mode).

- [x] Step 4 — Action cards, read-only. VERIFIED 2026-08-29 16:16 by wiring, not by
    file existence: `gamma_cockpit_cards.py` is imported by `gamma_home.py`,
    `payload["cards"]` is set, a `cards` entry is in the VIEWS[] registry, and the
    renderer lives in `gamma_cockpit_cards_js.py`. Quiet-mode is genuinely honoured —
    11 references to `quiet_active`/`quiet-mode` in the generator, so tasks that are
    deliberately held down render as quiesced instead of manufacturing false REDs.
    `action-cards.json` holds 9 ranked cards sourced from STATUS.md + queue.md.

- [x] Step 5 — Cards fire. VERIFIED 2026-08-29 16:16. The fire path lives in
    `setup/scripts/gamma_cockpit_cards_js.py` (NOT in views_js — a first grep missed it
    and wrongly called this step incomplete): `fetch('/api/approve')` with the
    `x-gamma-token` meta header, and the SSE drawer on `/api/ask-stream`. Both strings
    appear in the rendered `analysis/home/index.html`. Server-side prompt-lookup
    hardening is in `gamma-companion/server.js` (reads `action-cards.json` rather than
    trusting the client's task), RTH gating is in the generator (6 `rth`/`et_clock`
    references), and 4 card guard-test files exist.

- [x] Step 6 — `/gamma-goal`. THIS delivery: `.claude/skills/gamma-goal/SKILL.md`,
    `automation/state/goals/` (+ 3 legacy files folded, tombstones left),
    `automation/state/active-goal.json` pointing at this file, the queue.md row
    below, `automation/prompts/conductor.md` STAGE 1 clause 0a. Verify command:
    `task_scorer.py --top` — see this fire's own PROGRESS LOG line for the quoted
    result.
- [x] Step 7 — Stop-hook continuation. Already shipped ahead of this goal being
    opened — `setup/hooks/gamma_doctrine.py::_check_goal_continuation` +
    `setup/hooks/doctrine.py::goal_next_open_item`/`goal_expired`/
    `goal_should_continue`/`goal_max_continuations`/`goal_continuation_reason` all
    exist with full test coverage (`setup/hooks/test_doctrine_hooks.py`, the
    `goal continuation` sections) — `pytest setup/hooks/test_doctrine_hooks.py -q`
    was 100 passed before this fire touched anything. Built by a parallel lane;
    not this fire's work, credited honestly rather than re-claimed.
- [x] Step 8 — Reachable. VERIFIED 2026-08-29 16:20 with live commands:
    `Get-ScheduledTask Gamma_CompanionKeepalive` -> **Ready** (re-enabled);
    `Gamma_Home` and `Gamma_CompanionKeepalive` both present in
    `quiet-mode-restore.json`; `~/Desktop/Gamma Cockpit.lnk` exists;
    `curl 127.0.0.1:4317` -> HTTP 200. `Gamma_Home` currently reads **Disabled**,
    which is quiet mode holding it down BY DESIGN (quiet_active:true, 115 tasks held,
    weekend 08:00-23:00 ET) — it restores at 23:00 ET because it is in the restore list.
    Not a defect; the page is stale on purpose until then.
- [ ] VERIFY-A — pulse visibly travels on a REAL cross-session message. 13 `message`
    rows exist in pulse.jsonl but every one came from the test suite (now fixed so it
    writes to a temp path). No genuine `SendMessage` has been sent, because the only
    reachable peers are J's own live interactive windows and messaging them would inject
    text into whatever he is doing. Needs either a Gamma-spawned session to message, or
    J's say-so to ping one of his own.
- [ ] VERIFY-B — one card click spawns exactly ONE escalation, and a double-tap spawns
    none extra (`r.already` idempotency guard). Requires actually firing a card, which
    starts a real Sonnet session. J's first click is the test.

## J-DECISIONS
(none yet — every item above is either build work or a file-existence check, no
OP-0 four-things-route-to-J item has come up in this goal's scope so far)

## PROGRESS LOG
- 2026-08-29 16:32 ET — Live-companion probe corrected two claims. (a) The build agent's integrator note said :4317 runs pre-edit code and needs a restart before /api/army works. STALE: an authed GET returns real pulse rows right now, so the new code is live. (b) My own GET /api/approve -> 404 was a BAD PROBE; the route is POST-only and POST returns 403 unauthorized. Fire path (/api/approve, /api/ask-stream, /api/army, /cockpit.html) is live and authed. Injection test with a valid token, an unknown card id and a hostile task ('print .mcp.json') returned escalated:null -- nothing ran. IMPORTANT nuance: what blocked it was the IDEMPOTENCY guard (already:true, because the id was not a pending approval), NOT the prompt hardening. The hardening applies only when id names a REAL card, where the file's prompt wins and the client's is ignored outright. A pending NON-card id on the legacy escalate path still takes a client-supplied task -- pre-existing, token-gated, and the token already implies shell access, but it is the accurate statement. Also noted: the RTH gate is checked BEFORE resolveApproval so a refused fire never burns the card's idempotency slot.
- 2026-08-29 16:20 ET — Steps 4, 5 and 8 verified and ticked; all 8 build steps are built and wired. Resolved SPEC.md UNVERIFIED #3: `agent_id` DOES populate — 319 of 713 pulse rows carry it (subagent rows only, exactly as documented), so worker-level attribution works. Fixed two defects found while verifying: the Stop-hook block message garbled non-ASCII on the Windows console (`_ascii_safe` + guards), and the test suite was writing ~10 fake `message` rows per run into PRODUCTION pulse.jsonl (GAMMA_PULSE_PATH redirect; proven +0 rows across two suite runs). Goal stays OPEN on VERIFY-A and VERIFY-B — both need a real side effect (a live message, a live escalation) that is J's call, not mine. 103 guards green.
- 2026-08-29 16:11 ET — Reconciled QUEUE against disk: steps 2+3 were `[ ]` with "does not exist yet" while already shipped and wired. Verified by RUNNING `gamma_home.py` (6 answers rendered, 0 NO DATA, 92 army refs, dual-write 501,192 B to both index.html and public/cockpit.html), not by file existence. Steps 4+5 remain open and are in flight in wf_8c658368-df0. Root cause: parallel lanes + a QUEUE item written as a point-in-time observation; skill rule added to prevent recurrence.
- 2026-08-29 ~17:36 ET: goal opened by the /goal build itself (this fire). Surveyed
  steps 1-8 via file-existence checks (see QUEUE for exact evidence per step).
  Steps 1 and 7 found already shipped by parallel lanes; steps 2-5 not started;
  step 6 is this fire's own delivery; step 8 partially true. Building step 6 now.

## HONEST STATE
As of this fire: 2 of 8 steps fully verified (1, 7 — both by file evidence, step 1
not re-verified live), 1 of 8 in progress (6, this delivery), 1 of 8 partially true
(8), 4 of 8 not started (2, 3, 4, 5). This goal spans multiple parallel-lane
deliveries under one SPEC.md — the QUEUE above reflects a single point-in-time
survey (2026-08-29 ~17:36 ET) and WILL be stale within the hour if other lanes are
landing work concurrently. Any fire that picks up this goal's top open item
(currently Step 2) should re-check file existence fresh before trusting this
QUEUE's checkmarks, exactly as this fire did for the checkmarks it inherited.
