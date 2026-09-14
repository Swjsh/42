"use client";

import { useRef } from "react";
import type { HqApiResponse } from "@/components/hq/types";
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
    push("Station brief -> all hands at the core");
  }
  prevBriefMtime.current = briefMtime;

  // (g): presence toggling -- the greeter turns to face the room / dims.
  if (prevPresent.current !== null && prevPresent.current !== present) {
    push(present ? "J is here -> greeter turns to the room" : "J stepped away -> night patrol");
  }
  prevPresent.current = present;

  return events.current;
}
