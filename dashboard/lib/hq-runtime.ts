// PANEL-2 (2026-09-14): "is it running on my PC, or is this whole thing agents
// running on my PC? Do I really have this many active agents on my PC?" --
// J's verbatim question (2026-09-14 ~18:20 ET), routed to a standing
// instrument instead of a one-off answer, per this task's own brief: "never
// hardcoded prose, never invented."
//
// TRUTH ESTABLISHED THIS SESSION (verified against real files + a live
// `tasklist` capture, not assumed -- see each row below for the evidence):
//
//   Pilot            -- heartbeat_core.py via Gamma_HeartbeatCore. Deterministic
//                        Python, $0, no LLM anywhere in the tick. THIS PC.
//                        (company-roster.json; SCHEDULED-TASKS.md line 225;
//                        CLAUDE.md "Free-model veto DISABLED".)
//   Scout            -- scout_feed.py runs INSIDE Gamma_Station every ~30 min,
//                        no LLM (company-roster.json's own R1 note: "Scout is
//                        never 'done' between deep briefs"). THIS PC. A SEPARATE
//                        once-daily fire, Gamma_ScoutPremarket (05:30 ET), is a
//                        real claude.exe process hitting Anthropic directly --
//                        run-scout-premarket.ps1 does NOT dot-source _brain.ps1
//                        (confirmed: grep for _brain.ps1 dot-source across
//                        setup/scripts/*.ps1 does not list it), so that half
//                        spends real Max-plan tokens. The roster's own tracked
//                        deliverable (scout-feed-summary.json) is the python
//                        half, so that is what this module classifies Scout as.
//   Coach            -- sector_rows.py + coach_notes.py inside Gamma_Station,
//                        every 30 min, deterministic ("written on every fire,
//                        yielded or not" -- company-roster.json). THIS PC.
//   Chef             -- hypothesis_scorer.py inside Gamma_Station
//                        (score_testing_cards, "runs even when the LLM
//                        yields" -- company-roster.json). THIS PC.
//   Gamma (Manager)  -- station_loop.py's OWN model call inside Gamma_Station
//                        (every 30 min, 24/7) hits a LOCAL Ollama model
//                        (brain-mode.json: mode "local", map.sonnet/opus ->
//                        "gamma-planner-fast", proxy on 11435 -> ollama on
//                        11434) -- a real local-LLM inference call on J's own
//                        GPU, zero Anthropic tokens. THIS PC. A separate task,
//                        Gamma_Conductor (3x/day, "opus judgment"), is
//                        CONFIRMED DISABLED in sectors.json's own
//                        task_health.disabled list this session -- dark, not
//                        running, regardless of what CLAUDE.md's prose says.
//   Analyst          -- Gamma_AnalystEodReview: run-analyst-eod.ps1 tries a
//                        free-tier ladder first, only escalates to a Claude
//                        fire on total failure, and even that fire is
//                        brain-routed (dot-sources _brain.ps1). THIS PC.
//   Treasurer        -- Gamma_TreasurerWeekly: run-treasurer-weekly.ps1 DOES
//                        dot-source _brain.ps1 -- a real claude.exe process,
//                        brain-routed to local Ollama when brain-mode.json
//                        says "local" (it does, right now). THIS PC.
//
// COORDINATOR CORRECTION (2026-09-14, same evening): this module's first pass
// saw Gamma_AnalystEodReview / Gamma_TreasurerWeekly / Gamma_Conductor in
// sectors.json's task_health.disabled and reported "DISABLED -- no next
// fire" -- true of the TASK STATE but WRONG about the REASON, and alarming
// where the real story is benign. Verified this session:
// automation/state/quiet-mode.json (`quiet_active: true`, `total_held_down:
// 140`) + automation/state/quiet-mode-restore.json's own `restore_to_ready`
// array (140 entries, Analyst/Treasurer/Conductor all present, Pilot/
// Station/ScoutPremarket all ABSENT) together prove this is
// setup/scripts/quiet_mode.py -- J's own after-hours blackout (J directive
// 2026-08-24, quiet 18:00-23:00 ET every weekday, restores at 23:00) --
// holding ~140 non-essential tasks down for the evening, not a fault. A task
// only reads "DISABLED -- no next fire" now when it is Task-Scheduler-
// disabled AND that is NOT explained by an active quiet-mode hold (see
// resolveTaskDisposition/readQuietModeInfo below); the quiet-mode-explained
// case reads "held by quiet mode until HH:MM ET (fires ...)" instead, on
// every surface this module feeds (RUNS AS row, crew pill via
// lib/personas.ts#taskStateQuietReason equivalent, crew "next:" line).
//
// Independently: a live `tasklist /FO CSV /NH` capture this session (not
// assumed) found 25 claude.exe, 16 pythonw.exe, 2 python.exe, 1 ollama.exe,
// 1 "ollama app.exe", 0 ollama_llama_server.exe, 6 node.exe, 379 processes
// total -- proof that "claude.exe" alone is not one thing: interactive
// sessions (this one included), background agents, and brain-routed
// automation fires all show up as the same image name. That is exactly why
// `roles[].liveNow` below refuses to attribute a bare process count to any
// one persona -- see classifyRole()'s own comment.
//
// SECURITY: readProcessCounts() shells a FIXED argv (no string, no user
// input) and returns counts + raw image names ONLY -- never a command line,
// working directory, or environment variable. hostname (os.hostname()) is
// fine to expose on a 127.0.0.1-only page. Nothing here reads .mcp.json,
// secrets.json, or any credential file.
//
// Server-only. Every fs/child_process read below is independently fail-open
// (try/catch -> a degraded-but-valid default, never a throw) and the whole
// module's own entry point (readHqRuntime) is wrapped a second time, so a
// bug here can only ever degrade /api/hq's new `runtime` field -- it can
// never 500 the rest of the payload (same contract as this route's existing
// safeCollectCompany() wrapper in app/api/hq/route.ts).

