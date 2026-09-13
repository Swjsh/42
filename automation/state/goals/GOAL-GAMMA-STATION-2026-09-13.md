# GOAL: GAMMA-STATION-2026-09-13

> J verbatim (2026-09-13 ~13:40 ET, Sunday, `/goal`): *"Please set up my autonomous gamma once and for all … I want it here … move literally
> everything over to E … Get Ollama over there. Get project 42 copied over there … I have Wyze webcams … why do I need a Raspberry Pi? Why can't I
> just plug HDMI into my TV … You should be able to set this up in the next five days. I can drop down to the hundred dollar a month plan after 9/15,
> and we'll use the rest of our two hundred dollar month plan to get this all set up … If you don't [have enough data], ask me. But if you do, then
> that's your goal to set it up end to end."*
> Amendment 13:5x ET: *"weigh the options of hard disk vs M.2 speeds and how the LLM runs on them before you go moving things."* Weighed: all three
> drives are SSDs; E: is the only NVMe (970 EVO, ~3.4 GB/s vs ~0.5 GB/s SATA on C:/D:); disk speed affects model load/swap time only, never tok/s → E:.

Parent plan: [`markdown/planning/GAMMA-STATION.md`](../../../markdown/planning/GAMMA-STATION.md) (§3c Option A: brain on this PC, no new box).
Hard deadline: **2026-09-18** (five days; Max 20x → Max 5x after 09-15). Model tier: Fable does ops steps + specs; every code build is a Sonnet spawn (≤2/day).
Absorbs GOAL-EARN-YOUR-KEEP-2026-09-12 item (5) (the 09-18 honest-state verdict) — that goal is re-queued directly behind this one on the ladder; its
in-flight items (1) and (7) keep their builders and their own PROGRESS LOG.

## DONE-WHEN (falsifiable; each checked by a command or ledger row quoted in the PROGRESS LOG)
- (a) **The Station runs unattended for 24 h on this PC with a local brain and shows on the TV.** Check: `automation/state/station/loop-ledger.jsonl` has ≥48 rows
  over a 24 h span with `model` = the local planner and `status` ∈ {ok, yielded}; a screenshot of the TV display (or the kiosk window) taken by
  `station_kiosk.ps1 -Snapshot` carries a HOME timestamp < 35 min old.
- (b) **Gamma brought ideas nobody prompted.** Check: `automation/state/station/ideas-board.json` holds ≥3 cards with `evidence`, `proposed_shadow_test`,
  `cost_line` and `prompted_by: "station-loop"` written on ≥2 different days.
- (c) **Automation no longer bills the Max pool.** Check: one full day (a blackout day) with every `claude` fire routed to local or parked, quoted from
  `SCHEDULED-TASKS.md` + the per-fire launch env; `core-decisions.jsonl` shows no RTH gap > 3 min that day.
- (d) **An off-box alarm exists.** Check: a deliberate 15-minute silence of the heartbeat ping produces an alert on J's phone (alert-only; kill-type action waits
  for the 09-29 checkpoint).
- (e) **The trading path is byte-identical.** Check: `git diff 606e8640..HEAD --stat -- setup/scripts/heartbeat_core.py automation/state/fleet/ backtest/lib/filters.py backtest/lib/risk_gate.py automation/prompts/heartbeat*.md params*.json` is empty (freeze to 10-30 honoured).
- A null is a valid terminal state: if the local planner cannot pass the Claude-Code smoke test at ≥16K context after (3), the goal records that and falls back
  to the qwen3.6:35b floor for the loop — still counted against (a)/(b), reported plainly in HONEST STATE.

## OPERATING RULES
- **Freeze (→ 10-30):** nothing here edits `heartbeat_core`, fleet, filters, risk_gate, params, heartbeat prompts, or Task Scheduler entries on the trading path.
  The live engine keeps running from `C:\Users\jackw\Desktop\42`; the E: clone is the Station's working copy. Moving the live checkout to E: is a Phase-4 item
  (directory junction, after 10-30), not this goal.
- **No LLM on the live tick; paper only; no live keys on the Station side.** The loop reads ledgers and writes `automation/state/station/*` and docs — never orders.
- **Silent rig:** every new process is a hidden chain or a service; no console windows (J 09-05). The loop **yields** when a fullscreen game or GPU load > 50 % is
  detected, and never runs heavy work 09:30–15:55 ET.
- **Routing:** local models reach Claude Code through per-process env (`ANTHROPIC_BASE_URL` → Ollama, the `launch_claude_local.ps1` pattern). Never a router
  under J's interactive tools (scars 07-14, 08-23). J's desktop app stays on Anthropic direct.
