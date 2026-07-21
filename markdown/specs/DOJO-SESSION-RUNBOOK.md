# DOJO SESSION RUNBOOK — how a Sonnet session agent runs a dojo session with J

> **Audience: a Sonnet session agent, alone with J, no Opus/Fable in the room** (spec success
> criterion 4, `DOJO-REPLAY-TRAINING-SPEC.md`). This is a checklist, not prose — follow it
> top to bottom. Read `markdown/specs/DOJO-ARCHITECTURE-DECISION.md` once before your first
> session; after that, this doc alone is enough.
>
> **The split (memorize this):** you (the agent) are THE HANDS — the only thing that can call
> TradingView MCP tools. You make **zero** trading decisions. The Dojo Engine
> (`setup/scripts/dojo/`, pure deterministic Python) is THE BRAIN + BOOKS — it runs the real
> engine decision path, renders the whisper, validates directives, sim-executes them, scores
> arms. Your job every tick: **advance TV → read the cursor → call the dojo CLI → relay the
> whisper to J → capture what J says → call the dojo CLI again.** That's the whole loop.

---

## 0. Preconditions (check before you start)

- [ ] TradingView desktop is up with CDP debugging on port 9222 (same requirement as live
      trading — `setup\launch_tv_debug.ps1` if it's not).
- [ ] You have `mcp__tradingview__replay_start` / `replay_step` / `replay_status` /
      `replay_stop` / `replay_autoplay` bound in this session. Confirmed tool schemas
      (2026-07-20): `replay_start({date?: "YYYY-MM-DD"})`, `replay_step({})`,
      `replay_status({})`, `replay_stop({})` — all take no required args except `date` on
      start. **`replay_status`'s exact return shape (the `current_date` field) has not been
      empirically pulled from a live call as of this writing** — the DOJO-BUILD-HANDOFF
      queue item's "step 0" is still open. First real session: read the actual
      `replay_status()` response once, confirm it carries `current_date` as a Unix epoch
      (seconds), and note any divergence in the session ledger before trusting the cursor.
- [ ] You're running the dojo CLI from `setup/scripts/` (see §1 — `-m dojo.session` needs
      the package on `sys.path[0]`, which `-m` sets to the CWD).
- [ ] Interpreter: `backtest\.venv\Scripts\python.exe` (same venv the rest of the engine
      uses — has pandas etc. that `engine_step.py` will need once built).
- [ ] Pick the replay day from the curriculum (§7) unless J names one.
- [ ] Know the current Phase-1 build status (§8) — `engine_step.py` / `whisper.py` /
      `directive.py` / `sim_executor.py` / `scorecard.py` may not all be shipped yet. The
      CLI degrades gracefully (prints "`<module> not built yet`") rather than crashing —
      that is expected, not a bug, until those land.

---

## 1. Start the session

Two starts, in this order — **dojo session first, then TV replay** (the session ledger
should exist before you touch the chart):

```powershell
cd setup\scripts
..\..\backtest\.venv\Scripts\python.exe -m dojo.session start --replay-day 2026-07-17
```

Real output (verified 2026-07-20):

```json
{
  "ok": true,
  "session_id": "2026-07-17-223424",
  "phase": "CREATED",
  "ledger": "C:\\Users\\jackw\\Desktop\\42\\automation\\state\\dojo\\sessions\\2026-07-17-223424.jsonl",
  "note": "agent: replay_start on TV, then step per bar"
}
```

Save `session_id` — every later command needs it (`--session 2026-07-17-223424`).

Now start TV replay on the SAME day:

```
mcp__tradingview__replay_start(date="2026-07-17")
```

- [ ] Confirm TV shows replay mode active (chart in replay UI, not live).

---

## 2. The tick loop — repeat once per bar (or per J's "step" request)

**(a) Advance TV one bar:**

```
mcp__tradingview__replay_step()
```

**(b) Read the cursor:**

```
mcp__tradingview__replay_status()
```

Pull `current_date` (epoch seconds) out of the response — this is the ONLY clock the dojo
engine trusts. Never estimate or carry your own running clock forward.

**(c) Feed the cursor to the dojo engine:**