import { promises as fs } from "node:fs";
import path from "node:path";
import os from "node:os";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
// Type-only: fully erased by TypeScript (and Node's own type-stripping) --
// produces ZERO runtime import, so personas.ts's own fs/"@/..." import graph
// is never loaded by this module. Deliberate, so this file (and its test)
// stay resolvable under a plain `node --test` with no bundler -- see this
// file's own test for why that matters.
import type { PersonaState } from "./personas";

const execFileAsync = promisify(execFile);

// Deliberately NOT `import { WORKSPACE_ROOT } from "./workspace"` (every
// other lib/*.ts file's convention): that is a value import, and a relative
// .ts -> .ts value import needs an explicit ".ts" specifier to resolve under
// plain `node --test` (verified this session -- without it, ERR_MODULE_NOT_FOUND),
// while writing that extension would trip tsconfig.json's own
// `moduleResolution: "bundler"` (`allowImportingTsExtensions` is not enabled
// there, and that file is shared/out of this builder's ownership to change).
// WORKSPACE_ROOT itself is a one-line env-fallback constant -- duplicated
// here verbatim rather than imported, the same "tiny stable helper
// re-defined per file" convention this codebase already uses for etHHMM
// (personas.ts/crew.ts/hq.ts each carry their own copy).
const WORKSPACE_ROOT = process.env.GAMMA_WORKSPACE ?? "C:\\Users\\jackw\\Desktop\\42";

// ─── Types ────────────────────────────────────────────────────────────────

export interface HqProcessCounts {
  python: number;
  pythonw: number;
  ollama: number;
  ollama_llama_server: number;
  claude: number;
  node: number;
  total: number;
}

export type HqBrainState = "running" | "idle" | "yielding";

export interface HqBrainInfo {
  model: string | null;
  host: "this PC";
  gpu: boolean;
  state: HqBrainState;
  reason: string | null;
  /** Live nvidia-smi utilization.gpu percent (0-100) at the sample the
   * server took building this response, or null when nvidia-smi is
   * unavailable (readGpuVitals's own fail-open path) -- see `busy` below
   * for the derived HQ-render-pause signal built from this. */
  gpu_util_pct: number | null;
  /** True iff the local brain (Ollama) is actively burning GPU on an
   * inference burst -- see isBrainBusy's own doc comment for the exact
   * rule and why it is gated on Ollama having a loaded model, not on
   * gpu_util_pct alone (HQ's own r3f render loop uses the same GPU). */
  busy: boolean;
}

/** GPU-YIELD (queue item e, 2026-09-15): pure busy-rule for "is the local
 * brain (Ollama, on the same RTX 5080 HQ renders on) currently mid-burst,
 * such that HQ should pause/throttle its own render loop." Deliberately
 * NOT `gpu_util_pct > threshold` alone -- HQ's own PBR + N8AO + DoF +
 * GodRays stack routinely drives the SAME nvidia-smi utilization.gpu
 * metric past 50% on its own (that's the whole reason this feature
 * exists), so a bare utilization threshold would make HQ pause itself
 * every time it renders hard, a false-positive loop with no burst
 * happening at all. Gating on `modelsLoaded.length > 0` (Ollama actually
 * reporting a loaded model via `ollama ps`, the same source
 * lib/station.ts#readOllamaPs already feeds into deriveBrain's `running`
 * state below) distinguishes "Ollama is doing inference" from "the GPU is
 * busy for some other reason" -- only readable, already-available signals,
 * no separate nvidia-smi --query-compute-apps process list required. A
 * null utilization (nvidia-smi missing) always reads not-busy (fail open,
 * matching every other reader in this file's convention: a courtesy
 * signal, never a safety gate, must never wedge the render loop paused on
 * a permanently-missing nvidia-smi). */
export function isBrainBusy(
  modelsLoaded: string[],
  gpuUtilPct: number | null,
  thresholdPct = 50,
): boolean {
  if (gpuUtilPct === null) return false;
  if (modelsLoaded.length === 0) return false;
  return gpuUtilPct > thresholdPct;
}

export type HqRoleRuntimeKind = "python-script" | "local-llm" | "claude-session" | "none";
export type HqRoleHost = "this PC" | "anthropic-cloud" | "none";

export interface HqRoleRuntime {
  name: string;
  producer: string;
  runtime: HqRoleRuntimeKind;
  host: HqRoleHost;
  schedule: string;
  liveNow: boolean;
  evidence: string;
  nextFire: string;
  /** True iff EVERY one of this role's own tasks is currently disabled AND
   * that is fully explained by quiet_mode.py's active hold (see
   * readQuietModeInfo below) -- a temporary, by-design pause, never "none".
   * Coordinator-directed (2026-09-14): drives the TRUTH header's own count
   * (Hud.tsx) and distinguishes this from a genuinely dark role (`host`
   * reads "none" only when disabled AND NOT explained by quiet mode). */
  heldByQuietMode: boolean;
}

