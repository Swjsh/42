"use client";

import { useRef } from "react";
import type { HqApiResponse, CoreDecisionRow } from "@/components/hq/types";
import { computePurposefulWalk } from "@/components/hq/palette";

export interface MotionEvent {
  id: number;
  tsEt: string;
  text: string;
}

const MAX_EVENTS = 5;

function etHHMM(): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date());
}

function truncate(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

function hopKey(from: string, to: string, evidence: string): string {
  return `${from}->${to}::${evidence}`;
}

/** I2 (INTERACT-2, 2026-09-14): one already-seen key per crew-events.jsonl
 * row -- ts_et+who+kind is unique per real fire (the producer writes one row
 * per real unit of work, see the crew-events.jsonl schema in this task's own
 * brief), so no separate id field is needed. */
function crewEventKey(row: { ts_et: string; who: string; kind: string }): string {
  return `${row.ts_et}|${row.who}|${row.kind}`;
}

/** "HH:MM" out of a ts_et string, tolerant of both the "T"-separated
 * (core-decisions.jsonl) and " "-separated (crew-events.jsonl / station
 * loop ledgers) shapes this codebase's various producers use. */
function hhmmOf(tsEt: string): string {
  const m = /[T ](\d{2}):(\d{2})/.exec(tsEt);
  return m ? `${m[1]}:${m[2]}` : "";
}

/** "YYYY-MM-DD" out of a ts_et string -- used to fire event (f) at most once
 * per ET calendar day. */
function etDateOf(tsEt: string): string {
  return /^(\d{4}-\d{2}-\d{2})/.exec(tsEt)?.[1] ?? tsEt;
}

/** Whichever of the two live accounts' core-decisions row ticked most
 * recently -- tsEt string-sorts correctly (no offset, "YYYY-MM-DD[T ]HH:MM:SS"),
 * same convention Scene.tsx's own `latestDecision` pick already uses. */
function pickLatestCoreDecision(data: HqApiResponse): CoreDecisionRow | null {
  const rows = [data.trading?.core?.safe, data.trading?.core?.bold].filter(
    (r): r is CoreDecisionRow => !!r && !!r.tsEt,
  );
  if (rows.length === 0) return null;
  return rows.sort((a, b) => a.tsEt.localeCompare(b.tsEt)).pop() ?? null;
}

/** ET string ("2026-09-14 02:21:00 ET" -- station-brief/loop-ledger's own
 * format) or a real ISO string (PersonaState.lastFireISO, WITH a timezone
 * offset) -> a comparable sort key. The two need different handling: an ET
 * string has NO offset, so `Date.parse` would read it as the BROWSER's
 * local time (this codebase's own standing TZ bug, CLAUDE.md's own
 * lesson) -- parsed by digits instead, "as if UTC" (wrong in absolute
 * terms, but self-consistent for sorting since every ET-labeled value uses
 * the same trick). A real ISO string parses correctly via Date.parse, then
 * its ET-timezone digits are re-extracted via Intl and fed through the
 * SAME "as if UTC" trick -- so both source shapes land in one comparable
 * unit. Returns null on anything unparsable (an event that can't be
 * time-sorted honestly is dropped, never guessed into the wrong slot). */
function toComparableEtMs(raw: string): number | null {
  const etMatch = /(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/.exec(raw);
  if (etMatch && /ET\s*$/.test(raw)) {
    const [, y, mo, d, h, mi, s] = etMatch.map(Number);
    return Date.UTC(y, mo - 1, d, h, mi, s);
  }
  const parsed = Date.parse(raw);
  if (Number.isNaN(parsed)) return null;
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).formatToParts(new Date(parsed));
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? "0");
  const hour = get("hour") % 24;
  return Date.UTC(get("year"), get("month") - 1, get("day"), hour, get("minute"), get("second"));
}

