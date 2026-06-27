# PAUL PLAN — Gamma Pixel Office ("Gamma is alive")

> The living pixel-office layer behind the Gamma dashboard (`cockpit/face.html` + `cockpit/pixels.js`).
> One pixel worker per live agent, sectioned into themed rooms, fed by `/api/agents-live`.
> Owner of execution: the pixel build-agent. Owner of validation: main (screenshots + asserts).
> **Done = validated, not "built."** No check-ins until acceptance criteria pass.

---

## 1. Vision (J, verbatim intent)

Fill the black space around the dashboard with a **living pixel office**. Section it into
**themed rooms** — a real **kitchen** (stainless stoves/appliances), a **gym** (weights),
an **accounts** row (one square per account), an **R&D/lab**, a **trading** desk. Each agent
**spawned in a sector stays in that sector** (a Nemotron in the kitchen never leaves the
kitchen). Workers **walk around and actually do things** (proper pathing — no straight lines).
When J talks to Gamma or the kitchen/gym/R&D fire, the floor **comes alive**. It must look
**good** — **real pixel art sourced from the internet** (CC0), not crude procedural shapes.

---

## 2. Current state (2026-06-27)

- ✅ Sectors landed: KITCHEN / GYM / LAB·R&D / ACCOUNTS / TRADING render as labeled rooms.
- ✅ A* pathing fixed (multi-cell routes, no straight-line fallback).
- ✅ Roster wired: `/api/agents-live` (kitchen, conductor, research, engine + **6 account residents**); a Claude worker spawns on the mic.
- ❌ **Furniture is procedural + sparse/crude** — rooms read as mostly-empty dark columns. **Needs real CC0 pixel-art assets.**
- ❌ Containment not yet proven (agents must be fenced to their sector).
- ❌ No written plan (this doc fixes that).

---

## 3. Sectors + themed furniture (the target)

| Sector | Residents (role) | Runner shown | Furniture (real pixel art) |
|---|---|---|---|
| **Kitchen** | kitchen | Nemotron · free | stainless **stoves w/ burners + oven**, **counters/prep tables**, **fridge**, hood, pots |
| **Gym** | gym | Python | **weight rack + plates**, **bench**, **dumbbells**, treadmill, mat |
| **Lab / R&D** | research, conductor, claude/voice | Claude · Python | **whiteboards** (scribbles), research **desks + monitors**, **server racks**, plants |
| **Accounts** | account ×6 | account alias | **6 cubicles**, each a small desk + **terminal w/ a $ screen**, divider walls |
| **Trading** | engine, beacon | Python | trading **desks w/ multi-monitor charts**, ticker board |
| **Lobby/walkway** | (transit only) | — | floor, a plant or two, the door |

**Right-size rule:** furniture is themed + **capped per sector** — NEVER rows of empty desks.
Worker count = live roster + 6 account residents. Under-staffed rooms are lightly furnished, not padded.

---

## 4. Containment (J's explicit ask)

- Each agent's **home sector** is derived from its `role` (map above).
- A* walkable tiles = **only that sector's interior**; the dividing walls between sectors are obstacles.
- A kitchen Nemotron paths only between the kitchen's stoves/counters and never crosses into the gym.
- Account residents stay in their own cubicle square.

## 5. Roster → sector map

`kitchen→Kitchen · gym→Gym · research/conductor/claude/voice→Lab · account→Accounts(own square) · engine/beacon→Trading`

---

## 6. Asset sourcing — REAL pixel art from online (CC0 only, public repo safe)

- **License bar:** CC0 (public domain) preferred — no attribution friction on a PUBLIC repo. CC-BY acceptable only with the license file committed alongside.
- **Candidate sources (in order):**
  1. **Kenney.nl** — CC0 game assets (interior / furniture / roguelike packs).
  2. **OpenGameArt.org** — filter CC0 pixel-art interiors (kitchen/gym/office tilesets).
  3. GitHub CC0 pixel tilesets (raw PNG spritesheets, directly `curl`-able).
- **Process:** find a concrete pack → download the spritesheet(s) via `curl` → drop into `cockpit/assets/pixel/<theme>/` with the LICENSE → slice the tiles in `pixels.js` → map furniture per sector.
- Keep the existing **MIT character sprites** for the workers (already committed + attributed).

---

## 7. Phases

1. **Sectors** — labeled themed rooms, reserved card column. ✅ done
2. **Real assets** — source CC0 kitchen/gym/office pixel art online, download, slice, place per sector. ← **active**
3. **Containment** — fence each agent's A* to its sector; prove it in the harness.
4. **Liveliness + polish** — workers visibly walk/sit/use the themed stations; debug overlay off; tidy spacing.

---

## 8. Validation / acceptance (DONE means ALL pass)

- [ ] **Real pixel-art furniture** visible in each sector (stoves in kitchen, weights in gym, terminals in accounts) — sourced online, not procedural blocks.
- [ ] **No empty-desk carpet** — furniture bounded per sector; worker count == roster + 6 accounts.
- [ ] **Containment proven** — harness asserts every agent stays within its sector's tile bounds over time.
- [ ] **Pathing intact** — multi-cell A* routes (no straight lines), no ghost-leak on despawn.
- [ ] **Looks tidy + alive** in a full-dashboard screenshot at a real desktop size (verified by main).
- [ ] Licenses for any downloaded assets committed.

> Loop: build → screenshot → count/inspect → fix → repeat until every box is checked. Then ship + report.