export interface HqRuntime {
  hostname: string;
  snapshotAtEt: string;
  processes: HqProcessCounts | null;
  error?: string;
  brain: HqBrainInfo;
  roles: HqRoleRuntime[];
  /** "23:00" (HH:MM) when quiet_mode.py's blackout is currently active and
   * that time was parseable, else null -- exposed as its OWN top-level
   * field (not re-parsed out of a role's own nextFire/evidence prose in the
   * UI) so Hud.tsx's TRUTH header can build "N of 7 roles held by quiet
   * mode until HH:MM ET" from real, structured data. Coordinator-directed
   * (2026-09-14). */
  quietModeUntilEt: string | null;
}

export interface HqRuntimeInputs {
  /** data.company.personas from the SAME /api/hq poll -- reused, never
   * re-fetched, so this module never duplicates a shell-out or fs read that
   * buildHqResponse() already made this request. */
  personas: PersonaState[];
  /** config.model from lib/station.ts#readStationConfig() (already fetched
   * in route.ts as `config.model`). */
  brainModel: string | null;
  /** models.map(m => m.name) from lib/station.ts#readOllamaPs() (already
   * fetched in route.ts as `models`). */
  ollamaModelsLoaded: string[];
  /** gpu.ok from lib/station.ts#readGpuVitals() (already fetched as `gpu`). */
  gpuOk: boolean;
  /** gpu.util_pct from the SAME lib/station.ts#readGpuVitals() call as
   * gpuOk above -- one more field off an already-fetched, already-5s-cached
   * reader, no new shell-out. GPU-YIELD (queue item e). */
  gpuUtilPct: number | null;
}

// ─── Pure: tasklist CSV parsing (unit-tested, zero fs/child_process) ───────

/** One CSV line -> fields, quote-aware (tasklist's Mem Usage field embeds
 * commas inside quotes, e.g. "1,234,567 K" -- a naive split(",") would
 * miscount fields on any process using >1MB, i.e. almost all of them). No
 * escaped-quote handling beyond doubled-quote ("") since tasklist never
 * emits anything else in this format. */
export function parseCsvLine(line: string): string[] {
  const fields: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') { cur += '"'; i++; } else { inQuotes = false; }
      } else {
        cur += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      fields.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  fields.push(cur);
  return fields;
}

/** `tasklist /FO CSV /NH` stdout -> raw image names (column 0), one per
 * process, in the original casing tasklist reports (e.g. "ollama app.exe").
 * Blank/unparsable lines are skipped, never thrown on. */
export function parseTasklistCsv(text: string): string[] {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const images: string[] = [];
  for (const line of lines) {
    const fields = parseCsvLine(line);
    if (fields[0]) images.push(fields[0]);
  }
  return images;
}

/** Image names -> the fixed counts this instrument reports. EXACT
 * (lowercased) equality only -- never `.includes()` -- because "ollama.exe"
 * literally contains the substring "llama" (o-LLAMA), which would silently
 * double-count it as ollama_llama_server on a naive substring match (caught
 * this session against a live capture: 0 real ollama_llama_server.exe
 * processes were running, but a `*llama*` filter matched "ollama.exe" and
 * "ollama app.exe" anyway). */
export function countProcessImages(images: string[]): HqProcessCounts {
  const norm = images.map((i) => i.toLowerCase());
  const count = (name: string) => norm.filter((n) => n === name).length;
  return {
    python: count("python.exe"),
    pythonw: count("pythonw.exe"),
    ollama: count("ollama.exe") + count("ollama app.exe"),
    ollama_llama_server: count("ollama_llama_server.exe"),
    claude: count("claude.exe"),
    node: count("node.exe"),
    total: norm.length,
  };
}

// ─── Pure: per-persona next-fire text ──────────────────────────────────────
// Deliberately self-contained rather than importing lib/crew.ts's own (very
// similar) helpers: crew.ts transitively imports "@/components/hq/palette"
// via a path-alias specifier, which plain `node --test` cannot resolve
// without a bundler -- reusing it would make this file's own pure functions
// untestable without a full Next.js build. crew.ts's own header already
// established the "intentionally NOT centralized" precedent for the same
// per-persona cadence facts; this is the same call, for a different reason.

const WEEKDAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function etParts(nowMs: number): { minuteOfDay: number; dayOfWeek: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(new Date(nowMs));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  const hour = Number(get("hour")) % 24;
  const minute = Number(get("minute"));
  const dayOfWeek = WEEKDAY_NAMES.findIndex((w) => w.startsWith(get("weekday")));
  return { minuteOfDay: hour * 60 + minute, dayOfWeek: dayOfWeek < 0 ? 0 : dayOfWeek };
}

