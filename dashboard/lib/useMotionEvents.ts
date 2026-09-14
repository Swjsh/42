"use client";

import { useRef } from "react";
import type { HqApiResponse } from "@/components/hq/types";

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
    // First poll ever: seed every map/set, log nothing.
    seeded.current = true;
    for (const c of cards) prevCardStatus.current.set(c.id, c.status);
    for (const p of personas) prevPersonaFire.current.set(p.name, p.lastFireISO);
    for (const p of personas) prevPersonaStatus.current.set(p.name, p.status);
    for (const h of handoffs) if (h.status === "OK") prevHandoffOk.current.add(hopKey(h.from, h.to, h.evidence));
    for (const r of rows) prevLaneHealth.current.set(r.lane, r.health);
    prevGaming.current = gaming;
    prevPresent.current = present;
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

  // (g): presence toggling -- the greeter turns to face the room / dims.
  if (prevPresent.current !== null && prevPresent.current !== present) {
    push(present ? "J is here -> greeter turns to the room" : "J stepped away -> night patrol");
  }
  prevPresent.current = present;

  return events.current;
}
