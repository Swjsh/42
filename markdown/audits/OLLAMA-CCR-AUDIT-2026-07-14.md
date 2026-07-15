# CCR / Ollama Gateway Audit — 2026-07-14

**Scope:** read-only investigation. Nothing in this doc was applied — every fix below is
PROPOSED-FOR-J-APPROVAL. Current live state (as of 21:01 ET / 19:03 local, verified via
`et_clock.py` + `Get-Date`) confirms the interactive lockout is currently fixed and stable, but
one real residual gap remains in the guard's restart-timing (§2), and headless auth needed a
`/login` that nothing has yet turned into a standing check.

---

## 1. What happened (both lockouts) + what J turned off

**Two distinct, stacked failures — not one bug wearing two faces.**

### Failure A — interactive lockout (Monday full workday, recurred briefly this morning)

- **Mechanism:** on 2026-07-08 the "brain sovereignty" initiative wired `claude-code-router`
  (CCR) under *every* `claude` fire by writing `apiKeyHelper` + an `env` block
  (`ANTHROPIC_BASE_URL` / `ANTHROPIC_API_BASE_URL` / `CLAUDE_AGENT_API_BASE_URL` all pointed at
  `http://127.0.0.1:3456`) into `~/.claude/settings.json` — the one global file **every**
  `claude` entrypoint reads by default: J's Desktop app, bare terminal `claude`, *and*
  automation. There was never a distinction between "automation opts into cheap local routing"
  and "J's interactive tools need Anthropic, always."
- **Why it was silent:** `~/.claude-code-router/config.json` (read fresh this session, quoted
  verbatim):
  ```json
  "Router": {
    "default": "ollama,qwen3.6:35b",
    "background": "ollama,qwen3:14b",
    "think": "ollama,qwen3.6:35b",
    "longContext": "ollama,qwen3.6:35b",
    "longContextThreshold": 60000
  }
  ```
  Zero Anthropic provider entry, anywhere. So the moment CCR's gateway is listening on
  port 3456 — even mid-boot, even before its fuller profile stack is live — every
  default-routed request, including J's Desktop app, silently resolves to local Ollama. No
  error, no refused connection, just a much weaker model answering. The existing keepalive
  only TCP-probed the port ("is something listening"), which is a different fact from "is it
  serving real Claude" — so the probe read `port_up: true` the entire time J was locked out.
- **What J turned off (the actual fix, already shipped, commit `559d6a5`, 06:00 ET this
  morning):** `apiKeyHelper` + the `env` block were **removed from `~/.claude/settings.json`**.
  Backup preserved at `~/.claude/settings.json.pre-ccr-fix-2026-07-14.bak` (read this session —
  confirms the pre-fix file had the hijack). This is the "turned something off" J's remembering
  — he (or the session working with him) stripped CCR's global default route so Desktop/CLI hit
  `api.anthropic.com` directly, unconditionally. **This part is correct and did not leave
  anything half-broken** — verified below.
- **Confirmed live, not simulated, by the fixing session itself (quoted from commit
  `559d6a5`):** they killed and restarted CCR via the keepalive's own restart command, and
  CCR's *own* `start` sequence **re-injected the identical hijack** back into
  `~/.claude/settings.json`. This is the "vulnerability window": **any CCR restart —
  reinstall, `ccr code` re-sync, or the keepalive's own down→restart path — puts the hijack
  back**, and only the periodic guard (added same commit) catches it.
- **Real-world proof this window is real, not theoretical:** the day's own log
  (`automation/state/logs/ccr-keepalive-2026-07-14.log`), quoted:
  ```
  [2026-07-14 06:07:34] INTERACTIVE SETTINGS LEAK FIXED: ["env.ANTHROPIC_BASE_URL='http://127.0.0.1:3456' points at the CCR gateway", ...]
  ```
  This is the ONE leak event today — it happened at 06:07:34, seven minutes after the fixing
  session's live-verification restart, caught by the very next scheduled 5-minute tick. Zero
  further leak events logged through 20:57:34 (the state file `automation/state/ccr-keepalive.json`
  currently reads `"interactive_settings_clean": true`, checked this session). **Since 06:07
  this morning, `~/.claude/settings.json` has stayed clean continuously** — read directly this
  session, it currently carries no `apiKeyHelper`/`env` keys at all.

### Failure B — headless auth broke ("Not logged in")