function nextDailyFireText(targetHH: number, targetMM: number, weekdaysOnly: boolean, nowMs: number): string {
  const { minuteOfDay, dayOfWeek } = etParts(nowMs);
  const target = targetHH * 60 + targetMM;
  const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5;
  const label = `${pad2(targetHH)}:${pad2(targetMM)} ET`;
  if ((!weekdaysOnly || isWeekday) && minuteOfDay < target) return `today ${label}`;
  let d = dayOfWeek;
  for (let i = 1; i <= 7; i++) {
    d = (d + 1) % 7;
    if (!weekdaysOnly || (d >= 1 && d <= 5)) return i === 1 ? `tomorrow ${label}` : `${WEEKDAY_NAMES[d]} ${label}`;
  }
  return label;
}

function nextWeeklyFireText(dayOfWeekTarget: number, targetHH: number, targetMM: number, nowMs: number): string {
  const { minuteOfDay, dayOfWeek } = etParts(nowMs);
  const target = targetHH * 60 + targetMM;
  const label = `${pad2(targetHH)}:${pad2(targetMM)} ET`;
  if (dayOfWeek === dayOfWeekTarget && minuteOfDay < target) return `today ${label}`;
  let daysAhead = (dayOfWeekTarget - dayOfWeek + 7) % 7;
  if (daysAhead === 0) daysAhead = 7;
  return daysAhead === 1 ? `tomorrow ${label}` : `${WEEKDAY_NAMES[(dayOfWeek + daysAhead) % 7]} ${label}`;
}

function nextIntervalFireText(lastFireISO: string | null, intervalMin: number, nowMs: number): string {
  if (!lastFireISO) return "event-driven";
  const lastMs = Date.parse(lastFireISO);
  if (Number.isNaN(lastMs)) return "event-driven";
  const nextMs = lastMs + intervalMin * 60_000;
  if (nextMs <= nowMs) return "due now";
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(new Date(nextMs));
  const hh = parts.find((p) => p.type === "hour")?.value ?? "??";
  const mm = parts.find((p) => p.type === "minute")?.value ?? "??";
  return `~${hh}:${mm} ET`;
}

/** Exported (coordinator-directed, 2026-09-14) so lib/personas.ts's own
 * disabled-task quietReason text can reuse the SAME "what would this
 * persona's next fire normally be" projection for its "(fires ...)"
 * parenthetical, rather than a 3rd reimplementation of this date math. */
export function nextFireForName(name: string, lastFireISO: string | null, nowMs: number): string {
  switch (name) {
    case "Pilot": {
      const { minuteOfDay, dayOfWeek } = etParts(nowMs);
      const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5;
      const rth = isWeekday && minuteOfDay >= 9 * 60 + 30 && minuteOfDay < 15 * 60 + 55;
      return rth ? nextIntervalFireText(lastFireISO, 1, nowMs) : nextDailyFireText(9, 30, true, nowMs);
    }
    case "Scout":
      return nextDailyFireText(5, 30, false, nowMs);
    case "Coach":
    case "Chef":
    case "Gamma (Manager)":
      return nextIntervalFireText(lastFireISO, 30, nowMs);
    case "Analyst":
      return nextDailyFireText(16, 45, true, nowMs);
    case "Treasurer":
      return nextWeeklyFireText(0, 16, 0, nowMs);
    default:
      return "event-driven";
  }
}

function ageMinutes(iso: string | null, nowMs: number): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : Math.max(0, (nowMs - t) / 60000);
}

function hhmmEt(iso: string | null): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(new Date(t));
  const hh = parts.find((p) => p.type === "hour")?.value;
  const mm = parts.find((p) => p.type === "minute")?.value;
  return hh && mm ? `${hh}:${mm}` : null;
}

// ─── Pure: role runtime classification (unit-tested from a roster fixture) ─

/** The 3 fields this module needs out of company-roster.json's own richer
 * per-persona shape -- see automation/state/station/company-roster.json. */
export interface RosterPersonaFixture {
  name: string;
  cadence: string;
  tasks: string[];
}

interface RoleClassificationStatic {
  producer: string;
  runtime: HqRoleRuntimeKind;
  /** Where this role's OWN producer runs when its task(s) are enabled --
   * classifyRole() downgrades this to "none" when every one of the
   * persona's tasks is confirmed disabled. */
  host: HqRoleHost;
}

// The judgment call this file makes explicit: WHICH of python-script /
// local-llm / claude-session each persona's OWN roster deliverable actually
// comes from. Not derivable from any single machine-readable field -- built
// from SCHEDULED-TASKS.md's task rows + the _brain.ps1 dot-source list +
// station_loop.py's own header, all cited in this file's own top comment.
// Static, hand-curated, and expected to change rarely -- same shape as
// crew.ts's own per-persona cadence switch.
const ROLE_CLASSIFICATION: Record<string, RoleClassificationStatic> = {
  "Pilot": {
    producer: "heartbeat_core.py (deterministic, $0) via Gamma_HeartbeatCore",
    runtime: "python-script",
    host: "this PC",
  },
  "Scout": {
    producer: "scout_feed.py inside Gamma_Station (continuous, no LLM); Gamma_ScoutPremarket is a SEPARATE claude.exe deep-brief fire at 05:30 ET, Anthropic-billed",
    runtime: "python-script",
    host: "this PC",
  },
  "Coach": {
    producer: "sector_rows.py + coach_notes.py inside Gamma_Station (deterministic, no LLM)",
    runtime: "python-script",
    host: "this PC",
  },
  "Chef": {
    producer: "hypothesis_scorer.py inside Gamma_Station (deterministic, runs even when the model call yields)",
    runtime: "python-script",
    host: "this PC",
  },
  "Gamma (Manager)": {
    producer: "station_loop.py's own model call inside Gamma_Station -- local Ollama, always-on; Gamma_Conductor (opus judgment, Anthropic) is a separate task, commonly held by the evening quiet-mode blackout -- see evidence/nextFire for its CURRENT state",
    runtime: "local-llm",
    host: "this PC",
  },
  "Analyst": {
    producer: "run-analyst-eod.ps1: free-tier ladder, brain-routed Claude fallback only on failure, via Gamma_AnalystEodReview",
    runtime: "claude-session",
    host: "this PC",
  },
  "Treasurer": {
    producer: "run-treasurer-weekly.ps1, brain-routed via _brain.ps1, via Gamma_TreasurerWeekly",
    runtime: "claude-session",
    host: "this PC",
  },
};