```powershell
..\..\backtest\.venv\Scripts\python.exe -m dojo.session step --session 2026-07-17-223424 --cursor 1784297700
```

Real output today (2026-07-20, before `engine_step.py` ships — `whisper.py` itself is
already shipped and correctly wired, but `cmd_step` imports both together and fails closed
on either):

```json
{
  "ok": true,
  "session_id": "2026-07-17-224503",
  "bar_et": "2026-07-17T10:15:00-04:00",
  "whisper": "[10:15 ET] engine_step/whisper module not built yet (Phase 1 in progress): cannot import name 'engine_step' from 'dojo' (...dojo\\__init__.py)"
}
```

Once those modules land, `whisper` becomes the real terse per-arm block (per
DOJO-ARCHITECTURE-DECISION.md's `whisper.render` contract): one line per arm — verdict,
bear/bull scores, side, trigger, nearby key levels, `would_place`. Nothing fabricated —
only fields the engine actually computed for that bar.

If the cursor is pre-RTH / weekend, `bar_et` comes back `null` and the whisper says the
engine is idle — that's correct, not an error; still relay it to J ("nothing on, pre-market
still").

**(d) Relay the whisper to J verbatim** (or your best terse paraphrase — don't editorialize
scores). This is the "watch it form" moment — say what the engine sees on THIS bar only,
never reference bars that haven't replayed yet.

**(e) Listen for a directive.** If J just watches ("nothing to do here"), log nothing extra
— a `step` row with no directive IS a validated negative label. If J calls a trade
("put this on LOOSE-R and TIGHT-R, tight stop on TIGHT-R"), go to §3.

**(f) Loop back to (a).** Keep stepping until the day (or J) is done.

---

## 3. Capturing a directive

Translate what J said into the directive JSON shape below, then:

```powershell
..\..\backtest\.venv\Scripts\python.exe -m dojo.session directive --session 2026-07-17-223424 --json '<compact json>'
```

**PowerShell quoting** — nested double-quotes inside `--json` break easily. Write the
directive to a scratch file and inline it instead of hand-quoting:

```powershell
$directive = Get-Content C:\Users\jackw\AppData\Local\Temp\claude\...\scratchpad\dojo_directive.json -Raw
..\..\backtest\.venv\Scripts\python.exe -m dojo.session directive --session 2026-07-17-223424 --json $directive
```

### Directive JSON shape (verified against the SHIPPED `setup/scripts/dojo/directive.py`)

Required raw fields: `issued_et, cursor_et, arms, side, trigger, exits, sizing`.
Optional: `id` (auto-generated `dojo-YYYYMMDD-HHMMSS-<side>` if omitted), `invalidation`
(defaults `{}`), `note` (defaults `""`), `dojo` (must be `true` or omitted — never `false`).

- `issued_et` / `cursor_et` — ISO8601 ET timestamp strings. A trailing UTC offset
  (`-04:00`) is accepted but discarded (the parser truncates to the first 19 chars and
  treats the result as ET wall-clock) — write real ET wall-clock digits, not a UTC time
  with an offset tacked on.
- `arms` — non-empty list of arm-id strings. Valid ids (verified 2026-07-20): the two core
  aliases `"safe"` / `"bold"`, plus every `status=="active"` arm in
  `automation/state/fleet/accounts.json` — today `safe-2, safe-3, bold-2, risky-1, risky-3`
  (`safe-1` is retired; the two futures arms are pending/dormant — neither is a valid dojo
  target). Unknown id = loud `ValueError` naming the exact valid set.
- `side` — `"C"` or `"P"`.
- `trigger` — dict with a `type` in `{level_reject_confirmed_close,
  level_reclaim_confirmed_close, live_bid_cross}` (reuses
  `setup/scripts/j_intent_logic.py::evaluate_trigger`'s vocabulary exactly).
- `invalidation` — dict, e.g. `{"close_above": ...}` / `{"close_below": ...}`.
- `exits` — **ONE flat dict, shared by every arm named in `arms`** — keys restricted to
  `fleet_executor.EXIT_PATCH_ALLOWED_KEYS` (derived from `strategies.ExitShape`:
  `stop_mode, premium_stop_pct, trail_pct, runner_target_pct, tp1_qty_fraction,
  profit_lock_mode, profit_lock_arm_pct, profit_lock_arm_scope, catastrophe_stop_pct,
  tp1_premium_pct`). **Any other key — including a per-arm-id key — is rejected.** This is
  the one place the frozen contract's prose ("per-arm exit overrides") reads more flexibly
  than what shipped: see the KNOWN GAP box below.
- `sizing` — dict, e.g. `{"qty": "tier"}` or `{"qty": 3}`.

### KNOWN GAP — one directive call cannot give two DIFFERENT arms two DIFFERENT exits

Empirically verified 2026-07-20: a single directive with `arms: ["risky-3", "risky-1"]`
and a nested `exits: {"risky-3": {...}, "risky-1": {...}}` is **rejected** —
`parse_and_validate` treats `"risky-3"`/`"risky-1"` as unknown `exit_patch` keys (`exits`
is validated as ONE flat `ExitShape` patch, not a per-arm map). The spec's own words ("this
put on two of the arms, this stop for one of them") describe exactly this need, but the
shipped schema can only express it as **two separate directive calls, one per arm** (below).
**Log this as a Lane-A capability gap at session close** (§4) if J wants a single call to
carry per-arm exits — it is real plumbing work (extending `exits` to accept either a flat
dict OR an `{arm_id: patch}` map), not a policy question, so it ships without Fable review.

### Concrete example — J directs 2 arms with different exits (2 directive calls)

Scenario: J watches a rejection form at a zone and says: *"put a put on LOOSE-R and
TIGHT-R off this reject — let LOOSE ride the zone, TIGHT scalp it with a tight stop."*
(Levels below are illustrative placeholders, not real market data.) Issue it as two calls,
same trigger/invalidation, different `arms` + `exits`:

**Call 1 — FLEET-LOOSE-R (`risky-3`), zone-ride:**

```json
{
  "issued_et": "2026-07-17T10:15:00",
  "cursor_et": "2026-07-17T10:15:00",
  "arms": ["risky-3"],
  "side": "P",
  "trigger": {
    "type": "level_reject_confirmed_close",
    "tag_level": 640.00,
    "confirm_close_below": 639.85,
    "require_red_bar": true
  },
  "invalidation": {"close_above": 640.40},
  "sizing": {"qty": "tier"},
  "exits": {"stop_mode": "structure", "profit_lock_mode": "trailing", "trail_pct": 0.20, "runner_target_pct": 3.0},
  "note": "J: LOOSE-R rides the zone off this reject",
  "dojo": true
}
```

**Call 2 — FLEET-TIGHT-R (`risky-1`), tight stop, same trigger:**

```json
{
  "issued_et": "2026-07-17T10:15:00",
  "cursor_et": "2026-07-17T10:15:00",
  "arms": ["risky-1"],
  "side": "P",
  "trigger": {
    "type": "level_reject_confirmed_close",
    "tag_level": 640.00,
    "confirm_close_below": 639.85,
    "require_red_bar": true
  },
  "invalidation": {"close_above": 640.40},
  "sizing": {"qty": "tier"},
  "exits": {"stop_mode": "premium", "premium_stop_pct": -0.15, "trail_pct": 0.08, "tp1_qty_fraction": 0.8},
  "note": "J: TIGHT-R scalps the same reject, tight -15% premium stop",
  "dojo": true
}
```

Both JSON bodies were run end-to-end through the real CLI (`python -m dojo.session
directive`, 2026-07-20) and captured cleanly — `id` auto-generates from `issued_et`+`side`
if omitted (e.g. `dojo-20260717-101500-p` for both, since both share the same trigger
moment and side; pass an explicit `id` if you need the two calls to have distinct ledger
ids, e.g. `"dojo-2026-07-17-1015-loose"` / `"...-tight"`, as used above).

> **RESOLVED BUG (found + fixed same session, 2026-07-20):** `session.py`'s five lazy
> submodule imports (`engine_step`, `whisper`, `directive`, `sim_executor`, `scorecard`)
> were originally bare (`import directive as dojo_directive`), which can never resolve
> because `setup/scripts/dojo/` is never itself on `sys.path` (only its parent
> `setup/scripts/` is) — every one of those five would have silently reported "not built
> yet" forever, even once fully shipped, blocking success criterion 1. Fixed to `from dojo
> import <module>` (matching the `from dojo import clock` pattern already used at the top
> of `session.py`) — verified below: `directive` now arms correctly through the CLI. If you
> ever see "`<module>` not built yet" for a module you know exists on disk, re-check this
> import shape first before assuming the sibling module itself is broken.

**If J directs something this shape literally cannot express** ("trail only 2 of the 3
contracts", "stop above that specific wick not the level") — that IS a Lane-A capability
gap. Log it in the moment (a plain-text ledger note is fine if `directive` rejects it) and
carry it into the harvest (§4). Never silently approximate J's intent into the nearest
expressible shape — a capability gap that gets quietly rounded off never gets fixed.

Real CLI response (2026-07-20, verified after the import fix — call 1 shown, call 2 is
identical with `directive_id: "dojo-2026-07-17-1015-tight"` / `armed_arms: ["risky-1"]`):

```json
{"ok": true, "session_id": "2026-07-17-224503", "directive_id": "dojo-2026-07-17-1015-loose", "armed_arms": ["risky-3"]}
```

---

## 4. Closing the session

**(a) Stop TV replay:**

```
mcp__tradingview__replay_stop()
```

**(b) Close the dojo session:**

```powershell
..\..\backtest\.venv\Scripts\python.exe -m dojo.session close --session 2026-07-17-223424
```

Real output (2026-07-20, after the two directive calls in §3, before `scorecard.py` ships):

```json
{
  "ok": true,
  "session_id": "2026-07-17-224503",
  "steps": 1,
  "directives": 2,
  "scorecard": "scorecard module not built yet (Phase 1b)",
  "harvest_stub": "C:\\Users\\jackw\\Desktop\\42\\automation\\state\\dojo\\sessions\\2026-07-17-224503-harvest.md"
}
```

Once `scorecard.py` ships, `scorecard` carries per-arm J-directed vs engine-actual /
engine-counterfactual P&L — the prospective J-edge-capture measurement.

**(c) Fill in the harvest doc** at `harvest_stub` — this is mandatory, not optional ("a
session without a harvest doc didn't happen", per the spec). The stub is pre-templated with
two sections; route **every** divergence from the session into exactly one:

### LANE A — capability gap ("the code CANNOT express what J directed")

Ships immediately as a knob/plumbing fix — expressiveness is never overfitting.

- [ ] Write the item into the harvest doc under `## LANE A`.
- [ ] Add a matching entry to `automation/overnight/queue.md`'s Active backlog, format:
      `- [ ] <ID> (<priority>) :: <description> :: depends:none :: status:pending`. Example
      ID pattern: `DOJO-LANE-A-<short-slug>`.
- [ ] Sonnet ships Lane A directly — no Fable adjudication needed.

### LANE B — policy rule ("the engine SHOULD do X when Y")

Becomes a pre-registered hypothesis, run through the EXISTING validation stack
(pre-reg → population replay via `exit_manager_walk` → OP-16 gates) before any live wire.
J's judgment picks WHAT to test; the battery decides what SHIPS.

- [ ] Write the item into the harvest doc under `## LANE B`.
- [ ] File a pre-reg stub at `analysis/recommendations/<slug>.json` (see any existing file
      in that directory for the shape: `strategy`, `stage`, `gates`, `anchor_days`,
      `disclosures` — the anchor day is literally this replay day).
- [ ] Fable adjudicates Lane-B ship/kill calls — do not self-ship a Lane-B item.

**No third lane.** If you're unsure which lane an item belongs to, ask: "could the code
already express this if the exit_patch/trigger vocabulary were wired differently?" — yes =
Lane A (plumbing), no = Lane B (the engine's judgment would have to change).

---

## 5. Directive-capture cheat sheet (per tick)

| You do | Tool/CLI | What comes back |
|---|---|---|
| Advance one bar | `mcp__tradingview__replay_step()` | (no payload) |
| Read the clock | `mcp__tradingview__replay_status()` | `current_date` epoch |
| Ask the engine | `python -m dojo.session step --session <id> --cursor <epoch>` | `bar_et`, `whisper` |
| Relay to J | (you, verbatim) | J's spoken directive or silence |
| Log a trade | `python -m dojo.session directive --session <id> --json '<dir>'` | `directive_id`, `armed_arms` |
| End the day | `mcp__tradingview__replay_stop()` then `python -m dojo.session close --session <id>` | `scorecard`, `harvest_stub` |

---

## 6. Curriculum (from DOJO-REPLAY-TRAINING-SPEC.md §6 — use in this order)

1. **2026-07-17** — the +$679 day (known-good, engine performed well).
2. **2026-07-20** — red day, stale-sight day (known-bad, a real failure mode to relive).
3. **2026-06-30** — HTF-level miss J called out.
4. **2026-07-02** — HTF-level miss J called out.
5. **2026-07-08** — HTF-level miss J called out.
6. Random days — once the ritual works end-to-end (post session 3, per success criterion
   2: zero directives the schema can't express).
7. Adversarially-selected days (engine/J likely to disagree) — later still, once Lane B has
   shipped at least one hypothesis.

---

## 7. Build status as of 2026-07-20 (update this section as modules land)

| Module | Owner | Status |
|---|---|---|
| `clock.py` | Opus (spine) | Shipped, guard-tested (`backtest/tests/test_dojo_clock.py`) |
| `session.py` | Opus (spine) | Shipped, guard-tested (`backtest/tests/test_dojo_fence.py`). Its lazy-import bug (§3) was found and fixed same-session, 2026-07-20. |
| `engine_step.py` | Agent A | Not yet on disk — `step` degrades gracefully with a clear "not built yet" whisper |
| `whisper.py` | Agent B | **Shipped and wired** — blocked from actually rendering only by `engine_step.py`'s absence (`cmd_step` imports both together) |
| `directive.py` | Agent B | **Shipped, wired, verified end-to-end through the CLI** (§3) — directives capture cleanly today |
| `sim_executor.py` | Agent C | Not yet on disk — no-op (directives log + arm but don't sim-fill) |
| `scorecard.py` | Agent C | Not yet on disk — `close` reports the placeholder string |

A session is fully worth running now — directive capture (§3) already works end-to-end.
Once `engine_step.py` lands, `step`'s whisper starts rendering for real with zero runbook
changes needed. `sim_executor.py`/`scorecard.py` landing later loses nothing already
captured — directives + harvest items logged today are real data the moment those ship.

---

## 8. Troubleshooting

- **`step`/`directive`/`close` say "`<module>` not built yet" even though the module file
  exists on disk** — first check whether the message is a genuine `No module named
  '<module>'` (the module really isn't written yet — correct, expected) vs. a `cannot
  import name '<module>' from 'dojo'` (the file exists but something inside it fails to
  import, e.g. it imports a sibling module that ALSO doesn't exist yet — `whisper.py` shows
  this shape today because `cmd_step` imports it alongside the still-missing
  `engine_step.py`). session.py's own lazy-import shape (§3 RESOLVED BUG note) was the
  historical third cause — already fixed 2026-07-20; if it ever regresses to a bare `import
  <module>` instead of `from dojo import <module>`, that's the tell.
- **`step` says "no dojo session `<id>` at ..."** — you didn't `start` first, or you typo'd
  the session id. Run `status --session <id>` to check.
- **`directive` returns `"can only issue a directive while STEPPING"`** — you called
  `directive` before any `step` (phase is still `CREATED`), or after `close` (phase is
  `CLOSED`). Step at least once first.
- **TV cursor and dojo `bar_et` disagree by more than one bar** — STOP. This is the
  lockstep invariant the architecture doc calls load-bearing. Do not keep stepping through
  a drift; log it, and restart the session rather than let J train against a mismatched
  clock.
- **Fence violation (`PermissionError` from `_assert_under_dojo`)** — you or a module tried
  to write outside `automation/state/dojo/`. This should never happen from the CLI itself;
  if it does, STOP and treat it as a build bug, not something to route around.
- **Any git operation inside a dojo module** — should never happen (see
  `backtest/tests/test_dojo_fence.py`); this was the exact 2026-07-20
  STATE-FILE-REVERSION scar. If you ever see `git` invoked from inside `setup/scripts/dojo/`,
  stop and flag it — do not silently let it run.
