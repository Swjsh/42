"use client";

import { useEffect, useMemo } from "react";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import type { Handoff } from "@/lib/personas";

interface HandoffCourierProps {
  handoffs: Handoff[];
  resolvePosition: (label: string) => [number, number, number];
  // Accepted-but-unused (temporary): Scene.tsx (owned by the WORLD builder,
  // mid-edit as of this commit -- see git status) still calls this component
  // with its PRE-I4 prop shape. Kept optional here so the shared build stays
  // green until the coordinated Scene.tsx edit lands (same pass) and drops
  // these two -- never remove this without also touching that call site.
  restPosition?: [number, number, number];
  reducedMotion?: boolean;
}

/** One STALE/MISSING hop rendered as a dim dashed line + a small red "!"
 * at its midpoint -- always-visible current-state geometry (not
 * diff-triggered like the courier walk used to be). Only 6 hops exist
 * total, so recomputing this every render is cheap. */
function DashedLink({ from, to }: { from: [number, number, number]; to: [number, number, number] }) {
  const mid: [number, number, number] = [(from[0] + to[0]) / 2, 0.3, (from[2] + to[2]) / 2];

  // Built imperatively via <primitive> rather than JSX <line> -- r3f's raw
  // `line` intrinsic collides with @types/react's SVG `<line>` element (the
  // `ref` prop resolves to SVGLineElement and fails to compile). `primitive`
  // takes a pre-constructed THREE.Line, sidestepping the collision entirely.
  const line = useMemo(() => {
    const geometry = new THREE.BufferGeometry();
    const material = new THREE.LineDashedMaterial({
      color: "#4a5a78", dashSize: 0.35, gapSize: 0.25, transparent: true, opacity: 0.55,
    });
    return new THREE.Line(geometry, material);
  }, []);

  useEffect(() => {
    line.geometry.setFromPoints([new THREE.Vector3(...from), new THREE.Vector3(...to)]);
    line.computeLineDistances();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [line, from[0], from[2], to[0], to[2]]);

  return (
    <group>
      <primitive object={line} />
      <Html position={mid} center distanceFactor={9} style={{ pointerEvents: "none" }}>
        <div style={{ color: "#ff3b3b", fontSize: 18, fontWeight: 800, textShadow: "0 0 6px #ff3b3b" }}>!</div>
      </Html>
    </group>
  );
}

/**
 * I4 (INTERACT-2, 2026-09-14): the shared anonymous "courier bot" that used
 * to walk hop-to-hop on every OK handoff is RETIRED -- "people carry their
 * own work now": the real persona whose real event PRODUCES a handoff (a
 * fresh scout_output.json, a new EOD digest, a new treasury file, Chef's own
 * verdict row, Pilot's post-close decision, ...) now walks that same trip
 * itself, driven by the actual event (see lib/useMotionEvents.ts's (a)-(f)
 * ticker lines and Scene.tsx/Agent.tsx's eventWalk wiring). A second,
 * unnamed body making the identical trip on the identical OK-flip would read
 * as a duplicate signal, not a second one -- exactly the "random text with
 * cool graphics" complaint this pass exists to fix, just relocated to a
 * different mover.
 *
 * Only the STALE/MISSING half survives: a hop that ISN'T happening has no
 * persona walk to represent it (nobody carries work that was never done),
 * so the dashed line + "!" stays the one honest way to show "this handoff is
 * not confirmed" -- unchanged geometry/logic from before this pass, just no
 * longer sharing a component with the retired bot.
 */
export default function HandoffCourier({ handoffs, resolvePosition }: HandoffCourierProps) {
  const staleMissing = useMemo(() => handoffs.filter((h) => h.status !== "OK"), [handoffs]);

  return (
    <group>
      {staleMissing.map((h) => (
        <DashedLink key={`${h.from}->${h.to}`} from={resolvePosition(h.from)} to={resolvePosition(h.to)} />
      ))}
    </group>
  );
}