/** "provably mid-fire" tolerance -- deliberately tight. A process count
 * alone can never prove liveness (see this file's own header: 25 claude.exe
 * processes were alive in one live capture, for all sorts of reasons having
 * nothing to do with any one Gamma persona), so `liveNow` additionally
 * requires the persona's OWN last-fire evidence to be within this many
 * minutes -- "plausibly the fire that produced this evidence is still the
 * one running", not "this role fired recently". Everything less fresh than
 * this reads as "scheduled, last ran HH:MM", per this task's own literal
 * spec text. */
const LIVE_WINDOW_MIN = 2;

function relevantProcessCount(counts: HqProcessCounts | null, kind: HqRoleRuntimeKind): number | null {
  if (!counts) return null;
  switch (kind) {
    case "python-script": return counts.python + counts.pythonw;
    case "local-llm": return counts.ollama + counts.ollama_llama_server;
    case "claude-session": return counts.claude;
    case "none": return 0;
  }
}

/** One task-name's full disposition, cross-referencing Task-Scheduler-
 * disabled state against quiet_mode.py's own currently-held set (see this
 * file's own COORDINATOR CORRECTION header comment). Pure -- the single
 * shared source both classifyRole() and lib/personas.ts's disabled-task
 * quietReason text branch on, so the RUNS AS row and the crew pill/next:
 * line can never independently drift apart. */
export interface TaskDisposition {
  /** Every one of `taskNames` is currently Task-Scheduler-disabled. */
  allDisabled: boolean;
  /** `allDisabled` AND every one of those disabled tasks is explained by an
   * ACTIVE quiet-mode hold (never true while quiet mode is inactive, even
   * if the same task names happen to still be disabled for some other
   * reason -- see readQuietModeInfo's own fail-open contract). */
  allHeldByQuietMode: boolean;
  disabledHere: string[];
}

export function resolveTaskDisposition(
  taskNames: string[],
  disabledTaskNames: ReadonlySet<string>,
  quietModeHeldTaskNames: ReadonlySet<string>,
): TaskDisposition {
  const disabledHere = taskNames.filter((t) => disabledTaskNames.has(t));
  const allDisabled = taskNames.length > 0 && disabledHere.length === taskNames.length;
  const heldHere = disabledHere.filter((t) => quietModeHeldTaskNames.has(t));
  const allHeldByQuietMode = allDisabled && heldHere.length === disabledHere.length;
  return { allDisabled, allHeldByQuietMode, disabledHere };
}

/** The exact quietReason text lib/personas.ts's collectAnalyst/
 * collectTreasurer must use in place of their own normal "fresh?" check
 * whenever `resolveTaskDisposition` says the persona's task(s) are fully
 * disabled (coordinator-directed, 2026-09-14) -- pure, so it is
 * unit-testable without fs (see dashboard/tests/hq-runtime.test.ts);
 * taskStateQuietReason below is the thin async fs-reading wrapper personas.ts
 * actually calls. Returns null when the tasks are NOT fully disabled (the
 * caller's own normal logic applies unchanged). */
export function deriveTaskStateReason(
  personaName: string,
  taskNames: string[],
  disabledTaskNames: ReadonlySet<string>,
  quietModeHeldTaskNames: ReadonlySet<string>,
  quietModeUntilEt: string | null,
  lastFireISO: string | null,
  nowMs: number,
): string | null {
  const { allDisabled, allHeldByQuietMode, disabledHere } = resolveTaskDisposition(taskNames, disabledTaskNames, quietModeHeldTaskNames);
  if (!allDisabled) return null;
  if (allHeldByQuietMode) {
    const normalNext = nextFireForName(personaName, lastFireISO, nowMs);
    return `held by quiet mode${quietModeUntilEt ? ` until ${quietModeUntilEt} ET` : ""} (fires ${normalNext})`;
  }
  return `task ${disabledHere.join(", ")} DISABLED -- no next fire`;
}

/** Pure classifier: static producer/runtime/host facts (ROLE_CLASSIFICATION)
 * crossed with THIS poll's live facts (roster fixture, disabled-task set,
 * quiet-mode-held set, the persona's own already-collected evidence, and
 * the process counts) -- zero fs/child_process access, so this is the
 * unit-testable half of the module (see dashboard/tests/hq-runtime.test.ts). */
