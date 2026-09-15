"use client";

// ─── Screen-space label declutter -- registration half ────────────────────
// See labelDeclutter.ts's own header for the root cause + algorithm. This
// file is the wiring: a module-scope registry every Html label producer
// (Agent.tsx, GammaCharacter.tsx, LiveAgents.tsx, BrainCore.tsx) joins
// through ONE hook, plus the resolver that actually walks the registry each
// throttled tick (mounted once, LabelDeclutterManager.tsx). A module-scope
// Map (not React context) -- the SAME "every mounted instance shares one
// variable" convention Agent.tsx's own `lastGlobalWalkStartT` already uses
// for its cross-agent walk stagger -- because labels mount/unmount
// independently (a live agent despawning, a persona's showAgent flag) and a
// context provider would need every consumer to be inside the SAME
// <Canvas> subtree the manager is, which is already true here but adds a
// re-render on every registry change for zero benefit (the manager reads
// the registry imperatively inside a throttled frame, never via React
// state).

import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import * as THREE from "three";
import { PRIORITY } from "./labelDeclutter";

export type LabelPriority = (typeof PRIORITY)[keyof typeof PRIORITY];

export interface RegisteredLabel {
  id: string;
  priority: number;
  /** Wrapper div this label's caller renders as a NEW outer node around its
   * existing bubble/plaque markup -- the declutter manager mutates ONLY
   * this element's own `transform`/`opacity`, never touching whatever the
   * label's own inner markup already does (camera-distance scale/fade stay
   * exactly as each file already implements them, on an INNER node). */
  wrapperRef: RefObject<HTMLDivElement | null>;
  /** Called at most once per throttled tick -- return this label's CURRENT
   * world position (a moving character's group.position, or a fixed
   * literal for a static plaque). Never cached across ticks by the
   * registry itself, since walking characters move continuously. */
  getWorldPos: () => THREE.Vector3 | [number, number, number];
  /** Local, per-label smoothing state -- the manager owns writing this, no
   * caller ever reads or sets it. Kept ON the registry entry (not a
   * separate Map keyed by id) so a label that unmounts and remounts under
   * the same id starts fresh rather than inheriting stale smoothing. */
  lastLocalDy: number;
}

const registry = new Map<string, RegisteredLabel>();

/** Read-only snapshot for the manager -- returns the live Map (not a copy,
 * the manager runs inside the same module, this is just for clarity of
 * intent at the one call site that iterates it). */
export function getLabelRegistry(): ReadonlyMap<string, RegisteredLabel> {
  return registry;
}

/**
 * Registers ONE label with the shared declutter system for the lifetime of
 * the calling component. `id` MUST be stable across renders of the same
 * logical label (a persona name, a live-agent id, "gamma", "brain-plaque")
 * -- a changing id looks like a despawn+respawn to the resolver, which is
 * harmless (just loses that one label's smoothing state for a tick) but
 * never correct. Returns the wrapper ref the caller must attach to a NEW
 * outer `<div>` wrapping its existing bubble/plaque JSX -- see this file's
 * own header for why that has to be a separate node from any existing
 * camera-distance scale/fade wrapper.
 */
export function useLabelDeclutter(
  id: string,
  priority: number,
  getWorldPos: () => THREE.Vector3 | [number, number, number],
): RefObject<HTMLDivElement | null> {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  // Refs so the registered closure always calls the LATEST getWorldPos/
  // priority without re-registering every render (a walking character's
  // getWorldPos closes over a `group` ref that never changes identity, but
  // a persona's bubblePriority could in principle -- defensive either way).
  const getWorldPosRef = useRef(getWorldPos);
  getWorldPosRef.current = getWorldPos;
  const priorityRef = useRef(priority);
  priorityRef.current = priority;

  useEffect(() => {
    const entry: RegisteredLabel = {
      id,
      get priority() {
        return priorityRef.current;
      },
      wrapperRef,
      getWorldPos: () => getWorldPosRef.current(),
      lastLocalDy: 0,
    };
    registry.set(id, entry);
    return () => {
      // Only clear if WE are still the registered owner of this id -- a
      // fast unmount/remount under the same id (React strict-mode double-
      // invoke, or a key change) could otherwise have the OLD effect's
      // cleanup delete the NEW effect's already-registered entry.
      if (registry.get(id) === entry) registry.delete(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  return wrapperRef;
}