- **Model promotion:** every model enters a role through `shadow_model_eval` (≥85 % over ≥15 days). The planner ships as `gamma-planner` on a scorecard clock;
  until it passes, its outputs are labelled UNVERIFIED on the board.
- **Token pacing:** Fable = ops steps + specs; ≤2 sequential Sonnet builders/day (`model:"sonnet"` explicit), each with objective / return schema / scope / do-not list.
  Per-day token estimate in the PROGRESS LOG. Use the remaining Max 20x through 09-15 (J), then Max 5x.
- Every fire: `python setup/scripts/conductor_outcome.py record --task-id GOAL-GAMMA-STATION-2026-09-13 --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- `STATUS.md` gets a line at OPEN and CLOSE only. CLAIM an item (`[ ]` → `[~]`) before working it. Never `/loop` this goal in-session.
- Secrets J only: Wyze credentials, healthchecks URL, any key — pasted by J into gitignored homes; Fable never types them.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] (1) Dedicated area on E: (NVMe) + Ollama moved. DONE-WHEN: `ollama list` is served from `E:\Gamma\models` (user env `OLLAMA_MODELS`), shows the 3 existing models plus `qwen3.8:27b-mtp-q4_K_M`; `C:\Users\jackw\.ollama\models` is gone; `OLLAMA_KV_CACHE_TYPE=q8_0` + `OLLAMA_FLASH_ATTENTION=1` set.
- [x] (2) 42 cloned to `E:\Gamma\42` with origin = GitHub. DONE-WHEN: `git -C E:\Gamma\42 status` is clean and `remote get-url origin` prints the Swjsh/42 URL; a README note in `E:\Gamma\station\README.md` states the live engine stays on C: until 10-30 and names the junction procedure.
- [~] (3) Planner benched. DONE-WHEN: `gamma-planner` Modelfile (FROM qwen3.8:27b-mtp-q4_K_M, num_ctx ≥ 32768) exists; `automation/state/station/planner-bench.json` records tok/s at 2K and 16K prompts, VRAM/CPU split, and a Claude Code `--print` smoke test through Ollama's Anthropic API that answers a repo question correctly (`setup/launch_claude_local.ps1` pattern, `-Full`); if the q4 spill is slow, the unsloth Q3_K_M GGUF is imported and re-benched.
- [ ] (4) Station loop v1 (Sonnet build). DONE-WHEN: `setup/scripts/station_loop.py` + `automation/prompts/station.md` + task `Gamma_Station` (hidden chain, every 30 min 24/7, yield rule, RTH-light) run `claude --print` on the local planner, read the day's ledgers/autopsies/hypothesis-queue/goal ladder, and write `automation/state/station/ideas-board.json` (schema: id, title, evidence[], proposed_shadow_test, cost_line, prompted_by, ts_et) + `station-brief.md` + a row in `loop-ledger.jsonl`; 3 consecutive fires produce schema-valid output; guard test in `backtest/tests/test_station_loop.py`.
- [ ] (5) The TV face (Sonnet build). DONE-WHEN: the cockpit generator (`gamma_cockpit_*.py`) emits a Station panel (ideas board, last brief, planner status, last 10 loop rows) and `setup/scripts/station_kiosk.ps1` opens Edge `--kiosk` on the TV display (display index configurable), auto-refreshing every 5 min, hidden-chain launched at logon; `-Snapshot` writes a PNG; briefs' wav plays on the HDMI audio device via `gamma_speak.py --device`.
- [ ] (6) Presence via the Wyze cam. DONE-WHEN: `docker-wyze-bridge` runs on Docker Desktop with J's credentials in a gitignored `.wyze-bridge.env`; `setup/scripts/station_presence.py` reads the RTSP stream (OpenCV motion + person heuristic) and writes `automation/state/station/presence.json`; on a presence edge after 06:00 ET the morning brief plays once (≤2 greetings/day); one greeting logged. [B-J until cam model + creds]
- [ ] (7) Off-box alarm, alert-only. DONE-WHEN: `self_check.py` (already every 30 min) pings a healthchecks.io check URL from the gitignored secrets home; a deliberate 15-min silence reaches J's phone. [B-J until J creates the check and pastes the URL]
- [ ] (8) Phase 0 — subscription re-base. DONE-WHEN: `SCHEDULED-TASKS.md` carries a census row per `claude` fire (local / Claude-weekly / parked), `conductor-budget.json` cap lowered for Max 5x, each re-pointed fire launches with its own local env; one blackout day passes per DONE-WHEN (c).
- [ ] (9) 09-18 HONEST STATE for this goal and for GOAL-EARN-YOUR-KEEP (its item (5) folded here): per-account numbers, what shipped, what did not, nulls stated. NOT-BEFORE 2026-09-17 close.

## J-DECISIONS (blocked-on-J; everything else ships without asking)
- [ ] Which Wyze cam model(s) (v3 / Pan v3 / v4 / OG)? v3 and Pan v3 also have official RTSP firmware (Feb 2026, drops after hours); v4/OG need the bridge. Bridge works for all — it needs J's Wyze login in a gitignored env file, entered by J.
- [ ] HDMI from the PC to the Samsung TV: cable reach confirmed? The TV's "lights up when I walk by" is a motion/ambient sensor for Art/Ambient mode, not a camera Windows can read; presence comes from the Wyze cam.
- [ ] A free healthchecks.io check (2 minutes): create it, paste the ping URL into `automation/state/fleet/secrets.json` under `healthchecks_ping_url`. Until then item (7) is [B-J].
- [ ] Confirm: Max 20x → Max 5x ($100) after 09-15 (assumed from J's message).

## PROGRESS LOG
- 2026-09-13 13:44 ET (Fable): goal OPENED per J's `/goal`. Weigh-up before moving (J amendment): C:/D: = Samsung 870 EVO SATA SSDs, E: = 970 EVO NVMe, 466 GB free, empty → E: chosen; load/swap time is the only thing disk speed changes. Ollama 0.33.3 / Claude Code 2.1.205 / Docker Desktop 29.1.3 / Node 24 present. Ollama library has `qwen3.8:27b-mtp-q4_K_M` (18 GB) — the MTP head the 5080 benchmark used for 101 tok/s; no q3_K_M tag (unsloth GGUF import is the fallback). Item (1) claimed; execution script `station_e_setup.ps1` run this session (result quoted in the next line).

- 2026-09-13 13:52 ET (Fable): `station_e_setup.ps1` ran -- quoted: `ollama stopped: yes` · `robocopy rc=1 (0-7 ok) in 64s` · `C: model dir remains: False` · `E: models size GB: 30.9` · `env user OLLAMA_MODELS=E:\Gamma\models` · `ollama list` from E: = claude-local 23 GB, qwen3.6:35b 23 GB, qwen3:14b 9.3 GB · server pid 27996 · pull `qwen3.8:27b-mtp-q4_K_M` started (log E:\Gamma\logs; 16 GB/16 GB at 13:51) · clone HEAD `6466eb5e`, origin = github.com/Swjsh/42 · E: free 433 GB, C: free 32->63 GB. Item (2) DONE (E:\Gamma\station\README.md carries the Phase-4 junction procedure). Item (1) stays `[~]` until the planner tag shows in `ollama list`. Tokens today: Fable interactive only, no builders yet.

- 2026-09-13 14:05 ET (Fable): item (1) DONE -- `ollama list` shows `qwen3.8:27b-mtp-q4_K_M 17 GB` served from E:; `gamma-planner` created from `setup/ollama/Modelfile.gamma-planner`. Bench (`setup/scripts/station_planner_bench.py`, `automation/state/station/planner-bench.json` record 1, RTX 5080 16 GB, Ollama 0.33.3): ctx16K/2K-prompt prefill 384 tok/s, gen 18.9 tok/s, split 32%/68% CPU/GPU, correct · ctx16K/12K gen 4.4 tok/s (outlier, correct) · ctx32K/2K gen 17.9 · ctx32K/26K-prompt prefill 1,024 tok/s, gen 13.0 tok/s, correct -- 4/4 answers named both Rule-5 percentages. Verdict: usable for a 30-min loop (a 26K-token read ~26 s + ~10 s of output) but 3-4x under the fully-on-GPU Q3_K_M config (53-101 tok/s at 64K ctx on this card) -> importing the unsloth Q3_K_M GGUF is the next step of item (3); Claude Code smoke test running.

- 2026-09-13 14:12 ET (Fable): Claude Code smoke test PASSED -- `setup/launch_claude_local.ps1 -Model gamma-planner -Prompt "<Rule 5 + time-stop question>"` (isolated cfg, `--bare`, no-think proxy :11435) returned "Gamma-Safe -30% of start-of-day equity, Gamma-Bold -50% (isolated per account); hard time-stop 15:40 ET" in 36.7 s wall, zero Anthropic tokens; `ollama ps` = gamma-planner 18 GB, 37%/63% CPU/GPU, ctx 32768. Fully-on-GPU path: unsloth `Qwen3.8-27B-UD-Q3_K_XL.gguf` (12.2 GB) downloading to E:\Gamma\models\gguf for a `gamma-planner-fast` import at num_ctx 65536. Builder #1 (Sonnet) spawned for item (4) Station loop v1.

## HONEST STATE
- 2026-09-13 13:44 ET: opened; nothing verified yet beyond the read-only spec sweep.