export function classifyRole(
  name: string,
  roster: RosterPersonaFixture | null,
  disabledTaskNames: ReadonlySet<string>,
  quietModeHeldTaskNames: ReadonlySet<string>,
  quietModeUntilEt: string | null,
  persona: PersonaState | null,
  processCounts: HqProcessCounts | null,
  nowMs: number,
): HqRoleRuntime {
  const stat: RoleClassificationStatic = ROLE_CLASSIFICATION[name] ?? {
    producer: "no producer on file",
    runtime: "none",
    host: "none",
  };
  const tasks = roster?.tasks ?? [];
  const { allDisabled, allHeldByQuietMode, disabledHere } = resolveTaskDisposition(tasks, disabledTaskNames, quietModeHeldTaskNames);
  const schedule = roster?.cadence ?? "unknown -- company-roster.json unavailable this poll";

  const lastFireISO = persona?.lastFireISO ?? null;
  const ageMin = ageMinutes(lastFireISO, nowMs);
  const firedHHMM = hhmmEt(lastFireISO);
  const procCount = relevantProcessCount(processCounts, stat.runtime);
  const normalNextFire = nextFireForName(name, lastFireISO, nowMs);
  const heldSuffix = quietModeUntilEt ? ` until ${quietModeUntilEt} ET` : "";

  const nextFire = !allDisabled
    ? normalNextFire
    : allHeldByQuietMode
      ? `held by quiet mode${heldSuffix} (fires ${normalNextFire})`
      : `DISABLED -- ${disabledHere.join(", ")} not scheduled`;

  const liveNow = !allDisabled && procCount !== null && procCount > 0 && ageMin !== null && ageMin <= LIVE_WINDOW_MIN;

  let evidence: string;
  if (allHeldByQuietMode) {
    evidence = `${disabledHere.join(", ")} held by quiet mode${heldSuffix} -- last evidence ${firedHHMM ?? "none on file"} ET`;
  } else if (allDisabled) {
    evidence = `${disabledHere.join(", ")} DISABLED in Task Scheduler -- last evidence ${firedHHMM ?? "none on file"} ET`;
  } else if (processCounts === null) {
    evidence = `process table unavailable this poll -- last evidence ${firedHHMM ?? "?"} ET`;
  } else if (liveNow) {
    evidence = `${procCount} ${stat.runtime} process(es) alive + evidence ${firedHHMM} ET (<${LIVE_WINDOW_MIN} min ago) -- plausibly mid-fire`;
  } else if (firedHHMM) {
    evidence = procCount !== null && procCount > 0
      ? `scheduled, last ran ${firedHHMM} ET (${procCount} ${stat.runtime.replace("-", " ")} process(es) alive now, not attributable to this role alone)`
      : `scheduled, last ran ${firedHHMM} ET`;
  } else {
    evidence = "no fire on file yet";
  }

  return {
    name,
    producer: stat.producer,
    runtime: stat.runtime,
    // A quiet-mode hold is temporary and by design -- the producer's REAL
    // host never changes, so only a genuinely (non-quiet-mode) disabled
    // role downgrades to "none".
    host: allDisabled && !allHeldByQuietMode ? "none" : stat.host,
    schedule,
    liveNow,
    evidence,
    nextFire,
    heldByQuietMode: allHeldByQuietMode,
  };
}

// ─── fs/child_process readers -- fail-open, never throw ───────────────────

async function readCompanyRoster(): Promise<RosterPersonaFixture[]> {
  try {
    const text = await fs.readFile(
      path.join(WORKSPACE_ROOT, "automation", "state", "station", "company-roster.json"),
      "utf-8",
    );
    const data = JSON.parse(text) as { personas?: unknown };
    if (!Array.isArray(data.personas)) return [];
    const out: RosterPersonaFixture[] = [];
    for (const p of data.personas) {
      if (!p || typeof p !== "object") continue;
      const rec = p as Record<string, unknown>;
      if (typeof rec.name !== "string" || typeof rec.cadence !== "string" || !Array.isArray(rec.tasks)) continue;
      out.push({
        name: rec.name,
        cadence: rec.cadence,
        tasks: rec.tasks.filter((t): t is string => typeof t === "string"),
      });
    }
    return out;
  } catch {
    return [];
  }
}

/** sectors.json's own `task_health.disabled` array -- CREW-RIG's per-fire
 * snapshot of which Gamma_* tasks Get-ScheduledTask currently reports as
 * Disabled (see setup/scripts/audit_scheduled_tasks.py). A separate,
 * independent read from lib/hq.ts#readSectorsSnapshot (which deliberately
 * does not expose task_health -- see that function's own comment on why it
 * only picks 3 fields) rather than widening that shared reader's contract,
 * since MODELS'/LAYOUT's builders already depend on its exact current
 * shape this same pass. */
// Exported (coordinator-directed, 2026-09-14) so lib/personas.ts's
// taskStateQuietReason-equivalent branch reads the EXACT same
// Task-Scheduler-disabled set this module's own classifyRole() does --
// "not a second scheduler query", per that directive -- rather than each
// side maintaining its own copy that could drift.
export async function readDisabledTaskNames(): Promise<Set<string>> {
  try {
    const text = await fs.readFile(
      path.join(WORKSPACE_ROOT, "automation", "state", "station", "sectors.json"),
      "utf-8",
    );
    const data = JSON.parse(text) as { task_health?: { disabled?: unknown } };
    const raw = data.task_health?.disabled;
    return new Set(Array.isArray(raw) ? raw.filter((t): t is string => typeof t === "string") : []);
  } catch {
    return new Set();
  }
}