- **Mechanism (inferred from evidence, not simulated):** CCR's `apiKeyHelper` was a script
  (`ccr-claude-code-api-key-default-claude-code.cmd`) that supplied an API key to every
  `claude` invocation, interactive AND headless, as a side effect of the same global hijack.
  Project doctrine (`setup/scripts/run-heartbeat.ps1`, quoted verbatim, read this session)
  states headless automation is deliberately designed to run on **J's logged-in subscription
  OAuth session**, not a dedicated `ANTHROPIC_API_KEY`:
  > "Invoke-Claude inherits the logged-in subscription auth when `$env:ANTHROPIC_API_KEY` is
  > unset."
  Once `apiKeyHelper` was stripped (Failure A's fix), any headless `claude -p` call that had
  never independently produced a valid `~/.claude/.credentials.json` OAuth token (because CCR's
  helper had silently been the thing supplying credentials since 07-08) had nothing to
  authenticate with → "Not logged in."
- **Fix J applied:** ran `/login`. `~/.claude/.credentials.json` (read structurally this
  session, no secret values printed) now holds a standard `claudeAiOauth` block
  (`accessToken`/`refreshToken`/`expiresAt`/`subscriptionType`/`rateLimitTier`), last written
  **2026-07-14 16:30** — consistent with the timeline. This is the standard, correct
  credential store both interactive and headless `claude` read by default.
- **Current status: HEALTHY, not verified end-to-end this session.** The credential file exists
  and is structurally correct. I did not (per the read-only constraint) fire a real headless
  `claude -p` call to prove it authenticates — that would be an actual invocation, not
  inspection. **This is the one open item that "needs J to verify"**: run one real headless
  fire (or check tonight's next scheduled LLM-touching task's exit code/log) and confirm no
  "Not logged in" recurs. Everything else about it is consistent with healthy, but I'm not
  claiming "works" without having fired it.

### "Restarted twice more and had issues" — what I found, and what I didn't

I looked for a third lockout event after the 06:07 fix-and-heal and found **none** in any log,
state file, or settings backup. Specifically checked and ruled out:
- **No further router-leak events** — only the one 06:07:34 entry exists in today's
  full keepalive log (168 lines, grepped for `LEAK|FIXED|violat`).
- **No CCR autostart entry exists anywhere** (Startup folder, `HKCU`/`HKLM` Run keys, or a
  dedicated launcher scheduled task) — checked all three this session. CCR does **not**
  auto-launch at boot on its own; it only comes up when something invokes the `claude` CLI
  through it, or when `Gamma_CcrKeepalive`'s 5-minute probe finds it down and restarts it.
  `Ollama.lnk` **does** autostart from the Startup folder (added 2026-06-24) — that's expected
  and is the *intended* standing local-model service (kitchen, veto, `launch_claude_local.ps1`
  all depend on it being always-on).
- **The 3rd "extra" node.exe process** I initially flagged (PID 29536, started 13:56 local) is
  **not CCR** — `netstat` maps it to port 4317, which is `gamma-companion` (the Node robot UI),
  an unrelated process. CCR's actual two processes (PIDs 17256/20728, both started 06:07:25,
  matching the fixing session's live-verification restart) are bound to 3456/3457/3458 as
  expected.
- **The scheduled task itself never stopped firing.** `Gamma_CcrKeepalive` is a
  `MSFT_TaskTimeTrigger`, `Repetition Interval PT5M`, `Duration P3650D` (10 years) — this kind
  of trigger resumes on schedule after any reboot without needing a fresh logon trigger. Cross-
  checked local vs ET time explicitly (a real foot-gun on this box per doctrine) — local machine
  time is 19:03, ET is 21:01 (local+2, confirmed via `et_clock.py`), so the task's `LastRunTime`
  of `19:02:34` local is **40 seconds old, not a 2-hour gap** as it first appeared before I
  converted timezones. `LastTaskResult: 0` for every fire today.

**My honest read:** the two additional restarts J remembers most likely correspond to (a) the
06:00–06:07 fix-and-reintroduction-and-heal cycle from this morning's own verification pass, and
(b) the `/login` recovery for Failure B, which likely required closing and reopening the Desktop
app or CLI session to pick up the new credential file — not evidence of a third, undiagnosed
lockout. I did not find a third failure mode in the evidence. If J experienced something beyond
these two, the next data point to check would be Desktop-app-specific logs (outside this repo's
visibility) — I don't have read access to those from here.

---

## 2. Proposed permanent fix (PROPOSED-FOR-J-APPROVAL — NOT applied)

The shipped fix (commit `559d6a5`) is structurally correct — strip the global override, self-heal
every 5 minutes. It closes Failure A's *duration* (full workday → max ~5-10 min) but not its
*possibility*. Two concrete gaps remain, found by reading the code, not by testing it live:

**Gap 1 — the guard doesn't re-check immediately after its own restart.**
Read `setup/scripts/ccr_keepalive.py::main()` this session: `_check_and_fix_interactive_settings()`
runs once, at the top of the fire, BEFORE `_restart_ccr()` is ever called. If this same fire finds
CCR down and restarts it (which the fixing session proved reliably re-injects the hijack), the
newly-reintroduced leak is not re-scanned until the *next* fire — up to 5 more minutes serving
Ollama silently to Desktop/CLI. The lesson doc J's own fixing session filed
(`strategy/candidates/_lesson-inbox/2026-07-14-ccr-boot-lockout.md`) already states the correct
principle: *"when a keepalive's OWN restart action can itself re-introduce the exact fault it
exists to prevent, the guard must check AFTER every restart, not just before."* The code doesn't
yet do that.

- **Exact proposed change:** in `main()`, add one more
  `_check_and_fix_interactive_settings()` call immediately after `_restart_ccr()` +
  `time.sleep(RESTART_WAIT_SEC)`, before the function returns — same fire, not waiting for the
  next tick. Fold its `violations`/`fixed` result into the same `_write_state()` call already
  being built. ~6 lines, no new file, no schedule change.
- **Guard-test spec that would RED-proof it:** a new case in
  `backtest/tests/test_ccr_interactive_isolation.py` that monkeypatches `_restart_ccr` to leave a
  synthetic hijack in the settings fixture (simulating what a real CCR restart does), asserts
  `_probe_ccr` still reports down→up across the call, then asserts the settings fixture is clean
  **before `main()` returns** — not merely clean on the *next* invocation. Today's suite proves
  the leak gets fixed eventually; it does not prove it gets fixed same-fire.

**Gap 2 — the fix depends on a periodic guard remembering to run, not a structural guarantee.**
The cleanest permanent fix is **not availability-dependent on this script at all**: point
`ANTHROPIC_BASE_URL`/`apiKeyHelper` at nothing, ever, for the interactive path — i.e. never let
CCR's install/update process have write access to `~/.claude/settings.json` in the first place.
Two options, ranked:
1. **(Preferred) Uninstall or fully quarantine CCR** (see §3 — the KILL case is strong). If CCR
   isn't installed/running as a systray/updater process, it can't reinject anything, and Gap 1
   becomes moot. This removes the entire failure class rather than guarding it.
2. **(If CCR is kept) Make the interactive config immune by construction**, the same pattern
   `setup/launch_claude_local.ps1` already proves works: never let J's Desktop app / bare CLI
   read the shared `~/.claude/settings.json` for routing at all. `CLAUDE_CONFIG_DIR` per-profile
   isolation is a real, already-verified-working mechanism in this repo (see §4) — it could be
   extended so the *default* global file is the isolated, router-free one, and automation is the
   thing that must opt into an alternate `CLAUDE_CONFIG_DIR`, inverting today's arrangement
   where automation is default and J had to be carved out.

**Headless auth:** currently healthy by inspection (`.credentials.json` present, correctly
shaped, freshly written 16:30 today) but **UNVERIFIED end-to-end this session** — no live
headless fire was run to confirm (per the read-only constraint). Proposed check, not applied:
add a one-line assertion to whichever daily self-check already runs (`gym-session` or the
`self-check` cadence visible in `STATUS.md`) that a trivial headless `claude -p "ok"` returns
zero-cost/non-error, so a future silent auth expiry surfaces in `STATUS.md` instead of at the
next scheduled trading fire.

---

## 3. KEEP / SIMPLIFY / KILL — the honest call, with numbers

**Measured benefit, found this session (not assumed):**
- Kitchen's actual model routing (`automation/state/model-roster.json`, read this session)
  calls Ollama **directly** at `http://localhost:11434/v1/` — it does not go through CCR at
  all. `local_floor` = `qwen3:14b` served straight from Ollama.
- `setup/launch_claude_local.ps1` (J's interactive local-brain launcher) explicitly bypasses
  CCR by design — its own header comment, quoted: *"this launcher points `CLAUDE_CONFIG_DIR`
  at its OWN config dir... The global config is never read, so the router can never hijack the
  base URL."* It talks to Ollama through a `nothink_proxy.py` on :11435, never through :3456.
- A repo-wide grep for real (non-comment, non-test, non-worktree-duplicate) CCR usage found
  **zero live production call sites**. `setup/launch_claude_local.ps1` and
  `setup/scripts/run-premarket.ps1` only *mention* port 3456 in comments describing why they
  avoid it.
- `markdown/planning/BRAIN-SOVEREIGNTY.md` §11 (its own doctrine doc, read this session) still
  frames CCR's intended Tier-2 use ("re-point ONE parked mechanical fire... at `ccr code`") as
  a **future** action item, not something already shipped.

**Bottom line on the numbers:** CCR currently provides **measured production benefit ≈ $0** —
nothing in this repo's live automation actually routes through it today. Its intended purpose
(cheap-cloud Tier-2 routing for conductor/overnight-grinder fires) was never wired up; Ollama's
real, already-realized $0-electricity benefit (kitchen R&D, hot-path veto second-opinions,
`launch_claude_local.ps1`) is delivered entirely by talking to Ollama **directly**, with CCR
nowhere in that path.

Against that zero measured benefit: CCR caused **one full-workday interactive lockout (Monday)**
and **one ~7-minute recurrence this morning**, plus contributed to the separate headless-auth
break. Liability is confirmed and repeated (the fixing session proved the reinjection is CCR's
*normal* restart behavior, not a fluke); benefit is theoretical and not yet realized anywhere in
this codebase.

**Recommendation: KILL CCR. KEEP Ollama, unconditionally (it's genuinely load-bearing and has
never caused a lockout).**
- Uninstall or stop/disable CCR's own launch path (its npm-installed CLI, and whatever process
  currently listens on 3456-3458) so it can no longer restart itself and reinject anything.
- Retire `Gamma_CcrKeepalive` (nothing left to keep alive) — but only after J confirms no other
  in-flight branch/worktree still expects it (several `.claude/worktrees/*` copies of
  `ccr_keepalive.py`/`test_ccr_keepalive.py` exist; a scoped check before deletion, not covered
  by this read-only pass).
- Keep `setup/launch_claude_local.ps1` + Ollama exactly as-is — verified genuinely isolated
  from the interactive path by construction, zero incidents attributed to it.
- If Tier-2 cheap-cloud routing (DeepSeek/Kimi/MiniMax) is still wanted later, wire it the way
  BRAIN-SOVEREIGNTY.md §11 already describes — direct provider API calls or a
  narrowly-scoped, automation-only config, never a global `~/.claude/settings.json` default.

This is a KILL call on CCR specifically, not on the brain-sovereignty initiative as a whole —
Ollama (the actual $0 R&D/veto workhorse) stays exactly as designed.

---

## 4. Plain-English explainer (60 seconds)

**What it is:** two local pieces of software were added to this laptop to let Claude Code use
cheaper or free "brains" instead of always paying for Anthropic's models: **Ollama** runs an AI
model directly on this PC's graphics card, and **claude-code-router (CCR)** is a small proxy
that was supposed to sit in front of `claude` and decide, per-call, whether to send it to
Anthropic, a cheap cloud model, or the local one on this PC.

**What it's actually doing:** Ollama is doing real work — the overnight research "kitchen," a
background sanity-check on trade decisions, and an optional local chat mode all talk to it
directly, and it's never caused a problem. CCR, on the other hand, got wired into the ONE shared
settings file that *every* Claude Code window on this computer reads by default — including
J's normal working sessions — and it was misconfigured to silently hand every request to the
free local model instead of real Claude, with no error message. That's what caused the lockout:
J's Claude Desktop app just quietly got dumber for a whole workday, with no warning.

**The benefit, honestly assessed:** the intended benefit was $0-cost research and cheaper
automation. In practice, nothing in this project currently gets that benefit *through CCR* — the
research loop and the local-chat option both go straight to Ollama, skipping CCR entirely. So
right now CCR is pure downside: it can silently hijack J's real Claude sessions, and nothing
depends on it to keep working. The fix already applied today stops it from doing that by
default and adds a 5-minute self-check in case it happens again — solid, but the cleanest fix is
removing CCR from the picture rather than continuing to guard against something that isn't
earning its keep.
