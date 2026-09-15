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
  /** ROOT-CAUSE FIX (coordinator, 2026-09-15, read at 1:1 from
   * declutter-overview.png): CSS `transform` on a DESCENDANT never resizes
   * an ANCESTOR's own layout box, so `wrapperRef`'s own
   * getBoundingClientRect() never reflected the inner bubble's own
   * bubbleCounterScale transform (bubbleScale.ts) -- at the overview
   * camera that scale grows up to 2.6x to compensate for distance, so the
   * measured rect was far smaller than the real on-screen box and the
   * resolver saw no collision to fix. `measureRef` is the label's own
   * EXISTING inner scaled element (bubbleWrapRef in Agent.tsx/
   * GammaCharacter.tsx/LiveAgents.tsx, plaqueRef in BrainCore.tsx) --
   * transform affects an element's OWN getBoundingClientRect, so reading
   * THIS element gives the true, fully-composed visual box. `wrapperRef`
   * stays the node the manager WRITES the resolved offset onto (an
   * ancestor of `measureRef`, so the offset composes correctly with
   * whatever scale `measureRef` already carries). */
  measureRef: RefObject<HTMLDivElement | null>;
  /** Called at most once per throttled tick -- return this label's CURRENT
   * world position (a moving character's group.position, or a fixed
   * literal for a static plaque). Never cached across ticks by the
   * registry itself, since walking characters move continuously. */
  getWorldPos: () => THREE.Vector3 | [number, number, number];
  /** Local, per-label smoothing state -- the manager owns writing this, no
   * caller ever reads or sets it. Kept ON the registry entry (not a
   * separate Map keyed by id) so a label that unmounts and remounts under
   * the same id starts fresh rather than inheriting stale smoothing.
   * Tracks BOTH axes -- see labelDeclutter.ts's own header for why a label
   * is nudged along exactly one axis at a time (the other always stays 0). */
  lastLocalDx: number;
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
 * never correct. Returns `{ wrapperRef, measureRef }`: `wrapperRef` is a
 * NEW outer `<div>` the caller wraps around its existing bubble/plaque
 * JSX (the manager writes offset/opacity here); `measureRef` must be
 * attached to that SAME existing inner element that already carries the
 * label's own camera-distance scale/fade (bubbleWrapRef/plaqueRef) -- see
 * `RegisteredLabel.measureRef`'s own comment for why the manager reads
 * size from there, not from `wrapperRef`.
 */
export function useLabelDeclutter(
  id: string,
  priority: number,
  getWorldPos: () => THREE.Vector3 | [number, number, number],
): { wrapperRef: RefObject<HTMLDivElement | null>; measureRef: RefObject<HTMLDivElement | null> } {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const measureRef = useRef<HTMLDivElement | null>(null);
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
      measureRef,
      getWorldPos: () => getWorldPosRef.current(),
      lastLocalDx: 0,
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

  return { wrapperRef, measureRef };
}

/** Small helper: attaches BOTH `a` and `b` (React refs of the SAME
 * underlying type) to one DOM node via a single callback ref -- every
 * `measureRef` from `useLabelDeclutter` must point at the SAME element as
 * the caller's own existing scale/fade ref (bubbleWrapRef/plaqueRef), and
 * a plain JSX element can only take one `ref` prop. */
export function mergeRefs<T>(a: RefObject<T | null>, b: RefObject<T | null>): (el: T | null) => void {
  return (el) => {
    a.current = el;
    b.current = el;
  };
}