export interface QuietModeInfo {
  active: boolean;
  /** "23:00" (HH:MM, no "ET" suffix) parsed from quiet-mode.json's own
   * `quiet_window_et` prose -- null when unparseable (fail-open: callers
   * render the hold without a specific end time rather than guessing one). */
  untilEt: string | null;
  /** Task names that are BOTH currently disabled AND on quiet-mode's own
   * restore list -- the intersection, not the raw restore list, so a task
   * disabled for some unrelated reason is never mislabeled "quiet mode"
   * just because quiet mode happens to be active right now. */
  heldTaskNames: Set<string>;
}

let quietModeCache: { data: QuietModeInfo; at: number } | null = null;
const QUIET_MODE_CACHE_MS = 30_000;

/** automation/state/quiet-mode.json + automation/state/quiet-mode-restore.json
 * -- J's after-hours blackout (setup/scripts/quiet_mode.py, J directive
 * 2026-08-24: "everything needs to be turned off after market hours"), NOT
 * a fault. See this file's own COORDINATOR CORRECTION header comment for
 * the verification this session (quiet-mode.json's `total_held_down: 140`;
 * Analyst/Treasurer/Conductor all present in quiet-mode-restore.json's
 * `restore_to_ready`; Pilot/Station/ScoutPremarket all absent from it).
 * Two small JSON reads, 30s-cached alongside the process-count cache
 * (coordinator-directed) -- no scheduler shell-out here at all (the
 * PowerShell call that actually queries Task Scheduler lives inside
 * audit_scheduled_tasks.py, run by the 30-min Station loop, not by this
 * route). Fail-open: any read/parse failure degrades to "quiet mode
 * inactive, nothing held" -- never blocks a genuinely-disabled task from
 * reading as disabled just because this file couldn't be read. */
async function readQuietModeInfo(disabledTaskNames: ReadonlySet<string>): Promise<QuietModeInfo> {
  if (quietModeCache && Date.now() - quietModeCache.at < QUIET_MODE_CACHE_MS) return quietModeCache.data;
  const inactive: QuietModeInfo = { active: false, untilEt: null, heldTaskNames: new Set() };
  try {
    const [modeText, restoreText] = await Promise.all([
      fs.readFile(path.join(WORKSPACE_ROOT, "automation", "state", "quiet-mode.json"), "utf-8"),
      fs.readFile(path.join(WORKSPACE_ROOT, "automation", "state", "quiet-mode-restore.json"), "utf-8"),
    ]);
    const mode = JSON.parse(modeText) as { quiet_active?: unknown; quiet_window_et?: unknown };
    const active = mode.quiet_active === true;
    const windowText = typeof mode.quiet_window_et === "string" ? mode.quiet_window_et : "";
    // quiet-mode.json's own prose shape: "quiet 18:00-23:00 ET every day
    // (J's evening); LOUD maintenance 23:00-08:00; ..." -- the SECOND
    // captured time is the restore time this hold ends at.
    const m = /quiet (\d{2}:\d{2})-(\d{2}:\d{2}) ET/.exec(windowText);
    const untilEt = m ? m[2] : null;
    if (!active) {
      const data: QuietModeInfo = { active: false, untilEt, heldTaskNames: new Set() };
      quietModeCache = { data, at: Date.now() };
      return data;
    }
    const restore = JSON.parse(restoreText) as { restore_to_ready?: unknown };
    const restoreList = Array.isArray(restore.restore_to_ready)
      ? restore.restore_to_ready.filter((t): t is string => typeof t === "string")
      : [];
    const restoreSet = new Set(restoreList);
    const heldTaskNames = new Set([...disabledTaskNames].filter((t) => restoreSet.has(t)));
    const data: QuietModeInfo = { active: true, untilEt, heldTaskNames };
    quietModeCache = { data, at: Date.now() };
    return data;
  } catch {
    quietModeCache = { data: inactive, at: Date.now() };
    return inactive;
  }
}

/** Thin async wrapper around deriveTaskStateReason -- the two fs reads
 * (readDisabledTaskNames, readQuietModeInfo) both cached, so calling this
 * from BOTH collectAnalyst and collectTreasurer within the same /api/hq
 * request costs no extra scheduler work, just cheap cache hits after the
 * first call. lib/personas.ts is the only intended caller. */
export async function taskStateQuietReason(
  personaName: string,
  taskNames: string[],
  lastFireISO: string | null,
  nowMs: number,
): Promise<string | null> {
  const disabledTaskNames = await readDisabledTaskNames();
  const quiet = await readQuietModeInfo(disabledTaskNames);
  return deriveTaskStateReason(personaName, taskNames, disabledTaskNames, quiet.heldTaskNames, quiet.untilEt, lastFireISO, nowMs);
}

let processCache: { data: HqProcessCounts; at: number } | null = null;
const PROCESS_CACHE_MS = 30_000;

