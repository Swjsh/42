# HANDOFF 2026-09-15 — HQ world design pass (fresh session)

> Paste the **Prompt** section into a fresh Claude Code session in `C:\Users\jackw\Desktop\42`.
> Orchestrator tier: Opus/Fable = judgment + research synthesis; all build work → Sonnet workers
> (`model: "sonnet"`), max 2 at a time. Links: [[markdown/planning/GAMMA-STATION|GAMMA-STATION]] ·
> `dashboard/components/hq/ENVIRONMENT-PLAN.md` · goal log `automation/state/goals/GOAL-GAMMA-STATION-2026-09-13.md`

---

## Prompt

You are taking over the **HQ world design pass** for Project Gamma. The HQ is a
react-three-fiber scene at http://127.0.0.1:3000/hq (Next 15 + React 19 + drei; code in
`dashboard/components/hq/`). It visualises the real trading rig: persona desks, live Claude
agents walking in and out, the HoloChart with today's SPY candles, levels and trade markers.

### J's feedback (2026-09-15 ~18:30 ET, from a top-down screenshot of /hq)

1. **Ideas board is crooked and unreadable.** The big tilted screen over the hub (IDEAS BOARD)
   is angled so you can't read it. Replace it with **two large monitor screens, side by side,
   in that corner**, facing the camera and readable.
2. **Desk layout is awful.** From top-down the desks sit *inside* the walls and have no
   intentional layout. Needs a real floor plan: desks clear of walls, consistent orientation,
   clear aisles.
3. **Agents ignore the walkways.** J watched "Futures" run from the middle straight to its cube
   through walls. It didn't use the walkway or open any doors. Every walk must follow the walk
   graph and go through doors.
4. **Character models look wrong.** The purple-shirt characters appear to have
   "walking sticks" on their arms (a prop, rig or pose artifact). J wants **different character
   models**, not these.
5. **Labels are too big and wordy.** Above each head show only: **name + an icon for the model it
   runs (e.g. Sonnet/Opus/Haiku/local qwen/Python script) + a colored status dot**. Long status
   text belongs in hover/click, not floating over the scene.
6. **Research first, don't spitball.** Find real references and resources online (layouts,
   character packs, label conventions) before building. J noted earlier research was good and
   then it "fell off the deep end" into iterating our own output.

### Hard rules for this pass

- **Design starts at external references** (memory `feedback_design_starts_at_external_reference_2026_08_30`):
  every sub-task opens with WebSearch/WebFetch of real references. Cite each one (URL + what was
  taken from it) in `dashboard/components/hq/ENVIRONMENT-PLAN.md` *before* code is edited.
  Management-sim references already used there: Two Point Hospital, Prison Architect,
  Cities: Skylines, Planet Coaster.
- **Claude does not make taste calls.** For character models and the desk floor plan, research
  2–3 sourced options (screenshot/preview link, license, poly count, rig/animations included) and
  put them in front of J as ONE recommended pick plus alternates. Don't ship a new character pack
  until J picks. Mechanical fixes (pathing through doors, desks out of walls, readable screens,
  compact labels) are normal work: ship them.
- **Assets:** CC0 or clearly permissive only. Record every asset in
  `dashboard/public/hq-assets/LICENSES.md`. Current packs: kenney-mini-characters,
  kenney-modular-space-kit, kenney-space-kit, kenney-furniture-kit, kaykit-space-base-bits.
  Verify each candidate pack's license on its own page. Don't trust a summary.
- **HQ face rules** (memory `feedback_hq_face_rules_tv_never_wakes_motion_means_events_2026_09_13`):
  motion = real events only, never wake the TV, not-PS2 visual bar.
- **Verification = real-screen capture**, only when `setup/scripts/gamma_mode.ps1 -Mode status`
  is not gaming/off AND `automation/state/station/presence.json` has `present:false`:
  `powershell -NoProfile -ExecutionPolicy Bypass -File setup/scripts/hq_capture.ps1 -Out <png> -Url "http://127.0.0.1:3000/hq?tour=0" -SettleSec 35`,
  then Read the PNG. The in-app Browser pane runs hidden and pauses the canvas, so its numbers don't
  count. For motion, also run the live-agent probe per memory
  `reference_hq_live_agent_probe_procedure_2026_09_15` (11 checks; last all-green ~10:50 ET 09-15).
