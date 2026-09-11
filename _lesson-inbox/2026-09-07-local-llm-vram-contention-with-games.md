# Lesson inbox: the free-model lanes kept a 9 GB model resident on the GPU while J was gaming

**Date:** 2026-09-07 (Sunday), J: "im lagging so bad" / "kill everything now besides apex" / "rig needs to be gaming optimized"

**Symptom:** Apex stuttering; fans screaming. `llama-server` (child of `ollama serve`, autostart) at ~12% CPU (2 cores) and **9,199 MB dedicated VRAM**, loaded 15:11 ET and kept warm by periodic callers: Gamma_TwinSentinel (15 min), Gamma_FreeModelAudit (15 min), Gamma_KitchenSeeder (1 h), Gamma_KitchenReviewer (2 h), Gamma_Prospector (4 h). Not a rig-critical path — the live engine uses zero LLM tokens.

**Root cause (one sentence):** the "free/local-first" research doctrine was implemented as always-on local inference with no awareness of what else the machine is doing, so a research convenience became a second GPU tenant on a gaming PC.

**Fix applied:** Ollama stopped; autostart shortcut renamed to `.disabled`; quiet hold 4 h. With Ollama down, the callers above fail-open and flag STATUS (verify they do — a lane that silently returns fabricated numbers instead is the 09-05 kitchen lesson again).

**Durable fix (queued):** (1) a shared `game_running()` check (r5apex_dx12, and a small list) that every local-model caller consults and SKIPs on; (2) local models start on demand and unload (`OLLAMA_KEEP_ALIVE` ≤ 5 min), never autostart; (3) the launch-rate / quiet-mode instrument should also report GPU tenants, not just process launches.

**Encoded in:** memory `rig-gaming-optimized-ollama-off`; this inbox item → L## via lesson-author.
