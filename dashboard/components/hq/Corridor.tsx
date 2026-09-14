"use client";

interface CorridorProps {
  from: [number, number, number];
  to: [number, number, number];
  freshness: number;
  speedBoost?: number;
  reducedMotion: boolean;
}

/**
 * J 2026-09-14 ~18:15 ET: "the traveling orbs can go too" -- the small
 * floor-hugging pulse sphere that used to travel every hallway (2 hops per
 * lane, 16 orbs in flight at once; the cyan dots on the hallway floors in
 * real capture models-FINAL-preset0-2235.png) is REMOVED. J's standing
 * rule for this world is that the PEOPLE are the motion -- walks with a
 * purpose and a bubble saying what they are doing -- not ambient
 * particles. The props interface is kept so Scene.tsx's call sites (owned
 * by the HALLWAY-FIX pass at the time of this edit) compile untouched; the
 * mounts and this file are deleted together in the PEOPLE pass.
 */
export default function Corridor(props: CorridorProps) {
  void props;
  return null;
}