- Deploy: `powershell -NoProfile -File setup/scripts/dashboard_deploy.ps1 -Tag <TAG> -MaxWaitMin 30`
  (builds the working tree, honors `dashboard/.build.lock`). Commit only your files:
  `python setup/scripts/commit_scoped.py "<message>" <paths...>` (message FIRST). Push only
  outside 09:30–15:55 ET. No trading-path files. Timestamps via `setup/scripts/et_clock.py`.
  Append one proof line per verified item to the goal log.

### Where things live (verify, don't trust)

| Concern | Files |
|---|---|
| Floor plan, desk/bay positions, walk graph | `layout.ts`, `BayInterior.tsx`, `HubInterior.tsx`, `StationModule.tsx`, `SetKit.tsx` |
| Resident persona walking (Futures etc.) | `Agent.tsx` (walk kinds incl. legacy 2-point "roundtrip/arrival/purposeful" vs graph "waypoints"), `palette.ts#computePurposefulWalk`, `HandoffCourier.tsx` |
| Live Claude agents walking | `LiveAgents.tsx`, `liveAgentWalk.ts` (CONVOY v5–v14, walk-graph based) |
| Characters | `KitAgent.tsx` (useGLTF on `public/hq-assets/kenney-mini-characters/*.glb`), `GammaCharacter.tsx` |
| Ideas board | `IdeasWall.tsx` (`BRAIN_WALL_MOUNT`), `SmartBoard.tsx`, `DeskScreen.tsx` |
| Labels / bubbles | `labelDeclutter.ts`, `LabelDeclutterManager.tsx`, `useLabelDeclutter.ts`, `bubbleText.ts`, `bubbleScale.ts`, `liveAgentIdentity.ts` |
| Model/status data | `/api/hq` (personas: status, runs-as, model), `dashboard/lib/hq.ts`, `hq-runtime.ts` |

Likely root cause for #3 (UNVERIFIED, prove it first): some resident walks still use the legacy
straight-line kinds instead of the `waypoints` WalkPlan from the walk graph.
#4 "walking sticks": UNVERIFIED whether it's an attached prop node, a rig/skin weight issue, or
a held-item mesh in the Kenney GLB. Inspect the GLB node tree before blaming the model.

### Suggested order

1. Research sweep (references + 2–3 character-pack and floor-plan options) → ENVIRONMENT-PLAN.md → present picks to J.
2. Mechanical, ship now: (a) all walks go through the walk graph and doors (diagnose Futures first);
   (b) compact head labels: name + model icon + status dot, details on hover/click;
   (c) two flat readable monitor screens side by side in the corner, replacing the tilted IDEAS BOARD;
   (d) desks pulled out of walls onto a consistent grid with aisles.
3. After J picks: swap character models; re-run probe + capture.

### State at handoff (2026-09-15 evening)

- Pushed through `0c2bc5bc`: position truth, intraday candles, all 10 trade markers with arm ids,
  brain plaque truth, level-label declutter, last-close occlusion fix `dac624a6` (**visual
  UNVERIFIED**; J was present).
- Finished and pushed by the previous session (through `7a9d036f`), **data verified, visuals
  UNVERIFIED** (J present, no capture):
  - **HQ-TRADE-MOMENTS** `ee70175b`: Pilot bubble per real fill (75 s window keyed on
    fills-ledger `activity_id`), FLEET P&L panel for all active arms from `accounts.json`, day-close
    clause in the MARKET CLOSED banner. `/api/hq` checked: book −529, 1W/4L.
    **Design follow-ups:** label P&L as **gross** (journal net of fees is −530.05); check the
    panel/banner fit in the new compact-label layout.
  - **HQ-LEVEL-EPISODES** `df21ffed` + `7a9d036f`: level plaques show touch episodes + held/broke/
    testing; `/api/hq-chart` levels carry `interaction` (757.44 = 6 episodes, testing).
    **Design follow-up:** after the close, "testing" is misleading. Show a final state such as
    "closed in zone".
  - First job of the design session: take a J-away capture to verify these plus `dac624a6`.
- STATION-ORDER live proof pending on the ~00:37 ET 09-16 Gamma_Station cron.
