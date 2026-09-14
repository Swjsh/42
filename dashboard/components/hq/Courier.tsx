"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { StationIdeaCard } from "@/lib/station";
import { useThrottledFrame } from "./useThrottledFrame";
import { PALETTE } from "./palette";

interface CourierProps {
  cards: StationIdeaCard[];
  hub: [number, number, number];
  wall: [number, number, number];
  reducedMotion: boolean;
}

const REST_OFFSET: [number, number, number] = [1.1, 0, -1.1];
const CARRY_DURATION = 2.4;

/**
 * The one agent that lives at the hub: walks toward the core and carries a
 * small glowing card up to the Ideas wall whenever (a) a NEW idea-card id
 * appears, or (b) an existing card's STATUS changes (J 2026-09-13: a
 * Test/Kill/supported/refuted verdict is a real, nameable event -- routed
 * here rather than to a "lane agent" because StationIdeaCard carries no
 * lane/arm field to attribute a card to one of the sector-row lanes).
 * First snapshot on mount seeds `seenCards` without animating (so page load
 * doesn't fire a burst of carries for every pre-existing card) -- only a
 * genuinely new id or a genuinely changed status after that queues a carry.
 * Simplification: the courier itself stays ground-level and the card
 * visually "rises" the rest of the way to the elevated wall, since a
 * capsule-legged bot climbing there would look wrong.
 */
export default function Courier({ cards, hub, wall, reducedMotion }: CourierProps) {
  const bodyGroup = useRef<THREE.Group>(null);
  const cardMesh = useRef<THREE.Mesh>(null);

  const seenCards = useRef<Map<string, string> | null>(null);
  const queue = useRef<string[]>([]);
  const carrying = useRef(false);
  const carryStart = useRef(0);

  const restWorld: [number, number, number] = [hub[0] + REST_OFFSET[0], hub[1], hub[2] + REST_OFFSET[2]];

  useEffect(() => {
    const seen = seenCards.current;
    if (seen === null) {
      seenCards.current = new Map(cards.map((c) => [c.id, c.status]));
      return;
    }
    for (const c of cards) {
      const prevStatus = seen.get(c.id);
      if (prevStatus === undefined || prevStatus !== c.status) {
        seen.set(c.id, c.status);
        queue.current.push(c.id);
      }
    }
  }, [cards]);

  useThrottledFrame((t) => {
    if (!bodyGroup.current) return;
    if (reducedMotion) {
      bodyGroup.current.position.set(...restWorld);
      if (cardMesh.current) cardMesh.current.visible = false;
      return;
    }

    if (!carrying.current && queue.current.length > 0) {
      carrying.current = true;
      carryStart.current = t;
      queue.current.shift();
    }

    if (carrying.current) {
      const p = Math.min(1, (t - carryStart.current) / CARRY_DURATION);
      const toHub = Math.min(1, p / 0.4);
      bodyGroup.current.position.set(
        restWorld[0] + (hub[0] - restWorld[0]) * toHub,
        restWorld[1],
        restWorld[2] + (hub[2] - restWorld[2]) * toHub,
      );
      if (cardMesh.current) {
        const rise = Math.max(0, (p - 0.3) / 0.7);
        cardMesh.current.visible = p > 0.25;
        cardMesh.current.position.set(
          hub[0] + (wall[0] - hub[0]) * rise,
          hub[1] + 0.3 + (wall[1] - hub[1] - 0.3) * rise,
          hub[2] + (wall[2] - hub[2]) * rise,
        );
      }
      if (p >= 1) {
        carrying.current = false;
        if (cardMesh.current) cardMesh.current.visible = false;
      }
    } else {
      bodyGroup.current.position.set(...restWorld);
    }
  }, 20);

  return (
    <group>
      <group ref={bodyGroup}>
        <mesh position={[0, 0.5, 0]}>
          <capsuleGeometry args={[0.13, 0.3, 4, 8]} />
          <meshLambertMaterial color="#2a2440" />
        </mesh>
        <mesh position={[0, 0.78, 0.08]}>
          <sphereGeometry args={[0.09, 10, 8]} />
          <meshLambertMaterial color="#d68cff" emissive="#d68cff" emissiveIntensity={1.4} toneMapped={false} />
        </mesh>
      </group>
      <mesh ref={cardMesh} visible={false}>
        <boxGeometry args={[0.22, 0.15, 0.02]} />
        <meshBasicMaterial color={PALETTE.hubRing} toneMapped={false} />
      </mesh>
    </group>
  );
}