/** Ticker seed (Pass G, 2026-09-13, coordinator: "a fresh page shows the
 * last hour of the company" instead of the blank 'no events yet' state
 * every viewer saw on load). Two REAL-timestamped sources, both already on
 * the wire (zero new producers): brainVitals.fireTimeline (Gamma_Station's
 * own loop-ledger tail, readLedgerTail(10) in app/api/hq/route.ts) and
 * each persona's own lastFireISO. Merged, sorted newest-first by the
 * comparable key above, top 3 kept -- matching the live ticker's own
 * "newest first, 3 max" shape exactly, just computed once up front instead
 * of accumulated one poll at a time. Idea-card and handoff seeding were
 * considered and left out: StationIdeaCard has a real ts_et field (a
 * future addition could fold it in), but Handoff carries NO timestamp
 * field at all -- fabricating one to sort by would violate "every line
 * names a real event" by lying about the ORDER, not just inventing text. */
function buildSeedEvents(data: HqApiResponse): MotionEvent[] {
  const candidates: { ms: number; tsEt: string; text: string }[] = [];

  const fireTimeline = (data.brainVitals?.fireTimeline ?? []) as Array<{ ts_et?: string; cards_added?: number; status?: string; reason?: string }>;
  for (const row of fireTimeline) {
    if (!row.ts_et) continue;
    const ms = toComparableEtMs(row.ts_et);
    if (ms === null) continue;
    const hhmm = row.ts_et.slice(11, 16);
    const added = row.cards_added ?? 0;
    const text = row.status === "yielded"
      ? `Station fire ${hhmm} ET -> yielded (${row.reason ?? "GPU busy"})`
      : added > 0
        ? `Station fire ${hhmm} ET -> ${added} card${added === 1 ? "" : "s"} added`
        : `Station fire ${hhmm} ET -> nothing new`;
    candidates.push({ ms, tsEt: hhmm, text });
  }

  for (const p of data.company?.personas ?? []) {
    if (!p.lastFireISO) continue;
    const ms = toComparableEtMs(p.lastFireISO);
    if (ms === null) continue;
    const d = new Date(ms);
    const hhmm = `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
    candidates.push({ ms, tsEt: hhmm, text: `${p.emoji} ${p.name} fired` });
  }

  candidates.sort((a, b) => b.ms - a.ms);
  return candidates.slice(0, 3).map((c, i) => ({ id: -1000 - i, tsEt: c.tsEt, text: c.text }));
}

/**
 * "They need MEANING" (J 2026-09-13): every agent walk must trace to a
 * real, nameable event, and the HUD must SAY what it was. This hook is the
 * "say what it was" half -- pure logging, diffing successive /api/hq polls
 * into a small human-readable list for Hud.tsx's event ticker. It does NOT
 * drive any 3D animation itself; Agent.tsx/Courier.tsx independently diff
 * the same underlying fields (lastFireISO, card id+status, handoff
 * evidence) to decide whether to actually walk. Two decoupled readers of
 * one truth (`data`), not two sources of truth -- kept separate because
 * this hook must run in app/hq/page.tsx (outside the <Canvas>, where
 * Hud.tsx lives) while the walk-triggering happens inside Scene.tsx/Agent
 * (inside the <Canvas>); threading one shared object across that boundary
 * would cost more prop-plumbing than the small duplication it would save.
 *
 * Every diff below seeds silently on the first poll it ever sees (matching
 * Courier.tsx/HandoffCourier.tsx's own seen-id-diff convention) so a page
 * load never produces a burst of "N events just happened" -- only a
 * genuine change AFTER that is logged.
 */
export function useMotionEvents(data: HqApiResponse | undefined): MotionEvent[] {
  const events = useRef<MotionEvent[]>([]);
  const nextId = useRef(0);
  const seeded = useRef(false);

  const prevCardStatus = useRef<Map<string, string>>(new Map());
  const prevPersonaFire = useRef<Map<string, string | null>>(new Map());
  const prevHandoffOk = useRef<Set<string>>(new Set());
  const prevLaneHealth = useRef<Map<string, string>>(new Map());
  const prevPersonaStatus = useRef<Map<string, string>>(new Map());
  const prevGaming = useRef<boolean | null>(null);
  const prevPresent = useRef<boolean | null>(null);
  const prevBriefMtime = useRef<number | null | undefined>(undefined);
  // Item 2b (LIVE-1, 2026-09-14): purposeful-walk ticker -- keyed on
  // palette.ts#computePurposefulWalk's own `bucketKey`, the SAME pure
  // function Scene.tsx calls to actually queue the walk. Two decoupled
  // readers of one truth (this hook runs OUTSIDE <Canvas>, in page.tsx;
  // the walk itself is queued INSIDE it, in Scene.tsx/Agent.tsx) -- see
  // this file's own header comment for why that split exists at all.
  const prevWalkBucket = useRef<Map<string, string>>(new Map());
  // I2 (INTERACT-2, 2026-09-14): event kinds (a)-(f) -- each diffs a real
  // on-disk signal already on the wire (crewEvents rows, a persona's own
  // deliverable.mtimeISO, a desk's own source `path`, or the day's first
  // post-close core-decision row). Every ref below seeds silently on the
  // first poll (same convention as every diff above) so a page load never
  // fires a burst of "just happened" events for state that already existed.
  const seenCrewEventKeys = useRef<Set<string> | null>(null);
  const prevScoutMtime = useRef<string | null | undefined>(undefined);
  const prevAnalystDeskPath = useRef<string | null | undefined>(undefined);
  const prevTreasurerDeskPath = useRef<string | null | undefined>(undefined);
  const seenPostCloseEtDate = useRef<string | null>(null);

  if (!data) return events.current;

  const push = (text: string) => {
    nextId.current += 1;
    events.current = [{ id: nextId.current, tsEt: etHHMM(), text }, ...events.current].slice(0, MAX_EVENTS);
  };

  const cards = data.ideas?.cards ?? [];
  const personas = data.company?.personas ?? [];
  const handoffs = data.company?.handoffs ?? [];
  const rows = data.sectors?.rows ?? [];
  const gaming = data.mode === "gaming";
  const present = data.presence?.present ?? null;

  if (!seeded.current) {
    // First poll ever: seed every map/set (unchanged -- live diffing below
    // still only logs a GENUINE change after this point) AND populate the
    // ticker from real past events (Pass G, 2026-09-13) instead of leaving
    // it blank until something happens live.
    seeded.current = true;
    for (const c of cards) prevCardStatus.current.set(c.id, c.status);
    for (const p of personas) prevPersonaFire.current.set(p.name, p.lastFireISO);
    for (const p of personas) prevPersonaStatus.current.set(p.name, p.status);
    for (const h of handoffs) if (h.status === "OK") prevHandoffOk.current.add(hopKey(h.from, h.to, h.evidence));
    for (const r of rows) prevLaneHealth.current.set(r.lane, r.health);
    prevGaming.current = gaming;
    prevPresent.current = present;
    prevBriefMtime.current = data.brief?.mtime_ms ?? null;
    const innerSeed = personas.slice(1);
    innerSeed.forEach((p, i) => {
      const neighbor = innerSeed.length > 1 ? innerSeed[(i + 1) % innerSeed.length] : null;
      const walk = computePurposefulWalk(p.name, Date.now(), cards.length, p.lastFireISO, neighbor?.name ?? null);
      prevWalkBucket.current.set(p.name, walk.bucketKey);
    });
    // I2 seeding: crew-events rows already on the board don't replay as
    // "just happened"; the Scout/Analyst/Treasurer mtime/path trackers start
    // from whatever is currently on the wire.
    seenCrewEventKeys.current = new Set((data.crewEvents ?? []).map(crewEventKey));
    prevScoutMtime.current = personas.find((p) => p.name === "Scout")?.deliverable.mtimeISO ?? null;
    prevAnalystDeskPath.current = data.desks?.Analyst?.path ?? null;
    prevTreasurerDeskPath.current = data.desks?.Treasurer?.path ?? null;
    // (f) seeds "already handled today" from whatever the latest core-
    // decision row already shows -- a page opened AFTER the day's first
    // post-close tick must not re-fire for a transition that happened
    // before this hook ever mounted.
    const seedLatestCore = pickLatestCoreDecision(data);
    if (seedLatestCore && hhmmOf(seedLatestCore.tsEt) >= "15:55") {
      seenPostCloseEtDate.current = etDateOf(seedLatestCore.tsEt);
    }
    events.current = buildSeedEvents(data);
    return events.current;
  }

  // (a)/(b): new idea card, or an existing one's status changing.
  for (const c of cards) {
    const prev = prevCardStatus.current.get(c.id);
    if (prev === undefined) {
      prevCardStatus.current.set(c.id, c.status);
      push(`New idea card -> courier delivers "${truncate(c.title, 42)}" to the ideas wall`);
    } else if (prev !== c.status) {
      prevCardStatus.current.set(c.id, c.status);
      push(`"${truncate(c.title, 34)}" -> ${c.status} -- courier carries it to the board`);
    }
  }

  // (d): a persona's lastFireISO advancing -> it walks in from the hub.
  for (const p of personas) {
    const prev = prevPersonaFire.current.get(p.name);
    if (prev !== undefined && p.lastFireISO && prev !== p.lastFireISO) {
      push(`${p.emoji} ${p.name} fires -> walks in from the hub, working`);
    }
    prevPersonaFire.current.set(p.name, p.lastFireISO);
  }

  // (i) item 2b (LIVE-1, 2026-09-14): a purposeful-walk bucket advancing --
  // the SAME pure decision Scene.tsx independently computes to actually
  // queue the 3D walk (see this hook's own field comment). Neighbor = the
  // next persona in the fixed roster order, wrapping -- identical to
  // Scene.tsx's own convention so the ticker line and the walk it
  // describes always agree on WHO the "neighbour hop" names.
  const innerPersonas = personas.slice(1);
  innerPersonas.forEach((p, i) => {
    const neighbor = innerPersonas.length > 1 ? innerPersonas[(i + 1) % innerPersonas.length] : null;
    const walk = computePurposefulWalk(p.name, Date.now(), cards.length, p.lastFireISO, neighbor?.name ?? null);
    const prevBucket = prevWalkBucket.current.get(p.name);
    if (prevBucket !== undefined && prevBucket !== walk.bucketKey) {
      const destLabel = walk.destination === "ideas-wall" ? "ideas wall" : walk.destination === "core" ? "core" : walk.destination === "neighbor" ? "neighbour" : "lounge";
      push(`${p.emoji} ${p.name} -> ${destLabel}: ${walk.reason}`);
    }
    prevWalkBucket.current.set(p.name, walk.bucketKey);
  });

  // I2 (a)/(b) (INTERACT-2, 2026-09-14): a real crew-events.jsonl row --
  // Chef's own station-verdicts.jsonl scoring, or Coach's sectors.json
  // summary/task-health -- walks that persona to Gamma at the hub (see
  // Scene.tsx/Agent.tsx's eventWalk wiring for the 3D half of this same
  // diff). `seenCrewEventKeys` is null only if this hook somehow reached
  // here before ever seeding (defensive; seeded.current already guards
  // that in practice).
  if (seenCrewEventKeys.current) {
    for (const row of data.crewEvents ?? []) {
      const key = crewEventKey(row);
      if (seenCrewEventKeys.current.has(key)) continue;
      seenCrewEventKeys.current.add(key);
      const hhmm = hhmmOf(row.ts_et) || etHHMM();
      if (row.who === "Chef" && row.kind === "verdict") {
        push(`Chef → Gamma · ${truncate(row.line, 70)} · ${hhmm} ET`);
      } else if (row.who === "Coach" && (row.kind === "sectors" || row.kind === "task_health")) {
        push(`Coach → Gamma · ${truncate(row.line, 70)} · ${hhmm} ET`);
      }
    }
  }

  // I2 (d): Scout's own scout_output.json rewritten -> Scout walks to Pilot
  // with the fresh read. `deliverable.mtimeISO` is the SAME field
  // lib/personas.ts#collectScout already stamps from that exact file's mtime.
  const scoutPersona = personas.find((p) => p.name === "Scout");
  const scoutMtime = scoutPersona?.deliverable.mtimeISO ?? null;
  if (prevScoutMtime.current !== undefined && scoutMtime && prevScoutMtime.current !== scoutMtime) {
    push(`Scout → Pilot · fresh catalyst read · ${etHHMM()} ET`);
  }
  prevScoutMtime.current = scoutMtime;

  // I2 (c): a new Analyst EOD digest -> Analyst walks to Chef with the
  // queue. `desks.Analyst.path` (lib/desk-content.ts) changes to a new
  // dated filename exactly when a new digest lands.
  const analystDeskPath = data.desks?.Analyst?.path ?? null;
  if (prevAnalystDeskPath.current !== undefined && analystDeskPath && prevAnalystDeskPath.current !== analystDeskPath) {
    const firstItem = data.desks?.Analyst?.headline ?? "new digest";
    push(`Analyst → Chef · your queue: ${truncate(firstItem, 60)} · ${etHHMM()} ET`);
  }
  prevAnalystDeskPath.current = analystDeskPath;

  // I2 (e): a new treasury file (dated report or a fresh draft-params-
  // changes.md) -> Treasurer walks to Gamma. `desks.Treasurer.path` picks
  // the newest analysis/treasury/*.md by mtime, so either kind of new file
  // changes it.
  const treasurerDeskPath = data.desks?.Treasurer?.path ?? null;
  if (prevTreasurerDeskPath.current !== undefined && treasurerDeskPath && prevTreasurerDeskPath.current !== treasurerDeskPath) {
    const headline = data.desks?.Treasurer?.headline ?? "new report";
    push(`Treasurer → Gamma · ${truncate(headline, 60)} · ${etHHMM()} ET`);
  }
  prevTreasurerDeskPath.current = treasurerDeskPath;

  // I2 (f): the day's FIRST core-decisions row at/after 15:55 ET -> Pilot
  // walks to Analyst to hand off. Fires at most once per ET calendar day.
  const latestCore = pickLatestCoreDecision(data);
  if (latestCore) {
    const hh = hhmmOf(latestCore.tsEt);
    const d = etDateOf(latestCore.tsEt);
    if (hh >= "15:55" && seenPostCloseEtDate.current !== d) {
      seenPostCloseEtDate.current = d;
      push(`Pilot → Analyst · day's decisions in, handing off · ${etHHMM()} ET`);
    }
  }

  // (c): a handoff hop flipping to OK with new evidence -> HandoffCourier.
  for (const h of handoffs) {
    if (h.status !== "OK") continue;
    const key = hopKey(h.from, h.to, h.evidence);
    if (!prevHandoffOk.current.has(key)) {
      prevHandoffOk.current.add(key);
      push(`${h.from} -> ${h.to}: handoff confirmed, courier carries the folder`);
    }
  }

  // (e): health/status flipping to red -> that agent starts pacing.
  for (const r of rows) {
    const prev = prevLaneHealth.current.get(r.lane);
    prevLaneHealth.current.set(r.lane, r.health);
    if (prev !== undefined && prev !== "red" && r.health === "red") {
      push(`${r.lane} health -> RED, agent pacing`);
    } else if (prev === "red" && r.health !== "red") {
      push(`${r.lane} health recovered -> agent back to work`);
    }
  }
  for (const p of personas) {
    const prev = prevPersonaStatus.current.get(p.name);
    prevPersonaStatus.current.set(p.name, p.status);
    if (prev !== undefined && prev !== "RED" && p.status === "RED") {
      push(`${p.emoji} ${p.name} -> RED, pacing`);
    } else if (prev === "RED" && p.status !== "RED") {
      push(`${p.emoji} ${p.name} recovered from RED`);
    }
  }

  // (f): gaming mode toggling.
  if (prevGaming.current !== null && prevGaming.current !== gaming) {
    push(gaming ? "GPU reserved for J -- everyone freezes" : "Gaming ended -- agents resume");
  }
  prevGaming.current = gaming;

  // (h): a new station-brief mtime -> the all-hands event (Agent.tsx's
  // "allhands" walk, triggered from Scene.tsx off this SAME field). Named
  // here so the ticker says WHY 6 personas just converged on the core,
  // matching the brief's own example line.
  const briefMtime = data.brief?.mtime_ms ?? null;
  if (prevBriefMtime.current !== undefined && briefMtime !== null && prevBriefMtime.current !== briefMtime) {
    // I3 (INTERACT-2, 2026-09-14): reworded to the "who -> action · what ·
    // HH:MM ET" shape every I2 walk line uses now, so the ticker reads as
    // one consistent grammar regardless of which event produced the line.
    push(`Gamma: brief · all-hands ${etHHMM()} ET`);
  }
  prevBriefMtime.current = briefMtime;

  // (g): presence toggling -- the greeter turns to face the room / dims.
  if (prevPresent.current !== null && prevPresent.current !== present) {
    push(present ? "J is here -> greeter turns to the room" : "J stepped away -> night patrol");
  }
  prevPresent.current = present;

  return events.current;
}