/** `tasklist /FO CSV /NH` -- fixed argv via execFile (no shell string, no
 * user input reaches the command line), read-only, 30s in-memory cache so
 * concurrent/rapid /api/hq polls never spawn it more than twice a minute
 * (verified: proof step polls /api/hq 60x back-to-back -- this cache is
 * what keeps that from spawning tasklist 60 times). Fail-open: a spawn
 * failure (tasklist missing, timeout) degrades to `{counts: null, error}`,
 * never a throw. */
export async function readProcessCounts(): Promise<{ counts: HqProcessCounts | null; error?: string }> {
  if (processCache && Date.now() - processCache.at < PROCESS_CACHE_MS) return { counts: processCache.data };
  try {
    const { stdout } = await execFileAsync("tasklist", ["/FO", "CSV", "/NH"], { timeout: 5000, windowsHide: true });
    const counts = countProcessImages(parseTasklistCsv(stdout));
    processCache = { data: counts, at: Date.now() };
    return { counts };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { counts: null, error: `tasklist failed: ${message}` };
  }
}

function hhmmssEt(nowMs: number): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(new Date(nowMs)) + " ET";
}

/** Gamma (Manager)'s own quietReason already carries the Station loop's
 * "yields <reason>" text (lib/personas.ts#collectGammaManager, sourced from
 * loop-ledger.jsonl's own `status`/`reason` fields) -- reused here rather
 * than re-reading the ledger a second time. `running` is only ever claimed
 * when Ollama itself reports a loaded model (readOllamaPs, threaded in via
 * inputs.ollamaModelsLoaded) -- a fire that hasn't started its model call
 * yet, or already finished and Ollama's keep-alive expired, honestly reads
 * `idle`, never a guessed `running`. */
function deriveBrain(
  gammaManager: PersonaState | null,
  model: string | null,
  modelsLoaded: string[],
  gpuOk: boolean,
  gpuUtilPct: number | null,
): HqBrainInfo {
  const busy = isBrainBusy(modelsLoaded, gpuUtilPct);
  const reason = gammaManager?.quietReason ?? null;
  if (reason && reason.startsWith("yields")) {
    return { model, host: "this PC", gpu: gpuOk, state: "yielding", reason, gpu_util_pct: gpuUtilPct, busy };
  }
  if (modelsLoaded.length > 0) {
    return { model, host: "this PC", gpu: gpuOk, state: "running", reason: `${modelsLoaded.join(", ")} loaded`, gpu_util_pct: gpuUtilPct, busy };
  }
  return { model, host: "this PC", gpu: gpuOk, state: "idle", reason: reason ?? "no model currently loaded in Ollama", gpu_util_pct: gpuUtilPct, busy };
}

/** Fixed roster order -- Gamma (Manager) first, matching lib/personas.ts's
 * own collectCompany() order (the same order data.company.personas already
 * renders in). */
const ROSTER_ORDER = ["Gamma (Manager)", "Scout", "Coach", "Pilot", "Analyst", "Chef", "Treasurer"];

async function buildHqRuntime(inputs: HqRuntimeInputs): Promise<HqRuntime> {
  const nowMs = Date.now();
  const [roster, disabledTaskNames, processResult] = await Promise.all([
    readCompanyRoster(),
    readDisabledTaskNames(),
    readProcessCounts(),
  ]);
  // Depends on disabledTaskNames (the intersection with the restore list),
  // so sequential after the Promise.all above -- readQuietModeInfo has its
  // own 30s cache, so this costs a real read only once per cache window.
  const quiet = await readQuietModeInfo(disabledTaskNames);
  const rosterByName = new Map(roster.map((r) => [r.name, r]));
  const personaByName = new Map(inputs.personas.map((p) => [p.name, p]));

  const roles = ROSTER_ORDER.map((name) =>
    classifyRole(
      name,
      rosterByName.get(name) ?? null,
      disabledTaskNames,
      quiet.heldTaskNames,
      quiet.untilEt,
      personaByName.get(name) ?? null,
      processResult.counts,
      nowMs,
    ),
  );

  return {
    hostname: os.hostname(),
    snapshotAtEt: hhmmssEt(nowMs),
    processes: processResult.counts,
    ...(processResult.error ? { error: processResult.error } : {}),
    brain: deriveBrain(personaByName.get("Gamma (Manager)") ?? null, inputs.brainModel, inputs.ollamaModelsLoaded, inputs.gpuOk, inputs.gpuUtilPct),
    roles,
    quietModeUntilEt: quiet.active ? quiet.untilEt : null,
  };
}

/** Entry point. Wrapped a second time on top of every reader's own
 * try/catch (belt-and-suspenders, matching this route's existing
 * safeCollectCompany() contract in app/api/hq/route.ts) -- a bug here can
 * only ever degrade the `runtime` field of /api/hq's response, never 500
 * the whole payload. */
export async function readHqRuntime(inputs: HqRuntimeInputs): Promise<HqRuntime> {
  try {
    return await buildHqRuntime(inputs);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("[hq-runtime] readHqRuntime() threw past every reader's own fail-open guard:", err);
    return {
      hostname: "unknown",
      snapshotAtEt: hhmmssEt(Date.now()),
      processes: null,
      error: `readHqRuntime failed: ${message}`,
      brain: { model: inputs.brainModel ?? null, host: "this PC", gpu: false, state: "idle", reason: null, gpu_util_pct: null, busy: false },
      roles: [],
      quietModeUntilEt: null,
    };
  }
}
