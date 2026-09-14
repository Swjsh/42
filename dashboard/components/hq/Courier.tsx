"use client";

import type { StationIdeaCard } from "@/lib/station";

interface CourierProps {
  cards: StationIdeaCard[];
  hub: [number, number, number];
  wall: [number, number, number];
  reducedMotion: boolean;
}

/**
 * J 2026-09-14 ~18:15 ET: "the traveling orbs can go too" -- the hub's
 * anonymous courier bot (capsule body + emissive purple head sphere) and the
 * glowing card orb it floated up to the smart board on every idea-card
 * status change are REMOVED. Card events still reach the world through
 * Chef's own bubble/exchange (crew-events `verdict` rows -> Scene.tsx's hub
 * exchange) and the smart board's own content -- the event is not lost,
 * only the orb. Props kept so Scene.tsx's mount (owned by the HALLWAY-FIX
 * pass at the time of this edit) compiles untouched; mount + file go in
 * the PEOPLE pass.
 */
export default function Courier(props: CourierProps) {
  void props;
  return null;
}
