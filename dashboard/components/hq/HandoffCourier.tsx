"use client";

import { useEffect, useMemo, useRef } from "react";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import type { Handoff } from "@/lib/personas";
import { useThrottledFrame } from "./useThrottledFrame";
import { PALETTE } from "./palette";

interface HandoffCourierProps {
  handoffs: Handoff[];
  resolvePosition: (label: string) => [number, number, number];
  restPosition: [number, number, number];
  reducedMotion: boolean;
}

const CARRY_DURATION = 2.2;

function hopKey(h: Handoff): string {
  return `${h.from}->${h.to}::${h.evidence}`;
}

/** One STALE/MISSING hop rendered as a dim dashed line + a small red "!"
 * at its midpoint -- always-visible current-state geometry (not
 * diff-triggered like the courier walk below). Only 6 hops exist total, so
 * recomputing this every render is cheap. */
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
 * Handoff walks (Company Mode, 2026-09-13) -- cloned from Courier.tsx's
 * seen-id-diff pattern, pointed at computeHandoffs() instead of idea
 * cards. When a hop flips to OK with a NEW evidence string, one shared
 * courier body walks from that hop's `from` desk to its `to` desk carrying
 * a small glowing folder. STALE/MISSING hops render as a dim dashed link
 * with a red "!" instead (via DashedLink above). First snapshot on mount
 * seeds `seenOk` without animating, matching Courier.tsx's own rule against
 * a burst of walks on page load.
 */
export default function HandoffCourier({ handoffs, resolvePosition, restPosition, reducedMotion }: HandoffCourierProps) {
  const bodyGroup = useRef<THREE.Group>(null);
  const folderMesh = useRef<THREE.Mesh>(null);

  const seenOk = useRef<Set<string> | null>(null);
  const queue = useRef<Array<{ from: [number, number, number]; to: [number, number, number] }>>([]);
  const carrying = useRef(false);
  const carryStart = useRef(0);

  useEffect(() => {
    const okKeys = handoffs.filter((h) => h.status === "OK").map(hopKey);
    const seen = seenOk.current;
    if (seen === null) {
      seenOk.current = new Set(okKeys);
      return;
    }
    for (const h of handoffs) {
      if (h.status !== "OK") continue;
      const key = hopKey(h);
      if (!seen.has(key)) {
        seen.add(key);
        queue.current.push({ from: resolvePosition(h.from), to: resolvePosition(h.to) });
      }
    }
  }, [handoffs, resolvePosition]);

  useThrottledFrame((t) => {
    if (!bodyGroup.current) return;
    if (reducedMotion) {
      bodyGroup.current.position.set(...restPosition);
      if (folderMesh.current) folderMesh.current.visible = false;
      return;
    }

    if (!carrying.current && queue.current.length > 0) {
      carrying.current = true;
      carryStart.current = t;
    }

    if (carrying.current) {
      const hop = queue.current[0];
      const p = Math.min(1, (t - carryStart.current) / CARRY_DURATION);
      bodyGroup.current.position.set(
        hop.from[0] + (hop.to[0] - hop.from[0]) * p,
        0.3 + Math.sin(p * Math.PI) * 0.35,
        hop.from[2] + (hop.to[2] - hop.from[2]) * p,
      );
      if (folderMesh.current) folderMesh.current.visible = true;
      if (p >= 1) {
        carrying.current = false;
        queue.current.shift();
      }
    } else {
      bodyGroup.current.position.set(...restPosition);
      if (folderMesh.current) folderMesh.current.visible = false;
    }
  }, 20);

  const staleMissing = useMemo(() => handoffs.filter((h) => h.status !== "OK"), [handoffs]);

  return (
    <group>
      <group ref={bodyGroup}>
        <mesh position={[0, 0.5, 0]}>
          <capsuleGeometry args={[0.12, 0.28, 4, 8]} />
          <meshLambertMaterial color="#2a4030" />
        </mesh>
        <mesh position={[0, 0.76, 0.08]}>
          <sphereGeometry args={[0.085, 10, 8]} />
          <meshLambertMaterial color="#8cffb0" emissive="#8cffb0" emissiveIntensity={1.3} toneMapped={false} />
        </mesh>
        <mesh ref={folderMesh} position={[0, 0.55, 0.16]} visible={false}>
          <boxGeometry args={[0.18, 0.14, 0.02]} />
          <meshBasicMaterial color={PALETTE.hubRing} toneMapped={false} />
        </mesh>
      </group>

      {staleMissing.map((h) => (
        <DashedLink key={`${h.from}->${h.to}`} from={resolvePosition(h.from)} to={resolvePosition(h.to)} />
      ))}
    </group>
  );
}
